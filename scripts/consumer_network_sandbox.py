"""Prove and apply a local macOS external-network barrier for offline consumers.

Loopback and the exact local Docker Unix socket remain available for the real
database fixture. No global network setting is changed. Other OSes fail closed.
"""
from __future__ import annotations

import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import platform
import re
import socket
import ssl
import subprocess
import sys
import threading
from urllib.parse import urlsplit

PUBLIC_HOST = 'repo.maven.apache.org'
PUBLIC_PATH = ('/maven2/io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/'
               '0.1.3/routecontract-shardingsphere-5.5-0.1.3.pom')
SANDBOX = Path('/usr/bin/sandbox-exec')
JAVA_IPV4_OPTION = '-Djava.net.preferIPv4Stack=true'
PULL_POLICY_CLASS = 'io.github.ym0506.routecontract.a24.OfflineImagePullPolicy'
MYSQL_SOURCE_IMAGE = 'mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb'
MYSQL_IMAGE = 'mysql@' + MYSQL_SOURCE_IMAGE.split('@')[1]
RYUK_TAG = 'testcontainers/ryuk:0.12.0'
JAVA_CONTROL = '''import java.net.*;
public final class A24NetworkControl {
  public static void main(String[] args) throws Exception {
    if (!"true".equals(System.getProperty("java.net.preferIPv4Stack"))) {
      throw new IllegalStateException("Trusted IPv4 property missing");
    }
    try (Socket local = new Socket()) {
      local.connect(new InetSocketAddress("127.0.0.1", Integer.parseInt(args[0])), 5000);
    }
    try (Socket external = new Socket()) {
      external.connect(new InetSocketAddress(args[1], 443), 5000);
      throw new IllegalStateException("External connection was permitted");
    } catch (SocketException expected) {
      if (!expected.getMessage().contains("Operation not permitted")) throw expected;
      System.out.println("A24_JAVA_NETWORK_VERIFIED feature=" + Runtime.version().feature()
          + " loopback=ALLOWED external=OS_DENIED ipv4=true");
    }
  }
}
'''

PULL_POLICY_SOURCE = '''package io.github.ym0506.routecontract.a24;
import java.util.Arrays;
import org.testcontainers.images.ImagePullPolicy;
import org.testcontainers.utility.DockerImageName;
public final class OfflineImagePullPolicy implements ImagePullPolicy {
    public OfflineImagePullPolicy() { }
    @Override
    public boolean shouldPull(DockerImageName imageName) {
        String allowed = System.getenv("ROUTECONTRACT_A24_LOCAL_IMAGES");
        String image = imageName.asCanonicalNameString();
        if (allowed == null || !Arrays.asList(allowed.split(";")).contains(image)) {
            throw new IllegalStateException("Unapproved A24 fixture image: " + image);
        }
        if (!"true".equals(System.getProperty("java.net.preferIPv4Stack"))) {
            throw new IllegalStateException("A24 test JVM IPv4 property missing");
        }
        System.out.println("A24_IMAGE_PULL_BLOCKED image=" + image);
        return false;
    }
}
'''


class NetworkBarrierError(RuntimeError):
    pass


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def controlled_environment(environment: dict, *, docker_socket: Path | None = None,
                           images: dict | None = None) -> dict:
    """Replace ambient JVM/proxy/Testcontainers options, including inherited children."""
    result = {name: value for name, value in environment.items()
              if not name.lower().endswith('_proxy')
              and name.lower() not in ('proxy', 'classpath')
              and not name.startswith(('TESTCONTAINERS_', 'DOCKER_', 'ROUTECONTRACT_A24_'))
              and name not in ('JAVA_OPTS', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS',
                               '_JAVA_OPTIONS', 'MAVEN_OPTS', 'MAVEN_DEBUG_OPTS', 'GRADLE_OPTS')}
    result['JAVA_TOOL_OPTIONS'] = JAVA_IPV4_OPTION
    result['LC_ALL'] = 'C'
    result['LANG'] = 'C'
    if docker_socket is not None:
        result['DOCKER_HOST'] = 'unix://' + str(docker_socket)
        result['TESTCONTAINERS_HOST_OVERRIDE'] = '127.0.0.1'
        result['TESTCONTAINERS_CHECKS_DISABLE'] = 'true'
        result['TESTCONTAINERS_RYUK_DISABLED'] = 'false'
        result['TESTCONTAINERS_REUSE_ENABLE'] = 'false'
    if images is not None:
        result['TESTCONTAINERS_PULL_POLICY'] = PULL_POLICY_CLASS
        result['TESTCONTAINERS_RYUK_CONTAINER_IMAGE'] = images['ryuk']['reference']
        result['ROUTECONTRACT_A24_LOCAL_IMAGES'] = ';'.join(
            images[name]['reference'] for name in ('mysql', 'ryuk'))
    return result


