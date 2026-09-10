#!/usr/bin/env python3
"""Bind the unchanged 28-test MySQL corpus to independently reviewed staged JARs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples/packaged-corpus-consumer'
sys.path.insert(0, str(ROOT / 'scripts'))
from public_split_artifacts import load_consumer_receipt

GROUP = 'io.github.ym0506.routecontract'
GRADLE_SHA256 = 'f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d'
TIMEOUT_SECONDS = 2400
HELPERS = ['public_split_artifacts.py', 'legacy_artifact_inputs.py',
           'verify-staged-split-artifact-consumer.py', 'verify-gradle-legacy-artifact-consumer.py',
           'consumer_network_sandbox.py']


class CorpusError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def load_helper(name: str):
    spec = importlib.util.spec_from_file_location('packaged_' + name.replace('-', '_'), ROOT / 'scripts' / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise CorpusError(f'A regular file is required: {path}')


def inventory(directory: Path) -> dict:
    if directory.is_symlink() or not directory.is_dir():
        raise CorpusError('Inventory requires a real directory')
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise CorpusError(f'Symlink in input or evidence tree: {path}')
        if path.is_file():
            result[str(path.relative_to(directory))] = {'size': path.stat().st_size, 'sha256': digest(path)}
        elif not path.is_dir():
            raise CorpusError(f'Non-regular entry in input tree: {path}')
    return result


def original_inputs(contract: dict, root: Path = ROOT) -> dict:
    expected = contract['originalInputSha256']
    observed_paths = set()
    for name in ('examples/mysql/src', 'examples/mysql-5.5.2/src', 'examples/manifests'):
        observed_paths.update(str(Path(name) / relative) for relative in inventory(root / name))
    observed_paths.update(('examples/mysql/build.gradle', 'examples/mysql/gradle.lockfile',
                          'examples/mysql-5.5.2/build.gradle', 'examples/mysql-5.5.2/gradle.lockfile', 'gradle.properties'))
    if observed_paths != set(expected):
        raise CorpusError('Original corpus input set changed')
    actual = {}
    for name in expected:
        path = root / name
        regular(path)
        actual[name] = digest(path)
    if actual != expected:
        raise CorpusError('Original corpus inputs differ from the fixed pre-run contract')
    return actual


def fixture_snapshot() -> dict:
    paths = [Path(__file__), ROOT / 'scripts/tests/test_verify_packaged_corpus_consumer.py',
             ROOT / 'gradle/verification-metadata.xml', ROOT / 'gradlew',
             ROOT / 'gradle/wrapper/gradle-wrapper.jar', ROOT / 'gradle/wrapper/gradle-wrapper.properties']
    paths += [ROOT / 'scripts' / name for name in HELPERS]
    paths += [path for path in FIXTURE.rglob('*') if path.is_file()]
    for path in paths:
        regular(path)
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(paths)}


def reviewed_inputs(repository: Path, receipt_path: Path, expected_hash: str, source: str):
    if re.fullmatch(r'[0-9a-f]{64}', expected_hash) is None or re.fullmatch(r'[0-9a-f]{40}', source) is None:
        raise CorpusError('Explicit reviewed SHA-256 and full staged source revision are required')
    receipt = load_consumer_receipt(receipt_path)
    if digest(receipt_path) != expected_hash or receipt['routeContractVersion'] != '0.2.0':
        raise CorpusError('Receipt is not the explicitly reviewed 0.2.0 input')
    staged = load_helper('verify-staged-split-artifact-consumer.py')
    staged.verify_receipt(repository, receipt)
    binding = load_helper('verify-gradle-legacy-artifact-consumer.py').source_binding(source)
    return receipt, binding


def adapted_build(original: str, adapter: str) -> str:
    old = f"testImplementation project(':{adapter}')"
    if original.count(old) != 1 or original.count('project(') != 1:
        raise CorpusError('Expected exactly the original single adapter project dependency')
    return original.replace(old, f"testImplementation '{GROUP}:{adapter}:0.2.0'") + "\napply from: 'packaged-controls.gradle'\n"


def packaged_lock(original: str, adapter: str) -> str:
    lines = original.splitlines()
    if any(line.startswith(GROUP + ':') for line in lines):
        raise CorpusError('The original project lock unexpectedly contains first-party external modules')
    records = [line for line in lines if line and not line.startswith('#')]
    if len(records) < 100 or not any(line.startswith('empty=') for line in records):
        raise CorpusError('A complete original corpus lock is required')
    records += [f'{GROUP}:{name}:0.2.0=testCompileClasspath,testRuntimeClasspath'
                for name in ('routecontract-core', adapter)]
    return '\n'.join([line for line in lines if line.startswith('#')] + sorted(records)) + '\n'


def lock_graphs(text: str) -> dict[str, list[str]]:
    result = {'testCompileClasspath': [], 'testRuntimeClasspath': []}
    for line in text.splitlines():
        if not line or line.startswith('#') or line.startswith('empty='):
            continue
        coordinate, configurations = line.split('=', 1)
        for configuration in configurations.split(','):
            if configuration in result:
                result[configuration].append(coordinate)
    return {name: sorted(rows) for name, rows in result.items()}


def copy_consumer(destination: Path, runtime: str, contract: dict, receipt: dict,
                  root: Path = ROOT, fixture: Path = FIXTURE) -> dict:
    if destination.exists() or destination.is_symlink():
        raise CorpusError('The disposable consumer must begin absent')
    destination.mkdir(parents=True)
    lane = contract['lanes'][runtime]
    original = root / lane['sourceDirectory']
    copy_map = {}

    def copy(source: Path, relative: str) -> None:
        regular(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if source.read_bytes() != target.read_bytes():
            raise CorpusError('Original/copy bytes differ')
        copy_map[str(source.relative_to(root))] = {'copyPath': relative, 'sha256': digest(target)}

    for source in sorted((original / 'src').rglob('*')):
        if source.is_file():
            copy(source, str(source.relative_to(original)))
    for source in sorted((root / 'examples/manifests').rglob('*')):
        if source.is_file():
            copy(source, 'review-inputs/' + str(source.relative_to(root)))
    for source, name in ((original / 'build.gradle', 'original-corpus-build.gradle'),
                         (original / 'gradle.lockfile', 'original-corpus.lockfile'),
                         (root / 'gradle.properties', 'gradle.properties')):
        copy(source, name)
    for source in sorted(fixture.rglob('*')):
        if source.is_file() and source.name != 'expected-corpus.json':
            target = destination / source.relative_to(fixture)
            if target.exists():
                raise CorpusError('Supplemental fixture would overwrite an original corpus input')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    (destination / 'build.gradle').write_text(adapted_build((original / 'build.gradle').read_text(), lane['adapter']))
    (destination / 'gradle.lockfile').write_text(packaged_lock((original / 'gradle.lockfile').read_text(), lane['adapter']))
    shutil.copyfile(root / 'gradlew', destination / 'gradlew')
    (destination / 'gradlew').chmod(0o700)
    shutil.copytree(root / 'gradle/wrapper', destination / 'gradle/wrapper')
    load_helper('verify-staged-split-artifact-consumer.py').prepare_metadata(
        root / 'gradle/verification-metadata.xml', destination / 'gradle/verification-metadata.xml', receipt)
    # These are input copies, never destinations for generated observations or approval.
    for row in copy_map.values():
        (destination / row['copyPath']).chmod(0o444)
    verify_copies(destination, copy_map)
    return copy_map


def verify_copies(consumer: Path, mapping: dict) -> None:
    for row in mapping.values():
        path = consumer / row['copyPath']
        regular(path)
        if digest(path) != row['sha256']:
            raise CorpusError('Copied original corpus input changed')


def verify_consumer_inputs(consumer: Path, expected: dict) -> None:
    for name, row in expected.items():
        regular(consumer / name)
        if digest(consumer / name) != row['sha256']:
            raise CorpusError('An executed consumer input changed during the corpus run')
    for prefix in ('src', 'review-inputs'):
        expected_tree = {name[len(prefix) + 1:]: row for name, row in expected.items() if name.startswith(prefix + '/')}
        if inventory(consumer / prefix) != expected_tree:
            raise CorpusError('The copied corpus/provenance source or golden input set changed')


def verify_junit(directory: Path, suites: dict) -> dict:
    expected_files = {'TEST-' + name + '.xml' for name in suites}
    files = {path.name for path in directory.glob('TEST-*.xml')}
    if files != expected_files:
        raise CorpusError('JUnit suite files do not match the exact original corpus')
    result = {}
    for name, methods in suites.items():
        path = directory / ('TEST-' + name + '.xml')
        suite = ET.parse(path).getroot()
        counts = {key: int(suite.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
        if suite.get('name') != name or counts != {'tests': len(methods), 'failures': 0, 'errors': 0, 'skipped': 0}:
            raise CorpusError('The exact corpus suite must pass without skips')
        cases = suite.findall('testcase')
        actual = [case.get('name', '').removesuffix('()') for case in cases]
        if sorted(actual) != sorted(methods) or any(case.get('classname') != name for case in cases):
            raise CorpusError('JUnit method identities differ from the original fixed corpus')
        if any(case.find(kind) is not None for case in cases for kind in ('failure', 'error', 'skipped')):
            raise CorpusError('JUnit includes a failed, aborted or skipped corpus case')
        result[name] = {'counts': counts, 'methods': sorted(actual), 'junitSha256': digest(path)}
    return result


def verify_graphs(consumer: Path, runtime: str, receipt: dict) -> dict:
    graphs = read_json(consumer / 'build/packaged-corpus/selected-graphs.json')
    expected = lock_graphs((consumer / 'gradle.lockfile').read_text())
    if set(graphs) != set(expected):
        raise CorpusError('Both complete locked classpath graphs are required')
    pins = {row['module']: row['sha256'] for row in receipt['artifacts'] if row['name'].endswith('.jar')}
    artifact_paths = set()
    for name, graph in graphs.items():
        if graph['modules'] != expected[name]:
            raise CorpusError('Selected full graph differs from the original lock plus reviewed first-party coordinates')
        sharding = [entry for entry in graph['modules'] if entry.startswith('org.apache.shardingsphere:')]
        if not sharding or any(entry.rsplit(':', 1)[1] != runtime for entry in sharding):
            raise CorpusError('The complete selected ShardingSphere group must match the exact corpus runtime')
        first = []
        for row in graph['artifacts']:
            if row['coordinate'] not in graph['modules']:
                raise CorpusError('Artifact is not a component in the selected full graph')
            path = Path(row['path'])
            regular(path)
            if digest(path) != row['sha256'] or path.name != row['name']:
                raise CorpusError('Selected artifact bytes changed or do not match the actual inventory')
            group, module, version = row['coordinate'].split(':')
            if group == GROUP:
                if version != '0.2.0' or row['sha256'] != pins.get(module):
                    raise CorpusError('Unreviewed first-party artifact selected')
                first.append(module)
            if group == 'org.apache.shardingsphere' and version != runtime:
                raise CorpusError('Wrong ShardingSphere artifact selected')
            if name == 'testRuntimeClasspath':
                artifact_paths.add(str(path.resolve()))
        adapter = 'routecontract-shardingsphere-5.5.2' if runtime == '5.5.2' else 'routecontract-shardingsphere-5.5'
        if sorted(first) != sorted(['routecontract-core', adapter]):
            raise CorpusError('Exactly the core and selected adapter JARs must be materialized')
    classpath = read_json(consumer / 'build/packaged-corpus/test-runtime-classpath.json')
    directories = {str((consumer / name).resolve()) for name in ('build/classes/java/test', 'build/resources/test')}
    observed_jars = set()
    for row in classpath:
        path = Path(row['path'])
        if row['directory']:
            if str(path.resolve()) not in directories or not path.is_dir():
                raise CorpusError('A production or foreign class directory appeared in the actual test classpath')
        else:
            regular(path)
            if digest(path) != row['sha256']:
                raise CorpusError('Test runtime classpath artifact changed')
            observed_jars.add(str(path.resolve()))
    if observed_jars != artifact_paths:
        raise CorpusError('Actual test runtime classpath differs from the selected packaged graph')
    return graphs


def verify_provenance(consumer: Path, runtime: str, suites: dict, graphs: dict, receipt: dict) -> list[dict]:
    directory = consumer / 'build/packaged-corpus/provenance'
    expected_files = {name + '-' + phase + '.json' for name in suites for phase in ('before', 'after')}
    if {path.name for path in directory.glob('*.json')} != expected_files:
        raise CorpusError('Same-JVM before/after provenance is required for every original suite')
    actual = {row['coordinate'].split(':')[1]: row for row in graphs['testRuntimeClasspath']['artifacts']
              if row['coordinate'].startswith(GROUP + ':')}
    adapter = 'routecontract-shardingsphere-5.5.2' if runtime == '5.5.2' else 'routecontract-shardingsphere-5.5'
    pins = {row['module']: row['sha256'] for row in receipt['artifacts'] if row['name'].endswith('.jar')}
    rows = []
    suffix = runtime.replace('.', '')
    for name in suites:
        pair = []
        for phase in ('before', 'after'):
            path = directory / (name + '-' + phase + '.json')
            row = read_json(path)
            if any(row.get(key) != value for key, value in {
                'suite': name, 'phase': phase, 'runtime': runtime, 'generationEnabled': 'false',
                'currentEntry': 'io.github.ym0506.routecontract.api.RouteContract',
                'hookClass': f'io.github.ym0506.routecontract.shardingsphere{suffix}.internal.RouteContract{suffix}SqlExecutionHook',
                'runtimeAdapterClass': f'io.github.ym0506.routecontract.shardingsphere{suffix}.internal.ShardingSphere{suffix}RuntimeAdapter',
                'providerDescriptors': 'EXACT_PACKAGED'}.items()):
                raise CorpusError('Provenance identity, current entry or generation boundary mismatch')
            if not row['pid'].isdigit() or not row['javaVersion'].startswith('17.'):
                raise CorpusError('The actual corpus JVM must be Java 17')
            origin = urlsplit(row['suiteCodeSource'])
            if (origin.scheme != 'file' or origin.netloc or not row['loader']
                    or Path(unquote(origin.path)).resolve() != (consumer / 'build/classes/java/test').resolve()):
                raise CorpusError('Corpus suite must execute from its own copied and compiled test source')
            for prefix, module in (('core', 'routecontract-core'), ('adapter', adapter)):
                if row[prefix + 'Sha256'] != pins[module] or Path(row[prefix + 'Jar']).resolve() != Path(actual[module]['path']).resolve():
                    raise CorpusError('Same-JVM observed JAR is not the selected reviewed runtime artifact')
            pair.append(row)
            rows.append(dict(row, evidenceSha256=digest(path)))
        if any(pair[0][field] != pair[1][field] for field in ('pid', 'loader', 'coreJar', 'adapterJar', 'suiteCodeSource')):
            raise CorpusError('Suite provenance changed JVM, class loader or artifact origin')
    return rows


def verify_outputs(consumer: Path, runtime: str, output: str) -> dict:
    prefix = 'ROUTECONTRACT_552_' if runtime == '5.5.2' else 'ROUTECONTRACT_'
    markers = [prefix + 'CORPUS repetitions=20 cases=8 uniqueSignaturesPerCase=1',
               prefix + 'POLICY_SENSITIVITY businessResult=UNCHANGED observedPhysicalAttempts=1->1 observedDataSourceSet=UNCHANGED strictStatus=DRIFT strictBlocking=true budgetOnlyStatus=REVIEW_REQUIRED budgetOnlyBlocking=false',
               prefix + 'FINGERPRINT_DRIFT_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->1 observedDataSourceAliases=[orders-odd]->[orders-odd] fingerprintMultiset=CHANGED parameterTypeShape=[Long]->[Long,Long] verificationStatus=DRIFT blockingCodes=[RCM301,RCM302] privacy=MINIMIZED']
    if runtime == '5.5.3':
        markers += ['ROUTECONTRACT_DETERMINISM repetitions=20 uniqueSignatures=1',
                    'ROUTECONTRACT_CONCURRENCY simultaneousPairs=20 mixedCaptures=0',
                    'ROUTECONTRACT_MANIFEST_DEMO businessResult=UNCHANGED observedPhysicalAttempts=1->2 verificationStatus=POLICY_VIOLATION blockingCodes=[RCM201,RCM202] privacy=MINIMIZED',
                    'ROUTECONTRACT_DATASOURCE_PROXY_COMPARISON businessRows=1->1 outerLogicalCallbacks=1->1 innerPhysicalCallbacks=1->2 routeContractAttempts=1->2 diyWiring=[physical-wrappers,ttl-correlation,minimization,canonicalization,diff,assertion]']
    if any(output.count(marker) != 1 for marker in markers) or 'ROUTECONTRACT_552_EVIDENCE_CANDIDATE' in output:
        raise CorpusError('Required exact corpus markers missing/duplicated, or generation bypass was enabled')
    build = consumer / 'build'
    if runtime == '5.5.2':
        goldens = consumer / 'src/test/resources/corpus/shardingsphere-5.5.2'
        generated = build / 'routecontract-552-corpus'
        expected = inventory(goldens)
        if len(expected) != 14 or inventory(generated) != expected:
            raise CorpusError('All fourteen generated 5.5.2 observations must equal unchanged version-specific goldens')
        output_dir = build / 'routecontract-552-evidence'
        pairs = [(name, name) for name in ('find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json',
                  'find-paid-orders-by-user.shardingsphere-5.5.2.schema2.candidate.json',
                  'find-paid-orders-by-user.shardingsphere-5.5.2.expected-diff.txt')]
        required_reports = {'review.md', 'review.json', 'cross-runtime-review.md', 'cross-runtime-review.json'}
    else:
        output_dir = build / 'routecontract-demo'
        pairs = [(f'find-paid-orders-by-user.{kind}.json', f'find-paid-orders-by-user.shardingsphere-5.5.3.schema2.{kind}.json')
                 for kind in ('approved', 'candidate')]
        required_reports = {'review.md', 'review.json'}
    for observed, golden in pairs:
        if (output_dir / observed).read_bytes() != (consumer / 'review-inputs/examples/manifests' / golden).read_bytes():
            raise CorpusError('Generated packaged-runtime observation differs from its existing golden')
    for name in required_reports:
        regular(output_dir / name)
        if not (output_dir / name).stat().st_size:
            raise CorpusError('Empty corpus report')
    return {'verifiedMarkers': markers, 'outputInventory': inventory(output_dir),
            'corpusGoldenComparisons': 14 if runtime == '5.5.2' else None,
            'generationEnabled': False, 'humanReview': None}


def run(command: list[str], cwd: Path, environment: dict, evidence: Path) -> tuple[int, str]:
    write_json(evidence.with_suffix('.command.json'), {'argv': command, 'cwd': str(cwd)})
    with evidence.open('w', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, timeout=TIMEOUT_SECONDS)
    write_json(evidence.with_suffix('.exit.json'), {'exitCode': result.returncode})
    return result.returncode, evidence.read_text(encoding='utf-8', errors='replace')


def revalidate_completed_lane(lane_root: Path, result: dict, contract: dict, receipt: dict) -> None:
    """Close retained lane evidence again after every runtime has finished; never rerun a JVM."""
    for name, expected in result['retainedEvidenceSha256'].items():
        regular(lane_root / name)
        if digest(lane_root / name) != expected:
            raise CorpusError('Retained lane evidence changed after its actual execution')
    if read_json(lane_root / 'summary.json') != result:
        raise CorpusError('Retained lane summary changed')
    consumer = lane_root / 'consumer'
    runtime = result['runtime']
    suites = contract['lanes'][runtime]['suites']
    verify_copies(consumer, read_json(lane_root / 'original-copy-map.json'))
    verify_consumer_inputs(consumer, read_json(lane_root / 'consumer-inputs.json'))
    if verify_junit(consumer / 'build/test-results/test', suites) != result['junit']:
        raise CorpusError('Retained corpus JUnit results changed')
    graphs = verify_graphs(consumer, runtime, receipt)
    if verify_provenance(consumer, runtime, suites, graphs, receipt) != result['provenance']:
        raise CorpusError('Retained same-JVM corpus provenance changed')
    if verify_outputs(consumer, runtime, (lane_root / 'gradle.log').read_text()) != result['outputs']:
        raise CorpusError('Retained corpus outputs changed')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--reviewed-receipt', type=Path, required=True)
    parser.add_argument('--reviewed-receipt-sha256', required=True)
    parser.add_argument('--staged-source-revision', required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--gradle-distribution-zip', type=Path, required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args(argv)
    repository = args.repository.expanduser().resolve(strict=True)
    receipt_path = args.reviewed_receipt.expanduser().absolute()
    evidence = args.evidence_directory.expanduser().resolve()
    if evidence.exists() or args.evidence_directory.is_symlink():
        raise CorpusError('A new absent evidence directory is required')
    for protected in (ROOT, repository):
        if evidence.is_relative_to(protected) or protected.is_relative_to(evidence):
            raise CorpusError('Evidence must be separate from source and staging')
    java = args.java_home.expanduser().resolve(strict=True)
    regular(java / 'bin/java')
    archive = args.gradle_distribution_zip.expanduser().absolute()
    regular(archive)
    if digest(archive) != GRADLE_SHA256:
        raise CorpusError('Gradle distribution differs from the checked-in wrapper pin')
    wrapper = (ROOT / 'gradle/wrapper/gradle-wrapper.properties').read_text()
    if f'distributionSha256Sum={GRADLE_SHA256}' not in wrapper or 'gradle-8.14.4-bin.zip' not in wrapper:
        raise CorpusError('Checked-in wrapper no longer matches the reviewed distribution pin')
    receipt, binding = reviewed_inputs(repository, receipt_path, args.reviewed_receipt_sha256, args.staged_source_revision)
    contract = read_json(FIXTURE / 'expected-corpus.json')
    originals = original_inputs(contract)
    fixtures = fixture_snapshot()
    staging = inventory(repository)
    evidence.mkdir(parents=True)
    summary = {'formatVersion': 1, 'requirement': 'A-23 final packaged runtime binding',
               'completePackagedRuntimeBinding': False, 'fullA23Complete': False, 'humanReview': None,
               'publicConsumption': False, 'preparationOnly': args.prepare_only, 'lanes': [],
               'stagedSourceRevision': args.staged_source_revision, 'corpusSourceRevision': contract['corpusSourceRevision'],
               'reviewedReceiptSha256': args.reviewed_receipt_sha256}
    write_json(evidence / 'summary.json', summary)
    write_json(evidence / 'source-binding.json', binding)
    write_json(evidence / 'original-inputs.json', originals)
    write_json(evidence / 'fixture-inputs.json', fixtures)
    write_json(evidence / 'staged-inventory.json', staging)
    shutil.copyfile(receipt_path, evidence / 'reviewed-staged-receipt.json')
    for name in fixtures:
        target = evidence / 'executed-fixture' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    source_helper = load_helper('verify-gradle-legacy-artifact-consumer.py')
    network = load_helper('consumer_network_sandbox.py')
    docker = network.local_docker_socket() if not args.prepare_only else None
    try:
        for runtime in ('5.5.3', '5.5.2'):
            lane = contract['lanes'][runtime]
            lane_root = evidence / runtime
            consumer = lane_root / 'consumer'
            copies = copy_consumer(consumer, runtime, contract, receipt)
            write_json(lane_root / 'original-copy-map.json', copies)
            cache = lane_root / 'gradle-home'
            if cache.exists():
                raise CorpusError('Each Gradle dependency cache must begin absent')
            source_helper.seed_distribution_zip(archive, cache)
            if (cache / 'caches').exists():
                raise CorpusError('A dependency cache was imported with the wrapper archive')
            private_home = lane_root / 'private-home'
            private_home.mkdir(mode=0o700)
            environment = network.controlled_environment(dict(os.environ), docker_socket=docker)
            environment = {k: v for k, v in environment.items() if not k.startswith('ORG_GRADLE_PROJECT_')}
            environment.update(JAVA_HOME=str(java), GRADLE_USER_HOME=str(cache),
                               JAVA_TOOL_OPTIONS='-Djava.net.preferIPv4Stack=true -Duser.home=' + str(private_home))
            arguments = [str(consumer / 'gradlew'), '--no-daemon', '--no-build-cache', '--no-configuration-cache',
                         '--rerun-tasks', '--dependency-verification=strict', '--console=plain',
                         f'-PpackagedRuntime={runtime}', f'-PpackagedRepository={repository}',
                         '-PpackagedExpectedSuites=' + ','.join(lane['suites'])]
            for module in ('routecontract-core', lane['adapter']):
                pin = next(p for p in receipt['artifacts'] if p['module'] == module and p['name'].endswith('.jar'))
                arguments.append(f'-PpackagedSha256.{module}={pin["sha256"]}')
            write_json(lane_root / 'planned-command.json', {'argv': [*arguments, 'clean', 'test'], 'cwd': str(consumer),
                                                          'environment': {k: environment[k] for k in ('JAVA_HOME', 'GRADLE_USER_HOME', 'JAVA_TOOL_OPTIONS')}})
            write_json(lane_root / 'initial-cache.json', {'dependencyCacheInitiallyAbsent': True,
                                                        'onlyReviewedWrapperZipSeeded': True, 'distributionSha256': GRADLE_SHA256})
            initial_consumer = inventory(consumer)
            write_json(lane_root / 'consumer-inputs.json', initial_consumer)
            if args.prepare_only:
                summary['lanes'].append({'runtime': runtime, 'prepared': True, 'complete': False})
                continue
            code, toolchain = run([str(consumer / 'gradlew'), '--no-daemon', '--version'], consumer, environment, lane_root / 'toolchain.log')
            if code or 'Gradle 8.14.4' not in toolchain or re.search(r'Launcher JVM:\s+17(?:[.]|\s)', toolchain) is None:
                raise CorpusError('The pinned Gradle distribution must actually run on Java 17')
            code, output = run([*arguments, 'clean', 'test'], consumer, environment, lane_root / 'gradle.log')
            if code:
                raise CorpusError(f'Actual packaged corpus failed for {runtime}; retain raw exit/log and outputs')
            junit = verify_junit(consumer / 'build/test-results/test', lane['suites'])
            graphs = verify_graphs(consumer, runtime, receipt)
            origins = verify_provenance(consumer, runtime, lane['suites'], graphs, receipt)
            results = verify_outputs(consumer, runtime, output)
            verify_copies(consumer, copies)
            verify_consumer_inputs(consumer, initial_consumer)
            result = {'runtime': runtime, 'complete': True, 'junit': junit, 'provenance': origins,
                      'outputs': results, 'graphSha256': digest(consumer / 'build/packaged-corpus/selected-graphs.json'),
                      'originalCopiesUnchanged': True, 'testCount': 14, 'corpusShapes': 8,
                      'repetitionsPerShape': 20, 'concurrentlyOpenCapturePairs': 20,
                      'isolationBoundary': 'Concurrently open caller capture scopes; physical callback overlap not forced or measured.'}
            names = ['original-copy-map.json', 'consumer-inputs.json', 'initial-cache.json', 'planned-command.json',
                     'toolchain.log', 'toolchain.command.json', 'toolchain.exit.json',
                     'gradle.log', 'gradle.command.json', 'gradle.exit.json',
                     'consumer/build/packaged-corpus/selected-graphs.json',
                     'consumer/build/packaged-corpus/test-runtime-classpath.json']
            result['retainedEvidenceSha256'] = {name: digest(lane_root / name) for name in names}
            write_json(lane_root / 'summary.json', result)
            summary['lanes'].append(result)
            write_json(evidence / 'summary.json', summary)
            print(f'PACKAGED_CORPUS_LANE_VERIFIED runtime={runtime} existingTests=14', flush=True)
        if not args.prepare_only:
            for result in summary['lanes']:
                revalidate_completed_lane(evidence / result['runtime'], result, contract, receipt)
            summary['allRetainedLaneEvidenceUnchanged'] = True
        if (original_inputs(contract) != originals or fixture_snapshot() != fixtures
                or inventory(repository) != staging or digest(receipt_path) != args.reviewed_receipt_sha256):
            raise CorpusError('Final corpus/fixture/staging/receipt inputs changed')
        if reviewed_inputs(repository, receipt_path, args.reviewed_receipt_sha256, args.staged_source_revision)[1] != binding:
            raise CorpusError('Final staged production/publication source binding changed')
        summary['finalInputsUnchanged'] = True
        summary['completePackagedRuntimeBinding'] = not args.prepare_only and len(summary['lanes']) == 2
        write_json(evidence / 'summary.json', summary)
        print('PACKAGED_CORPUS_PREPARED' if args.prepare_only else 'PACKAGED_CORPUS_VERIFIED existingTests=28 humanReview=null', flush=True)
        return 0
    except Exception as error:
        summary['error'] = f'{type(error).__name__}: {error}'
        write_json(evidence / 'summary.json', summary)
        raise


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as failure:
        print(f'PACKAGED_CORPUS_FAILED: {type(failure).__name__}: {failure}', file=sys.stderr)
        raise SystemExit(1)
