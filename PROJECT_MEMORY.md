# Project memory — Video quality direction

Updated: 2026-11-06 (Asia/Bangkok)

## Current reference build

- Primary reviewed render: `drafts_factory/agi_premium_remotion/draft_01/draft_video.mp4`
- Format: 1080x1920, 30 fps, 54.3 seconds, H.264 + AAC.
- Main composition: `remotion-engine/src/PremiumMotion.tsx`.
- Pipeline adapter: `pipeline/premium_remotion_renderer.py`.
- Automated gate: `pipeline/production_quality.py`.

## Standing quality judgment

The current output is technically clean and readable, but not yet production-complete for strong YouTube Shorts/TikTok retention. The central illustrations are simple, mostly flat SVG loops. They repeat motion continuously instead of using purposeful action arcs tied to narration. The five scenes share nearly the same composition and timing, so the video feels like a themed slide deck rather than a developing visual story.

The existing `quality_report.json` passing result only proves structural checks (scene count, spoken text, prompt count, beat duration). It does not validate motion quality, semantic synchronization, visual variety, audio dynamics, safe zones, retention, or platform readiness.

## Non-negotiable direction for future work

1. Each visual beat must illustrate a specific spoken idea, not merely decorate the topic.
2. Use action arcs: setup -> anticipation -> primary action -> settle/hold. Avoid perpetual sine-wave movement as the main animation.
3. Introduce shot grammar and depth: macro/detail, wide/establishing, parallax camera moves, masks, foreground/background layers, and deliberate transitions.
4. Keep one hero motion per shot and reserve at least 0.4-1.0 seconds of visual rest after important reveals.
5. Replace uniform scene templates with concept-specific compositions while preserving a coherent design system.
6. Expand quality gates to cover motion diversity, repeated layouts, caption safe zones, frame holds, audio peaks/loudness, deterministic rendering, and sampled-frame visual review.
7. Use deterministic frame-based animation only; no time-based or random output without a fixed seed.

## External references already consulted

- Official Remotion repositories and examples for frame-based `spring()` / `interpolate()` patterns.
- Motion Canvas repository as a reference for generator-driven 2D animation architecture.
- Reddit motion-design and video-editing discussions emphasizing hierarchy, meaningful illustrative motion, pacing, music alignment, and the generic look of unart-directed AI motion graphics.

## Workflow decision still required

Decision made on 2026-11-06: **autonomous free creation**. Ink Press was rejected because the project is an editorial explainer factory rather than a product demo. The reusable motion-language and quality-gate redesign is documented in `docs/VIDEO_FACTORY_CREATIVE_SPEC.md`.

## Implemented improvement baseline

- `PremiumMotion.tsx` now treats each scene as establish → evidence → resolve, with anticipate → act → settle motion instead of perpetual hero loops.
- `production_quality.py` now rejects unstructured decorative plans and enforces semantic beats, a motion arc, and a minimum hold.
- The rendered file itself is inspected for 1080x1920, 30 fps, audio presence, duration, integrated loudness, true peak, and LRA.
- Latest verified reference output: `drafts_factory/agi_premium_remotion_v7/draft_01/draft_video.mp4`.
- Verified audio metrics: -14.06 LUFS integrated, -1.50 dBTP, 2.40 LU LRA.
- Automated test baseline: 9 tests passing; TypeScript compiles with no errors.
- V7 fixes the independent-review findings: Vietnamese glyph fallback, caption effective size/safe zone, semantic beat evidence, first-frame visibility, camera/visual hold before fade, and explicit separation of plan/technical/creative gates.

## Viral-system research direction

- Strategy source of truth: `docs/VIRAL_VIDEO_SYSTEM_STRATEGY_VI.md`.
- Never promise virality. Optimize measurable retention, rewatch, saves, shares, comments, and conversion.
- Select a format family before scripting; do not force every niche into the same five-scene template.
- A research brief must contain at least three sourced proof items before an authoritative explainer is rendered.
- Generate controlled hook/duration/presentation variants and learn from post-publication analytics.
