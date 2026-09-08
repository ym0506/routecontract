#!/usr/bin/env python3
"""Run actual A-27 Gradle resolution against pinned legacy and staged split bytes."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from legacy_artifact_inputs import (ARTIFACT, GROUP, LegacyInputError, digest,
                                    load_registry, obtain_payload, verify_layout)
from public_split_artifacts import MODULES, load_consumer_receipt

FIXTURE = ROOT / 'examples/gradle-legacy-artifact-consumer'
REGISTRY = ROOT / 'scripts/legacy-artifact-inputs.json'
NAMESPACE = 'https://schema.gradle.org/dependency-verification'
PRODUCTION_PATHS = ['build.gradle', 'settings.gradle', 'gradle.properties', 'gradle', 'gradlew', 'LICENSE', 'NOTICE'] + [
    f'{module}/{suffix}' for module in MODULES for suffix in ('build.gradle', 'gradle.lockfile', 'src/main')]


class ResolverError(RuntimeError):
    pass


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def source_binding(source: str) -> dict:
    revision = git('rev-parse', '--verify', f'{source}^{{commit}}')
    changed = git('diff', '--name-only', revision, '--', *PRODUCTION_PATHS)
    untracked = git('ls-files', '--others', '--exclude-standard', '--', *PRODUCTION_PATHS)
    if changed or untracked:
        raise ResolverError('Staged source differs in production/publication inputs: ' + changed + untracked)
    return {'stagedSourceRevision': revision, 'checkoutRevision': git('rev-parse', 'HEAD'),
            'comparedPaths': PRODUCTION_PATHS, 'productionPublicationInputsIdentical': True,
            'stagedInputTree': git('ls-tree', '-r', revision, '--', *PRODUCTION_PATHS).splitlines(),
            'boundary': 'Reviewed local staged receipt; no claim of byte identity to CI-generated metadata.'}


def snapshot() -> dict:
    files = [REGISTRY, ROOT / 'gradle/verification-metadata.xml', Path(__file__).resolve(),
             ROOT / 'scripts/legacy_artifact_inputs.py', ROOT / 'scripts/public_split_artifacts.py',
             ROOT / 'scripts/verify-gradle-split-artifact-consumer.py', ROOT / 'gradlew',
             ROOT / 'gradle/wrapper/gradle-wrapper.jar', ROOT / 'gradle/wrapper/gradle-wrapper.properties']
    files += sorted(path for path in FIXTURE.rglob('*') if path.is_file())
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in files}


def prepare_repository(repository: Path, receipt: dict, registry: dict, destination: Path,
                       legacy_payload_directory: Path | None) -> list[dict]:
    inventory = []
    for pin in receipt['artifacts']:
        source = repository / pin['relativePath']
        if source.is_symlink() or not source.is_file():
            raise ResolverError('Staged payload must be a regular file: ' + pin['name'])
        payload = source.read_bytes()
        if digest(payload) != pin['sha256']:
            raise ResolverError('Staged payload does not match reviewed receipt: ' + pin['name'])
        target = destination / pin['relativePath']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        inventory.append(dict(pin, version=receipt['routeContractVersion'], byteCount=len(payload), origin='staged'))
    for legacy in registry['distributed']:
        payloads = {}
        for pin in legacy['payloads']:
            local = legacy_payload_directory / legacy['version'] / pin['name'] if legacy_payload_directory else None
            payload = obtain_payload(pin, local)
            relative = f'{GROUP.replace(".", "/")}/{ARTIFACT}/{legacy["version"]}/{pin["name"]}'
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            payloads[pin['extension']] = payload
            inventory.append(dict(pin, module=ARTIFACT, version=legacy['version'], relativePath=relative, origin='public-legacy'))
        verify_layout(legacy, payloads)
    return inventory


def prepare_metadata(destination: Path, inventory: list[dict]) -> None:
    ET.register_namespace('', NAMESPACE)
    ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    tag = lambda name: f'{{{NAMESPACE}}}{name}'
    tree = ET.parse(ROOT / 'gradle/verification-metadata.xml')
    root = tree.getroot()
    if root.findtext(f'{tag("configuration")}/{tag("verify-metadata")}') != 'true':
        raise ResolverError('Third-party metadata verification must be enabled')
    if root.findall(f'.//{tag("trusted-artifacts")}'):
        raise ResolverError('Unconditional artifact trust is not allowed in the legacy resolver fixture')
    components = root.find(tag('components'))
    for component in list(components):
        if component.get('group') == GROUP:
            components.remove(component)
    added = {}
    for pin in inventory:
        key = (pin['module'], pin['version'])
        if key not in added:
            added[key] = ET.SubElement(components, tag('component'), group=GROUP, name=key[0], version=key[1])
        artifact = ET.SubElement(added[key], tag('artifact'), name=pin['name'])
        ET.SubElement(artifact, tag('sha256'), value=pin['sha256'], origin='Reviewed legacy registry or local staged receipt')
    ET.indent(tree, space='   ')
    tree.write(destination, encoding='utf-8', xml_declaration=True)


def seed_distribution_zip(source: Path, seed: Path) -> None:
    """Reuse a reviewed distribution archive, never a dependency cache or .ok marker."""
    expected = 'f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d'
    if source.is_symlink() or not source.is_file() or digest(source.read_bytes()) != expected:
        raise ResolverError('Gradle distribution ZIP does not match the wrapper checksum')
    # Gradle Wrapper's cache key for the checked-in services.gradle.org URL.
    target = seed / 'wrapper/dists/gradle-8.14.4-bin/92wwslzcyst3phie3o264zltu/gradle-8.14.4-bin.zip'
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    if digest(target.read_bytes()) != expected:
        raise ResolverError('Gradle distribution ZIP changed during copying')


def cases(registry: dict, inventory: list[dict], repository: Path, current: str) -> list[dict]:
    jars = {(p['module'], p['version']): {field: p[field] for field in ('module', 'version', 'name', 'sha256', 'byteCount')}
            for p in inventory if p['name'].endswith('.jar')}
    result = []
    def add(case_id, legacy, requests, expected, expected_coordinates=(), ownership=True, runtime=None):
        result.append({'caseId': case_id, 'repository': str(repository), 'legacyVersion': legacy,
                       'currentVersion': current, 'ownershipRule': ownership, 'runtime': runtime,
                       'requests': [{'module': module, 'version': version, 'strict': strict}
                                    for module, version, strict in requests], 'expected': expected,
                       'expectedArtifacts': [jars[coordinate] for coordinate in expected_coordinates]})
    for item in registry['distributed']:
        version = item['version']
        legacy = (ARTIFACT, version, False)
        core = ('routecontract-core', current, False)
        adapter552 = ('routecontract-shardingsphere-5.5.2', current, False)
        adapter553 = (ARTIFACT, current, False)
        add(f'{version}-alone', version, [legacy], 'RESOLVED', [(ARTIFACT, version)])
        for suffix, other in [('core', core), ('552', adapter552)]:
            for order, requests in [('legacy-first', [legacy, other]), ('legacy-last', [other, legacy])]:
                add(f'{version}-{suffix}-{order}', version, requests, 'CAPABILITY_CONFLICT')
        for order, requests in [('legacy-first', [legacy, adapter553]), ('legacy-last', [adapter553, legacy])]:
            add(f'{version}-mediated-{order}', version, requests, 'RESOLVED',
                [(ARTIFACT, current), ('routecontract-core', current)], runtime='5.5.3')
            add(f'{version}-strict-{order}', version, [(m, v, True) for m, v, _ in requests], 'STRICT_VERSION_CONFLICT')
    add('0.1.3-core-without-ownership-control', '0.1.3',
        [(ARTIFACT, '0.1.3', False), ('routecontract-core', current, False)], 'RESOLVED',
        [(ARTIFACT, '0.1.3'), ('routecontract-core', current)], ownership=False)
    return result


def run_case(case: dict, evidence: Path, metadata: Path, seed: Path, java_home: Path, helper) -> dict:
    case_dir = evidence / 'cases' / case['caseId']
    case_dir.mkdir(parents=True)
    fixture = case_dir / 'consumer'
    shutil.copytree(FIXTURE, fixture)
    (fixture / 'gradle').mkdir()
    copied_metadata = fixture / 'gradle/verification-metadata.xml'
    shutil.copyfile(metadata, copied_metadata)
    write_json(fixture / 'case-inputs.json', case)
    gradle_home = case_dir / 'gradle-home'
    gradle_home.mkdir()
    helper.seed_wrapper_distribution(seed, gradle_home)
    if (gradle_home / 'caches').exists():
        raise ResolverError('Case did not start with an absent dependency cache')
    command = [str(ROOT / 'gradlew'), '--no-daemon', '--no-build-cache', '--no-configuration-cache',
               '--dependency-verification=strict', '--console=plain', '--max-workers=2',
               '--project-dir', str(fixture), '--project-cache-dir', str(case_dir / 'project-cache'),
               'check']
    write_json(case_dir / 'command.json', {'argv': command, 'cwd': str(fixture),
               'JAVA_HOME': str(java_home), 'GRADLE_USER_HOME': str(gradle_home),
               'dependencyCacheInitiallyAbsent': True, 'wrapperDistributionOnlySeeded': True})
    with (case_dir / 'gradle.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=fixture, env=helper.clean_environment(java_home, gradle_home),
                                stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)
    report_path = fixture / 'build/legacy-resolver-evidence.json'
    if result.returncode != 0 or not report_path.is_file():
        raise ResolverError(f'Unexpected resolver result in {case["caseId"]}; inspect {case_dir / "gradle.log"}')
    report = json.loads(report_path.read_text())
    marker = f'ROUTECONTRACT_LEGACY_RESOLVER_VERIFIED case={case["caseId"]} result={case["expected"]}'
    if (report['result'] != case['expected'] or report['requests'] != case['requests']
            or (case_dir / 'gradle.log').read_text().count(marker) != 1
            or digest(copied_metadata.read_bytes()) != digest(metadata.read_bytes())):
        raise ResolverError('Resolver evidence mismatch: ' + case['caseId'])
    shutil.copyfile(report_path, case_dir / 'result.json')
    print(marker, flush=True)
    return {'caseId': case['caseId'], 'result': report['result'],
            'resultSha256': digest(report_path.read_bytes()), 'logSha256': digest((case_dir / 'gradle.log').read_bytes())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--staged-receipt', required=True, type=Path)
    parser.add_argument('--staged-source-revision', required=True)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--legacy-payload-directory', type=Path)
    parser.add_argument('--gradle-distribution-zip', type=Path,
                        help='Optional exact checksum-pinned Gradle 8.14.4 archive; no dependency cache reuse')
    parser.add_argument('--case', action='append', dest='case_ids', help='Partial diagnostic run; never marks full coverage')
    parser.add_argument('--workers', type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    evidence = args.evidence_directory.expanduser().resolve()
    if evidence == ROOT or ROOT in evidence.parents or evidence.exists():
        raise ResolverError('Evidence directory must be absent and outside the checkout')
    evidence.mkdir(parents=True, mode=0o700)
    try:
        initial_snapshot = snapshot()
        registry = load_registry(REGISTRY)
        receipt_bytes = args.staged_receipt.read_bytes()
        receipt = load_consumer_receipt(args.staged_receipt)
        if receipt['routeContractVersion'] != '0.2.0':
            raise ResolverError('This candidate fixture is scoped to reviewed 0.2.0 bytes')
        binding = source_binding(args.staged_source_revision)
        write_json(evidence / 'source-binding.json', binding)
        write_json(evidence / 'fixture-inputs.json', initial_snapshot)
        shutil.copyfile(REGISTRY, evidence / 'legacy-artifact-inputs.json')
        (evidence / 'staged-receipt.json').write_bytes(receipt_bytes)
        repository = evidence / 'repository'
        inventory = prepare_repository(args.repository.resolve(), receipt, registry, repository,
                                       args.legacy_payload_directory.resolve() if args.legacy_payload_directory else None)
        write_json(evidence / 'verified-input-inventory.json', inventory)
        metadata = evidence / 'verification-metadata.xml'
        prepare_metadata(metadata, inventory)
        all_cases = cases(registry, inventory, repository, receipt['routeContractVersion'])
        selected = all_cases
        if args.case_ids:
            if set(args.case_ids) - {case['caseId'] for case in all_cases}:
                raise ResolverError('Unknown requested diagnostic case')
            selected = [case for case in all_cases if case['caseId'] in args.case_ids]
        write_json(evidence / 'case-plan.json', {'allCaseCount': len(all_cases), 'selected': selected})
        spec = importlib.util.spec_from_file_location('split_consumer_helpers', ROOT / 'scripts/verify-gradle-split-artifact-consumer.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        java_home = args.java_home.resolve()
        helper.verify_toolchain(ROOT, java_home)
        seed = evidence / 'wrapper-seed'
        seed.mkdir()
        if args.gradle_distribution_zip:
            seed_distribution_zip(args.gradle_distribution_zip.resolve(), seed)
        helper.prepare_wrapper_seed(ROOT, ROOT / 'gradlew', java_home, seed)
        toolchain = subprocess.check_output([str(ROOT / 'gradlew'), '--no-daemon', '--version'], cwd=ROOT,
                    env=helper.clean_environment(java_home, seed), text=True, stderr=subprocess.STDOUT, timeout=60)
        (evidence / 'toolchain.txt').write_text(toolchain)
        results = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_case, case, evidence, metadata, seed, java_home, helper) for case in selected]
            try:
                for future in as_completed(futures):
                    results.append(future.result())
                    write_json(evidence / 'progress.json', sorted(results, key=lambda case: case['caseId']))
            except Exception:
                for future in futures:
                    future.cancel()
                raise
        if snapshot() != initial_snapshot or args.staged_receipt.read_bytes() != receipt_bytes:
            raise ResolverError('Reviewed fixture or receipt changed during the run')
        if source_binding(args.staged_source_revision) != binding:
            raise ResolverError('Production/publication source binding changed during the run')
        for pin in inventory:
            if digest((repository / pin['relativePath']).read_bytes()) != pin['sha256']:
                raise ResolverError('Isolated repository input changed during the run')
        summary = {'formatVersion': 1, 'status': 'VERIFIED' if not args.case_ids else 'PARTIAL_VERIFIED',
                   'fullGradleA27Matrix': not bool(args.case_ids), 'caseCount': len(results), 'requiredCaseCount': len(all_cases),
                   'registrySha256': initial_snapshot['scripts/legacy-artifact-inputs.json'],
                   'stagedReceiptSha256': digest(receipt_bytes), 'verificationMetadataSha256': digest(metadata.read_bytes()),
                   'sourceBinding': binding, 'results': sorted(results, key=lambda case: case['caseId']),
                   'boundary': 'Real Gradle 8.14.4 / Java 17 resolution and pinned first-party JAR materialization. '
                               'No Maven, third-party runtime JAR execution, SQL, A-28, or public 0.2 publication claim.'}
        write_json(evidence / 'summary.json', summary)
        print(f'ROUTECONTRACT_GRADLE_LEGACY_MATRIX_{summary["status"]} cases={len(results)} evidence={evidence}', flush=True)
    except Exception as error:
        write_json(evidence / 'failure.json', {'status': 'FAILED', 'error': str(error), 'fullGradleA27Matrix': False})
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'ROUTECONTRACT_GRADLE_LEGACY_MATRIX_FAILED: {error}', file=sys.stderr)
        sys.exit(1)
