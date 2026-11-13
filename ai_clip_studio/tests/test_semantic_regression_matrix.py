"""Semantic regression matrix (directive section 16).

16 families, Vietnamese paraphrases + negative tests + unseen
scripts, driven through the REAL paths (resolver -> compiler ->
scene graph -> preflight -> planner -> renderer), never through
mocks of the code under test. NO hardcoding for Hitler/Zeus/
Minh/Lan: the unseen-script fixture (tests/fixtures/
unseen_garden_key.studio.md) carries new characters, locations
and props, and every paraphrase table uses fresh sentences.

Families:
 1 head-tilt vs bend          9 scene-local weather
 2 pocket vs ground          10 scene-local costume
 3 table vs receive          11 scene-local lighting
 4 crouch vs pickup          12 multi-shot narration
 5 open vs close             13 multi-character prop
 6 give vs receive           14 unknown mandatory props
 7 left vs right hand        15 conflicting directives
 8 prop ownership            16 cross-project isolation

TEST E (unseen script end-to-end) is the capstone class at the
end of this module. TEST A (wallet semantics) and TEST B
(environment isolation) were proven by A2/B2 and are referenced
from their proof artifacts; TEST C (Zeus handover) and TEST D
(narration continuity) assemble on the corrected full renders.

Known honest gaps (documented, not hidden):
- READ has no verb: "đọc thư" is honestly unsupported.
- One action per sentence: an expression layered on an action
  sentence ("mỉm cười nhìn ra cửa sổ") resolves the action; the
  expression rides the shot's expression record, not the event.
- A two-hand receive ("nhận bằng hai tay") records BOTH in the
  semantic record but stages at the left hand (engine default).
- Cross-scene prop carry-over is undeclared: preflight checks
  prop timelines per scene; a fresh scene may re-introduce a
  prop in a fresh state.

Run from ~/workspace/agent/:
  python3 -m unittest ai_clip_studio.tests.test_semantic_regression_matrix -v
"""

import copy
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import (
    FORBIDDEN_SEMANTIC_COMPILATIONS, compile_actions,
    resolve_semantic_action)
from ai_clip_studio.preflight import semantic_preflight_checks
from ai_clip_studio.product_flow import _scene_is_rainy
from ai_clip_studio.product_renderer import (
    _render_shot, _scene_costume_overrides, map_character, plan_shots)
from ai_clip_studio.prop_system import (
    ForbiddenPropTransition, SemanticPropTracker, check_chain_order,
    geometry_for_prop)
from ai_clip_studio.scene_graph import (
    build_scene_graph, validate_or_raise)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document
from ai_clip_studio.unified_timeline import build_unified_timeline

AGENT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / "fixtures" \
    / "unseen_garden_key.studio.md"


def _resolve(text, actor_id="CHAR_X"):
    return resolve_semantic_action(
        text, actor_id=actor_id, source_scene_id="SC01",
        source_shot_id="SC01_SH01", source_directive_id="D1")


def _package(name):
    return adapt_document(parse_studio_script_v1(
        (AGENT / "examples" / f"{name}.studio.md").read_text(
            encoding="utf-8")))


def _fixture_package():
    return adapt_document(parse_studio_script_v1(
        FIXTURE.read_text(encoding="utf-8")))


def _compile(pkg):
    sem = []
    events, unsupported = compile_actions(pkg, semantic_sink=sem)
    return events, unsupported, sem


def _plan_with_spans(pkg, n_lines):
    """W4-harness pattern: plan + compile with real shot spans."""
    shots = plan_shots(
        pkg, [{"line_index": i + 1, "duration": 3.0}
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
        pkg, timeline={"spans": spans})
    pkg["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None,
    }
    return shots, events, unsupported


class TestFamily01HeadTiltVsBend(unittest.TestCase):
    PARAPHRASES = (
        ("Mai hơi cúi đầu suy nghĩ.", "HEAD_TILT_DOWN"),
        ("An cúi đầu xuống, mắt nhìn xuống đất.", "HEAD_TILT_DOWN"),
        ("Cô ấy gục đầu xuống bàn.", "HEAD_TILT_DOWN"),
        ("Nam nghiêng đầu lắng nghe.", "HEAD_TILT_DOWN"),
        ("Bà cúi mặt trầm tư.", "HEAD_TILT_DOWN"),
        ("Nam cúi xuống nhặt chiếc chìa khóa.", "BEND_PICK"),
        ("Nam cúi người nhặt tờ giấy rơi.", "BEND_PICK"),
        ("Cô quỳ xuống nhặt đồng xu.", "BEND_PICK"),
        # Bare "nhặt" (no bend directed) is a plain pickup from
        # the ground, not a bend: PICK_FROM_GROUND, and the
        # renderer stages it without the kneel.
        ("Anh nhặt chiếc ví trên đường.", "PICK_FROM_GROUND"),
    )

    def test_paraphrases(self):
        for text, expected in self.PARAPHRASES:
            with self.subTest(text=text):
                rec = _resolve(text)
                self.assertIsNotNone(rec, text)
                self.assertEqual(rec.action_type, expected)

    def test_head_up_to_look_is_not_a_tilt_down(self):
        rec = _resolve("An ngẩng đầu nhìn lên bầu trời.")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.action_type, "LOOK_AT")

    def test_forbidden_pairs_never_compile(self):
        for pkg in (_package("hitler_ep01_munich_1914"),
                    _package("zeus_ep01_fall_of_cronus"),
                    _fixture_package()):
            events, _, _ = _compile(pkg)
            for e in events:
                sem = e.get("semantic_action_type")
                if sem in FORBIDDEN_SEMANTIC_COMPILATIONS:
                    self.assertNotIn(
                        e["action_type"],
                        FORBIDDEN_SEMANTIC_COMPILATIONS[sem],
                        f"{sem} compiled as {e['action_type']}: "
                        f"{e.get('directive_text')}")


