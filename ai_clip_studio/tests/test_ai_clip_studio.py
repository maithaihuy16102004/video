"""Unit tests for ai_clip_studio (stdlib unittest, no network, no Drive).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/video-16x9-v2/
"""

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.production_request import (
    ProductionRequest, HashChainError, compute_script_hash,
)
from ai_clip_studio.timeline import (
    TimelineLine, build_timeline, measure_wav_duration, TimelineError,
)
from ai_clip_studio.preflight import run_preflight
from ai_clip_studio.audio_events import (
    plan_audio_events, resolve_meme, is_serious_scene, STEMS,
)
from ai_clip_studio.drive_uploader import (
    DriveUploader, PROJECT_FOLDERS, GROUP_FOLDER, DRIVE_ROOT_FOLDER_ID,
)
from ai_clip_studio.pipeline import (
    run_production, segment_script,
    STATUS_BLOCKED, STATUS_DRAFT_READY,
)


def make_silent_wav(path: Path, seconds: float, sr: int = 48000) -> None:
    frames = int(seconds * sr)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * frames)


class TestProductionRequest(unittest.TestCase):
    def test_hash_is_full_sha256(self):
        req = ProductionRequest(script_text="Xin chào Hà Nội.")
        self.assertEqual(req.script_hash, compute_script_hash("Xin chào Hà Nội."))
        self.assertEqual(len(req.script_hash), 64)

    def test_same_script_same_hash_different_request(self):
        a = ProductionRequest(script_text="Một câu chuyện.")
        b = ProductionRequest(script_text="Một câu chuyện.")
        self.assertEqual(a.script_hash, b.script_hash)
        self.assertNotEqual(a.request_id, b.request_id)

    def test_chain_ok_when_all_stages_recorded(self):
        req = ProductionRequest(script_text="Chuyện.")
        for stage in ("analysis", "storyboard", "preflight", "render_job", "output_manifest"):
            req.record_stage(stage, req.script_hash)
        self.assertEqual(req.verify_chain(), [])

    def test_chain_fails_when_script_changed(self):
        req = ProductionRequest(script_text="Bản gốc.")
        req.record_stage("analysis", compute_script_hash("Bản đã sửa."))
        problems = req.verify_chain()
        self.assertTrue(any("analysis" in p for p in problems))

    def test_render_guard_rejects_mismatched_hash(self):
        req = ProductionRequest(script_text="Bản gốc.")
        with self.assertRaises(HashChainError):
            req.require_hash_match("render_job", compute_script_hash("Bản khác."))

    def test_render_guard_accepts_matching_hash(self):
        req = ProductionRequest(script_text="Bản gốc.")
        req.require_hash_match("render_job", req.script_hash)
        self.assertEqual(req.stage_hash("render_job"), req.script_hash)


class TestTimeline(unittest.TestCase):
    def test_dynamic_duration_from_real_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            w1 = Path(tmp) / "l1.wav"
            w2 = Path(tmp) / "l2.wav"
            make_silent_wav(w1, 3.0)
            make_silent_wav(w2, 5.0)
            tl = build_timeline([
                TimelineLine(text="Câu một.", voice_wav=w1, pause_after_sec=0.5),
                TimelineLine(text="Câu hai dài hơn.", voice_wav=w2, pause_after_sec=0.5),
            ])
            # 3.0 + 0.5 + 5.0 + 0.5 + 0.5 tail = 9.5
            self.assertAlmostEqual(tl.total_duration_sec, 9.5, places=2)
            self.assertTrue(tl.all_measured)

    def test_no_fixed_cap_17s_voice_fits(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp) / "long.wav"
            make_silent_wav(w, 17.0)
            tl = build_timeline([TimelineLine(text="Giọng dài.", voice_wav=w)])
            self.assertGreater(tl.total_duration_sec, 17.0)

    def test_truncation_guard_raises(self):
        tl_lines = [TimelineLine(text="x", duration_sec=3.0)]
        from ai_clip_studio.timeline import Timeline
        t = Timeline(lines=tl_lines, total_duration_sec=2.0)
        with self.assertRaises(TimelineError):
            t.check_no_truncation(2.0, 3.0)

    def test_speed_up_refused(self):
        with self.assertRaises(TimelineError):
            build_timeline([TimelineLine(text="Câu.")], speech_speed=1.25)

    def test_measure_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp) / "a.wav"
            make_silent_wav(w, 2.5)
            self.assertAlmostEqual(measure_wav_duration(w), 2.5, places=2)

    def test_end_card_sec_included_in_total(self):
        # Stage 3 integration: the end card is rendered video, so
        # the timeline total must cover it (else timeline_sync
        # fails on every script with an END_CARD block).
        tl = build_timeline(
            [TimelineLine(text="Câu.", duration_sec=2.0,
                          pause_after_sec=0.35)],
            end_card_sec=3.0)
        # 2.0 + 0.35 + 0.5 tail + 3.0 card = 5.85
        self.assertAlmostEqual(tl.total_duration_sec, 5.85, places=2)
        self.assertAlmostEqual(tl.end_card_sec, 3.0, places=2)
        tl0 = build_timeline(
            [TimelineLine(text="Câu.", duration_sec=2.0,
                          pause_after_sec=0.35)])
        self.assertAlmostEqual(tl0.total_duration_sec, 2.85, places=2)
        self.assertAlmostEqual(tl0.end_card_sec, 0.0, places=2)


