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

One format serves all genres: historical documentaries, comedy, educational
videos, fictional stories, biographies, first-person storytelling,
third-person storytelling, and others. Nothing in this specification is
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
  - `BLOCK <id>:` — for example `CHARACTER: <name>`, `LOCATION: <id>`,
    `PROP: <name>`, `SCENE <n>: <title>`, `SHOT <id>:`.
  - The colon is REQUIRED on every block header. A block header without
    its required name, id, number, or title part is a syntax error
    (V1E019, §8), except that a `SCENE` title may be empty.
- A block identifier (character name, location id, prop name, shot id)
  is the full trimmed remainder of the header line. Identifiers may
  contain spaces. Matching of identifiers against references is done on
  the trimmed value, case-insensitively (§2.4).
- `END_SCENE` and `END_SCRIPT` are legacy terminators: accepted, carrying
  no data and producing no parsed nodes. `END_SCENE` additionally closes
  the current SCENE/SHOT context (§2.5). `END_SCRIPT` is a pure no-op
  marker. Neither is required.

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
  canonical stored speaker is the declared CHARACTER name (or `Narrator`).

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
    `END_CARD:`) appearing inside a scene implicitly ends that scene.
    Authors SHOULD write `END_SCENE` explicitly; parsers MUST NOT fail
    merely because it is absent.
- Non-scene blocks (CHARACTER, LOCATION, PROP, GLOBAL_AUDIO,
  GLOBAL_NEGATIVE_CONSTRAINTS, QA, OUTPUT, END_CARD) MAY appear before or
  after scenes. References (speakers, LOCATION ids, OWNER, SUBJECT,
  COSTUME_CHANGE scenes, PROP scenes) are resolved over the whole
  document, so forward references are allowed.
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

---

## 3. Format detection and backward compatibility

### 3.1 Detection rule

A document is a STUDIO SCRIPT V1 document if and only if it satisfies
either condition:

1. it contains a `# STUDIO SCRIPT V1` marker line (§3.2); OR
2. it contains a `PROJECT:` header AND at least one `SCENE <n>:` header.

Otherwise the document is a free-form script, handled by the existing
free-form parser. Detection MUST happen before V1 parsing, and the two
paths MUST NOT be mixed for a single document.

### 3.2 Marker matching

The marker is a comment line whose trimmed text, after the leading `#`,
begins with `STUDIO SCRIPT V1`, matched case-insensitively, with trailing
text allowed (for example `# STUDIO SCRIPT V1 — UNIVERSAL VIDEO FORMAT`).
The marker SHOULD be the first non-blank line, but MAY appear anywhere;
detection scans the whole document.

### 3.3 Backward compatibility

- Free-form scripts (no marker, and no `PROJECT:` + `SCENE` combination)
  continue to work through the existing free-form parser, unchanged.
- A document detected as V1 stays V1: V1 syntax or validation failures
  MUST be reported as V1 errors (§8) and MUST NOT silently fall back to
  the free-form parser.
- There is exactly one V1 parser. This specification extends the existing
  parser; it does not create a second parser or a second pipeline.

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

### 3.5 Validation fixture

`examples/hitler_ep01.studio.md` is the first complete test fixture for
this format: 8 scenes, 4 characters, Vietnamese, using the legacy forms
above (inline LOCATION text, bare dialogue, `STYLE:`, `MUSIC:`,
`END_SCENE` / `END_SCRIPT`). It is used for schema, parser, reference,
timeline, and preflight VALIDATION ONLY and MUST NOT be rendered into a
video without ATLAS approval. Generality is proven by running at least two
unrelated scripts through the same schema and pipeline — never by
special-casing the fixture.

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
| `TARGET_DURATION` | No | `AUTO` | `AUTO`, or seconds (non-negative number) | Otherwise: V1E012 |
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
  non-negative decimal number meaning seconds. No unit suffix is defined;
  a value such as `30s` is invalid (V1E012). `END_CARD` `DURATION` does
  not accept `AUTO` (§5.10).
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


---

## 5. Blocks

Every block section below gives the header syntax, a field table
(field, required/optional, default, values, validation), and a short
correct example using neutral placeholder names. Unless a field is marked
repeatable, it MUST appear at most once per block; a second occurrence is
a validation error (V1E006, §8.2). Unknown fields inside a block are
recorded under §8.3, never discarded.

### 5.1 CHARACTER

