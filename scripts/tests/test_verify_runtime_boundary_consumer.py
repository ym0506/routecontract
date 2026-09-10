from __future__ import annotations
from collections import Counter
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('boundary_test',ROOT/'scripts/verify-runtime-boundary-consumer.py')
h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)

class BoundaryTest(unittest.TestCase):
    def setUp(self):self.plan=h.cases()
    def pick(self,mode=None,category=None,runtime='5.5.2'):
        return next(c for c in self.plan if c['runtime']==runtime and (mode is None or c['mode']==mode) and (category is None or c['category']==category))
    def types(self,c):
        named=c['topology']=='modulepath';result={}
        names=['consumer','newEntry','coreBridge','currentGuard','captureRegistry','adapter552','adapter553','hook552','hook553']
        for name in names:
            version='5.5.2' if name.endswith('552') else '5.5.3' if name.endswith('553') else None
            t={'className':'fixture.'+name,'present':version is None or version in c['adapters']}
            if t['present']:t.update(origin='/named' if named else '/classes',moduleName='fixture.'+name if named else None,namedModule=named)
            result[name]=t
        return result
    def observation(self,c,pid=11):
        types=copy.deepcopy(self.types(c))
        for t in types.values():
            if t['present']:t.update(loaderClass='jdk.internal.loader.ClassLoaders$AppClassLoader',loaderName='app',loaderIdentity='aa1')
        positive=c['mode']=='sequence';core=c['mode']=='core-only'
        observed=dict(mode=c['mode'],pid=pid,javaVersion='17.0.15',shardingSphereVersion=c['runtime'],returned=positive,
            actionEntries=2 if positive else 0,actionEntered=positive,driverCount=4 if positive else 1 if core else 0,
            datasourceConstructionEntered=c['mode']!='capture',businessRows=h.ROWS if positive or core else [],
            steps=[],snapshots=[],driverEvents=[],types=types,exceptionClasses=[],exceptionMessages=[],stackFrames=[],linkageFailure=False)
        names=['ordinary-before','capture-first','ordinary-between','capture-second'] if positive else ['ordinary-before','capture-missing-adapter'] if core else ['capture-rejection' if c['mode']=='capture' else 'ordinary-rejection']
        fingerprint='a'*64
        for i,name in enumerate(names):
            success=positive or core and i==0;captured=positive and i in (1,3)
            observed['steps'].append(dict(name=name,returned=success,actionDelta=1 if captured else 0,driverDelta=1 if success else 0,businessRows=h.ROWS if success else [],driverSqlFingerprints=[fingerprint] if success else [],snapshotIndex={1:0,3:1}.get(i) if positive else None))
            if success:observed['driverEvents'].append(dict(phase=name,sqlFingerprint=fingerprint))
        if positive:
            for operation in ('boundary-first','boundary-second'):
                observed['snapshots'].append(dict(schemaVersion=2,runtimeIdentity=h.A29.identity(c['runtime']),operationId=operation,status='COMPLETE',
                    observedPhysicalAttemptCount=1,callbackReturnedCount=1,callbackFailureCount=0,unknownOutcomeCount=0,trunkThreadFlagCount=1,workerThreadFlagCount=0,
                    observedDataSourceNames=['ds_0'],attempts=[dict(observedDataSourceName='ds_0',sqlFingerprint=fingerprint,parameterCount=2,parameterTypes=['java.lang.Long','java.lang.String'],threadRole='TRUNK',outcome='CALLBACK_RETURNED',reportedFailureType=None)],collectorDiagnostics=[]))
        else:
            observed['exceptionClasses']=['java.lang.IllegalStateException'];observed['exceptionMessages']=[c['expected']+': actual rejection']
            lane=c['adapters'][0].replace('.','') if c['adapters'] else '552'
            observed['stackFrames']=[f'io.github.ym0506.routecontract.shardingsphere{lane}.internal.ShardingSphere{lane}HookConstructionGuard.verify'] if c['mode']=='sql' else ['io.github.ym0506.routecontract.internal.RuntimeAdapterRegistry.verify']
        return observed
    def reject(self,c,o):self.assertNotEqual('PASS',h.classify(c,o,self.types(c)))

    def test_exact_28_canonical_cells_and_existing_rows(self):
        self.assertEqual(28,len(self.plan));self.assertEqual(28,len({c['id'] for c in self.plan}))
        self.assertEqual(Counter({'ordered-isolation':2,'wrong-adapter':4,'dual-classpath':8,'core-only':2,'single-modulepath':4,'dual-modulepath':8}),Counter(c['category'] for c in self.plan))
        self.assertEqual({'A-01','A-02','A-03','A-04','A-05','A-06','A-07','A-08','A-10','A-18','A-19'},{r for c in self.plan for r in c['requirements']})
    def test_wrong_pairs_and_each_dual_order_action_sql_runtime(self):
        wrong=[c for c in self.plan if c['category']=='wrong-adapter']
        self.assertEqual({('5.5.2','5.5.3',m) for m in ('capture','sql')}|{('5.5.3','5.5.2',m) for m in ('capture','sql')},{(c['runtime'],c['adapters'][0],c['mode']) for c in wrong})
        for category in ('dual-classpath','dual-modulepath'):
            self.assertEqual({(r,o,m) for r in ('5.5.2','5.5.3') for o in (('5.5.2','5.5.3'),('5.5.3','5.5.2')) for m in ('capture','sql')},{(c['runtime'],tuple(c['adapters']),c['mode']) for c in self.plan if c['category']==category})
    def test_all_complete_observations_pass(self):
        for c in self.plan:
            with self.subTest(c=c['id']):self.assertEqual('PASS',h.classify(c,self.observation(c),self.types(c)))
    def test_no_missing_or_ill_typed_proof_passes(self):
        for c in self.plan:
            o=self.observation(c)
            for field in o:
                v=copy.deepcopy(o);del v[field]
                with self.subTest(c=c['id'],missing=field):self.reject(c,v)
            for field in ('pid','actionEntries','driverCount'):
                v=copy.deepcopy(o);v[field]=bool(v[field]);self.reject(c,v)
    def test_sequence_order_action_driver_and_snapshot_isolation(self):
        c=self.pick('sequence');o=self.observation(c)
        for change in ({'driverCount':3},{'actionEntries':1},{'snapshots':[]},{'businessRows':[]},{'steps':o['steps'][::-1]},{'returned':False}):self.reject(c,dict(copy.deepcopy(o),**change))
        for index in range(4):
            for field,value in (('driverDelta',2),('businessRows',[]),('snapshotIndex',0),('actionDelta',3)):
                v=copy.deepcopy(o);v['steps'][index][field]=value
                if v!=o:self.reject(c,v)
        for index in range(2):
            for field,value in (('observedPhysicalAttemptCount',2),('callbackReturnedCount',2),('schemaVersion',2.0),('collectorDiagnostics',['leaked']),('operationId','wrong'),('unknownOutcomeCount',False)):
                v=copy.deepcopy(o);v['snapshots'][index][field]=value;self.reject(c,v)
    def test_driver_fingerprints_bind_to_each_wrapped_operation(self):
        c=self.pick('sequence');o=self.observation(c)
        v=copy.deepcopy(o);v['snapshots'][0]['attempts'][0]['sqlFingerprint']='b'*64;self.reject(c,v)
        v=copy.deepcopy(o);v['driverEvents'][1]['phase']='ordinary-before';self.reject(c,v)
        v=copy.deepcopy(o);v['steps'][1]['driverSqlFingerprints']=['b'*64];self.reject(c,v)
        for key,value in (('parameterTypes',['java.lang.Integer','java.lang.String']),('outcome','START_REPORTED'),('observedDataSourceName','ds_1'),('threadRole','WORKER')):
            v=copy.deepcopy(o);v['snapshots'][0]['attempts'][0][key]=value;self.reject(c,v)
    def test_core_only_requires_successful_ordinary_then_missing_capture(self):
        c=self.pick('core-only');o=self.observation(c)
        for change in ({'driverCount':0},{'businessRows':[]},{'returned':True},{'actionEntries':1},{'datasourceConstructionEntered':False},{'steps':o['steps'][::-1]}):self.reject(c,dict(copy.deepcopy(o),**change))
        v=copy.deepcopy(o);v['steps'][0]['returned']=False;self.reject(c,v)
        v=copy.deepcopy(o);v['steps'][1]['returned']=True;self.reject(c,v)
    def test_negative_markers_cannot_mask_action_sql_or_linkage(self):
        for c in [v for v in self.plan if v['mode'] in ('capture','sql')]:
            o=self.observation(c)
            for change in ({'actionEntries':1},{'driverCount':1},{'businessRows':h.ROWS},{'returned':True},{'linkageFailure':True},{'exceptionClasses':['java.lang.AbstractMethodError']},{'exceptionMessages':['RC_FAKE: wrong marker']}):self.reject(c,dict(copy.deepcopy(o),**change))
            self.reject(c,dict(copy.deepcopy(o),datasourceConstructionEntered=not o['datasourceConstructionEntered']))
            if c['mode']=='sql':self.reject(c,dict(copy.deepcopy(o),stackFrames=['fixture.preflight']))
    def test_named_consumer_requires_actual_named_core_and_selected_adapters(self):
        for c in [v for v in self.plan if v['topology']=='modulepath']:
            o=self.observation(c)
            for name,t in o['types'].items():
                if t['present']:
                    for field,value in (('namedModule',False),('moduleName',None),('origin','/wrong.jar'),('loaderIdentity','other')):
                        v=copy.deepcopy(o);v['types'][name][field]=value;self.reject(c,v)
    def test_absence_cannot_hide_type_inspection_failure(self):
        c=self.pick('core-only');o=self.observation(c)
        for name in ('adapter552','adapter553','hook552','hook553'):
            v=copy.deepcopy(o);v['types'][name]['inspectionErrorClass']='java.lang.LinkageError';self.reject(c,v)
        v=copy.deepcopy(o);v['types']['adapter552']['present']=0;self.reject(c,v)
    def test_only_full_canonical_matrix_with_cross_runtime_parity_is_verified(self):
        results=[dict(case=copy.deepcopy(c),outcome='PASS',observed=self.observation(c,100+i)) for i,c in enumerate(self.plan)]
        self.assertEqual('VERIFIED',h.completion_status(results)['status'])
        self.assertEqual('INCOMPLETE',h.completion_status(results,True)['status'])
        self.assertEqual('INCOMPLETE',h.completion_status(results[:14])['status'])
        duplicate=results[:-1]+[results[0]];self.assertNotEqual('VERIFIED',h.completion_status(duplicate)['status'])
        mutated=copy.deepcopy(results);mutated[0]['case']['adapters']=[];self.assertNotEqual('VERIFIED',h.completion_status(mutated)['status'])
        reused=copy.deepcopy(results);reused[0]['observed']['pid']=reused[1]['observed']['pid'];self.assertNotEqual('VERIFIED',h.completion_status(reused)['status'])
        parity=copy.deepcopy(results);next(r for r in parity if r['case']['mode']=='sequence')['observed']['snapshots'][0]['attempts'][0]['sqlFingerprint']='b'*64
        self.assertEqual('FAILED',h.completion_status(parity)['status'])
        bad=copy.deepcopy(results);bad[0]['outcome']='WRONG_DIAGNOSTIC';self.assertEqual('FAILED',h.completion_status(bad)['status'])
    def test_class_output_rejects_production_shadows_missing_modules_and_byte_changes(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);classes=base/'classes';consumer=classes/'io/github/ym0506/routecontract/consumer';consumer.mkdir(parents=True)
            (consumer/'RuntimeBoundaryProbe.class').write_bytes(b'class');graph={'artifacts':[],'compiledClasses':h.class_hashes([str(classes)])}
            receipt={'artifacts':[]};h.verify_launch_inputs([],[str(classes)],graph,base,receipt,False)
            (consumer/'RuntimeBoundaryProbe.class').write_bytes(b'tampered')
            with self.assertRaises(h.BoundaryError):h.verify_launch_inputs([],[str(classes)],graph,base,receipt,False)
            with self.assertRaises(h.BoundaryError):h.class_hashes([str(classes)],True)
            (classes/'module-info.class').write_bytes(b'module');self.assertTrue(h.class_hashes([str(classes)],True))
            (classes/'io/github/ym0506/routecontract/RouteContract.class').write_bytes(b'shadow')
            with self.assertRaises(h.BoundaryError):h.class_hashes([str(classes)],True)
    def test_post_process_pin_verification_survives_python_optimization(self):
        c=self.pick('capture','wrong-adapter')
        before={'artifacts':[],'compiledClasses':{}}
        after={'artifacts':[{'path':'changed.jar','sha256':'b'*64}],'compiledClasses':{}}
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            with patch.object(h,'launch',return_value=(['/unexecuted/java'],[],[])), patch.object(h,'expected_types',return_value=self.types(c)), patch.object(h,'verify_launch_inputs',side_effect=[before,after]) as verification, patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0)), patch('builtins.print'):
                result=h.run_case(c,base,{},base,{},base,{},0)
            self.assertEqual(2,verification.call_count)
            self.assertEqual('INPUT_CHANGED',result['outcome'])
            self.assertFalse(result['launchInputsUnchanged'])

    def test_named_launch_roots_actual_jdk_dependencies_without_changing_classpath_cells(self):
        receipt={'artifacts':[dict(module=module,name=module+'.jar',relativePath=module+'.jar',sha256='a'*64) for module in h.MODULES]}
        graph={'artifacts':[dict(group='third',path='/third.jar')],'classes':['/classes'],'namedClasses':['/named']}
        for c in self.plan:
            argv,paths,classes=h.launch(c,graph,Path('/repository'),receipt,Path('/jdk'),Path('/observed.json'),1234)
            if c['topology']=='modulepath':
                self.assertEqual('ALL-MODULE-PATH,java.instrument,jdk.unsupported',argv[argv.index('--add-modules')+1])
                self.assertEqual('/third.jar',argv[argv.index('-cp')+1])
                self.assertEqual(h.CONSUMER_MODULE+'=ALL-UNNAMED',argv[argv.index('--add-reads')+1])
            else:
                self.assertNotIn('--add-modules',argv)
                self.assertNotIn('--module-path',argv)

    def test_named_launch_excludes_firstparty_from_classpath_and_retains_both_orders(self):
        receipt={'artifacts':[dict(module=module,name=module+'.jar',relativePath=module+'.jar',sha256='a'*64) for module in h.MODULES]}
        graph={'artifacts':[dict(group='third',path='/third.jar')], 'classes':['/classes'],'namedClasses':['/named']}
        for c in [v for v in self.plan if v['topology']=='modulepath']:
            argv,paths,classes=h.launch(c,graph,Path('/repository'),receipt,Path('/jdk'),Path('/observed.json'),1234)
            self.assertEqual('/third.jar',argv[argv.index('-cp')+1]);self.assertIn('--module',argv)
            modulepath=argv[argv.index('--module-path')+1].split(':')
            self.assertEqual(['/repository/routecontract-core.jar',*['/repository/'+h.ADAPTERS[r]+'.jar' for r in c['adapters']],'/named'],modulepath)
            self.assertEqual(h.CONSUMER_MODULE+'/'+h.PROBE,argv[argv.index('--module')+1])

if __name__=='__main__':unittest.main()
