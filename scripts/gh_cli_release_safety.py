#!/usr/bin/env python3
"""Fail closed before GitHub release-attestation verification commands.

GHSA-8xvp-7hj6-mcj9 affects GitHub CLI through 2.92.0. This module only
executes ``gh version``; it never runs an attestation or release verification.
It is importable so every release path can share the same parser and probe.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys


MINIMUM_SAFE_VERSION = (2, 93, 0)
ADVISORY_URL = (
    "https://github.com/cli/cli/security/advisories/GHSA-8xvp-7hj6-mcj9"
)
VERSION_LINE = re.compile(
    r"gh version (0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?: \([^()\r\n]+\))?"
)
RELEASE_URL_PREFIX = "https://github.com/cli/cli/releases/tag/v"


class GithubCliSafetyError(RuntimeError):
    """The installed GitHub CLI cannot safely run verification commands."""


def parse_version(output: str) -> tuple[int, int, int]:
    """Parse one unambiguous stable version from canonical ``gh version`` output."""
    lines = output.splitlines()
    if len(lines) not in (1, 2):
        raise GithubCliSafetyError(
            "GitHub CLI version output is not an unambiguous stable version"
        )
    match = VERSION_LINE.fullmatch(lines[0])
    if match is None:
        raise GithubCliSafetyError(
            "GitHub CLI version output is not an unambiguous stable version"
        )
    version = tuple(int(part) for part in match.groups())
    rendered = ".".join(str(part) for part in version)
    if len(lines) == 2 and lines[1] != f"{RELEASE_URL_PREFIX}{rendered}":
        raise GithubCliSafetyError(
            "GitHub CLI version output is not an unambiguous stable version"
        )
    return version  # type: ignore[return-value]


def require_safe_github_cli() -> tuple[str, tuple[int, int, int]]:
    """Return the exact executable and version only when the CLI is safe."""
    executable = shutil.which("gh")
    if executable is None:
        raise GithubCliSafetyError("GitHub CLI is not installed or is not on PATH")
    try:
        result = subprocess.run(
            [executable, "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise GithubCliSafetyError("could not execute GitHub CLI version check") from None
    if result.returncode != 0:
        raise GithubCliSafetyError(
            f"GitHub CLI version check failed with exit {result.returncode}"
        )
    version = parse_version(result.stdout)
    if version < MINIMUM_SAFE_VERSION:
        rendered = ".".join(str(part) for part in version)
        raise GithubCliSafetyError(
            "GitHub CLI 2.93.0 or newer is required before attestation "
            "verification (GHSA-8xvp-7hj6-mcj9); found " + rendered
        )
    return executable, version


def main() -> int:
    try:
        _, version = require_safe_github_cli()
    except GithubCliSafetyError as error:
        print(f"UNSAFE_GH_VERSION: {error}", file=sys.stderr)
        print(f"See {ADVISORY_URL}", file=sys.stderr)
        return 2
    rendered = ".".join(str(part) for part in version)
    print(f"SAFE_GH_RELEASE_VERIFICATION_VERSION gh={rendered} minimum=2.93.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
