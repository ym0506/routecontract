#!/usr/bin/env python3
"""Acceptance tests for the no-credential exact v0.1.2 installer wrapper."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install-public-v0_1_2.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("public_v012_installer", INSTALLER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {INSTALLER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeDownloader:
    def __init__(self, payloads: dict[str, bytes]):
        self.payloads = payloads
        self.requested: list[str] = []

    def __call__(self, url: str, destination: Path) -> None:
        self.requested.append(url)
        destination.write_bytes(self.payloads[url])


class PublicV012InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve(strict=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _fixture(self, module):
        asset_payloads = {
            name: f"fixture:{name}\n".encode("utf-8") for name in module.ASSET_NAMES
        }
        checksum_payload = "".join(
            f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
            for name, payload in asset_payloads.items()
            if name != "SHA256SUMS"
        ).encode("ascii")
        asset_payloads["SHA256SUMS"] = checksum_payload
        installer_payload = b"#!/usr/bin/env python3\nraise SystemExit(0)\n"
        preparer_payload = b"#!/usr/bin/env python3\nraise SystemExit(0)\n"
        payloads = {
            module.INSTALLER_URL: installer_payload,
            module.CHECKSUM_PREPARER_URL: preparer_payload,
        }
        payloads.update(
            {
                f"{module.RELEASE_DOWNLOAD_BASE}/{name}": payload
                for name, payload in asset_payloads.items()
            }
        )
        return (
            asset_payloads,
            installer_payload,
            preparer_payload,
            FakeDownloader(payloads),
        )

    def test_production_anchors_and_inventory_are_exact(self) -> None:
        module = load_installer()
        self.assertEqual("0.1.2", module.VERSION)
        self.assertEqual(
            "6adacbe04d60b3af83d9067a14a878d26a6c90f5", module.TAG_OBJECT
        )
        self.assertEqual(
            "fc4fdd16c21574afa1150654ce354cf8004b138b", module.RELEASE_COMMIT
        )
        self.assertEqual(
            "7849adf417f0170b08d01902b023e8b328d8796f7c2aeacc471eb7acf8e2b217",
            module.EXPECTED_INDEX_SHA256,
        )
        self.assertEqual(
            "134b265709ac071dedd395da269426d83f1972f602c3b3f7d2201eecc525e204",
            module.EXPECTED_INSTALLER_SHA256,
        )
        self.assertEqual(
            "ee1928e578819fb597fffe7f1c72c055ff74ec6b36d37fe35f29c7fbd382b7b7",
            module.EXPECTED_CHECKSUM_PREPARER_SHA256,
        )
        self.assertEqual(
            "2264b6e6292ee80f131148f2acef601cbaede096",
            module.CHECKSUM_PREPARER_COMMIT,
        )
        self.assertEqual(
            "https://raw.githubusercontent.com/ym0506/routecontract/"
            "fc4fdd16c21574afa1150654ce354cf8004b138b/"
            "scripts/install-release-assets.py",
            module.INSTALLER_URL,
        )
        self.assertEqual(
            "https://raw.githubusercontent.com/ym0506/routecontract/"
            "2264b6e6292ee80f131148f2acef601cbaede096/"
            "scripts/prepare_maven_v0_1_2_checksums.py",
            module.CHECKSUM_PREPARER_URL,
        )
        self.assertEqual(
            (
                "SHA256SUMS",
                "routecontract-0.1.2-source.zip",
                "routecontract-shardingsphere-5.5-0.1.2.jar",
                "routecontract-shardingsphere-5.5-0.1.2-sources.jar",
                "routecontract-shardingsphere-5.5-0.1.2-javadoc.jar",
                "routecontract-shardingsphere-5.5.pom",
                "routecontract-shardingsphere-5.5-cyclonedx.json",
                "routecontract-shardingsphere-5.5-cyclonedx.xml",
                "routecontract-aggregate-cyclonedx.json",
                "routecontract-aggregate-cyclonedx.xml",
                "supply-chain-evidence.json",
                "test-summary.txt",
            ),
            module.ASSET_NAMES,
        )
        expected_sizes = {
            module.INSTALLER_URL: 77_732,
            module.CHECKSUM_PREPARER_URL: 10_727,
            f"{module.RELEASE_DOWNLOAD_BASE}/SHA256SUMS": 1_155,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-0.1.2-source.zip": 1_062_150,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-0.1.2.jar": 75_891,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-0.1.2-sources.jar": 46_313,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-0.1.2-javadoc.jar": 208_628,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5.pom": 2_138,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-cyclonedx.json": 114_460,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-cyclonedx.xml": 103_653,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-aggregate-cyclonedx.json": 373_935,
            f"{module.RELEASE_DOWNLOAD_BASE}/routecontract-aggregate-cyclonedx.xml": 338_758,
            f"{module.RELEASE_DOWNLOAD_BASE}/supply-chain-evidence.json": 3_700,
            f"{module.RELEASE_DOWNLOAD_BASE}/test-summary.txt": 950,
        }
        self.assertEqual(
            expected_sizes,
            module.EXPECTED_DOWNLOAD_SIZES,
        )

    def test_public_docs_pin_the_exact_wrapper_contract(self) -> None:
        wrapper_url = (
            "https://raw.githubusercontent.com/ym0506/routecontract/"
            "a11c5ca1df41e4a0d25d6e211dd2274e35d5b593/"
            "scripts/install-public-v0_1_2.py"
        )
        wrapper_sha256 = (
            "bec71208b138765bbc017589cb04ef0159e015364616e14dc19c633873b9ecb8"
        )
        required_fragments = (
            wrapper_url,
            'expected_helper_size="33309"',
            f'expected_helper_sha256="{wrapper_sha256}"',
            '--max-filesize "${expected_helper_size}"',
            "payload = sys.stdin.buffer.read(expected_size + 1)",
            'flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)',
            'test -f "${helper}"',
            'test ! -L "${helper}"',
            'test "${actual_helper_size}" = "${expected_helper_size}"',
            'python3 -I "${helper}" --repository "${repository_dir}"',
        )

        for relative_path in (
            "README.md",
            "README.en.md",
            "docs/first-integration.md",
        ):
            with self.subTest(relative_path=relative_path):
                contents = (REPOSITORY_ROOT / relative_path).read_text(
                    encoding="utf-8"
                )
                for fragment in required_fragments:
                    self.assertIn(fragment, contents)
                self.assertNotIn(
                    "raw.githubusercontent.com/ym0506/routecontract/main/"
                    "scripts/install-public-v0_1_2.py",
                    contents,
                )

        guide = (REPOSITORY_ROOT / "docs/first-integration.md").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            guide.index("The recommended wrapper below downloads"),
            guide.index("Manual asset-by-asset audit fallback"),
        )
        self.assertIn(
            "Do not run the checksum helper again against that repository.",
            guide,
        )

    def test_downloads_exact_public_state_then_delegates_once(self) -> None:
        module = load_installer()
        asset_payloads, installer_payload, preparer_payload, downloader = self._fixture(
            module
        )
        repository = self.root / "new-repository"
        calls: list[list[str]] = []
        output = io.StringIO()

        def fake_run(arguments, **kwargs):
            self.assertEqual(subprocess.DEVNULL, kwargs["stdin"])
            self.assertFalse(kwargs["check"])
            self.assertEqual(module.INSTALL_TIMEOUT_SECONDS, kwargs["timeout"])
            calls.append(arguments)
            selected_repository = Path(arguments[arguments.index("--repository") + 1])
            coordinate = (
                selected_repository
                / "io/github/ym0506/routecontract"
                / "routecontract-shardingsphere-5.5"
                / module.VERSION
            )
            coordinate.mkdir(parents=True, exist_ok=True)
            payload_names = (
                f"routecontract-shardingsphere-5.5-{module.VERSION}.pom",
                f"routecontract-shardingsphere-5.5-{module.VERSION}.jar",
                f"routecontract-shardingsphere-5.5-{module.VERSION}-sources.jar",
                f"routecontract-shardingsphere-5.5-{module.VERSION}-javadoc.jar",
            )
            if "install-release-assets.py" in arguments[2]:
                for name in payload_names:
                    (coordinate / name).write_bytes(f"fixture:{name}\n".encode())
            else:
                for name in payload_names:
                    for algorithm in ("sha1", "sha256"):
                        (coordinate / f"{name}.{algorithm}").write_text(
                            f"fixture-{algorithm}\n", encoding="ascii"
                        )
            return subprocess.CompletedProcess(arguments, 0, b"installed\n", b"")

        with (
            mock.patch.object(
                module,
                "EXPECTED_INDEX_SHA256",
                hashlib.sha256(asset_payloads["SHA256SUMS"]).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_INSTALLER_SHA256",
                hashlib.sha256(installer_payload).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_CHECKSUM_PREPARER_SHA256",
                hashlib.sha256(preparer_payload).hexdigest(),
            ),
            mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            contextlib.redirect_stdout(output),
        ):
            module.install_public_release(repository, downloader=downloader)

        self.assertEqual(2, len(calls))
        staged_repository = Path(calls[0][-1])
        self.assertNotEqual(repository, staged_repository)
        self.assertEqual("staged-maven", staged_repository.name)
        self.assertTrue(staged_repository.parent.name.startswith(
            "routecontract-v0.1.2-public-"
        ))
        self.assertEqual(
            [
                sys.executable,
                "-I",
                calls[0][2],
                "--release-assets-dir",
                calls[0][4],
                "--repository",
                os.fspath(staged_repository),
            ],
            calls[0],
        )
        self.assertEqual("install-release-assets.py", Path(calls[0][2]).name)
        self.assertEqual("assets", Path(calls[0][4]).name)
        self.assertEqual(
            [
                sys.executable,
                "-I",
                calls[1][2],
                "--repository",
                os.fspath(staged_repository),
            ],
            calls[1],
        )
        self.assertEqual(
            "prepare_maven_v0_1_2_checksums.py", Path(calls[1][2]).name
        )
        self.assertEqual(14, len(downloader.requested))
        self.assertEqual(14, len(set(downloader.requested)))
        self.assertEqual(0o700, stat.S_IMODE(repository.stat().st_mode))
        coordinate = repository.joinpath(*module._coordinate_parts())
        self.assertEqual(
            module._expected_coordinate_names(),
            {path.name for path in coordinate.iterdir()},
        )
        self.assertFalse(staged_repository.exists())
        self.assertIn("ROUTECONTRACT_PUBLIC_INSTALL_OK", output.getvalue())
        self.assertIn("tagObjectAnchor=6adacbe04d60", output.getvalue())
        self.assertIn("releaseCommit=fc4fdd16c215", output.getvalue())
        self.assertIn("2026-12-05 UTC", output.getvalue())

    def test_rejects_checksum_index_mismatch_before_delegating(self) -> None:
        module = load_installer()
        _, installer_payload, preparer_payload, downloader = self._fixture(module)
        downloader.payloads[
            f"{module.RELEASE_DOWNLOAD_BASE}/SHA256SUMS"
        ] = b"tampered\n"

        with (
            mock.patch.object(
                module,
                "EXPECTED_INSTALLER_SHA256",
                hashlib.sha256(installer_payload).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_CHECKSUM_PREPARER_SHA256",
                hashlib.sha256(preparer_payload).hexdigest(),
            ),
            mock.patch.object(module.subprocess, "run") as delegated,
            self.assertRaisesRegex(
                module.PublicInstallError,
                "SHA256SUMS mismatch.*reserved target residue.*do not reuse",
            ),
        ):
            module.install_public_release(
                self.root / "repository", downloader=downloader
            )

        delegated.assert_not_called()
        self.assertTrue((self.root / "repository").is_dir())

    def test_rejects_each_helper_hash_mismatch_before_delegating(self) -> None:
        module = load_installer()

        for helper in ("installer", "preparer"):
            with self.subTest(helper=helper):
                _, installer_payload, preparer_payload, downloader = self._fixture(
                    module
                )
                repository = self.root / f"bad-{helper}"
                patches = []
                if helper == "installer":
                    downloader.payloads[module.INSTALLER_URL] = b"tampered-installer\n"
                    patches.append(
                        mock.patch.object(
                            module,
                            "EXPECTED_CHECKSUM_PREPARER_SHA256",
                            hashlib.sha256(preparer_payload).hexdigest(),
                        )
                    )
                    expected = "installer SHA-256 mismatch"
                else:
                    downloader.payloads[
                        module.CHECKSUM_PREPARER_URL
                    ] = b"tampered-preparer\n"
                    patches.append(
                        mock.patch.object(
                            module,
                            "EXPECTED_INSTALLER_SHA256",
                            hashlib.sha256(installer_payload).hexdigest(),
                        )
                    )
                    expected = "checksum preparer SHA-256 mismatch"

                with contextlib.ExitStack() as stack:
                    for selected_patch in patches:
                        stack.enter_context(selected_patch)
                    delegated = stack.enter_context(
                        mock.patch.object(module.subprocess, "run")
                    )
                    stack.enter_context(
                        self.assertRaisesRegex(
                            module.PublicInstallError,
                            f"{expected}.*reserved target residue",
                        )
                    )
                    module.install_public_release(repository, downloader=downloader)

                delegated.assert_not_called()
                self.assertTrue(repository.is_dir())

    def test_installer_timeout_preserves_target_and_reports_no_retry(self) -> None:
        module = load_installer()
        asset_payloads, installer_payload, preparer_payload, downloader = self._fixture(
            module
        )
        repository = self.root / "timed-out"
        with (
            mock.patch.object(
                module,
                "EXPECTED_INDEX_SHA256",
                hashlib.sha256(asset_payloads["SHA256SUMS"]).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_INSTALLER_SHA256",
                hashlib.sha256(installer_payload).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_CHECKSUM_PREPARER_SHA256",
                hashlib.sha256(preparer_payload).hexdigest(),
            ),
            mock.patch.object(
                module.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(
                    cmd=["tag-pinned-installer"],
                    timeout=module.INSTALL_TIMEOUT_SECONDS,
                ),
            ) as delegated,
            self.assertRaisesRegex(
                module.PublicInstallError,
                "installer timed out.*reserved target residue.*do not reuse",
            ),
        ):
            module.install_public_release(repository, downloader=downloader)

        self.assertEqual(1, delegated.call_count)
        self.assertTrue(repository.is_dir())

    def test_validates_and_canonicalizes_target_before_network(self) -> None:
        module = load_installer()
        with self.assertRaisesRegex(module.PublicInstallError, "absolute"):
            module._validate_repository_argument("relative/repository")

        existing = self.root / "existing"
        existing.mkdir()
        with self.assertRaisesRegex(module.PublicInstallError, "new absent"):
            module._validate_repository_argument(os.fspath(existing))

        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(module.PublicInstallError, "new absent"):
            module._validate_repository_argument(os.fspath(link))

        conventional = Path.home().resolve(strict=True) / ".m2" / "repository"
        with self.assertRaisesRegex(module.PublicInstallError, "must not be"):
            module._validate_repository_argument(os.fspath(conventional / "pilot"))

        canonical_parent = self.root / "canonical-parent"
        canonical_parent.mkdir()
        alias_parent = self.root / "alias-parent"
        alias_parent.symlink_to(canonical_parent, target_is_directory=True)
        self.assertEqual(
            canonical_parent / "repository",
            module._validate_repository_argument(
                os.fspath(alias_parent / "repository")
            ),
        )

        nonexistent_home = self.root / "nonexistent-home"
        with mock.patch.object(module.Path, "home", return_value=nonexistent_home):
            self.assertEqual(
                self.root / "safe-repository",
                module._validate_repository_argument(
                    os.fspath(self.root / "safe-repository")
                ),
            )

    def test_parent_swap_inside_delegate_never_redirects_helper_writes(self) -> None:
        module = load_installer()
        asset_payloads, installer_payload, preparer_payload, delegate = self._fixture(
            module
        )
        approved_parent = self.root / "approved-parent"
        approved_parent.mkdir()
        moved_parent = self.root / "approved-parent-moved"
        outside = self.root / "outside"
        outside.mkdir()
        repository = approved_parent / "raced-repository"

        calls = 0

        def fake_run(arguments, **kwargs):
            nonlocal calls
            calls += 1
            selected_repository = Path(
                arguments[arguments.index("--repository") + 1]
            )
            self.assertNotEqual(repository, selected_repository)
            coordinate = selected_repository.joinpath(*module._coordinate_parts())
            coordinate.mkdir(parents=True, exist_ok=True)
            if calls == 1:
                for name in module._payload_names():
                    (coordinate / name).write_bytes(f"fixture:{name}\n".encode())
                approved_parent.rename(moved_parent)
                approved_parent.symlink_to(outside, target_is_directory=True)
            else:
                for name in module._payload_names():
                    for algorithm in ("sha1", "sha256"):
                        (coordinate / f"{name}.{algorithm}").write_text(
                            f"fixture-{algorithm}\n", encoding="ascii"
                        )
            return subprocess.CompletedProcess(arguments, 0, b"", b"")

        with (
            mock.patch.object(
                module,
                "EXPECTED_INDEX_SHA256",
                hashlib.sha256(asset_payloads["SHA256SUMS"]).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_INSTALLER_SHA256",
                hashlib.sha256(installer_payload).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_CHECKSUM_PREPARER_SHA256",
                hashlib.sha256(preparer_payload).hexdigest(),
            ),
            mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            self.assertRaisesRegex(
                module.PublicInstallError,
                "path binding changed.*reserved target residue",
            ),
        ):
            module.install_public_release(repository, downloader=delegate)

        self.assertEqual(2, calls)
        self.assertFalse((outside / "raced-repository").exists())
        self.assertTrue((moved_parent / "raced-repository").is_dir())
        self.assertEqual([], list((moved_parent / "raced-repository").iterdir()))

    def test_post_mkdir_reservation_failures_report_retained_residue(self) -> None:
        module = load_installer()

        for case in ("open", "fchmod"):
            with self.subTest(case=case):
                repository = self.root / f"reservation-{case}"
                if case == "open":
                    real_open = module.os.open

                    def fail_target_open(path, flags, *args, **kwargs):
                        if (
                            path == repository.name
                            and kwargs.get("dir_fd") is not None
                        ):
                            raise OSError("simulated target open failure")
                        return real_open(path, flags, *args, **kwargs)

                    selected_patch = mock.patch.object(
                        module.os,
                        "open",
                        side_effect=fail_target_open,
                    )
                else:
                    selected_patch = mock.patch.object(
                        module.os,
                        "fchmod",
                        side_effect=OSError("simulated fchmod failure"),
                    )

                with (
                    selected_patch,
                    self.assertRaisesRegex(
                        module.PublicInstallError,
                        "initialization failed after creation.*"
                        "reserved target residue.*do not reuse",
                    ),
                ):
                    module._reserve_repository(repository)

                self.assertTrue(repository.is_dir())

    def test_python_version_gate_precedes_argument_and_network_work(self) -> None:
        module = load_installer()
        with (
            mock.patch.object(module.sys, "version_info", (3, 9, 20)),
            self.assertRaisesRegex(module.PublicInstallError, "3.10 or newer"),
        ):
            module.run([])

    def test_url_policy_is_https_and_host_scoped(self) -> None:
        module = load_installer()
        for url in (
            module.INSTALLER_URL,
            module.CHECKSUM_PREPARER_URL,
            f"{module.RELEASE_DOWNLOAD_BASE}/SHA256SUMS",
            "https://release-assets.githubusercontent.com/github-production-release-asset/file",
        ):
            module._validate_https_url(url)

        for url in (
            "http://github.com/ym0506/routecontract",
            "https://example.com/routecontract.jar",
            "https://user:password@github.com/ym0506/routecontract",
            "https://github.com/ym0506/routecontract#fragment",
        ):
            with self.assertRaisesRegex(module.PublicInstallError, "untrusted"):
                module._validate_https_url(url)

        release_url = f"{module.RELEASE_DOWNLOAD_BASE}/SHA256SUMS"
        signed_url = (
            "https://release-assets.githubusercontent.com/github-production-release-asset/"
            "fixture?sp=r&sig=secret"
        )
        module._validate_release_redirect(release_url, "302", signed_url)
        with self.assertRaisesRegex(module.PublicInstallError, "not an exact"):
            module._validate_release_redirect(release_url, "302", module.INSTALLER_URL)
        with self.assertRaisesRegex(module.PublicInstallError, "allowed 302"):
            module._validate_release_redirect(release_url, "301", signed_url)

    def test_curl_validates_redirect_before_fetch_and_withholds_signed_url(self) -> None:
        module = load_installer()
        destination = self.root / "download.bin"
        payload = b"fixed payload\n"
        initial = f"{module.RELEASE_DOWNLOAD_BASE}/SHA256SUMS"
        effective = (
            "https://release-assets.githubusercontent.com/github-production-release-asset/"
            "fixture?sig=secret"
        )

        def discover(arguments, **kwargs):
            self.assertIn("--proto-redir", arguments)
            self.assertIn("--head", arguments)
            self.assertNotIn("--location", arguments)
            self.assertNotIn("--retry-all-errors", arguments)
            self.assertNotIn("--remove-on-error", arguments)
            self.assertEqual("0", arguments[arguments.index("--max-redirs") + 1])
            self.assertEqual(
                "Accept-Encoding: identity",
                arguments[arguments.index("--header") + 1],
            )
            for name in module.GITHUB_AUTH_ENVIRONMENT:
                self.assertNotIn(name, kwargs["env"])
            return subprocess.CompletedProcess(
                arguments, 0, f"302\n{effective}".encode("utf-8"), b""
            )

        def fetch(curl, url, selected_destination, expected_size):
            self.assertEqual(effective, url)
            self.assertEqual(destination, selected_destination)
            self.assertEqual(len(payload), expected_size)
            selected_destination.write_bytes(payload)

        with (
            mock.patch.object(module.subprocess, "run", side_effect=discover),
            mock.patch.object(module, "_fetch_exact_url", side_effect=fetch) as fetched,
        ):
            module._download_with_curl(
                Path("/usr/bin/curl"), initial, destination, len(payload)
            )
        fetched.assert_called_once()
        self.assertEqual(payload, destination.read_bytes())

        forbidden = (
            "https://evil.invalid/file?sp=r&sig=secret-that-must-not-leak"
        )
        with (
            mock.patch.object(
                module.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    [], 0, f"302\n{forbidden}".encode("utf-8"), b""
                ),
            ),
            mock.patch.object(module, "_fetch_exact_url") as forbidden_fetch,
            self.assertRaises(module.PublicInstallError) as failure,
        ):
            module._download_with_curl(
                Path("/usr/bin/curl"), initial, self.root / "failed.bin", len(payload)
            )
        forbidden_fetch.assert_not_called()
        self.assertNotIn("secret-that-must-not-leak", str(failure.exception))

    def test_curl_stream_has_hard_cap_cleans_failures_and_scrubs_tokens(self) -> None:
        module = load_installer()
        fake_curl = self.root / "fake-curl.py"
        fake_curl.write_text(
            """#!/usr/bin/env python3
