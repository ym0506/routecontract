#!/usr/bin/env python3
"""Prepare or explicitly execute ten remaining A-15/A-17 boundary cases.

Preparation is the default. It never resolves dependencies or runs the older
staged candidate merely to obtain a passing result before a pending guard fix.
"""
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
import subprocess
import sys
import signal
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples/dual-resolver-boundary-consumer'
GROUP = 'io.github.ym0506.routecontract'
SS = 'org.apache.shardingsphere'
VERSION = '0.2.0'
ADAPTERS = {'5.5.2': 'routecontract-shardingsphere-5.5.2',
            '5.5.3': 'routecontract-shardingsphere-5.5'}
MIRROR_ID = 'routecontract-boundary-staging'
GUARD_CLASS = 'io.github.ym0506.routecontract.boundary.OppositeRuntimeGuardProbe'
GUARD_PREFIX = 'BOUNDARY_RUNTIME_RESULT '
TOKEN = re.compile(r'@@([A-Z][A-Z0-9_]*)@@')
CAPABILITY = re.compile(r"conflict on capability '([^']+)' also provided by \[([^\]]+)\]", re.DOTALL)
UNRESOLVED = re.compile(r'Could not (?:find|resolve) ([A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.+-]+)\.')
UNRELATED = ('Could not GET', 'Could not HEAD', 'status code', 'Dependency verification failed',
             'No cached version', 'Could not find ', 'Cannot find a version',
             'No matching variant', 'Checksum validation failed', 'RC_STAGED_RUNTIME_REJECTED')


class BoundaryError(RuntimeError):
    pass


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


