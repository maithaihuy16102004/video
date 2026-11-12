# Affiliate Export Profiles (Draft, Phase 1)

Export is executed by Subagent A's render stage. This document
records the profiles the schema + API expose, so the render stage,
QA, and the frontend agree on the same targets. Phase 1 does not
render; the export endpoint returns 501 (after the 403 gate) until
the render stage lands at integration.

## Profiles

| Preset | Resolution | Aspect | FPS | Container | Video | Audio |
|---|---|---|---|---|---|---|
| `TIKTOK_VERTICAL` | 1080x1920 | 9:16 | 30 | mp4 | H.264, CRF 17–19, yuv420p | AAC 192k, 48 kHz stereo |
| `FACEBOOK_REELS_VERTICAL` | 1080x1920 | 9:16 | 30 | mp4 | H.264, CRF 17–19, yuv420p | AAC 192k, 48 kHz stereo |

Rules:

- **9:16 is its own framing**, produced by the reframe/transform
  stage from the source — never a center-crop of a 16:9 render.
- **CRF 17–19** (constant quality). No fixed-bitrate ladder in
  Phase 1; `video_bitrate` in the profile is informational only.
- **Burned-in subtitles**: the ASS file from the subtitle engine is
  burned with the `subtitles` filter (`captions.burn_filter_args`).
  Safe-zone guides are preview-only and are **never** burned in.
- **SRT sidecar** is always written next to the MP4.
- **Audio** is the mixed stem from the audio timeline (voice +
  original + music + SFX, ducked, faded). The mix length equals the
  timeline length exactly; speech is never truncated or accelerated.
- **No black bars**: the frame is exactly 1080x1920. Letterbox /
  pillarbox output is a hard QA failure.
- **Blur-then-overlay** (Douyin requirement): Chinese on-screen text
  regions are blurred by the edit stage and Vietnamese subtitles are
  overlaid on top. Protected tracks (labels/logos/attribution/
  watermarks) are never blurred/removed without explicit approval.

## EXPORT_PROFILE schema fields

| Field | Type | Notes |
|---|---|---|
| `preset` | enum | `TIKTOK_VERTICAL` / `FACEBOOK_REELS_VERTICAL` |
| `resolution` | string | `1080x1920` |
| `fps` | number | 30 |
| `crf` | int | 17–19 (validated AFF014 outside this range) |
| `video_bitrate` | string | Informational, e.g. `8M` |
| `audio_bitrate` | string | e.g. `192k` |
| `format` | string | `mp4` |

## Batch export

Batch is a list of projects sharing one profile; each project keeps
its own authorization gate. A project whose gate refuses is skipped
with its reasons recorded — batch export never overrides the gate.
(Batch orchestration lands at integration; the schema already carries
per-project profiles.)

## QA on export (see AFFILIATE_QA_CHECKLIST.md)

- ffprobe: exactly 1080x1920, fps as profiled, has audio stream.
- Duration matches the audio timeline within tolerance; final
  narration line present (no cut-off).
- No black bars (frame sampling at edges).
- Subtitles legible on a phone-sized preview; no safe-zone overlap.
- Loudness: no clipping (max volume < −0.5 dB), voice above music.
- Export gate passed (authorization + approvals) — recorded in QA.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Export returns 403 | Gate refused | Read `reasons`; confirm authorization / approve script / approve edits |
| Export returns 501 | Render stage not wired yet | Phase 1 limitation; lands at integration |
| Black bars in preview | Wrong reframe | Reframe stage must fill 1080x1920; report to the CV owner |
| Subtitles overlap UI buttons | Safe-zone profile mismatch | Check `safe_zone_profile` matches the target platform |
| Audio ends early | Mix shorter than timeline | Mix must be padded to the timeline length (apad + `-t`) |
| Final line cut off | Timeline built from estimates | Timeline must use measured TTS durations only |
