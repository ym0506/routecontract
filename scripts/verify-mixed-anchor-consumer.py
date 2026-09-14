#!/usr/bin/env python3
"""Observe the complete nominal A-09 manual mixed-anchor matrix; retain diagnostic failures."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from legacy_artifact_inputs import digest
from public_split_artifacts import load_consumer_receipt
GROUP = 'io.github.ym0506.routecontract'
SS = 'org.apache.shardingsphere'
VERSIONS = ('5.5.2', '5.5.3')
ADAPTERS = {'5.5.2': 'routecontract-shardingsphere-5.5.2', '5.5.3': 'routecontract-shardingsphere-5.5'}
DATABASE_MODULES = {'5.5.2': 'shardingsphere-infra-database-core', '5.5.3': 'shardingsphere-database-connector-core'}
DATABASE_CLASSES = {'5.5.2': 'org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties',
                    '5.5.3': 'org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties'}
ANCHOR_MODULES = {'shardingsphere-infra-executor', 'shardingsphere-infra-spi', *DATABASE_MODULES.values()}
FIXTURE = ROOT / 'examples/mixed-anchor-consumer'
PROBE = 'io.github.ym0506.routecontract.consumer.MixedAnchorProbe'
MARKER = 'RC_MIXED_SHARDINGSPHERE_RUNTIME'

class RuntimeAcceptanceError(RuntimeError):
    pass

def load_helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    helper = importlib.util.module_from_spec(spec)
    sys.modules[name] = helper
    spec.loader.exec_module(helper)
    return helper

def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def cases():
    result = []
    for executor, spi, database in itertools.product(VERSIONS, repeat=3):
        clean = executor == spi == database
        for order in ('forward',) if clean else ('forward', 'reverse'):
            result.append({'id': f'e{executor}-s{spi}-d{database}-{order}',
                'executor': executor, 'spi': spi, 'database': database, 'adapter': database,
                'order': order, 'category': 'clean' if clean else 'mixed',
                'expected': 'CLEAN_NO_SQL' if clean else MARKER})
    return result

def anchor_classes(adapter):
    return {'executor': 'org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook',
            'spi': 'org.apache.shardingsphere.infra.spi.' +
                ('ShardingSphereServiceLoader' if adapter == '5.5.2' else 'ShardingSphereSPI'),
            'database': DATABASE_CLASSES[adapter]}

def selected_anchor(case, graphs, role):
    module = {'executor': 'shardingsphere-infra-executor', 'spi': 'shardingsphere-infra-spi',
              'database': DATABASE_MODULES[case['database']]}[role]
    matches = [item for item in graphs[case[role]]['artifacts'] if item['group'] == SS and item['module'] == module]
    if len(matches) != 1:
        raise RuntimeAcceptanceError('Expected one real official artifact for each anchor role')
    return matches[0]

def assemble_classpath(case, graphs):
    graph = graphs[case['adapter']]
    anchors = [selected_anchor(case, graphs, role)['path'] for role in ('executor', 'spi', 'database')]
    if case['order'] == 'reverse':
        anchors.reverse()
    rest = [item['path'] for item in graph['artifacts']
            if not (item['group'] == SS and item['module'] in ANCHOR_MODULES)]
    paths = [*graph['classes'], *anchors, *rest]
    if len(paths) != len(set(paths)):
        raise RuntimeAcceptanceError('Duplicate launch path')
    return paths

def expected_anchors(case, graphs):
    expected = {}
    for role, name in anchor_classes(case['adapter']).items():
        item = selected_anchor(case, graphs, role)
        path = Path(item['path'])
        with zipfile.ZipFile(path) as jar:
            names = set(jar.namelist())
            manifest = jar.read('META-INF/MANIFEST.MF').decode('utf-8').replace('\r\n', '\n')
        version = next((line.split(': ', 1)[1] for line in manifest.splitlines()
                        if line.startswith('Implementation-Version: ')), None)
        if version != case[role]:
            raise RuntimeAcceptanceError('Official anchor manifest does not match its resolved version')
        expected[role] = {'className': name, 'origin': str(path), 'sha256': item['sha256'],
                          'implementationVersion': version,
                          'classResourcePresent': name.replace('.', '/') + '.class' in names,
                          'module': item['module']}
    return expected

def verify_launch_inputs(paths, graphs):
    pins = {item['path']: item['sha256'] for graph in graphs.values() for item in graph['artifacts']}
    class_dirs = {directory for graph in graphs.values() for directory in graph['classes']}
    result = []
    for value in paths:
        if value in class_dirs:
            continue
        path = Path(value)
        if value not in pins or path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != pins[value]:
            raise RuntimeAcceptanceError('Launch artifact is absent, unpinned or changed')
        result.append({'path': value, 'sha256': pins[value]})
    for graph in graphs.values():
        if class_hashes(graph['classes']) != graph['compiledClasses']:
            raise RuntimeAcceptanceError('Compiled fixture bytes changed')
    return result

def classify(case, observed, anchors, core):
    required = {'pid', 'javaVersion', 'adapter', 'returned', 'actionEntries', 'snapshot',
                'exceptionClasses', 'exceptionMessages', 'stackFrames', 'linkageFailure', 'newEntry', 'anchors'}
    if not isinstance(observed, dict) or set(observed) != required:
        return 'MISSING_OBSERVATION'
    if (type(observed['pid']) is not int or observed['pid'] < 1 or type(observed['actionEntries']) is not int
            or observed['actionEntries'] < 0 or type(observed['returned']) is not bool
            or type(observed['linkageFailure']) is not bool):
        return 'INVALID_OBSERVATION'
    for key in ('exceptionClasses', 'exceptionMessages', 'stackFrames'):
        if not isinstance(observed[key], list) or any(not isinstance(value, str) for value in observed[key]):
            return 'INVALID_OBSERVATION'
    if len(observed['exceptionClasses']) != len(observed['exceptionMessages']):
        return 'INVALID_OBSERVATION'
    if not isinstance(observed['javaVersion'], str) or not observed['javaVersion'].startswith('17.') or observed['adapter'] != case['adapter']:
        return 'WRONG_ENVIRONMENT'
    entry = {'className': 'io.github.ym0506.routecontract.api.RouteContract', 'loaded': True,
             'implementationVersion': '0.2.0', 'origin': core['path'], 'sha256': core['sha256']}
    if observed['newEntry'] != entry:
        return 'WRONG_CURRENT_ENTRY_ORIGIN'
    if not isinstance(observed['anchors'], dict) or set(observed['anchors']) != set(anchors):
        return 'MISSING_ANCHOR_OBSERVATION'
    loaded = True
    for role, expected in anchors.items():
        actual = observed['anchors'][role]
        if not isinstance(actual, dict) or type(actual.get('loaded')) is not bool or actual.get('className') != expected['className']:
            return 'INVALID_ANCHOR_OBSERVATION'
        if actual['loaded']:
            wanted = {key: expected[key] for key in ('className', 'origin', 'sha256', 'implementationVersion')}
            if not expected['classResourcePresent'] or actual != {**wanted, 'loaded': True}:
                return 'WRONG_ANCHOR_ORIGIN'
        else:
            if set(actual) != {'className', 'loaded', 'loadFailureClass', 'loadFailureMessage'} or not isinstance(actual['loadFailureClass'], str) or not actual['loadFailureClass'] or not isinstance(actual['loadFailureMessage'], str):
                return 'INVALID_ANCHOR_OBSERVATION'
            loaded = False
    if case['category'] == 'clean':
        runtime = case['adapter']
        snapshot = {'schemaVersion': 2, 'status': 'INCOMPLETE', 'observedPhysicalAttemptCount': 0,
                    'collectorDiagnostics': ['RC_NO_START_CALLBACK_OBSERVED'],
                    'runtimeIdentity': {'adapterId': 'apache-shardingsphere-jdbc/sql-execution-hook',
                     'adapterContractVersion': 1, 'infraExecutorImplementationVersion': runtime,
                     'infraSpiImplementationVersion': runtime, 'supported': True}}
        observed_identity = observed['snapshot'].get('runtimeIdentity') if isinstance(observed['snapshot'], dict) else None
        good = (isinstance(observed_identity, dict) and type(observed_identity.get('supported')) is bool
                and loaded and observed['returned'] and observed['actionEntries'] == 1
                and observed['snapshot'] == snapshot and not observed['exceptionClasses']
                and not observed['stackFrames'] and not observed['linkageFailure'])
        return 'PASS' if good else 'CONTROL_FAILED'
    if observed['returned'] or observed['actionEntries'] != 0 or observed['snapshot'] is not None:
        return 'ACTION_OR_RESULT_ESCAPED'
    if observed['linkageFailure']:
        return 'LINKAGE_FAILURE'
    if not observed['exceptionClasses'] or not observed['exceptionMessages'][0].startswith(MARKER + ':'):
        return 'WRONG_DIAGNOSTIC'
    guard = 'io.github.ym0506.routecontract.shardingsphere' + case['adapter'].replace('.', '') + '.internal.ShardingSphere' + case['adapter'].replace('.', '') + 'HookConstructionGuard.'
    if not any(frame.startswith(guard) for frame in observed['stackFrames']):
        return 'GUARD_NOT_OBSERVED'
    # Missing official anchor classes remain observed; exact pre-action rejection is the gate.
    return 'PASS'

def completion_status(results, partial=False):
    plan = {case['id']: case for case in cases()}
    exact = (len(results) == 14 and len({row['case']['id'] for row in results}) == 14
             and all(row['case'] == plan.get(row['case']['id']) for row in results))
    pids = [row.get('observed', {}).get('pid') for row in results]
    fresh = all(type(pid) is int and pid > 0 for pid in pids) and len(set(pids)) == len(pids)
    passed = sum(row['outcome'] == 'PASS' for row in results)
    status = ('FAILED' if passed != len(results) else 'VERIFIED' if exact and fresh and not partial else 'INCOMPLETE')
    return {'status': status, 'fullManualA09Matrix': status == 'VERIFIED', 'fullA09Acceptance': False,
            'executedCount': len(results), 'passedCount': passed, 'distinctFreshJvmPids': fresh}

def prepare_lane(runtime, evidence, repository, receipt, seed, java_home, staged, split):
    lane = evidence / 'lanes' / runtime
    lane.mkdir(parents=True)
    consumer = lane / 'consumer'
    staged.copy_consumer(ROOT, consumer, runtime, receipt)
    shutil.rmtree(consumer / 'src')
    shutil.copytree(FIXTURE / 'src', consumer / 'src')
    shutil.copyfile(FIXTURE / 'runtime-evidence.gradle', consumer / 'runtime-evidence.gradle')
    with (consumer / 'build.gradle').open('a') as output:
        output.write("\napply from: 'runtime-evidence.gradle'\n")
    cache = lane / 'gradle-home'
    cache.mkdir()
    split.seed_wrapper_distribution(seed, cache)
    if (cache / 'caches').exists():
        raise RuntimeAcceptanceError('Runtime lane did not begin with an absent dependency cache')
    command = [str(consumer / 'gradlew'), '--no-daemon', '--no-build-cache', '--no-configuration-cache',
               '--dependency-verification=strict', '--console=plain', '--max-workers=2',
               f'-ProutecontractRuntime={runtime}', f'-ProutecontractRepository={repository}']
    for module in ('routecontract-core', ADAPTERS[runtime]):
        pin = next(p for p in receipt['artifacts'] if p['module'] == module and p['name'].endswith('.jar'))
        command.append(f'-ProutecontractSha256.{module}={pin["sha256"]}')
    command.append('prepareMixedAnchorRuntimeClasspath')
    write_json(lane / 'command.json', {'argv': command, 'JAVA_HOME': str(java_home),
               'GRADLE_USER_HOME': str(cache), 'dependencyCacheInitiallyAbsent': True})
    with (lane / 'gradle.log').open('w') as log:
        completed = subprocess.run(command, cwd=consumer, env=split.clean_environment(java_home, cache),
                                   stdout=log, stderr=subprocess.STDOUT, timeout=1200, check=False)
    if completed.returncode:
        raise RuntimeAcceptanceError(f'Runtime {runtime} compilation/resolution failed; inspect {lane / "gradle.log"}')
    graph = json.loads((consumer / 'build/mixed-anchor-runtime-classpath.json').read_text())
    first_party = [item for item in graph['artifacts'] if item['group'] == GROUP]
    if sorted((item['module'], item['version']) for item in first_party) != sorted([
            ('routecontract-core', '0.2.0'), (ADAPTERS[runtime], '0.2.0')]):
        raise RuntimeAcceptanceError('Unexpected first-party runtime artifact set')
    sharding = [item for item in graph['artifacts'] if item['group'] == 'org.apache.shardingsphere']
    if not sharding or any(item['version'] != runtime for item in sharding):
        raise RuntimeAcceptanceError('Whole ShardingSphere group is not the exact lane version')
    for item in graph['artifacts']:
        path = Path(item['path'])
        if not path.is_file() or path.is_symlink() or digest(path.read_bytes()) != item['sha256']:
            raise RuntimeAcceptanceError('Resolved runtime bytes changed')
        if item['group'] == GROUP:
            pin = next(p for p in receipt['artifacts'] if p['module'] == item['module'] and p['name'].endswith('.jar'))
            if item['sha256'] != pin['sha256']:
                raise RuntimeAcceptanceError('Resolved current artifact differs from reviewed staged receipt')
    graph['compiledClasses'] = class_hashes(graph['classes'])
    write_json(lane / 'resolved-classpath.json', graph)
    print(f'A09_PREPARED_RUNTIME {runtime}', flush=True)
    return graph


def class_hashes(directories):
    result = {}
    for directory in directories:
        root = Path(directory)
        if root.is_symlink() or not root.is_dir():
            raise RuntimeAcceptanceError('Fixture output must be a regular directory')
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                raise RuntimeAcceptanceError('Fixture classes must not be symlinks')
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                if not relative.startswith('io/github/ym0506/routecontract/consumer/') or not relative.endswith('.class'):
                    raise RuntimeAcceptanceError('Unexpected production/non-fixture class in consumer output')
                result[str(path)] = digest(path.read_bytes())
    if not result:
        raise RuntimeAcceptanceError('No compiled consumer class evidence')
    return result


def fingerprint_inputs():
    files = [Path(__file__).resolve(), ROOT / 'scripts/tests/test_verify_mixed_anchor_consumer.py',
        ROOT / 'docs/mixed-anchor-acceptance.md', ROOT / 'AGENTS.md',
        ROOT / 'scripts/legacy_artifact_inputs.py', ROOT / 'scripts/public_split_artifacts.py',
        ROOT / 'scripts/verify-gradle-legacy-artifact-consumer.py',
        ROOT / 'scripts/verify-gradle-split-artifact-consumer.py',
        ROOT / 'scripts/verify-staged-split-artifact-consumer.py',
        ROOT / 'gradle/verification-metadata.xml', ROOT / 'gradlew',
        *sorted((ROOT / 'gradle/wrapper').rglob('*')), *sorted(FIXTURE.rglob('*')),
        ROOT / 'examples/staged-split-artifact-consumer/build.gradle',
        ROOT / 'examples/staged-split-artifact-consumer/settings.gradle',
        *sorted((ROOT / 'examples/staged-split-artifact-consumer/gradle-locks').rglob('*'))]
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in files if path.is_file()}

def repository_inventory(repository):
    result = {}
    for path in sorted(repository.rglob('*')):
        if path.is_symlink():
            raise RuntimeAcceptanceError('Staging must not contain symlinks')
        if path.is_file():
            result[path.relative_to(repository).as_posix()] = digest(path.read_bytes())
    return result

def run_case(case, evidence, graphs, java_home, environment):
    destination = evidence / 'cases' / case['id']
    destination.mkdir(parents=True)
    paths = assemble_classpath(case, graphs)
    anchors = expected_anchors(case, graphs)
    core = next(item for item in graphs[case['adapter']]['artifacts'] if item['group'] == GROUP and item['module'] == 'routecontract-core')
    observed_path = destination / 'observed.json'
    command = [str(java_home / 'bin/java'), '-Dorg.slf4j.simpleLogger.defaultLogLevel=warn',
               '-cp', os.pathsep.join(paths), PROBE, case['adapter'], str(observed_path)]
    inputs = verify_launch_inputs(paths, graphs)
    write_json(destination / 'command.json', {'argv': command, 'case': case, 'freshJvm': True,
        'expectedAnchors': anchors, 'expectedCore': core, 'launchArtifacts': inputs,
        'compiledClasses': graphs[case['adapter']]['compiledClasses']})
    started = time.monotonic()
    code = None
    with (destination / 'jvm.log').open('w') as log:
        try:
            code = subprocess.run(command, cwd=destination, env=environment, stdout=log,
                stderr=subprocess.STDOUT, timeout=120, check=False).returncode
        except subprocess.TimeoutExpired:
            pass
    row = {'case': case, 'exitCode': code, 'outcome': 'PROCESS_FAILED' if code is not None else 'PROCESS_TIMEOUT',
           'elapsedSeconds': round(time.monotonic() - started, 3),
           'commandSha256': digest((destination / 'command.json').read_bytes()),
           'logSha256': digest((destination / 'jvm.log').read_bytes())}
    if code == 0 and observed_path.is_file() and not observed_path.is_symlink():
        try:
            row['observed'] = json.loads(observed_path.read_text())
            row['observedSha256'] = digest(observed_path.read_bytes())
            row['outcome'] = classify(case, row['observed'], anchors, core)
        except (ValueError, TypeError):
            row['outcome'] = 'MALFORMED_OBSERVATION'
    row['launchInputsUnchanged'] = verify_launch_inputs(paths, graphs) == inputs
    if not row['launchInputsUnchanged']:
        row['outcome'] = 'INPUT_CHANGED'
    write_json(destination / 'result.json', row)
    print(f'A09_CASE {case["id"]} {row["outcome"]}', flush=True)
    return row

def write_junit(evidence, results):
    suite = ET.Element('testsuite', name='A09MixedAnchorFreshJvmAssertions', tests=str(len(results)),
        failures=str(sum(row['outcome'] != 'PASS' for row in results)), errors='0', skipped='0')
    for row in results:
        test = ET.SubElement(suite, 'testcase', classname='A09MixedAnchorFreshJvmAssertions',
            name=row['case']['id'], time=str(row['elapsedSeconds']))
        if row['outcome'] != 'PASS':
            ET.SubElement(test, 'failure', message=row['outcome']).text = json.dumps(row.get('observed', {}), sort_keys=True)
    ET.indent(suite)
    ET.ElementTree(suite).write(evidence / 'TEST-a09-subprocess-assertions.xml', encoding='utf-8', xml_declaration=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--staged-receipt', required=True, type=Path)
    parser.add_argument('--expected-staged-receipt-sha256', required=True)
    parser.add_argument('--staged-source-revision', required=True)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--gradle-distribution-zip', required=True, type=Path)
    parser.add_argument('--case', action='append', dest='case_ids')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    evidence = args.evidence_directory.expanduser().resolve()
    repository = args.repository.expanduser().resolve()
    if evidence.exists() or evidence == ROOT or ROOT in evidence.parents or repository in evidence.parents:
        raise RuntimeAcceptanceError('Evidence must be new and outside checkout and staged repository')
    evidence.mkdir(parents=True, mode=0o700)
    initial = fingerprint_inputs()
    receipt_bytes = args.staged_receipt.read_bytes()
    if digest(receipt_bytes) != args.expected_staged_receipt_sha256:
        raise RuntimeAcceptanceError('Receipt differs from independently reviewed digest')
    receipt = load_consumer_receipt(args.staged_receipt)
    if receipt['routeContractVersion'] != '0.2.0':
        raise RuntimeAcceptanceError('Expected coordinated 0.2.0 candidate')
    legacy = load_helper('a09_legacy', 'verify-gradle-legacy-artifact-consumer.py')
    staged = load_helper('a09_staged', 'verify-staged-split-artifact-consumer.py')
    split = load_helper('a09_split', 'verify-gradle-split-artifact-consumer.py')
    staged.verify_receipt(repository, receipt)
    inventory = repository_inventory(repository)
    binding = legacy.source_binding(args.staged_source_revision)
    write_json(evidence / 'source-binding.json', binding)
    write_json(evidence / 'fixture-inputs.json', initial)
    write_json(evidence / 'staged-inventory.json', inventory)
    (evidence / 'staged-receipt.json').write_bytes(receipt_bytes)
    required = cases()
    selected = required
    if args.case_ids:
        if len(args.case_ids) != len(set(args.case_ids)) or set(args.case_ids) - {case['id'] for case in required}:
            raise RuntimeAcceptanceError('Unknown or duplicate case ID')
        selected = [case for case in required if case['id'] in args.case_ids]
    write_json(evidence / 'case-plan.json', {'requiredCount': 14, 'mixedCount': 12, 'cleanCount': 2,
        'required': required, 'selected': selected, 'unchangedOriginalExpectedMixedMarker': MARKER})
    java_home = args.java_home.resolve()
    split.verify_toolchain(ROOT, java_home)
    seed = evidence / 'wrapper-seed'
    seed.mkdir()
    legacy.seed_distribution_zip(args.gradle_distribution_zip.resolve(), seed)
    split.prepare_wrapper_seed(ROOT, ROOT / 'gradlew', java_home, seed)
    version = subprocess.check_output([str(ROOT / 'gradlew'), '--no-daemon', '--version'], cwd=ROOT,
        env=split.clean_environment(java_home, seed), text=True, stderr=subprocess.STDOUT, timeout=60)
    (evidence / 'toolchain.txt').write_text(version)
    with ThreadPoolExecutor(max_workers=2) as pool:
        graphs = dict(zip(VERSIONS, pool.map(lambda runtime: prepare_lane(runtime, evidence, repository,
            receipt, seed, java_home, staged, split), VERSIONS)))
    launches = []
    for case in selected:
        paths = assemble_classpath(case, graphs)
        launches.append({'case': case, 'classpath': paths, 'anchors': expected_anchors(case, graphs),
            'launchArtifacts': verify_launch_inputs(paths, graphs)})
    write_json(evidence / 'prepared-launches.json', launches)
    results = []
    if not args.prepare_only:
        for case in selected:
            results.append(run_case(case, evidence, graphs, java_home, split.clean_environment(java_home, seed)))
        write_junit(evidence, results)
    staged.verify_receipt(repository, receipt)
    if (repository_inventory(repository) != inventory or fingerprint_inputs() != initial
            or legacy.source_binding(args.staged_source_revision) != binding
            or args.staged_receipt.read_bytes() != receipt_bytes):
        raise RuntimeAcceptanceError('Fixture, staging, receipt or production source changed')
    summary = {**completion_status(results, partial=bool(args.case_ids or args.prepare_only)),
        'preparedOnly': args.prepare_only, 'sourceBinding': binding,
        'stagedReceiptSha256': digest(receipt_bytes), 'requiredCount': 14,
        'fixtureInputsUnchanged': True, 'stagingUnchanged': True, 'results': results,
        'scope': 'Java 17 current capture; six nominal manual tuples in both anchor orders plus two clean controls; no SQL, resolver, public-release or arbitrary non-anchor claim'}
    write_json(evidence / 'summary.json', summary)
    print(f'A09_RESULT {summary["status"]} {summary["passedCount"]}/{summary["executedCount"]}', flush=True)
    return 0 if args.prepare_only or summary['status'] == 'VERIFIED' else 1 if summary['status'] == 'FAILED' else 2

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except RuntimeAcceptanceError as error:
        print('A09_ERROR ' + str(error), file=sys.stderr)
        raise SystemExit(1)
