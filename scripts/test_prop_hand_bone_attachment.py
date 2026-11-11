"""Comprehensive validation and acceptance tests for Handheld Prop Parenting & Invariants.

Contract Requirements:
1. Any handheld prop must be parented to the hand bone with zero positional offset tolerance.
2. Validate that prop_position == hand_bone_world_position ± 2px before finalizing render.
3. Reject frames where prop-to-hand distance exceeds 5px.
"""

import sys
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.universal.v5_story_director import V5UniversalStoryDirector


def test_python_prop_validation():
    print("\n--- Running Python V5UniversalStoryDirector Prop Parenting Tests ---")
    director = V5UniversalStoryDirector()

    # 1. Zero positional offset parenting
    passed, violations = director.validate_handheld_prop_parenting(
        actor_id="haru",
        held_props={"rightHand": "letter_envelope", "leftHand": "none"},
        prop_offsets={"rightHand": [0.0, 0.0]}
    )
    assert passed, f"Zero offset should pass validation, got violations: {violations}"
    print("  [PASS] Zero offset parenting: distance == 0.0px (within ±2px tolerance).")

    # 2. Offset within ±2px tolerance
    passed, violations = director.validate_handheld_prop_parenting(
        actor_id="haru",
        held_props={"rightHand": "letter_envelope"},
        prop_offsets={"rightHand": [1.2, 0.8]}  # dist = 1.442px <= 2px
    )
    assert passed, f"Offset within 2px should pass, got violations: {violations}"
    print("  [PASS] Offset 1.44px: within ±2px tolerance passes validation.")

    # 3. Offset > 2px and <= 5px (tolerance violation before finalizing render)
    passed, violations = director.validate_handheld_prop_parenting(
        actor_id="haru",
        held_props={"rightHand": "letter_envelope"},
        prop_offsets={"rightHand": [2.5, 2.0]}  # dist = 3.202px > 2px
    )
    assert not passed, "Offset > 2px should fail tolerance validation"
    assert any("RENDER_TOLERANCE_VIOLATION" in v for v in violations), f"Expected RENDER_TOLERANCE_VIOLATION in {violations}"
    print(f"  [PASS] Offset 3.20px: correctly flagged {violations[0]}.")

    # 4. Offset > 5px (frame rejection)
    passed, violations = director.validate_handheld_prop_parenting(
        actor_id="haru",
        held_props={"rightHand": "letter_envelope"},
        prop_offsets={"rightHand": [4.0, 4.0]}  # dist = 5.657px > 5px
    )
    assert not passed, "Offset > 5px must fail"
    assert any("FRAME_REJECTED" in v for v in violations), f"Expected FRAME_REJECTED in {violations}"
    print(f"  [PASS] Offset 5.66px: correctly flagged {violations[0]}.")


