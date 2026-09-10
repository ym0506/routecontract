#!/usr/bin/env python3
"""Run the finite existing-ADR staged runtime/action/module boundary plan."""
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
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from legacy_artifact_inputs import GROUP,digest
from public_split_artifacts import load_consumer_receipt

def helper(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value)
    return value

A29=helper('runtime_boundary_a29','verify-current-entry-successor.py')
ADAPTERS=A29.ADAPTERS
FIXTURE=ROOT/'examples/runtime-boundary-consumer'
PROBE='io.github.ym0506.routecontract.consumer.RuntimeBoundaryProbe'
CONSUMER_MODULE='io.github.ym0506.routecontract.consumer.runtimeboundary'
NAMED_JDK_ROOTS=('java.instrument','jdk.unsupported')
MODULES={'routecontract-core':'io.github.ym0506.routecontract.core',
         'routecontract-shardingsphere-5.5.2':'io.github.ym0506.routecontract.shardingsphere552',
         'routecontract-shardingsphere-5.5':'io.github.ym0506.routecontract.shardingsphere55'}
ROWS=['201:3:PAID']
class BoundaryError(RuntimeError): pass
write_json=A29.write_json


def cases():
    result=[]
    def add(runtime,mode,adapters,topology,category,expected,requirements,label):
        result.append(dict(id=f'{runtime}-{label}-{mode}',runtime=runtime,mode=mode,adapters=adapters,
            topology=topology,category=category,expected=expected,requirements=requirements))
    for runtime in ADAPTERS:
        other=next(v for v in ADAPTERS if v!=runtime)
        add(runtime,'sequence',[runtime],'classpath','ordered-isolation','SEQUENCE_SUCCESS',
            ['A-01' if runtime=='5.5.2' else 'A-02','A-03'],'matching')
        for mode in ('capture','sql'):
            add(runtime,mode,[other],'classpath','wrong-adapter','RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME',
                ['A-04' if runtime=='5.5.3' else 'A-05'] if mode=='capture' else ['A-06'],'wrong-adapter')
        add(runtime,'core-only',[],'classpath','core-only','RC_ADAPTER_NOT_FOUND',['A-10'],'core-only')
        for order in (['5.5.2','5.5.3'],['5.5.3','5.5.2']):
            for mode in ('capture','sql'):
                add(runtime,mode,order,'classpath','dual-classpath','RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS',
                    ['A-07' if runtime=='5.5.2' else 'A-08'],'dual-'+'-'.join(order))
                add(runtime,mode,order,'modulepath','dual-modulepath','RC_UNSUPPORTED_MODULE_PATH',
                    ['A-19'],'module-dual-'+'-'.join(order))
        for mode in ('capture','sql'):
            add(runtime,mode,[runtime],'modulepath','single-modulepath','RC_UNSUPPORTED_MODULE_PATH',
                ['A-18'],'module-single')
    return result


def snapshots_valid(observed,runtime):
    snapshots=observed['snapshots'];steps=observed['steps']
    if len(snapshots)!=2: return False
    for index,snapshot in enumerate(snapshots):
        expected_counts={'schemaVersion':2,'observedPhysicalAttemptCount':1,'callbackReturnedCount':1,
            'callbackFailureCount':0,'unknownOutcomeCount':0,'trunkThreadFlagCount':1,'workerThreadFlagCount':0}
        if (not isinstance(snapshot,dict) or any(type(snapshot.get(k)) is not int or snapshot[k]!=v for k,v in expected_counts.items())
            or snapshot.get('status')!='COMPLETE' or snapshot.get('collectorDiagnostics')!=[]
            or snapshot.get('operationId')!=('boundary-first' if index==0 else 'boundary-second')
            or snapshot.get('observedDataSourceNames')!=['ds_0']
            or not A29.exact_identity(snapshot.get('runtimeIdentity'),runtime)): return False
        attempts=snapshot.get('attempts')
        if not isinstance(attempts,list) or len(attempts)!=1: return False
        attempt=attempts[0]
        expected={'observedDataSourceName':'ds_0','parameterCount':2,
            'parameterTypes':['java.lang.Long','java.lang.String'],'threadRole':'TRUNK',
            'outcome':'CALLBACK_RETURNED','reportedFailureType':None}
        if (not isinstance(attempt,dict) or type(attempt.get('parameterCount')) is not int
            or any(attempt.get(k)!=v for k,v in expected.items())
            or not re.fullmatch('[0-9a-f]{64}',str(attempt.get('sqlFingerprint','')))): return False
        if steps[1 if index==0 else 3]['driverSqlFingerprints']!=[attempt['sqlFingerprint']]: return False
    return snapshots[0]['attempts']==snapshots[1]['attempts']