class TestFamily02PocketVsGround(unittest.TestCase):
    PARAPHRASES = (
        ("Linh lấy điện thoại từ túi quần.", "TAKE_FROM_POCKET",
         "pocket"),
        ("Linh móc ví ra khỏi túi áo khoác.", "TAKE_FROM_POCKET",
         "pocket"),
        ("An rút thư từ túi áo.", "TAKE_FROM_POCKET", "pocket"),
        ("Cô lấy chìa khóa trong túi xách.", "TAKE_FROM_POCKET",
         "pocket"),
        ("Nam cúi xuống nhặt ví dưới đất.", "BEND_PICK", "ground"),
        ("Nam nhặt hòn đá trên mặt đất.", "PICK_FROM_GROUND",
         "ground"),
        ("Cô nhặt tờ giấy rơi dưới sàn.", "PICK_FROM_GROUND",
         "ground"),
    )

    def test_paraphrases(self):
        for text, expected, source in self.PARAPHRASES:
            with self.subTest(text=text):
                rec = _resolve(text)
                self.assertIsNotNone(rec, text)
                self.assertEqual(rec.action_type, expected)
                self.assertEqual(rec.source_location, source)

    def test_fixture_key_state_timeline(self):
        # Pocket take -> held; drop -> ground; pickup -> held.
        # The ground state exists ONLY between the drop and the
        # grasp: the key never rests on the ground before the drop.
        pkg = _fixture_package()
        shots, events, _ = _plan_with_spans(pkg, 5)
        scene1 = [e for e in events if e.get("scene_number") == 1]
        tracker = SemanticPropTracker(pkg["props"], scene1)
        self.assertEqual(tracker.initial_location("prop_key"),
                         "IN_POCKET")
        release = next(e for e in scene1
                       if e["action_type"] == "RELEASE")
        pickup = next(e for e in scene1
                      if e["action_type"] == "KNEEL_PICK")
        self.assertFalse(tracker.ground_rest_allowed(
            "prop_key", release["start_time"] - 0.1))
        self.assertTrue(tracker.ground_rest_allowed(
            "prop_key", pickup["start_time"] - 0.05))
        self.assertEqual(
            tracker.location_at("prop_key", pickup["end_time"]),
            "HELD_RIGHT")

    def test_fixture_rest_kinds_at_render(self):
        pkg = _fixture_package()
        shots, _, _ = _plan_with_spans(pkg, 5)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rests = {}
            for s in shots:
                did = s.get("directive_shot_id")
                if did not in ("SC01_SH02", "SC01_SH03"):
                    continue
                r = _render_shot({
                    "shot": s, "package": pkg,
                    "out_dir": str(out / f"shot_{s['index']:02d}"),
                    "still_only": True,
                })
                rests[did] = r["prop_rest_kinds"].get("prop_key")
        # Pocket take: the key rests hidden. Drop + pickup: the
        # key's rest is the ground it is dropped onto.
        self.assertEqual(rests["SC01_SH02"], "pocket")
        self.assertEqual(rests["SC01_SH03"], "ground")

    def test_drop_sequence_staging(self):
        # The key is at the hand until the release moment, on the
        # ground while it lies there, and back at the hand after
        # the grasp -- never at the rest position while held.
        from ai_clip_studio.prop_system import PropStateMachine
        pkg = _fixture_package()
        _, events, _ = _plan_with_spans(pkg, 5)
        shot_events = [e for e in events
                       if e.get("shot_id") == "SC01_SH03"]
        staging = {"prop_key": {"x": 700.0, "y": 900.0,
                                "angle": 0.0, "kind": "ground"}}
        psm = PropStateMachine(pkg["props"], shot_events,
                               staging=staging, ground_y=900.0)
        joints = {"CHAR_GARDENER": {
            "hand_l": (500.0, 400.0), "hand_r": (540.0, 400.0),
            "hip": (520.0, 600.0)}}
        release, pickup = shot_events
        held = psm.transform_at(
            "prop_key", release["start_time"] + 0.1, joints)
        self.assertEqual(held[3], "ATTACHED_TO_HAND")
        self.assertEqual((held[0], held[1]), (540.0, 400.0))
        lying = psm.transform_at(
            "prop_key", release["end_time"] + 0.05, joints)
        self.assertEqual(lying[3], "WORLD_STATIC")
        self.assertEqual((lying[0], lying[1]), (700.0, 900.0))
        grasped = psm.transform_at(
            "prop_key", pickup["end_time"] - 0.05, joints)
        self.assertEqual(grasped[3], "ATTACHED_TO_HAND")
        self.assertEqual((grasped[0], grasped[1]), (540.0, 400.0))