a24 = load('dual_boundary_a24', 'verify-a24-maven-consumer.py')
maven = a24.maven_support
staged = a24.shared
wrapper = load('dual_boundary_wrapper', 'verify-gradle-split-artifact-consumer.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def opposite(runtime):
    if runtime not in ADAPTERS:
        raise BoundaryError('Only exact 5.5.2 and 5.5.3 are in this plan')
    return '5.5.3' if runtime == '5.5.2' else '5.5.2'


def anchors(runtime):
    return ['shardingsphere-infra-executor', 'shardingsphere-infra-spi',
            'shardingsphere-infra-database-core' if runtime == '5.5.2'
            else 'shardingsphere-database-connector-core']


def coordinate(module):
    return f'{GROUP}:{module}:{VERSION}'


def fixed_plan():
    result = []
    for tool in ('gradle', 'maven'):
        for runtime, adapter in ADAPTERS.items():
            other = ADAPTERS[opposite(runtime)]
            for order_name, order in (('selected-first', [adapter, other]),
                                      ('opposite-first', [other, adapter])):
                result.append({'id': f'{tool}-{runtime}-{order_name}', 'tool': tool, 'kind': 'dual',
                               'runtime': runtime, 'adapter': adapter, 'order': order,
                               'observedRuntime': runtime})
    for runtime, adapter in ADAPTERS.items():
        result.append({'id': f'maven-{runtime}-runtime-guard', 'tool': 'maven', 'kind': 'runtime-guard',
                       'runtime': runtime, 'adapter': adapter, 'order': [],
                       'observedRuntime': opposite(runtime)})
    return result


def choose_plan(ids=None):
    plan = fixed_plan()
    if ids is None:
        return plan
    if not ids or len(ids) != len(set(ids)) or not set(ids) <= {c['id'] for c in plan}:
        raise BoundaryError('Requested cases must be distinct identities from the fixed ten-case plan')
    return [c for c in plan if c['id'] in ids]


def render_template(text, values):
    names = set(TOKEN.findall(text))
    if names != set(values) or '@@' in TOKEN.sub('', text):
        raise BoundaryError('Template tokens and supplied values must match exactly')
    if any(not isinstance(v, str) or '@@' in v for v in values.values()):
        raise BoundaryError('Substitution values cannot introduce another template token')
    return TOKEN.sub(lambda match: values[match.group(1)], text)


def require_case(case, kind=None, tool=None):
    if case not in fixed_plan() or (kind and case['kind'] != kind) or (tool and case['tool'] != tool):
        raise BoundaryError('Case differs from the reviewed finite plan')


def capability_provider(providers):
    match = re.fullmatch(r"\s*'([^']+)'\s+\(runtimeElements\)\s*", providers)
    if match is None:
        raise BoundaryError('A capability cause must name exactly one quoted runtimeElements provider')
    return match.group(1)


def normalize_native_cause(text):
    return '\n'.join(re.sub(r'^\s*(?:>\s*)?', '', line).rstrip()
                     for line in text.splitlines() if line.strip())


def verify_root_requests(case, graph, selected, unresolved):
    expected = [coordinate(module) for module in case['order']] + [
        f'{SS}:{module}:{case["runtime"]}' for module in anchors(case['runtime'])]
    edges = graph.get('rootDependencies', [])
    if (len(edges) != 5 or [e.get('requested') for e in edges] != expected
            or any(e.get('from') != 'root project :' or e.get('constraint') is not False for e in edges)):
        raise BoundaryError('Actual five ordinary direct requests and their declaration order must match the fixture')
    for edge in edges:
        requested = edge['requested']
        root_failure = [e for e in unresolved if e.get('from') == 'root project :' and e.get('requested') == requested]
        if edge.get('resolved') is True:
            if (requested.startswith(GROUP + ':') or root_failure
                    or edge.get('selected') != requested or requested not in selected):
                raise BoundaryError('A direct resolved destination is not bound to its actual requested runtime anchor')
        elif edge.get('resolved') is False:
            if edge.get('selected') is not None or len(root_failure) != 1:
                raise BoundaryError('Every unresolved direct request must have exactly one matching actual root edge')
        else:
            raise BoundaryError('Root edge resolution state must be an actual JSON Boolean')
    return expected


def verify_intrinsic_strict(node, case, selected, metadata):
    own = node['requested']
    fields = own.split(':')
    modules = ('shardingsphere-infra-executor', 'shardingsphere-infra-spi')
    if (len(fields) != 3 or fields[0] != SS or fields[1] not in modules or fields[2] not in ADAPTERS
            or node['attempted'] != own or (node['from'] != 'root project :'
                and (node['from'] not in selected or not node['from'].startswith(SS + ':')))):
        raise BoundaryError('Only actual executor/SPI edges at exact5.5.2/5.5.3 may have intrinsic strict collisions')
    module_coordinate = ':'.join(fields[:2])
    pins = metadata.get(module_coordinate, [])
    if (len(pins) != 2 or {p.get('adapter') for p in pins} != {coordinate(m) for m in ADAPTERS.values()}
            or {p.get('version') for p in pins} != set(ADAPTERS)
            or any(p.get('kind') != ('Dependency' if fields[1] == modules[0] else 'Constraint')
                   or not isinstance(p.get('reason'), str) or not p['reason']
                   or not re.fullmatch(r'[0-9a-f]{64}', p.get('sourceMetadataSha256', ''))
                   or p['adapter'] != coordinate(ADAPTERS[p['version']]) for p in pins)):
        raise BoundaryError('Require both contradictory strict edges from the receipt-pinned published runtime metadata')
    messages = node.get('failureMessages', [])
    if (len(messages) != 2 or messages[0] != {
            'exceptionType': 'org.gradle.internal.resolve.ModuleVersionResolveException', 'message': f'Could not resolve {own}.'}
            or messages[1].get('exceptionType') != 'org.gradle.api.GradleException'
            or not isinstance(messages[1].get('message'), str)):
        raise BoundaryError('An intrinsic collision must have only its actual two native exception causes')
    leaf = messages[1]['message']
    lines = [line.strip() for line in leaf.splitlines() if line.strip()]
    header = f"Cannot find a version of '{module_coordinate}' that satisfies the version constraints:"
    if not lines or lines[0] != header or any(marker in leaf for marker in UNRELATED if marker != 'Cannot find a version'):
        raise BoundaryError('The intrinsic strict cause names a foreign module or another failure')
    found = []
    for line in lines[1:]:
        path = re.fullmatch(r'(Dependency|Constraint) path: (.+?)(?: because of the following reason: (.+))?', line)
        if path is None:
            raise BoundaryError('An unrecognized line appears inside the intrinsic strict failure')
        kind, description, reason = path.groups()
        segments = [re.fullmatch(r"'([^']+)'(?: \(([^)]+)\))?", segment) for segment in description.split(' --> ')]
        if (len(segments) < 2 or any(segment is None for segment in segments)
                or segments[0].groups() != ('root project :', 'dualAdapterRuntime')):
            raise BoundaryError('Intrinsic failure paths must start at the actual consumer configuration')
        coordinates = [segment.group(1) for segment in segments]
        variants = [segment.group(2) for segment in segments]
        strict = re.fullmatch(re.escape(module_coordinate) + r':\{strictly (5[.]5[.][23])\}', coordinates[-1])
        if strict:
            matching = [pin for pin in pins if pin['adapter'] == coordinates[1] and pin['version'] == strict.group(1)]
            if (len(segments) != 3 or variants != ['dualAdapterRuntime', 'runtimeElements', None]
                    or len(matching) != 1 or kind != matching[0]['kind'] or reason != matching[0]['reason']):
                raise BoundaryError('The strict adapter path, kind, version or reason differs from reviewed module metadata')
            found.append(matching[0]['adapter'])
        else:
            # These are Gradle's retained contributing paths through a partially rejected graph.
            # They do not establish a coherent or executable runtime.
            if (kind != 'Dependency' or reason is not None
                    or any(v not in (None, 'default', 'runtime', 'runtimeElements') for v in variants[1:])
                    or any(not re.fullmatch(re.escape(SS) + r':shardingsphere-[a-z0-9.-]+:5[.]5[.][23]', c)
                           for c in coordinates[1:])
                    or coordinates[1].split(':')[1] not in anchors(case['runtime'])
                    or coordinates[-1].rsplit(':', 1)[0] != module_coordinate):
                raise BoundaryError('A contributing strict-failure path is not an actual requested ShardingSphere anchor path')
    if len(found) != 2 or set(found) != {pin['adapter'] for pin in pins}:
        raise BoundaryError('Each intrinsic collision must show exactly both published contradictory adapter paths')
    return {'requested': own, 'from': node['from'], 'module': module_coordinate,
            'nativeCauseSha256': hashlib.sha256(leaf.encode()).hexdigest(),
            'publishedStrictRequirements': sorted(pins, key=lambda p: p['adapter'])}


def verify_gradle_dual(case, exit_code, output, graph, published_capabilities, *, published_constraints=None):
    require_case(case, 'dual', 'gradle')
    expected = [coordinate(module) for module in case['order']]
    allowed = set(published_capabilities)
    known = {f'{GROUP}:routecontract-shardingsphere-hook-adapter:1',
             f'{GROUP}:routecontract-shardingsphere-5.5:{VERSION}'}
    if not allowed or not allowed <= known:
        raise BoundaryError('Require the exact collision capabilities published by both modules')
    if (exit_code != 1 or 'BUILD FAILED' not in output
            or any(x in output for x in UNRELATED if x != 'Cannot find a version')):
        raise BoundaryError('Native Gradle failure contains an unrelated transport, variant, checksum or runtime-policy cause')
    if (graph.get('schemaVersion') != 2 or graph.get('tool') != 'gradle'
            or graph.get('configuration') != 'dualAdapterRuntime'
            or graph.get('requestedRuntime') != case['runtime']
            or graph.get('routeContractVersion') != VERSION
            or graph.get('declaredAdapters') != expected
            or graph.get('declaredRuntimeAnchors') != [f'{SS}:{name}:{case["runtime"]}' for name in anchors(case['runtime'])]):
        raise BoundaryError('Observed Gradle graph does not bind the requested order and runtime')
    unresolved = graph.get('unresolved', [])
    identities = [(n.get('requested'), n.get('attempted'), n.get('from')) for n in unresolved]
    if len(set(identities)) != len(identities) or any(a != b for a, b, _ in identities):
        raise BoundaryError('Unresolved graph contains duplicated edges or changed attempted selectors')
    selected = [item.get('coordinate', '') for item in graph.get('selectedComponents', [])]
    if (len(set(selected)) != len(selected)
            or any(c.startswith(SS + ':') and not re.fullmatch(re.escape(SS) + r':shardingsphere-[a-z0-9.-]+:5[.]5[.][23]', c) for c in selected)
            or any(c.startswith(GROUP + ':') and c != coordinate('routecontract-core') for c in selected)):
        raise BoundaryError('The retained partial graph contains a foreign version, duplicate or conflicting first-party selection')
    root_requests = verify_root_requests(case, graph, selected, unresolved)
    adapter_nodes = [n for n in unresolved if n.get('requested', '').startswith(GROUP + ':')]
    if (len(adapter_nodes) != 2 or {n.get('requested') for n in adapter_nodes} != set(expected)
            or any(n.get('from') != 'root project :' for n in adapter_nodes)):
        raise BoundaryError('The actual first-party unresolved selectors must be exactly both direct adapters')
    intrinsic_nodes = [n for n in unresolved if n not in adapter_nodes]
    intrinsic = [verify_intrinsic_strict(node, case, selected, published_constraints or {}) for node in intrinsic_nodes]
    native_unresolved = set(UNRESOLVED.findall(output))
    if not set(expected) <= native_unresolved or not native_unresolved <= {n['requested'] for n in unresolved}:
        raise BoundaryError('Native Gradle unresolved selectors differ from the actual retained rejected graph')
    strict_headers = re.findall(r"Cannot find a version of '([^']+)' that satisfies the version constraints:", output)
    if (output.count('Cannot find a version') != len(strict_headers)
            or set(strict_headers) != {item['module'] for item in intrinsic}):
        raise BoundaryError('Native output contains a missing or unbound strict-constraint failure section')
    normalized = normalize_native_cause(output)
    for node in intrinsic_nodes:
        if normalize_native_cause(node['failureMessages'][1]['message']) not in normalized:
            raise BoundaryError('Actual intrinsic exception text is not retained in native Gradle output')
    observed = set()
    for node in adapter_nodes:
        own = node['requested']
        other = next(value for value in expected if value != own)
        messages = node.get('failureMessages', [])
        if (len(messages) != 2 or messages[0] != {
                'exceptionType': 'org.gradle.internal.resolve.ModuleVersionResolveException', 'message': f'Could not resolve {own}.'}
                or messages[1].get('exceptionType') != 'org.gradle.api.GradleException'
                or not isinstance(messages[1].get('message'), str)):
            raise BoundaryError('An unrelated native exception appears in the capability cause chain')
        causal = messages[1]['message']
        conflicts = CAPABILITY.findall(causal)
        leaf_lines = [line.strip() for line in causal.splitlines() if line.strip()]
        capability_lines = [re.fullmatch(r"Cannot select module with conflict on capability '([^']+)' "
                                          r"also provided by \[([^\]]+)\]", line) for line in leaf_lines[1:]]
        if (not causal.startswith(f"Module '{own.rsplit(':', 1)[0]}' has been rejected:")
                or any(x in causal for x in UNRELATED) or not conflicts
                or not capability_lines or any(line is None for line in capability_lines)
                or any(cap not in allowed or capability_provider(providers) != other for cap, providers in conflicts)):
            raise BoundaryError('Each native capability cause must bind its own adapter to the exact opposite provider')
        observed.update(cap for cap, _providers in conflicts)
    native_conflicts = CAPABILITY.findall(output)
    if not native_conflicts or {cap for cap, _providers in native_conflicts} != observed:
        raise BoundaryError('Structured and native capability identities differ')
    rejection_headers = list(re.finditer(r"Module '([^']+)' has been rejected:", output))
    if len(rejection_headers) != 2 or {m.group(1) for m in rejection_headers} != {c.rsplit(':', 1)[0] for c in expected}:
        raise BoundaryError('Native Gradle output must retain exactly both actual adapter rejection sections')
    for index, match in enumerate(rejection_headers):
        end = rejection_headers[index + 1].start() if index + 1 < len(rejection_headers) else len(output)
        other = next(value for value in expected if value != match.group(1) + ':' + VERSION)
        conflicts = CAPABILITY.findall(output[match.end():end])
        if not conflicts or any(cap not in allowed or capability_provider(providers) != other for cap, providers in conflicts):
            raise BoundaryError('Each native module rejection must name exactly its opposite adapter provider')
    return {'result': 'NATIVE_CAPABILITY_AND_INTRINSIC_STRICT_REJECTED' if intrinsic else 'NATIVE_CAPABILITY_REJECTED',
            'capabilities': sorted(observed), 'declaredAdapters': expected,
            'capabilityUnresolvedSelectors': sorted(expected),
            'unresolvedSelectors': sorted({node['requested'] for node in unresolved}),
            'actualRootRequests': root_requests, 'intrinsicStrictCollisions': intrinsic,
            'coherentResolvedRuntimeClaimed': False}


def graph_coordinates(tree, case):
    require_case(case)
    items = list(maven.nodes(tree))
    coordinates = {f'{n.get("groupId")}:{n.get("artifactId")}:{n.get("version")}' for n in items}
    expected_modules = set(case['order']) if case['kind'] == 'dual' else {case['adapter']}
    expected = {coordinate(module) for module in expected_modules | {'routecontract-core'}}
    first = {c for c in coordinates if c.startswith(GROUP + ':')}
    if first != expected:
        raise BoundaryError('The actual selected graph must contain exactly the expected first-party modules')
    direct = [n for n in tree.get('children', []) if n.get('groupId') == GROUP]
    expected_direct = case['order'] if case['kind'] == 'dual' else [case['adapter']]
    if [n.get('artifactId') for n in direct] != expected_direct:
        raise BoundaryError('Maven graph does not retain the ordinary adapter declaration order')
    if not any(n.get('groupId') == GROUP and n.get('artifactId') == 'routecontract-core'
               for dep in direct for n in maven.nodes(dep) if n is not dep):
        raise BoundaryError('Core must resolve transitively from the adapter POM')
    runtime = case['observedRuntime']
    sharding = {c for c in coordinates if c.startswith(SS + ':')}
    expected_anchors = {f'{SS}:{module}:{runtime}' for module in anchors(runtime)}
    if not expected_anchors <= sharding or any(c.split(':')[-1] != runtime for c in sharding):
        raise BoundaryError('The selected ShardingSphere graph and all three anchors must be coherent')
    return sorted(coordinates)


def verify_maven_dual(case, exit_code, output, tree):
    require_case(case, 'dual', 'maven')
    selected = graph_coordinates(tree, case)
    banned = coordinate(ADAPTERS[opposite(case['runtime'])])
    native = banned.rsplit(':', 1)[0] + ':jar:' + VERSION
    rules = re.findall(r'Rule \d+: ([A-Za-z0-9_.]+) failed', output)
    banned_lines = [line.strip() for line in output.splitlines() if '<--- banned via the exclude/include list' in line]
    section = re.search(r'^\[ERROR\] Rule \d+: org\.apache\.maven\.enforcer\.rules\.dependency\.BannedDependencies '
                        r'failed with message:\n((?:\[ERROR\](?!.*(?:-> \[Help|Rule \d+:)).*\n)*)',
                        output, re.MULTILINE)
    if (exit_code != 1 or 'BUILD FAILURE' not in output
            or 'org.apache.maven.plugins:maven-enforcer-plugin:3.6.3:enforce (reject-opposite-adapter)' not in output
            or rules != ['org.apache.maven.enforcer.rules.dependency.BannedDependencies']
            or len(banned_lines) != 1 or native not in banned_lines[0]
            or section is None or banned_lines[0] not in section.group(1)
            or any(marker in output for marker in UNRELATED)
            or any(marker in output for marker in ('Could not resolve ', 'Could not transfer ',
                       'Failed to collect dependencies', '--- compiler:', '--- surefire:'))):
        raise BoundaryError('Require the unique native BannedDependencies cause naming only the opposite adapter')
    if re.findall(r'[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:jar:[A-Za-z0-9_.+-]+', banned_lines[0]) != [native]:
        raise BoundaryError('Banned dependency line contains another coordinate')
    return {'result': 'NATIVE_ENFORCER_REJECTED', 'bannedCoordinate': banned,
            'selectedCoordinates': selected}


def anchor_classes(runtime):
    return {'executor': 'org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook',
            'spi': ('org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader' if runtime == '5.5.2'
                    else 'org.apache.shardingsphere.infra.spi.ShardingSphereSPI'),
            'database': ('org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties'
                         if runtime == '5.5.2' else
                         'org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties')}


def verify_guard_report(case, report, expected):
    require_case(case, 'runtime-guard', 'maven')
    runtime = case['observedRuntime']
    message = f'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: exact adapter {case["runtime"]} observed {runtime}'
    if (report.get('schemaVersion') != 1 or report.get('adapterRuntime') != case['runtime']
            or report.get('observedRuntime') != runtime
            or report.get('currentApi') != 'io.github.ym0506.routecontract.api.RouteContract'
            or report.get('javaFeature') != 17 or not re.fullmatch(r'17(?:[.+-].*)?', report.get('javaVersion', ''))
            or report.get('preferIPv4Stack') is not True or report.get('userHome') != expected['userHome']
            or report.get('pid') != expected['pid'] or report.get('parentPid') != expected['parentPid']
            or report.get('pid') == report.get('parentPid') or report.get('actionInvoked') is not False
            or report.get('diagnosticCode') != 'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME'
            or report.get('diagnosticMessage') != message or report.get('exceptionType') != 'java.lang.IllegalStateException'
            or any(report.get(k) for k in ('cause', 'causes', 'suppressed', 'suppressedExceptions'))):
        raise BoundaryError('The fresh JVM did not prove the coherent opposite-runtime rejection before action')
    if report.get('core') != expected['core'] or report.get('adapter') != expected['adapter']:
        raise BoundaryError('Actual loaded core/adapter bytes or origins differ from the resolved receipt')
    jars = sorted(expected['shardingSphereJars'], key=lambda j: j['coordinate'])
    coordinates = [j['coordinate'] for j in jars]
    if (not jars or len(set(coordinates)) != len(coordinates)
            or any(not c.startswith(SS + ':') or c.split(':')[-1] != runtime for c in coordinates)
            or sorted(report.get('shardingSphereCoordinates', [])) != coordinates
            or sorted(report.get('shardingSphereJars', []), key=lambda j: j['coordinate']) != jars):
        raise BoundaryError('Executed and selected complete ShardingSphere JAR sets differ')
    actual = report.get('anchors', [])
    classes = anchor_classes(runtime)
    modules = dict(zip(('executor', 'spi', 'database'), anchors(runtime)))
    if len(actual) != 3 or {x.get('role') for x in actual} != set(classes):
        raise BoundaryError('All three distinct actual opposite-runtime anchors are required')
    by_coordinate = {j['coordinate']: j for j in jars}
    for entry in actual:
        role = entry['role']
        coord = f'{SS}:{modules[role]}:{runtime}'
        jar = by_coordinate.get(coord)
        if (jar is None or entry.get('className') != classes[role] or entry.get('implementationVersion') != runtime
                or any(entry.get(k) != value for k, value in jar.items())):
            raise BoundaryError('An anchor is missing, mixed, or loaded from a different JAR')
    return {'result': 'COHERENT_OPPOSITE_RUNTIME_REJECTED', 'actionInvoked': False,
            'diagnosticCode': report['diagnosticCode'], 'actualJavaFeature': 17,
            'actualAnchorCoordinates': sorted(x['coordinate'] for x in actual)}


def source_snapshot():
    files = [Path(__file__).resolve(), ROOT / 'scripts/tests/test_verify_dual_resolver_boundaries.py',
             ROOT / 'gradlew', ROOT / 'gradle/verification-metadata.xml']
    files += [ROOT / 'scripts' / name for name in (
        'verify-a24-maven-consumer.py', 'verify-staged-maven-artifact-consumer.py',
        'verify-staged-split-artifact-consumer.py', 'verify-gradle-legacy-artifact-consumer.py',
        'verify-gradle-split-artifact-consumer.py', 'consumer_network_sandbox.py',
        'staged_maven_repository.py', 'public_split_artifacts.py', 'legacy_artifact_inputs.py',
        'maven_legacy_central_cache.py')]
    for directory in (FIXTURE, ROOT / 'gradle/wrapper'):
        files.extend(p for p in directory.rglob('*') if p.is_file())
    if any(p.is_symlink() or not p.is_file() or p.resolve(strict=True) != p for p in files):
        raise BoundaryError('Every executed input must be a regular file')
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(files))}