def inspect_local_images(docker_socket: Path) -> dict:
    result = {}
    for name, image in (('mysql', MYSQL_IMAGE), ('ryuk', RYUK_TAG)):
        command = ['docker', '--host', 'unix://' + str(docker_socket), 'image', 'inspect',
                   '--format', '{{json .}}', image]
        inspected = subprocess.run(command, capture_output=True, text=True, timeout=20)
        if inspected.returncode != 0:
            raise NetworkBarrierError('Required local fixture image missing; no pull was attempted: ' + image)
        details = json.loads(inspected.stdout)
        identity = details.get('Id', '')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', identity):
            raise NetworkBarrierError('Docker returned no immutable image identity')
        if name == 'ryuk':
            digests = [entry for entry in details.get('RepoDigests', [])
                       if re.fullmatch(r'testcontainers/ryuk@sha256:[0-9a-f]{64}', entry)]
            if len(digests) != 1:
                raise NetworkBarrierError('Ryuk must have one verified repository digest')
            image = digests[0]
        result[name] = {'reference': image, 'imageId': identity,
                        'repoDigests': sorted(details.get('RepoDigests', []))}
    return result


def install_pull_policy(consumer: Path) -> Path:
    policy = consumer / 'src/test/java' / (PULL_POLICY_CLASS.replace('.', '/') + '.java')
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(PULL_POLICY_SOURCE, encoding='utf-8')
    return policy


def require_same_images(expected: dict, actual: dict) -> None:
    if set(expected) != {'mysql', 'ryuk'} or expected != actual:
        raise NetworkBarrierError('Online and offline must use the same pinned local image manifest')


def verify_pull_policy(output: str, images: dict) -> dict:
    expected = {images[name]['reference'] for name in ('mysql', 'ryuk')}
    observed = set(re.findall(r'^A24_IMAGE_PULL_BLOCKED image=(\S+)\s*$', output, re.MULTILINE))
    if observed != expected:
        raise NetworkBarrierError('Actual no-pull policy invocation for both approved images is required')
    return {'policyClass': PULL_POLICY_CLASS, 'actualInvocations': sorted(observed),
            'javaTestIpv4Property': True}


def require_closed_endpoint(url: str) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port:
        raise NetworkBarrierError('The prime must use a controlled loopback HTTP endpoint')
    try:
        with socket.create_connection((parsed.hostname, parsed.port), timeout=5):
            pass
    except ConnectionRefusedError:
        return {'url': url, 'connectionAfterShutdown': 'REFUSED'}
    raise NetworkBarrierError('Prime endpoint must refuse a connection before offline replay')


def local_docker_socket() -> Path:
    host = os.environ.get('DOCKER_HOST')
    if not host:
        host = subprocess.check_output(
            ['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'],
            text=True, timeout=15).strip()
    if not host.startswith('unix://'):
        raise NetworkBarrierError('Offline MySQL proof requires a local Docker Unix socket')
    path = Path(host[7:])
    if not path.is_absolute() or not path.is_socket():
        raise NetworkBarrierError('Docker endpoint must identify an existing local Unix socket')
    return path


def policy_text(docker_socket: Path) -> str:
    if not docker_socket.is_absolute():
        raise NetworkBarrierError('The Docker socket path must be absolute')
    paths = {str(docker_socket), str(docker_socket.resolve(strict=True))}
    conventional = Path('/var/run/docker.sock')
    if conventional.exists() and conventional.resolve() == docker_socket.resolve():
        paths.add(str(conventional))
    rules = ['(version 1)', '(allow default)', '(deny network-outbound)',
             '(allow network-outbound (remote ip "localhost:*"))']
    rules += ['(allow network-outbound (literal ' + json.dumps(path) + '))'
              for path in sorted(paths)]
    return '\n'.join(rules) + '\n'


def sandboxed(command: list[str], barrier: dict) -> list[str]:
    profile = Path(barrier['profilePath'])
    if (sys.platform != 'darwin' or not SANDBOX.is_file() or not command
            or profile.is_symlink() or not profile.is_file()
            or digest(profile.read_bytes()) != barrier['profileSha256']):
        raise NetworkBarrierError('A verified, unchanged macOS network policy is required')
    return [str(SANDBOX), '-f', str(profile), *command]


class _LoopbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'routecontract-local-network-control')

    def log_message(self, *args):
        pass


def _restricted_probe(port: int, public_ip: str, docker_socket: str) -> dict:
    local = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        local.request('GET', '/')
        response = local.getresponse()
        if response.status != 200 or response.read() != b'routecontract-local-network-control':
            raise NetworkBarrierError('Restricted loopback control did not succeed')
    finally:
        local.close()
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(docker_socket)
        connection.sendall(b'GET /_ping HTTP/1.0\r\nHost: localhost\r\n\r\n')
        if b'200 OK' not in connection.recv(4096):
            raise NetworkBarrierError('Restricted local Docker control did not succeed')
    try:
        with socket.create_connection((public_ip, 443), timeout=5):
            pass
    except PermissionError as error:
        if error.errno != 1:
            raise
        return {'externalOutbound': 'OS_DENIED', 'deniedErrno': error.errno,
                'loopbackHttp': 'ALLOWED', 'localDockerUnixSocket': 'ALLOWED'}
    raise NetworkBarrierError('OS did not reject the external connection with EPERM')


