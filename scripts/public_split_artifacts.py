"""Closed reviewed-byte receipt shared by the public 0.2 consumer checks.

Loading this document verifies its shape, not publication or publisher identity.
The expected hashes must come from the maintainer's reviewed release evidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

CENTRAL_ROOT = 'https://repo.maven.apache.org/maven2/'
GROUP = 'io.github.ym0506.routecontract'
GROUP_PATH = PurePosixPath('io/github/ym0506/routecontract')
MODULES = ('routecontract-core', 'routecontract-shardingsphere-5.5',
           'routecontract-shardingsphere-5.5.2')
EXTENSIONS = ('jar', 'pom', 'module')
MAX_RECEIPT_BYTES = 32 * 1024


class ReceiptError(ValueError):
    """The reviewed consumer receipt is missing or inconsistent."""


def stable_version(value: object) -> str:
    if not isinstance(value, str) or len(value) > 32 or re.fullmatch(r'0\.2\.(0|[1-9][0-9]*)', value) is None:
        raise ReceiptError('Expected a stable 0.2.x release version')
    return value


def validate_consumer_receipt(document: object) -> dict:
    if not isinstance(document, dict) or set(document) != {'formatVersion', 'routeContractVersion', 'artifacts'}:
        raise ReceiptError('Consumer receipt header does not match format 1')
    if type(document['formatVersion']) is not int or document['formatVersion'] != 1:
        raise ReceiptError('Consumer receipt format must be integer 1')
    version = stable_version(document['routeContractVersion'])
    artifacts = document['artifacts']
    if not isinstance(artifacts, list) or len(artifacts) != 9:
        raise ReceiptError('Consumer receipt must contain exactly nine payloads')
    expected = {}
    for module in MODULES:
        for extension in EXTENSIONS:
            name = f'{module}-{version}.{extension}'
            relative = (GROUP_PATH / module / version / name).as_posix()
            expected[relative] = (module, name)
    found = {}
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {'module', 'name', 'relativePath', 'sha256'}:
            raise ReceiptError('Consumer receipt payload has unexpected fields')
        if any(not isinstance(item[field], str) for field in item):
            raise ReceiptError('Consumer receipt payload fields must be strings')
        relative = item['relativePath']
        if relative not in expected or expected[relative] != (item['module'], item['name']):
            raise ReceiptError('Consumer receipt payload is outside the exact coordinate set')
        if relative in found:
            raise ReceiptError('Consumer receipt contains a duplicate payload')
        if re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is None:
            raise ReceiptError('Consumer receipt requires lowercase SHA-256 digests')
        found[relative] = dict(item)
    return {'formatVersion': 1, 'routeContractVersion': version,
            'artifacts': [found[relative] for relative in expected]}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError('Consumer receipt contains duplicate JSON keys')
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReceiptError('Consumer receipt contains a non-finite JSON value')


def load_consumer_receipt(path: Path) -> dict:
    """Read one bounded regular file, rejecting symlink leaves and ambiguous JSON."""
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_RECEIPT_BYTES:
            raise ReceiptError('Consumer receipt must be a bounded nonempty regular file')
        with os.fdopen(descriptor, 'rb') as source:
            descriptor = None
            payload = source.read(MAX_RECEIPT_BYTES + 1)
            after = os.fstat(source.fileno())
        if len(payload) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ReceiptError('Consumer receipt changed while being read')
        document = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
        return validate_consumer_receipt(document)
    except ReceiptError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ReceiptError('Consumer receipt cannot be read as strict UTF-8 JSON') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
