"""Synthetic boundary-verifier unit tests; never staged execution evidence.

No Gradle, Maven, Java, network, Docker or MySQL process is launched here. These
tests exercise finite planning, input rendering and rejection-evidence parsing.
"""
import copy
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'dual_resolver_boundaries_unit_tests',
    ROOT / 'scripts/verify-dual-resolver-boundaries.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

GROUP = 'io.github.ym0506.routecontract'
SS_GROUP = 'org.apache.shardingsphere'
ADAPTERS = {
    '5.5.2': 'routecontract-shardingsphere-5.5.2',
    '5.5.3': 'routecontract-shardingsphere-5.5',
}


def opposite(runtime):
    return '5.5.3' if runtime == '5.5.2' else '5.5.2'


def anchors(runtime):
    database = ('shardingsphere-infra-database-core' if runtime == '5.5.2'
                else 'shardingsphere-database-connector-core')
    return [f'{SS_GROUP}:{module}:{runtime}' for module in
            ('shardingsphere-infra-executor', 'shardingsphere-infra-spi', database)]


def gradle_fixture(case, capability):
    """Use native 8.14.4 wording retained previously, with synthetic graph data."""
    declared = [f'{GROUP}:{module}:0.2.0' for module in case['order']]
    failures = []
    for own, other in (declared, declared[::-1]):
        messages = [
            {'exceptionType': 'org.gradle.internal.resolve.ModuleVersionResolveException',
             'message': f'Could not resolve {own}.'},
            {'exceptionType': 'org.gradle.api.GradleException',
             'message': f"Module '{own.rsplit(':', 1)[0]}' has been rejected:\n"
                        f"   Cannot select module with conflict on capability '{capability}' "
                        f"also provided by ['{other}' (runtimeElements)]"},
        ]
        failures.append({'requested': own, 'attempted': own, 'from': 'root project :',
                         'failureMessages': messages})
    graph = {'schemaVersion': 2, 'tool': 'gradle', 'configuration': 'dualAdapterRuntime',
             'requestedRuntime': case['runtime'], 'routeContractVersion': '0.2.0',
             'declaredAdapters': declared, 'declaredRuntimeAnchors': anchors(case['runtime']),
             'rootDependencies': [dict(requested=gav, constraint=False, resolved=gav not in declared,
                                       selected=None if gav in declared else gav, **{'from': 'root project :'})
                                  for gav in declared + anchors(case['runtime'])],
             'selectedComponents': [{'coordinate': coordinate,
                                     'selectionReasons': [{'cause': 'REQUESTED', 'description': 'requested'}]}
                                    for coordinate in anchors(case['runtime'])],
             'unresolved': failures}
    output = "FAILURE: Build failed with an exception.\n\n* What went wrong:\n"
    output += "Execution failed for task ':resolveDualAdapters'.\n"
    output += "Could not resolve all files for configuration ':dualAdapterRuntime'.\n"
    output += '\n'.join(entry['message'] for failure in failures
                        for entry in failure['failureMessages'])
    output += '\n\nBUILD FAILED in 1s\n'
    return output, graph


def maven_fixture(case):
    def node(coordinate, children=None):
        group, artifact, version = coordinate.split(':')
        return {'groupId': group, 'artifactId': artifact, 'version': version,
                'type': 'jar', 'scope': 'compile', 'children': children or []}
    declared = [node(f'{GROUP}:{module}:0.2.0') for module in case['order']]
    declared[0]['children'].append(node(f'{GROUP}:routecontract-core:0.2.0'))
    tree = node('io.github.ym0506.routecontract.examples:dual-resolver-boundary-consumer:0.2.0-fixture',
                declared + [node(coordinate) for coordinate in anchors(case['runtime'])]
                + [node(f'{SS_GROUP}:shardingsphere-infra-common:{case["runtime"]}')])
    banned = f'{GROUP}:{ADAPTERS[opposite(case["runtime"])]}:jar:0.2.0'
    output = (
        '[INFO] --- enforcer:3.6.3:enforce (reject-opposite-adapter) @ dual-resolver-boundary-consumer ---\n'
        '[INFO] Rule 0: org.apache.maven.enforcer.rules.version.RequireJavaVersion passed\n'
        '[INFO] BUILD FAILURE\n'
        '[ERROR] Failed to execute goal org.apache.maven.plugins:maven-enforcer-plugin:3.6.3:enforce '
        '(reject-opposite-adapter) on project dual-resolver-boundary-consumer:\n'
        '[ERROR] Rule 1: org.apache.maven.enforcer.rules.dependency.BannedDependencies failed with message:\n'
        '[ERROR] io.github.ym0506.routecontract.examples:dual-resolver-boundary-consumer:jar:0.2.0-fixture\n'
        f'[ERROR]    {banned}:compile <--- banned via the exclude/include list\n'
        '[ERROR]\n[ERROR] -> [Help 1]\n')
    return output, tree, banned


def guard_fixture(case):
    """Synthetic loaded-origin report; no files or classloader are measured here."""
    runtime = case['observedRuntime']
    def artifact(coordinate):
        _, module, version = coordinate.split(':')
        contents = ('synthetic-not-executed:' + coordinate).encode()
        return {'coordinate': coordinate, 'path': f'/synthetic/no-execution/{module}-{version}.jar',
                'sha256': hashlib.sha256(contents).hexdigest(), 'byteCount': len(contents)}
    expected = {
        'pid': 27183, 'parentPid': 27180, 'userHome': '/synthetic/no-execution/private-home',
        'core': artifact(f'{GROUP}:routecontract-core:0.2.0'),
        'adapter': artifact(f'{GROUP}:{case["adapter"]}:0.2.0'),
        'shardingSphereJars': [artifact(coordinate) for coordinate in sorted(
            anchors(runtime) + [f'{SS_GROUP}:shardingsphere-infra-common:{runtime}'])],
    }
    classes = [
        'org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook',
        ('org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader' if runtime == '5.5.2'
         else 'org.apache.shardingsphere.infra.spi.ShardingSphereSPI'),
        ('org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties' if runtime == '5.5.2'
         else 'org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties'),
    ]
    report = copy.deepcopy(expected)
    report.update({
        'schemaVersion': 1, 'adapterRuntime': case['runtime'], 'observedRuntime': runtime,
        'currentApi': 'io.github.ym0506.routecontract.api.RouteContract',
        'javaFeature': 17, 'javaVersion': '17.0.16', 'preferIPv4Stack': True,
        'anchors': [dict(artifact(coordinate), role=role, className=class_name,
                         implementationVersion=runtime)
                    for coordinate, role, class_name in zip(anchors(runtime),
                                                           ('executor', 'spi', 'database'), classes)],
        'shardingSphereCoordinates': sorted(item['coordinate'] for item in expected['shardingSphereJars']),
        'actionInvoked': False,
        'diagnosticCode': 'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME',
        'diagnosticMessage': f'RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: exact adapter {case["runtime"]} observed {runtime}',
        'exceptionType': 'java.lang.IllegalStateException',
    })
    return report, expected


