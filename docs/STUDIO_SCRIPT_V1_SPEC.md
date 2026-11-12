# STUDIO SCRIPT V1 — Specification

**Version:** V1
**Date:** 2026-11-12
**Status:** Single source of truth for script input to AI Clip Studio.
This document defines the STUDIO SCRIPT V1 text format: its grammar,
defaults, enums, validation rules, snapshot rule, and the semantics that
every consumer (parser, frontend, planner, TTS, animation, audio, renderer,
QA) MUST honour. The machine-readable schema that mirrors this specification
is `docs/studio_script_v1.schema.json` (owned by the parser stream, §13).
The reusable blank template is `docs/STUDIO_SCRIPT_V1_TEMPLATE.md`.
The validation fixture is `examples/hitler_ep01.studio.md` (§3.5).

This specification derives from the standing directive in
`docs/DIRECTIVE_STUDIO_SCRIPT_V1.md` (Mai, 2026-11-12, "đặc biệt ghi nhớ").
In case of any conflict between this specification and any other document
about script input, this specification wins. Do not introduce a second,
conflicting script format.

> **HEAD-RATIO LOCK (Mai-approved, non-negotiable).** The character head
> ratio standard is **0.34**, valid range **0.33–0.35 inclusive**
> (`HEAD_RATIO`, §5.1). The upstream V5.1 parser default of **0.42 is NOT
> valid** in STUDIO SCRIPT V1: a `HEAD_RATIO` of 0.42, or any value outside
> 0.33–0.35, is a validation error (V1E009, §8). No consumer may fall back
> to 0.42. When `HEAD_RATIO` is omitted, the default is 0.34.

## Contents

1. Purpose and design principles
2. Document structure and line model
3. Format detection and backward compatibility
4. Header schema
5. Blocks (CHARACTER, LOCATION, PROP, SCENE, SHOT, GLOBAL_AUDIO,
   GLOBAL_NEGATIVE_CONSTRAINTS, QA, OUTPUT, END_CARD)
6. Content lines
7. LINE_ID rules and spoken-text integrity
8. Validation rules, error codes, and unsupported-field policy
9. Snapshot and SHA-256 integrity
10. Audio bus model, SFX NONE semantics, and the no-invented-sound rule
11. LOCATION semantics
12. CHARACTER semantics
13. Machine-readable schema reference
14. Versioning and changelog
15. Planner trait contract (Gemini sketcher)
16. First-person prerequisite rule
Appendix A. Rules defined by this specification where the brief was silent
Appendix B. Open questions for the coordinator / Phase B

---

## 1. Purpose and design principles

### 1.1 Purpose

STUDIO SCRIPT V1 is the one universal script input format for AI Clip
Studio. A user pastes one STUDIO SCRIPT V1 document into the frontend and,
without writing any project-specific code, gets a complete production Draft
through the existing UniversalProductionPipeline: parse and validate,
storyboard review, preflight, scene package, character design, rig,
animation, Vietnamese TTS, audio timeline, SFX/music, subtitles, rendering,
Technical QA, Creative QA, and Drive upload.

One format serves all genres: historical documentaries, comedy,
educational videos, fictional stories, biographies — all told in the
first person (§16) — and others. Nothing in this specification is
specific to any one story, character, or location.

### 1.2 Design principles

1. **One format for all stories.** Every project uses the same schema, the
   same parser, and the same pipeline. No per-story code, no per-story
   parser branches, no hardcoded characters, locations, or props.
2. **Script data drives distinct renders.** CHARACTER, LOCATION, and PROP
   data MUST produce visibly distinct characters, environments, and objects.
   Every script's scenes and characters MUST be diverse, each with its own
   distinctive traits (§11, §12). Generic fallbacks that make different
   scripts look alike are defects, not features.
3. **Never substitute.** One location MUST NEVER be rendered as another
   merely because an existing background is available (§11). An unsupported
   action MUST NEVER be silently replaced by a camera move (§12).
4. **Vietnamese by default.** The default language is `vi-VN`. Narration,
   dialogue, and subtitles are Vietnamese unless the script explicitly says
   otherwise. Values preserve Unicode and Vietnamese text verbatim (§2.4).
5. **Spoken text is sacred.** Spoken lines are NEVER rewritten without
   explicit user approval. Production directives MUST NEVER reach TTS as
   spoken content (§7).
6. **Explicit over silent.** Unknown keys are recorded, never silently
   discarded (§8.3). Invalid values and references are validation errors
   with line numbers and error codes, explained before any render.
   Unresolvable triggers are errors or explicit review requirements, never
   silently invented timestamps (§6.7, §10).
7. **Audio drives the timeline.** Real generated speech determines shot
   durations. Timing MUST NOT be estimated from character count alone
   (directive §4; timeline behaviour is a pipeline concern, but the script
   format supports it through LINE_IDs, §7).
8. **Review before render; Master never automatic.** Invalid scripts are
   explained before rendering. A Master is produced only after explicit user
   approval, never automatically (§5.9).
9. **One immutable snapshot.** One SHA-256 hash of the exact raw input is
   used end to end, unchanged (§9).
10. **First person, never an external narrator.** All scripts are told
    in the first person by the character(s); an external narrator is
    forbidden. This is a prerequisite rule (§16): `NARRATION` lines are
    spoken by the primary character in that character's voice, never by
    a narrator voice, and every spoken line MUST resolve to a declared
    CHARACTER in documents that declare first-person mode.

### 1.3 Scope

This specification defines the input text format and the semantics of the
parsed data. It constrains consumers (notably §§10–12 and the planner
trait contract in §15) but does not define
renderer internals, animation primitives, TTS voices, or the frontend UI;
those are defined by their own components and MUST conform to this
specification where they consume script data.

### 1.4 Normative language

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD
NOT, RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted
as described in RFC 2119: MUST / REQUIRED / SHALL state absolute
requirements; SHOULD / RECOMMENDED state strong guidance with a reason
required for deviation; MAY / OPTIONAL state truly optional behaviour.

---

## 2. Document structure and line model

### 2.1 Encoding and lines

- A document is UTF-8 text, parsed line by line.
- Lines are split on line-feed (`\n`); a trailing carriage return (`\r`)
  is stripped, so CRLF files parse identically to LF files. A leading
  UTF-8 byte-order mark (BOM), if present, is stripped before parsing; it
  remains part of the raw input for snapshot purposes (§9).
- Blank lines (empty, or whitespace only) are ignored everywhere.
- Line numbers in parse results and validation errors are 1-based,
  counting every physical line of the raw input, including blank lines
  and comment lines.

### 2.2 Comments

- A line whose first non-whitespace character is `#` is a comment line. It
  is ignored everywhere (headers, blocks, scenes, shots) and produces no
  parsed node, except that the format-detection marker (§3.2) is itself
  such a comment line.
- There is no inline-comment syntax. A `#` appearing later in a line is
  part of the value and MUST be preserved verbatim.

### 2.3 `KEY: value` lines and block headers

- Most lines have the form `KEY: value`. The key is the text before the
  FIRST colon; the value is the remainder of the line. Values may contain
  further colons (for example `DIALOGUE: NHÂN VẬT A: ...` and
  `COSTUME_CHANGE: SCENE 1: ...`); only the first colon separates key
  from value.
- Block headers take one of these forms:
  - `BLOCK:` — for example `GLOBAL_AUDIO:`, `QA:`, `OUTPUT:`, `END_CARD:`,
    `GLOBAL_NEGATIVE_CONSTRAINTS:`.
  - `BLOCK` (bare header, new dialect) — for example `PROJECT`,
    `VISUAL_STYLE`, `GLOBAL_AUDIO`, `QA`, `OUTPUT`, `END_CARD`,
    `GLOBAL_NEGATIVE_CONSTRAINTS`. A bare header is exactly the block
    keyword alone on the line; it opens the same block as the `BLOCK:`
    form. The bare forms `PROJECT` and `VISUAL_STYLE` have no legacy
    `BLOCK:` equivalent with the same meaning (see §§4.1–4.2).
  - `BLOCK <id>:` — for example `CHARACTER: <name>`, `LOCATION: <id>`,
    `PROP: <name>`, `SCENE <n>: <title>`, `SHOT <id>:`.
  - `BLOCK: <id>` (new dialect) — for example `SCENE: SC01`,
    `SHOT: SC01_SH01`. The id is a single token (letters, digits,
    underscore, starting with a letter); see §§5.4–5.5.
  - The colon is REQUIRED on every block header except the bare-header
    form above. A block header without its required name, id, number,
    or title part is a syntax error (V1E019, §8), except that a `SCENE`
    title may be empty.
- A block identifier (character id or name, location id, prop name, shot
  id) is the full trimmed remainder of the header line. In the legacy
  dialect identifiers may contain spaces; in the new dialect `SCENE:` /
  `SHOT:` ids are single tokens. Matching of identifiers against
  references is done on the trimmed value, case-insensitively (§2.4).
  In the new dialect a CHARACTER block's id and its display `NAME` are
  distinct: the id (after `CHARACTER:`) is the reference key, and `NAME`
  is the display name (§5.1).
- `END_SCENE` and `END_SCRIPT` are legacy terminators: accepted, carrying
  no data and producing no parsed nodes. `END_SCENE` additionally closes
  the current SCENE/SHOT context (§2.5). `END_SCRIPT` is a pure no-op
  marker. Neither is required.
- `END STUDIO SCRIPT V1` (new dialect, optional trailing colon) is the
  document terminator: it ends the document. Blank lines and comment
  lines after it are ignored; any other content after it is a syntax
  error (V1E019, §8.2) and is not parsed. The terminator itself
  produces no parsed node.

### 2.4 Case rules and value preservation

- Keys are case-insensitive. `project:`, `PROJECT:`, and `Project:` are
  the same key. The canonical key spelling in this specification is
  UPPER_SNAKE_CASE.
- Block-header keywords (`CHARACTER`, `LOCATION`, `PROP`, `SCENE`,
  `SHOT`, and the `BLOCK:` headers) are case-insensitive.
- Enum values are matched case-insensitively and stored in the canonical
  form given in this specification (UPPER_SNAKE_CASE for most enums;
  lower_snake_case for SHOT `TYPE`, §5.5). The literals `AUTO`, `NONE`,
  `ALL`, and the booleans `true` / `false` are likewise case-insensitive.
- All other values preserve Unicode and Vietnamese text verbatim: no case
  changes, no diacritic changes, no punctuation changes, no translation.
  Leading and trailing whitespace around a value is trimmed; internal
  whitespace is preserved exactly.
- Speaker-name matching (§6.2) and identifier matching (§2.3) additionally
  normalise by trimming, collapsing internal runs of whitespace to a single
  space, and Unicode casefolding, so that a dialogue speaker written in a
  different case from its CHARACTER declaration still resolves. The
  canonical stored speaker is the declared CHARACTER display name (or
  `Narrator` for legacy narrator lines). In the new dialect a speaker
  reference matches a CHARACTER by block id OR by display name; the
  stored `speaker_id` is the block id (§§5.1, 6.1–6.2).

### 2.5 Blocks, context, and termination

- A document consists of header keys (§4) followed by blocks (§5). Header
  keys are recognised ONLY before the first block header; the same key
  appearing later is interpreted in block context (and, if unknown there,
  recorded under §8.3).
- Field and content lines belong to the innermost open block:
  - Lines after a `CHARACTER:`, `LOCATION:`, or `PROP:` header belong to
    that block until the next block header or the end of the document.
  - Lines after a `SCENE` header belong to that scene until the next
    `SCENE` header, `END_SCENE`, another document-level block header, or
    the end of the document.
  - Lines after a `SHOT` header belong to that shot until the next `SHOT`
    header, the next `SCENE` header, `END_SCENE`, or the end of the
    document. Content lines (§6) appearing in SHOT context are scoped to
    that shot; SHOT fields (§5.5) are likewise shot-scoped.
  - `TRANSITION:` is the one exception: it attaches to the enclosing
    SCENE even when it appears inside SHOT context, so that a transition
    written at the end of a scene (after its shots) still means the scene
    transition. Other scene-only keys (`LOCATION`, `TIME_OF_DAY`, `MOOD`,
    `VISUAL`) appearing in SHOT context are recorded under §8.3.
  - A document-level block header (`CHARACTER:`, `LOCATION:`, `PROP:`,
    `GLOBAL_AUDIO:`, `GLOBAL_NEGATIVE_CONSTRAINTS:`, `QA:`, `OUTPUT:`,
    `END_CARD:`, or any bare header in §2.3, including `PROJECT` and
    `VISUAL_STYLE`) appearing inside a scene implicitly ends that scene.
    Authors SHOULD write `END_SCENE` explicitly; parsers MUST NOT fail
    merely because it is absent.
- Non-scene blocks (PROJECT, VISUAL_STYLE, CHARACTER, LOCATION, PROP,
  GLOBAL_AUDIO, GLOBAL_NEGATIVE_CONSTRAINTS, QA, OUTPUT, END_CARD) MAY
  appear before or after scenes. References (speakers, LOCATION ids,
  OWNER, SUBJECT, COSTUME_CHANGE scenes, PROP scenes) are resolved over
  the whole document, so forward references are allowed.
- A block header ends the previous block of any kind. There is no
  `END_CHARACTER`, `END_LOCATION`, or `END_SHOT` terminator.

### 2.6 Source lines

Every parsed node (header value, block, field, content line, spoken line,
audio cue) MUST record the 1-based source line number it came from. The
frontend and all error reports use these line numbers.

### 2.7 Empty values

- A `KEY:` line with an empty (whitespace-only) value is preserved as an
  empty value and validated per field: empty values are validation errors
  for enum, numeric, and boolean fields, and for block names (CHARACTER /
  LOCATION / PROP names, SHOT ids); empty values are allowed for free-text
  fields (stored as the empty string) and for SCENE titles (stored empty).
- An absent `PROJECT:` header is treated as "no project name", not as an
  error, when the document is detected as V1 by its marker (§3).
- An empty `KEY:` line MAY also open a list or sub-block: bullet lines
  following it attach to the key (§2.8), and empty `NARRATION:` /
  `DIALOGUE:` / `SFX:` lines inside a scene open spoken / SFX sub-blocks
  (§§6.1–6.2, 6.6).

### 2.8 Bullet lists and separator lines

- A bullet line starts (after optional whitespace) with `* ` or `- `
  followed by item text. Bullet lines attach to the preceding context:
  - to the preceding `KEY:` field with an empty value (the field's value
    becomes the list of bullet items, in order); or, when the preceding
    `KEY:` line carries an inline value, the list becomes that value
    followed by the bullet items;
  - to a bare block header that takes a list (for example
    `GLOBAL_NEGATIVE_CONSTRAINTS`, §5.7), where the bullets are the
    block's list;
  - inside an `SFX:` sub-block, bullets are `SUBKEY: value` pairs
    (§6.6), not plain list items.
- Blank lines and comment lines between a key and its bullets do NOT
  break the attachment. Any other non-blank, non-comment line ends the
  list context, as does a separator line (below).
- A bullet line with no attachable context (no preceding key or list
  block in the current block) is recorded under §8.3 with its line
  number — never dropped, never a crash, never spoken text.
- A separator line consists solely of one or more `⸻` characters
  (U+2E3B, THREE-EM DASH). Separator lines are skipped: they carry no
  content, produce no parsed nodes, and never cause errors. They close
  any open sub-block or list context. Authors use them to separate
  blocks visually; parsers MUST ignore them.

---

## 3. Format detection and backward compatibility

### 3.1 Detection rule

A document is a STUDIO SCRIPT V1 document if and only if it satisfies
any of these conditions:

1. it contains a `# STUDIO SCRIPT V1` marker line (§3.2); OR
2. it contains a bare `STUDIO SCRIPT V1` marker line (§3.2); OR
3. it contains a `PROJECT:` header AND at least one `SCENE <n>:` header;
   OR
4. it contains a bare `PROJECT` header, a `SCENE: <id>` header, or a
   `SHOT: <id>` header.

Otherwise the document is a free-form script, handled by the existing
free-form parser. Detection MUST happen before V1 parsing, and the two
paths MUST NOT be mixed for a single document.

### 3.2 Marker matching