Header: `CHARACTER: <name>`

Declares one character. The name is the character's display name and, by
default, its identity (§12). Duplicate names (compared with the §2.4
normalisation) are a validation error (V1E001). A character need not speak;
visual-only characters are valid.

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `ROLE` | No | — (absent) | Free text | — |
| `APPEARANCE` | No | — (absent) | Free text | — |
| `TRAITS` | No | — (absent) | `;`-separated distinctive traits | Empty segments ignored |
| `COSTUME` | No | — (absent) | Free text (default outfit) | — |
| `COSTUME_CHANGE` | No, repeatable | — (none) | `SCENE <n>: <outfit>` | Bad format: V1E019; unknown scene: V1E018 |
| `VOICE` | No | `AUTO` | Voice id, or `AUTO` | Non-empty if present |
| `VOICE_STYLE` | No | — (absent) | Free text | — |
| `HEAD_RATIO` | No | `0.34` | Float, 0.33–0.35 inclusive | Non-numeric: V1E008; out of range (including 0.42): V1E009 |
| `IDENTITY_ID` | No | The character name | Free text, stable identity key | Non-empty if present; duplicates across characters: V1E001 |

`COSTUME_CHANGE` format: the value MUST start with `SCENE <n>:` where
`<n>` is a scene number that exists in the document, followed by the
outfit description. Example: `COSTUME_CHANGE: SCENE 1: Trang phục mẫu`.
Scene numbers match numerically, so `SCENE 01` and `SCENE 1` are the
same scene. Multiple `COSTUME_CHANGE` lines are allowed; two changes for
the same scene are a validation error (V1E006).

```text
CHARACTER: NHÂN VẬT A
ROLE: Vai trò mẫu
APPEARANCE: Ngoại hình mẫu riêng biệt
TRAITS: Nét riêng mẫu một; nét riêng mẫu hai
COSTUME: Trang phục mặc định mẫu
COSTUME_CHANGE: SCENE 1: Trang phục mẫu cho cảnh 1
VOICE: AUTO
VOICE_STYLE: Phong cách giọng mẫu
HEAD_RATIO: 0.34
IDENTITY_ID: NHAN_VAT_A
```

### 5.2 LOCATION

Header: `LOCATION: <id>`

Declares one reusable environment specification. The id is how scenes
refer to this location (§5.4). Duplicate ids (compared with the §2.4
normalisation) are a validation error (V1E002). All fields are OPTIONAL;
an absent field means "unspecified", never "use another location's value"
(§11).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `NAME` | No | — (absent) | Free text (display name) | — |
| `PERIOD` | No | — (absent) | Free text (historical period / era) | — |
| `GEOGRAPHY` | No | — (absent) | Free text | — |
| `ARCHITECTURE` | No | — (absent) | Free text | — |
| `FEATURES` | No | — (absent) | `;`-separated distinctive features | Empty segments ignored |
| `FOREGROUND` | No | — (absent) | Free text | — |
| `MIDGROUND` | No | — (absent) | Free text | — |
| `BACKGROUND` | No | — (absent) | Free text | — |
| `LIGHTING` | No | — (absent) | Free text | — |
| `WEATHER` | No | — (absent) | Free text | — |
| `PALETTE` | No | — (absent) | `;`-separated colours | Empty segments ignored |
| `FORBIDDEN` | No | — (absent) | `;`-separated forbidden elements | Empty segments ignored |

```text
LOCATION: ĐỊA ĐIỂM X
NAME: Tên địa điểm mẫu
PERIOD: Thời kỳ mẫu
GEOGRAPHY: Địa lý mẫu
ARCHITECTURE: Kiến trúc mẫu
FEATURES: Đặc điểm riêng mẫu một; đặc điểm riêng mẫu hai
FOREGROUND: Tiền cảnh mẫu
MIDGROUND: Trung cảnh mẫu
BACKGROUND: Hậu cảnh mẫu
LIGHTING: Ánh sáng mẫu
WEATHER: Thời tiết mẫu
PALETTE: Màu mẫu một; màu mẫu hai
FORBIDDEN: Yếu tố cấm mẫu một; yếu tố cấm mẫu hai
```

### 5.3 PROP

Header: `PROP: <name>`

