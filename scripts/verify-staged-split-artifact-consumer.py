#!/usr/bin/env python3
"""Run independent real-MySQL consumers against supplied local staged 0.2 bytes.

This never builds/publishes RouteContract and never claims public repository availability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

GROUP = 'io.github.ym0506.routecontract'
GROUP_PATH = Path('io/github/ym0506/routecontract')
VERSION = '0.2.0'
MODULES = ('routecontract-core', 'routecontract-shardingsphere-5.5', 'routecontract-shardingsphere-5.5.2')
LANES = {'5.5.2': MODULES[2], '5.5.3': MODULES[1]}
NAMESPACE = 'https://schema.gradle.org/dependency-verification'
JUNIT_NAME = 'TEST-io.github.ym0506.routecontract.consumer.StagedArtifactMySqlTest.xml'
TIMEOUT_SECONDS = 1200


class VerificationError(RuntimeError):
    """Required staged-consumer evidence is missing or inconsistent."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repository_receipt(repository: Path) -> dict:
    artifacts = []
    for module in MODULES:
        directory = GROUP_PATH / module / VERSION
        for extension in ('jar', 'pom', 'module'):
            relative = directory / f'{module}-{VERSION}.{extension}'
            cursor = repository
            for component in relative.parts:
                cursor = cursor / component
                try:
                    attributes = cursor.lstat()
                except OSError as error:
                    raise VerificationError(f'Staged coordinate is incomplete: {relative}') from error
                if stat.S_ISLNK(attributes.st_mode):
                    raise VerificationError(f'Staged paths must not be symlinks: {relative}')
            if not stat.S_ISREG(attributes.st_mode):
                raise VerificationError(f'Staged payload is not a regular file: {relative}')
            artifacts.append({'module': module, 'name': relative.name,
                              'relativePath': relative.as_posix(), 'sha256': sha256(repository / relative)})
    return {'formatVersion': 1, 'routeContractVersion': VERSION, 'artifacts': artifacts}


def verify_receipt(repository: Path, expected: dict) -> None:
    if repository_receipt(repository) != expected:
        raise VerificationError('Staged artifacts changed during consumer verification')


def prepare_metadata(source: Path, destination: Path, receipt: dict) -> None:
    tree = ET.parse(source)
    root = tree.getroot()
    configuration = root.find(f'{{{NAMESPACE}}}configuration')
    if configuration is None or configuration.findtext(f'{{{NAMESPACE}}}verify-metadata') != 'true':
        raise VerificationError('The supplied trust metadata must verify artifact metadata')
    if configuration.find(f'{{{NAMESPACE}}}trusted-artifacts') is not None:
        raise VerificationError('This fixture does not accept artifact trust bypasses')
    components = root.find(f'{{{NAMESPACE}}}components')
    if components is None:
        raise VerificationError('The supplied trust metadata has no components')
    for component in list(components):
        if component.get('group') == GROUP:
            components.remove(component)
    for module in MODULES:
        component = ET.SubElement(components, f'{{{NAMESPACE}}}component',
                                  {'group': GROUP, 'name': module, 'version': VERSION})
        for payload in receipt['artifacts']:
            if payload['module'] == module:
                artifact = ET.SubElement(component, f'{{{NAMESPACE}}}artifact', {'name': payload['name']})
                ET.SubElement(artifact, f'{{{NAMESPACE}}}sha256', {
                    'value': payload['sha256'], 'origin': 'Supplied local staged-byte receipt; not public publisher provenance'})
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.register_namespace('', NAMESPACE)
    tree.write(destination, encoding='UTF-8', xml_declaration=True)


