"""Light payoff vocabulary + burst effects (round-2 system 5).

A prop state-change sentence -- the core cracks, the machine
activates, the prop emits light -- must compile to a real semantic
event whose character presents the prop steady while the renderer
paints an event-driven glow burst on it. Before this, no such
vocabulary existed (CRACK/ACTIVATE/EMIT were UNSUPPORTED) and the
only glow was the held-prop ramp, which cannot mark a payoff
moment: the light payoff had no beat.
"""

import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import (
    _classify, _disambiguate_semantic, _normalize)
from ai_clip_studio.animation.primitives import (
    Stickman, pose_at_completion, present_prop, standing)
from ai_clip_studio.semantic_contracts import SEMANTIC_ACTION_TYPES


class TestPayoffVocabulary(unittest.TestCase):
    def _type(self, sentence):
        return _classify(_normalize(sentence), {})[0]

    def test_crack_phrases(self):
        for s in ("Lõi đá nứt ra, ánh sáng tỏa ra.",
                  "Chiếc bình vỡ vụn.",
                  "Tường rạn nứt.",
                  "Viên đá vỡ làm đôi."):
            with self.subTest(sentence=s):
                self.assertEqual(self._type(s), "CRACK")

    def test_activate_phrases(self):
        for s in ("Tôi kích hoạt cỗ máy.",
                  "Bà Tư khởi động lò rèn.",
                  "Anh ấy bật máy lên.",
                  "Cô ấy mở máy ra.",
                  "Người thợ vận hành cỗ máy."):
            with self.subTest(sentence=s):
                self.assertEqual(self._type(s), "ACTIVATE")

    def test_emit_phrases(self):
        for s in ("Lõi đá phát sáng.",
                  "Chiếc nhẫn sáng lên.",
                  "Viên ngọc tỏa sáng.",
                  "Ngọn đuốc bừng sáng."):
            with self.subTest(sentence=s):
                self.assertEqual(self._type(s), "EMIT")

    def test_negatives_stay_out(self):
        # Bare "vỡ"/"bật"/"sáng" must never fire the payoff rules.
        self.assertIsNone(self._type("Cô ấy vỡ òa trong nước mắt."))
        self.assertIsNone(self._type("Đứa bé bật khóc."))
        # "Sáng mai" is a time expression; the sentence is a walk.
        self.assertEqual(self._type("Sáng mai tôi đi chợ."), "WALK")
        self.assertNotEqual(self._type("Sáng mai tôi đi chợ."),
                            "EMIT")
        # Wallet/door opens keep their own types.
        self.assertEqual(self._type("Tôi mở ví ra xem."),
                         "OPEN_WALLET")
        self.assertEqual(self._type("Tôi mở cửa sổ."), "OPEN")
        # Phenomenon subjects route to ENVIRONMENT, not EMIT: a
        # lightning bolt in the sky is weather, not a prop payoff.
        # (The held bolt's glow is the energy-glow ramp.)
        atype, category, _n, _i = _classify(
            _normalize("Tia sét sáng rực lên."), {})
        self.assertIsNone(atype)
        self.assertEqual(category, "ENVIRONMENT")

    def test_semantic_resolution(self):
        for verb in ("CRACK", "ACTIVATE", "EMIT"):
            with self.subTest(verb=verb):
                sem, _rule, conf = _disambiguate_semantic(
                    verb, "x", {"mechanism": "rule"})
                self.assertEqual(sem, verb)
                self.assertEqual(conf, 1.0)
        for verb in ("CRACK", "ACTIVATE", "EMIT"):
            self.assertIn(verb, SEMANTIC_ACTION_TYPES)


