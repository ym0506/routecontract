#!/usr/bin/env python3
"""Compare anonymous Central downloads with a locally verified signed bundle.

This performs no publication, credential handling or public consumer execution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time
from typing import NamedTuple
import urllib.error
import urllib.request
import zipfile


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


artifacts = _load('central_readback_artifacts', 'public_split_artifacts.py')
bundle_tool = _load('central_readback_bundle', 'prepare-central-upload-bundle.py')
REQUEST_TIMEOUT_SECONDS = 20
TOTAL_TIMEOUT_SECONDS = 600
CHUNK_BYTES = 64 * 1024


class ReadbackError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class VerifiedSnapshot(NamedTuple):
    version: str
    bundle_sha256: str
    receipt_sha256: str
    manifest_sha256: str
    fingerprint: str
    bundle_bytes: bytes
    entries: tuple[dict, ...]


def verified_snapshot(*, repository: Path, bundle: Path, receipt: Path,
                      reviewed_payload_manifest: Path, public_gpg_home: Path,
                      expected_primary_fingerprint: str) -> VerifiedSnapshot:
    result = bundle_tool.verify_bundle(
        repository=repository, bundle_path=bundle, receipt_path=receipt,
        reviewed_manifest_path=reviewed_payload_manifest,
        public_gpg_home=public_gpg_home,
        expected_primary_fingerprint=expected_primary_fingerprint)
    # Bind our immutable snapshots to the bytes the local verifier actually checked.
    archive_bytes = bundle_tool._read_stable_regular(bundle, 'verified bundle snapshot', bundle_tool.MAX_BUNDLE_BYTES)
    receipt_bytes = bundle_tool._read_stable_regular(receipt, 'verified receipt snapshot', bundle_tool.MAX_RECEIPT_BYTES)
    if hashlib.sha256(archive_bytes).hexdigest() != result.bundle_sha256 or hashlib.sha256(receipt_bytes).hexdigest() != result.receipt_sha256:
        raise ReadbackError('LOCAL_INPUT_CHANGED')
    value = json.loads(receipt_bytes)
    return VerifiedSnapshot(artifacts.stable_version(result.version), result.bundle_sha256,
                            result.receipt_sha256, value['reviewedPayloadManifest']['sha256'],
                            expected_primary_fingerprint, archive_bytes,
                            tuple(value['bundle']['entries']))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        if response is not None:
            response.close()
        raise ReadbackError('REDIRECT_REJECTED')


def central_opener():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ReadbackError('DEADLINE_EXCEEDED')
    return min(REQUEST_TIMEOUT_SECONDS, remaining)


def _verify_response(opener, path: str, expected: bytes, deadline: float) -> None:
    url = artifacts.CENTRAL_ROOT + path
    request = urllib.request.Request(url, headers={
        'Accept-Encoding': 'identity', 'User-Agent': 'RouteContract-public-readback/1'}, method='GET')
    try:
        with opener.open(request, timeout=_remaining(deadline)) as response:
            if response.geturl() != url:
                raise ReadbackError('UNEXPECTED_ORIGIN')
            if response.status != 200:
                raise ReadbackError('HTTP_STATUS')
            if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise ReadbackError('CONTENT_ENCODING')
            length = response.headers.get('Content-Length')
            if length is not None:
                if re.fullmatch(r'[0-9]{1,12}', length) is None:
                    raise ReadbackError('CONTENT_LENGTH')
                if int(length) != len(expected):
                    raise ReadbackError('SIZE_MISMATCH')
            offset = 0
            while True:
                _remaining(deadline)
                # HTTPResponse.read() can fill across many receives while a peer
                # trickles bytes. read1() returns after one underlying read so
                # the monotonic budget is checked between receives.
                chunk = response.read1(min(CHUNK_BYTES, len(expected) - offset + 1))
                if not chunk:
                    break
                if offset + len(chunk) > len(expected):
                    raise ReadbackError('SIZE_MISMATCH')
                if chunk != expected[offset:offset + len(chunk)]:
                    raise ReadbackError('BYTE_MISMATCH')
                offset += len(chunk)
            if offset != len(expected):
                raise ReadbackError('SIZE_MISMATCH')
    except urllib.error.HTTPError as error:
        error.close()
        raise ReadbackError(f'HTTP_{error.code}') from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
        raise ReadbackError('TRANSPORT_ERROR') from None


def _write_json(directory: Path, name: str, value: dict) -> None:
    temporary = directory / f'.{name}.pending'
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, directory / name)


def _consumer_receipt(snapshot: VerifiedSnapshot) -> dict:
    by_path = {item['path']: item for item in snapshot.entries}
    records = []
    for module in artifacts.MODULES:
        for extension in artifacts.EXTENSIONS:
            name = f'{module}-{snapshot.version}.{extension}'
            path = (artifacts.GROUP_PATH / module / snapshot.version / name).as_posix()
            record = by_path[path]
            records.append({'module': module, 'name': name, 'relativePath': path, 'sha256': record['sha256']})
    return artifacts.validate_consumer_receipt({
        'formatVersion': 1, 'routeContractVersion': snapshot.version, 'artifacts': records})


def readback(snapshot: VerifiedSnapshot, evidence: Path, *, opener=None) -> int:
    # The CLI supplies only verified_snapshot(); transport injection is for unit tests.
    if not evidence.is_absolute() or evidence.parent.resolve(strict=True) != evidence.parent or evidence.exists() or evidence.is_symlink():
        raise ReadbackError('EVIDENCE_DIRECTORY_MUST_BE_NEW_AND_CANONICAL')
    evidence.mkdir(mode=0o700)
    summary = {
        'formatVersion': 1, 'kind': 'routecontract-public-central-readback',
        'routeContractVersion': snapshot.version, 'repository': artifacts.CENTRAL_ROOT,
        'result': 'RUNNING', 'startedAt': datetime.now(timezone.utc).isoformat(),
        'source': {'bundleSha256': snapshot.bundle_sha256, 'receiptSha256': snapshot.receipt_sha256,
                   'reviewedManifestSha256': snapshot.manifest_sha256, 'primaryFingerprint': snapshot.fingerprint},
        'toolSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'verifiedEntryCount': 0, 'entries': [], 'publicReadbackVerified': False,
        'consumerExecutionVerified': False, 'availabilityClaim': False, 'networkPublication': False,
    }
    _write_json(evidence, 'public-readback.json', summary)
    deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS
    current_path = None
    try:
        transport = opener if opener is not None else central_opener()
        with zipfile.ZipFile(io.BytesIO(snapshot.bundle_bytes)) as archive:
            for record in snapshot.entries:
                current_path = record['path']
                expected = archive.read(current_path)
                if len(expected) != record['size'] or hashlib.sha256(expected).hexdigest() != record['sha256']:
                    raise ReadbackError('LOCAL_INPUT_CHANGED')
                _verify_response(transport, current_path, expected, deadline)
                summary['entries'].append({key: record[key] for key in ('path', 'size', 'sha256')})
                summary['verifiedEntryCount'] = len(summary['entries'])
                _write_json(evidence, 'public-readback.json', summary)
        if summary['verifiedEntryCount'] != 90:
            raise ReadbackError('INCOMPLETE_INVENTORY')
        _write_json(evidence, 'consumer-receipt.json', _consumer_receipt(snapshot))
        summary.update(result='VERIFIED', publicReadbackVerified=True)
    except ReadbackError as error:
        summary.update(result='FAILED', failureCode=error.code, failedPath=current_path)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        summary.update(result='FAILED', failureCode='LOCAL_EVIDENCE_ERROR', failedPath=current_path)
    summary['finishedAt'] = datetime.now(timezone.utc).isoformat()
    _write_json(evidence, 'public-readback.json', summary)
    return 0 if summary['publicReadbackVerified'] else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('repository', 'bundle', 'receipt', 'reviewed-payload-manifest', 'public-gpg-home', 'evidence-directory'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--expected-primary-fingerprint', required=True)
    args = parser.parse_args(argv)
    try:
        snapshot = verified_snapshot(repository=args.repository, bundle=args.bundle, receipt=args.receipt,
                                     reviewed_payload_manifest=args.reviewed_payload_manifest,
                                     public_gpg_home=args.public_gpg_home,
                                     expected_primary_fingerprint=args.expected_primary_fingerprint)
        result = readback(snapshot, args.evidence_directory)
    except (ReadbackError, bundle_tool.BundleError, artifacts.ReceiptError, OSError):
        print('Public Central readback failed before a complete evidence result; inspect local inputs.', file=sys.stderr)
        return 2
    if result:
        print('Public Central readback incomplete; inspect public-readback.json. No availability claim.', file=sys.stderr)
    else:
        print(f'ROUTECONTRACT_PUBLIC_CENTRAL_READBACK_VERIFIED version={snapshot.version} entries=90; public consumers still required')
    return result


if __name__ == '__main__':
    raise SystemExit(main())