The marker is either a comment line whose trimmed text, after the
leading `#`, begins with `STUDIO SCRIPT V1`, or a bare line whose
trimmed text is exactly `STUDIO SCRIPT V1` (matched case-insensitively,
with an optional trailing colon on the terminator form only, §2.3).
Trailing text is allowed after the comment form (for example
`# STUDIO SCRIPT V1 — UNIVERSAL VIDEO FORMAT`). The marker SHOULD be
the first non-blank line, but MAY appear anywhere; detection scans the
whole document. A bare marker line inside the document is skipped
during parsing, like a comment line.

### 3.3 Backward compatibility

- Free-form scripts (no marker, and no `PROJECT:` + `SCENE` combination,
  and no bare `PROJECT` / `SCENE:` / `SHOT:` header) continue to work
  through the existing free-form parser, unchanged.
- A document detected as V1 stays V1: V1 syntax or validation failures
  MUST be reported as V1 errors (§8) and MUST NOT silently fall back to
  the free-form parser.
- There is exactly one V1 parser. This specification extends the existing
  parser; it does not create a second parser or a second pipeline.
- **Document-wide dialect determination.** A V1 document is classified
  once, before parsing, as either legacy-dialect or new-dialect: the
  presence of ANY new-dialect marker — a bare `STUDIO SCRIPT V1` line,
  a bare block header (§2.3), a `SCENE: <id>` / `SHOT: <id>` header, or
  the `END STUDIO SCRIPT V1` terminator — makes the whole document
  new-dialect. Three rules differ by dialect, and ONLY these three:
  (a) `TRANSITION` values are preserved verbatim in new-dialect
  documents but validated against the §5.4 enum in legacy documents
  (§6.11); (b) a SHOT with `CAMERA` but no `TYPE` is valid in
  new-dialect documents (`type` null) but a V1E013 error in legacy
  documents (§5.5); (c) `END_CARD` `DURATION` accepts `3s`-style
  values in new-dialect documents but plain numbers only in legacy
  documents (§5.10). Every other rule in this specification applies
  identically to both dialects, including the `CAMERA_MOVEMENT` prose
  rule (§5.5), `TARGET_DURATION` ranges (§4), per-block duplicate
  scoping (§8.2, V1E006), scoped `NONE` semantics (§10.2), and
  per-scope cue limits (§§6.7–6.9).

### 3.4 Legacy constructs preserved in V1

The following legacy forms remain valid V1 and MUST be parsed as specified:

| Legacy form | Meaning in V1 |
|---|---|
| `STYLE:` header | Legacy alias of `VISUAL_STYLE` (§4) |
| `MUSIC:` content line | Legacy alias of `BGM:` (§6.8) |
| Bare `<SPEAKER>: <text>` dialogue | Legacy dialogue form (§6.2) |
| Bare narrator lines (`NARRATOR:`, `NGƯỜI KỂ CHUYỆN:`, `DẪN CHUYỆN:`) | Narration, speaker `Narrator` (§6.2) |
| Inline free-text `LOCATION:` in a SCENE | Legacy location text; no structured LOCATION spec (§5.4, §11.4) |
| `MEME:` lines | Legacy meme cues, recorded as data (§6.9) |
| `MEME_NOTE:` lines | Supported legacy scene field: the author's note justifying or forbidding memes in the scene, kept as data, never spoken (§6.13) |
| `END_SCENE` / `END_SCRIPT` | Legacy terminators, no data (§2.3) |

New-dialect forms (bare marker line, bare block headers, `SCENE:` /
`SHOT:` headers, spoken and SFX sub-blocks, bullet lists, separator
lines, the `END STUDIO SCRIPT V1` terminator) are defined alongside the
legacy forms in §§2–6 and are equally valid V1. A document MAY mix
legacy and new-dialect forms; the document-wide dialect classification
(§3.3) governs only the three rules listed there.

### 3.5 Validation fixture

`examples/hitler_ep01.studio.md` is the first complete test fixture for
this format: 8 scenes, 4 characters, Vietnamese, using the legacy forms
above (inline LOCATION text, bare dialogue, `STYLE:`, `MUSIC:`,
`END_SCENE` / `END_SCRIPT`). It is used for schema, parser, reference,
timeline, and preflight VALIDATION ONLY and MUST NOT be rendered into a
video without ATLAS approval. Generality is proven by running at least two
unrelated scripts through the same schema and pipeline — never by
special-casing the fixture.

The authoritative new-dialect validation document is
`examples/hitler_ep01_munich_1914.studio.md` (supplied verbatim by the
author; read-only): 6 scenes, 17 shots, 9 spoken lines, 0 external
narrator lines, 7 SFX events, 6 locations, 4 props, end card, QA and
OUTPUT blocks. It exercises the new-dialect forms and the first-person
rule (§16) and MUST parse with 0 errors.

---

## 4. Header schema

Header keys appear before the first block header (§2.5). All header keys
are OPTIONAL for validity; defaults apply when a key is absent. A header
key appearing twice is a validation error (V1E006, §8.2).

| Field | Required | Default | Values / enum | Validation |
|---|---|---|---|---|
| `PROJECT` | No | — (absent) | Free text | Non-empty if present (§2.7) |
| `LANGUAGE` | No | `vi-VN` | Language tag, free text (BCP 47 style, e.g. `vi-VN`) | Non-empty if present |
| `GENRE` | No | — (absent) | Free text | — |
| `STYLE` | No | — (absent) | Free text; legacy alias of `VISUAL_STYLE` | See alias rule below |
| `VISUAL_STYLE` | No | — (absent) | Free text | See alias rule below |
| `ASPECT_RATIO` | No | `16:9` | Enum: `16:9`, `9:16` | Any other value: V1E007 |
| `TARGET_DURATION` | No | `AUTO` | `AUTO`, seconds (non-negative number), or a range such as `85–100 seconds` | Otherwise: V1E012 |
| `TONE` | No | — (absent) | Free text | — |
| `MEME_POLICY` | No | `CONTEXTUAL` | Enum: `CONTEXTUAL`, `NONE`, `ALWAYS` | Any other value: V1E007 |
| `MEME_MAX_PER_MINUTE` | No | `2` | Integer, 0 or greater | Non-integer or negative: V1E008 |

Notes:

- **STYLE / VISUAL_STYLE alias rule.** Both keys map to the single parsed
  field `visual_style`. If only one is present, its value is used. If both
  are present with the same value, that value is used. If both are present
  with different values, `VISUAL_STYLE` wins (it is the canonical name)
  and the `STYLE` value is recorded under §8.3 with its line number.
- **Duration values.** `TARGET_DURATION`, and every `DURATION` field in
  §§5.4–5.5 and §5.10, accept `AUTO` (case-insensitive) or a plain
  non-negative decimal number meaning seconds. `TARGET_DURATION`
  additionally accepts a range `N–M` (en dash, em dash, or hyphen,
  with an optional `seconds` / `s` suffix), stored verbatim with parsed
  lower and upper bounds. No unit suffix is defined for other duration
  fields; a value such as `30s` is invalid (V1E012) — EXCEPT that
  `END_CARD` `DURATION` in new-dialect documents (§3.3) and the shot
  pause fields `POST_DIALOGUE_PAUSE` / `END_HOLD` (§5.5) accept
  `Ns`-style values, parsed to seconds and stored verbatim alongside.
  `END_CARD` `DURATION` does not accept `AUTO` (§5.10).
- **Duplicate detection is per-block-context.** A key appearing twice
  in the SAME block (or twice among the header keys) is V1E006; the
  same key in DIFFERENT blocks (for example `LANGUAGE` in the PROJECT
  block and in `GLOBAL_AUDIO`) is legal. See §8.2, V1E006.
- **No upstream defaults are inherited.** The upstream V5.1 parser filled
  in its own defaults for project name, genre, style, and tone. STUDIO
  SCRIPT V1 defines no defaults for `PROJECT`, `GENRE`, `STYLE` /
  `VISUAL_STYLE`, or `TONE`; an absent key means "unspecified" in the
  parsed output. Consumers MUST NOT substitute upstream-style defaults.

Example (header only; full documents also contain blocks):

```text
# STUDIO SCRIPT V1
PROJECT: Tên dự án mẫu
LANGUAGE: vi-VN
GENRE: Thể loại mẫu
VISUAL_STYLE: Phong cách hình ảnh mẫu
ASPECT_RATIO: 16:9
TARGET_DURATION: AUTO
TONE: Giọng điệu mẫu
MEME_POLICY: CONTEXTUAL
MEME_MAX_PER_MINUTE: 2
```

### 4.1 PROJECT block (new dialect)

Header: bare `PROJECT` (§2.3).

The PROJECT block is the new-dialect form of the header: it carries the
project identity and the first-person declarations (§16). Its fields
are preserved verbatim in the parsed output (`project_fields`); the
recognised fields below also populate the parsed `meta` object. Header
keys (§4 table) and PROJECT-block fields share meanings: `LANGUAGE`,
`GENRE`, `ASPECT_RATIO`, `TARGET_DURATION` in the block behave exactly
as the header keys of the same name. At most one `PROJECT` block per
document; a second block is a validation error (V1E006).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `PROJECT_ID` | No | — (absent) | Free text (project / Drive folder id) | — |
| `TITLE` | No | — (absent) | Free text | — |
| `EPISODE` | No | — (absent) | Free text | — |
| `GENRE` | No | — (absent) | Free text | — |
| `LANGUAGE` | No | `vi-VN` | Language tag, free text | Non-empty if present |
| `STORYTELLING_MODE` | No | — (absent) | Free text; first-person modes start with `FIRST_PERSON` | See §16 |
| `PRIMARY_CHARACTER` | No | — (absent) | A declared CHARACTER id | Unknown id: V1E018 (§16) |
| `EXTERNAL_NARRATOR` | No | — (absent) | `NONE` | Any other value: V1E025 (§16) |
| `PLATFORM` | No | — (absent) | Free text | — |
| `ASPECT_RATIO` | No | `16:9` | Enum: `16:9`, `9:16` | Any other value: V1E007 |
| `RESOLUTION` | No | — (absent) | Free text | — |
| `FPS` | No | — (absent) | Free text | — |
| `DURATION_MODE` | No | — (absent) | Free text | — |
| `TARGET_DURATION` | No | `AUTO` | `AUTO`, seconds, or a range (see §4) | Otherwise: V1E012 |
| `HISTORICAL_PERIOD` | No | — (absent) | Free text | — |
| `CONTENT_PURPOSE` | No | — (absent) | Free text | — |
| `HISTORICAL_DISCLAIMER` | No | — (absent) | Free text | — |
| `MYTHOLOGY_DISCLAIMER` | No | — (absent) | Free text | — |
| `MYTHOLOGY_SOURCE` | No | — (absent) | Free text | — |
| `SERIES` | No | — (absent) | Free text | — |

```text
PROJECT
PROJECT_ID: DU_AN_MAU
TITLE: Tiêu đề mẫu
STORYTELLING_MODE: FIRST_PERSON_ROLEPLAY
PRIMARY_CHARACTER: CHAR_NHAN_VAT_A
EXTERNAL_NARRATOR: NONE
TARGET_DURATION: 85–100 seconds
```

### 4.2 VISUAL_STYLE block (new dialect)

Header: bare `VISUAL_STYLE` (§2.3).

The VISUAL_STYLE block carries the visual design policy for the whole
production. Its fields are preserved verbatim in the parsed output
(`visual_style_fields`); `STYLE` in this block also populates the
parsed `visual_style` meta field under the §4 alias rule (a
document-level `VISUAL_STYLE` header key still wins on conflict). At
most one `VISUAL_STYLE` block per document; a second block is a
validation error (V1E006).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `STYLE` | No | — (absent) | Free text | — |
| `QUALITY_REFERENCE` | No | — (absent) | Free text | — |
| `VISUAL_TARGET_SCORE` | No | — (absent) | Free text | — |
| `DESIGN_POLICY` | No | — (absent) | Free text | — |
| `HEAD_RATIO` | No | `0.34` | Float, 0.33–0.35 inclusive | Non-numeric: V1E008; out of range (including 0.42): V1E009 |
| `BODY_STYLE` | No | — (absent) | Free text | — |
| `OUTLINE` | No | — (absent) | Free text | — |
| `SHADING` | No | — (absent) | Free text | — |
| `LIGHTING` | No | — (absent) | Free text | — |
| `BACKGROUND` | No | — (absent) | Free text | — |
| `DEPTH` | No | — (absent) | Free text | — |
| `ANIMATION` | No | — (absent) | Free text | — |
| `FACIAL_ANIMATION` | No | — (absent) | Free text | — |
| `LIP_SYNC` | No | — (absent) | Free text | — |
| `EYE_TRACKING` | No | — (absent) | Free text | — |
| `CAMERA_STYLE` | No | — (absent) | Free text | — |
| `COLOR_PROGRESSION` | No | — (absent) | Bullet list (§2.8) | — |
| `STATIC_SLIDESHOW` | No | — (absent) | Free text (typically `FORBIDDEN`) | — |
| `PREGENERATED_AI_VIDEO` | No | — (absent) | Free text (typically `FORBIDDEN`) | — |
| `COMEDY_STYLE` | No | — (absent) | Free text | — |
| `CHARACTER_AGE_PROGRESSION` | No | — (absent) | Free text | — |
| `CHARACTER_SCALE_VARIATION` | No | — (absent) | Free text | — |
| `BACKGROUND_STYLE` | No | — (absent) | Free text | — |
| `CAMERA_ONLY_ANIMATION` | No | — (absent) | Free text (typically `FORBIDDEN`) | — |
| `GRAPHIC_GORE` | No | — (absent) | Free text | — |

```text
VISUAL_STYLE
STYLE: Phong cách hình ảnh mẫu
HEAD_RATIO: 0.34
COLOR_PROGRESSION:
* Cảnh mở đầu: màu ấm, ánh sáng dịu.
STATIC_SLIDESHOW: FORBIDDEN
PREGENERATED_AI_VIDEO: FORBIDDEN
```


---

## 5. Blocks

Every block section below gives the header syntax, a field table
(field, required/optional, default, values, validation), and a short
correct example using neutral placeholder names. Unless a field is marked
repeatable, it MUST appear at most once per block; a second occurrence is
a validation error (V1E006, §8.2). Unknown fields inside a block are
recorded under §8.3, never discarded.

### 5.1 CHARACTER

Header: `CHARACTER: <id>` (new dialect) or `CHARACTER: <name>` (legacy).

Declares one character. In the new dialect the header carries a stable
block id (for example `CHAR_HITLER`) and the display name comes from
the `NAME` field; id and name are distinct, and references (speakers,
`PRIMARY_CHARACTER`, `OWNER`, `SUBJECT`) match by id OR by display
name. In the legacy dialect the header carries the name itself, which
is both id and display name. Duplicate ids (compared with the §2.4
normalisation) are a validation error (V1E001). A character need not
speak; visual-only characters are valid.

Every field in the block is preserved verbatim in the parsed output
(`fields` dict: all `KEY:` values plus bullet lists keyed by key name).
The recognised fields below also populate the mapped character object:
`role` ← `ROLE`, `appearance` ← legacy `APPEARANCE` (empty in the new
dialect), `traits` ← `TRAITS`, `costume` ← `COSTUME`, `voice` ←
`VOICE_ID`, else `VOICE`, else legacy `VOICE`, `voice_style` ←
`VOICE_TONE`, else legacy `VOICE_STYLE`, `identity_id` ← block id
(unless `IDENTITY_ID` is given).

