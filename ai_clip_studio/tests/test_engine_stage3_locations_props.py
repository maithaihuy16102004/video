"""Stage 3 engine tests: F5 locations + F7 props.

F5: LOCATION trait data must drive DISTINCT environments (never a
substituted street); map-kind locations compose as a map board, and
the block's TYPE data (not only its features) drives the kind.
F7: the general prop system covers Ep1 v2's wallet/letter/pen/bag
plus general kinds; props attach to the holder's hand, and fall to
the ground only when no holder is known.

Run: python3 -m unittest ai_clip_studio.tests.test_engine_stage3_locations_props
from ~/workspace/video-16x9-v2/
"""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_clip_studio.product_renderer import (
    CAM, H, PROP_KINDS, W, _draw_prop, _enrich_location_block,
    _render_shot, _shot_location_kind, compose_location,
    infer_prop_kind, plan_shots)
from ai_clip_studio.renderer25d import render as render_mod
from ai_clip_studio.renderer25d.scene import Scene25D


def _block(location_id, name, type_text, features, **extra):
    block = {
        "location_id": location_id, "name": name, "type": type_text,
        "features": features, "foreground": "", "background": "",
        "lighting": "daylight", "weather": "Clear",
        "palette": ["Cream", "gray", "muted brown"],
        "render_traits": {"setting": name, "mood": "warm",
                          "time_of_day": "day"},
    }
    block.update(extra)
    return block


# Six trait blocks in the Ep1 v2 shapes (type + features), built
# inline so the test does not depend on the example script file.
SIX_BLOCKS = [
    _block("LOC_MUNICH_STREET", "Munich street", "Street",
           ["Cửa sổ cao.", "Mái nhà dốc.", "Đường lát đá.",
            "Cột đèn đường."]),
    _block("LOC_EUROPE_MAP", "Europe map", "Historical animated map",
           ["Đế quốc Đức.", "Đế quốc Áo-Hung.", "Pháp.",
            "Đế quốc Nga.", "Anh.", "Bỉ.",
            "Đường biên giới được vẽ rõ."]),
    _block("LOC_RECRUITMENT_OFFICE", "Recruitment office", "Interior",
           ["Bàn gỗ.", "Cửa sổ.", "Bàn làm việc.",
            "Tường gạch."]),
    _block("LOC_BAVARIA_BARRACKS", "Barracks", "Barracks",
           ["Doanh trại.", "Sân tập.", "Hàng rào gỗ."]),
    _block("LOC_FLANDERS_ROUTE", "Flanders route", "Rural road",
           ["Con đường đất.", "Cánh đồng.", "Cây cối.",
            "Hàng rào."]),
    _block("LOC_YPRES_TRENCH", "Ypres trench", "Trench",
           ["Chiến hào.", "Bao cát.", "Cây gãy."]),
]


class TestLocations(unittest.TestCase):
    def test_six_locations_compose_distinct_kinds(self):
        kinds = [compose_location(b)["kind"] for b in SIX_BLOCKS]
        self.assertEqual(len(set(kinds)), 6,
                         f"kinds must all differ: {kinds}")

    def test_map_kind_from_type_text_alone(self):
        # No map word in the features: the TYPE drives the kind.
        block = _block("LOC_MAP2", "War map", "Historical animated map",
                       ["Đế quốc Đức.", "Pháp."])
        self.assertEqual(compose_location(block)["kind"], "map_panel")

    def test_map_labels_skip_border_descriptions(self):
        comp = compose_location(SIX_BLOCKS[1])
        labels = [b.label for b in comp["boxes"]
                  if b.name.startswith("map_region_")]
        self.assertEqual(len(labels), 6)
        joined = " ".join(labels).lower()
        self.assertNotIn("biên giới", joined)
        self.assertNotIn("border", joined)
        self.assertIn("Đế quốc Đức", labels)

    def test_enrichment_never_mutates_the_package_block(self):
        block = _block("LOC_MAP3", "War map", "Street", ["Pháp."])
        package = {"v1_locations": [
            {"location_id": "LOC_MAP3", "type": "Historical animated map",
             "fields": {"MAP_STYLE": "period board"}}]}
        before = dict(block)
        enriched = _enrich_location_block(package, block)
        self.assertEqual(block, before, "the package block is immutable")
        self.assertIsNot(enriched, block)
        self.assertEqual(compose_location(enriched)["kind"], "map_panel")

    def test_six_locations_render_distinctly(self):
        frames = []
        for block in SIX_BLOCKS:
            comp = compose_location(block)
            scene = Scene25D(boxes=comp["boxes"], characters=[],
                             camera=CAM, sky_top=comp["sky_top"],
                             sky_bottom=comp["sky_bottom"],
                             ground_color=comp["ground_color"],
                             ground_extent=30.0)
            frames.append(np.asarray(
                render_mod.render_frame(scene, W, H)).astype(float))
        worst = None
        for i in range(len(frames)):
            for j in range(i + 1, len(frames)):
                mad = float(np.abs(frames[i] - frames[j]).mean())
                if worst is None or mad < worst[0]:
                    worst = (mad, i, j)
        # Measured 26.83 after the map fix; 5.0 is a wide margin
        # against "same scene, different tint".
        self.assertGreater(worst[0], 5.0,
                           f"closest pair {worst[1]}/{worst[2]} "
                           f"MAD={worst[0]:.2f}")

    def test_ep1_map_shot_kind_is_map_panel(self):
        # The real Ep1 v2 flow: parse + adapt + plan -> the scene-2
        # shot's location kind is map_panel (the adapter's trait
        # block carries no type; the engine-side enrichment supplies
        # it from the preserved v1_locations record).
        from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
        from ai_clip_studio.studio_script_v1_adapter import adapt_document
        root = Path(__file__).resolve().parents[2]
        text = (root / "examples"
                / "hitler_ep01_munich_1914.studio.md").read_text(
                    encoding="utf-8")
        package = adapt_document(parse_studio_script_v1(text))
        shots = plan_shots(
            package,
            [{"line_index": i + 1, "duration": 3.0} for i in range(9)])
        scene2 = [s for s in shots if s.get("scene") == 2]
        self.assertTrue(scene2, "Ep1 scene 2 must produce shots")
        self.assertTrue(all(_shot_location_kind(s) == "map_panel"
                            for s in scene2),
                        "every scene-2 shot must be a map view")