class TestFamily03TableVsReceive(unittest.TestCase):
    PARAPHRASES = (
        ("Tuấn lấy cuốn sách trên kệ.", "PICK_FROM_SURFACE"),
        ("Tuấn cầm lấy cây bút trên bàn.", "PICK_FROM_SURFACE"),
        ("Cô nhấc tách trà trên bàn lên.", "PICK_FROM_SURFACE"),
        ("Lan nhận chiếc ô từ tay Minh.", "RECEIVE_PROP"),
        ("Lan đón lấy bó hoa.", "RECEIVE_PROP"),
        ("Zeus nhận quyền trượng bằng tay phải.", "RECEIVE_PROP"),
    )
    NEGATIVES = (
        "An nhận ra mình đã quên chìa khóa.",
        "Cô nhận thấy trời sắp mưa.",
        "Mỗi người nhận một phần quyền cai quản.",
        "An nhận nhiệm vụ mới từ cấp trên.",
    )

    def test_paraphrases(self):
        for text, expected in self.PARAPHRASES:
            with self.subTest(text=text):
                rec = _resolve(text)
                self.assertIsNotNone(rec, text)
                self.assertEqual(rec.action_type, expected)

    def test_negatives_resolve_to_nothing(self):
        for text in self.NEGATIVES:
            with self.subTest(text=text):
                self.assertIsNone(_resolve(text), text)


class TestFamily04CrouchVsPickup(unittest.TestCase):
    PARAPHRASES = (
        ("Hùng cúi người tránh cành cây.", "CROUCH"),
        ("Hùng khom người né viên đá bay tới.", "CROUCH"),
        ("Cô hạ thấp người tránh làn khói.", "CROUCH"),
        ("An ngồi xổm xuống nhìn tổ kiến.", "CROUCH"),
        ("Hùng cúi xuống nhặt mũ rơi.", "BEND_PICK"),
        ("Hùng cúi người theo phản xạ.", "REACT"),
    )

    def test_paraphrases(self):
        for text, expected in self.PARAPHRASES:
            with self.subTest(text=text):
                rec = _resolve(text)
                self.assertIsNotNone(rec, text)
                self.assertEqual(rec.action_type, expected)


class TestFamily05OpenVsClose(unittest.TestCase):
    PARAPHRASES = (
        ("Bà mở nắp hộp ra.", "OPEN"),
        ("An mở ví xem tiền.", "OPEN"),
        ("Cô mở cổng sắt.", "OPEN"),
        ("Bà mở bức thư ra.", "OPEN"),
        ("An mở quyển sách ra đọc.", "OPEN"),
        ("Bà đóng nắp hộp lại.", "CLOSE"),
        ("An gấp ví lại.", "CLOSE"),
        ("Cô đóng cổng lại.", "CLOSE"),
    )

    def test_paraphrases(self):
        for text, expected in self.PARAPHRASES:
            with self.subTest(text=text):
                rec = _resolve(text)
                self.assertIsNotNone(rec, text)
                self.assertEqual(rec.action_type, expected)

    def test_container_states(self):
        events = [
            {"action_id": "A1", "action_type": "TAKE_OUT",
             "semantic_action_type": "TAKE_FROM_POCKET",
             "actor_id": "CHAR_A", "prop_id": "prop_wallet",
             "shot_id": "SC01_SH01", "scene_number": 1,
             "start_time": 0.0, "end_time": 1.0,
             "required_pose": {"params": {"hand": "r"}}},
            {"action_id": "A2", "action_type": "OPEN_WALLET",
             "semantic_action_type": "OPEN",
             "actor_id": "CHAR_A", "prop_id": "prop_wallet",
             "shot_id": "SC01_SH01", "scene_number": 1,
             "start_time": 1.0, "end_time": 2.0,
             "required_pose": {"params": {"hand": "both"}}},
            {"action_id": "A3", "action_type": "CLOSE_WALLET",
             "semantic_action_type": "CLOSE",
             "actor_id": "CHAR_A", "prop_id": "prop_wallet",
             "shot_id": "SC01_SH01", "scene_number": 1,
             "start_time": 2.0, "end_time": 3.0,
             "required_pose": {"params": {"hand": "both"}}},
        ]
        props = [{"id": "prop_wallet", "kind": "wallet"}]
        tracker = SemanticPropTracker(props, events)
        # Container changes land at the event END: open completes
        # at 2.0, close completes at 3.0.
        self.assertEqual(
            tracker.container_at("prop_wallet", 1.5), "CLOSED")
        self.assertEqual(
            tracker.container_at("prop_wallet", 2.5), "OPEN")
        self.assertEqual(
            tracker.container_at("prop_wallet", 3.5), "CLOSED")