A character is an EXTRA (`is_extra`) when `VOICE: NONE` or when `ROLE`
is `Background extras` (case-insensitive, §2.4 normalisation). Extras
have no spoken lines; the pipeline MUST NOT invent speech for them.

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `NAME` | No | Block id | Free text (display name) | — |
| `ROLE` | No | — (absent) | Free text | — |
| `AGE` | No | — (absent) | Free text | — |
| `GENDER` | No | — (absent) | Free text | — |
| `NATIONALITY` | No | — (absent) | Free text | — |
| `YEAR` | No | — (absent) | Free text | — |
| `SPECIES` | No | — (absent) | Free text | — |
| `BODY_TYPE` | No | — (absent) | Free text | — |
| `BODY_COLOR` | No | — (absent) | Free text | — |
| `HEAD_RATIO` | No | `0.34` | Float, 0.33–0.35 inclusive | Non-numeric: V1E008; out of range (including 0.42): V1E009 |
| `FACE_SHAPE` | No | — (absent) | Free text | — |
| `HAIR` | No | — (absent) | Free text | — |
| `BEARD` | No | — (absent) | Free text | — |
| `MOUSTACHE` | No | — (absent) | Free text | — |
| `EYEBROWS` | No | — (absent) | Free text | — |
| `EYES` | No | — (absent) | Free text | — |
| `HORNS` | No | — (absent) | Free text | — |
| `SKIN_TONE` | No | — (absent) | Free text | — |
| `DEFAULT_EXPRESSION` | No | — (absent) | Free text | — |
| `PERSONALITY_PRESENTATION` | No | — (absent) | Free text | — |
| `FACIAL_FEATURES` | No | — (absent) | Free text | — |
| `DISTINCTIVE_FEATURES` | No | — (absent) | Bullet list (§2.8) | — |
| `APPEARANCE` | No | — (absent) | Free text (legacy) | — |
| `TRAITS` | No | — (absent) | `;`-separated distinctive traits, or bullet list | Empty segments ignored |
| `COSTUME` | No | — (absent) | Free text (default outfit), or bullet list | — |
| `COSTUME_*` | No | — (absent) | Bullet list per variant (e.g. `COSTUME_CIVILIAN`, `COSTUME_MILITARY`, `COSTUME_ADULT`, `COSTUME_CHILD`, `COSTUME_KING`) | — |
| `COSTUME_CHANGE` | No, repeatable | — (none) | `SCENE <n>: <outfit>` | Bad format: V1E019; unknown scene: V1E018 |
| `VOICE` | No | `AUTO` | Voice id, `AUTO`, or `NONE` (extras) | Non-empty if present |
| `VOICE_ENGINE` | No | — (absent) | Free text | — |
| `VOICE_ID` | No | — (absent) | Free text (voice id; wins over `VOICE`) | — |
| `VOICE_SPEED` | No | — (absent) | Free text | — |
| `VOICE_TONE` | No | — (absent) | Free text | — |
| `VOICE_STYLE` | No | — (absent) | Free text (legacy) | — |
| `NARRATION_VOICE` | No | — (absent) | Free text | — |
| `ANIMATION_CAPABILITIES` | No | — (absent) | Bullet list (§2.8) | — |
| `ANIMATION` | No | — (absent) | Bullet list (§2.8) | — |
| `AGE_VARIANTS` | No | — (absent) | Free text | — |
| `HEIGHT_RATIO*` | No | — (absent) | Free text (scale-ratio traits, e.g. `HEIGHT_RATIO_TO_ADULT_ZEUS`) | — |
| `RIG_REQUIREMENT` | No | — (absent) | Free text | — |
| `SIGNATURE_PROP` | No | — (absent) | Free text | — |
| `PROPS` | No | — (absent) | Free text | — |
| `NAMES` | No | — (absent) | Free text | — |
| `COUNT` | No | — (absent) | Free text | — |
| `IDENTITY_LOCK` | No | — (absent) | Free text | — |
| `IDENTITY_ID` | No | The block id | Free text, stable identity key | Non-empty if present; duplicates across characters: V1E001 |

`COSTUME_*` is a PATTERN, not a closed list: any key starting with
`COSTUME_` (other than the repeatable `COSTUME_CHANGE`) declares a
per-variant costume list. Likewise any key starting with `HEIGHT_RATIO`
declares a scale-ratio trait. Both patterns exist so that per-script
distinctive traits (§15) need no specification amendment per story.

`COSTUME_CHANGE` format: the value MUST start with `SCENE <n>:` where
`<n>` is a scene number that exists in the document, followed by the
outfit description. Example: `COSTUME_CHANGE: SCENE 1: Trang phục mẫu`.
Scene numbers match numerically, so `SCENE 01` and `SCENE 1` are the
same scene. Multiple `COSTUME_CHANGE` lines are allowed; two changes for
the same scene are a validation error (V1E006).

```text
CHARACTER: CHAR_NHAN_VAT_A
NAME: Nhân vật A
ROLE: Vai trò mẫu
AGE: 25
HEAD_RATIO: 0.34
FACE_SHAPE: Tròn
HAIR: Tóc ngắn đen
EYES: Mắt tròn
COSTUME_CIVILIAN:
* Áo sơ mi trắng
* Quần dài sẫm màu
VOICE_ENGINE: VieNeu-TTS
VOICE_ID: GIONG_DOC_MAU_A
VOICE_TONE: Ấm, rõ ràng
IDENTITY_LOCK: TRUE
```

### 5.2 LOCATION

Header: `LOCATION: <id>`

Declares one reusable environment specification. The id is how scenes
refer to this location (§5.4). Duplicate ids (compared with the §2.4
normalisation) are a validation error (V1E002). All fields are OPTIONAL;
an absent field means "unspecified", never "use another location's value"
(§11).

Every field in the block is preserved verbatim in the parsed output
(`fields` dict). The recognised fields below also populate the mapped
location object: `period` ← `PERIOD`, else `YEAR`, else
`HISTORICAL_PERIOD`; `geography` ← `GEOGRAPHY`, else
`HISTORICAL_REFERENCE`; `features` ← `DISTINCTIVE_FEATURES`, else
`FEATURES`; `palette` ← `COLOR_PALETTE` (comma/semicolon-split), else
`PALETTE`; `foreground` / `midground` / `background` ← bullet lists
(new dialect) or single values (legacy).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `NAME` | No | — (absent) | Free text (display name) | — |
| `TYPE` | No | — (absent) | Free text (e.g. `INTERIOR`, `EXTERIOR`) | — |
| `PERIOD` | No | — (absent) | Free text (historical period / era) | — |
| `HISTORICAL_PERIOD` | No | — (absent) | Free text | — |
| `HISTORICAL_REFERENCE` | No | — (absent) | Free text | — |
| `HISTORICAL_STATUS` | No | — (absent) | Free text | — |
| `YEAR` | No | — (absent) | Free text | — |
| `TIME_OF_DAY` | No | — (absent) | Free text | — |
| `GEOGRAPHY` | No | — (absent) | Free text | — |
| `ARCHITECTURE` | No | — (absent) | Free text | — |
| `FEATURES` | No | — (absent) | `;`-separated distinctive features (legacy) | Empty segments ignored |
| `DISTINCTIVE_FEATURES` | No | — (absent) | Bullet list (§2.8) | — |
| `FOREGROUND` | No | — (absent) | Free text, or bullet list | — |
| `MIDGROUND` | No | — (absent) | Free text, or bullet list | — |
| `BACKGROUND` | No | — (absent) | Free text, or bullet list | — |
| `LIGHTING` | No | — (absent) | Free text | — |
| `WEATHER` | No | — (absent) | Free text | — |
| `PALETTE` | No | — (absent) | `;`-separated colours (legacy) | Empty segments ignored |
| `COLOR_PALETTE` | No | — (absent) | Comma/semicolon-separated colours | Empty segments ignored |
| `FORBIDDEN` | No | — (absent) | `;`-separated forbidden elements, or bullet list | Empty segments ignored |
| `AMBIENCE` | No | — (absent) | Free text | — |
| `MAP_STYLE` | No | — (absent) | Free text | — |
| `LABEL_LANGUAGE` | No | — (absent) | Free text | — |
| `ANIMATION` | No | — (absent) | Bullet list (§2.8) | — |
| `REFERENCE_RESEARCH` | No | — (absent) | Free text | — |

```text
LOCATION: LOC_DIA_DIEM_X
NAME: Tên địa điểm mẫu
TYPE: EXTERIOR
YEAR: 2024
TIME_OF_DAY: MORNING
WEATHER: Nắng nhẹ
HISTORICAL_REFERENCE: Tham chiếu mẫu
DISTINCTIVE_FEATURES:
* Đặc điểm riêng mẫu một
* Đặc điểm riêng mẫu hai
FOREGROUND:
* Tiền cảnh mẫu
MIDGROUND:
* Trung cảnh mẫu
BACKGROUND:
* Hậu cảnh mẫu
LIGHTING: Ánh sáng mẫu
COLOR_PALETTE: Màu mẫu một, màu mẫu hai
FORBIDDEN:
* Yếu tố cấm mẫu
```

### 5.3 PROP

Header: `PROP: <id>` (new dialect) or `PROP: <name>` (legacy).

Declares one prop (object). In the new dialect the header carries a
block id and the display name comes from `NAME` when present; in the
legacy dialect the header carries the name itself, which is both id
and name. Duplicate ids (compared with the §2.4 normalisation) are a
validation error (V1E001). All fields are OPTIONAL. Every field is
preserved verbatim in the parsed output (`fields` dict).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `NAME` | No | Block id | Free text (display name) | — |
| `TYPE` | No | — (absent) | Free text (e.g. `DOCUMENT`, `WEAPON`) | — |
| `COLOR` | No | — (absent) | Free text | — |
| `MATERIAL` | No | — (absent) | Free text | — |
| `VFX` | No | — (absent) | Free text | — |
| `DESCRIPTION` | No | — (absent) | Free text | — |
| `OWNER` | No | — (unspecified) | A declared CHARACTER id or name, or `NONE` | Unknown character: V1E018 |
| `SCENES` | No | — (unspecified) | Comma-separated scene numbers, or `ALL` | Bad format: V1E019; unknown scene: V1E018 |
| `INTERACTION` | No | — (absent) | Comma/semicolon-separated verbs (how the prop is handled) | Empty segments ignored |

`OWNER: NONE` means the prop belongs to no character. An absent `OWNER`
means ownership is unspecified. `SCENES: ALL` means the prop may appear
in every scene; a comma list (for example `SCENES: 1, 3`) restricts it
to the listed scenes. Scene numbers match numerically.

```text
PROP: VẬT DỤNG X
DESCRIPTION: Mô tả vật dụng mẫu
OWNER: NHÂN VẬT A
SCENES: 1
INTERACTION: Cầm; đưa; đặt xuống
```

### 5.4 SCENE

Header: `SCENE: <id>` (new dialect) or `SCENE <n>: <title>` (legacy).

Declares one scene. In the legacy form `<n>` is a positive integer;
leading zeros are allowed (`SCENE 01` is scene 1). Duplicate scene
numbers (by numeric value) are a validation error (V1E003). In the new
dialect the header carries a single-token id (for example `SC01`); the
scene NUMBER is its 1-based ordinal in document order, and the id is
kept alongside (`id` in the parsed output; empty in the legacy
dialect). Duplicate new-dialect scene ids are a validation error
(V1E003). Scene numbers need not be consecutive. The production order
of scenes is DOCUMENT ORDER, not numeric order. A V1 document MUST
contain at least one SCENE (V1E020). A scene contains SHOT blocks
(§5.5) and content lines (§6). The scene `TITLE` in the new dialect is
a `TITLE:` field inside the block (the header carries only the id).

Every field in the block is preserved verbatim in the parsed output
(`fields` dict).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `TITLE` | No | — (absent) | Free text | — |
| `LOCATION` | No | — (absent) | A LOCATION id (reference), or inline free text (legacy) | Never an error: non-matching values are inline text (§11.4) |
| `CHARACTERS` | No | — (absent) | Comma-separated CHARACTER ids, or `NONE` | — |
| `COSTUME` | No | — (absent) | Free text (e.g. `CIVILIAN`, `MILITARY`) | — |
| `TIME_OF_DAY` | No | — (absent) | Free text | — |
| `MOOD` | No | — (absent) | Free text | — |
| `STORY_PURPOSE` | No | — (absent) | Free text | — |
| `HISTORICAL_PROVENANCE` | No | — (absent) | Free text | — |
| `DURATION` | No | `AUTO` | `AUTO`, or seconds (non-negative number) | Otherwise: V1E012 |
| `VISUAL` | No | — (absent) | Free text (scene description) | — |
| `TRANSITION` | No | `CUT` | Enum in legacy documents; verbatim free text in new-dialect documents (§6.11) | Legacy only, any other value: V1E007 |

`CHARACTERS: NONE` means the scene declares no characters (stored as an
empty list). Character references in `CHARACTERS` are NOT validated
against declared CHARACTER blocks: the list is casting data, and an
unknown entry is preserved, not an error. (Speaker references ARE
validated, §6.2; `LOCATION_OVERRIDE` references ARE validated, §5.5.)

`LOCATION` resolution: if the trimmed value matches a declared LOCATION
id (§2.4 normalisation), the scene references that LOCATION block; the
structured environment specification governs the render (§11). Otherwise
the value is legacy inline free text and is kept verbatim. Matching is
checked against ALL declared LOCATION blocks in the document, regardless
of block order. A `LOCATION:` line INSIDE a scene is always a reference
or inline text — never a LOCATION declaration (a document-level
`LOCATION: <id>` header declares, §5.2); the V1E002 duplicate-location
error MUST NOT fire for scene LOCATION references.

`TRANSITION` MAY appear among the scene fields (as in the example) or as
a content line at the end of the scene (§6.11); both positions mean the
same field. If it appears in both positions with different values, that
is a duplicate-field error (V1E006).

```text
SCENE: SC01
TITLE: Tiêu đề cảnh mẫu
LOCATION: LOC_DIA_DIEM_X
CHARACTERS: CHAR_NHAN_VAT_A, CHAR_NHAN_VAT_B
MOOD: Tâm trạng mẫu
STORY_PURPOSE: Mục đích truyện mẫu
TRANSITION: CUT
NARRATION:
SPEAKER: CHAR_NHAN_VAT_A
LINE_ID: MAU_001
TEXT: “Lời dẫn mẫu.”
```

### 5.5 SHOT

Header: `SHOT: <id>` (new dialect) or `SHOT <id>:` (legacy) — inside a
SCENE only.

Declares one shot (camera setup) within its scene. A `SHOT` header
outside any SCENE is a validation error (V1E019). Shot ids MUST be
unique within their scene (V1E004); the same id MAY be reused in a
different scene. A shot contains its fields plus, optionally, content
lines scoped to the shot (§2.5, §6). Every field is preserved verbatim
in the parsed output (`fields` dict).

**CAMERA vs TYPE.** `CAMERA` is a FREE-TEXT description of the shot
(what the camera sees); it is NEVER validated against the nine
`TYPE` values. `TYPE` is the closed enum below. The two fields are
independent: a shot MAY declare both, either, or — in legacy documents
only — neither (see the `TYPE` rule below). Consumers MUST NOT treat
`CAMERA` text as a `TYPE` value.

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `TYPE` | See rule below | — (none) | Enum, see table below | Missing (when required): V1E013; unknown: V1E014 |
| `CAMERA` | No | — (absent) | Free text, never enum-validated | — |
| `CAMERA_MOVEMENT` | No | `STATIC` | Enum (below), or descriptive prose (see rule below) | Failed enum attempt: V1E007 |
| `SUBJECT` | No | — (absent) | A CHARACTER or PROP id or name | Unknown name: V1E018 |
| `DURATION` | No | `AUTO` | `AUTO`, or seconds (non-negative number) | Otherwise: V1E012 |
| `ACTION` | No | — (absent) | Free text, kept verbatim, or bullet list (§2.8) | — |
| `EXPRESSION` | No | — (absent) | Same two forms as §6.4 | Unknown character prefix: V1E018 |
| `VFX` | No | — (absent) | `;`-separated VFX names, or bullet list | Empty segments ignored |
| `LOCATION_OVERRIDE` | No | — (absent) | A declared LOCATION id | Unknown id: V1E018 |
| `TRIGGER` | No | — (absent) | Free text, typically `LINE_ID — "quote"` | — |
| `COMPOSITION` | No | — (absent) | Free text | — |
| `POST_DIALOGUE_PAUSE` | No | — (absent) | `Ns` seconds (e.g. `0.6s`) | Unparseable: V1E012 |
| `END_HOLD` | No | — (absent) | `Ns` seconds (e.g. `1.5s`) | Unparseable: V1E012 |
| `FLASH_SAFETY` | No | — (absent) | Free text | — |