class BoundaryPlanTest(unittest.TestCase):
    def test_plan_contains_exactly_eight_dual_orders_and_two_opposite_runtime_guards(self):
        plan = MODULE.fixed_plan()
        self.assertEqual(10, len(plan))
        self.assertEqual(10, len({case['id'] for case in plan}))
        self.assertEqual(
            {f'{tool}-{runtime}-{order}' for tool in ('gradle', 'maven')
             for runtime in ADAPTERS for order in ('selected-first', 'opposite-first')}
            | {f'maven-{runtime}-runtime-guard' for runtime in ADAPTERS},
            {case['id'] for case in plan})
        self.assertTrue(all(isinstance(case['id'], str) and case['id'] for case in plan))
        for tool in ('gradle', 'maven'):
            for runtime, adapter in ADAPTERS.items():
                with self.subTest(tool=tool, runtime=runtime):
                    cases = [case for case in plan if case['tool'] == tool
                             and case['kind'] == 'dual' and case['runtime'] == runtime]
                    other = ADAPTERS[opposite(runtime)]
                    self.assertEqual(2, len(cases))
                    self.assertEqual({(adapter, other), (other, adapter)},
                                     {tuple(case['order']) for case in cases})
                    self.assertTrue(all(case['adapter'] == adapter for case in cases))
                    self.assertTrue(all(case['observedRuntime'] == runtime for case in cases))
        guards = [case for case in plan if case['kind'] == 'runtime-guard']
        self.assertEqual(2, len(guards))
        self.assertEqual(set(ADAPTERS), {case['runtime'] for case in guards})
        for case in guards:
            self.assertEqual('maven', case['tool'])
            self.assertEqual(ADAPTERS[case['runtime']], case['adapter'])
            self.assertEqual(opposite(case['runtime']), case['observedRuntime'])
            self.assertEqual([], case['order'])

    def test_plan_is_deterministic_and_mutating_a_returned_case_does_not_change_it(self):
        expected = copy.deepcopy(MODULE.fixed_plan())
        returned = MODULE.fixed_plan()
        returned[0]['id'] = 'changed-outside-verifier'
        returned[0]['order'].reverse()
        self.assertEqual(expected, MODULE.fixed_plan())

    def test_selection_returns_only_requested_identities_without_expanding_the_plan(self):
        full = MODULE.fixed_plan()
        self.assertEqual(full, MODULE.choose_plan())
        ids = [full[-1]['id'], full[0]['id']]
        selected = MODULE.choose_plan(ids)
        self.assertEqual(2, len(selected))
        self.assertEqual(set(ids), {case['id'] for case in selected})
        self.assertTrue(all(case in full for case in selected))

    def test_duplicate_or_unknown_selection_is_rejected_before_execution(self):
        first = MODULE.fixed_plan()[0]['id']
        for ids in ([first, first], ['unknown-case'], [first, 'unknown-case']):
            with self.subTest(ids=ids), self.assertRaises(MODULE.BoundaryError):
                MODULE.choose_plan(ids)

    def test_template_replaces_repeated_tokens_without_rewriting_literal_text(self):
        text = 'before @@RUNTIME@@ / @@ADAPTER@@ / @@RUNTIME@@ after\n'
        rendered = MODULE.render_template(text, {'RUNTIME': '5.5.2', 'ADAPTER': ADAPTERS['5.5.2']})
        self.assertEqual('before 5.5.2 / routecontract-shardingsphere-5.5.2 / 5.5.2 after\n', rendered)

    def test_template_requires_exactly_the_declared_substitution_keys(self):
        for values in ({}, {'RUNTIME': '5.5.2', 'UNUSED': 'ignored'}, {'runtime': '5.5.2'}):
            with self.subTest(values=values), self.assertRaises(MODULE.BoundaryError):
                MODULE.render_template('@@RUNTIME@@', values)

    def test_template_values_cannot_introduce_or_recursively_expand_another_token(self):
        for value in ('@@OTHER@@', '5.5.2@@RUNTIME@@', '@@'):
            with self.subTest(value=value), self.assertRaises(MODULE.BoundaryError):
                MODULE.render_template('@@RUNTIME@@', {'RUNTIME': value})


class GradleDualCauseTest(unittest.TestCase):
    capabilities = [f'{GROUP}:routecontract-shardingsphere-hook-adapter:1',
                    f'{GROUP}:routecontract-shardingsphere-5.5:0.2.0']

    def cases(self):
        return [case for case in MODULE.fixed_plan() if case['tool'] == 'gradle']

    def verify(self, case, output, graph, code=1, capabilities=None):
        return MODULE.verify_gradle_dual(
            case, code, output, graph, self.capabilities if capabilities is None else capabilities)

    def test_each_order_and_runtime_accepts_native_conflict_on_either_reviewed_capability(self):
        for case in self.cases():
            for capability in self.capabilities:
                with self.subTest(case=case['id'], capability=capability):
                    output, graph = gradle_fixture(case, capability)
                    proof = self.verify(case, output, graph)
                    self.assertEqual('NATIVE_CAPABILITY_REJECTED', proof['result'])
                    self.assertEqual([capability], proof['capabilities'])

    def test_success_or_missing_native_failure_cannot_count_as_resolver_rejection(self):
        case = self.cases()[0]
        output, graph = gradle_fixture(case, self.capabilities[0])
        for code, text in ((0, output), (1, output.replace('BUILD FAILED', 'BUILD SUCCESSFUL')),
                           (1, 'BUILD FAILED in 1s\n'), (137, output)):
            with self.subTest(code=code, output=text), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, text, graph, code)

    def test_report_must_bind_the_case_and_actual_direct_anchor_destinations(self):
        case = self.cases()[0]
        output, graph = gradle_fixture(case, self.capabilities[0])
        mutations = [
            ('schemaVersion', 1), ('tool', 'maven'), ('configuration', 'unrelatedRuntime'),
            ('requestedRuntime', opposite(case['runtime'])), ('routeContractVersion', '0.1.2'),
            ('declaredAdapters', graph['declaredAdapters'][::-1]),
            ('declaredRuntimeAnchors', anchors(opposite(case['runtime']))),
        ]
        for field, value in mutations:
            invalid = copy.deepcopy(graph)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output, invalid)
        for selected in ([], graph['selectedComponents'][:-1],
                         graph['selectedComponents'] + [copy.deepcopy(graph['selectedComponents'][0])]):
            invalid = copy.deepcopy(graph)
            invalid['selectedComponents'] = selected
            with self.subTest(selected=selected), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output, invalid)

    def test_unresolved_selectors_must_be_exactly_both_adapters_without_hidden_other_failures(self):
        case = self.cases()[0]
        output, graph = gradle_fixture(case, self.capabilities[0])
        invalids = []
        missing = copy.deepcopy(graph); missing['unresolved'].pop(); invalids.append(missing)
        duplicate = copy.deepcopy(graph); duplicate['unresolved'].append(copy.deepcopy(duplicate['unresolved'][0])); invalids.append(duplicate)
        unknown = copy.deepcopy(graph)
        unknown['unresolved'].append({'requested': 'other:missing:1', 'attempted': 'other:missing:1',
                                      'from': 'root project :', 'failureMessages': []})
        invalids.append(unknown)
        for field in ('requested', 'attempted'):
            wrong = copy.deepcopy(graph)
            wrong['unresolved'][0][field] = wrong['unresolved'][0][field].replace(':0.2.0', ':0.2.00')
            invalids.append(wrong)
        for invalid in invalids:
            with self.subTest(unresolved=invalid['unresolved']), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output, invalid)

    def test_each_adapter_cause_must_bind_its_own_rejection_to_the_other_adapter(self):
        case = self.cases()[0]
        output, graph = gradle_fixture(case, self.capabilities[0])
        other = graph['declaredAdapters'][1]
        for replacement in ('other:unrelated:0.2.0', graph['declaredAdapters'][0],
                            other + '0', other + '-SNAPSHOT',
                            other + "' (runtimeElements), 'other:unrelated:0.2.0"):
            invalid = copy.deepcopy(graph)
            message = invalid['unresolved'][0]['failureMessages'][1]
            message['message'] = message['message'].replace(other, replacement)
            with self.subTest(replacement=replacement), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output, invalid)
            native_wrong = output.replace("also provided by ['" + other + "'",
                                          "also provided by ['" + replacement + "'")
            with self.subTest(native_provider=replacement), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, native_wrong, graph)
        invalid = copy.deepcopy(graph)
        invalid['unresolved'][0]['failureMessages'] = copy.deepcopy(invalid['unresolved'][1]['failureMessages'])
        with self.assertRaises(MODULE.BoundaryError):
            self.verify(case, output, invalid)

    def test_capability_must_be_published_and_bound_in_both_graph_and_native_output(self):
        case = self.cases()[0]
        output, graph = gradle_fixture(case, self.capabilities[0])
        with self.assertRaises(MODULE.BoundaryError):
            self.verify(case, output, graph, capabilities=[self.capabilities[1]])
        with self.assertRaises(MODULE.BoundaryError):
            self.verify(case, output.replace(self.capabilities[0], self.capabilities[1]), graph)
        unrelated_output = output.replace(graph['declaredAdapters'][1], 'other:unrelated:0.2.0')
        unrelated_output += '\nThe requested adapter was ' + graph['declaredAdapters'][1] + '\n'
        with self.assertRaises(MODULE.BoundaryError):
            self.verify(case, unrelated_output, graph)

    def test_correct_capability_text_cannot_mask_transport_checksum_or_runtime_policy_failure(self):
        case = self.cases()[0]
        output, graph = gradle_fixture(case, self.capabilities[0])
        unrelated = [
            'Could not GET http://127.0.0.1:1234/missing.module. Received status code 404',
            'Dependency verification failed for configuration dualAdapterRuntime: checksum failed',
            'RC_STAGED_RUNTIME_REJECTED: expected 5.5.2; requested org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3',
            'Could not find other:missing:1.',
        ]
        for message in unrelated:
            with self.subTest(message=message):
                with self.assertRaises(MODULE.BoundaryError):
                    self.verify(case, output + message + '\n', graph)
                invalid = copy.deepcopy(graph)
                invalid['unresolved'][0]['failureMessages'].append(
                    {'exceptionType': 'synthetic.UnrelatedFailure', 'message': message})
                with self.assertRaises(MODULE.BoundaryError):
                    self.verify(case, output, invalid)
        invalid = copy.deepcopy(graph)
        invalid['unresolved'][0]['failureMessages'].append(
            {'exceptionType': 'java.lang.NullPointerException',
             'message': 'Cannot invoke a method because an internal component is null'})
        with self.assertRaises(MODULE.BoundaryError):
            self.verify(case, output, invalid)


