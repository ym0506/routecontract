"""Pinned public pre-0.2 inputs shared by resolver and future classpath fixtures.

The registry records an audit, not live publication discovery. Downloaded bytes
are always checked; tag-only source evidence never becomes an executable input.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import zipfile

GROUP = 'io.github.ym0506.routecontract'
ARTIFACT = 'routecontract-shardingsphere-5.5'
DISTRIBUTED = ('0.1.0', '0.1.2', '0.1.3', '0.1.0-rc2')
SERVICE = 'META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook'
PROVIDER = 'io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook'
ENTRIES = ('io/github/ym0506/routecontract/RouteContract.class',
           'io/github/ym0506/routecontract/internal/CaptureRegistry.class',
           'io/github/ym0506/routecontract/internal/RouteContractSqlExecutionHook.class', SERVICE)


class LegacyInputError(ValueError):
    """A registered artifact or its inspected layout does not match."""


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LegacyInputError('Duplicate JSON key')
        result[key] = value
    return result


def parse_json(payload: bytes) -> dict:
    def invalid_constant(value):
        raise LegacyInputError('Non-finite JSON value')
    try:
        return json.loads(payload, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise LegacyInputError('Invalid UTF-8 JSON input') from error


def load_registry(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < 128 * 1024:
        raise LegacyInputError('Registry must be a bounded regular file')
    registry = parse_json(path.read_bytes())
    if (type(registry.get('formatVersion')) is not int or registry['formatVersion'] != 1 or registry.get('groupId') != GROUP
            or registry.get('artifactId') != ARTIFACT
            or [item.get('version') for item in registry.get('distributed', [])] != list(DISTRIBUTED)):
        raise LegacyInputError('Registry does not contain the reviewed distributed coordinate set')
    if {item.get('version') for item in registry.get('tagOnly', [])} != {'0.1.0-rc1', '0.1.1'}:
        raise LegacyInputError('Tag-only evidence must stay separate from distributed inputs')
    for item in registry['distributed']:
        version = item['version']
        expected_extensions = ['jar', 'pom', 'module'] if version == '0.1.3' else ['jar', 'pom']
        if ([p.get('extension') for p in item.get('payloads', [])] != expected_extensions
                or item.get('tag') != f'v{version}'
                or re.fullmatch('[0-9a-f]{40}', item.get('sourceRevision', '')) is None):
            raise LegacyInputError('Invalid registered legacy identity')
        for payload in item['payloads']:
            expected_name = f'{ARTIFACT}-{version}.{payload["extension"]}'
            if (payload.get('name') != expected_name
                    or type(payload.get('byteCount')) is not int or not 0 < payload['byteCount'] < 2_000_000
                    or re.fullmatch('[0-9a-f]{64}', payload.get('sha256', '')) is None):
                raise LegacyInputError('Invalid registered payload pin')
            parsed = urlparse(payload.get('url', ''))
            expected_prefix = (f'https://repo.maven.apache.org/maven2/{GROUP.replace(".", "/")}/{ARTIFACT}/{version}/'
                               if version == '0.1.3' else f'https://github.com/ym0506/routecontract/releases/download/v{version}/')
            if (not payload['url'].startswith(expected_prefix) or parsed.query or parsed.fragment
                    or parsed.username or parsed.password):
                raise LegacyInputError('Payload URL is outside the reviewed public release')
        layout = item.get('layout', {})
        if (set(layout.get('entries', {})) != set(ENTRIES) or layout.get('hookProvider') != PROVIDER
                or any(re.fullmatch('[0-9a-f]{64}', value) is None for value in layout['entries'].values())):
            raise LegacyInputError('Missing audited all-in-one class/service layout')
    return registry


def verify_payload(pin: dict, payload: bytes) -> None:
    if len(payload) != pin['byteCount'] or digest(payload) != pin['sha256']:
        raise LegacyInputError(f'Published payload differs from its pin: {pin["name"]}')


def verify_layout(item: dict, payloads: dict[str, bytes]) -> None:
    """Inspect exact public inputs without extracting or executing their code."""
    try:
        with zipfile.ZipFile(io.BytesIO(payloads['jar'])) as archive:
            names = archive.namelist()
            for name, expected in item['layout']['entries'].items():
                if names.count(name) != 1 or digest(archive.read(name)) != expected:
                    raise LegacyInputError(f'Legacy JAR entry differs from reviewed layout: {name}')
            providers = [line.split('#', 1)[0].strip() for line in archive.read(SERVICE).decode('utf-8').splitlines()]
            if [provider for provider in providers if provider] != [item['layout']['hookProvider']]:
                raise LegacyInputError('Legacy hook service provider differs')
        pom = ET.fromstring(payloads['pom'])
        ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
        expected = {'groupId': GROUP, 'artifactId': ARTIFACT, 'version': item['version']}
        if any(pom.findtext(f'm:{field}', namespaces=ns) != value for field, value in expected.items()):
            raise LegacyInputError('Legacy POM coordinate differs')
        if 'module' in payloads:
            metadata = parse_json(payloads['module'])
            if metadata.get('component') != {'group': GROUP, 'module': ARTIFACT, 'version': item['version'],
                                              'attributes': {'org.gradle.status': 'release'}}:
                raise LegacyInputError('Legacy Gradle metadata coordinate differs')
            main_name = f'{ARTIFACT}-{item["version"]}.jar'
            for variant_name in ('apiElements', 'runtimeElements'):
                variants = [v for v in metadata.get('variants', []) if v.get('name') == variant_name]
                if len(variants) != 1 or len(variants[0].get('files', [])) != 1:
                    raise LegacyInputError('Missing legacy main-JAR variant')
                entry = variants[0]['files'][0]
                if (entry.get('name') != main_name or entry.get('url') != main_name
                        or entry.get('sha256') != digest(payloads['jar'])
                        or entry.get('size') != len(payloads['jar'])):
                    raise LegacyInputError('Legacy Gradle metadata does not bind the exact main JAR')
    except (zipfile.BadZipFile, KeyError, UnicodeError, ET.ParseError) as error:
        raise LegacyInputError('Cannot inspect the legacy public payload layout') from error


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != 'https' or parsed.hostname not in {
                'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
                'repo.maven.apache.org'} or parsed.username or parsed.password:
            raise LegacyInputError('Unexpected public artifact redirect')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def obtain_payload(pin: dict, local_path: Path | None = None) -> bytes:
    if local_path is not None:
        if local_path.is_symlink() or not local_path.is_file():
            raise LegacyInputError('Pinned cached input must be a regular file')
        payload = local_path.read_bytes()
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirects())
        request = urllib.request.Request(pin['url'], headers={'User-Agent': 'RouteContract-legacy-input-verifier/1'})
        with opener.open(request, timeout=90) as response:
            payload = response.read(pin['byteCount'] + 1)
    verify_payload(pin, payload)
    return payload
