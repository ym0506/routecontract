from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from submission.tools import video_caption_contract
from submission.tools.tests.test_package_submission import (
    package_submission,
    valid_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE = REPOSITORY_ROOT / "submission" / "video-caption-cues.json"
SOURCE_SHA256 = "19560225c18ca8156a13760e8412e46462383df5e80a92bc2dd7d4615a1f0158"


class VideoCaptionContractTest(unittest.TestCase):
    def test_tracked_source_and_selected_srt_hashes_are_deterministic(self) -> None:
        contract, observed_sha256 = video_caption_contract.load_contract(
            SOURCE, SOURCE_SHA256
        )
        self.assertEqual(SOURCE_SHA256, observed_sha256)
        expected = {
            "zero": {
                "selected_cues_sha256": (
                    "f0df2fe73e013756010a144f6512e3ed"
                    "d0ed8bc2cb215e92b1ff434bd6d6abaf"
                ),
                "srt_sha256": (
                    "8b8130e12db376ce349e3e22008e970b"
                    "c94f0567a938ee943ca44de9724c41f6"
                ),
                "included": "독립 검증은 공개 양식으로 받습니다",
                "excluded": "정해진 양식의 RC 결과 접수는 1건",
            },
            "rc_only": {
                "selected_cues_sha256": (
                    "1a92e56786fbe382ae6fc2d4c66180b3"
                    "cd50cbba3a8e9001cf99ba4098bb3fca"
                ),
                "srt_sha256": (
                    "7bfa80c8ca3f9536c225595f700ae6cc"
                    "6f44ddf4121a56355e7410e706bb4c3a"
                ),
                "included": "정해진 양식의 RC 결과 접수는 1건",
                "excluded": "독립 검증은 공개 양식으로 받습니다",
            },
        }
        for branch, assertions in expected.items():
            with self.subTest(branch=branch):
                evidence = video_caption_contract.build_branch_evidence(
                    SOURCE, SOURCE_SHA256, branch
                )
                self.assertEqual(24, evidence["selected_cue_count"])
                self.assertEqual(172_500, evidence["selected_last_cue_end_ms"])
                self.assertEqual(
                    assertions["selected_cues_sha256"],
                    evidence["selected_cues_sha256"],
                )
                self.assertEqual(assertions["srt_sha256"], evidence["srt_sha256"])
                rendered = video_caption_contract.render_srt(contract, branch)
                self.assertNotIn(b"\r", rendered)
                self.assertTrue(rendered.endswith(b"\n"))
                text = rendered.decode("utf-8")
                self.assertIn(assertions["included"], text)
                self.assertNotIn(assertions["excluded"], text)

    def test_strict_source_rejects_duplicate_unknown_and_noncanonical_cues(self) -> None:
        valid = json.loads(SOURCE.read_text(encoding="utf-8"))
        cases: list[bytes] = []
        cases.append(
            b'{"schema_version":1,"schema_version":1,"timebase":"milliseconds","cues":[]}'
        )
        unknown = deepcopy(valid)
        unknown["unexpected"] = True
        cases.append(json.dumps(unknown, ensure_ascii=False).encode("utf-8"))
        reversed_cues = deepcopy(valid)
        reversed_cues["cues"] = list(reversed(reversed_cues["cues"]))
        cases.append(json.dumps(reversed_cues, ensure_ascii=False).encode("utf-8"))
        one_line = deepcopy(valid)
        one_line["cues"][0]["lines"] = ["한 행만 있습니다"]
        cases.append(json.dumps(one_line, ensure_ascii=False).encode("utf-8"))
        placeholder = deepcopy(valid)
        placeholder["cues"][0]["lines"][0] = "[[CAPTION_TEXT]]"
        cases.append(json.dumps(placeholder, ensure_ascii=False).encode("utf-8"))

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "cues.json"
            for index, payload in enumerate(cases):
                with self.subTest(index=index):
                    path.write_bytes(payload)
                    with self.assertRaises(video_caption_contract.CaptionContractError):
                        video_caption_contract.load_contract(path)

    def test_manifest_binds_fixed_source_branch_hashes_and_final_cue(self) -> None:
        checked = package_submission.validate_manifest(valid_manifest())
        evidence = package_submission.manifest_video_caption_evidence(checked)
        self.assertEqual("rc_only", evidence["selected_branch"])
        self.assertEqual(SOURCE_SHA256, evidence["source_sha256"])
        self.assertEqual(172_500, evidence["selected_last_cue_end_ms"])

        packaged = package_submission.package_video_metadata(
            {"sha256": "4" * 64, "audio_stream_count": 0}, checked
        )
        self.assertEqual(evidence, packaged["caption_contract"])
        self.assertRegex(packaged["caption_contract"]["srt_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(
            packaged["local_burned_in_caption_pixels_automatically_verified"]
        )
        self.assertTrue(
            packaged["local_actual_screen_caption_watchthrough_participant_attested"]
        )
        self.assertFalse(
            packaged["public_frame_audio_caption_equivalence_automatically_verified"]
        )
        self.assertTrue(
            packaged["public_frame_audio_caption_equivalence_participant_attested"]
        )

        for key, value in (
            ("source_path", "submission/alternate-cues.json"),
            ("source_sha256", "f" * 64),
            ("schema_version", 2),
        ):
            manifest = valid_manifest()
            manifest["video"]["caption_contract"][key] = value
            with self.subTest(key=key), self.assertRaises(package_submission.GateError):
                package_submission.validate_manifest(manifest)

        manifest = valid_manifest()
        manifest["video"]["duration_seconds"] = 172.499
        with self.assertRaisesRegex(
            package_submission.GateError, "selected caption branch's final cue"
        ):
            package_submission.validate_manifest(manifest)

    def test_final_rehash_rejects_video_change_before_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            video = Path(raw) / "final.mp4"
            video.write_bytes(b"reviewed")
            expected = hashlib.sha256(b"reviewed").hexdigest()
            self.assertEqual(
                expected,
                package_submission.revalidate_local_video_hash_before_metadata(
                    video, expected
                ),
            )
            video.write_bytes(b"changed")
            with self.assertRaisesRegex(
                package_submission.GateError, "before package metadata write"
            ):
                package_submission.revalidate_local_video_hash_before_metadata(
                    video, expected
                )


if __name__ == "__main__":
    unittest.main()
