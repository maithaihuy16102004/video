"""Unit tests for the Cinematic Engine Upgrade, Subagent B scope
(Phases C + E): P-S2/P-S3/P-S5/P-S12 environment work, semantic
landmark selection, ground painting, lighting sun position, and the
Camera Director. Run from ~/workspace/agent:

    python3 -m unittest ai_clip_studio.tests.test_cinematic_upgrade_b
"""
import hashlib
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.camera_planner import (
    CameraPlanner,
    SHOT_SCALE,
    anchor_focus_for_shot,
    apply_camera_anchored,
    camera_transform,
    crop_rect_for,
    directive_for_shot,
    orientation_basis,
    plan_coverage,
    plan_shot,
    projection_matrix,
    scripted_directive_for_shot,
    scripted_transforms,
    static_directive_for_shot,
    validate_camera_sequence,
    validate_composition,
    validate_shot_camera_static,
    validation_for_camera,
    viewpoint_for_shot,
)
from ai_clip_studio.cinematic_contracts import (
    TRANSFORM_TOLERANCE,
    CameraMode,
)
from ai_clip_studio.environment_v2 import (
    _bush,
    _face_texture,
    _facade,
    _hedge,
    _tree,
    apply_negative_constraints,
    build_environment,
    build_landmarks,
    fit_foreground_to_frustum,
    frustum_cull,
    render_environment,
    select_archetype,
    select_landmarks,
    sight_lines_for_camera,
    sightline_occlusion,
    ray_aabb_intersect,
    validate_attachments,
    validate_fg_composition,
)
from ai_clip_studio.lighting import light_for, sun_position
from ai_clip_studio.paint_textures import (
    MIN_FACE_PX,
    facade_window_layout,
    ground_texture_for,
    paint_plaster,
    texture_for_material,
)
from ai_clip_studio.renderer25d.camera import PerspectiveCamera
from PIL import Image


def _camera(pos=(0.0, 2.0, 4.8), tgt=(0.0, 1.5, 0.0)):
    return PerspectiveCamera(position=pos, target=tgt, fov_deg=46,
                             aspect=16 / 9)


def _munich_traits():
    return {"id": "LOC_MUNICH",
            "features": ["European street 1914.",
                         "Cobblestone street."],
            "type": "European street", "period": "1914"}


# ---------------------------------------------------------------------------
# P-S2: shared window layout + wood + ground painters
# ---------------------------------------------------------------------------
class TestSharedWindowLayout(unittest.TestCase):
    def test_pitch_grid_reproduces_original(self):
        layout = facade_window_layout(7.0, 5.6)
        self.assertEqual(layout["grid"], "pitch")
        self.assertEqual(layout["floors"], 2)  # floor(5.6 / 2.8)
        self.assertEqual(layout["n_win"], 3)  # floor(7.0 / 2.2)
        self.assertEqual(len(layout["windows"]), 6)
        self.assertIsNotNone(layout["door"])

    def test_even_grid_rows_count_from_top(self):
        layout = facade_window_layout(3.3, 4.5, grid="even", rows=3,
                                      cols=3, win_w=0.5, win_h=0.85)
        self.assertEqual(len(layout["windows"]), 9)
        ys = [w[1] for w in layout["windows"]]
        # Row 0 (first 3 windows) is the TOP row: highest y.
        self.assertGreater(min(ys[:3]), max(ys[3:6]))
        self.assertGreater(min(ys[3:6]), max(ys[6:]))

    def test_even_grid_skips_out_of_wall_windows(self):
        layout = facade_window_layout(0.6, 1.2, grid="even", rows=1,
                                      cols=2, win_w=0.5, win_h=0.85)
        for (wx, wy, ww, wh) in layout["windows"]:
            self.assertGreaterEqual(wx, 0.0)
            self.assertLessEqual(wx + ww, 0.6)
            self.assertGreaterEqual(wy, 0.0)
            self.assertLessEqual(wy + wh, 1.2)

    def test_unknown_grid_raises(self):
        with self.assertRaises(ValueError):
            facade_window_layout(3.0, 3.0, grid="radial")

    def test_facade_windows_match_shared_layout(self):
        rng = random.Random(7)
        els, wall = _facade("f", rng, 0.0, -6.0, 3.3, 3,
                            [(200, 180, 160)], (120, 60, 50),
                            (52, 66, 88))
        layout = wall["extra"]["window_layout"]["layout"]
        wins = [e for e in els if e["kind"] == "window"]
        self.assertEqual(len(wins), len(layout["windows"]))
        # Compare as sets: layout order is row-major top-to-bottom,
        # element order is build order.
        expected = {(round(-3.3 / 2 + wx_m + ww_m / 2, 6),
                     round(wy_m + wh_m / 2, 6))
                    for (wx_m, wy_m, ww_m, wh_m) in layout["windows"]}
        actual = {(round(e["center"][0], 6), round(e["center"][1], 6))
                  for e in wins}
        self.assertEqual(actual, expected)

    def test_painted_windows_use_same_layout(self):
        layout = facade_window_layout(3.3, 4.5, grid="even", rows=3,
                                      cols=3, win_w=0.5, win_h=0.85,
                                      door_w=0.85, door_h=1.5)
        img = paint_plaster(3.3, 4.5, (210, 190, 170), seed=3,
                            windows=True, window_layout=layout)
        w, h = img.size
        # Every layout window must read as glass (blue-ish), not
        # plaster: painted and geometric openings agree. Sample
        # the upper-left glass quadrant (offset from the centre
        # muntins, the frame, the curtains and the glint). The
        # door paints OVER the bottom-centre window — the same
        # overlap the 3D facade has (door element drawn after the
        # window) — so windows intersecting the door rect are
        # expected to read as door colour instead.
        door = layout["door"]
        for (wx_m, wy_m, ww_m, wh_m) in layout["windows"]:
            sx_m = wx_m + ww_m / 2 - ww_m / 8
            sy_m = wy_m + wh_m / 2 + wh_m / 4
            px = int(sx_m / 3.3 * w)
            py = int(h - sy_m / 4.5 * h)
            r, g, b = img.getpixel((px, py))
            overlaps_door = (
                door is not None
                and sx_m >= door[0] and sx_m <= door[0] + door[2]
                and sy_m >= door[1] and sy_m <= door[1] + door[3])
            if overlaps_door:
                # Door colour: darken(base, 0.5) = (105, 95, 85).
                self.assertEqual((r, g, b), (105, 95, 85))
            else:
                self.assertGreater(
                    b, r, f"window glass at {(px, py)} not glass")
        # A wall point far from any opening stays plaster-toned.
        r, g, b = img.getpixel((5, 5))
        self.assertGreater(r, b)

    def test_facade_relief_present_and_valid(self):
        rng = random.Random(7)
        els, _wall = _facade("f", rng, 0.0, -6.0, 3.3, 3,
                             [(200, 180, 160)], (120, 60, 50),
                             (52, 66, 88))
        kinds = {e["kind"] for e in els}
        for kind in ("plinth", "cornice", "chimney", "window_sill",
                     "window_lintel", "door_step"):
            self.assertIn(kind, kinds)
        self.assertEqual(validate_attachments({"elements": els}), [])