class TestPresentProp(unittest.TestCase):
    def _completed(self, hand):
        char = Stickman(height=560, name="Test")
        standing(char, 500.0, 900.0)
        pose_at_completion(present_prop(char, 1.0, hand=hand),
                           char, 1.0)
        return char.joints()

    def test_single_hand_presents_at_chest(self):
        joints = self._completed("r")
        hand = joints["hand_r"]
        head = joints["head"]
        hip = joints["hip"]
        # Forward of the torso, between head and hip height.
        self.assertGreater(hand[0], hip[0] + 60.0)
        self.assertGreater(hand[1], head[1])
        self.assertLess(hand[1], hip[1])
        # The other hand hangs.
        self.assertGreater(joints["hand_l"][1], hip[1] - 40.0)

    def test_both_hands_flank_the_hold(self):
        joints = self._completed("both")
        left = joints["hand_l"]
        right = joints["hand_r"]
        spread = abs(right[0] - left[0])
        self.assertAlmostEqual(spread, 24.0, delta=2.0)
        self.assertAlmostEqual(left[1], right[1], delta=2.0)

    def test_hold_is_stable(self):
        char = Stickman(height=560, name="Test")
        standing(char, 500.0, 900.0)
        fn = present_prop(char, 1.0, hand="both")
        fn(0.6)
        mid = char.joints()["hand_r"]
        fn(1.0)
        end = char.joints()["hand_r"]
        self.assertAlmostEqual(mid[0], end[0], delta=1.0)
        self.assertAlmostEqual(mid[1], end[1], delta=1.0)

    def test_bad_hand_rejected(self):
        char = Stickman(height=560, name="Test")
        with self.assertRaises(ValueError):
            present_prop(char, 1.0, hand="x")




# ---------------------------------------------------------------------------
# Burst envelopes, records, crack geometry, reaction math (B2/B3).
# ---------------------------------------------------------------------------

import tempfile

from PIL import Image

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.effects import (
    REACTION_PAINT_FLOOR, burst_color_radius, burst_envelope,
    burst_record, crack_lines, names_set_piece, strike_reaction)
from ai_clip_studio.lighting import paint_energy_glow
from ai_clip_studio.product_renderer import (
    _render_shot, plan_shots)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.tests.test_insert_two_pass import (
    EXAMPLES, _zeus_package_and_shots)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / \
    "unseen_garden_key.studio.md"


def _warmth(img, box):
    px = img.crop(box).convert("RGB")
    data = list(px.getdata())
    return sum(r - b for r, _g, b in data) / max(len(data), 1)


def _shot_camera(result):
    return PerspectiveCamera(tuple(result["camera_position"]),
                             tuple(result["camera_target"]))


class TestBurstEnvelope(unittest.TestCase):
    def test_crack_silent_then_burst_then_leak(self):
        self.assertEqual(burst_envelope("CRACK", 0.0), 0.0)
        self.assertEqual(burst_envelope("CRACK", 0.59), 0.0)
        self.assertGreater(burst_envelope("CRACK", 0.64), 0.4)
        self.assertEqual(burst_envelope("CRACK", 0.68), 1.0)
        sustain = burst_envelope("CRACK", 1.0)
        self.assertAlmostEqual(sustain, 0.55, delta=0.01)

    def test_activate_ramps_and_sustains(self):
        self.assertEqual(burst_envelope("ACTIVATE", 0.0), 0.0)
        mid = burst_envelope("ACTIVATE", 0.5)
        self.assertGreater(mid, 0.3)
        self.assertLess(mid, 0.8)
        self.assertEqual(burst_envelope("ACTIVATE", 0.9), 1.0)
        self.assertEqual(burst_envelope("ACTIVATE", 1.0), 1.0)

    def test_emit_pulses_then_holds_warm(self):
        self.assertEqual(burst_envelope("EMIT", 0.0), 0.0)
        self.assertEqual(burst_envelope("EMIT", 0.5), 1.0)
        self.assertAlmostEqual(burst_envelope("EMIT", 1.0), 0.6,
                               delta=0.01)

    def test_out_of_span_and_unknown_are_dark(self):
        for atype in ("CRACK", "ACTIVATE", "EMIT"):
            self.assertEqual(burst_envelope(atype, -0.1), 0.0)
            self.assertEqual(burst_envelope(atype, 1.1), 0.0)
        self.assertEqual(burst_envelope("WALK", 0.5), 0.0)
        self.assertEqual(burst_envelope("SHIELD", 0.5), 0.0)


class TestBurstRecord(unittest.TestCase):
    def test_record_paints_and_scales_radius(self):
        rec = burst_record("prop_x", 100.0, 100.0, 0.5,
                           (255, 200, 90), 240.0)
        self.assertEqual(rec["radius"], 120.0)
        self.assertEqual(rec["source_position"], (100.0, 100.0))
        img = Image.new("RGB", (300, 300), (10, 10, 10))
        paint_energy_glow(img, rec)  # must validate + paint
        self.assertGreater(_warmth(img, (50, 50, 150, 150)), 0.0)

    def test_color_radius_prefers_energy_spec(self):
        color, radius = burst_color_radius(
            {"energy": {"color": "#112233", "radius_px": 100.0}})
        self.assertEqual(color, (0x11, 0x22, 0x33))
        self.assertEqual(radius, 100.0)
        color, radius = burst_color_radius({})
        self.assertEqual(color, (255, 200, 90))
        self.assertEqual(radius, 240.0)


