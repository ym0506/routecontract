#!/usr/bin/env python3
"""Execute ADR A-28 against real pinned public legacy and reviewed local split JARs."""
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from legacy_artifact_inputs import ARTIFACT, GROUP, digest, load_registry
from public_split_artifacts import load_consumer_receipt

FIXTURE = ROOT / 'examples/legacy-runtime-collision-consumer'
BASE_FIXTURE = ROOT / 'examples/staged-split-artifact-consumer'
REGISTRY = ROOT / 'scripts/legacy-artifact-inputs.json'
MYSQL_IMAGE = 'mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb'
ADAPTERS = {'5.5.2': 'routecontract-shardingsphere-5.5.2', '5.5.3': ARTIFACT}
PROBE = 'io.github.ym0506.routecontract.consumer.LegacyRuntimeProbe'


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
    result = []
    for runtime in ADAPTERS:
        for mode in ('capture', 'sql'):
            result.append({'id': f'{runtime}-clean-{mode}', 'runtime': runtime, 'mode': mode, 'legacy': None,
                           'order': None, 'expected': 'CLEAN_SUCCESS'})
        for legacy in registry['distributed']:
            for order in ('legacy-first', 'legacy-last'):
                for mode in ('capture', 'sql'):
                    result.append({'id': f'{runtime}-{legacy["version"]}-{order}-{mode}', 'runtime': runtime,
                                   'legacy': legacy['version'], 'order': order, 'mode': mode,
                                   'expected': 'RC_LEGACY_ADAPTER_COLLISION'})
    return result


def classify(case, observed):
    if case['expected'] == 'CLEAN_SUCCESS':
        good = observed['returned'] and not observed['exceptionClasses']
        if case['mode'] == 'capture':
            good = (good and observed['actionEntered'] and observed['physicalBusinessExecutions'] == 0
                    and observed.get('captureSnapshot') == {'status': 'INCOMPLETE', 'observedPhysicalAttemptCount': 0,
                        'collectorDiagnostics': ['RC_NO_START_CALLBACK_OBSERVED']})
        else:
            good = (good and not observed['actionEntered'] and observed['physicalBusinessExecutions'] == 1
                    and observed['businessRows'] == ['201:3:PAID'])
        return 'PASS' if good else 'CONTROL_FAILED'
    message = '\n'.join(observed['exceptionMessages'])
    if observed['actionEntered'] or observed['physicalBusinessExecutions'] or observed['businessRows']:
        return 'ACTION_OR_SQL_EXECUTED'
    if observed['returned']:
        return 'SILENT_SUCCESS'
    if observed['linkageFailure']:
        return 'LINKAGE_FAILURE'
    return 'PASS' if 'RC_LEGACY_ADAPTER_COLLISION:' in message else 'WRONG_DIAGNOSTIC'


def fingerprint_inputs():
    files = [Path(__file__).resolve(), REGISTRY, ROOT / 'scripts/legacy_artifact_inputs.py',
             ROOT / 'scripts/public_split_artifacts.py', ROOT / 'scripts/verify-gradle-legacy-artifact-consumer.py',
             ROOT / 'scripts/verify-gradle-split-artifact-consumer.py',
             ROOT / 'scripts/verify-staged-split-artifact-consumer.py', ROOT / 'gradle/verification-metadata.xml',
             ROOT / 'gradlew', *sorted((ROOT / 'gradle/wrapper').rglob('*')),
             *sorted(FIXTURE.rglob('*')), BASE_FIXTURE / 'build.gradle', BASE_FIXTURE / 'settings.gradle',
             *sorted((BASE_FIXTURE / 'gradle-locks').rglob('*'))]
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in files if path.is_file()}


def prepare_lane(runtime, evidence, repository, receipt, seed, java_home, staged, split):
    lane = evidence / 'lanes' / runtime
    lane.mkdir(parents=True)
    consumer = lane / 'consumer'
    # The existing locked dependency graph is copied; no product source or includeBuild.
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
    command.append('prepareLegacyRuntimeClasspath')
    write_json(lane / 'command.json', {'argv': command, 'JAVA_HOME': str(java_home),
               'GRADLE_USER_HOME': str(cache), 'dependencyCacheInitiallyAbsent': True})
    with (lane / 'gradle.log').open('w') as log:
        completed = subprocess.run(command, cwd=consumer, env=split.clean_environment(java_home, cache),
                                   stdout=log, stderr=subprocess.STDOUT, timeout=1200, check=False)
    if completed.returncode:
        raise RuntimeAcceptanceError(f'Runtime {runtime} compilation/resolution failed; inspect {lane / "gradle.log"}')
    graph = json.loads((consumer / 'build/legacy-runtime-classpath.json').read_text())
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
    graph['compiledClasses'] = class_hashes(graph['classes'])
    write_json(lane / 'resolved-classpath.json', graph)
    return graph


