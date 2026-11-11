"""Comprehensive validation and acceptance tests for Camera Composition & Overhead Structure Invariants.

Contract Requirements:
1. Default camera height must keep at least 60% of frame as open sky/background.
2. Characters must occupy the lower-middle third of the frame.
3. Avoid framing shots from beneath overhead structures unless the shot is explicitly tagged 'claustrophobic/reveal'.
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.universal.v5_story_director import V5UniversalStoryDirector


def test_story_director_camera_presets_composition():
    print("\n--- [1/4] Running Python Story Director Camera Composition Invariant Tests ---")
    director = V5UniversalStoryDirector()
    categories = [
        "EDO_BRIDGE",
        "RAIL_STATION",
        "CAFE",
        "HOSPITAL_ER",
        "DESERT_STATION",
        "ANTARCTIC",
        "VICTORIAN_THAMES",
        "EDO_HOUSE",
        "ROBOTICS_LAB",
        "NEOCLASSICAL"
    ]

    for cat in categories:
        test_pkg = {
            "locations": [{"category": cat, "name": f"Location {cat}", "weather": "CLEAR"}],
            "dialogue": [("Character A", "Test line")],
            "characters": [{"characterId": "char_1", "role": "LEAD", "archetype": "young_courier"}],
            "story_beats": [{"time": 0.0, "beat": "Opening scene"}],
        }

        compiled = director.compile_to_runner_package(test_pkg)
        audit = compiled.get("camera_composition_audit", {})

        assert audit.get("passed"), (
            f"Category '{cat}' failed camera composition audit: {audit.get('violations')}"
        )
        assert audit.get("average_sky_fraction", 0.0) >= 0.58, (
            f"Category '{cat}' has insufficient open sky: {audit.get('average_sky_fraction')*100:.1f}% < 60%"
        )

        bounds = audit.get("character_screen_bounds", [{}])[0]
        head_y = bounds.get("head_y", 0)
        feet_y = bounds.get("feet_y", 0)

        # Head must be >= 432px (40% from top) and feet <= 1040px
        assert head_y >= 432, f"Category '{cat}' head too high in frame: Y={head_y}px"
        assert feet_y <= 1040, f"Category '{cat}' feet clipped at bottom: Y={feet_y}px"

        print(
            f"  [PASS] {cat:17s}: Sky={audit['average_sky_fraction']*100:.1f}%, "
            f"Body in [Y={head_y:.0f}px, Y={feet_y:.0f}px] (Lower-Middle Third), Overhead cleared."
        )


def test_overhead_structure_avoidance_and_tag_exception():
    print("\n--- [2/4] Testing Overhead Structure Avoidance & 'claustrophobic/reveal' Tag Exception ---")
    director = V5UniversalStoryDirector()

    # Case A: Edo Bridge - Camera placed under bridge deck (Y=1.8m < 2.65m) WITHOUT tag -> MUST FAIL
    bridge_under_untagged = {
        "scene_world": {
            "location_id": "LOC_EDO_WOODEN_BRIDGE",
            "architecture_style": "EDO_BRIDGE",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 1.8, 0.0], "target": [0.0, 2.5, 0.0], "fov": 44},
                "camera_keyframes": [
                    {"t": 0.0, "position": [0.0, 1.8, 0.0], "target": [0.0, 2.5, 0.0]}
                ]
            }
        },
        "actors": [{"actor_id": "haru", "staging": {"initial_world_pos": [0.0, 2.65, 0.0]}}],
        "tags": []
    }
    passed_a, violations_a, audit_a = director.validate_camera_composition_and_overhead(bridge_under_untagged)
    assert not passed_a, "Camera placed beneath bridge deck without tag must fail validation!"
    assert any("OVERHEAD_STRUCTURE_VIOLATION" in v for v in violations_a), f"Expected OVERHEAD_STRUCTURE_VIOLATION in {violations_a}"
    print(f"  [PASS] Untagged shot beneath bridge deck correctly rejected: {violations_a[0]}")

    # Case B: Edo Bridge - Camera placed under bridge deck WITH 'claustrophobic/reveal' tag -> MUST PASS
    bridge_under_tagged = {
        "scene_world": {
            "location_id": "LOC_EDO_WOODEN_BRIDGE",
            "architecture_style": "EDO_BRIDGE",
            "shot_tag": "claustrophobic/reveal",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 1.8, 0.0], "target": [0.0, 2.5, 0.0], "fov": 44},
                "camera_keyframes": [
                    {"t": 0.0, "position": [0.0, 1.8, 0.0], "target": [0.0, 2.5, 0.0]}
                ]
            }
        },
        "actors": [{"actor_id": "haru", "staging": {"initial_world_pos": [0.0, 2.65, 0.0]}}],
        "tags": ["claustrophobic/reveal"]
    }
    passed_b, violations_b, audit_b = director.validate_camera_composition_and_overhead(bridge_under_tagged)
    assert passed_b, f"Tagged 'claustrophobic/reveal' shot beneath bridge should be permitted, got: {violations_b}"
    assert audit_b["is_claustrophobic_reveal"] is True
    print("  [PASS] Tagged 'claustrophobic/reveal' shot beneath bridge deck explicitly permitted!")

    # Case C: Shanghai Rail Station - Camera inside pedestrian tunnel underpass (Y=1.6m < 2.20m) WITHOUT tag -> MUST FAIL
    rail_tunnel_untagged = {
        "scene_world": {
            "location_id": "LOC_RAIL_STATION",
            "architecture_style": "RAIL_STATION",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 1.6, 0.0], "target": [0.0, 2.0, 0.0], "fov": 42},
                "camera_keyframes": [
                    {"t": 0.0, "position": [0.0, 1.6, 0.0], "target": [0.0, 2.0, 0.0]}
                ]
            }
        },
        "actors": [{"actor_id": "conductor", "staging": {"initial_world_pos": [0.0, 0.45, 0.0]}}],
        "tags": []
    }
    passed_c, violations_c, audit_c = director.validate_camera_composition_and_overhead(rail_tunnel_untagged)
    assert not passed_c, "Camera inside station pedestrian tunnel underpass without tag must fail!"
    assert any("pedestrian tunnel" in v.lower() for v in violations_c), f"Expected tunnel violation, got: {violations_c}"
    print(f"  [PASS] Untagged shot inside rail tunnel underpass correctly rejected: {violations_c[0]}")

    # Case D: Shanghai Rail Station - Tunnel underpass WITH 'claustrophobic/reveal' tag -> MUST PASS
    rail_tunnel_tagged = {
        "scene_world": {
            "location_id": "LOC_RAIL_STATION",
            "architecture_style": "RAIL_STATION",
            "shot_tag": "claustrophobic/reveal",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 1.6, 0.0], "target": [0.0, 2.0, 0.0], "fov": 42},
                "camera_keyframes": [
                    {"t": 0.0, "position": [0.0, 1.6, 0.0], "target": [0.0, 2.0, 0.0]}
                ]
            }
        },
        "actors": [{"actor_id": "conductor", "staging": {"initial_world_pos": [0.0, 0.45, 0.0]}}],
        "tags": ["claustrophobic/reveal"]
    }
    passed_d, violations_d, audit_d = director.validate_camera_composition_and_overhead(rail_tunnel_tagged)
    assert passed_d, f"Tagged 'claustrophobic/reveal' shot in tunnel should be permitted, got: {violations_d}"
    print("  [PASS] Tagged 'claustrophobic/reveal' shot in station underpass explicitly permitted!")

    # Case E: Foreground structure occupies > 35% of frame height WITHOUT tag -> MUST FAIL
    cov_untagged = {
        "scene_world": {
            "location_id": "LOC_EDO_WOODEN_BRIDGE",
            "architecture_style": "EDO_BRIDGE",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 2.0, 3.5], "target": [0.0, 3.2, 0.0], "fov": 50},
                "camera_keyframes": [{"t": 0.0, "position": [0.0, 2.0, 3.5], "target": [0.0, 3.2, 0.0]}]
            }
        },
        "actors": [{"actor_id": "haru", "staging": {"initial_world_pos": [0.0, 2.65, 0.0]}}],
        "tags": []
    }
    passed_e, violations_e, audit_e = director.validate_camera_composition_and_overhead(cov_untagged)
    assert not passed_e, "Shot with foreground structure occupying > 35% without tag must fail!"
    assert any("FOREGROUND_STRUCTURE_COVERAGE_VIOLATION" in v for v in violations_e), f"Expected coverage violation, got: {violations_e}"
    print(f"  [PASS] >35% foreground structure coverage without tag correctly rejected: {violations_e[0]}")

    # Case F: Foreground structure occupies > 35% of frame height WITH 'composition: claustrophobic' -> MUST PASS
    cov_tagged = {
        "scene_world": {
            "location_id": "LOC_EDO_WOODEN_BRIDGE",
            "architecture_style": "EDO_BRIDGE",
            "composition": "claustrophobic",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 2.0, 3.5], "target": [0.0, 3.2, 0.0], "fov": 50},
                "camera_keyframes": [{"t": 0.0, "position": [0.0, 2.0, 3.5], "target": [0.0, 3.2, 0.0]}]
            }
        },
        "composition": "claustrophobic",
        "actors": [{"actor_id": "haru", "staging": {"initial_world_pos": [0.0, 2.65, 0.0]}}],
        "tags": []
    }
    passed_f, violations_f, audit_f = director.validate_camera_composition_and_overhead(cov_tagged)
    assert passed_f, f"Tagged claustrophobic shot with foreground coverage should be permitted, got: {violations_f}"
    print("  [PASS] >35% foreground structure coverage with 'composition: claustrophobic' explicitly permitted!")


def test_node_three_universal_world_camera_composition():
    print("\n--- [3/4] Running Node UniversalWorldEngine Camera Framing & Composition Tests ---")

    node_script = """
    import('./bundle_world.mjs').then(mod => {
      const UniversalWorldEngine = mod.UniversalWorldEngine;

      // Test 1: Edo Wooden Bridge Default Camera
      const locBridge = {
        location_id: 'LOC_EDO_WOODEN_BRIDGE',
        name: 'Edo Wooden Bridge Canal',
        architecture: 'TRADITIONAL_EAST_ASIAN',
        weather: 'RAIN'
      };

      const world = new UniversalWorldEngine(locBridge, 1920, 1080);
      world.update(0.0);

      const actors = [
        {
          actor_id: 'haru',
          dna: { name: 'Haru' },
          staging: { initial_world_pos: [-1.2, 2.65, 0.0] }
        }
      ];

      const framingAudit = world.evaluateCameraFraming(0.0, actors);

      if (!framingAudit.passed) {
        throw new Error(`Default camera framing failed: sky=${framingAudit.skyFraction}, overheadViolation=${framingAudit.overheadStructureViolation}`);
      }
      if (framingAudit.skyFraction < 0.58) {
        throw new Error(`Insufficient open sky: ${framingAudit.skyFraction * 100}% < 60%`);
      }
      if (!framingAudit.lowerMiddleThirdOccupied) {
        throw new Error(`Characters not occupying lower-middle third: headY=${framingAudit.characterHeadScreenY}px, feetY=${framingAudit.characterFeetScreenY}px`);
      }
      if (framingAudit.overheadStructureViolation) {
        throw new Error(`Unexpected overhead structure violation: ${framingAudit.overheadStructureName}`);
      }

      console.log(`  [PASS] Node Edo Bridge: Sky=${(framingAudit.skyFraction * 100).toFixed(1)}%, HeadY=${framingAudit.characterHeadScreenY}px, FeetY=${framingAudit.characterFeetScreenY}px, OverheadViolation=${framingAudit.overheadStructureViolation}`);

      // Test 2: Framing from beneath bridge structure without tag -> Violation detected
      const beneathCheckUntagged = world.checkOverheadStructure([0.0, 1.8, 0.0], false);
      if (!beneathCheckUntagged.violated) {
        throw new Error('Expected camera position under bridge deck to be flagged as violation');
      }
      console.log(`  [PASS] Node Overhead Check: Camera at Y=1.8m correctly flagged under '${beneathCheckUntagged.structureName}'.`);

      // Test 3: Framing from beneath bridge structure WITH 'claustrophobic/reveal' -> Permitted
      const beneathCheckTagged = world.checkOverheadStructure([0.0, 1.8, 0.0], true);
      if (beneathCheckTagged.violated || !beneathCheckTagged.isPermitted) {
        throw new Error('Expected camera position under bridge deck with claustrophobic/reveal to be permitted');
      }
      console.log(`  [PASS] Node Overhead Check: Camera at Y=1.8m with 'claustrophobic/reveal' is permitted.`);

      // Test 4: Rail Station Default Camera
      const locRail = {
        location_id: 'LOC_RAIL_STATION',
        name: 'Shanghai Rail Station 1930',
        architecture: 'RAIL_STATION',
        weather: 'RAIN'
      };
      const railWorld = new UniversalWorldEngine(locRail, 1920, 1080);
      railWorld.update(0.0);
      const railActors = [
        {
          actor_id: 'passenger',
          staging: { initial_world_pos: [-0.8, 0.45, -0.6] }
        }
      ];
      const railAudit = railWorld.evaluateCameraFraming(0.0, railActors);
      if (!railAudit.passed || railAudit.skyFraction < 0.58) {
        throw new Error(`Rail station framing failed: sky=${railAudit.skyFraction}`);
      }
      console.log(`  [PASS] Node Rail Station: Sky=${(railAudit.skyFraction * 100).toFixed(1)}%, HeadY=${railAudit.characterHeadScreenY}px, FeetY=${railAudit.characterFeetScreenY}px.`);

      console.log('\\nALL NODE UNIVERSAL WORLD ENGINE CAMERA TESTS PASSED!');
    }).catch(err => {
      console.error('Node World Engine Test Failure:', err);
      process.exit(1);
    });
    """

    res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, cwd=str(ROOT / "scratch"))
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr)
        raise RuntimeError(f"Node Camera Tests failed with code {res.returncode}")


def test_node_edo_bridge_world():
    print("\n--- [4/4] Running Node EdoBridgeWorld Camera Invariant Tests ---")

    node_script = """
    import('./bundle_edo_bridge.mjs').then(mod => {
      const EdoBridgeWorld = mod.EdoBridgeWorld;
      const world = new EdoBridgeWorld(1920, 1080);
      world.update(0.0);

      // Verify camera position is elevated (Y=4.5m) and not beneath bridge deck (Y=2.65m)
      const camY = world.camera.position.y;
      if (camY < 3.5) {
        throw new Error(`EdoBridgeWorld camera height too low: Y=${camY}m (should be >= 3.5m to clear bridge deck)`);
      }

      // Project Haru (feet at Y=2.65, head at Y=4.37)
      const feetProj = world.projectToScreen([-1.2, 2.65, 0.0]);
      const headProj = world.projectToScreen([-1.2, 4.37, 0.0]);

      const skyFraction = headProj.y / 1080.0;
      if (skyFraction < 0.58) {
        throw new Error(`EdoBridgeWorld sky fraction too low: ${(skyFraction * 100).toFixed(1)}% < 60%`);
      }
      if (headProj.y < 432 || feetProj.y > 1040) {
        throw new Error(`EdoBridgeWorld character not in lower-middle third: headY=${headProj.y}px, feetY=${feetProj.y}px`);
      }

      console.log(`  [PASS] EdoBridgeWorld: CamY=${camY.toFixed(2)}m (clears bridge), Sky=${(skyFraction * 100).toFixed(1)}%, Body in [Y=${headProj.y.toFixed(0)}px, Y=${feetProj.y.toFixed(0)}px].`);
      console.log('\\nALL EDO BRIDGE WORLD CAMERA TESTS PASSED!');
    }).catch(err => {
      console.error('Node Edo Bridge World Test Failure:', err);
      process.exit(1);
    });
    """

    res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, cwd=str(ROOT / "scratch"))
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr)
        raise RuntimeError(f"Node Edo Bridge World Camera Tests failed with code {res.returncode}")


def main():
    print("=" * 70)
    print("CAMERA COMPOSITION & OVERHEAD STRUCTURE AUDIT")
    print("=" * 70)

    test_story_director_camera_presets_composition()
    test_overhead_structure_avoidance_and_tag_exception()
    test_node_three_universal_world_camera_composition()
    test_node_edo_bridge_world()

    print("\n" + "=" * 70)
    print("CAMERA COMPOSITION & OVERHEAD AUDIT: ALL TESTS PASSED STRICTLY (100%)")
    print("=" * 70)


if __name__ == "__main__":
    main()
