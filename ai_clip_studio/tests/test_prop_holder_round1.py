"""Round 1 prop-holder tests: an adapter-declared OWNER (ID form) must
seed a declared SIGNATURE_PROP into the owner's hand when no compiled
event ever stages it. Before this fix the fallback looked the owner ID
up in name_to_id, always got None, and the trident / invisibility
helmet were never drawn in any Zeus shot (0 draws in the whole job
telemetry), while name-form holders seeded fine.

The seed is deliberately narrow: history (event-driven carry-over) and
name-form tracker holders behave exactly as before; the ID-form owner
path seeds ONLY a declared signature prop with no compiled events, so
a pocket prop (the Ep1 wallet) never appears in hand before its
take-out shot. Ownerless props (chain, boulder) are unchanged: no
owner, no events, no ON_GROUND evidence -- the renderer must not
invent their placement; they stay flagged by the coverage report.
"""
import tempfile
import unittest
from pathlib import Path

from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.product_renderer import (
    _build_shot_prop_machine,
    _render_shot,
    plan_shots,
)
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

_JOINTS = {"CHAR_POSEIDON": {"hand_r": (600.0, 400.0),
                             "hand_l": (400.0, 400.0),
                             "hip": (500.0, 600.0), "facing": 1}}


def _machine(holder_value, signature, events=(), visible=("Poseidon",)):
    package = {
        "characters": [{"id": "CHAR_POSEIDON", "name": "Poseidon",
                        "signature_prop": signature}],
        "props": [{"id": "prop_trident", "name": "Trident",
                   "kind": "trident", "owner": "CHAR_POSEIDON"}],
        "compiled_actions": {"events": list(events)},
    }
    shot = {"props": ["prop_trident"],
            "prop_holders": {"prop_trident": holder_value}, "index": 0}
    shot_events = [{"action_id": "X1", "action_type": "LOOK_AT",
                    "actor_id": "CHAR_POSEIDON", "start_time": 10.0,
                    "end_time": 11.0}]
    machine, _, _, _, _ = _build_shot_prop_machine(
        package, shot, shot_events,
        rests={"prop_trident": (500.0, 500.0)},
        rest_kinds={"prop_trident": "pocket"},
        pocket_anchors={"prop_trident": None},
        id_to_name={"CHAR_POSEIDON": "Poseidon"},
        name_to_id={"Poseidon": "CHAR_POSEIDON"},
        visible_names=list(visible), t0=10.0)
    return machine


def _zeus_package_and_shots():
    text = (EXAMPLES / "zeus_ep01_fall_of_cronus.studio.md").read_text(
        encoding="utf-8")
    package = adapt_document(parse_studio_script_v1(text))
    shots = plan_shots(
        package, [{"line_index": i + 1, "duration": 3.0}
                  for i in range(40)])
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
    return package, shots


