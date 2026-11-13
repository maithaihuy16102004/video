# Patches — what they do, and the 2026-11-11 correction

Both patches are proposals for Mai to review. They are **not applied**
to the upstream `video` repo; they live here as real unified diffs that
can be applied with `git apply`.

## 01-headratio-schema.patch

Locks the V51 character standard into the code:

- `V5_PRODUCTION_SCENE_SCHEMA.json`: `headRatio` allowed range
  `0.20–0.35` → `0.142–0.155`.
- `pipeline/universal/v5_story_director.py`: `compile_v2` default
  `headRatio 0.42` → `0.15`, and the prompt text
  "40–45% … oversized round head" → "14–16% … V51 standard,
  6.5–7.0 heads tall, never chibi".

Effect: a V50 package with `headRatio 0.28` will now **fail**
validation instead of silently rendering with the rejected V50 rig.
Those packages must be re-rendered with the V51 rig.

## 02-tts-duration-fit.patch

Fixes the bug that cuts the last voice line in all three V51 drafts
(draft 3 loses its twist line entirely).

- `pipeline/studio_api.py` (`run_production_render_service`): the
  preview cap is 15 s and the final cap 30 s, whatever the voice
  needs. The patch measures the real voice first and extends the
  timeline (`effective_duration = max(capped, voice + 0.5 s tail)`)
  instead of cutting the last line. It uses the `duration` argument —
  callers already pass `duration = voice_duration(voice)` (ffprobe) —
  and, for a WAV voice file, measures it directly with `wave`
  (already imported in that file) as a safety net. Speech is never
  sped up. Consequence to be aware of: a preview whose voice needs
  17 s will now render as ~17.5 s, not 15 s.
- `pipeline/universal/v5_audio_director.py` (`compose_scene_audio`):
  two fail-loud guards replace silent truncation — one for a
  pre-synthesised voice WAV longer than the timeline, one for an
  individually synthesised line that would overflow. Both raise
  `ValueError` telling the operator to extend the timeline.

## Correction made 2026-11-11 (before Mai reviewed them)

The first versions of these two files, sent to Mai at 10:34 local,
were **not actually applicable**:

- Patch 01 had a wrong hunk length (`@@ -1513,7 +1513,7 @@` for a
  hunk that is really 8 lines) so `git apply --check` failed with
  "patch fragment without header".
- Patch 02 was not a diff at all — it was commented pseudo-code
  (`# --- a/...`) calling a helper `_wav_duration_seconds` that does
  not exist anywhere in the repo, so `git apply` reported
  "No valid patches in input".

Both files have been rewritten as genuine unified diffs (generated
from the edited files, so the hunk headers are correct) and verified:

- `git apply --check` passes for both, on a fresh copy of upstream
  commit `c4832c8`.
- `git apply` of both reproduces the edited tree exactly.
- `python3 -m py_compile` passes for all three touched Python files;
  the schema file is still valid JSON.
- Functional test of the patched audio director (stubbed sound
  registry, silent test WAVs): a 3.00 s voice on a 2.00 s timeline
  now raises `ValueError: Voice audio (3.00s) is longer than the
  planned timeline (2.00s)…`; the same voice on a 5.00 s timeline
  renders a master WAV successfully.
- The 11 unit tests in `youtube_16x9/tests/test_16x9.py` still pass.

Nothing in the upstream repo was changed; only these local files
in `~/workspace/agent/` were corrected.