**`TYPE` rule.** When `TYPE` is present it is validated as the enum
below (V1E013/V1E014 as in the legacy dialect). When `TYPE` is ABSENT:
in new-dialect documents (§3.3) the shot is valid if `CAMERA` is
present, and its parsed `type` is null; in legacy documents, or when
neither `TYPE` nor `CAMERA` is present, the missing `TYPE` is a
validation error (V1E013).

**`CAMERA_MOVEMENT` rule (both dialects).** The value is first matched
against the enum below (case-insensitive, spaces/hyphens as
underscores). If it matches, the enum value is stored. If it does NOT
match: a value containing lowercase letters or spaces is DESCRIPTIVE
PROSE — accepted verbatim, stored in `camera_movement_text`, with the
enum movement null; an UPPER_SNAKE_CASE value that matches no enum
entry is a FAILED ENUM ATTEMPT and a validation error (V1E007).
`camera_movement_text` always holds the verbatim line whenever a
`CAMERA_MOVEMENT` line is present, and is empty otherwise.

`LOCATION_OVERRIDE` MUST match a declared LOCATION id (or, by §2.4
normalisation, a LOCATION display name); otherwise V1E018. It
overrides the scene LOCATION for this shot only.

`TRIGGER` is preserved verbatim; when it starts with a LINE_ID token
(letters/digits/underscore, followed by a dash or colon), that token
is also stored as `trigger_line_id`. Trigger resolution is V1E022 at
the timeline stage (§8.2), never a parse-time error.

`POST_DIALOGUE_PAUSE` and `END_HOLD` are parsed to seconds (float) and
stored verbatim alongside (`post_dialogue_pause_raw` / `end_hold_raw`).
Plain numbers without a unit are also accepted.

`TYPE` enum (canonical form lower_snake_case; UPPER_SNAKE_CASE input is
accepted and normalised to the canonical form; matching is
case-insensitive and treats spaces and hyphens as underscores). These
eleven values match the engine camera planner's shot types:

| Canonical `TYPE` | Accepted input forms include | Meaning |
|---|---|---|
| `establishing` | `ESTABLISHING` | Wide shot establishing place and scale |
| `medium` | `MEDIUM` | Medium shot of the subject(s) |
| `close_up` | `CLOSE_UP` | Close-up on the subject |
| `extreme_close_up` | `EXTREME_CLOSE_UP` | Extreme close-up on a detail |
| `over_the_shoulder` | `OVER_THE_SHOULDER` | Shot from behind one subject toward another |
| `reaction` | `REACTION` | Reaction shot of a subject |
| `object_insert` | `OBJECT_INSERT` | Insert shot of an object or detail |
| `tracking` | `TRACKING` | Shot whose camera tracks a moving subject |
| `shot_reverse_shot` | `SHOT_REVERSE_SHOT` | Alternating shot/reverse-shot pair |
| `medium_close_up` | `MEDIUM_CLOSE_UP` | Chest-up medium close-up of the subject (channel-study R1) |
| `graphic_insert` | `GRAPHIC_INSERT` | Flat full-frame graphic insert card: time, counting, or object card, rendered as a card, not a crop (channel-study R6) |

Any other `TYPE` value is a validation error (V1E014). No other shot
type may be invented by the parser or the planner; a script needing a
new shot type requires a specification amendment (§14).

`CAMERA_MOVEMENT` enum (canonical form UPPER_SNAKE_CASE): `STATIC`,
`PAN_LEFT`, `PAN_RIGHT`, `TILT_UP`, `TILT_DOWN`, `DOLLY_IN`,
`DOLLY_OUT`, `TRACKING`, `CRANE_UP`, `CRANE_DOWN`, `HANDHELD`.

```text
SHOT SH01:
TYPE: establishing
CAMERA: Mô tả góc máy mẫu
CAMERA_MOVEMENT: DOLLY_IN
SUBJECT: NHÂN VẬT A
DURATION: AUTO
ACTION: Hành động mẫu trong shot.
EXPRESSION: NHÂN VẬT A: Biểu cảm mẫu
VFX: Hiệu ứng mẫu một; hiệu ứng mẫu hai
```

### 5.6 GLOBAL_AUDIO

Header: `GLOBAL_AUDIO:` (legacy) or bare `GLOBAL_AUDIO` (new dialect).

Sets mix levels for the six audio buses (§10) and the global audio
policy. All fields are OPTIONAL. Every field is preserved verbatim in
the parsed output (`fields` dict). At most one `GLOBAL_AUDIO` block per
document; a second block is a validation error (V1E006).

Gain fields are floats in decibels (dB); non-numeric values are V1E008.
No range validation is defined for gain values: any finite float is
accepted.

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `NARRATION_GAIN_DB` | No | `0` | Float (dB) | Non-numeric: V1E008 |
| `DIALOGUE_GAIN_DB` | No | `0` | Float (dB) | Non-numeric: V1E008 |
| `AMBIENCE_GAIN_DB` | No | `-18` | Float (dB) | Non-numeric: V1E008 |
| `FOLEY_GAIN_DB` | No | `-12` | Float (dB) | Non-numeric: V1E008 |
| `SFX_GAIN_DB` | No | `-6` | Float (dB) | Non-numeric: V1E008 |
| `BGM_GAIN_DB` | No | `-18` | Float (dB) | Non-numeric: V1E008 |
| `BGM_DUCKING_DB` | No | `-6` | Float (dB) | Non-numeric: V1E008 |
| `MASTER_LIMIT_DB` | No | `-1.0` | Float (dB) | Non-numeric: V1E008 |
| `TTS_ENGINE` | No | — (absent) | Free text | — |
| `LANGUAGE` | No | — (absent) | Language tag, free text | — |
| `TTS_SPEED` | No | — (absent) | Free text | — |
| `VOICE_FALLBACK` | No | — (absent) | Free text (typically `NONE`) | — |
| `VOICE_PRIORITY` | No | — (absent) | Free text | — |
| `BGM_DUCKING` | No | — (absent) | Free text, e.g. a range `12–18 dB` | — |
| `SFX_DENSITY` | No | — (absent) | Free text | — |
| `SFX_TRIGGER_MODE` | No | — (absent) | Free text | — |
| `AMBIENCE_MODE` | No | — (absent) | Free text | — |
| `SUBTITLE_LANGUAGE` | No | — (absent) | Free text | — |
| `SUBTITLE_SYNC` | No | — (absent) | Free text | — |
| `SUBTITLE_STYLE` | No | — (absent) | Free text | — |
| `AUDIO_TRUNCATION` | No | — (absent) | Free text (typically `FORBIDDEN`) | — |
| `UNNATURAL_AUDIO_SPEEDUP` | No | — (absent) | Free text (typically `FORBIDDEN`) | — |
| `MEME_SOUND` | No | — (absent) | Free text (typically `DISABLED`) | — |
| `AUTOMATIC_TRANSITION_WHOOSH` | No | — (absent) | Free text (typically `DISABLED`) | — |
| `PRONUNCIATION_POLICY` | No | — (absent) | Free text | — |
| `PRONUNCIATION_REVIEW` | No | — (absent) | Free text | — |

`BGM_DUCKING` (free text, often a range) and `BGM_DUCKING_DB` (a single
numeric gain) are distinct fields; both are preserved when present.
`LANGUAGE` here is scoped to this block: the same key in the PROJECT
block is legal (§4, per-block duplicate scoping).

```text
GLOBAL_AUDIO:
NARRATION_GAIN_DB: 0
DIALOGUE_GAIN_DB: 0
AMBIENCE_GAIN_DB: -18
FOLEY_GAIN_DB: -12
SFX_GAIN_DB: -6
BGM_GAIN_DB: -18
BGM_DUCKING_DB: -6
MASTER_LIMIT_DB: -1.0
```

### 5.7 GLOBAL_NEGATIVE_CONSTRAINTS

Header: `GLOBAL_NEGATIVE_CONSTRAINTS:` (legacy) or bare
`GLOBAL_NEGATIVE_CONSTRAINTS` (new dialect).

Lists production-wide prohibitions. The block contains one constraint
per line, in any of three forms. Lines in any other form inside this
block are recorded under §8.3.

- `- <text>` — a dash followed by the constraint text.
- `* <text>` — an asterisk bullet followed by the constraint text
  (§2.8).
- `NO: <text>` — the key `NO:` followed by the constraint text.

Constraints are kept verbatim and in document order. They apply to the
whole production. At most one `GLOBAL_NEGATIVE_CONSTRAINTS:` block per
document; a second block is a validation error (V1E006).

```text
GLOBAL_NEGATIVE_CONSTRAINTS:
- Điều cấm mẫu một
NO: Điều cấm mẫu hai
```

### 5.8 QA

Header: `QA:` (legacy) or bare `QA` (new dialect).

Sets quality-gate requirements for the production. All fields are
OPTIONAL. Every field is preserved verbatim in the parsed output
(`fields` dict). At most one `QA` block per document; a second block
is a validation error (V1E006).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `MIN_SCORE` | No | `8.0` | Float, 0–10 inclusive | Non-numeric: V1E008; out of range: V1E010 |
| `MIN_OVERALL_SCORE` | No | — (absent) | `8.0/10`-style score text | Parsed to `min_score` when numeric |
| `MIN_*` | No | — (absent) | Free text (further minimum thresholds) | — |
| `TARGET_*` | No | — (absent) | Free text (target scores) | — |
| `HARD_FAIL_COUNT` | No | — (absent) | Integer, 0 or greater | Parsed to `max_hard_fails` when numeric |
| `EXPECTED_*` | No | — (absent) | Integer counts (e.g. `EXPECTED_SCENES`, `EXPECTED_SHOTS`, `EXPECTED_SPOKEN_LINES`, `EXPECTED_NARRATION_LINES`, `EXPECTED_DIALOGUE_LINES`, `EXPECTED_EXTERNAL_NARRATOR_LINES`, `EXPECTED_EXPLICIT_SFX_EVENTS`) | Parsed ints in `expected_counts`; non-numeric values preserved verbatim only |
| `*_CHECK` | No | — (absent) | Free text (typically `REQUIRED`) | — |
| `*_REVIEW` | No | — (absent) | Free text (typically `REQUIRED`) | — |
| `REQUIRE_TECHNICAL` | No | `true` | Boolean `true` / `false` | Otherwise: V1E011 |
| `REQUIRE_CREATIVE_REVIEW` | No | `true` | Boolean `true` / `false` | Otherwise: V1E011 |
| `LANGUAGE_GATE` | No | `true` | Boolean `true` / `false` | Otherwise: V1E011 |
| `MAX_HARD_FAILS` | No | `0` | Integer, 0 or greater | Non-integer or negative: V1E008 |
| `HUMAN_VISUAL_REVIEW` | No | — (absent) | Free text | — |
| `VOICE_LISTENING_REVIEW` | No | — (absent) | Free text | — |
| `MP4_VALIDATION` | No | — (absent) | Free text | — |
| `UNSUPPORTED_ANIMATION_POLICY` | No | — (absent) | Free text | — |
| `FAILED_QA_POLICY` | No | — (absent) | Free text (typically `BLOCK_MASTER`) | — |

Boolean values are matched case-insensitively (`true`, `TRUE`, `True`
are the same). No other spelling (such as `yes` / `no` / `1` / `0`) is
accepted.

`MIN_*`, `TARGET_*`, `EXPECTED_*`, `*_CHECK`, and `*_REVIEW` are
PATTERNS, not closed lists. `EXPECTED_*` counts are preserved verbatim
and, when numeric, parsed into `expected_counts` (keyed by lowercase
name, e.g. `expected_scenes`). The parser performs NO cross-check of
`EXPECTED_*` counts against the parsed document: the QA block is
preserved data for the QA stage, and a mismatch between a QA count and
the document body is never a parse error — the body is always rendered
in full, never truncated to match a QA count.

```text
QA:
MIN_SCORE: 8.0
REQUIRE_TECHNICAL: true
REQUIRE_CREATIVE_REVIEW: true
LANGUAGE_GATE: true
MAX_HARD_FAILS: 0
```

### 5.9 OUTPUT

Header: `OUTPUT:` (legacy) or bare `OUTPUT` (new dialect).

Sets render output parameters. All fields are OPTIONAL. Every field is
preserved verbatim in the parsed output (`fields` dict). At most one
`OUTPUT` block per document; a second block is a validation error
(V1E006).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `RESOLUTION` | No | `1920x1080` | Enum: `1920x1080`, `1280x720` | Any other value: V1E007 |
| `FPS` | No | `24` | Enum: `24`, `25`, `30` | Any other value: V1E007 |
| `FORMAT` | No | `MP4` | Enum: `MP4` | Any other value: V1E007 |
| `VIDEO_FORMAT` | No | — (absent) | Enum: `MP4` (alias of `FORMAT`) | Any other value: V1E007 |
| `VIDEO_CODEC` | No | — (absent) | Free text | — |
| `AUDIO_CODEC` | No | — (absent) | Free text | — |
| `PIXEL_FORMAT` | No | — (absent) | Free text | — |
| `EXPORT_*` | No | — (absent) | Free text (export flags, e.g. `EXPORT_DRAFT`, `EXPORT_MASTER`, `EXPORT_SUBTITLES`) | — |
| `UPLOAD_GOOGLE_DRIVE` | No | — (absent) | Free text | — |
| `DRIVE_ROOT_ID` | No | — (absent) | Free text | — |
| `DRIVE_PROJECT_FOLDER` | No | — (absent) | Free text | — |
| `DRIVE_SUBFOLDERS` | No | — (absent) | Bullet list (§2.8) | — |
| `MASTER_APPROVAL` | No | — (absent) | Free text | — |
| `DRAFT_FOLDER` | No | `drive:drafts` | Free text | — |
| `MASTER` | No | `MANUAL_ONLY` | Enum: `MANUAL_ONLY` | Any other value: V1E017 |

`EXPORT_*` is a PATTERN, not a closed list. `VIDEO_FORMAT` is an alias
of `FORMAT`: both populate the parsed `format` field, and both must be
`MP4` when present.

**Master is never automatic.** `MASTER` accepts exactly one value,
`MANUAL_ONLY`: a Master render happens only after explicit user approval.
Any other value (including `AUTO`, `ALWAYS`, `true`) is a validation
error (V1E017). Omitting `MASTER` means `MANUAL_ONLY`.

```text
OUTPUT:
RESOLUTION: 1920x1080
FPS: 24
FORMAT: MP4
DRAFT_FOLDER: drive:drafts
MASTER: MANUAL_ONLY
```

### 5.10 END_CARD

Header: `END_CARD:` (legacy) or bare `END_CARD` (new dialect).

Describes the closing card shown at the end of the video. All fields are
OPTIONAL. Every field is preserved verbatim in the parsed output
(`fields` dict). At most one `END_CARD` block per document; a second
block is a validation error (V1E006).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `TEXT` | No | — (absent) | Free text, kept verbatim (quotes NOT stripped) | — |
| `SECONDARY_TEXT` | No | — (absent) | Free text | — |
| `TEXT_LANGUAGE` | No | — (absent) | Free text | — |
| `BACKGROUND` | No | — (absent) | Free text | — |
| `DURATION` | No | `3.0` | Seconds (non-negative number); `AUTO` is NOT accepted; `3s`-style values accepted in new-dialect documents (§3.3) | Otherwise: V1E012 |
| `STYLE` | No | — (absent) | Free text | — |
| `BGM` | No | — (absent) | Free text, or `NONE` | — |
| `SFX` | No | — (absent) | Free text, or `NONE` | — |

`DURATION` is stored both verbatim (`duration_raw`, e.g. `3s`) and
parsed (`duration` / `duration_sec`, float seconds). An absent
`END_CARD` block means no end card is specified; consumers MUST NOT
invent one.

```text
END_CARD
BACKGROUND: Đen
TEXT: HẾT
SECONDARY_TEXT: Cảm ơn bạn đã xem
TEXT_LANGUAGE: vi-VN
DURATION: 3s
BGM: NONE
SFX: NONE
```

---

## 6. Content lines

Content lines appear inside a SCENE, and optionally inside a SHOT
(§2.5). A content line outside any SCENE is recorded under §8.3, except
that `TRANSITION:` outside a scene is likewise recorded, never applied.
Content lines are ordered: their document order is their production
order within the enclosing scene or shot.

