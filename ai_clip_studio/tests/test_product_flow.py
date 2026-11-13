"""Regression tests for the product flow (luồng chuẩn).

Covers the mission's hard rules:
- No 15 s cap / no truncation: the V5.1 preview bug (hard-lock to 15 s,
  final line cut) must never recur in the improved code — the timeline
  is built from MEASURED voice durations and extended to fit.
- Fallback planner is always labelled, never presented as Gemini.
- Preflight is universal (no Episode01/Munich/Eiffel hardcoding).
- Language gate: English text in a vi-VN production hard-fails; no
  English voice fallback exists.
- SFX are deduplicated and tied to real cues (Eiffel excessive-SFX fix).
- The same data-driven renderer renders two different scripts with
  zero code changes.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_clip_studio.audio_events import AudioEvent  # noqa: E402
from ai_clip_studio.gemini_planner import _merge, resolve_plan  # noqa: E402
from ai_clip_studio.language_gate import (  # noqa: E402
    check_production_language, resolve_voice,
)
from ai_clip_studio.preflight import run_preflight  # noqa: E402
from ai_clip_studio.product_flow import (  # noqa: E402
    _end_card_seconds, build_frame_symlinks, dedupe_audio_events,
)
from ai_clip_studio.product_renderer import (  # noqa: E402
    PAUSE_AFTER_SEC, action_actor, plan_shots, render_product_video,
    render_storyboard_stills,
)
from ai_clip_studio.production_request import ProductionRequest  # noqa: E402
from ai_clip_studio.timeline import (  # noqa: E402
    TimelineError, TimelineLine, build_timeline, measure_wav_duration,
)


def _silent_wav(path: Path, seconds: float) -> Path:
    """A real WAV of an exact duration (silence) — for measuring."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(48000 * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(b"\x00\x00" * n)
    return path


def _tiny_package(char_name="An", jacket="#2E5FA3", setting="",
                  location="street", line_text="Xin chào, đây là một câu thử."):
    return {
        "characters": [{"name": char_name, "description": "",
                        "voice_hint": "giọng nam",
                        "jacket_color": jacket, "height_px": 560}],
        "locations": [setting],
        "scenes": [{
            "number": 1, "title": "Cảnh 1", "setting": setting,
            "action_text": "", "audio_text": "", "animation_reqs": [],
            "action_cues": [], "action_lead_sec": 0.0,
            "lines": [{"speaker": char_name, "kind": "dialogue",
                       "text": line_text}],
            "location": {"setting": setting, "location_keyword": location,
                         "mood": "warm", "time_of_day": "day"},
        }],
        "shots": [{"shot_id": "S1L1", "scene": 1, "kind": "dialogue",
                   "speaker": char_name, "text": line_text,
                   "action_cues": [], "estimated_sec": 4.0}],
        "audio_events": [],
    }


class TestNoTruncation(unittest.TestCase):
    """The V5.1 bug, as a regression test: voice longer than 15 s must
    extend the timeline, never cut the final line."""

    def test_timeline_extends_past_15s(self):
        lines = [TimelineLine(text=f"Câu thoại thứ {i} trong kịch bản dài.",
                              speaker="narrator", kind="narration",
                              duration_sec=3.2)
                 for i in range(6)]  # 6 x 3.2 = 19.2 s of voice
        timeline = build_timeline(lines)
        self.assertGreater(timeline.total_duration_sec, 15.0)
        self.assertTrue(timeline.all_measured)
        # The guard that V5.1 lacked: voice longer than the plan raises.
        with self.assertRaises(TimelineError):
            timeline.check_no_truncation(15.0, 19.2)
        timeline.check_no_truncation(timeline.total_duration_sec, 19.2)

    def test_measured_wav_durations_drive_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            wavs = [_silent_wav(Path(tmp) / f"line{i}.wav", 4.5)
                    for i in range(4)]
            durations = [measure_wav_duration(w) for w in wavs]
            self.assertTrue(all(abs(d - 4.5) < 0.05 for d in durations))
            lines = [TimelineLine(text="Câu thử.", speaker="narrator",
                                  kind="narration", duration_sec=d)
                     for d in durations]
            timeline = build_timeline(lines)
            self.assertGreater(timeline.total_duration_sec, 15.0)