class TestPreflight(unittest.TestCase):
    def test_pass_with_measured_timeline(self):
        req = ProductionRequest(script_text="Chuyện ngắn.")
        tl = build_timeline([TimelineLine(text="Chuyện ngắn.", duration_sec=2.0)])
        result = run_preflight(req, timeline=tl, available_voices=("narrator",),
                               required_voices=("narrator",),
                               script_hash_at_preflight=req.script_hash)
        self.assertTrue(result.passed, result.to_dict())

    def test_fail_on_hash_mismatch(self):
        req = ProductionRequest(script_text="Bản gốc.")
        tl = build_timeline([TimelineLine(text="x", duration_sec=1.0)])
        result = run_preflight(req, timeline=tl,
                               script_hash_at_preflight=compute_script_hash("Bản khác."))
        self.assertFalse(result.passed)
        self.assertTrue(any(c.name == "script_hash" for c in result.failures()))

    def test_fail_on_missing_voice(self):
        req = ProductionRequest(script_text="Chuyện.")
        tl = build_timeline([TimelineLine(text="x", duration_sec=1.0)])
        result = run_preflight(req, timeline=tl, available_voices=("narrator",),
                               required_voices=("Lan",))
        self.assertFalse(result.passed)

    def test_fail_on_wrong_resolution(self):
        req = ProductionRequest(script_text="Chuyện.")
        tl = build_timeline([TimelineLine(text="x", duration_sec=1.0)])
        result = run_preflight(req, timeline=tl, output_width=1080, output_height=1920)
        self.assertFalse(result.passed)

    def test_fail_when_timeline_only_estimated(self):
        req = ProductionRequest(script_text="Chuyện.")
        tl = build_timeline([TimelineLine(text="Chuyện dài chưa có audio thật.")])
        result = run_preflight(req, timeline=tl)
        self.assertFalse(result.passed)
        self.assertTrue(any(c.name == "timeline_measured" for c in result.failures()))


class TestAudioEvents(unittest.TestCase):
    def test_event_map(self):
        plan = plan_audio_events([
            {"event": "foot_contact", "at_seconds": 1.0},
            {"event": "paper_movement", "at_seconds": 2.5},
            {"event": "door_rotation", "at_seconds": 4.0},
        ])
        sfx = [e.sfx for e in plan.events]
        self.assertEqual(sfx, ["FOOTSTEP", "PAPER_RUSTLE", "DOOR_OPEN"])
        self.assertEqual(plan.stems, STEMS)
        self.assertEqual(plan.ducking_db, -14.0)

    def test_unknown_event_dropped_not_invented(self):
        plan = plan_audio_events([{"event": "teleport", "at_seconds": 1.0}])
        self.assertEqual(plan.events, [])
        self.assertEqual(len(plan.blocked_memes), 1)

    def test_meme_blocked_in_serious_scene(self):
        self.assertTrue(is_serious_scene("Anh ấy chết trong chiến tranh."))
        result = resolve_meme("vine_boom", script_text="Anh ấy chết trong chiến tranh.",
                              catalog={"memes": [{"id": "meme_001", "slug": "vine_boom"}]})
        self.assertFalse(result["inserted"])

    def test_meme_resolved_from_catalog(self):
        catalog = {"memes": [{"id": "meme_001", "slug": "vine_boom",
                              "filename": "vine_boom_sound.mp3"}]}
        result = resolve_meme("vine_boom", script_text="Cảnh hài vui vẻ.",
                              catalog=catalog)
        self.assertTrue(result["inserted"])
        self.assertEqual(result["meme_id"], "meme_001")

    def test_missing_meme_has_no_substitute(self):
        result = resolve_meme("khong_co", script_text="Cảnh hài.",
                              catalog={"memes": []})
        self.assertFalse(result["inserted"])
        self.assertIn("not in catalog", result["reason"])


class MockDriveClient:
    def __init__(self):
        self.folders = {}
        self.files = {}
        self.counter = 0

    def _next(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter:03d}"

    def create_folder(self, name, parent_id):
        fid = self._next("fld_")
        self.folders[fid] = {"id": fid, "name": name, "parent": parent_id}
        return fid

    def find_file(self, name, parent_id):
        for f in self.files.values():
            if f["name"] == name and f["parent"] == parent_id:
                return f
        for f in self.folders.values():
            if f["name"] == name and f["parent"] == parent_id:
                return f
        return None

    def upload_file(self, path, parent_id):
        fid = self._next("file_")
        self.files[fid] = {"id": fid, "name": Path(path).name,
                           "parent": parent_id, "size": str(Path(path).stat().st_size)}
        return {"id": fid, "name": Path(path).name}

    def get_file(self, file_id):
        return self.files.get(file_id) or self.folders.get(file_id, {})