def classify(case,observed,expected_types):
    required={'mode','pid','javaVersion','shardingSphereVersion','returned','actionEntries','actionEntered',
        'driverCount','datasourceConstructionEntered','businessRows','steps','snapshots','driverEvents','types',
        'exceptionClasses','exceptionMessages','stackFrames','linkageFailure'}
    if not isinstance(observed,dict) or not required.issubset(observed): return 'MISSING_PROOF'
    for field in ('pid','actionEntries','driverCount'):
        if type(observed[field]) is not int or observed[field]<(1 if field=='pid' else 0): return 'INVALID_PROOF'
    for field in ('returned','actionEntered','datasourceConstructionEntered','linkageFailure'):
        if type(observed[field]) is not bool: return 'INVALID_PROOF'
    if observed['actionEntered']!=(observed['actionEntries']>0): return 'INVALID_PROOF'
    for field in ('businessRows','steps','snapshots','driverEvents','exceptionClasses','exceptionMessages','stackFrames'):
        if not isinstance(observed[field],list): return 'INVALID_PROOF'
    if (observed['mode']!=case['mode'] or not isinstance(observed['javaVersion'],str)
        or not observed['javaVersion'].startswith('17.') or observed['shardingSphereVersion']!=case['runtime']): return 'WRONG_RUNTIME'
    if not isinstance(observed['types'],dict) or set(observed['types'])!=set(expected_types): return 'WRONG_TYPE_PROOF'
    for name,expected in expected_types.items():
        actual=observed['types'][name]
        keys=set(expected)|({'loaderClass','loaderName','loaderIdentity'} if expected['present'] else set())
        if (not isinstance(actual,dict) or set(actual)!=keys or type(actual.get('present')) is not bool
            or any(actual.get(k)!=v for k,v in expected.items())): return 'WRONG_TYPE_ORIGIN_OR_MODULE'
        if actual.get('present') and (type(actual.get('namedModule')) is not bool or not actual.get('loaderClass') or not actual.get('loaderIdentity')): return 'MISSING_LOADER_PROOF'
    consumer=observed['types']['consumer']
    if any(any(t[k]!=consumer[k] for k in ('loaderClass','loaderName','loaderIdentity')) for t in observed['types'].values() if t['present']): return 'WRONG_DEFINING_LOADER'
    for name in ('exceptionClasses','exceptionMessages','stackFrames','businessRows'):
        if any(not isinstance(v,str) for v in observed[name]): return 'INVALID_PROOF'
    if len(observed['exceptionClasses'])!=len(observed['exceptionMessages']): return 'INVALID_PROOF'
    if observed['linkageFailure'] or any(n.endswith(('LinkageError','AbstractMethodError','NoClassDefFoundError','NoSuchMethodError','ExceptionInInitializerError','IllegalAccessError','IncompatibleClassChangeError','VerifyError')) for n in observed['exceptionClasses']): return 'LINKAGE_FAILURE'
    steps=observed['steps']
    for step in steps:
        if (not isinstance(step,dict) or set(step)!={'name','returned','actionDelta','driverDelta','businessRows','driverSqlFingerprints','snapshotIndex'}
            or type(step['returned']) is not bool or type(step['actionDelta']) is not int or type(step['driverDelta']) is not int
            or step['actionDelta']<0 or step['driverDelta']<0 or not isinstance(step['businessRows'],list)
            or not isinstance(step['driverSqlFingerprints'],list)
            or any(not re.fullmatch('[0-9a-f]{64}',str(v)) for v in step['driverSqlFingerprints'])
            or step['snapshotIndex'] is not None and type(step['snapshotIndex']) is not int): return 'INVALID_STEP'
    events=observed['driverEvents']
    if any(not isinstance(e,dict) or set(e)!={'phase','sqlFingerprint'} or not re.fullmatch('[0-9a-f]{64}',str(e['sqlFingerprint'])) for e in events): return 'INVALID_DRIVER_EVENT'
    if len(events)!=observed['driverCount'] or sum(s['driverDelta'] for s in steps)!=observed['driverCount'] or sum(s['actionDelta'] for s in steps)!=observed['actionEntries']: return 'COUNTER_MISMATCH'
    for step in steps:
        if [e['sqlFingerprint'] for e in events if e['phase']==step['name']]!=step['driverSqlFingerprints'] or len(step['driverSqlFingerprints'])!=step['driverDelta']: return 'DRIVER_PHASE_MISMATCH'
    if case['expected']=='SEQUENCE_SUCCESS':
        names=['ordinary-before','capture-first','ordinary-between','capture-second']
        if (not observed['returned'] or observed['exceptionClasses'] or observed['stackFrames']
            or not observed['datasourceConstructionEntered'] or observed['actionEntries']!=2 or observed['driverCount']!=4
            or observed['businessRows']!=ROWS or [s['name'] for s in steps]!=names): return 'SEQUENCE_FAILED'
        for i,step in enumerate(steps):
            if not step['returned'] or step['driverDelta']!=1 or step['actionDelta']!=(1 if i in (1,3) else 0) or step['businessRows']!=ROWS or step['snapshotIndex']!=({1:0,3:1}.get(i)): return 'SEQUENCE_FAILED'
        return 'PASS' if snapshots_valid(observed,case['runtime']) else 'SNAPSHOT_OR_PARITY_FAILED'
    if observed['returned'] or observed['actionEntries'] or observed['snapshots']: return 'ACTION_OR_SILENT_SUCCESS'
    if not observed['exceptionClasses'] or not observed['stackFrames'] or not any(case['expected']+':' in m for m in observed['exceptionMessages']): return 'WRONG_DIAGNOSTIC'
    if case['mode']=='core-only':
        good=(observed['driverCount']==1 and observed['businessRows']==ROWS and observed['datasourceConstructionEntered']
            and [s['name'] for s in steps]==['ordinary-before','capture-missing-adapter']
            and steps[0]['returned'] and steps[0]['driverDelta']==1 and steps[0]['businessRows']==ROWS
            and not steps[1]['returned'] and steps[1]['driverDelta']==0 and steps[1]['businessRows']==[]
            and all(s['snapshotIndex'] is None for s in steps))
        return 'PASS' if good else 'CORE_ONLY_SEQUENCE_FAILED'
    if (observed['driverCount'] or observed['businessRows'] or observed['driverEvents']
        or observed['datasourceConstructionEntered']!=(case['mode']=='sql')): return 'SQL_OR_DATASOURCE_BOUNDARY_FAILED'
    expected_step='ordinary-rejection' if case['mode']=='sql' else 'capture-rejection'
    if len(steps)!=1 or steps[0]['name']!=expected_step or steps[0]['returned'] or steps[0]['businessRows'] or steps[0]['snapshotIndex'] is not None: return 'REJECTION_STEP_FAILED'
    if case['mode']=='sql':
        guards=[]
        for runtime in case['adapters']:
            lane=runtime.replace('.','')
            guards.append(f'io.github.ym0506.routecontract.shardingsphere{lane}.internal.ShardingSphere{lane}HookConstructionGuard.')
        if not any(frame.startswith(prefix) for frame in observed['stackFrames'] for prefix in guards): return 'CONSTRUCTION_GUARD_NOT_OBSERVED'
    return 'PASS'