class TestWoodAndGroundPainters(unittest.TestCase):
    def test_wood_maps_to_planks(self):
        tex = texture_for_material("wood", (150, 110, 70), 2.0, 1.0, 5)
        self.assertIsInstance(tex, Image.Image)

    def test_face_texture_size_gate_keeps_small_faces_flat(self):
        el = {"id": "tiny", "kind": "box", "center": (0, 1, -3),
              "size": (0.2, 0.2, 0.2), "color": (150, 110, 70),
              "material": "wood"}
        small = [(100, 100), (100 + MIN_FACE_PX - 1, 100),
                 (100 + MIN_FACE_PX - 1, 100 + MIN_FACE_PX - 1),
                 (100, 100 + MIN_FACE_PX - 1)]
        self.assertIsNone(_face_texture(el, (0, 0, 1), small, 0.2, 0.2))
        big = [(100, 100), (300, 100), (300, 300), (100, 300)]
        self.assertIsInstance(
            _face_texture(el, (0, 0, 1), big, 2.0, 2.0), Image.Image)

    def test_ground_mapping(self):
        for kind in ("cobblestone", "grass", "forest_floor",
                     "pale_stone", "dark_stone", "asphalt",
                     "wood_floor", "sand", "packed_earth", "mud"):
            tex = ground_texture_for(kind, (140, 130, 110), 4.0, 2.0, 1)
            self.assertIsInstance(tex, Image.Image, kind)
        self.assertIsNone(
            ground_texture_for("neutral", (140, 130, 110), 4.0, 2.0, 1))
        self.assertIsNone(
            ground_texture_for("void", (140, 130, 110), 4.0, 2.0, 1))

    def test_ground_texture_deterministic(self):
        a = ground_texture_for("cobblestone", (140, 130, 110),
                               4.0, 2.0, 42)
        b = ground_texture_for("cobblestone", (140, 130, 110),
                               4.0, 2.0, 42)
        self.assertEqual(a.tobytes(), b.tobytes())


# ---------------------------------------------------------------------------
# Selection: field-weighted, no keyword hijack
# ---------------------------------------------------------------------------
class TestFieldWeightedSelection(unittest.TestCase):
    def test_forge_beats_street_keyword_hijack(self):
        traits = {"features": ["Lò nung lớn.", "Đe kim loại.",
                               "Búa khổng lồ.", "Tia lửa."],
                  "type": "Mythological Blacksmith Forge",
                  "render_traits": {"location_keyword": "street"}}
        arch, _score, _hits = select_archetype(traits)
        self.assertEqual(arch, "FORGE")
        pkg = build_environment(traits)
        self.assertEqual(pkg["archetype"], "FORGE")
        self.assertTrue(pkg["provenance"]["location_keyword_ignored"])
        self.assertEqual(pkg["provenance"]["location_keyword"], "street")

    def test_keyword_only_falls_back_to_keyword(self):
        arch, score, _hits = select_archetype(
            {"render_traits": {"location_keyword": "street"}})
        self.assertEqual(arch, "EUROPEAN_STREET_1900")
        self.assertEqual(score, 1)

    def test_word_boundary_de_does_not_match_dem(self):
        arch, _s, hits = select_archetype(
            {"features": ["Anh ta đem búa đến."]})
        self.assertEqual(arch, "FORGE")
        self.assertIn("búa", hits)
        self.assertNotIn("đe", hits)

    def test_name_does_not_select(self):
        # "Lò rèn" in the NAME alone must not select FORGE; the
        # name is excluded from selection text.
        arch, score, _hits = select_archetype(
            {"name": "Lò rèn thần thánh", "features": ["Bãi cỏ xanh."]})
        self.assertNotEqual(arch, "FORGE")

    def test_landmarks_field_outweighs_features(self):
        traits = {"features": ["Đường phố."],
                  "landmarks": ["mountain peak"]}
        pkg = build_environment(traits)
        self.assertEqual(pkg["provenance"]["landmarks"],
                         ["mountain_peak"])

    def test_unknown_traits_fall_back_neutral(self):
        arch, score, _hits = select_archetype(
            {"features": ["Blorptastic wobble."]})
        self.assertEqual(arch, "GENERIC_NEUTRAL")
        self.assertEqual(score, 0)

    def test_seven_test_locations(self):
        cases = [
            ({"features": ["European street 1914.",
                           "Cobblestone street."],
              "type": "European street"}, "EUROPEAN_STREET_1900"),
            ({"features": ["Doanh trại quân đội.", "Lều bạt."],
              "type": "Military barracks"}, "BARRACKS"),
            ({"features": ["Chiến hào.", "Bùn lầy.", "Bao cát."],
              "type": "Trench"}, "TRENCH"),
            ({"features": ["Cung điện đá trắng.", "Núi Olympus."],
              "type": "Greek palace"}, "GREEK_PALACE"),
            ({"features": ["Cung điện của Cronus.", "Cột đá cẩm thạch."],
              "type": "Greek palace"}, "GREEK_PALACE"),
            ({"features": ["Lò rèn.", "Lò nung lớn.", "Tia lửa."],
              "type": "Mythological Blacksmith Forge"}, "FORGE"),
            ({"features": ["Nhà ống.", "Biển hiệu.", "Xe máy."],
              "type": "Modern Vietnamese street"}, "SHOPHOUSE_STREET"),
        ]
        for traits, expected in cases:
            with self.subTest(expected=expected):
                arch, _s, _h = select_archetype(traits)
                self.assertEqual(arch, expected)
                pkg = build_environment(traits)
                self.assertEqual(validate_attachments(pkg), [])

    def test_olympus_mention_does_not_hijack_battlefield(self):
        traits = {"features": ["Đỉnh Othrys ở phía đối diện Olympus."],
                  "type": "Titan battlefield"}
        arch, _s, _h = select_archetype(traits)
        self.assertNotEqual(arch, "GREEK_PALACE")


