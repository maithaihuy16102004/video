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

```
overall 90.43  passed False     # fails the per-dimension floor
format           91.67   10 s clip is inside the short-form band, not the 20-60 s band
pacing           96.67   shots 3.04 / 3.00 / 3.04 s — all in band
cut_grammar     100.00   2/2 boundaries are hard cuts
motion           77.82   per-shot mean diff 0.13 / 0.27 / 0.72 — below the 0.35 floor
lighting         83.33   shot 0 luma 0.352 < 0.38
framing_variety 100.00   establishing → medium → close_up, no repeats
captions          null   plan carries no caption metrics
characters        null   plan carries no character boxes
```

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
| T1 | **Make every shot move.** Add an idle layer (breath, blink, weight shift, cloth/prop settle) and a slow camera drift for framing that has no action; a static establishing shot is the single biggest parity gap. | per-shot mean diff 0.13 / 0.27 / 0.72 vs floor 0.35 | `motion ≥ 85` and no frozen span before the final second |
| T2 | **Lift the dark shot over the luma floor.** Apply the style-B exposure (1.45) and the 0.38 action-zone floor to the interior/workshop palette instead of leaving shot 0 at 0.352. | shot 0 luma 0.352 | `lighting ≥ 85` |
| T3 | **Emit character boxes into the plan.** The renderer already computes standing boxes for crop anchoring; write `characters[]` (`name`, `head_ratio`, `bbox`) per shot so the `characters` dimension becomes measurable. | `characters: null` | dimension has a score |
| T4 | **Emit caption metrics into the plan.** Font px, line count, max chars, y fraction per caption block. | `captions: null` | dimension has a score |
| T5 | **Close-up framing must not crop the head.** `shot_002_mid.png` cuts the top of the head at the frame edge; the planner pairs `close_up` with a standing anchor that puts the head above the safe area. | still frame, job dir | `characters` shot with a close-up is compliant |
| T6 | **Decide the reference-repo integration.** `Flaxa-Technologies/ricks-clips-nextjs-studio` is a *motion-graphics* studio (transitions, odometers, maps), not a character-animation engine: it cannot supply characters, rigs or shot grammar for this pipeline. Its `src/lib/kinematics.ts` (closed-form spring ODE, Newton-Raphson bezier, arc-length splines) is the only directly reusable idea, and the repo ships **no LICENSE file**, so nothing may be copied. `claude-animated-shorts` (MIT) is already adapted and recorded in `THIRD_PARTY_NOTICES.md`. | repo audit | a written decision: port the easing math as new code, or skip |
| T7 | **Format band.** A 10 s acceptance clip cannot score the 20–60 s band; either render a 20–40 s acceptance episode or make the band depend on the declared format. | `format 91.67` | deliberate choice recorded |
| T8 | **3D character parity is out of this engine's reach.** Ricks Clips switched to a 3D cartoon look; a 2D stickman engine can match camera grammar, pacing, captions and composition, not the character render. The 3D path exists in `ai_clip_studio/motioncanvas25d/` (Three.js + Playwright) but its `node_modules` are not installed and the reference job ("014") is not in this worktree. | channel study | an explicit scope decision, not a silent gap |

## Rules

- Never move the target to make a render pass. If a target is wrong, the
  fix is argued here first and the change is recorded above.
- A dimension with `null` is a missing measurement, never a free pass.
- No channel artwork, characters, scripts or branding; techniques and
  measured values only (`THIRD_PARTY_NOTICES.md`, decision D4).