def completion_status(results,partial=False):
    planned=cases();expected={c['id']:c for c in planned}
    ids=[r.get('case',{}).get('id') for r in results];pids=[r.get('observed',{}).get('pid') for r in results]
    passed=sum(r.get('outcome')=='PASS' for r in results)
    full=(len(results)==28 and len(set(ids))==28 and set(ids)==set(expected)
        and all(r['case']==expected[r['case']['id']] for r in results)
        and all(type(p) is int and p>0 for p in pids) and len(set(pids))==28 and not partial)
    parity=False
    sequence=[r for r in results if r.get('case',{}).get('mode')=='sequence' and r.get('outcome')=='PASS']
    if len(sequence)==2:
        parity=sequence[0]['observed']['snapshots'][0]['attempts']==sequence[1]['observed']['snapshots'][0]['attempts']
    status='FAILED' if passed!=len(results) or full and not parity else 'VERIFIED' if full else 'INCOMPLETE'
    return dict(status=status,fullRuntimeBoundaryMatrix=status=='VERIFIED',executedCount=len(results),passedCount=passed,orderedRuntimeParity=parity)


def fingerprint_inputs():
    preserved=[ROOT/'scripts/verify-current-entry-successor.py',ROOT/'scripts/tests/test_verify_current_entry_successor.py',
        ROOT/'docs/current-entry-migration-acceptance.md',*sorted((ROOT/'examples/current-entry-successor-consumer').rglob('*')),
        ROOT/'docs/evidence/current-entry-successor-4e06694-2026-09-08.json',ROOT/'docs/evidence/current-entry-successor-4e06694-2026-09-08.md']
    files=[Path(__file__).resolve(),ROOT/'scripts/tests/test_verify_runtime_boundary_consumer.py',ROOT/'docs/runtime-boundary-acceptance.md',
        ROOT/'docs/versioned-shardingsphere-adapters.md',ROOT/'scripts/legacy_artifact_inputs.py',ROOT/'scripts/public_split_artifacts.py',
        ROOT/'scripts/verify-gradle-legacy-artifact-consumer.py',ROOT/'scripts/verify-gradle-split-artifact-consumer.py',
        ROOT/'scripts/verify-staged-split-artifact-consumer.py',ROOT/'gradle/verification-metadata.xml',ROOT/'gradlew',
        *sorted((ROOT/'gradle/wrapper').rglob('*')),*sorted(FIXTURE.rglob('*')),
        ROOT/'examples/staged-split-artifact-consumer/build.gradle',ROOT/'examples/staged-split-artifact-consumer/settings.gradle',
        *sorted((ROOT/'examples/staged-split-artifact-consumer/gradle-locks').rglob('*')),*preserved]
    if any(p.is_symlink() for p in files): raise BoundaryError('Source inputs must not be symlinks')
    return {str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in files if p.is_file()}