Pipe-segment syntax (`SFX:`, `AMBIENCE:`, `BGM:` / `MUSIC:`, `MEME:`,
`VFX:`) is: `<name>` followed by zero or more `| SUBKEY: value`
segments. The name comes first; subkeys MAY appear in any order. Unknown
subkeys are recorded under §8.3 with the line number. A subkey appearing
twice on one line is a validation error (V1E006).

### 6.1 NARRATION

Syntax (legacy one-line form):

```text
NARRATION: <text>
NARRATION [Lnn]: <text>
```

Syntax (new-dialect sub-block form):

```text
NARRATION:
SPEAKER: <CHARACTER id or name>
LINE_ID: <verbatim id>
TEXT: <spoken text, optionally quoted>
LIP_SYNC: <value>
```

A spoken narration line. In the legacy form the speaker is `Narrator`
(§7). In the sub-block form the speaker is the `SPEAKER:` value,
resolved to a declared CHARACTER (§6.2); a sub-block `NARRATION`
without a `SPEAKER` resolving to a declared CHARACTER is a narrator
line, which is a V1E025 error in first-person documents (§16) and a
legacy narrator line otherwise. The `[Lnn]` form carries an explicit
LINE_ID (§7.1); in the sub-block form `LINE_ID:` carries it verbatim.
`SPEAKER:`, `LINE_ID:`, `TEXT:`, and `LIP_SYNC:` may appear in any
order; any other line ends the sub-block. A sub-block with no `TEXT:`
is a syntax error (V1E019). Spoken text is kept verbatim (§7.2),
except that `TEXT:` strips ONE layer of matching surrounding quotes
(straight `"` or curly `“”`); inner quotes are preserved.

A `LIP_SYNC:` line appearing at shot/scene level AFTER a spoken
sub-block (rather than inside it) applies to the most recent spoken
line in that shot (or scene) that has no `LIP_SYNC` yet, and is also
preserved in the shot/scene fields.

### 6.2 DIALOGUE and bare speaker lines

Syntax (legacy one-line forms):

```text
DIALOGUE: <Speaker>: <text>
DIALOGUE [Lnn]: <Speaker>: <text>
<SPEAKER>: <text>
```

Syntax (new-dialect sub-block form):

```text
DIALOGUE:
SPEAKER: <CHARACTER id or name>
LINE_ID: <verbatim id>
TEXT: <spoken text, optionally quoted>
LIP_SYNC: <value>
```

A spoken dialogue line. In the one-line forms the speaker is the text
between the key (or the start of the line, for the bare form) and the
next colon; the spoken text is the remainder. In the sub-block form the
speaker is the `SPEAKER:` value and the text is the `TEXT:` value
(one quote layer stripped, §6.1); a `DIALOGUE` sub-block without a
`SPEAKER:` is a syntax error (V1E019). The speaker MUST be a declared
CHARACTER, matched by block id or display name with the §2.4
normalisation, otherwise it is a validation error with the line number
(V1E015). The stored speaker is the CHARACTER display name, and
`speaker_id` is the block id.

Narrator aliases: the speaker names `NARRATOR`, `NGƯỜI KỂ CHUYỆN`, and
`DẪN CHUYỆN` (matched case-insensitively, §2.4 normalisation) map to the
speaker `Narrator`, in both the `DIALOGUE:` form and the bare form.
Alias mapping takes precedence over CHARACTER-name matching: a bare
`NGƯỜI DẪN CHUYỆN: ...` line is narration even if a CHARACTER of that
name is declared.

The bare form is legacy (§3.4) but fully valid. A bare line is
recognised as dialogue when its pre-colon part matches a declared
CHARACTER name or a narrator alias. Any other `SOMETHING: ...` line that
matches no known key and no speaker is recorded under §8.3 — it is
never treated as spoken text.

### 6.3 ACTION

Syntax: `ACTION: <text>`, or `ACTION:` followed by bullet lines (§2.8).

Free text describing an action, kept verbatim. Multiple `ACTION:` lines
are allowed and are ordered. Scene-level `ACTION:` lines describe the
scene's action; shot-level `ACTION:` lines (including the SHOT `ACTION`
field, §5.5) describe the shot's action. `ACTION:` text is NEVER spoken.
How actions map to animation — including the rule that unsupported
actions are reported, never replaced by camera moves — is defined in
§12.3.

### 6.4 EXPRESSION

Syntax:

```text
EXPRESSION: <Character>: <expression>
EXPRESSION: <expression>
```

The first form names the character the expression applies to; the
character prefix MUST resolve to a declared CHARACTER or a narrator
alias, otherwise it is a validation error (V1E018). The second ("bare")
form carries no character prefix and applies to the scene's or shot's
current subject. A line with no `EXPRESSION:` key is NOT an expression
line (see §8.3). Expression text is kept verbatim and is NEVER spoken.

### 6.5 CAMERA and CAMERA_MOVEMENT at scene level

Syntax:

```text
CAMERA: <free text>
CAMERA_MOVEMENT: <enum>
```

At scene level, these two lines define the scene's DEFAULT shot: the
camera description and movement used for scene content that is not
inside an explicit SHOT block. `CAMERA:` is free text. `CAMERA_MOVEMENT:`
follows the §5.5 rule: an enum value, or descriptive prose stored
verbatim (an UPPER_SNAKE value outside the enum is V1E007); default
`STATIC`. Inside a SHOT block, the same keys are SHOT fields (§5.5).
Neither line is ever spoken.

### 6.6 SFX

Syntax (legacy one-line form):

```text
SFX: <name> | TRIGGER: <LINE_ID or action text> | PRIORITY: <REQUIRED|OPTIONAL>
SFX: NONE
```

Syntax (new-dialect structured sub-block form):

```text
SFX:
* ID: SFX_001
* EVENT: <event name>
* TRIGGER: <LINE_ID or action text>
* TYPE: <free text>
* INTENSITY: <LOW|MEDIUM|HIGH>
* DURATION: <e.g. 0.4s>
* DURATION_MODE: <free text>
```

Multiple `SFX:` lines are allowed per scene (and per shot). Subkeys
(one-line form):

| Subkey | Required | Default | Values |
|---|---|---|---|
| `TRIGGER` | No | — (absent) | A LINE_ID (e.g. `L001`) or free action text |
| `PRIORITY` | No | `REQUIRED` | Enum: `REQUIRED`, `OPTIONAL` |

In the sub-block form, each bullet is a `SUBKEY: value` pair; all
sub-fields are preserved verbatim in the audio cue (`cue_id`, `event`,
`trigger`, `cue_type_text`, `intensity`, `duration`, `duration_mode`,
plus `duration_seconds` when the duration parses). The cue name is the
`EVENT` value (or the `ID` when no `EVENT` is given); the cue records
its scene, shot, and line. A bullet without a colon inside an `SFX`
sub-block is recorded under §8.3; a repeated subkey is a validation
error (V1E006). An empty `SFX:` sub-block (no bullets) produces no cue
and no error.

`TRIGGER` resolution happens against the generated speech timeline
(LINE_ID triggers) or the animation timeline (action-text triggers).
A trigger that cannot be resolved is a validation error or an explicit
review requirement at the timeline stage (V1E022, §8.2); a timestamp
MUST NEVER be silently invented (§10.3).

`SFX: NONE` means this scope (scene or shot, §10.2) has NO sound
effects. It MUST be recorded as an explicit none (§10.2) and MUST NOT
be treated as "no SFX line present". A `NONE` line MUST NOT carry `|`
segments; segments on a `NONE` line are a validation error (V1E021).
`NONE` is matched case-insensitively. A `NONE` line does not count
toward the at-most-one limit in §§6.7–6.9; a `NONE` line coexisting
with real cues of the same type in the SAME scope is a validation
error (V1E024, §8.2, §10.2).

### 6.7 AMBIENCE

Syntax:

```text
AMBIENCE: <name> | MODE: <LOOP|ONCE>
AMBIENCE: NONE
```

At most one `AMBIENCE:` line per SCOPE: one per scene for scene-level
lines, one per shot for shot-level lines; a second line in the same
scope is a validation error (V1E006). Lines in different shots of one
scene do not conflict. `MODE` defaults to `LOOP`. `AMBIENCE: NONE` (no
segments, §6.6) means the scope has no ambience. `NONE` is matched
case-insensitively.

### 6.8 BGM and MUSIC

Syntax:

```text
BGM: <name> | INTENSITY: <LOW|MEDIUM|HIGH>
MUSIC: <name> | INTENSITY: <LOW|MEDIUM|HIGH>
BGM: NONE
```

`MUSIC:` is a legacy alias of `BGM:` (§3.4): both keys write the same
scene field. At most one BGM/MUSIC line per SCOPE (one per scene for
scene-level lines, one per shot for shot-level lines); a second line
under either key in the same scope is a validation error (V1E006).
`INTENSITY` defaults to `MEDIUM`. `BGM: NONE` (equivalently
`MUSIC: NONE`; no segments, §6.6) means the scope has no background
music. `NONE` is matched case-insensitively.

### 6.9 MEME

Syntax:

```text
MEME: <name> | TRIGGER: ... | GAIN_DB: ... | PRIORITY: ...
MEME: NONE
```

Legacy meme cues. The parser records them as data only: it MUST NOT
resolve meme files, and it MUST NOT treat a missing meme file as a parse
error. Subkeys:

| Subkey | Required | Default | Values |
|---|---|---|---|
| `TRIGGER` | No | — (absent) | Free text, or a LINE_ID |
| `GAIN_DB` | No | — (absent; no default defined) | Float (dB); non-numeric: V1E008 |
| `PRIORITY` | No | `OPTIONAL` | Enum: `REQUIRED`, `OPTIONAL` |

At most one `MEME:` line per SCOPE (one per scene for scene-level
lines, one per shot for shot-level lines); a second line in the same
scope is a validation error (V1E006). `MEME: NONE` (no segments, §6.6)
means the scope has no meme.
Whether and how recorded meme cues are rendered is governed by the
header `MEME_POLICY` and `MEME_MAX_PER_MINUTE` at the audio stage
(§10.4). `MEME: NONE` is the explicit way to forbid memes in a scene
whose header policy would otherwise allow them.

Note: the fixture (§3.5) also uses `MEME_NOTE:` lines. `MEME_NOTE` is a
supported legacy scene field, defined in §6.13: it is parsed into the
scene's `meme_note` field, kept as data, and never spoken.

### 6.10 VFX

Syntax:

```text
VFX: <name> | TRIGGER: ...
VFX: <name one>; <name two>
```

Multiple `VFX:` lines are allowed, and a single line MAY list several
VFX names separated by `;`. When `;`-separated names are used, no
`TRIGGER` segment may be present on that line (a trigger applies to a
single named effect); combining `;` names with a `TRIGGER` segment is a
validation error (V1E019). `TRIGGER` follows the §6.6 resolution rule.
The SHOT `VFX` field (§5.5) accepts the `;`-separated names form or a
bullet list (§2.8).

### 6.11 TRANSITION

Syntax: `TRANSITION: <value>`

The scene transition. This is the SAME field as the SCENE `TRANSITION`
field: it MAY appear among the scene fields or as a content line at the
end of the scene, with identical meaning (§5.4). Inside SHOT context it
still attaches to the enclosing scene (§2.5).

In legacy documents the value MUST be one of the §5.4 enum
(`CUT`, `DISSOLVE`, `FADE`, `FADE_TO_BLACK`, `MATCH_CUT`, `WIPE`); any
other value is V1E007. In new-dialect documents (§3.3) the value is
preserved VERBATIM with no enum validation (for example `HARD_CUT`,
`CUT_TO_BLACK`). In both dialects, the same value written twice is
allowed; two DIFFERENT values are a duplicate-field error (V1E006),
with the first value kept.

### 6.12 VOICE_NOTE

Syntax: `VOICE_NOTE: <free text>`

A production directive about voice delivery. It is free text, kept
verbatim, associated with the enclosing scene or shot. It is NEVER
spoken and MUST NEVER be passed to TTS. Multiple `VOICE_NOTE:` lines
are allowed and are ordered.

### 6.13 MEME_NOTE

Syntax: `MEME_NOTE: <free text>`

A supported legacy scene field (coordinator decision, 2026-11-12
reconciliation; see Appendix B item 1, resolved). The author uses it to
record why memes are used — or why they MUST NOT be used — in a serious
scene: it is the upstream "Rule 9" justification, kept as data. The
value is free text, kept verbatim, stored in the scene's `meme_note`
field with its line number. At most one `MEME_NOTE:` line per scene; a
second line is a duplicate-field error (V1E006). It is NEVER spoken,
MUST NEVER be passed to TTS, and MUST NEVER be discarded or moved to
`unsupported_fields`. It does not by itself add, remove, or rate-limit
any meme cue; meme rendering is governed by §10.4.

---

## 7. LINE_ID rules and spoken-text integrity

### 7.1 LINE_ID assignment

- Every spoken line (every `NARRATION:`, `DIALOGUE:`, and bare-speaker
  line, in any scene or shot) gets exactly one LINE_ID.
- Explicit form: `NARRATION [Lnn]: ...` or `DIALOGUE [Lnn]: ...`, where
  `Lnn` is the letter `L` followed by digits; or `LINE_ID: <id>` in a
  spoken sub-block (§§6.1–6.2), where `<id>` is kept VERBATIM (for
  example `EP01_FP_01`). Bare speaker lines cannot carry an explicit
  LINE_ID. The canonical form for `L`-ids is `L` followed by the
  number zero-padded to three digits (`L001`, `L002`, ...); numbers
  above 999 keep all their digits (`L1000`). Explicit `L`-ids are
  normalised to canonical form (`[L2]` becomes `L002`). Non-`L` ids
  are never normalised.
- Automatic form: spoken lines without an explicit id receive `L001`,
  `L002`, ... in DOCUMENT ORDER across the whole document (not
  per-scene). The auto counter starts at 1 and skips numbers already
  claimed by earlier explicit ids; an explicit id that equals an
  already-assigned id is a duplicate-LINE_ID error (V1E005).
- LINE_IDs are unique across the whole document (compared
  case-insensitively). Duplicate explicit ids are a validation error
  (V1E005). A malformed explicit id (for example `[LX]` or a missing
  closing bracket) is a validation error (V1E019).
- LINE_IDs are the stable keys that bind spoken lines to generated
  speech timing (§1.2 principle 7) and to `TRIGGER` references (§6.6,
  §6.9, §6.10). They MUST be preserved unchanged from parse through
  TTS, timeline, subtitles, and QA.

### 7.2 Spoken-text integrity

- Spoken text is NEVER rewritten: no case changes, no punctuation fixes,
  no word substitutions, no translation, no trimming beyond the §2.4
  line-level trim. The ONE exception is the sub-block `TEXT:` quote
  rule (§6.1): exactly one layer of matching surrounding quotes is
  stripped, and the inner text is then verbatim. The text sent to TTS
  and the text shown in subtitles MUST be the parsed spoken text, byte
  for byte apart from subtitle phrase-splitting that preserves the
  words.
- Only spoken lines (§7.1) are ever sent to TTS. No other line kind —
  `VISUAL:`, `ACTION:`, `CAMERA:`, `VOICE_NOTE:`, audio cues, headers,
  block fields — is spoken content.
- Production tags inside spoken text are a validation error (V1E016).
  The forbidden tags are exactly: `LOCATION:`, `ACTION:`, `CAMERA:`,
  `SFX:`, `GAIN_DB:`. If any of these strings appears inside a spoken
  line's text, the document is invalid and the error MUST name the line
  number and the tag found. (This is the upstream "Rule 2" check,
  restricted to the five tags listed here; see Appendix A.)
- Spoken lines MUST NOT be rewritten to fix a V1E016 error. The author
  fixes the script; a new snapshot is created (§9).

---

## 8. Validation rules, error codes, and unsupported-field policy

### 8.1 Validation model

Validation has two phases, both reporting line numbers and error codes:

1. **Structural parsing** — line model (§2), block structure, header
   syntax, `KEY: value` shape. Syntax failures are errors (V1E019).
