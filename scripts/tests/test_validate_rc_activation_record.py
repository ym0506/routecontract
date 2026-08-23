from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import sys
import subprocess
import tempfile
import unittest
from unittest import mock
import warnings
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts/validate-rc-activation-record.py"
SPEC = importlib.util.spec_from_file_location("validate_rc_activation_record", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import precondition
    raise RuntimeError(f"could not import {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


TAG = "v0.1.0-rc1"
VERSION = TAG[1:]
TAG_COMMIT = "a" * 40
ARTIFACT_DIGEST = "sha256:" + "b" * 64
SHA256SUMS_DIGEST = "c" * 64
RC1_FORM_SHA256 = "0f4afc4ac098e0ee425704168f045352b3e2a77f856a0ae7438a9f93d955e583"
RC2_FORM_SHA256 = "518c4102b9a0f7725b46b825ad5952263b3418bdb07b0164c54a037d902e7f8a"


def valid_document(
    *, tag: str = TAG, tag_commit: str = TAG_COMMIT
) -> dict[str, object]:
    version = tag[1:]
    issue_form_filename = MODULE.expected_issue_form_filename(tag)
    return {
        "issueFormFilename": issue_form_filename,
        "issueFormPermalink": (
            f"{MODULE.REPOSITORY}/blob/{tag_commit}/.github/ISSUE_TEMPLATE/"
            f"{issue_form_filename}"
        ),
        "issueFormUrl": (
            f"{MODULE.REPOSITORY}/issues/new?template={issue_form_filename}"
        ),
        "publicAssets": list(MODULE.expected_public_assets(version)),
        "releaseEvidence": {
            "artifactDigest": ARTIFACT_DIGEST,
            "artifactFileCount": 17,
            "artifactId": 24680,
            "headSha": tag_commit,
            "runId": 13579,
            "runUrl": f"{MODULE.REPOSITORY}/actions/runs/13579",
        },
        "releaseImmutability": {"enabled": True, "enforcedByOwner": False},
        "releaseState": {"draft": False, "immutable": True, "prerelease": True},
        "releaseUrl": f"{MODULE.REPOSITORY}/releases/tag/{tag}",
        "repository": MODULE.REPOSITORY,
        "schemaVersion": 2,
        "sha256sumsSha256": SHA256SUMS_DIGEST,
        "tag": tag,
        "tagCommit": tag_commit,
        "taggedProtocolUrl": (
            f"{MODULE.REPOSITORY}/blob/{tag}/docs/independent-install-study.md"
        ),
        "taggedReadmeUrl": f"{MODULE.REPOSITORY}/blob/{tag}/README.md",
    }


def create_asset_set(
    root: Path,
) -> tuple[dict[str, object], MODULE.ValidatedRecord]:
    document = valid_document()
    payloads = MODULE.expected_public_assets(VERSION)[:-1]
    lines: list[str] = []
    for index, name in enumerate(payloads):
        content = f"synthetic payload {index}: {name}\n".encode()
        (root / name).write_bytes(content)
        lines.append(f"{hashlib.sha256(content).hexdigest()}  {name}\n")
    checksums = "".join(lines).encode("ascii")
    (root / "SHA256SUMS").write_bytes(checksums)
    document["sha256sumsSha256"] = hashlib.sha256(checksums).hexdigest()
    return document, MODULE.validate_record_schema(document)


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


class ActivationRecordSchemaTest(unittest.TestCase):
    def test_accepts_exact_strict_rc_schema(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        self.assertEqual(TAG, record.tag)
        self.assertEqual(VERSION, record.version)
        self.assertEqual(TAG_COMMIT, record.tag_commit)
        self.assertEqual(12, len(record.public_assets))
        self.assertEqual(11, len(record.payloads))
        self.assertEqual("independent-rc1-install.yml", record.issue_form_filename)

    def test_exact_object_schema_error_never_echoes_attacker_controlled_keys(
        self,
    ) -> None:
        canary = "CANARY_PRIVATE_SCHEMA_KEY"
        with self.assertRaises(MODULE.ActivationError) as caught:
            MODULE._exact_object({canary: True}, {"SECRET_REQUIRED_FIELD"}, "record")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIn("missing_count=1", str(caught.exception))
        self.assertIn("unexpected_count=1", str(caught.exception))
        self.assertNotIn(canary, str(caught.exception))
        self.assertNotIn("SECRET_REQUIRED_FIELD", str(caught.exception))

        for scope in ("top", "nested"):
            document = valid_document()
            target = document if scope == "top" else document["releaseEvidence"]
            target[canary] = "CANARY_PRIVATE_SCHEMA_VALUE"
            with self.subTest(scope=scope, surface="direct"), self.assertRaises(
                MODULE.ActivationError
            ) as caught:
                MODULE.validate_record_schema(document)
            self.assertIsNone(caught.exception.__cause__)
            self.assertIn("unexpected_count=1", str(caught.exception))
            self.assertNotIn(canary, str(caught.exception))

            with self.subTest(scope=scope, surface="cli"), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                record_path = root / "activation.json"
                assets = root / "assets"
                assets.mkdir()
                record_path.write_text(json.dumps(document), encoding="utf-8")
                process = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--record",
                        str(record_path),
                        "--release-assets-dir",
                        str(assets),
                        "--repository-root",
                        str(REPOSITORY_ROOT),
                    ],
                    cwd=REPOSITORY_ROOT,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            self.assertEqual(2, process.returncode)
            self.assertIn("missing_count=0", process.stderr)
            self.assertIn("unexpected_count=1", process.stderr)
            self.assertNotIn(canary, process.stdout + process.stderr)
            self.assertNotIn(
                "CANARY_PRIVATE_SCHEMA_VALUE", process.stdout + process.stderr
            )

    def test_derives_version_specific_issue_form_for_rc1_and_rc2(self) -> None:
        for tag, filename in (
            ("v0.1.0-rc1", "independent-rc1-install.yml"),
            ("v0.1.0-rc2", "independent-rc2-install.yml"),
        ):
            with self.subTest(tag=tag):
                record = MODULE.validate_record_schema(valid_document(tag=tag))
                self.assertEqual(filename, record.issue_form_filename)
                self.assertEqual(filename, record.document["issueFormFilename"])
                self.assertTrue(record.document["issueFormPermalink"].endswith(filename))
                self.assertEqual(
                    f"{MODULE.REPOSITORY}/issues/new?template={filename}",
                    record.document["issueFormUrl"],
                )

    def test_template_is_json_but_cannot_activate(self) -> None:
        template = (
            REPOSITORY_ROOT
            / "docs/evidence/independent-rc-activation.example.json"
        )
        document = json.loads(template.read_text(encoding="utf-8"))
        self.assertEqual(0, document["releaseEvidence"]["artifactId"])
        self.assertEqual(0, document["releaseEvidence"]["runId"])
        self.assertEqual(2, document["schemaVersion"])
        self.assertIs(False, document["releaseImmutability"]["enforcedByOwner"])
        self.assertEqual(
            "[[WORKFLOW_ARTIFACT_SHA256_WITH_SHA256_PREFIX]]",
            document["releaseEvidence"]["artifactDigest"],
        )
        with self.assertRaisesRegex(MODULE.ActivationError, "unresolved"):
            MODULE.load_record(template)

    def test_template_materializes_to_valid_rc1_and_current_rc2_schema(self) -> None:
        template = (
            REPOSITORY_ROOT
            / "docs/evidence/independent-rc-activation.example.json"
        ).read_text(encoding="utf-8")
        for tag in ("v0.1.0-rc1", "v0.1.0-rc2"):
            with self.subTest(tag=tag):
                rendered = template
                for placeholder, value in (
                    ("[[STRICT_RC_TAG]]", tag),
                    ("[[RC_VERSION_WITHOUT_V]]", tag[1:]),
                    (
                        "[[VERSION_DERIVED_ISSUE_FORM_FILENAME]]",
                        MODULE.expected_issue_form_filename(tag),
                    ),
                    ("[[TAG_COMMIT_40_HEX]]", TAG_COMMIT),
                    (
                        "[[WORKFLOW_ARTIFACT_SHA256_WITH_SHA256_PREFIX]]",
                        ARTIFACT_DIGEST,
                    ),
                    ("[[POSITIVE_RELEASE_EVIDENCE_RUN_ID]]", "13579"),
                    ("[[SHA256SUMS_SHA256]]", SHA256SUMS_DIGEST),
                ):
                    rendered = rendered.replace(placeholder, value)
                document = json.loads(rendered)
                document["releaseEvidence"]["artifactId"] = 24680
                document["releaseEvidence"]["runId"] = 13579
                record = MODULE.validate_record_schema(document)
                self.assertEqual(tag, record.tag)
                self.assertNotIn("[[", rendered)

    def test_rejects_non_rc_placeholder_and_mismatched_identity(self) -> None:
        mutations = (
            ("rc0", lambda value: value.__setitem__("tag", "v0.1.0-rc0")),
            ("snapshot", lambda value: value.__setitem__("tag", "v0.1.0-SNAPSHOT")),
            ("stable", lambda value: value.__setitem__("tag", "v0.1.0")),
            ("leading zero", lambda value: value.__setitem__("tag", "v0.01.0-rc1")),
            ("old schema", lambda value: value.__setitem__("schemaVersion", 1)),
            ("zero commit", lambda value: value.__setitem__("tagCommit", "0" * 40)),
            (
                "wrong release URL",
                lambda value: value.__setitem__(
                    "releaseUrl", f"{MODULE.REPOSITORY}/releases/tag/v0.1.0-rc2"
                ),
            ),
            (
                "generic issue form filename",
                lambda value: value.__setitem__(
                    "issueFormFilename", "independent-rc-install.yml"
                ),
            ),
            (
                "wrong RC issue form permalink",
                lambda value: value.__setitem__(
                    "issueFormPermalink",
                    f"{MODULE.REPOSITORY}/blob/{TAG_COMMIT}/.github/ISSUE_TEMPLATE/"
                    "independent-rc2-install.yml",
                ),
            ),
            (
                "wrong RC interactive form URL",
                lambda value: value.__setitem__(
                    "issueFormUrl",
                    f"{MODULE.REPOSITORY}/issues/new?template=independent-rc2-install.yml",
                ),
            ),
            (
                "wrong head",
                lambda value: value["releaseEvidence"].__setitem__(
                    "headSha", "d" * 40
                ),
            ),
            (
                "string run id",
                lambda value: value["releaseEvidence"].__setitem__("runId", "13579"),
            ),
            (
                "mutable",
                lambda value: value["releaseState"].__setitem__("immutable", False),
            ),
            (
                "draft",
                lambda value: value["releaseState"].__setitem__("draft", True),
            ),
            (
                "disabled",
                lambda value: value["releaseImmutability"].__setitem__(
                    "enabled", False
                ),
            ),
            (
                "asset reorder",
                lambda value: value["publicAssets"].reverse(),
            ),
            ("extra key", lambda value: value.__setitem__("claim", "pass")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                value = valid_document()
                mutate(value)
                with self.assertRaises(MODULE.ActivationError):
                    MODULE.validate_record_schema(value)

    def test_rejects_duplicate_keys_and_non_regular_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"tag":"one","tag":"two"}\n', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.ActivationError, "strict UTF-8 JSON"):
                MODULE.load_record(duplicate)

            directory = root / "directory.json"
            directory.mkdir()
            with self.assertRaisesRegex(MODULE.ActivationError, "regular file"):
                MODULE.load_record(directory)


class ActivationStrictJsonDecoderTest(unittest.TestCase):
    @staticmethod
    def nested_payload(kind: str, depth: int) -> bytes:
        value = "0"
        for index in range(depth):
            if kind == "array" or (kind == "mixed" and index % 2 == 0):
                value = f"[{value}]"
            else:
                value = f'{{"level":{value}}}'
        return value.encode("utf-8")

    @staticmethod
    def node_payload(kind: str, node_count: int) -> bytes:
        if node_count < 1:
            raise AssertionError("node_count must include one root node")
        if kind == "array":
            value: object = [0] * (node_count - 1)
        elif kind == "object":
            value = {f"k{index}": 0 for index in range(node_count - 1)}
        elif kind == "mixed":
            if node_count < 3:
                raise AssertionError("mixed JSON needs a list, object, and scalar")
            value = [{"nested": 0}, *([0] * (node_count - 3))]
        else:  # pragma: no cover - test helper precondition
            raise AssertionError(f"unknown JSON shape: {kind}")
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    def test_accepts_valid_strict_utf8_activation_record(self) -> None:
        self.assertEqual(64, MODULE.MAX_JSON_NESTING_DEPTH)
        self.assertEqual(100_000, MODULE.MAX_JSON_NODE_COUNT)
        self.assertEqual(1_000, MODULE.MAX_JSON_INTEGER_DIGITS)
        self.assertEqual(8 * 1024 * 1024, MODULE.MAX_GITHUB_JSON_BYTES)
        encoded = json.dumps(valid_document(), separators=(",", ":")).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "activation.json"
            path.write_bytes(encoded)
            raw, document = MODULE.load_record(path)
        self.assertEqual(encoded, raw)
        self.assertEqual(TAG, MODULE.validate_record_schema(document).tag)

    def test_integer_digit_and_encoded_byte_boundaries_are_exact(self) -> None:
        maximum_integer = b"9" * MODULE.MAX_JSON_INTEGER_DIGITS
        parsed = MODULE._decode_strict_json(b'{"value":' + maximum_integer + b"}")
        self.assertEqual(int(maximum_integer), parsed["value"])
        with self.assertRaisesRegex(
            ValueError, "strict JSON validation failed"
        ) as caught:
            MODULE._decode_strict_json(
                b'{"value":' + maximum_integer + b"9}"
            )
        self.assertIsNone(caught.exception.__cause__)

    def test_activation_record_file_size_boundary_is_exactly_one_mibibyte(
        self,
    ) -> None:
        accepted = b"{}" + b" " * (MODULE.MAX_RECORD_BYTES - 2)
        rejected = accepted + b" "
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "activation.json"
            path.write_bytes(accepted)
            raw, document = MODULE.load_record(path)
            self.assertEqual(accepted, raw)
            self.assertEqual({}, document)

            path.write_bytes(rejected)
            with self.assertRaisesRegex(
                MODULE.ActivationError, "1 MiB safety limit"
            ) as caught:
                MODULE.load_record(path)
            self.assertIsNone(caught.exception.__cause__)

        encoded = b'{"ok":true}'
        self.assertEqual(
            {"ok": True},
            MODULE._decode_strict_json(encoded, maximum_bytes=len(encoded)),
        )
        with self.assertRaisesRegex(
            ValueError, "strict JSON validation failed"
        ) as caught:
            MODULE._decode_strict_json(encoded, maximum_bytes=len(encoded) - 1)
        self.assertIsNone(caught.exception.__cause__)

    def test_rejects_duplicate_nonfinite_overflow_huge_integer_and_encoding_generically(
        self,
    ) -> None:
        canary_key = "CANARY_PRIVATE_DUPLICATE_KEY"
        canary_value = "CANARY_PRIVATE_DUPLICATE_VALUE"
        malformed = (
            f'{{"{canary_key}":"{canary_value}","{canary_key}":0}}'.encode(),
            f'{{"outer":{{"{canary_key}":1,"{canary_key}":2}}}}'.encode(),
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b'{"value":-Infinity}',
            b'{"value":1e999}',
            b'{"value":' + (b"9" * 5_000) + b"}",
            b'{"value":"\xff"}',
            '{"value":1}'.encode("utf-16"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "activation.json"
            for raw in malformed:
                path.write_bytes(raw)
                with self.subTest(raw_prefix=raw[:24]), self.assertRaisesRegex(
                    MODULE.ActivationError, "strict UTF-8 JSON"
                ) as caught:
                    MODULE.load_record(path)
                self.assertIsNone(caught.exception.__cause__)
                self.assertNotIn(canary_key, str(caught.exception))
                self.assertNotIn(canary_value, str(caught.exception))

    def test_nesting_depth_boundary_for_arrays_objects_and_mixed_trees(self) -> None:
        for kind in ("array", "object", "mixed"):
            with self.subTest(kind=kind, boundary="max"):
                MODULE._decode_strict_json(
                    self.nested_payload(kind, MODULE.MAX_JSON_NESTING_DEPTH)
                )
            with self.subTest(kind=kind, boundary="max-plus-one"), self.assertRaisesRegex(
                ValueError, "strict JSON validation failed"
            ) as caught:
                MODULE._decode_strict_json(
                    self.nested_payload(kind, MODULE.MAX_JSON_NESTING_DEPTH + 1)
                )
            self.assertIsNone(caught.exception.__cause__)

    def test_node_count_boundary_for_arrays_objects_and_mixed_trees(self) -> None:
        for kind in ("array", "object", "mixed"):
            with self.subTest(kind=kind, boundary="max"):
                MODULE._decode_strict_json(
                    self.node_payload(kind, MODULE.MAX_JSON_NODE_COUNT)
                )
            with self.subTest(kind=kind, boundary="max-plus-one"), self.assertRaisesRegex(
                ValueError, "strict JSON validation failed"
            ) as caught:
                MODULE._decode_strict_json(
                    self.node_payload(kind, MODULE.MAX_JSON_NODE_COUNT + 1)
                )
            self.assertIsNone(caught.exception.__cause__)

    def test_deep_1050_and_1200_inputs_fail_without_recursion_details(self) -> None:
        cases = (
            ("array", 1_050),
            ("object", 1_050),
            ("mixed", 1_200),
        )
        for kind, depth in cases:
            with self.subTest(kind=kind, depth=depth), self.assertRaisesRegex(
                ValueError, "strict JSON validation failed"
            ) as caught:
                MODULE._decode_strict_json(self.nested_payload(kind, depth))
            self.assertIsNone(caught.exception.__cause__)
            self.assertNotIn("recursion", str(caught.exception).lower())

    def test_budget_failure_precedes_placeholder_tree_walk(self) -> None:
        over_budget = self.nested_payload(
            "object", MODULE.MAX_JSON_NESTING_DEPTH + 1
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "activation.json"
            path.write_bytes(over_budget)
            with mock.patch.object(MODULE, "_contains_placeholder") as walker:
                with self.assertRaisesRegex(
                    MODULE.ActivationError, "strict UTF-8 JSON"
                ):
                    MODULE.load_record(path)
            walker.assert_not_called()

    def test_duplicate_canary_is_not_echoed_by_cli_or_exception_chain(self) -> None:
        canary_key = "CANARY_PRIVATE_DUPLICATE_KEY"
        canary_value = "CANARY_PRIVATE_DUPLICATE_VALUE"
        raw = (
            f'{{"{canary_key}":"{canary_value}",'
            f'"{canary_key}":"SECOND_PRIVATE_VALUE"}}'
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "activation.json"
            assets = root / "assets"
            assets.mkdir()
            path.write_bytes(raw)
            with self.assertRaises(MODULE.ActivationError) as caught:
                MODULE.load_record(path)
            self.assertIsNone(caught.exception.__cause__)

            process = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--record",
                    str(path),
                    "--release-assets-dir",
                    str(assets),
                    "--repository-root",
                    str(REPOSITORY_ROOT),
                ],
                cwd=REPOSITORY_ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        self.assertEqual(2, process.returncode)
        self.assertIn("RC_ACTIVATION_NO_GO", process.stderr)
        self.assertNotIn("Traceback", process.stderr)
        for secret in (canary_key, canary_value, "SECOND_PRIVATE_VALUE"):
            self.assertNotIn(secret, str(caught.exception))
            self.assertNotIn(secret, process.stdout)
            self.assertNotIn(secret, process.stderr)


class ActivationAssetSetTest(unittest.TestCase):
    def create_assets(self, root: Path) -> tuple[dict[str, object], MODULE.ValidatedRecord]:
        return create_asset_set(root)

    def test_accepts_exact_flat_checksums_and_own_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, record = self.create_assets(root)
            digests = MODULE.validate_asset_directory(root, record)
            self.assertEqual(set(record.public_assets), set(digests))

    def test_fails_closed_on_missing_extra_reordered_or_mutated_assets(self) -> None:
        cases = ("missing", "extra", "reordered", "mutated", "wrong-own-digest")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                document, record = self.create_assets(root)
                if case == "missing":
                    (root / record.payloads[0]).unlink()
                elif case == "extra":
                    (root / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
                elif case == "reordered":
                    lines = (root / "SHA256SUMS").read_text(encoding="ascii").splitlines(True)
                    (root / "SHA256SUMS").write_text(
                        "".join(reversed(lines)), encoding="ascii"
                    )
                elif case == "mutated":
                    (root / record.payloads[0]).write_text("mutated\n", encoding="utf-8")
                else:
                    document["sha256sumsSha256"] = "e" * 64
                    record = MODULE.validate_record_schema(document)
                with self.assertRaises(MODULE.ActivationError):
                    MODULE.validate_asset_directory(root, record)

    def test_requires_absolute_real_directory(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        with self.assertRaisesRegex(MODULE.ActivationError, "explicit absolute"):
            MODULE.validate_asset_directory(Path("relative-assets"), record)


class ActivationLocalRepositoryTest(unittest.TestCase):
    common_required_tagged_paths = (
        ".github/workflows/release-evidence.yml",
        "README.md",
        "NOTICE",
        "build.gradle",
        "docs/independent-install-study.md",
        "docs/evidence/independent-rc-activation.example.json",
        "scripts/gh_cli_release_safety.py",
        "scripts/validate-rc-activation-record.py",
        "scripts/install-release-assets.py",
    )

    def create_repository(
        self,
        root: Path,
        *,
        tag: str = TAG,
        extra_record_change: bool = False,
        tagged_gitmodules: bool = False,
        tagged_symlink: bool = False,
        derived_form_kind: str = "file",
    ) -> tuple[Path, bytes, MODULE.ValidatedRecord, str]:
        git(root, "init", "--initial-branch=main")
        git(root, "config", "user.name", "Activation Test")
        git(root, "config", "user.email", "activation-test@example.invalid")
        required_paths = list(self.common_required_tagged_paths)
        for name in required_paths:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture {name}\n", encoding="utf-8")
        issue_form_path = (
            root
            / ".github/ISSUE_TEMPLATE"
            / MODULE.expected_issue_form_filename(tag)
        )
        issue_form_path.parent.mkdir(parents=True, exist_ok=True)
        if derived_form_kind == "file":
            issue_form_path.write_text("fixture Issue Form\n", encoding="utf-8")
        elif derived_form_kind == "tree":
            issue_form_path.mkdir()
            (issue_form_path / "not-a-form.txt").write_text(
                "not an Issue Form\n", encoding="utf-8"
            )
        elif derived_form_kind == "symlink":
            issue_form_path.symlink_to("../../README.md")
        elif derived_form_kind == "executable":
            issue_form_path.write_text("fixture Issue Form\n", encoding="utf-8")
            issue_form_path.chmod(0o755)
        elif derived_form_kind != "missing":
            raise AssertionError(f"unsupported derived form fixture: {derived_form_kind}")
        if tagged_gitmodules:
            (root / ".gitmodules").write_text(
                "[submodule \"fixture\"]\n\tpath = fixture\n\turl = https://example.invalid\n",
                encoding="utf-8",
            )
        if tagged_symlink:
            (root / "tagged-link").symlink_to("README.md")
        git(root, "add", ".")
        git(root, "commit", "-m", "tagged candidate")
        tag_commit = git(root, "rev-parse", "HEAD")
        git(root, "tag", "-a", tag, "-m", "candidate")

        document = valid_document(tag=tag, tag_commit=tag_commit)
        record = MODULE.validate_record_schema(document)
        raw = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
        path = root / f"docs/evidence/independent-rc-activation-{tag}.json"
        path.write_bytes(raw)
        git(root, "add", path.relative_to(root).as_posix())
        if extra_record_change:
            (root / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
            git(root, "add", "unexpected.txt")
        git(root, "commit", "-m", "record activation")
        return path, raw, record, git(root, "rev-parse", "HEAD")

    def test_accepts_exact_direct_child_single_record_commit(self) -> None:
        for tag in ("v0.1.0-rc1", "v0.1.0-rc2"):
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path, raw, record, record_commit = self.create_repository(root, tag=tag)
                with mock.patch.object(
                    MODULE,
                    "__file__",
                    str(root / "scripts/validate-rc-activation-record.py"),
                ):
                    actual = MODULE.validate_local_repository(root, path, raw, record)
                self.assertEqual(record_commit, actual)

    def test_rejects_invalid_repository_or_version_derived_form_shape(self) -> None:
        cases = (
            "extra",
            "later-head",
            "gitmodules",
            "symlink",
            "missing-form",
            "form-tree",
            "form-symlink",
            "form-executable",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path, raw, record, _record_commit = self.create_repository(
                    root,
                    extra_record_change=case == "extra",
                    tagged_gitmodules=case == "gitmodules",
                    tagged_symlink=case == "symlink",
                    derived_form_kind={
                        "missing-form": "missing",
                        "form-tree": "tree",
                        "form-symlink": "symlink",
                        "form-executable": "executable",
                    }.get(case, "file"),
                )
                if case == "later-head":
                    (root / "later.txt").write_text("later\n", encoding="utf-8")
                    git(root, "add", "later.txt")
                    git(root, "commit", "-m", "advance main")
                with (
                    mock.patch.object(
                        MODULE,
                        "__file__",
                        str(root / "scripts/validate-rc-activation-record.py"),
                    ),
                    self.assertRaises(MODULE.ActivationError),
                ):
                    MODULE.validate_local_repository(root, path, raw, record)


class ActivationWorkflowArtifactTest(unittest.TestCase):
    def write_artifact(
        self,
        path: Path,
        assets: Path,
        record: MODULE.ValidatedRecord,
        *,
        omit: str | None = None,
        mutate: str | None = None,
        extra: str | None = None,
        duplicate: str | None = None,
        symlink: str | None = None,
    ) -> None:
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            for name in record.public_assets:
                if name == omit:
                    continue
                content = (assets / name).read_bytes()
                if name == mutate:
                    content += b"artifact-only mutation\n"
                archive.writestr(name, content)
            for name in MODULE.WORKFLOW_ONLY_FILES:
                if name != omit:
                    archive.writestr(name, f"workflow-only {name}\n".encode())
            if extra is not None:
                archive.writestr(extra, b"unexpected\n")
            if duplicate is not None:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(duplicate, (assets / duplicate).read_bytes())
            if symlink is not None:
                info = ZipInfo(symlink)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, b"target")

    def bound_record(
        self, document: dict[str, object], archive: Path
    ) -> MODULE.ValidatedRecord:
        updated = copy.deepcopy(document)
        updated["releaseEvidence"]["artifactDigest"] = "sha256:" + MODULE.sha256(
            archive
        )
        return MODULE.validate_record_schema(updated)

    def test_exact_artifact_binds_all_twelve_release_assets_and_five_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            document, initial = create_asset_set(assets)
            archive = root / "artifact.zip"
            self.write_artifact(archive, assets, initial)
            record = self.bound_record(document, archive)
            local_digests = MODULE.validate_asset_directory(assets, record)

            members = MODULE.validate_workflow_artifact_archive(
                archive, record, local_digests
            )

        self.assertEqual(
            set(record.public_assets) | set(MODULE.WORKFLOW_ONLY_FILES),
            set(members),
        )
        self.assertEqual(MODULE.EXPECTED_ARTIFACT_FILE_COUNT, len(members))

    def test_rejects_missing_extra_duplicate_traversal_symlink_and_public_mutation(self) -> None:
        cases = (
            ("missing", {"omit": "environment.txt"}),
            ("extra", {"extra": "unexpected.txt"}),
            ("nested wrapper", {"extra": "wrapper/environment.txt"}),
            ("traversal", {"extra": "../environment.txt"}),
            (
                "duplicate",
                {"duplicate": MODULE.expected_public_assets(VERSION)[0]},
            ),
            ("symlink", {"omit": "environment.txt", "symlink": "environment.txt"}),
            (
                "public mutation",
                {"mutate": MODULE.expected_public_assets(VERSION)[0]},
            ),
        )
        for label, options in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                assets = root / "assets"
                assets.mkdir()
                document, initial = create_asset_set(assets)
                archive = root / "artifact.zip"
                self.write_artifact(archive, assets, initial, **options)
                record = self.bound_record(document, archive)
                local_digests = MODULE.validate_asset_directory(assets, record)
                with self.assertRaises(MODULE.ActivationError):
                    MODULE.validate_workflow_artifact_archive(
                        archive, record, local_digests
                    )

    def test_rejects_archive_digest_mismatch_and_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            _, record = create_asset_set(assets)
            archive = root / "artifact.zip"
            self.write_artifact(archive, assets, record)
            local_digests = MODULE.validate_asset_directory(assets, record)
            with self.assertRaisesRegex(MODULE.ActivationError, "digest"):
                MODULE.validate_workflow_artifact_archive(
                    archive, record, local_digests
                )

            link = root / "artifact-link.zip"
            link.symlink_to(archive)
            with self.assertRaisesRegex(MODULE.ActivationError, "regular ZIP"):
                MODULE.validate_workflow_artifact_archive(
                    link, record, local_digests
                )


class ActivationPublicMetadataTest(unittest.TestCase):
    def metadata_fixture(
        self, record: MODULE.ValidatedRecord, raw_record: bytes, record_commit: str
    ) -> dict[str, object]:
        evidence = record.document["releaseEvidence"]
        asset_digests = {name: "1" * 64 for name in record.public_assets}
        record_path = f"docs/evidence/independent-rc-activation-{record.tag}.json"
        encoded = base64.b64encode(raw_record).decode("ascii")
        encoded_with_lines = "\n".join(
            encoded[index : index + 20] for index in range(0, len(encoded), 20)
        )
        tag_object = "9" * 40
        pull_number = 88
        pull = {
            "id": 8_800,
            "node_id": "PR_kwDOActivation88",
            "number": pull_number,
            "html_url": f"{MODULE.REPOSITORY}/pull/{pull_number}",
            "state": "closed",
            "merged_at": "2026-07-20T05:00:00Z",
            "merge_commit_sha": record_commit,
            "base": {
                "ref": "main",
                "repo": {"full_name": MODULE.REPOSITORY_SLUG},
            },
        }
        return {
            f"repos/{MODULE.REPOSITORY_SLUG}": {
                "id": 123_456,
                "node_id": "R_kgDORouteContract",
                "full_name": MODULE.REPOSITORY_SLUG,
                "html_url": MODULE.REPOSITORY,
                "default_branch": "main",
                "private": False,
                "archived": False,
                "disabled": False,
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record.tag_commit}": {
                "sha": record.tag_commit
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}": {
                "sha": record_commit,
                "commit": {
                    "author": {"date": "2026-07-20T04:30:00Z"},
                    "committer": {"date": "2026-07-20T04:31:00Z"},
                },
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/git/ref/tags/{record.tag}": {
                "ref": f"refs/tags/{record.tag}",
                "object": {"type": "tag", "sha": tag_object},
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/git/tags/{tag_object}": {
                "sha": tag_object,
                "tag": record.tag,
                "object": {"type": "commit", "sha": record.tag_commit},
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/branches/main": {
                "name": "main",
                "commit": {"sha": record_commit},
            },
            (
                f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}/"
                "pulls?per_page=100"
            ): [copy.deepcopy(pull)],
            f"repos/{MODULE.REPOSITORY_SLUG}/pulls/{pull_number}": {
                **copy.deepcopy(pull),
                "merged": True,
            },
            f"graphql:pull/{pull_number}": {
                "data": {
                    "repository": {
                        "id": "R_kgDORouteContract",
                        "nameWithOwner": MODULE.REPOSITORY_SLUG,
                        "pullRequest": {
                            "id": pull["node_id"],
                            "databaseId": pull["id"],
                            "number": pull_number,
                            "url": pull["html_url"],
                            "state": "MERGED",
                            "merged": True,
                            "mergedAt": pull["merged_at"],
                            "baseRefName": "main",
                            "baseRepository": {
                                "id": "R_kgDORouteContract",
                                "nameWithOwner": MODULE.REPOSITORY_SLUG,
                            },
                            "mergeCommit": {"oid": record_commit},
                        },
                    }
                }
            },
            (
                f"repos/{MODULE.REPOSITORY_SLUG}/contents/{record_path}"
                f"?ref={record_commit}"
            ): {
                "type": "file",
                "encoding": "base64",
                "content": encoded_with_lines,
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/actions/runs/{record.run_id}": {
                "id": record.run_id,
                "html_url": evidence["runUrl"],
                "head_sha": record.tag_commit,
                "head_branch": record.tag,
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "name": MODULE.EXPECTED_WORKFLOW_NAME,
                "path": MODULE.EXPECTED_WORKFLOW_PATH,
                "repository": {"full_name": MODULE.REPOSITORY_SLUG},
                "created_at": "2026-07-20T02:00:00Z",
                "updated_at": "2026-07-20T02:30:00Z",
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/actions/artifacts/{record.artifact_id}": {
                "id": record.artifact_id,
                "name": f"routecontract-release-evidence-{record.tag_commit}",
                "digest": evidence["artifactDigest"],
                "expired": False,
                "size_in_bytes": 123456,
                "created_at": "2026-07-20T02:31:00Z",
                "updated_at": "2026-07-20T02:32:00Z",
                "workflow_run": {
                    "id": record.run_id,
                    "head_sha": record.tag_commit,
                    "head_branch": record.tag,
                },
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/releases/tags/{record.tag}": {
                "tag_name": record.tag,
                "html_url": record.document["releaseUrl"],
                "draft": False,
                "prerelease": True,
                "immutable": True,
                "created_at": "2026-07-20T03:00:00Z",
                "published_at": "2026-07-20T04:00:00Z",
                "updated_at": "2026-07-20T04:05:00Z",
                "assets": [
                    {
                        "id": 5000 + index,
                        "name": name,
                        "state": "uploaded",
                        "size": index + 1,
                        "digest": f"sha256:{asset_digests[name]}",
                        "url": (
                            f"https://api.github.com/repos/{MODULE.REPOSITORY_SLUG}/"
                            f"releases/assets/{5000 + index}"
                        ),
                        "browser_download_url": (
                            f"{MODULE.REPOSITORY}/releases/download/{record.tag}/{name}"
                        ),
                        "created_at": "2026-07-20T03:30:00Z",
                        "updated_at": "2026-07-20T03:40:00Z",
                    }
                    for index, name in enumerate(record.public_assets)
                ],
            },
            f"repos/{MODULE.REPOSITORY_SLUG}/immutable-releases": {
                "enabled": True,
                "enforced_by_owner": False,
            },
        }

    def invoke(
        self,
        root: Path,
        record_path: Path,
        raw_record: bytes,
        record_commit: str,
        record: MODULE.ValidatedRecord,
        fixture: dict[str, object],
    ) -> tuple[list[str], MODULE.PublicMetadata]:
        calls: list[str] = []

        def response(_gh: str, _root: Path, endpoint: str) -> dict[str, object]:
            calls.append(endpoint)
            value = copy.deepcopy(fixture[endpoint])
            if not isinstance(value, dict):
                raise AssertionError(f"expected object fixture for {endpoint}")
            return value

        def response_list(
            _gh: str, _root: Path, endpoint: str
        ) -> list[dict[str, object]]:
            calls.append(endpoint)
            value = copy.deepcopy(fixture[endpoint])
            if not isinstance(value, list) or any(
                not isinstance(item, dict) for item in value
            ):
                raise AssertionError(f"expected object-list fixture for {endpoint}")
            return value

        def response_graphql(
            _gh: str, _root: Path, pull_number: int
        ) -> dict[str, object]:
            key = f"graphql:pull/{pull_number}"
            calls.append(key)
            value = copy.deepcopy(fixture[key])
            if not isinstance(value, dict):
                raise AssertionError(f"expected GraphQL fixture for {key}")
            return value

        with (
            mock.patch.object(MODULE, "_gh_json", side_effect=response),
            mock.patch.object(MODULE, "_gh_json_list", side_effect=response_list),
            mock.patch.object(
                MODULE, "_gh_graphql_activation_pull", side_effect=response_graphql
            ),
            mock.patch.object(MODULE, "_git", return_value="9" * 40 + "\n"),
        ):
            metadata = MODULE.validate_public_metadata(
                "/safe/gh",
                root,
                record_path,
                raw_record,
                record_commit,
                record,
                {name: "1" * 64 for name in record.public_assets},
            )
        return calls, metadata

    def test_accepts_exact_api_fixture_and_queries_only_derived_endpoints(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record_path = (
                root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
            )
            record_path.parent.mkdir(parents=True)
            record_path.write_bytes(raw_record)
            fixture = self.metadata_fixture(record, raw_record, record_commit)
            calls, metadata = self.invoke(
                root, record_path, raw_record, record_commit, record, fixture
            )
        self.assertEqual(set(fixture), set(calls))
        self.assertEqual(len(fixture), len(calls))
        self.assertEqual(123456, metadata.artifact_size)
        self.assertEqual(
            tuple(
                (name, 5000 + index, index + 1)
                for index, name in enumerate(record.public_assets)
            ),
            metadata.release_assets,
        )

    def test_accepts_null_association_merge_sha_only_when_direct_pull_is_exact(
        self,
    ) -> None:
        """The commit/pulls summary may omit the squash SHA for a public repository."""
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()
        pull_list_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}/"
            "pulls?per_page=100"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record_path = (
                root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
            )
            record_path.parent.mkdir(parents=True)
            record_path.write_bytes(raw_record)
            fixture = self.metadata_fixture(record, raw_record, record_commit)
            fixture[pull_list_endpoint][0]["merge_commit_sha"] = None
            _, metadata = self.invoke(
                root, record_path, raw_record, record_commit, record, fixture
            )

        self.assertEqual(123456, metadata.artifact_size)

    def test_accepts_null_direct_merge_sha_only_when_association_is_exact(
        self,
    ) -> None:
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()
        pull_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/pulls/88"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record_path = (
                root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
            )
            record_path.parent.mkdir(parents=True)
            record_path.write_bytes(raw_record)
            fixture = self.metadata_fixture(record, raw_record, record_commit)
            fixture[pull_endpoint]["merge_commit_sha"] = None
            _, metadata = self.invoke(
                root, record_path, raw_record, record_commit, record, fixture
            )

        self.assertEqual(123456, metadata.artifact_size)

    def test_accepts_both_rest_merge_shas_null_when_graphql_is_exact(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()
        pull_list_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}/"
            "pulls?per_page=100"
        )
        pull_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/pulls/88"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record_path = (
                root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
            )
            record_path.parent.mkdir(parents=True)
            record_path.write_bytes(raw_record)
            fixture = self.metadata_fixture(record, raw_record, record_commit)
            fixture[pull_list_endpoint][0]["merge_commit_sha"] = None
            fixture[pull_endpoint]["merge_commit_sha"] = None
            _, metadata = self.invoke(
                root, record_path, raw_record, record_commit, record, fixture
            )

        self.assertEqual(123456, metadata.artifact_size)

    def test_rejects_missing_rest_merge_sha_keys(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()
        pull_list_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}/"
            "pulls?per_page=100"
        )
        pull_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/pulls/88"

        for surface in ("associated", "direct"):
            with self.subTest(surface=surface), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                record_path = (
                    root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
                )
                record_path.parent.mkdir(parents=True)
                record_path.write_bytes(raw_record)
                fixture = self.metadata_fixture(record, raw_record, record_commit)
                target = (
                    fixture[pull_list_endpoint][0]
                    if surface == "associated"
                    else fixture[pull_endpoint]
                )
                target.pop("merge_commit_sha")
                with self.assertRaises(MODULE.ActivationError):
                    self.invoke(
                        root, record_path, raw_record, record_commit, record, fixture
                    )

    def test_rejects_noninteger_rest_and_graphql_identities(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()
        repo_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}"
        pull_list_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}/"
            "pulls?per_page=100"
        )
        pull_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/pulls/88"
        pull_path = ("data", "repository", "pullRequest")

        def reject(mutator) -> None:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                record_path = (
                    root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
                )
                record_path.parent.mkdir(parents=True)
                record_path.write_bytes(raw_record)
                fixture = self.metadata_fixture(record, raw_record, record_commit)
                mutator(fixture)
                with self.assertRaises(MODULE.ActivationError):
                    self.invoke(
                        root, record_path, raw_record, record_commit, record, fixture
                    )

        for value in (True, 1.0, 0, -1):
            with self.subTest(surface="repository", value=value):
                reject(lambda fixture, value=value: fixture[repo_endpoint].__setitem__("id", value))
            for surface, endpoint in (
                ("associated", pull_list_endpoint),
                ("direct", pull_endpoint),
            ):
                for field in ("id", "number"):
                    with self.subTest(surface=surface, field=field, value=value):
                        reject(
                            lambda fixture, endpoint=endpoint, surface=surface,
                            field=field, value=value: (
                                fixture[endpoint][0].__setitem__(field, value)
                                if surface == "associated"
                                else fixture[endpoint].__setitem__(field, value)
                            )
                        )
            for field in ("databaseId", "number"):
                with self.subTest(surface="graphql", field=field, value=value):
                    reject(
                        lambda fixture, field=field, value=value: fixture[
                            "graphql:pull/88"
                        ]["data"]["repository"]["pullRequest"].__setitem__(
                            field, value
                        )
                    )

        strict_graphql_cases = (
            ((*pull_path, "merged"), 1),
            ((*pull_path, "id"), 1),
            ((*pull_path, "url"), 88),
            ((*pull_path, "state"), 1),
            ((*pull_path, "mergedAt"), 1),
            ((*pull_path, "baseRefName"), 1),
            (("data", "repository", "id"), 1),
            (("data", "repository", "nameWithOwner"), 1),
            ((*pull_path, "baseRepository", "id"), 1),
            ((*pull_path, "baseRepository", "nameWithOwner"), 1),
            ((*pull_path, "mergeCommit", "oid"), 1),
        )
        for path, value in strict_graphql_cases:
            def mutate(fixture, path=path, value=value) -> None:
                target = fixture["graphql:pull/88"]
                for component in path[:-1]:
                    target = target[component]
                target[path[-1]] = value

            with self.subTest(surface="graphql", path=path):
                reject(mutate)

    def test_rejects_activation_pull_association_drift_or_ambiguity(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()
        pull_list_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}/"
            "pulls?per_page=100"
        )
        pull_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/pulls/88"

        def mutate_direct(field: str, value):
            def mutate(fixture: dict[str, object]) -> None:
                fixture[pull_list_endpoint][0]["merge_commit_sha"] = None
                direct = fixture[pull_endpoint]
                if field == "base_ref":
                    direct["base"]["ref"] = value
                elif field == "base_repository":
                    direct["base"]["repo"]["full_name"] = value
                else:
                    direct[field] = value

            return mutate

        mutations = (
            ("list SHA drift", lambda fixture: fixture[pull_list_endpoint][0].__setitem__("merge_commit_sha", "8" * 40)),
            ("direct id drift", mutate_direct("id", 9999)),
            ("direct node drift", mutate_direct("node_id", "PR_drifted")),
            ("direct number drift", mutate_direct("number", 89)),
            ("direct URL drift", mutate_direct("html_url", f"{MODULE.REPOSITORY}/pull/89")),
            ("direct state drift", mutate_direct("state", "open")),
            ("direct merge drift", mutate_direct("merged", False)),
            ("direct time missing", mutate_direct("merged_at", None)),
            ("direct SHA drift", mutate_direct("merge_commit_sha", "8" * 40)),
            ("direct base drift", mutate_direct("base_ref", "next")),
            ("direct repository drift", mutate_direct("base_repository", "other/repo")),
            (
                "foreign listed repository",
                lambda fixture: fixture[pull_list_endpoint][0]["base"]["repo"].__setitem__(
                    "full_name", "other/repo"
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                record_path = (
                    root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
                )
                record_path.parent.mkdir(parents=True)
                record_path.write_bytes(raw_record)
                fixture = self.metadata_fixture(record, raw_record, record_commit)
                mutate(fixture)
                with self.assertRaises(MODULE.ActivationError):
                    self.invoke(
                        root, record_path, raw_record, record_commit, record, fixture
                    )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record_path = (
                root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
            )
            record_path.parent.mkdir(parents=True)
            record_path.write_bytes(raw_record)
            fixture = self.metadata_fixture(record, raw_record, record_commit)
            first = fixture[pull_list_endpoint][0]
            first["merge_commit_sha"] = None
            second = copy.deepcopy(first)
            second.update(
                {
                    "id": 8_900,
                    "node_id": "PR_kwDOActivation89",
                    "number": 89,
                    "html_url": f"{MODULE.REPOSITORY}/pull/89",
                }
            )
            fixture[pull_list_endpoint].append(second)
            fixture[f"repos/{MODULE.REPOSITORY_SLUG}/pulls/89"] = {
                **copy.deepcopy(second),
                "merged": True,
                "merge_commit_sha": record_commit,
            }
            graphql_second = copy.deepcopy(fixture["graphql:pull/88"])
            graphql_pull = graphql_second["data"]["repository"]["pullRequest"]
            graphql_pull.update(
                {
                    "id": second["node_id"],
                    "databaseId": second["id"],
                    "number": second["number"],
                    "url": second["html_url"],
                }
            )
            fixture["graphql:pull/89"] = graphql_second
            with self.assertRaises(MODULE.ActivationError):
                self.invoke(
                    root, record_path, raw_record, record_commit, record, fixture
                )

    def test_rejects_graphql_pull_partial_or_identity_drift(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()

        def mutate(path: tuple[str, ...], value):
            def apply(payload: dict) -> None:
                target = payload
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

            return apply

        pull_path = ("data", "repository", "pullRequest")
        cases = (
            (("data", "repository"), None),
            (("data", "unexpected"), {}),
            (("data", "repository", "unexpected"), True),
            (("data", "repository", "id"), "R_wrong"),
            (("data", "repository", "nameWithOwner"), "other/repo"),
            ((*pull_path, "id"), "PR_wrong"),
            ((*pull_path, "databaseId"), 9999),
            ((*pull_path, "number"), 89),
            ((*pull_path, "url"), f"{MODULE.REPOSITORY}/pull/89"),
            ((*pull_path, "state"), "CLOSED"),
            ((*pull_path, "merged"), False),
            ((*pull_path, "mergedAt"), None),
            ((*pull_path, "baseRefName"), "next"),
            ((*pull_path, "baseRepository", "id"), "R_wrong"),
            ((*pull_path, "baseRepository", "nameWithOwner"), "other/repo"),
            ((*pull_path, "mergeCommit"), None),
            ((*pull_path, "mergeCommit", "oid"), "8" * 40),
        )
        for path, value in cases:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                record_path = (
                    root
                    / f"docs/evidence/independent-rc-activation-{record.tag}.json"
                )
                record_path.parent.mkdir(parents=True)
                record_path.write_bytes(raw_record)
                fixture = self.metadata_fixture(record, raw_record, record_commit)
                mutate(path, value)(fixture["graphql:pull/88"])
                with self.assertRaises(MODULE.ActivationError):
                    self.invoke(
                        root,
                        record_path,
                        raw_record,
                        record_commit,
                        record,
                        fixture,
                    )

    def test_rejects_wrong_public_run_artifact_release_asset_or_setting(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        record_commit = "f" * 40
        raw_record = (json.dumps(record.document, sort_keys=True) + "\n").encode()
        run_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/actions/runs/{record.run_id}"
        artifact_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/actions/artifacts/{record.artifact_id}"
        )
        release_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/releases/tags/{record.tag}"
        )
        immutable_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/immutable-releases"
        repo_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}"
        main_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/branches/main"
        pull_list_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}/"
            "pulls?per_page=100"
        )
        pull_endpoint = f"repos/{MODULE.REPOSITORY_SLUG}/pulls/88"
        record_commit_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/commits/{record_commit}"
        )
        tag_ref_endpoint = (
            f"repos/{MODULE.REPOSITORY_SLUG}/git/ref/tags/{record.tag}"
        )
        def set_pull_time(value: dict[str, object], timestamp: str) -> None:
            value[pull_list_endpoint][0]["merged_at"] = timestamp
            value[pull_endpoint]["merged_at"] = timestamp

        mutations = (
            ("private repository", lambda value: value[repo_endpoint].__setitem__("private", True)),
            ("wrong default branch", lambda value: value[repo_endpoint].__setitem__("default_branch", "next")),
            ("wrong public main", lambda value: value[main_endpoint]["commit"].__setitem__("sha", "2" * 40)),
            ("direct push without pull", lambda value: value.__setitem__(pull_list_endpoint, [])),
            ("unmerged activation pull", lambda value: value[pull_endpoint].__setitem__("merged", False)),
            ("wrong activation pull base", lambda value: value[pull_endpoint]["base"].__setitem__("ref", "next")),
            ("activation pull before prerequisites", lambda value: set_pull_time(value, "2026-07-20T04:00:00Z")),
            ("record commit after merge", lambda value: value[record_commit_endpoint]["commit"]["committer"].__setitem__("date", "2026-07-20T05:01:00Z")),
            ("lightweight public tag", lambda value: value[tag_ref_endpoint]["object"].__setitem__("type", "commit")),
            ("failed run", lambda value: value[run_endpoint].__setitem__("conclusion", "failure")),
            ("wrong run head", lambda value: value[run_endpoint].__setitem__("head_sha", "2" * 40)),
            ("run updated after release", lambda value: value[run_endpoint].__setitem__("updated_at", "2026-07-20T04:30:00Z")),
            ("expired artifact", lambda value: value[artifact_endpoint].__setitem__("expired", True)),
            ("wrong artifact digest", lambda value: value[artifact_endpoint].__setitem__("digest", "sha256:" + "3" * 64)),
            ("draft release", lambda value: value[release_endpoint].__setitem__("draft", True)),
            ("mutable release", lambda value: value[release_endpoint].__setitem__("immutable", False)),
            ("reversed release time", lambda value: value[release_endpoint].__setitem__("published_at", "2026-07-20T02:00:00Z")),
            ("disabled setting", lambda value: value[immutable_endpoint].__setitem__("enabled", False)),
            (
                "wrong asset digest",
                lambda value: value[release_endpoint]["assets"][0].__setitem__(
                    "digest", "sha256:" + "4" * 64
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                record_path = (
                    root / f"docs/evidence/independent-rc-activation-{record.tag}.json"
                )
                record_path.parent.mkdir(parents=True)
                record_path.write_bytes(raw_record)
                fixture = self.metadata_fixture(record, raw_record, record_commit)
                mutate(fixture)
                with self.assertRaises(MODULE.ActivationError):
                    self.invoke(
                        root, record_path, raw_record, record_commit, record, fixture
                    )


class ActivationPublicByteDownloadTest(unittest.TestCase):
    def fixture(
        self, root: Path
    ) -> tuple[
        Path,
        Path,
        MODULE.ValidatedRecord,
        dict[str, str],
        MODULE.PublicMetadata,
    ]:
        assets = root / "assets"
        assets.mkdir()
        document, initial = create_asset_set(assets)
        artifact = root / "artifact.zip"
        ActivationWorkflowArtifactTest().write_artifact(
            artifact, assets, initial
        )
        document["releaseEvidence"]["artifactDigest"] = (
            "sha256:" + MODULE.sha256(artifact)
        )
        record = MODULE.validate_record_schema(document)
        digests = MODULE.validate_asset_directory(assets, record)
        metadata = MODULE.PublicMetadata(
            artifact_size=artifact.stat().st_size,
            release_assets=tuple(
                (name, 7000 + index, (assets / name).stat().st_size)
                for index, name in enumerate(record.public_assets)
            ),
        )
        return assets, artifact, record, digests, metadata

    def test_downloads_exact_artifact_and_release_endpoints_and_binds_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, artifact, record, digests, metadata = self.fixture(root)
            by_id = {
                asset_id: assets / name
                for name, asset_id, _size in metadata.release_assets
            }
            calls: list[tuple[str, int, str]] = []

            def download(
                _gh: str,
                _repository_root: Path,
                endpoint: str,
                destination: Path,
                expected_size: int,
                *,
                accept: str,
            ) -> None:
                calls.append((endpoint, expected_size, accept))
                if endpoint.endswith(f"/{record.artifact_id}/zip"):
                    source = artifact
                else:
                    source = by_id[int(endpoint.rsplit("/", 1)[1])]
                self.assertEqual(expected_size, source.stat().st_size)
                shutil.copyfile(source, destination)

            with mock.patch.object(MODULE, "_download_gh_file", side_effect=download):
                MODULE.download_and_validate_public_bytes(
                    "/safe/gh", root, assets, metadata, record, digests
                )

        self.assertEqual(13, len(calls))
        self.assertEqual(
            (
                f"repos/{MODULE.REPOSITORY_SLUG}/actions/artifacts/"
                f"{record.artifact_id}/zip",
                metadata.artifact_size,
                "application/vnd.github+json",
            ),
            calls[0],
        )
        self.assertEqual(
            [asset_id for _name, asset_id, _size in metadata.release_assets],
            [int(endpoint.rsplit("/", 1)[1]) for endpoint, _size, _accept in calls[1:]],
        )
        self.assertTrue(
            all(accept == "application/octet-stream" for _endpoint, _size, accept in calls[1:])
        )

    def test_rejects_release_download_that_differs_from_artifact_and_local_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, artifact, record, digests, metadata = self.fixture(root)
            first_name, first_id, _ = metadata.release_assets[0]
            mutated = root / "mutated-release-asset"
            mutated.write_bytes((assets / first_name).read_bytes() + b"mutation\n")
            metadata = MODULE.PublicMetadata(
                artifact_size=metadata.artifact_size,
                release_assets=tuple(
                    (name, asset_id, mutated.stat().st_size if asset_id == first_id else size)
                    for name, asset_id, size in metadata.release_assets
                ),
            )

            def download(
                _gh: str,
                _repository_root: Path,
                endpoint: str,
                destination: Path,
                _expected_size: int,
                *,
                accept: str,
            ) -> None:
                del accept
                if endpoint.endswith(f"/{record.artifact_id}/zip"):
                    source = artifact
                else:
                    asset_id = int(endpoint.rsplit("/", 1)[1])
                    name = next(
                        name
                        for name, candidate_id, _size in metadata.release_assets
                        if candidate_id == asset_id
                    )
                    source = mutated if asset_id == first_id else assets / name
                shutil.copyfile(source, destination)

            with (
                mock.patch.object(MODULE, "_download_gh_file", side_effect=download),
                self.assertRaisesRegex(MODULE.ActivationError, "differs"),
            ):
                MODULE.download_and_validate_public_bytes(
                    "/safe/gh", root, assets, metadata, record, digests
                )


class ActivationAttestationCommandTest(unittest.TestCase):
    def test_invokes_exact_release_and_all_twelve_asset_attestations(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        completed = subprocess.CompletedProcess(
            ["/safe/gh"], 0, stdout="presentation is not parsed\n", stderr=""
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            with mock.patch.object(MODULE, "_run", return_value=completed) as runner:
                MODULE.validate_release_attestations(
                    "/safe/gh", root, assets, record
                )
        self.assertEqual(13, runner.call_count)
        commands = [call.args[0] for call in runner.call_args_list]
        self.assertEqual(
            [
                "/safe/gh",
                "release",
                "verify",
                record.tag,
                "--repo",
                MODULE.QUALIFIED_REPOSITORY,
            ],
            commands[0],
        )
        self.assertEqual(
            list(record.public_assets),
            [Path(command[4]).name for command in commands[1:]],
        )
        self.assertTrue(all(command[1:4] == ["release", "verify-asset", record.tag] for command in commands[1:]))
        self.assertTrue(all(command[5:] == ["--repo", MODULE.QUALIFIED_REPOSITORY] for command in commands[1:]))

    def test_rejects_failed_or_empty_attestation_output(self) -> None:
        record = MODULE.validate_record_schema(valid_document())
        for result in (
            subprocess.CompletedProcess(["/safe/gh"], 1, stdout="", stderr="sensitive"),
        ):
            with self.subTest(returncode=result.returncode, stdout=result.stdout), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                assets = root / "assets"
                assets.mkdir()
                with mock.patch.object(MODULE, "_run", return_value=result):
                    with self.assertRaises(MODULE.ActivationError) as caught:
                        MODULE.validate_release_attestations(
                            "/safe/gh", root, assets, record
                        )
                self.assertNotIn("sensitive", str(caught.exception))


class ActivationGitHubCommandTest(unittest.TestCase):
    def test_api_commands_pin_github_dot_com_and_endpoint_specific_accept(self) -> None:
        artifact = MODULE._gh_download_command(
            "/safe/gh", "repos/ym0506/routecontract/actions/artifacts/7/zip",
            "application/vnd.github+json",
        )
        release = MODULE._gh_download_command(
            "/safe/gh", "repos/ym0506/routecontract/releases/assets/8",
            "application/octet-stream",
        )
        for command in (artifact, release):
            self.assertEqual(
                ["--hostname", "github.com"],
                command[command.index("--hostname") : command.index("--hostname") + 2],
            )
        self.assertIn("Accept: application/vnd.github+json", artifact)
        self.assertIn("Accept: application/octet-stream", release)
        with self.assertRaises(MODULE.ActivationError):
            MODULE._gh_download_command("/safe/gh", "endpoint", "text/plain")

    def test_json_api_command_pins_github_dot_com(self) -> None:
        completed = subprocess.CompletedProcess(
            ["/safe/gh"], 0, stdout='{"ok":true}\n', stderr=""
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            MODULE, "_run", return_value=completed
        ) as runner:
            value = MODULE._gh_json("/safe/gh", Path(temporary), "repos/owner/repo")
        self.assertEqual({"ok": True}, value)
        command = runner.call_args.args[0]
        self.assertEqual(
            ["--hostname", "github.com"],
            command[command.index("--hostname") : command.index("--hostname") + 2],
        )

    def test_json_list_api_command_pins_github_dot_com_and_requires_objects(self) -> None:
        completed = subprocess.CompletedProcess(
            ["/safe/gh"], 0, stdout='[{"number":88}]\n', stderr=""
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            MODULE, "_run", return_value=completed
        ) as runner:
            value = MODULE._gh_json_list(
                "/safe/gh", Path(temporary), "repos/owner/repo/commits/a/pulls"
            )
        self.assertEqual([{"number": 88}], value)
        command = runner.call_args.args[0]
        self.assertEqual(
            ["--hostname", "github.com"],
            command[command.index("--hostname") : command.index("--hostname") + 2],
        )
        bad = subprocess.CompletedProcess(
            ["/safe/gh"], 0, stdout='[1]\n', stderr=""
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            MODULE, "_run", return_value=bad
        ), self.assertRaises(MODULE.ActivationError):
            MODULE._gh_json_list(
                "/safe/gh", Path(temporary), "repos/owner/repo/commits/a/pulls"
            )

    def test_graphql_pull_transport_is_authenticated_strict_and_duplicate_safe(
        self,
    ) -> None:
        good = subprocess.CompletedProcess(
            ["/safe/gh"], 0, stdout='{"data":{}}\n', stderr=""
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            MODULE, "_run", return_value=good
        ) as runner:
            self.assertEqual(
                {"data": {}},
                MODULE._gh_graphql_activation_pull(
                    "/safe/gh", Path(temporary), 26
                ),
            )
        command = runner.call_args.args[0]
        self.assertEqual("graphql", command[command.index("api") + 1])
        self.assertEqual(
            ["--hostname", "github.com"],
            command[command.index("--hostname") : command.index("--hostname") + 2],
        )
        self.assertIn("number=26", command)

        failures = (
            subprocess.CompletedProcess(
                ["/safe/gh"], 1, stdout="", stderr="unavailable"
            ),
            subprocess.CompletedProcess(
                ["/safe/gh"], 0, stdout='{"data":{},"errors":[]}\n', stderr=""
            ),
            subprocess.CompletedProcess(
                ["/safe/gh"], 0, stdout='{"data":{},"data":{}}\n', stderr=""
            ),
            subprocess.CompletedProcess(
                ["/safe/gh"], 0, stdout='{"data":null}\n', stderr=""
            ),
        )
        for result in failures:
            with self.subTest(stdout=result.stdout), tempfile.TemporaryDirectory() as temporary, mock.patch.object(
                MODULE, "_run", return_value=result
            ), self.assertRaises(MODULE.ActivationError):
                MODULE._gh_graphql_activation_pull(
                    "/safe/gh", Path(temporary), 26
                )

    def test_all_public_json_transports_reject_duplicate_nonfinite_and_overflow_values(
        self,
    ) -> None:
        canary = "CANARY_PRIVATE_JSON_KEY"
        cases = (
            ("object-duplicate", MODULE._gh_json, f'{{"{canary}":1,"{canary}":2}}'),
            ("object-nested-duplicate", MODULE._gh_json, f'{{"outer":{{"{canary}":1,"{canary}":2}}}}'),
            ("object-nan", MODULE._gh_json, '{"value":NaN}'),
            ("object-overflow", MODULE._gh_json, '{"value":1e999}'),
            ("list-duplicate", MODULE._gh_json_list, f'[{{"{canary}":1,"{canary}":2}}]'),
            ("list-infinity", MODULE._gh_json_list, '[{"value":Infinity}]'),
        )
        for label, helper, payload in cases:
            completed = subprocess.CompletedProcess(
                ["/safe/gh"], 0, stdout=payload, stderr=""
            )
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary, mock.patch.object(
                MODULE, "_run", return_value=completed
            ), self.assertRaises(MODULE.ActivationError) as caught:
                helper("/safe/gh", Path(temporary), "repos/owner/repo")
            self.assertNotIn(canary, str(caught.exception))

        graphql_payloads = (
            f'{{"data":{{"{canary}":1,"{canary}":2}}}}',
            '{"data":{"value":-Infinity}}',
            '{"data":{"value":1e999}}',
        )
        for payload in graphql_payloads:
            completed = subprocess.CompletedProcess(
                ["/safe/gh"], 0, stdout=payload, stderr=""
            )
            with self.subTest(surface="graphql", payload=payload), tempfile.TemporaryDirectory() as temporary, mock.patch.object(
                MODULE, "_run", return_value=completed
            ), self.assertRaises(MODULE.ActivationError) as caught:
                MODULE._gh_graphql_activation_pull(
                    "/safe/gh", Path(temporary), 26
                )
            self.assertNotIn(canary, str(caught.exception))

    def test_all_public_json_transports_share_utf8_integer_and_tree_budgets(
        self,
    ) -> None:
        huge_integer = b'{"value":' + (b"9" * 5_000) + b"}"
        malformed_utf8 = b'{"value":"\xff"}'
        utf16_object = '{"value":1}'.encode("utf-16")
        over_depth = ActivationStrictJsonDecoderTest.nested_payload(
            "object", MODULE.MAX_JSON_NESTING_DEPTH + 1
        )
        over_nodes = ActivationStrictJsonDecoderTest.node_payload(
            "object", MODULE.MAX_JSON_NODE_COUNT + 1
        )
        rest_cases = (
            ("object-huge-integer", MODULE._gh_json, huge_integer),
            ("object-malformed-utf8", MODULE._gh_json, malformed_utf8),
            ("object-utf16", MODULE._gh_json, utf16_object),
            ("object-over-depth", MODULE._gh_json, over_depth),
            ("object-over-nodes", MODULE._gh_json, over_nodes),
            (
                "list-utf16",
                MODULE._gh_json_list,
                '[{"value":1}]'.encode("utf-16"),
            ),
        )
        for label, helper, payload in rest_cases:
            completed = subprocess.CompletedProcess(
                ["/safe/gh"], 0, stdout=payload, stderr=b""
            )
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary, mock.patch.object(
                MODULE, "_run", return_value=completed
            ), self.assertRaises(MODULE.ActivationError) as caught:
                helper("/safe/gh", Path(temporary), "repos/owner/repo")
            self.assertIsNone(caught.exception.__cause__)
            self.assertNotIn("999999999999", str(caught.exception))

        graphql_cases = (
            b'{"data":{"value":' + (b"9" * 5_000) + b"}}",
            '{"data":{}}'.encode("utf-16"),
            b'{"data":' + over_depth + b"}",
            b'{"data":' + over_nodes + b"}",
        )
        for payload in graphql_cases:
            completed = subprocess.CompletedProcess(
                ["/safe/gh"], 0, stdout=payload, stderr=b""
            )
            with self.subTest(surface="graphql", payload_prefix=payload[:24]), tempfile.TemporaryDirectory() as temporary, mock.patch.object(
                MODULE, "_run", return_value=completed
            ), self.assertRaises(MODULE.ActivationError) as caught:
                MODULE._gh_graphql_activation_pull(
                    "/safe/gh", Path(temporary), 26
                )
            self.assertIsNone(caught.exception.__cause__)
            self.assertNotIn("999999999999", str(caught.exception))

    def test_rest_and_graphql_json_outputs_enforce_eight_mib_without_echo(self) -> None:
        canary = b"CANARY_OVERSIZE_PRIVATE_VALUE"
        padding = b"x" * MODULE.MAX_GITHUB_JSON_BYTES
        cases = (
            (
                "object",
                MODULE._gh_json,
                b'{"' + canary + b'":"' + padding + b'"}',
            ),
            (
                "list",
                MODULE._gh_json_list,
                b'[{"' + canary + b'":"' + padding + b'"}]',
            ),
        )
        for label, helper, payload in cases:
            completed = subprocess.CompletedProcess(
                ["/safe/gh"], 0, stdout=payload, stderr=b""
            )
            with self.subTest(surface=label), tempfile.TemporaryDirectory() as temporary, mock.patch.object(
                MODULE, "_run", return_value=completed
            ), self.assertRaises(MODULE.ActivationError) as caught:
                helper("/safe/gh", Path(temporary), "repos/owner/repo")
            self.assertIsNone(caught.exception.__cause__)
            self.assertNotIn(canary.decode("ascii"), str(caught.exception))

        graphql_payload = (
            b'{"data":{"' + canary + b'":"' + padding + b'"}}'
        )
        completed = subprocess.CompletedProcess(
            ["/safe/gh"], 0, stdout=graphql_payload, stderr=b""
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            MODULE, "_run", return_value=completed
        ), self.assertRaises(MODULE.ActivationError) as caught:
            MODULE._gh_graphql_activation_pull(
                "/safe/gh", Path(temporary), 26
            )
        self.assertIsNone(caught.exception.__cause__)
        self.assertNotIn(canary.decode("ascii"), str(caught.exception))

    def test_command_transport_rejects_timeout_and_malformed_utf8_generically(self) -> None:
        canary = "CANARY_TRANSPORT_SECRET"
        failures = (
            subprocess.TimeoutExpired(["/safe/gh"], 60, output=canary, stderr=canary),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, canary),
        )
        for failure in failures:
            with self.subTest(kind=type(failure).__name__), mock.patch.object(
                MODULE.subprocess, "run", side_effect=failure
            ), self.assertRaises(MODULE.ActivationError) as caught:
                MODULE._run(["/safe/gh"], cwd=Path("/private/tmp"), timeout=60)
            self.assertNotIn(canary, str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)


class ActivationDocumentationContractTest(unittest.TestCase):
    def test_protocol_and_issue_form_use_only_validated_record_identity(self) -> None:
        protocol = (REPOSITORY_ROOT / "docs/independent-install-study.md").read_text(
            encoding="utf-8"
        )
        form_root = REPOSITORY_ROOT / ".github/ISSUE_TEMPLATE"
        rc1_form_path = form_root / "independent-rc1-install.yml"
        rc2_form_path = form_root / "independent-rc2-install.yml"
        rc1_issue_form = rc1_form_path.read_text(encoding="utf-8")
        rc2_issue_form = rc2_form_path.read_text(encoding="utf-8")
        releasing = (REPOSITORY_ROOT / "RELEASING.md").read_text(encoding="utf-8")
        for required in (
            "scripts/validate-rc-activation-record.py",
            "ROUTECONTRACT_RC_ACTIVATION_VERIFIED",
            "ACTIVATION_RECORD_PERMALINK",
        ):
            self.assertIn(required, protocol)
            self.assertIn(required, releasing)
        for issue_form in (rc1_issue_form, rc2_issue_form):
            self.assertIn("ROUTECONTRACT_RC_ACTIVATION_VERIFIED", issue_form)
        for text in (protocol, rc1_issue_form, rc2_issue_form):
            self.assertNotIn("0000000000000000000000000000000000000000", text)
        for issue_form in (rc1_issue_form, rc2_issue_form):
            self.assertNotIn("<record>.md", issue_form)
        self.assertIn("routecontract_exact_checkout", protocol)
        self.assertIn("direct parent is the tag commit", protocol)
        self.assertIn("only tree change", protocol)
        for required in (
            "independent-rc1-install.yml",
            "independent-rc2-install.yml",
            "issueFormFilename",
            "issueFormPermalink",
            "issueFormUrl",
        ):
            self.assertIn(required, protocol)
            self.assertIn(required, releasing)
        self.assertFalse((form_root / "independent-rc-install.yml").exists())
        self.assertNotIn("template=independent-rc-install.yml", protocol)
        self.assertEqual(
            RC1_FORM_SHA256,
            hashlib.sha256(rc1_form_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            RC2_FORM_SHA256,
            hashlib.sha256(rc2_form_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(1, rc1_issue_form.count("0.1.0-rc1"))
        self.assertNotIn("0.1.0-rc2", rc1_issue_form)
        self.assertEqual(
            rc1_issue_form.replace("0.1.0-rc1", "0.1.0-rc2"),
            rc2_issue_form,
        )
        self.assertIn(
            "future RC candidate must add and review its derived form", releasing
        )
        for required in (
            "generic validator binds only the active",
            "separate reviewed tag-history and owner gate",
        ):
            self.assertIn(required, protocol)
            self.assertIn(required, releasing)


if __name__ == "__main__":
    unittest.main()
