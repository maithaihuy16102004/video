"""Round 16 (L02-D1): birds-eye character path. The environment
pitches with the camera elevation, but ``draw_character_v4`` drew an
upright billboard at every angle -- under a 62 deg birds-eye camera
An stood frontal with a full face while the ground read top-down.
The fix is a drawn-space projection (the _squash precedent): every
drawn point's height above the character's ground line foreshortens
by cos(elevation) toward the feet, the joint map is untouched, and
at or above 45 deg the head renders from the top (hair crown, no
face). A plain vertical squash WITHOUT the head-top switch is the
defect, not the fix, so the face switch is asserted directly.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.animation.character_art import (
    STYLE_LOCK, _draw_tail, _shade, draw_character_v4)
from ai_clip_studio.animation.rig import Stickman
from ai_clip_studio.product_renderer import _render_shot
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parents[2]
JOB = AGENT / "jobs" / "req_80be4e5ca4dd"

W, H = 1920, 1080
FACE_FILL = tuple(int(STYLE_LOCK["face_fill"][i:i + 2], 16)
                  for i in (1, 3, 5))
INK = tuple(int(STYLE_LOCK["ink"][i:i + 2], 16) for i in (1, 3, 5))


def _standing_char():
    ch = Stickman(height=560, name="test_char", hat=None,
                  moustache=False)
    ch.suit = "#172033"
    ch.skin = "#F0C8A0"
    ch.set_pose(root_x=960, root_y=920 - 241, facing=1,
                thigh_l=0.1, thigh_r=-0.1, knee_l=0.15, knee_r=0.15,
                arm_l=0.1, arm_r=0.1, elbow_l=0.2, elbow_r=0.2,
                bob=0.0, torso_lean=0.0, head_look=0.0)
    return ch


def _draw(elevation_deg, view="profile", char=None):
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")
    ch = char if char is not None else _standing_char()
    joints = draw_character_v4(
        d, ch, expression="neutral", view=view,
        ground_kind="stone", elevation_deg=elevation_deg)
    return img, joints, ch


def _dark_bbox(img):
    a = np.asarray(img).astype(int).sum(axis=2)
    ys, xs = np.where(a < 400)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def _frac_near(img, cx, cy, half, rgb, tol=10):
    a = np.asarray(img).astype(int)
    box = a[max(0, cy - half):cy + half + 1,
            max(0, cx - half):cx + half + 1]
    dist = np.abs(box - np.array(rgb)).sum(axis=2)
    return float((dist <= tol * 3).mean())


def _ring_frac(img, cx, cy, r, rgb, tol=10):
    """Fraction of pixels near ``rgb`` in the annulus 0.35r..0.8r
    around (cx, cy) -- inside the head disc, outside the crown
    whorl (0.22r) and the outline."""
    a = np.asarray(img).astype(int)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    mask = (dist >= 0.35 * r) & (dist <= 0.8 * r)
    px = a[mask]
    d = np.abs(px - np.array(rgb)).sum(axis=1)
    return float((d <= tol * 3).mean())


class TestElevationProjection(unittest.TestCase):
    def test_default_is_identical_to_zero(self):
        img_none, _, _ = _draw(None)
        img_zero, _, _ = _draw(0.0)
        self.assertEqual(img_none.tobytes(), img_zero.tobytes())

    def test_joint_map_untouched_by_projection(self):
        _, j0, _ = _draw(0.0)
        _, j62, _ = _draw(62.0)
        self.assertEqual(j0, j62)

    def test_drawn_height_foreshortens_by_cos(self):
        # Expected heights computed FROM the rig geometry: the
        # figure spans the head top (projected head centre - r)
        # to the foot bottom (ground line + 0.05 * foreshortened
        # foot height). cos(62 deg) = 0.469.
        cos62 = math.cos(math.radians(62.0))
        img0, j0, ch = _draw(0.0)
        img62, _, _ = _draw(62.0)
        hy = j0["head"][1]
        ground = max(j0["foot_l"][1], j0["foot_r"][1])
        r = ch.head_r
        fh = STYLE_LOCK["foot_h_frac"] * float(ch.H)
        h0 = (ground + 0.05 * fh) - (hy - r)
        h62 = ((ground + 0.05 * fh * cos62)
               - (ground + (hy - ground) * cos62 - r))
        expected = h62 / h0
        _, top0, _, bot0 = _dark_bbox(img0)
        _, top62, _, bot62 = _dark_bbox(img62)
        self.assertAlmostEqual((bot62 - top62) / (bot0 - top0),
                               expected, delta=0.06)

    def test_eye_level_barely_changes(self):
        # cos(9.46 deg) = 0.986: the default eye-level elevation
        # must not visibly shrink the figure.
        img0, _, _ = _draw(0.0)
        img9, _, _ = _draw(9.46)
        _, top0, _, bot0 = _dark_bbox(img0)
        _, top9, _, bot9 = _dark_bbox(img9)
        self.assertAlmostEqual((bot9 - top9) / (bot0 - top0),
                               0.986, delta=0.03)

    def test_three_quarter_and_elevation_compose(self):
        img, joints, _ = _draw(62.0, view="three_quarter")
        self.assertIn("head", joints)
        _, top, _, bot = _dark_bbox(img)
        self.assertLess(bot - top, 560)  # foreshortened, not full height


class TestHeadTopSwitch(unittest.TestCase):
    def _head_centre(self, joints, ch, elev):
        hy = joints["head"][1]
        ground = max(joints["foot_l"][1], joints["foot_r"][1])
        cos_e = math.cos(math.radians(elev))
        return (int(joints["head"][0]),
                int(ground + (hy - ground) * cos_e))

    def test_birds_eye_head_is_hair_not_face(self):
        img, joints, ch = _draw(62.0)
        cx, cy = self._head_centre(joints, ch, 62.0)
        # The disc annulus is hair; the cream whorl arc at the
        # centre is the only face-fill in the disc.
        self.assertLess(_ring_frac(img, cx, cy, ch.head_r, FACE_FILL),
                        0.02)
        self.assertGreater(_ring_frac(img, cx, cy, ch.head_r, INK),
                           0.9)

    def test_high_angle_keeps_face(self):
        img, joints, ch = _draw(32.0)
        cx, cy = self._head_centre(joints, ch, 32.0)
        half = int(0.3 * ch.head_r)
        self.assertGreater(_frac_near(img, cx, cy, half, FACE_FILL),
                           0.3)

    def test_threshold_boundary(self):
        # 44 deg: face. 45 deg: crown. The switch is the threshold,
        # not a gradual fade.
        img44, j44, ch44 = _draw(44.0)
        cx, cy = self._head_centre(j44, ch44, 44.0)
        half = int(0.3 * ch44.head_r)
        self.assertGreater(_frac_near(img44, cx, cy, half, FACE_FILL),
                           0.3)
        img45, j45, ch45 = _draw(45.0)
        cx, cy = self._head_centre(j45, ch45, 45.0)
        self.assertLess(_ring_frac(img45, cx, cy, ch45.head_r,
                                   FACE_FILL), 0.02)

    def test_hat_renders_as_brim_disc_from_above(self):
        ch = _standing_char()
        ch.hat = "cap"
        ch.hat_color = "#FF7A00"
        hat_rgb = (255, 122, 0)
        img, joints, ch = _draw(62.0, char=ch)
        cx, cy = self._head_centre(joints, ch, 62.0)
        r = ch.head_r
        # Brim extends to 1.15r: a point at 1.05r is hat, not sky.
        self.assertLess(
            abs(np.asarray(img)[cy, int(cx + 1.05 * r)].astype(int)
                - np.array(hat_rgb)).sum(), 30)
        # Dome covers the centre, in a darker shade of the brim
        # (two flat concentric discs read as a target, not a hat).
        dome_rgb = _shade(hat_rgb, 0.78)
        self.assertLess(
            abs(np.asarray(img)[cy, cx].astype(int)
                - np.array(dome_rgb)).sum(), 30)


class TestTailForeshortening(unittest.TestCase):
    def test_tail_y_offsets_scale(self):
        ch = _standing_char()
        ch.tail = "monkey"
        bboxes = []
        for scale in (1.0, 0.5):
            img = Image.new("RGB", (600, 600), (255, 255, 255))
            d = ImageDraw.Draw(img, "RGBA")
            _draw_tail(d, ch, (300, 300), 1, (23, 32, 51),
                       "profile", 560.0, y_scale=scale)
            a = np.asarray(img).astype(int).sum(axis=2)
            ys, _ = np.where(a < 400)
            bboxes.append((int(ys.min()), int(ys.max())))
        h1 = bboxes[0][1] - bboxes[0][0]
        h05 = bboxes[1][1] - bboxes[1][0]
        self.assertAlmostEqual(h05 / h1, 0.5, delta=0.15)


def _delivered_shots():
    text = (AGENT / "examples" / "loop_test_02_brass_key.studio.md"
            ).read_text(encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    timeline = json.loads((JOB / "timeline.json").read_text(
        encoding="utf-8"))
    shots = timeline["shots"]
    starts = {}
    _t = 0.0
    for s in shots:
        starts[id(s)] = _t
        _t += float(s["duration"])
    spans = {}
    for s in shots:
        sid = s.get("directive_shot_id")
        if sid:
            st = starts[id(s)]
            en = st + float(s["duration"])
            if sid in spans:
                spans[sid][1] = max(spans[sid][1], en)
            else:
                spans[sid] = [st, en]
    events, unsupported = compile_actions(
        package, timeline={"spans": spans})
    package["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    out = []
    for i, s in enumerate(shots):
        shot = dict(s)
        shot["index"] = i
        shot["start_sec"] = starts[id(s)]
        out.append(shot)
    return package, out


class TestBirdsEyeStill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _delivered_shots()
        cls.an_name = next(
            str(c.get("name")) for c in cls.package["characters"]
            if str(c.get("id")) == "CHAR_AN")

    def test_shot6_head_is_crown_not_face(self):
        # Loop 02 timeline shot 6 = SC03_SH02, the birds-eye
        # establishing shot (62 deg). The R15 delivered frame
        # shows An's cream face at the rig head centre; the new
        # still must show the dark hair crown at the PROJECTED
        # head centre (rig head foreshortened toward the feet).
        with tempfile.TemporaryDirectory() as tmp:
            rep = _render_shot({"shot": dict(self.shots[6]),
                                "package": self.package,
                                "out_dir": tmp, "still_only": True})
            still = Image.open(
                Path(tmp) / "shot_006" / "still.png").convert("RGB")
            still.load()
        joints = rep["joints_last_frame"][self.an_name]
        hy = joints["head"][1]
        ground = max(joints["foot_l"][1], joints["foot_r"][1])
        cos62 = math.cos(math.radians(62.0))
        cx = int(joints["head"][0])
        cy = int(ground + (hy - ground) * cos62)
        a = np.asarray(still).astype(int)
        box = a[max(0, cy - 20):cy + 21, max(0, cx - 20):cx + 21]
        # The crown disc is dark hair; the R15 face disc was
        # cream (mean RGB sum ~600). A dark box mean proves the
        # face is gone at the projected centre.
        self.assertLess(box.sum(axis=2).mean(), 300)


if __name__ == "__main__":
    unittest.main()
