# Third-Party Notices

This file records third-party material adapted into this repository, as
required by its license. It was created on 2026-11-12 during the external
repo audit (see `../acceptance_loop/EXTERNAL_REPO_AUDIT_CLAUDE_ANIMATED_SHORTS.md`).

## 1. claude-animated-shorts (MIT License)

- **Source repository:** https://github.com/mromidev/claude-animated-shorts.git
- **Author / copyright holder:** Mr omi
- **License:** MIT (full text below, copied from the source repo's `LICENSE` file)
- **Local read-only reference clone:** `~/workspace/external/claude-animated-shorts/`
  (commit `e3b817b`, never edited, never pushed anywhere from this project)
- **What it is:** an independent Claude skill (`cartoon-3d-short`) that makes
  vertical animated story shorts with three.js inside Remotion. It is **not**
  affiliated with RicksClips or with the channel it studied privately.

### MIT License text (Copyright (c) 2026 Mr omi)

```
MIT License

Copyright (c) 2026 Mr omi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### What was taken / adapted (file by file)

Only techniques and measured values were adapted. No artwork, characters,
scenes, scripts, branding, or reference imagery was taken. Every adapted
file below carries an MIT attribution header naming the source repo and
copyright. Nothing is wired into the pipeline, renderer, or server yet —
wiring is Phase 2 work, after Stage 3 lands.

| File in this repo | Source file(s) in claude-animated-shorts | What was adapted |
|---|---|---|
| `ai_clip_studio/frame_qa.py` | `templates/scripts/short_qa.py` | Black/white/frozen/pop frame detection thresholds and math (luma < 0.04, luma > 0.93, diff < 0.02 for >= 0.4 s, pop > 3x local median + 1.0), planned-frame exclusion construction, per-shot median stats. Re-parameterized for 16:9 / 24 fps (the original hard-codes 180x320 vertical decode and 30 fps frame counts) and restructured as importable functions. |
| `ai_clip_studio/synth_sfx.py` | `templates/audio/dsp.py`, `templates/audio/sfx_gen.py` | Synthesis mechanisms only: modal decaying-sine synthesis (`modal`), pitch-drop thump (core of `boot`), inharmonic clink (`clink`), layered footstep (`boot`), constant-power pan (`pan`), buffer placement (`place`), WAV output (simplified `write_wav`). Re-implemented numpy-only without scipy; filters, STFT shaping, reverb, and loudness metering were NOT ported. |
| `ai_clip_studio/look_targets.py` | `references/reports/grade.md`, `lighting.md`, `depth.md`, `motion.md`, `outlines.md`; `templates/bridge/grade.ts`, `lights.ts`, `ink.ts`, `lensblur.ts`, `cast.ts` | Measured values only: 7-knot grade curves + zone saturation + 3-way tints + vignette (incl. the gentle round-2 re-fit), Fritsch-Carlson monotone tangent math, two-tone light presets, 5-stop sky colours, fog ranges, DOF C_inf table, headroom/horizon/camera-height fractions, ink widths/angles, luma targets, shadow ratios, and timing values (blink pattern, reaction lead, anticipation, walk) marked PROPOSED. Measurement only — no render behaviour. |
| `ai_clip_studio/tests/test_frame_qa.py` | (tests for the adaptation above) | New tests, written for this repo; no source test code was copied (the source repo ships no tests). |
| `ai_clip_studio/tests/test_synth_sfx.py` | (tests for the adaptation above) | New tests, written for this repo. |
| `ai_clip_studio/tests/test_look_targets.py` | (tests for the adaptation above) | New tests, written for this repo. |

### Explicitly EXCLUDED — never copied, moved, uploaded, or pushed

- `references/frames/` — 38 reference frames (study-only per the source
  repo's own README/SKILL.md, which forbids upload, publish, or send).
  Viewed locally (2 frames) for audit purposes only. No copies exist in
  this repository, in Drive, or in any push.
- `references/sheets/` — 20 contact sheets (1,200 frames). Same study-only
  restriction. Never viewed frame-by-frame, never copied anywhere.
- The studied channel's scripts, characters, artwork, scenes, shots, and
  branding, and RicksClips' characters/artwork/branding: never copied.
  Techniques and measured values only, as the source README itself directs
  ("Use the references for the look, not the content").
- Kenney CC0 GLB props referenced by `templates/bridge/build.ts` /
  `world.ts`: **no Kenney assets are present in the source repo** (verified:
  zero `.glb`/`.gltf` files; `loadKit()` expects them under an external
  Remotion `public/bridge/kenney/` path). Nothing was taken; the dependency
  is recorded honestly in the audit report.
- The source repo's voice files (`voice/voice.wav`, `voice/words.json`,
  required by `templates/audio/mix.py`): not present in the source repo,
  nothing taken.

### Other third-party material in this repository

None recorded yet. The upstream V5.1 code (`video-upstream/`, read-only
reference) is Mai's own project code, not third-party material. If further
external code, assets, or data are adapted in the future, they must be
added to this file with the same file-by-file record before any push.