# Exact native cause strings retained from the FAILED first Gradle attempt.
# This bounded unit projection is not a rerun or a passing reclassification.
# Raw graph SHA256 and audit identity make the source independently inspectable.
RETAINED_FAILED_GRAPH_SHA256 = "b2c02597509be0160c565d475970cf0a9f796b523a8ad345de528e5862b8167d"
RETAINED_STRICT_EDGES = json.loads(r'''
[
  {
    "requested": "org.apache.shardingsphere:shardingsphere-infra-executor:5.5.2",
    "attempted": "org.apache.shardingsphere:shardingsphere-infra-executor:5.5.2",
    "from": "root project :",
    "failureMessages": [
      {
        "exceptionType": "org.gradle.internal.resolve.ModuleVersionResolveException",
        "message": "Could not resolve org.apache.shardingsphere:shardingsphere-infra-executor:5.5.2."
      },
      {
        "exceptionType": "org.gradle.api.GradleException",
        "message": "Cannot find a version of 'org.apache.shardingsphere:shardingsphere-infra-executor' that satisfies the version constraints:\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-executor:5.5.2'\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'io.github.ym0506.routecontract:routecontract-shardingsphere-5.5.2:0.2.0' (runtimeElements) --> 'org.apache.shardingsphere:shardingsphere-infra-executor:{strictly 5.5.2}' because of the following reason: SQLExecutionHook has an exact 5.5.2 binary descriptor\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.2.0' (runtimeElements) --> 'org.apache.shardingsphere:shardingsphere-infra-executor:{strictly 5.5.3}' because of the following reason: SQLExecutionHook has an exact 5.5.3 binary descriptor\n"
      }
    ]
  },
  {
    "requested": "org.apache.shardingsphere:shardingsphere-infra-spi:5.5.2",
    "attempted": "org.apache.shardingsphere:shardingsphere-infra-spi:5.5.2",
    "from": "root project :",
    "failureMessages": [
      {
        "exceptionType": "org.gradle.internal.resolve.ModuleVersionResolveException",
        "message": "Could not resolve org.apache.shardingsphere:shardingsphere-infra-spi:5.5.2."
      },
      {
        "exceptionType": "org.gradle.api.GradleException",
        "message": "Cannot find a version of 'org.apache.shardingsphere:shardingsphere-infra-spi' that satisfies the version constraints:\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.2'\n   Constraint path: 'root project :' (dualAdapterRuntime) --> 'io.github.ym0506.routecontract:routecontract-shardingsphere-5.5.2:0.2.0' (runtimeElements) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:{strictly 5.5.2}' because of the following reason: the runtime-adapter preflight requires the exact 5.5.2 SPI anchor\n   Constraint path: 'root project :' (dualAdapterRuntime) --> 'io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.2.0' (runtimeElements) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:{strictly 5.5.3}' because of the following reason: the runtime-adapter preflight requires the exact 5.5.3 SPI anchor\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-database-core:5.5.2' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-util:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3'\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-executor:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-rewrite-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-route-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-session:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-binder-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-parser-sql-engine-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-parser-sql-spi:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3'\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-executor:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-rewrite-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-sql-translator-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-mode-node:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-common:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-data-source-pool-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-database-connector-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3'\n"
      }
    ]
  },
  {
    "requested": "org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3",
    "attempted": "org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3",
    "from": "org.apache.shardingsphere:shardingsphere-infra-util:5.5.3",
    "failureMessages": [
      {
        "exceptionType": "org.gradle.internal.resolve.ModuleVersionResolveException",
        "message": "Could not resolve org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3."
      },
      {
        "exceptionType": "org.gradle.api.GradleException",
        "message": "Cannot find a version of 'org.apache.shardingsphere:shardingsphere-infra-spi' that satisfies the version constraints:\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.2'\n   Constraint path: 'root project :' (dualAdapterRuntime) --> 'io.github.ym0506.routecontract:routecontract-shardingsphere-5.5.2:0.2.0' (runtimeElements) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:{strictly 5.5.2}' because of the following reason: the runtime-adapter preflight requires the exact 5.5.2 SPI anchor\n   Constraint path: 'root project :' (dualAdapterRuntime) --> 'io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.2.0' (runtimeElements) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:{strictly 5.5.3}' because of the following reason: the runtime-adapter preflight requires the exact 5.5.3 SPI anchor\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-database-core:5.5.2' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-util:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3'\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-executor:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-rewrite-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-route-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-session:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-binder-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-parser-sql-engine-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-parser-sql-spi:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3'\n   Dependency path: 'root project :' (dualAdapterRuntime) --> 'org.apache.shardingsphere:shardingsphere-infra-executor:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-rewrite-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-sql-translator-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-mode-node:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-common:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-data-source-pool-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-database-connector-core:5.5.3' (default) --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3'\n"
      }
    ]
  }
]
''')
RETAINED_GUAVA_EDGE = json.loads(r'''
{
  "requested": "com.google.guava:guava:32.1.2-jre",
  "attempted": "com.google.guava:guava:32.1.2-jre",
  "from": "org.apache.shardingsphere:shardingsphere-infra-database-core:5.5.2",
  "failureMessages": [
    {
      "exceptionType": "org.gradle.internal.resolve.ModuleVersionResolveException",
      "message": "Could not resolve com.google.guava:guava:32.1.2-jre."
    },
    {
      "exceptionType": "org.gradle.internal.component.resolution.failure.exception.VariantSelectionByAttributesException",
      "message": "No matching variant of com.google.guava:guava:33.4.6-jre was found. The consumer was configured to find attribute 'org.gradle.category' with value 'library', attribute 'org.gradle.dependency.bundling' with value 'external', attribute 'org.gradle.jvm.version' with value '17', attribute 'org.gradle.libraryelements' with value 'jar', attribute 'org.gradle.usage' with value 'java-runtime' but:\n  - Variant 'androidApiElements' declares attribute 'org.gradle.category' with value 'library', attribute 'org.gradle.dependency.bundling' with value 'external', attribute 'org.gradle.libraryelements' with value 'jar':\n      - Incompatible because this component declares attribute 'org.gradle.jvm.version' with value '8', attribute 'org.gradle.usage' with value 'java-api' and the consumer needed attribute 'org.gradle.jvm.version' with value '17', attribute 'org.gradle.usage' with value 'java-runtime'\n  - Variant 'androidRuntimeElements' declares attribute 'org.gradle.category' with value 'library', attribute 'org.gradle.dependency.bundling' with value 'external', attribute 'org.gradle.libraryelements' with value 'jar', attribute 'org.gradle.usage' with value 'java-runtime':\n      - Incompatible because this component declares attribute 'org.gradle.jvm.version' with value '8' and the consumer needed attribute 'org.gradle.jvm.version' with value '17'\n  - Variant 'jreApiElements' declares attribute 'org.gradle.category' with value 'library', attribute 'org.gradle.dependency.bundling' with value 'external', attribute 'org.gradle.libraryelements' with value 'jar':\n      - Incompatible because this component declares attribute 'org.gradle.jvm.version' with value '8', attribute 'org.gradle.usage' with value 'java-api' and the consumer needed attribute 'org.gradle.jvm.version' with value '17', attribute 'org.gradle.usage' with value 'java-runtime'\n  - Variant 'jreRuntimeElements' declares attribute 'org.gradle.category' with value 'library', attribute 'org.gradle.dependency.bundling' with value 'external', attribute 'org.gradle.libraryelements' with value 'jar', attribute 'org.gradle.usage' with value 'java-runtime':\n      - Incompatible because this component declares attribute 'org.gradle.jvm.version' with value '8' and the consumer needed attribute 'org.gradle.jvm.version' with value '17'"
    }
  ]
}
''')
RETAINED_REVIEWED_CONSTRAINTS = json.loads(r'''
{
  "org.apache.shardingsphere:shardingsphere-infra-executor": [
    {
      "adapter": "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5.2:0.2.0",
      "version": "5.5.2",
      "kind": "Dependency",
      "reason": "SQLExecutionHook has an exact 5.5.2 binary descriptor",
      "sourceMetadataSha256": "b3dd0230824a5bf442069e183074ca24e610e0c3eebbac7dc968557205cc8dac"
    },
    {
      "adapter": "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.2.0",
      "version": "5.5.3",
      "kind": "Dependency",
      "reason": "SQLExecutionHook has an exact 5.5.3 binary descriptor",
      "sourceMetadataSha256": "dca55d4f57ef7b8b9d577abc37858ba3a53b901d617086640b50befcd1a1ac96"
    }
  ],
  "org.apache.shardingsphere:shardingsphere-infra-spi": [
    {
      "adapter": "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5.2:0.2.0",
      "version": "5.5.2",
      "kind": "Constraint",
      "reason": "the runtime-adapter preflight requires the exact 5.5.2 SPI anchor",
      "sourceMetadataSha256": "b3dd0230824a5bf442069e183074ca24e610e0c3eebbac7dc968557205cc8dac"
    },
    {
      "adapter": "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.2.0",
      "version": "5.5.3",
      "kind": "Constraint",
      "reason": "the runtime-adapter preflight requires the exact 5.5.3 SPI anchor",
      "sourceMetadataSha256": "dca55d4f57ef7b8b9d577abc37858ba3a53b901d617086640b50befcd1a1ac96"
    }
  ]
}
''')


