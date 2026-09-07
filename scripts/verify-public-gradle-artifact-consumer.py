#!/usr/bin/env python3
"""Verify reviewed split-artifact release bytes with anonymous public Gradle consumers.

This command never installs or publishes RouteContract. A missing public version must fail.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PUBLIC_REPOSITORY = 'https://repo.maven.apache.org/maven2'
GROUP = 'io.github.ym0506.routecontract'
STAGED_VERSION = '0.2.0'
LANES = {'5.5.2': 'routecontract-shardingsphere-5.5.2', '5.5.3': 'routecontract-shardingsphere-5.5'}
STABLE_VERSION = re.compile(r'0\.2\.(?:0|[1-9][0-9]*)\Z')


class PublicConsumerError(RuntimeError):
    """Public consumption did not produce the required evidence."""


def load_tool(name: str, filename: str):
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PublicConsumerError(f'Cannot load required consumer helper: {filename}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


STAGED = load_tool('_routecontract_staged_consumer_public', 'verify-staged-split-artifact-consumer.py')


def versioned_lock(original: str, version: str, adapter: str) -> str:
    if not STABLE_VERSION.fullmatch(version):
        raise PublicConsumerError('Expected a strict stable 0.2.x receipt version')
    expected = {'routecontract-core', adapter}
    seen = set()
    result = []
    for line in original.splitlines(keepends=True):
        if line.startswith(GROUP + ':'):
            coordinate, separator, configurations = line.partition('=')
            parts = coordinate.split(':')
            if (not separator or len(parts) != 3 or parts[0] != GROUP
                    or parts[1] not in expected or parts[1] in seen or parts[2] != STAGED_VERSION):
                raise PublicConsumerError('First-party lock coordinates differ from the reviewed staged fixture')
            seen.add(parts[1])
            line = f'{GROUP}:{parts[1]}:{version}={configurations}'
        result.append(line)
    if seen != expected:
        raise PublicConsumerError('The reviewed lock must include exactly core and the selected adapter')
    return ''.join(result)


def copy_public_consumer(root: Path, consumer: Path, runtime: str, receipt: dict) -> None:
    if runtime not in LANES:
        raise PublicConsumerError('Expected exact ShardingSphere 5.5.2 or 5.5.3')
    fixture = root / 'examples/staged-split-artifact-consumer'
    consumer.mkdir()
    for filename in ('settings.gradle', 'build.gradle'):
        shutil.copy2(fixture / filename, consumer / filename)
    shutil.copytree(fixture / 'src', consumer / 'src')
    original = (fixture / 'gradle-locks' / f'{runtime}.lockfile').read_text(encoding='utf-8')
    (consumer / 'gradle.lockfile').write_text(
        versioned_lock(original, receipt['routeContractVersion'], LANES[runtime]), encoding='utf-8')
    shutil.copy2(root / 'gradlew', consumer / 'gradlew')
    shutil.copytree(root / 'gradle/wrapper', consumer / 'gradle/wrapper')
    STAGED.prepare_metadata(root / 'gradle/verification-metadata.xml',
                            consumer / 'gradle/verification-metadata.xml', receipt)


def gradle_arguments(consumer: Path, runtime: str, receipt: dict) -> list[str]:
    version = receipt['routeContractVersion']
    if not STABLE_VERSION.fullmatch(version) or runtime not in LANES:
        raise PublicConsumerError('Invalid public consumer version/runtime')
    args = [str(consumer / 'gradlew'), '--no-daemon', '--no-build-cache',
            '--no-configuration-cache', '--dependency-verification=strict', '--console=plain',
            '-ProutecontractPublicConsumer=true', f'-ProutecontractVersion={version}',
            f'-ProutecontractRuntime={runtime}']
    for module in ('routecontract-core', LANES[runtime]):
        items = [item for item in receipt['artifacts']
                 if item['module'] == module and item['name'] == f'{module}-{version}.jar']
        if len(items) != 1 or not re.fullmatch(r'[0-9a-f]{64}', items[0]['sha256']):
            raise PublicConsumerError('The validated receipt must identify each selected JAR exactly once')
        args.append(f'-ProutecontractSha256.{module}={items[0]["sha256"]}')
    return args



def public_environment(cache: Path) -> dict[str, str]:
    environment = STAGED.clean_environment(cache)
    # Gradle reads this separate shared cache independently of GRADLE_USER_HOME.
    environment.pop('GRADLE_RO_DEP_CACHE', None)
    return environment


def verify_lane(root: Path, temporary: Path, evidence: Path, runtime: str, receipt: dict) -> dict:
    consumer = temporary / f'consumer-{runtime}'
    cache = temporary / f'gradle-home-{runtime}'
    if consumer.exists() or consumer.is_symlink() or cache.exists() or cache.is_symlink():
        raise PublicConsumerError('Each public lane must start with a new consumer and absent dependency cache')
    lane = evidence / runtime
    lane.mkdir()
    copy_public_consumer(root, consumer, runtime, receipt)
    args = gradle_arguments(consumer, runtime, receipt)
    environment = public_environment(cache)
    print(f'Checking anonymous public Gradle consumer {runtime} from Maven Central...', flush=True)
    try:
        output = STAGED.run([*args, 'clean', 'check'], consumer, environment, lane / 'gradle.log')
    finally:
        STAGED.retain_lane_evidence(consumer, lane)
    markers = [f'ROUTECONTRACT_PUBLIC_GRAPH_VERIFIED version={runtime} artifacts=2 ',
               f'ROUTECONTRACT_PUBLIC_NEGATIVES_VERIFIED version={runtime} cases=5',
               f'ROUTECONTRACT_STAGED_SPLIT_MYSQL_VERIFIED version={runtime} baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2']
    if any(marker not in output for marker in markers):
        raise PublicConsumerError('Public consumer omitted required graph, negative or real-MySQL evidence')
    counts = STAGED.verify_junit(consumer / 'build/test-results/test' / STAGED.JUNIT_NAME)
    return {'runtime': runtime, 'adapter': LANES[runtime], 'junit': counts, 'negativeGraphCases': 5,
            'configuredRepository': PUBLIC_REPOSITORY, 'distributionEvidence': 'anonymous-public-repository',
            'evidenceLabel': 'verified - MySQL'}


def verify(root: Path, receipt_path: Path, evidence: Path) -> dict:
    public = load_tool('_routecontract_public_split_artifacts_gradle', 'public_split_artifacts.py')
    receipt = public.load_consumer_receipt(receipt_path)
    reviewed_bytes = (json.dumps(receipt, indent=2) + '\n').encode('utf-8')
    receipt_hash = hashlib.sha256(reviewed_bytes).hexdigest()
    # The shared validator owns the complete nine-payload schema and path validation.
    # This additional check protects direct preparer calls and keeps the fixture's version boundary explicit.
    if not STABLE_VERSION.fullmatch(receipt['routeContractVersion']):
        raise PublicConsumerError('The public Gradle lane accepts only strict stable 0.2.x receipts')
    if evidence.exists() or evidence.is_symlink():
        raise PublicConsumerError('Choose a new public-consumer evidence directory')
    evidence.mkdir(parents=True)
    (evidence / 'reviewed-receipt.json').write_bytes(reviewed_bytes)
    with tempfile.TemporaryDirectory(prefix='routecontract-public-gradle-consumer-') as directory:
        temporary = Path(directory).resolve()
        lanes = []
        for runtime in LANES:
            if public.load_consumer_receipt(receipt_path) != receipt:
                raise PublicConsumerError('Reviewed receipt changed during public consumption')
            lanes.append(verify_lane(root, temporary, evidence, runtime, receipt))
    if public.load_consumer_receipt(receipt_path) != receipt:
        raise PublicConsumerError('Reviewed receipt changed during public consumption')
    summary = {'formatVersion': 1, 'routeContractVersion': receipt['routeContractVersion'],
               'normalizedReviewedReceiptSha256': receipt_hash, 'configuredRepository': PUBLIC_REPOSITORY,
               'transportBoundary': 'Gradle redirect behavior is not independently constrained; require the separate redirect-rejecting public-byte readback',
               'publicRepositoryConsumptionVerified': True, 'buildTool': 'Gradle', 'lanes': lanes,
               'boundary': 'ShardingSphere SQLExecutionHook-reported physical JDBC execution attempts; not a complete route plan or business success'}
    (evidence / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print('ROUTECONTRACT_PUBLIC_GRADLE_CONSUMER_VERIFIED lanes=2 mysqlTests=6 negativeGraphCases=10 publicConsumption=true')
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    # Helper validation remains authoritative; all receipt validation completes before any network run.
    public = load_tool('_routecontract_public_split_artifacts_gradle', 'public_split_artifacts.py')
    try:
        verify(root, args.receipt.expanduser().absolute(), args.evidence_directory.expanduser().absolute())
        return 0
    except (PublicConsumerError, public.ReceiptError, STAGED.VerificationError,
            OSError, KeyError, ValueError, subprocess.SubprocessError) as error:
        print(f'PUBLIC_GRADLE_CONSUMER_FAILED: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