class TestPlannerLabelling(unittest.TestCase):
    def test_fallback_is_labelled_when_no_key(self):
        env = dict(os.environ)
        env.pop("GEMINI_API_KEY", None)
        old = os.environ.get("GEMINI_API_KEY")
        os.environ.pop("GEMINI_API_KEY", None)
        try:
            package, label, detail = resolve_plan(
                "## CẢNH 01 — TEST\nNgười dẫn chuyện: \"Xin chào.\"\n")
            self.assertEqual(label, "fallback")
            self.assertIn("fallback", detail.lower())
            self.assertIn("Gemini", detail)
            self.assertEqual(len(package["scenes"]), 1)
        finally:
            if old is not None:
                os.environ["GEMINI_API_KEY"] = old

    def test_fallback_derives_hook_and_twist_from_script(self):
        """Preflight requires hook+twist; the fallback derives them
        from the script's own first/last lines (never invented)."""
        old = os.environ.get("GEMINI_API_KEY")
        os.environ.pop("GEMINI_API_KEY", None)
        try:
            package, label, detail = resolve_plan(
                "## CẢNH 01 — TEST\nNgười dẫn chuyện: \"Đêm mưa.\"\n"
                "An: \"Cháu ơi, cảm ơn cháu nhé.\"\n")
            self.assertEqual(label, "fallback")
            self.assertTrue(package.get("hook"))
            self.assertTrue(package.get("twist"))
            self.assertIn("Đêm mưa", package["hook"])
            self.assertIn("cảm ơn", package["twist"])
        finally:
            if old is not None:
                os.environ["GEMINI_API_KEY"] = old

    def test_gemini_merge_drops_invented_content(self):
        base = _tiny_package()
        parsed_lines = [{"speaker": "An", "kind": "dialogue",
                         "text": "Xin chào, đây là một câu thử."}]
        enrichment = {
            "characters": [
                {"name": "An", "description": "thanh niên áo xanh",
                 "voice_hint": "giọng nam", "template": "male"},
                {"name": "NhanVatBia", "description": "không có trong kịch bản",
                 "voice_hint": "giọng nam"},
            ],
            "shots": [
                {"scene": 1, "line_index": 1, "shot_type": "close_up",
                 "purpose": "real line"},
                {"scene": 1, "line_index": 99, "shot_type": "medium",
                 "purpose": "invented line"},
            ],
            "hook": "hook thật", "twist": "twist thật",
        }
        merged = _merge(base, enrichment, parsed_lines)
        names = [c["name"] for c in merged["characters"]]
        self.assertIn("An", names)
        self.assertNotIn("NhanVatBia", names)
        self.assertEqual(merged["characters"][0]["description"],
                         "thanh niên áo xanh")
        self.assertEqual(len(merged.get("gemini_shots", [])), 1)
        self.assertEqual(merged["hook"], "hook thật")


class TestUniversalPreflight(unittest.TestCase):
    def test_non_episode01_script_passes_generic_preflight(self):
        script = ("## CẢNH 01 — QUÁN CÀ PHÊ\n"
                  "Người dẫn chuyện: \"Sáng nay, Mai mở quán cà phê nhỏ.\"\n"
                  "Mai: \"Chào buổi sáng, mời vào.\"\n")
        request = ProductionRequest(script_text=script)
        from ai_clip_studio.pipeline import segment_script
        segmented = segment_script(script)
        timeline = build_timeline(segmented.lines)
        result = run_preflight(
            request, timeline=timeline,
            required_voices=("narrator", "Mai"),
            # available_voices are SPEAKER names with a resolvable vi
            # voice — not voice IDs (that mismatch failed preflight).
            available_voices=("narrator", "Mai"),
            script_hash_at_preflight=request.script_hash,
            allow_estimated_timeline=True)
        self.assertTrue(result.passed, result.failures())