2. **Semantic validation** — duplicates, enums, ranges, required fields,
   and reference resolution over the whole parsed document (§§4–7).

All errors found SHOULD be reported together (not just the first), each
with its 1-based source line number, its error code, and a human-readable
message naming the field and value involved. The frontend MUST display
validation errors with line numbers and explain them BEFORE any render
is started. A document with ANY validation error is invalid and MUST NOT
proceed to production.

### 8.2 Error codes

These codes are defined by this specification (the brief required error
codes without enumerating them; see Appendix A). Parsers MUST emit
exactly these codes for the conditions listed. Messages SHOULD include
the offending value and the expected values or range.

| Code | Condition |
|---|---|
| V1E001 | Duplicate CHARACTER name, PROP name, or IDENTITY_ID |
| V1E002 | Duplicate LOCATION id |
| V1E003 | Duplicate SCENE number (by numeric value) |
| V1E004 | Duplicate SHOT id within the same scene |
| V1E005 | Duplicate LINE_ID |
| V1E006 | Duplicate single-valued field in the SAME block-context (the same key in different blocks is legal, §4), duplicate header key, duplicate singleton block (PROJECT, VISUAL_STYLE, GLOBAL_AUDIO, GLOBAL_NEGATIVE_CONSTRAINTS, QA, OUTPUT, END_CARD), duplicate subkey on one pipe-segment line or in one SFX sub-block, duplicate COSTUME_CHANGE for the same scene, second AMBIENCE/BGM/MEME line in the same scope (§§6.7–6.9), or conflicting TRANSITION values (§6.11) |
| V1E007 | Invalid enum value (ASPECT_RATIO, MEME_POLICY, TRANSITION in legacy documents, CAMERA_MOVEMENT failed enum attempt, SFX/MEME PRIORITY, AMBIENCE MODE, BGM INTENSITY, RESOLUTION, FPS, FORMAT) |
| V1E008 | Invalid number (non-numeric value, or negative value where 0 or greater is required: MEME_MAX_PER_MINUTE, MAX_HARD_FAILS, gains) |
| V1E009 | HEAD_RATIO outside 0.33–0.35 inclusive (including the forbidden upstream default 0.42) |
| V1E010 | MIN_SCORE outside 0–10 inclusive |
| V1E011 | Invalid boolean value (QA flags) |
| V1E012 | Invalid duration value (not AUTO — where AUTO is allowed — nor a non-negative number of seconds, nor a TARGET_DURATION range, nor an `Ns` value where `Ns` is accepted: END_CARD DURATION in new-dialect documents, POST_DIALOGUE_PAUSE, END_HOLD) |
| V1E013 | Missing required SHOT TYPE (legacy documents, or new-dialect shots with neither TYPE nor CAMERA) |
| V1E014 | Unknown SHOT TYPE value |
| V1E015 | Undeclared speaker in a DIALOGUE, bare-speaker, or spoken sub-block line |
| V1E016 | Production tag inside spoken text (§7.2) |
| V1E017 | OUTPUT MASTER value other than MANUAL_ONLY |
| V1E018 | Unresolvable reference (PROP OWNER, SHOT SUBJECT, EXPRESSION character prefix, COSTUME_CHANGE scene, PROP SCENES entry, SHOT LOCATION_OVERRIDE, PRIMARY_CHARACTER) |
| V1E019 | Malformed syntax (block header missing its name/id/number, SHOT outside a SCENE, COSTUME_CHANGE bad format, PROP SCENES bad format, malformed LINE_ID, malformed DIALOGUE form, empty spoken line, multiple VFX names combined with one TRIGGER, empty block name, spoken sub-block missing TEXT or (for DIALOGUE) SPEAKER, non-blank content after the END STUDIO SCRIPT V1 terminator) |
| V1E020 | V1 document contains no SCENE |
| V1E021 | NONE line carrying pipe segments (SFX / AMBIENCE / BGM / MEME) |
| V1E022 | Unresolvable TRIGGER (LINE_ID or action text) — raised at the timeline stage, not at parse time; parse records the trigger verbatim |
| V1E023 | V1 document contains no spoken lines |
| V1E024 | NONE directive coexists with real cues of the same type in the SAME scope (scene-level NONE forbids cues anywhere in the scene; shot-level NONE forbids cues only in that shot, §10.2) |
| V1E025 | First-person prerequisite rule violated (§16): an external-narrator spoken line in a document that declares first-person mode, or an EXTERNAL_NARRATOR declaration other than NONE. In legacy documents that do NOT declare first-person mode, narrator lines are allowed and produce exactly one V1E025 WARNING (line 0) noting the rule |

### 8.3 Unsupported-field policy

- Any `KEY: value` line whose key is not defined for its context, any
  unknown pipe-segment subkey, any content line outside a SCENE, any
  bullet line with no attachable context (§2.8), and any other
  non-blank, non-comment, non-separator line that matches no rule in
  this specification MUST be recorded in the parse result's
  `unsupported_fields` list, with the key (if any), the full line text,
  the block context, and the 1-based source line number.
- Unsupported fields are NEVER silently discarded. They MUST be surfaced
  in the parse result and in the frontend review display, so the author
  can see exactly what was not understood.
- An unsupported field on its own does NOT fail validation: the document
  may still proceed, with the unsupported data visible for review. It
  MUST NOT be treated as spoken text, MUST NOT be passed to TTS, and
  MUST NOT change any parsed field.
- The `STYLE`-vs-`VISUAL_STYLE` loser value (§4) and scene-only keys in
  SHOT context (§2.5) are recorded under this policy. (`MEME_NOTE:` is
  NOT recorded here: it is a defined scene field, §6.13.)

---

## 9. Snapshot and SHA-256 integrity

- On ingest, the frontend/parser MUST create ONE immutable script
  snapshot: the exact raw input text, plus its SHA-256 hash.
- The hash is the SHA-256 digest of the exact raw input bytes as received
  by the parser, rendered as 64 lowercase hexadecimal characters. It is
  computed over the raw text BEFORE any parsing, trimming, or
  normalisation (line-ending and BOM handling in §2.1 affect parsing
  only, never the hashed bytes).
- The snapshot and its hash MUST be used end to end, unchanged, through
  every stage: frontend → parser → planner → scene package → TTS →
  animation → audio → renderer → QA → Drive. Every stage that consumes
  script data MUST record the snapshot hash it consumed.
- Any edit to the script creates a NEW snapshot with a NEW hash, and the
  document MUST be re-validated from scratch. Stages MUST NEVER mix data
  from two different snapshots in one production.
- QA MUST verify that the artifacts it checks were produced from the
  snapshot hash recorded for the job. A hash mismatch is a hard failure:
  the Draft is invalid and MUST be re-rendered from the correct snapshot.
- The hash MUST be stored in the job manifest and in QA artifacts so a
  Draft can always be traced back to the exact script text that produced
  it.

---

## 10. Audio bus model, SFX NONE semantics, and the no-invented-sound rule

### 10.1 Buses

Audio is mixed on six separate buses. The `GLOBAL_AUDIO` gains (§5.6)
apply per bus. No bus may be merged into another before the final mix.

| Bus | Source in the script | Gain field (default) |
|---|---|---|
| narration | `NARRATION:` lines | `NARRATION_GAIN_DB` (0) |
| dialogue | `DIALOGUE:` / bare-speaker lines | `DIALOGUE_GAIN_DB` (0) |
| ambience | `AMBIENCE:` lines | `AMBIENCE_GAIN_DB` (-18) |
| foley | (no V1 authoring syntax; see below) | `FOLEY_GAIN_DB` (-12) |
| sfx | `SFX:` lines | `SFX_GAIN_DB` (-6) |
| bgm | `BGM:` / `MUSIC:` lines | `BGM_GAIN_DB` (-18) |

The foley bus exists in the mix model, but V1 defines NO syntax for
authoring foley cues. Therefore no foley sound may be added from script
data in V1; `FOLEY_GAIN_DB` configures the bus for future use only. (See
Appendix B.)

### 10.2 Explicit-none semantics

- `SFX: NONE`, `AMBIENCE: NONE`, `BGM: NONE`, and `MEME: NONE` are
  EXPLICIT prohibitions, recorded as explicit-none values in the parsed
  scene — distinct from "no line present". An explicit none MUST survive
  into the storyboard review display and the audio timeline, and MUST
  forbid even pipeline-default sounds of that kind in its scope.
- NONE directives are SCOPED. A scene-level NONE (written outside any
  SHOT) forbids cues of that type anywhere in the scene. A shot-level
  NONE (written inside a SHOT) forbids cues of that type ONLY in that
  shot; cues of the same type in other shots of the same scene are
  unaffected. A scene that declares an explicit none AND contains real
  cues of the same type in the SAME scope is invalid (V1E024, §8.2):
  the author must remove either the none or the cues.
- An absent line means "nothing scripted". It likewise results in no
  sound of that kind (§10.3); the difference from explicit none is one
  of author intent, preserved for review and for any future feature that
  might add default sounds: explicit none always wins within its scope.

### 10.3 No invented sound

- SFX MUST be attached to meaningful scripted events (their `TRIGGER`s).
  The pipeline MUST NOT automatically add transition whooshes, meme
  sounds, footsteps, impact sounds, or any other sound that the script
  does not require — in any scene, and especially in a scene with an
  explicit `NONE`.
- Overlapping duplicate sound events MUST be deduplicated in the audio
  timeline.
- Narration and dialogue MUST remain intelligible: background music is
  ducked by `BGM_DUCKING_DB` during speech, and the final mix MUST
  respect `MASTER_LIMIT_DB` as its ceiling. SFX and ambience MUST NOT
  overpower speech.
- A trigger that cannot be resolved against real speech timing or the
  animation timeline is an error or an explicit review requirement
  (V1E022). A timestamp MUST NEVER be silently invented.

### 10.4 Meme policy

- `MEME_POLICY: NONE` — no meme cue is rendered, however many `MEME:`
  lines the script contains (they remain recorded as data).
- `MEME_POLICY: CONTEXTUAL` (default) — scripted meme cues render,
  subject to the `MEME_MAX_PER_MINUTE` rate limit, enforced at the audio
  / QA stage against the real timeline duration.
- `MEME_POLICY: ALWAYS` — all scripted meme cues render, subject to the
  same rate limit.
- `MEME: NONE` in a scene forbids memes in that scene under every policy.
- Meme rendering decisions MUST be visible in the review display: which
  cues rendered, which were suppressed by policy or rate limit, and why.

---

## 11. LOCATION semantics

### 11.1 Environment specifications compose the render

A LOCATION block is a reusable environment specification. The scene
package and renderer MUST compose the rendered environment FROM the
LOCATION data: `PERIOD`, `GEOGRAPHY`, `ARCHITECTURE`, `FEATURES`,
`FOREGROUND`, `MIDGROUND`, `BACKGROUND`, `LIGHTING`, `WEATHER`, and
`PALETTE`. Distinct LOCATION blocks MUST produce visibly distinct
environments. Reusing the same LOCATION id in several scenes MUST
produce the same environment specification in each (consistency); using
different LOCATION ids MUST NOT produce the same backdrop.

### 11.2 Distinctive features must be visible

Every `FEATURES` entry names something distinctive about the location.
The render MUST make the distinctive features visible in the scene —
they are the reason the location is itself and not any other place.
A render in which no declared feature can be seen is a defect to be
reported, not an acceptable simplification. Likewise, `FOREGROUND`,
`MIDGROUND`, and `BACKGROUND` MUST each contribute visible depth layers;
a flat single-layer backdrop does not satisfy a three-layer
specification.

### 11.3 Never substitute; forbidden means forbidden

- NEVER substitute one location for another merely because an existing
  background is available. If a LOCATION cannot be rendered from its own
  data, the production MUST report the blocker explicitly and stop or
  request review — it MUST NOT quietly render a different place.
- Every `FORBIDDEN` entry MUST NOT appear in the rendered scene. A
  forbidden element appearing in a render is a defect.
- Factual details in a LOCATION spec (period, geography, architecture)
  SHOULD be researched and verified when the production requires it;
  verification is a planner/pipeline responsibility (Phase B), not a
  parser rule. Unverifiable details MUST be flagged for review rather
  than silently replaced with familiar ones.

### 11.4 Inline LOCATION text (legacy)

A SCENE `LOCATION:` value that matches no LOCATION id is legacy inline
free text (§5.4). It is kept verbatim and passed to the scene package as
an unstructured location description. The no-substitution rule applies
equally: the renderer MUST render what the text describes, and MUST
report it if it cannot, rather than substituting an available backdrop.
Inline text carries no structured layers, palette, or forbidden list;
authors who need those SHOULD declare a LOCATION block.

### 11.5 Why this matters

Unrelated scripts MUST NOT converge on one generic street, one generic
room, or one generic backdrop. The diversity requirement (Mai, 2026-11-12:
every script's scenes and characters must be diverse, each with its own
distinctive traits) is a property of the DATA — distinct LOCATION,
CHARACTER, and PROP blocks per script — and the pipeline MUST honour the
data instead of collapsing it onto a single reused layout or a fixed
prop vocabulary. A prop or feature declared in the script but absent
from the render (for example a story-central prop that never appears,
or a character trait with no visible effect) is a pipeline defect to be
reported with the scene and line numbers involved.

---

## 12. CHARACTER semantics

### 12.1 Identity preserved across scenes

- A CHARACTER's identity is its `IDENTITY_ID` (default: its block id,
  §5.1; in the legacy dialect the block id equals the name). The same
  identity MUST look like the same character in every scene: same
  proportions, same face system, same `APPEARANCE` and `TRAITS`
  rendering, same voice. Identity MUST NOT drift between scenes.
- Distinct CHARACTER blocks MUST produce visibly distinct characters.
  `TRAITS`, `APPEARANCE`, and `COSTUME` are the data that make
  characters different from each other; a render in which two declared
  characters differ only by shirt colour has not honoured the data.
  Traits with no visible effect (for example age traits that leave a
  character indistinguishable from the others) are defects to report.
- `HEAD_RATIO` is locked (§1, §5.1): 0.34 by default, 0.33–0.35 only.
  No character, scene, or shot may use any other head ratio.

### 12.2 Costume changes

`COSTUME_CHANGE` lines change what a character WEARS in the listed
scene; they MUST NOT change the character's identity, proportions, face,
or voice. The default `COSTUME` applies in every scene without a
`COSTUME_CHANGE` for that character. A costume change for a scene the
character does not appear in is valid but has no visible effect; it is
NOT an error.

### 12.3 Actions and expressions

- `ACTION:` and `EXPRESSION:` directives connect to the existing
  articulated animation system. The animation stage MUST attempt the
  scripted action or expression from the script data.
- Unsupported actions MUST be reported EXPLICITLY (action text, scene,
  shot, and line number) as review requirements. They MUST NEVER be
  silently replaced by a camera pan, zoom, or any other camera move,
  and MUST NEVER be silently dropped. Camera movement is not character
  animation.
- The same rule applies to expressions: an expression the face system
  cannot perform MUST be reported, not replaced by a cutaway or a
  camera move.
- `ACTION:` / `EXPRESSION:` text is data, not a fixed vocabulary: the
  specification defines no closed list of allowed actions. The
  animation stage owns the supported-action vocabulary and the
  unsupported-action report (Phase B); this specification only requires
  that the report exists and that substitution never happens silently.

### 12.4 Voice

`VOICE_ID` (else `VOICE`, else legacy `VOICE`) and `VOICE_TONE` (else
legacy `VOICE_STYLE`) drive TTS voice selection and delivery for that
character's spoken lines. The same character MUST sound like the same
voice across scenes. In first-person documents (§16) `NARRATION` lines
are spoken by the primary character in that character's voice; there
is no narrator voice. Voice resolution for legacy `Narrator` lines is
a pipeline concern (see Appendix B); the parser records the speaker as
`Narrator` and preserves `VOICE_NOTE:` lines verbatim.

---

## 13. Machine-readable schema reference

- The machine-readable schema for STUDIO SCRIPT V1 lives at
  `docs/studio_script_v1.schema.json` (repository-relative:
  `video-16x9-v2/docs/studio_script_v1.schema.json`).
