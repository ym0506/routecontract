#!/usr/bin/env python3
"""Real Maven A-27 legacy graph/Enforcer matrix against reviewed public/staged bytes."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from legacy_artifact_inputs import ARTIFACT, GROUP, digest, load_registry
from public_split_artifacts import load_consumer_receipt
import staged_maven_repository as mirror
from maven_legacy_central_cache import cached_central

FIXTURE = ROOT / 'examples/maven-legacy-artifact-consumer'
REGISTRY = ROOT / 'scripts/legacy-artifact-inputs.json'
GROUP_PATH = GROUP.replace('.', '/')
FIXTURE_GROUP = GROUP + '.fixtures'
MIRROR_ID = 'routecontract-maven-legacy-verified'
POM_NS = 'http://maven.apache.org/POM/4.0.0'
N = '{' + POM_NS + '}'
TREE_GOAL = 'org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree'
CLASSPATH_GOAL = 'org.apache.maven.plugins:maven-dependency-plugin:3.11.0:build-classpath'


class VerificationError(RuntimeError):
    pass


def sibling(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


inputs_helper = sibling('legacy_gradle_input_support', 'verify-gradle-legacy-artifact-consumer.py')
maven_helper = sibling('legacy_maven_support', 'verify-staged-maven-artifact-consumer.py')


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def snapshot() -> dict:
    files = [Path(__file__).resolve(), REGISTRY, ROOT / 'scripts/legacy_artifact_inputs.py',
             ROOT / 'scripts/public_split_artifacts.py', ROOT / 'scripts/staged_maven_repository.py',
             ROOT / 'scripts/maven_legacy_central_cache.py',
             ROOT / 'scripts/verify-gradle-legacy-artifact-consumer.py',
             ROOT / 'scripts/verify-staged-maven-artifact-consumer.py',
             ROOT / 'scripts/verify-staged-split-artifact-consumer.py']
    files += sorted(path for path in FIXTURE.rglob('*') if path.is_file())
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in files}


def dependency(parent, group, artifact, version, *, packaging=None):
    node = ET.SubElement(parent, N + 'dependency')
    for name, value in [('groupId', group), ('artifactId', artifact), ('version', version)]:
        ET.SubElement(node, N + name).text = value
    if packaging:
        ET.SubElement(node, N + 'type').text = packaging
    return node


def xml_bytes(root) -> bytes:
    ET.register_namespace('', POM_NS)
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n'


def carrier_name(version: str, current: bool, strict: bool) -> str:
    return f'{"current" if current else "legacy"}-{"hard" if strict else "bare"}-request-{version}'


def prepare_carriers(registry: dict, repository: Path, current: str) -> list[dict]:
    """POM-only graph inputs; no fabricated RouteContract binary is created."""
    result = []
    for legacy in registry['distributed']:
        for is_current in (False, True):
            for strict in (False, True):
                name = carrier_name(legacy['version'], is_current, strict)
                requested = current if is_current else legacy['version']
                requirement = f'[{requested}]' if strict else requested
                root = ET.Element(N + 'project')
                for field, value in [('modelVersion', '4.0.0'), ('groupId', FIXTURE_GROUP),
                                     ('artifactId', name), ('version', '1'), ('packaging', 'pom')]:
                    ET.SubElement(root, N + field).text = value
                dependency(ET.SubElement(root, N + 'dependencies'), GROUP, ARTIFACT, requirement)
                payload = xml_bytes(root)
                relative = f'{FIXTURE_GROUP.replace(".", "/")}/{name}/1/{name}-1.pom'
                target = repository / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                result.append({'module': name, 'version': '1', 'name': target.name, 'relativePath': relative,
                               'sha256': digest(payload), 'byteCount': len(payload), 'origin': 'generated-fixture-pom',
                               'requestedCoordinate': f'{GROUP}:{ARTIFACT}:{requirement}'})
    return result


def add_checksums(repository: Path, inventory: list[dict]) -> list[dict]:
    result = []
    for item in inventory:
        payload = (repository / item['relativePath']).read_bytes()
        for algorithm in ('sha1', 'sha256', 'sha512', 'md5'):
            relative = item['relativePath'] + '.' + algorithm
            checksum = (hashlib.new(algorithm, payload).hexdigest() + '\n').encode('ascii')
            (repository / relative).write_bytes(checksum)
            result.append({'relativePath': relative, 'sha256': digest(checksum), 'byteCount': len(checksum)})
    return result


def cases(registry: dict, current: str = '0.2.0') -> list[dict]:
    result = []
    def add(case_id, legacy, kind, requests, expected, selected, *, policy=True, managed=False):
        result.append({'caseId': case_id, 'legacyVersion': legacy, 'currentVersion': current, 'kind': kind,
                       'requests': requests, 'expected': expected, 'expectedFirstParty': selected,
                       'ownershipPolicy': policy, 'managedCurrentVersion': managed})
    for item in registry['distributed']:
        version = item['version']
        legacy = {'groupId': GROUP, 'artifactId': ARTIFACT, 'version': version}
        add(f'{version}-alone', version, 'legacy-control', [legacy], 'RESOLVED', [[ARTIFACT, version]], policy=False)
        for suffix, module in [('core', 'routecontract-core'), ('552', 'routecontract-shardingsphere-5.5.2')]:
            other = {'groupId': GROUP, 'artifactId': module, 'version': current}
            selected = [[ARTIFACT, version], [module, current]]
            if suffix == '552':
                selected.append(['routecontract-core', current])
            for order, requests in [('legacy-first', [legacy, other]), ('legacy-last', [other, legacy])]:
                add(f'{version}-{suffix}-{order}', version, 'mixed-components', requests, 'ENFORCER_REJECTED', selected)
        for kind, strict, managed in [('bare', False, False), ('managed', False, True), ('strict', True, False)]:
            old = {'groupId': FIXTURE_GROUP, 'artifactId': carrier_name(version, False, strict), 'version': '1', 'type': 'pom'}
            new = {'groupId': FIXTURE_GROUP, 'artifactId': carrier_name(version, True, strict), 'version': '1', 'type': 'pom'}
            for order, requests in [('legacy-first', [old, new]), ('legacy-last', [new, old])]:
                if strict:
                    expected, selected = 'STRICT_RANGE_CONFLICT', []
                elif kind == 'bare' and order == 'legacy-first':
                    expected, selected = 'ENFORCER_REJECTED', [[ARTIFACT, version]]
                else:
                    # Enforcer 3.6.3 checks a verbose graph, including losing legacy
                    # nodes. Managed alignment changes both requests; bare mediation
                    # can select only current bytes yet still fail the policy.
                    expected = 'RESOLVED' if managed else 'ENFORCER_REJECTED'
                    selected = [[ARTIFACT, current], ['routecontract-core', current]]
                add(f'{version}-{kind}-{order}', version, kind, requests, expected, selected, managed=managed)
    add('0.1.3-core-without-policy-control', '0.1.3', 'ownership-disabled-control',
        [{'groupId': GROUP, 'artifactId': ARTIFACT, 'version': '0.1.3'},
         {'groupId': GROUP, 'artifactId': 'routecontract-core', 'version': current}],
        'RESOLVED', [[ARTIFACT, '0.1.3'], ['routecontract-core', current]], policy=False)
    return result


def prepare_consumer(case: dict, destination: Path) -> Path:
    destination.mkdir()
    root = ET.parse(FIXTURE / 'pom.xml').getroot()
    root.find(N + 'artifactId').text = 'maven-legacy-' + case['caseId']
    deps = root.find(N + 'dependencies')
    for item in case['requests']:
        dependency(deps, item['groupId'], item['artifactId'], item['version'], packaging=item.get('type'))
    if case['managedCurrentVersion']:
        management = ET.Element(N + 'dependencyManagement')
        dependency(ET.SubElement(management, N + 'dependencies'), GROUP, ARTIFACT, case['currentVersion'])
        root.insert(list(root).index(deps), management)
    if case['ownershipPolicy']:
        root.find(N + 'build/' + N + 'plugins').append(ET.parse(FIXTURE / 'legacy-ownership-enforcer.xml').getroot())
    pom = destination / 'pom.xml'
    pom.write_bytes(xml_bytes(root))
    return pom


def verify_selected_graph(graph: dict, case: dict) -> list[dict]:
    selected = sorted({(n['artifactId'], n['version']) for n in maven_helper.nodes(graph) if n.get('groupId') == GROUP})
    if selected != sorted(map(tuple, case['expectedFirstParty'])):
        raise VerificationError(f'Unexpected actual selected graph in {case["caseId"]}: {selected}')
    components = [n for n in maven_helper.nodes(graph) if n.get('groupId') == 'org.apache.shardingsphere']
    if [ARTIFACT, case['currentVersion']] in case['expectedFirstParty']:
        if not any(n['artifactId'] == 'shardingsphere-infra-executor' for n in components) or any(n['version'] != '5.5.3' for n in components):
            raise VerificationError('Current adapter553 selection lost exact whole-group ShardingSphere identity')
    return [{'module': module, 'version': version} for module, version in selected]


def regular_under(path: Path, root: Path, *, directory: bool = False) -> Path:
    try:
        relative = path.relative_to(root)
        if '..' in relative.parts or root.is_symlink():
            raise ValueError('Traversing cache path')
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('Symlink cache ancestor')
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        if not (path.is_dir() if directory else path.is_file()):
            raise ValueError('Unexpected cache entry type')
        return path
    except (OSError, ValueError) as error:
        raise VerificationError('Consumed path must be a regular entry inside its fresh cache') from error


def verify_origin(file: Path, cache: Path) -> None:
    try:
        marker = regular_under(file.parent / '_remote.repositories', cache)
    except VerificationError as error:
        raise VerificationError('Consumed artifact has no regular controlled-mirror origin marker') from error
    origins = {line.strip() for line in marker.read_text().splitlines() if line.startswith(file.name + '>')}
    if origins != {f'{file.name}>{MIRROR_ID}='}:
        raise VerificationError('Consumed artifact origin differs from the controlled mirror')


def verify_cache(cache: Path, repository: Path, inventory: list[dict]) -> None:
    pins = {p['relativePath']: p for p in inventory}
    group_root = regular_under(cache / GROUP_PATH, cache, directory=True)
    for file in group_root.rglob('*'):
        if file.is_symlink():
            raise VerificationError('Symlink first-party cache entry cannot establish artifact origin')
        if not file.is_file() or file.suffix not in ('.jar', '.pom'):
            continue
        regular_under(file, cache)
        relative = file.relative_to(cache).as_posix()
        if relative not in pins or file.is_symlink() or digest(file.read_bytes()) != pins[relative]['sha256']:
            raise VerificationError('Consumed first-party or carrier bytes differ from their input pin')
        verify_origin(file, cache)


def verify_classpath(path: Path, case: dict, cache: Path, inventory: list[dict]) -> list[dict]:
    pins = {p['relativePath']: p for p in inventory if p.get('origin') != 'generated-fixture-pom'}
    actual = []
    for filename in path.read_text().strip().split(os.pathsep):
        if not filename:
            continue
        file = regular_under(Path(filename), cache)
        relative = file.relative_to(cache).as_posix()
        if relative.startswith(GROUP_PATH + '/') and file.suffix == '.jar':
            pin = pins.get(relative)
            if not pin or file.is_symlink() or digest(file.read_bytes()) != pin['sha256']:
                raise VerificationError('Resolved first-party JAR differs from reviewed input bytes')
            verify_origin(file, cache)
            actual.append({field: pin[field] for field in ('module', 'version', 'name', 'sha256', 'byteCount')})
    if sorted((p['module'], p['version']) for p in actual) != sorted(map(tuple, case['expectedFirstParty'])):
        raise VerificationError('Materialized first-party classpath differs from the selected graph')
    return sorted(actual, key=lambda p: (p['module'], p['version']))


def verify_failure(output: str, case: dict) -> None:
    unrelated = ('Could not transfer artifact', 'Could not find artifact', 'Checksum validation failed',
                 'PluginResolutionException', 'Non-resolvable parent POM', 'Could not transfer metadata')
    if any(marker in output for marker in unrelated):
        raise VerificationError('Unrelated resolution/infrastructure failure cannot count as a negative case')
    if case['expected'] == 'ENFORCER_REJECTED':
        coordinate = re.escape(f'{GROUP}:{ARTIFACT}:jar:{case["legacyVersion"]}')
        banned_node = r'(?<![\w.:-])' + coordinate + r'(?:\:[\w.-]+)?\s+<--- banned via the exclude/include list'
        if 'BannedDependencies failed' not in output or not re.search(banned_node, output):
            raise VerificationError('Negative case omitted its exact Maven/Enforcer conflict cause')
        return
    else:
        if 'BannedDependencies failed' in output:
            raise VerificationError('A consumer ban cannot substitute for an incompatible hard-range solver conflict')
        # Maven 3.9.14 normalizes hard singleton requirements [v] to [v,v].
        # Bind both complete coordinates to the same actual resolver diagnostic;
        # a version elsewhere in a failed build must not manufacture coverage.
        conflict_records = [line for line in output.splitlines()
                            if 'Could not resolve version conflict among' in line]
        patterns = []
        for version in (case['legacyVersion'], case['currentVersion']):
            coordinate = re.escape(f'{GROUP}:{ARTIFACT}:jar:')
            bound = re.escape(version)
            patterns.append(r'(?<![\w.:-])' + coordinate + rf'\[{bound}(?:,{bound})?\]')
        if not any(all(re.search(pattern, record) for pattern in patterns) for record in conflict_records):
            raise VerificationError('Negative case omitted its exact Maven/Enforcer conflict cause')
        return


def run_case(case: dict, evidence: Path, settings: Path, repository: Path, inventory: list[dict],
             maven: str, environment: dict) -> dict:
    case_dir = evidence / 'cases' / case['caseId']
    case_dir.mkdir(parents=True)
    pom = prepare_consumer(case, case_dir / 'consumer')
    write_json(case_dir / 'case-inputs.json', case)
    cache = case_dir / 'm2'
    if cache.exists():
        raise VerificationError('Each Maven case must start with an absent dependency cache')
    base = [maven, '--batch-mode', '--no-transfer-progress', '--strict-checksums',
            '--settings', str(settings), '--global-settings', str(settings), '--file', str(pom),
            f'-Dmaven.repo.local={cache}', '-Dstyle.color=never']
    commands = []
    def execute(label: str, goals: list[str], expected_failure=False):
        command = [*base, *goals]
        commands.append({'argv': command, 'cwd': str(pom.parent), 'log': label + '.log'})
        write_json(case_dir / 'commands.json', {'JAVA_HOME': environment['JAVA_HOME'],
                   'dependencyCacheInitiallyAbsent': True, 'commands': commands})
        log = case_dir / (label + '.log')
        with log.open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=pom.parent, env={**environment, 'MAVEN_BASEDIR': str(pom.parent)},
                                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=900, check=False)
        output = log.read_text()
        if expected_failure != (result.returncode != 0):
            raise VerificationError(f'Unexpected Maven command result in {case["caseId"]}: {log}')
        if expected_failure:
            verify_failure(output, case)
        return {'log': log.name, 'sha256': digest(log.read_bytes()), 'exitCode': result.returncode}
    tree = case_dir / 'selected-graph.json'
    logs = [execute('graph', [TREE_GOAL, '-DoutputType=json', f'-DoutputFile={tree}'],
                    case['expected'] == 'STRICT_RANGE_CONFLICT')]
    selected, artifacts = [], []
    if case['expected'] != 'STRICT_RANGE_CONFLICT':
        graph = json.loads(tree.read_text())
        selected = verify_selected_graph(graph, case)
        classpath = case_dir / 'classpath.txt'
        logs.append(execute('classpath', [CLASSPATH_GOAL, f'-Dmdep.outputFile={classpath}']))
        artifacts = verify_classpath(classpath, case, cache, inventory)
        logs.append(execute('validate', ['validate'], case['expected'] == 'ENFORCER_REJECTED'))
    verify_cache(cache, repository, inventory)
    report = {'caseId': case['caseId'], 'kind': case['kind'], 'requests': case['requests'],
              'ownershipPolicy': case['ownershipPolicy'], 'managedCurrentVersion': case['managedCurrentVersion'],
              'result': case['expected'], 'selectedFirstParty': selected, 'selectedArtifacts': artifacts,
              'logs': logs, 'pomSha256': digest(pom.read_bytes())}
    if tree.is_file():
        report['selectedGraphSha256'] = digest(tree.read_bytes())
    write_json(case_dir / 'result.json', report)
    print(f'ROUTECONTRACT_MAVEN_LEGACY_CASE_VERIFIED case={case["caseId"]} result={case["expected"]}', flush=True)
    return {'caseId': case['caseId'], 'result': case['expected'], 'reportSha256': digest((case_dir / 'result.json').read_bytes())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--staged-receipt', type=Path, required=True)
    parser.add_argument('--staged-source-revision', required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--maven', default='mvn')
    parser.add_argument('--legacy-payload-directory', type=Path)
    parser.add_argument('--case', action='append', dest='case_ids')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    evidence = args.evidence_directory.expanduser().resolve()
    if evidence.exists() or evidence == ROOT or ROOT in evidence.parents:
        raise VerificationError('Evidence directory must be absent and outside the checkout')
    evidence.mkdir(parents=True, mode=0o700)
    try:
        initial = snapshot()
        registry = load_registry(REGISTRY)
        receipt = load_consumer_receipt(args.staged_receipt)
        receipt_bytes = args.staged_receipt.read_bytes()
        if receipt['routeContractVersion'] != '0.2.0':
            raise VerificationError('The current candidate matrix requires reviewed 0.2.0 bytes')
        binding = inputs_helper.source_binding(args.staged_source_revision)
        write_json(evidence / 'source-binding.json', binding)
        write_json(evidence / 'fixture-inputs.json', initial)
        (evidence / 'staged-receipt.json').write_bytes(receipt_bytes)
        shutil.copyfile(REGISTRY, evidence / 'legacy-artifact-inputs.json')
        repository = evidence / 'repository'
        inventory = inputs_helper.prepare_repository(args.repository.resolve(), receipt, registry, repository,
                    args.legacy_payload_directory.resolve() if args.legacy_payload_directory else None)
        inventory += prepare_carriers(registry, repository, receipt['routeContractVersion'])
        checksums = add_checksums(repository, inventory)
        write_json(evidence / 'verified-input-inventory.json', inventory)
        write_json(evidence / 'repository-checksums.json', checksums)
        all_cases = cases(registry)
        if args.case_ids and set(args.case_ids) - {case['caseId'] for case in all_cases}:
            raise VerificationError('Unknown diagnostic case id')
        selected = [case for case in all_cases if not args.case_ids or case['caseId'] in args.case_ids]
        write_json(evidence / 'case-plan.json', {'allCaseCount': len(all_cases), 'selected': selected})
        maven = shutil.which(args.maven)
        if not maven:
            raise VerificationError('Maven executable is missing')
        environment = maven_helper.clean_environment(args.java_home.resolve())
        toolchain = subprocess.check_output([maven, '--version'], cwd=evidence, env=environment, text=True, timeout=30)
        if 'Apache Maven 3.9.14 ' not in toolchain or 'Java version: 17.' not in toolchain:
            raise VerificationError('Requires exact Maven 3.9.14 and Java 17')
        (evidence / 'toolchain.txt').write_text(toolchain)
        results = []
        with cached_central(evidence / 'central-responses'), mirror.serve_repository(repository, evidence / 'repository-requests.jsonl') as url:
            settings = evidence / 'controlled-settings.xml'
            maven_helper.write_settings(settings, url, MIRROR_ID)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(run_case, case, evidence, settings, repository, inventory, maven, environment) for case in selected]
                try:
                    for future in as_completed(futures):
                        results.append(future.result())
                        write_json(evidence / 'progress.json', sorted(results, key=lambda case: case['caseId']))
                except Exception:
                    for future in futures:
                        future.cancel()
                    raise
        if snapshot() != initial or args.staged_receipt.read_bytes() != receipt_bytes:
            raise VerificationError('Fixture or reviewed receipt changed during execution')
        if inputs_helper.source_binding(args.staged_source_revision) != binding:
            raise VerificationError('Production/publication source binding changed during execution')
        for pin in inventory + checksums:
            if digest((repository / pin['relativePath']).read_bytes()) != pin['sha256']:
                raise VerificationError('Isolated repository input changed during execution')
        summary = {'formatVersion': 1, 'status': 'PARTIAL_VERIFIED' if args.case_ids else 'VERIFIED',
                   'fullMavenA27Matrix': not bool(args.case_ids), 'caseCount': len(results), 'requiredCaseCount': len(all_cases),
                   'registrySha256': initial['scripts/legacy-artifact-inputs.json'], 'stagedReceiptSha256': digest(receipt_bytes),
                   'sourceBinding': binding, 'results': sorted(results, key=lambda case: case['caseId']),
                   'boundary': 'Maven 3.9.14 / Java17 actual resolver and consumer Enforcer against reviewed local staging/public legacy bytes; no SQL, A28, or public0.2 publication claim.'}
        write_json(evidence / 'summary.json', summary)
        print(f'ROUTECONTRACT_MAVEN_LEGACY_MATRIX_{summary["status"]} cases={len(results)} evidence={evidence}', flush=True)
    except Exception as error:
        write_json(evidence / 'failure.json', {'status': 'FAILED', 'error': str(error), 'fullMavenA27Matrix': False})
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'ROUTECONTRACT_MAVEN_LEGACY_MATRIX_FAILED: {error}', file=sys.stderr)
        sys.exit(1)