class TestLanguageGate(unittest.TestCase):
    def test_vietnamese_lines_pass(self):
        result = check_production_language(
            "vi-VN",
            captions=["Hắn đã bán tháp Eiffel những hai lần."],
            narration_texts=["Đêm mưa, An chạy vào trạm xe buýt."])
        self.assertTrue(result["ok"], result)

    def test_english_lines_fail(self):
        result = check_production_language(
            "vi-VN",
            captions=["He sold the Eiffel Tower twice."],
            narration_texts=["Nobody stopped him."])
        self.assertFalse(result["ok"])
        self.assertGreaterEqual(len(result["violations"]), 1)

    def test_no_english_voice_fallback(self):
        with self.assertRaises(ValueError):
            resolve_voice("en-US", speaker="narrator")
        with self.assertRaises(ValueError):
            resolve_voice("", speaker="narrator")
        self.assertEqual(resolve_voice("vi-VN", speaker="narrator"),
                         "avocado_v2:MAI_01")


class TestSfxRestraint(unittest.TestCase):
    def test_repeated_events_deduplicated(self):
        events = [
            AudioEvent("rain_start", 0.0, "RAIN_AMBIENCE", "ambience", -20.0),
            AudioEvent("rain_start", 0.0, "RAIN_AMBIENCE", "ambience", -20.0),
            AudioEvent("rain_start", 0.0, "RAIN_AMBIENCE", "ambience", -20.0),
            AudioEvent("foot_contact", 2.0, "FOOTSTEP", "foley", -18.0),
            AudioEvent("foot_contact", 2.0, "FOOTSTEP", "foley", -18.0),
            AudioEvent("foot_contact", 5.0, "FOOTSTEP", "foley", -18.0),
        ]
        deduped = dedupe_audio_events(events)
        self.assertEqual(len(deduped), 3)  # rain x1, footstep@2s, footstep@5s


