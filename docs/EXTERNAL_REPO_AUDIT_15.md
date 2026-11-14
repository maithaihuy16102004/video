# External repo audit — the 15-repo list (2026-11-14)

Question asked: do any of these 15 repos need to be added to the
pipeline to reach the 90% Ricks-Clips parity target in
`docs/RICKS_PARITY_90.md`?

**Answer: no. No dependency is added.** Each repo below was checked
against the three standing criteria — license usable here, fits a
Windows/local Python pipeline, and a *measured* improvement to a parity
dimension. Nothing cleared all three. This file records the decision so
it is not re-litigated, following the convention in
`THIRD_PARTY_NOTICES.md` (decision D4: techniques and measured values
only, never artwork, characters, scripts or branding).

## Verdicts

| # | Repo | What it actually is | License | Decision |
|---|---|---|---|---|
| 1 | `JuneYaooo/rea-video` | Python package + agent skill that reverse-engineers any video shot by shot into a `VIDEO.md` breakdown (filmed / AI / coded, camera notes, audio) | Apache-2.0 (verified) | **Not now.** Genuinely the closest fit to our loop, but it consumes the reference video itself: this project is barred from using the channel's frames or scripts (D4). It could later audit *our own* renders, and `ricks_parity.py` already measures those from pixels. |
| 2 | `yihui-dev/awesome-opus5-5-videos` | A curated list of code-generated videos and prompts | n/a (list) | No code to integrate. |
| 3 | `lemomo-ai/lemo-opuscar` | 99 "film styles" as prompt + demo code, for Claude Code | Code MIT, assets per-file (verified) | No. Our style is a numeric target set (luma, cut band, head ratio) already encoded in `look_targets.py` and the parity targets; prose styles would add a second, conflicting source of truth. |
| 4 | `storytold/effectcraft` | Pure-Rust After Effects alternative: GUI compositor, 259–308 effects, keyframes, Lottie, MCP server | MIT OR Apache-2.0 (verified) | No. It is an application, not a library; self-rated ~45% pro-ready and alpha. Embedding an alpha GUI compositor into a deterministic Python render path is risk with no measured gain. |
| 5 | `heygen-com/hyperframes` | HTML/CSS → deterministic MP4 via headless Chrome + FFmpeg; local CLI, agent skills; Windows supported | Apache-2.0 (verified) | **No, but the only credible fallback backend.** We already render the same way through `motioncanvas25d/` (puppeteer-core + three.js + FFmpeg). Adopt only if we need HTML/CSS-authored inserts, and only with a before/after score. |
| 6 | `patch…/pixelfx` | Pixel-art VFX library + sprite sheets | not verified | No. Wrong visual style for this engine. |
| 7 | `remotion-dev/remotion` | React-based video renderer | Remotion license (source-available, company license above a size threshold) | Already rejected earlier; `remotion-engine/` exists but is not the production path. |
| 8 | `remotion-dev/skills` | Agent instructions for Remotion | follows Remotion | No (depends on #7). |
| 9 | `ahuja…/blender-mcp` | MCP bridge that lets an agent drive Blender | not verified | No. Requires Blender + a live 3D scene; our 3D path is three.js in Chrome, and nothing in the parity backlog is blocked on Blender. |
| 10 | `mrdoob/three.js` | 3D web library | MIT | **Already a dependency** (`three@^0.170.0` in the root and `motioncanvas25d` package.json). |
| 11 | `greensock/GSAP` | JS animation library | GreenSock standard license (free with conditions) | No. Animation is authored in Python and baked into frames; there is no browser timeline to drive. |
| 12 | `ComfyUI` | Node-based generative image/video workflow UI | GPL-3.0 | No. The project directive forbids AI-generated video, and diffusion output is not reproducible frame-for-frame. |
| 13 | `heyda…/unslop` | Agent skill that reviews UI for "AI-generated" look | not verified | No. Frontend design skill, not video. |
| 14 | `pbakaus/impeccable` | Design guidance set for agents | not verified | No. Same reason as #13. |
| 15 | (remaining list entries) | Collections/pointers | n/a | No. |

## What this means for the parity backlog

Nothing on the list closes T3 (character boxes), T4 (caption metrics)
or T5 (close-up head crop): those are our own renderer emitting data it
already computes, and a camera pairing fix. T8 (the 3D character look)
is a scope decision, not a dependency problem — `three.js` is already
installed in the 3D path.

The rule stays: a dependency enters only with a measured before/after on
`python -m ai_clip_studio.ricks_parity`, and a license line recorded in
`THIRD_PARTY_NOTICES.md` first.
