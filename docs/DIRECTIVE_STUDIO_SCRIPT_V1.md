# UNIVERSAL STUDIO SCRIPT V1 — IMPLEMENTATION DIRECTIVE

Source: Mai, 2026-11-12 08:12 (+07), sent twice; second send marked "đặc biệt ghi nhớ"
("remember this especially"). Verbatim copy of the user's directive. This file is the
standing requirement source for the STUDIO SCRIPT V1 work. The specification derived
from it lives in `STUDIO_SCRIPT_V1_SPEC.md`; the reusable template in
`STUDIO_SCRIPT_V1_TEMPLATE.md`.

---

Your task is to standardize the existing AI Clip Studio frontend and production pipeline around a single universal script input format.

The supplied Hitler Episode 01 script is a validation fixture, not a project-specific implementation target.

CORE REQUIREMENT

Every future project must use the same STUDIO SCRIPT V1 schema.

Support historical documentaries, comedy, educational videos, fictional stories, biographies, first-person storytelling, third-person storytelling, and other genres.

Do not hardcode Hitler, Munich, Eiffel, Minh, Lan, or any specific story.

1. EXTEND THE EXISTING PARSER

Inspect the current STUDIO SCRIPT V1 parser.

Extend it to support:

* PROJECT
* VISUAL_STYLE
* GLOBAL_AUDIO
* CHARACTER
* LOCATION
* PROP
* SCENE
* SHOT
* NARRATION
* DIALOGUE
* ACTION
* EXPRESSION
* CAMERA
* CAMERA_MOVEMENT
* AMBIENCE
* SFX
* BGM
* VFX
* TRANSITION
* END_CARD
* GLOBAL_NEGATIVE_CONSTRAINTS
* QA
* OUTPUT

Maintain backward compatibility.

Do not create a second parser or production pipeline.

Define explicit schemas, required fields, optional fields, defaults, enums, and validation rules.

Preserve Unicode and Vietnamese text.

2. FRONTEND INTEGRATION

The existing frontend must support:

1. Paste the complete script.
2. Parse and validate the script.
3. Display detected characters.
4. Display detected locations.
5. Display detected props.
6. Display scenes and shots.
7. Display narration and dialogue.
8. Display SFX, ambience, BGM and VFX.
9. Display validation errors with line numbers.
10. Allow review before production.
11. Start the existing UniversalProductionPipeline.
12. Display job progress and artifacts.

Do not silently discard unsupported fields.

If the script contains invalid data, explain the error before rendering.

3. SCRIPT INTEGRITY

Create one immutable script snapshot and SHA-256 hash.

Use the same snapshot throughout:

Frontend → Parser → Gemini → Scene Package → TTS → Animation → Audio → Renderer → QA → Drive.

Never rewrite exact spoken text without explicit user approval.

Production directives must never be passed into TTS as spoken content.

4. AUDIO-DRIVEN TIMELINE

Generate actual Vietnamese speech before finalizing shot durations.

Map each LINE_ID to actual audio timing.

Resolve phrase triggers against the generated speech.

Resolve action triggers against the animation timeline.

Do not estimate final timing from character count alone.

If a trigger cannot be resolved, return a validation error or an explicit review requirement.

Never silently invent an SFX timestamp.

5. SOUND DESIGN

Separate audio buses:

* Narration
* Dialogue
* Ambience
* Foley
* SFX
* Background music

SFX must be attached to meaningful events.

Respect explicit SFX: NONE directives.

Do not automatically add transition whooshes, meme sounds, footsteps, or impact sounds when they are not required.

Deduplicate overlapping sound events.

Ensure narration and dialogue remain intelligible.

6. LOCATION SYSTEM

LOCATION blocks must become reusable environment specifications.

Extract:

* Historical period
* Geography
* Architecture
* Distinctive features
* Foreground
* Midground
* Background
* Lighting
* Weather
* Color palette
* Forbidden elements

Research and verify factual details when required.

Never substitute one location with another merely because an existing background is available.

7. CHARACTER SYSTEM

