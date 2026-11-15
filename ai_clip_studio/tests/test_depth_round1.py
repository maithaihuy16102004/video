"""RicksClips loop round 1 -- depth: atmospheric perspective (distant
elements tint toward the horizon sky) and the blurred foreground
occlusion layer. Both are general, kind/layer-driven rules."""
import math
import unittest

from PIL import Image

from ai_clip_studio.environment_v2 import (
    _haze_color,
    _haze_factor,
    render_environment,
)
from ai_clip_studio.lighting import light_for
from ai_clip_studio.renderer25d.camera import PerspectiveCamera

SKY_BOTTOM = (205, 224, 240)


def _camera():
    return PerspectiveCamera(position=(0.0, 2.0, 4.8),
                             target=(0.0, 1.2, 0.0), fov_deg=46.0,
                             aspect=16 / 9)


def _box(el_id, layer, center, color=(150, 60, 40)):
    return {"id": el_id, "kind": "wall", "layer": layer,
            "geometry": "box", "center": center,
            "size": (4.0, 3.0, 1.0), "color": color,
            "material": "generic", "attachment": None,
            "label": "", "extra": {}}


def _package(elements):
    return {"light": light_for("day", "warm"),
            "ground": {"color": (122, 112, 96), "kind": "neutral"},
            "elements": elements}


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


class TestHazeHelpers(unittest.TestCase):
    def test_factor_boundaries(self):
        self.assertEqual(_haze_factor(5.0), 0.0)
        self.assertEqual(_haze_factor(10.0), 0.0)
        self.assertEqual(_haze_factor(30.0), 0.40)
        self.assertEqual(_haze_factor(40.0), 0.40)
        self.assertAlmostEqual(_haze_factor(20.0), 0.20)

    def test_color_lerp(self):
        self.assertEqual(_haze_color((100, 100, 100), SKY_BOTTOM, 0.0),
                         (100, 100, 100))
        self.assertEqual(_haze_color((100, 100, 100), SKY_BOTTOM, 1.0),
                         SKY_BOTTOM)
        mid = _haze_color((0, 0, 0), (200, 200, 200), 0.5)
        self.assertEqual(mid, (100, 100, 100))


class TestAtmosphericPerspective(unittest.TestCase):
    def test_far_box_hazes_near_box_does_not(self):
        cam = _camera()
        # Offset in x: a far box directly behind the near box would
        # be occluded at its centre and the sample would read the
        # near face twice.
        near = _box("near", "MG", (-3.0, 1.5, 0.0))
        far = _box("far", "BG", (6.0, 1.5, -26.0))
        self.assertEqual(_haze_factor(cam.depth_of(near["center"])), 0.0)
        self.assertEqual(_haze_factor(cam.depth_of(far["center"])), 0.40)
        both = render_environment(_package([near, far]), cam,
                                  size=(640, 360))
        px = both.load()
        nx, ny, _, _ = cam.project(near["center"], 640, 360)
        fx, fy, _, _ = cam.project(far["center"], 640, 360)
        near_px = px[int(nx), int(ny)][:3]
        far_px = px[int(fx), int(fy)][:3]
        self.assertLess(_dist(far_px, SKY_BOTTOM),
                        _dist(near_px, SKY_BOTTOM) - 10,
                        f"far {far_px} not hazier than near {near_px}")
        # The near box is pixel-identical with the far box removed:
        # haze never touches near content.
        solo = render_environment(_package([near]), cam, size=(640, 360))
        self.assertEqual(solo.load()[int(nx), int(ny)][:3], near_px)

    def test_package_elements_never_mutated(self):
        cam = _camera()
        far = _box("far", "BG", (0.0, 1.5, -26.0))
        render_environment(_package([far]), cam, size=(640, 360))
        self.assertEqual(far["color"], (150, 60, 40))


class TestForegroundBlur(unittest.TestCase):
    def _fg_package(self):
        return _package([_box("fg1", "FG", (0.0, 1.0, 2.0),
                              color=(90, 120, 70))])

    def test_default_is_crisp(self):
        cam = _camera()
        a = render_environment(self._fg_package(), cam, size=(640, 360),
                               draw_layers=("FG",), transparent=True)
        b = render_environment(self._fg_package(), cam, size=(640, 360),
                               draw_layers=("FG",), transparent=True,
                               fg_blur_radius=0.0)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_blur_softens_edges(self):
        cam = _camera()
        crisp = render_environment(
            self._fg_package(), cam, size=(640, 360),
            draw_layers=("FG",), transparent=True)
        blurred = render_environment(
            self._fg_package(), cam, size=(640, 360),
            draw_layers=("FG",), transparent=True, fg_blur_radius=6.0)
        alpha = lambda img: list(img.getchannel("A").getdata())
        partial = lambda img: sum(1 for a in alpha(img) if 0 < a < 255)
        self.assertEqual(partial(crisp), 0)
        self.assertGreater(partial(blurred), 100)
        # The blurred layer still covers the same subject: the fully
        # opaque core survives.
        self.assertGreater(sum(1 for a in alpha(blurred) if a == 255),
                           1000)


if __name__ == "__main__":
    unittest.main()
