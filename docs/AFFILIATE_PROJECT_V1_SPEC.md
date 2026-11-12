# AFFILIATE_PROJECT_V1 — Schema Specification (Draft, Phase 1)

Machine-readable schema:
`ai_clip_studio/affiliate/affiliate_project_v1.schema.json`
(JSON Schema draft 2020-12). Python implementation:
`ai_clip_studio/affiliate/schema.py` (dataclasses + `validate_project`
+ `parse_project` + `project_snapshot_hash` + `export_allowed`).

This schema is **separate** from STUDIO SCRIPT V1. It shares only
infrastructure and artifact conventions with Story Studio. Do not
modify `studio_script_v1.py` or its docs for affiliate work.

## Top-level structure

| Section | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Must be `AFFILIATE_PROJECT_V1` |
| `project_id` | yes | `aff_` + 12 hex chars (store-generated) |
| `project_name` | no | Human name |
| `source_video` | no | `SOURCE_VIDEO` record (see below) |
| `authorization` | no | `SOURCE_AUTHORIZATION` (see below) |
| `product` | yes | `PRODUCT` (see below) |
| `video_analysis` | no | Scenes/faces/hands/motion (Subagent A) |
| `ocr_tracks` | no | OCR text tracks (Subagent A) |
| `translation` | no | `TRANSLATION` record |
| `script` | no | `SCRIPT` record |
| `voice` | no | `VOICE` config |
| `edit_operations` | no | Edit ops (Subagent A executes) |
| `subtitle_style` | no | `SUBTITLE_STYLE` |
| `audio_mix` | no | `AUDIO_MIX` |
| `export_profile` | no | `EXPORT_PROFILE` |
| `stages` | no | 16-stage status records (store-managed) |
| `qa` | no | QA report (see QA checklist doc) |
| `output` | no | Export outputs (filled at export) |
| `created_at` | no | ISO timestamp |

## SOURCE_VIDEO

| Field | Type | Notes |
|---|---|---|
| `file_name` | string, required | Original file name |
| `file_size_bytes` | int ≥ 0 | |
| `resolution` | string | e.g. `1080x1920` |
| `fps` | number | |
| `duration_sec` | number ≥ 0 | |
| `video_codec` / `audio_codec` | string | |
| `aspect_ratio` | string | e.g. `9:16` |
| `orientation` | string | `vertical` / `horizontal` / `square` |
| `has_audio` | bool | |
| `container` | string | `mp4` / `mov` / `mkv` / `webm` |
| `sha256` | string | 64-char lowercase hex of the immutable stored copy |
| `stored_path` | string | Server-side path of the stored copy |
| `source_url` | string | **Provenance only.** Original share/source link, if any. Must be http/https when present (AFF004). The module **never fetches** this URL. A link-only record (`file_name` = `(link only — no file uploaded)`, no checksum) cannot pass the export gate. |

## SOURCE_AUTHORIZATION

| Field | Type | Notes |
|---|---|---|
| `authorization_type` | enum, required | `USER_OWNED` / `LICENSED` / `SELLER_AUTHORIZED` / `UNKNOWN` |
| `commercial_rights_confirmed` | bool | User confirmation flag; required for export |
| `rights_note` | string | Licence / permission detail |
| `confirmed_by` / `confirmed_at` | string | Who confirmed, ISO timestamp |

**Export gate** (`export_allowed`): export is REFUSED when the
authorization is `UNKNOWN` (AFF008), the confirmation flag is missing
(AFF009), the source checksum is missing (AFF018), the script is
unapproved (AFF017), a mirror/protected-track edit lacks approval
(AFF020/AFF021), or background music lacks authorization. The export
endpoint enforces the gate with HTTP 403 before the render stage.

The confirmed value for the Douyin test job is `SELLER_AUTHORIZED`
with `commercial_rights_confirmed = true` (Mai's confirmation,
2026-11-12 09:34).

## PRODUCT

Fields: `product_name` (required), `product_category`,
`shopee_product_url`, `affiliate_url`, `product_price`,
`product_features[]`, `product_benefits[]`, `target_audience`,
`call_to_action`, `brand_name`, `brand_color`, `product_images[]`,
`seller_information`, `disclosure_text`,
`personally_tested_confirmed` (bool).

Rules (enforced by `product.py`, not by the schema alone):

- Missing info → neutral wording from visible demo + user facts only.
- Never invent prices, discounts, certifications, medical benefits,
  performance claims, testimonials, or links.
- An affiliate link without a disclosure is flagged (AFF019); the
  default disclosure template is applied when a link is present.
- First-person testing wording is flagged unless
  `personally_tested_confirmed` is true.

## TRANSLATION

| Field | Type | Notes |
|---|---|---|
| `mode` | enum | `DIRECT_TRANSLATION` / `NATURAL_LOCALIZATION` / `AFFILIATE_COPYWRITING` |
| `style` | enum | `neutral` / `humorous_viral_review` (Douyin requirement: humorous viral review-style wording, faithful facts) |
| `engine` | string | `gemini:<model>` or `fallback` |
| `engine_detail` | string | |
| `original_segments[]` | {start, end, text, speaker_id} | Untouchable source record |
| `translated_segments[]` | same shape | Gemini/fallback translation (DIRECT/NATURAL) |
| `rewritten_segments[]` | same shape | Affiliate rewrite (COPYWRITING mode) |
| `needs_human_review` | bool | |
| `review_notes[]` | string | |