def intrinsic_fixture():
    case = next(c for c in MODULE.fixed_plan() if c['id'] == 'gradle-5.5.2-selected-first')
    output, graph = gradle_fixture(case, f'{GROUP}:routecontract-shardingsphere-5.5:0.2.0')
    graph['unresolved'] += copy.deepcopy(RETAINED_STRICT_EDGES)
    graph['selectedComponents'] = [
        {'coordinate': f'{SS_GROUP}:shardingsphere-infra-database-core:5.5.2', 'selectionReasons': []},
        {'coordinate': f'{SS_GROUP}:shardingsphere-infra-util:5.5.3', 'selectionReasons': []}]
    for edge in graph['rootDependencies']:
        if any(edge['requested'] == item['requested'] for item in RETAINED_STRICT_EDGES):
            edge.update(resolved=False, selected=None)
    raw_causes = '\n'.join(message['message'] for edge in RETAINED_STRICT_EDGES
                           for message in edge['failureMessages'])
    output = output.replace('BUILD FAILED in 1s', raw_causes + '\nBUILD FAILED in 1s')
    return case, output, graph, copy.deepcopy(RETAINED_REVIEWED_CONSTRAINTS)


class GradleIntrinsicCollisionTest(unittest.TestCase):
    def verify(self, case, output, graph, metadata):
        return MODULE.verify_gradle_dual(case, 1, output, graph,
            [f'{GROUP}:routecontract-shardingsphere-5.5:0.2.0'], published_constraints=metadata)

    def test_retained_intrinsic_causes_are_separate_from_both_required_capability_causes(self):
        case, output, graph, metadata = intrinsic_fixture()
        proof = self.verify(case, output, graph, metadata)
        self.assertEqual('NATIVE_CAPABILITY_AND_INTRINSIC_STRICT_REJECTED', proof['result'])
        self.assertEqual(3, len(proof['intrinsicStrictCollisions']))
        self.assertEqual(2, len(proof['capabilityUnresolvedSelectors']))
        self.assertEqual(5, len(proof['actualRootRequests']))
        self.assertIs(False, proof['coherentResolvedRuntimeClaimed'])

    def test_retained_guava_failure_still_prevents_acceptance(self):
        case, output, graph, metadata = intrinsic_fixture()
        graph['unresolved'].append(copy.deepcopy(RETAINED_GUAVA_EDGE))
        output += '\n'.join(m['message'] for m in RETAINED_GUAVA_EDGE['failureMessages'])
        with self.assertRaises(MODULE.BoundaryError):
            self.verify(case, output, graph, metadata)

    def test_strict_rejection_cannot_replace_either_adapter_capability(self):
        case, output, graph, metadata = intrinsic_fixture()
        graph['unresolved'] = [e for e in graph['unresolved'] if e['requested'] != graph['declaredAdapters'][0]]
        with self.assertRaises(MODULE.BoundaryError):
            self.verify(case, output, graph, metadata)

    def test_only_the_two_reviewed_anchor_modules_versions_and_reasons_are_allowed(self):
        case, output, graph, metadata = intrinsic_fixture()
        for old, new in (('shardingsphere-infra-executor', 'shardingsphere-infra-common'),
                         ('5.5.2', '5.5.20'),
                         ('SQLExecutionHook has an exact 5.5.2 binary descriptor', 'unreviewed reason')):
            changed = json.loads(json.dumps(graph).replace(old, new))
            text = output.replace(old, new)
            with self.subTest(change=(old, new)), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, text, changed, metadata)

    def test_both_exact_metadata_paths_are_required_in_each_strict_cause(self):
        case, output, graph, metadata = intrinsic_fixture()
        for adapter in ADAPTERS.values():
            bad = copy.deepcopy(graph)
            edge = next(e for e in bad['unresolved'] if e['requested'].startswith(SS_GROUP + ':'))
            edge['failureMessages'][1]['message'] = '\n'.join(
                line for line in edge['failureMessages'][1]['message'].splitlines()
                if f"'{GROUP}:{adapter}:0.2.0'" not in line) + '\n'
            with self.subTest(adapter=adapter), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output, bad, metadata)
        for changed_metadata in ({}, {key: values[:1] for key, values in metadata.items()}):
            with self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output, graph, changed_metadata)

    def test_extra_or_duplicate_strict_cause_and_foreign_paths_are_rejected(self):
        case, output, graph, metadata = intrinsic_fixture()
        invalids = []
        duplicate = copy.deepcopy(graph); duplicate['unresolved'].append(copy.deepcopy(duplicate['unresolved'][-1])); invalids.append(duplicate)
        cause = copy.deepcopy(graph)
        cause['unresolved'][-1]['failureMessages'].append({'exceptionType':'java.lang.NullPointerException','message':'unrelated cause'})
        invalids.append(cause)
        path = copy.deepcopy(graph)
        path['unresolved'][-1]['failureMessages'][1]['message'] += "   Dependency path: 'root project :' (dualAdapterRuntime) --> 'other:foreign:5.5.3' --> 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3'\n"
        invalids.append(path)
        parent = copy.deepcopy(graph)
        parent['unresolved'][-1]['from'] = 'com.google.guava:guava:33.4.6-jre'
        parent['selectedComponents'].append({'coordinate':'com.google.guava:guava:33.4.6-jre','selectionReasons':[]})
        invalids.append(parent)
        cap = copy.deepcopy(graph)
        cap['unresolved'][0]['failureMessages'][1]['message'] += '\n   another unbound rejection'
        invalids.append(cap)
        for invalid in invalids:
            with self.subTest(invalid=invalid), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output, invalid, metadata)

    def test_actual_five_direct_requests_are_required_and_cannot_be_constraints(self):
        case, output, graph, metadata = intrinsic_fixture()
        for mutation in ('missing', 'extra', 'constraint', 'wrong-version', 'resolved-adapter', 'unbound-selected'):
            invalid=copy.deepcopy(graph); edges=invalid['rootDependencies']
            if mutation=='missing': edges.pop()
            elif mutation=='extra': edges.append(copy.deepcopy(edges[-1]))
            elif mutation=='constraint': edges[0]['constraint']=True
            elif mutation=='wrong-version': edges[-1]['requested']=edges[-1]['requested'].replace('5.5.2','5.5.3')
            elif mutation=='resolved-adapter': edges[0].update(resolved=True,selected=edges[0]['requested'])
            else: edges[-1]['selected']='other:foreign:1'
            with self.subTest(mutation=mutation), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output, invalid, metadata)

    def test_retained_java_base_runtime_variant_paths_keep_all_exact_cause_restrictions(self):
        # Recorded native graph SHA256: 7bcbefb518c2d43f1ddd237884644b6275b176156dc2bbef9e62382fb584dbd6
        # Derive the new native POM path spelling from prior retained causes, then
        # bind each complete cause to its actual newly retained message digest.
        expected_message_hashes = {'org.apache.shardingsphere:shardingsphere-infra-executor:5.5.2': 'f4f355efb1d57be6aa5aabdb78902efb340fe53054751db3676b89d31c9fea89', 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.2': '02bb6640b7e5b20dcec8dd8c787c0c1c8a878b7e75e49f38a7a6a697f34749c8', 'org.apache.shardingsphere:shardingsphere-infra-spi:5.5.3': '02bb6640b7e5b20dcec8dd8c787c0c1c8a878b7e75e49f38a7a6a697f34749c8'}
        case, output, graph, metadata = intrinsic_fixture()
        for node in graph['unresolved']:
            if node['requested'] in expected_message_hashes:
                message = node['failureMessages'][1]['message'].replace(' (default)', ' (runtime)')
                self.assertEqual(expected_message_hashes[node['requested']], hashlib.sha256(message.encode()).hexdigest())
                node['failureMessages'][1]['message'] = message
        output = output.replace(' (default)', ' (runtime)')
        proof = self.verify(case, output, graph, metadata)
        self.assertEqual('NATIVE_CAPABILITY_AND_INTRINSIC_STRICT_REJECTED', proof['result'])
        self.assertEqual(3, len(proof['intrinsicStrictCollisions']))
        for variant in ('api', 'custom-runtime'):
            invalid = json.loads(json.dumps(graph).replace(' (runtime)', f' ({variant})'))
            with self.subTest(variant=variant), self.assertRaises(MODULE.BoundaryError):
                self.verify(case, output.replace(' (runtime)', f' ({variant})'), invalid, metadata)
        invalid = json.loads(json.dumps(graph).replace(' (runtimeElements)', ' (runtime)'))
        with self.assertRaises(MODULE.BoundaryError):
            self.verify(case, output.replace(' (runtimeElements)', ' (runtime)'), invalid, metadata)

    def test_java_base_schema_does_not_enable_source_sets_or_change_ordinary_edges(self):
        text=(ROOT/'examples/dual-resolver-boundary-consumer/gradle/build.gradle.template').read_text()
        self.assertIn("id 'java-base'", text)
        for forbidden in ("id 'java'", 'sourceSets', 'isTransitive = false', 'transitive = false', 'dependencySubstitution', 'requireCapability'):
            self.assertNotIn(forbidden, text)

class MavenDualCauseTest(unittest.TestCase):
    def cases(self):
        return [case for case in MODULE.fixed_plan()
                if case['tool'] == 'maven' and case['kind'] == 'dual']

    def test_each_order_and_runtime_retains_exact_banned_adapter_and_selected_graph(self):
        for case in self.cases():
            with self.subTest(case=case['id']):
                output, tree, banned = maven_fixture(case)
                proof = MODULE.verify_maven_dual(case, 1, output, tree)
                self.assertEqual('NATIVE_ENFORCER_REJECTED', proof['result'])
                self.assertEqual(banned.replace(':jar:', ':'), proof['bannedCoordinate'])
                selected = proof['selectedCoordinates']
                self.assertEqual(sorted(set(selected)), selected)
                self.assertTrue(set(anchors(case['runtime'])).issubset(selected))
                self.assertTrue({f'{GROUP}:{module}:0.2.0' for module in
                                 ('routecontract-core', *ADAPTERS.values())}.issubset(selected))

    def test_native_validate_failure_requires_exact_enforcer_version_and_rule(self):
        case = self.cases()[0]
        output, tree, _ = maven_fixture(case)
        for code, text in (
                (0, output), (137, output), (1, output.replace('BUILD FAILURE', 'BUILD SUCCESS')),
                (1, output.replace('3.6.3', '3.6.2')),
                (1, output.replace('BannedDependencies', 'DependencyConvergence'))):
            with self.subTest(code=code, output=text), self.assertRaises(MODULE.BoundaryError):
                MODULE.verify_maven_dual(case, code, text, tree)

    def test_banned_coordinate_must_be_exact_and_inside_its_failure_section(self):
        case = self.cases()[0]
        output, tree, banned = maven_fixture(case)
        banned_line = f'[ERROR]    {banned}:compile <--- banned via the exclude/include list\n'
        without_banned_line = output.replace(banned_line, '')
        invalids = [output.replace(banned, banned + '0'),
                    output.replace(banned, banned + '-SNAPSHOT'),
                    output.replace(banned, 'other:library:jar:1') + '\n[INFO] requested ' + banned,
                    output.replace('banned via the exclude/include list', 'mentioned but not banned'),
                    output.replace('BannedDependencies failed', 'BannedDependencies passed'),
                    banned_line + without_banned_line,
                    without_banned_line + '[INFO] Archived earlier failure:\n' + banned_line]
        for text in invalids:
            with self.subTest(output=text), self.assertRaises(MODULE.BoundaryError):
                MODULE.verify_maven_dual(case, 1, text, tree)

    def test_correct_banned_line_cannot_hide_additional_rules_or_resolution_failures(self):
        case = self.cases()[0]
        output, tree, _ = maven_fixture(case)
        for extra in (
                '[ERROR] Rule 2: org.apache.maven.enforcer.rules.dependency.DependencyConvergence failed with message:',
                '[ERROR]    other:unrelated:jar:1:compile <--- banned via the exclude/include list',
                '[ERROR] Could not transfer artifact other:missing:jar:1 from/to reviewed-staging',
                '[ERROR] Failed to collect dependencies at other:missing:jar:1',
                '[ERROR] Checksum validation failed, expected abcd but is dcba',
                '[INFO] --- compiler:3.14.1:compile (default-compile) @ dual-resolver-boundary-consumer ---'):
            with self.subTest(extra=extra), self.assertRaises(MODULE.BoundaryError):
                MODULE.verify_maven_dual(case, 1, output + extra + '\n', tree)

    def test_selected_graph_requires_both_ordered_adapters_transitive_core_and_coherent_ss(self):
        case = self.cases()[0]
        output, tree, _ = maven_fixture(case)
        invalids = []
        missing = copy.deepcopy(tree); missing['children'].pop(1); invalids.append(missing)
        reordered = copy.deepcopy(tree); reordered['children'][:2] = reordered['children'][:2][::-1]; invalids.append(reordered)
        no_core = copy.deepcopy(tree); no_core['children'][0]['children'] = []; invalids.append(no_core)
        wrong_core = copy.deepcopy(tree); wrong_core['children'][0]['children'][0]['version'] = '0.1.2'; invalids.append(wrong_core)
        no_anchor = copy.deepcopy(tree); no_anchor['children'].pop(2); invalids.append(no_anchor)
        extra_first_party = copy.deepcopy(tree)
        extra_first_party['children'].append({'groupId': GROUP, 'artifactId': 'unexpected-module',
                                              'version': '0.2.0', 'type': 'jar', 'children': []})
        invalids.append(extra_first_party)
        for index in (2, -1):
            mixed = copy.deepcopy(tree); mixed['children'][index]['version'] = opposite(case['runtime']); invalids.append(mixed)
        for invalid in invalids:
            with self.subTest(tree=invalid), self.assertRaises(MODULE.BoundaryError):
                MODULE.verify_maven_dual(case, 1, output, invalid)


class RuntimeGuardReportTest(unittest.TestCase):
    def cases(self):
        return [case for case in MODULE.fixed_plan() if case['kind'] == 'runtime-guard']

    def test_both_coherent_opposite_runtime_reports_preserve_the_bounded_guard_result(self):
        for case in self.cases():
            with self.subTest(case=case['id']):
                report, expected = guard_fixture(case)
                proof = MODULE.verify_guard_report(case, report, expected)
                self.assertEqual('COHERENT_OPPOSITE_RUNTIME_REJECTED', proof['result'])

    def test_actual_action_execution_or_unbound_external_process_identity_is_rejected(self):
        case = self.cases()[0]
        report, expected = guard_fixture(case)
        for field, value in (('actionInvoked', True), ('actionInvoked', 'false'), ('actionInvoked', 0),
                             ('pid', expected['pid'] + 1), ('parentPid', expected['parentPid'] + 1),
                             ('userHome', '/synthetic/another-home'), ('preferIPv4Stack', False),
                             ('javaFeature', 21), ('javaVersion', '21.0.8')):
            invalid = copy.deepcopy(report); invalid[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(MODULE.BoundaryError):
                MODULE.verify_guard_report(case, invalid, expected)

    def test_guard_must_use_current_api_and_exact_coherent_unsupported_runtime_diagnostic(self):
        case = self.cases()[0]
        report, expected = guard_fixture(case)
        mutations = (
            ('currentApi', 'io.github.ym0506.routecontract.RouteContract'),
            ('adapterRuntime', case['observedRuntime']), ('observedRuntime', case['runtime']),
            ('diagnosticCode', 'RC_MIXED_SHARDINGSPHERE_RUNTIME'),
            ('diagnosticMessage', report['diagnosticMessage'] + ' with unavailable anchors'),
            ('exceptionType', 'java.lang.LinkageError'),
            ('cause', {'exceptionType': 'java.lang.NoClassDefFoundError', 'message': 'missing'}),
            ('suppressed', [{'exceptionType': 'java.lang.LinkageError'}]),
        )
        for field, value in mutations:
            invalid = copy.deepcopy(report); invalid[field] = value
            with self.subTest(field=field), self.assertRaises(MODULE.BoundaryError):
                MODULE.verify_guard_report(case, invalid, expected)
        missing = copy.deepcopy(report); missing.pop('diagnosticCode')
        with self.assertRaises(MODULE.BoundaryError):
            MODULE.verify_guard_report(case, missing, expected)

    def test_loaded_core_and_adapter_origins_must_match_measured_receipt_records(self):
        case = self.cases()[0]
        report, expected = guard_fixture(case)
        for owner in ('core', 'adapter'):
            for field, value in (('path', '/synthetic/unreviewed.jar'), ('sha256', '0' * 64),
                                 ('byteCount', 1), ('coordinate', f'{GROUP}:routecontract-core:0.1.2')):
                invalid = copy.deepcopy(report); invalid[owner][field] = value
                with self.subTest(owner=owner, field=field), self.assertRaises(MODULE.BoundaryError):
                    MODULE.verify_guard_report(case, invalid, expected)

    def test_three_loaded_anchors_require_exact_roles_classes_versions_and_jar_origins(self):
        for case in self.cases():
            report, expected = guard_fixture(case)
            invalids = []
            missing = copy.deepcopy(report); missing['anchors'].pop(); invalids.append(missing)
            duplicate = copy.deepcopy(report); duplicate['anchors'][1] = copy.deepcopy(duplicate['anchors'][0]); invalids.append(duplicate)
            for field, value in (('role', 'unknown'), ('className', 'synthetic.UnrelatedClass'),
                                 ('implementationVersion', case['runtime']), ('path', '/synthetic/other.jar'),
                                 ('sha256', '0' * 64), ('byteCount', 1),
                                 ('coordinate', anchors(case['runtime'])[0])):
                invalid = copy.deepcopy(report); invalid['anchors'][0][field] = value; invalids.append(invalid)
            for invalid in invalids:
                with self.subTest(case=case['id'], anchors=invalid['anchors']), self.assertRaises(MODULE.BoundaryError):
                    MODULE.verify_guard_report(case, invalid, expected)

    def test_entire_selected_ss_set_and_consumed_bytes_cannot_omit_or_add_a_component(self):
        case = self.cases()[0]
        report, expected = guard_fixture(case)
        invalids = []
        missing = copy.deepcopy(report); missing['shardingSphereJars'].pop(); invalids.append(missing)
        hidden = copy.deepcopy(report); hidden['shardingSphereCoordinates'].pop(); invalids.append(hidden)
        extra = copy.deepcopy(report); extra['shardingSphereCoordinates'].append(f'{SS_GROUP}:extra:{case["observedRuntime"]}'); invalids.append(extra)
        changed = copy.deepcopy(report); changed['shardingSphereJars'][0]['sha256'] = '0' * 64; invalids.append(changed)
        duplicate = copy.deepcopy(report); duplicate['shardingSphereJars'].append(copy.deepcopy(duplicate['shardingSphereJars'][0])); invalids.append(duplicate)
        for invalid in invalids:
            with self.subTest(report=invalid), self.assertRaises(MODULE.BoundaryError):
                MODULE.verify_guard_report(case, invalid, expected)


class MavenGraphRetentionTest(unittest.TestCase):
    def collect_until_enforcer(self, root, *, overwrite_graph=False):
        case = MODULE.fixed_plan()[4]
        _, tree, _ = maven_fixture(case)
        directory = root / case['id']
        consumer = MODULE.prepare_case(directory, case)
        graph = consumer / 'negative-graph.json'
        calls = []

        class ReachedEnforcer(Exception):
            pass

        def native(command, cwd, environment, evidence, name, **kwargs):
            calls.append((list(command), name))
            if command[-1] == 'validate':
                raise ReachedEnforcer()
            output_file = next((Path(arg.split('=', 1)[1]) for arg in command
                                if arg.startswith('-DoutputFile=')), None)
            # Actual plugin 3.11.0 tree/resolve both bind ${outputFile}, with
            # appendOutput=false. Retained overwritten output SHA-256:
            # 6cbaf86647e6756a986e64b4d697ba76267f6b769b367075a620e2c82c65f91d.
            for goal in command:
                if goal == MODULE.maven.DEPENDENCY_TREE:
                    output_file.write_text(json.dumps(tree))
                elif goal == MODULE.a24.DEPENDENCY_RESOLVE:
                    if output_file:
                        output_file.write_text('The following files have been resolved:\n')
                    if overwrite_graph:
                        graph.write_text('The following files have been resolved:\n')
            return '[INFO] BUILD SUCCESS\n', {'exitCode': 0}

        with mock.patch.object(MODULE.a24.mirror, 'serve_repository',
                               return_value=nullcontext('http://127.0.0.1:12345/')), \
                mock.patch.object(MODULE, 'native', side_effect=native):
            expected = MODULE.BoundaryError if overwrite_graph else ReachedEnforcer
            with self.assertRaises(expected):
                MODULE.execute_case(case, directory, root / 'unused-repository', None,
                                    root / 'unused-java17', root / 'unused-maven', None)
        return calls, graph, tree

    def test_tree_and_resolve_cannot_share_an_invocation_or_overwrite_json(self):
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-graph-unit-') as temporary:
            calls, graph, tree = self.collect_until_enforcer(Path(temporary).resolve())
            self.assertEqual(3, len(calls))  # two collection commands, then the untouched Enforcer boundary
            tree_command, resolve_command = calls[0][0], calls[1][0]
            self.assertIn(MODULE.maven.DEPENDENCY_TREE, tree_command)
            self.assertNotIn(MODULE.a24.DEPENDENCY_RESOLVE, tree_command)
            self.assertIn(MODULE.a24.DEPENDENCY_RESOLVE, resolve_command)
            self.assertNotIn(MODULE.maven.DEPENDENCY_TREE, resolve_command)
            self.assertIn('--strict-checksums', tree_command)
            self.assertIn('--strict-checksums', resolve_command)
            self.assertNotEqual(calls[0][1], calls[1][1])
            tree_output = next(arg for arg in tree_command if arg.startswith('-DoutputFile='))
            resolve_output = next(arg for arg in resolve_command if arg.startswith('-DoutputFile='))
            self.assertNotEqual(tree_output, resolve_output)
            self.assertEqual(tree, json.loads(graph.read_text()))

    def test_graph_mutation_during_separate_resolution_stops_before_enforcer(self):
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-graph-unit-') as temporary:
            calls, _, _ = self.collect_until_enforcer(Path(temporary).resolve(), overwrite_graph=True)
            self.assertEqual(2, len(calls))
            self.assertTrue(all(command[-1] != 'validate' for command, _ in calls))


class ReviewedRepositoryCopyTest(unittest.TestCase):
    algorithms = ('md5', 'sha1', 'sha256', 'sha512')

    def repository(self, root):
        repository = root / 'original'
        for module in ('routecontract-core', 'routecontract-shardingsphere-5.5',
                       'routecontract-shardingsphere-5.5.2'):
            for extension in ('jar', 'pom', 'module'):
                path = repository / 'io/github/ym0506/routecontract' / module / '0.2.0' / f'{module}-0.2.0.{extension}'
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = f'Synthetic receipt-pinned {module}.{extension}\n'.encode()
                path.write_bytes(payload)
                for index, algorithm in enumerate(self.algorithms):
                    # Existing sidecar bytes, including a final newline, must be copied verbatim.
                    sidecar = hashlib.new(algorithm, payload).hexdigest().encode() + (b'\n' if index % 2 else b'')
                    Path(str(path) + '.' + algorithm).write_bytes(sidecar)
        return repository, MODULE.staged.repository_receipt(repository)

    def test_copy_retains_exact_verified_sidecars_needed_by_strict_maven(self):
        # Actual failed Maven log SHA-256:
        # 786949d10506c8c2d09cfabd03c19d220114e2a89bd8bae33d33efbe5421411d.
        # Both adapter POM GETs were 200; their .sha1/.md5 GETs were 404, causing
        # "Checksum validation failed, no checksums available" before Enforcer.
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-copy-unit-') as temporary:
            root = Path(temporary).resolve()
            repository, receipt = self.repository(root)
            extra = repository / 'unreviewed-sources.jar'
            extra.write_bytes(b'not in the reviewed receipt')
            Path(str(extra) + '.sha1').write_text(hashlib.sha1(extra.read_bytes()).hexdigest())
            before = MODULE.a24.inventory(repository)
            destination = root / 'copy'
            copied = MODULE.copy_reviewed_repository(repository, receipt, destination)
            for module in ADAPTERS.values():
                pom = f'io/github/ym0506/routecontract/{module}/0.2.0/{module}-0.2.0.pom'
                for algorithm in ('sha1', 'md5'):
                    self.assertTrue((destination / (pom + '.' + algorithm)).is_file(),
                                    'Strict Maven must receive the previously omitted checksum URL')
            payloads, sidecars = copied
            self.assertEqual(9, len(payloads))
            self.assertEqual(36, len(sidecars))
            expected_paths = {item['relativePath'] for item in receipt['artifacts']}
            expected_paths.update(item['relativePath'] + '.' + algorithm
                                  for item in receipt['artifacts'] for algorithm in self.algorithms)
            self.assertEqual(expected_paths, {item['path'] for item in MODULE.a24.inventory(destination)})
            for item in receipt['artifacts']:
                payload = (repository / item['relativePath']).read_bytes()
                self.assertIn(dict(item, byteCount=len(payload)), payloads)
                self.assertEqual(payload, (destination / item['relativePath']).read_bytes())
                for algorithm in self.algorithms:
                    relative = item['relativePath'] + '.' + algorithm
                    source = (repository / relative).read_bytes()
                    self.assertEqual(source, (destination / relative).read_bytes())
                    self.assertIn({'relativePath': relative, 'sha256': hashlib.sha256(source).hexdigest(),
                                   'byteCount': len(source), 'algorithm': algorithm,
                                   'digest': hashlib.new(algorithm, payload).hexdigest(),
                                   'payloadRelativePath': item['relativePath'], 'payloadSha256': item['sha256'],
                                   'origin': 'copied-existing-staging-sidecar'}, sidecars)
            self.assertEqual(before, MODULE.a24.inventory(repository))
            self.assertIn('--strict-checksums', MODULE.maven_command(
                root / 'mvn', root / 'settings', root / 'cache', root / 'home', root / 'consumer'))

    def test_missing_malformed_and_wrong_digests_fail_before_creating_a_copy(self):
        for algorithm in self.algorithms:
            for defect in ('missing', 'wrong-digest', 'wrong-length', 'non-hex', 'filename', 'two-lines'):
                with self.subTest(algorithm=algorithm, defect=defect), tempfile.TemporaryDirectory(
                        prefix='routecontract-dual-copy-unit-') as temporary:
                    root = Path(temporary).resolve()
                    repository, receipt = self.repository(root)
                    item = receipt['artifacts'][-1]
                    sidecar = repository / (item['relativePath'] + '.' + algorithm)
                    valid = sidecar.read_bytes().strip()
                    values = {'wrong-digest': b'0' * len(valid), 'wrong-length': valid[:-1],
                              'non-hex': b'z' * len(valid), 'filename': valid + b'  artifact.jar',
                              'two-lines': valid + b'\n' + valid}
                    if defect == 'missing':
                        sidecar.unlink()
                    else:
                        sidecar.write_bytes(values[defect])
                    before = MODULE.a24.inventory(repository)
                    with self.assertRaises(MODULE.BoundaryError):
                        MODULE.copy_reviewed_repository(repository, receipt, root / 'never-created')
                    self.assertFalse((root / 'never-created').exists())
                    self.assertEqual(before, MODULE.a24.inventory(repository))

    def test_symlink_sidecar_is_rejected_without_creating_a_copy(self):
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-copy-unit-') as temporary:
            root = Path(temporary).resolve()
            repository, receipt = self.repository(root)
            sidecar = repository / (receipt['artifacts'][0]['relativePath'] + '.sha1')
            outside = root / 'external-checksum'
            outside.write_bytes(sidecar.read_bytes())
            sidecar.unlink()
            sidecar.symlink_to(outside)
            with self.assertRaises(MODULE.a24.VerificationError):
                MODULE.copy_reviewed_repository(repository, receipt, root / 'never-created')
            self.assertFalse((root / 'never-created').exists())

    def test_matching_sidecar_cannot_replace_the_reviewed_payload_digest(self):
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-copy-unit-') as temporary:
            root = Path(temporary).resolve()
            repository, receipt = self.repository(root)
            path = repository / receipt['artifacts'][0]['relativePath']
            path.write_bytes(b'changed payload with matching untrusted checksums')
            for algorithm in self.algorithms:
                Path(str(path) + '.' + algorithm).write_text(hashlib.new(algorithm, path.read_bytes()).hexdigest())
            with self.assertRaises(MODULE.staged.VerificationError):
                MODULE.copy_reviewed_repository(repository, receipt, root / 'never-created')
            self.assertFalse((root / 'never-created').exists())


class BoundaryPreparationTest(unittest.TestCase):
    def no_execution(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        for owner, name in ((MODULE.subprocess, 'run'), (MODULE.subprocess, 'Popen'),
                            (MODULE, 'verify_toolchain'), (MODULE, 'execute_case'),
                            (MODULE.a24, 'reviewed_inputs')):
            patched = stack.enter_context(mock.patch.object(
                owner, name, side_effect=AssertionError(f'Unexpected execution boundary: {name}')))
            self.addCleanup(patched.assert_not_called)
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(redirect_stderr(io.StringIO()))
        return stack

    def execution_arguments(self, root):
        return {
            '--repository': str(root / 'unreviewed-repository'),
            '--reviewed-receipt': str(root / 'unreviewed-receipt.json'),
            '--reviewed-receipt-sha256': '1' * 64,
            '--staged-source-revision': '2' * 40,
            '--expected-input-manifest': str(root / 'frozen-inputs.json'),
            '--java17-home': str(root / 'unused-java17'),
            '--maven': str(root / 'unused-maven'),
            '--gradle-distribution-zip': str(root / 'unused-gradle.zip'),
        }

    def test_default_unbound_preparation_creates_exact_plan_with_zero_executions(self):
        self.no_execution()
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-unit-') as temporary:
            evidence = Path(temporary).resolve() / 'prepared'
            self.assertEqual(0, MODULE.main(['--evidence-directory', str(evidence)]))
            summary = json.loads((evidence / 'summary.json').read_text())
            self.assertEqual('PREPARED_WAITING_FOR_REVIEWED_STAGE', summary['status'])
            self.assertEqual(10, summary['preparedCases'])
            self.assertEqual(0, summary['executedCases'])
            self.assertEqual([], summary['results'])
            for field in ('completeBoundaryMatrix', 'requestedCasesComplete', 'independentlyAudited'):
                self.assertIs(False, summary[field])
            self.assertEqual(MODULE.fixed_plan(), json.loads((evidence / 'explicit-case-plan.json').read_text()))
            self.assertEqual(MODULE.source_snapshot(), json.loads((evidence / 'fixture-inputs.json').read_text()))
            self.assertEqual({case['id'] for case in MODULE.fixed_plan()},
                             {json.loads(path.read_text())['id'] for path in evidence.glob('*/case.json')})
            self.assertEqual([], list(evidence.rglob('result.json')))
            self.assertEqual([], list(evidence.rglob('*.class')))

    def test_requested_subset_stays_unexecuted_preparation_and_never_completes_full_plan(self):
        self.no_execution()
        selected = [MODULE.fixed_plan()[0]['id'], MODULE.fixed_plan()[-1]['id']]
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-unit-') as temporary:
            evidence = Path(temporary).resolve() / 'subset'
            arguments = ['--evidence-directory', str(evidence), '--prepare-only']
            for case_id in selected:
                arguments += ['--case-id', case_id]
            self.assertEqual(0, MODULE.main(arguments))
            summary = json.loads((evidence / 'summary.json').read_text())
            self.assertEqual(2, summary['preparedCases'])
            self.assertEqual(0, summary['executedCases'])
            self.assertEqual(set(selected), {case['id'] for case in summary['requestedCases']})
            self.assertEqual('PREPARED_WAITING_FOR_REVIEWED_STAGE', summary['status'])
            self.assertIs(False, summary['completeBoundaryMatrix'])
            self.assertIs(False, summary['requestedCasesComplete'])
            self.assertIs(False, summary['independentlyAudited'])

    def test_execution_requires_every_reviewed_stage_toolchain_and_frozen_manifest_argument(self):
        self.no_execution()
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-unit-') as temporary:
            root = Path(temporary).resolve()
            supplied = self.execution_arguments(root)
            for missing in supplied:
                arguments = ['--evidence-directory', str(root / 'never-executed'), '--execute']
                arguments += [part for key, value in supplied.items() if key != missing for part in (key, value)]
                with self.subTest(missing=missing), self.assertRaises(MODULE.BoundaryError):
                    MODULE.main(arguments)
                self.assertFalse((root / 'never-executed').exists())

    def test_stale_fingerprint_is_rejected_before_stage_git_or_toolchain_access(self):
        self.no_execution()
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-unit-') as temporary:
            root = Path(temporary).resolve()
            supplied = self.execution_arguments(root)
            Path(supplied['--expected-input-manifest']).write_text(json.dumps({'synthetic-stale-input': '0' * 64}))
            arguments = ['--evidence-directory', str(root / 'never-executed'), '--execute']
            arguments += [part for key, value in supplied.items() for part in (key, value)]
            with self.assertRaisesRegex(MODULE.BoundaryError, 'frozen manifest'):
                MODULE.main(arguments)
            self.assertFalse((root / 'never-executed').exists())

    def test_prepared_guard_uses_all_opposite_runtime_anchors_without_enforcer(self):
        namespace = {'m': 'http://maven.apache.org/POM/4.0.0'}
        with tempfile.TemporaryDirectory(prefix='routecontract-dual-unit-') as temporary:
            root = Path(temporary).resolve()
            for case in MODULE.fixed_plan():
                if case['kind'] != 'runtime-guard':
                    continue
                with self.subTest(case=case['id']):
                    consumer = MODULE.prepare_case(root / case['id'], case)
                    tree = ET.parse(consumer / 'pom.xml')
                    dependencies = tree.findall('./m:dependencies/m:dependency', namespace)
                    coordinates = [':'.join(dependency.findtext(f'm:{field}', namespaces=namespace)
                                            for field in ('groupId', 'artifactId', 'version'))
                                   for dependency in dependencies]
                    self.assertEqual([f'{GROUP}:{case["adapter"]}:0.2.0'] + anchors(case['observedRuntime']),
                                     coordinates)
                    self.assertEqual([], tree.findall('.//m:plugin[m:artifactId="maven-enforcer-plugin"]', namespace))
                    self.assertEqual('17', tree.findtext('.//m:plugin[m:artifactId="maven-compiler-plugin"]'
                                                        '/m:configuration/m:release', namespaces=namespace))
                    self.assertTrue(list((consumer / 'src').rglob('*.java')))
                    self.assertFalse(list(consumer.rglob('*.class')))


if __name__ == '__main__':
    unittest.main()
