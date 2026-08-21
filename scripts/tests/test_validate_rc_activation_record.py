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

    def test_template_materializes_to_valid_rc1_and_future_rc2_schema(self) -> None:
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
            with self.assertRaisesRegex(MODULE.ActivationError, "duplicate JSON key"):
                MODULE.load_record(duplicate)

            directory = root / "directory.json"
            directory.mkdir()
            with self.assertRaisesRegex(MODULE.ActivationError, "regular file"):
                MODULE.load_record(directory)


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

        with (
            mock.patch.object(MODULE, "_gh_json", side_effect=response),
            mock.patch.object(MODULE, "_gh_json_list", side_effect=response_list),
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


class ActivationDocumentationContractTest(unittest.TestCase):
    def test_protocol_and_issue_form_use_only_validated_record_identity(self) -> None:
        protocol = (REPOSITORY_ROOT / "docs/independent-install-study.md").read_text(
            encoding="utf-8"
        )
        form_root = REPOSITORY_ROOT / ".github/ISSUE_TEMPLATE"
        rc1_form_path = form_root / "independent-rc1-install.yml"
        rc2_form_path = form_root / "independent-rc2-install.yml"
        issue_form = rc1_form_path.read_text(encoding="utf-8")
        releasing = (REPOSITORY_ROOT / "RELEASING.md").read_text(encoding="utf-8")
        for required in (
            "scripts/validate-rc-activation-record.py",
            "ROUTECONTRACT_RC_ACTIVATION_VERIFIED",
            "ACTIVATION_RECORD_PERMALINK",
        ):
            self.assertIn(required, protocol)
            self.assertIn(required, releasing)
        self.assertIn("ROUTECONTRACT_RC_ACTIVATION_VERIFIED", issue_form)
        for text in (protocol, issue_form):
            self.assertNotIn("0000000000000000000000000000000000000000", text)
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
        self.assertFalse(rc2_form_path.exists())
        self.assertNotIn("template=independent-rc-install.yml", protocol)
        self.assertEqual(
            RC1_FORM_SHA256,
            hashlib.sha256(rc1_form_path.read_bytes()).hexdigest(),
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