def assemble_classpath(case, graph, inventory, repository):
    selected = graph['artifacts']
    current = sorted((item for item in selected if item['group'] == GROUP), key=lambda item: item['module'])
    third_party = [item for item in selected if item['group'] != GROUP]
    paths = [item['path'] for item in current]
    if case['legacy']:
        pin = next(item for item in inventory if item['origin'] == 'public-legacy'
                   and item['version'] == case['legacy'] and item['name'].endswith('.jar'))
        legacy = str(repository / pin['relativePath'])
        paths = [legacy, *paths] if case['order'] == 'legacy-first' else [*paths, legacy]
    # No class with a RouteContract production FQCN is compiled into the fixture directory.
    return [*paths, *graph['classes'], *[item['path'] for item in third_party]]


def class_hashes(directories):
    result = {}
    for directory in directories:
        root = Path(directory)
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
    result_path = destination / 'observed.json'
    command = [str(java_home / 'bin/java'), '-Dorg.slf4j.simpleLogger.defaultLogLevel=warn',
               '-cp', os.pathsep.join(paths), PROBE, case['mode'], str(result_path),
               str(port if case['mode'] == 'sql' else 0)]
    inputs = verified_launch_inputs(paths, graph, inventory, repository)
    write_json(destination / 'command.json', {'argv': command, 'freshJvm': True, 'case': case, **inputs})
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
              'logSha256': digest((destination / 'jvm.log').read_bytes())}
    if not timed_out and exit_code == 0 and result_path.is_file():
        observed = json.loads(result_path.read_text())
        result['observed'] = observed
        result['observedSha256'] = digest(result_path.read_bytes())
        result['outcome'] = classify(case, observed)
        # Bind selected API and collector to the actual first JAR, never a test guard.
        if observed['routeContractOrigin'] != paths[0] or observed['captureRegistryOrigin'] != paths[0]:
            result['outcome'] = 'UNEXPECTED_CLASS_ORIGIN'
    write_json(destination / 'result.json', result)
    try:
        if verified_launch_inputs(paths, graph, inventory, repository) != inputs:
            raise RuntimeAcceptanceError('Launch bytes changed during execution')
    except RuntimeAcceptanceError as error:
        result['outcome'] = 'INPUT_CHANGED'
        result['inputError'] = str(error)
        write_json(destination / 'result.json', result)
    print(f'A28_CASE {case["id"]} {result["outcome"]}', flush=True)
    return result


def write_junit(evidence, results):
    failures = sum(result['outcome'] != 'PASS' for result in results)
    suite = ET.Element('testsuite', name='A28FreshJvmAssertions', tests=str(len(results)), failures=str(failures),
                       errors='0', skipped='0')
    for result in results:
        case = ET.SubElement(suite, 'testcase', classname='A28FreshJvmAssertions', name=result['case']['id'],
                             time=str(result['elapsedSeconds']))
        if result['outcome'] != 'PASS':
            ET.SubElement(case, 'failure', message=result['outcome']).text = json.dumps(result.get('observed', {}), sort_keys=True)
    ET.indent(suite)
    ET.ElementTree(suite).write(evidence / 'TEST-a28-subprocess-assertions.xml', encoding='utf-8', xml_declaration=True)


