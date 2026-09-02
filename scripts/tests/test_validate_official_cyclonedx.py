#!/usr/bin/env python3
"""Adversarial tests for the checksum-pinned official CycloneDX validator."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "validate-official-cyclonedx.py"
LOCK_PATH = REPOSITORY_ROOT / "security" / "cyclonedx-cli.lock.json"
SPEC = importlib.util.spec_from_file_location("validate_official_cyclonedx", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import precondition
    raise RuntimeError(f"could not import {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

GOLDEN_ASSETS = {
    "darwin-arm64": {
        "asset": "cyclonedx-osx-arm64",
        "url": (
            "https://github.com/CycloneDX/cyclonedx-cli/releases/download/"
            "v0.33.1/cyclonedx-osx-arm64"
        ),
        "size": 86373536,
        "sha256": "750c148780154833f6401f9067d08c5a4c31567b6ee3c26c062c3a95c62d741c",
    },
    "darwin-x86_64": {
        "asset": "cyclonedx-osx-x64",
        "url": (
            "https://github.com/CycloneDX/cyclonedx-cli/releases/download/"
            "v0.33.1/cyclonedx-osx-x64"
        ),
        "size": 79598282,
        "sha256": "0ea92306fc7d7c30ed112a7463781a200585a3bf1cdaf77229181c5aabd1d4b6",
    },
    "linux-x86_64": {
        "asset": "cyclonedx-linux-x64",
        "url": (
            "https://github.com/CycloneDX/cyclonedx-cli/releases/download/"
            "v0.33.1/cyclonedx-linux-x64"
        ),
        "size": 80337458,
        "sha256": "bfc8b2538da86fe239bc53658bbb63c1c8c510a293c1e6891aa5bea5d3c58746",
    },
}
GOLDEN_PAIRS = (
    (
        "aggregate",
        "build/reports/verified-sbom/aggregate/bom.json",
        "build/reports/verified-sbom/aggregate/bom.xml",
    ),
    (
        "core",
        "build/reports/verified-sbom/routecontract-core/bom.json",
        "build/reports/verified-sbom/routecontract-core/bom.xml",
    ),
    (
        "adapter553",
        "build/reports/verified-sbom/routecontract-shardingsphere-5.5/bom.json",
        "build/reports/verified-sbom/routecontract-shardingsphere-5.5/bom.xml",
    ),
    (
        "adapter552",
        "build/reports/verified-sbom/routecontract-shardingsphere-5.5.2/bom.json",
        "build/reports/verified-sbom/routecontract-shardingsphere-5.5.2/bom.xml",
    ),
    (
        "mysql553",
        "build/reports/verified-sbom/mysql-example/bom.json",
        "build/reports/verified-sbom/mysql-example/bom.xml",
    ),
    (
        "mysql552",
        "build/reports/verified-sbom/mysql-5.5.2-example/bom.json",
        "build/reports/verified-sbom/mysql-5.5.2-example/bom.xml",
    ),
)


class FakeResponse(io.BytesIO):
    def __init__(
        self,
        content: bytes,
        *,
        url: str,
        content_length: int | None = None,
        content_encoding: str | None = None,
        status: int = 200,
    ) -> None:
        super().__init__(content)
        self._url = url
        self.status = status
        self.headers: dict[str, str] = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        if content_encoding is not None:
            self.headers["Content-Encoding"] = content_encoding

    def geturl(self) -> str:
        return self._url


class OfficialCycloneDxValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name).resolve()
        self.repository = temporary_root / "repository"
        self.repository.mkdir()
        (self.repository / "security").mkdir()
        self.asset_bytes = b"synthetic pinned CycloneDX executable\n"
        self.asset_sha = hashlib.sha256(self.asset_bytes).hexdigest()
        self.lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        selected = self.lock["tool"]["platforms"]["linux-x86_64"]
        selected["sha256"] = self.asset_sha
        selected["size"] = len(self.asset_bytes)
        self.write_lock()
        for pair_name, json_relative, xml_relative in MODULE.SBOM_PAIRS:
            for format_name, relative in (("json", json_relative), ("xml", xml_relative)):
                path = self.repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    f"fixture:{pair_name}:{format_name}\n", encoding="utf-8"
                )
        self.commands: list[list[str]] = []

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @property
    def asset(self) -> dict[str, object]:
        return self.lock["tool"]["platforms"]["linux-x86_64"]

    @property
    def cache_binary(self) -> Path:
        return (
            self.repository
            / MODULE.CACHE_RELATIVE_PATH
            / str(self.asset["sha256"])
            / "cyclonedx"
        )

    def write_lock(self) -> None:
        (self.repository / MODULE.LOCK_RELATIVE_PATH).write_text(
            json.dumps(self.lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def install_cache(self, content: bytes | None = None) -> Path:
        self.cache_binary.parent.mkdir(parents=True, exist_ok=True)
        self.cache_binary.write_bytes(self.asset_bytes if content is None else content)
        self.cache_binary.chmod(0o500)
        return self.cache_binary

    def successful_process(
        self, arguments: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(arguments))
        if arguments[1:] == ["--version"]:
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=MODULE.EXPECTED_VERSION_OUTPUT,
                stderr="",
            )
        return subprocess.CompletedProcess(arguments, 0, stdout="Valid BOM\n", stderr="")

    def run_validator(
        self,
        *,
        offline: bool = False,
        process_side_effect: object | None = None,
        response: FakeResponse | None = None,
        sbom_pairs: tuple[tuple[str, Path, Path], ...] | None = None,
        input_root: Path | None = None,
    ) -> int:
        if response is None:
            response = FakeResponse(
                self.asset_bytes,
                url=str(self.asset["url"]),
                content_length=len(self.asset_bytes),
            )
        side_effect = process_side_effect or self.successful_process
        with (
            mock.patch.object(MODULE, "detect_platform", return_value="linux-x86_64"),
            mock.patch.object(MODULE.urllib.request, "urlopen", return_value=response),
            mock.patch.object(MODULE.subprocess, "run", side_effect=side_effect),
        ):
            return MODULE.validate_repository(
                self.repository,
                offline=offline,
                sbom_pairs=sbom_pairs,
                input_root=input_root,
            )

    def test_checked_in_lock_and_default_paths_match_literal_golden_contract(self) -> None:
        checked_in = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "schemaVersion": 1,
                "tool": {
                    "name": "CycloneDX CLI",
                    "releaseTag": "v0.33.1",
                    "sourceCommit": "b3cfa4b0edc356dad07e0b6e7ab6da0a94af0246",
                    "sourceRepository": "https://github.com/CycloneDX/cyclonedx-cli",
                    "version": "0.33.1",
                    "platforms": GOLDEN_ASSETS,
                },
            },
            checked_in,
        )
        self.assertEqual(
            GOLDEN_PAIRS,
            tuple(
                (role, str(json_path), str(xml_path))
                for role, json_path, xml_path in MODULE.SBOM_PAIRS
            ),
        )

    def test_downloads_to_checksum_address_and_runs_exact_twelve_validations(self) -> None:
        with mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            return_value=FakeResponse(
                self.asset_bytes,
                url=str(self.asset["url"]),
                content_length=len(self.asset_bytes),
            ),
        ) as download:
            with (
                mock.patch.object(
                    MODULE, "detect_platform", return_value="linux-x86_64"
                ),
                mock.patch.object(
                    MODULE.subprocess, "run", side_effect=self.successful_process
                ),
            ):
                self.assertEqual(
                    12, MODULE.validate_repository(self.repository, offline=False)
                )

        download.assert_called_once()
        request = download.call_args.args[0]
        self.assertEqual(self.asset["url"], request.full_url)
        self.assertEqual(self.asset_bytes, self.cache_binary.read_bytes())
        self.assertTrue(self.cache_binary.stat().st_mode & 0o100)
        self.assertEqual([str(self.cache_binary), "--version"], self.commands[0])
        expected_documents: list[tuple[str, str, Path]] = []
        for name, json_relative, xml_relative in MODULE.SBOM_PAIRS:
            expected_documents.extend(
                (
                    (name, "json", self.repository / json_relative),
                    (name, "xml", self.repository / xml_relative),
                )
            )
        self.assertEqual(13, len(self.commands))
        for command, (_, format_name, path) in zip(
            self.commands[1:], expected_documents, strict=True
        ):
            self.assertEqual(
                [
                    str(self.cache_binary),
                    "validate",
                    "--input-file",
                    str(path),
                    "--input-format",
                    format_name,
                    "--input-version",
                    "v1_6",
                    "--fail-on-errors",
                ],
                command,
            )
            self.assertTrue(Path(command[0]).is_absolute())
            self.assertTrue(Path(command[3]).is_absolute())
        self.assertEqual(
            [
                "aggregate",
                "aggregate",
                "core",
                "core",
                "adapter553",
                "adapter553",
                "adapter552",
                "adapter552",
                "mysql553",
                "mysql553",
                "mysql552",
                "mysql552",
            ],
            [name for name, _, _ in expected_documents],
        )
        self.assertEqual([], list(self.cache_binary.parent.glob(".cyclonedx-download-*")))

    def test_explicit_external_input_root_runs_exact_role_pairs(self) -> None:
        self.install_cache()
        external_root = self.repository.parent / "extracted-evidence"
        external_root.mkdir()
        supplied: list[tuple[str, Path, Path]] = []
        expected_paths: list[Path] = []
        for role in (
            "mysql552",
            "mysql553",
            "core",
            "aggregate",
            "adapter552",
            "adapter553",
        ):
            json_relative = Path(f"renamed-{role}.cdx.json")
            xml_relative = Path(f"renamed-{role}.cdx.xml")
            for relative in (json_relative, xml_relative):
                path = external_root / relative
                path.write_text(f"external:{role}:{path.suffix}\n", encoding="utf-8")
            supplied.append((role, json_relative, xml_relative))
        with (
            mock.patch.object(MODULE, "detect_platform", return_value="linux-x86_64"),
            mock.patch.object(MODULE.urllib.request, "urlopen") as download,
            mock.patch.object(
                MODULE.subprocess, "run", side_effect=self.successful_process
            ),
        ):
            self.assertEqual(
                12,
                MODULE.validate_repository(
                    self.repository,
                    offline=True,
                    sbom_pairs=tuple(supplied),
                    input_root=external_root,
                ),
            )
        download.assert_not_called()
        expected_paths = [
            external_root / f"renamed-{role}.cdx.{format_name}"
            for role in MODULE.EXPECTED_PAIR_ROLES
            for format_name in ("json", "xml")
        ]
        self.assertEqual(expected_paths, [Path(command[3]) for command in self.commands[1:]])

    def test_explicit_pairs_require_exact_roles_relative_distinct_safe_paths(self) -> None:
        input_root = self.repository.parent / "evidence"
        input_root.mkdir()
        good = (
            ("aggregate", Path("aggregate.json"), Path("aggregate.xml")),
            ("core", Path("core.json"), Path("core.xml")),
            ("adapter553", Path("published.json"), Path("published.xml")),
            ("adapter552", Path("published552.json"), Path("published552.xml")),
            ("mysql553", Path("example.json"), Path("example.xml")),
            ("mysql552", Path("example552.json"), Path("example552.xml")),
        )
        for supplied_pairs, supplied_root in ((good, None), (None, input_root)):
            with self.subTest(
                all_or_none_pairs=supplied_pairs is not None,
                all_or_none_root=supplied_root is not None,
            ):
                with self.assertRaisesRegex(
                    MODULE.CycloneDxValidationError, "must be supplied together"
                ):
                    MODULE.validate_repository(
                        self.repository,
                        offline=True,
                        sbom_pairs=supplied_pairs,
                        input_root=supplied_root,
                    )
        cases = (
            ("missing", good[:5]),
            ("duplicate", (good[0], good[0], *good[2:])),
            (
                "unexpected",
                (*good[:5], ("other", Path("o.json"), Path("o.xml"))),
            ),
            ("absolute", (("aggregate", input_root / "a.json", Path("a.xml")), *good[1:])),
            ("traversal", (("aggregate", Path("../a.json"), Path("a.xml")), *good[1:])),
            (
                "same file",
                (
                    ("aggregate", Path("shared.json"), Path("aggregate.xml")),
                    ("core", Path("shared.json"), Path("core.xml")),
                    *good[2:],
                ),
            ),
        )
        for label, candidate in cases:
            with self.subTest(label=label):
                with self.assertRaises(MODULE.CycloneDxValidationError):
                    MODULE.validate_repository(
                        self.repository,
                        offline=True,
                        sbom_pairs=candidate,
                        input_root=input_root,
                    )

    def test_external_input_root_rejects_symlink_and_detects_mutation(self) -> None:
        self.install_cache()
        input_root = self.repository.parent / "external-evidence"
        input_root.mkdir()
        pairs = tuple(
            (
                role,
                Path(f"{role}.json"),
                Path(f"{role}.xml"),
            )
            for role in MODULE.EXPECTED_PAIR_ROLES
        )
        for role, json_relative, xml_relative in pairs:
            (input_root / json_relative).write_text(f"{role}:json\n", encoding="utf-8")
            (input_root / xml_relative).write_text(f"{role}:xml\n", encoding="utf-8")
        target = input_root / "aggregate.json"
        outside = self.repository.parent / "outside-bom.json"
        outside.write_text("outside\n", encoding="utf-8")
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaisesRegex(MODULE.CycloneDxValidationError, "symbolic links"):
            self.run_validator(
                offline=True,
                sbom_pairs=pairs,
                input_root=input_root,
            )
        target.unlink()
        target.write_text("aggregate:json\n", encoding="utf-8")

        mutated = False

        def mutate_external(
            arguments: list[str], **_: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal mutated
            if arguments[1:] == ["--version"]:
                return subprocess.CompletedProcess(
                    arguments, 0, stdout=MODULE.EXPECTED_VERSION_OUTPUT, stderr=""
                )
            if not mutated:
                target.write_text("mutated\n", encoding="utf-8")
                mutated = True
            return subprocess.CompletedProcess(arguments, 1, stdout="", stderr="")

        with self.assertRaisesRegex(
            MODULE.CycloneDxValidationError, "changed while the official CLI ran"
        ):
            with (
                mock.patch.object(MODULE, "detect_platform", return_value="linux-x86_64"),
                mock.patch.object(
                    MODULE.subprocess, "run", side_effect=mutate_external
                ),
            ):
                MODULE.validate_repository(
                    self.repository,
                    offline=True,
                    sbom_pairs=pairs,
                    input_root=input_root,
                )

    def test_offline_requires_existing_checksum_addressed_cache(self) -> None:
        with (
            mock.patch.object(MODULE, "detect_platform", return_value="linux-x86_64"),
            mock.patch.object(MODULE.urllib.request, "urlopen") as download,
            mock.patch.object(MODULE.subprocess, "run") as process,
        ):
            with self.assertRaisesRegex(
                MODULE.CycloneDxValidationError,
                "offline mode requires the checksum-addressed",
            ):
                MODULE.validate_repository(self.repository, offline=True)
        download.assert_not_called()
        process.assert_not_called()

    def test_offline_accepts_verified_existing_cache_without_network(self) -> None:
        self.install_cache()
        with (
            mock.patch.object(MODULE, "detect_platform", return_value="linux-x86_64"),
            mock.patch.object(MODULE.urllib.request, "urlopen") as download,
            mock.patch.object(
                MODULE.subprocess, "run", side_effect=self.successful_process
            ),
        ):
            self.assertEqual(
                12, MODULE.validate_repository(self.repository, offline=True)
            )
        download.assert_not_called()

    def test_wrong_existing_cache_fails_without_repair_or_download(self) -> None:
        wrong = b"wrong existing cache content\n"
        self.install_cache(wrong)
        with (
            mock.patch.object(MODULE, "detect_platform", return_value="linux-x86_64"),
            mock.patch.object(MODULE.urllib.request, "urlopen") as download,
            mock.patch.object(MODULE.subprocess, "run") as process,
        ):
            with self.assertRaisesRegex(
                MODULE.CycloneDxValidationError, "existing.*does not match"
            ):
                MODULE.validate_repository(self.repository, offline=False)
        self.assertEqual(wrong, self.cache_binary.read_bytes())
        download.assert_not_called()
        process.assert_not_called()

    def test_atomic_publish_does_not_replace_cache_that_appears_during_download(self) -> None:
        original_link = MODULE.os.link
        competing_bytes = b"competing cache entry\n"

        def install_competing_then_link(
            source: Path,
            destination: Path,
            *,
            follow_symlinks: bool,
        ) -> None:
            Path(destination).write_bytes(competing_bytes)
            original_link(source, destination, follow_symlinks=follow_symlinks)

        with (
            mock.patch.object(MODULE, "detect_platform", return_value="linux-x86_64"),
            mock.patch.object(
                MODULE.urllib.request,
                "urlopen",
                return_value=FakeResponse(
                    self.asset_bytes,
                    url=str(self.asset["url"]),
                    content_length=len(self.asset_bytes),
                ),
            ),
            mock.patch.object(MODULE.os, "link", side_effect=install_competing_then_link),
            mock.patch.object(MODULE.subprocess, "run") as process,
        ):
            with self.assertRaisesRegex(
                MODULE.CycloneDxValidationError, "appeared during download"
            ):
                MODULE.validate_repository(self.repository, offline=False)
        self.assertEqual(competing_bytes, self.cache_binary.read_bytes())
        self.assertEqual([], list(self.cache_binary.parent.glob(".cyclonedx-download-*")))
        process.assert_not_called()

    def test_rejects_duplicate_keys_at_any_lock_depth(self) -> None:
        lock_path = self.repository / MODULE.LOCK_RELATIVE_PATH
        original = lock_path.read_text(encoding="utf-8")
        duplicate = original.replace(
            '"asset": "cyclonedx-osx-arm64",',
            '"asset": "cyclonedx-osx-arm64",\n        '
            '"asset": "cyclonedx-osx-arm64",',
            1,
        )
        lock_path.write_text(duplicate, encoding="utf-8")
        with self.assertRaisesRegex(
            MODULE.CycloneDxValidationError, "duplicate key: asset"
        ):
            MODULE.load_lock(self.repository, lock_path)

    def test_lock_schema_rejects_identity_drift_extra_keys_and_invalid_types(self) -> None:
        mutations = (
            ("source commit", lambda value: value["tool"].__setitem__("sourceCommit", "a" * 40)),
            ("version", lambda value: value["tool"].__setitem__("version", "0.33.2")),
            ("extra", lambda value: value["tool"].__setitem__("unexpected", True)),
            (
                "boolean size",
                lambda value: value["tool"]["platforms"]["linux-x86_64"].__setitem__(
                    "size", True
                ),
            ),
            (
                "uppercase sha",
                lambda value: value["tool"]["platforms"]["linux-x86_64"].__setitem__(
                    "sha256", "A" * 64
                ),
            ),
            (
                "asset URL",
                lambda value: value["tool"]["platforms"]["linux-x86_64"].__setitem__(
                    "url", "http://example.invalid/tool"
                ),
            ),
        )
        lock_path = self.repository / MODULE.LOCK_RELATIVE_PATH
        pristine = copy.deepcopy(self.lock)
        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate = copy.deepcopy(pristine)
                mutate(candidate)
                lock_path.write_text(
                    json.dumps(candidate, sort_keys=True) + "\n", encoding="utf-8"
                )
                with self.assertRaises(MODULE.CycloneDxValidationError):
                    MODULE.load_lock(self.repository, lock_path)

    def test_rejects_lock_input_and_cache_symlinks(self) -> None:
        outside = self.repository.parent / "outside"
        outside.mkdir()

        lock_path = self.repository / MODULE.LOCK_RELATIVE_PATH
        outside_lock = outside / "lock.json"
        outside_lock.write_text(lock_path.read_text(encoding="utf-8"), encoding="utf-8")
        lock_path.unlink()
        lock_path.symlink_to(outside_lock)
        with self.assertRaisesRegex(MODULE.CycloneDxValidationError, "symbolic links"):
            MODULE.load_lock(self.repository, lock_path)

        lock_path.unlink()
        self.write_lock()
        input_path = self.repository / MODULE.SBOM_PAIRS[0][1]
        outside_input = outside / "bom.json"
        outside_input.write_text("{}\n", encoding="utf-8")
        input_path.unlink()
        input_path.symlink_to(outside_input)
        self.install_cache()
        with self.assertRaisesRegex(MODULE.CycloneDxValidationError, "symbolic links"):
            self.run_validator(offline=True)

        input_path.unlink()
        input_path.write_text("fixture\n", encoding="utf-8")
        cache_root = self.repository / MODULE.CACHE_RELATIVE_PATH
        for child in sorted(cache_root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        cache_root.rmdir()
        outside_cache = outside / "cache"
        outside_cache.mkdir()
        cache_root.parent.mkdir(parents=True, exist_ok=True)
        cache_root.symlink_to(outside_cache, target_is_directory=True)
        with self.assertRaisesRegex(
            MODULE.CycloneDxValidationError, "cache path component"
        ):
            self.run_validator(offline=False)

    def test_download_rejects_size_hash_encoding_status_and_redirect_drift(self) -> None:
        cases = (
            (
                "too large",
                FakeResponse(
                    self.asset_bytes + b"x",
                    url=str(self.asset["url"]),
                    content_length=None,
                ),
            ),
            (
                "wrong hash",
                FakeResponse(
                    b"x" * len(self.asset_bytes),
                    url=str(self.asset["url"]),
                    content_length=len(self.asset_bytes),
                ),
            ),
            (
                "declared size",
                FakeResponse(
                    self.asset_bytes,
                    url=str(self.asset["url"]),
                    content_length=len(self.asset_bytes) + 1,
                ),
            ),
            (
                "encoding",
                FakeResponse(
                    self.asset_bytes,
                    url=str(self.asset["url"]),
                    content_length=len(self.asset_bytes),
                    content_encoding="gzip",
                ),
            ),
            (
                "status",
                FakeResponse(
                    self.asset_bytes,
                    url=str(self.asset["url"]),
                    content_length=len(self.asset_bytes),
                    status=206,
                ),
            ),
            (
                "redirect",
                FakeResponse(
                    self.asset_bytes,
                    url="http://example.invalid/tool",
                    content_length=len(self.asset_bytes),
                ),
            ),
        )
        for label, response in cases:
            with self.subTest(label=label):
                if self.cache_binary.parent.exists():
                    for child in self.cache_binary.parent.iterdir():
                        child.unlink()
                with self.assertRaises(MODULE.CycloneDxValidationError):
                    self.run_validator(response=response)
                self.assertFalse(self.cache_binary.exists())
                if self.cache_binary.parent.exists():
                    self.assertEqual(
                        [], list(self.cache_binary.parent.glob(".cyclonedx-download-*"))
                    )

    def test_requires_exact_version_output_and_silent_stderr(self) -> None:
        self.install_cache()
        cases = (
            ("0.33.1\n", ""),
            (MODULE.EXPECTED_VERSION_OUTPUT.rstrip("\n"), ""),
            (MODULE.EXPECTED_VERSION_OUTPUT + "extra\n", ""),
            (MODULE.EXPECTED_VERSION_OUTPUT, "warning\n"),
        )
        for stdout, stderr in cases:
            with self.subTest(stdout=stdout, stderr=stderr):
                def version_result(
                    arguments: list[str], **_: object
                ) -> subprocess.CompletedProcess[str]:
                    return subprocess.CompletedProcess(
                        arguments, 0, stdout=stdout, stderr=stderr
                    )

                with self.assertRaisesRegex(
                    MODULE.CycloneDxValidationError, "--version output"
                ):
                    self.run_validator(
                        offline=True, process_side_effect=version_result
                    )

    def test_names_the_failed_pair_without_echoing_tool_output(self) -> None:
        self.install_cache()

        def fail_published_xml(
            arguments: list[str], **_: object
        ) -> subprocess.CompletedProcess[str]:
            if arguments[1:] == ["--version"]:
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    stdout=MODULE.EXPECTED_VERSION_OUTPUT,
                    stderr="",
                )
            if (
                arguments[4:6] == ["--input-format", "xml"]
                and "routecontract-shardingsphere-5.5" in arguments[3]
            ):
                return subprocess.CompletedProcess(
                    arguments,
                    1,
                    stdout="synthetic-sensitive-output",
                    stderr="synthetic-sensitive-error",
                )
            return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

        with self.assertRaisesRegex(
            MODULE.CycloneDxValidationError, "adapter553/xml"
        ) as caught:
            self.run_validator(offline=True, process_side_effect=fail_published_xml)
        self.assertNotIn("synthetic-sensitive", str(caught.exception))

    def test_detects_input_mutation_around_external_process(self) -> None:
        self.install_cache()
        target = self.repository / MODULE.SBOM_PAIRS[0][1]
        mutated = False

        def mutate_after_first_validation(
            arguments: list[str], **_: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal mutated
            if arguments[1:] == ["--version"]:
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    stdout=MODULE.EXPECTED_VERSION_OUTPUT,
                    stderr="",
                )
            if not mutated:
                target.write_text("mutated during validation\n", encoding="utf-8")
                mutated = True
            return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

        with self.assertRaisesRegex(
            MODULE.CycloneDxValidationError, "changed while the official CLI ran"
        ):
            self.run_validator(
                offline=True, process_side_effect=mutate_after_first_validation
            )

    def test_detect_platform_accepts_only_three_pinned_targets(self) -> None:
        cases = (
            ("Darwin", "arm64", "darwin-arm64"),
            ("Darwin", "x86_64", "darwin-x86_64"),
            ("Linux", "x86_64", "linux-x86_64"),
        )
        for system, machine, expected in cases:
            with (
                self.subTest(system=system, machine=machine),
                mock.patch.object(MODULE.platform, "system", return_value=system),
                mock.patch.object(MODULE.platform, "machine", return_value=machine),
            ):
                self.assertEqual(expected, MODULE.detect_platform())
        with (
            mock.patch.object(MODULE.platform, "system", return_value="Linux"),
            mock.patch.object(MODULE.platform, "machine", return_value="aarch64"),
        ):
            with self.assertRaisesRegex(
                MODULE.CycloneDxValidationError, "unsupported.*Linux:aarch64"
            ):
                MODULE.detect_platform()

    def test_cli_explicit_input_contract_is_all_or_none(self) -> None:
        explicit_arguments = [
            "--offline",
            "--input-root",
            str(self.repository),
            "--pair",
            "aggregate",
            "a.json",
            "a.xml",
            "--pair",
            "core",
            "c.json",
            "c.xml",
            "--pair",
            "adapter553",
            "p.json",
            "p.xml",
            "--pair",
            "adapter552",
            "p552.json",
            "p552.xml",
            "--pair",
            "mysql553",
            "e.json",
            "e.xml",
            "--pair",
            "mysql552",
            "e552.json",
            "e552.xml",
        ]
        with (
            mock.patch.object(
                MODULE, "_repository_root_from_script", return_value=self.repository
            ),
            mock.patch.object(MODULE, "validate_repository", return_value=12) as validate,
        ):
            self.assertEqual(0, MODULE.main(explicit_arguments))
        validate.assert_called_once_with(
            self.repository,
            offline=True,
            sbom_pairs=(
                ("aggregate", Path("a.json"), Path("a.xml")),
                ("core", Path("c.json"), Path("c.xml")),
                ("adapter553", Path("p.json"), Path("p.xml")),
                ("adapter552", Path("p552.json"), Path("p552.xml")),
                ("mysql553", Path("e.json"), Path("e.xml")),
                ("mysql552", Path("e552.json"), Path("e552.xml")),
            ),
            input_root=self.repository,
        )

        invalid_argument_sets = (
            ["--input-root", str(self.repository)],
            ["--pair", "aggregate", "a.json", "a.xml"],
        )
        for arguments in invalid_argument_sets:
            with (
                self.subTest(arguments=arguments),
                mock.patch.object(
                    MODULE, "_repository_root_from_script", return_value=self.repository
                ),
                mock.patch.object(MODULE, "validate_repository") as invalid_validate,
                mock.patch("sys.stderr", new_callable=io.StringIO),
            ):
                self.assertEqual(2, MODULE.main(arguments))
            invalid_validate.assert_not_called()


@unittest.skipUnless(
    os.environ.get("ROUTECONTRACT_REAL_CYCLONEDX") == "1",
    "set ROUTECONTRACT_REAL_CYCLONEDX=1 for a real pinned CLI and twelve-file probe",
)
class RealOfficialCycloneDxValidatorTest(unittest.TestCase):
    def test_current_generated_twelve_files_with_real_cli(self) -> None:
        required = [
            REPOSITORY_ROOT / relative
            for _, json_relative, xml_relative in MODULE.SBOM_PAIRS
            for relative in (json_relative, xml_relative)
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            self.skipTest("generate the twelve verified SBOMs first: " + ", ".join(missing))
        self.assertEqual(
            12,
            MODULE.validate_repository(REPOSITORY_ROOT.resolve(), offline=False),
        )


if __name__ == "__main__":
    unittest.main()