class TestShotPlanSync(unittest.TestCase):
    """Shot plan must match the timeline total (TechnicalGate tolerance
    is 0.6 s): action leads are split, never clamped away, and each
    line shot carries its 0.35 s beat. Also: one action shot per
    movement cue, each with its own actor, and the prop holder is
    tracked across the shot list."""

    def _pkg(self):
        loc = {"location_keyword": "rainy_street", "setting": "đường mưa",
               "mood": "warm", "time_of_day": "night"}
        return {
            "characters": [{"name": "Minh", "template": "male"},
                           {"name": "Lan", "template": "female"}],
            "scenes": [
                {"number": 1, "location": loc, "action_lead_sec": 4.2,
                 "action_cues": ["walk_fast", "stop", "bend_pick", "look"],
                 "action_text": "Minh đi nhanh, tránh vũng nước, "
                                "cúi nhặt chiếc ví.",
                 "lines": [
                     {"speaker": "narrator", "kind": "narration",
                      "text": "Một buổi tối mưa."},
                     {"speaker": "Minh", "kind": "dialogue",
                      "text": "Ủa, ví của ai đây?"}]},
                {"number": 2, "location": loc, "action_lead_sec": 5.1,
                 "action_cues": ["give", "take"],
                 "action_text": "Minh đưa ví cho Lan. Lan nhận ví.",
                 "lines": [
                     {"speaker": "Lan", "kind": "dialogue",
                      "text": "Ví của tôi! Cảm ơn anh."}]},
                {"number": 3, "location": loc, "action_lead_sec": 3.0,
                 "action_cues": ["put_away", "wave", "board"],
                 "action_text": "Lan cất ví vào túi, bước lên xe. "
                                "Minh vẫy tay chào.",
                 "lines": [
                     {"speaker": "narrator", "kind": "narration",
                      "text": "Chiếc xe buýt rời trạm."},
                     {"speaker": "Minh", "kind": "dialogue",
                      "text": "Tạm biệt nhé!"}]},
            ],
        }

    def _timeline(self):
        return [{"line_index": i + 1, "duration": d}
                for i, d in enumerate([3.0, 2.0, 4.0, 2.5, 3.5])]

    def test_action_shots_split_the_lead_exactly(self):
        shots = plan_shots(self._pkg(), self._timeline())
        for number, lead in ((1, 4.2), (2, 5.1), (3, 3.0)):
            got = sum(s["duration"] for s in shots
                      if s["scene"] == number and s["kind"] == "action")
            self.assertAlmostEqual(got, lead, places=1,
                                   msg=f"scene {number} lead lost")
        s1 = [s for s in shots if s["scene"] == 1
              and s["kind"] == "action"]
        self.assertEqual([s["action_cues"] for s in s1],
                         [["walk_fast"], ["bend_pick"]])
        self.assertEqual([s["actor"] for s in s1], ["Minh", "Minh"])
        # bend_pick is a full-body kneel: medium, never a tight insert
        # (a 3.4x object_insert on one kneeling subject cuts the head).
        self.assertEqual(
            [s["shot_type"] for s in s1], ["tracking", "medium"])
        s3 = [s for s in shots if s["scene"] == 3
              and s["kind"] == "action"]
        self.assertEqual([s["action_cues"] for s in s3],
                         [["put_away"], ["wave"], ["board"]])
        self.assertEqual([s["actor"] for s in s3],
                         ["Lan", "Minh", "Lan"])

    def test_line_shot_carries_pause_and_voice_duration(self):
        shots = plan_shots(self._pkg(), self._timeline())
        lines = [s for s in shots if s["kind"] in ("narration", "dialogue")]
        self.assertEqual(len(lines), 5)
        for shot, voice in zip(lines, [3.0, 2.0, 4.0, 2.5, 3.5]):
            self.assertAlmostEqual(shot["duration"],
                                   voice + PAUSE_AFTER_SEC, places=2)
            self.assertAlmostEqual(shot["voice_duration"], voice, places=2)

    def test_video_duration_matches_timeline_total(self):
        pkg = self._pkg()
        shots = plan_shots(pkg, self._timeline())
        lines = [TimelineLine(speaker="x", kind="narration", text="t",
                              duration_sec=e["duration"],
                              pause_after_sec=PAUSE_AFTER_SEC)
                 for e in self._timeline()]
        action_seconds = sum(float(s.get("action_lead_sec") or 0.0)
                             for s in pkg["scenes"])
        timeline = build_timeline(lines, action_seconds=action_seconds)
        video = sum(s["duration"] for s in shots) + 0.5
        self.assertAlmostEqual(video, timeline.total_duration_sec,
                               delta=0.1)

    def test_prop_holder_transitions(self):
        shots = plan_shots(self._pkg(), self._timeline())
        holders = [(s.get("action_cues"), s.get("prop_holder"))
                   for s in shots]
        # bend_pick -> Minh holds; give -> Lan holds; put_away -> hidden.
        self.assertIn((["bend_pick"], "Minh"), holders)
        self.assertIn((["give"], "Lan"), holders)
        self.assertIn((["put_away"], None), holders)
        # Dialogue in scene 1: Minh holds; scene 2 (after the give):
        # Lan holds; scene 3 (after put_away): hidden.
        s1_line = next(s for s in shots if s["scene"] == 1
                       and s["kind"] == "dialogue")
        self.assertEqual(s1_line["prop_holder"], "Minh")
        s2_line = next(s for s in shots if s["scene"] == 2
                       and s["kind"] == "dialogue")
        self.assertEqual(s2_line["prop_holder"], "Lan")
        s3_line = next(s for s in shots if s["scene"] == 3
                       and s["kind"] == "dialogue")
        self.assertIsNone(s3_line["prop_holder"])

    def test_put_away_actor_uses_verb(self):
        text = "Lan cất ví vào túi, bước lên xe. Minh vẫy tay chào."
        self.assertEqual(
            action_actor(text, ["put_away"], ["Minh", "Lan"]), "Lan")

    def test_characters_visible_only_after_introduction(self):
        shots = plan_shots(self._pkg(), self._timeline())
        s1 = [s for s in shots if s["scene"] == 1]
        self.assertTrue(all(s["visible"] == ["Minh"] for s in s1),
                        [s["visible"] for s in s1])
        s2 = [s for s in shots if s["scene"] == 2]
        self.assertTrue(all(s["visible"] == ["Minh", "Lan"] for s in s2))


    def test_kneel_pick_head_not_cut_at_edge(self):
        """A lone kneeling subject must be framed, not edge-flush:
        the head must be whole AND the jacket/back leg must not be
        cut at the frame edge. v11 fixed the head (head_y = head
        top) but the kneel lunges ~250 px behind the root, so the
        jacket was cut at x=0 — the staging is now clamped inboard
        and the subject box includes the feet."""
        from ai_clip_studio.product_renderer import _render_shot
        from PIL import Image
        pkg = self._pkg()
        shots = plan_shots(pkg, self._timeline())
        bend = next(s for s in shots if s["kind"] == "action"
                    and s.get("action_cues") == ["bend_pick"])
        with tempfile.TemporaryDirectory() as tmp:
            _render_shot({"shot": dict(bend, index=1), "package": pkg,
                          "out_dir": Path(tmp), "still_only": True})
            img = Image.open(Path(tmp) / "shot_001" / "still.png"
                             ).convert("RGB")
        px = img.load()
        # The face fill is exactly (247, 243, 232); rain streaks are
        # 1-2 px wide, the head is hundreds of px wide — look for a
        # wide run of face colour, not isolated bright pixels.
        FACE = (247, 243, 232)
        runs = []
        for y in range(100, 700, 2):
            run = 0
            start = 0
            for x in range(1920):
                if px[x, y] == FACE:
                    if run == 0:
                        start = x
                    run += 1
                else:
                    if run > 100:
                        runs.append((start, start + run, y))
                    run = 0
        self.assertTrue(runs, "no face found in the still")
        left = min(r[0] for r in runs)
        right = max(r[1] for r in runs)
        # The head must be fully inside the frame with a margin.
        self.assertGreater(left, 100,
                           f"head cut at left edge (left={left})")
        self.assertLess(right, 1820)
        # The jacket (Minh's blue #2E5FA3) must not touch the left
        # edge either — the kneel lunge stays in frame.
        jacket_xs = [x for x in range(1920) for y in range(1080)
                     if px[x, y] == (46, 95, 163)]
        self.assertTrue(jacket_xs, "jacket not found in the still")
        self.assertGreater(min(jacket_xs), 20,
                           f"jacket cut at left edge (min_x={min(jacket_xs)})")
        prop = [(x, y) for y in range(700, 1080, 2)
                for x in range(0, 1920, 2)
                if px[x, y] == (138, 90, 43)]
        self.assertTrue(prop, "wallet prop not visible in the still")


