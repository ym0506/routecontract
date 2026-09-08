#!/usr/bin/env python3
"""Inspect or retain unsigned 0.2 preparation evidence; never approve or publish."""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from public_split_artifacts import GROUP, GROUP_PATH, MODULES, stable_version, validate_consumer_receipt

MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
JAVADOC_JMOD_SHA256 = '4fd0541eb01b08f79a280484ec11569d87cebdf2b90a5e5b4bff695732d049ea'
SCHEMA_KIND = 'routecontract-coordinated-release-preparation'
SOURCE_PREFIX = 'io/github/ym0506/routecontract/'
MODULE_NAMES = dict(zip(MODULES, ('io.github.ym0506.routecontract.core',
    'io.github.ym0506.routecontract.shardingsphere55', 'io.github.ym0506.routecontract.shardingsphere552')))
SBOM_ROLES = {'aggregate': '', 'routecontract-core': 'core-',
    'routecontract-shardingsphere-5.5': 'published-', 'routecontract-shardingsphere-5.5.2': 'adapter552-',
    'mysql-example': 'example-', 'mysql-5.5.2-example': 'mysql552-'}
RESULT_DIRS = ['routecontract-core/build/test-results/test',
    'routecontract-shardingsphere-5.5/build/test-results/test',
    'routecontract-shardingsphere-5.5.2/build/test-results/test',
    'examples/mysql/build/test-results/test', 'examples/mysql-5.5.2/build/test-results/test']

class PreparationError(ValueError):
    pass

