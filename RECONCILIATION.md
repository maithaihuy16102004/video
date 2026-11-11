# Reconciliation — 16:9 Ricks-style layer vs. real V5.1 code

> Correction 2026-11-11: the two patch files in `patches/` as first sent
> at 10:34 local did **not** apply — patch 01 had a wrong hunk length and
> patch 02 was commented pseudo-code, not a diff. Both have been rewritten
> as real unified diffs and verified (`git apply --check` passes, the
> audio guard was functionally tested). Details in `PATCHES.md`.
> Nothing in the upstream repo was changed.

Date: 2026-11-11. Upstream checked: `maithaihuy16102004/video`
at commit `c4832c8ff8e5d6273daba4d6647bbf62a69092e7` ("first commit",
2,090 files, cloned read-only — nothing in the repo was changed).

## What was checked

- `V5_PRODUCTION_SCENE_SCHEMA.json`
- `pipeline/universal/v5_story_director.py`
- `pipeline/universal/v5_audio_director.py`
- `pipeline/studio_api.py` (`run_production_render_service`)
- `scripts/production_render_service.mjs`
- `motioncanvas/contract/VisualStyleBible.ts`
- `motioncanvas/contract/CharacterDNA.ts`
- Root `README.md`, `.gitignore`, `pipeline/__init__.py`

## Result: the 16:9 layer does NOT overwrite upstream code

The first version of the 16:9 layer (in `~/workspace/video-16x9/`) would
have collided with three upstream files:

| File in first version | Upstream file | Conflict |
|---|---|---|
| `README.md` | `README.md` (3,586 bytes, YouTube/TikTok automation workspace) | would overwrite |
| `.gitignore` | `.gitignore` (578 bytes, secrets + output rules) | would overwrite, and would **weaken** the secrets rules |
| `pipeline/__init__.py` (empty) | `pipeline/__init__.py` (`"""Agent media and universal story pipeline package."""`) | would overwrite |

So the push-ready tree in this folder restructures the layer as a
purely additive folder:

```
youtube_16x9/
  README.md, config/youtube_16x9.json
  pipeline/ricks_story_director.py
  pipeline/quality_gate_16x9.py
  pipeline/render_16x9.py
  motioncanvas/contract/VisualStyleBible16x9.ts
  examples/, tests/, requirements.txt
patches/
  01-headratio-schema.patch      (proposed, NOT applied)
  02-tts-duration-fit.patch      (proposed, NOT applied)
RECONCILIATION.md                (this file)
```

No upstream file is modified by this tree. The two patches are
proposals for Mai to review — they change upstream files, so they are
kept separate and are not applied here.

All 11 unit tests in `youtube_16x9/tests/test_16x9.py` pass in this
layout (`python3 -m unittest discover -s youtube_16x9/tests -v`).

## Confirmed in real code

### 1. 16:9 is already the default render — the layer only locks it in

`scripts/production_render_service.mjs:129-130`:
`renderW = activePkg?.width || (aspect_ratio === '9:16' ? 1080 : 1920)`,
same for height, `fps = 24` (line 98). The 16:9 layer therefore does
not need to change the renderer; it only makes 1920x1080 mandatory
in the package and rejects a 9:16 input instead of pillarboxing it
(`youtube_16x9/pipeline/render_16x9.py: validate_16x9_input`).

### 2. headRatio has THREE different values in real code — patch 01

- `V5_PRODUCTION_SCENE_SCHEMA.json:51` — allows `0.20–0.35`
- `pipeline/universal/v5_story_director.py:1253-1273` — the five
  archetypes actually use `0.142–0.155` (V51 standard)
- `motioncanvas/contract/CharacterDNA.ts:70` — comment says
  `0.14–0.16 (6.3 to 7.0 heads tall, never chibi)`, archetypes
  `0.142–0.155`
- `pipeline/universal/v5_story_director.py:1516` — `compile_v2_…`
  defaults to `headRatio 0.42`, and line 1668 describes it as
  "40–45% of total height (oversized round head)"

That is the V50/V51 conflict from the Drive review, confirmed in
code. Patch 01 locks the schema to `0.142–0.155` and changes the
0.42 default to `0.15`. Until that lands, a V50 package with
`headRatio 0.28` still validates against the schema.

### 3. TTS cut-off root cause — patch 02 (the draft-3 twist bug)

`pipeline/studio_api.py: run_production_render_service`:
`effective_duration = min(15.0 if mode == "preview" else 30.0, …)` —
drafts are capped at 15 s in preview mode, whatever the voice needs.

`pipeline/universal/v5_audio_director.py: compose_scene_audio`:
tracks are allocated exactly `total_duration_sec`, lines are laid
out sequentially from 0.5 s (`current_voice_t += line_dur + 0.5`),
and each line is truncated with
`s_end = min(n_total_samples, s_start + int(line_dur * sr))`.
A pre-synthesised voice file is truncated the same way
(`n_copy = min(n_total_samples, len(v_data))`).

So if the real TTS audio is longer than the planned 15 s, the last
line is cut — exactly what the Drive review found in all three V51
drafts, and why draft 3 loses its twist line entirely.

Patch 02 proposes the fix without changing speech speed (V5 forbids
speed-up): measure the real voice WAV first, set
`effective_duration = max(planned, measured + 0.5 s tail)`, and make
`compose_scene_audio` raise instead of silently truncating when a
line would overflow. It is a proposal, not an applied change.

## What still needs Mai

1. Grant the Muse GitHub App access to the `video` repo (it returned
   403 on push). Then this tree can be pushed as new files only.
2. Review patches 01 and 02 before they are applied to upstream files.
3. After patch 02, re-render the three V51 drafts and check that the
   final line / twist is present in full before any 16:9 YouTube upload.
