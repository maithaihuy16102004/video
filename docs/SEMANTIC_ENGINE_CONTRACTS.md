# Semantic Engine Contracts

Mai's SEMANTIC PRODUCTION ENGINE UPGRADE (2026-11-12 21:05). ATLAS owns
these contracts. A2/B2 import `ai_clip_studio/semantic_contracts.py`
and build against it; they never edit it and never redesign these
interfaces independently.

## Principle

One source of truth per concern. Downstream modules decide
PRESENTATION, never story meaning.

```
STUDIO SCRIPT V1 -> Immutable Snapshot -> Semantic Parser
  -> Canonical Scene Graph -> Action Compiler
  -> Unified Production Timeline (FROZEN)
  -> {Shot Planner, Animation, Camera, Props, Environment,
      Lighting/VFX, Audio/SFX, Subtitles} -> Final Renderer
  -> Technical QA + Semantic QA + Creative QA -> Drive Draft
```

## Authority order (directive §4)

1. Explicit structured STUDIO SCRIPT V1 directives.
2. Explicit contextual action descriptions.
3. Canonical compiled action events.
4. Safe supporting actions.
5. Optional planner suggestions (keyword cues live here — lowest).

Generic keyword cues must never override higher-authority instructions.
If the compiler produces TAKE_OUT + OPEN_WALLET, the shot planner stages
those events; it must not substitute BEND_PICK / PICK_FROM_GROUND.

## Canonical scene graph (ATLAS, directive §5)

EXTEND the existing scene-package dict architecture — no duplicate
representation. The graph adds, on top of the current package shape:

- Stable identifiers for every entity: `CHAR_*`, `LOC_*`, `PROP_*`,
  `SC*_SH*` directive ids, `ACT*` event ids. Every downstream artifact
  references these ids (no name matching).
- Per entity: identity + state + source provenance
  (`source_script_hash`, `source_scene_id`, `source_shot_id`,
  `source_directive_id`).
- Coverage: characters (+ relationships, identity, costume states),
  locations (+ environment attributes), props (+ ownership, states),
  actions, expressions, weather, lighting, camera requirements,
  narration, dialogue, audio cues, VFX, scene transitions.
- Validation BEFORE expensive rendering (semantic preflight): unknown
  mandatory props fail; unresolved mandatory conflicts fail; missing
  provenance fails.

## Contextual semantic parser (A2, directive §3)

`vi_script_parser.py`: phrase-level + contextual interpretation. Do NOT
solve by adding isolated keywords to ACTION_VERBS. Each action resolves
to the 16-field `SemanticAction` record in `semantic_contracts.py`
(actor, type, target, source/destination location, body part, hand,
object states before/after, spatial relationship, intent, source ids,
source text, confidence, provenance) + origin/authority/authorization.

Normative distinctions (regression seed; paraphrases required):

| Phrase | Expected | Never |
|---|---|---|
| Cúi đầu suy nghĩ | HEAD_TILT_DOWN | BEND_PICK |
| Cúi xuống nhặt chiếc ví trên đường | BEND_PICK | HEAD_TILT_DOWN |
| Lấy ví từ túi áo | TAKE_FROM_POCKET | PICK_FROM_GROUND |
| Lấy bút trên bàn | PICK_FROM_SURFACE | TAKE_FROM_POCKET |
| Cúi người tránh tiếng pháo | CROUCH | PICK_FROM_GROUND |
| Nhận tia sét bằng tay phải | RECEIVE_PROP (RIGHT) | SPAWN_PROP |
| Cyclops đập búa | HAMMER_STRIKE | GENERIC_ATTACK |

## Scene-local state isolation (B2, directive §6)

Scopes: PROJECT / SCENE / SHOT / EVENT / CHARACTER / PROP.
Inheritance SHOT -> SCENE -> PROJECT (nearest wins,
`resolve_scoped_attribute`). Scene change resets SHOT scope; project
change resets everything below PROJECT. Scene attributes (rain,
lighting, costume) never propagate to unrelated scenes unless the graph
explicitly declares carry-over (e.g., a held prop crossing a scene
boundary only when the graph says so).

