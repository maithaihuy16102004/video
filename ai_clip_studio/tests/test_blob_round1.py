"""RicksClips loop round 1 -- blob structure: foliage lobes, dome
highlight, cloud puffs. The flat single-ellipse read (ENV-BLOB) is
gone for structured kinds; small footprints and other kinds keep
the plain ellipse."""
import unittest

from PIL import Image, ImageDraw

from ai_clip_studio.environment_v2 import (
    _draw_blob,
    build_environment,
    render_environment,
)
from ai_clip_studio.lighting import light_for, rig_for
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

BG = (255, 255, 255)


def _camera():
    return PerspectiveCamera(position=(0.0, 2.0, 4.8),
                             target=(0.0, 1.2, 0.0), fov_deg=46.0,
                             aspect=16 / 9)


def _rig():
    return rig_for(light_for("day", "warm"))


def _element(el_id, kind, center, size, color):
    return {"id": el_id, "kind": kind, "layer": "MG",
            "geometry": "blob", "center": center, "size": size,
            "color": color, "material": "generic",
            "attachment": None, "label": "", "extra": {}}


def _render(el, size=(800, 450)):
    cam = _camera()
    img = Image.new("RGB", size, BG)
    _draw_blob(img, ImageDraw.Draw(img, "RGBA"), el, cam, _rig(),
               size[0], size[1])
    x, y, scale, vis = cam.project(el["center"], size[0], size[1])
    assert vis, "test element must project visible"
    rx = el["size"][0] / 2 * scale
    ry = el["size"][1] / 2 * scale
    return img, (x, y, rx, ry)


def _tones(img, box):
    colors = img.crop(box).getcolors(maxcolors=1000000)
    return {c for _, c in colors if c != BG}


class TestBlobStructure(unittest.TestCase):
    def test_foliage_blob_has_internal_tones(self):
        el = _element("bush1", "bush", (0.0, 1.0, -5.0),
                      (4.0, 2.0, 1.0), (84, 110, 66))
        img, (x, y, rx, ry) = _render(el)
        box = (int(x - rx), int(y - ry), int(x + rx), int(y + ry))
        # Base + light lobe + dark lobe + outline: >= 4 tones.
        # The old flat ellipse had exactly 2.
        self.assertGreaterEqual(len(_tones(img, box)), 4)

    def test_dome_blob_has_highlight(self):
        el = _element("dome1", "dome", (0.0, 2.0, -5.0),
                      (4.0, 2.5, 1.0), (70, 110, 180))
        img, (x, y, rx, ry) = _render(el)
        px = img.load()
        ul = px[int(x - 0.26 * rx), int(y - 0.32 * ry)]
        lr = px[int(x + 0.5 * rx), int(y + 0.5 * ry)]
        self.assertGreater(sum(ul), sum(lr) + 30,
                           "dome highlight missing in upper-left")

    def test_cloud_blob_has_puffs(self):
        el = _element("cloud1", "cloud", (0.0, 4.0, -8.0),
                      (6.0, 2.0, 1.0), (200, 200, 205))
        img, (x, y, rx, ry) = _render(el)
        box = (int(x - rx), int(y - ry), int(x + rx), int(y + ry))
        self.assertGreaterEqual(len(_tones(img, box)), 3)

    def test_small_footprint_stays_flat(self):
        el = _element("bush2", "bush", (0.0, 1.0, -5.0),
                      (0.2, 0.1, 1.0), (84, 110, 66))
        img, (x, y, rx, ry) = _render(el)
        self.assertLess(rx, 14.0)
        box = (int(x - rx) - 1, int(y - ry) - 1,
               int(x + rx) + 1, int(y + ry) + 1)
        self.assertLessEqual(len(_tones(img, box)), 2)

    def test_other_kinds_unchanged(self):
        # "fire" is NOT an "other" kind anymore: round 6 gave
        # it a dedicated branch (fire bed / teardrops, pinned
        # by TestFireBedAndCloudsRound6). A kind with no branch
        # -- rock -- keeps the plain 2-tone ellipse.
        el = _element("rock1", "rock", (0.0, 1.0, -5.0),
                      (4.0, 2.0, 1.0), (120, 115, 110))
        img, (x, y, rx, ry) = _render(el)
        box = (int(x - rx), int(y - ry), int(x + rx), int(y + ry))
        self.assertEqual(len(_tones(img, box)), 2)

    def test_deterministic_pixels(self):
        el = _element("bush3", "bush", (0.0, 1.0, -5.0),
                      (4.0, 2.0, 1.0), (84, 110, 66))
        img_a, _ = _render(el)
        img_b, _ = _render(el)
        self.assertEqual(img_a.tobytes(), img_b.tobytes())

    def test_full_package_renders(self):
        pkg = build_environment(
            {"features": ["Khu rừng.", "Cây cổ thụ.", "Bụi rậm."]},
            time_of_day="day")
        img = render_environment(pkg, _camera(), size=(640, 360))
        self.assertEqual(img.size, (640, 360))


if __name__ == "__main__":
    unittest.main()