import os
from pathlib import Path
import sys

for name in (\"GH_TOKEN\", \"GITHUB_TOKEN\", \"GITHUB_AUTH_TOKEN\"):
    if name in os.environ:
        raise SystemExit(91)
arguments = sys.argv[1:]
header = Path(arguments[arguments.index(\"--dump-header\") + 1])
header.write_bytes(b\"HTTP/1.1 200 OK\\r\\nContent-Type: application/octet-stream\\r\\n\\r\\n\")
sys.stdout.buffer.write(b\"x\" * int(os.environ[\"FAKE_CURL_BODY_SIZE\"]))
""",
            encoding="utf-8",
        )
        fake_curl.chmod(0o755)

        with mock.patch.dict(
            module.os.environ,
            {
                "FAKE_CURL_BODY_SIZE": "6",
                "GH_TOKEN": "do-not-pass",
                "GITHUB_TOKEN": "do-not-pass",
            },
        ):
            overlong = self.root / "overlong.bin"
            with self.assertRaisesRegex(module.PublicInstallError, "hard byte limit"):
                module._fetch_exact_url(
                    fake_curl, module.INSTALLER_URL, overlong, 5
                )
            self.assertFalse(overlong.exists())

        with mock.patch.dict(
            module.os.environ, {"FAKE_CURL_BODY_SIZE": "4"}
        ):
            truncated = self.root / "truncated.bin"
            with self.assertRaisesRegex(module.PublicInstallError, "size mismatch"):
                module._fetch_exact_url(
                    fake_curl, module.INSTALLER_URL, truncated, 5
                )
            self.assertFalse(truncated.exists())

        with mock.patch.dict(
            module.os.environ, {"FAKE_CURL_BODY_SIZE": "5"}
        ):
            exact = self.root / "exact.bin"
            module._fetch_exact_url(fake_curl, module.INSTALLER_URL, exact, 5)
            self.assertEqual(b"xxxxx", exact.read_bytes())

    def test_posix_preflight_and_direct_api_validation_precede_network(self) -> None:
        module = load_installer()
        _, _, _, downloader = self._fixture(module)
        with self.assertRaisesRegex(module.PublicInstallError, "absolute"):
            module.install_public_release(
                Path("relative-repository"), downloader=downloader
            )
        self.assertEqual([], downloader.requested)

        repository = self.root / "unsupported"
        with (
            mock.patch.object(module.os, "O_NOFOLLOW", None),
            self.assertRaisesRegex(module.PublicInstallError, "O_NOFOLLOW"),
        ):
            module.install_public_release(repository, downloader=downloader)
        self.assertFalse(repository.exists())
        self.assertEqual([], downloader.requested)

    def test_delegate_failures_preserve_target_and_forbid_reuse(self) -> None:
        module = load_installer()
        asset_payloads, installer_payload, preparer_payload, downloader = self._fixture(
            module
        )
        repository = self.root / "failed-install"

        with (
            mock.patch.object(
                module,
                "EXPECTED_INDEX_SHA256",
                hashlib.sha256(asset_payloads["SHA256SUMS"]).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_INSTALLER_SHA256",
                hashlib.sha256(installer_payload).hexdigest(),
            ),
            mock.patch.object(
                module,
                "EXPECTED_CHECKSUM_PREPARER_SHA256",
                hashlib.sha256(preparer_payload).hexdigest(),
            ),
            mock.patch.object(
                module.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 2, b"", b"rejected"),
            ) as delegated,
            self.assertRaisesRegex(
                module.PublicInstallError,
                "installer rejected.*reserved target residue.*do not reuse",
            ),
        ):
            module.install_public_release(repository, downloader=downloader)

        self.assertEqual(1, delegated.call_count)
        self.assertTrue(repository.is_dir())
        with self.assertRaisesRegex(module.PublicInstallError, "new absent"):
            module.install_public_release(repository, downloader=downloader)

    def test_helper_failures_preserve_empty_target_without_publishing_staging(self) -> None:
        module = load_installer()

        for case, checksum_exit in (("checksum", 2), ("inventory", 0)):
            with self.subTest(case=case):
                asset_payloads, installer_payload, preparer_payload, downloader = (
                    self._fixture(module)
                )
                repository = self.root / f"failed-{case}"
                call_count = 0

                def fake_run(arguments, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    selected_repository = Path(
                        arguments[arguments.index("--repository") + 1]
                    )
                    coordinate = (
                        selected_repository
                        / "io/github/ym0506/routecontract"
                        / "routecontract-shardingsphere-5.5"
                        / module.VERSION
                    )
                    payload_names = (
                        f"routecontract-shardingsphere-5.5-{module.VERSION}.pom",
                        f"routecontract-shardingsphere-5.5-{module.VERSION}.jar",
                        f"routecontract-shardingsphere-5.5-{module.VERSION}-sources.jar",
                        f"routecontract-shardingsphere-5.5-{module.VERSION}-javadoc.jar",
                    )
                    if call_count == 1:
                        coordinate.mkdir(parents=True)
                        for name in payload_names:
                            (coordinate / name).write_bytes(b"payload\n")
                        return subprocess.CompletedProcess(arguments, 0, b"", b"")
                    return subprocess.CompletedProcess(
                        arguments, checksum_exit, b"", b"checksum failed"
                    )

                expected_message = (
                    "checksum preparation failed"
                    if case == "checksum"
                    else "inventory is not exact"
                )
                with (
                    mock.patch.object(
                        module,
                        "EXPECTED_INDEX_SHA256",
                        hashlib.sha256(asset_payloads["SHA256SUMS"]).hexdigest(),
                    ),
                    mock.patch.object(
                        module,
                        "EXPECTED_INSTALLER_SHA256",
                        hashlib.sha256(installer_payload).hexdigest(),
                    ),
                    mock.patch.object(
                        module,
                        "EXPECTED_CHECKSUM_PREPARER_SHA256",
                        hashlib.sha256(preparer_payload).hexdigest(),
                    ),
                    mock.patch.object(module.subprocess, "run", side_effect=fake_run),
                    self.assertRaisesRegex(
                        module.PublicInstallError,
                        f"{expected_message}.*reserved target residue",
                    ),
                ):
                    module.install_public_release(repository, downloader=downloader)

                self.assertTrue(repository.is_dir())
                self.assertEqual([], list(repository.iterdir()))

    def test_cli_rejects_relative_target(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(INSTALLER), "--repository", "relative"],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("absolute", result.stderr)


if __name__ == "__main__":
    unittest.main()