def class_hashes(directories,named=False):
    result={}
    for directory in directories:
        base=Path(directory)
        if base.is_symlink() or not base.is_dir(): raise BoundaryError('Invalid consumer output directory')
        for path in base.rglob('*'):
            if path.is_symlink(): raise BoundaryError('Symlink consumer output')
            if path.is_file():
                relative=path.relative_to(base).as_posix()
                if not (relative.startswith('io/github/ym0506/routecontract/consumer/') and relative.endswith('.class') or named and relative=='module-info.class'): raise BoundaryError('Unexpected production/shadow output class')
                result[str(path)]=digest(path.read_bytes())
    if not result or named and not any(Path(p).name=='module-info.class' for p in result): raise BoundaryError('Missing consumer bytecode/module descriptor')
    return result


def prepare_lane(runtime,evidence,repository,receipt,seed,java_home,staged,split):
    lane=evidence/'lanes'/runtime;lane.mkdir(parents=True);consumer=lane/'consumer'
    staged.copy_consumer(ROOT,consumer,runtime,receipt);shutil.rmtree(consumer/'src');shutil.copytree(FIXTURE/'src',consumer/'src')
    shutil.copyfile(FIXTURE/'runtime-evidence.gradle',consumer/'runtime-evidence.gradle')
    with (consumer/'build.gradle').open('a') as f:f.write("\napply from: 'runtime-evidence.gradle'\n")
    cache=lane/'gradle-home';cache.mkdir();split.seed_wrapper_distribution(seed,cache)
    if (cache/'caches').exists():raise BoundaryError('Dependency cache was not absent')
    command=[str(consumer/'gradlew'),'--no-daemon','--no-build-cache','--no-configuration-cache','--dependency-verification=strict','--console=plain','--max-workers=2',f'-ProutecontractRuntime={runtime}',f'-ProutecontractRepository={repository}']
    for module in ('routecontract-core',ADAPTERS[runtime]):
        pin=next(p for p in receipt['artifacts'] if p['module']==module and p['name'].endswith('.jar'))
        command.append(f'-ProutecontractSha256.{module}={pin["sha256"]}')
    command.append('prepareRuntimeBoundaryClasspath')
    write_json(lane/'command.json',dict(argv=command,dependencyCacheInitiallyAbsent=True))
    with (lane/'gradle.log').open('w') as log:
        p=subprocess.run(command,cwd=consumer,env=split.clean_environment(java_home,cache),stdout=log,stderr=subprocess.STDOUT,timeout=1200)
    if p.returncode:raise BoundaryError(f'Lane {runtime} compile failed; inspect retained gradle.log')
    graph=json.loads((consumer/'build/runtime-boundary-classpath.json').read_text())
    first=[a for a in graph['artifacts'] if a['group']==GROUP]
    if sorted((a['module'],a['version']) for a in first)!=sorted([('routecontract-core','0.2.0'),(ADAPTERS[runtime],'0.2.0')]):raise BoundaryError('Wrong resolved first-party graph')
    ss=[a for a in graph['artifacts'] if a['group']=='org.apache.shardingsphere']
    if not ss or any(a['version']!=runtime for a in ss):raise BoundaryError('Mixed whole-group runtime')
    for a in graph['artifacts']:
        if digest(Path(a['path']).read_bytes())!=a['sha256']:raise BoundaryError('Resolved JAR bytes changed')
        if a['group']==GROUP and a['sha256']!=next(p['sha256'] for p in receipt['artifacts'] if p['module']==a['module'] and p['name'].endswith('.jar')):raise BoundaryError('Unreviewed resolved JAR')
    graph['compiledClasses']=class_hashes(graph['classes'])
    named=lane/'named-classes';named.mkdir()
    core=next(a['path'] for a in first if a['module']=='routecontract-core')
    third=[a['path'] for a in graph['artifacts'] if a['group']!=GROUP]
    command=[str(java_home/'bin/javac'),'--release','17','-g','-encoding','UTF-8','-Xlint:unchecked,-module','-Werror',
        '--module-path',core,'--add-reads',CONSUMER_MODULE+'=ALL-UNNAMED','-cp',os.pathsep.join(third),'-d',str(named),
        str(FIXTURE/'named-module/module-info.java'),str(FIXTURE/'src/test/java/io/github/ym0506/routecontract/consumer/RuntimeBoundaryProbe.java')]
    write_json(lane/'named-compile-command.json',dict(argv=command))
    with (lane/'named-compile.log').open('w') as log:
        p=subprocess.run(command,cwd=lane,env=split.clean_environment(java_home,cache),stdout=log,stderr=subprocess.STDOUT,timeout=120)
    if p.returncode:raise BoundaryError(f'Lane {runtime} named consumer compilation failed')
    graph['namedClasses']=[str(named)];graph['compiledNamedClasses']=class_hashes([named],True)
    write_json(lane/'resolved-classpath.json',graph)
    print('BOUNDARY_PREPARED_RUNTIME '+runtime,flush=True);return graph


