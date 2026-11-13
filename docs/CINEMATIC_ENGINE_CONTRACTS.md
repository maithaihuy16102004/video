# Cinematic Engine Upgrade — Interfaces & Ownership

Mai's directive, 2026-11-12 17:01. Interfaces are defined BEFORE
parallel implementation. The Python source of truth is
`ai_clip_studio/cinematic_contracts.py` (ATLAS-owned, 16 tests);
this file records the ownership map and checkpoint rules.

## Decisions (resolved by this directive)

- **D1 Locomotion:** one shared canonical engine + parametric gait
  profiles (`GaitProfile`: step/stride separated, cadence, speed,
  mass, posture, head stability, arm pose, fatigue, terrain,
  style). Canonical gait is the default; elderly/soldier/giant/
  Zeus/civilian must not move identically.
- **D2 Camera:** head-tracking crop OFF by default; framing anchored
  to scene/explicit target; static + hard cuts as default grammar.
  Scripted movements (dolly/pan/tracking/crane/reveal/shake) remain
  available as explicit capabilities, never implicit defaults.
- **D3 Character art:** head ratio 0.34 locked; no redesign without
  authorization. Acting/costume/silhouette/hands improve without
  changing the approved identity.
- **D4 Reference:** RicksClips is a principles benchmark, not a set
  of unconditional restrictions. No copying characters/art/scenes.

## Ownership (disjoint — no concurrent edits to shared modules)

| Owner | Writable files |
|---|---|
| Subagent A | `animation/rig.py`, `animation/primitives.py`, `expression_library.py` (repo root — the directive's `animation/` path was a misnomer), `action_compiler.py`, `prop_system.py`, new modules under `animation/`, character-motion tests |
| Subagent B | `environment_v2.py`, `paint_textures.py`, `lighting.py` (repo root — NOT `renderer25d/lighting.py`, read-only), `map_renderer.py`, `camera_planner.py`, environment/camera tests |
| ATLAS | `product_flow.py`, `product_renderer.py` (incl. `plan_shots`), `server.py`, `qa_gates.py`, `coverage_audit.py`, `cinematic_contracts.py`, `motioncanvas_spec.py`, audio timeline, `character_art.py`, Drive delivery, final rendering |

`cinematic_contracts.py` is import-only for A and B. `affiliate/`,
`youtube_16x9/`, `motioncanvas25d/`, `frontend_patches/` are
read-only for both. The legacy orchestrator stays isolated.

## Checkpoint rules

1. A change needed in a file outside your ownership is delivered as
   a written spec in your report (file, function, exact behavior) —
   never edited directly. ATLAS applies it at the checkpoint.
   Known splits: head-tracking crop removal spans `camera_planner.py`
   (B) + the crop call site in `product_renderer.py` (ATLAS);
   locomotion framing rules span `rig.py` (A) + `camera_planner.py`
   (B) + `plan_shots` (ATLAS); costume/silhouette rendering spans
   owned modules (A) + `character_art.py` (ATLAS).
2. No second planner, compiler, or pipeline. Refactor in place.
3. Every change ships with unit tests; proofs are real rendered
   MP4s + measured frames, never scores alone.
4. Standing rules hold: Vietnamese default, first-person, no
   narrator, no Master without approval, no GitHub push, Affiliate
   paused, no AI-generated video, no freelance test scripts (Tests
   A–G are Mai-specified).

## Phase map

- A: canonical locomotion + gait profiles (Phase A), expression
  transitions (Phase D), prop interaction (Tests A/B/E).
- B: camera modes + anchoring (Phase C), environment P-S2/P-S3/
  P-S5/P-S12 + semantic landmarks (Phase E), Tests C/D/F-env.
- ATLAS: shot planner V2 (Phase B), measurement integrity (Phase
  F), audio/action sync (Phase G), Motion Canvas proof (Phase H),
  integration, Tests C–G assembly, episodes, Drive, final report.

## Checkpoint decisions (2026-11-12, ATLAS; from the A/B reports)

- **A-Q1 arm_pose:** the product flow always resolves a gait
  profile (S2/S3), so production renders use the contract's
  `arm_pose="task"`. The legacy `"swing"` default remains only
  on the no-profile path (unit tests / backward compat).
- **A-Q2 stride:** stride stays measured/reported, driven by
  step only. Asymmetric gaits are deferred; no engine change.
- **A-Q3 unsnapped transitions:** a major change with no
  cut/beat anchor keeps its time WITH a surfaced warning; it
  is not a hard failure in a draft. Phase B owns the snapping.
- **A-Q4 plan_locomotion call site:** per continuous locomotion
  segment, with `cut_before` at shot boundaries (spec S4).
- **B-Q1 standing boxes:** answered by implementation — staging
  x + ground_y/char_height + head_r (see `_standing_box` in
  `product_renderer.py`).
- **B-Q2 directive duration:** answered by implementation — the
  render path constructs the real `CameraDirective` with the
  timeline duration; the shot report carries it.
- **B-Q3 repeated framing:** NOT decided as deliberate. Phase B
  investigates the 4 pairs; the validator keeps flagging them.
  An `allow_repeat` flag only if Phase B proves intent.
- **B-Q4 FG vertical fit:** accept B's recommendation — keep
  the fit X-only (pinned W2 behaviour), stage shorter FG lamps;
  the validator flags the rest.
- **B-Q5 emitter tolerance:** open for Phase H — verify the
  Motion Canvas emitter tolerates the new `extra`/provenance
  keys, or strip them at the emitter boundary.
- **B §5.2 location_keyword default:** Phase B scope — emit
  `None`/omit when no keyword was derived; check all consumers
  of `derive_location_traits` first.
- **Crop freeze (B §5.1, implemented):** one standing-box crop
  per shot, frozen; object_insert anchors from the first built
  frame's prop position. TEST C close-up sky MAD 44.92 → 0.00.
  The freeze EXPOSED a planner pairing gap (close_up on a
  walking shot lets the head exit the frame): Phase B fixes
  pairing; tracking is never re-enabled.
