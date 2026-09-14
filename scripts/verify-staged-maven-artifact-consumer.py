#!/usr/bin/env python3
"""Verify independent Maven/MySQL consumers of supplied local staged 0.2 bytes."""
from __future__ import annotations

import argparse
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


def sibling(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


shared = sibling('staged_split_support', 'verify-staged-split-artifact-consumer.py')
mirror = sibling('staged_maven_repository', 'staged_maven_repository.py')
VerificationError = shared.VerificationError
GROUP = shared.GROUP
SS_GROUP = 'org.apache.shardingsphere'
LANES = shared.LANES
VERSION = shared.VERSION
MAVEN_VERSION = '3.9.14'
MIRROR_ID = 'routecontract-controlled'
POM_NS = 'http://maven.apache.org/POM/4.0.0'
N = '{' + POM_NS + '}'
TIMEOUT_SECONDS = 1200
DEPENDENCY_TREE = 'org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree'


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def clean_environment(java_home: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name in ('MAVEN_ARGS', 'MAVEN_OPTS', 'MAVEN_DEBUG_OPTS', 'JAVA_OPTS', 'JAVA_TOOL_OPTIONS',
                 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'MAVEN_PROJECTBASEDIR',
                 'MAVEN_BASEDIR', 'MAVEN_CONFIG', 'M2_HOME', 'MAVEN_HOME'):
        environment.pop(name, None)
    environment['JAVA_HOME'] = str(java_home)
    environment['MAVEN_SKIP_RC'] = 'true'
    return environment


def run(command: list[str], cwd: Path, environment: dict[str, str], log: Path,
        expect_failure: bool = False) -> str:
    # Stream to retained evidence: failed/timeout runs must not discard partial output.
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=cwd, env={**environment, 'MAVEN_BASEDIR': str(cwd)}, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT, timeout=TIMEOUT_SECONDS)
    text = log.read_text(encoding='utf-8', errors='replace')
    if expect_failure:
        if result.returncode == 0 or 'BannedDependencies failed' not in text:
            raise VerificationError(f'Expected an explicit BannedDependencies rejection; inspect {log}')
    elif result.returncode != 0:
        raise VerificationError(f'Consumer command failed with exit {result.returncode}; inspect {log}')
    return text


def write_settings(path: Path, url: str, mirror_id: str = MIRROR_ID) -> None:
    settings = ET.Element('settings', {'xmlns': 'http://maven.apache.org/SETTINGS/1.2.0'})
    mirrors = ET.SubElement(settings, 'mirrors')
    item = ET.SubElement(mirrors, 'mirror')
    for name, text in (('id', mirror_id), ('mirrorOf', '*'), ('url', url)):
        ET.SubElement(item, name).text = text
    ET.indent(settings)
    ET.ElementTree(settings).write(path, encoding='UTF-8', xml_declaration=True)


def copy_consumer(root: Path, destination: Path, version: str = VERSION) -> None:
    destination.mkdir()
    shutil.copy2(root / 'examples/staged-maven-artifact-consumer/pom.xml', destination / 'pom.xml')
    shutil.copytree(root / 'examples/staged-split-artifact-consumer/src', destination / 'src')
    if version != VERSION:
        tree = ET.parse(destination / 'pom.xml')
        tree.getroot().find(N + 'properties/' + N + 'routecontract.version').text = version
        tree.getroot().find('.//' + N + 'requireProperty/' + N + 'regex').text = re.escape(version)
        ET.register_namespace('', POM_NS)
        ET.indent(tree)
        tree.write(destination / 'pom.xml', encoding='UTF-8', xml_declaration=True)


def retain_lane_evidence(consumer: Path, cache: Path, destination: Path) -> None:
    for source, name in ((consumer / 'target/surefire-reports', 'junit'),
                         (consumer / 'build/routecontract-consumer-evidence', 'reports'),
                         (consumer / 'src', 'inputs/src'),
                         (cache / shared.GROUP_PATH, 'resolved-first-party')):
        if source.is_dir():
            shutil.copytree(source, destination / name, dirs_exist_ok=True)
    if (consumer / 'pom.xml').is_file():
        shutil.copy2(consumer / 'pom.xml', destination / 'consumer-pom.xml')


def nodes(tree: dict):
    yield tree
    for child in tree.get('children', []):
        yield from nodes(child)


def verify_tree(tree: dict, runtime: str, adapter: str, version: str = VERSION) -> dict:
    selected = list(nodes(tree))
    first_party = {(n.get('artifactId'), n.get('version')) for n in selected if n.get('groupId') == GROUP}
    expected = {(adapter, version), ('routecontract-core', version)}
    if first_party != expected:
        raise VerificationError(f'Unexpected selected RouteContract graph: {first_party}')
    direct = [n for n in tree.get('children', []) if n.get('groupId') == GROUP]
    if len(direct) != 1 or direct[0].get('artifactId') != adapter:
        raise VerificationError('The adapter must be the only direct first-party dependency')
    if not any(n.get('groupId') == GROUP and n.get('artifactId') == 'routecontract-core'
               for n in nodes(direct[0]) if n is not direct[0]):
        raise VerificationError('Core did not resolve transitively from the adapter POM')
    ss = {(n.get('artifactId'), n.get('version')) for n in selected if n.get('groupId') == SS_GROUP}
    if not ss or any(version != runtime for _, version in ss):
        raise VerificationError(f'The selected whole ShardingSphere group must be exactly {runtime}: {ss}')
    return {'firstPartyArtifacts': len(first_party), 'coreResolvedTransitively': True,
            'shardingSphereComponents': len(ss)}


def verify_origins(cache: Path, adapter: str, receipt: dict, mirror_id: str = MIRROR_ID) -> None:
    for item in receipt['artifacts']:
        if item['module'] not in ('routecontract-core', adapter) or not item['name'].endswith(('.jar', '.pom')):
            continue
        resolved = cache / item['relativePath']
        if not resolved.is_file() or resolved.is_symlink() or shared.sha256(resolved) != item['sha256']:
            raise VerificationError(f'Resolved bytes do not match staged receipt: {item["name"]}')
        marker = resolved.parent / '_remote.repositories'
        if not marker.is_file() or marker.is_symlink():
            raise VerificationError(f'Resolved payload does not identify the controlled mirror: {item["name"]}')
        entries = {line.strip() for line in marker.read_text().splitlines()
                   if line.strip() and not line.lstrip().startswith(('#', '!'))}
        origins = {line for line in entries if line.startswith(f'{resolved.name}>')}
        if origins != {f'{resolved.name}>{mirror_id}='}:
            raise VerificationError(f'Resolved payload does not identify the controlled mirror: {item["name"]}')


def negative_pom(source: Path, destination: Path, case: str, runtime: str,
                 artifact_version: str = VERSION) -> tuple[str, str]:
    tree = ET.parse(source)
    dependencies = tree.getroot().find(N + 'dependencies')
    opposite_runtime = '5.5.3' if runtime == '5.5.2' else '5.5.2'
    if case == 'wrong-runtime':
        group, artifact, version = SS_GROUP, 'shardingsphere-infra-executor', opposite_runtime
    elif case == 'wrong-non-anchor':
        group, artifact, version = SS_GROUP, 'shardingsphere-infra-common', opposite_runtime
    elif case in ('dual-selected-first', 'dual-opposite-first'):
        group, artifact, version = GROUP, LANES[opposite_runtime], artifact_version
    else:
        raise VerificationError(f'Unknown negative graph case: {case}')
    dependency = ET.Element(N + 'dependency')
    for name, text in (('groupId', group), ('artifactId', artifact), ('version', version), ('scope', 'test')):
        ET.SubElement(dependency, N + name).text = text
    dependencies.insert(0 if case == 'dual-opposite-first' else 1, dependency)
    ET.register_namespace('', POM_NS)
    ET.indent(tree)
    tree.write(destination, encoding='UTF-8', xml_declaration=True)
    return artifact, version


def verify_negative_selection(tree: dict, case: str, runtime: str, artifact: str, version: str,
                              artifact_version: str = VERSION) -> None:
    selected = {(n.get('groupId'), n.get('artifactId')): n.get('version') for n in nodes(tree)}
    group = GROUP if case.startswith('dual-') else SS_GROUP
    if selected.get((group, artifact)) != version:
        raise VerificationError(f'Negative case did not select its requested dependency: {case}')
    if case == 'wrong-non-anchor':
        database = 'shardingsphere-infra-database-core' if runtime == '5.5.2' else 'shardingsphere-database-connector-core'
        anchors = ('shardingsphere-infra-executor', 'shardingsphere-infra-spi', database)
        if any(selected.get((SS_GROUP, anchor)) != runtime for anchor in anchors):
            raise VerificationError('Wrong non-anchor case must retain all three correct runtime anchors')
    if case.startswith('dual-') and selected.get((GROUP, LANES[runtime])) != artifact_version:
        raise VerificationError('Dual-adapter case must actually select both ordinary module requests')


def verify_lane(root: Path, temporary: Path, evidence: Path, repository: Path | None, settings: Path,
                maven: str, environment: dict[str, str], runtime: str, adapter: str, receipt: dict,
                *, version: str = VERSION, mirror_id: str = MIRROR_ID,
                maven_arguments: tuple[str, ...] = ()) -> dict:
    consumer, cache = temporary / f'consumer-{runtime}', temporary / f'm2-{runtime}'
    copy_consumer(root, consumer, version)
    if cache.exists():
        raise VerificationError('Maven local repository must start absent')
    lane = evidence / runtime
    lane.mkdir()
    arguments = [maven, '--batch-mode', '--no-transfer-progress', '--strict-checksums',
                 '--settings', str(settings), '--global-settings', str(settings),
                 f'-Dmaven.repo.local={cache}', f'-Pruntime-{runtime}', '-Dstyle.color=never', *maven_arguments]
    for module, property_name in (('routecontract-core', 'core'), (adapter, 'adapter')):
        digest = next(item['sha256'] for item in receipt['artifacts']
                      if item['module'] == module and item['name'].endswith('.jar'))
        arguments.append(f'-Droutecontract.{property_name}Sha256={digest}')
    def command(pom: Path, goals: list[str], log: Path, expect_failure: bool = False) -> str:
        return run([*arguments, '--file', str(pom), *goals], consumer, environment, log, expect_failure)

    if repository is not None:
        shared.verify_receipt(repository, receipt)
    print(f'Checking Maven {runtime} real-MySQL consumer with a fresh local repository...', flush=True)
    try:
        output = command(consumer / 'pom.xml', ['clean', 'verify'], lane / 'maven.log')
        counts = shared.verify_junit(consumer / 'target/surefire-reports' / shared.JUNIT_NAME)
        marker = f'ROUTECONTRACT_STAGED_SPLIT_MYSQL_VERIFIED version={runtime} baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2'
        if marker not in output:
            raise VerificationError('Maven test output omitted the MySQL acceptance marker')
        print(f'Maven {runtime} real MySQL passed: tests=3, exact rows, MATCH and 1-to-2 policy rejection.', flush=True)
        graph_path = lane / 'resolved-graph.json'
        command(consumer / 'pom.xml', [DEPENDENCY_TREE, '-DoutputType=json', f'-DoutputFile={graph_path}'],
                lane / 'graph.log')
        graph = verify_tree(json.loads(graph_path.read_text()), runtime, adapter, version)
        verify_origins(cache, adapter, receipt, mirror_id)
        negatives = []
        for case in ('wrong-runtime', 'wrong-non-anchor', 'dual-selected-first', 'dual-opposite-first'):
            case_path = lane / case
            case_path.mkdir()
            pom = case_path / 'pom.xml'
            artifact, rejected_version = negative_pom(consumer / 'pom.xml', pom, case, runtime, version)
            # Direct tree goal does not enter validate. Preserve the actual selected graph
            # independently of Enforcer's rejection; no enforcer.skip or fake metadata.
            selected_path = case_path / 'selected-graph.json'
            command(pom, [DEPENDENCY_TREE, '-DoutputType=json', f'-DoutputFile={selected_path}'],
                    case_path / 'graph.log')
            verify_negative_selection(json.loads(selected_path.read_text()), case, runtime, artifact,
                                      rejected_version, version)
            rejected = command(pom, ['validate'], case_path / 'rejection.log', expect_failure=True)
            if f'{artifact}:jar:{rejected_version}' not in rejected:
                raise VerificationError(f'Enforcer rejection did not identify the offending dependency: {case}')
            negatives.append(case)
        if repository is not None:
            shared.verify_receipt(repository, receipt)
        result = {'runtime': runtime, 'adapter': adapter, 'junit': counts, **graph,
                  'negativeGraphCases': negatives, 'evidenceLabel': 'verified - MySQL',
                  'distributionEvidence': 'local-staged-bytes' if repository is not None else 'public-maven-central'}
        write_json(lane / 'summary.json', result)
        print(f'Verified Maven {runtime}: real MySQL tests=3, ordinary negative graphs=4.', flush=True)
        return result
    finally:
        retain_lane_evidence(consumer, cache, lane)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--maven', default=os.environ.get('MAVEN_BIN', 'mvn'))
    arguments = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    repository = arguments.repository.expanduser().resolve(strict=True)
    evidence = arguments.evidence_directory.expanduser().absolute()
    java_home = arguments.java_home.expanduser().resolve(strict=True)
    maven = shutil.which(arguments.maven)
    if not maven or not (java_home / 'bin/java').is_file():
        raise VerificationError('Supply Maven 3.9.14 and a Java 17 home')
    if not repository.is_dir() or evidence.exists() or evidence.is_symlink():
        raise VerificationError('Supply an existing staging repository and a new evidence directory')
    if evidence.resolve().is_relative_to(repository) or repository.is_relative_to(evidence.resolve()):
        raise VerificationError('Evidence must be separate from staging')
    if evidence.resolve().is_relative_to(root):
        raise VerificationError('Evidence and its negative consumer POMs must be outside the checkout')
    receipt = shared.repository_receipt(repository)
    evidence.mkdir(parents=True)
    write_json(evidence / 'staged-receipt.json', receipt)
    environment = clean_environment(java_home)
    summary = {'formatVersion': 1, 'routeContractVersion': VERSION,
               'publicRepositoryConsumptionVerified': False, 'complete': False, 'lanes': [],
               'boundary': 'ShardingSphere SQLExecutionHook-reported physical JDBC execution attempts; not a complete route plan or business success'}
    try:
        with tempfile.TemporaryDirectory(prefix='routecontract-staged-maven-') as temporary_name:
            temporary = Path(temporary_name).resolve()
            if temporary.is_relative_to(root):
                raise VerificationError('Temporary consumer and Maven cache must be outside the checkout')
            toolchain = run([maven, '--version'], temporary, environment, evidence / 'toolchain.log')
            if f'Apache Maven {MAVEN_VERSION} ' not in toolchain or not re.search(r'Java version: 17[.,]', toolchain):
                raise VerificationError('The consumer fixture requires exact Maven 3.9.14 and Java 17')
            with mirror.serve_repository(repository, evidence / 'repository-requests.jsonl') as url:
                settings = evidence / 'controlled-settings.xml'
                write_settings(settings, url)
                for runtime, adapter in LANES.items():
                    summary['lanes'].append(verify_lane(root, temporary, evidence, repository, settings,
                                                       maven, environment, runtime, adapter, receipt))
        shared.verify_receipt(repository, receipt)
        summary['complete'] = True
    finally:
        write_json(evidence / 'summary.json', summary)
    print('ROUTECONTRACT_STAGED_MAVEN_CONSUMER_VERIFIED lanes=2 mysqlTests=6 negativeGraphCases=8 publicConsumption=false')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, VerificationError, mirror.RepositoryError, subprocess.SubprocessError) as error:
        print(f'STAGED_MAVEN_CONSUMER_FAILED: {error}', file=sys.stderr)
        raise SystemExit(1)