class TestFramingHeadNotCut(unittest.TestCase):
    """v9 defect: medium / reaction / give / board shots cut the
    characters' heads at the top of the frame. Root cause: the
    subject box passed the head JOINT (centre of the head circle)
    as head_y, but validate_framing treats head_y as the TOP of the
    subject and the drawn head extends head_r (~133 px) above the
    joint. The fix passes the true drawn head top; safe_frame then
    steps the scale down until the whole head fits."""

    def test_two_character_shots_keep_heads_whole(self):
        pkg = {
            "characters": [
                {"name": "An", "description": "", "voice_hint": "giọng nam",
                 "jacket_color": "#2E5FA3", "height_px": 560},
                {"name": "Lan", "description": "", "voice_hint": "giọng nữ",
                 "jacket_color": "#3FA36B", "height_px": 520},
            ],
            "locations": [""], "audio_events": [],
            "scenes": [{
                "number": 1, "title": "Cảnh 1", "setting": "",
                "action_text": "", "audio_text": "", "animation_reqs": [],
                "action_cues": ["give"], "action_lead_sec": 2.0,
                "lines": [
                    {"speaker": "An", "kind": "dialogue",
                     "text": "Cầm lấy đi."},
                    {"speaker": "Lan", "kind": "dialogue",
                     "text": "Cảm ơn anh."},
                ],
                "location": {"setting": "", "location_keyword": "street",
                             "mood": "warm", "time_of_day": "day"},
            }],
            "shots": [
                {"shot_id": "S1L1", "scene": 1, "kind": "dialogue",
                 "speaker": "An", "text": "Cầm lấy đi.",
                 "action_cues": [], "estimated_sec": 2.0},
                {"shot_id": "S1L2", "scene": 1, "kind": "dialogue",
                 "speaker": "Lan", "text": "Cảm ơn anh.",
                 "action_cues": [], "estimated_sec": 2.0},
            ],
        }
        timeline = [{"line_index": 1, "duration": 2.0},
                    {"line_index": 2, "duration": 2.0}]
        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image

            stills = render_storyboard_stills(
                pkg, timeline, Path(tmp) / "stills")
            self.assertTrue(stills, "no stills rendered")
            FACE = (247, 243, 232)
            for st in stills:
                img = Image.open(st["still"]).convert("RGB")
                px = img.load()
                runs = []
                for y in range(0, 700, 2):
                    run = 0
                    start = 0
                    for x in range(1920):
                        if px[x, y] == FACE:
                            if run == 0:
                                start = x
                            run += 1
                        else:
                            if run > 100:
                                runs.append((start, start + run, y))
                            run = 0
                if st["shot_type"] == "object_insert":
                    # An insert frames the PROP, not a face: the wallet
                    # must be visible (wide run of wallet brown).
                    prop = [(x, y) for y in range(0, 1080, 2)
                            for x in range(0, 1920, 2)
                            if px[x, y] == (138, 90, 43)]
                    self.assertTrue(prop,
                                    "wallet prop not visible in insert")
                    continue
                self.assertTrue(runs,
                                f"no face in {st['shot_type']} still")
                top = min(r[2] for r in runs)
                left = min(r[0] for r in runs)
                right = max(r[1] for r in runs)
                self.assertGreater(
                    top, 10,
                    f"{st['shot_type']}: head cut at top (top={top})")
                self.assertGreater(left, 50)
                self.assertLess(right, 1870)
                # Shot language must survive: a close_up frames the
                # face, it must not fall back to a 1.0x wide shot
                # (v10: all 21 shots were 1.0x).
                if st["shot_type"] == "close_up":
                    self.assertGreater(
                        st.get("applied_scale", 1.0), 1.0,
                        "close_up fell back to 1.0x wide")