class TestCrackLines(unittest.TestCase):
    def test_stable_deterministic_and_inside(self):
        bbox = (100.0, 100.0, 176.0, 150.0)
        first = crack_lines(bbox, "prop_key")
        second = crack_lines(bbox, "prop_key")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        for line in first:
            self.assertEqual(len(line), 5)
            for x, y in line:
                self.assertGreaterEqual(x, bbox[0])
                self.assertLessEqual(x, bbox[2])
                self.assertGreaterEqual(y, bbox[1])
                self.assertLessEqual(y, bbox[3])
        other = crack_lines(bbox, "prop_stone")
        self.assertNotEqual(first, other)


class TestNamesSetPiece(unittest.TestCase):
    def test_names(self):
        for text in ("tôi kích hoạt lò rèn", "khởi động cỗ máy",
                     "bật lò lên", "mở máy ra"):
            with self.subTest(text=text):
                self.assertTrue(names_set_piece(text))
        self.assertTrue(names_set_piece("Lò rèn bùng lên"))

    def test_no_names(self):
        for text in ("cầm búa lên", "đi chợ", "mở ví ra xem",
                     "lõi đá nứt ra"):
            with self.subTest(text=text):
                self.assertFalse(names_set_piece(text))


class TestStrikeReaction(unittest.TestCase):
    def test_pulse_at_contact_then_decay(self):
        moments = [1.0, 1.9]
        self.assertEqual(strike_reaction(0.5, moments), 0.0)
        self.assertEqual(strike_reaction(1.0, moments), 1.0)
        self.assertLess(strike_reaction(1.35, moments), 0.4)
        self.assertEqual(strike_reaction(1.9, moments), 1.0)

    def test_sparks_gated_to_contact_frames(self):
        # Round-7 (R6-D3): sparks burst 0.24 s after contact while
        # the hammer head was already up-left of the anvil. The
        # visible pulse is ~4 frames: strong at 2 frames, below
        # the paint floor by 6 frames.
        moments = [1.0]
        self.assertGreater(strike_reaction(1.0 + 2 / 24.0, moments),
                           REACTION_PAINT_FLOOR)
        self.assertLess(strike_reaction(1.0 + 6 / 24.0, moments),
                        REACTION_PAINT_FLOOR)


def _compile_package(package, n_lines):
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(n_lines)])
    for i, s in enumerate(shots):
        s["index"] = i
    spans = {}
    clock = 0.0
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            span = spans.setdefault(str(did), [clock, clock])
            span[1] = clock + float(s["duration"])
        clock += float(s["duration"])
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None,
    }
    return shots


def _frame_path(out_dir, index, frame):
    return Path(out_dir) / f"shot_{index:03d}" / f"f{frame:04d}.png"


class TestCrackBurstRenders(unittest.TestCase):
    def test_burst_paints_and_warms_the_key(self):
        # The crack goes in SC01_SH03, after the pickup: the key is
        # held there (a pocketed key bursts nothing, by design).
        text = FIXTURE.read_text(encoding="utf-8")
        anchor = "* Bà Tư cúi xuống nhặt chìa khóa lên."
        text = text.replace(
            anchor,
            anchor + "\n* Chìa khóa nứt ra, ánh sáng tỏa ra.", 1)
        package = adapt_document(parse_studio_script_v1(text))
        shots = _compile_package(package, 5)
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC01_SH03")
        cracks = [e for e in package["compiled_actions"]["events"]
                  if e["action_type"] == "CRACK"
                  and e.get("shot_id") == "SC01_SH03"]
        self.assertEqual(len(cracks), 1)
        self.assertEqual(cracks[0]["prop_id"], "prop_key")
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot(
                {"shot": shot, "package": package, "out_dir": tmp})
            self.assertNotIn(cracks[0]["action_id"],
                             result["action_dispatch_fallback"])
            records = [r for r in result["effect_records"]
                       if r["effect"] == "CRACK"]
            self.assertEqual(len(records), 1)
            self.assertGreaterEqual(records[0]["peak_intensity"],
                                    0.9)
            # Pixels: the key's neighbourhood warms from the
            # pre-crack frames to the burst peak.
            start = float(cracks[0]["start_time"])
            end = float(cracks[0]["end_time"])
            t0 = float(shot.get("start_sec", start))
            peak_t = start + 0.7 * (end - start)
            peak_f = int((peak_t - t0) * 24)
            tel = result["grip_telemetry"]
            draws = [d for d in tel[peak_f]["draws"]
                     if d.get("pid") == "prop_key"]
            self.assertTrue(draws, "no key draw at the peak frame")
            kx, ky = draws[0]["x"], draws[0]["y"]
            box = (kx - 60, ky - 60, kx + 60, ky + 60)
            before = _warmth(
                Image.open(_frame_path(tmp, shot["index"], 5)), box)
            peak = _warmth(
                Image.open(
                    _frame_path(tmp, shot["index"], peak_f)), box)
            self.assertGreater(peak, before + 5.0,
                               f"warmth {before:.1f} -> {peak:.1f}")