class TestFamily06GiveVsReceive(unittest.TestCase):
    PARAPHRASES = (
        ("Minh đưa chiếc ô cho Lan.", "GIVE"),
        ("Cô trao bó hoa cho bà.", "GIVE"),
        # Formal transfer phrasing resolves to HAND_OVER, the
        # paired transfer, rather than the plain GIVE.
        ("An chuyển giao tài liệu cho sếp.", "HAND_OVER"),
        ("Lan nhận chiếc ô từ tay Minh.", "RECEIVE_PROP"),
        ("Bà đón lấy bức thư.", "RECEIVE_PROP"),
    )

    NEGATIVES = (
        # "trao đổi" (exchange/discuss) is not a give, even with
        # a later "cho".
        "Họ trao đổi ý kiến cho rõ ràng.",
        "Hai bên trao đổi thư từ cho nhau.",
    )

    def test_negatives(self):
        for text in self.NEGATIVES:
            with self.subTest(text=text):
                self.assertIsNone(_resolve(text), text)

    def test_paraphrases(self):
        for text, expected in self.PARAPHRASES:
            with self.subTest(text=text):
                rec = _resolve(text)
                self.assertIsNotNone(rec, text)
                self.assertEqual(rec.action_type, expected)

    def test_fixture_handover_timeline(self):
        # The letter: held by the boy, IN_TRANSIT during the
        # transfer, then held by the gardener. No teleport, no
        # duplicate: exactly one holder at every sampled time.
        pkg = _fixture_package()
        _, events, _ = _plan_with_spans(pkg, 5)
        scene2 = [e for e in events if e.get("scene_number") == 2]
        tracker = SemanticPropTracker(pkg["props"], scene2)
        handover = next(e for e in scene2
                        if e["action_type"] == "HAND_OVER")
        receive = next(e for e in scene2
                       if e["action_type"] == "RECEIVE_PROP")
        self.assertEqual(
            tracker.holder_at("prop_letter",
                              handover["start_time"] - 0.05),
            "CHAR_BOY")
        mid = (handover["start_time"] + receive["end_time"]) / 2
        self.assertTrue(
            tracker.transfer_in_progress("prop_letter", mid))
        self.assertIsNone(tracker.holder_at("prop_letter", mid))
        self.assertEqual(
            tracker.holder_at("prop_letter", receive["end_time"]),
            "CHAR_GARDENER")


class TestFamily07LeftVsRightHand(unittest.TestCase):
    PARAPHRASES = (
        ("Lan nhận lấy bó hoa bằng tay trái.", "RECEIVE_PROP",
         "LEFT"),
        ("Zeus nắm chặt tia sét bằng tay phải.", "HOLD", "RIGHT"),
        ("An nhận bằng hai tay.", "RECEIVE_PROP", "BOTH"),
        ("Lan nhận chiếc ô từ tay Minh.", "RECEIVE_PROP", "NONE"),
    )

    def test_paraphrases(self):
        for text, expected, hand in self.PARAPHRASES:
            with self.subTest(text=text):
                rec = _resolve(text)
                self.assertIsNotNone(rec, text)
                self.assertEqual(rec.action_type, expected)
                self.assertEqual(rec.interaction_hand, hand)

    def test_compiled_receive_carries_the_named_hand(self):
        # Fixture: left-hand receive; Zeus: right-hand receive.
        # The event's hand param drives both the PSM attachment
        # and the receive primitive -- it must name the hand the
        # script names, never the "r" default.
        pkg = _fixture_package()
        events, _, _ = _compile(pkg)
        recv = next(e for e in events
                    if e["action_type"] == "RECEIVE_PROP")
        self.assertEqual(
            (recv.get("required_pose") or {}).get("params", {}).get(
                "hand"), "l")
        zeus = _package("zeus_ep01_fall_of_cronus")
        events, _, _ = _compile(zeus)
        recv = next(e for e in events
                    if e.get("shot_id") == "SC08_SH02"
                    and e["action_type"] == "RECEIVE_PROP")
        self.assertEqual(
            (recv.get("required_pose") or {}).get("params", {}).get(
                "hand"), "r")


