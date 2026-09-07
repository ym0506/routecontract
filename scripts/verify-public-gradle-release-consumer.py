#!/usr/bin/env python3
"""Consume a reviewed stable 0.1.3+ release from anonymous Maven Central with Gradle.

No publication, local installation, source build or unavailable-version fallback occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

GROUP = 'io.github.ym0506.routecontract'
MODULE = 'routecontract-shardingsphere-5.5'
SUITE = 'io.github.ym0506.routecontract.consumer.PublicReleaseMySqlTest'
JUNIT_NAME = f'TEST-{SUITE}.xml'
TEST_NAMES = {'selectedRuntimeApiOriginsAndAutoDiscoveredHookAreTheExpectedJarBytes',
              'captureAndCaptureResultMatchTheReviewedSchemaOneBaseline',
              'sameBusinessRowWithTwoAttemptsFailsPolicyAndSeparateJvmCli'}
NAMESPACE = 'https://schema.gradle.org/dependency-verification'
CENTRAL = 'https://repo.maven.apache.org/maven2'


class PublicConsumerError(RuntimeError):
    """The independent public consumer did not establish the required evidence."""


def load_helper():
    name = '_routecontract_public_release_artifacts_gradle'
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name('public_release_artifacts.py'))
    if spec is None or spec.loader is None:
        raise PublicConsumerError('Required reviewed release receipt helper is unavailable')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PUBLIC = load_helper()


def versioned_lock(original: str, version: str) -> str:
    PUBLIC.stable_version(version)
    if any(line.startswith(GROUP + ':') for line in original.splitlines()):
        raise PublicConsumerError('Standalone source lock must not contain unreviewed first-party coordinates')
    if not original.endswith('\n') or sum(line.startswith('empty=') for line in original.splitlines()) != 1:
        raise PublicConsumerError('Expected the complete reviewed standalone lock')
    return original + f'{GROUP}:{MODULE}:{version}=reviewedReleaseMetadata,testCompileClasspath,testRuntimeClasspath\n'


def prepare_metadata(source: Path, destination: Path, receipt: dict) -> None:
    receipt = PUBLIC.validate_consumer_receipt(receipt)
    tree = ET.parse(source)
    root = tree.getroot()
    configuration = root.find(f'{{{NAMESPACE}}}configuration')
    if configuration is None or configuration.findtext(f'{{{NAMESPACE}}}verify-metadata') != 'true':
        raise PublicConsumerError('Reviewed metadata must verify artifact metadata')
    # The legacy installer owns its exemption. This public consumer removes all exemptions.
    for trusted in list(configuration.findall(f'{{{NAMESPACE}}}trusted-artifacts')):
        configuration.remove(trusted)
    components = root.find(f'{{{NAMESPACE}}}components')
    if components is None:
        raise PublicConsumerError('Reviewed third-party verification metadata is absent')
    for component in list(components):
        if component.get('group') == GROUP:
            components.remove(component)
    component = ET.SubElement(components, f'{{{NAMESPACE}}}component',
                              {'group': GROUP, 'name': MODULE, 'version': receipt['routeContractVersion']})
    for item in receipt['artifacts']:
        artifact = ET.SubElement(component, f'{{{NAMESPACE}}}artifact', {'name': item['name']})
        ET.SubElement(artifact, f'{{{NAMESPACE}}}sha256', {
            'value': item['sha256'], 'origin': 'Reviewed expected-byte receipt; not publisher authentication'})
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.register_namespace('', NAMESPACE)
    tree.write(destination, encoding='UTF-8', xml_declaration=True)


def copy_consumer(root: Path, consumer: Path, receipt: dict) -> None:
    receipt = PUBLIC.validate_consumer_receipt(receipt)
    fixture = root / 'examples/public-gradle-release-consumer'
    legacy = root / 'examples/standalone-consumer'
    consumer.mkdir()
    for name in ('settings.gradle', 'build.gradle'):
        shutil.copy2(fixture / name, consumer / name)
    shutil.copytree(fixture / 'src', consumer / 'src')
    (consumer / 'gradle.lockfile').write_text(versioned_lock(
        (legacy / 'gradle.lockfile').read_text(encoding='utf-8'), receipt['routeContractVersion']), encoding='utf-8')
    shutil.copy2(root / 'gradlew', consumer / 'gradlew')
    shutil.copytree(root / 'gradle/wrapper', consumer / 'gradle/wrapper')
    prepare_metadata(legacy / 'gradle/verification-metadata.xml',
                     consumer / 'gradle/verification-metadata.xml', receipt)


def gradle_arguments(consumer: Path, receipt: dict) -> list[str]:
    receipt = PUBLIC.validate_consumer_receipt(receipt)
    args = [str(consumer / 'gradlew'), '--no-daemon', '--no-build-cache', '--no-configuration-cache',
            '--dependency-verification=strict', '--console=plain',
            f'-ProutecontractVersion={receipt["routeContractVersion"]}']
    for item in receipt['artifacts']:
        extension = item['name'].rsplit('.', 1)[1]
        args.append(f'-ProutecontractSha256.{extension}={item["sha256"]}')
    return args


def clean_environment(cache: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith(('ORG_GRADLE_PROJECT_', 'ROUTECONTRACT_')) or name in (
                'GRADLE_OPTS', 'GRADLE_RO_DEP_CACHE', 'JAVA_OPTS', 'JAVA_TOOL_OPTIONS',
                'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
            environment.pop(name, None)
    environment['GRADLE_USER_HOME'] = str(cache)
    return environment


def run(command: list[str], cwd: Path, environment: dict[str, str], log: Path) -> str:
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT, timeout=1200)
    if result.returncode:
        raise PublicConsumerError(f'Public Gradle consumer exited {result.returncode}; inspect {log}')
    return log.read_text(encoding='utf-8', errors='replace')


def retain_evidence(consumer: Path, evidence: Path) -> None:
    for source, name in ((consumer / 'build/test-results/test', 'junit'),
                         (consumer / 'build/routecontract-consumer-evidence', 'reports')):
        if source.is_dir():
            shutil.copytree(source, evidence / name, dirs_exist_ok=True)
    for source, name in ((consumer / 'gradle.lockfile', 'gradle.lockfile'),
                         (consumer / 'gradle/verification-metadata.xml', 'verification-metadata.xml'),
                         (consumer / 'build.gradle', 'consumer-build.gradle'),
                         (consumer / 'settings.gradle', 'consumer-settings.gradle')):
        if source.is_file():
            shutil.copy2(source, evidence / name)


def verify_junit(path: Path) -> dict:
    try:
        suite = ET.parse(path).getroot()
        counts = {name: int(suite.attrib[name]) for name in ('tests', 'failures', 'errors', 'skipped')}
    except (OSError, ET.ParseError, KeyError, ValueError) as error:
        raise PublicConsumerError('Public consumer JUnit evidence is missing or malformed') from error
    if suite.tag != 'testsuite' or suite.get('name') != SUITE or counts != {
            'tests': 3, 'failures': 0, 'errors': 0, 'skipped': 0}:
        raise PublicConsumerError('Exactly three successful real MySQL tests are required')
    cases = suite.findall('testcase')
    if len(cases) != 3 or {case.get('name', '').removesuffix('()') for case in cases} != TEST_NAMES or any(
            case.find(kind) is not None for case in cases for kind in ('failure', 'error', 'skipped')):
        raise PublicConsumerError('JUnit testcase entries must prove three distinct successful tests')
    return counts


def verify(root: Path, receipt_path: Path, evidence: Path) -> dict:
    root = root.resolve()
    receipt = PUBLIC.load_consumer_receipt(receipt_path)
    normalized = (json.dumps(receipt, indent=2) + '\n').encode('utf-8')
    if evidence.exists() or evidence.is_symlink():
        raise PublicConsumerError('Choose a new public release evidence directory')
    evidence = evidence.resolve()
    if evidence.is_relative_to(root):
        raise PublicConsumerError('Public evidence must be outside the checkout')
    with tempfile.TemporaryDirectory(prefix='routecontract-public-gradle-release-') as directory:
        temporary = Path(directory).resolve()
        if temporary.is_relative_to(root):
            raise PublicConsumerError('Public temporary directory must be outside the checkout')
        consumer, cache = temporary / 'consumer', temporary / 'gradle-home'
        if consumer.exists() or consumer.is_symlink() or cache.exists() or cache.is_symlink():
            raise PublicConsumerError('Consumer and dependency cache must start absent')
        evidence.mkdir(parents=True)
        (evidence / 'reviewed-receipt.json').write_bytes(normalized)
        copy_consumer(root, consumer, receipt)
        if PUBLIC.load_consumer_receipt(receipt_path) != receipt:
            raise PublicConsumerError('Reviewed receipt changed before public consumption')
        print(f'Checking public Gradle release {receipt["routeContractVersion"]} with a fresh cache...', flush=True)
        try:
            output = run([*gradle_arguments(consumer, receipt), 'clean', 'check'], consumer,
                         clean_environment(cache), evidence / 'gradle.log')
        finally:
            retain_evidence(consumer, evidence)
        markers = [f'ROUTECONTRACT_PUBLIC_RELEASE_GRAPH_VERIFIED version={receipt["routeContractVersion"]} runtime=5.5.3 payloads=3',
                   f'ROUTECONTRACT_PUBLIC_SINGLE_MYSQL_VERIFIED version={receipt["routeContractVersion"]} runtime=5.5.3 baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2']
        if any(marker not in output for marker in markers):
            raise PublicConsumerError('Public consumer omitted required graph, MySQL or CLI evidence')
        counts = verify_junit(consumer / 'build/test-results/test' / JUNIT_NAME)
    if PUBLIC.load_consumer_receipt(receipt_path) != receipt:
        raise PublicConsumerError('Reviewed receipt changed during public consumption')
    summary = {'formatVersion': 1, 'routeContractVersion': receipt['routeContractVersion'],
               'normalizedReviewedReceiptSha256': hashlib.sha256(normalized).hexdigest(),
               'buildTool': 'Gradle', 'runtime': '5.5.3', 'junit': counts,
               'configuredRepository': CENTRAL, 'publicRepositoryConsumptionVerified': True,
               'evidenceLabel': 'verified - MySQL',
               'transportBoundary': 'Gradle final redirect origins are not independently constrained; require separate redirect-rejecting public-byte readback',
               'boundary': 'SQLExecutionHook-reported physical JDBC execution attempts; not a complete route plan or business success'}
    (evidence / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print('ROUTECONTRACT_PUBLIC_GRADLE_RELEASE_CONSUMER_VERIFIED mysqlTests=3 publicConsumption=true')
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        verify(Path(__file__).resolve().parents[1], args.receipt.expanduser().absolute(),
               args.evidence_directory.expanduser().absolute())
        return 0
    except (PublicConsumerError, PUBLIC.ReceiptError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'PUBLIC_GRADLE_RELEASE_CONSUMER_FAILED: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
