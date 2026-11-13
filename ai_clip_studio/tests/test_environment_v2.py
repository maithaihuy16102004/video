"""Unit tests for ai_clip_studio.environment_v2 (stdlib unittest).

Run:  python3 -m unittest discover -s ai_clip_studio/tests -v
from ~/workspace/agent/
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.environment_v2 import (
    ARCHETYPES,
    build_environment,
    render_environment,
    select_archetype,
    to_box_dicts,
    validate_attachments,
    validate_period,
)
from ai_clip_studio.lighting import (
    DAY_LUMINANCE_FLOOR,
    check_day_brightness,
)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from ai_clip_studio.renderer25d.scene import Box3D

TRAITS = {
    "EUROPEAN_STREET_1900": {
        "features": ["Kiến trúc đô thị đầu thế kỷ XX.",
                     "Nhà nhiều tầng, mặt tiền trát vữa.",
                     "Cửa sổ cao, khung gỗ.", "Mái nhà dốc.",
                     "Đường lát đá.", "Biển hiệu cửa hàng.",
                     "Cột đèn đường.", "Mép vỉa hè."],
        "period": "1914"},
    "GREEK_PALACE": {
        "features": ["Cung điện Hy Lạp.", "Cột đá cẩm thạch.",
                     "Đầu hồi.", "Đền thờ."],
        "period": "Ancient Greece"},
    "MEDITERRANEAN_ISLAND": {
        "features": ["Đảo Địa Trung Hải.", "Nhà vôi trắng.",
                     "Mái vòm.", "Cây ô liu.", "Bờ biển."]},
    "CAVE": {
        "features": ["Hang động.", "Thạch nhũ.", "Đuốc.",
                     "Dưới lòng đất."]},
    "BARRACKS": {
        "features": ["Doanh trại quân đội.", "Sân tập.",
                     "Công trình xây bằng gạch.", "Trại lính."],
        "period": "1914"},
    "TRENCH": {
        "features": ["Chiến hào.", "Bao cát.", "Bùn lầy.",
                     "Ván gỗ.", "Khói pháo."],
        "period": "1914"},
    "FOREST": {
        "features": ["Khu rừng.", "Cây cổ thụ.", "Tán cây.",
                     "Bụi rậm."]},
    "MODERN_CITY": {
        "features": ["Thành phố hiện đại.", "Cao ốc.",
                     "Glass tower.", "Giao lộ.", "Đường nhựa."],
        "period": "2024"},
}


def _camera():
    return PerspectiveCamera(position=(0.0, 2.0, 4.8),
                             target=(0.0, 1.2, 0.0), fov_deg=46.0,
                             aspect=16 / 9)


class TestSelection(unittest.TestCase):
    def test_each_archetype_selected_by_traits(self):
        for archetype_id, traits in TRAITS.items():
            got, score, hits = select_archetype(traits)
            self.assertEqual(got, archetype_id, f"traits: {traits}")
            self.assertGreaterEqual(score, 2)
            self.assertTrue(hits)

    def test_unknown_traits_fall_back_to_neutral(self):
        got, score, _ = select_archetype(
            {"features": ["Something indescribable and placeless."]})
        self.assertEqual(got, "GENERIC_NEUTRAL")
        self.assertEqual(score, 0)

    def test_empty_traits_do_not_raise(self):
        got, _, _ = select_archetype({})
        self.assertEqual(got, "GENERIC_NEUTRAL")

    def test_map_type_defers(self):
        got, _, _ = select_archetype(
            {"type": "Historical animated map",
             "features": ["Biên giới lịch sử."]})
        self.assertEqual(got, "MAP")

    def test_selection_ignores_ids_and_names(self):
        # Same generic words, different ids/names -> same archetype.
        base = dict(TRAITS["TRENCH"])
        a = select_archetype(dict(base, id="LOC_A", name="Place A"))
        b = select_archetype(dict(base, id="LOC_B", name="Place B"))
        self.assertEqual(a[0], b[0])


class TestBuild(unittest.TestCase):
    def test_all_archetypes_validate_clean(self):
        for archetype_id, traits in TRAITS.items():
            pkg = build_environment(traits, period=traits.get("period", ""),
                                    time_of_day="day")
            self.assertEqual(pkg["archetype"], archetype_id)
            self.assertEqual(pkg["validation"], [],
                             f"{archetype_id}: {pkg['validation'][:3]}")
            self.assertEqual(pkg["period_errors"], [])

    def test_deterministic_layout(self):
        traits = TRAITS["EUROPEAN_STREET_1900"]
        a = build_environment(traits, period="1914", time_of_day="day")
        b = build_environment(traits, period="1914", time_of_day="day")
        self.assertEqual([e["center"] for e in a["elements"]],
                         [e["center"] for e in b["elements"]])
        self.assertEqual(a["provenance"]["seed"],
                         b["provenance"]["seed"])

    def test_layers_cover_all_elements(self):
        for traits in TRAITS.values():
            pkg = build_environment(traits, time_of_day="day")
            layered = (pkg["layers"]["FG"] + pkg["layers"]["MG"]
                       + pkg["layers"]["BG"])
            self.assertEqual(sorted(layered),
                             sorted(e["id"] for e in pkg["elements"]))
            self.assertTrue(pkg["layers"]["FG"], "no FG occluders")
            self.assertTrue(pkg["layers"]["BG"], "no background")

    def test_provenance_records_selection(self):
        pkg = build_environment(TRAITS["TRENCH"], period="1914")
        prov = pkg["provenance"]
        self.assertEqual(prov["archetype"], "TRENCH")
        self.assertIn("chiến hào", [h.lower() for h in
                                    prov["matched_keywords"]])
        self.assertFalse(prov["fallback"])

    def test_windows_inside_wall_rects(self):
        pkg = build_environment(TRAITS["EUROPEAN_STREET_1900"],
                                period="1914")
        for el in pkg["elements"]:
            if el["kind"] == "window":
                rect = el["attachment"]["local_rect"]
                u0, v0, u1, v1 = rect
                self.assertGreaterEqual(u0, 0.0)
                self.assertLessEqual(u1, 1.0)
                self.assertGreaterEqual(v0, 0.0)
                self.assertLessEqual(v1, 1.0)

    def test_doors_reach_parent_ground(self):
        pkg = build_environment(TRAITS["EUROPEAN_STREET_1900"],
                                period="1914")
        by_id = {e["id"]: e for e in pkg["elements"]}
        for el in pkg["elements"]:
            if el["kind"] == "door":
                parent = by_id[el["attachment"]["parent"]]
                parent_bottom = parent["center"][1] - parent["size"][1] / 2
                bottom = el["center"][1] - el["size"][1] / 2
                self.assertAlmostEqual(bottom, parent_bottom, places=1)

    def test_roofs_sit_on_walls(self):
        pkg = build_environment(TRAITS["EUROPEAN_STREET_1900"],
                                period="1914")
        by_id = {e["id"]: e for e in pkg["elements"]}
        for el in pkg["elements"]:
            if el["kind"] == "gable_roof":
                parent = by_id[el["attachment"]["parent"]]
                top = parent["center"][1] + parent["size"][1] / 2
                bottom = el["center"][1] - el["size"][1] / 2
                self.assertAlmostEqual(bottom, top, places=1)

    def test_map_traits_defer(self):
        pkg = build_environment({"type": "Historical animated map"})
        self.assertEqual(pkg["kind"], "map_deferred")
        self.assertEqual(pkg["elements"], [])

    def test_sign_text_only_from_data(self):
        pkg = build_environment(TRAITS["EUROPEAN_STREET_1900"],
                                period="1914")
        labels = [e["label"] for e in pkg["elements"] if e.get("label")]
        self.assertEqual(labels, [])  # no sign text in traits: no sign
        pkg2 = build_environment(
            dict(TRAITS["EUROPEAN_STREET_1900"],
                 sign_text="BÄCKEREI"), period="1914")
        labels2 = [e["label"] for e in pkg2["elements"] if e.get("label")]
        self.assertIn("BÄCKEREI", labels2)

    def test_to_box_dicts_constructible(self):
        pkg = build_environment(TRAITS["BARRACKS"], period="1914")
        boxes = to_box_dicts(pkg)
        self.assertTrue(boxes)
        for kwargs in boxes:
            box = Box3D(**kwargs)
            self.assertEqual(len(box.center), 3)
        # Non-box geometries are excluded, not faked.
        non_box = [e for e in pkg["elements"]
                   if e["geometry"] != "box"]
        self.assertLess(len(boxes), len(pkg["elements"]) if non_box
                        else len(pkg["elements"]) + 1)


class TestPeriod(unittest.TestCase):
    def test_led_in_1914_is_anachronism(self):
        elements = [{"id": "lamp1", "kind": "lamp_head",
                     "material": "led", "extra": {}}]
        self.assertTrue(validate_period(elements, "1914"))
        self.assertEqual(validate_period(elements, "2024"), [])

    def test_neon_and_cars(self):
        elements = [{"id": "s1", "kind": "neon_sign", "material": "",
                     "extra": {}},
                    {"id": "c1", "kind": "automobile", "material": "",
                     "extra": {}}]
        self.assertEqual(len(validate_period(elements, "1800")), 2)
        # 1900: cars exist (1885), neon does not (1910).
        self.assertEqual(len(validate_period(elements, "1900")), 1)
        self.assertEqual(validate_period(elements, "1920"), [])

    def test_mythological_has_no_constraint(self):
        elements = [{"id": "lamp1", "kind": "lamp_head",
                     "material": "led", "extra": {}}]
        self.assertEqual(validate_period(elements, "mythological"), [])
        self.assertEqual(validate_period(elements, ""), [])

    def test_archetype_range_reported(self):
        pkg = build_environment(TRAITS["MODERN_CITY"], period="1914")
        self.assertTrue(pkg["period_errors"])
        self.assertTrue(any("MODERN_CITY" in e
                            for e in pkg["period_errors"]))


class TestRender(unittest.TestCase):
    def test_render_size_and_day_brightness(self):
        cam = _camera()
        for archetype_id, traits in TRAITS.items():
            if archetype_id == "CAVE":
                continue  # dark by nature; tested separately
            pkg = build_environment(traits,
                                    period=traits.get("period", ""),
                                    time_of_day="day")
            img = render_environment(pkg, cam, size=(480, 270))
            self.assertEqual(img.size, (480, 270))
            check = check_day_brightness(img)
            self.assertTrue(check["ok"],
                            f"{archetype_id} too dark: {check}")

    def test_cave_is_dark_by_design(self):
        cam = _camera()
        pkg = build_environment(TRAITS["CAVE"], time_of_day="day")
        img = render_environment(pkg, cam, size=(480, 270))
        self.assertLess(check_day_brightness(img)["mean_luminance"],
                        DAY_LUMINANCE_FLOOR)

    def test_render_deterministic(self):
        cam = _camera()
        pkg = build_environment(TRAITS["GREEK_PALACE"],
                                period="Ancient Greece")
        a = render_environment(pkg, cam, size=(480, 270))
        b = render_environment(pkg, cam, size=(480, 270))
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_render_accepts_camera_tuple(self):
        pkg = build_environment(TRAITS["FOREST"], time_of_day="day")
        img = render_environment(pkg, ((0.0, 2.0, 4.8), (0.0, 1.2, 0.0),
                                      46.0), size=(320, 180))
        self.assertEqual(img.size, (320, 180))

    def test_validation_catches_floating_window(self):
        pkg = build_environment(TRAITS["EUROPEAN_STREET_1900"],
                                period="1914")
        for el in pkg["elements"]:
            if el["kind"] == "window":
                el["center"] = (el["center"][0] + 2.0, el["center"][1],
                                el["center"][2])
                break
        self.assertTrue(validate_attachments(pkg))


if __name__ == "__main__":
    unittest.main()
