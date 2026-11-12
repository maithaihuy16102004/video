# Affiliate QA Checklist (Draft, Phase 1)

QA is split into two independent gates, like Story Studio:
**Technical QA** (measured on real files) and **Creative QA**
(human review). Only both PASS → `DRAFT_PASSED_QA`. No trustworthy
automated creative method exists here, so creative status is always
`REVIEW_REQUIRED` — never self-awarded.

Implementation: `ai_clip_studio/affiliate/qa.py`
(`run_affiliate_qa`). Each check returns `{name, passed, detail,
evidence}`. Video/OCR/export sections report `NOT_RUN` in Phase 1
(Subagent A's stages) and merge at integration.

## Translation QA

- [ ] Every original segment has a translated segment (same count,
      same order), OR the record is honestly flagged
      `needs_human_review` with no invented translations.
- [ ] Numbers preserved: every digit sequence in the original
      appears in the translation (units, model numbers, prices).
- [ ] Engine label honest: `gemini:<model>` only on a real call,
      else `fallback`.
- [ ] Style recorded (`neutral` / `humorous_viral_review`); for the
      humorous style, spot-check that jokes are in the wording, not
      in the facts.
- [ ] No added discount/urgency wording (giảm giá, số lượng có hạn…).
- [ ] Protected OCR tracks keep `replace_allowed=False`.

## Voice QA

- [ ] Every script segment has a real WAV; durations measured, none
      estimated.
- [ ] Language is Vietnamese (no English fallback, ever).
- [ ] Per-character dubbing: each speaker's segments use that
      speaker's mapped voice, consistently across the video.
- [ ] Speed within 90–110; speech never accelerated to fit.
- [ ] **Pronunciation ear-check: PENDING until a human listens.**
      Voice score is capped at 7.0 without a real pronunciation
      check (transcription + listening), per the standing QA rule.
- [ ] TTS failure stops the job (no placeholder audio).

## Subtitle QA

- [ ] ASS parses; PlayRes 1080x1920; cues cover the narration span.
- [ ] Max 2 lines per cue, one consistent font size (default 64px),
      phone-readable (≥ 3% of frame height).
- [ ] Vietnamese Unicode correct (NFC, full diacritics); font covers
      all glyphs (DejaVu Sans check).
- [ ] No cue overlaps a restricted safe-zone area; no cue outside
      the frame.
- [ ] Word highlight (`\kf`) only when real ASR word timings exist.
- [ ] SRT sidecar matches the ASS cues.
- [ ] Safe-zone guides are preview-only, never burned in.

## Audio QA (measured on real files)

- [ ] Mix exists; duration equals the timeline length.
- [ ] No clipping (max volume < −0.5 dB).
- [ ] Voice above music: effective bus levels (stem mean + mix gain)
      differ by ≥ 6 dB in favor of voice.
- [ ] Smooth fades: fade-in window quieter than the window after it;
      fade-out window quieter than the window before it.
- [ ] Music authorized or absent; SFX restrained.
- [ ] Final narration line present (no cut-off); no truncated speech.

## Commercial-content QA

- [ ] Export gate passes: authorization confirmed (not UNKNOWN),
      rights flag set, script approved, mirror/protected edits
      approved, music authorized.
- [ ] Disclosure present when an affiliate link is present.
- [ ] No fabricated testimonials (first-person testing wording
      flagged unless explicitly confirmed).
- [ ] No invented prices/claims/discounts/links (claim tripwire
      clean, or findings reviewed by a human).
- [ ] Marketing package: `facts_source = user_input_only`; source
      warning present when authorization is unconfirmed; no sales
      promises; `auto_publish = false`.

## Video / export QA (Subagent A — NOT_RUN in Phase 1)

- [ ] Exactly 1080x1920, profile fps, has audio.
- [ ] No black bars; no stretched/squashed framing.
- [ ] Chinese text regions blurred; Vietnamese subtitles overlaid
      (blur-then-overlay); protected tracks intact.
- [ ] Mirror (if enabled): approved, labels/logos checked.
- [ ] CRF 17–19; file plays end-to-end.

## Creative QA (human — always REVIEW_REQUIRED in Phase 1)

- [ ] Watch the full video: does the dubbing match the characters?
- [ ] Is the humorous wording actually funny without changing facts?
- [ ] Do subtitles read well on a phone? Any overlap with platform UI?
- [ ] Is the pacing watchable? Any awkward silence or rush?
- [ ] Human verdict recorded before any Master/export approval.

## Verdicts

| Verdict | Meaning |
|---|---|
| `DRAFT_PASSED_QA` | Technical PASS **and** Creative PASS (human) |
| `TECHNICAL_PASS / CREATIVE_REVIEW_REQUIRED` | Technical checks pass; human review pending |
| `QA_FAILED` | Any technical check failed — fix and re-render (real loop) |
| `NOT_RUN` | Section has no stage output yet (Phase 1 video/OCR/export) |
