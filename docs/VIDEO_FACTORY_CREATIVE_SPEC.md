# Video Factory creative specification

Mode: autonomous free creation  
Format: research-to-draft editorial explainer, 1080x1920, Vietnamese narration  
Primary platforms: YouTube Shorts and TikTok

## Product brief

The product is not one fixed video. It is a reusable local factory that turns GPT niche research and content research into a reviewable draft. The draft must explain, not merely decorate, and must remain deterministic and cheap enough to render repeatedly.

## Chosen direction

**Layered editorial documentary**: bold editorial type, dark restrained surfaces, concept-specific diagrams, controlled depth, and meaningful camera emphasis. Motion voice: intelligent, urgent, composed.

Energy: medium-high. Tone: serious but accessible. Primary entrance: 22–30 frames with strong deceleration. Overshoot: 1.02 maximum. Hero action: 45–75 frames. Settle/hold: 18–30 frames. Decorative perpetual loops may exist only as low-amplitude background texture.

## Design tokens

- Background: `#07101D`; ink: `#F4F8FF`; muted: `rgba(244,248,255,.62)`.
- Accent is scene-semantic and limited to one dominant hue per scene.
- Font: Arial 700 for headlines, 400/500 for supporting copy. This local render baseline is intentionally chosen for complete Vietnamese glyph coverage; a bundled Vietnamese-capable brand font may replace it later.
- Depth layers: atmosphere, grid/world, hero concept, evidence/detail, captions.
- Camera scale range: 1.00–1.08; no handheld shake.
- Captions live above the TikTok bottom interaction zone and below the hero visual.

## Research-to-execution decisions

| Input | Execution rule |
|---|---|
| GPT niche research | Extract one tension and one concrete claim for the hook. |
| GPT content research | Every scene gets establish, evidence, and resolve beats. |
| Narration | Visual changes follow semantic clauses, not equal time slices alone. |
| Missing assets | Use deterministic concept diagrams; never insert unrelated stock merely for movement. |
| Draft status | Prefer clarity and editability over expensive generative footage. |
| Platform | First meaningful visual in <0.5s; readable at phone size; reserve UI safe zones. |

## Storyboard grammar

| # | Time | Shot | Key motion |
|---|---|---|---|
| 1 | 0–18% | Establish | Headline locks; hero concept anticipates. |
| 2 | 18–72% | Evidence | Diagram performs one semantic action; camera moves to detail. |
| 3 | 72–100% | Resolve | Evidence resolves into a clear final state; 0.6–1.0s hold. |

Each full video alternates wide, detail, and wide resolution views. A visual language may lead only one scene unless the topic genuinely requires repetition.

## Production approval

Approved autonomously on 2026-11-06. Ink Press was rejected because this is a reusable editorial explainer factory, not a product showcase. The implementation will extend the existing PremiumMotion architecture and quality gates rather than reskin a one-off template.
