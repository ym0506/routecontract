#!/usr/bin/env python3
"""Verify bounded v0.1.2 -> staged 0.2 public classpath migration on exact 5.5.3.

First-party artifacts are resolved from supplied repositories, never built by this harness.
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
import zipfile

GROUP = 'io.github.ym0506.routecontract'
GROUP_PATH = Path('io/github/ym0506/routecontract')
ADAPTER = 'routecontract-shardingsphere-5.5'
CORE = 'routecontract-core'
NS = 'https://schema.gradle.org/dependency-verification'
SUITE = 'io.github.ym0506.routecontract.consumer.OldBytecodeMySqlTest'
EXPECTED_MYSQL_CASES = {
    'selectedRuntimeApiOriginsAndAutoDiscoveredHookAreTheExpectedJarBytes',
    'unchangedOldCaptureAndCaptureResultBytecodeMatchTheReviewedSchemaOneBaseline',
    'oldBytecodeStillRejectsTwoAttemptsWhenTheBusinessRowIsUnchanged',
}
TIMEOUT = 1200


class VerificationError(RuntimeError):
    """A required migration contract or its evidence did not hold."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_regular(root: Path, relative: Path) -> Path:
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        mode = cursor.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise VerificationError(f'Artifact paths must not be symlinks: {relative}')
    if not stat.S_ISREG(mode):
        raise VerificationError(f'Artifact must be a regular file: {relative}')
    return cursor


def receipt(repository: Path, version: str, pinned: dict) -> dict:
    modules = (ADAPTER,) if version == '0.1.2' else (ADAPTER, CORE)
    artifacts = []
    for module in modules:
        for extension in ('jar', 'pom'):
            relative = GROUP_PATH / module / version / f'{module}-{version}.{extension}'
            path = require_regular(repository, relative)
            sha = digest(path)
            if version == '0.1.2' and pinned['artifacts'].get(path.name) != sha:
                raise VerificationError(f'Immutable public v0.1.2 hash mismatch: {path.name}')
            artifacts.append({'module': module, 'version': version, 'name': path.name,
                              'relativePath': relative.as_posix(), 'sha256': sha})
    return {'version': version, 'artifacts': artifacts}


def prepare_metadata(source: Path, destination: Path, receipts: list[dict]) -> None:
    tree = ET.parse(source)
    configuration = tree.getroot().find(f'{{{NS}}}configuration')
    if configuration is None or configuration.findtext(f'{{{NS}}}verify-metadata') != 'true':
        raise VerificationError('Strict verification must include dependency metadata')
    if configuration.find(f'{{{NS}}}trusted-artifacts') is not None:
        raise VerificationError('Artifact trust bypasses are not accepted')
    components = tree.getroot().find(f'{{{NS}}}components')
    if components is None:
        raise VerificationError('Missing third-party verification components')
    for component in list(components):
        if component.get('group') == GROUP:
            components.remove(component)
    for item in receipts:
        by_module = {}
        for artifact in item['artifacts']:
            module = artifact['module']
            if module not in by_module:
                by_module[module] = ET.SubElement(components, f'{{{NS}}}component',
                    {'group': GROUP, 'name': module, 'version': item['version']})
            element = ET.SubElement(by_module[module], f'{{{NS}}}artifact', {'name': artifact['name']})
            ET.SubElement(element, f'{{{NS}}}sha256', {'value': artifact['sha256'],
                'origin': 'Pinned immutable v0.1.2 release' if item['version'] == '0.1.2'
                else 'Supplied local staging receipt; not publisher provenance'})
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.register_namespace('', NS)
    tree.write(destination, encoding='UTF-8', xml_declaration=True)