def prepare_case(directory, case, receipt=None):
    require_case(case)
    consumer = directory / 'consumer'
    consumer.mkdir(parents=True)
    (directory / 'home').mkdir()
    context = {'RUNTIME': case['runtime'], 'FIRST_ADAPTER': case['order'][0] if case['order'] else case['adapter'],
               'SECOND_ADAPTER': case['order'][1] if case['order'] else '', 'SELECTED_ADAPTER': case['adapter'],
               'OPPOSITE_RUNTIME': opposite(case['runtime']), 'OPPOSITE_ADAPTER': ADAPTERS[opposite(case['runtime'])],
               'DATABASE_ANCHOR': anchors(case['observedRuntime'])[-1],
               'OPPOSITE_DATABASE_ANCHOR': anchors(opposite(case['runtime']))[-1]}
    if case['tool'] == 'gradle':
        templates = [('gradle/build.gradle.template', 'build.gradle'),
                     ('gradle/settings.gradle.template', 'settings.gradle')]
        shutil.copy2(ROOT / 'gradlew', consumer / 'gradlew')
        shutil.copytree(ROOT / 'gradle/wrapper', consumer / 'gradle/wrapper')
        if receipt:
            staged.prepare_metadata(ROOT / 'gradle/verification-metadata.xml',
                                    consumer / 'gradle/verification-metadata.xml', receipt)
    else:
        templates = [(f'maven/{"dual" if case["kind"] == "dual" else "guard"}-pom.xml.template', 'pom.xml')]
        if case['kind'] == 'runtime-guard':
            shutil.copytree(FIXTURE / 'guard/src', consumer / 'src')
    for template, name in templates:
        text = (FIXTURE / template).read_text()
        names = set(TOKEN.findall(text))
        if not names <= set(context):
            raise BoundaryError('Fixture declares an unknown substitution token')
        (consumer / name).write_text(render_template(text, {key: context[key] for key in names}))
    if case['tool'] == 'maven':
        tree = ET.parse(consumer / 'pom.xml')
        n = {'m': 'http://maven.apache.org/POM/4.0.0'}
        enforcer = tree.findall('.//m:plugin[m:artifactId="maven-enforcer-plugin"]', n)
        if (case['kind'] == 'dual' and len(enforcer) != 1) or (case['kind'] == 'runtime-guard' and enforcer):
            raise BoundaryError('The dual and intentional no-Enforcer POMs must remain distinct')
    write_json(directory / 'case.json', case)
    write_json(directory / 'initial-cache.json', {'dependencyCacheInitiallyAbsent': True,
               'positiveCacheImported': False, 'stageBound': receipt is not None})
    write_json(directory / 'prepared-inputs.json', {str(p.relative_to(consumer)): sha(p)
               for p in sorted(consumer.rglob('*')) if p.is_file()})
    return consumer