class TestOwnerSignatureSeed(unittest.TestCase):
    def test_id_owner_with_signature_seeds_hold(self):
        machine = _machine("CHAR_POSEIDON", "PROP_TRIDENT")
        self.assertIsNotNone(machine)
        x, y, _ang, state, hand = machine.transform_at(
            "prop_trident", 10.5, _JOINTS)
        self.assertEqual(state, "ATTACHED_TO_HAND")
        self.assertEqual(hand, "r")
        self.assertAlmostEqual(x, 600.0)
        self.assertAlmostEqual(y, 400.0)

    def test_id_owner_with_signature_by_prop_name_seeds_hold(self):
        machine = _machine("CHAR_POSEIDON", "Trident")
        self.assertIsNotNone(machine)
        self.assertEqual(machine.transform_at(
            "prop_trident", 10.5, _JOINTS)[3], "ATTACHED_TO_HAND")

    def test_id_owner_without_signature_never_seeds(self):
        machine = _machine("CHAR_POSEIDON", None)
        self.assertIsNotNone(machine)
        self.assertEqual(machine.transform_at(
            "prop_trident", 10.5, _JOINTS)[3], "WORLD_STATIC")

    def test_id_owner_with_other_signature_never_seeds(self):
        machine = _machine("CHAR_POSEIDON", "PROP_SWORD")
        self.assertIsNotNone(machine)
        self.assertEqual(machine.transform_at(
            "prop_trident", 10.5, _JOINTS)[3], "WORLD_STATIC")

    def test_id_owner_signature_with_any_event_never_seeds(self):
        events = ({"action_id": "E1", "action_type": "HOLD",
                   "actor_id": "CHAR_POSEIDON",
                   "prop_id": "prop_trident",
                   "start_time": 50.0, "end_time": 51.0},)
        machine = _machine("CHAR_POSEIDON", "PROP_TRIDENT", events=events)
        self.assertIsNotNone(machine)
        self.assertEqual(machine.transform_at(
            "prop_trident", 10.5, _JOINTS)[3], "WORLD_STATIC")

    def test_name_form_holder_still_seeds_as_before(self):
        machine = _machine("Poseidon", None)
        self.assertIsNotNone(machine)
        self.assertEqual(machine.transform_at(
            "prop_trident", 10.5, _JOINTS)[3], "ATTACHED_TO_HAND")

    def test_owner_not_visible_never_seeds(self):
        machine = _machine("CHAR_POSEIDON", "PROP_TRIDENT",
                           visible=("Zeus",))
        self.assertIsNotNone(machine)
        self.assertEqual(machine.transform_at(
            "prop_trident", 10.5, _JOINTS)[3], "WORLD_STATIC")


class TestZeusSignatureProps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.shots = _zeus_package_and_shots()

    def test_adapter_carries_signature_props(self):
        by_id = {c["id"]: c for c in self.package["characters"]}
        self.assertEqual(by_id["CHAR_POSEIDON"]["signature_prop"],
                         "PROP_TRIDENT")
        self.assertEqual(by_id["CHAR_HADES"]["signature_prop"],
                         "PROP_INVISIBILITY_HELMET")
        for cid, char in by_id.items():
            if cid not in ("CHAR_POSEIDON", "CHAR_HADES"):
                self.assertIsNone(char["signature_prop"], cid)

    def test_owners_and_no_events_for_signature_props(self):
        by_id = {p["id"]: p for p in self.package["props"]}
        self.assertEqual(by_id["prop_trident"]["owner"], "CHAR_POSEIDON")
        self.assertEqual(by_id["prop_invisibility_helmet"]["owner"],
                         "CHAR_HADES")
        staged = {e.get("prop_id") for e in
                  self.package["compiled_actions"]["events"]}
        # The helmet still stages owner-seeded, with no events. The
        # trident has exactly ONE event: Poseidon's genuine lift
        # ("Poseidon nâng đinh ba", recovered by the "nâng"
        # vocabulary) -- no other event may claim it.
        trident = [e for e in
                   self.package["compiled_actions"]["events"]
                   if e.get("prop_id") == "prop_trident"]
        self.assertEqual([e["action_id"] for e in trident],
                         ["SC08_SH03_ACT01"])
        self.assertEqual(trident[0]["action_type"], "PICK_UP")
        self.assertEqual(trident[0]["actor_id"], "CHAR_POSEIDON")
        self.assertNotIn("prop_invisibility_helmet", staged)

    def test_render_draws_trident_and_helmet(self):
        shot = None
        for s in self.shots:
            if s.get("scene") == 8 and s.get("shot_type") == "medium" \
                    and "Poseidon" in (s.get("visible") or []) \
                    and "Hades" in (s.get("visible") or []):
                shot = s
                break
        self.assertIsNotNone(shot, "no scene-8 shot with both owners")
        with tempfile.TemporaryDirectory() as tmp:
            report = _render_shot({"shot": shot, "package": self.package,
                                   "out_dir": tmp, "still_only": True})
        kinds = set()
        for entry in report.get("grip_telemetry") or []:
            for draw in entry.get("draws") or []:
                kinds.add(draw.get("kind"))
        self.assertIn("trident", kinds)
        self.assertIn("helmet", kinds)


if __name__ == "__main__":
    unittest.main()
