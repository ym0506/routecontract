#!/usr/bin/env python3
"""Execute the separate A-29 current-entry contract; original A-28 remains FAILED."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
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
from legacy_artifact_inputs import ARTIFACT, GROUP, digest, load_registry
from public_split_artifacts import load_consumer_receipt

FIXTURE = ROOT / 'examples/current-entry-successor-consumer'
BASE_FIXTURE = ROOT / 'examples/staged-split-artifact-consumer'
REGISTRY = ROOT / 'scripts/legacy-artifact-inputs.json'
ADAPTERS = {'5.5.2': 'routecontract-shardingsphere-5.5.2', '5.5.3': ARTIFACT}
LEGACIES = {'0.1.0', '0.1.2', '0.1.3', '0.1.0-rc2'}
MYSQL_IMAGE = 'mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb'
PROBE = 'io.github.ym0506.routecontract.consumer.CurrentEntrySuccessorProbe'
CURRENT_CLASSES = ('io/github/ym0506/routecontract/api/RouteContract.class',
                   'io/github/ym0506/routecontract/internal/CurrentRuntimeGuard.class')
PRESERVED = ('docs/legacy-runtime-collision-acceptance.md',
             'docs/legacy-runtime-collision-feasibility.md',
             'docs/evidence/legacy-runtime-collision-2026-09-08.md',
             'docs/evidence/current-entry-regression-2026-09-08.md',
             'scripts/verify-legacy-runtime-collision.py',
             'scripts/verify-current-entry-regression.py',
             'docs/evidence/legacy-runtime-collision-2026-09-08.json',
             'docs/evidence/current-entry-regression-2026-09-08.json')
ROWS = ['201:3:PAID']


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


def cases(registry):
    versions = [item['version'] for item in registry['distributed']]
    if len(versions) != 4 or set(versions) != LEGACIES:
        raise RuntimeAcceptanceError('A-29 requires exactly the four audited distributed legacy versions')
    result = []
    for runtime in ADAPTERS:
        for mode in ('current-capture', 'current-capture-result', 'compatibility-capture',
                     'compatibility-capture-result', 'sql', 'startup-sql'):
            expected = {'sql': 'CLEAN_SQL', 'startup-sql': 'CLEAN_CAPTURED_SQL'}.get(mode, 'CLEAN_NO_SQL')
            result.append({'id': f'{runtime}-clean-{mode}', 'runtime': runtime, 'mode': mode,
                           'legacy': None, 'order': None, 'adapter': runtime,
                           'expected': expected, 'category': 'clean'})
        for legacy in versions:
            for order in ('legacy-first', 'legacy-last'):
                for mode in ('current-capture', 'current-capture-result', 'sql'):
                    result.append({'id': f'{runtime}-{legacy}-{order}-{mode}', 'runtime': runtime,
                                   'mode': mode, 'legacy': legacy, 'order': order, 'adapter': runtime,
                                   'expected': 'COLLISION',
                                   'category': 'sql-collision' if mode == 'sql' else 'capture-collision'})
        for adapter, label, marker in ((None, 'missing-adapter', 'RC_ADAPTER_NOT_FOUND'),
                (next(version for version in ADAPTERS if version != runtime),
                 'wrong-adapter', 'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME')):
            result.append({'id': f'{runtime}-{label}-startup', 'runtime': runtime, 'mode': 'startup',
                           'legacy': None, 'order': None, 'adapter': adapter, 'expected': marker,
                           'category': 'startup-rejection'})
    return result


def identity(runtime):
    return {'adapterId': 'apache-shardingsphere-jdbc/sql-execution-hook', 'adapterContractVersion': 1,
            'infraExecutorImplementationVersion': runtime, 'infraSpiImplementationVersion': runtime}


def exact_identity(value, runtime):
    return (isinstance(value, dict) and type(value.get('adapterContractVersion')) is int
            and value == identity(runtime))


def exact_snapshot(value, runtime, sql):
    expected = {'schemaVersion': 2, 'status': 'COMPLETE' if sql else 'INCOMPLETE',
                'observedPhysicalAttemptCount': 1 if sql else 0,
                'collectorDiagnostics': [] if sql else ['RC_NO_START_CALLBACK_OBSERVED'],
                'runtimeIdentity': identity(runtime)}
    return (isinstance(value, dict) and type(value.get('schemaVersion')) is int
            and type(value.get('observedPhysicalAttemptCount')) is int
            and exact_identity(value.get('runtimeIdentity'), runtime) and value == expected)


def classify(case, observed, expected_origins):
    required = {'mode', 'pid', 'javaVersion', 'shardingSphereVersion', 'returned', 'actionEntered',
                'actionEntries', 'physicalBusinessExecutions', 'businessRows', 'datasourceConstructionEntered',
                'captureSnapshot', 'resultValue', 'verifiedRuntimeIdentity', 'exceptionClasses',
                'exceptionMessages', 'stackFrames', 'linkageFailure', 'newEntryOrigin', 'guardOrigin',
                'compatibilityEntryOrigin', 'captureRegistryOrigin'}
    if not isinstance(observed, dict) or not required.issubset(observed):
        return 'MISSING_OBSERVATION'
    for field in ('pid', 'actionEntries', 'physicalBusinessExecutions'):
        if type(observed[field]) is not int or observed[field] < (1 if field == 'pid' else 0):
            return 'INVALID_OBSERVATION'
    for field in ('returned', 'actionEntered', 'datasourceConstructionEntered', 'linkageFailure'):
        if type(observed[field]) is not bool:
            return 'INVALID_OBSERVATION'
    for field in ('businessRows', 'exceptionClasses', 'exceptionMessages', 'stackFrames'):
        if not isinstance(observed[field], list) or any(not isinstance(item, str) for item in observed[field]):
            return 'INVALID_OBSERVATION'
    if (observed['actionEntered'] != (observed['actionEntries'] != 0)
            or len(observed['exceptionClasses']) != len(observed['exceptionMessages'])):
        return 'INCONSISTENT_OBSERVATION'
    if (observed['mode'] != case['mode'] or not isinstance(observed['javaVersion'], str)
            or not observed['javaVersion'].startswith('17.')
            or observed['shardingSphereVersion'] != case['runtime']):
        return 'WRONG_EXECUTION_ENVIRONMENT'
    if (set(expected_origins) != {'newEntryOrigin', 'guardOrigin', 'compatibilityEntryOrigin', 'captureRegistryOrigin'}
            or any(observed.get(key) != value for key, value in expected_origins.items())):
        return 'UNEXPECTED_CLASS_ORIGIN'
    linkage = ('LinkageError', 'AbstractMethodError', 'NoSuchMethodError', 'NoClassDefFoundError',
               'IncompatibleClassChangeError', 'ExceptionInInitializerError', 'UnsatisfiedLinkError',
               'ClassFormatError', 'VerifyError', 'BootstrapMethodError', 'IllegalAccessError',
               'NoSuchFieldError', 'InstantiationError')
    if observed['linkageFailure'] or any(name.rsplit('.', 1)[-1] in linkage for name in observed['exceptionClasses']):
        return 'LINKAGE_FAILURE'
    expected = case['expected']
    if expected.startswith('CLEAN_'):
        if not observed['returned'] or observed['exceptionClasses'] or observed['stackFrames']:
            return 'CONTROL_FAILED'
        if expected == 'CLEAN_NO_SQL':
            good = (observed['actionEntries'] == 1 and observed['physicalBusinessExecutions'] == 0
                    and observed['businessRows'] == [] and not observed['datasourceConstructionEntered']
                    and observed['verifiedRuntimeIdentity'] is None
                    and exact_snapshot(observed['captureSnapshot'], case['runtime'], False)
                    and observed['resultValue'] == ('current-entry-sentinel'
                         if case['mode'].endswith('-result') else None))
        elif expected == 'CLEAN_SQL':
            good = (observed['actionEntries'] == 0 and observed['physicalBusinessExecutions'] == 1
                    and observed['businessRows'] == ROWS and observed['datasourceConstructionEntered']
                    and observed['captureSnapshot'] is None and observed['resultValue'] is None
                    and observed['verifiedRuntimeIdentity'] is None)
        elif expected == 'CLEAN_CAPTURED_SQL':
            good = (observed['actionEntries'] == 1 and observed['physicalBusinessExecutions'] == 1
                    and observed['businessRows'] == ROWS and observed['datasourceConstructionEntered']
                    and observed['resultValue'] == ROWS
                    and exact_snapshot(observed['captureSnapshot'], case['runtime'], True)
                    and exact_identity(observed['verifiedRuntimeIdentity'], case['runtime']))
        else:
            good = False
        return 'PASS' if good else 'CONTROL_FAILED'
    if observed['actionEntries'] or observed['physicalBusinessExecutions'] or observed['businessRows']:
        return 'ACTION_OR_SQL_EXECUTED'
    if observed['returned']:
        return 'SILENT_SUCCESS'
    if any(observed[field] is not None for field in ('captureSnapshot', 'resultValue', 'verifiedRuntimeIdentity')):
        return 'UNEXPECTED_RESULT'
    if observed['datasourceConstructionEntered'] != (case['mode'] == 'sql'):
        return 'WRONG_DATASOURCE_BOUNDARY'
    marker = 'RC_LEGACY_ADAPTER_COLLISION' if expected == 'COLLISION' else expected
    if (not observed['exceptionClasses'] or not observed['stackFrames']
            or not any(marker + ':' in message for message in observed['exceptionMessages'])):
        return 'WRONG_DIAGNOSTIC'
    if case['mode'].startswith('current-') and not any(
            frame.startswith('io.github.ym0506.routecontract.internal.CurrentRuntimeGuard.')
            for frame in observed['stackFrames']):
        return 'CURRENT_GUARD_NOT_OBSERVED'
    if case['mode'] == 'sql':
        lane = case['runtime'].replace('.', '')
        guard = (f'io.github.ym0506.routecontract.shardingsphere{lane}.internal.'
                 f'ShardingSphere{lane}HookConstructionGuard.')
        if not any(frame.startswith(guard) for frame in observed['stackFrames']):
            return 'HOOK_CONSTRUCTION_GUARD_NOT_OBSERVED'
    return 'PASS'


def completion_status(required, results, partial=False):
    canonical = cases(load_registry(REGISTRY))
    required_by_id = {case['id']: case for case in canonical}
    exact_plan = (len(required) == 64 and len({case['id'] for case in required}) == 64
                  and {case['id']: case for case in required} == required_by_id)
    actual_ids = [result.get('case', {}).get('id') for result in results]
    pids = [result.get('observed', {}).get('pid') for result in results]
    exact_results = (len(results) == 64 and len(set(actual_ids)) == 64
                     and set(actual_ids) == set(required_by_id)
                     and all(result['case'] == required_by_id.get(result['case']['id']) for result in results))
    fresh = all(type(pid) is int and pid > 0 for pid in pids) and len(set(pids)) == len(pids)
    passed = sum(result.get('outcome') == 'PASS' for result in results)
    status = ('FAILED' if passed != len(results) else
              'VERIFIED' if exact_plan and exact_results and fresh and not partial else 'INCOMPLETE')
    return {'status': status, 'fullA29Matrix': status == 'VERIFIED', 'executedCount': len(results),
            'passedCount': passed}


def fingerprint_inputs():
    files = [Path(__file__).resolve(), REGISTRY, ROOT / 'scripts/legacy_artifact_inputs.py',
             ROOT / 'scripts/public_split_artifacts.py', ROOT / 'scripts/verify-gradle-legacy-artifact-consumer.py',
             ROOT / 'scripts/verify-gradle-split-artifact-consumer.py', ROOT / 'scripts/verify-staged-split-artifact-consumer.py',
             ROOT / 'scripts/tests/test_verify_current_entry_successor.py',
             ROOT / 'docs/current-entry-migration-acceptance.md',
             ROOT / 'gradle/verification-metadata.xml', ROOT / 'gradlew',
             *[ROOT / value for value in PRESERVED],
             *sorted((ROOT / 'gradle/wrapper').rglob('*')), *sorted(FIXTURE.rglob('*')),
             *sorted((ROOT / 'examples/legacy-runtime-collision-consumer').rglob('*')),
             *sorted((ROOT / 'examples/current-entry-regression-consumer').rglob('*')),
             BASE_FIXTURE / 'build.gradle', BASE_FIXTURE / 'settings.gradle',
             *sorted((BASE_FIXTURE / 'gradle-locks').rglob('*'))]
    result = {}
    for path in files:
        if path.is_symlink():
            raise RuntimeAcceptanceError('Harness inputs must not be symlinks')
        if path.is_file():
            result[str(path.relative_to(ROOT))] = digest(path.read_bytes())
        elif path in [ROOT / value for value in PRESERVED]:
            raise RuntimeAcceptanceError('Preserved original evidence is missing')
    return result


def assert_unchanged_inputs(initial, receipt_path, receipt_sha256):
    if fingerprint_inputs() != initial or digest(receipt_path.read_bytes()) != receipt_sha256:
        raise RuntimeAcceptanceError('Harness inputs or reviewed receipt changed')


def verify_current_names(inventory, repository):
    for pin in inventory:
        if not pin['name'].endswith('.jar') or pin['name'].endswith(('-sources.jar', '-javadoc.jar')):
            continue
        if pin['origin'] == 'public-legacy' or pin['module'] == 'routecontract-core':
            with zipfile.ZipFile(repository / pin['relativePath']) as jar:
                names = set(jar.namelist())
            if pin['origin'] == 'public-legacy' and any(name in names for name in CURRENT_CLASSES):
                raise RuntimeAcceptanceError('New API or guard name is present in a legacy input')
            if pin['module'] == 'routecontract-core' and not all(name in names for name in CURRENT_CLASSES):
                raise RuntimeAcceptanceError('Reviewed core does not contain the successor API and guard')


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
    command.append('prepareCurrentEntryRuntimeClasspath')
    write_json(lane / 'command.json', {'argv': command, 'JAVA_HOME': str(java_home),
               'GRADLE_USER_HOME': str(cache), 'dependencyCacheInitiallyAbsent': True})
    with (lane / 'gradle.log').open('w') as log:
        completed = subprocess.run(command, cwd=consumer, env=split.clean_environment(java_home, cache),
                                   stdout=log, stderr=subprocess.STDOUT, timeout=1200, check=False)
    if completed.returncode:
        raise RuntimeAcceptanceError(f'Runtime {runtime} compilation/resolution failed; inspect {lane / "gradle.log"}')
    graph = json.loads((consumer / 'build/current-entry-runtime-classpath.json').read_text())
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
    print(f'A29_PREPARED_RUNTIME {runtime}', flush=True)
    return graph


def assemble_classpath(case, graph, inventory, repository):
    core = next(item['path'] for item in graph['artifacts'] if item['group'] == GROUP and item['module'] == 'routecontract-core')
    paths = [core]
    if case['adapter']:
        module = ADAPTERS[case['adapter']]
        if case['adapter'] == case['runtime']:
            paths.append(next(item['path'] for item in graph['artifacts'] if item['group'] == GROUP and item['module'] == module))
        else:
            pin = next(item for item in inventory if item['origin'] == 'staged' and item['module'] == module
                       and item['name'].endswith('.jar'))
            paths.append(str(repository / pin['relativePath']))
    if case['legacy']:
        pin = next(item for item in inventory if item['origin'] == 'public-legacy'
                   and item['version'] == case['legacy'] and item['name'].endswith('.jar'))
        legacy = str(repository / pin['relativePath'])
        paths = [legacy, *paths] if case['order'] == 'legacy-first' else [*paths, legacy]
    return [*paths, *graph['classes'], *[item['path'] for item in graph['artifacts'] if item['group'] != GROUP]]


def expected_origins(case, graph, inventory, repository):
    core = next(item['path'] for item in graph['artifacts'] if item['group'] == GROUP and item['module'] == 'routecontract-core')
    shadowed = core
    if case['legacy'] and case['order'] == 'legacy-first':
        pin = next(item for item in inventory if item['origin'] == 'public-legacy'
                   and item['version'] == case['legacy'] and item['name'].endswith('.jar'))
        shadowed = str(repository / pin['relativePath'])
    return {'newEntryOrigin': core, 'guardOrigin': core,
            'compatibilityEntryOrigin': shadowed, 'captureRegistryOrigin': shadowed}


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


def verified_launch_inputs(paths, graph, inventory, repository):
    pins = {item['path']: item['sha256'] for item in graph['artifacts']}
    pins.update({str(repository / item['relativePath']): item['sha256'] for item in inventory})
    if len(paths) != len(set(paths)):
        raise RuntimeAcceptanceError('Duplicate launch path')
    result = []
    for value in paths:
        path = Path(value)
        if value in graph['classes']:
            continue
        if path.is_symlink() or not path.is_file() or value not in pins:
            raise RuntimeAcceptanceError('Unexpected launch artifact')
        actual = digest(path.read_bytes())
        if actual != pins[value]:
            raise RuntimeAcceptanceError('Launch artifact differs from its resolved/reviewed pin')
        result.append({'path': value, 'sha256': actual})
    classes = class_hashes(graph['classes'])
    if classes != graph['compiledClasses']:
        raise RuntimeAcceptanceError('Compiled consumer bytes changed')
    return {'artifacts': result, 'compiledClasses': classes}


def run_case(case, evidence, graph, inventory, repository, java_home, environment, port):
    destination = evidence / 'cases' / case['id']
    destination.mkdir(parents=True)
    paths = assemble_classpath(case, graph, inventory, repository)
    origins = expected_origins(case, graph, inventory, repository)
    result_path = destination / 'observed.json'
    command = [str(java_home / 'bin/java'), '-Dorg.slf4j.simpleLogger.defaultLogLevel=warn',
               '-cp', os.pathsep.join(paths), PROBE, case['mode'], str(result_path),
               str(port if case['mode'] in ('sql', 'startup-sql') else 0)]
    inputs = verified_launch_inputs(paths, graph, inventory, repository)
    write_json(destination / 'command.json', {'argv': command, 'freshJvm': True, 'case': case,
               'expectedOrigins': origins, **inputs})
    started = time.monotonic()
    exit_code = None
    timed_out = False
    with (destination / 'jvm.log').open('w') as log:
        try:
            process = subprocess.run(command, cwd=destination, env=environment, stdout=log,
                                     stderr=subprocess.STDOUT, timeout=180, check=False)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    result = {'case': case, 'outcome': 'PROCESS_TIMEOUT' if timed_out else 'PROCESS_FAILED', 'exitCode': exit_code,
              'elapsedSeconds': round(time.monotonic() - started, 3),
              'commandSha256': digest((destination / 'command.json').read_bytes()),
              'logSha256': digest((destination / 'jvm.log').read_bytes())}
    if not timed_out and exit_code == 0 and result_path.is_file() and not result_path.is_symlink():
        try:
            observed = json.loads(result_path.read_text())
            result['observed'] = observed
            result['observedSha256'] = digest(result_path.read_bytes())
            result['outcome'] = classify(case, observed, origins)
        except (ValueError, TypeError):
            result['outcome'] = 'MALFORMED_OBSERVATION'
    try:
        if verified_launch_inputs(paths, graph, inventory, repository) != inputs:
            raise RuntimeAcceptanceError('Launch bytes changed during execution')
        result['launchInputsUnchanged'] = True
    except RuntimeAcceptanceError as error:
        result['outcome'] = 'INPUT_CHANGED'
        result['inputError'] = str(error)
        result['launchInputsUnchanged'] = False
    write_json(destination / 'result.json', result)
    print(f'A29_CASE {case["id"]} {result["outcome"]}', flush=True)
    return result


def write_junit(evidence, results):
    suite = ET.Element('testsuite', name='A29FreshJvmAssertions', tests=str(len(results)),
                       failures=str(sum(result['outcome'] != 'PASS' for result in results)), errors='0', skipped='0')
    for result in results:
        cell = ET.SubElement(suite, 'testcase', classname='A29FreshJvmAssertions', name=result['case']['id'],
                             time=str(result['elapsedSeconds']))
        if result['outcome'] != 'PASS':
            ET.SubElement(cell, 'failure', message=result['outcome']).text = json.dumps(result.get('observed', {}), sort_keys=True)
    ET.indent(suite)
    ET.ElementTree(suite).write(evidence / 'TEST-a29-subprocess-assertions.xml', encoding='utf-8', xml_declaration=True)


def start_mysql(evidence):
    container = subprocess.check_output(['docker', 'run', '--rm', '-d', '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes',
                 '-e', 'MYSQL_DATABASE=routecontract_a29', '-p', '127.0.0.1::3306', MYSQL_IMAGE], text=True, timeout=180).strip()
    write_json(evidence / 'mysql-container.json', {'image': MYSQL_IMAGE, 'containerId': container})
    try:
        for _ in range(120):
            ready = subprocess.run(['docker', 'exec', container, 'mysqladmin', 'ping', '-h', '127.0.0.1', '-uroot'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
            if ready.returncode == 0:
                port = int(subprocess.check_output(['docker', 'port', container, '3306/tcp'], text=True, timeout=10).strip().split(':')[-1])
                return container, port
            time.sleep(1)
        raise RuntimeAcceptanceError('Pinned disposable MySQL did not become ready')
    except BaseException:
        subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, timeout=30, check=False)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--staged-receipt', required=True, type=Path)
    parser.add_argument('--expected-staged-receipt-sha256', required=True, help='Independently reviewed new nine-payload receipt digest')
    parser.add_argument('--staged-source-revision', required=True)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--gradle-distribution-zip', required=True, type=Path)
    parser.add_argument('--legacy-payload-directory', type=Path)
    parser.add_argument('--case', action='append', dest='case_ids', help='Diagnostic subset; exits 2 if otherwise successful, never full A-29')
    parser.add_argument('--prepare-only', action='store_true', help='Verify inputs and compile both exact lanes; no probe JVMs or MySQL')
    args = parser.parse_args()
    evidence = args.evidence_directory.expanduser().resolve()
    repository_source = args.repository.expanduser().resolve()
    if (evidence.exists() or evidence == ROOT or ROOT in evidence.parents
            or repository_source in evidence.parents):
        raise RuntimeAcceptanceError('Evidence directory must be absent and outside the checkout and staged repository')
    evidence.mkdir(parents=True, mode=0o700)
    container = None
    results = []
    try:
        initial = fingerprint_inputs()
        registry = load_registry(REGISTRY)
        receipt_bytes = args.staged_receipt.read_bytes()
        if digest(receipt_bytes) != args.expected_staged_receipt_sha256:
            raise RuntimeAcceptanceError('Staged receipt differs from independently reviewed digest')
        receipt = load_consumer_receipt(args.staged_receipt)
        if receipt['routeContractVersion'] != '0.2.0':
            raise RuntimeAcceptanceError('A-29 requires the reviewed coordinated 0.2.0 candidate')
        original = json.loads((ROOT / 'docs/evidence/legacy-runtime-collision-2026-09-08.json').read_text())
        if original.get('status') != 'FAILED':
            raise RuntimeAcceptanceError('Original A-28 failure must remain explicit and preserved')
        legacy_helper = load_helper('a29_legacy_helper', 'verify-gradle-legacy-artifact-consumer.py')
        staged = load_helper('a29_staged_helper', 'verify-staged-split-artifact-consumer.py')
        split = load_helper('a29_split_helper', 'verify-gradle-split-artifact-consumer.py')
        staged.verify_receipt(repository_source, receipt)
        binding = legacy_helper.source_binding(args.staged_source_revision)
        write_json(evidence / 'source-binding.json', binding)
        write_json(evidence / 'fixture-inputs.json', initial)
        shutil.copyfile(REGISTRY, evidence / 'legacy-artifact-inputs.json')
        (evidence / 'staged-receipt.json').write_bytes(receipt_bytes)
        repository = evidence / 'repository'
        inventory = legacy_helper.prepare_repository(repository_source, receipt, registry, repository,
                    args.legacy_payload_directory.resolve() if args.legacy_payload_directory else None)
        verify_current_names(inventory, repository)
        write_json(evidence / 'verified-input-inventory.json', inventory)
        required = cases(registry)
        selected = required
        if args.case_ids:
            if len(args.case_ids) != len(set(args.case_ids)) or set(args.case_ids) - {case['id'] for case in required}:
                raise RuntimeAcceptanceError('Unknown or duplicate diagnostic case ID')
            selected = [case for case in required if case['id'] in args.case_ids]
        write_json(evidence / 'case-plan.json', {'requiredCount': 64, 'captureCollisions': 32, 'sqlCollisions': 16,
                   'cleanControls': 12, 'startupRejections': 4, 'required': required, 'selected': selected})
        java_home = args.java_home.resolve()
        split.verify_toolchain(ROOT, java_home)
        seed = evidence / 'wrapper-seed'
        seed.mkdir()
        legacy_helper.seed_distribution_zip(args.gradle_distribution_zip.resolve(), seed)
        split.prepare_wrapper_seed(ROOT, ROOT / 'gradlew', java_home, seed)
        version = subprocess.check_output([str(ROOT / 'gradlew'), '--no-daemon', '--version'], cwd=ROOT,
                    env=split.clean_environment(java_home, seed), text=True, stderr=subprocess.STDOUT, timeout=60)
        (evidence / 'toolchain.txt').write_text(version)
        runtimes = list(ADAPTERS) if args.prepare_only else sorted({case['runtime'] for case in selected})
        with ThreadPoolExecutor(max_workers=2) as pool:
            graphs = dict(zip(runtimes, pool.map(lambda runtime: prepare_lane(runtime, evidence, repository,
                          receipt, seed, java_home, staged, split), runtimes)))
        # Record even preparation-only launch plans, including manual negative-graph mutations.
        prepared_launches = []
        for case in selected:
            graph = graphs[case['runtime']]
            paths = assemble_classpath(case, graph, inventory, repository)
            prepared_launches.append({'case': case, 'classpath': paths,
                'expectedOrigins': expected_origins(case, graph, inventory, repository),
                **verified_launch_inputs(paths, graph, inventory, repository)})
        write_json(evidence / 'prepared-launch-inputs.json', prepared_launches)
        if not args.prepare_only:
            container, port = start_mysql(evidence) if any(case['mode'] in ('sql', 'startup-sql') for case in selected) else (None, 0)
            environment = split.clean_environment(java_home, seed)
            for case in selected:
                assert_unchanged_inputs(initial, args.staged_receipt, args.expected_staged_receipt_sha256)
                results.append(run_case(case, evidence, graphs[case['runtime']], inventory, repository,
                                        java_home, environment, port))
                write_json(evidence / 'progress.json', results)
                write_junit(evidence, results)
        assert_unchanged_inputs(initial, args.staged_receipt, args.expected_staged_receipt_sha256)
        if legacy_helper.source_binding(args.staged_source_revision) != binding:
            raise RuntimeAcceptanceError('Production/source binding changed during execution')
        staged.verify_receipt(repository_source, receipt)
        for pin in inventory:
            if digest((repository / pin['relativePath']).read_bytes()) != pin['sha256']:
                raise RuntimeAcceptanceError('Verified repository input changed during execution')
        completion = (dict(status='PREPARED', fullA29Matrix=False, executedCount=0, passedCount=0) if args.prepare_only
                      else completion_status(required, results, partial=bool(args.case_ids)))
        summary = {'formatVersion': 1, 'gate': 'A29', **completion, 'requiredCount': 64,
                   'captureCollisionCount': 32, 'sqlCollisionCount': 16, 'cleanControlCount': 12,
                   'startupRejectionCount': 4, 'originalA28Status': 'FAILED', 'sourceBinding': binding,
                   'registrySha256': initial['scripts/legacy-artifact-inputs.json'],
                   'stagedReceiptSha256': args.expected_staged_receipt_sha256,
                   'fixtureInputsSha256': digest((evidence / 'fixture-inputs.json').read_bytes()),
                   'inventorySha256': digest((evidence / 'verified-input-inventory.json').read_bytes()),
                   'resolvedClasspathSha256': {runtime: digest((evidence / 'lanes' / runtime / 'resolved-classpath.json').read_bytes())
                                               for runtime in runtimes}, 'results': results,
                   'junitBoundary': 'Python-generated assertions over actual fresh JVM observations, not product JUnit',
                   'boundary': 'Reviewed local coordinated 0.2 staging plus registry-bound actual public legacy JARs. '
                               'Separate A-29 changed-entry contract; original A-28 remains FAILED and A-26 is separate. '
                               'Driver evidence covers the fixed business PreparedStatement, excluding setup and metadata SQL. '
                               'No public 0.2 availability, transaction commit, or production adoption claim.'}
        write_json(evidence / 'summary.json', summary)
        print(f'A29_{summary["status"]} passed={summary["passedCount"]}/{len(results)} evidence={evidence}', flush=True)
        return 0 if summary['status'] in ('VERIFIED', 'PREPARED') else 2 if summary['status'] == 'INCOMPLETE' else 1
    except Exception as error:
        write_json(evidence / 'failure.json', {'status': 'FAILED', 'gate': 'A29', 'fullA29Matrix': False,
                   'originalA28Status': 'FAILED', 'error': str(error), 'completedCases': len(results)})
        raise
    finally:
        if container:
            try:
                with (evidence / 'mysql.log').open('w') as log:
                    subprocess.run(['docker', 'logs', container], stdout=log, stderr=subprocess.STDOUT, timeout=30, check=False)
            finally:
                subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, timeout=30, check=False)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'A29_FAILED: {error}', file=sys.stderr)
        sys.exit(1)