def regular(path):
    path = Path(path).absolute()
    if not path.is_file() or path.is_symlink() or path.resolve(strict=True) != path:
        raise BoundaryError('Input must be one canonical regular nonsymlink file: ' + str(path))
    return path


def controlled_environment(java_home, private_home, cache=None):
    result = a24.environment(java_home, private_home)
    for key in tuple(result):
        if key.startswith('ORG_GRADLE_PROJECT_') or key in ('GRADLE_HOME', 'GRADLE_USER_HOME', 'GRADLE_RO_DEP_CACHE'):
            result.pop(key)
    result['PATH'] = str(java_home / 'bin') + ':/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin'
    if cache is not None:
        result['GRADLE_USER_HOME'] = str(cache)
    docker = private_home / '.docker'
    docker.mkdir(exist_ok=True)
    (docker / 'config.json').write_text('{}\n')
    return result


def native(command, cwd, environment, evidence, name, *, expected_exit=0):
    """Retain actual argv, PID and partial logs even on timeout; never retry implicitly."""
    record = {'name': name, 'argv': [str(x) for x in command], 'cwd': str(cwd),
              'environment': {key: environment[key] for key in (
                  'JAVA_HOME', 'JAVA_TOOL_OPTIONS', 'HOME', 'DOCKER_CONFIG', 'MAVEN_OPTS',
                  'MAVEN_SKIP_RC', 'GRADLE_USER_HOME', 'PATH', 'LANG', 'LC_ALL') if key in environment},
              'startedAt': datetime.now(timezone.utc).isoformat(), 'parentPid': os.getpid()}
    files = {}
    prepared_path = evidence / 'prepared-inputs.json'
    if prepared_path.exists():
        for relative, digest in json.loads(regular(prepared_path).read_text()).items():
            path = regular(cwd / relative)
            if sha(path) != digest:
                raise BoundaryError('A prepared input changed before native command launch')
            files[str(path)] = digest
    for filename in ('settings.xml', 'endpoint.json', 'guard-expectations.properties', 'runtime-classpath.txt'):
        path = evidence / filename
        if path.exists():
            files[str(regular(path))] = sha(path)
    record['inputFileSha256'] = files
    log = evidence / (name + '.log')
    with log.open('x', encoding='utf-8') as output:
        process = subprocess.Popen(record['argv'], cwd=cwd, env={**environment, 'MAVEN_BASEDIR': str(cwd)},
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        record['pid'] = process.pid
        write_json(evidence / (name + '-command.json'), record)
        try:
            process.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            record['timedOut'] = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
        finally:
            record.update(exitCode=process.returncode, endedAt=datetime.now(timezone.utc).isoformat())
            write_json(evidence / (name + '-command.json'), record)
    output = log.read_text(encoding='utf-8', errors='replace')
    if any(sha(regular(Path(path))) != digest for path, digest in files.items()):
        raise BoundaryError('An executed input changed during native command execution')
    if record.get('timedOut') or process.returncode != expected_exit:
        raise BoundaryError(f'{name} did not exit {expected_exit}; retained {log}')
    return output, record


def copy_reviewed_repository(repository, receipt, destination):
    a24.inventory(repository)  # Reject symlink ancestors and special files before any copying.
    staged.verify_receipt(repository, receipt)
    pins = []
    sidecars = []
    copies = {}
    for item in receipt['artifacts']:
        source = regular(repository / item['relativePath'])
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != item['sha256']:
            raise BoundaryError('Reviewed staging changed before copying')
        copies[item['relativePath']] = payload
        pins.append(dict(item, byteCount=len(payload)))
        for algorithm in ('md5', 'sha1', 'sha256', 'sha512'):
            relative = item['relativePath'] + '.' + algorithm
            checksum = regular(repository / relative).read_bytes()
            digest = hashlib.new(algorithm, payload).hexdigest()
            pattern = rb'[0-9a-fA-F]{' + str(len(digest)).encode() + rb'}(?:\r?\n)?'
            if not re.fullmatch(pattern, checksum) or checksum.rstrip(b'\r\n').lower() != digest.encode():
                raise BoundaryError('Existing staging checksum does not match receipt-verified payload: ' + relative)
            copies[relative] = checksum
            sidecars.append({'relativePath': relative, 'sha256': hashlib.sha256(checksum).hexdigest(),
                             'byteCount': len(checksum), 'algorithm': algorithm, 'digest': digest,
                             'payloadRelativePath': item['relativePath'], 'payloadSha256': item['sha256'],
                             'origin': 'copied-existing-staging-sidecar'})
    # Validate all existing sidecars before creating the disposable copy; never derive a replacement.
    destination.mkdir()
    for relative, payload in copies.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    staged.verify_receipt(destination, receipt)
    if sorted(a24.inventory(destination), key=lambda item: item['path']) != [
            {'path': path, 'size': len(copies[path]), 'sha256': hashlib.sha256(copies[path]).hexdigest()}
            for path in sorted(copies)]:
        raise BoundaryError('Disposable payload/checksum inventory differs from verified source bytes')
    return pins, sidecars


def maven_command(executable, settings, cache, private_home, consumer):
    return [str(executable), '--batch-mode', '--no-transfer-progress', '--strict-checksums',
            '--settings', str(settings), '--global-settings', str(settings),
            f'-Dmaven.repo.local={cache}', f'-Duser.home={private_home}',
            '-Dstyle.color=never', '--file', str(consumer / 'pom.xml')]


def gradle_command(consumer, cache, java_home, private_home, url):
    return [str(consumer / 'gradlew'), '--no-daemon', '--no-build-cache', '--no-configuration-cache',
            '--dependency-verification=strict', '--console=plain', '--project-dir', str(consumer),
            '--project-cache-dir', str(cache.parent / 'project-cache'),
            f'-Dorg.gradle.java.home={java_home}',
            f'-Dorg.gradle.jvmargs=-Xmx512m -Djava.net.preferIPv4Stack=true -Duser.home={private_home}',
            f'-Duser.home={private_home}', f'-ProutecontractRepositoryUrl={url}', 'resolveDualAdapters']


def published_capabilities(repository, receipt):
    published = []
    for module in ADAPTERS.values():
        pin = next(item for item in receipt['artifacts'] if item['module'] == module and item['name'].endswith('.module'))
        metadata = json.loads(regular(repository / pin['relativePath']).read_text())
        variants = [v for v in metadata['variants'] if v['name'] == 'runtimeElements']
        if len(variants) != 1:
            raise BoundaryError('Require exactly one reviewed runtimeElements variant')
        published.append({f'{c["group"]}:{c["name"]}:{c["version"]}' for c in variants[0].get('capabilities', [])})
    allowed = published[0] & published[1]
    known = {f'{GROUP}:routecontract-shardingsphere-hook-adapter:1',
             f'{GROUP}:routecontract-shardingsphere-5.5:{VERSION}'}
    if not allowed or not allowed <= known:
        raise BoundaryError('Reviewed modules do not publish the expected mutual collision capabilities')
    return sorted(allowed)


def published_strict_requirements(repository, receipt):
    result = {f'{SS}:shardingsphere-infra-executor': [], f'{SS}:shardingsphere-infra-spi': []}
    for runtime, adapter in ADAPTERS.items():
        pin = next(item for item in receipt['artifacts'] if item['module'] == adapter and item['name'].endswith('.module'))
        path = regular(repository / pin['relativePath'])
        if sha(path) != pin['sha256']:
            raise BoundaryError('Intrinsic strict requirements must come from unchanged receipt-pinned module bytes')
        metadata = json.loads(path.read_text())
        variants = [v for v in metadata['variants'] if v['name'] == 'runtimeElements']
        if len(variants) != 1:
            raise BoundaryError('Require one reviewed runtimeElements variant for intrinsic collisions')
        for module, section, kind in (('shardingsphere-infra-executor', 'dependencies', 'Dependency'),
                                      ('shardingsphere-infra-spi', 'dependencyConstraints', 'Constraint')):
            entries = [item for item in variants[0].get(section, []) if item.get('group') == SS and item.get('module') == module]
            if (len(entries) != 1 or entries[0].get('version') != {'requires': runtime, 'strictly': runtime}
                    or not isinstance(entries[0].get('reason'), str) or not entries[0]['reason']):
                raise BoundaryError('Reviewed metadata does not prove the exact intrinsic executor/SPI strict requirement')
            result[f'{SS}:{module}'].append({'adapter': coordinate(adapter), 'version': runtime,
                'kind': kind, 'reason': entries[0]['reason'], 'sourceMetadataSha256': pin['sha256']})
    return result


def cached_gradle_metadata(cache, receipt, case):
    a24.inventory(cache)
    result = []
    for module in case['order']:
        pin = next(item for item in receipt['artifacts'] if item['module'] == module and item['name'].endswith('.module'))
        directory = cache / 'caches/modules-2/files-2.1' / GROUP / module / VERSION
        actual = list(directory.glob('*/' + pin['name']))
        if len(actual) != 1 or sha(regular(actual[0])) != pin['sha256']:
            raise BoundaryError('Actual cached Gradle module metadata differs from its reviewed receipt')
        result.append({'path': pin['relativePath'], 'sha256': pin['sha256'],
                       'byteCount': actual[0].stat().st_size, 'cachePath': str(actual[0])})
    return result


def cached_maven_payloads(cache, receipt, case):
    a24.inventory(cache)
    modules = case['order'] if case['kind'] == 'dual' else [case['adapter']]
    result = {}
    for module in modules:
        for item in a24.selected_files(cache, module, receipt, MIRROR_ID):
            actual = regular(cache / item['path'])
            result[item['path']] = dict(item, cachePath=str(actual), byteCount=actual.stat().st_size)
    expected = {pin['relativePath'] for pin in receipt['artifacts']
                if pin['module'] in set(modules) | {'routecontract-core'} and pin['name'].endswith(('.jar', '.pom'))}
    if set(result) != expected:
        raise BoundaryError('Selected first-party cache proof is missing a reviewed JAR or POM')
    return [result[key] for key in sorted(result)]


def jar_record(coord, path):
    path = regular(path)
    return {'coordinate': coord, 'path': str(path), 'sha256': sha(path), 'byteCount': path.stat().st_size}


def guard_classpath(cache, consumer, case, tree, classpath_file, consumed):
    selected = graph_coordinates(tree, case)
    coordinates = {c for c in selected if c.startswith(SS + ':')}
    text = regular(classpath_file).read_text().strip()
    paths = [regular(Path(p)) for p in text.split(os.pathsep)]
    if not paths or len(set(paths)) != len(paths) or any(not p.is_relative_to(cache) for p in paths):
        raise BoundaryError('Guard runtime classpath must contain unique JARs only from this fresh cache')
    first = {record['cachePath']: record for record in consumed if record['cachePath'].endswith('.jar')}
    seen_first, sharding = set(), []
    for path in paths:
        if path.suffix != '.jar':
            raise BoundaryError('A runtime dependency classpath entry is not a JAR')
        relative = path.relative_to(cache).as_posix()
        if relative.startswith(GROUP.replace('.', '/') + '/'):
            if str(path) not in first or sha(path) != first[str(path)]['sha256']:
                raise BoundaryError('Runtime first-party JAR is outside selected receipt-pinned payloads')
            seen_first.add(str(path))
        if relative.startswith(SS.replace('.', '/') + '/'):
            fields = relative.split('/')
            module, version, filename = fields[-3:]
            coord = f'{SS}:{module}:{version}'
            if coord not in coordinates or filename != f'{module}-{version}.jar':
                raise BoundaryError('Classpath ShardingSphere JAR differs from the actual selected graph')
            sharding.append(jar_record(coord, path))
    if seen_first != set(first) or {j['coordinate'] for j in sharding} != coordinates or len(sharding) != len(coordinates):
        raise BoundaryError('Classpath is missing a selected first-party or ShardingSphere JAR')
    classes = consumer / 'target/classes'
    class_files = sorted(classes.rglob('*.class'))
    expected_class = classes / (GUARD_CLASS.replace('.', '/') + '.class')
    if class_files != [expected_class]:
        raise BoundaryError('Compile must produce only the intended current-API probe class')
    raw = regular(expected_class).read_bytes()
    if len(raw) < 8 or raw[:4] != bytes.fromhex('cafebabe') or int.from_bytes(raw[6:8], 'big') != 61:
        raise BoundaryError('The actual compiled probe must be Java 17 bytecode')
    if (consumer / 'target/test-classes').exists() or (consumer / 'target/surefire-reports').exists():
        raise BoundaryError('Guard fixtures may not execute tests')
    expected = {'parentPid': os.getpid(), 'userHome': str(consumer.parent / 'home'),
                'shardingSphereJars': sorted(sharding, key=lambda j: j['coordinate'])}
    for label, module in (('core', 'routecontract-core'), ('adapter', case['adapter'])):
        jar = next(Path(name) for name in first if Path(name).name == f'{module}-{VERSION}.jar')
        expected[label] = jar_record(coordinate(module), jar)
    return os.pathsep.join(map(str, [classes, *paths])), expected, {
        'classFile': str(expected_class), 'classSha256': sha(expected_class), 'classMajor': 61,
        'classpathSha256': sha(classpath_file), 'selectedCoordinates': selected,
        'resolvedJarFiles': [{'path': str(path), 'cacheRelativePath': path.relative_to(cache).as_posix(),
                              'sha256': sha(path), 'byteCount': path.stat().st_size} for path in paths]}


def write_properties(path, values):
    # java.util.Properties.load(InputStream) decodes ISO-8859-1 and backslash escapes.
    def escape(value):
        result = ''
        encoded = str(value).encode('utf-16-be')
        for offset in range(0, len(encoded), 2):
            code = int.from_bytes(encoded[offset:offset + 2], 'big')
            char = chr(code)
            if char in '\\:=#! ':
                result += '\\' + char
            elif code < 32 or code > 126:
                result += '\\u' + format(code, '04x')
            else:
                result += char
        return result
    path.write_text(''.join(escape(k) + '=' + escape(v) + '\n' for k, v in sorted(values.items())), encoding='ascii')


def execute_guard(case, consumer, directory, cache, command, environment, java_home, tree, receipt):
    classpath_file = directory / 'runtime-classpath.txt'
    output, _ = native([*command, 'compile',
                        'org.apache.maven.plugins:maven-dependency-plugin:3.11.0:build-classpath',
                        '-Dmdep.includeScope=runtime', f'-Dmdep.outputFile={classpath_file}'],
                       consumer, environment, directory, 'compile-current-api')
    if ('--- compiler:3.14.1:compile ' not in output or 'enforcer:' in output
            or '--- surefire:' in output or 'BUILD SUCCESS' not in output):
        raise BoundaryError('Guard must compile current API without Enforcer or tests')
    consumed = cached_maven_payloads(cache, receipt, case)
    classpath, expected, compiled = guard_classpath(cache, consumer, case, tree, classpath_file, consumed)
    write_json(directory / 'compiled-classpath.json', compiled)
    values = {'adapterRuntime': case['runtime'], 'observedRuntime': case['observedRuntime'],
              'expectedUserHome': expected['userHome'], 'expectedParentPid': expected['parentPid'],
              'expectedShardingSphereCoordinates': ','.join(j['coordinate'] for j in expected['shardingSphereJars'])}
    for label in ('core', 'adapter'):
        values[label + 'Sha256'] = expected[label]['sha256']
        values[label + 'ByteCount'] = expected[label]['byteCount']
    expectations = directory / 'guard-expectations.properties'
    write_properties(expectations, values)
    java_argv = [str(java_home / 'bin/java'), '-Djava.net.preferIPv4Stack=true',
                 f'-Duser.home={directory / "home"}', '-cp', classpath, GUARD_CLASS,
                 '--expectations', str(expectations)]
    output, process = native(java_argv, consumer, environment, directory, 'fresh-jvm-current-api-guard')
    reports = [json.loads(line[len(GUARD_PREFIX):]) for line in output.splitlines() if line.startswith(GUARD_PREFIX)]
    if len(reports) != 1:
        raise BoundaryError('Exactly one actual fresh-JVM guard result is required')
    expected['pid'] = process['pid']
    write_json(directory / 'independent-guard-expectations.json', expected)
    write_json(directory / 'actual-guard-report.json', reports[0])
    proof = verify_guard_report(case, reports[0], expected)
    for record in [expected['core'], expected['adapter'], *expected['shardingSphereJars']]:
        if jar_record(record['coordinate'], Path(record['path'])) != record:
            raise BoundaryError('Actual runtime JAR bytes changed while measuring the guard')
    return proof, consumed


def execute_case(case, directory, repository, receipt, java_home, mvn, gradle_zip):
    consumer = directory / 'consumer'
    cache = directory / ('gradle-home' if case['tool'] == 'gradle' else 'm2')
    if cache.exists() or cache.is_symlink() or (directory / 'project-cache').exists():
        raise BoundaryError('Each native boundary case requires its own absent dependency cache')
    environment = controlled_environment(java_home, directory / 'home', cache if case['tool'] == 'gradle' else None)
    if case['tool'] == 'gradle':
        a24.source_support.seed_distribution_zip(gradle_zip, cache)
        if (cache / 'caches').exists():
            raise BoundaryError('Only the externally pinned Gradle ZIP may seed a fresh cache')
    write_json(directory / 'pre-execution-cache.json', {'caseId': case['id'], 'dependencyCacheInitiallyAbsent': True,
               'positiveCacheImported': False, 'files': a24.inventory(cache) if cache.exists() else []})
    graph_file = consumer / 'negative-graph.json'
    requests_file = directory / 'repository-requests.jsonl'
    with a24.mirror.serve_repository(repository, requests_file) as url:
        write_json(directory / 'endpoint.json', {'baseUrl': url, 'firstPartySource': 'receipt-pinned-disposable-copy'})
        if case['tool'] == 'gradle':
            command = gradle_command(consumer, cache, java_home, directory / 'home', url)
            output, process = native(command, consumer, environment, directory, 'native-capability-rejection', expected_exit=1)
            graph = json.loads(regular(graph_file).read_text())
            proof = verify_gradle_dual(case, process['exitCode'], output, graph,
                                       published_capabilities(repository, receipt),
                                       published_constraints=published_strict_requirements(repository, receipt))
            consumed = cached_gradle_metadata(cache, receipt, case)
            if (consumer / 'build/classes').exists() or (consumer / 'build/test-results').exists():
                raise BoundaryError('Native Gradle conflict fixtures may not compile or execute tests')
        else:
            settings = directory / 'settings.xml'
            maven.write_settings(settings, url, MIRROR_ID)
            a24.verify_settings(settings, url, MIRROR_ID)
            command = maven_command(mvn, settings, cache, directory / 'home', consumer)
            output, _ = native([*command, maven.DEPENDENCY_TREE, '-DoutputType=json',
                                 f'-DoutputFile={graph_file}'],
                                consumer, environment, directory, 'actual-selected-graph')
            if any(marker in output for marker in ('--- enforcer:', '--- compiler:', '--- surefire:')):
                raise BoundaryError('Graph collection must not enter compilation, test or Enforcer lifecycle')
            graph_bytes = regular(graph_file).read_bytes()
            tree = json.loads(graph_bytes)
            graph_coordinates(tree, case)
            # Both plugin goals bind outputFile; a combined invocation overwrites the JSON.
            output, _ = native([*command, a24.DEPENDENCY_RESOLVE,
                                 f'-DoutputFile={directory / "resolved-payloads.txt"}'],
                                consumer, environment, directory, 'actual-resolved-payloads')
            if any(marker in output for marker in ('--- enforcer:', '--- compiler:', '--- surefire:')):
                raise BoundaryError('Artifact resolution must not enter compilation, test or Enforcer lifecycle')
            if regular(graph_file).read_bytes() != graph_bytes:
                raise BoundaryError('Selected graph bytes changed during artifact resolution')
            if case['kind'] == 'dual':
                output, process = native([*command, 'validate'], consumer, environment, directory,
                                          'native-enforcer-rejection', expected_exit=1)
                proof = verify_maven_dual(case, process['exitCode'], output, tree)
                consumed = cached_maven_payloads(cache, receipt, case)
                if (consumer / 'target/classes').exists() or (consumer / 'target/test-classes').exists():
                    raise BoundaryError('Maven dual-adapter fixtures may not compile or execute tests')
            else:
                proof, consumed = execute_guard(case, consumer, directory, cache, command, environment, java_home, tree, receipt)
    # Server context joins request handlers; only these finalized GETs may bind origins.
    requests = [json.loads(line) for line in regular(requests_file).read_text().splitlines()]
    gets = a24.verify_origin_requests(requests, consumed)
    write_json(directory / 'consumed-first-party.json', consumed)
    write_json(directory / 'exact-successful-first-party-gets.json', gets)
    prepared = json.loads((directory / 'prepared-inputs.json').read_text())
    if any(sha(regular(consumer / name)) != digest for name, digest in prepared.items()):
        raise BoundaryError('Generated fixture inputs changed during their native execution')
    proof.update(caseId=case['id'], passed=True, graphSha256=sha(graph_file),
                 generatedInputsSha256=sha(directory / 'prepared-inputs.json'),
                 requestLogSha256=sha(requests_file), consumedFirstPartySha256=sha(directory / 'consumed-first-party.json'),
                 freshDependencyCache=True, mysqlExecutions=0)
    proof['nativeEvidenceFiles'] = {path.name: sha(path) for path in sorted(directory.iterdir())
                                    if path.is_file() and (path.name.endswith('-command.json')
                                                           or path.name.endswith('.log'))}
    proof['executionEvidenceFiles'] = {path.name: sha(path) for path in sorted(directory.iterdir())
                                       if path.is_file() and path.suffix in ('.json', '.xml', '.properties', '.txt')}
    write_json(directory / 'result.json', proof)
    return proof


def verify_toolchain(directory, java_home, mvn, gradle_zip):
    home = directory / 'home'
    consumer = directory / 'consumer'
    home.mkdir(parents=True)
    consumer.mkdir()
    cache = directory / 'gradle-home'
    environment = controlled_environment(java_home, home, cache)
    java = regular(java_home / 'bin/java')
    mvn = regular(mvn)
    output, _ = native([str(java), '-XshowSettings:properties', '-version'], consumer, environment, directory, 'java17-identity')
    if (not re.search(r'java\.version = 17(?:[.\n+-])', output)
            or not re.search(r'java\.home = ' + re.escape(str(java_home)) + r'\s*$', output, re.MULTILINE)):
        raise BoundaryError('Selected Java executable did not report the exact Java17 home')
    output, _ = native([str(mvn), '--version'], consumer, environment, directory, 'maven-identity')
    if ('Apache Maven 3.9.14' not in output or not re.search(r'Java version: 17(?:[.,+-])', output)
            or f'runtime: {java_home}' not in output):
        raise BoundaryError('Selected Maven must run version3.9.14 on the exact Java17 home')
    a24.source_support.seed_distribution_zip(gradle_zip, cache)
    shutil.copy2(ROOT / 'gradlew', consumer / 'gradlew')
    shutil.copytree(ROOT / 'gradle/wrapper', consumer / 'gradle/wrapper')
    output, _ = native([str(consumer / 'gradlew'), '--no-daemon', '--offline', '--version',
                        f'-Dorg.gradle.java.home={java_home}', f'-Duser.home={home}'],
                       consumer, environment, directory, 'gradle-identity')
    if ('Gradle 8.14.4' not in output or not re.search(r'Launcher JVM:\s+17[.\s]', output)
            or not re.search(r'Daemon JVM:\s+' + re.escape(str(java_home)) + r'(?:\s|$)', output)):
        raise BoundaryError('Pinned Gradle must identify the exact selected Java17 home')
    result = {'javaFeature': 17, 'javaHome': str(java_home), 'javaExecutableSha256': sha(java),
              'mavenVersion': '3.9.14', 'mavenExecutable': str(mvn), 'mavenExecutableSha256': sha(mvn),
              'gradleVersion': '8.14.4', 'gradleDistributionSha256': sha(gradle_zip)}
    write_json(directory / 'toolchain.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--execute', action='store_true')
    parser.add_argument('--repository', type=Path)
    parser.add_argument('--reviewed-receipt', type=Path)
    parser.add_argument('--reviewed-receipt-sha256')
    parser.add_argument('--staged-source-revision')
    parser.add_argument('--expected-input-manifest', type=Path)
    parser.add_argument('--java17-home', type=Path)
    parser.add_argument('--maven', type=Path)
    parser.add_argument('--gradle-distribution-zip', type=Path)
    parser.add_argument('--case-id', action='append')
    args = parser.parse_args(argv)
    plan = choose_plan(args.case_id)
    stage = (args.repository, args.reviewed_receipt, args.reviewed_receipt_sha256, args.staged_source_revision)
    if any(stage) and not all(stage):
        raise BoundaryError('All four reviewed staging inputs must be supplied together')
    if args.execute and (not all(stage) or not all((args.expected_input_manifest, args.java17_home,
                                                   args.maven, args.gradle_distribution_zip))):
        raise BoundaryError('Execution requires reviewed staging, explicit toolchains and a reviewed frozen input manifest')
    inputs = source_snapshot()
    if args.expected_input_manifest:
        expected_inputs = json.loads(regular(args.expected_input_manifest).read_text())
        if expected_inputs != inputs:
            raise BoundaryError('Executed fixture/helper inputs differ from the reviewed frozen manifest')
    repository = args.repository.resolve(strict=True) if args.repository else None
    evidence = a24.evidence_path(args.evidence_directory, ROOT, repository or ROOT)
    receipt = binding = None
    if repository:
        receipt, binding = a24.reviewed_inputs(repository, regular(args.reviewed_receipt),
                                               args.reviewed_receipt_sha256, args.staged_source_revision)
    gradle_zip = regular(args.gradle_distribution_zip) if args.gradle_distribution_zip else None
    distribution_hash = 'f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d'
    if gradle_zip and sha(gradle_zip) != distribution_hash:
        raise BoundaryError('Gradle ZIP differs from the independently supplied distribution SHA-256')
    evidence.mkdir(parents=True, mode=0o700)
    write_json(evidence / 'fixture-inputs.json', inputs)
    write_json(evidence / 'explicit-case-plan.json', plan)
    summary = {'schemaVersion': 1, 'requirements': ['A-15', 'A-17'],
               'status': 'PREPARED_WAITING_FOR_REVIEWED_STAGE' if not receipt else 'PREPARED_WAITING_FOR_EXECUTION_REVIEW',
               'completeBoundaryMatrix': False, 'nativeBoundaryMatrixComplete': False,
               'requestedCasesComplete': False, 'independentlyAudited': False,
               'requestedCases': plan, 'executedCases': 0, 'results': [], 'mysqlExecutions': 0,
               'publicConsumption': False, 'fullA24Complete': False,
               'stagedSourceRevision': args.staged_source_revision,
               'reviewedReceiptSha256': args.reviewed_receipt_sha256,
               'inputManifestSha256': sha(evidence / 'fixture-inputs.json'),
               'gradleDistributionSha256': sha(gradle_zip) if gradle_zip else None,
               'limits': ['Only remaining dual-resolver and coherent-opposite runtime guard boundaries',
                          'Existing scoped A24 anchor/nonanchor and positive evidence remains separate',
                          'Final native execution requires newly reviewed A09 candidate and explicit run review']}
    write_json(evidence / 'summary.json', summary)
    try:
        if receipt:
            receipt_before = regular(args.reviewed_receipt).read_bytes()
            repository_before = a24.inventory(repository)
            (evidence / 'reviewed-staged-receipt.json').write_bytes(receipt_before)
            write_json(evidence / 'source-binding.json', binding)
            write_json(evidence / 'original-staging-inventory.json', repository_before)
            disposable = evidence / 'repository'
            payload_pins, checksum_pins = copy_reviewed_repository(repository, receipt, disposable)
            write_json(evidence / 'receipt-pinned-payloads.json', payload_pins)
            write_json(evidence / 'verified-checksum-sidecars.json', checksum_pins)
            disposable_before = a24.inventory(disposable)
            write_json(evidence / 'disposable-staging-inventory.json', disposable_before)
        for case in plan:
            prepare_case(evidence / case['id'], case, receipt)
        write_json(evidence / 'prepared-case-inputs.json', {case['id']: json.loads(
            (evidence / case['id'] / 'prepared-inputs.json').read_text()) for case in plan})
        if args.execute:
            if source_snapshot() != inputs:
                raise BoundaryError('Reviewed execution inputs changed before the first toolchain command')
            java_home = args.java17_home.resolve(strict=True)
            mvn = args.maven.resolve(strict=True)
            summary['status'] = 'RUNNING'
            summary['toolchain'] = verify_toolchain(evidence / 'toolchain', java_home, mvn, gradle_zip)
            for case in plan:
                print('Running bounded case ' + case['id'], flush=True)
                summary['activeCase'] = case['id']
                summary['executedCases'] += 1
                write_json(evidence / 'summary.json', summary)
                proof = execute_case(case, evidence / case['id'], disposable, receipt, java_home, mvn, gradle_zip)
                summary['results'].append(proof)
                if source_snapshot() != inputs:
                    raise BoundaryError('Frozen executable inputs changed while the matrix was running')
                staged.verify_receipt(disposable, receipt)
                staged.verify_receipt(repository, receipt)
                if a24.inventory(disposable) != disposable_before:
                    raise BoundaryError('Disposable payload/checksum bytes changed during execution')
                write_json(evidence / 'summary.json', summary)
            if (source_snapshot() != inputs or a24.inventory(repository) != repository_before
                    or regular(args.reviewed_receipt).read_bytes() != receipt_before
                    or a24.reviewed_inputs(repository, args.reviewed_receipt, args.reviewed_receipt_sha256,
                                            args.staged_source_revision) != (receipt, binding)
                    or sha(gradle_zip) != distribution_hash):
                raise BoundaryError('Original staging, receipt, source binding or execution inputs changed')
            summary.pop('activeCase', None)
            summary['requestedCasesComplete'] = True
            summary['nativeBoundaryMatrixComplete'] = plan == fixed_plan()
            summary['finalInputsUnchanged'] = True
            summary['status'] = 'NATIVE_CASES_PASSED_PENDING_INDEPENDENT_AUDIT'
        else:
            if source_snapshot() != inputs:
                raise BoundaryError('Fixture inputs changed during preparation')
            summary['preparedCases'] = len(plan)
        if receipt and (a24.inventory(repository) != repository_before
                        or regular(args.reviewed_receipt).read_bytes() != receipt_before
                        or a24.reviewed_inputs(repository, args.reviewed_receipt, args.reviewed_receipt_sha256,
                                               args.staged_source_revision) != (receipt, binding)):
            raise BoundaryError('Reviewed staging or source binding changed during preparation or execution')
        write_json(evidence / 'summary.json', summary)
    except BaseException as error:
        summary['status'] = 'FAILED_PRESERVED'
        summary['failureType'] = type(error).__name__
        summary['failure'] = str(error)
        raise
    finally:
        write_json(evidence / 'summary.json', summary)
    print(summary['status'] + ' prepared=' + str(len(plan)) + ' executed=' + str(summary['executedCases']), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, BoundaryError, a24.VerificationError, a24.source_support.ResolverError,
            a24.mirror.RepositoryError, subprocess.SubprocessError) as error:
        print('DUAL_RESOLVER_BOUNDARY_FAILED: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