## Prop state machine (A2 extends prop_system.py, directive §7)

Independent dimensions: location (IN_POCKET / ON_SURFACE / ON_GROUND /
HELD_LEFT / HELD_RIGHT / HELD_BOTH / IN_TRANSIT), container (OPEN /
CLOSED / NA), lifecycle (PRESENT / RELEASED / DESTROYED), ownership
(holder id + TRANSFER_IN_PROGRESS). Allowed transitions in
`PROP_TRANSITIONS`. Ground rule: a prop renders on the ground ONLY
while its location state is ON_GROUND. Handover: giver owns before
contact, both hands may contact during transfer, ownership changes at
the transfer event, receiver owns after; no teleportation, no
duplicates, no floating geometry.

## Semantic prop renderer (A2 geometry + B2 materials, directive §8)

Procedural/vector geometry + materials + articulated components + grip
points + contact points + emissive surfaces + state-dependent geometry
+ consistent scale + camera-independent identity. Proof props: wallet,
pen, letter, blacksmith hammer, lightning bolt, trident, helmet.
Unknown mandatory props fail preflight. Brown boxes only in explicitly
labeled engineering previews.

## Unified production clock (ATLAS, directive §9)

Measured TTS durations + approved narrative timing -> narrative beats
-> action events -> shot intervals, resolved BEFORE freezing. After
freeze, no module mutates spoken-line placement; a scheduling conflict
requires an explicit rebuild. Integer frame indices (24 fps) + integer
audio sample indices (48 kHz) are authoritative; seconds derive from
indices. Tracks: narration, dialogue, actions, prop_interactions,
expressions, shots, camera_cuts, lighting, vfx, sfx, ambience, music,
subtitles, end_cards. `FrozenSchedule` in `semantic_contracts.py`
defines freeze semantics + the exactly-once narration check.

## Shot planner (ATLAS, directive §10)

Presentation layer. Consumes canonical events + the frozen timeline.
Never invents contradictory actions. Context-aware hooks, meaningful
reactions, object inserts, full-body locomotion, fixed camera within
shots, cuts for viewpoint changes, stable screen direction, explicit
reveals, context-sensitive durations. The 2–5 s guideline is NOT
mechanical: comprehension, action continuity, and emotional timing win.

## Semantic audio anchors (ATLAS, directive §11)

Mandatory physical SFX reference semantic events (WALLET_OPENED,
PEN_CONTACT_PAPER, DOCUMENT_PICKUP, FOOT_CONTACT_MUD,
HAMMER_CONTACT_ANVIL, PROP_TRANSFER, LIGHTNING_ACTIVATED). No silent
scene-start fallback for unresolved mandatory action sounds — report
explicitly. Ambience/music may use scene intervals. Onsets verified
against rendered visual events.

## Conflict detection (A2 mechanism, ATLAS rules, directive §4)

Levels: parser / cues / compiled_events / shot_staging /
renderer_events. `ConflictRecord` + `resolve_conflict` in
`semantic_contracts.py`: higher authority wins; equal-authority
disagreement stays unresolved; unresolved MANDATORY conflicts fail
semantic preflight.

## Ownership

| Area | Owner |
|---|---|
| semantic_contracts.py, this doc | ATLAS (A2/B2 import-only) |
| Contextual parser, provenance, conflicts, prop states/geometry, handover, interaction regressions | A2 |
| Scene isolation, prop materials, emissive lighting, forge, landmarks, map verification | B2 |
| Scene graph, unified timeline, shot planner authority, audio anchors, cross-module validation, MP4 verification, regression, Drive | ATLAS |

## Integration order

1. Contracts (this doc + module + 24 tests) — DONE 2026-11-12.
2. A2 parser + provenance + prop machine/geometry; B2 isolation +
   materials + forge + map research — in flight.
3. ATLAS: scene-graph builder/validator + unified-timeline builder +
   shot-planner rewire + SFX anchors + MP4 verifier.
4. Joint integration: full suite + semantic regression matrix + TEST
   A–E proofs + Zeus full-draft correction (§18) + Ep1 resume on a
   VERIFIED map dataset.