class TestProps(unittest.TestCase):
    def test_ep1_prop_kinds_covered(self):
        for kind in ("wallet", "letter", "pen", "bag"):
            self.assertIn(kind, PROP_KINDS)

    def test_infer_prop_kind_resolves_script_props(self):
        cases = [
            ({"name": "Chiếc ví", "type": "wallet"}, "wallet"),
            ({"name": "Lá thư", "type": "letter"}, "letter"),
            ({"name": "Cây bút", "type": "pen"}, "pen"),
            ({"name": "Chiếc túi", "type": "bag"}, "bag"),
            ({"name": "Bó hoa", "type": "flower"}, "flower"),
        ]
        for prop, want in cases:
            self.assertEqual(infer_prop_kind(prop), want, prop)

    def test_all_prop_kinds_draw_distinct_shapes(self):
        canvases = {}
        for kind in sorted(PROP_KINDS):
            img = Image.new("RGB", (200, 160), (255, 255, 255))
            _draw_prop(ImageDraw.Draw(img), 100, 80, kind=kind)
            canvases[kind] = np.asarray(img).astype(int)
        kinds = sorted(PROP_KINDS)
        worst = None
        for i, a in enumerate(kinds):
            for b in kinds[i + 1:]:
                diff = float(np.abs(canvases[a] - canvases[b]).mean())
                if worst is None or diff < worst[0]:
                    worst = (diff, a, b)
        # Most-similar pair measured 3.86 (book/wallet).
        self.assertGreater(worst[0], 1.0,
                           f"closest pair {worst[1]}/{worst[2]}")

    def test_unknown_prop_kind_renders_as_generic(self):
        img = Image.new("RGB", (200, 160), (255, 255, 255))
        _draw_prop(ImageDraw.Draw(img), 100, 80, kind="spaceship")
        ref = Image.new("RGB", (200, 160), (255, 255, 255))
        _draw_prop(ImageDraw.Draw(ref), 100, 80, kind="generic")
        self.assertEqual(
            float(np.abs(np.asarray(img).astype(int)
                         - np.asarray(ref).astype(int)).mean()), 0.0)

    def test_prop_attaches_to_holder_hand_not_ground(self):
        # A/B on one planned solo line shot (medium, scale 1.0, so
        # still coordinates are full-frame coordinates). The flower
        # petals are the exact fill (220, 90, 120) — no scene box
        # uses it. Held -> petals at hand height; no holder (take
        # cue, solo cast) -> petals on the ground band.
        package = {
            "characters": [{"name": "An", "description": "young woman",
                            "template": "female",
                            "voice_hint": "giọng nữ",
                            "jacket_color": "#47BD75"}],
            "scenes": [{
                "number": 1,
                "location": {"location_keyword": "street",
                             "setting": "day street corner",
                             "mood": "warm", "time_of_day": "day"},
                "setting": "day street corner",
                "action_text": "An đứng một mình.",
                "action_cues": [],
                "action_lead_sec": 0.0,
                "lines": [{"speaker": "An", "kind": "dialogue",
                           "text": "Bông hoa này đẹp quá."}],
            }],
            "shot_directives": [
                {"scene": 1, "line_index": 1, "shot_type": "medium",
                 "camera_angle": "eye_level",
                 "camera_movement": "STATIC"}],
            "props": [{"id": "PROP_FLOWER", "name": "Bó hoa",
                       "type": "flower", "owner": ""}],
        }
        shots = plan_shots(
            package, [{"line_index": 1, "duration": 2.0}])
        shot = shots[0]
        shot["index"] = 0
        shot["props"] = ["PROP_FLOWER"]
        shot["prop_kind"] = "flower"

        def petal_centroid_y(prop_holder, cues):
            shot["prop_holder"] = prop_holder
            shot["action_cues"] = cues
            with tempfile.TemporaryDirectory() as tmp:
                rep = _render_shot({
                    "shot": shot, "package": package, "out_dir": tmp,
                    "still_only": True})
                arr = np.asarray(
                    Image.open(rep["still"]).convert("RGB")).astype(int)
            mask = (arr[:, :, 0] == 220) & (arr[:, :, 1] == 90) \
                & (arr[:, :, 2] == 120)
            ys, _xs = np.where(mask)
            self.assertGreater(len(ys), 50, "petals must be visible")
            return float(np.mean(ys))

        held_y = petal_centroid_y("An", [])
        self.assertLess(held_y, 750.0,
                        f"held prop must be at hand height, got y={held_y:.0f}")
        ground_y = petal_centroid_y(None, ["take"])
        self.assertGreater(ground_y, 800.0,
                           f"unheld prop must rest on the ground, "
                           f"got y={ground_y:.0f}")


if __name__ == "__main__":
    unittest.main()