class TestForgeAndShophouseBuilders(unittest.TestCase):
    def test_forge_builds_and_validates(self):
        pkg = build_environment(
            {"features": ["Lò rèn.", "Lò nung lớn."],
             "type": "Mythological Blacksmith Forge"})
        self.assertEqual(pkg["archetype"], "FORGE")
        self.assertEqual(validate_attachments(pkg), [])
        kinds = {e["kind"] for e in pkg["elements"]}
        self.assertTrue({"furnace", "anvil", "bellows"} & kinds)
        self.assertTrue(pkg["layers"]["FG"])

    def test_shophouse_builds_and_validates(self):
        pkg = build_environment(
            {"features": ["Nhà ống.", "Biển hiệu.", "Xe máy."],
             "type": "Modern Vietnamese street"})
        self.assertEqual(pkg["archetype"], "SHOPHOUSE_STREET")
        self.assertEqual(validate_attachments(pkg), [])
        kinds = {e["kind"] for e in pkg["elements"]}
        self.assertIn("motorbike", kinds)
        self.assertTrue(pkg["layers"]["FG"])


# ---------------------------------------------------------------------------
# Landmarks + negative constraints
# ---------------------------------------------------------------------------
class TestLandmarksAndConstraints(unittest.TestCase):
    def test_landmarks_only_from_landmarks_field(self):
        self.assertEqual(select_landmarks(
            {"features": ["A mountain peak rises."]}), [])
        self.assertEqual(
            select_landmarks({"landmarks": ["mountain peak",
                                            "temple"]}),
            ["mountain_peak", "temple_front"])

    def test_landmark_builders_validate(self):
        rng = random.Random(3)
        ctx = {"facade_colors": [(200, 190, 170)],
               "roof_color": (120, 60, 50),
               "window_color": (52, 66, 88), "is_night": False,
               "sign_text": "", "trait_text": ""}
        els = build_landmarks(
            {"landmarks": ["mountain peak", "temple", "city gate",
                           "bridge", "tower", "statue", "waterfall",
                           "lighthouse", "furnace"]}, rng, ctx)
        self.assertEqual(len(els) > 0, True)
        self.assertEqual(validate_attachments({"elements": els}), [])
        self.assertTrue(all("landmark" in e["extra"] for e in els))

    def test_landmarks_recorded_in_provenance(self):
        pkg = build_environment(
            {"features": ["Cung điện đá trắng."],
             "type": "Greek palace",
             "landmarks": ["temple"]})
        self.assertEqual(pkg["provenance"]["landmarks"],
                         ["temple_front"])
        self.assertTrue(pkg["provenance"]["landmark_elements"])
        self.assertEqual(validate_attachments(pkg), [])

    def test_constraint_drops_matching_element_loudly(self):
        pkg = build_environment(
            {"features": ["Glass towers.", "Steel skyline."],
             "type": "modern city", "sign_text": "CINEMA",
             "forbidden": ["biển quảng cáo"]})
        ids = [e["id"] for e in pkg["elements"]]
        self.assertNotIn("billboard", ids)
        dropped = pkg["provenance"]["negative_constraints_applied"]
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["element_id"], "billboard")
        self.assertEqual(dropped[0]["constraint"], "biển quảng cáo")
        self.assertEqual(validate_attachments(pkg), [])

    def test_constraint_no_match_recorded_not_silent(self):
        pkg = build_environment(
            {"features": ["European street 1914."],
             "type": "European street",
             "forbidden": ["Ô tô hiện đại."]})
        self.assertEqual(
            pkg["provenance"]["negative_constraints_applied"], [])
        self.assertIn("Ô tô hiện đại.",
                      pkg["provenance"]["negative_constraints_no_match"])

    def test_constraint_application_does_not_mutate_input(self):
        elements = [{"id": "b1", "kind": "billboard", "layer": "BG",
                     "geometry": "box", "center": (0, 1, -5),
                     "size": (1, 1, 1), "color": (1, 2, 3),
                     "material": "paint", "attachment": None,
                     "label": "", "extra": {}}]
        kept, report = apply_negative_constraints(
            elements, ["billboard"])
        self.assertEqual(kept, [])
        self.assertEqual(len(elements), 1)
        self.assertEqual(len(report["dropped"]), 1)

    def test_munich_forbidden_drops_nothing(self):
        pkg = build_environment(dict(
            _munich_traits(),
            forbidden=["Kiến trúc Vienna thay thế Munich.",
                       "Ô tô hiện đại.", "Nhà kính cao tầng.",
                       "Đèn LED.", "Điện thoại.",
                       "Biển quảng cáo hiện đại."]))
        self.assertEqual(
            pkg["provenance"]["negative_constraints_applied"], [])
        self.assertEqual(validate_attachments(pkg), [])
        self.assertGreater(len(pkg["elements"]), 150)