def current_paths(case,repository,receipt):
    modules=['routecontract-core',*[ADAPTERS[runtime] for runtime in case['adapters']]]
    return [str(repository/next(p['relativePath'] for p in receipt['artifacts'] if p['module']==module and p['name'].endswith('.jar'))) for module in modules]


def expected_types(case,graph,repository,receipt):
    jars=current_paths(case,repository,receipt);named=case['topology']=='modulepath'
    names={'consumer':PROBE,'newEntry':'io.github.ym0506.routecontract.api.RouteContract',
        'coreBridge':'io.github.ym0506.routecontract.spi.RouteContractHookBridge','currentGuard':'io.github.ym0506.routecontract.internal.CurrentRuntimeGuard',
        'captureRegistry':'io.github.ym0506.routecontract.internal.CaptureRegistry',
        'adapter552':'io.github.ym0506.routecontract.shardingsphere552.internal.ShardingSphere552RuntimeAdapter',
        'adapter553':'io.github.ym0506.routecontract.shardingsphere553.internal.ShardingSphere553RuntimeAdapter',
        'hook552':'io.github.ym0506.routecontract.shardingsphere552.internal.RouteContract552SqlExecutionHook',
        'hook553':'io.github.ym0506.routecontract.shardingsphere553.internal.RouteContract553SqlExecutionHook'}
    result={}
    for name,fqcn in names.items():
        runtime='5.5.2' if name.endswith('552') else '5.5.3' if name.endswith('553') else None
        present=runtime is None or runtime in case['adapters']
        expected=dict(present=present,className=fqcn)
        if present:
            if name=='consumer':origin=graph['namedClasses' if named else 'classes'][0];module=CONSUMER_MODULE
            elif runtime:origin=jars[case['adapters'].index(runtime)+1];module=MODULES[ADAPTERS[runtime]]
            else:origin=jars[0];module=MODULES['routecontract-core']
            expected.update(origin=origin,moduleName=module if named else None,namedModule=named)
        result[name]=expected
    return result


