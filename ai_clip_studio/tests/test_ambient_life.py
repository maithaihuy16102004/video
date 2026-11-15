"""Round-4 "hon" (ambient life): blinks, mutual gaze, listener nods,
idle amplitude, brow angles.

Diagnosis (2026-11-14, Mai: characters look like NPCs): the life
systems existed but were gated behind explicit script sentences --
blinks only from scripted BLINK events, gaze only during LOOK_AT /
dialogue, one frozen expression per shot, idle breathing below
notice. These tests pin the ambient behaviour: life that happens
whether or not the script asks for it.
"""

import math
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.animation.character_art import (
    EXPRESSIONS, _draw_face, draw_character_v4,
)
from ai_clip_studio.animation.primitives import idle, standing
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.product_renderer import _shot_action_events


def _package(names):
    return {
        "characters": [{"name": n, "id": f"c{i}"}
                       for i, n in enumerate(names)],
        "compiled_actions": {"events": []},
    }


class TestAmbientBlinks(unittest.TestCase):
    def test_blinks_scheduled_without_scripted_events(self):
        _, _, _, blinks, _, _ = _shot_action_events(
            _package(["Linh", "Ong Ba"]),
            {"directive_shot_id": "SC01_SH01", "start_sec": 0.0}, 6.0)
        self.assertEqual(set(blinks), {"Linh", "Ong Ba"})
        for times in blinks.values():
            self.assertGreater(len(times), 0)
            for t in times:
                self.assertGreaterEqual(t, 0.0)
                self.assertLess(t, 6.0)

    def test_blinks_deterministic(self):
        pkg = _package(["Linh"])
        shot = {"directive_shot_id": "SC01_SH01", "start_sec": 0.0}
        a = _shot_action_events(pkg, shot, 6.0)[3]
        b = _shot_action_events(pkg, shot, 6.0)[3]
        self.assertEqual(a, b)

    def test_blinks_differ_per_character(self):
        _, _, _, blinks, _, _ = _shot_action_events(
            _package(["Linh", "Ong Ba", "Be Nam"]),
            {"directive_shot_id": "SC01_SH01", "start_sec": 0.0}, 12.0)
        schedules = [tuple(v) for v in blinks.values()]
        self.assertEqual(len(set(schedules)), 3)

    def test_split_shots_sharing_a_directive_id_get_different_schedules(self):
        # R4-L1: segmentation-split shots share a directive id; the
        # seed must still distinguish the rendered shots.
        pkg = _package(["Linh"])
        a = _shot_action_events(
            pkg, {"directive_shot_id": "SC02_SH01", "start_sec": 10.0,
                  "index": 7}, 6.0)[3]
        b = _shot_action_events(
            pkg, {"directive_shot_id": "SC02_SH01", "start_sec": 13.5,
                  "index": 8}, 6.0)[3]
        self.assertNotEqual(a, b)

    def test_scripted_blink_preserved_and_ambient_suppressed_nearby(self):
        pkg = _package(["Linh"])
        pkg["compiled_actions"]["events"] = [{
            "shot_id": "SC01_SH01", "actor_id": "c0",
            "action_type": "BLINK", "start_time": 2.0, "end_time": 2.4,
            "required_pose": {"primitive": "face_only", "params": {}},
        }]
        _, _, _, blinks, _, _ = _shot_action_events(
            pkg, {"directive_shot_id": "SC01_SH01", "start_sec": 0.0},
            6.0)
        times = blinks["Linh"]
        self.assertIn(2.0, times)
        for t in times:
            if t != 2.0:
                self.assertGreater(abs(t - 2.0), 0.4)


class TestBrowAngles(unittest.TestCase):
    """Brow slant measured from the actual line calls _draw_face
    makes: the F4 clamp used to pin both ends of every raised brow
    to one line, drawing them perfectly flat."""

    def _brow_lines(self, expression):
        img = Image.new("RGB", (400, 400), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        ch = Stickman(height=560, name="T", hat="none", moustache=False)
        standing(ch, 200, 380)
        lines = []
        orig_line = draw.line

        def spy(xy, **kw):
            lines.append((list(xy), kw))
            return orig_line(xy, **kw)

        draw.line = spy
        params = dict(EXPRESSIONS[expression])
        _draw_face(draw, ch, 200, 150, "front", 0.0, params,
                   (20, 20, 40), None)
        draw.line = orig_line
        # Brow lines: short (~0.22r), above the eye line (y < 150).
        brows = [xy for xy, _ in lines
                 if len(xy) == 2 and xy[0][1] < 150 and xy[1][1] < 150
                 and abs(xy[1][0] - xy[0][0]) < 60]
        self.assertEqual(len(brows), 2)
        return brows

    def _slant(self, expression):
        # Inner end is the end nearer the face centre (x=200).
        slants = []
        for (x1, y1), (x2, y2) in self._brow_lines(expression):
            inner_y = y1 if abs(x1 - 200) < abs(x2 - 200) else y2
            outer_y = y2 if abs(x1 - 200) < abs(x2 - 200) else y1
            slants.append(outer_y - inner_y)
        return slants

    def test_neutral_brows_flat(self):
        for s in self._slant("neutral"):
            self.assertAlmostEqual(s, 0.0, delta=1.0)

    def test_angry_brows_slant_down_toward_centre(self):
        for s in self._slant("angry"):
            self.assertLess(s, -8.0)

    def test_sad_brows_slant_up_toward_centre(self):
        for s in self._slant("sad"):
            self.assertGreater(s, 4.0)

    def test_happy_brows_have_a_visible_slant(self):
        for s in self._slant("happy"):
            self.assertGreater(s, 2.0)

    def test_surprised_brows_raised_and_slanted(self):
        brows = self._brow_lines("surprised")
        neutral = self._brow_lines("neutral")
        # Raised: both ends above the neutral brow line.
        self.assertLess(max(y for _, y in brows[0]),
                        min(y for _, y in neutral[0]))
        for s in self._slant("surprised"):
            self.assertGreater(s, 2.0)

    def test_brows_stay_on_forehead(self):
        # No brow end above the hairline (-0.55r) or touching an eye.
        for name in EXPRESSIONS:
            for (x1, y1), (x2, y2) in self._brow_lines(name):
                for y in (y1, y2):
                    self.assertGreaterEqual(y, 150 - 0.55 * 95 - 1)
                    self.assertLess(y, 150 - 5)


class TestIdleAmplitude(unittest.TestCase):
    def test_idle_moves_visibly_over_four_seconds(self):
        ch = Stickman(height=560, name="T")
        standing(ch, 300, 500)
        fn = idle(ch, 4.0, 500)
        heads = []
        roots = []
        looks = []
        for i in range(97):
            fn(i / 24.0)
            heads.append(ch.joints()["head"])
            roots.append(ch.pose["root_x"])
            looks.append(ch.pose["head_look"])
        head_y_range = max(h[1] for h in heads) - min(h[1] for h in heads)
        root_range = max(roots) - min(roots)
        look_range = max(looks) - min(looks)
        # Round-4 amplitudes: bob 6 px, sway 10 px, drift 0.12.
        self.assertGreater(head_y_range, 4.0)
        self.assertGreater(root_range, 6.0)
        self.assertGreater(look_range, 0.08)


if __name__ == "__main__":
    unittest.main()