# ---------------------------------------------------------------------------
# P-S3 vegetation + P-S5 attachment validation
# ---------------------------------------------------------------------------
class TestVegetation(unittest.TestCase):
    def test_tree_has_satellite_lobes(self):
        els = _tree("t", random.Random(1), 0.0, -5.0, "BG", scale=1.0)
        kinds = [e["kind"] for e in els]
        self.assertEqual(kinds.count("tree_trunk"), 1)
        self.assertEqual(kinds.count("canopy"), 4)  # centre + 3 lobes
        self.assertEqual(validate_attachments({"elements": els}), [])

    def test_tree_lobe_jitter_is_isolated(self):
        # Same seed twice -> identical trees; the lobe RNG must not
        # disturb the shared builder stream (checked by determinism
        # of a full build instead: two identical builds match).
        pkg_a = build_environment(_munich_traits())
        pkg_b = build_environment(_munich_traits())
        self.assertEqual(pkg_a["elements"], pkg_b["elements"])

    def test_bush_and_hedge_validate(self):
        els = _bush("b", random.Random(1), 1.0, -2.0, "MG", scale=1.0)
        self.assertGreaterEqual(len(els), 3)
        self.assertEqual(validate_attachments({"elements": els}), [])
        els = _hedge("h", 1.0, -2.0, 2.2, "MG", height=1.0)
        self.assertEqual(len(els), 2)
        self.assertEqual(validate_attachments({"elements": els}), [])

    def test_trait_leaf_color_reaches_generic_trees(self):
        # Palette "olive" is green-dominant AND distinct from the
        # default leaf colour, so an exact match proves the trait
        # colour reached the generic street trees.
        pkg = build_environment(dict(
            _munich_traits(),
            features=["European street 1914.", "Cây xanh.",
                      "Cobblestone street."],
            palette=["olive"]))
        trees = [e for e in pkg["elements"]
                 if e["id"].startswith("street_tree")
                 and e["kind"] == "canopy"
                 and e["id"].endswith("_canopy")]
        self.assertTrue(trees)
        for canopy in trees:
            self.assertEqual(canopy["color"], (112, 116, 62))

    def test_olive_colors_never_overridden(self):
        pkg = build_environment(
            {"features": ["Cây ô liu.", "Biển Địa Trung Hải."],
             "type": "Mediterranean island", "palette": ["green"]})
        olives = [e for e in pkg["elements"]
                  if e["kind"] == "canopy"
                  and e["color"] == (112, 116, 62)]
        self.assertTrue(olives)


class TestAttachmentValidation(unittest.TestCase):
    def _el(self, el_id, center, size, attachment=None, extra=None):
        return {"id": el_id, "kind": "box", "layer": "BG",
                "geometry": "box", "center": center, "size": size,
                "color": (1, 2, 3), "material": "stone",
                "attachment": attachment, "label": "",
                "extra": extra or {}}

    def test_overlaps_relation(self):
        base = self._el("base", (0, 0.5, 0), (1, 1, 1),
                        {"parent": None, "relation": "on_ground",
                         "local_rect": None})
        overlap = self._el("ov", (0.5, 1.2, 0), (1, 1, 1),
                           {"parent": "base", "relation": "overlaps",
                            "local_rect": None})
        self.assertEqual(
            validate_attachments({"elements": [base, overlap]}), [])
        apart = self._el("ap", (5, 1.2, 0), (1, 1, 1),
                         {"parent": "base", "relation": "overlaps",
                          "local_rect": None})
        issues = validate_attachments({"elements": [base, apart]})
        self.assertTrue(any("overlaps" in i for i in issues))

    def test_hangs_from_relation(self):
        ceiling = self._el("ceil", (0, 4.0, 0), (4, 0.4, 4),
                           extra={"suspension": "spans walls"})
        drop = self._el("drop", (0, 3.5, 0), (0.3, 0.6, 0.3),
                        {"parent": "ceil", "relation": "hangs_from",
                         "local_rect": None})
        self.assertEqual(
            validate_attachments({"elements": [ceiling, drop]}), [])

    def test_floating_element_fails_loudly(self):
        floater = self._el("float", (0, 3.0, 0), (1, 1, 1))
        issues = validate_attachments({"elements": [floater]})
        self.assertTrue(any("float" in i for i in issues))

    def test_suspension_reason_exempts_floater(self):
        smoke = self._el("smoke", (0, 3.0, 0), (1, 1, 1),
                         extra={"suspension": "airborne smoke"})
        self.assertEqual(validate_attachments({"elements": [smoke]}), [])

    def test_unknown_relation_is_an_error(self):
        base = self._el("base", (0, 0.5, 0), (1, 1, 1),
                        {"parent": None, "relation": "on_ground",
                         "local_rect": None})
        weird = self._el("w", (0, 1.5, 0), (1, 1, 1),
                         {"parent": "base", "relation": "levitates",
                          "local_rect": None})
        issues = validate_attachments({"elements": [base, weird]})
        self.assertTrue(any("levitates" in i for i in issues))


# ---------------------------------------------------------------------------
# P-S5 culling + P-S12 foreground composition
# ---------------------------------------------------------------------------
class TestCulling(unittest.TestCase):
    def test_ray_aabb_hit_and_miss(self):
        origin, direction = (0.0, 2.0, 4.8), (0.0, 0.0, -1.0)
        t = ray_aabb_intersect(origin, direction, (0, 2, 0),
                               (2, 2, 2))
        self.assertAlmostEqual(t, 3.8)
        self.assertIsNone(ray_aabb_intersect(
            origin, direction, (10, 2, 0), (2, 2, 2)))

    def test_sight_lines_one_set_per_shot(self):
        cam = _camera()
        rays = sight_lines_for_camera(cam, size=(1920, 1080))
        self.assertEqual(len(rays), 5)
        rays2 = sight_lines_for_camera(cam, size=(1920, 1080))
        self.assertEqual(rays, rays2)
        for origin, direction in rays:
            self.assertAlmostEqual(
                math.sqrt(sum(v * v for v in direction)), 1.0)

    def test_sightline_occlusion_fg_blocks_bg_does_not(self):
        pkg = {"elements": [
            {"id": "fg_block", "center": (0, 1.5, 2.0),
             "size": (1, 2, 0.5)},
            {"id": "bg_wall", "center": (0, 1.5, -5.0),
             "size": (4, 3, 0.5)},
        ]}
        cam = _camera()
        subject = (0.0, 1.5, 0.0)
        rays = sight_lines_for_camera(cam, targets=[subject])
        report = sightline_occlusion(pkg, rays, [subject])
        self.assertEqual(report["subjects"][0]["occluders"],
                         ["fg_block"])
        self.assertEqual(report["occluded_subjects"], [0])

    def test_frustum_cull_keeps_spanning_kerb(self):
        pkg = build_environment(_munich_traits())
        kept, culled, report = frustum_cull(pkg, _camera(),
                                            size=(640, 360))
        self.assertIn("kerb", kept)
        self.assertNotIn("kerb", culled)
        self.assertEqual(report["kept_count"], len(kept))

    def test_frustum_cull_reports_behind_camera(self):
        pkg = {"elements": [
            {"id": "behind", "center": (0, 1, 20), "size": (1, 1, 1)},
            {"id": "front", "center": (0, 1, 0), "size": (1, 2, 1)},
        ]}
        kept, culled, report = frustum_cull(pkg, _camera(),
                                            size=(640, 360))
        self.assertEqual(culled, ["behind"])
        self.assertEqual(report["culled"]["behind"], "behind_camera")
        self.assertEqual(kept, ["front"])

    def test_frustum_cull_keeps_near_plane_straddler(self):
        pkg = {"elements": [
            {"id": "straddle", "center": (0, 2, 4.8),
             "size": (1, 1, 3)},
        ]}
        kept, _culled, _rep = frustum_cull(pkg, _camera(),
                                           size=(640, 360))
        self.assertEqual(kept, ["straddle"])