def launch(case,graph,repository,receipt,java_home,result_path,port):
    first=current_paths(case,repository,receipt);third=[a['path'] for a in graph['artifacts'] if a['group']!=GROUP]
    command=[str(java_home/'bin/java'),'-Dorg.slf4j.simpleLogger.defaultLogLevel=warn']
    named=case['topology']=='modulepath';classes=graph['namedClasses' if named else 'classes']
    if named:command+=['--module-path',os.pathsep.join([*first,*classes]),'--add-modules',','.join(('ALL-MODULE-PATH',*NAMED_JDK_ROOTS)),'--add-reads',CONSUMER_MODULE+'=ALL-UNNAMED','-cp',os.pathsep.join(third),'--module',CONSUMER_MODULE+'/'+PROBE]
    else:command+=['-cp',os.pathsep.join([*first,*classes,*third]),PROBE]
    return command+[case['mode'],str(result_path),str(port if case['mode']!='capture' else 0)],first+third,classes


def verify_launch_inputs(paths,classes,graph,repository,receipt,named):
    pins={a['path']:a['sha256'] for a in graph['artifacts']}
    pins.update({str(repository/p['relativePath']):p['sha256'] for p in receipt['artifacts']})
    if len(paths)!=len(set(paths)):raise BoundaryError('Duplicate launch artifact')
    checked=[]
    for value in paths:
        path=Path(value)
        if path.is_symlink() or not path.is_file() or value not in pins or digest(path.read_bytes())!=pins[value]:raise BoundaryError('Launch artifact not reviewed or changed')
        checked.append(dict(path=value,sha256=pins[value]))
    actual=class_hashes(classes,named)
    if actual!=graph['compiledNamedClasses' if named else 'compiledClasses']:raise BoundaryError('Consumer bytecode changed')
    return dict(artifacts=checked,compiledClasses=actual)


def run_case(case,evidence,graph,repository,receipt,java_home,environment,port):
    folder=evidence/'cases'/case['id'];folder.mkdir(parents=True);output=folder/'observed.json'
    command,paths,classes=launch(case,graph,repository,receipt,java_home,output,port)
    pins=verify_launch_inputs(paths,classes,graph,repository,receipt,case['topology']=='modulepath')
    types=expected_types(case,graph,repository,receipt)
    write_json(folder/'command.json',dict(argv=command,case=case,expectedTypes=types,freshJvm=True,**pins))
    started=time.monotonic();code=None;outcome='PROCESS_FAILED'
    with (folder/'jvm.log').open('w') as log:
        try:code=subprocess.run(command,cwd=folder,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=180).returncode
        except subprocess.TimeoutExpired:outcome='PROCESS_TIMEOUT'
    result=dict(case=case,outcome=outcome,exitCode=code,elapsedSeconds=round(time.monotonic()-started,3),
        commandSha256=digest((folder/'command.json').read_bytes()),logSha256=digest((folder/'jvm.log').read_bytes()))
    if code==0 and output.is_file():
        try:
            observed=json.loads(output.read_text());result.update(observed=observed,observedSha256=digest(output.read_bytes()),outcome=classify(case,observed,types))
        except (ValueError,TypeError,KeyError,IndexError):result['outcome']='INVALID_OBSERVATION'
    try:
        if verify_launch_inputs(paths,classes,graph,repository,receipt,case['topology']=='modulepath')!=pins:
            raise BoundaryError('Launch inputs changed during the process')
        result['launchInputsUnchanged']=True
    except BoundaryError as error:result.update(outcome='INPUT_CHANGED',launchInputsUnchanged=False,inputError=str(error))
    write_json(folder/'result.json',result);print(f'BOUNDARY_CASE {case["id"]} {result["outcome"]}',flush=True);return result


