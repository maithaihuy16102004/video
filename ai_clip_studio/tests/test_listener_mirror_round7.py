"""Round-7 listener-mirroring tests.

A listener with no declared resting face and no face keyframe
mirrors the speaker's expression at half strength, so a worried
speaker does not leave the child with a flat 0.0-degree brow
while the adults' brows slant (tester R6). A declared resting
face still wins, and a neutral speaker mirrors to neutral.
"""

import json
import tempfile
import unittest
from pathlib import Path

import ai_clip_studio.product_renderer as PR
from ai_clip_studio.action_compiler import compile_actions
from ai_clip_studio.studio_script_v1 import parse_studio_script_v1
from ai_clip_studio.studio_script_v1_adapter import adapt_document

AGENT = Path(__file__).resolve().parent.parent.parent
JOB = AGENT / "jobs" / "req_ca4d2c6d1959" / "timeline.json"


def _render_still(shot_index, strip_defaults=False):
    doc = parse_studio_script_v1(
        (AGENT / "examples" / "loop_test_01_fire_stone.studio.md"
         ).read_text(encoding="utf-8"))
    pkg = adapt_document(doc)
    if strip_defaults:
        # The Loop-01 characters all declare resting faces, which
        # win over mirroring by design. Stripping the declarations
        # exposes the mirror path for the listener under test.
        for _c in pkg.get("characters") or []:
            _c.pop("default_expression", None)
    timeline = json.loads(JOB.read_text(encoding="utf-8"))
    shots = PR.plan_shots(pkg, timeline["lines"])
    shot = dict(shots[shot_index])
    shot["index"] = shot_index
    spans = {}
    for s in shots:
        did = s.get("directive_shot_id")
        if did:
            spans.setdefault(
                did, [float(s["start_sec"]),
                      float(s["start_sec"]) + float(s["duration"])])
    events, unsupported = compile_actions(
        pkg, timeline={"spans": spans})
    pkg["compiled_actions"] = {
        "events": events, "unsupported": unsupported,
        "spans_supplied": True, "compile_error": None}
    seen = {}
    orig = PR.draw_character_v4

    def spy(draw, char, expression="neutral", **kw):
        seen[char.name] = expression
        return orig(draw, char, expression=expression, **kw)

    PR.draw_character_v4 = spy
    try:
        PR._render_shot({"shot": shot, "package": pkg,
                         "out_dir": tempfile.mkdtemp(),
                         "still_only": True})
    finally:
        PR.draw_character_v4 = orig
    return shot, seen


class TestListenerMirror(unittest.TestCase):
    def test_listener_mirrors_speaker_at_half_strength(self):
        # Shot 13: Linh narrates happy; Be Nam listens with no
        # declared resting face and no keyframe.
        shot, seen = _render_still(13, strip_defaults=True)
        self.assertEqual(shot.get("speaker"), "Linh")
        self.assertEqual(shot.get("expression"), "happy")
        mirrored = seen["Bé Nam"]
        self.assertIsInstance(mirrored, dict)
        # Halfway between neutral (0.0) and happy (-0.08).
        self.assertAlmostEqual(mirrored["brow_in"], -0.04,
                               places=3)
        self.assertAlmostEqual(mirrored["mouth_curve"], 0.5,
                               places=3)

    def test_neutral_speaker_leaves_listener_neutral(self):
        # Shot 1: Linh narrates with no expression label and
        # neutral text; the listener keeps the name path.
        shot, seen = _render_still(1, strip_defaults=True)
        self.assertEqual(seen["Bé Nam"], "neutral")

    def test_declared_resting_face_wins_over_mirror(self):
        # With the script's declarations intact, Be Nam keeps
        # his resting face ("Excited, curious" -> surprised)
        # instead of mirroring the happy speaker.
        shot, seen = _render_still(13)
        self.assertEqual(seen["Bé Nam"], "surprised")


if __name__ == "__main__":
    unittest.main()