class TestTwoScriptsSamePipeline(unittest.TestCase):
    """The same data-driven renderer renders two different scripts
    with zero code changes."""

    def test_two_different_packages_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = []
            for i, (name, jacket, location, text) in enumerate([
                    ("An", "#2E5FA3", "street",
                     "Đêm mưa, An chạy vào trạm xe buýt."),
                    ("Lustig", "#4A4A3C", "eiffel_tower",
                     "Hắn đã bán tháp Eiffel những hai lần.")]):
                pkg = _tiny_package(char_name=name, jacket=jacket,
                                    setting="Paris" if i else "",
                                    location=location, line_text=text)
                timeline = [{"line_index": 1, "duration": 2.0}]
                out = render_product_video(
                    pkg, timeline, Path(tmp) / f"job{i}", workers=1)
                self.assertGreater(out["n_frames"], 0)
                self.assertEqual(out["violations"], [])
                results.append(out)
            self.assertEqual(len(results), 2)
            # Different stories -> different shot plans, both real frames.
            self.assertNotEqual(
                results[0]["shots"][0]["location_keyword"],
                results[1]["shots"][0]["location_keyword"])


class TestFrameCountExact(unittest.TestCase):
    """The mux must produce exactly the rendered frame count at 24 fps
    (TechnicalGate.frames_rendered_real demands total_frames ==
    round(duration x fps)). Two earlier failures: per-shot rounding
    lost frames, and the concat demuxer added a phantom frame. Now:
    cumulative-clock frame counts + audio-tail frames + image2 mux."""

    def test_frame_symlinks_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.png"
            src.write_bytes(b"x")
            pattern = build_frame_symlinks(
                [str(src), str(src), str(src)], Path(tmp) / "flat")
            self.assertTrue(pattern.endswith("f%04d.png"))
            flat = Path(tmp) / "flat"
            self.assertEqual(sorted(p.name for p in flat.glob("f*.png")),
                             ["f0000.png", "f0001.png", "f0002.png"])
            self.assertTrue((flat / "f0001.png").is_symlink())

    def test_render_frame_count_is_exact(self):
        pkg = _tiny_package()
        with tempfile.TemporaryDirectory() as tmp:
            out = render_product_video(
                pkg, [{"line_index": 1, "duration": 2.0}],
                Path(tmp) / "job", workers=1)
            # 1 line shot: 2.0 s voice + 0.35 s beat = 2.35 s, plus the
            # 0.5 s audio tail held on the final frame.
            self.assertEqual(out["n_frames"],
                             round(2.35 * 24) + round(0.5 * 24))
            self.assertEqual(
                out["n_frames"],
                round(out["duration_sec"] * 24),
                "frame count must equal round(duration x fps)")