Declares one prop (object). Duplicate names (compared with the §2.4
normalisation) are a validation error (V1E001). All fields are OPTIONAL.

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `DESCRIPTION` | No | — (absent) | Free text | — |
| `OWNER` | No | — (unspecified) | A declared CHARACTER name, or `NONE` | Unknown character: V1E018 |
| `SCENES` | No | — (unspecified) | Comma-separated scene numbers, or `ALL` | Bad format: V1E019; unknown scene: V1E018 |
| `INTERACTION` | No | — (absent) | `;`-separated verbs (how the prop is handled) | Empty segments ignored |

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

Header: `SCENE <n>: <title>`

Declares one scene. `<n>` is a positive integer; leading zeros are
allowed (`SCENE 01` is scene 1). Duplicate scene numbers (by numeric
value) are a validation error (V1E003). Scene numbers need not be
consecutive. The production order of scenes is DOCUMENT ORDER, not
numeric order. A V1 document MUST contain at least one SCENE (V1E020).
A scene contains SHOT blocks (§5.5) and content lines (§6).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `LOCATION` | No | — (absent) | A LOCATION id (reference), or inline free text (legacy) | Never an error: non-matching values are inline text (§11.4) |
| `TIME_OF_DAY` | No | — (absent) | Free text | — |
| `MOOD` | No | — (absent) | Free text | — |
| `DURATION` | No | `AUTO` | `AUTO`, or seconds (non-negative number) | Otherwise: V1E012 |
| `VISUAL` | No | — (absent) | Free text (scene description) | — |
| `TRANSITION` | No | `CUT` | Enum: `CUT`, `DISSOLVE`, `FADE`, `FADE_TO_BLACK`, `MATCH_CUT`, `WIPE` | Any other value: V1E007 |

`LOCATION` resolution: if the trimmed value matches a declared LOCATION
id (§2.4 normalisation), the scene references that LOCATION block; the
structured environment specification governs the render (§11). Otherwise
the value is legacy inline free text and is kept verbatim. Matching is
checked against ALL declared LOCATION blocks in the document, regardless
of block order.

`TRANSITION` MAY appear among the scene fields (as in the example) or as
a content line at the end of the scene (§6.11); both positions mean the
same field. If it appears in both positions with different values, that
is a duplicate-field error (V1E006).

```text
SCENE 1: Tiêu đề cảnh mẫu
LOCATION: ĐỊA ĐIỂM X
TIME_OF_DAY: Thời điểm mẫu
MOOD: Tâm trạng mẫu
DURATION: AUTO
VISUAL: Mô tả hình ảnh mẫu
TRANSITION: CUT
NARRATION: Lời dẫn mẫu.
SFX: Hiệu ứng âm thanh mẫu | TRIGGER: L001 | PRIORITY: REQUIRED
END_SCENE
```

### 5.5 SHOT

Header: `SHOT <id>:` — inside a SCENE only.

Declares one shot (camera setup) within its scene. A `SHOT` header
outside any SCENE is a validation error (V1E019). Shot ids MUST be
unique within their scene (V1E004); the same id MAY be reused in a
different scene. A shot contains its fields plus, optionally, content
lines scoped to the shot (§2.5, §6).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `TYPE` | **YES** | — (none) | Enum, see table below | Missing: V1E013; unknown: V1E014 |
| `CAMERA` | No | — (absent) | Free text | — |
| `CAMERA_MOVEMENT` | No | `STATIC` | Enum, see below | Any other value: V1E007 |
| `SUBJECT` | No | — (absent) | A CHARACTER or PROP name | Unknown name: V1E018 |
| `DURATION` | No | `AUTO` | `AUTO`, or seconds (non-negative number) | Otherwise: V1E012 |
| `ACTION` | No | — (absent) | Free text, kept verbatim | — |
| `EXPRESSION` | No | — (absent) | Same two forms as §6.4 | Unknown character prefix: V1E018 |
| `VFX` | No | — (absent) | `;`-separated VFX names | Empty segments ignored |

`TYPE` enum (canonical form lower_snake_case; UPPER_SNAKE_CASE input is
accepted and normalised to the canonical form; matching is
case-insensitive and treats spaces and hyphens as underscores). These
nine values match the engine camera planner's shot types:

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

Header: `GLOBAL_AUDIO:`

Sets mix levels for the six audio buses (§10). All fields are OPTIONAL
floats in decibels (dB). At most one `GLOBAL_AUDIO:` block per document;
a second block is a validation error (V1E006).

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