class TestFamily08PropOwnership(unittest.TestCase):
    def _events(self, spec):
        return [{"action_id": f"E{i}", "action_type": verb,
                 "actor_id": actor, "prop_id": pid,
                 "target_id": target, "start_time": float(i),
                 "end_time": float(i) + 0.5}
                for i, (verb, actor, pid, target) in
                enumerate(spec)]

    def test_three_way_chain_has_no_violations(self):
        events = self._events([
            ("TAKE_OUT", "CHAR_A", "prop_key", None),
            ("HAND_OVER", "CHAR_A", "prop_key", "CHAR_B"),
            ("RECEIVE_PROP", "CHAR_B", "prop_key", None),
            ("HAND_OVER", "CHAR_B", "prop_key", "CHAR_C"),
            ("RECEIVE_PROP", "CHAR_C", "prop_key", None),
        ])
        self.assertEqual(check_chain_order(events), [])

    def test_handover_without_grasp_is_a_violation(self):
        events = self._events([
            ("HAND_OVER", "CHAR_A", "prop_key", "CHAR_B"),
        ])
        violations = check_chain_order(events)
        self.assertEqual(len(violations), 1)
        self.assertIn("preceding grasp", violations[0]["issue"])

    def test_handover_by_non_holder_is_a_violation(self):
        events = self._events([
            ("TAKE_OUT", "CHAR_A", "prop_key", None),
            ("HAND_OVER", "CHAR_B", "prop_key", "CHAR_C"),
        ])
        violations = check_chain_order(events)
        self.assertEqual(len(violations), 1)
        self.assertIn("held by", violations[0]["issue"])

    def test_release_clears_ownership(self):
        events = self._events([
            ("TAKE_OUT", "CHAR_A", "prop_key", None),
            ("RELEASE", "CHAR_A", "prop_key", None),
            ("HAND_OVER", "CHAR_A", "prop_key", "CHAR_B"),
        ])
        violations = check_chain_order(events)
        self.assertEqual(len(violations), 1)


class TestFamily09SceneLocalWeather(unittest.TestCase):
    def test_fixture_rain_is_scene_2_only(self):
        pkg = _fixture_package()
        rainy = [s["number"] for s in pkg["scenes"]
                 if _scene_is_rainy(s)]
        self.assertEqual(rainy, [2])

    def test_ep1_rain_is_scene_6_only(self):
        pkg = _package("hitler_ep01_munich_1914")
        rainy = [s["number"] for s in pkg["scenes"]
                 if _scene_is_rainy(s)]
        self.assertEqual(rainy, [6])

    def test_zeus_has_no_rain(self):
        pkg = _package("zeus_ep01_fall_of_cronus")
        rainy = [s["number"] for s in pkg["scenes"]
                 if _scene_is_rainy(s)]
        self.assertEqual(rainy, [])

    def test_trait_block_weather_drives_the_renderer_flag(self):
        # The renderer reads the trait block's WEATHER field; the
        # fixture's shed (WEATHER "Mưa rào") renders rainy, the
        # garden (WEATHER "Nắng nhẹ") renders dry.
        from ai_clip_studio.product_renderer import (
            build_scene_ex_with_package)
        pkg = _fixture_package()
        blocks = {b.get("location_id"): b for b in
                  pkg["trait_blocks"]["locations"]}
        for loc_id, want_rainy in (("LOC_GARDEN", False),
                                   ("LOC_SHED", True)):
            block = blocks[loc_id]
            *_, rainy, _, _, _ = build_scene_ex_with_package(
                block["render_traits"]["location_keyword"],
                block["render_traits"]["setting"],
                block["render_traits"]["mood"],
                block["render_traits"]["time_of_day"],
                location_data=block)
            self.assertEqual(rainy, want_rainy, loc_id)


class TestFamily10SceneLocalCostume(unittest.TestCase):
    def test_overrides_resolve_per_scene_without_leak(self):
        package = {"characters": [
            {"name": "An",
             "costume_overrides": {1: "uniform", "2": "dress"}}]}
        scene1 = {"costume_overrides": {}}
        scene2 = {}
        scene3 = {}
        self.assertEqual(
            _scene_costume_overrides(scene1, package, 1),
            {"An": "uniform"})
        self.assertEqual(
            _scene_costume_overrides(scene2, package, 2),
            {"An": "dress"})
        # Scene 3 declares nothing: no override leaks in.
        self.assertEqual(
            _scene_costume_overrides(scene3, package, 3), {})

    def test_scene_mapping_wins_over_character_mapping(self):
        package = {"characters": [
            {"name": "An", "costume_overrides": {1: "uniform"}}]}
        scene = {"costumes": {"An": "dress"}}
        self.assertEqual(
            _scene_costume_overrides(scene, package, 1),
            {"An": "dress"})

    def test_invalid_garments_never_pass_through(self):
        package = {"characters": [
            {"name": "An", "costume_overrides": {1: "ballgown"}}]}
        scene = {"costume_overrides": {"An": "tuxedo"}}
        self.assertEqual(
            _scene_costume_overrides(scene, package, 1), {})

    def test_map_character_override_is_call_local(self):
        char = {"name": "An", "costume": "dress"}
        uniform = map_character(char, 0, costume_override="uniform")
        self.assertEqual(uniform.costume, "uniform")
        plain = map_character(char, 0)
        self.assertEqual(plain.costume, "dress")
        none = map_character(char, 0, costume_override="none")
        self.assertEqual(none.costume, "none")