CHARACTER blocks must become reusable character specifications.

Preserve identity across scenes.

Support costume changes without changing character identity.

Connect ACTION and EXPRESSION directives to the existing articulated animation system.

Report unsupported actions explicitly.

Do not replace unsupported actions with camera pan or zoom.

8. VALIDATION AND TESTING

Run schema validation, reference validation, parser tests, timeline tests, audio tests, animation tests, renderer tests and frontend integration tests.

Use the supplied Hitler Episode 01 script as the first complete test fixture.

Then test at least two unrelated scripts to prove general-purpose behavior.

All scripts must use the same schema and the same UniversalProductionPipeline.

9. PRODUCTION OUTPUT

Render a real Draft using the existing code-driven engine.

Upload the Draft and all QA artifacts to the configured Google Drive folder.

Do not approve Master automatically.

Report actual failures, unsupported fields, implementation blockers, and creative review requirements.

10. DOCUMENTATION

Create and maintain:

* docs/STUDIO_SCRIPT_V1_SPEC.md
* docs/STUDIO_SCRIPT_V1_TEMPLATE.md
* examples/hitler_ep01.studio.md
* A machine-readable script schema.
* Parser regression tests.
* Frontend validation tests.

The template must be reusable for every future project.

The specification must be the single source of truth for script input.

Do not introduce conflicting script formats.

FINAL OBJECTIVE:

The user should be able to paste any valid STUDIO SCRIPT V1 document into the frontend and generate a complete production Draft without writing additional project-specific code.

---

Standing context recorded with this directive (Mai, 2026-11-12 08:12):

- Scenes are not diverse enough: whatever the script and characters, scenes and
  characters must all be diverse and each have its own distinctive traits.
- This directive is a standing requirement ("đặc biệt ghi nhớ"). It does not
  expire when the current implementation round ends.
- Head ratio stays 0.34 (Mai-approved v8 design); never inherit the upstream
  V1 parser's 0.42 default.
- The Episode 01 fixture is for validation only; generality is proven by
  rendering unrelated scripts. No render of the fixture without ATLAS approval.
- Gemini's role (Mai, 2026-11-12 08:25 — "đặc biệt lưu ý", pay special
  attention): Gemini is the sketcher supporting the drawing of distinctive
  traits — character actions, costumes and appearance; distinctive features of
  locations and places; SFX; music; special actions. Gemini supplies these as
  structured per-script trait data; the general engine/pipeline consumes the
  data and renders. This is the core of the V1 LOCATION/CHARACTER systems.
- Test script (Mai, 2026-11-12 09:33): AI clip tests use the Hitler Episode 01
  script supplied before; follow her requirements exactly; do not invent or
  freelance test scripts. This OVERRIDES the earlier "validation only" note for
  the fixture above — the V1 end-to-end proof renders the Ep1 script.
  Generality is proven only with scripts Mai supplies herself.
- FIRST-PERSON RULE, PREREQUISITE (Mai, 2026-11-12 10:20 — "rules tiên quyết"):
  ALL of Mai's scripts are told in the FIRST PERSON by the character(s);
  there is NEVER an external narrator ("không cần người dẫn truyện").
  NARRATION blocks are spoken by the primary character in first-person voice,
  never by a narrator voice. This is a prerequisite project rule recorded in
  long-term memory. The parser and SPEC must encode it: EXTERNAL_NARRATOR
  must be NONE and external narrator lines must be 0; the adapter must never
  inject a narrator sentinel for such scripts.
- Authoritative Ep1 script (Mai, 2026-11-12 10:20): the first-person script
  pasted in chat (PROJECT_ID HITLER_EP01_MUNICH_1914, 6 scenes, 17 shots,
  9 spoken lines, 0 narrator lines, 7 SFX events) saved verbatim at
  examples/hitler_ep01_munich_1914.studio.md REPLACES the older upstream
  fixture (8 scenes, narrator, Bà Chủ Nhà) as the render target. The
  req_8faa5a8dd9e2 render used the outdated fixture and is superseded.