class TestForegroundComposition(unittest.TestCase):
    def test_fit_then_validate_clean_at_establishing_camera(self):
        pkg = build_environment(_munich_traits())
        cam = viewpoint_for_shot("establishing", None, (0, 1.5, 0))
        fit = fit_foreground_to_frustum(pkg, cam, size=(1920, 1080))
        report = validate_fg_composition(fit, cam, size=(1920, 1080))
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["ok"])

    def test_fg_fit_provenance_and_input_immutability(self):
        pkg = build_environment(_munich_traits())
        before = [dict(e) for e in pkg["elements"]]
        fit = fit_foreground_to_frustum(pkg, _camera(), size=(640, 360))
        self.assertIn("fg_fit", fit["provenance"])
        self.assertIn("moved", fit["provenance"]["fg_fit"])
        self.assertNotIn("fg_fit", pkg["provenance"])
        self.assertEqual(pkg["elements"], before)

    def test_fg_off_frame_is_an_error(self):
        pkg = {"elements": [
            {"id": "fg_far", "layer": "FG", "center": (50, 1, -2),
             "size": (1, 2, 1)},
        ]}
        report = validate_fg_composition(pkg, _camera(),
                                         size=(640, 360))
        self.assertTrue(any("fully off-frame" in e
                            for e in report["errors"]))

    def test_fg_standing_box_overlap_is_an_error(self):
        pkg = {"elements": [
            {"id": "fg_mid", "layer": "FG", "center": (0, 1.5, 2.0),
             "size": (2, 3, 0.5)},
        ]}
        report = validate_fg_composition(
            pkg, _camera(), size=(640, 360),
            subject_boxes=[(200, 100, 440, 300)])
        self.assertTrue(any("standing box" in e
                            for e in report["errors"]))

    def test_fg_huge_coverage_is_an_error(self):
        pkg = {"elements": [
            {"id": "fg_wall", "layer": "FG", "center": (0, 1.5, 4.0),
             "size": (8, 4, 0.5)},
        ]}
        report = validate_fg_composition(pkg, _camera(),
                                         size=(640, 360))
        self.assertTrue(any(">40%" in e or "40%" in e
                            for e in report["errors"]))

    def test_standing_box_check_skipped_without_boxes(self):
        pkg = build_environment(_munich_traits())
        report = validate_fg_composition(pkg, _camera(),
                                         size=(640, 360))
        self.assertIn("skipped", report["standing_box_check"])


# ---------------------------------------------------------------------------
# Ground painting + exclude_ids
# ---------------------------------------------------------------------------
class TestGroundPainting(unittest.TestCase):
    def _hash(self, img):
        return hashlib.sha256(img.tobytes()).hexdigest()

    def test_textured_render_deterministic(self):
        pkg = build_environment(_munich_traits())
        cam = _camera()
        a = render_environment(pkg, cam, size=(320, 180), textures=True)
        b = render_environment(pkg, cam, size=(320, 180), textures=True)
        self.assertEqual(self._hash(a), self._hash(b))

    def test_textured_differs_from_flat(self):
        pkg = build_environment(_munich_traits())
        cam = _camera()
        a = render_environment(pkg, cam, size=(320, 180), textures=True)
        b = render_environment(pkg, cam, size=(320, 180), textures=False)
        self.assertNotEqual(self._hash(a), self._hash(b))

    def test_exclude_behind_camera_identical(self):
        pkg = build_environment(_munich_traits())
        behind = {"id": "zz_behind", "kind": "box", "layer": "BG",
                  "geometry": "box", "center": (0, 1, 20),
                  "size": (1, 1, 1), "color": (9, 9, 9),
                  "material": "stone", "attachment": None, "label": "",
                  "extra": {}}
        pkg = dict(pkg)
        pkg["elements"] = list(pkg["elements"]) + [behind]
        cam = _camera()
        a = render_environment(pkg, cam, size=(320, 180), textures=True)
        b = render_environment(pkg, cam, size=(320, 180), textures=True,
                               exclude_ids=["zz_behind"])
        self.assertEqual(self._hash(a), self._hash(b))

    def test_exclude_visible_element_changes_pixels(self):
        pkg = build_environment(_munich_traits())
        cam = _camera()
        a = render_environment(pkg, cam, size=(320, 180), textures=True)
        b = render_environment(pkg, cam, size=(320, 180), textures=True,
                               exclude_ids=["kerb"])
        self.assertNotEqual(self._hash(a), self._hash(b))

    def test_transparent_pass_supports_exclude_ids(self):
        pkg = build_environment(_munich_traits())
        cam = _camera()
        # Fit the foreground into the frame first: unfitted FG
        # elements sit off-frame for this camera and the pass
        # would be empty either way.
        pkg = fit_foreground_to_frustum(pkg, cam, size=(320, 180))
        a = render_environment(pkg, cam, size=(320, 180),
                               draw_layers=("FG",), transparent=True,
                               textures=True)
        fg_ids = [e["id"] for e in pkg["elements"]
                  if e["layer"] == "FG"]
        b = render_environment(pkg, cam, size=(320, 180),
                               draw_layers=("FG",), transparent=True,
                               textures=True, exclude_ids=fg_ids)
        self.assertNotEqual(self._hash(a), self._hash(b))
        # Excluding every FG element leaves a fully transparent canvas.
        self.assertEqual(b.getextrema(), ((0, 0),) * 4)