class TestFamily11SceneLocalLighting(unittest.TestCase):
    def test_same_traits_render_identically_after_a_forge(self):
        # Determinism + isolation at the environment level: the
        # garden built after a forge build is identical to the
        # garden built before it (no shared mutable lighting).
        from ai_clip_studio.environment_v2 import build_environment
        garden = _fixture_package()["trait_blocks"]["locations"][0]
        forge = next(
            b for b in _package(
                "zeus_ep01_fall_of_cronus")["trait_blocks"][
                    "locations"]
            if b.get("location_id") == "LOC_DIVINE_FORGE")
        first = build_environment(garden, time_of_day="day",
                                  style={"mood": "warm"})
        build_environment(forge, time_of_day="day",
                          style={"mood": "warm"})
        second = build_environment(garden, time_of_day="day",
                                   style={"mood": "warm"})
        self.assertEqual(first, second)
        forge_pkg = build_environment(forge, time_of_day="day",
                                      style={"mood": "warm"})
        self.assertNotEqual(first.get("light"),
                            forge_pkg.get("light"))


class TestFamily12MultiShotNarration(unittest.TestCase):
    def test_ep1_long_lines_span_shots_exactly_once(self):
        # Lines 8 and 9 each run across 4 shots (Test G): one
        # narration interval per line in the frozen schedule, one
        # start (the FIRST segment's), phrase windows tiling.
        from ai_clip_studio.product_flow import _assign_line_starts
        from ai_clip_studio.subtitles import phrase_windows
        pkg = _package("hitler_ep01_munich_1914")
        entries = [{"line_index": i + 1, "kind": "narration",
                    "duration": d, "wav": f"/tmp/l{i + 1}.wav"}
                   for i, d in enumerate(
                       [9.79, 9.12, 9.55, 3.0, 3.0, 3.0, 3.0, 10.68,
                        10.63])]
        shots = plan_shots(pkg, entries)
        _assign_line_starts(shots, entries)
        starts = {e["line_index"]: e["start"] for e in entries}
        self.assertEqual(len(starts), 9)
        line8_shots = [s for s in shots
                       if s.get("line_index") == 8]
        line9_shots = [s for s in shots
                       if s.get("line_index") == 9]
        self.assertGreaterEqual(len(line8_shots), 2)
        self.assertGreaterEqual(len(line9_shots), 2)
        events, _, _ = _compile(pkg)
        unified = build_unified_timeline(shots, entries, events)
        self.assertTrue(unified.narration_complete(
            [f"line:{e['line_index']}" for e in entries]))
        narration = unified.track("narration")
        self.assertEqual(len(narration), 9)
        for line_index in (8, 9):
            entry = entries[line_index - 1]
            windows = phrase_windows(
                entry["start"], entry["end"],
                ["cụm một", "cụm hai", "cụm ba", "cụm bốn"])
            self.assertEqual(len(windows), 4)
            self.assertAlmostEqual(windows[0]["start"],
                                   entry["start"], delta=0.005)
            self.assertAlmostEqual(windows[-1]["end"],
                                   entry["end"], delta=0.005)
            for a, b in zip(windows, windows[1:]):
                self.assertAlmostEqual(a["end"], b["start"],
                                       delta=0.005)


class TestFamily13MultiCharacterProp(unittest.TestCase):
    def test_prop_drawn_once_at_the_current_holder(self):
        # PSM level: the letter's transform follows the holder's
        # hand through the transfer (giver -> transit -> receiver),
        # never duplicated, never floating at a stale position.
        from ai_clip_studio.prop_system import PropStateMachine
        pkg = _fixture_package()
        _, events, _ = _plan_with_spans(pkg, 5)
        scene2 = [e for e in events if e.get("scene_number") == 2]
        joints = {
            "CHAR_BOY": {"hand_l": (300.0, 400.0),
                         "hand_r": (340.0, 400.0)},
            "CHAR_GARDENER": {"hand_l": (900.0, 400.0),
                              "hand_r": (940.0, 400.0)},
        }
        psm = PropStateMachine(pkg["props"], scene2)
        handover = next(e for e in scene2
                        if e["action_type"] == "HAND_OVER")
        receive = next(e for e in scene2
                       if e["action_type"] == "RECEIVE_PROP")
        before = psm.transform_at(
            "prop_letter", handover["start_time"] - 0.05, joints)
        after = psm.transform_at(
            "prop_letter", receive["end_time"] + 0.05, joints)
        # Before: at the boy's hands; after: at the gardener's.
        self.assertLess(before[0], 500.0)
        self.assertGreater(after[0], 700.0)
        mid = (handover["start_time"] + receive["end_time"]) / 2
        transit = psm.transform_at("prop_letter", mid, joints)
        self.assertGreater(transit[0], before[0])
        self.assertLess(transit[0], after[0])


