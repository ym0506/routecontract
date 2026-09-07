#!/usr/bin/env python3
"""Resolve and verify a reviewed public 0.1.3+ single-coordinate release with Maven/MySQL."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

GROUP = 'io.github.ym0506.routecontract'
GROUP_PATH = 'io/github/ym0506/routecontract'
ARTIFACT = 'routecontract-shardingsphere-5.5'
SS_GROUP = 'org.apache.shardingsphere'
RUNTIME = '5.5.3'
REQUIRED_SS = {'shardingsphere-jdbc', 'shardingsphere-infra-executor',
               'shardingsphere-infra-spi', 'shardingsphere-database-connector-core'}
MAVEN_VERSION = '3.9.14'
CENTRAL_URL = 'https://repo.maven.apache.org/maven2'
MIRROR_ID = 'routecontract-public-central'
DEPENDENCY_PLUGIN = 'org.apache.maven.plugins:maven-dependency-plugin:3.11.0'
SUITE = 'io.github.ym0506.routecontract.consumer.PublicReleaseMySqlTest'
JUNIT_NAME = f'TEST-{SUITE}.xml'
TEST_NAMES = {'selectedRuntimeApiOriginsAndAutoDiscoveredHookAreTheExpectedJarBytes',
              'captureAndCaptureResultMatchTheReviewedSchemaOneBaseline',
              'sameBusinessRowWithTwoAttemptsFailsPolicyAndSeparateJvmCli'}
N = '{http://maven.apache.org/POM/4.0.0}'
TIMEOUT_SECONDS = 1200
STRIPPED_ENV = ('MAVEN_ARGS', 'MAVEN_OPTS', 'MAVEN_DEBUG_OPTS', 'JAVA_OPTS',
                'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS',
                'MAVEN_PROJECTBASEDIR', 'MAVEN_BASEDIR', 'MAVEN_CONFIG',
                'M2_HOME', 'MAVEN_HOME', 'CLASSPATH')


class VerificationError(ValueError):
    """A distribution acceptance boundary failed."""


def public_artifacts():
    name = 'routecontract_public_release_artifacts'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name('public_release_artifacts.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def check_receipt(path: Path, expected: dict) -> None:
    if public_artifacts().load_consumer_receipt(path) != expected:
        raise VerificationError('Reviewed receipt changed during verification')


def clean_environment(java_home: Path, private_home: Path) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key not in STRIPPED_ENV}
    # Every Maven invocation runs in temporary/consumer, beside temporary/home.
    # A fixed relative JVM option survives the launcher's shell splitting even when
    # the temporary path contains spaces. MAVEN_OPTS is not read by CLI child JVMs.
    environment.update(JAVA_HOME=str(java_home), HOME=str(private_home), MAVEN_SKIP_RC='true',
                       MAVEN_OPTS='-Duser.home=../home')
    return environment


def maven_arguments(maven: str, settings: Path, cache: Path, private_home: Path) -> list[str]:
    return [maven, '--batch-mode', '--no-transfer-progress', '--strict-checksums',
            '--settings', str(settings), '--global-settings', str(settings),
            f'-Dmaven.repo.local={cache}', f'-Duser.home={private_home}', '-Dstyle.color=never',
            '-Dmaven.resolver.transport=native', '-Daether.connector.http.followRedirects=false']


def run(command: list[str], cwd: Path, environment: dict[str, str], log: Path) -> str:
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=cwd, env={**environment, 'MAVEN_BASEDIR': str(cwd)},
                                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                timeout=TIMEOUT_SECONDS)
    output = log.read_text(encoding='utf-8', errors='replace')
    if result.returncode != 0:
        raise VerificationError(f'Maven command failed with exit {result.returncode}; inspect {log}')
    return output


def validate_evidence_path(root: Path, receipt_path: Path, evidence: Path) -> None:
    if evidence.exists() or evidence.is_symlink():
        raise VerificationError('Supply a new evidence directory')
    if evidence.resolve().is_relative_to(root.resolve()):
        raise VerificationError('Evidence must be outside the checkout')
    if receipt_path.resolve().is_relative_to(evidence.resolve()):
        raise VerificationError('Evidence must be separate from the reviewed receipt')


def copy_consumer(root: Path, destination: Path, version: str) -> None:
    public_artifacts().stable_version(version)
    destination.mkdir()
    shutil.copytree(root / 'examples/public-gradle-release-consumer/src', destination / 'src')
    tree = ET.parse(root / 'examples/public-maven-release-consumer/pom.xml')
    tree.getroot().find(N + 'properties/' + N + 'routecontract.version').text = version
    tree.getroot().find('.//' + N + 'requireProperty/' + N + 'regex').text = version.replace('.', '[.]')
    ET.register_namespace('', N[1:-1])
    ET.indent(tree)
    tree.write(destination / 'pom.xml', encoding='UTF-8', xml_declaration=True)


def nodes(tree: dict):
    if not isinstance(tree, dict) or not isinstance(tree.get('children', []), list):
        raise VerificationError('Malformed Maven dependency graph')
    yield tree
    for child in tree.get('children', []):
        yield from nodes(child)


def verify_tree(tree: dict, version: str) -> dict:
    selected = list(nodes(tree))
    first_party = [node for node in selected if node.get('groupId') == GROUP]
    direct = [node for node in tree.get('children', []) if node.get('groupId') == GROUP]
    if len(first_party) != 1 or len(direct) != 1 or direct[0] is not first_party[0]:
        raise VerificationError('The reviewed single coordinate must be the sole direct first-party dependency')
    item = first_party[0]
    if (item.get('artifactId'), item.get('version'), item.get('type'), item.get('classifier') or '') != (
            ARTIFACT, version, 'jar', ''):
        raise VerificationError('Unexpected selected RouteContract coordinate')
    ss = {(item.get('artifactId'), item.get('version')) for item in selected if item.get('groupId') == SS_GROUP}
    if not REQUIRED_SS.issubset({artifact for artifact, _ in ss}) or any(value != RUNTIME for _, value in ss):
        raise VerificationError('The whole selected ShardingSphere group must be exactly 5.5.3, including runtime anchors')
    return {'firstPartyArtifacts': 1, 'soleDirectFirstPartyCoordinate': f'{GROUP}:{ARTIFACT}:{version}',
            'shardingSphereComponents': len(ss), 'shardingSphereVersion': RUNTIME,
            'selectedComponents': sorted({':'.join(str(item.get(field) or '') for field in
                ('groupId', 'artifactId', 'type', 'classifier', 'version', 'scope')) for item in selected})}


def verify_origins(cache: Path, receipt: dict) -> list[dict]:
    consumed = []
    for item in receipt['artifacts']:
        if not item['name'].endswith(('.jar', '.pom')):
            continue
        resolved = cache / item['relativePath']
        if (not resolved.is_file() or resolved.is_symlink()
                or not resolved.resolve().is_relative_to(cache.resolve()) or sha256(resolved) != item['sha256']):
            raise VerificationError(f'Resolved bytes do not match reviewed receipt: {item["name"]}')
        marker = resolved.parent / '_remote.repositories'
        if not marker.is_file() or marker.is_symlink():
            raise VerificationError(f'Resolved payload lacks Central origin marker: {item["name"]}')
        entries = {line.strip() for line in marker.read_text(encoding='utf-8').splitlines()
                   if line.strip() and not line.lstrip().startswith(('#', '!'))}
        origins = {line for line in entries if line.startswith(f'{resolved.name}>')}
        if origins != {f'{resolved.name}>{MIRROR_ID}='}:
            raise VerificationError(f'Resolved payload has an unexpected repository origin: {item["name"]}')
        consumed.append(dict(item))
    if len(consumed) != 2:
        raise VerificationError('The reviewed receipt must identify exactly one JAR and POM')
    return consumed


def verify_junit(path: Path) -> dict:
    suite = ET.parse(path).getroot()
    counts = {name: int(suite.get(name, '-1')) for name in ('tests', 'failures', 'errors', 'skipped')}
    cases = suite.findall('testcase')
    if (suite.tag != 'testsuite' or suite.get('name') != SUITE
            or counts != {'tests': 3, 'failures': 0, 'errors': 0, 'skipped': 0}
            or len(cases) != 3 or {case.get('name') for case in cases} != TEST_NAMES
            or any(case.find(tag) is not None for case in cases for tag in ('failure', 'error', 'skipped'))):
        raise VerificationError('Require exactly three passing real-MySQL tests with zero skips')
    return counts


def retain_evidence(consumer: Path, cache: Path, evidence: Path) -> None:
    for source, name in ((consumer / 'target/surefire-reports', 'junit'),
                         (consumer / 'src', 'inputs/src'), (cache / GROUP_PATH, 'resolved-first-party')):
        if source.is_dir():
            shutil.copytree(source, evidence / name, dirs_exist_ok=True)
    if (consumer / 'pom.xml').is_file():
        shutil.copy2(consumer / 'pom.xml', evidence / 'consumer-pom.xml')


def verify_consumer(root: Path, temporary: Path, evidence: Path, receipt_path: Path,
                    receipt: dict, maven: str, java_home: Path) -> dict:
    if temporary.resolve().is_relative_to(root.resolve()):
        raise VerificationError('Temporary consumer, home and Maven cache must be outside the checkout')
    consumer, cache, private_home = temporary / 'consumer', temporary / 'repository', temporary / 'home'
    if cache.exists() or cache.is_symlink() or private_home.exists() or private_home.is_symlink():
        raise VerificationError('Maven repository and private home must start absent')
    private_home.mkdir()
    version = receipt['routeContractVersion']
    copy_consumer(root, consumer, version)
    settings = temporary / 'settings.xml'
    shutil.copy2(root / 'examples/public-maven-release-consumer/settings.xml', settings)
    shutil.copy2(settings, evidence / 'central-settings.xml')
    environment = clean_environment(java_home, private_home)
    arguments = maven_arguments(maven, settings, cache, private_home)
    graph_path = evidence / 'resolved-graph.json'
    try:
        toolchain = run([*arguments, '--version'], consumer, environment, evidence / 'toolchain.log')
        if (f'Apache Maven {MAVEN_VERSION} ' not in toolchain
                or not re.search(r'Java version: 17[.,]', toolchain)):
            raise VerificationError('The fixture requires exact Maven 3.9.14 and Java 17')
        check_receipt(receipt_path, receipt)
        print(f'Resolving public Maven {version} with a fresh repository before compiling or testing...', flush=True)
        run([*arguments, f'{DEPENDENCY_PLUGIN}:resolve', f'{DEPENDENCY_PLUGIN}:tree',
             '-DoutputType=json', f'-DoutputFile={graph_path}'], consumer, environment, evidence / 'resolve.log')
        graph = verify_tree(json.loads(graph_path.read_text(encoding='utf-8')), version)
        consumed = verify_origins(cache, receipt)
        check_receipt(receipt_path, receipt)
        write_json(evidence / 'verified-before-tests.json', {'consumedPayloads': consumed, **graph})
        digest = next(item['sha256'] for item in consumed if item['name'].endswith('.jar'))
        output = run([*arguments, f'-Droutecontract.sha256.{ARTIFACT}={digest}',
                      f'-Droutecontract.evidenceDirectory={evidence / "reports"}', 'clean', 'verify'],
                     consumer, environment, evidence / 'maven.log')
        counts = verify_junit(consumer / 'target/surefire-reports' / JUNIT_NAME)
        marker = (f'ROUTECONTRACT_PUBLIC_SINGLE_MYSQL_VERIFIED version={version} runtime=5.5.3 '
                  'baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2')
        if marker not in output:
            raise VerificationError('Maven output omitted the real-MySQL acceptance marker')
        final_graph = evidence / 'resolved-graph-after-tests.json'
        run([*arguments, f'{DEPENDENCY_PLUGIN}:tree', '-DoutputType=json', f'-DoutputFile={final_graph}'],
            consumer, environment, evidence / 'graph-after-tests.log')
        if verify_tree(json.loads(final_graph.read_text(encoding='utf-8')), version) != graph:
            raise VerificationError('Selected dependency components changed during MySQL verification')
        verify_origins(cache, receipt)
        check_receipt(receipt_path, receipt)
        return {'junit': counts, **graph, 'consumedPayloads': consumed,
                'evidenceLabels': ['verified - MySQL', 'verified - ShardingSphere-JDBC 5.5.3']}
    finally:
        retain_evidence(consumer, cache, evidence)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--maven', default='mvn')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    receipt_path = args.receipt.expanduser().absolute()
    receipt = public_artifacts().load_consumer_receipt(receipt_path)
    evidence = args.evidence_directory.expanduser().absolute()
    validate_evidence_path(root, receipt_path, evidence)
    java_home = args.java_home.expanduser().resolve(strict=True)
    maven = shutil.which(args.maven)
    if not maven or not (java_home / 'bin/java').is_file():
        raise VerificationError('Supply Maven 3.9.14 and a Java 17 home')
    evidence.mkdir(parents=True)
    write_json(evidence / 'reviewed-receipt.json', receipt)
    try:
        with tempfile.TemporaryDirectory(prefix='routecontract-public-maven-release-') as temporary:
            result = verify_consumer(root, Path(temporary).resolve(), evidence, receipt_path, receipt, maven, java_home)
        check_receipt(receipt_path, receipt)
        write_json(evidence / 'summary.json', {
            'formatVersion': 1, 'complete': True, 'routeContractVersion': receipt['routeContractVersion'],
            'publicRepositoryConsumptionVerified': True, 'repository': CENTRAL_URL,
            'redirectsFollowed': False, 'mavenVersion': MAVEN_VERSION, 'javaMajorVersion': 17,
            'normalizedReviewedReceiptSha256': sha256(evidence / 'reviewed-receipt.json'),
            'distributionEvidence': 'public-maven-central',
            'boundary': 'Maven consumes reviewed JAR and POM only; Gradle module metadata requires independent public readback. '
                        'SQLExecutionHook-reported physical JDBC execution attempts are not a complete route plan or transaction commit.',
            **result})
    except BaseException:
        write_json(evidence / 'failure.json', {'formatVersion': 1, 'complete': False,
                   'routeContractVersion': receipt['routeContractVersion'],
                   'publicRepositoryConsumptionVerified': False})
        raise
    print(f'ROUTECONTRACT_PUBLIC_MAVEN_RELEASE_CONSUMER_VERIFIED version={receipt["routeContractVersion"]} mysqlTests=3 publicConsumption=true')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ET.ParseError, subprocess.SubprocessError) as error:
        print(f'PUBLIC_MAVEN_RELEASE_CONSUMER_FAILED: {error}', file=sys.stderr)
        raise SystemExit(1)