class TestDriveUploader(unittest.TestCase):
    def test_folder_structure(self):
        self.assertEqual(PROJECT_FOLDERS, ("01_SCRIPT", "02_STORYBOARD", "03_AUDIO",
                                           "04_DRAFT", "05_QA_REPORTS", "06_MASTER"))
        self.assertEqual(GROUP_FOLDER["script"], "01_SCRIPT")
        self.assertEqual(GROUP_FOLDER["master"], "06_MASTER")
        self.assertEqual(DRIVE_ROOT_FOLDER_ID, "1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm")

    def test_upload_creates_structure_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "draft.mp4"
            p.write_bytes(b"fake mp4" * 100)
            up = DriveUploader(client=MockDriveClient())
            folders = up.ensure_project_folders("proj_test")
            self.assertEqual(set(folders), {"project"} | set(PROJECT_FOLDERS))
            rec = up.upload(p, "draft", folders)
            self.assertEqual(rec.status, "uploaded")
            self.assertEqual(rec.size_bytes, p.stat().st_size)
            self.assertTrue(rec.drive_url.startswith("https://drive.google.com/file/d/"))

    def test_retry_reuses_existing_no_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "draft.mp4"
            p.write_bytes(b"x" * 50)
            up = DriveUploader(client=MockDriveClient())
            folders = up.ensure_project_folders("proj_test")
            r1 = up.upload(p, "draft", folders)
            r2 = up.upload(p, "draft", folders)
            self.assertEqual(r2.status, "reused_existing")
            self.assertEqual(r1.drive_id, r2.drive_id)

    def test_master_upload_blocked_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "master.mp4"
            p.write_bytes(b"x" * 10)
            up = DriveUploader(client=MockDriveClient())
            folders = up.ensure_project_folders("proj_test")
            with self.assertRaises(ValueError):
                up.upload(p, "master", folders, allow_master=False)


class TestPipeline(unittest.TestCase):
    def test_segmentation_structured_vi_script_only_speech(self):
        text = open(
            "/home/hatch/workspace/acceptance_loop/test_chiec_vi_trong_mua/script.txt",
            encoding="utf-8").read()
        seg = segment_script(text)
        # 10 spoken lines only — headers/metadata/action text never spoken
        self.assertEqual(len(seg.lines), 10)
        self.assertEqual(seg.characters, ["Minh", "Lan"])
        self.assertEqual(
            [l.speaker for l in seg.lines],
            ["narrator", "Minh", "narrator", "Lan", "Minh",
             "Lan", "narrator", "Lan", "Minh", "narrator"])
        joined = " ".join(l.text for l in seg.lines)
        for forbidden in ("KỊCH BẢN", "Bối cảnh", "Yêu cầu", "Premium"):
            self.assertNotIn(forbidden, joined)
        events = {e["event"] for e in seg.visual_events}
        self.assertIn("rain_start", events)

    def test_segmentation_no_hardcoded_story(self):
        seg = segment_script("Lan: Chào buổi sáng.\nMinh: Tôi mở cửa và bước ra ngoài trời mưa.")
        self.assertEqual(seg.characters, ["Lan", "Minh"])
        self.assertEqual(seg.lines[0].kind, "dialogue")
        self.assertEqual(seg.lines[1].kind, "dialogue")

    def test_narration_with_colon_is_not_dialogue(self):
        seg = segment_script("Minh cười và nói: Ối dồi ôi, thật không thể tin được.")
        self.assertEqual(seg.lines[0].kind, "narration")
        self.assertEqual(seg.lines[0].speaker, "narrator")
        self.assertEqual(seg.characters, [])
        events = {e["event"] for e in seg.visual_events}
        self.assertIn("character_reaction", events)

    def test_blocked_without_renderer_honest(self):
        result = run_production(
            "Lan: Chào buổi sáng.\nLan bước ra ngoài.",
            available_voices=("Lan", "narrator"),
            allow_estimated_timeline=True,
        )
        self.assertEqual(result.status, STATUS_BLOCKED)
        self.assertIn("Windows", result.blocked_reason)
        self.assertIn("timeline_seconds", result.manifest)

    def test_draft_ready_with_injected_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = Path(tmp) / "draft.mp4"
            draft.write_bytes(b"fake" * 10)

            def fake_render(req, manifest):
                return draft

            result = run_production(
                "Lan: Chào buổi sáng.",
                available_voices=("Lan", "narrator"),
                render_fn=fake_render,
                allow_estimated_timeline=True,
            )
            self.assertEqual(result.status, STATUS_DRAFT_READY)
            self.assertEqual(result.manifest["draft_mp4"], str(draft))


if __name__ == "__main__":
    unittest.main()