class TestFamily14UnknownMandatoryProps(unittest.TestCase):
    def test_truly_unknown_kind_fails_preflight(self):
        pkg = _fixture_package()
        pkg["props"] = [dict(p) for p in pkg["props"]]
        pkg["props"].append({"id": "prop_scope",
                             "name": "kính viễn vọng",
                             "kind": "telescope"})
        checks = semantic_preflight_checks(pkg)
        by_name = {c.name: c for c in checks}
        self.assertFalse(by_name["prop_kinds"].passed)
        self.assertIn("prop_scope",
                      by_name["prop_kinds"].detail)

    def test_generic_kind_prop_fails_preflight(self):
        # "generic" is the unclassified fallback: a script prop
        # that resolved to it has no renderable identity.
        pkg = _fixture_package()
        pkg["props"] = [dict(p) for p in pkg["props"]]
        pkg["props"].append({"id": "prop_gem", "name": "viên ngọc",
                             "kind": "generic"})
        checks = semantic_preflight_checks(pkg)
        by_name = {c.name: c for c in checks}
        self.assertFalse(by_name["prop_kinds"].passed)
        self.assertIn("prop_gem", by_name["prop_kinds"].detail)

    def test_umbrella_kind_passes_preflight(self):
        # Boundary, pinned honestly: umbrella has a legacy
        # renderer shape, so preflight passes it even though no
        # semantic geometry builder exists for it yet.
        pkg = _fixture_package()
        pkg["props"] = [dict(p) for p in pkg["props"]]
        pkg["props"].append({"id": "prop_umbrella", "name": "chiếc ô",
                             "kind": "umbrella"})
        checks = semantic_preflight_checks(pkg)
        by_name = {c.name: c for c in checks}
        self.assertTrue(by_name["prop_kinds"].passed,
                        by_name["prop_kinds"].detail)

    def test_unknown_kinds_raise_at_geometry_build(self):
        from ai_clip_studio.prop_system import UnsupportedPropError
        for kind in ("umbrella", "generic"):
            with self.subTest(kind=kind):
                with self.assertRaises(UnsupportedPropError):
                    geometry_for_prop(
                        {"kind": kind, "length_px": 200.0,
                         "size_px": 170.0})


class TestFamily15ConflictingDirectives(unittest.TestCase):
    def _contradictory_events(self):
        base = {"actor_id": "CHAR_A", "prop_id": "prop_wallet",
                "shot_id": "SC01_SH01", "scene_number": 1,
                "required_pose": {"params": {"hand": "r"}}}
        return [
            dict(base, action_id="A1", action_type="TAKE_OUT",
                 semantic_action_type="TAKE_FROM_POCKET",
                 start_time=0.0, end_time=1.0),
            dict(base, action_id="A2", action_type="KNEEL_PICK",
                 semantic_action_type="BEND_PICK",
                 start_time=1.0, end_time=2.0),
        ]

    def test_pocket_take_then_ground_pickup_raises(self):
        props = [{"id": "prop_wallet", "kind": "wallet"}]
        with self.assertRaises(ForbiddenPropTransition):
            SemanticPropTracker(props, self._contradictory_events())

    def test_drop_between_makes_it_legal(self):
        props = [{"id": "prop_wallet", "kind": "wallet"}]
        events = self._contradictory_events()
        events.insert(1, dict(
            events[0], action_id="A15", action_type="RELEASE",
            semantic_action_type="RELEASE_PROP",
            start_time=1.0, end_time=1.5))
        events[2] = dict(events[2], start_time=1.5, end_time=2.5)
        tracker = SemanticPropTracker(props, events)
        self.assertEqual(
            tracker.location_at("prop_wallet", 2.5), "HELD_RIGHT")

    def test_contradiction_fails_preflight_prop_states(self):
        # Inject the contradictory sentence into the fixture's
        # scene-1 shot text (the V1 path the compiler reads), so
        # the package, graph and preflight all see the real shape.
        pkg = _fixture_package()
        v1_scene = pkg["scenes"][0]["v1_scene"]
        shot = next(s for s in v1_scene["shots"]
                    if s.get("id") == "SC01_SH02")
        fields = shot.setdefault("fields", {})
        actions = fields.get("ACTION") or []
        if isinstance(actions, str):
            actions = [actions]
        fields["ACTION"] = list(actions) + [
            "Bà Tư cúi xuống nhặt chìa khóa dưới đất."]
        checks = semantic_preflight_checks(pkg)
        by_name = {c.name: c for c in checks}
        self.assertIn("prop_states", by_name)
        self.assertFalse(by_name["prop_states"].passed,
                         by_name["prop_states"].detail)

    def test_fixture_drop_and_pickup_passes_preflight(self):
        checks = semantic_preflight_checks(_fixture_package())
        by_name = {c.name: c for c in checks}
        self.assertTrue(by_name["prop_states"].passed,
                        by_name["prop_states"].detail)


