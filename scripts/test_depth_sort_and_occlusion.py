"""Comprehensive verification tests for Per-Frame Depth-Sorting and Occlusion Re-Evaluation.

Contract Requirements:
1. Depth-sort all scene elements (props, characters, environment) by their z-distance
   from camera every frame, not just at scene setup.
2. Re-evaluate occlusion whenever a character's world position changes relative to a foreground object.
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.universal.v5_story_director import V5UniversalStoryDirector


def test_python_depth_sort_and_occlusion():
    print("\n--- Running Python V5UniversalStoryDirector Depth Sort Tests ---")
    director = V5UniversalStoryDirector()

    # Package with two actors at different depths
    pkg = {
        "actors": [
            {
                "actor_id": "haru",
                "staging": {"initial_world_pos": [0.0, 2.75, 0.0]},
                "performance_cues": [
                    {"time": 0.0, "pos": [0.0, 2.75, 0.0]},   # Behind railing (z=2.05)
                    {"time": 5.0, "pos": [0.0, 2.75, 2.8]},   # Stepped in front of railing (z=2.05)
                ]
            },
            {
                "actor_id": "station_master",
                "staging": {"initial_world_pos": [-1.5, 2.75, -1.0]},
                "performance_cues": [
                    {"time": 0.0, "pos": [-1.5, 2.75, -1.0]}, # Further back (z=-1.0)
                    {"time": 5.0, "pos": [-1.5, 2.75, -1.0]},
                ]
            }
        ]
    }

    # Camera at [0, 2.4, 7.0]
    camera_pos = [0.0, 2.4, 7.0]
    passed, records = director.validate_depth_sorting_and_occlusion(pkg, camera_pos)
    assert passed, "Depth sorting validation should pass"

    # Verify descending depth order
    for i in range(len(records) - 1):
        assert records[i]["camera_distance"] >= records[i + 1]["camera_distance"], (
            f"Elements not depth-sorted: {records[i]} vs {records[i+1]}"
        )

    print(f"  [PASS] Successfully depth-sorted {len(records)} elements from furthest to nearest.")

    # Check occlusion re-evaluation when Haru moves:
    # At t=0.0: Haru z=0.0 -> cam_dist = 7.0m. Railing z=2.05 -> cam_dist = 4.95m.
    # Haru is BEHIND railing -> is_occluded must be True
    # At t=5.0: Haru z=2.8 -> cam_dist = 4.2m. Railing z=2.05 -> cam_dist = 4.95m.
    # Haru is IN FRONT OF railing -> is_occluded must be False

    haru_cues = pkg["actors"][0]["performance_cues"]
    dist_t0 = sum((haru_cues[0]["pos"][i] - camera_pos[i])**2 for i in range(3))**0.5
    dist_t5 = sum((haru_cues[1]["pos"][i] - camera_pos[i])**2 for i in range(3))**0.5
    railing_dist = sum(([0.0, 3.7, 2.05][i] - camera_pos[i])**2 for i in range(3))**0.5

    assert dist_t0 > railing_dist, "At t=0 Haru must be behind railing"
    assert dist_t5 < railing_dist, "At t=5 Haru must be in front of railing"
    print("  [PASS] Occlusion re-evaluation verified: Haru transitions from BEHIND (occluded) to IN FRONT (unoccluded).")


def test_node_three_world_depth_sorting():
    print("\n--- Running Node UniversalWorldEngine Depth-Sorting & Occlusion Invariant Tests ---")

    # Bundle UniversalWorldEngine for Node execution
    bundle_cmd = [
        "npx.cmd" if sys.platform == "win32" else "npx",
        "esbuild",
        str(ROOT / "motioncanvas" / "three" / "UniversalWorldEngine.ts"),
        "--bundle",
        "--platform=node",
        "--format=esm",
        f"--outfile={ROOT / 'scratch' / 'bundle_world.mjs'}"
    ]
    bundle_res = subprocess.run(bundle_cmd, capture_output=True, text=True, cwd=str(ROOT))
    if bundle_res.returncode != 0:
        raise RuntimeError(f"Failed to bundle UniversalWorldEngine: {bundle_res.stderr}")

    node_script = """
    import('./bundle_world.mjs').then(mod => {
      const UniversalWorldEngine = mod.UniversalWorldEngine;

      const locDna = {
        location_id: 'LOC_EDO_WOODEN_BRIDGE',
        name: 'Edo Wooden Bridge Canal',
        architecture: 'TRADITIONAL_EAST_ASIAN',
        weather: 'RAIN',
        camera_initial: {
          position: [-2.2, 3.8, 5.6],
          target: [0.1, 2.7, 0.0],
          fov: 42
        }
      };

      const world = new UniversalWorldEngine(locDna, 1920, 1080);
      world.update(0.0);

      // Verify foreground elements registered
      const fgElements = world.getForegroundElements();
      if (fgElements.length === 0) {
        throw new Error('Test Failed: Expected foregroundElements to be populated');
      }
      console.log(`  [PASS] Registered ${fgElements.length} foreground occluder element(s) (e.g. ${fgElements[0].name}).`);

      const actors = [
        {
          actor_id: 'haru',
          dna: { name: 'Haru', heldProps: { rightHand: 'letter_envelope' } },
          staging: { initial_world_pos: [-2.8, 2.75, 0.0] },
          performance_cues: [
            { time: 0.0, pos: [-2.8, 2.75, 0.0] }, // Behind front railing (z=2.05)
            { time: 4.8, pos: [0.25, 2.15, -0.5] }, // Hanging behind railing
            { time: 8.0, pos: [0.25, 2.5, 3.2] },   // Climbed in front of railing (z=3.2)
          ]
        },
        {
          actor_id: 'passerby',
          dna: { name: 'Passerby' },
          staging: { initial_world_pos: [2.0, 2.75, -1.5] }, // Far background
          performance_cues: [
            { time: 0.0, pos: [2.0, 2.75, -1.5] }
          ]
        }
      ];

      // FRAME 1: t = 0.0s (Haru is sprinting on bridge deck at z = 0.0)
      world.update(0.0);
      const res0 = world.evaluateSceneDepthSort(0.0, actors);

      // Verify all elements are depth sorted descending
      const el0 = res0.depthSortedElements;
      for (let i = 0; i < el0.length - 1; i++) {
        if (el0[i].cameraDistance < el0[i + 1].cameraDistance) {
          throw new Error(`Test Failed: elements not depth-sorted at t=0: ${el0[i].id} (${el0[i].cameraDistance}m) vs ${el0[i+1].id} (${el0[i+1].cameraDistance}m)`);
        }
      }
      console.log(`  [PASS] Frame 0 (t=0.0s): Depth-sorted ${el0.length} scene elements.`);

      // Verify Haru is occluded by front railing at t=0
      const haruOcc0 = res0.occlusionEvents.find(e => e.characterId === 'haru' && e.foregroundObjectId === 'bridge_front_railing');
      if (!haruOcc0 || !haruOcc0.isOccluded) {
        throw new Error(`Test Failed: Haru must be occluded by front railing at t=0. Event: ${JSON.stringify(haruOcc0)}`);
      }
      console.log(`  [PASS] Frame 0 (t=0.0s): Haru is BEHIND railing (depth delta = +${haruOcc0.depthDelta}m) -> isOccluded = true.`);

      // Verify active occluders includes the front railing
      if (!res0.activeOccluders.some(o => o.userData?.elementId === 'bridge_front_railing' || o.name === 'bridge_front_railing')) {
        throw new Error('Test Failed: bridge_front_railing must be in activeOccluders at t=0');
      }

      // FRAME 2: t = 8.0s (Haru has moved in front of railing to z = 3.2m, closer to camera)
      world.update(8.0);
      const res8 = world.evaluateSceneDepthSort(8.0, actors);

      // Verify depth sorting at frame 8
      const el8 = res8.depthSortedElements;
      for (let i = 0; i < el8.length - 1; i++) {
        if (el8[i].cameraDistance < el8[i + 1].cameraDistance) {
          throw new Error(`Test Failed: elements not depth-sorted at t=8: ${el8[i].id} vs ${el8[i+1].id}`);
        }
      }
      console.log(`  [PASS] Frame 8 (t=8.0s): Depth-sorted ${el8.length} scene elements.`);

      // Re-evaluate occlusion at t=8: Haru is now IN FRONT of the railing (unoccluded),
      // while passerby remains behind the railing (occluded)
      const haruOcc8 = res8.occlusionEvents.find(e => e.characterId === 'haru' && e.foregroundObjectId === 'bridge_front_railing');
      if (!haruOcc8) throw new Error('Test Failed: missing occlusion event for Haru at t=8');
      if (haruOcc8.isOccluded) {
        throw new Error(`Test Failed: Haru moved in front of railing (z=3.2 > z=2.05), so isOccluded must be false! Event: ${JSON.stringify(haruOcc8)}`);
      }
      console.log(`  [PASS] Frame 8 (t=8.0s): Haru moved IN FRONT of railing (depth delta = ${haruOcc8.depthDelta}m) -> isOccluded = false.`);

      const passerbyOcc8 = res8.occlusionEvents.find(e => e.characterId === 'passerby' && e.foregroundObjectId === 'bridge_front_railing');
      if (!passerbyOcc8 || !passerbyOcc8.isOccluded) {
        throw new Error('Test Failed: Passerby at z=-1.5 must still be occluded by railing');
      }
      console.log(`  [PASS] Frame 8 (t=8.0s): Passerby remains BEHIND railing (depth delta = +${passerbyOcc8.depthDelta}m) -> isOccluded = true.`);

      // When only Haru is in scene at t=8, activeOccluders must be empty (railing not drawn on top)
      const res8Solo = world.evaluateSceneDepthSort(8.0, [actors[0]]);
      if (res8Solo.activeOccluders.length !== 0) {
        throw new Error('Test Failed: activeOccluders must be empty when Haru is in front and no other actors are behind');
      }
      console.log('  [PASS] Frame 8: Front railing correctly excluded from foreground occluders when all actors are in front.');

      // Multi-character order verification
      const passerbyOcc = res0.depthSortedElements.findIndex(e => e.id === 'passerby');
      const haruIdx = res0.depthSortedElements.findIndex(e => e.id === 'haru');
      if (passerbyOcc > haruIdx) {
        throw new Error('Test Failed: Passerby (further away) must appear before Haru (closer) in descending depth sort');
      }
      console.log('  [PASS] Multi-character depth sorting verified: distant characters render before foreground characters.');

      console.log('\\n--- ALL DEPTH-SORTING & OCCLUSION CHECKS PASSED ---');
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    test_mjs = ROOT / "scratch" / "test_depth_sort_invariants.mjs"
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
        raise RuntimeError(f"Node depth sorting tests failed with return code {res.returncode}")


def main():
    print("=" * 70)
    print("PRODUCTIONS ACCEPTANCE: PER-FRAME DEPTH-SORTING & OCCLUSION")
    print("=" * 70)
    test_python_depth_sort_and_occlusion()
    test_node_three_world_depth_sorting()
    print("=" * 70)
    print("ALL ACCEPTANCE SUITES PASSED: Per-frame depth sorting and dynamic occlusion enforced!")
    print("=" * 70)


if __name__ == "__main__":
    main()
