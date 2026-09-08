#!/usr/bin/env python3
"""Focused local-build regression for the four original A-28 old-first 5.5.2 failures.

Uses retained verified dependencies without downloads or changes to original A-28
evidence. This is not an A-28 pass, a full successor matrix, or reviewed staging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from legacy_artifact_inputs import ARTIFACT, GROUP, load_registry

REGISTRY = ROOT / 'scripts/legacy-artifact-inputs.json'
PROBE = 'io.github.ym0506.routecontract.consumer.CurrentEntryRegressionProbe'
PROBE_ROOT = ROOT / 'examples/current-entry-regression-consumer'
NEW_CLASSES = ('io/github/ym0506/routecontract/api/RouteContract.class',
               'io/github/ym0506/routecontract/internal/CurrentRuntimeGuard.class')
BOUNDARY = ('Locally built replacement core plus unchanged retained 5.5.2 adapter/dependency bytes; '
            'four actual legacy JARs first, both new capture methods, fresh Java 17 JVMs. '
            'No SQL, reviewed-staging, public-distribution, adoption, full successor-matrix, or A-28 pass claim.')


class RegressionError(RuntimeError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def file_pin(path, expected=None, size=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RegressionError('Required input is absent, non-regular, or a symbolic link')
    data = path.read_bytes()
    actual = digest(data)
    if expected is not None and actual != expected:
        raise RegressionError('Input SHA-256 differs from its required pin')
    if size is not None and len(data) != size:
        raise RegressionError('Input byte count differs from its required pin')
    return {'path': str(path), 'sha256': actual, 'byteCount': len(data)}


def contained_file(path, root):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RegressionError('Retained input is absent, non-regular, or a symbolic link')
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise RegressionError('Retained input escapes its evidence root')
    return resolved


def class_hashes(root, prefix=None):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise RegressionError('Compiled output contains a symbolic link')
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not relative.endswith('.class') or (prefix and not relative.startswith(prefix)):
            raise RegressionError('Unexpected non-probe or non-class file in compiled output')
        result[relative] = digest(path.read_bytes())
    if not result:
        raise RegressionError('Compiled class output is empty')
    return result


def verify_core(core, expected_sha, classes):
    pin = file_pin(core, expected_sha)
    compiled = class_hashes(classes)
    with zipfile.ZipFile(core) as jar:
        entries = jar.namelist()
        if len(entries) != len(set(entries)):
            raise RegressionError('Core JAR contains duplicate entries')
        for required in NEW_CLASSES:
            if required not in entries:
                raise RegressionError('Core JAR lacks a required new API or guard class')
        actual = {name: digest(jar.read(name)) for name in entries if name.endswith('.class')}
    if actual != compiled:
        raise RegressionError('Core JAR classes differ from supplied local compiler outputs')
    return dict(pin, maturity='locally-built-not-reviewed-staging', compiledClasses=compiled,
                compiledClassesDirectory=str(classes))


def source_footprint():
    files = [ROOT / name for name in ('build.gradle', 'settings.gradle', 'gradle.properties', 'gradle.lockfile',
                                     'gradlew', 'routecontract-core/build.gradle', 'routecontract-core/gradle.lockfile')]
    for directory in ('routecontract-core/src/main', 'gradle'):
        files.extend(path for path in (ROOT / directory).rglob('*') if path.is_file())
    hashes = {str(path.relative_to(ROOT)): file_pin(path)['sha256'] for path in sorted(set(files)) if path.is_file()}
    return {'files': hashes, 'sha256': digest(json.dumps(hashes, sort_keys=True).encode()),
            'boundary': 'Current source/build-input snapshot; compiler-output equality is verified separately. '
                        'This is not an independent reproducible build or reviewed staging receipt.'}


def verify_sources_jar(path, expected_sha):
    pin = file_pin(path, expected_sha)
    source_root = ROOT / 'routecontract-core/src/main/java'
    sources = {file.relative_to(source_root).as_posix(): file_pin(file)['sha256']
               for file in source_root.rglob('*.java')}
    with zipfile.ZipFile(path) as jar:
        names = jar.namelist()
        if len(names) != len(set(names)):
            raise RegressionError('Sources JAR contains duplicate entries')
        archived = {name: digest(jar.read(name)) for name in names if name.endswith('.java')}
    if archived != sources or not sources:
        raise RegressionError('Sources JAR differs from current core Java sources')
    return dict(pin, sources=sources,
                boundary='Sources JAR equals retained worktree Java sources; not independent bytecode reproducibility')


def load_retained(retained):
    registry = load_registry(REGISTRY)
    metadata_paths = [retained / name for name in ('verified-input-inventory.json', 'summary.json',
                                                  'lanes/5.5.2/resolved-classpath.json')]
    for path in metadata_paths:
        contained_file(path, retained)
    inventory, summary, graph = (json.loads(path.read_text()) for path in metadata_paths)
    if summary.get('registrySha256') != file_pin(REGISTRY)['sha256']:
        raise RegressionError('Retained A-28 used a different legacy registry')
    if summary.get('status') != 'FAILED':
        raise RegressionError('Expected the preserved failing original A-28 summary')
    first_party = [item for item in graph['artifacts'] if item['group'] == GROUP]
    if sorted((p['module'], p['version']) for p in first_party) != [
            ('routecontract-core', '0.2.0'), ('routecontract-shardingsphere-5.5.2', '0.2.0')]:
        raise RegressionError('Retained 5.5.2 first-party graph differs')
    sharding = [item for item in graph['artifacts'] if item['group'] == 'org.apache.shardingsphere']
    if not sharding or any(item['version'] != '5.5.2' for item in sharding):
        raise RegressionError('Retained graph is not exact ShardingSphere 5.5.2')
    paths = set()
    pins = []
    for artifact in graph['artifacts']:
        path = contained_file(artifact['path'], retained)
        if str(path) in paths:
            raise RegressionError('Duplicate retained graph artifact path')
        paths.add(str(path))
        pins.append(file_pin(path, artifact['sha256']))
        if artifact['group'] == GROUP:
            matching = [p for p in inventory if p['origin'] == 'staged' and p['module'] == artifact['module']
                        and p['version'] == artifact['version'] and p['name'].endswith('.jar')]
            if len(matching) != 1 or matching[0]['sha256'] != artifact['sha256']:
                raise RegressionError('Retained first-party graph differs from its original inventory')
    legacy_inputs = []
    failures = []
    for release in registry['distributed']:
        jars = [p for p in release['payloads'] if p['extension'] == 'jar']
        if len(jars) != 1:
            raise RegressionError('Expected exactly one actual legacy JAR per release')
        pin = jars[0]
        matching = [p for p in inventory if p['origin'] == 'public-legacy'
                    and p['version'] == release['version'] and p['name'] == pin['name']]
        if len(matching) != 1 or matching[0]['sha256'] != pin['sha256']:
            raise RegressionError('Retained legacy inventory differs from public registry')
        path = contained_file(retained / 'repository' / matching[0]['relativePath'], retained)
        entry = dict(file_pin(path, pin['sha256'], pin['byteCount']), version=release['version'])
        with zipfile.ZipFile(path) as jar:
            names = jar.namelist()
            if len(names) != len(set(names)) or any(name in names for name in NEW_CLASSES):
                raise RegressionError('Actual legacy layout duplicates or shadows a new class')
            for name, expected in release['layout']['entries'].items():
                if digest(jar.read(name)) != expected:
                    raise RegressionError('Actual legacy class/service layout differs from registry')
        case_id = f'5.5.2-{release["version"]}-legacy-first-capture'
        results = [r for r in summary['results'] if r['case']['id'] == case_id]
        observation_path = contained_file(retained / 'cases' / case_id / 'observed.json', retained)
        if len(results) != 1 or results[0]['outcome'] != 'WRONG_DIAGNOSTIC':
            raise RegressionError('Original A-28 failure was not preserved')
        observed_pin = file_pin(observation_path, results[0]['observedSha256'])
        observed = json.loads(observation_path.read_text())
        if (observed != results[0]['observed'] or observed['actionEntered'] or observed['returned']
                or observed['linkageFailure'] or observed['physicalBusinessExecutions'] != 0
                or observed['businessRows'] or observed['routeContractOrigin'] != str(path)
                or observed['captureRegistryOrigin'] != str(path)
                or 'reported 5.5.2' not in '\n'.join(observed['exceptionMessages'])
                or 'RC_LEGACY_ADAPTER_COLLISION' in '\n'.join(observed['exceptionMessages'])):
            raise RegressionError('Original failure observation no longer proves legacy-first version rejection')
        failures.append({'caseId': case_id, 'outcome': 'WRONG_DIAGNOSTIC', **observed_pin})
        legacy_inputs.append(entry)
    if len(legacy_inputs) != 4:
        raise RegressionError('Focused regression expects exactly four registered legacy releases')
    return {'graph': graph, 'artifactPins': pins, 'legacyInputs': legacy_inputs,
            'originalFailures': failures, 'metadataPins': [file_pin(p) for p in metadata_paths]}


def classify(case, observed, core):
    required = ('mode', 'pid', 'javaVersion', 'shardingSphereVersion', 'returned', 'actionEntered',
                'actionEntries', 'linkageFailure', 'exceptionClasses', 'exceptionMessages', 'stackFrames',
                'newEntryOrigin', 'guardOrigin', 'legacyEntryOrigin', 'captureRegistryOrigin')
    if any(key not in observed for key in required):
        return 'MALFORMED_OBSERVATION'
    if observed['mode'] != case['mode'] or not observed['javaVersion'].startswith('17.'):
        return 'WRONG_EXECUTION_ENVIRONMENT'
    if observed['shardingSphereVersion'] != '5.5.2':
        return 'WRONG_EXECUTION_ENVIRONMENT'
    if observed['actionEntered'] or observed['actionEntries'] != 0:
        return 'ACTION_ENTERED'
    if observed['returned']:
        return 'SILENT_SUCCESS'
    if observed['linkageFailure']:
        return 'LINKAGE_FAILURE'
    if (observed['newEntryOrigin'] != str(core) or observed['guardOrigin'] != str(core)
            or observed['legacyEntryOrigin'] != case['legacyPath']
            or observed['captureRegistryOrigin'] != case['legacyPath']):
        return 'UNEXPECTED_CLASS_ORIGIN'
    if not observed['exceptionClasses'] or not any(
            message.startswith('RC_LEGACY_ADAPTER_COLLISION:') for message in observed['exceptionMessages']):
        return 'WRONG_DIAGNOSTIC'
    # The actual guard must be on the thrown stack; a fixture must not synthesize its error.
    if not any(frame.startswith('io.github.ym0506.routecontract.internal.CurrentRuntimeGuard.')
               for frame in observed['stackFrames']):
        return 'GUARD_NOT_OBSERVED'
    return 'PASS'


def clean_environment(java_home):
    # No inherited agents, bootstrap classpaths, JDK options, or application credentials.
    return {'PATH': str(java_home / 'bin') + os.pathsep + '/usr/bin:/bin',
            'JAVA_HOME': str(java_home), 'LANG': 'en_US.UTF-8', 'LC_ALL': 'en_US.UTF-8'}


def verify_pins(pins):
    for pin in pins:
        file_pin(pin['path'], pin['sha256'], pin['byteCount'])


def run_case(case, directory, java_home, core, adapter, third_party, classes, class_pins, input_pins):
    destination = directory / 'cases' / case['id']
    destination.mkdir(parents=True)
    paths = [case['legacyPath'], str(core), adapter, str(classes), *third_party]
    command = [str(java_home / 'bin/java'), '-cp', os.pathsep.join(paths), PROBE, case['mode'],
               str(destination / 'observed.json')]
    write_json(destination / 'command.json', {'argv': command, 'freshJvm': True, 'case': case,
                                            'artifacts': input_pins, 'compiledClasses': class_pins})
    result = {'case': case, 'outcome': 'PROCESS_FAILED', 'exitCode': None}
    started = time.monotonic()
    try:
        verify_pins(input_pins)
        if class_hashes(classes, 'io/github/ym0506/routecontract/consumer/') != class_pins:
            raise RegressionError('Compiled probe changed before launch')
        with (destination / 'jvm.log').open('w') as log:
            process = subprocess.run(command, cwd=destination, env=clean_environment(java_home), stdout=log,
                                     stderr=subprocess.STDOUT, timeout=60, check=False)
        result['exitCode'] = process.returncode
        observation = destination / 'observed.json'
        if process.returncode == 0 and observation.is_file():
            result['observed'] = json.loads(observation.read_text())
            result['observedSha256'] = file_pin(observation)['sha256']
            result['outcome'] = classify(case, result['observed'], core)
        verify_pins(input_pins)
        if class_hashes(classes, 'io/github/ym0506/routecontract/consumer/') != class_pins:
            raise RegressionError('Compiled probe changed during launch')
    except subprocess.TimeoutExpired:
        result['outcome'] = 'PROCESS_TIMEOUT'
    except (RegressionError, ValueError, OSError) as error:
        result.update(outcome='INPUT_OR_OBSERVATION_ERROR', error=str(error))
    result['elapsedSeconds'] = round(time.monotonic() - started, 3)
    if (destination / 'jvm.log').is_file():
        result['logSha256'] = file_pin(destination / 'jvm.log')['sha256']
    write_json(destination / 'result.json', result)
    print(f'CURRENT_ENTRY_CASE {case["id"]} {result["outcome"]}', flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-jar', type=Path, required=True)
    parser.add_argument('--expected-core-sha256', required=True)
    parser.add_argument('--core-classes-directory', type=Path, required=True)
    parser.add_argument('--core-sources-jar', type=Path, required=True)
    parser.add_argument('--expected-core-sources-sha256', required=True)
    parser.add_argument('--retained-a28-evidence', type=Path, required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch('[0-9a-f]{64}', args.expected_core_sha256):
        parser.error('--expected-core-sha256 must be a lowercase SHA-256')
    if not re.fullmatch('[0-9a-f]{64}', args.expected_core_sources_sha256):
        parser.error('--expected-core-sources-sha256 must be a lowercase SHA-256')
    retained = args.retained_a28_evidence.resolve(strict=True)
    directory = args.evidence_directory.resolve()
    if directory.exists() or directory.is_relative_to(retained) or directory.is_relative_to(ROOT):
        parser.error('Evidence directory must be new and outside the checkout and retained evidence')
    directory.mkdir(parents=True)
    summary = {'formatVersion': 1, 'status': 'INCOMPLETE', 'boundary': BOUNDARY,
               'originalA28Status': 'FAILED', 'fullSuccessorMatrix': False, 'reviewedStaging': False,
               'requiredCases': 8, 'results': []}
    write_json(directory / 'summary.json', summary)
    try:
        core = args.core_jar.resolve(strict=True)
        classes = args.core_classes_directory.resolve(strict=True)
        java_home = args.java_home.resolve(strict=True)
        source_before = source_footprint()
        core_evidence = verify_core(core, args.expected_core_sha256, classes)
        sources_path = args.core_sources_jar.resolve(strict=True)
        sources_evidence = verify_sources_jar(sources_path, args.expected_core_sources_sha256)
        retained_inputs = load_retained(retained)
        harness_paths = [Path(__file__).resolve(), REGISTRY, ROOT / 'scripts/legacy_artifact_inputs.py',
                         *sorted(PROBE_ROOT.rglob('*.java'))]
        harness_pins = [file_pin(path) for path in harness_paths]
        java_check = subprocess.run([str(java_home / 'bin/java'), '-version'], capture_output=True,
                                    text=True, env=clean_environment(java_home), timeout=30, check=False)
        javac_check = subprocess.run([str(java_home / 'bin/javac'), '-version'], capture_output=True,
                                     text=True, env=clean_environment(java_home), timeout=30, check=False)
        versions = {'java': java_check.stdout + java_check.stderr, 'javac': javac_check.stdout + javac_check.stderr}
        if (java_check.returncode or javac_check.returncode or not re.search(r'version "17\.', versions['java'])
                or not re.search(r'javac 17\.', versions['javac'])):
            raise RegressionError('Both java and javac must be Java 17')
        write_json(directory / 'local-build-inputs.json', {'core': core_evidence, 'source': source_before,
                   'sourcesJar': sources_evidence,
                   'harness': harness_pins, 'toolchain': versions,
                   'gitHead': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   'gitStatus': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)})
        write_json(directory / 'retained-inputs.json', retained_inputs)
        graph = retained_inputs['graph']
        adapter = next(p['path'] for p in graph['artifacts']
                       if p['group'] == GROUP and p['module'] == 'routecontract-shardingsphere-5.5.2')
        third_party = [p['path'] for p in graph['artifacts'] if p['group'] != GROUP]
        output = directory / 'probe-classes'
        output.mkdir()
        compile_command = [str(java_home / 'bin/javac'), '--release', '17', '-Xlint:all', '-Werror',
                           '-proc:none', '-cp', os.pathsep.join([str(core), adapter, *third_party]),
                           '-d', str(output), *[str(path) for path in sorted(PROBE_ROOT.rglob('*.java'))]]
        write_json(directory / 'compile-command.json', {'argv': compile_command,
                   'boundary': 'External probe compilation only; no product compilation or substituted production class'})
        with (directory / 'javac.log').open('w') as log:
            compiled = subprocess.run(compile_command, cwd=directory, env=clean_environment(java_home),
                                      stdout=log, stderr=subprocess.STDOUT, timeout=60, check=False)
        if compiled.returncode:
            raise RegressionError('External new-API probe compilation failed; inspect javac.log')
        probe_classes = class_hashes(output, 'io/github/ym0506/routecontract/consumer/')
        common_pins = [file_pin(core, args.expected_core_sha256), *[p for p in retained_inputs['artifactPins']
                       if p['path'] in [adapter, *third_party]]]
        for legacy in retained_inputs['legacyInputs']:
            for mode in ('capture', 'captureResult'):
                case = {'id': f'5.5.2-{legacy["version"]}-legacy-first-{mode}', 'legacyVersion': legacy['version'],
                        'legacyPath': legacy['path'], 'runtime': '5.5.2', 'order': 'legacy-first', 'mode': mode}
                result = run_case(case, directory, java_home, core, adapter, third_party, output, probe_classes,
                                  [legacy, *common_pins])
                summary['results'].append(result)
                write_json(directory / 'summary.json', summary)
        verify_pins(harness_pins + retained_inputs['metadataPins'] + retained_inputs['artifactPins']
                    + retained_inputs['legacyInputs'] + retained_inputs['originalFailures'])
        if source_footprint() != source_before or verify_core(core, args.expected_core_sha256, classes) != core_evidence:
            raise RegressionError('Local source/build inputs or compiler outputs changed during the regression')
        if verify_sources_jar(sources_path, args.expected_core_sources_sha256) != sources_evidence:
            raise RegressionError('Local sources JAR changed during the regression')
        passed = sum(result['outcome'] == 'PASS' for result in summary['results'])
        pids = [result.get('observed', {}).get('pid') for result in summary['results']]
        summary.update(executedCount=len(summary['results']), passedCount=passed,
                       status='PASS' if passed == 8 and len(set(pids)) == 8 else 'FAILED')
    except (RegressionError, OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        summary.update(status='FAILED', error=str(error), executedCount=len(summary['results']),
                       passedCount=sum(result['outcome'] == 'PASS' for result in summary['results']))
    write_json(directory / 'summary.json', summary)
    print(json.dumps({key: summary.get(key) for key in ('status', 'executedCount', 'passedCount', 'error')}))
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