def start_mysql(evidence):
    # Fixed local disposable fixture credentials; no release secrets or user DB.
    container = subprocess.check_output(['docker', 'run', '--rm', '-d', '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes',
                 '-e', 'MYSQL_DATABASE=routecontract_a28', '-p', '127.0.0.1::3306', MYSQL_IMAGE], text=True).strip()
    write_json(evidence / 'mysql-container.json', {'image': MYSQL_IMAGE, 'containerId': container})
    try:
        for _ in range(120):
            ready = subprocess.run(['docker', 'exec', container, 'mysqladmin', 'ping', '-h', '127.0.0.1', '-uroot'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if ready.returncode == 0:
                port = int(subprocess.check_output(['docker', 'port', container, '3306/tcp'], text=True).strip().split(':')[-1])
                return container, port
            time.sleep(1)
        raise RuntimeAcceptanceError('Pinned disposable MySQL did not become ready')
    except BaseException:
        subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, check=False)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--staged-receipt', required=True, type=Path)
    parser.add_argument('--staged-source-revision', required=True)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--gradle-distribution-zip', required=True, type=Path)
    parser.add_argument('--legacy-payload-directory', type=Path)
    parser.add_argument('--case', action='append', dest='case_ids', help='Diagnostic subset; never full A-28 evidence')
    args = parser.parse_args()
    evidence = args.evidence_directory.expanduser().resolve()
    if evidence.exists() or evidence == ROOT or ROOT in evidence.parents:
        raise RuntimeAcceptanceError('Evidence directory must be absent and outside the checkout')
    evidence.mkdir(parents=True, mode=0o700)
    container = None
    results = []
    try:
        initial = fingerprint_inputs()
        registry = load_registry(REGISTRY)
        receipt_bytes = args.staged_receipt.read_bytes()
        receipt = load_consumer_receipt(args.staged_receipt)
        if receipt['routeContractVersion'] != '0.2.0':
            raise RuntimeAcceptanceError('A-28 fixture currently requires reviewed candidate 0.2.0')
        legacy_helper = load_helper('a28_legacy_helper', 'verify-gradle-legacy-artifact-consumer.py')
        staged = load_helper('a28_staged_helper', 'verify-staged-split-artifact-consumer.py')
        split = load_helper('a28_split_helper', 'verify-gradle-split-artifact-consumer.py')
        binding = legacy_helper.source_binding(args.staged_source_revision)
        write_json(evidence / 'source-binding.json', binding)
        write_json(evidence / 'fixture-inputs.json', initial)
        shutil.copyfile(REGISTRY, evidence / 'legacy-artifact-inputs.json')
        (evidence / 'staged-receipt.json').write_bytes(receipt_bytes)
        repository = evidence / 'repository'
        inventory = legacy_helper.prepare_repository(args.repository.resolve(), receipt, registry, repository,
                    args.legacy_payload_directory.resolve() if args.legacy_payload_directory else None)
        write_json(evidence / 'verified-input-inventory.json', inventory)
        selected = cases(registry)
        if args.case_ids:
            if set(args.case_ids) - {case['id'] for case in selected}:
                raise RuntimeAcceptanceError('Unknown diagnostic case ID')
            selected = [case for case in selected if case['id'] in args.case_ids]
        write_json(evidence / 'case-plan.json', {'requiredCollisionCases': 32, 'requiredControls': 4, 'selected': selected})
        java_home = args.java_home.resolve()
        split.verify_toolchain(ROOT, java_home)
        seed = evidence / 'wrapper-seed'
        seed.mkdir()
        legacy_helper.seed_distribution_zip(args.gradle_distribution_zip.resolve(), seed)
        split.prepare_wrapper_seed(ROOT, ROOT / 'gradlew', java_home, seed)
        version = subprocess.check_output([str(ROOT / 'gradlew'), '--no-daemon', '--version'], cwd=ROOT,
                    env=split.clean_environment(java_home, seed), text=True, stderr=subprocess.STDOUT, timeout=60)
        (evidence / 'toolchain.txt').write_text(version)
        runtimes = sorted({case['runtime'] for case in selected})
        with ThreadPoolExecutor(max_workers=2) as pool:
            graphs = dict(zip(runtimes, pool.map(lambda runtime: prepare_lane(runtime, evidence, repository,
                          receipt, seed, java_home, staged, split), runtimes)))
        if any(case['mode'] == 'sql' for case in selected):
            container, port = start_mysql(evidence)
        else:
            port = 0
        environment = split.clean_environment(java_home, seed)
        for case in selected:
            results.append(run_case(case, evidence, graphs[case['runtime']], inventory, repository,
                                    java_home, environment, port))
            write_json(evidence / 'progress.json', results)
            write_junit(evidence, results)
        if fingerprint_inputs() != initial or args.staged_receipt.read_bytes() != receipt_bytes:
            raise RuntimeAcceptanceError('Fixture or reviewed receipt changed during execution')
        if legacy_helper.source_binding(args.staged_source_revision) != binding:
            raise RuntimeAcceptanceError('Production/source binding changed during execution')
        for pin in inventory:
            if digest((repository / pin['relativePath']).read_bytes()) != pin['sha256']:
                raise RuntimeAcceptanceError('First-party input changed during execution')
        passed = all(result['outcome'] == 'PASS' for result in results)
        status = ('VERIFIED' if not args.case_ids else 'PARTIAL_VERIFIED') if passed else 'FAILED'
        summary = {'formatVersion': 1, 'status': status, 'fullA28Matrix': status == 'VERIFIED',
                   'executedCount': len(results), 'passedCount': sum(r['outcome'] == 'PASS' for r in results),
                   'requiredCollisionCases': 32, 'requiredControls': 4, 'sourceBinding': binding,
                   'registrySha256': initial['scripts/legacy-artifact-inputs.json'],
                   'stagedReceiptSha256': digest(receipt_bytes), 'results': results,
                   'junitBoundary': 'Python-generated assertions over actual fresh JVM observations, not product JUnit',
                   'boundary': 'Reviewed local staged 0.2 bytes plus pinned real public legacy JARs; exact Java 17 and pinned MySQL. '
                               'No public 0.2 availability or production adoption claim.'}
        write_json(evidence / 'summary.json', summary)
        print(f'A28_{status} passed={summary["passedCount"]}/{len(results)} evidence={evidence}', flush=True)
        return 0 if passed else 1
    except Exception as error:
        write_json(evidence / 'failure.json', {'status': 'FAILED', 'fullA28Matrix': False, 'error': str(error),
                   'completedCases': len(results)})
        raise
    finally:
        if container:
            with (evidence / 'mysql.log').open('w') as log:
                subprocess.run(['docker', 'logs', container], stdout=log, stderr=subprocess.STDOUT, check=False)
            subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, check=False)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'A28_FAILED: {error}', file=sys.stderr)
        sys.exit(1)
