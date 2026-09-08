"""Focused rejection regressions; synthetic reports do not constitute MySQL evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('packaged_corpus_under_test', ROOT / 'scripts/verify-packaged-corpus-consumer.py')
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def receipt():
    modules = ['routecontract-core', 'routecontract-shardingsphere-5.5', 'routecontract-shardingsphere-5.5.2']
    return {'formatVersion': 1, 'routeContractVersion': '0.2.0', 'artifacts': [
        {'module': name, 'name': f'{name}-0.2.0.{ext}',
         'relativePath': f'io/github/ym0506/routecontract/{name}/0.2.0/{name}-0.2.0.{ext}',
         'sha256': 'a' * 64} for name in modules for ext in ('jar', 'pom', 'module')]}


class CorpusAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name).resolve()
        self.contract = mod.read_json(mod.FIXTURE / 'expected-corpus.json')

    def tearDown(self):
        for path in self.base.rglob('*'):
            if path.is_file() and not path.is_symlink():
                path.chmod(0o600)
        self.directory.cleanup()

    def junit(self, suites):
        result = self.base / 'junit'
        result.mkdir(exist_ok=True)
        for name, methods in suites.items():
            root = ET.Element('testsuite', name=name, tests=str(len(methods)), failures='0', errors='0', skipped='0')
            for method in methods:
                ET.SubElement(root, 'testcase', name=method + '()', classname=name, time='0.1')
            ET.ElementTree(root).write(result / ('TEST-' + name + '.xml'))
        return result

    def test_fixed_contract_has_exact_six_suites_twenty_eight_tests(self):
        self.assertEqual(39, len(mod.original_inputs(self.contract)))
        self.assertEqual(6, sum(len(l['suites']) for l in self.contract['lanes'].values()))
        self.assertEqual(28, sum(len(t) for l in self.contract['lanes'].values() for t in l['suites'].values()))
        self.assertIsNone(self.contract['humanReview'])

    def test_junit_requires_each_original_method_with_no_skip_or_failure(self):
        suites = self.contract['lanes']['5.5.3']['suites']
        directory = self.junit(suites)
        self.assertEqual(14, sum(x['counts']['tests'] for x in mod.verify_junit(directory, suites).values()))
        first = next(directory.glob('TEST-*.xml'))
        original = first.read_bytes()
        for mutation in ('rename', 'skip', 'duplicate', 'wrong-class', 'false-count'):
            tree = ET.fromstring(original)
            case = tree.find('testcase')
            if mutation == 'rename': case.set('name', 'replacementWorkload()')
            if mutation == 'skip': ET.SubElement(case, 'skipped')
            if mutation == 'duplicate': tree.append(copy.deepcopy(case))
            if mutation == 'wrong-class': case.set('classname', 'other.Suite')
            if mutation == 'false-count': tree.set('tests', '0')
            ET.ElementTree(tree).write(first)
            with self.subTest(mutation=mutation), self.assertRaises(mod.CorpusError):
                mod.verify_junit(directory, suites)
        first.write_bytes(original)
        (directory / 'TEST-extra.Suite.xml').write_bytes(original)
        with self.assertRaises(mod.CorpusError): mod.verify_junit(directory, suites)

    def test_packaged_locks_preserve_all_original_third_party_selections(self):
        for runtime, lane in self.contract['lanes'].items():
            text = (ROOT / lane['sourceDirectory'] / 'gradle.lockfile').read_text()
            expected = mod.lock_graphs(text)
            actual = mod.lock_graphs(mod.packaged_lock(text, lane['adapter']))
            for name in expected:
                additions = sorted(set(actual[name]) - set(expected[name]))
                self.assertEqual(sorted([f'{mod.GROUP}:routecontract-core:0.2.0',
                                         f'{mod.GROUP}:{lane["adapter"]}:0.2.0']), additions)
                self.assertEqual(expected[name], [x for x in actual[name] if not x.startswith(mod.GROUP + ':')])
            with self.assertRaises(mod.CorpusError): mod.packaged_lock('empty=testRuntimeClasspath\n', lane['adapter'])
            with self.assertRaises(mod.CorpusError): mod.packaged_lock(mod.packaged_lock(text, lane['adapter']), lane['adapter'])

    def test_build_changes_only_single_project_dependency_and_appends_controls(self):
        for lane in self.contract['lanes'].values():
            text = (ROOT / lane['sourceDirectory'] / 'build.gradle').read_text()
            value = mod.adapted_build(text, lane['adapter'])
            restored = value.removesuffix("\napply from: 'packaged-controls.gradle'\n").replace(
                f"testImplementation '{mod.GROUP}:{lane['adapter']}:0.2.0'",
                f"testImplementation project(':{lane['adapter']}')")
            self.assertEqual(text, restored)
            with self.assertRaises(mod.CorpusError): mod.adapted_build(text + "\nproject(':extra')\n", lane['adapter'])

    def test_original_input_bytes_and_closed_file_set_are_required(self):
        for relative in self.contract['originalInputSha256']:
            target = self.base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.assertEqual(self.contract['originalInputSha256'], mod.original_inputs(self.contract, self.base))
        extra = self.base / 'examples/mysql/src/test/java/Extra.java'
        extra.write_text('class Extra {}')
        with self.assertRaises(mod.CorpusError): mod.original_inputs(self.contract, self.base)
        extra.unlink()
        golden = self.base / 'examples/manifests/find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json'
        golden.write_text('{}')
        with self.assertRaises(mod.CorpusError): mod.original_inputs(self.contract, self.base)

    def test_copies_preserve_sources_and_goldens_and_do_not_add_test_cases(self):
        consumer = self.base / 'consumer'
        mapping = mod.copy_consumer(consumer, '5.5.2', self.contract, receipt())
        mod.verify_copies(consumer, mapping)
        self.assertEqual(33, len(mapping))  # two sources, fourteen goldens, fourteen manifests, three build inputs
        source = 'examples/mysql-5.5.2/src/test/java/io/github/ym0506/routecontract/example552/Exact552OperationContractMySqlTest.java'
        self.assertEqual((ROOT / source).read_bytes(), (consumer / mapping[source]['copyPath']).read_bytes())
        extension = consumer / 'src/test/java/io/github/ym0506/routecontract/packaged/PackagedCorpusProvenance.java'
        self.assertNotIn('@Test', extension.read_text())
        self.assertFalse((consumer / 'src/main').exists())
        golden = consumer / 'review-inputs/examples/manifests/find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json'
        golden.chmod(0o600)
        golden.write_text('{}')
        with self.assertRaises(mod.CorpusError): mod.verify_copies(consumer, mapping)

    def test_input_inventory_rejects_symlinks(self):
        (self.base / 'real').write_text('bytes')
        (self.base / 'alias').symlink_to(self.base / 'real')
        with self.assertRaises(mod.CorpusError): mod.inventory(self.base)

    def graph_fixture(self):
        consumer = self.base / 'consumer'
        target = consumer / 'build/packaged-corpus'
        target.mkdir(parents=True)
        artifacts = []
        pins = receipt()
        for name in ('routecontract-core', 'routecontract-shardingsphere-5.5.2'):
            jar = self.base / (name + '-0.2.0.jar')
            jar.write_bytes(name.encode())
            for pin in pins['artifacts']:
                if pin['name'] == jar.name: pin['sha256'] = mod.digest(jar)
            artifacts.append({'coordinate': f'{mod.GROUP}:{name}:0.2.0', 'name': jar.name,
                              'path': str(jar), 'sha256': mod.digest(jar)})
        sharding = self.base / 'shardingsphere-infra-executor-5.5.2.jar'
        sharding.write_bytes(b'synthetic unit fixture')
        artifacts.append({'coordinate': 'org.apache.shardingsphere:shardingsphere-infra-executor:5.5.2',
                          'name': sharding.name, 'path': str(sharding), 'sha256': mod.digest(sharding)})
        graphs = {name: {'modules': sorted(x['coordinate'] for x in artifacts), 'artifacts': artifacts}
                  for name in ('testCompileClasspath', 'testRuntimeClasspath')}
        mod.write_json(target / 'selected-graphs.json', graphs)
        (consumer / 'gradle.lockfile').write_text('\n'.join(x['coordinate'] + '=testCompileClasspath,testRuntimeClasspath' for x in artifacts))
        classes = consumer / 'build/classes/java/test'
        classes.mkdir(parents=True)
        classpath = [{'path': str(classes), 'directory': True, 'sha256': None}] + [dict(x, directory=False) for x in artifacts]
        mod.write_json(target / 'test-runtime-classpath.json', classpath)
        return consumer, graphs, pins, classpath

    def test_graph_rejects_missing_locked_nodes_tampered_jars_and_production_directory(self):
        consumer, graphs, pins, classpath = self.graph_fixture()
        mod.verify_graphs(consumer, '5.5.2', pins)
        wrong = copy.deepcopy(graphs)
        wrong['testCompileClasspath']['modules'].pop()
        mod.write_json(consumer / 'build/packaged-corpus/selected-graphs.json', wrong)
        with self.assertRaises(mod.CorpusError): mod.verify_graphs(consumer, '5.5.2', pins)
        mod.write_json(consumer / 'build/packaged-corpus/selected-graphs.json', graphs)
        production = consumer / 'build/classes/java/main'
        production.mkdir(parents=True)
        mod.write_json(consumer / 'build/packaged-corpus/test-runtime-classpath.json',
                       classpath + [{'path': str(production), 'directory': True, 'sha256': None}])
        with self.assertRaises(mod.CorpusError): mod.verify_graphs(consumer, '5.5.2', pins)
        mod.write_json(consumer / 'build/packaged-corpus/test-runtime-classpath.json', classpath)
        Path(graphs['testRuntimeClasspath']['artifacts'][0]['path']).write_bytes(b'tampered')
        with self.assertRaises(mod.CorpusError): mod.verify_graphs(consumer, '5.5.2', pins)

    def test_provenance_rejects_wrong_origin_generation_entry_jvm_and_missing_suite(self):
        consumer, graphs, pins, _ = self.graph_fixture()
        suites = {'example.CorpusTest': ['existingCase']}
        actual = {x['coordinate'].split(':')[1]: x for x in graphs['testRuntimeClasspath']['artifacts']}
        rows = {}
        for phase in ('before', 'after'):
            row = {'suite': 'example.CorpusTest', 'phase': phase, 'runtime': '5.5.2', 'pid': '123',
                   'javaVersion': '17.0.15', 'loader': 'TestLoader@1', 'generationEnabled': 'false',
                   'suiteCodeSource': (consumer / 'build/classes/java/test').as_uri() + '/',
                   'currentEntry': 'io.github.ym0506.routecontract.api.RouteContract',
                   'hookClass': 'io.github.ym0506.routecontract.shardingsphere552.internal.RouteContract552SqlExecutionHook',
                   'runtimeAdapterClass': 'io.github.ym0506.routecontract.shardingsphere552.internal.ShardingSphere552RuntimeAdapter',
                   'providerDescriptors': 'EXACT_PACKAGED'}
            for prefix, name in [('core', 'routecontract-core'), ('adapter', 'routecontract-shardingsphere-5.5.2')]:
                row[prefix + 'Jar'] = actual[name]['path']; row[prefix + 'Sha256'] = actual[name]['sha256']
            rows[phase] = row
            mod.write_json(consumer / f'build/packaged-corpus/provenance/example.CorpusTest-{phase}.json', row)
        self.assertEqual(2, len(mod.verify_provenance(consumer, '5.5.2', suites, graphs, pins)))
        target = consumer / 'build/packaged-corpus/provenance/example.CorpusTest-after.json'
        for key, value in [('pid', '456'), ('generationEnabled', 'true'), ('currentEntry', 'legacy.RouteContract'),
                           ('coreSha256', 'f' * 64), ('javaVersion', '21.0.11'), ('hookClass', 'wrong.Hook'),
                           ('suiteCodeSource', self.base.as_uri()), ('adapterJar', str(self.base / 'other.jar'))]:
            changed = dict(rows['after'], **{key: value})
            mod.write_json(target, changed)
            with self.subTest(key=key), self.assertRaises(mod.CorpusError):
                mod.verify_provenance(consumer, '5.5.2', suites, graphs, pins)
        target.unlink()
        with self.assertRaises(mod.CorpusError): mod.verify_provenance(consumer, '5.5.2', suites, graphs, pins)

    def test_explicit_review_hash_and_source_are_not_optional(self):
        with self.assertRaises(mod.CorpusError):
            mod.reviewed_inputs(self.base, self.base / 'receipt.json', '', '4e06694')
        path = self.base / 'receipt.json'
        mod.write_json(path, receipt())
        with self.assertRaises(mod.CorpusError):
            mod.reviewed_inputs(self.base, path, '0' * 64, '4' * 40)

    def test_missing_markers_or_generation_bypass_cannot_count_as_corpus_success(self):
        for output in ('BUILD SUCCESSFUL', 'ROUTECONTRACT_552_EVIDENCE_CANDIDATE approvedBytes=1'):
            with self.assertRaises(mod.CorpusError): mod.verify_outputs(self.base, '5.5.2', output)

    def test_final_consumer_recheck_rejects_late_source_addition_and_mutation(self):
        consumer = self.base / 'consumer'
        for relative in ('src/test/java/Original.java', 'review-inputs/examples/manifests/golden.json'):
            path = consumer / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original')
        expected = mod.inventory(consumer)
        mod.verify_consumer_inputs(consumer, expected)
        extra = consumer / 'src/test/java/Late.java'
        extra.write_text('late injected source')
        with self.assertRaises(mod.CorpusError): mod.verify_consumer_inputs(consumer, expected)
        extra.unlink()
        (consumer / 'review-inputs/examples/manifests/golden.json').write_text('changed after lane one')
        with self.assertRaises(mod.CorpusError): mod.verify_consumer_inputs(consumer, expected)

    def test_final_lane_recheck_rejects_changed_retained_command_before_reading_results(self):
        log = self.base / 'gradle.command.json'
        log.write_text('{"argv":["actual"]}')
        result = {'retainedEvidenceSha256': {log.name: mod.digest(log)}}
        log.write_text('{"argv":["different"]}')
        with self.assertRaises(mod.CorpusError):
            mod.revalidate_completed_lane(self.base, result, self.contract, receipt())


if __name__ == '__main__':
    unittest.main()
