#!/usr/bin/env python3
"""Execute the bounded A-24 Maven17/21 matrix against reviewed staged 0.2 bytes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
from urllib.parse import urlsplit


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


maven_support = sibling('a24_maven_support', 'verify-staged-maven-artifact-consumer.py')
network = sibling('a24_consumer_network', 'consumer_network_sandbox.py')
shared = maven_support.shared
mirror = maven_support.mirror
VerificationError = shared.VerificationError
REVIEWED_RECEIPT_SHA256 = 'ff4ad23aca357baa0a29f6ddac3a8b3708f1dbe62e0a73f200f84737449fdb41'
STAGED_SOURCE = '008e125a0648ed615842a572d60fd453698bb5aa'
BOUNDARY_CLASS = 'io.github.ym0506.routecontract.a24.A24JavaBoundary'
DEPENDENCY_RESOLVE = 'org.apache.maven.plugins:maven-dependency-plugin:3.11.0:resolve'
TEST_NAMES = {'loadedCoreAndAutoDiscoveredHookAreTheExpectedStagedJarBytes',
              'unchangedRealMySqlCaptureMatchesTheExistingReviewedSchemaTwoBaseline',
              'sameBusinessRowWithExpandedExecutionFailsAssertionsAndBothCliReportFormats'}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def inventory(directory):
    result = []
    for path in sorted(directory.rglob('*')):
        attributes = path.lstat()
        if stat.S_ISLNK(attributes.st_mode):
            raise VerificationError('Cache inventories reject symlinks')
        if path.is_file():
            result.append({'path': path.relative_to(directory).as_posix(),
                           'size': attributes.st_size, 'sha256': shared.sha256(path)})
        elif not path.is_dir():
            raise VerificationError('Cache inventories reject special files')
    return result


def freeze_cache(source, snapshot):
    if snapshot.exists() or snapshot.is_symlink():
        raise VerificationError('Frozen snapshot must start absent')
    before = inventory(source)
    shutil.copytree(source, snapshot)
    if inventory(snapshot) != before:
        raise VerificationError('Cache snapshot differs from the successful prime')
    for path in snapshot.rglob('*'):
        path.chmod(0o555 if path.is_dir() else 0o444)
    snapshot.chmod(0o555)
    return before


def clone_cache(snapshot, destination):
    if destination.exists() or destination.is_symlink():
        raise VerificationError('Disposable cache must start absent')
    shutil.copytree(snapshot, destination)
    for path in destination.rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
    destination.chmod(0o700)
    if inventory(snapshot) != inventory(destination):
        raise VerificationError('Disposable cache differs from the frozen prime')


def configure_consumer(root, destination, java_feature):
    if java_feature not in (17, 21):
        raise VerificationError('Only explicitly bounded Java 17 and 21 cells exist')
    maven_support.copy_consumer(root, destination)
    pom = destination / 'pom.xml'
    tree = ET.parse(pom)
    n = maven_support.N
    tree.getroot().find(n+'properties/'+n+'maven.compiler.release').text = str(java_feature)
    tree.getroot().find('.//'+n+'requireJavaVersion/'+n+'version').text = f'[{java_feature},{java_feature+1})'
    tree.getroot().find('.//'+n+'configuration/'+n+'release').text = str(java_feature)
    ET.register_namespace('', maven_support.POM_NS)
    ET.indent(tree)
    tree.write(pom, encoding='UTF-8', xml_declaration=True)
    probe = destination / 'src/main/java/io/github/ym0506/routecontract/a24/A24JavaBoundary.java'
    probe.parent.mkdir(parents=True)
    probe.write_text('''package io.github.ym0506.routecontract.a24;
public final class A24JavaBoundary {
    private A24JavaBoundary() { }
    public static void main(String[] args) {
        int expected = Integer.parseInt(args[0]);
        if (Runtime.version().feature() != expected) {
            throw new IllegalStateException("Unexpected Java runtime");
        }
        if (!"true".equals(System.getProperty("java.net.preferIPv4Stack"))) {
            throw new IllegalStateException("Trusted Java IPv4 property missing");
        }
        System.out.println("A24_JAVA_RUNTIME_VERIFIED feature=" + expected);
    }
}
''', encoding='utf-8')
    source = destination / 'src/test/java/io/github/ym0506/routecontract/consumer/StagedArtifactMySqlTest.java'
    source_text = source.read_text()
    if source_text.count(network.MYSQL_SOURCE_IMAGE) != 1:
        raise VerificationError('The bounded fixture must use the reviewed MySQL image')
    source.write_text(source_text.replace(network.MYSQL_SOURCE_IMAGE, network.MYSQL_IMAGE))
    network.install_pull_policy(destination)


def verify_failure(returncode, output, category, artifact):
    if category != 'graph' or returncode == 0 or 'BannedDependencies failed' not in output or artifact not in output:
        raise VerificationError(f'Expected specific {category} rejection for {artifact}')


def checksum_control(repository, corrupted_repository, receipt):
    """Independently bind one changed core JAR byte to reviewed bytes and sidecars."""
    candidates = [item for item in receipt['artifacts']
                  if item['module'] == 'routecontract-core' and item['name'].endswith('.jar')]
    if len(candidates) != 1:
        raise VerificationError('Checksum control requires exactly one reviewed core JAR')
    core = candidates[0]
    version = receipt['routeContractVersion']
    relative = f'{shared.GROUP_PATH}/routecontract-core/{version}/routecontract-core-{version}.jar'
    if core['relativePath'] != relative:
        raise VerificationError('Checksum control must target the exact reviewed core JAR coordinate')
    original_path, changed_path = repository/relative, corrupted_repository/relative
    original, changed = original_path.read_bytes(), changed_path.read_bytes()
    if hashlib.sha256(original).hexdigest() != core['sha256'] or len(original) != len(changed):
        raise VerificationError('Original JAR must match the reviewed receipt and retain its size')
    offsets = [index for index, (left, right) in enumerate(zip(original, changed)) if left != right]
    if len(offsets) != 1:
        raise VerificationError('Checksum control must change exactly one core JAR byte')
    original_inventory = inventory(repository)
    changed_inventory = inventory(corrupted_repository)
    if ([item for item in original_inventory if item['path'] != relative]
            != [item for item in changed_inventory if item['path'] != relative]):
        raise VerificationError('Checksum control must leave all other staged files and sidecars unchanged')
    digests = {}
    for algorithm in ('sha1', 'sha256', 'sha512', 'md5'):
        sidecar = original_path.with_name(original_path.name+'.'+algorithm)
        if sidecar.is_file():
            original_digest = hashlib.new(algorithm, original).hexdigest()
            changed_digest = hashlib.new(algorithm, changed).hexdigest()
            content = sidecar.read_bytes()
            if content.decode('ascii').strip() != original_digest:
                raise VerificationError('Original checksum sidecar does not describe the reviewed JAR')
            digests[algorithm] = {'expected': original_digest, 'actual': changed_digest,
                                  'sidecarPath': relative+'.'+algorithm,
                                  'sidecarSha256': hashlib.sha256(content).hexdigest()}
    if 'sha1' not in digests:
        raise VerificationError('The native Maven SHA-1 sidecar must be present')
    return {'path': relative, 'coordinate': f'io.github.ym0506.routecontract:routecontract-core:jar:{version}',
            'reviewedSha256': core['sha256'], 'corruptedSha256': hashlib.sha256(changed).hexdigest(),
            'size': len(original), 'changedBytes': 1, 'changedOffset': offsets[0],
            'digests': digests,
            'originalStagingInventorySha256': hashlib.sha256(json.dumps(original_inventory, sort_keys=True).encode()).hexdigest(),
            'corruptedStagingInventorySha256': hashlib.sha256(json.dumps(changed_inventory, sort_keys=True).encode()).hexdigest()}


def verify_checksum_failure(returncode, output, requests, command, url, control):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
            or url != f'http://127.0.0.1:{parsed.port}/'):
        raise VerificationError('Native checksum proof requires the exact controlled loopback endpoint')
    if (returncode == 0 or '[INFO] BUILD FAILURE' not in output.splitlines()
            or '--strict-checksums' not in command or DEPENDENCY_RESOLVE not in command
            or any(option in command for option in ('--lax-checksums', '-c'))):
        raise VerificationError('Checksum proof requires a failed native Maven strict dependency resolution')
    # Maven 3.9.14 identifies the exact GAV + repository base URL in the transfer
    # exception. Bind the complete error line to the precise GET path below.
    matches = []
    for algorithm, digests in control['digests'].items():
        message = (f"Could not transfer artifact {control['coordinate']} from/to {maven_support.MIRROR_ID} ({url}): "
                   f"Checksum validation failed, expected '{digests['expected']}' (REMOTE_EXTERNAL) "
                   f"but is actually '{digests['actual']}'")
        for line in output.splitlines():
            if re.fullmatch(r'\[ERROR\][ \t]*'+re.escape(message), line.rstrip()):
                matches.append((algorithm, line))
    if not matches or len({item[0] for item in matches}) != 1:
        raise VerificationError('Expected exact native core JAR transfer rejection with original/corrupted digests')
    algorithm = matches[0][0]
    selected = {}
    for name, relative in (('jar', control['path']), ('sidecar', control['digests'][algorithm]['sidecarPath'])):
        selected[name] = [item for item in requests if item == {
            'method': 'GET', 'route': 'staged', 'status': 200, 'path': relative}]
        if not selected[name]:
            raise VerificationError('Checksum proof requires finalized successful GETs for exact JAR and used sidecar')
    return {'case': 'checksum', 'rejection': 'MAVEN_STRICT_CHECKSUM', 'actualModifiedArtifact': True,
            'nativeExitCode': returncode, 'coordinate': control['coordinate'],
            'repositoryId': maven_support.MIRROR_ID, 'repositoryUrl': url,
            'requestedJarUrl': url+control['path'], 'algorithm': algorithm,
            'expectedDigest': control['digests'][algorithm]['expected'],
            'actualDigest': control['digests'][algorithm]['actual'],
            'reviewedSha256': control['reviewedSha256'], 'corruptedSha256': control['corruptedSha256'],
            'nativeRejectionLines': [item[1] for item in matches], 'successfulRequests': selected}


def evidence_path(value, root, repository):
    absolute = value.absolute()
    resolved = absolute.resolve(strict=False)
    if (absolute != resolved or resolved.exists() or resolved.is_symlink()
            or resolved.is_relative_to(root.resolve()) or root.resolve().is_relative_to(resolved)
            or resolved.is_relative_to(repository.resolve()) or repository.resolve().is_relative_to(resolved)):
        raise VerificationError('Supply a new canonical evidence directory outside source and staging')
    return resolved


def verify_junit_identity(suite):
    cases = suite.findall('testcase')
    name = 'io.github.ym0506.routecontract.consumer.StagedArtifactMySqlTest'
    if (suite.get('name') != name or len(cases) != 3
            or {case.get('name') for case in cases} != TEST_NAMES
            or any(case.get('classname') != name for case in cases)):
        raise VerificationError('Three distinct expected MySQL test identities are required')


def execute(command, cwd, environment, evidence, name, *, barrier=None, failure=None,
            collect_failure=False):
    if barrier is not None:
        if (environment.get('JAVA_TOOL_OPTIONS') != network.JAVA_IPV4_OPTION
                or environment['JAVA_HOME'] not in barrier.get('javaRuntimes', {})):
            raise VerificationError('Offline execution requires this exact JDK network control and trusted options')
        command = network.sandboxed(command, barrier)
    with (evidence / 'commands.jsonl').open('a', encoding='utf-8') as record:
        record.write(json.dumps({'name': name, 'argv': command, 'cwd': str(cwd),
                                 'JAVA_HOME': environment['JAVA_HOME'],
                                 'JAVA_TOOL_OPTIONS': environment['JAVA_TOOL_OPTIONS'],
                                 'startedAt': datetime.now(timezone.utc).isoformat()}) + '\n')
    log = evidence / (name + '.log')
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=cwd, env={**environment, 'MAVEN_BASEDIR': str(cwd)},
                                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                timeout=maven_support.TIMEOUT_SECONDS)
    text = log.read_text(encoding='utf-8', errors='replace')
    write_json(evidence / (name + '-exit.json'), {'exitCode': result.returncode})
    if failure:
        verify_failure(result.returncode, text, *failure)
    elif result.returncode != 0 and not collect_failure:
        raise VerificationError(f'{name} failed with exit {result.returncode}; inspect {log}')
    return text


def arguments(maven, settings, cache, private_home, runtime, adapter, receipt):
    result = [maven, '--batch-mode', '--no-transfer-progress', '--strict-checksums',
              '--settings', str(settings), '--global-settings', str(settings),
              f'-Dmaven.repo.local={cache}', f'-Duser.home={private_home}',
              f'-Pruntime-{runtime}', '-Dstyle.color=never']
    for module, name in [('routecontract-core', 'core'), (adapter, 'adapter')]:
        item = next(item for item in receipt['artifacts'] if item['module'] == module and item['name'].endswith('.jar'))
        result.append(f'-Droutecontract.{name}Sha256={item["sha256"]}')
    return result


def environment(java_home, private_home, *, docker_socket=None, images=None):
    result = network.controlled_environment(maven_support.clean_environment(java_home),
                                            docker_socket=docker_socket, images=images)
    result.update(HOME=str(private_home), DOCKER_CONFIG=str(private_home/'.docker'),
                  MAVEN_OPTS='-Duser.home=../home')
    return result


def verify_reports(consumer, runtime):
    reports = consumer / 'build/routecontract-consumer-evidence' / runtime
    approved = (consumer / 'src/test/resources/manifests' /
                f'find-paid-orders-by-user.shardingsphere-{runtime}.schema2.approved.json').read_bytes()
    if (reports/'reviewed-baseline.json').read_bytes() != approved:
        raise VerificationError('Reviewed baseline changed during the consumer')
    report = json.loads((reports/'review.json').read_text())
    rendered = (reports/'review.md').read_text()
    if (report['status'] != 'POLICY_VIOLATION' or report['strictExitCode'] != 1
            or {item['code'] for item in report['findings']} != {'RCM201', 'RCM202'}
            or any(marker not in rendered for marker in ('POLICY_VIOLATION', 'RCM201', 'RCM202'))):
        raise VerificationError('Both actual CLI report formats must prove the expected policy failure')
    for path in reports.iterdir():
        if path.is_file() and any(value in path.read_text() for value in
                                 ('SELECT', 't_order', 'PAID', 'user_id', 'ds_0', 'ds_1', 'staged-consumer-private-bind-39fa5e72')):
            raise VerificationError('Minimized evidence disclosed SQL, private bind data or raw aliases')
    return {'sameExpectedBusinessRow': True, 'attempts': [1, 2],
            'approvedBaselineUnchanged': True, 'privateBindAssertionPassed': True,
            'cliRegressionReturnCodes': {'markdown': 1, 'json': 1},
            'cliExecutionMode': 'in-process ManifestReviewCli.run assertions',
            'minimizedReportsVerified': True}


def positive(root, work, evidence, cache, settings, maven, java_home, java_feature,
             runtime, adapter, receipt, *, barrier=None, expected_images=None):
    consumer, home = work/'consumer', work/'home'
    home.mkdir(parents=True)
    configure_consumer(root, consumer, java_feature)
    docker_socket = network.local_docker_socket()
    images = network.inspect_local_images(docker_socket)
    write_json(evidence/'local-images-before.json', images)
    if expected_images is not None:
        network.require_same_images(expected_images, images)
    write_json(evidence/'image-reference-normalization.json', {
        'sourceReference': network.MYSQL_SOURCE_IMAGE, 'dockerReference': network.MYSQL_IMAGE,
        'sameImmutableDigest': True})
    env = environment(java_home, home, docker_socket=docker_socket, images=images)
    write_json(evidence/'controlled-environment.json', {
        key: value for key, value in env.items()
        if key.startswith('TESTCONTAINERS_') or key in ('JAVA_TOOL_OPTIONS', 'DOCKER_HOST',
                                                      'ROUTECONTRACT_A24_LOCAL_IMAGES')})
    args = arguments(maven, settings, cache, home, runtime, adapter, receipt)
    if barrier:
        args.append('--offline')
    try:
        toolchain = execute([maven, '--version'], consumer, env, evidence, 'toolchain', barrier=barrier)
        if f'Apache Maven {maven_support.MAVEN_VERSION} ' not in toolchain or not re.search(fr'Java version: {java_feature}[.,]', toolchain):
            raise VerificationError('Unexpected Maven or Java runtime')
        output = execute([*args, 'clean', 'verify'], consumer, env, evidence, 'maven', barrier=barrier)
        counts = shared.verify_junit(consumer/'target/surefire-reports'/shared.JUNIT_NAME)
        suite = ET.parse(consumer/'target/surefire-reports'/shared.JUNIT_NAME).getroot()
        verify_junit_identity(suite)
        actual_java = suite.find("./properties/property[@name='java.version']")
        if actual_java is None or not actual_java.get('value', '').startswith(str(java_feature)+'.'):
            raise VerificationError('The actual test JVM must match the bounded Java cell')
        ipv4 = suite.find("./properties/property[@name='java.net.preferIPv4Stack']")
        if ipv4 is None or ipv4.get('value') != 'true':
            raise VerificationError('Actual Surefire test JVM must inherit the trusted IPv4 property')
        policy = network.verify_pull_policy(output, images)
        after_images = network.inspect_local_images(docker_socket)
        write_json(evidence/'local-images-after.json', after_images)
        if after_images != images:
            raise VerificationError('Fixture local Docker image identities changed during execution')
        if f'ROUTECONTRACT_STAGED_SPLIT_MYSQL_VERIFIED version={runtime} baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2' not in output:
            raise VerificationError('Missing actual MySQL marker')
        graph = evidence/'resolved-graph.json'
        execute([*args, maven_support.DEPENDENCY_TREE, '-DoutputType=json', f'-DoutputFile={graph}'],
                consumer, env, evidence, 'graph', barrier=barrier)
        selected = maven_support.verify_tree(json.loads(graph.read_text()), runtime, adapter)
        maven_support.verify_origins(cache, adapter, receipt)
        classes = []
        for folder in ('classes', 'test-classes'):
            files = sorted((consumer/'target'/folder).rglob('*.class'))
            if not files:
                raise VerificationError('Main probe and test classes must both be compiled')
            for path in files:
                data = path.read_bytes()
                major = int.from_bytes(data[6:8], 'big')
                if data[:4] != b'\xca\xfe\xba\xbe' or major != java_feature+44:
                    raise VerificationError('Unexpected compiled classfile Java boundary')
                classes.append({'path': path.relative_to(consumer/'target').as_posix(), 'major': major,
                                'sha256': shared.sha256(path)})
        execute([str(java_home/'bin/java'), '-cp', str(consumer/'target/classes'), BOUNDARY_CLASS, str(java_feature)],
                consumer, env, evidence, 'java-boundary', barrier=barrier)
        result = {'javaFeature': java_feature, 'runtime': runtime, 'junit': counts, **selected,
                  'classfiles': classes, **verify_reports(consumer, runtime),
                  'containerControls': policy, 'localImageIdentitiesUnchanged': True,
                  'localImages': images,
                  'offline': bool(barrier), 'publicConsumption': False}
        write_json(evidence/'summary.json', result)
        return result
    finally:
        maven_support.retain_lane_evidence(consumer, cache, evidence)


def negative(root, cell, snapshot, repository, receipt, maven, java_home, feature, runtime, adapter, case):
    evidence = cell/case
    evidence.mkdir()
    work = evidence/'work'
    work.mkdir()
    consumer, home, cache = work/'consumer', work/'home', work/'repository'
    home.mkdir()
    configure_consumer(root, consumer, feature)
    clone_cache(snapshot, cache)
    env = environment(java_home, home)
    selected_repository = repository
    if case in ('checksum', 'wrong-origin'):
        # Discard first-party files only in this new disposable clone to force a real download.
        shutil.rmtree(cache/shared.GROUP_PATH)
    if case == 'checksum':
        selected_repository = work/'corrupt-staging'
        shutil.copytree(repository, selected_repository)
        core = next(item for item in receipt['artifacts'] if item['module']=='routecontract-core' and item['name'].endswith('.jar'))
        path = selected_repository/core['relativePath']
        data = bytearray(path.read_bytes())
        data[len(data)//2] ^= 1
        path.write_bytes(data)
        control = checksum_control(repository, selected_repository, receipt)
        write_json(evidence/'corruption.json', control)
    try:
        with mirror.serve_repository(selected_repository, evidence/'repository-requests.jsonl') as url:
            settings = evidence/'settings.xml'
            mirror_id = 'routecontract-unintended-a24' if case=='wrong-origin' else maven_support.MIRROR_ID
            maven_support.write_settings(settings, url, mirror_id)
            args = arguments(maven, settings, cache, home, runtime, adapter, receipt)
            if case == 'checksum':
                command = [*args, DEPENDENCY_RESOLVE]
                output = execute(command, consumer, env, evidence, 'rejection', collect_failure=True)
            elif case == 'wrong-origin':
                graph = evidence/'selected-graph.json'
                execute([*args, DEPENDENCY_RESOLVE, maven_support.DEPENDENCY_TREE, '-DoutputType=json', f'-DoutputFile={graph}'],
                        consumer, env, evidence, 'resolve')
                maven_support.verify_tree(json.loads(graph.read_text()), runtime, adapter)
                # First establish correct bytes and the actual unintended origin; then require
                # rejection solely because the expected controlled origin differs.
                maven_support.verify_origins(cache, adapter, receipt, mirror_id)
                try:
                    maven_support.verify_origins(cache, adapter, receipt)
                except VerificationError as error:
                    if 'does not identify the controlled mirror' not in str(error):
                        raise
                    result = {'case': case, 'rejection': 'UNEXPECTED_REPOSITORY_ORIGIN',
                              'correctReviewedBytes': True, 'actualOrigin': mirror_id,
                              'expectedOrigin': maven_support.MIRROR_ID}
                else:
                    raise VerificationError('Wrong actual repository origin was accepted')
            else:
                pom = consumer/'negative-pom.xml'
                artifact, version = maven_support.negative_pom(consumer/'pom.xml', pom, case, runtime)
                graph = evidence/'selected-graph.json'
                execute([*args, '--file', str(pom), maven_support.DEPENDENCY_TREE, '-DoutputType=json', f'-DoutputFile={graph}'],
                        consumer, env, evidence, 'graph')
                maven_support.verify_negative_selection(json.loads(graph.read_text()), case, runtime, artifact, version)
                execute([*args, '--file', str(pom), 'validate'], consumer, env, evidence, 'rejection',
                        failure=('graph', f'{artifact}:jar:{version}'))
                result = {'case': case, 'rejection': 'BannedDependencies', 'artifact': artifact,
                          'rejectedVersion': version, 'correctAnchorsRetained': case=='wrong-non-anchor'}
        if case == 'checksum':
            # Context shutdown joins all response threads and flushes the final GET
            # records before they can be used as evidence of a completed transfer.
            if checksum_control(repository, selected_repository, receipt) != control:
                raise VerificationError('Reviewed/corrupted staging changed during native checksum execution')
            requests = [json.loads(line) for line in (evidence/'repository-requests.jsonl').read_text().splitlines()]
            commands = [json.loads(line) for line in (evidence/'commands.jsonl').read_text().splitlines()]
            if len(commands) != 1 or commands[0]['name'] != 'rejection' or commands[0]['argv'] != command:
                raise VerificationError('Checksum proof must match the exact recorded native Maven invocation')
            settings_tree = ET.parse(settings).getroot()
            settings_ns = '{http://maven.apache.org/SETTINGS/1.2.0}'
            actual_mirror = settings_tree.findall(settings_ns+'mirrors/'+settings_ns+'mirror')
            if (len(actual_mirror) != 1 or actual_mirror[0].findtext(settings_ns+'id') != maven_support.MIRROR_ID
                    or actual_mirror[0].findtext(settings_ns+'url') != url
                    or actual_mirror[0].findtext(settings_ns+'mirrorOf') != '*'):
                raise VerificationError('The executed settings must identify only the controlled mirror')
            result = verify_checksum_failure(json.loads((evidence/'rejection-exit.json').read_text())['exitCode'],
                                             output, requests, command, url, control)
            result['evidenceSha256'] = {name: shared.sha256(evidence/name) for name in
                                       ('rejection.log', 'rejection-exit.json', 'repository-requests.jsonl',
                                        'commands.jsonl', 'settings.xml', 'corruption.json')}
        write_json(evidence/'summary.json', result)
        return result
    finally:
        maven_support.retain_lane_evidence(consumer, cache, evidence)


def cell(root, evidence, repository, receipt, maven, java_home, feature, runtime, barrier,
         *, positive_only=False):
    adapter = shared.LANES[runtime]
    directory = evidence/f'java-{feature}'/runtime
    directory.mkdir(parents=True)
    online = directory/'online'
    online.mkdir()
    cache = online/'work/repository'
    if cache.exists():
        raise VerificationError('Each online cell requires an absent cache')
    with mirror.serve_repository(repository, online/'repository-requests.jsonl') as url:
        settings = online/'settings.xml'
        maven_support.write_settings(settings, url)
        good = positive(root, online/'work', online, cache, settings, maven, java_home,
                        feature, runtime, adapter, receipt)
    # The online proxy is closed before the restricted process starts, preventing a
    # loopback proxy from silently fetching dependencies outside the process sandbox.
    closed_endpoint = network.require_closed_endpoint(url)
    write_json(directory/'closed-prime-endpoint.json', closed_endpoint)
    snapshot = directory/'frozen-primed-repository'
    before = freeze_cache(cache, snapshot)
    write_json(directory/'frozen-cache-inventory.json', before)
    offline = directory/'offline'
    offline.mkdir()
    offline_cache = offline/'work/repository'
    offline_cache.parent.mkdir()
    clone_cache(snapshot, offline_cache)
    offline_result = positive(root, offline/'work', offline, offline_cache, settings, maven,
                              java_home, feature, runtime, adapter, receipt, barrier=barrier,
                              expected_images=good['localImages'])
    if inventory(snapshot) != before:
        raise VerificationError('Immutable primed cache changed during offline verification')
    write_json(directory/'frozen-cache-after-offline.json', inventory(snapshot))
    rejected = [] if positive_only else [negative(root, directory, snapshot, repository, receipt, maven, java_home,
                         feature, runtime, adapter, case) for case in
                ('checksum', 'wrong-origin', 'wrong-runtime', 'wrong-non-anchor')]
    if inventory(snapshot) != before:
        raise VerificationError('Immutable primed cache changed during negative controls')
    shared.verify_receipt(repository, receipt)
    result = {'javaFeature': feature, 'runtime': runtime, 'online': good, 'offline': offline_result,
              'frozenCacheUnchanged': True, 'closedPrimeEndpoint': closed_endpoint,
              'negativeControls': rejected, 'complete': not positive_only,
              'diagnosticOnly': positive_only}
    write_json(directory/'summary.json', result)
    marker = 'A24_MAVEN_POSITIVE_DIAGNOSTIC_VERIFIED' if positive_only else 'A24_MAVEN_CELL_VERIFIED'
    print(f'{marker} java={feature} runtime={runtime} mysqlTests=6 negatives={len(rejected)}', flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--reviewed-receipt', type=Path, required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    parser.add_argument('--java17-home', type=Path, required=True)
    parser.add_argument('--java21-home', type=Path, required=True)
    parser.add_argument('--maven', required=True)
    parser.add_argument('--java-feature', action='append', type=int, choices=(17, 21))
    parser.add_argument('--runtime', action='append', choices=tuple(shared.LANES))
    parser.add_argument('--positive-only', action='store_true',
                        help='One-cell online/offline diagnostic only; never completes A-24')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    repository = args.repository.resolve(strict=True)
    evidence = evidence_path(args.evidence_directory, root, repository)
    receipt_path = args.reviewed_receipt.resolve(strict=True)
    if shared.sha256(receipt_path) != REVIEWED_RECEIPT_SHA256:
        raise VerificationError('The independently reviewed 008e125 receipt is required')
    receipt = json.loads(receipt_path.read_text())
    shared.verify_receipt(repository, receipt)
    maven = shutil.which(args.maven)
    if not maven:
        raise VerificationError('Exact Maven 3.9.14 is required')
    homes = {17: args.java17_home.resolve(strict=True), 21: args.java21_home.resolve(strict=True)}
    features, runtimes = args.java_feature or [17, 21], args.runtime or list(shared.LANES)
    if len(set(features)) != len(features) or len(set(runtimes)) != len(runtimes):
        raise VerificationError('Each requested cell must be unique')
    full_matrix = set(features)=={17, 21} and set(runtimes)==set(shared.LANES)
    if args.positive_only and len(features)*len(runtimes) != 1:
        raise VerificationError('Positive-only diagnostics require exactly one explicit Java/runtime cell')
    evidence.mkdir(parents=True, mode=0o700)
    shutil.copy2(receipt_path, evidence/'reviewed-staged-receipt.json')
    summary = {'formatVersion': 1, 'requirement': 'A-24', 'complete': False, 'requestedCellsComplete': False,
               'requestedCells': [{'javaFeature': feature, 'runtime': runtime} for feature in features for runtime in runtimes],
               'fullMavenMatrixRequested': full_matrix, 'cells': [],
               'diagnosticOnly': args.positive_only,
               'stagedSourceRevision': STAGED_SOURCE, 'reviewedReceiptSha256': REVIEWED_RECEIPT_SHA256,
               'harnessSha256': shared.sha256(Path(__file__)),
               'mirrorHelperSha256': shared.sha256(Path(mirror.__file__)),
               'publicConsumption': False, 'boundary': 'Local staged 0.2 bytes; exact synchronous non-batch MySQL fixture only'}
    try:
        barrier = network.prepare_barrier(evidence/'network', {feature: homes[feature] for feature in features})
        for feature in features:
            for runtime in runtimes:
                summary['cells'].append(cell(root, evidence, repository, receipt, maven, homes[feature], feature, runtime,
                                             barrier, positive_only=args.positive_only))
        summary['requestedCellsComplete'] = not args.positive_only
        summary['positiveDiagnosticsComplete'] = args.positive_only
        summary['complete'] = full_matrix and not args.positive_only
    finally:
        write_json(evidence/'summary.json', summary)
    marker = ('A24_MAVEN_POSITIVE_DIAGNOSTICS_ONLY' if args.positive_only else
              'A24_MAVEN_MATRIX_VERIFIED' if full_matrix else 'A24_MAVEN_REQUESTED_CELLS_VERIFIED')
    print(marker+' cells='+str(len(summary['cells'])), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, VerificationError, mirror.RepositoryError, network.NetworkBarrierError, subprocess.SubprocessError) as error:
        print('A24_MAVEN_FAILED: '+str(error), file=sys.stderr)
        raise SystemExit(1)