def prepare_barrier(destination: Path, java_homes: dict[int, Path] | None = None) -> dict:
    if sys.platform != 'darwin' or not SANDBOX.is_file():
        raise NetworkBarrierError('This implementation proves macOS isolation only')
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise NetworkBarrierError('Network proof directory must start absent')
    destination.mkdir(parents=True, mode=0o700)
    docker_socket = local_docker_socket()
    profile = destination / 'network-policy.sb'
    profile.write_text(policy_text(docker_socket), encoding='utf-8')
    barrier = {'profilePath': str(profile), 'profileSha256': digest(profile.read_bytes())}
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    control = http.client.HTTPSConnection(PUBLIC_HOST, context=context, timeout=15)
    try:
        control.request('HEAD', PUBLIC_PATH)
        response = control.getresponse()
        if response.status != 200:
            raise NetworkBarrierError('Unrestricted public endpoint control must return 200')
    finally:
        control.close()
    public_ip = socket.getaddrinfo(PUBLIC_HOST, 443, family=socket.AF_INET,
                                  type=socket.SOCK_STREAM)[0][4][0]
    # Confirm this exact address is reachable before interpreting its denial.
    with socket.create_connection((public_ip, 443), timeout=10):
        pass
    server = HTTPServer(('127.0.0.1', 0), _LoopbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        command = [sys.executable, str(Path(__file__).resolve()), '--restricted-probe',
                   str(server.server_port), public_ip, str(docker_socket)]
        result = subprocess.run(sandboxed(command, barrier), capture_output=True,
                                text=True, timeout=20, check=False)
        (destination / 'probe-stdout.txt').write_text(result.stdout)
        (destination / 'probe-stderr.txt').write_text(result.stderr)
        if result.returncode != 0:
            raise NetworkBarrierError('Restricted network probe failed; inspect retained output')
        proof = json.loads(result.stdout)
        expected = {'externalOutbound': 'OS_DENIED', 'deniedErrno': 1,
                    'loopbackHttp': 'ALLOWED', 'localDockerUnixSocket': 'ALLOWED'}
        if proof != expected:
            raise NetworkBarrierError('Restricted network probe evidence is incomplete')
        barrier.update(proof)
        java_proofs = {}
        for feature, java_home in (java_homes or {}).items():
            java_home = java_home.resolve(strict=True)
            java_directory = destination / ('java-' + str(feature))
            java_directory.mkdir()
            source = java_directory / 'A24NetworkControl.java'
            source.write_text(JAVA_CONTROL, encoding='utf-8')
            environment = controlled_environment(dict(os.environ))
            commands = [([str(java_home/'bin/javac'), '--release', str(feature), '-Xlint:all',
                          '-Werror', '-d', str(java_directory), str(source)], 'compile'),
                        (sandboxed([str(java_home/'bin/java'), '-cp', str(java_directory),
                                    'A24NetworkControl', str(server.server_port), public_ip], barrier), 'probe')]
            for command, step in commands:
                completed = subprocess.run(command, env=environment, capture_output=True,
                                           text=True, timeout=30)
                (java_directory/(step+'-stdout.txt')).write_text(completed.stdout)
                (java_directory/(step+'-stderr.txt')).write_text(completed.stderr)
                if completed.returncode != 0:
                    raise NetworkBarrierError(f'Java {feature} {step} control failed; inspect retained output')
            marker = (f'A24_JAVA_NETWORK_VERIFIED feature={feature} '
                      'loopback=ALLOWED external=OS_DENIED ipv4=true')
            if completed.stdout.strip() != marker:
                raise NetworkBarrierError('Java network proof does not match the requested runtime')
            java_proofs[str(java_home)] = {'feature': feature, 'javaToolOptions': JAVA_IPV4_OPTION,
                                          'result': marker, 'sourceSha256': digest(source.read_bytes())}
        barrier['javaRuntimes'] = java_proofs
        barrier.update(platform=platform.platform(), publicControlHost=PUBLIC_HOST,
                       publicControlPath=PUBLIC_PATH, publicControlHttpStatus=200,
                       directAddressControl='CONNECTED_BEFORE_OS_DENIAL',
                       helperSha256=digest(Path(__file__).read_bytes()))
        (destination / 'network-proof.json').write_text(json.dumps(barrier, indent=2) + '\n')
        return barrier
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    if len(sys.argv) != 5 or sys.argv[1] != '--restricted-probe':
        raise SystemExit('Import prepare_barrier/sandboxed from a consumer harness')
    print(json.dumps(_restricted_probe(int(sys.argv[2]), sys.argv[3], sys.argv[4])))