No range validation is defined for gain values: any finite float is
accepted.

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

Header: `GLOBAL_NEGATIVE_CONSTRAINTS:`

Lists production-wide prohibitions. The block contains one constraint
per line, in either of two forms. Lines in any other form inside this
block are recorded under §8.3.

- `- <text>` — a dash followed by the constraint text.
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

Header: `QA:`

Sets quality-gate requirements for the production. All fields are
OPTIONAL. At most one `QA:` block per document; a second block is a
validation error (V1E006).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `MIN_SCORE` | No | `8.0` | Float, 0–10 inclusive | Non-numeric: V1E008; out of range: V1E010 |
| `REQUIRE_TECHNICAL` | No | `true` | Boolean `true` / `false` | Otherwise: V1E011 |
| `REQUIRE_CREATIVE_REVIEW` | No | `true` | Boolean `true` / `false` | Otherwise: V1E011 |
| `LANGUAGE_GATE` | No | `true` | Boolean `true` / `false` | Otherwise: V1E011 |
| `MAX_HARD_FAILS` | No | `0` | Integer, 0 or greater | Non-integer or negative: V1E008 |

Boolean values are matched case-insensitively (`true`, `TRUE`, `True`
are the same). No other spelling (such as `yes` / `no` / `1` / `0`) is
accepted.

```text
QA:
MIN_SCORE: 8.0
REQUIRE_TECHNICAL: true
REQUIRE_CREATIVE_REVIEW: true
LANGUAGE_GATE: true
MAX_HARD_FAILS: 0
```

### 5.9 OUTPUT

Header: `OUTPUT:`

Sets render output parameters. All fields are OPTIONAL. At most one
`OUTPUT:` block per document; a second block is a validation error
(V1E006).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `RESOLUTION` | No | `1920x1080` | Enum: `1920x1080`, `1280x720` | Any other value: V1E007 |
| `FPS` | No | `24` | Enum: `24`, `25`, `30` | Any other value: V1E007 |
| `FORMAT` | No | `MP4` | Enum: `MP4` | Any other value: V1E007 |
| `DRAFT_FOLDER` | No | `drive:drafts` | Free text | — |
| `MASTER` | No | `MANUAL_ONLY` | Enum: `MANUAL_ONLY` | Any other value: V1E017 |

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

Header: `END_CARD:`

Describes the closing card shown at the end of the video. All fields are
OPTIONAL. At most one `END_CARD:` block per document; a second block is
a validation error (V1E006).

| Field | Required | Default | Values | Validation |
|---|---|---|---|---|
| `TEXT` | No | — (absent) | Free text | — |
| `DURATION` | No | `3.0` | Seconds (non-negative number); `AUTO` is NOT accepted | Otherwise: V1E012 |
| `STYLE` | No | — (absent) | Free text | — |

An absent `END_CARD:` block means no end card is specified; consumers
MUST NOT invent one.