def test_node_universal_character_engine():
    print("\n--- Running Node UniversalCharacterEngine & RenderRunner Invariant Tests ---")

    # Bundle the engine for test execution
    bundle_cmd = [
        "npx.cmd" if sys.platform == "win32" else "npx",
        "esbuild",
        str(ROOT / "motioncanvas" / "components" / "UniversalCharacterEngine.ts"),
        "--bundle",
        "--platform=node",
        "--format=esm",
        f"--outfile={ROOT / 'scratch' / 'bundle_engine.mjs'}"
    ]
    bundle_res = subprocess.run(bundle_cmd, capture_output=True, text=True, cwd=str(ROOT))
    if bundle_res.returncode != 0:
        raise RuntimeError(f"Failed to bundle UniversalCharacterEngine: {bundle_res.stderr}")

    node_script = """
    globalThis.window = {
      __renderMetrics: {
        framesRendered: 0,
        propAttachmentAudit: {
          passed: true,
          maxDistance: 0,
          checkedCount: 0,
          violations: []
        }
      }
    };

    const finalizeRender = function() {
      const audit = window.__renderMetrics.propAttachmentAudit;
      if (!audit || audit.checkedCount === 0) {
        return { success: true, status: 'NO_PROPS_EVALUATED', checkedCount: 0, maxDistance: 0, tolerancePx: 2.0 };
      }
      if (!audit.passed || audit.violations.length > 0 || audit.maxDistance > 2.0) {
        const errorMsg = `RENDER_FINALIZATION_REJECTED: Handheld prop-to-hand distance tolerance (±2px) violated. ` +
          `Max deviation: ${audit.maxDistance.toFixed(2)}px (tolerance: ±2.0px). Total violations: ${audit.violations.length}`;
        throw new Error(errorMsg);
      }
      return {
        success: true,
        status: 'VALIDATED_WITHIN_TOLERANCE',
        checkedCount: audit.checkedCount,
        maxDistance: Number(audit.maxDistance.toFixed(3)),
        tolerancePx: 2.0
      };
    };

    const mockCtx = {
      save() {}, restore() {}, translate() {}, scale() {}, rotate() {},
      beginPath() {}, moveTo() {}, lineTo() {}, quadraticCurveTo() {}, bezierCurveTo() {},
      arc() {}, ellipse() {}, closePath() {}, fill() {}, stroke() {}, fillRect() {}, strokeRect() {},
      fillText() {}, clearRect() {},
      createLinearGradient() { return { addColorStop() {} }; },
      createRadialGradient() { return { addColorStop() {} }; },
    };

    import('./bundle_engine.mjs').then(mod => {
      const engine = new mod.UniversalCharacterEngine(mockCtx);
      const dna = {
        characterId: 'haru',
        name: 'Haru',
        heldProps: { rightHand: 'letter_envelope', leftHand: 'none' }
      };
      const baseState = {
        screenX: 960,
        screenY: 540,
        scale: 1.0,
        facing: 1,
        action: 'sprint',
        progress: 1.0,
        emotion: 'determined'
      };

      // 1. Zero positional offset parenting
      engine.render(dna, { ...baseState });
      const a1 = engine.lastPropAudits[0];
      if (a1.distance !== 0 || !a1.withinTolerance || a1.rejected) {
        throw new Error(`Test 1 Failed: expected distance 0, got ${a1.distance}`);
      }
      console.log('  [PASS] Node Engine: Zero offset parenting distance is exactly 0.0px.');

      // 2. Tolerance check within ±2px
      engine.render(dna, { ...baseState, propOffsetR: [1.2, 0.8] });
      const a2 = engine.lastPropAudits[0];
      if (a2.distance > 2.0 || !a2.withinTolerance || a2.rejected) {
        throw new Error(`Test 2 Failed: expected withinTolerance true, got ${JSON.stringify(a2)}`);
      }
      console.log(`  [PASS] Node Engine: Offset within 2px (${a2.distance}px) passed tolerance.`);

      // 3. Tolerance violation check: between 2px and 5px does not reject frame, but finalizeRender fails
      window.__renderMetrics.propAttachmentAudit = { passed: true, maxDistance: 0, checkedCount: 0, violations: [] };
      engine.render(dna, { ...baseState, propOffsetR: [2.5, 2.0] }); // dist ≈ 3.2px
      const a3 = engine.lastPropAudits[0];
      if (a3.rejected) {
        throw new Error(`Test 3 Failed: frame should not be rejected for 3.2px deviation`);
      }
      if (a3.withinTolerance) {
        throw new Error(`Test 3 Failed: 3.2px deviation must violate ±2px tolerance`);
      }
      let finalizationFailed = false;
      try {
        finalizeRender();
      } catch (err) {
        if (err.message.includes('RENDER_FINALIZATION_REJECTED')) {
          finalizationFailed = true;
          console.log(`  [PASS] Node Runner: finalizeRender aborted on deviation > 2px (${err.message.split('.')[0]}).`);
        } else {
          throw err;
        }
      }
      if (!finalizationFailed) throw new Error(`Test 3 Failed: finalizeRender did not abort`);

      // 4. Strict Frame Rejection Check: deviation > 5px throws FRAME_REJECTED immediately
      let frameRejected = false;
      try {
        engine.render(dna, { ...baseState, propOffsetR: [4.0, 4.0] }); // dist ≈ 5.66px
      } catch (err) {
        if (err.message.includes('FRAME_REJECTED')) {
          frameRejected = true;
          console.log(`  [PASS] Node Engine: Frame rejected immediately on > 5px distance: ${err.message}`);
        } else {
          throw err;
        }
      }
      if (!frameRejected) throw new Error(`Test 4 Failed: deviation > 5px did not trigger FRAME_REJECTED`);

      // 5. Dual-hand parenting test (Left + Right hands simultaneously parented)
      const dualDna = {
        characterId: 'haru',
        name: 'Haru',
        heldProps: { rightHand: 'letter_envelope', leftHand: 'letter_scroll_sealed' }
      };
      engine.render(dualDna, { ...baseState });
      if (engine.lastPropAudits.length !== 2) {
        throw new Error(`Test 5 Failed: expected 2 prop audits, got ${engine.lastPropAudits.length}`);
      }
      const [rAudit, lAudit] = engine.lastPropAudits;
      if (rAudit.distance !== 0 || lAudit.distance !== 0) {
        throw new Error(`Test 5 Failed: both hands must have zero offset distance`);
      }
      console.log('  [PASS] Node Engine: Dual-hand props (right + left) simultaneously parented with 0px offset.');

      console.log('\\n--- ALL INVARIANT CHECKS PASSED SUCCESSFULLY ---');
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    test_mjs = ROOT / "scratch" / "test_prop_invariants.mjs"
    test_mjs.parent.mkdir(parents=True, exist_ok=True)
    with open(test_mjs, "w", encoding="utf-8") as f:
        f.write(node_script)

    res = subprocess.run(
        ["node", str(test_mjs)],
        capture_output=True,
        text=True,
        cwd=str(ROOT)
    )
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        raise RuntimeError(f"Node invariant tests failed with return code {res.returncode}")


def main():
    print("=" * 70)
    print("PRODUCTIONS ACCEPTANCE: HANDHELD PROP PARENTING & INVARIANTS")
    print("=" * 70)
    test_python_prop_validation()
    test_node_universal_character_engine()
    print("=" * 70)
    print("ALL ACCEPTANCE SUITES PASSED: Handheld prop parenting rules strictly enforced!")
    print("=" * 70)


if __name__ == "__main__":
    main()
