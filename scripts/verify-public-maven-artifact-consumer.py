#!/usr/bin/env python3
"""Verify published split artifacts using only anonymous Maven Central and reviewed hashes."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def sibling(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


maven_support = sibling('public_maven_support', 'verify-staged-maven-artifact-consumer.py')
public_artifacts = sibling('public_split_artifacts', 'public_split_artifacts.py')
VerificationError = maven_support.VerificationError
CENTRAL_URL = 'https://repo.maven.apache.org/maven2'
MIRROR_ID = 'routecontract-public-central'
TRANSPORT_ARGUMENTS = ('-Dmaven.resolver.transport=native',
                       '-Daether.connector.http.followRedirects=false')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--maven', default=os.environ.get('MAVEN_BIN', 'mvn'))
    arguments = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    receipt_path = arguments.receipt.expanduser().absolute()
    receipt = public_artifacts.load_consumer_receipt(receipt_path)
    version = receipt['routeContractVersion']
    evidence = arguments.evidence_directory.expanduser().absolute()
    java_home = arguments.java_home.expanduser().resolve(strict=True)
    maven = shutil.which(arguments.maven)
    if not maven or not (java_home / 'bin/java').is_file():
        raise VerificationError('Supply Maven 3.9.14 and a Java 17 home')
    if evidence.exists() or evidence.is_symlink():
        raise VerificationError('Supply a new evidence directory')
    if evidence.resolve().is_relative_to(root) or receipt_path.resolve().is_relative_to(evidence.resolve()):
        raise VerificationError('Evidence and negative consumer POMs must be outside the checkout and separate from the receipt')
    evidence.mkdir(parents=True)
    maven_support.write_json(evidence / 'reviewed-receipt.json', receipt)
    environment = maven_support.clean_environment(java_home)
    summary = {'formatVersion': 1, 'routeContractVersion': version,
               'repository': CENTRAL_URL, 'publicRepositoryConsumptionVerified': False,
               'complete': False, 'lanes': [],
               'boundary': 'ShardingSphere SQLExecutionHook-reported physical JDBC execution attempts; not a complete route plan or business success'}
    try:
        with tempfile.TemporaryDirectory(prefix='routecontract-public-maven-') as temporary_name:
            temporary = Path(temporary_name).resolve()
            if temporary.is_relative_to(root):
                raise VerificationError('Temporary consumer and Maven cache must be outside the checkout')
            toolchain = maven_support.run([maven, '--version'], temporary, environment, evidence / 'toolchain.log')
            if (f'Apache Maven {maven_support.MAVEN_VERSION} ' not in toolchain
                    or not re.search(r'Java version: 17[.,]', toolchain)):
                raise VerificationError('The consumer fixture requires exact Maven 3.9.14 and Java 17')
            settings = evidence / 'central-settings.xml'
            maven_support.write_settings(settings, CENTRAL_URL, MIRROR_ID)
            for runtime, adapter in maven_support.LANES.items():
                summary['lanes'].append(maven_support.verify_lane(
                    root, temporary, evidence, None, settings, maven, environment, runtime, adapter,
                    receipt, version=version, mirror_id=MIRROR_ID,
                    maven_arguments=TRANSPORT_ARGUMENTS))
        if public_artifacts.load_consumer_receipt(receipt_path) != receipt:
            raise VerificationError('Reviewed receipt changed during public consumer verification')
        summary['complete'] = True
        summary['publicRepositoryConsumptionVerified'] = True
    finally:
        maven_support.write_json(evidence / 'summary.json', summary)
    print(f'ROUTECONTRACT_PUBLIC_MAVEN_CONSUMER_VERIFIED version={version} lanes=2 mysqlTests=6 negativeGraphCases=8 publicConsumption=true')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, VerificationError, public_artifacts.ReceiptError, subprocess.SubprocessError) as error:
        print(f'PUBLIC_MAVEN_CONSUMER_FAILED: {error}', file=sys.stderr)
        raise SystemExit(1)