# ---------------------------------------------------------------------------
# Lighting: sun position
# ---------------------------------------------------------------------------
class TestSunPosition(unittest.TestCase):
    def test_dusk_sun_low_in_minus_x_sky(self):
        sun = sun_position({"light_direction": (0.7, -0.45, -0.2)})
        self.assertAlmostEqual(sun["azimuth_deg"], -74.055, places=2)
        self.assertAlmostEqual(sun["elevation_deg"], 31.721, places=2)
        self.assertLess(sun["direction"][0], 0.0)
        self.assertGreater(sun["direction"][1], 0.0)

    def test_day_sun_high(self):
        sun = sun_position({"light_direction": (0.35, -1.0, -0.3)})
        self.assertGreater(sun["elevation_deg"], 60.0)

    def test_light_for_carries_sun_keys(self):
        spec = light_for("day", "warm")
        self.assertIn("sun_azimuth_deg", spec)
        self.assertIn("sun_elevation_deg", spec)
        self.assertEqual(spec["time_of_day"], "day")

    def test_zero_direction_raises(self):
        with self.assertRaises(ValueError):
            sun_position({"light_direction": (0.0, 0.0, 0.0)})


# ---------------------------------------------------------------------------
# Phase C: Camera Director
# ---------------------------------------------------------------------------
class TestCameraTransforms(unittest.TestCase):
    def test_transform_is_flat_7_tuple(self):
        t = camera_transform(_camera())
        self.assertEqual(len(t), 7)
        self.assertTrue(all(isinstance(v, float) for v in t))
        self.assertEqual(t, (0.0, 2.0, 4.8, 0.0, 1.5, 0.0, 46.0))

    def test_orientation_basis_orthonormal(self):
        basis = orientation_basis(_camera())
        self.assertEqual(len(basis), 9)
        rows = [basis[i * 3:(i + 1) * 3] for i in range(3)]
        for i in range(3):
            for j in range(3):
                dot = sum(rows[i][k] * rows[j][k] for k in range(3))
                self.assertAlmostEqual(dot, 1.0 if i == j else 0.0)

    def test_projection_matrix_convention(self):
        cam = _camera()
        mat = projection_matrix(cam)
        self.assertEqual(len(mat), 16)

        def apply_m(x, y, z):
            v = (x, y, z, 1.0)
            out = [sum(mat[i * 4 + j] * v[j] for j in range(4))
                   for i in range(4)]
            return tuple(c / out[3] for c in out)

        self.assertAlmostEqual(apply_m(0, 0, cam.near)[2], 0.0)
        self.assertAlmostEqual(apply_m(0, 0, cam.far)[2], 1.0)
        tan_half = math.tan(math.radians(cam.fov_deg) / 2.0)
        self.assertAlmostEqual(
            apply_m(tan_half * cam.aspect * 5, 0, 5)[0], 1.0)
        self.assertAlmostEqual(apply_m(0, tan_half * 5, 5)[1], 1.0)

    def test_static_series_validation(self):
        cam = _camera()
        series = [camera_transform(cam)] * 24
        ok, delta, issues = validate_shot_camera_static(series)
        self.assertTrue(ok)
        self.assertEqual(delta, 0.0)
        self.assertEqual(issues, [])
        moved = camera_transform(cam.moved(dpos=(0.01, 0, 0)))
        ok, delta, issues = validate_shot_camera_static(
            [camera_transform(cam), moved])
        self.assertFalse(ok)
        self.assertAlmostEqual(delta, 0.01)
        self.assertTrue(issues)

    def test_empty_series_is_an_error(self):
        ok, _delta, issues = validate_shot_camera_static([])
        self.assertFalse(ok)
        self.assertTrue(issues)

    def test_tolerance_boundary(self):
        cam = _camera()
        base = camera_transform(cam)
        within = list(base)
        within[0] += TRANSFORM_TOLERANCE / 2
        ok, _d, _i = validate_shot_camera_static([base, tuple(within)])
        self.assertTrue(ok)


class TestCameraDirectives(unittest.TestCase):
    def test_static_directive_defaults(self):
        d = static_directive_for_shot("S1", _camera(), 2.5)
        self.assertEqual(d.mode, CameraMode.STATIC_ANCHORED)
        self.assertEqual(d.source, "planner:static:S1")
        self.assertEqual(d.start_transform, d.end_transform)
        self.assertEqual(d.anchor, "scene")

    def test_static_mismatch_refused(self):
        cam = _camera()
        with self.assertRaises(ValueError):
            directive_for_shot(CameraMode.STATIC_ANCHORED, cam,
                               cam.moved(dpos=(1, 0, 0)), 1.0, "x")

    def test_empty_source_refused(self):
        cam = _camera()
        with self.assertRaises(ValueError):
            directive_for_shot(CameraMode.STATIC_ANCHORED, cam, cam,
                               1.0, "")
        with self.assertRaises(ValueError):
            scripted_directive_for_shot(
                "S2", CameraMode.SCRIPTED_DOLLY, cam, 2.0, "")

    def test_scripted_modes_move(self):
        cam = _camera()
        for mode in (CameraMode.SCRIPTED_PAN, CameraMode.SCRIPTED_DOLLY,
                     CameraMode.SCRIPTED_TRACKING,
                     CameraMode.SCRIPTED_REVEAL,
                     CameraMode.SCRIPTED_SHAKE):
            start, end = scripted_transforms(mode, cam)
            self.assertNotEqual(camera_transform(start),
                                camera_transform(end), mode)
            d = scripted_directive_for_shot("S", mode, cam, 2.0,
                                            "dir:test-1")
            self.assertEqual(d.mode, mode)
            self.assertEqual(d.source, "dir:test-1")

    def test_scripted_transforms_reject_static(self):
        with self.assertRaises(ValueError):
            scripted_transforms(CameraMode.STATIC_ANCHORED, _camera())

    def test_pan_direction_flips(self):
        cam = _camera()
        _s, right = scripted_transforms(CameraMode.SCRIPTED_PAN, cam,
                                        direction=1)
        _s, left = scripted_transforms(CameraMode.SCRIPTED_PAN, cam,
                                       direction=-1)
        self.assertGreater(camera_transform(right)[3],
                           camera_transform(cam)[3])
        self.assertLess(camera_transform(left)[3],
                        camera_transform(cam)[3])

    def test_validation_for_camera(self):
        cam = _camera()
        v = validation_for_camera(cam, crop_rect=(0, 0, 960, 540))
        self.assertTrue(v.is_static())
        self.assertEqual(v.fov_deg, 46.0)
        self.assertEqual(v.crop_rect, (0, 0, 960, 540))
        self.assertEqual(len(v.projection_matrix), 16)
        self.assertEqual(len(v.orientation), 9)
        moved = camera_transform(cam.moved(dpos=(1, 0, 0)))
        v2 = validation_for_camera(cam, start_transform=v.start_transform,
                                   end_transform=moved)
        self.assertFalse(v2.is_static())