- The schema is OWNED BY THE PARSER STREAM. It is not part of this
  Phase A documentation deliverable; the parser stream creates and
  maintains it, and it lives alongside this specification in `docs/`.
- The schema describes the PARSED-OUTPUT structure (the JSON object a
  conforming parser produces): header, characters, locations, props,
  scenes (with shots, spoken lines with LINE_IDs, and audio cues),
  global audio, negative constraints, QA, output, end card, snapshot
  hash, `unsupported_fields`, and validation errors with line numbers
  and codes. The line grammar in §§2–8 of this specification is
  authoritative for the TEXT format; the schema MUST mirror it and MUST
  NOT define a different text syntax.
- JSON field naming in the schema SHOULD follow lower_snake_case forms
  of the names used in this specification (for example `head_ratio`,
  `meme_max_per_minute`, `snapshot_sha256`). Exact JSON field names are
  the parser stream's decision, recorded in the schema itself.
- In case of any conflict between the schema and this specification, this
  specification wins and the schema MUST be fixed. The schema MUST be
  versioned with the specification (§14): a schema that validates
  documents this specification rejects (or vice versa) is a bug in the
  schema.

---

## 14. Versioning and changelog

- This is STUDIO SCRIPT V1, dated 2026-11-12. The version is identified
  by the `# STUDIO SCRIPT V1` marker (§3.2) and by this document.
- Additive changes within V1 (new OPTIONAL fields, new OPTIONAL blocks,
  new enum values) are allowed ONLY by amending this specification, with
  a changelog entry below and a matching schema update. Additive changes
  MUST NOT invalidate any document that was valid before them.
- Breaking changes (removing or redefining fields, changing defaults,
  narrowing enums, changing LINE_ID or snapshot rules) REQUIRE a new
  major version with a new marker; they MUST NOT be smuggled into V1.
- The upstream V5.1 parser's behaviour (including its 0.42 head-ratio
  default and its own header defaults) is NOT part of V1 and MUST NOT be
  treated as V1 behaviour. Where V1 deliberately differs from upstream,
  this specification says so (§1 head-ratio lock, §4, §7.2).

### Changelog

| Version | Date | Change |
|---|---|---|
| V1 | 2026-11-12 | Initial specification: full grammar (headers, CHARACTER, LOCATION, PROP, SCENE, SHOT, GLOBAL_AUDIO, GLOBAL_NEGATIVE_CONSTRAINTS, QA, OUTPUT, END_CARD), content lines, LINE_ID and spoken-text integrity rules, validation error codes V1E001–V1E022, unsupported-field policy, snapshot/SHA-256 rule, six-bus audio model, LOCATION/CHARACTER semantics, head-ratio lock at 0.34 (0.33–0.35). Derived from the standing directive in `docs/DIRECTIVE_STUDIO_SCRIPT_V1.md`. |
| V1 | 2026-11-12 | Phase A reconciliation: parser emits exactly the §8.2 codes (V1E001–V1E024); new codes V1E023 (no spoken lines) and V1E024 (NONE coexists with real cues, an error); V1E019 row extended (empty spoken line, malformed DIALOGUE, PROP SCENES format, multiple VFX names + one TRIGGER); header defaults removed (absent PROJECT/GENRE/VISUAL_STYLE/TONE = unspecified); STYLE/VISUAL_STYLE single `visual_style` field; `MEME_NOTE` promoted to a defined legacy scene field (§6.13, Appendix B item 1 resolved); duration unit suffixes rejected (V1E012) and END_CARD DURATION rejects AUTO; V1E006 duplicate detection and V1E021 defined in the parser; TRIGGERs recorded verbatim at parse time (V1E022 timeline-stage only); unresolvable references (V1E018) are errors, per this specification. Schema updated to match (nullable unspecified headers, no `style` field, V1E code pattern). |
| V1 | 2026-11-12 | New §15, planner trait contract (Gemini sketcher): structured trait-block shapes the planner must emit and the pipeline must consume, grounded in the V1 parsed-output shapes and the existing planner / scene-package / animation-primitive vocabulary. Phase B interface requirement; no planner-output JSON Schema is defined in Phase A. |
| V1 | 2026-11-12 | Phase B Stage 3 dialect extension: new-dialect forms (bare marker line, bare block headers, `SCENE:` / `SHOT:` headers, `⸻` separators, `END STUDIO SCRIPT V1` terminator, bullet lists, spoken and SFX sub-blocks, PROJECT and VISUAL_STYLE blocks, extended CHARACTER / LOCATION / PROP / SCENE / SHOT / GLOBAL_AUDIO / QA / OUTPUT / END_CARD vocabularies); document-wide dialect determination with exactly three dialect-gated rules (§3.3: verbatim TRANSITION, TYPE-optional-with-CAMERA shots, `3s` END_CARD durations); per-block duplicate scoping (V1E006); CAMERA-vs-TYPE distinction and the CAMERA_MOVEMENT prose rule (§5.5); TARGET_DURATION ranges; scoped NONE semantics (§10.2) and per-scope AMBIENCE/BGM/MEME limits (§§6.7–6.9); verbatim non-L LINE_IDs; new §16 first-person prerequisite rule with error V1E025 (error in first-person documents, one line-0 warning in legacy documents with narrator lines); LOCATION ref-vs-declare fix; `to_dict()` additions (`id`/`name`/`is_extra`/`fields` on blocks, `speaker_id`/`lip_sync`, structured SFX sub-fields, `duration_sec`, `expected_counts`, first-person meta). Schema and template updated to match. The head-ratio lock (0.33–0.35, default 0.34) is unchanged. All Phase A documents that were valid remain valid; the sole behaviour adjustment is the V1E025 legacy-narrator warning. |

---

## 15. Planner trait contract (Gemini sketcher)

### 15.1 Role, standing requirement, and status

Gemini is the SKETCHER that supplies the distinctive traits (Mai,
2026-11-12 08:25, "đặc biệt lưu ý" — pay special attention; recorded in
the standing-context section of `docs/DIRECTIVE_STUDIO_SCRIPT_V1.md`):
per-character actions, costumes, and appearance; per-location
distinctive features; SFX; music; and special actions. Gemini supplies
these as STRUCTURED per-script trait data; the general engine/pipeline
consumes the data and renders. This is the core of the V1
LOCATION/CHARACTER systems (§§11–12). It is a standing requirement: it
does not expire when the current implementation round ends.

STATUS: this section is a Phase B INTERFACE REQUIREMENT. It defines the
shapes the planner MUST emit and the pipeline stages MUST consume. It
does NOT describe already-implemented behaviour: the current planner
(`ai_clip_studio/gemini_planner.py`, `ai_clip_studio/planner_fallback.py`)
consumes free-form / structured-Vietnamese scripts through
`vi_script_parser` / `segment_script`, not V1 documents, and its output
shapes are the CURRENT vocabulary this contract aligns to (see §15.7
for the gaps). No planner-output JSON Schema is defined in Phase A; if
one is needed, it is Phase B work and MUST mirror this section, not
define a second vocabulary.