Original / translated / rewritten are **separate records** — never
merged. `speaker_id` is preserved through translation for dubbing.
Without a Gemini key, DIRECT/NATURAL produce **no** translated
segments and set `needs_human_review` (the fallback never invents
translations); COPYWRITING fallback builds copy from verified facts
only.

## SCRIPT

| Field | Type | Notes |
|---|---|---|
| `variant` | enum | `natural_review` / `demonstration` / `problem_solution` / `dubbed_translation` |
| `target_seconds` | number | 15/30/45/60 preset or audio-driven custom |
| `segments[]` | `SCRIPT_SEGMENT` | |
| `engine` / `engine_detail` | string | Labelling |
| `approved` / `approved_by` / `approved_at` / `approval_note` | | Approval record |

`SCRIPT_SEGMENT`: `segment_id`, `section` (HOOK / PROBLEM /
PRODUCT_INTRODUCTION / DEMONSTRATION / BENEFITS / CALL_TO_ACTION),
`text`, `speaker_id` ("" = default voice; otherwise per-character
dubbing), `start_time` / `end_time` (timeline-filled),
`estimated_sec`, `voice_wav`, `measured_sec`.

`dubbed_translation` scripts are built 1:1 from translated segments
(`script_from_translation`), preserving timing windows and speaker
labels. Any edit clears approval (`clear_approval_on_edit`); TTS and
export require approval.

## VOICE

| Field | Type | Notes |
|---|---|---|
| `voice_id` | string | Real provider voice id (must be offered) |
| `voice_gender` | string | `female` / `male` / "" |
| `voice_region` | string | Provider default (not exposed by the CLI) |
| `voice_speed` | int | 90–110 enforced (100 = 1.00x) |
| `voice_style` | string | Descriptive metadata |
| `preset` | string | Preset name from `voice.py` |
| `pause_after_sec` | number | Default 0.5 |
| `pronunciation_dictionary` | object | Literal text replacements |
| `speaker_voices` | object | **speaker_id → preset name**, per-character dubbing (data-driven). Preset existence is validated in `voice.py`. |

## EDIT_OPERATIONS / SUBTITLE_STYLE / AUDIO_MIX / EXPORT_PROFILE

- `EDIT_OPERATION`: `operation` (enum incl. `hflip`, `text_blur`,
  `text_inpaint`, `text_crop`, trim/crop/speed ops), `parameters`,
  `target_track_id`, `approved`. Protected OCR classes
  (`PRODUCT_LABEL`, `BRAND_LOGO`, `CREATOR_ATTRIBUTION`, `WATERMARK`)
  need approval for removal ops (AFF020). `hflip` needs the
  label/logo warning review + approval (AFF021, mirror defaults OFF).
  The Douyin blur-then-overlay flow uses `text_blur` on `SUBTITLE` /
  `PROMOTIONAL_OVERLAY` tracks.
- `SUBTITLE_STYLE`: font (DejaVu Sans), `font_size` 16–160 (default
  64), colors `#RRGGBB`, `outline_color`, `background_color` +
  `background_opacity`, `position_y`, `max_lines` 1–4, `max_chars_per_line`
  10–80, `highlight_color`, `word_highlight`, `safe_zone_profile`
  (`TIKTOK_VERTICAL` / `FACEBOOK_REELS_VERTICAL`).
- `AUDIO_MIX`: `mode` (`REPLACE_ALL` / `KEEP_PRODUCT_SOUNDS` /
  `DUCK_ORIGINAL_AUDIO` / `CUSTOM_MIX`), `bus_gains_db` (voice /
  original / music / sfx), `music_path`, `music_authorized` (music
  without authorization is refused), `ducking_db`.
- `EXPORT_PROFILE`: `preset` (`TIKTOK_VERTICAL` /
  `FACEBOOK_REELS_VERTICAL`), `resolution` (1080x1920), `fps`,
  `crf` 17–19, `video_bitrate`, `audio_bitrate`, `format`. See
  `AFFILIATE_EXPORT_PROFILES.md`.

## Validation errors (AFF001–AFF024)

Stable, field-pathed codes; see the module docstring in `schema.py`
for the full list. Gate-level codes (AFF008, AFF009, AFF017, AFF020,
AFF021) describe legitimate intermediate states: they are reported by
`validate_project` and enforced by the gates, but they do **not**
block `parse_project` — otherwise a project with unconfirmed
authorization could never be reloaded.

## Snapshot hash

`project_snapshot_hash` is a SHA-256 over the canonical project dict
excluding `stages`, `qa`, `output`, and `created_at`, so the content
hash is stable across stage transitions and sensitive to any content
edit (used for the immutable script snapshot rule).

## Example (minimal, valid)

```json
{
  "schema_version": "AFFILIATE_PROJECT_V1",
  "project_id": "aff_0123456789ab",
  "project_name": "hop-dung-do-01",
  "product": {"product_name": "Hộp đựng đồ nhà bếp"},
  "authorization": {
    "authorization_type": "SELLER_AUTHORIZED",
    "commercial_rights_confirmed": true,
    "rights_note": "Người bán đã cho phép mình dùng"
  },
  "source_video": {
    "file_name": "demo.mp4",
    "file_size_bytes": 123456,
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "source_url": "https://example.com/share/video/123"
  }
}
```