class TestRenderUsesFrozenShots(unittest.TestCase):
    """The renderer renders the FROZEN plan verbatim (Ep1 2026-11-13:
    the internal re-plan diverged 5.2 s from the frozen timeline, so
    the mux's -t cut the final line's audio and the verifier could
    not find it)."""

    def test_passed_shots_win_over_replan(self):
        pkg = _tiny_package()
        timeline = [{"line_index": 1, "duration": 2.0}]
        shots = plan_shots(pkg, timeline)
        # Stretch the first shot the way the frozen stage-7 plan
        # differs from a fresh re-plan; the render must follow
        # the passed plan, not recompute it.
        shots[0] = dict(shots[0],
                        duration=round(shots[0]["duration"] + 1.0, 3))
        expected = (round(sum(s["duration"] for s in shots) * 24)
                    + round(0.5 * 24))
        with tempfile.TemporaryDirectory() as tmp:
            out = render_product_video(pkg, timeline, Path(tmp) / "job",
                                       workers=1, shots=shots)
        self.assertEqual(out["shots"][0]["duration"],
                         shots[0]["duration"])
        self.assertEqual(out["n_frames"], expected)
        # The caller's plan is not mutated (index/n_frames are
        # written to copies).
        self.assertNotIn("index", shots[0])
        self.assertNotIn("n_frames", shots[0])

    def test_storyboard_stills_use_frozen_shots(self):
        pkg = _tiny_package()
        timeline = [{"line_index": 1, "duration": 2.0}]
        shots = plan_shots(pkg, timeline)
        shots[0] = dict(shots[0],
                        duration=round(shots[0]["duration"] + 1.0, 3))
        with tempfile.TemporaryDirectory() as tmp:
            stills = render_storyboard_stills(
                pkg, timeline, Path(tmp) / "board", shots=shots)
        self.assertEqual(len(stills), len(shots))
        self.assertEqual(stills[0]["duration"], shots[0]["duration"])


class TestEndCardSeconds(unittest.TestCase):
    """Stage 3 integration: the timeline must cover the end card."""

    def test_duration_sec_preferred(self):
        self.assertEqual(
            _end_card_seconds({"v1_end_card": {"duration_sec": 3.0,
                                               "duration": "3s"}}), 3.0)

    def test_duration_string_parsed(self):
        self.assertEqual(
            _end_card_seconds({"v1_end_card": {"duration": "4s"}}), 4.0)
        self.assertEqual(
            _end_card_seconds({"end_card": {"duration": 2.5}}), 2.5)

    def test_no_card_is_zero(self):
        self.assertEqual(_end_card_seconds({}), 0.0)
        self.assertEqual(_end_card_seconds({"v1_end_card": None}), 0.0)
        self.assertEqual(
            _end_card_seconds({"v1_end_card": {"duration": "bogus"}}),
            0.0)
        self.assertEqual(
            _end_card_seconds({"v1_end_card": {"duration_sec": -1}}), 0.0)


if __name__ == "__main__":
    unittest.main()
