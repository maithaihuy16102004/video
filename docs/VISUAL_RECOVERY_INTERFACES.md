# VISUAL QUALITY RECOVERY — Shared Interface Contracts

Mission directive: 2026-11-12 (Mai). Visual review of the Ep1 v2 draft ~4.15/10.
Goal: improve the reusable engine. No per-script/per-character hardcoding. No GitHub
push without Mai's explicit permission. No Master without approval. No fabricated
creative scores.

Owners: Subagent A = action compiler, prop system, expression library, rig/acting.
Subagent B = environment v2, map renderer, lighting, camera composition.
ATLAS = this contract, audio recovery, Motion Canvas, coverage audit, pipeline
wiring (product_renderer / product_flow / server), regression, proof renders, Drive.

## 1. Action compiler — `ai_clip_studio/action_compiler.py` (A)

```python
compile_actions(scene_package: dict, timeline: dict) -> (events, unsupported)
```

Event dict keys (all required unless noted):
- `action_id`: stable, e.g. `SC01_SH02_ACT01`
- `actor_id`, `action_type` (verb enum, documented in module), `target_id` (or None),
  `prop_id` (or None)
- `start_time`, `end_time`: seconds, from the timeline
- `required_pose`: pose name + params
- `contact_points`: list of `{joint, target_kind, target_id, tolerance_px}`
- `animation_dependencies`: list of `action_id`
- `completion_state`: e.g. `POSE_HELD` / `PROP_TRANSFERRED` / `OBJECT_STATE_CHANGED` + details

Unsupported actions: separate list of `{action_id, reason, directive_text}`.
NEVER silently substitute idle. First-person pronoun resolution: when
`scene_package["meta"]["STORYTELLING_MODE"] == "FIRST_PERSON_ROLEPLAY"`,
actor mentions `Tôi/tôi/mình` resolve to `PRIMARY_CHARACTER`. Pronoun list
documented in the module.

## 2. Prop state machine — `ai_clip_studio/prop_system.py` (A)

States: `WORLD_STATIC`, `APPROACHING`, `GRASPED`, `ATTACHED_TO_HAND`, `IN_USE`,
`TRANSFERRED`, `RELEASED`.

```python
PropStateMachine(props, events)
state_at(prop_id, t) -> state
transform_at(prop_id, t, joints: dict) -> (x, y, angle_deg, state, hand)
contact_satisfied(event, joints, prop_transforms) -> bool
```

Invariants (tested): prop follows the named hand joint while attached/in use;
no teleport between consecutive samples (documented max-jump threshold); prop on
the ground ONLY after an explicit RELEASED transition from a release action.

## 3. Expression library — `ai_clip_studio/expression_library.py` (A)

- 8 base expressions: reuse/extend `EXPRESSIONS` in `character_art.py`, no duplicates.
- `blend(expr_a, expr_b, u)`, `interpret(text) -> expression` with NEGATION handling
  (`không X` must NOT map to X; negation words documented).
- Lip sync: timing-driven mouth-openness function over `(start, end)` per spoken
  line + documented interface for TTS timing. No fake phonemes.
- Primitives in `animation/primitives.py`: `sit_at_desk`, `stand_from_chair`,
  `pick_up`, `open_wallet`, `close_wallet`, `hold_pen`, `write_on_paper`,
  `sign_document`, `hand_over`, `walk_mud`, `carry_bag`, `look_at`, `react_event`.
  Parameterized, each with a completion pose. Approved identity preserved:
  head_ratio lock 0.33–0.35, same line system.

## 4. Environment engine V2 — `ai_clip_studio/environment_v2.py` (B)

```python
build_environment(location_traits, period, time_of_day, style) -> EnvironmentPackage
render_environment(pkg, camera, size) -> PIL.Image  # or documented draw calls
validate_period(elements, period) -> list[violations]
```

EnvironmentPackage: `{layers: {FG, MG, BG}, elements: [{kind, geometry, attachment,
material, palette}], palette, light, provenance: {trait_source, archetype}}`.
Attachment validation: windows inside walls, doors reach ground, roofs on top.
Archetype catalog is general and data-selected from location traits only
(EUROPEAN_STREET_1900, GREEK_PALACE, MEDITERRANEAN_ISLAND, CAVE, BARRACKS,
TRENCH, FOREST, MODERN_CITY, ...). Never select by script/project ID.

## 5. Map renderer — `ai_clip_studio/map_renderer.py` (B)

```python
render_map(map_spec: dict) -> (PIL.Image, MapReport)
```

map_spec: `{svg_paths | dataset_ref, highlight, labels, route: {points, progress_t},
framing, timeline_sync}`. MapReport MUST carry provenance: dataset name, source
URL, license, date. Historical mode with no verified dataset: FAIL LOUDLY with a
named missing-data error. Modern-boundary fallback only with the report stating
"modern boundaries — not 1914". No rectangular country cards. Route progress
parameterized by `t in [0,1]`.

## 6. Lighting — `ai_clip_studio/lighting.py` (B)

`light_direction`, `shadow_scale` (contact shadows proportional to object size;
documented ratio + test — fixes the oversized-blob defect), time-of-day palettes
that must NOT darken daytime (regression test on day-scene luminance).

## 7. Camera composition — `ai_clip_studio/camera_planner.py` (B, extend)

```python
plan_shot(shot, scene) -> {camera_position, target, fov, framing, subject,
                           location_override, screen_direction} + accounting entry
```

Accounting entry: `{shot_id, directive, frame_range (ATLAS fills at render), pose,
continuity_notes}`. Locked rules: camera FIXED within a shot; viewpoint changes BY
CUT only; no zoom-as-angle; F2 standing-box preserved (heads stable, max_scale 1.0
full-body); OTS/SRS from character positions; any CAMERA_MOVEMENT override
documented in the accounting. Measurement helpers for the independent audit:
within-shot sky-band MAD, cut MAD, head-width stability.

## 8. Coverage audit — ATLAS (P9)

Consumes: action compiler events + unsupported list, prop state traces, camera
accounting, expression mappings, SFX/location records. Output: machine-readable
report, every source item -> IMPLEMENTED / PARTIALLY_IMPLEMENTED / UNSUPPORTED /
FAILED with frame ranges + evidence references. No silent omission.

## 9. Wiring (ATLAS only)

Only ATLAS edits `product_renderer.py`, `product_flow.py`, `server.py`,
`pipeline/*`. A/B prove modules with direct calls + the real rig; ATLAS integrates
after both land, runs the full suite, renders proof clips (Tests 1–6), and
delivers to Drive `VISUAL_QUALITY_RECOVERY`.