```text
END_CARD:
TEXT: Nội dung thẻ kết mẫu
DURATION: 3.0
STYLE: Phong cách thẻ kết mẫu
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

Syntax:

```text
NARRATION: <text>
NARRATION [Lnn]: <text>
```

A spoken narration line. The speaker is `Narrator` (§7). The `[Lnn]`
form carries an explicit LINE_ID (§7.1). Spoken text is kept verbatim
(§7.2).

### 6.2 DIALOGUE and bare speaker lines

Syntax:

```text
DIALOGUE: <Speaker>: <text>
DIALOGUE [Lnn]: <Speaker>: <text>
<SPEAKER>: <text>
```

A spoken dialogue line. The speaker is the text between the key (or the
start of the line, for the bare form) and the next colon; the spoken
text is the remainder. The speaker MUST be a declared CHARACTER,
compared with the §2.4 normalisation, otherwise it is a validation
error with the line number (V1E015).

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

Syntax: `ACTION: <text>`

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
uses the §5.5 enum (default `STATIC`). Inside a SHOT block, the same
keys are SHOT fields (§5.5). Neither line is ever spoken.

### 6.6 SFX

Syntax:

```text
SFX: <name> | TRIGGER: <LINE_ID or action text> | PRIORITY: <REQUIRED|OPTIONAL>
SFX: NONE
```

Multiple `SFX:` lines are allowed per scene (and per shot). Subkeys:

| Subkey | Required | Default | Values |
|---|---|---|---|
| `TRIGGER` | No | — (absent) | A LINE_ID (e.g. `L001`) or free action text |
| `PRIORITY` | No | `REQUIRED` | Enum: `REQUIRED`, `OPTIONAL` |

`TRIGGER` resolution happens against the generated speech timeline
(LINE_ID triggers) or the animation timeline (action-text triggers).
A trigger that cannot be resolved is a validation error or an explicit
review requirement at the timeline stage (V1E022, §8.2); a timestamp
MUST NEVER be silently invented (§10.3).

`SFX: NONE` means this scene has NO sound effects. It MUST be recorded
as an explicit none (§10.2) and MUST NOT be treated as "no SFX line
present". A `NONE` line MUST NOT carry `|` segments; segments on a
`NONE` line are a validation error (V1E021). `NONE` is matched
case-insensitively. A `NONE` line does not count toward the at-most-one
limit in §§6.7–6.9; a `NONE` line coexisting with real cues of the same
type in the same scene is a validation error (V1E024, §8.2).

### 6.7 AMBIENCE

Syntax:

```text
AMBIENCE: <name> | MODE: <LOOP|ONCE>
AMBIENCE: NONE
```

At most one `AMBIENCE:` line per scene; a second line is a validation
error (V1E006). `MODE` defaults to `LOOP`. `AMBIENCE: NONE` (no segments,
§6.6) means the scene has no ambience. `NONE` is matched
case-insensitively.

### 6.8 BGM and MUSIC

Syntax:

```text
BGM: <name> | INTENSITY: <LOW|MEDIUM|HIGH>
MUSIC: <name> | INTENSITY: <LOW|MEDIUM|HIGH>
BGM: NONE
```

`MUSIC:` is a legacy alias of `BGM:` (§3.4): both keys write the same
scene field. At most one BGM/MUSIC line per scene in total; a second
line under either key is a validation error (V1E006). `INTENSITY`
defaults to `MEDIUM`. `BGM: NONE` (equivalently `MUSIC: NONE`; no
segments, §6.6) means the scene has no background music. `NONE` is
matched case-insensitively.

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

At most one `MEME:` line per scene; a second line is a validation error
(V1E006). `MEME: NONE` (no segments, §6.6) means the scene has no meme.
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
The SHOT `VFX` field (§5.5) accepts only the `;`-separated names form.

### 6.11 TRANSITION

Syntax: `TRANSITION: <enum>`

The scene transition, using the §5.4 enum. This is the SAME field as the
SCENE `TRANSITION` field: it MAY appear among the scene fields or as a
content line at the end of the scene, with identical meaning (§5.4).
Inside SHOT context it still attaches to the enclosing scene (§2.5).

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
  `Lnn` is the letter `L` followed by digits. Bare speaker lines cannot
  carry an explicit LINE_ID. The canonical form is `L` followed by the
  number zero-padded to three digits (`L001`, `L002`, ...); numbers
  above 999 keep all their digits (`L1000`). Explicit ids are normalised
  to canonical form (`[L2]` becomes `L002`).
- Automatic form: spoken lines without an explicit id receive `L001`,
  `L002`, ... in DOCUMENT ORDER across the whole document (not
  per-scene). The auto counter starts at 1 and skips numbers already
  claimed by earlier explicit ids; an explicit id that equals an
  already-assigned id is a duplicate-LINE_ID error (V1E005).
- LINE_IDs are unique across the whole document. Duplicate explicit ids
  are a validation error (V1E005). A malformed explicit id (for example
  `[LX]` or a missing closing bracket) is a validation error (V1E019).
- LINE_IDs are the stable keys that bind spoken lines to generated
  speech timing (§1.2 principle 7) and to `TRIGGER` references (§6.6,
  §6.9, §6.10). They MUST be preserved unchanged from parse through
  TTS, timeline, subtitles, and QA.

### 7.2 Spoken-text integrity

- Spoken text is NEVER rewritten: no case changes, no punctuation fixes,
  no word substitutions, no translation, no trimming beyond the §2.4
  line-level trim. The text sent to TTS and the text shown in subtitles
  MUST be the parsed spoken text, byte for byte apart from subtitle
  phrase-splitting that preserves the words.
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
| V1E006 | Duplicate single-valued field in the same block, duplicate header key, duplicate singleton block (GLOBAL_AUDIO, GLOBAL_NEGATIVE_CONSTRAINTS, QA, OUTPUT, END_CARD), duplicate subkey on one pipe-segment line, or duplicate COSTUME_CHANGE for the same scene |
| V1E007 | Invalid enum value (ASPECT_RATIO, MEME_POLICY, TRANSITION, CAMERA_MOVEMENT, SFX/MEME PRIORITY, AMBIENCE MODE, BGM INTENSITY, RESOLUTION, FPS, FORMAT) |
| V1E008 | Invalid number (non-numeric value, or negative value where 0 or greater is required: MEME_MAX_PER_MINUTE, MAX_HARD_FAILS, gains) |
| V1E009 | HEAD_RATIO outside 0.33–0.35 inclusive (including the forbidden upstream default 0.42) |
| V1E010 | MIN_SCORE outside 0–10 inclusive |
| V1E011 | Invalid boolean value (QA flags) |
| V1E012 | Invalid duration value (not AUTO — where AUTO is allowed — nor a non-negative number of seconds) |
| V1E013 | Missing required SHOT TYPE |
| V1E014 | Unknown SHOT TYPE value |
| V1E015 | Undeclared speaker in a DIALOGUE or bare-speaker line |
| V1E016 | Production tag inside spoken text (§7.2) |
| V1E017 | OUTPUT MASTER value other than MANUAL_ONLY |
| V1E018 | Unresolvable reference (PROP OWNER, SHOT SUBJECT, EXPRESSION character prefix, COSTUME_CHANGE scene, PROP SCENES entry) |
| V1E019 | Malformed syntax (block header missing its name/id/number, SHOT outside a SCENE, COSTUME_CHANGE bad format, PROP SCENES bad format, malformed LINE_ID, malformed DIALOGUE form, empty spoken line, multiple VFX names combined with one TRIGGER, empty block name) |
| V1E020 | V1 document contains no SCENE |
| V1E021 | NONE line carrying pipe segments (SFX / AMBIENCE / BGM / MEME) |
| V1E022 | Unresolvable TRIGGER (LINE_ID or action text) — raised at the timeline stage, not at parse time; parse records the trigger verbatim |
| V1E023 | V1 document contains no spoken lines |
| V1E024 | NONE directive coexists with real cues of the same type in the same scene |

### 8.3 Unsupported-field policy

- Any `KEY: value` line whose key is not defined for its context, any
  unknown pipe-segment subkey, any content line outside a SCENE, and any
  other non-blank, non-comment line that matches no rule in this
  specification MUST be recorded in the parse result's
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
  forbid even pipeline-default sounds of that kind in that scene.
- An absent line means "nothing scripted". It likewise results in no
  sound of that kind (§10.3); the difference from explicit none is one
  of author intent, preserved for review and for any future feature that
  might add default sounds: explicit none always wins.
- A scene that declares an explicit none AND contains real cues of the
  same type is invalid (V1E024, §8.2): the author must remove either
  the none or the cues.

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

- A CHARACTER's identity is its `IDENTITY_ID` (default: its name, §5.1).
  The same identity MUST look like the same character in every scene:
  same proportions, same face system, same `APPEARANCE` and `TRAITS`
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

`VOICE` (`AUTO` by default) and `VOICE_STYLE` drive TTS voice selection
and delivery for that character's spoken lines. The same character MUST
sound like the same voice across scenes. Voice resolution for the
`Narrator` speaker is a pipeline concern (see Appendix B); the parser
records the speaker as `Narrator` and preserves `VOICE_NOTE:` lines
verbatim.

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
   shot types; the V1 vocabulary (§5.5) has nine
   (`extreme_close_up`, `over_the_shoulder`, `shot_reverse_shot` are
   missing from the prompt). Phase B MUST use the full V1 vocabulary
   and key shot enrichment by V1 SHOT id, not by spoken-line index.

---

## Appendix A. Rules defined by this specification where the brief was silent

The canonical grammar brief defined the format but left the following
points open. This specification defines them, as marked, so that the
parser, schema, tests, and frontend can implement one consistent
behaviour. The coordinator SHOULD confirm each item; any change requires
a specification amendment (§14), not a unilateral parser deviation.

1. **Error code values** (V1E001–V1E024, §8.2): the brief required codes
   but did not enumerate them. The code list in §8.2 is normative.
   V1E023–V1E024 were added by the 2026-11-12 Phase A reconciliation;
   see §14.
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