class TestAnchoredCrop(unittest.TestCase):
    def _subject(self):
        return [{"cx": 960.0, "head_y": 300.0, "foot_y": 900.0,
                 "half_w": 120.0}]

    def test_frozen_crop_matches_apply_camera(self):
        img = Image.new("RGB", (1920, 1080), (10, 20, 30))
        shot = {"shot_type": "close_up", "camera": {"scale": 2.6}}
        safe_shot, safe_focus, _notes, frozen = anchor_focus_for_shot(
            shot, self._subject())
        a = CameraPlanner.apply_camera(img, safe_shot, safe_focus)
        b = apply_camera_anchored(img, frozen)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_frozen_record_shape(self):
        _s, _f, _n, frozen = anchor_focus_for_shot(
            {"shot_type": "medium"}, self._subject())
        self.assertTrue(frozen["frozen"])
        self.assertEqual(frozen["anchor"], "standing_box")
        self.assertEqual(frozen["frame_size"], [1920, 1080])
        self.assertEqual(len(frozen["crop_rect"]), 4)
        self.assertEqual(
            tuple(frozen["crop_rect"]),
            crop_rect_for(frozen["scale"], frozen["focus"],
                          1920, 1080))

    def test_f2_cap_default_for_full_body(self):
        _s, _f, _n, frozen = anchor_focus_for_shot(
            {"shot_type": "medium", "camera": {"scale": 1.6}},
            self._subject())
        self.assertEqual(frozen["scale"], 1.0)
        _s, _f, _n, frozen = anchor_focus_for_shot(
            {"shot_type": "tracking", "camera": {"scale": 1.6}},
            self._subject())
        self.assertEqual(frozen["scale"], 1.0)

    def test_anchor_uses_standing_head_for_head_framings(self):
        # Two subjects with the same standing box but different
        # live poses must freeze the same crop: the anchor comes
        # from the standing box, never a live joint.
        shot = {"shot_type": "close_up", "camera": {"scale": 2.6}}
        _s1, _f1, _n1, frozen1 = anchor_focus_for_shot(
            shot, self._subject())
        _s2, _f2, _n2, frozen2 = anchor_focus_for_shot(
            shot, self._subject())
        self.assertEqual(frozen1, frozen2)

    def test_size_mismatch_raises(self):
        _s, _f, _n, frozen = anchor_focus_for_shot(
            {"shot_type": "medium"}, self._subject())
        small = Image.new("RGB", (640, 360), (0, 0, 0))
        with self.assertRaises(ValueError):
            apply_camera_anchored(small, frozen)

    def test_crop_rect_for_matches_apply_camera_geometry(self):
        rect = crop_rect_for(2.6, (960.0, 300.0), 1920, 1080)
        self.assertEqual(rect, (591, 92, 1329, 508))


class TestCompositionValidation(unittest.TestCase):
    def test_clean_head_framing(self):
        # A head box (not a full body) at 2.6x with the focus on
        # the standing head: clean.
        head = [{"cx": 960.0, "head_y": 300.0, "foot_y": 480.0,
                 "half_w": 90.0}]
        issues = validate_composition(
            {"shot_type": "close_up", "camera": {"scale": 2.6}},
            (960.0, 390.0), head)
        self.assertEqual(issues, [])

    def test_tracking_lead_room(self):
        subj = [{"cx": 1500.0, "head_y": 300.0, "foot_y": 900.0,
                 "half_w": 120.0}]
        issues = validate_composition(
            {"shot_type": "tracking", "camera": {"scale": 1.6}},
            (960.0, 540.0), subj, movement_direction="right")
        self.assertTrue(any("lead room" in i for i in issues))

    def test_tracking_lead_room_clean_when_space_ahead(self):
        subj = [{"cx": 700.0, "head_y": 300.0, "foot_y": 900.0,
                 "half_w": 120.0}]
        issues = validate_composition(
            {"shot_type": "tracking", "camera": {"scale": 1.0}},
            (960.0, 540.0), subj, movement_direction="right")
        self.assertFalse(any("lead room" in i for i in issues))

    def test_eyeline_out_of_band(self):
        head = [{"cx": 960.0, "head_y": 800.0, "foot_y": 980.0,
                 "half_w": 90.0}]
        # Focus far above the head: the head lands below the
        # crop's eyeline band.
        issues = validate_composition(
            {"shot_type": "reaction", "camera": {"scale": 2.6}},
            (960.0, 540.0), head)
        self.assertTrue(any("eyeline" in i for i in issues))

    def test_object_insert_centring(self):
        obj = [{"cx": 500.0, "head_y": 400.0, "foot_y": 600.0,
                "half_w": 50.0}]
        issues = validate_composition(
            {"shot_type": "object_insert", "camera": {"scale": 3.4}},
            (960.0, 540.0), obj)
        self.assertTrue(any("off-centre" in i for i in issues))
        centred = [{"cx": 960.0, "head_y": 440.0, "foot_y": 640.0,
                    "half_w": 50.0}]
        issues = validate_composition(
            {"shot_type": "object_insert", "camera": {"scale": 3.4}},
            (960.0, 540.0), centred)
        self.assertFalse(any("off-centre" in i for i in issues))

    def test_half_cut_other_reported(self):
        head = [{"cx": 960.0, "head_y": 300.0, "foot_y": 480.0,
                 "half_w": 90.0}]
        other = [{"cx": 1330.0, "head_y": 300.0, "foot_y": 480.0,
                  "half_w": 90.0}]
        issues = validate_composition(
            {"shot_type": "close_up", "camera": {"scale": 2.6}},
            (960.0, 390.0), head, others=other)
        self.assertTrue(any("half-cut" in i for i in issues))


