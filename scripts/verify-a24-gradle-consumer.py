#!/usr/bin/env python3
"""Execute the staged Groovy/Kotlin Java-17 portion of ADR A-24 on macOS."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import consumer_network_sandbox as network
from public_split_artifacts import load_consumer_receipt


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


staged = load('a24_staged_helpers', 'verify-staged-split-artifact-consumer.py')
wrapper = load('a24_wrapper_helpers', 'verify-gradle-split-artifact-consumer.py')
legacy = load('a24_source_helpers', 'verify-gradle-legacy-artifact-consumer.py')
cache_support = load('a24_shared_cache_helpers', 'verify-a24-maven-consumer.py')
mirror = load('a24_http_repository', 'staged_maven_repository.py')
CASES = ('online', 'offline', 'bad-checksum', 'wrong-origin', 'origin-control',
         'wrong-anchor', 'wrong-non-anchor')
FIXTURES = {'groovy': 'staged-split-artifact-consumer', 'kotlin': 'staged-kotlin-artifact-consumer'}
RUNTIME_MARKER = 'A24_JAVA_TEST_RUNTIME_VERIFIED feature=17 ipv4=true'
ENVIRONMENT_PROBE = '''package io.github.ym0506.routecontract.a24;
public final class A24Environment {
    private A24Environment() { }
    public static void verify() {
        if (Runtime.version().feature() != 17
                || !"true".equals(System.getProperty("java.net.preferIPv4Stack"))
                || !System.getProperty("user.home").equals(System.getenv("ROUTECONTRACT_A24_PRIVATE_HOME"))) {
            throw new IllegalStateException("Actual A24 test JVM must be Java 17 with trusted IPv4");
        }
        System.out.println("A24_JAVA_TEST_RUNTIME_VERIFIED feature=17 ipv4=true");
    }
}
'''


class AcceptanceError(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def tree_inventory(directory):
    result = {}
    for path in sorted(Path(directory).rglob('*')):
        if path.is_symlink():
            raise AcceptanceError('Inventory cannot silently follow symlinks: ' + str(path))
        if path.is_file():
            result[str(path.relative_to(directory))] = {'sha256': sha(path), 'size': path.stat().st_size}
    return result


def source_snapshot(dsls):
    files = [Path(__file__), ROOT / 'scripts/consumer_network_sandbox.py',
             ROOT / 'scripts/public_split_artifacts.py',
             ROOT / 'scripts/verify-staged-split-artifact-consumer.py',
             ROOT / 'scripts/verify-gradle-split-artifact-consumer.py',
             ROOT / 'scripts/verify-gradle-legacy-artifact-consumer.py',
             ROOT / 'scripts/legacy_artifact_inputs.py',
             ROOT / 'scripts/verify-a24-maven-consumer.py',
             ROOT / 'scripts/verify-staged-maven-artifact-consumer.py',
             ROOT / 'scripts/staged_maven_repository.py', ROOT / 'gradlew',
             ROOT / 'gradle/verification-metadata.xml']
    directories = [ROOT / 'gradle/wrapper', ROOT / 'examples/staged-split-artifact-consumer/src',
                   ROOT / 'examples/staged-split-artifact-consumer/gradle-locks']
    for dsl in dsls:
        suffix = '.kts' if dsl == 'kotlin' else ''
        files += [ROOT / 'examples' / FIXTURES[dsl] / (name + suffix)
                  for name in ('build.gradle', 'settings.gradle')]
    for directory in directories:
        files.extend(path for path in directory.rglob('*') if path.is_file())
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(set(files))}


def copy_repository(source, receipt, destination):
    for pin in receipt['artifacts']:
        path = source / pin['relativePath']
        if path.is_symlink() or not path.is_file() or sha(path) != pin['sha256']:
            raise AcceptanceError('Staged input does not match the reviewed receipt: ' + pin['name'])
        target = destination / pin['relativePath']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    staged.verify_receipt(destination, receipt)


def prepare_case(directory, dsl, runtime, receipt, seed):
    directory.mkdir(parents=True)
    consumer = directory / 'consumer'
    consumer.mkdir()
    suffix = '.kts' if dsl == 'kotlin' else ''
    fixture = ROOT / 'examples' / FIXTURES[dsl]
    for name in ('build.gradle', 'settings.gradle'):
        shutil.copyfile(fixture / (name + suffix), consumer / (name + suffix))
    common = ROOT / 'examples/staged-split-artifact-consumer'
    shutil.copytree(common / 'src', consumer / 'src')
    test = consumer / 'src/test/java/io/github/ym0506/routecontract/consumer/StagedArtifactMySqlTest.java'
    text = test.read_text()
    anchor = 'static void createPhysicalSchemaAndDataSource() throws Exception {'
    if text.count(network.MYSQL_SOURCE_IMAGE) != 1 or text.count(anchor) != 1:
        raise AcceptanceError('Expected the bounded common fixture and immutable MySQL reference')
    text = text.replace(network.MYSQL_SOURCE_IMAGE, network.MYSQL_IMAGE)
    test.write_text(text.replace(anchor, anchor+'\n        io.github.ym0506.routecontract.a24.A24Environment.verify();'))
    network.install_pull_policy(consumer)
    probe = consumer / 'src/test/java/io/github/ym0506/routecontract/a24/A24Environment.java'
    probe.write_text(ENVIRONMENT_PROBE)
    (consumer / 'gradle.properties').write_text('org.gradle.dependency.verification.console=verbose\n')
    shutil.copyfile(common / 'gradle-locks' / (runtime + '.lockfile'), consumer / 'gradle.lockfile')
    staged.prepare_metadata(ROOT / 'gradle/verification-metadata.xml',
                            consumer / 'gradle/verification-metadata.xml', receipt)
    cache = directory / 'gradle-home'
    cache.mkdir()
    if seed is not None:
        wrapper.seed_wrapper_distribution(seed, cache)
    if (cache / 'caches').exists():
        raise AcceptanceError('Each initial case must have an absent dependency cache')
    return consumer, cache


def command_for(consumer, cache, repository, runtime, receipt, java_home, tasks):
    try:
        parsed = urlsplit(str(repository))
        valid = (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port
                 and str(repository) == f'http://127.0.0.1:{parsed.port}/')
    except ValueError:
        valid = False
    if not valid:
        raise AcceptanceError('Consumer commands require the controlled loopback HTTP repository URL')
    command = [str(ROOT / 'gradlew'), '--no-daemon', '--no-build-cache', '--no-configuration-cache',
               '--dependency-verification=strict', '--console=plain', '--max-workers=2',
               '--project-dir', str(consumer), '--project-cache-dir', str(consumer.parent / 'project-cache'),
               '-Dorg.gradle.java.installations.auto-download=false',
               '-Dorg.gradle.java.installations.auto-detect=false',
               f'-Dorg.gradle.java.installations.paths={java_home}',
               f'-ProutecontractRuntime={runtime}', f'-ProutecontractRepositoryUrl={repository}',
               '-Porg.gradle.dependency.verification.console=verbose']
    for module in ('routecontract-core', staged.LANES[runtime]):
        pin = next(p for p in receipt['artifacts'] if p['module'] == module and p['name'].endswith('.jar'))
        command.append(f'-ProutecontractSha256.{module}={pin["sha256"]}')
    return command + list(tasks)


def execute(directory, command, cache, java_home, initial_cache, barrier=None, images=None):
    home = directory / 'home'
    home.mkdir(exist_ok=True)
    environment = network.controlled_environment(wrapper.clean_environment(java_home, cache),
                                                 docker_socket=network.local_docker_socket(), images=images)
    environment.update(HOME=str(home), DOCKER_CONFIG=str(home/'.docker'),
                       ROUTECONTRACT_A24_PRIVATE_HOME=str(home))
    environment.pop('GRADLE_RO_DEP_CACHE', None)
    if barrier and str(java_home) not in barrier.get('javaRuntimes', {}):
        raise AcceptanceError('Offline execution requires the exact selected JDK kernel network proof')
    command = [command[0], '-Duser.home='+str(home), *command[1:]]
    actual = network.sandboxed(command, barrier) if barrier else command
    write_json(directory / 'command.json', {'argv': actual, 'cwd': str(directory / 'consumer'),
               'JAVA_HOME': str(java_home), 'GRADLE_USER_HOME': str(cache),
               'initialDependencyCache': initial_cache, 'externalNetworkDeniedByOS': bool(barrier),
               'JAVA_TOOL_OPTIONS': environment['JAVA_TOOL_OPTIONS'],
               'TESTCONTAINERS_PULL_POLICY': environment.get('TESTCONTAINERS_PULL_POLICY'),
               'sharedReadOnlyDependencyCacheRemoved': True})
    with (directory / 'gradle.log').open('w') as log:
        result = subprocess.run(actual, cwd=directory / 'consumer', env=environment,
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                timeout=1200, check=False)
    write_json(directory/'exit.json', {'exitCode': result.returncode})
    return result.returncode, (directory / 'gradle.log').read_text(errors='replace')


def verified_first_party(consumer, runtime, receipt):
    path = consumer / 'build/routecontract-consumer-evidence/resolved-first-party.json'
    first_party = json.loads(path.read_text())
    if isinstance(first_party, list):
        scopes = {'testCompileClasspath': 'compile', 'testRuntimeClasspath': 'runtime'}
        if len(first_party) != 4 or any(p.get('configuration') not in scopes for p in first_party):
            raise AcceptanceError('Kotlin first-party evidence must cover exactly both classpaths')
        first_party = {scope: [{k: v for k, v in p.items() if k != 'configuration'}
                              for p in first_party if p['configuration'] == configuration]
                       for configuration, scope in scopes.items()}
    if not isinstance(first_party, dict) or set(first_party) != {'compile', 'runtime'}:
        raise AcceptanceError('First-party evidence must describe compile and runtime classpaths')
    expected = {p['module']: p for p in receipt['artifacts']
                if p['name'].endswith('.jar') and p['module'] in ('routecontract-core', staged.LANES[runtime])}
    for scope in ('compile', 'runtime'):
        actual = first_party[scope]
        if len(actual) != 2 or len({p['coordinate'] for p in actual}) != 2:
            raise AcceptanceError('Both compile and runtime must contain exactly two first-party JARs')
        for item in actual:
            coordinate = item['coordinate'].split(':')
            if len(coordinate) != 3 or coordinate[0] != staged.GROUP or coordinate[2] != '0.2.0':
                raise AcceptanceError('Unexpected first-party coordinate')
            pin = expected[coordinate[1]]
            if item['sha256'] != pin['sha256'] or item['name'] != pin['name']:
                raise AcceptanceError('Selected first-party bytes do not match reviewed pins')
    return first_party


def positive_evidence(consumer, runtime, receipt, output, images):
    markers = [f'ROUTECONTRACT_STAGED_GRAPH_VERIFIED version={runtime} artifacts=2 ',
               f'ROUTECONTRACT_STAGED_SPLIT_MYSQL_VERIFIED version={runtime} baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2']
    if any(output.count(marker) != 1 for marker in markers):
        raise AcceptanceError('Positive consumer omitted a unique graph/MySQL marker')
    counts = staged.verify_junit(consumer / 'build/test-results/test' / staged.JUNIT_NAME)
    suite = ET.parse(consumer / 'build/test-results/test' / staged.JUNIT_NAME).getroot()
    cases = suite.findall('testcase')
    expected_class = 'io.github.ym0506.routecontract.consumer.StagedArtifactMySqlTest'
    if (suite.get('name') != expected_class or len(cases) != 3
            or {case.get('name', '').removesuffix('()') for case in cases} != cache_support.TEST_NAMES
            or any(case.get('classname') != expected_class for case in cases)):
        raise AcceptanceError('Expected three distinct real representative MySQL tests')
    test_output = suite.findtext('system-out', '')
    if test_output.count(RUNTIME_MARKER) != 1:
        raise AcceptanceError('Actual test JVM must verify Java 17 and trusted IPv4')
    container_controls = network.verify_pull_policy(test_output, images)
    compiled = sorted((consumer / 'build/classes/java/test').rglob('*.class'))
    if not compiled or any(path.read_bytes()[:4] != b'\xca\xfe\xba\xbe'
                           or int.from_bytes(path.read_bytes()[6:8], 'big') != 61 for path in compiled):
        raise AcceptanceError('Compiled fixture classes must target Java 17')
    reports = consumer / 'build/routecontract-consumer-evidence'
    graph = (reports / 'resolved-graph.txt').read_text().splitlines()
    ss = [c for c in graph if c.startswith('org.apache.shardingsphere:')]
    if len(ss) != {'5.5.2': 122, '5.5.3': 75}[runtime] or any(c.split(':')[-1] != runtime for c in ss):
        raise AcceptanceError('Selected ShardingSphere closure is not exact')
    first_party = verified_first_party(consumer, runtime, receipt)
    return {'junit': counts, 'shardingSphereComponentCount': len(ss),
            'firstParty': first_party, 'reportInventory': tree_inventory(reports),
            'actualJavaFeature': 17, 'classfileMajor': 61, 'containerControls': container_controls,
            'businessAndReports': cache_support.verify_reports(consumer, runtime)}


@contextmanager
def repository_server(repository, log):
    requests = []
    try:
        with mirror.serve_repository(repository, log) as url:
            yield url, requests
    finally:
        if log.is_file():
            requests.extend(json.loads(line) for line in log.read_text().splitlines())


def decoy_init(path, url):
    # URL is produced by our loopback listener, never supplied shell/source text.
    path.write_text("allprojects { afterEvaluate { repositories { maven { name = 'unintendedDecoy'; "
                    + "url = uri('" + url + "'); allowInsecureProtocol = true; "
                    + "metadataSources { gradleMetadata(); mavenPom() }; "
                    + "content { includeGroup 'io.github.ym0506.routecontract' } } } } }\n")


def disable_exclusive_group(consumer, dsl):
    build = consumer / ('build.gradle.kts' if dsl == 'kotlin' else 'build.gradle')
    original = build.read_text()
    old = 'includeGroup(routeGroup)' if dsl == 'kotlin' else 'includeGroup routeGroup'
    new = ('includeGroup("io.github.ym0506.routecontract.disabled-origin-control")' if dsl == 'kotlin'
           else "includeGroup 'io.github.ym0506.routecontract.disabled-origin-control'")
    if original.count(old) != 1:
        raise AcceptanceError('Cannot identify the exact exclusive-origin control mutation')
    build.write_text(original.replace(old, new))
    return {'originalBuildSha256': hashlib.sha256(original.encode()).hexdigest(),
            'controlBuildSha256': sha(build), 'mutation': 'reserve an unrelated group instead of RouteContract'}


def core_pin(receipt):
    return next(pin for pin in receipt['artifacts']
                if pin['module'] == 'routecontract-core' and pin['name'].endswith('.jar'))


def corrupt_core_checksum(consumer, receipt=None):
    path = consumer / 'gradle/verification-metadata.xml'
    tree = ET.parse(path)
    ns = '{' + staged.NAMESPACE + '}'
    component = next(c for c in tree.getroot().find(ns + 'components')
                     if c.get('group') == staged.GROUP and c.get('name') == 'routecontract-core')
    jar = next(a for a in component if a.get('name') == 'routecontract-core-0.2.0.jar')
    pins = list(jar)
    if len(pins) != 1 or pins[0].tag != ns + 'sha256':
        raise AcceptanceError('Expected one reviewed SHA256 for the checksum-negative payload')
    original = path.read_bytes()
    actual = pins[0].get('value')
    if receipt is not None and actual != core_pin(receipt)['sha256']:
        raise AcceptanceError('The original trust pin must match the independently reviewed core JAR')
    before = { (c.get('group'), c.get('name'), c.get('version'), a.get('name')): ET.tostring(a)
              for c in tree.getroot().find(ns+'components') for a in c }
    pins[0].set('value', '0' * 64)
    tree.write(path, encoding='utf-8', xml_declaration=True)
    after_tree = ET.parse(path)
    after = { (c.get('group'), c.get('name'), c.get('version'), a.get('name')): ET.tostring(a)
             for c in after_tree.getroot().find(ns+'components') for a in c }
    target = (staged.GROUP, 'routecontract-core', '0.2.0', 'routecontract-core-0.2.0.jar')
    if set(before) != set(after) or [key for key in before if before[key] != after[key]] != [target]:
        raise AcceptanceError('Checksum negative may alter only the single core JAR trust pin')
    (consumer.parent/'verification-metadata.original.xml').write_bytes(original)
    return {'artifact': target[-1], 'coordinate': f'{staged.GROUP}:routecontract-core:0.2.0',
            'incorrectExpectedSha256': '0'*64, 'reviewedActualSha256': actual,
            'originalMetadataSha256': hashlib.sha256(original).hexdigest(),
            'mutatedMetadataSha256': sha(path)}


def successful_gets(requests, relative):
    return [row for row in requests if row == {'method': 'GET', 'path': relative,
                                               'route': 'staged', 'status': 200}]


def verify_checksum_negative(code, output, requests, url, receipt, mutation, consumer):
    pin = core_pin(receipt)
    message = (f"On artifact {pin['name']} ({staged.GROUP}:routecontract-core:0.2.0) "
               "in repository 'reviewedStaging': expected a 'sha256' checksum of '"+'0'*64+
               f"' but was '{pin['sha256']}'")
    # The Gradle verbose renderer may indent/wrap text; permit whitespace only
    # between native tokens, never unrelated artifact/hash text in other sections.
    pattern = r'\s+'.join(re.escape(token) for token in message.split())
    match = re.search(pattern, output)
    if (code == 0 or 'Dependency verification failed for' not in output or 'BUILD FAILED' not in output
            or match is None or mutation['reviewedActualSha256'] != pin['sha256']
            or mutation['incorrectExpectedSha256'] != '0'*64
            or sha(consumer/'gradle/verification-metadata.xml') != mutation['mutatedMetadataSha256']):
        raise AcceptanceError('Expected exact native Gradle core JAR/repository/expected/actual checksum failure')
    gets = successful_gets(requests, pin['relativePath'])
    if not gets:
        raise AcceptanceError('Checksum control requires the exact reviewed core JAR GET 200')
    cached = list((consumer.parent/'gradle-home/caches/modules-2/files-2.1'/staged.GROUP/
                   'routecontract-core/0.2.0').glob('*/'+pin['name']))
    if not cached or any(sha(path) != pin['sha256'] for path in cached):
        raise AcceptanceError('Native verification must have downloaded the reviewed core JAR bytes')
    return {'result': 'NATIVE_CHECKSUM_REJECTED', 'mutation': mutation,
            'requestedJarUrl': url+pin['relativePath'], 'successfulJarGets': gets,
            'nativeFailureSection': match.group(), 'cachedCoreSha256': pin['sha256']}


def verify_origin_negative(case, code, output, approved_requests, decoy_requests,
                           approved_url, decoy_url, consumer, runtime, receipt):
    selected = [pin for pin in receipt['artifacts'] if pin['module'] in
                ('routecontract-core', staged.LANES[runtime]) and pin['name'].endswith('.jar')]
    missing = [f"Could not find {staged.GROUP}:{pin['module']}:0.2.0." for pin in selected]
    if case == 'wrong-origin':
        bad_failures = ('Dependency verification failed', 'Could not GET', 'Could not HEAD',
                        'status code', 'No cached version')
        unresolved = set(re.findall(r'Could not (?:find|resolve) ([A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.+-]+)\.', output))
        expected_missing = {f'{staged.GROUP}:{pin["module"]}:0.2.0' for pin in selected}
        if (code == 0 or decoy_requests or any(marker not in output for marker in missing)
                or any(marker in output for marker in bad_failures) or unresolved != expected_missing):
            raise AcceptanceError('Protected origin must reject both exact first-party coordinates without decoy access')
        for pin in selected:
            prefix = pin['relativePath'].removesuffix('.jar')
            if not any(row.get('route') == 'staged' and row.get('status') == 404
                       and row.get('method') in ('GET', 'HEAD') and row.get('path') in
                       (prefix+'.pom', prefix+'.module') for row in approved_requests):
                raise AcceptanceError('Protected origin omitted the exact approved endpoint missing-artifact lookup')
        return {'result': 'WRONG_ORIGIN_REJECTED', 'approvedUrl': approved_url, 'decoyUrl': decoy_url,
                'approvedMissingRequests': approved_requests, 'decoyRequests': []}
    if code != 0 or output.count(f'ROUTECONTRACT_STAGED_GRAPH_VERIFIED version={runtime} artifacts=2 ') != 1:
        raise AcceptanceError('Disabled-policy origin control must resolve its actual exact graph')
    for pin in selected:
        if not successful_gets(decoy_requests, pin['relativePath']):
            raise AcceptanceError('Origin control requires actual GET 200 for both core and adapter JARs')
    return {'result': 'UNPROTECTED_ORIGIN_CONTROL_RESOLVED', 'approvedUrl': approved_url,
            'decoyUrl': decoy_url, 'decoyRequests': decoy_requests,
            'firstParty': verified_first_party(consumer, runtime, receipt)}


def verify_version_negative(case, code, output, consumer, runtime):
    other = '5.5.3' if runtime == '5.5.2' else '5.5.2'
    module = 'shardingsphere-infra-executor' if case == 'wrong-anchor' else 'shardingsphere-infra-common'
    wrong = f'org.apache.shardingsphere:{module}:{other}'
    marker = 'WRONG_ANCHOR_REJECTED' if case == 'wrong-anchor' else 'WRONG_NON_ANCHOR_REJECTED'
    if code != 0 or output.count(f'ROUTECONTRACT_STAGED_{marker} version={runtime} ') != 1:
        raise AcceptanceError('Exact runtime negative did not finish its actual rejection task')
    path = consumer/'build/routecontract-consumer-evidence'/(case+'.json')
    report = json.loads(path.read_text())
    causal = '\n'.join(report.get('failureMessages', []))
    expected_policy = f'RC_STAGED_RUNTIME_REJECTED: expected {runtime}; requested {wrong}'
    unresolved_coordinates = set(re.findall(
        r'Could not (?:find|resolve) ([A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.+-]+)\.', causal))
    policy_lines = [line.strip() for line in causal.splitlines() if 'RC_STAGED_RUNTIME_REJECTED' in line]
    expected_adapter = f'{staged.GROUP}:{staged.LANES[runtime]}:0.2.0'
    if (report.get('runtime') != runtime or report.get('requestedWrongCoordinate') != wrong
            or report.get('actualUnresolvedSelector') != wrong or expected_policy not in causal
            or f'Could not resolve {wrong}' not in causal
            or unresolved_coordinates != {wrong} or not policy_lines
            or any(line != expected_policy for line in policy_lines)
            or 'Could not find ' in causal
            or report.get('selectedAdapter') != expected_adapter
            or any(marker in causal for marker in ('Could not GET', 'Could not HEAD', 'status code',
                                                   'Dependency verification failed', 'No cached version'))):
        raise AcceptanceError('Runtime policy evidence is not bound to the actual injected wrong selector')
    if case == 'wrong-non-anchor':
        anchors = ['shardingsphere-infra-executor', 'shardingsphere-infra-spi',
                   'shardingsphere-infra-database-core' if runtime == '5.5.2' else 'shardingsphere-database-connector-core']
        expected = sorted('org.apache.shardingsphere:'+name+':'+runtime for name in anchors)
        if sorted(report.get('correctAnchors', [])) != expected:
            raise AcceptanceError('Wrong non-anchor must retain all three exact selected runtime anchors')
    return {'result': 'EXACT_RUNTIME_POLICY_REJECTED', 'rejectionReportSha256': sha(path),
            'observedPolicyRejection': report}


def run_profile(evidence, dsl, runtime, selected, repository, receipt, seed, java_home, barrier):
    profile = evidence / f'{dsl}-{runtime}'
    profile.mkdir()
    results, online, frozen_inventory = [], None, None
    docker_socket = network.local_docker_socket()
    for case in CASES:
        if case not in selected:
            continue
        directory = profile / case
        consumer, cache = prepare_case(directory, dsl, runtime, receipt, seed)
        tasks = ['clean', 'test', 'verifySelectedGraph']
        initial_cache = 'absent; checksum-pinned wrapper distribution only'
        restricted = barrier if case == 'offline' else None
        info, requests, images = {}, [], None
        if case == 'offline':
            if online is None:
                raise AcceptanceError("Offline requires this profile's own successful positive prime")
            shutil.rmtree(cache)
            cache_support.clone_cache(profile/'frozen-prime-cache', cache)
            if tree_inventory(cache) != frozen_inventory:
                raise AcceptanceError('Offline cache differs from this profile frozen prime')
            tasks = ['--offline', *tasks]
            initial_cache = 'exact disposable copy of immutable successful positive-prime snapshot'
        if case in ('online', 'offline'):
            images = network.inspect_local_images(docker_socket)
            write_json(directory/'local-images-before.json', images)
            if online is not None:
                network.require_same_images(online['localImages'], images)
            info['localImages'] = images
            info['imageReferenceNormalization'] = {'source': network.MYSQL_SOURCE_IMAGE,
                                                   'immutableDockerReference': network.MYSQL_IMAGE}
        elif case in ('wrong-anchor', 'wrong-non-anchor'):
            tasks = ['verifyWrongAnchor' if case == 'wrong-anchor' else 'verifyWrongNonAnchor']
        elif case == 'bad-checksum':
            mutation = corrupt_core_checksum(consumer, receipt)
            write_json(directory/'checksum-mutation.json', mutation)
            tasks = ['verifySelectedGraph']
        if case in ('wrong-origin', 'origin-control'):
            empty = directory/'empty-reviewed-repository'
            empty.mkdir()
            if case == 'origin-control':
                info['disabledPolicyControl'] = disable_exclusive_group(consumer, dsl)
            with repository_server(empty, directory/'approved-requests.jsonl') as (approved_url, approved_requests):
                with repository_server(repository, directory/'decoy-requests.jsonl') as (decoy_url, decoy_requests):
                    init = directory/'decoy.init.gradle'
                    decoy_init(init, decoy_url)
                    command = command_for(consumer, cache, approved_url, runtime, receipt, java_home,
                                          ['--init-script', str(init), 'verifySelectedGraph'])
                    code, output = execute(directory, command, cache, java_home, initial_cache)
            info.update(verify_origin_negative(case, code, output, approved_requests, decoy_requests,
                                               approved_url, decoy_url, consumer, runtime, receipt))
            info['requestEvidenceSha256'] = {name: sha(directory/name) for name in
                                             ('approved-requests.jsonl', 'decoy-requests.jsonl')}
        else:
            if case == 'offline':
                url = online['repositoryUrl']
                info['closedPrimeEndpoint'] = network.require_closed_endpoint(url)
                command = command_for(consumer, cache, url, runtime, receipt, java_home, tasks)
                code, output = execute(directory, command, cache, java_home, initial_cache, restricted, images)
            else:
                with repository_server(repository, directory/'repository-requests.jsonl') as (url, requests):
                    command = command_for(consumer, cache, url, runtime, receipt, java_home, tasks)
                    code, output = execute(directory, command, cache, java_home, initial_cache, images=images)
                info['repositoryRequests'] = requests
                info['requestEvidenceSha256'] = sha(directory/'repository-requests.jsonl')
            info['repositoryUrl'] = url
            if case in ('online', 'offline'):
                after_images = network.inspect_local_images(docker_socket)
                write_json(directory/'local-images-after.json', after_images)
                network.require_same_images(images, after_images)
                if code != 0:
                    raise AcceptanceError(f'{dsl}/{runtime}/{case} positive command failed; inspect retained log')
                info.update(positive_evidence(consumer, runtime, receipt, output, images))
                info['result'] = 'MYSQL_AND_REPORTS_VERIFIED'
                if case == 'online':
                    info['closedPrimeEndpoint'] = network.require_closed_endpoint(url)
                    cache_support.freeze_cache(cache, profile/'frozen-prime-cache')
                    frozen_inventory = tree_inventory(profile/'frozen-prime-cache')
                    write_json(profile/'frozen-prime-inventory.json', frozen_inventory)
                    online = info.copy()
                elif (info['firstParty'] != online['firstParty']
                      or info['reportInventory'] != online['reportInventory']):
                    raise AcceptanceError('Offline selected artifacts/reports differ from the successful prime')
            elif case == 'bad-checksum':
                info.update(verify_checksum_negative(code, output, requests, url, receipt, mutation, consumer))
            else:
                info.update(verify_version_negative(case, code, output, consumer, runtime))
        if case not in ('online', 'offline') and any((consumer/path).exists() for path in
                ('build/test-results/test', 'build/classes/java')):
            raise AcceptanceError('A rejection/control unexpectedly compiled or ran consumer tests')
        if frozen_inventory is not None and tree_inventory(profile/'frozen-prime-cache') != frozen_inventory:
            raise AcceptanceError('Preserved positive-prime cache changed')
        staged.verify_receipt(repository, receipt)
        info.update(case=case, profile=dsl, runtime=runtime, commandExitCode=code,
                    logSha256=sha(directory/'gradle.log'), commandSha256=sha(directory/'command.json'))
        write_json(directory/'result.json', info)
        results.append(info)
        write_json(profile/'progress.json', results)
        print(f'ROUTECONTRACT_A24_GRADLE_CASE_VERIFIED profile={dsl} runtime={runtime} case={case}', flush=True)
    return results


def selected_plan(dsls, runtimes, cases):
    for values in (dsls, runtimes, cases):
        if len(values) != len(set(values)):
            raise AcceptanceError('Duplicate requested profiles/runtime/cases are not a distinct plan')
    selected = set(cases)
    if 'offline' in selected:
        selected.add('online')
    if 'wrong-origin' in selected:
        selected.add('origin-control')
    return [{'profile': dsl, 'runtime': runtime, 'case': case}
            for dsl in sorted(dsls) for runtime in sorted(runtimes) for case in CASES if case in selected]


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--staged-receipt', type=Path, required=True)
    parser.add_argument('--staged-receipt-sha256', required=True)
    parser.add_argument('--staged-source-revision', required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--gradle-distribution-zip', type=Path, required=True)
    parser.add_argument('--dsl', action='append', choices=FIXTURES)
    parser.add_argument('--runtime', action='append', choices=staged.LANES)
    parser.add_argument('--case', action='append', choices=CASES, dest='cases')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--expected-input-manifest', type=Path,
                        help='Previously reviewed fixture-inputs.json; reject any changed source before execution')
    args = parser.parse_args()
    plan = selected_plan(args.dsl or list(FIXTURES), args.runtime or list(staged.LANES), args.cases or list(CASES))
    dsls = sorted({item['profile'] for item in plan})
    runtimes = sorted({item['runtime'] for item in plan})
    cases = {item['case'] for item in plan}
    complete = dsls == sorted(FIXTURES) and runtimes == sorted(staged.LANES) and cases == set(CASES)
    evidence = cache_support.evidence_path(args.evidence_directory, ROOT, args.repository)
    evidence.mkdir(parents=True, mode=0o700)
    try:
        inputs = source_snapshot(dsls)
        if args.expected_input_manifest and json.loads(args.expected_input_manifest.read_text()) != inputs:
            raise AcceptanceError('Current fixtures/helpers differ from the reviewed input manifest')
        binding = legacy.source_binding(args.staged_source_revision)
        receipt_bytes = args.staged_receipt.read_bytes()
        if (not re.fullmatch(r'[0-9a-f]{64}', args.staged_receipt_sha256)
                or hashlib.sha256(receipt_bytes).hexdigest() != args.staged_receipt_sha256):
            raise AcceptanceError('Staging receipt does not match the separately reviewed SHA-256')
        receipt = load_consumer_receipt(args.staged_receipt)
        if receipt['routeContractVersion'] != '0.2.0':
            raise AcceptanceError('This staged gate is scoped to reviewed 0.2.0 bytes')
        write_json(evidence / 'fixture-inputs.json', inputs)
        write_json(evidence / 'plan.json', plan)
        write_json(evidence / 'source-binding.json', binding)
        (evidence / 'staged-receipt.json').write_bytes(receipt_bytes)
        repository = evidence / 'verified-staging'
        copy_repository(args.repository.resolve(), receipt, repository)
        java_home = args.java_home.resolve()
        wrapper.verify_toolchain(ROOT, java_home)
        seed = evidence / 'wrapper-seed'
        seed.mkdir()
        legacy.seed_distribution_zip(args.gradle_distribution_zip, seed)
        if args.prepare_only:
            for item in plan:
                directory = evidence/'prepared'/item['profile']/item['runtime']/item['case']
                consumer, _cache = prepare_case(directory, item['profile'], item['runtime'], receipt, None)
                if item['case'] == 'bad-checksum':
                    corrupt_core_checksum(consumer, receipt)
                elif item['case'] == 'origin-control':
                    disable_exclusive_group(consumer, item['profile'])
            if (source_snapshot(dsls) != inputs or legacy.source_binding(args.staged_source_revision) != binding
                    or args.staged_receipt.read_bytes() != receipt_bytes):
                raise AcceptanceError('Reviewed source, fixture or receipt changed during preparation')
            write_json(evidence/'summary.json', {'status': 'PREPARED_ONLY', 'completeGradleA24Matrix': False,
                       'executedCaseCount': 0, 'preparedCaseCount': len(plan), 'requiredGradleCaseCount': 28,
                       'stagedReceiptSha256': args.staged_receipt_sha256})
            return
        bootstrap_home = evidence/'bootstrap-home'
        bootstrap_home.mkdir()
        bootstrap_environment = network.controlled_environment(wrapper.clean_environment(java_home, seed))
        bootstrap_environment.update(HOME=str(bootstrap_home), DOCKER_CONFIG=str(bootstrap_home/'.docker'))
        output = subprocess.check_output([str(ROOT/'gradlew'), '-Duser.home='+str(bootstrap_home),
                                          '--no-daemon', '--version'], cwd=ROOT,
                 env=bootstrap_environment, text=True, stderr=subprocess.STDOUT, timeout=60)
        (evidence / 'toolchain.txt').write_text(output)
        if (f'Gradle {wrapper.EXPECTED_GRADLE_VERSION}' not in output
                or re.search(r'Launcher JVM:\s+17(?:[.]|\s)', output) is None):
            raise AcceptanceError('The verified wrapper seed must actually launch Gradle 8.14.4 on Java 17')
        results = []
        barrier = network.prepare_barrier(evidence/'network-proof', {17: java_home}) if 'offline' in cases else None
        for dsl in dsls:
            for runtime in runtimes:
                results.extend(run_profile(evidence, dsl, runtime, cases, repository, receipt, seed, java_home, barrier))
        if [{key: item[key] for key in ('profile', 'runtime', 'case')} for item in results] != plan:
            raise AcceptanceError('Completed case identities do not match the finite requested plan')
        staged.verify_receipt(repository, receipt)
        if (source_snapshot(dsls) != inputs or legacy.source_binding(args.staged_source_revision) != binding
                or args.staged_receipt.read_bytes() != receipt_bytes):
            raise AcceptanceError('Reviewed source, fixture or receipt changed during execution')
        summary = {'formatVersion': 1, 'status': 'VERIFIED' if complete else 'PARTIAL_VERIFIED',
                   'completeGradleA24Matrix': complete, 'mavenA24Verified': False,
                   'caseCount': len(results), 'requiredGradleCaseCount': 28,
                   'stagedReceiptSha256': hashlib.sha256(receipt_bytes).hexdigest(),
                   'sourceBinding': binding, 'results': results,
                   'boundary': 'Local macOS Gradle Groovy/Kotlin Java17 staged-byte acceptance; no public0.2 or adoption claim.'}
        write_json(evidence / 'summary.json', summary)
        print(f'ROUTECONTRACT_A24_GRADLE_{summary["status"]} cases={len(results)}', flush=True)
    except Exception as error:
        write_json(evidence / 'failure.json', {'status': 'FAILED', 'error': str(error), 'completeGradleA24Matrix': False})
        raise


if __name__ == '__main__':
    main()
