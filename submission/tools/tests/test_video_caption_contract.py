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
SOURCE_SHA256 = "e698947f8b5a8df610d5b4e521758ef781a11e4f694618340aff2f54721f3f83"


class VideoCaptionContractTest(unittest.TestCase):
    def test_tracked_source_and_selected_srt_hashes_are_deterministic(self) -> None:
        contract, observed_sha256 = video_caption_contract.load_contract(
            SOURCE, SOURCE_SHA256
        )
        self.assertEqual(SOURCE_SHA256, observed_sha256)
        early_process_cue = contract["cues"][1]
        self.assertEqual(
            (5_700, 11_500),
            (early_process_cue["start_ms"], early_process_cue["end_ms"]),
        )
        self.assertEqual(
            ["실제 MySQL 검증을 실행 중입니다", "결과가 나오면 기록 차이를 확인합니다"],
            early_process_cue["lines"],
        )
        self.assertNotIn("1→2", "".join(early_process_cue["lines"]))
        self.assertNotIn("관측된", "".join(early_process_cue["lines"]))
        self.assertEqual(
            ["승인본 차이를 실패로 바꾸는", "CI용 검사를 지금 실행합니다"],
            contract["cues"][6]["lines"],
        )
        self.assertEqual(
            (54_000, 59_500),
            (contract["cues"][7]["start_ms"], contract["cues"][7]["end_ms"]),
        )
        self.assertEqual(
            ["실제 exit 1로 빌드가 멈췄습니다", "차이는 사람이 승인해야 합니다"],
            contract["cues"][7]["lines"],
        )
        self.assertEqual(
            [
                "실행 횟수가 같아도 구조가 달라질까요?",
                "실제 MySQL로 다시 확인합니다",
            ],
            contract["cues"][11]["lines"],
        )
        self.assertEqual(
            ["입력값은 저장하지 않습니다", "매개변수 수는 한 개에서 두 개입니다"],
            contract["cues"][12]["lines"],
        )
        self.assertEqual(
            ["횟수가 같아도 자동 승인하지 않습니다", "SQL 뜻은 판단하지 않습니다"],
            contract["cues"][13]["lines"],
        )
        self.assertEqual(
            [
                "실제 MySQL 여덟 사례를 스무 번씩",
                "각 사례에서 같은 기록이 나왔습니다",
            ],
            contract["cues"][14]["lines"],
        )
        self.assertEqual(
            [
                "독립 검증은 공개 양식으로 모집했습니다",
                "안정판 외부 검증은 확보하지 못했습니다",
            ],
            contract["cues"][20]["lines"],
        )
        expected = {
            "zero": {
                "selected_cues_sha256": (
                    "3c1af19e852d23efc0e30176cddf7cac"
                    "e2f44814f2150cc91514a87df2ad1d74"
                ),
                "srt_sha256": (
                    "19cedeec8699f0977a4159612455cdf47"
                    "9936c3736ffdcc5fa21bb957b1babb6"
                ),
                "included": "독립 검증은 공개 양식으로 모집했습니다",
                "excluded": "정해진 양식의 RC 결과 접수는 1건",
            },
            "rc_only": {
                "selected_cues_sha256": (
                    "6fef3efa8bb7b5e8c191bd2653cfc656"
                    "2d1c2dd997d63a9ece69f0d681b8f292"
                ),
                "srt_sha256": (
                    "310a6e6cba9a73c1b948dd756937ae40"
                    "d73977c671ae3b8a7a53af71303a93fb"
                ),
                "included": "정해진 양식의 RC 결과 접수는 1건",
                "excluded": "독립 검증은 공개 양식으로 모집했습니다",
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
        manifest["video"]["duration_seconds"] = 172.999
        with self.assertRaisesRegex(
            package_submission.GateError, "173 through 175 seconds inclusive"
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