class TestFamily16CrossProjectIsolation(unittest.TestCase):
    def test_compile_order_does_not_change_results(self):
        def _signature(pkg):
            events, unsupported, sem = _compile(pkg)
            return ([(e["action_id"], e["action_type"],
                      e.get("semantic_action_type"))
                     for e in events],
                    len(unsupported), len(sem))

        first = _signature(_fixture_package())
        _signature(_package("hitler_ep01_munich_1914"))
        _signature(_package("zeus_ep01_fall_of_cronus"))
        second = _signature(_fixture_package())
        self.assertEqual(first, second)

    def test_packages_do_not_share_mutable_state(self):
        a = _fixture_package()
        b = _fixture_package()
        a["scenes"][0]["action_cues"].append("injected_cue")
        self.assertNotIn("injected_cue",
                         b["scenes"][0]["action_cues"])
        self.assertEqual(a["v1_snapshot_hash"],
                         b["v1_snapshot_hash"])
        ep1 = _package("hitler_ep01_munich_1914")
        self.assertNotEqual(a["v1_snapshot_hash"],
                            ep1["v1_snapshot_hash"])

    def test_cue_records_carry_their_own_script_hash(self):
        for pkg in (_fixture_package(),
                    _package("hitler_ep01_munich_1914")):
            for scene in pkg["scenes"]:
                for record in scene.get("cue_records") or []:
                    if isinstance(record, dict):
                        self.assertEqual(
                            record.get("source_script_hash"),
                            pkg["v1_snapshot_hash"])


class TestETestUnseenScriptEndToEnd(unittest.TestCase):
    """TEST E: the unseen fixture through the whole front half of
    the pipeline -- parse, adapt, preflight, compile, scene
    graph, plan, render -- with story-correct results at every
    stage. The back half (TTS + mix + mux + MP4 verification)
    runs on the real renders; the fixture's audio path is
    exercised by the job-level tests with stub TTS."""

    @classmethod
    def setUpClass(cls):
        cls.pkg = _fixture_package()
        cls.checks = semantic_preflight_checks(cls.pkg)
        cls.events, cls.unsupported, cls.sem = _compile(cls.pkg)
        cls.graph = build_scene_graph(
            cls.pkg, cls.events, semantic_actions=cls.sem,
            unsupported=cls.unsupported)
        cls.shots, cls.timed, _ = _plan_with_spans(cls.pkg, 5)

    def test_preflight_passes_all_five_checks(self):
        # Five checks since the integration sprint (section 6,
        # 2026-11-13): actor_resolution joins the original four.
        # The fixture resolves every classified actor.
        by_name = {c.name: c for c in self.checks}
        self.assertEqual(
            set(by_name),
            {"semantic_conflicts", "scene_graph", "prop_states",
             "prop_kinds", "actor_resolution"})
        for check in self.checks:
            self.assertTrue(check.passed, check.detail)

    def test_compile_counts(self):
        self.assertEqual(len(self.events), 11)
        self.assertEqual(len(self.unsupported), 1)
        self.assertIn("đọc thư",
                      self.unsupported[0]["directive_text"])

    def test_scene_graph_validates(self):
        validate_or_raise(self.graph)
        self.assertEqual(len(self.graph["scenes"]), 2)
        self.assertEqual(len(self.graph["shots"]), 5)
        self.assertEqual(len(self.graph["characters"]), 2)
        self.assertEqual(len(self.graph["props"]), 2)
        key_take = self.graph["events"]["SC01_SH02_ACT01"]
        self.assertEqual(key_take["semantic_type"],
                         "TAKE_FROM_POCKET")
        self.assertEqual(key_take["verb"], "TAKE_OUT")
        self.assertEqual(key_take["prop_id"], "prop_key")

    def test_plan_consumes_every_directive_once(self):
        directives = {s.get("directive_shot_id") for s in self.shots
                      if s.get("directive_shot_id")}
        self.assertEqual(directives, {
            "SC01_SH01", "SC01_SH02", "SC01_SH03",
            "SC02_SH01", "SC02_SH02"})
        # The authority chain is the graph's event assignment, not
        # scene-level cues: the pocket-take shot's events contain
        # no ground pickup (the Hitler contamination), while the
        # pickup shot's events contain the kneel pick.
        shot_nodes = self.graph["shots"]
        take_verbs = [self.graph["events"][eid]["verb"]
                      for eid in shot_nodes["SC01_SH02"]["event_ids"]]
        self.assertNotIn("KNEEL_PICK", take_verbs)
        pickup_verbs = [self.graph["events"][eid]["verb"]
                        for eid in shot_nodes["SC01_SH03"]["event_ids"]]
        self.assertIn("KNEEL_PICK", pickup_verbs)

    def test_no_rain_cue_in_the_dry_scene(self):
        dry = self.pkg["scenes"][0]
        self.assertNotIn("rain", dry.get("action_cues") or [])
        self.assertFalse(_scene_is_rainy(dry))

    def test_first_person_throughout(self):
        first_person = self.pkg["v1_first_person"]
        self.assertTrue(first_person["enabled"])
        self.assertEqual(
            first_person["storytelling_mode"],
            "FIRST_PERSON_ROLEPLAY")
        self.assertEqual(first_person["primary_character"],
                         "CHAR_GARDENER")
        self.assertEqual(first_person["external_narrator"], "NONE")


if __name__ == "__main__":
    unittest.main()