class TestSetPieceReactionRenders(unittest.TestCase):
    def test_strike_fires_the_reaction(self):
        package, shots = _zeus_package_and_shots()
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC08_SH01")
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot(
                {"shot": shot, "package": package, "out_dir": tmp})
            records = [r for r in result["effect_records"]
                       if r["effect"] == "SET_PIECE_REACTION"]
            self.assertEqual(len(records), 1)
            self.assertGreaterEqual(records[0]["peak_intensity"],
                                    0.5)
            self.assertGreater(records[0]["frames"], 0)
            # Pixels: the furnace wall warms just after a strike
            # contact moment vs before the first strike. The strike
            # moments come from hammer_strike_times (STRIKE_U 0.6:
            # the first contact is 0.54 s into the event, NOT 0.45).
            # The box is the wall ABOVE the furnace mouth: inside
            # the flare wash, and no character ever reaches it, so
            # the rise can only be the reaction overlay (an earlier
            # version measured a box the swinging arm entered and
            # passed for the wrong reason).
            from ai_clip_studio.animation.primitives import (
                hammer_cycles, hammer_strike_times)
            strikes = [e for e in
                       package["compiled_actions"]["events"]
                       if e["action_type"] == "HAMMER_STRIKE"
                       and e.get("shot_id") == "SC08_SH01"]
            self.assertTrue(strikes)
            start = float(strikes[0]["start_time"])
            end = float(strikes[0]["end_time"])
            first = hammer_strike_times(
                end - start, hammer_cycles(end - start))[0]
            t0 = float(shot.get("start_sec", start))
            strike_f = int((start + first + 0.08 - t0) * 24)
            cam = _shot_camera(result)
            fx, fy, _s, vis = cam.project((-3.2, 0.9, -6.5),
                                          1920, 1080)
            self.assertTrue(vis)
            box = (fx - 100, fy - 200, fx + 100, fy - 60)
            before = _warmth(
                Image.open(_frame_path(tmp, shot["index"], 2)), box)
            at = _warmth(
                Image.open(
                    _frame_path(tmp, shot["index"], strike_f)), box)
            self.assertGreater(at, before + 2.0,
                               f"furnace warmth {before:.1f} -> "
                               f"{at:.1f} (frame {strike_f})")

    def test_activate_sustains_the_reaction(self):
        text = (EXAMPLES
                / "zeus_ep01_fall_of_cronus.studio.md").read_text(
                    encoding="utf-8")
        anchor = "* Một người giữ vật liệu."
        self.assertEqual(text.count(anchor), 1)
        text = text.replace(
            anchor, anchor + "\n* Tôi kích hoạt lò rèn.", 1)
        package = adapt_document(parse_studio_script_v1(text))
        shots = _compile_package(package, 40)
        shot = next(s for s in shots
                    if s.get("directive_shot_id") == "SC08_SH01")
        acts = [e for e in package["compiled_actions"]["events"]
                if e["action_type"] == "ACTIVATE"
                and e.get("shot_id") == "SC08_SH01"]
        self.assertEqual(len(acts), 1)
        with tempfile.TemporaryDirectory() as tmp:
            result = _render_shot(
                {"shot": shot, "package": package, "out_dir": tmp})
            records = [r for r in result["effect_records"]
                       if r["effect"] == "SET_PIECE_REACTION"]
            self.assertEqual(len(records), 1)
            # The activation sustains the reaction at full: the
            # peak must reach the ACTIVATE sustain, not just a
            # strike pulse.
            self.assertGreaterEqual(records[0]["peak_intensity"],
                                    0.95)


if __name__ == "__main__":
    unittest.main()
