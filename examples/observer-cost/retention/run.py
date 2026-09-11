#!/usr/bin/env python3
"""Inspect completed capture lifecycles in child JVMs using live-object histograms."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import re
import shutil
import subprocess
import threading

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = Path('io/github/ym0506/routecontract/examples/firstproject')
PREFIX = 'io.github.ym0506.routecontract.'
CLASSES = tuple(PREFIX + name for name in (
    'CapturedResult', 'RouteSnapshot', 'PhysicalExecutionAttempt',
    'internal.CaptureScope', 'internal.CaptureToken', 'internal.MutableCapture', 'internal.MutableAttempt'))
JAR_HASH = '9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def parse_histogram(text):
    counts = dict.fromkeys(CLASSES, 0)
    total_instances = total_bytes = rows = 0
    for line in text.splitlines():
        match = re.fullmatch(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)(?:\s+.*)?', line)
        if match:
            instances, size, name = match.groups()
            total_instances += int(instances)
            total_bytes += int(size)
            rows += 1
            if name in counts:
                counts[name] += int(instances)
    total = re.findall(r'^Total\s+(\d+)\s+(\d+)\s*$', text, re.MULTILINE)
    if rows == 0 or len(total) != 1 or tuple(map(int, total[0])) != (total_instances, total_bytes):
        raise ValueError('Incomplete or inconsistent live-object histogram')
    return {'instances': counts, 'totalLiveObjectBytes': total_bytes, 'histogramRows': rows}


def require_zero(observation):
    retained = {name: count for name, count in observation['instances'].items() if count != 0}
    if retained:
        raise ValueError('Per-capture objects remain at a quiescent checkpoint: ' + str(retained))


def check_checkpoint(event, phase, smoke):
    if event.get('event') != 'checkpoint' or event.get('phase') != phase:
        raise ValueError('Unexpected checkpoint order or event')
    if event.get('publicJarSha256') != JAR_HASH or not event.get('java', '').startswith('17.'):
        raise ValueError('Wrong loaded JAR or JVM identity')
    block = int(phase.split('-')[1]) if phase.startswith('block-') else 0
    expected = block * (160 if smoke else 10000)
    for key, value in (('operations', expected), ('successes', expected * 9 // 10),
                       ('exceptions', expected // 20), ('errors', expected // 20)):
        if type(event.get(key)) is not int or event[key] != value:
            raise ValueError('Unexpected completed-operation counter: ' + key)
    if type(event.get('workloadNanos')) is not int or event['workloadNanos'] < 0:
        raise ValueError('Invalid workload duration')
    if block and event['workloadNanos'] == 0:
        raise ValueError('Missing measured workload duration')


def run_trial(command, jcmd, directory, smoke):
    directory.mkdir()
    events = queue.Queue()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1)

    def drain():
        with (directory / 'process.log').open('w', encoding='utf-8') as log:
            for line in process.stdout:
                log.write(line)
                if line.startswith('RETENTION_JSON '):
                    events.put(line[len('RETENTION_JSON '):])
        events.put(None)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    observations = []
    blocks = 2 if smoke else 10
    phases = ['held', 'released', 'warmup', *[f'block-{i}' for i in range(1, blocks + 1)]]
    try:
        for phase in phases:
            raw = events.get(timeout=300)
            if raw is None:
                raise ValueError('JVM exited before all checkpoints')
            event = json.loads(raw)
            check_checkpoint(event, phase, smoke)
            histogram_command = [str(jcmd), str(process.pid), 'GC.class_histogram']
            result = subprocess.run(histogram_command, text=True, capture_output=True, check=True, timeout=60)
            path = directory / (phase + '.histogram.txt')
            path.write_text(result.stdout, encoding='utf-8')
            observation = parse_histogram(result.stdout)
            if phase == 'held':
                try:
                    require_zero(observation)
                except ValueError:
                    pass
                else:
                    raise ValueError('Retained-result negative control was not detected')
                for name, count in (('CapturedResult', 16), ('RouteSnapshot', 16), ('PhysicalExecutionAttempt', 24)):
                    if observation['instances'][PREFIX + name] != count:
                        raise ValueError('Retained-result control has unexpected live counts')
            else:
                require_zero(observation)
            observation.update(event)
            observation.update({'histogramSha256': sha256(path), 'diagnosticCommand': histogram_command,
                                'zeroRetentionGatePassed': phase != 'held'})
            observations.append(observation)
            write_json(directory / 'checkpoints.json', observations)
            print(f'{directory.name}: {phase}; operations={event["operations"]}; '
                  f'liveBytes={observation["totalLiveObjectBytes"]}; '
                  + ('retained control detected' if phase == 'held' else 'per-capture instances=0'), flush=True)
            process.stdin.write('continue\n')
            process.stdin.flush()
        raw = events.get(timeout=300)
        if raw is None:
            raise ValueError('Missing completion event')
        completed = json.loads(raw)
        if completed != {'event': 'complete', 'operations': 320 if smoke else 100000,
                         'mode': 'smoke' if smoke else 'full'}:
            raise ValueError('Invalid completion event')
        if process.wait(timeout=60) != 0:
            raise ValueError('JVM failed during cleanup')
        reader.join(timeout=5)
        if events.get(timeout=5) is not None:
            raise ValueError('Unexpected event after completion')
        return {'status': 'SMOKE_ONLY_PASS' if smoke else 'COMPLETED', 'checkpoints': observations}
    finally:
        if process.poll() is None:
            try:
                process.stdin.write('stop\n')
                process.stdin.flush()
                process.wait(timeout=30)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        process.stdin.close()
        reader.join(timeout=5)
        process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--maven-repository', type=Path)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists() or output.is_relative_to(ROOT):
        parser.error('Use a new output directory outside the repository')
    jdk = Path(os.environ.get('JAVA_HOME', ''))
    java, jcmd = jdk / 'bin/java', jdk / 'bin/jcmd'
    if not java.is_file() or not jcmd.is_file() or not shutil.which('mvn'):
        parser.error('Select a Java 17 JDK with JAVA_HOME and make Maven available')
    runtime = subprocess.check_output([str(java), '-version'], stderr=subprocess.STDOUT, text=True).strip()
    if not ('version "17.' in runtime or 'openjdk 17.' in runtime):
        parser.error('Select Java 17')
    subprocess.run(['docker', 'info'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    output.mkdir(parents=True)
    settings = ROOT / 'examples/public-maven-release-consumer/settings.xml'
    fixture = ROOT / 'examples/first-project/src/test/java' / PACKAGE
    sources = output / 'sources' / PACKAGE
    sources.mkdir(parents=True)
    inputs = [HERE / 'src/main/java' / PACKAGE / 'CaptureRetentionProbe.java', fixture / 'OrderFixture.java', fixture / 'OrderRepository.java']
    for source in inputs:
        shutil.copyfile(source, sources / source.name)
    inputs += [HERE / 'run.py', HERE / 'README.md', HERE.parent / 'pom.xml', settings,
               ROOT / 'examples/first-project/src/test/resources/sharding.yaml']
    repository = (args.maven_repository or output / 'm2').expanduser().resolve()
    receipt = {'status': 'RUNNING', 'startedAt': datetime.now(timezone.utc).isoformat(),
               'sourceRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'sourceInputs': {str(p.relative_to(ROOT)): sha256(p) for p in inputs},
               'runtime': runtime, 'maven': subprocess.check_output(['mvn', '-version'], text=True).strip(),
               'logicalCpuCount': os.cpu_count(), 'os': platform.system() + ' ' + platform.release(), 'arch': platform.machine(),
               'docker': subprocess.check_output(['docker', 'version', '--format', '{{.Server.Version}}'], text=True).strip(),
               'smoke': args.smoke, 'callers': 4, 'forks': 1 if args.smoke else 3,
               'operationsPerFork': 320 if args.smoke else 100000, 'trials': []}
    write_json(output / 'run.json', receipt)
    try:
        classpath_file = output / 'classpath.txt'
        command = ['mvn', '-B', '-ntp', '-f', str(HERE.parent / 'pom.xml'), '-s', str(settings), '-gs', str(settings),
                   '-Dmaven.repo.local=' + str(repository), '-Dobserver.build.directory=' + str(output / 'build'),
                   '-Dobserver.source.directory=' + str(output / 'sources'), 'compile', 'dependency:build-classpath',
                   '-Dmdep.outputFile=' + str(classpath_file)]
        with (output / 'build.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
        paths = [Path(p) for p in classpath_file.read_text().strip().split(os.pathsep)]
        routecontract = [p for p in paths if p.name.startswith('routecontract-')]
        if len(routecontract) != 1 or sha256(routecontract[0]) != JAR_HASH:
            raise ValueError('Expected exactly one immutable public 0.1.3 JAR')
        for path in paths:
            if 'org/apache/shardingsphere/' in path.as_posix() and path.parent.name != '5.5.3':
                raise ValueError('Mismatched ShardingSphere dependency')
        receipt['dependencies'] = {str(p.relative_to(repository)): sha256(p) for p in paths}
        command = [str(java), '-Xms512m', '-Xmx512m', '-XX:+UseG1GC', '-Dapi.version=1.44',
                   '-Dorg.slf4j.simpleLogger.defaultLogLevel=warn', '-cp',
                   os.pathsep.join([str(output / 'build/classes'), *map(str, paths)]),
                   'io.github.ym0506.routecontract.examples.firstproject.CaptureRetentionProbe',
                   'smoke' if args.smoke else 'full']
        receipt['javaCommand'] = command
        write_json(output / 'run.json', receipt)
        for trial in range(1, receipt['forks'] + 1):
            receipt['trials'].append(run_trial(command, jcmd, output / f'trial-{trial}', args.smoke))
            write_json(output / 'run.json', receipt)
        receipt['status'] = 'SMOKE_ONLY_PASS' if args.smoke else 'DIAGNOSTIC_RUN_COMPLETE'
        print(receipt['status'], flush=True)
    except BaseException as error:
        receipt.update(status='FAILED', errorType=type(error).__name__)
        raise
    finally:
        receipt['finishedAt'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'run.json', receipt)


if __name__ == '__main__':
    main()
