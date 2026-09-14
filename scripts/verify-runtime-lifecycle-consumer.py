#!/usr/bin/env python3
"""Run only existing ADR A-11/A-12/A-13 against externally pinned local staged bytes."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from legacy_artifact_inputs import GROUP, digest
from public_split_artifacts import load_consumer_receipt

FIXTURE = ROOT / 'examples/runtime-lifecycle-consumer'
BASE_FIXTURE = ROOT / 'examples/staged-split-artifact-consumer'
ADAPTERS = {'5.5.2': 'routecontract-shardingsphere-5.5.2',
            '5.5.3': 'routecontract-shardingsphere-5.5'}
PROBE = 'io.github.ym0506.routecontract.lifecycle.RuntimeLifecycleProbe'
COMMON_CHECKS = ('tcclRestored', 'firstPartyOriginsPinned', 'actualShardingSphereDiscoveryUsed')
CASE_CHECKS = {
    'A11': ('firstTcclHidesAdapter', 'exposedTcclSeesAdapter',
            'firstDiscoveryHasNoRouteContractProvider', 'laterDiscoveryHasNoRouteContractProvider'),
    'A12': ('firstBothLoadersSeeAdapter', 'laterTcclHidesAdapter', 'laterCoreLoaderSeesAdapter',
            'cachedProviderClassUnchanged', 'physicalDriverDelegatedToMysql', 'noCallbackFailure'),
    'A13': ('bridgeLoaderDistinct', 'bridgeOriginMatchesCore', 'otherAnchorsShareApplicationLoader',
            'discoveryRejectedWithStableDiagnostic', 'discoveryTraceShowsRealHookConstructor',
            'captureRejectedWithStableDiagnostic'),
}


class LifecycleError(RuntimeError):
    pass


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def load_helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def case_plan():
    return [{'caseId': f'{row}-{runtime.replace(".", "")}', 'row': row, 'runtime': runtime,
             'expected': {'A11': 'RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE', 'A12': 'CAPTURED',
                          'A13': 'RC_ADAPTER_CLASSLOADER_MISMATCH'}[row]}
            for runtime in ADAPTERS for row in CASE_CHECKS]


def pinned_receipt(path, expected_sha256):
    if re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is None:
        raise LifecycleError('An external lowercase SHA-256 pin is required for the reviewed receipt')
    receipt = load_consumer_receipt(path)
    payload = path.read_bytes()
    if digest(payload) != expected_sha256:
        raise LifecycleError('Reviewed receipt differs from the external SHA-256 pin')
    if receipt['routeContractVersion'] != '0.2.0':
        raise LifecycleError('This finite fixture requires coordinated 0.2.0 staged artifacts')
    return receipt, payload


def fingerprint_inputs():
    files = [Path(__file__).resolve(), ROOT / 'scripts/tests/test_verify_runtime_lifecycle_consumer.py',
             ROOT / 'docs/runtime-lifecycle-acceptance.md', ROOT / 'scripts/legacy_artifact_inputs.py',
             ROOT / 'scripts/public_split_artifacts.py', ROOT / 'scripts/verify-gradle-legacy-artifact-consumer.py',
             ROOT / 'scripts/verify-staged-split-artifact-consumer.py',
             ROOT / 'scripts/verify-gradle-split-artifact-consumer.py', ROOT / 'gradle/verification-metadata.xml',
             ROOT / 'gradlew', *sorted((ROOT / 'gradle/wrapper').rglob('*')),
             *sorted(FIXTURE.rglob('*')), BASE_FIXTURE / 'build.gradle', BASE_FIXTURE / 'settings.gradle',
             *sorted((BASE_FIXTURE / 'gradle-locks').rglob('*'))]
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in files if path.is_file()}


def class_hashes(directories):
    result = {}
    for directory in directories:
        root = Path(directory)
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                raise LifecycleError('Compiled fixture classes must not be symlinks')
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                if not relative.startswith('io/github/ym0506/routecontract/lifecycle/') or not relative.endswith('.class'):
                    raise LifecycleError('A production or non-fixture class appeared in the launcher output')
                result[str(path)] = digest(path.read_bytes())
    if not result:
        raise LifecycleError('No compiled lifecycle fixture classes')
    return result


def verify_graph(graph, runtime, receipt):
    expected = {'routecontract-core', ADAPTERS[runtime]}
    pins = {pin['module']: pin['sha256'] for pin in receipt['artifacts'] if pin['name'].endswith('.jar')}
    if graph.get('runtime') != runtime:
        raise LifecycleError('Resolved graph has the wrong exact runtime')
    for field in ('compileArtifacts', 'artifacts'):
        artifacts = graph[field]
        ours = [item for item in artifacts if item['group'] == GROUP]
        if len(ours) != 2 or {item['module'] for item in ours} != expected:
            raise LifecycleError('Unexpected first-party compile/runtime classpath')
        if any(item['version'] != '0.2.0' or item['sha256'] != pins[item['module']] for item in ours):
            raise LifecycleError('Resolved first-party bytes differ from the reviewed receipt')
        sharding = [item for item in artifacts if item['group'] == 'org.apache.shardingsphere']
        if not sharding or any(item['version'] != runtime for item in sharding):
            raise LifecycleError('Compile/runtime ShardingSphere graph is not exact')
        for item in artifacts:
            path = Path(item['path'])
            if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != item['sha256']:
                raise LifecycleError('Resolved JAR bytes changed or are missing')


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
        raise LifecycleError('Dependency cache was not initially absent')
    command = [str(consumer / 'gradlew'), '--no-daemon', '--no-build-cache', '--no-configuration-cache',
               '--dependency-verification=strict', '--console=plain', '--max-workers=2',
               f'-ProutecontractRuntime={runtime}', f'-ProutecontractRepository={repository}']
    for module in ('routecontract-core', ADAPTERS[runtime]):
        pin = next(p for p in receipt['artifacts'] if p['module'] == module and p['name'].endswith('.jar'))
        command.append(f'-ProutecontractSha256.{module}={pin["sha256"]}')
    command.append('prepareRuntimeLifecycleClasspath')
    write_json(lane / 'command.json', {'argv': command, 'JAVA_HOME': str(java_home),
               'GRADLE_USER_HOME': str(cache), 'dependencyCacheInitiallyAbsent': True})
    with (lane / 'gradle.log').open('w') as log:
        completed = subprocess.run(command, cwd=consumer, env=split.clean_environment(java_home, cache),
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   timeout=1200, check=False)
    if completed.returncode:
        raise LifecycleError(f'Exact {runtime} graph/fixture compilation failed; inspect {lane / "gradle.log"}')
    graph = json.loads((consumer / 'build/runtime-lifecycle-classpath.json').read_text())
    verify_graph(graph, runtime, receipt)
    graph['compiledClasses'] = class_hashes(graph['classes'])
    write_json(lane / 'resolved-classpath.json', graph)
    return graph


def classify(case, observed):
    if (type(observed.get('formatVersion')) is not int or observed.get('formatVersion') != 1
            or observed.get('caseId') != case['caseId']
            or observed.get('runtime') != case['runtime']):
        return 'WRONG_CASE_IDENTITY'
    if observed.get('exposedRawLinkageError') is not False:
        return 'RAW_LINKAGE_OR_MISSING_EVIDENCE'
    checks = observed.get('semanticChecks', {})
    if not isinstance(checks, dict) or any(checks.get(key) is not True
                                         for key in (*COMMON_CHECKS, *CASE_CHECKS[case['row']])):
        return 'LOADER_SEMANTICS_NOT_PROVEN'
    phases = observed.get('loaderPhases')
    if not isinstance(phases, list) or len(phases) < 2 or not all(isinstance(p, dict) and p for p in phases):
        return 'MISSING_RAW_LOADER_EVIDENCE'
    if case['row'] == 'A12':
        expected = {'outcome': 'CAPTURED', 'diagnosticCode': None, 'actionCount': 1,
                    'driverExecutionCount': 1, 'returnedSnapshot': True, 'captureStatus': 'COMPLETE',
                    'observedPhysicalAttemptCount': 1, 'exactBusinessRowsMatched': True,
                    'topLevelThrowableClass': None}
    else:
        expected = {'outcome': 'EXPECTED_REJECTION', 'diagnosticCode': case['expected'],
                    'actionCount': 0, 'driverExecutionCount': 0, 'returnedSnapshot': False,
                    'captureStatus': None, 'observedPhysicalAttemptCount': 0,
                    'topLevelThrowableClass': 'java.lang.IllegalStateException'}
    for key, value in expected.items():
        if key not in observed or type(observed[key]) is not type(value) or observed[key] != value:
            return 'WRONG_BUSINESS_OR_CAPTURE_RESULT'
    return 'PASS'


def uncaught_thread_failures(process_log):
    """Inspect the complete terminated JVM log, including shutdown after the JSON report."""
    return [line for line in process_log.splitlines()
            if re.match(r'^Exception in thread "[^"\r\n]+"', line)]


def evaluate_process(case, exit_code, observed, process_log, timed_out=False):
    if timed_out:
        return 'PROCESS_TIMEOUT'
    if exit_code != 0:
        return 'PROCESS_FAILED'
    if uncaught_thread_failures(process_log):
        return 'UNCAUGHT_JVM_THROWABLE'
    if not isinstance(observed, dict):
        return 'MISSING_OR_MALFORMED_RESULT'
    return classify(case, observed)


def run_case(case, evidence, graph, receipt, java_home, environment):
    destination = evidence / 'cases' / case['caseId']
    destination.mkdir(parents=True)
    verify_graph(graph, case['runtime'], receipt)
    if class_hashes(graph['classes']) != graph['compiledClasses']:
        raise LifecycleError('Compiled probe bytes changed before launch')
    pins = {item['module']: {'path': item['path'], 'sha256': item['sha256']}
            for item in graph['artifacts'] if item['group'] == GROUP}
    pins_path = destination / 'first-party-expected.json'
    write_json(pins_path, pins)
    output_path = destination / 'observed.json'
    classpath = os.pathsep.join([item['path'] for item in graph['artifacts']])
    fixture_classes = os.pathsep.join(graph['classes'])
    command = [str(java_home / 'bin/java'), '-Dapi.version=1.44',
               '-Dorg.slf4j.simpleLogger.defaultLogLevel=warn',
               f'-Droutecontract.resolvedClasspath={classpath}',
               f'-Droutecontract.fixtureClasses={fixture_classes}', '-cp', fixture_classes,
               PROBE, case['caseId'], case['runtime'], str(output_path), str(pins_path)]
    write_json(destination / 'command.json', {'argv': command, 'JAVA_HOME': str(java_home),
               'freshJvm': True, 'launcherContainsOnlyFixtureClasses': True,
               'compiledClasses': graph['compiledClasses'], 'firstPartyExpected': pins})
    started = time.monotonic()
    exit_code = None
    timed_out = False
    with (destination / 'jvm.log').open('w') as log:
        try:
            process = subprocess.run(command, cwd=destination, env=environment, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, timeout=300, check=False)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    observed = None
    read_error = None
    if output_path.is_file():
        try:
            observed = json.loads(output_path.read_text())
        except (OSError, ValueError) as error:
            read_error = str(error)
    process_log = (destination / 'jvm.log').read_text(encoding='utf-8', errors='replace')
    result = {'case': case, 'exitCode': exit_code, 'timedOut': timed_out,
              'elapsedSeconds': round(time.monotonic() - started, 3),
              'outcome': evaluate_process(case, exit_code, observed, process_log, timed_out),
              'uncaughtThreadFailureLines': uncaught_thread_failures(process_log),
              'observed': observed, 'readError': read_error,
              'logSha256': digest((destination / 'jvm.log').read_bytes()),
              'observedSha256': digest(output_path.read_bytes()) if output_path.is_file() else None}
    try:
        verify_graph(graph, case['runtime'], receipt)
        if class_hashes(graph['classes']) != graph['compiledClasses']:
            raise LifecycleError('Compiled probe bytes changed during launch')
        if json.loads(pins_path.read_text()) != pins:
            raise LifecycleError('First-party expected origins changed during launch')
    except Exception as error:
        result.update(outcome='INPUT_CHANGED', inputError=str(error))
    write_json(destination / 'result.json', result)
    print(f'LIFECYCLE_CASE {case["caseId"]} {result["outcome"]}', flush=True)
    return result


def complete_matrix(results):
    required = {item['caseId'] for item in case_plan()}
    return (len(results) == len(required) and {r['case']['caseId'] for r in results} == required
            and all(r['outcome'] == 'PASS' for r in results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--staged-receipt', required=True, type=Path)
    parser.add_argument('--staged-receipt-sha256', required=True)
    parser.add_argument('--staged-source-revision', required=True)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--gradle-distribution-zip', required=True, type=Path)
    args = parser.parse_args()
    evidence = args.evidence_directory.expanduser().resolve()
    if evidence.exists() or evidence == ROOT or ROOT in evidence.parents:
        raise LifecycleError('Evidence directory must start absent and outside the checkout')
    evidence.mkdir(parents=True, mode=0o700)
    results = []
    initial = fingerprint_inputs()
    receipt = None
    binding = None
    initial_payloads = None
    final_payloads = None
    final_binding = None
    final_receipt = None
    final_error = None
    try:
        receipt, receipt_bytes = pinned_receipt(args.staged_receipt, args.staged_receipt_sha256)
        staged = load_helper('lifecycle_staged', 'verify-staged-split-artifact-consumer.py')
        legacy = load_helper('lifecycle_source', 'verify-gradle-legacy-artifact-consumer.py')
        split = load_helper('lifecycle_toolchain', 'verify-gradle-split-artifact-consumer.py')
        repository = args.repository.resolve()
        staged.verify_receipt(repository, receipt)
        initial_payloads = staged.repository_receipt(repository)
        binding = legacy.source_binding(args.staged_source_revision)
        write_json(evidence / 'fixture-inputs-before.json', initial)
        write_json(evidence / 'source-binding-before.json', binding)
        (evidence / 'staged-receipt.json').write_bytes(receipt_bytes)
        write_json(evidence / 'staged-payloads-before.json', initial_payloads)
        write_json(evidence / 'case-plan.json', {'cases': case_plan(), 'requiredCases': 6,
                   'freshDependencyCaches': 2, 'freshJvms': 6, 'retryCount': 0})
        java_home = args.java_home.resolve()
        split.verify_toolchain(ROOT, java_home)
        seed = evidence / 'wrapper-seed'
        seed.mkdir()
        legacy.seed_distribution_zip(args.gradle_distribution_zip.resolve(), seed)
        split.prepare_wrapper_seed(ROOT, ROOT / 'gradlew', java_home, seed)
        environment = split.clean_environment(java_home, seed)
        toolchain = subprocess.check_output([str(ROOT / 'gradlew'), '--no-daemon', '--version'], cwd=ROOT,
                    env=environment, text=True, stderr=subprocess.STDOUT, timeout=60)
        (evidence / 'toolchain.txt').write_text(toolchain)
        write_json(evidence / 'invocation.json', {'argv': sys.argv, 'pythonVersion': sys.version,
                   'JAVA_HOME': str(java_home), 'javaReleaseSha256': digest((java_home / 'release').read_bytes()),
                   'gradleDistributionSha256': digest(args.gradle_distribution_zip.read_bytes())})
        with ThreadPoolExecutor(max_workers=2) as pool:
            graphs = dict(zip(ADAPTERS, pool.map(lambda runtime: prepare_lane(runtime, evidence, repository,
                          receipt, seed, java_home, staged, split), ADAPTERS)))
        for case in case_plan():
            results.append(run_case(case, evidence, graphs[case['runtime']], receipt, java_home, environment))
            write_json(evidence / 'progress.json', results)
    except Exception as error:
        final_error = f'{type(error).__name__}: {error}'
    finally:
        final_inputs = fingerprint_inputs()
        if receipt is not None:
            try:
                final_receipt, _ = pinned_receipt(args.staged_receipt, args.staged_receipt_sha256)
                staged.verify_receipt(args.repository.resolve(), receipt)
                final_payloads = staged.repository_receipt(args.repository.resolve())
                final_binding = legacy.source_binding(args.staged_source_revision)
            except Exception as error:
                final_error = (final_error or '') + f' Final binding failed: {type(error).__name__}: {error}'
        unchanged = (initial == final_inputs and receipt is not None and receipt == final_receipt
                     and initial_payloads is not None and initial_payloads == final_payloads
                     and binding is not None and binding == final_binding)
        if not unchanged and not final_error:
            final_error = 'Source, receipt, staged payload or harness binding changed'
        write_json(evidence / 'fixture-inputs-after.json', final_inputs)
        write_json(evidence / 'source-binding-after.json', final_binding)
        write_json(evidence / 'staged-payloads-after.json', final_payloads)
        summary = {'formatVersion': 1, 'status': 'VERIFIED' if complete_matrix(results) and unchanged
                   and final_error is None else 'FAILED', 'completeExistingLifecycleMatrix': complete_matrix(results)
                   and unchanged and final_error is None, 'requiredCases': 6, 'executedCount': len(results),
                   'passedCount': sum(r['outcome'] == 'PASS' for r in results), 'inputBindingsUnchanged': unchanged,
                   'stagedReceiptSha256': args.staged_receipt_sha256, 'sourceBinding': binding,
                   'error': final_error, 'results': results, 'publicRepositoryConsumption': False,
                   'boundary': 'Existing A-11/A-12/A-13 only; exact local staged 0.2.0, Java 17, controlled loader '
                               'topologies and one pinned MySQL operation per positive cell. No release/adoption claim.'}
        write_json(evidence / 'summary.json', summary)
    print(f'LIFECYCLE_{summary["status"]} passed={summary["passedCount"]}/6 evidence={evidence}', flush=True)
    return 0 if summary['status'] == 'VERIFIED' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'LIFECYCLE_FAILED: {error}', file=sys.stderr)
        sys.exit(1)