Ground-truth rule (unchanged from the current planner's safety rule):
the parsed V1 document (`to_dict()` output, §§4–8) is GROUND TRUTH.
The planner only ENRICHES it. Spoken lines, speakers, scene order, and
LINE_IDs always come from the parsed document; any character, scene,
shot, or spoken line the planner invents MUST be dropped by validation.
The planner's input is the V1 parsed document plus its `snapshot_hash`;
its output MUST record the `snapshot_hash` it consumed (§9), and stages
MUST NEVER mix trait data from two different snapshots.

Planner labelling: output produced by a real Gemini call is labelled
`planner: "gemini"` with the model name; output from the deterministic
local planner is labelled `planner: "fallback"` with the reason, and
MUST stay clearly labelled as fallback (§15.6). The labels are the
current `PLANNER_GEMINI` / `PLANNER_FALLBACK` values in
`gemini_planner.py`.

Field-name rule: trait blocks reuse the V1 `to_dict()` field names
(§13, `docs/studio_script_v1.schema.json`) and the existing planner /
scene-package / animation-primitive names EXACTLY. Where a planner
render field collides with a V1 field name, the planner fields live
under a `render_traits` object (§§15.2–15.3) so neither vocabulary is
renamed. No second competing vocabulary may be invented.

### 15.2 Character trait blocks

One block per declared CHARACTER, keyed by identity. The V1 fields are
copied verbatim from the parsed CHARACTER block; the planner ADDS the
`render_traits` object and the `actions` list. The planner MUST NOT
rename, drop, or contradict the V1 fields.

```json
{
  "identity_id": "V1 CHARACTER identity_id (§5.1, §12.1)",
  "name": "declared CHARACTER name",
  "role": "V1 ROLE, verbatim",
  "appearance": "V1 APPEARANCE, verbatim",
  "traits": ["V1 TRAITS, verbatim, in order"],
  "costume": "V1 COSTUME free text, verbatim",
  "costume_changes": [{"scene_number": 1, "outfit": "V1 outfit", "line": 12}],
  "voice": "V1 VOICE, verbatim",
  "voice_style": "V1 VOICE_STYLE, verbatim",
  "head_ratio": 0.34,
  "actions": ["special-action directives for this character, §15.5"],
  "render_traits": {
    "description": "short appearance/personality description",
    "voice_hint": "voice hint, e.g. a gender/narrator hint",
    "template": "male | female | child | elderly",
    "body_variant": "slim | standard | sturdy",
    "costume": "none | dress | uniform (render garment shape; NOT the V1 costume text)",
    "hair_style": "short | long | tuft | side_part | none",
    "hat": "none | bowler",
    "moustache_style": "none | toothbrush | handlebar | full",
    "glasses": false,
    "jacket_color": "#RRGGBB",
    "height_px": 540
  }
}
```

The `render_traits` field names and value sets are the current
Gemini-planner prompt/merge vocabulary (`gemini_planner.py`: `template`,
`body_variant`, `costume`, `hair_style`, `hat`, `moustache_style`,
`glasses`, `jacket_color`, `description`, `voice_hint`) plus `height_px`
from the deterministic planner. `head_ratio` is locked (§1): trait data
MUST NOT carry any other head ratio, and no trait may change identity,
proportions, face, or voice across scenes (§12.1–12.2). Costume changes
change ONLY what the character wears in the listed scene.

### 15.3 Location trait blocks

One block per declared LOCATION, keyed by its id. The V1 fields are
copied verbatim from the parsed LOCATION block; the planner ADDS the
`render_traits` object. Scenes reference the block through the V1
`location_ref` (§5.4); scenes with inline `location_text` (§11.4) have
no trait block and MUST be rendered from the inline text, never
substituted (§11.3).

```json
{
  "location_id": "declared LOCATION id",
  "scene_numbers": [1, 2],
  "name": "V1 NAME, verbatim",
  "period": "V1 PERIOD, verbatim",
  "geography": "V1 GEOGRAPHY, verbatim",
  "architecture": "V1 ARCHITECTURE, verbatim",
  "features": ["V1 FEATURES, verbatim, in order"],
  "foreground": "V1 FOREGROUND, verbatim",
  "midground": "V1 MIDGROUND, verbatim",
  "background": "V1 BACKGROUND, verbatim",
  "lighting": "V1 LIGHTING, verbatim",
  "weather": "V1 WEATHER, verbatim",
  "palette": ["V1 PALETTE, verbatim, in order"],
  "forbidden": ["V1 FORBIDDEN, verbatim, in order"],
  "render_traits": {
    "setting": "short setting description for the scene package",
    "location_keyword": "great_wall | eiffel_tower | rainy_street | street | generic",
    "mood": "warm | cold",
    "time_of_day": "day | night"
  }
}
```

The `render_traits` field names and value sets are the current
Gemini-planner location vocabulary (`gemini_planner.py`). The closed
`location_keyword` set is a CURRENT limitation, not the target: Phase B
MUST compose environments FROM the LOCATION trait data (features,
foreground/midground/background, lighting, palette, forbidden) per
§11.1–11.2, and a `location_keyword` MUST NEVER substitute one location
for another (§11.3). Scene-package consumption follows the existing
engine contract (`animation/scene_packages.py`): `build_scene(package,
camera, characters, **options)` over the `SCENE_PACKAGES` registry,
with new locations registered at runtime via `register_scene_package`
from structured trait data — the engine never hardcodes a new location.
Today the registry holds exactly one package (`rainy_street_night`); see
§15.7.

### 15.4 Audio events

Two lists, both derived ONLY from scripted cues. Every event carries
the V1 cue fields verbatim (cue name, trigger, priority/mode/intensity/
gain, scene, shot, line) plus the engine mapping. The planner MUST NOT
invent events: no event may be emitted for a scene with an explicit
`NONE` of that kind (§10.2), and no transition whoosh, footstep, meme,
or impact sound may be added beyond the script (§10.3).

SFX events (one per scripted `SFX:` cue):

```json
{
  "cue_type": "SFX",
  "name": "V1 cue name, verbatim",
  "trigger": "V1 TRIGGER, verbatim (LINE_ID or action text)",
  "priority": "REQUIRED | OPTIONAL",
  "scene_number": 1,
  "shot_id": "SH01 | null",
  "line": 42,
  "source_key": "SFX",
  "event": "engine event name (see below)",
  "note": "short planner note"
}
```

`event` uses the current Gemini SFX event vocabulary
(`gemini_planner.py`): `rain_start`, `foot_contact`, `door_contact`,
`door_rotation`, `paper_movement`, `object_impact`,
`character_reaction`. The planner MUST map each V1 cue name to an engine
event explicitly; a cue it cannot map MUST be reported as an unmapped
cue for review, never silently dropped and never given an invented
timestamp. `TRIGGER` resolution happens at the timeline stage against
real speech/animation timing; an unresolvable trigger is V1E022 (§8.2).

Music events (one per scripted `BGM:` / `MUSIC:` cue):

```json
{
  "cue_type": "BGM",
  "name": "V1 cue name, verbatim",
  "intensity": "LOW | MEDIUM | HIGH",
  "scene_number": 1,
  "shot_id": "SH01 | null",
  "line": 42,
  "source_key": "BGM | MUSIC",
  "note": "short planner note"
}
```

Music events honour `GLOBAL_AUDIO` gains and the six-bus mix model
(§10.1), including `BGM_DUCKING_DB` during speech and `MASTER_LIMIT_DB`
as the ceiling. There is currently NO engine event vocabulary for music
in the planner output (see §15.7): Phase B MUST define the mapping from
scripted music cues to rendered music explicitly; it MUST NOT reuse SFX
event names for music.

Timing rule: planner output MUST NOT include `at_seconds` or any other
estimated timestamp. Timing is assigned by the timeline stage from
measured TTS durations (§7, directive §4). (The current deterministic
planner's `audio_events` carry estimated `at_seconds` for lead-in
sizing only; the Phase B adapter MUST drop or relabel those estimates
so they are never treated as timeline truth.)

### 15.5 Special-action directives

One directive per scripted action/expression that the animation stage
must perform. The directive IS a `compile_actions` action dict
(`animation/primitives.py`) plus V1 provenance. Free prose stays in
`action_text` for review; it MUST NOT be passed to the animation stage
as a directive name.

```json
{
  "type": "primitive name, MUST be a PRIMITIVES key (see below)",
  "char": "identity_id of the acting character",
  "other": "identity_id of the second character (give_to only)",
  "start": null,
  "duration": 1.5,
  "from_x": 300, "to_x": 1180, "ground_y": 920,
  "target": [640, 920],
  "angle_keys": [],
  "facing": 1,
  "freq": 1.8, "amp": 0.1,
  "hand": "r",
  "scene_number": 1,
  "shot_id": "SH01 | null",
  "source_line": 42,
  "action_text": "V1 ACTION / EXPRESSION text, verbatim"
}
```

`type` MUST be one of the sixteen keys of `PRIMITIVES` in
`animation/primitives.py` (authoritative list; the module docstring
mentions further names that are NOT implemented): `walk_to`, `run_to`,
`turn_to`, `look_at`, `point_at`, `wave`, `reach_to`, `give_to`,
`shrug`, `cover_face`, `nod`, `sit_down`, `stand_up`, `idle`,
`bend_pick`, `kneel_pick`. Parameters follow `compile_actions`: `give_to`
takes `other`; `walk_to`/`run_to` take `from_x`/`to_x`/`ground_y`;
`look_at` takes `angle_keys`; `point_at`/`reach_to`/`bend_pick`/
`kneel_pick` take `target` (plus `ground_y`/`hand` for the pickups);
`turn_to` takes `facing`; `wave`/`shrug`/`cover_face`/`nod` take `freq`/
`amp` where defined; `sit_down`/`stand_up`/`idle` take `ground_y`.
`start` is assigned by the timeline stage; `duration` is the planner's
hint in seconds and MUST be reconciled with real speech timing.

Unsupported-action rule (§12.3): a scripted action or expression with
no `PRIMITIVES` mapping MUST be reported EXPLICITLY (action text, scene,
shot, line number) as a review requirement. It MUST NEVER be silently
replaced by a camera pan, zoom, or any other camera move, and MUST NEVER
be silently dropped. `compile_actions` raising `ValueError` for an
unknown action type is the engine side of this rule: the pipeline MUST
surface it as an unsupported-action report, not swallow it. Expression
directives (from `EXPRESSION:` lines) follow the same rule; there is
currently no expression-directive vocabulary in the primitives module
(see §15.7), so the face system owns that vocabulary in Phase B.

### 15.6 Fallback, generic consumption, and visibility proof

- **Fallback shape parity.** The fallback planner MUST emit the SAME
  trait-block shapes (§§15.2–15.5) with GENERIC traits derived only
  from V1 script data (for example jacket colours from the generic
  colour-word map in `planner_fallback.py`, default templates, and
  cue-derived audio events). It MUST stay clearly labelled `fallback`
  with the reason, and MUST NEVER be presented as Gemini output.
- **Generic consumption.** Scene package, character design, audio, and
  animation stages MUST consume trait blocks generically, keyed by
  `identity_id`, `location_id`, `scene_number`, `shot_id`, and
  `LINE_ID`. No per-story code, no per-story branches, no hardcoded
  character/location/prop names anywhere in the consuming stages. The
  GENERAL-CODE BOUNDARY stands: the engine is one general system; the
  per-script differences arrive ONLY as trait data.
- **Visibility proof.** Distinct traits per script MUST be visible in
  rendered frames. Phase B proves this with TWO unrelated scripts run
  through the same pipeline, with side-by-side frame evidence showing
  that distinct CHARACTER traits (appearance, costume, actions) and
  distinct LOCATION traits (features, layers, lighting, palette)
  produce visibly distinct characters and environments (§§11–12). A
  trait with no visible effect is a defect to report, not an acceptable
  simplification.
- **No silent substitution, anywhere.** The no-substitution rules of
  §§11.3 and 12.3 apply to the planner as well as to the renderer: the
  planner MUST NOT replace an unrenderable location with an available
  backdrop, an unsupported action with a camera move, or an unmapped
  cue with an invented sound. It reports the blocker; the pipeline
  stops or requests review.

### 15.7 Vocabulary gaps (Phase B requirements, not current behaviour)

The following gaps were found by comparing the V1 parsed-output shapes
(§13) with the current planner / scene-package / primitive vocabulary.
Each is a Phase B requirement. None of them is implemented behaviour,
and none of them may be papered over by inventing a second vocabulary.

1. **No V1 input adapter.** The planner consumes `vi_script_parser` /
   `segment_script` output, not V1 `to_dict()` documents. Phase B MUST
   add a V1→planner adapter that feeds the parsed document (with
   `snapshot_hash`, LINE_IDs, and block identities) to the planner and
   validates planner output against it.
2. **No identity-keyed character traits.** Planner characters are keyed
   by display `name` only; there is no `identity_id` keying and no
   per-scene costume trait (the planner's `costume` is a closed
   three-value render enum, unrelated to V1 `COSTUME` /
   `COSTUME_CHANGE` free text). Phase B MUST emit §15.2 blocks.
3. **No LOCATION-id keying; one scene package.** Planner locations are
   keyed by scene number with a closed five-value `location_keyword`
   set, and `SCENE_PACKAGES` holds exactly one package
   (`rainy_street_night`). No foreground/midground/background, palette,
   or forbidden data is consumed. Phase B MUST emit §15.3 blocks and
   build scene packages from LOCATION trait data generically.
4. **No music planning.** Planner output carries SFX events only; no
   `BGM`/`MUSIC` cue is planned, and no music event vocabulary exists.
   Phase B MUST emit §15.4 music events.
5. **No special-action directives.** Planner output carries `action_cues`
   string tags (from `segment_script`) and estimated lead-in seconds,
   not `compile_actions` directives. Two implemented primitives,
   `detour_walk` and `board_vehicle`, exist as functions but are NOT in
   the `PRIMITIVES` registry, so `compile_actions` cannot run them.
   Phase B MUST emit §15.5 directives and reconcile the registry.
6. **No expression vocabulary.** `animation/primitives.py` defines no
   face/expression directives; `EXPRESSION:` data has no animation
   mapping. The face system owns this vocabulary in Phase B (§12.3,
   Appendix B item 7).
7. **Shot-type vocabulary is a subset.** The Gemini prompt offers six
   shot types; the V1 vocabulary (§5.5) has eleven
   (`extreme_close_up`, `over_the_shoulder`, `shot_reverse_shot`,
   `medium_close_up`, `graphic_insert` are
   missing from the prompt). Phase B MUST use the full V1 vocabulary
   and key shot enrichment by V1 SHOT id, not by spoken-line index.
   (Resolved in Stage 3: both the free-form and V1 enrichment
   prompts now offer the full eleven-type vocabulary.)

---

## 16. First-person prerequisite rule

This rule is a PREREQUISITE ("rules tiên quyết", Mai, 2026-11-12
10:20): **all scripts are told in the first person; NEVER an external
narrator** ("không cần người dẫn truyện"). It overrides any
narrator-default behaviour in consumers: `NARRATION` blocks are spoken
by the primary character in first-person voice (that character's
`VOICE_ID`), never by a narrator voice, and no consumer may inject a
narrator sentinel, a narrator voice, or narrator lines into a
first-person production.

### 16.1 Declaring first-person mode

A document declares first-person mode when ANY of these holds:

- `STORYTELLING_MODE` (PROJECT block, §4.1) starts with `FIRST_PERSON`
  (case-insensitive); OR
- `EXTERNAL_NARRATOR` is `NONE`; OR
- `PRIMARY_CHARACTER` is present and is not `NONE` or empty.

New scripts MUST declare first-person mode: the template
(`docs/STUDIO_SCRIPT_V1_TEMPLATE.md`) declares all three. Documents
that declare none of the three are legacy documents (§16.3).

### 16.2 Validation in first-person documents (V1E025)

In a document that declares first-person mode:

- (a) ANY spoken line whose speaker is an external narrator is a
  validation error (V1E025): a line whose speaker is a narrator alias
  (§6.2), or a `NARRATION` line with no `SPEAKER` resolving to a
  declared CHARACTER. The error message MUST cite the prerequisite
  rule ("all scripts are first-person; an external narrator is
  forbidden").
- (b) `EXTERNAL_NARRATOR` declaring anything other than `NONE` is a
  validation error (V1E025, same citation), reported at the
  declaration's line.
- (c) `PRIMARY_CHARACTER` MUST reference a declared CHARACTER id (or,
  by §2.4 normalisation, a display name); otherwise it is an
  unresolvable-reference error (V1E018) at the declaration's line.

### 16.3 Legacy documents

When a document does NOT declare first-person mode, legacy behaviour is
preserved: narrator lines (speaker `Narrator`) are allowed and the
document may still be valid. The parser MUST emit exactly ONE warning
(code V1E025, line 0) noting the prerequisite rule, so that authors
see that new scripts must declare first-person mode. A legacy document
with no narrator lines gets no warning. The warning never fails
validation.

### 16.4 Consumer obligations

- TTS MUST read `NARRATION` lines in first-person documents with the
  speaking character's voice (`VOICE_ID`), on the narration bus
  (§10.1) with that character's delivery. It MUST NOT substitute a
  narrator voice.
- The adapter/pipeline MUST NOT inject a narrator character, narrator
  lines, or a narrator sentinel for first-person documents, and MUST
  NOT re-label character narration as narrator content.
- QA `EXPECTED_EXTERNAL_NARRATOR_LINES` (§5.8) MUST be `0` in
  first-person documents; the QA stage verifies the count from the
  parsed document.

---

## Appendix A. Rules defined by this specification where the brief was silent

The canonical grammar brief defined the format but left the following
points open. This specification defines them, as marked, so that the
parser, schema, tests, and frontend can implement one consistent
behaviour. The coordinator SHOULD confirm each item; any change requires
a specification amendment (§14), not a unilateral parser deviation.

1. **Error code values** (V1E001–V1E025, §8.2): the brief required codes
   but did not enumerate them. The code list in §8.2 is normative.
   V1E023–V1E024 were added by the 2026-11-12 Phase A reconciliation;
   V1E025 (first-person prerequisite rule, §16) was added by the
   Phase B Stage 3 dialect extension; see §14.
2. **Enum case-insensitivity** (§2.4): the brief normalised only SHOT
   `TYPE`. This specification matches ALL enums case-insensitively.
3. **Speaker/identifier normalisation** (§2.4): trim, collapse
   whitespace, Unicode casefold. Required for the fixture's bare
   dialogue lines (whose speaker spellings differ in case from the
   CHARACTER declarations) to validate.
4. **Narrator-alias precedence** (§6.2): aliases win over CHARACTER-name
   matching when both could apply.
5. **SHOT context termination and the TRANSITION exception** (§2.5).
6. **Duplicate single-valued fields are errors** (V1E006, §8.2),
   including duplicate header keys and duplicate singleton blocks;
   repeatable fields are listed per block.
7. **Empty-value handling** (§2.7).
8. **SCENE/SHOT `DURATION` default `AUTO`** (§§5.4–5.5) and **`MASTER`
   omission means `MANUAL_ONLY`** (§5.9).
9. **`STYLE` vs `VISUAL_STYLE` precedence** (§4): `VISUAL_STYLE` wins.
10. **Document-wide reference resolution and flexible block order**
    (§2.5): forward references allowed; non-scene blocks may precede or
    follow scenes.
11. **Marker tolerance and sticky detection** (§§3.2–3.3): trailing text
    after the marker allowed; V1 detection never falls back to free-form.
12. **LINE_ID details** (§7.1): canonical 3-digit padding (brief showed
    both `[Lnn]` and `L001`); explicit ids allowed on `DIALOGUE:` as
    well as `NARRATION:`; auto-counter interaction with explicit ids;
    document-wide uniqueness.
13. **`NONE` lines MUST NOT carry segments** (V1E021, §6.6).
14. **MEME `PRIORITY` enum** (`REQUIRED`/`OPTIONAL`, default `OPTIONAL`,
    §6.9) and **no default for MEME `GAIN_DB`** (§6.9).
15. **Pipe-segment subkey order** (any order) and **unknown subkeys**
    recorded under §8.3 (§6).
16. **BOM/CRLF handling** (§2.1) and **snapshot over raw bytes** (§9).
17. **Counts must be 0 or greater** (`MEME_MAX_PER_MINUTE`,
    `MAX_HARD_FAILS`, §§4, 5.8).
18. **SHOT id uniqueness scope** (within scene only, §5.5) and
    **LOCATION reference matching** (case-insensitive trimmed match,
    §5.4).
19. **Bare `EXPRESSION` reading** (§6.4): "bare" means an `EXPRESSION:`
    line without a character prefix, not a keyless line. Keyless lines
    are recorded under §8.3.
20. **Production-tag list restricted to five tags** (§7.2): the upstream
    check also flagged `MEME:`; this specification follows the brief's
    five-tag list exactly.
21. **Unsupported fields are non-fatal** (§8.3): recorded and surfaced,
    not validation errors.
22. **Meme rate-limit enforcement stage** (audio/QA stage, §10.4) and
    **V1E022 raised at the timeline stage** (§8.2).
23. **`END_SCRIPT` is a pure no-op**; `END_SCENE` closes context but
    carries no data (§2.3).
24. **No upstream header defaults inherited** (§4).
25. **`MEME_NOTE` is a defined legacy scene field** (§6.13), decided by
    the coordinator in the 2026-11-12 Phase A reconciliation: the
    parser behaviour (a supported `meme_note` scene field, never
    spoken, never discarded) is kept, and this specification was
    amended to define it. The upstream Rule 9 justification stays
    available as data. Resolves Appendix B item 1.
26. **Error severities settled by the reconciliation** (§8.2):
    unresolvable references (V1E018) and NONE coexisting with real cues
    (V1E024) are validation ERRORS, not warnings — this specification
    is authoritative over the original brief's "warning" wording for
    these conditions. Duplicate SHOT ids (V1E004) are likewise errors.
27. **Document-wide dialect determination** (§3.3, Stage 3): exactly
    three rules differ between the legacy and new dialects (verbatim
    TRANSITION, TYPE-optional-with-CAMERA, `3s` END_CARD durations);
    every other rule applies identically to both dialects.
28. **`CAMERA_MOVEMENT` prose rule** (§5.5, Stage 3): the lexical test
    (lowercase letters or spaces → prose; UPPER_SNAKE non-enum →
    V1E007) applies in both dialects.
29. **Scoped NONE semantics and per-scope cue limits** (§10.2,
    §§6.7–6.9, Stage 3): NONE directives and at-most-one limits apply
    per scope (scene vs shot), in both dialects.
30. **Per-block duplicate scoping** (§4, §8.2 V1E006, Stage 3): the
    same key in different blocks is legal; duplicates are errors only
    within one block-context.
31. **First-person rule severity split** (§16, Stage 3): V1E025 is an
    error in documents declaring first-person mode and a single line-0
    warning in legacy documents with narrator lines, preserving
    backward compatibility for the fixture and legacy scripts.

## Appendix B. Open questions for the coordinator / Phase B

These items could NOT be settled from the grammar brief or the directive
and are NOT decided by this specification. They need a coordinator
decision; until then, the interim behaviour noted in the body applies.

1. **`MEME_NOTE:` status — RESOLVED (2026-11-12 Phase A
   reconciliation).** Decision: `MEME_NOTE` is a supported legacy scene
   field (§6.13), parsed into the scene's `meme_note` field, kept as
   data, never spoken, never discarded, never recorded under §8.3.
   The fixture uses `MEME_NOTE:` lines and the upstream parser used them
   to justify memes in serious scenes (upstream "Rule 9"); that
   justification stays available as data in V1.
2. **Narrator voice resolution.** Which voice reads `Narrator` lines,
   and how a declared narrator CHARACTER's `VOICE` relates to them,
   is unspecified. Pipeline/Phase B decision.
3. **Foley authoring.** V1 has a foley bus and gain but no foley cue
   syntax (§10.1). Decision needed: add a `FOLEY:` line in a future
   amendment, or keep the bus reserved?
4. **Meme "recorded as data only".** The brief describes `MEME:` lines
   as legacy, "recorded as data only", while also defining
   `MEME_POLICY` / `MEME_MAX_PER_MINUTE` and the upstream parser
   resolved meme files. This specification reads "data only" as
   parse-time behaviour (no file resolution at parse time) with
   rendering governed by policy (§10.4). Confirm or revise.
5. **Schema JSON field names.** Exact names are the parser stream's
   decision (§13); frontend and tests MUST align to the published
   schema, not to guesses.
6. **Frontend review UI and Gemini consumption.** The directive's
   frontend (§2) and planner behaviours are Phase B integration work,
   not defined here beyond the constraints in §§8–12. The parser MUST
   expose everything the review display needs: characters, locations,
   props, scenes, shots, spoken lines, audio cues, VFX, validation
   errors with line numbers, unsupported fields, and the snapshot hash.
7. **Supported-action vocabulary.** Which `ACTION:` / `EXPRESSION:`
   values the animation system supports, and the exact format of the
   unsupported-action report, are animation-stage decisions (§12.3).
8. **Factual verification of LOCATION data** (§11.3): planner/pipeline
   responsibility; no parser rule is defined.

---

*End of STUDIO SCRIPT V1 Specification (V1, 2026-11-12).*
