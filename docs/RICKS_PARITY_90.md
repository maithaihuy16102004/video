# 90% Ricks-Clips parity — scorecard and task backlog

Reference: [@RicksClips3000](https://www.youtube.com/@RicksClips3000/shorts).
Target: **overall ≥ 90.0 and no measured dimension below 85.0**.

"Giống 90%" is a number a render can fail, not an opinion. Every
dimension below is measured from the decoded MP4 (or from the shot plan
the renderer emits); nothing is self-reported. A dimension that cannot
be measured is reported as `null` and is **excluded** from the mean — it
never counts as a pass.

## How to run

```bash
# 1. render an acceptance clip (job script writes frames + plan.json)
PYTHONPATH=. python jobs/acceptance_species_clip/render_clip.py

# 2. score it
python -m ai_clip_studio.ricks_parity \
  jobs/acceptance_species_clip/species_acceptance.mp4 \
  --plan jobs/acceptance_species_clip/plan.json \
  --json-out jobs/parity/baseline.json
# exit 0 = pass (≥90 overall, nothing below 85), exit 1 = still short
```

Unit tests for the scorecard itself: `python -m unittest ai_clip_studio.tests.test_ricks_parity`

## Dimensions, weights and targets

| Dimension | Weight | Measured from | Target |
|---|---:|---|---|
| `format` | 0.10 | ffprobe | 1920×1080, 24–30 fps, 20–60 s |
| `pacing` | 0.22 | shot durations | every shot 3.0–6.5 s, ideal 4.5 s |
| `cut_grammar` | 0.10 | frame-diff spikes | hard cuts only, shot count ≈ duration/4.5 |
| `motion` | 0.18 | per-shot mean \|Δframe\| | ≥0.35 and ≤18, no frozen span outside the final 1 s hold |
| `lighting` | 0.16 | per-shot luma/contrast | luma ≥0.38, contrast ≥0.06, no black frames |
| `framing_variety` | 0.10 | plan framings | every shot a distinct framing, no adjacent repeats |
| `captions` | 0.07 | plan caption metrics | ≥64 px at 1080p, ≤2 lines, ≤42 chars, lower third |
| `characters` | 0.07 | plan character boxes | head ratio 0.34 ±0.06, inside the 84% safe action area |

Targets come from the channel study already encoded in
`youtube_16x9/config/youtube_16x9.json` and
`docs/CINEMATIC_ENGINE_CONTRACTS.md` (D2 hard cuts, D3 head ratio).
No channel artwork, characters or scripts are used.

## Baseline (2026-11-14, `species_acceptance.mp4`)

After T1 + T2 (executed micro-dolly + exposure floor) and T3 + T4
(renderer-reported boxes and caption metrics) — **all eight dimensions
measured**:

```
overall 98.06  passed True
format           91.67   10 s clip sits inside the short-form band, not 20-60 s (T7)
pacing           96.67   shots 3.04 / 3.00 / 3.04 s — all in band
cut_grammar     100.00   2/2 boundaries are hard cuts
motion           97.92   every shot moves
lighting        100.00   one exposure gain per shot, no shot below 0.40
framing_variety 100.00   establishing → medium → close_up, no repeats
captions        100.00   64 px, 1 line, ≤39 chars, y 0.88 inside the safe-title line
characters      100.00   3/3 shots: head ratio 0.34, head inside the action area
```

History on the same project: **78.49** (first honest measure, before four
checker bugs were fixed) → **90.43 `passed False`** (motion 77.82,
lighting 83.33) → **97.86** after T1/T2 → **98.06** after T3/T4 with all
eight dimensions measured.

The high overall number is **not** a pass: the gate is
`overall ≥ 90 AND every measured dimension ≥ 85`, and motion plus
lighting are below it. Two of the eight dimensions cannot be measured
yet, which is itself a task (T3, T4).

## Measurement bugs found and fixed while building this

These were defects in the *checker*, not the render; fixing them changed
the baseline from 78.49 to 90.43 on the same pixels:

1. **Muxing duplicated frames** — concat with `-fps_mode vfr` produced
   251 encoded frames from a 239-frame render, which diluted motion and
   created a phantom frozen tail. The job script now muxes
   `-r 24 -fps_mode cfr`.
2. **Cut detection trusted plan frame offsets** — a boundary moved by the
   encoder was scored as a fade. Shots are now detected from pixels; the
   plan only labels them, and only when the counts agree.
3. **Shot-count target was absolute** (`min 4 cuts`) — a correct 10 s
   three-shot clip was penalised. The expected count is now
   `ceil(duration / 4.5)`.
4. **The intentional final hold was scored as frozen** — the last ≤1 s is
   now excluded from frozen-span counting, as the channel ends on a hold.

## Task backlog (do in order, re-score after each)

| # | Task | Evidence | Done when |
|---|---|---|---|
| ~~T1~~ ✅ | **Make every shot move.** DONE: `apply_micro_dolly` executes `DOLLY_IN`/`DOLLY_OUT`/`PAN_LEFT`/`PAN_RIGHT` as an image-level micro move (reported as executed, not as a limitation), and a shot with no action events gets a gentle auto push-in recorded as `camera_auto_drift`. Character idle amplitudes were left alone: `idle()` alone changed too little per frame to read. | was 0.13 / 0.27 / 0.72 vs floor 0.35 | **motion 98.50** |
| ~~T2~~ ✅ | **Lift the dark shot over the luma floor.** DONE: `apply_exposure_floor` applies a capped linear gain (≤1.45) when a finished frame sits below 0.40 — the reference floor plus headroom, because the lift is computed pre-encode with captions drawn last. | was shot 0 luma 0.352 | **lighting 100.00** |
| ~~T3~~ ✅ | **Emit character boxes into the plan.** DONE: `_render_shot` reports `character_boxes` in FINAL frame coordinates by mapping the standing box through the same frozen crop + dolly rects the frames went through, plus `in_frame` and the diameter head ratio (`2*head_r/H`). | was `characters: null` | **characters 100.00** |
| ~~T4~~ ✅ | **Emit caption metrics into the plan.** DONE: `subtitles.caption_metrics` computes font px / lines / longest line / y fraction from the SAME wrapping `draw_phrase` uses; the renderer reports one entry per phrase. | was `captions: null` | **captions 100.00** |
| ~~T5~~ ✅ | **Close-up must not crop the head.** DONE, and the measurement says the earlier read was wrong: the close-up's reported head top is 178 px, well inside the 86 px action margin. What actually needed fixing was the checker counting characters pushed out of shot (see the review below), not the framing. | measured head top 178 px vs 86 px safe line | close-up shot compliant, `characters` 100 |
| T6 | **Decide the reference-repo integration.** Audited 15 shared repos on 2026-11-14 — none clears the license/fit/measured-gain bar, nothing added: see `docs/EXTERNAL_REPO_AUDIT_15.md`. `Flaxa-Technologies/ricks-clips-nextjs-studio` is a *motion-graphics* studio (transitions, odometers, maps), not a character-animation engine: it cannot supply characters, rigs or shot grammar for this pipeline. Its `src/lib/kinematics.ts` (closed-form spring ODE, Newton-Raphson bezier, arc-length splines) is the only directly reusable idea, and the repo ships **no LICENSE file**, so nothing may be copied. `claude-animated-shorts` (MIT) is already adapted and recorded in `THIRD_PARTY_NOTICES.md`. | repo audit | a written decision: port the easing math as new code, or skip |
| T7 | **Format band.** A 10 s acceptance clip cannot score the 20–60 s band; either render a 20–40 s acceptance episode or make the band depend on the declared format. | `format 91.67` | deliberate choice recorded |
| T8 | **3D character parity is out of this engine's reach.** Ricks Clips switched to a 3D cartoon look; a 2D stickman engine can match camera grammar, pacing, captions and composition, not the character render. The 3D path exists in `ai_clip_studio/motioncanvas25d/` (Three.js + Playwright) but its `node_modules` are not installed and the reference job ("014") is not in this worktree. | channel study | an explicit scope decision, not a silent gap |

## System review (2026-11-14, after T1–T4)

Reviewing the changes rather than only the scores found four defects, all
in the *reporting/measurement* layer added for parity, all fixed:

1. **Head ratio was reported at half its true value.** `head_r / H` is a
   radius ratio; the 0.34 identity lock is a *diameter* ratio (`2*head_r/H`).
   The dimension scored 0 on correct art because of a units bug.
2. **Characters pushed out of shot were counted as safe-area failures.**
   A close-up sending the rest of the cast off-frame is correct framing;
   the renderer now reports `in_frame` and the scorer only judges the
   characters that are actually on screen.
3. **The safe-area check tested the whole body.** A tight shot cuts the
   body at the bottom by design, so only the head's top edge and the
   subject's horizontal centre are checked now.
4. **Captions sat below the safe-title line.** The block's bottom was
   pinned at `height - 40` (y 0.927 for one line), outside the inner 80%
   the project's own `youtube_16x9.json` requires. It is now pinned to
   0.88 of the frame height, computed once in `subtitles._caption_y0` so
   drawing and metrics cannot drift apart.
5. **Exposure was re-measured every frame.** The gain followed the moving
   characters, which reads as a slow flicker. It is now measured once on
   the shot's first finished frame and applied as a constant.

Regression at that point: 280 tests across 15 modules OK (with the
known Windows font path patched in), plus a fresh render and re-score.

## Rules

- Never move the target to make a render pass. If a target is wrong, the
  fix is argued here first and the change is recorded above.
- A dimension with `null` is a missing measurement, never a free pass.
- No channel artwork, characters, scripts or branding; techniques and
  measured values only (`THIRD_PARTY_NOTICES.md`, decision D4).