def start_mysql(evidence):
    container=subprocess.check_output(['docker','run','--rm','-d','-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','-e','MYSQL_DATABASE=routecontract_runtime_boundaries','-p','127.0.0.1::3306',A29.MYSQL_IMAGE],text=True,timeout=180).strip()
    write_json(evidence/'mysql-container.json',dict(image=A29.MYSQL_IMAGE,containerId=container))
    try:
        for _ in range(120):
            if subprocess.run(['docker','exec',container,'mysqladmin','ping','-h','127.0.0.1','-uroot'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode==0:
                return container,int(subprocess.check_output(['docker','port',container,'3306/tcp'],text=True,timeout=10).strip().split(':')[-1])
            time.sleep(1)
        raise BoundaryError('MySQL startup timeout')
    except BaseException:
        subprocess.run(['docker','rm','-f',container],stdout=subprocess.DEVNULL,timeout=30);raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('repository','staged-receipt','evidence-directory','java-home','gradle-distribution-zip'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--expected-staged-receipt-sha256',required=True);p.add_argument('--staged-source-revision',required=True)
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--case',dest='case_ids',action='append')
    args=p.parse_args();evidence=args.evidence_directory.resolve();repository_source=args.repository.resolve()
    if evidence.exists() or ROOT in evidence.parents or repository_source in evidence.parents:raise BoundaryError('Evidence must be absent and outside input trees')
    evidence.mkdir(parents=True,mode=0o700);container=None;results=[]
    try:
        initial=fingerprint_inputs();write_json(evidence/'fixture-inputs.json',initial)
        receipt=load_consumer_receipt(args.staged_receipt)
        if receipt['routeContractVersion']!='0.2.0' or digest(args.staged_receipt.read_bytes())!=args.expected_staged_receipt_sha256:raise BoundaryError('Wrong reviewed receipt')
        staged=helper('boundary_staged','verify-staged-split-artifact-consumer.py');split=helper('boundary_split','verify-gradle-split-artifact-consumer.py');legacy=helper('boundary_source','verify-gradle-legacy-artifact-consumer.py')
        staged.verify_receipt(repository_source,receipt);binding=legacy.source_binding(args.staged_source_revision)
        write_json(evidence/'source-binding.json',binding);shutil.copyfile(args.staged_receipt,evidence/'staged-receipt.json')
        repository=evidence/'repository';inventory=[]
        for pin in receipt['artifacts']:
            target=repository/pin['relativePath'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repository_source/pin['relativePath'],target)
            if digest(target.read_bytes())!=pin['sha256']:raise BoundaryError('Staged copy changed')
            inventory.append(dict(pin,origin='staged',version='0.2.0'))
        A29.verify_current_names(inventory,repository)
        write_json(evidence/'verified-input-inventory.json',inventory)
        required=cases();selected=required
        if args.case_ids:
            if len(args.case_ids)!=len(set(args.case_ids)) or set(args.case_ids)-{c['id'] for c in required}:raise BoundaryError('Invalid selected IDs')
            selected=[c for c in required if c['id'] in args.case_ids]
        write_json(evidence/'case-plan.json',dict(requiredCount=28,required=required,selected=selected))
        java_home=args.java_home.resolve();split.verify_toolchain(ROOT,java_home)
        seed=evidence/'wrapper-seed';seed.mkdir();legacy.seed_distribution_zip(args.gradle_distribution_zip.resolve(),seed);split.prepare_wrapper_seed(ROOT,ROOT/'gradlew',java_home,seed)
        metadata=[]
        for module,name in MODULES.items():
            pin=next(v for v in receipt['artifacts'] if v['module']==module and v['name'].endswith('.jar'))
            command=[str(java_home/'bin/jar'),'--describe-module','--file',str(repository/pin['relativePath'])]
            output=subprocess.run(command,text=True,capture_output=True,env=split.clean_environment(java_home,seed),timeout=30)
            (evidence/(module+'-describe-module.log')).write_text(output.stdout+output.stderr)
            if output.returncode or not re.search(r'^'+re.escape(name)+r'(?:@\S+)? automatic\s*$',output.stdout,re.M):raise BoundaryError('Wrong automatic module identity')
            metadata.append(dict(module=module,automaticModuleName=name,argv=command,exitCode=output.returncode,logSha256=digest((output.stdout+output.stderr).encode())))
        write_json(evidence/'module-descriptions.json',metadata)
        runtimes=sorted(ADAPTERS if args.prepare_only else {c['runtime'] for c in selected})
        with ThreadPoolExecutor(max_workers=2) as pool:graphs=dict(zip(runtimes,pool.map(lambda r:prepare_lane(r,evidence,repository,receipt,seed,java_home,staged,split),runtimes)))
        launches=[]
        for c in selected:
            command,paths,classes=launch(c,graphs[c['runtime']],repository,receipt,java_home,evidence/'cases'/c['id']/'observed.json',1)
            launches.append(dict(case=c,argvTemplate=command,expectedTypes=expected_types(c,graphs[c['runtime']],repository,receipt),**verify_launch_inputs(paths,classes,graphs[c['runtime']],repository,receipt,c['topology']=='modulepath')))
        write_json(evidence/'prepared-launch-inputs.json',launches)
        if not args.prepare_only:
            container,port=start_mysql(evidence) if any(c['mode']!='capture' for c in selected) else (None,0)
            for c in selected:
                if fingerprint_inputs()!=initial:raise BoundaryError('Source input changed')
                results.append(run_case(c,evidence,graphs[c['runtime']],repository,receipt,java_home,split.clean_environment(java_home,seed),port));write_json(evidence/'progress.json',results)
        if fingerprint_inputs()!=initial or digest(args.staged_receipt.read_bytes())!=args.expected_staged_receipt_sha256 or legacy.source_binding(args.staged_source_revision)!=binding:raise BoundaryError('Source/receipt binding changed')
        staged.verify_receipt(repository_source,receipt);staged.verify_receipt(repository,receipt)
        completion=dict(status='PREPARED',fullRuntimeBoundaryMatrix=False,executedCount=0,passedCount=0,orderedRuntimeParity=False) if args.prepare_only else completion_status(results,bool(args.case_ids))
        summary=dict(formatVersion=1,**completion,requiredCount=28,originalA28Status='FAILED',sourceBinding=binding,stagedReceiptSha256=args.expected_staged_receipt_sha256,results=results,boundary='Existing ADR A01-A08/A10/A18/A19 representative staged runtime obligations only; A09/A11-A13/A23 separate. Original A29 remains unchanged. No publication or release-ready claim.')
        write_json(evidence/'summary.json',summary)
        if results:
            suite=ET.Element('testsuite',name='RuntimeBoundaryFreshJvmAssertions',tests=str(len(results)),failures=str(sum(r['outcome']!='PASS' for r in results)),errors='0',skipped='0')
            for r in results:
                cell=ET.SubElement(suite,'testcase',classname='RuntimeBoundaryFreshJvmAssertions',name=r['case']['id'])
                if r['outcome']!='PASS':ET.SubElement(cell,'failure',message=r['outcome'])
            ET.indent(suite);ET.ElementTree(suite).write(evidence/'TEST-runtime-boundary-subprocess-assertions.xml',encoding='utf-8',xml_declaration=True)
        print(f'BOUNDARY_{summary["status"]} passed={summary["passedCount"]}/{len(results)}',flush=True)
        return 0 if summary['status'] in ('PREPARED','VERIFIED') else 2 if summary['status']=='INCOMPLETE' else 1
    except Exception as error:
        write_json(evidence/'failure.json',dict(status='FAILED',error=str(error),completedCount=len(results)));raise
    finally:
        if container:
            try:
                with (evidence/'mysql.log').open('w') as log:subprocess.run(['docker','logs',container],stdout=log,stderr=subprocess.STDOUT,timeout=30)
            finally:subprocess.run(['docker','rm','-f',container],stdout=subprocess.DEVNULL,timeout=30)

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:print('BOUNDARY_FAILED: '+str(error),file=sys.stderr);sys.exit(1)