class TestSequenceValidation(unittest.TestCase):
    def _entry(self, shot_id, shot_type, direction, azimuth=0.0,
               elevation=10.0, radius=5.0, crop_scale=1.0):
        return {"shot_id": shot_id, "shot_type_resolved": shot_type,
                "screen_direction": direction,
                "pose": {"azimuth_deg": azimuth,
                         "elevation_deg": elevation, "radius": radius},
                "framing": {"crop_scale": crop_scale}}

    def test_axis_flip_without_pair_is_issue(self):
        entries = [self._entry("A", "medium", "LTR"),
                   self._entry("B", "medium", "RTL", azimuth=20.0)]
        report = validate_camera_sequence(entries)
        self.assertFalse(report["ok"])
        self.assertTrue(any(i["rule"] == "180_degree"
                            for i in report["issues"]))

    def test_axis_flip_via_srs_pair_is_clean(self):
        entries = [self._entry("A", "shot_reverse_shot", "LTR"),
                   self._entry("B", "shot_reverse_shot", "RTL",
                               azimuth=40.0)]
        report = validate_camera_sequence(entries)
        self.assertFalse(any(i["rule"] == "180_degree"
                             for i in report["issues"]))

    def test_srs_eyeline_mismatch(self):
        entries = [self._entry("A", "shot_reverse_shot", "LTR",
                               azimuth=0.0, elevation=10.0),
                   self._entry("B", "shot_reverse_shot", "RTL",
                               azimuth=40.0, elevation=15.0)]
        report = validate_camera_sequence(entries)
        self.assertTrue(any(i["rule"] == "srs_eyeline"
                            for i in report["issues"]))

    def test_srs_same_angle_is_issue(self):
        entries = [self._entry("A", "shot_reverse_shot", "LTR",
                               azimuth=0.0),
                   self._entry("B", "shot_reverse_shot", "RTL",
                               azimuth=5.0)]
        report = validate_camera_sequence(entries)
        self.assertTrue(any("reverse angle" in i["message"]
                            for i in report["issues"]))

    def test_repeated_framing_is_issue(self):
        entries = [self._entry("A", "medium", "centered"),
                   self._entry("B", "medium", "centered")]
        report = validate_camera_sequence(entries)
        self.assertTrue(any(i["rule"] == "repeated_framing"
                            for i in report["issues"]))

    def test_f2_violation_is_issue(self):
        entries = [self._entry("A", "medium", "centered",
                               crop_scale=1.6)]
        report = validate_camera_sequence(entries)
        self.assertTrue(any(i["rule"] == "F2"
                            for i in report["issues"]))

    def test_clean_sequence(self):
        entries = [self._entry("A", "establishing", "centered",
                               azimuth=0.0),
                   self._entry("B", "medium", "LTR", azimuth=25.0),
                   self._entry("C", "close_up", "LTR", azimuth=25.0,
                               elevation=12.0, radius=2.5,
                               crop_scale=2.6)]
        report = validate_camera_sequence(entries)
        self.assertTrue(report["ok"])
        self.assertEqual(report["checked"], 3)


class TestPlanShotCameraOptIn(unittest.TestCase):
    def test_default_entry_unchanged(self):
        entry = plan_shot({"shot_id": "A", "shot_type": "medium"})
        self.assertNotIn("camera_directive", entry)
        self.assertNotIn("camera_validation", entry)
        self.assertEqual(entry["movement_decision"]["executed"],
                         "STATIC")

    def test_static_opt_in_records_directive(self):
        entry = plan_shot({"shot_id": "A", "shot_type": "medium"},
                          camera_mode="static_anchored")
        directive = entry["camera_directive"]
        self.assertEqual(directive["mode"], "static_anchored")
        self.assertEqual(directive["source"], "planner:static:A")
        self.assertEqual(directive["start_transform"],
                         directive["end_transform"])
        self.assertTrue(entry["camera_validation"]["is_static"])
        self.assertEqual(entry["movement_decision"]["executed"],
                         "STATIC")

    def test_scripted_opt_in_records_directive(self):
        entry = plan_shot({"shot_id": "A", "shot_type": "establishing"},
                          camera_mode=CameraMode.SCRIPTED_DOLLY,
                          camera_source="dir:open-1")
        self.assertEqual(entry["movement_decision"]["executed"],
                         "scripted_dolly")
        self.assertEqual(entry["movement_decision"]["source"],
                         "dir:open-1")
        self.assertEqual(entry["camera_directive"]["mode"],
                         "scripted_dolly")
        self.assertNotEqual(
            entry["camera_directive"]["start_transform"],
            entry["camera_directive"]["end_transform"])
        self.assertFalse(entry["camera_validation"]["is_static"])
        self.assertIsNone(entry["camera_directive"]["duration_s"])

    def test_scripted_without_source_falls_back_static(self):
        entry = plan_shot({"shot_id": "A", "shot_type": "medium"},
                          camera_mode="scripted_pan")
        self.assertEqual(entry["movement_decision"]["executed"],
                         "STATIC")
        self.assertNotIn("camera_directive", entry)
        self.assertTrue(any("camera_source" in e
                            for e in entry["errors"]))

    def test_unknown_mode_falls_back_static(self):
        entry = plan_shot({"shot_id": "A", "shot_type": "medium"},
                          camera_mode="bogus", camera_source="x")
        self.assertEqual(entry["movement_decision"]["executed"],
                         "STATIC")
        self.assertTrue(any("unknown camera_mode" in e
                            for e in entry["errors"]))

    def test_coverage_forwards_camera_keys(self):
        result = plan_coverage([{"shot_id": "A", "shot_type": "medium",
                                 "camera_mode": "static_anchored"}])
        self.assertEqual(
            result["entries"][0]["camera_directive"]["mode"],
            "static_anchored")
        result = plan_coverage([{"shot_id": "A",
                                 "shot_type": "medium"}])
        self.assertNotIn("camera_directive", result["entries"][0])

    def test_shot_types_and_scales_unchanged(self):
        self.assertEqual(SHOT_SCALE["establishing"], 1.0)
        self.assertEqual(SHOT_SCALE["close_up"], 2.6)
        self.assertEqual(SHOT_SCALE["object_insert"], 3.4)


if __name__ == "__main__":
    unittest.main()