def sibling(name):
    path = ROOT / 'scripts' / name
    spec = importlib.util.spec_from_file_location('coordinated_' + name.replace('-', '_').replace('.', '_'), path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value

BUNDLE = sibling('prepare-central-upload-bundle.py')
ARCHIVE = sibling('install-release-assets.py')
SUMMARY = sibling('summarize-test-results.py')
POLICY = sibling('verify-supply-chain-policy.py')

def sha(payload):
    return hashlib.sha256(payload).hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()

def release_family(version):
    if re.fullmatch(r'0\.1\.(0|[1-9][0-9]*)(-rc[1-9][0-9]*)?', version or ''):
        return 'legacy'
    try:
        stable_version(version)
    except ValueError as error:
        raise PreparationError('Preparation supports historical 0.1.x or stable split 0.2.x only') from error
    return 'split'

def payload_paths(version):
    stable_version(version)
    return [str(GROUP_PATH / module / version / name)
            for module in MODULES for name in BUNDLE._payload_names(module, version)]

def read(path, maximum=MAX_FILE):
    try:
        return BUNDLE._read_stable_regular(path.absolute(), 'preparation input', maximum)
    except (OSError, ValueError, BUNDLE.BundleError) as error:
        raise PreparationError(f'Missing or unsafe preparation input: {path.name}') from error

def tree_files(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise PreparationError('Expected a regular input directory')
    result = {}
    for current, directories, filenames in os.walk(directory, followlinks=False):
        for name in directories:
            if (Path(current) / name).is_symlink():
                raise PreparationError('Input directory contains a symlink')
        for name in filenames:
            path = Path(current) / name
            result[path.relative_to(directory).as_posix()] = read(path)
            if sum(map(len, result.values())) > MAX_TOTAL:
                raise PreparationError('Input inventory exceeds its size bound')
    return result

def git(source, *args):
    return subprocess.check_output(['git', *args], cwd=source, stderr=subprocess.PIPE)

def source_identity(source, revision):
    if re.fullmatch('[0-9a-f]{40}', revision or '') is None:
        raise PreparationError('Expected exact source revision')
    if git(source, 'rev-parse', 'HEAD').decode().strip() != revision:
        raise PreparationError('Source HEAD differs from requested revision')
    if git(source, 'status', '--porcelain=v1', '--untracked-files=all', '--ignore-submodules=none').strip():
        raise PreparationError('Release preparation requires a clean exact source checkout')
    return {'revision': revision, 'tree': git(source, 'rev-parse', revision + '^{tree}').decode().strip()}

def expected_source_files(source, module):
    result = {}
    for kind in ('java', 'resources'):
        root = source / module / 'src/main' / kind
        if root.exists():
            result.update(tree_files(root))
    result.update({'META-INF/LICENSE': read(source / 'LICENSE'), 'META-INF/NOTICE': read(source / 'NOTICE')})
    return result

def class_binary_name(payload):
    # Read the JVM constant-pool shape and this_class rather than trusting ZIP names.
    if len(payload)<10 or payload[:4]!=b'\xca\xfe\xba\xbe' or int.from_bytes(payload[6:8],'big')!=61:
        raise PreparationError('Expected a Java17 class file')
    cursor=10; count=int.from_bytes(payload[8:10],'big'); pool={}; index=1
    def take(size):
        nonlocal cursor
        if cursor+size>len(payload):raise PreparationError('Truncated class file')
        value=payload[cursor:cursor+size];cursor+=size;return value
    while index<count:
        tag=take(1)[0]
        if tag==1:pool[index]=(tag,take(int.from_bytes(take(2),'big')))
        elif tag in (7,8,16,19,20):pool[index]=(tag,int.from_bytes(take(2),'big'))
        elif tag in (3,4,9,10,11,12,17,18):take(4)
        elif tag in (5,6):take(8);index+=1
        elif tag==15:take(3)
        else:raise PreparationError('Invalid constant-pool tag')
        index+=1
    take(2); owner=int.from_bytes(take(2),'big');take(2)
    try:
        tag,reference=pool[owner];string_tag,name=pool[reference]
        if tag!=7 or string_tag!=1:raise ValueError('Invalid class identity')
        result=name.decode('utf-8')
    except (KeyError,TypeError,ValueError) as error:
        raise PreparationError('Invalid class identity constant') from error
    interfaces=int.from_bytes(take(2),'big');take(interfaces*2)
    for _ in range(2):
        members=int.from_bytes(take(2),'big')
        for _ in range(members):
            take(6);attributes=int.from_bytes(take(2),'big')
            for _ in range(attributes):take(2);take(int.from_bytes(take(4),'big'))
    attributes=int.from_bytes(take(2),'big')
    for _ in range(attributes):take(2);take(int.from_bytes(take(4),'big'))
    if cursor!=len(payload):raise PreparationError('Class file has trailing bytes')
    return result

def jar_contents(path):
    payload = read(path, ARCHIVE.MAX_JAR_BYTES)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries=archive.infolist()
        if not entries or len(entries)>ARCHIVE.MAX_JAR_ENTRIES:
            raise PreparationError('JAR has an invalid entry count')
        data={}; logical={}; trie={}; portable={}; component_count=[0]; total=0; seen=set()
        for entry in entries:
            name=entry.filename
            original=getattr(entry,'orig_filename',name)
            pure=Path(name)
            if original!=name or name in seen or not name or '\x00' in name or '\\' in name or name.startswith('/') or '..' in pure.parts or any(ord(c)<32 or ord(c)==127 for c in name) or entry.flag_bits&1:
                raise PreparationError('JAR contains unsafe, duplicate or encrypted entries')
            seen.add(name)
            canonical='/'.join(pure.parts)+('/' if entry.is_dir() else '')
            mode=stat.S_IFMT(entry.external_attr>>16)
            if canonical!=name or mode not in ((0,stat.S_IFDIR) if entry.is_dir() else (0,stat.S_IFREG)):
                raise PreparationError('JAR entry path/type is not canonical')
            ARCHIVE.register_archive_path(name.rstrip('/'),entry.is_dir(),label='split JAR',
                logical_entries=logical,portable_trie=trie,portable_paths=portable,total_path_components=component_count)
            total+=entry.file_size
            if total>ARCHIVE.MAX_JAR_UNCOMPRESSED_BYTES or (entry.is_dir() and entry.file_size):
                raise PreparationError('JAR exceeds expanded bounds or has a directory payload')
            if ARCHIVE.crosses_jts_or_mahout_distribution_boundary(name):
                raise PreparationError('JAR crosses the JTS/Mahout distribution boundary')
            if not entry.is_dir():data[name]=archive.read(entry)
        ARCHIVE.validate_archive_path_graph(logical,portable,label='split JAR')
        if not {'META-INF/LICENSE','META-INF/NOTICE'} <= data.keys():
            raise PreparationError('JAR is missing first-party legal files')
        if archive.testzip() is not None:
            raise PreparationError('JAR CRC failed')
    return data

def inspect_jar(path, module, source, classifier, release_javadoc):
    label = {'': 'split main JAR', '-sources': 'sources JAR', '-javadoc':
        'Javadoc JAR' if release_javadoc else 'local Javadoc payload'}[classifier]
    data = jar_contents(path)
    with zipfile.ZipFile(path) as archive:
        if classifier == '-sources':
            ARCHIVE.validate_sources_classifier_contents(archive, set(data))
        elif classifier == '-javadoc':
            ARCHIVE.validate_thin_first_party_jar_inventory(set(data), label)
            if release_javadoc:
                api_packages = {name.rsplit('/', 1)[0]
                                for name in expected_source_files(source, module)
                                if name.startswith(SOURCE_PREFIX) and name.endswith('.java')}
                ARCHIVE.validate_javadoc_classifier_contents(archive, api_packages=api_packages)
    for name in ('LICENSE', 'NOTICE'):
        if data['META-INF/' + name] != read(source / name):
            raise PreparationError('Embedded legal file differs from source revision')
    if classifier == '-sources':
        actual = {name: value for name, value in data.items() if name != 'META-INF/MANIFEST.MF'}
        if actual != expected_source_files(source, module):
            raise PreparationError('Sources classifier differs from exact module source/resources')
    elif not classifier:
        manifest = ARCHIVE.parse_jar_main_manifest(data.get('META-INF/MANIFEST.MF', b''))
        if manifest.get('automatic-module-name') != MODULE_NAMES[module]:
            raise PreparationError('Wrong split automatic-module identity')
        classes = {name: value for name, value in data.items() if name.endswith('.class')}
        if not classes or any(not name.startswith(SOURCE_PREFIX) or name.endswith('module-info.class')
                or value[:4] != b'\xca\xfe\xba\xbe' or int.from_bytes(value[6:8], 'big') != 61
                for name, value in classes.items()):
            raise PreparationError('Invalid first-party Java17 class inventory')
        sources=expected_source_files(source,module)
        for name,value in classes.items():
            if class_binary_name(value)+'.class'!=name:
                raise PreparationError('Class identity does not match its JAR path')
            outer=name.removesuffix('.class').split('$',1)[0]+'.java'
            if outer not in sources:
                raise PreparationError('Class has no corresponding first-party module source')
        services = {name: value for name, value in data.items() if name.startswith('META-INF/services/')}
        if set(data) != set(classes) | set(services) | {'META-INF/MANIFEST.MF','META-INF/LICENSE','META-INF/NOTICE'}:
            raise PreparationError('Main JAR contains undeclared resources or bundled payloads')
        if module == MODULES[0]:
            if services or SOURCE_PREFIX+'api/RouteContract.class' not in classes:
                raise PreparationError('Core must own current API and no providers')
            if any(b'org/apache/shardingsphere/' in value for value in classes.values()):
                raise PreparationError('Core contains ShardingSphere binary references')
        else:
            lane = '553' if module == MODULES[1] else '552'
            prefix = SOURCE_PREFIX + 'shardingsphere' + lane + '/internal/'
            if any(not name.startswith(prefix) for name in classes):
                raise PreparationError('Adapter contains core/foreign implementation classes')
            expected = {
                'META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook':
                    f'io.github.ym0506.routecontract.shardingsphere{lane}.internal.RouteContract{lane}SqlExecutionHook',
                'META-INF/services/io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter':
                    f'io.github.ym0506.routecontract.shardingsphere{lane}.internal.ShardingSphere{lane}RuntimeAdapter'}
            if set(services) != set(expected) or any(ARCHIVE.parse_service_descriptor(services[k].decode()) != [v] for k,v in expected.items()):
                raise PreparationError('Adapter provider inventory differs from exact lane')
        return set(classes)
    return set()

def inspect_payloads(repository, source, version, *, release_javadoc=True):
    stable_version(version)
    contents = tree_files(repository)
    required = set(payload_paths(version))
    metadata = {str(GROUP_PATH / m / 'maven-metadata.xml') for m in MODULES}
    expected = required | metadata
    for name in list(expected):
        expected.update(name + '.' + algorithm for algorithm in ('md5', 'sha1', 'sha256', 'sha512'))
    if set(contents) != expected:
        raise PreparationError('Unsigned coordinated repository must contain exactly 15 payloads and their local metadata/checksums')
    for name in required | metadata:
        for algorithm in ('md5','sha1','sha256','sha512'):
            BUNDLE._verify_checksum(contents, name, name+'.'+algorithm, algorithm)
    BUNDLE._verify_xml_coordinates_and_graph(contents, version)
    BUNDLE._verify_module_metadata_and_graph(contents, version)
    records, classes = [], []
    for module in MODULES:
        pom=ET.fromstring(contents[str(GROUP_PATH/module/version/f'{module}-{version}.pom')])
        ns='{http://maven.apache.org/POM/4.0.0}'
        for field in ('name','description','url','scm/'+ns+'connection','scm/'+ns+'developerConnection','scm/'+ns+'url'):
            values=pom.findall(ns+field)
            if len(values)!=1 or not values[0].text or not values[0].text.strip():
                raise PreparationError('POM is missing unique project/SCM publication metadata')
        licenses=pom.findall(ns+'licenses/'+ns+'license')
        if len(licenses)!=1 or licenses[0].findtext(ns+'name')!='The Apache License, Version 2.0' or licenses[0].findtext(ns+'url')!='https://www.apache.org/licenses/LICENSE-2.0.txt':
            raise PreparationError('POM does not declare exact project license')
        developers=pom.findall(ns+'developers/'+ns+'developer')
        if not developers or any(not d.findtext(ns+'id') or not d.findtext(ns+'name') for d in developers):
            raise PreparationError('POM is missing developer publication metadata')
        for classifier in ('','-sources','-javadoc'):
            filename = f'{module}-{version}{classifier}.jar'
            relative = str(GROUP_PATH/module/version/filename)
            classes.append(inspect_jar(repository/relative, module, source, classifier, release_javadoc))
        for name in BUNDLE._payload_names(module,version):
            payload = contents[str(GROUP_PATH/module/version/name)]
            records.append({'artifactId':module,'name':name,'size':len(payload),'sha256':sha(payload)})
    nonempty = [c for c in classes if c]
    if any(a & b for index,a in enumerate(nonempty) for b in nonempty[index+1:]):
        raise PreparationError('Split artifact class inventories overlap')
    consumer = validate_consumer_receipt({'formatVersion':1,'routeContractVersion':version,'artifacts':[
        {'module':m,'name':f'{m}-{version}.{ext}','relativePath':str(GROUP_PATH/m/version/f'{m}-{version}.{ext}'),
         'sha256':sha(contents[str(GROUP_PATH/m/version/f'{m}-{version}.{ext}')])}
        for m in MODULES for ext in ('jar','pom','module')]})
    return {'payloads':records,'contents':contents,'consumerReceipt':consumer}

def verify_toolchain(java_home):
    release = read(java_home/'release',1024*1024)
    lines = release.decode().splitlines()
    for key,value in [('IMPLEMENTOR_VERSION','Temurin-17.0.20.1+1'),('JAVA_RUNTIME_VERSION','17.0.20.1+1')]:
        if [line for line in lines if line.startswith(key+'=')] != [f'{key}="{value}"']:
            raise PreparationError('Release preparation requires exact Temurin17.0.20.1+1')
    command = subprocess.run([str(java_home/'bin/java'),'-fullversion'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True,timeout=30)
    if command.stdout.decode().strip() != 'openjdk full version "17.0.20.1+1"':
        raise PreparationError('Release Java executable does not match pinned runtime')
    jmod = read(java_home/'jmods/jdk.javadoc.jmod')
    if sha(jmod) != JAVADOC_JMOD_SHA256:
        raise PreparationError('Release Javadoc module differs from pinned Linux toolchain')
    return {'runtime':'Temurin-17.0.20.1+1','releaseFileSha256':sha(release),'javadocJmodSha256':sha(jmod)}

def evidence_inputs(source, version, revision, repository, java_home):
    identity = source_identity(source,revision)
    toolchain = verify_toolchain(java_home)
    inspected = inspect_payloads(repository,source,version)
    files = {}
    for module in MODULES:
        for record in [r for r in inspected['payloads'] if r['artifactId']==module]:
            name = record['name']
            generated = source/module/'build'/('libs/'+name if name.endswith('.jar') else
                'publications/mavenJava/'+('pom-default.xml' if name.endswith('.pom') else 'module.json'))
            if sha(read(generated)) != record['sha256']:
                raise PreparationError('Staged payload differs from exact-source generated build output')
    files[f'routecontract-{version}-source.zip'] = git(source,'archive','--format=zip',f'--prefix=routecontract-{version}/',revision)
    # Exact git archive bytes, not legacy all-in-one source requirements.
    if len(files[f'routecontract-{version}-source.zip'])>MAX_FILE:
        raise PreparationError('Source archive exceeds size bound')
    arguments = ['verify']
    for role,prefix in SBOM_ROLES.items():
        for ext in ('json','xml'):
            path=source/'build/reports/verified-sbom'/role/('bom.'+ext)
            files[f'{role}-cyclonedx.{ext}']=read(path)
            arguments += ['--'+prefix+'sbom'+('-xml' if ext=='xml' else ''),str(path)]
    for module,prefix in zip(MODULES,('core','published','adapter552')):
        arguments += ['--'+prefix+'-pom',str(source/module/'build/publications/mavenJava/pom-default.xml'),
            '--'+prefix+'-lock',str(source/module/'gradle.lockfile')]
    security=source/'build/reports/security'
    retained=read(security/'supply-chain-evidence.json',1024*1024)
    document=BUNDLE._load_json(retained,'supply-chain evidence',require_canonical=False)
    if document.get('schemaVersion')!=3 or document.get('revision')!=revision or document.get('sourceTree')!=identity['tree']:
        raise PreparationError('Supply-chain evidence must be exact-source six-role format3')
    arguments += ['--policy',str(source/'security/supply-chain-policy.json'),
        '--scanner-lock',str(source/'security/osv-scanner.lock.json'),
        '--scanner-config',str(source/'security/osv-scanner.toml'),
        '--scanner-platform',document['scanner']['platform'],
        '--inventory',str(security/'derived/gradle.lockfile'),'--raw-scan',str(security/'osv-raw.json'),
        '--revision',revision,'--source-tree',identity['tree']]
    # Recompute semantic SBOM/license/OSV evidence from the retained raw scan.
    # No scanner invocation, download, signature or approval is performed here.
    with tempfile.TemporaryDirectory(prefix='routecontract-preparation-policy-') as tmp:
        output=Path(tmp)/'verified.json'
        parsed=POLICY._parser().parse_args(arguments+['--output',str(output)])
        with contextlib.redirect_stdout(io.StringIO()):
            parsed.handler(parsed)
        if read(output)!=retained:
            raise PreparationError('Retained supply-chain summary differs from semantic recomputation')
    files['supply-chain-evidence.json']=retained
    summary=SUMMARY.build_summary(revision,[source/x for x in RESULT_DIRS]).encode()
    files['test-summary.txt']=summary
    files['toolchain.json']=canonical(toolchain)
    # Revalidate source and all supplied bytes after external readers complete.
    if source_identity(source,revision)!=identity or tree_files(repository)!=inspected['contents']:
        raise PreparationError('Source or artifact inputs changed during preparation')
    return identity,toolchain,inspected,files

def collection_document(identity,toolchain,inspected,files,version):
    return {'formatVersion':2,'kind':SCHEMA_KIND,'sourceRevision':identity['revision'],'sourceTree':identity['tree'],
        'coordinateSet':{'groupId':GROUP,'artifactIds':list(MODULES),'version':version},'toolchain':toolchain,
        'payloads':inspected['payloads'],
        'evidence':[{'name':n,'size':len(b),'sha256':sha(b)} for n,b in sorted(files.items())],
        'repositoryFiles':[{'name':n,'size':len(b),'sha256':sha(b)} for n,b in sorted(inspected['contents'].items())],
        'reviewed':False,'signed':False,'published':False,'publicationHeld':True,
        'boundary':'Unsigned preparation only. Remaining ADR and human review, signatures, final tag/run provenance, upload and public availability remain separate.'}

def collect(repository, source, version, revision, java_home, output):
    if output.exists() or output.is_symlink():
        raise PreparationError('Preparation output must be absent')
    repository_absolute=repository.absolute()
    output_absolute=output.absolute()
    if output_absolute==repository_absolute or repository_absolute in output_absolute.parents or output_absolute in repository_absolute.parents or output_absolute in source.absolute().parents:
        raise PreparationError('Preparation output must not overlap an input repository or contain its source')
    identity,toolchain,inspected,files=evidence_inputs(source,version,revision,repository,java_home)
    document=collection_document(identity,toolchain,inspected,files,version)
    inventory={'repository/'+n:b for n,b in inspected['contents'].items()}
    inventory.update({'evidence/'+n:b for n,b in files.items()})
    inventory['candidate-payloads.json']=canonical(document)
    inventory['consumer-receipt.json']=canonical(inspected['consumerReceipt'])
    checksums=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(inventory.items())).encode()
    # Never remove an existing destination or retry an ambiguous partial write.
    if not output.parent.is_dir() or output.parent.resolve()!=output.parent.absolute() or output.parent.is_symlink():
        raise PreparationError('Output parent must already exist and be canonical without symlinks')
    output.mkdir(mode=0o700)
    for name,payload in {**inventory,'SHA256SUMS':checksums}.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(payload)
    verify(output,source,version,revision,java_home)
    return document

def verify(output,source,version,revision,java_home):
    identity,toolchain,inspected,files=evidence_inputs(source,version,revision,output/'repository',java_home)
    document=collection_document(identity,toolchain,inspected,files,version)
    expected={'repository/'+n:b for n,b in inspected['contents'].items()}
    expected.update({'evidence/'+n:b for n,b in files.items()})
    expected['candidate-payloads.json']=canonical(document)
    expected['consumer-receipt.json']=canonical(inspected['consumerReceipt'])
    expected['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(expected.items())).encode()
    if tree_files(output)!=expected:
        raise PreparationError('Retained preparation inventory/receipt/checksums differ from verified inputs')
    return document

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('command',choices=('inspect-payloads','collect','verify'))
    parser.add_argument('--repository',type=Path)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--revision')
    parser.add_argument('--java-home',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    try:
        if release_family(args.version)!='split':
            raise PreparationError('Historical releases must use their historical installer/receipt path')
        if args.command=='inspect-payloads':
            if args.repository is None:raise PreparationError('Payload inspection requires --repository')
            result=inspect_payloads(args.repository,args.source_root,args.version,release_javadoc=False)
            print(json.dumps({'formatVersion':2,'kind':'routecontract-local-payload-inspection','payloads':result['payloads'],
                'releasePreparationVerified':False,'reviewed':False,'signed':False,'published':False,
                'boundary':'Local15-payload shape/source/metadata check only; release JDK, SBOM/OSV, JUnit and source revision provenance not established.'},sort_keys=True))
        else:
            if args.revision is None or args.java_home is None or args.output is None:
                raise PreparationError('Full preparation requires exact --revision, --java-home and --output')
            if args.command=='collect':
                if args.repository is None:raise PreparationError('Collection requires --repository')
                collect(args.repository,args.source_root,args.version,args.revision,args.java_home,args.output)
            else:verify(args.output,args.source_root,args.version,args.revision,args.java_home)
            print(f'ROUTECONTRACT_COORDINATED_PREPARATION_VERIFIED version={args.version} payloads=15 publicationHeld=true')
        return 0
    except (PreparationError,ValueError,OSError,KeyError,subprocess.SubprocessError,ARCHIVE.InstallError,BUNDLE.BundleError,POLICY.PolicyError) as error:
        print('Coordinated preparation failed: '+str(error),file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