def clean_environment(cache: Path) -> dict:
    result = dict(os.environ)
    for key in tuple(result):
        if key.startswith('ORG_GRADLE_PROJECT_') or key in (
                'GRADLE_OPTS', 'JAVA_OPTS', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
            result.pop(key, None)
    result['GRADLE_USER_HOME'] = str(cache)
    return result


def run(command: list[str], cwd: Path, environment: dict, log: Path,
        expected_exit: int = 0, marker: str | None = None) -> str:
    print(f'Running {log.name}', flush=True)
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.run(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT, timeout=TIMEOUT)
    content = log.read_text(encoding='utf-8', errors='replace')
    if process.returncode != expected_exit or (marker and marker not in content):
        raise VerificationError(f'Unexpected probe result (exit {process.returncode}): {log}')
    return content


def class_receipt(directory: Path) -> dict[str, str]:
    result = {p.relative_to(directory).as_posix(): digest(p) for p in sorted(directory.rglob('*.class'))}
    if not result:
        raise VerificationError('Old bytecode directory contains no compiled classes')
    return result


def verify_junit(path: Path) -> dict:
    suite = ET.parse(path).getroot()
    expected = {'tests': 3, 'failures': 0, 'errors': 0, 'skipped': 0}
    counts = {name: int(suite.attrib[name]) for name in expected}
    cases = suite.findall('testcase')
    names = {case.get('name', '').removesuffix('()') for case in cases}
    if counts != expected or suite.get('name') != SUITE or len(cases) != 3 or names != EXPECTED_MYSQL_CASES:
        raise VerificationError(f'MySQL migration suite is incomplete or failed: {path}')
    if any(case.find(kind) is not None for case in cases for kind in ('failure', 'error', 'skipped')):
        raise VerificationError('A required MySQL migration testcase did not pass')
    return counts



def verify_mysql_evidence(directory: Path, version: str, baseline_sha256: str) -> None:
    if digest(directory / 'approved.json') != baseline_sha256:
        raise VerificationError('Retained approved baseline differs from reviewed bytes')
    schema = 1 if version == '0.1.2' else 2
    for filename, attempts in (('equality-capture.json', 1), ('equality-capture-result.json', 1), ('candidate.json', 2)):
        manifest = json.loads((directory / filename).read_text())
        if manifest['schemaVersion'] != schema or manifest['counts']['observedPhysicalAttemptCount'] != attempts:
            raise VerificationError('Retained manifest does not prove the expected migration observation')
    if (directory / 'equality-capture.json').read_bytes() != (directory / 'equality-capture-result.json').read_bytes():
        raise VerificationError('Capture and captureResult route evidence differs')
    business = json.loads((directory / 'business-rows.json').read_text())
    rows = [{'orderId': 201, 'userId': 3, 'status': 'PAID'}]
    if business != {'syntheticFixtureData': True, 'equality': rows, 'range': rows}:
        raise VerificationError('Retained business rows do not prove the exact expected result')
    summary = json.loads((directory / 'business-summary.json').read_text())
    if (summary['routeContractVersion'] != version or summary['shardingSphereJdbcVersion'] != '5.5.3'
            or summary['business'] != {'exactExpectedRowMatched': True, 'equalityRowCount': 1, 'rangeRowCount': 1, 'sameRows': True}
            or summary['equality'] != {'physicalJdbcExecutionAttempts': 1, 'verification': 'MATCH'}
            or summary['range'] != {'physicalJdbcExecutionAttempts': 2, 'verification': 'POLICY_VIOLATION', 'codes': ['RCM201', 'RCM202']}):
        raise VerificationError('Retained business/route summary is incomplete')


def parse_api(text: str) -> dict:
    result = {}
    current = None
    member = None
    for line in text.splitlines():
        if line.startswith('public ') and line.endswith(' {'):
            match = re.search(r'(?:class|interface) ([^ <]+)', line)
            if not match:
                raise VerificationError('Unrecognized public API declaration')
            current = match.group(1)
            result[current] = {'declaration': line, 'members': set()}
        elif line.startswith(('  public ', '  protected ')):
            member = line.strip().split(' = ', 1)[0]
        elif line.strip().startswith('descriptor:'):
            if current is None or member is None:
                raise VerificationError('Descriptor has no public owner/member')
            result[current]['members'].add((member, line.strip().split(': ', 1)[1]))
    if not result:
        raise VerificationError('Empty API inventory')
    return result


def verify_api_inventory(old: str, current: str, frozen: str) -> dict:
    if old != frozen:
        raise VerificationError('Pinned old API inventory does not match authenticated v0.1.2 bytes')
    before, after = parse_api(old), parse_api(current)
    removed = []
    for name, item in before.items():
        selected = after.get(name)
        if selected is None or selected['declaration'] != item['declaration']:
            removed.append(name + ': class declaration changed')
        else:
            removed.extend(name + ': ' + str(member)
                           for member in sorted(item['members'] - selected['members']))
    if removed:
        raise VerificationError('Public descriptors removed/changed: ' + '; '.join(removed))
    return {'publicTypes': len(before), 'preservedMemberDescriptors': sum(len(x['members']) for x in before.values())}


def copy_consumer(root: Path, fixture: Path, target: Path, version: str, receipts: list[dict]) -> None:
    target.mkdir()
    for filename in ('build.gradle', 'settings.gradle'):
        shutil.copy2(fixture / filename, target / filename)
    shutil.copytree(fixture / 'src', target / 'src')
    shutil.copy2(fixture / 'gradle-locks' / f'{version}.lockfile', target / 'gradle.lockfile')
    shutil.copy2(root / 'gradlew', target / 'gradlew')
    shutil.copytree(root / 'gradle/wrapper', target / 'gradle/wrapper')
    prepare_metadata(root / 'gradle/verification-metadata.xml', target / 'gradle/verification-metadata.xml', receipts)


def graph_data(consumer: Path, repository: Path, expected: dict) -> dict:
    value = json.loads((consumer / 'build/migration-graph.json').read_text())
    version = expected['version']
    if value['version'] != version or value['directRouteContractDependencies'] != [ADAPTER]:
        raise VerificationError('Consumer did not request exactly the existing adapter GAV')
    if value['transitiveCore'] != (version == '0.2.0'):
        raise VerificationError('Current adapter must resolve core transitively')
    first_party = [a for a in value['artifacts'] if a['coordinate'].startswith(GROUP + ':')]
    wanted = {f'{GROUP}:{a["module"]}:{version}': a for a in expected['artifacts'] if a['name'].endswith('.jar')}
    if {a['coordinate'] for a in first_party} != set(wanted) or len(first_party) != len(wanted):
        raise VerificationError('Unexpected selected first-party artifact set')
    for artifact in first_party:
        selected = Path(artifact['file'])
        frozen = wanted[artifact['coordinate']]
        if selected.name != frozen['name'] or digest(selected) != frozen['sha256']:
            raise VerificationError('Resolved artifact differs from frozen supplied bytes')
        if artifact['sha256'] != frozen['sha256']:
            raise VerificationError('Resolver graph checksum evidence disagrees')
        if artifact['file'] not in value['compileClasspath']:
            raise VerificationError('First-party API is absent from the resolved compile classpath')
    if len(value['classpath']) != len(set(value['classpath'])):
        raise VerificationError('Duplicate runtime classpath entries')
    return value


def probes(root: Path, fixture: Path, evidence: Path, old_graph: dict, new_graph: dict,
           environment: dict) -> dict:
    home = Path(environment.get('JAVA_HOME', ''))
    javac, java, javap = (home / 'bin' / name for name in ('javac', 'java', 'javap'))
    if not all(path.is_file() for path in (javac, java, javap)):
        raise VerificationError('Set JAVA_HOME to the Java 17 JDK used by this migration lane')
    if not re.search(r'javac 17(?:\.|\s)', subprocess.check_output([str(javac), '-version'], text=True)):
        raise VerificationError('Migration bytecode/source lane requires Java 17')
    output = evidence / 'probes'
    output.mkdir()
    old_classes, recompiled, current_classes = (output / name for name in ('old-classes', 'recompiled', 'current-classes'))
    for path in (old_classes, recompiled, current_classes):
        path.mkdir()
    oldcp, newcp = (os.pathsep.join(item['classpath']) for item in (old_graph, new_graph))
    old_compile_cp, new_compile_cp = (os.pathsep.join(item['compileClasspath']) for item in (old_graph, new_graph))
    sources = fixture / 'probes'
    frozen = (fixture / 'public-api-0.1.2.txt').read_text()
    names = list(parse_api(frozen))
    for label, cp in (('old', oldcp), ('current', newcp)):
        run([str(javap), '-protected', '-s', '-constants', '-classpath', cp, *names], root, environment,
            output / f'{label}-api.txt')
    api = verify_api_inventory((output / 'old-api.txt').read_text(), (output / 'current-api.txt').read_text(), frozen)
    old_jar = next(Path(a['file']) for a in old_graph['artifacts'] if a['coordinate'] == f'{GROUP}:{ADAPTER}:0.1.2')
    with zipfile.ZipFile(old_jar) as archive:
        classes = {name[:-6].replace('/', '.') for name in archive.namelist()
                   if name.endswith('.class') and '/internal/' not in name}
    if classes != set(names):
        raise VerificationError('Public inventory does not cover the complete old non-internal class layout')
    old_sources = ['LegacyModelProbe', 'LegacyEnumSwitchProbe', 'ModuleBoundaryProbe']
    run([str(javac), '--release', '17', '-cp', old_compile_cp, '-d', str(old_classes),
         *(str(sources / f'{name}.java') for name in old_sources)], root, environment, output / 'old-compile.log')
    bytecode = class_receipt(old_classes)
    (output / 'old-bytecode.json').write_text(json.dumps(bytecode, indent=2) + '\n')
    for label, cp, version in (('old-control', oldcp, '0.1.2'), ('old-on-current', newcp, '0.2.0')):
        model_output = output / label
        model_output.mkdir()
        text = run([str(java), '-cp', str(old_classes) + os.pathsep + cp, 'LegacyModelProbe', str(model_output)],
                   root, environment, output / f'{label}-models.log', marker='ROUTECONTRACT_LEGACY_MODELS_PASS')
        wanted_core = f'routecontract-{ "shardingsphere-5.5-0.1.2" if version == "0.1.2" else "core-0.2.0" }.jar'
        identity = 'false' if version == '0.1.2' else 'true'
        expected_schema = 1 if version == '0.1.2' else 2
        for marker in (f'snapshotCodeSource={wanted_core}', f'generatedSchema={expected_schema}',
                       f'snapshotStringHasIdentity={identity}', f'manifestStringHasIdentity={identity}'):
            if marker not in text:
                raise VerificationError(f'Missing record/code-source migration evidence: {marker}')
        shapes = [line for line in text.splitlines() if line.startswith(('snapshotComponents=', 'manifestComponents='))]
        expected_shapes = (fixture / 'record-shapes-0.1.2.txt').read_text().splitlines()
        if version == '0.2.0':
            expected_shapes = [line.replace('schemaVersion:int, ', 'schemaVersion:int, runtimeIdentity:io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity, ') for line in expected_shapes]
        if shapes != expected_shapes:
            raise VerificationError('Record reflection does not exhibit the documented identity migration')
        (model_output / 'record-shapes.txt').write_text('\n'.join(shapes) + '\n')
        run([str(java), '-cp', str(old_classes) + os.pathsep + cp, 'LegacyModelProbe', str(model_output), 'manifest-constant'],
            root, environment, output / f'{label}-manifest-constant.log', marker='ROUTECONTRACT_LEGACY_MANIFEST_CONSTANT_PASS')
    if (output / 'old-control/legacy-schema1.json').read_bytes() != (output / 'old-on-current/legacy-schema1.json').read_bytes():
        raise VerificationError('Synthetic legacy schema-1 codec bytes changed')
    run([str(javac), '--release', '17', '-cp', new_compile_cp, '-d', str(recompiled), str(sources / 'LegacyModelProbe.java')],
        root, environment, output / 'unchanged-source-recompile.log')
    for mode, message in (('snapshot', 'The legacy RouteSnapshot constructor accepts only snapshot schema 1'),
                          ('manifest-constant', 'The legacy ObservedExecutionManifest constructor accepts only manifest schema 1')):
        run([str(java), '-cp', str(recompiled) + os.pathsep + newcp, 'LegacyModelProbe', str(output), mode],
            root, environment, output / f'constant-rejection-{mode}.log', expected_exit=1, marker=message)
    run([str(java), '-cp', str(old_classes) + os.pathsep + oldcp, 'LegacyEnumSwitchProbe'],
        root, environment, output / 'enum-old-control.log', marker='OUTCOME_COUNTS_CHANGED')
    run([str(java), '-cp', str(old_classes) + os.pathsep + newcp, 'LegacyEnumSwitchProbe', 'old-values'],
        root, environment, output / 'enum-old-values-on-current.log', marker='OUTCOME_COUNTS_CHANGED')
    for value in ('UNSUPPORTED_RUNTIME_IDENTITY', 'RUNTIME_IDENTITY_MISMATCH'):
        run([str(java), '-cp', str(old_classes) + os.pathsep + newcp, 'LegacyEnumSwitchProbe', value],
            root, environment, output / f'enum-old-on-current-{value}.log', expected_exit=1, marker='IncompatibleClassChangeError')
    run([str(javac), '-J-Duser.language=en', '--release', '17', '-cp', new_compile_cp, '-d', str(recompiled),
         str(sources / 'LegacyEnumSwitchProbe.java')], root, environment, output / 'enum-source-recompile.log',
        expected_exit=1, marker='does not cover all possible input values')
    # Recompile the complete old public capture/captureResult consumer against the normal
    # new compile graph, but never substitute these classes for the old-bytecode execution.
    mysql_source = fixture / 'src/test/java/io/github/ym0506/routecontract/consumer/OldBytecodeMySqlTest.java'
    run([str(javac), '--release', '17', '-g', '-encoding', 'UTF-8', '-Xlint:all', '-Werror',
         '-cp', new_compile_cp, '-d', str(current_classes), str(mysql_source)],
        root, environment, output / 'unchanged-mysql-source-recompile.log')
    for name, marker in (('ExplicitIdentityProbe', 'schema1Schema2VerifierMatch=true'),
                         ('MigratedEnumProbe', 'ROUTECONTRACT_MIGRATED_ENUM_PASS')):
        run([str(javac), '--release', '17', '-cp', new_compile_cp, '-d', str(current_classes), str(sources / f'{name}.java')],
            root, environment, output / f'{name}-compile.log')
        run([str(java), '-cp', str(current_classes) + os.pathsep + newcp, name], root, environment,
            output / f'{name}-run.log', marker=marker)
    first_party = [a['file'] for a in new_graph['artifacts'] if a['coordinate'].startswith(GROUP + ':')]
    third_party = [path for path in new_graph['classpath'] if path not in first_party]
    run([str(java), '--module-path', os.pathsep.join(first_party), '--add-modules', 'ALL-MODULE-PATH',
         '-cp', os.pathsep.join([str(old_classes), *third_party]), 'ModuleBoundaryProbe'], root, environment,
        output / 'module-boundary.log', marker='RC_UNSUPPORTED_MODULE_PATH; action=false')
    if class_receipt(old_classes) != bytecode:
        raise VerificationError('Old probe bytecode changed during migration verification')
    return {**api, 'oldBytecodeClasses': len(bytecode), 'schema1CodecBytesEqual': True,
            'sourceConstantRejections': 2, 'enumNewValuesRejectedByOldBytecode': 2, 'enumBinaryAndSourceChangesObserved': True,
            'unchangedMySqlSourceRecompiled': True, 'explicitIdentitySourcePassed': True,
            'moduleCaptureRejectedBeforeAction': True}


def verify(root: Path, legacy_repository: Path, repository: Path, evidence: Path) -> dict:
    fixture = root / 'examples/public-api-migration-consumer'
    pinned = json.loads((fixture / 'release-inputs.json').read_text())
    legacy = receipt(legacy_repository, '0.1.2', pinned)
    current = receipt(repository, '0.2.0', pinned)
    baseline = fixture / 'src/test/resources/manifests/find-paid-orders-by-user.approved.json'
    if digest(baseline) != pinned['baselineSha256']:
        raise VerificationError('Immutable reviewed schema-1 baseline differs from the pinned bytes')
    evidence.mkdir()
    receipts = [legacy, current]
    (evidence / 'artifact-receipts.json').write_text(json.dumps(receipts, indent=2) + '\n')
    counts = {}
    with tempfile.TemporaryDirectory(prefix='routecontract-api-migration-') as temp:
        temporary = Path(temp)
        consumers = {}
        graphs = {}
        old_classes = None
        frozen_classes = None
        for item, supplied in ((legacy, legacy_repository), (current, repository)):
            version = item['version']
            consumer = temporary / f'consumer-{version}'
            cache = temporary / f'gradle-home-{version}'
            copy_consumer(root, fixture, consumer, version, receipts)
            lane = evidence / version
            lane.mkdir()
            environment = clean_environment(cache)
            args = [str(consumer / 'gradlew'), '--no-daemon', '--no-build-cache', '--no-configuration-cache',
                    '--dependency-verification=strict', '--console=plain', f'-ProutecontractVersion={version}',
                    f'-ProutecontractRepository={supplied}', f'-ProutecontractLegacySha256={pinned["artifacts"][ADAPTER + "-0.1.2.jar"]}']
            for artifact in item['artifacts']:
                if artifact['name'].endswith('.jar'):
                    args.append(f'-ProutecontractSha256.{artifact["module"]}={artifact["sha256"]}')
            if old_classes is not None:
                args.append(f'-ProutecontractOldClasses={old_classes}')
            try:
                run(args + ['verifyMigrationGraph', 'testClasses'], consumer, environment, lane / 'resolve-and-compile.log',
                    marker='ROUTECONTRACT_MIGRATION_POM_GRAPH_VERIFIED')
                graphs[version] = graph_data(consumer, supplied, item)
                if version == '0.1.2':
                    old_classes = consumer / 'build/classes/java/test'
                    frozen_classes = class_receipt(old_classes)
                    (evidence / 'old-mysql-bytecode.json').write_text(json.dumps(frozen_classes, indent=2) + '\n')
                    shutil.copytree(old_classes, evidence / 'old-mysql-classes')
                run(args + ['test'], consumer, environment, lane / 'mysql-test.log',
                    marker=f'ROUTECONTRACT_OLD_BYTECODE_MYSQL_VERIFIED routecontract={version}')
                counts[version] = verify_junit(consumer / 'build/test-results/test' / f'TEST-{SUITE}.xml')
                verify_mysql_evidence(consumer / 'build/migration-mysql-evidence' / version, version, pinned['baselineSha256'])
                if class_receipt(old_classes) != frozen_classes:
                    raise VerificationError('The old MySQL consumer was recompiled or changed')
                consumers[version] = consumer
            finally:
                for source, name in ((consumer / 'build/test-results/test', 'junit'),
                                     (consumer / 'build/migration-mysql-evidence', 'mysql-evidence')):
                    if source.is_dir():
                        shutil.copytree(source, lane / name, dirs_exist_ok=True)
                for source, name in ((consumer / 'build/migration-graph.json', 'resolved-graph.json'),
                                     (consumer / 'gradle/verification-metadata.xml', 'verification-metadata.xml'),
                                     (consumer / 'gradle.lockfile', 'gradle.lockfile')):
                    if source.is_file():
                        shutil.copy2(source, lane / name)
        probe_summary = probes(root, fixture, evidence, graphs['0.1.2'], graphs['0.2.0'], clean_environment(temporary / 'probe-home'))
    if receipt(legacy_repository, '0.1.2', pinned) != legacy or receipt(repository, '0.2.0', pinned) != current:
        raise VerificationError('Supplied artifacts changed during migration verification')
    if digest(baseline) != pinned['baselineSha256']:
        raise VerificationError('Reviewed baseline changed during verification')
    summary = {'formatVersion': 1, 'scope': 'bounded-local-public-api-migration',
               'runtime': 'Apache ShardingSphere-JDBC 5.5.3', 'java': 17,
               'mysqlImage': 'mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb',
               'mysqlJunit': counts, 'oldMySqlBytecodeClasses': len(frozen_classes), 'probes': probe_summary,
               'publicRepositoryConsumption': False, 'completeBehavioralCompatibility': False}
    (evidence / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-repository', required=True, type=Path)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        paths = [args.legacy_repository, args.repository, args.evidence_directory]
        if any(path.is_symlink() for path in paths):
            raise VerificationError('Repository/evidence roots must not be symlinks')
        legacy, repository, evidence = (path.resolve() for path in paths)
        if not legacy.is_dir() or not repository.is_dir():
            raise VerificationError('Both supplied repositories must exist')
        if evidence.exists() or not evidence.parent.is_dir():
            raise VerificationError('Choose a new evidence directory with an existing parent')
        if any(evidence == path or evidence.is_relative_to(path) or path.is_relative_to(evidence)
               for path in (legacy, repository)):
            raise VerificationError('Evidence and supplied repositories must be separate')
        result = verify(Path(__file__).resolve().parents[1], legacy, repository, evidence)
        print(json.dumps(result, indent=2))
        return 0
    except (VerificationError, OSError, ValueError, KeyError, ET.ParseError, subprocess.SubprocessError) as error:
        print(f'Public API migration verification failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