def verify_junit(path: Path) -> dict:
    try:
        suite = ET.parse(path).getroot()
        counts = {key: int(suite.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
    except (OSError, ET.ParseError, KeyError, ValueError) as error:
        raise VerificationError('Consumer JUnit evidence is missing or malformed') from error
    if counts != {'tests': 3, 'failures': 0, 'errors': 0, 'skipped': 0}:
        raise VerificationError(f'All three consumer tests must run and pass: {counts}')
    cases = suite.findall('testcase')
    if len(cases) != 3 or any(case.find(kind) is not None for case in cases for kind in ('failure', 'error', 'skipped')):
        raise VerificationError('Consumer JUnit testcase entries do not prove three successful tests')
    return counts


def clean_environment(gradle_home: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith('ORG_GRADLE_PROJECT_') or name in (
                'GRADLE_OPTS', 'JAVA_OPTS', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
            environment.pop(name, None)
    environment['GRADLE_USER_HOME'] = str(gradle_home)
    return environment


def run(command: list[str], cwd: Path, environment: dict[str, str], log: Path) -> str:
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT, timeout=TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise VerificationError(f'Consumer command failed with exit {result.returncode}; inspect {log}')
    return log.read_text(encoding='utf-8', errors='replace')


def retain_lane_evidence(consumer: Path, destination: Path) -> None:
    for source, name in ((consumer / 'build/test-results/test', 'junit'),
                         (consumer / 'build/routecontract-consumer-evidence', 'reports')):
        if source.is_dir():
            shutil.copytree(source, destination / name, dirs_exist_ok=True)
    for source, name in ((consumer / 'gradle.lockfile', 'gradle.lockfile'),
                         (consumer / 'gradle/verification-metadata.xml', 'verification-metadata.xml'),
                         (consumer / 'build.gradle', 'consumer-build.gradle'),
                         (consumer / 'settings.gradle', 'consumer-settings.gradle')):
        if source.is_file():
            shutil.copy2(source, destination / name)


def copy_consumer(root: Path, destination: Path, runtime: str, receipt: dict) -> None:
    fixture = root / 'examples/staged-split-artifact-consumer'
    destination.mkdir()
    for name in ('settings.gradle', 'build.gradle'):
        shutil.copy2(fixture / name, destination / name)
    shutil.copytree(fixture / 'src', destination / 'src')
    shutil.copy2(fixture / 'gradle-locks' / f'{runtime}.lockfile', destination / 'gradle.lockfile')
    shutil.copy2(root / 'gradlew', destination / 'gradlew')
    shutil.copytree(root / 'gradle/wrapper', destination / 'gradle/wrapper')
    prepare_metadata(root / 'gradle/verification-metadata.xml',
                     destination / 'gradle/verification-metadata.xml', receipt)


def verify_lane(root: Path, temporary: Path, evidence: Path, repository: Path,
                runtime: str, adapter: str, receipt: dict) -> dict:
    consumer = temporary / f'consumer-{runtime}'
    cache = temporary / f'gradle-home-{runtime}'
    copy_consumer(root, consumer, runtime, receipt)
    if cache.exists():
        raise VerificationError('Consumer dependency cache must start absent')
    lane_evidence = evidence / runtime
    lane_evidence.mkdir()
    environment = clean_environment(cache)
    arguments = [str(consumer / 'gradlew'), '--no-daemon', '--no-build-cache',
                 '--no-configuration-cache', '--dependency-verification=strict', '--console=plain',
                 f'-ProutecontractRuntime={runtime}', f'-ProutecontractRepository={repository}']
    for module in ('routecontract-core', adapter):
        digest = next(item['sha256'] for item in receipt['artifacts']
                      if item['module'] == module and item['name'].endswith('.jar'))
        arguments.append(f'-ProutecontractSha256.{module}={digest}')
    verify_receipt(repository, receipt)
    print(f'Checking staged {runtime} consumer with a fresh dependency cache...', flush=True)
    try:
        output = run([*arguments, 'clean', 'check'], consumer, environment, lane_evidence / 'gradle.log')
    finally:
        retain_lane_evidence(consumer, lane_evidence)
    markers = [f'ROUTECONTRACT_STAGED_GRAPH_VERIFIED version={runtime} artifacts=2 ',
               f'ROUTECONTRACT_STAGED_NEGATIVES_VERIFIED version={runtime} cases=5',
               f'ROUTECONTRACT_STAGED_SPLIT_MYSQL_VERIFIED version={runtime} baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2']
    if any(marker not in output for marker in markers):
        raise VerificationError(f'Consumer {runtime} omitted required positive/negative evidence markers')
    junit = consumer / 'build/test-results/test' / JUNIT_NAME
    counts = verify_junit(junit)
    verify_receipt(repository, receipt)
    print(f'Verified staged {runtime}: real MySQL tests=3, negative graph cases=5', flush=True)
    return {'runtime': runtime, 'adapter': adapter, 'junit': counts, 'negativeGraphCases': 5,
            'evidenceLabel': 'verified - MySQL', 'distributionEvidence': 'local-staged-bytes'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    arguments = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    repository = arguments.repository.expanduser().resolve(strict=True)
    evidence = arguments.evidence_directory.expanduser().absolute()
    if not repository.is_dir() or evidence.exists() or evidence.is_symlink():
        raise VerificationError('Supply an existing repository and a new evidence directory')
    resolved_evidence = evidence.resolve()
    if resolved_evidence.is_relative_to(repository) or repository.is_relative_to(resolved_evidence):
        raise VerificationError('The evidence directory must be separate from the supplied repository')
    receipt = repository_receipt(repository)
    evidence.mkdir(parents=True)
    (evidence / 'staged-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='routecontract-staged-consumer-') as temporary:
        temporary_root = Path(temporary).resolve()
        lanes = [verify_lane(root, temporary_root, evidence, repository, runtime, adapter, receipt)
                 for runtime, adapter in LANES.items()]
    summary = {'formatVersion': 1, 'routeContractVersion': VERSION,
               'publicRepositoryConsumptionVerified': False, 'lanes': lanes,
               'boundary': 'ShardingSphere SQLExecutionHook-reported physical JDBC execution attempts; not a complete route plan or business success'}
    (evidence / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('ROUTECONTRACT_STAGED_SPLIT_CONSUMER_VERIFIED lanes=2 mysqlTests=6 negativeGraphCases=10 publicConsumption=false')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, VerificationError, subprocess.SubprocessError) as error:
        print(f'STAGED_SPLIT_CONSUMER_FAILED: {error}', file=sys.stderr)
        raise SystemExit(1)
