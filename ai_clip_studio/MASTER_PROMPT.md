# MASTER PROMPT — UNIVERSAL END-TO-END AI VIDEO PRODUCTION PIPELINE

Tài liệu gốc của Mai (lưu nguyên văn ý, 2026-11-11). Đây là bản lưu
để làm tài liệu gốc cho `ai_clip_studio/`; mọi module trong package
này đều đối chiếu với các mục dưới đây (xem `AUDIT.md`).

> Mai sẽ tự chạy frontend, nhiệm vụ của chúng ta là IMPLEMENT +
> CONNECT + DEBUG + TEST code thật, KHÔNG chỉ viết tài liệu/kế hoạch
> hay module rời rạc.

## SYSTEM-WIDE IMPLEMENTATION DIRECTIVE

- **Workspace:** `D:/Agent`
- **Application:** AI Clip Studio
- **Frontend:** Existing frontend at `http://127.0.0.1:5173`
- **Default Language:** Vietnamese (`vi-VN`)
- **Visual Style:** Premium Stickman Cinematic B
- **Rendering:** Motion Canvas + Three.js
- **Audio:** VieNeu-TTS + event-driven Foley/SFX/ambience/music/meme system
- **Delivery:** Google Drive
- **Permanent Google Drive Root Folder ID:** `1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm`
- **Drive Folder URL:** https://drive.google.com/drive/u/0/folders/1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm

## PRIMARY OBJECTIVE

Build a fully integrated, universal, frontend-driven cinematic animation
production system. The user should only need to: open AI Clip Studio,
paste a script, click Analyze, review the generated storyboard and
production plan, click Generate Draft, review the Draft, approve Master
when satisfied. Everything else must be automated.

The application must generate actual animated cinematic videos, not
static slideshows. After rendering, automatically upload the production
artifacts to the designated Google Drive folder and display clickable
Drive links in the frontend. This must work for arbitrary future scripts
without editing the source code or writing new Antigravity prompts for
each episode.

## Luồng AI Clip Studio hoàn chỉnh (tóm tắt của Mai)

1. Frontend — nhập kịch bản (tiếng Việt tự do hoặc STUDIO SCRIPT V1).
2. Gemini — phân tích và lập kế hoạch (cảnh · nhân vật · bối cảnh ·
   hành động · camera · audio).
3. Preflight — kiểm định kịch bản (cùng script hash · kiểm tra asset ·
   giọng · timeline).
4. Engine — dựng hoạt hình thực (Motion Canvas + Three.js · Rig · IK ·
   tương tác vật thể).
5. Audio — VieNeu-TTS + Sound Engine (tiếng Việt · Foley · Ambience ·
   Music · Meme · Subtitles).
6. Render — MP4 Draft + QA (1920×1080 · 24 fps · kiểm tra hình và
   tiếng thực tế).
7. Google Drive — upload kết quả (Draft · Audio stems · Storyboard ·
   Báo cáo · Link xem video). Thư mục đích cố định là root folder trên.

Quan trọng nhất: đây là kiến trúc dùng chung cho mọi kịch bản, không
hardcode theo Eiffel, Munich hay bất kỳ câu chuyện nào.

# 1. UNIVERSAL SCRIPT INPUT

Frontend phải nhận cả hai dạng:

### Mode A — Free-form script

Người dùng dán văn bản tiếng Việt thường. Hệ thống tự trích xuất:
story structure, characters, narration, dialogue, locations, historical
period, props, actions, emotions, camera opportunities, scene
transitions, audio events.

### Mode B — STUDIO SCRIPT V1

Người dùng cung cấp metadata scene có cấu trúc. Giữ mọi instruction
rõ ràng được hỗ trợ. Nếu người dùng chỉ định góc máy, hành động nhân
vật, giọng hay meme cue, engine phải tôn trọng trừ khi không thể về kỹ
thuật hoặc mâu thuẫn với quy tắc sản xuất ưu tiên cao hơn.

### Universal requirements

- No fixed number of scenes. No fixed number of characters.
- No fixed video duration. No predefined story templates.
- No robot-demo fallback. No unrelated historical setting fallback.
- No hidden replacement of the submitted script.
- Tạo một `ProductionRequest` bất biến cho mỗi submission. Mọi stage
  sau phải tham chiếu cùng request ID và content hash.

# 2. GEMINI UNIVERSAL STORY DIRECTOR

Nối hệ thống planning Gemini hiện có trực tiếp vào workflow frontend.
Input: `ProductionRequest`. Output: `ProductionScenePackage` chứa:
`project_id`, `script_hash`, `language`, `visual_style`, `aspect_ratio`,
`characters`, `locations`, `props`, `scenes`, `shots`, `actions`,
`dialogue`, `narration`, `camera`, `lighting`, `audio_events`,
`subtitle_events`, `transitions`, `continuity`, `asset_manifest`,
`render_settings`.

Gemini chịu trách nhiệm semantic planning. Gemini không được sinh
renderer implementation mới cho mỗi script. Dùng strict structured
outputs với schema validation. Nếu planner không hiểu một scene bắt
buộc, báo unresolved issue thay vì bịa nội dung không liên quan.

# 3. UNIVERSAL CHARACTER SYSTEM

Build/repair một character engine Premium Stickman Cinematic dùng lại
được. Nhân vật sinh từ `CharacterDNA` có cấu trúc: body proportions,
head and face, hair, costume, accessories, age presentation, character
identity, expression library, voice identity, movement style. Giữ cùng
một nhân vật qua mọi shot.

Real animation là bắt buộc: walking, running, turning, sitting,
standing, looking, talking, gesturing, reaching, grabbing, holding,
giving, receiving, opening objects, carrying objects, falling,
recovering, emotional reactions. Dùng articulated rigs, joint
transforms, animation blending và inverse kinematics khi phù hợp.
Enforce bone-length invariants, valid joint limits, stable feet,
reliable hand-object contact. Không dùng ảnh nhân vật đông cứng +
pan/zoom thay cho animation. Không chấp nhận disconnected limbs,
inverted knees, distorted proportions, floating props.

# 4. UNIVERSAL ENVIRONMENT SYSTEM

Dùng `LocationDNA` và procedural environment generation, dùng lại được.
Three.js phải sinh buildings, architecture, terrain, interiors,
furniture, streets, vegetation, weather, lighting, atmosphere, physical
props phù hợp scene. Environment selection phải theo semantic thực của
script. Các setting khác nhau phải trông khác nhau thật. Không dùng lại
cùng pillars generic, empty floor hay background cho các location không
liên quan. Giữ historical consistency khi script yêu cầu thời kỳ lịch
sử. Không đưa vật hiện đại vào scene lịch sử trừ khi được yêu cầu rõ.

# 5. REAL CINEMATIC RENDERING

Visual pipeline cuối phải dùng **Motion Canvas + Three.js**. Motion
Canvas: character presentation and animation timeline, scene
composition, typography, subtitles, transitions, 2D visual effects.
Three.js: three-dimensional environments, architecture, props,
materials, lighting, shadows, atmospheric effects, spatial camera
rendering. Một deterministic synchronized production clock. Python chỉ
orchestrate planning, assets, jobs và validation. FFmpeg chỉ encode,
mux và package output. Python image generation hay static slide
composition không được lặng lẽ thay thế renderer đã duyệt.

Required motion validation: đo actual joint movement, root movement,
foot contact, object interaction, pose continuity, camera continuity,
scene transitions. Moving camera trên static character không được tính
là character animation.

# 6. VIETNAMESE VOICE PIPELINE

Ngôn ngữ xuất bản mặc định là tiếng Việt:

```yaml
production_language: vi-VN
narration_language: vi-VN
dialogue_language: vi-VN
subtitle_language: vi-VN
tts_engine: VieNeu-TTS
allow_english_fallback: false
```

Yêu cầu: parse script thành spoken segments sạch; tách dialogue khỏi
narration; gán giọng nhất quán cho nhân vật; dùng VieNeu-TTS voice
registry đã cấu hình; giữ dấu tiếng Việt và phrasing tự nhiên; sinh
giọng với emotional delivery phù hợp; thêm pause và pacing tự nhiên;
giữ speaker identity qua các scene; đo thời lượng audio thật đã sinh;
đồng bộ speech với gesture và subtitle. Nếu user gửi source tiếng Anh
trong khi chọn output tiếng Việt, dịch spoken content sang tiếng Việt
trước khi synthesis, với transcript có thể review. Nếu TTS tiếng Việt
fail, dừng với lỗi rõ ràng. Không bao giờ lặng lẽ dùng English TTS
provider. Không bao giờ đọc production metadata thành tiếng.

# 7. UNIVERSAL AUDIO EVENT ENGINE

Tích hợp audio infrastructure hiện có và local meme catalog.
Asset: `D:/Agent/assets/memes`, metadata `catalog.json`, resolver
`MemeSoundResolver`. Categories: dialogue, narration, Foley,
environmental ambience, music, meme sounds, character vocal reactions.

Event-driven audio: SFX gắn với visual event thật, ví dụ
`foot_contact -> FOOTSTEP`, `door_contact -> DOOR_KNOCK`,
`door_rotation -> DOOR_OPEN`, `paper_movement -> PAPER_RUSTLE`,
`object_impact -> IMPACT`, `rain_start -> RAIN_AMBIENCE`,
`character_reaction -> CONTEXTUAL_MEME`. Không đặt SFX ở timestamp
tùy tiện không liên quan animation.

Meme rules: resolve qua stable catalog asset IDs; hỗ trợ explicit meme
tags trong STUDIO SCRIPT V1; hỗ trợ auto meme suggestions khi bật;
không chèn meme ngẫu nhiên; không ngắt dialogue quan trọng; không chèn
âm hài vào scene đau thương nặng, chết chóc hay atrocities lịch sử;
tôn trọng gain và duration; không bao giờ thay meme thiếu bằng audio
không liên quan; verify usage rights trước khi publish/distribute audio
bên thứ ba.

Audio mixing: dialogue priority, automatic ducking, loudness
normalization, peak limiting, crossfades, spatial consistency khi phù
hợp, export stems riêng. Stems bắt buộc: `dialogue.wav`,
`narration.wav`, `foley.wav`, `ambience.wav`, `music.wav`, `memes.wav`,
`master_mix.wav`.

# 8. DYNAMIC TIMELINE ENGINE

Không ép video vào duration cố định 10 giây hay 15 giây. Tính duration
từ: actual TTS audio, speech pauses, required character actions,
object interactions, camera movements, scene transitions, audio event
tails, story pacing. Nếu speech cần 17 giây, scene phải chứa được 17
giây. Nếu physical action cần thêm thời gian, extend hoặc restructure
scene. Không bao giờ giải quyết duration bằng cách freeze frame cuối.
Không bao giờ truncate narration. Không bao giờ tăng tốc dialogue để
vừa timeline cố định. Subtitles, animation, SFX, memes và music đều
đồng bộ trên cùng một clock.

# 9. FRONTEND PREVIEW AND CONTROL PANEL

Nâng cấp frontend hiện có thay vì tạo app thứ hai rời rạc. Control bắt
buộc: Script Input (paste script, load file, chọn output language,
aspect ratio, visual style, voice preferences); Analyze (storyboard,
characters, environments, scene descriptions, estimated duration);
Audio (preview assigned voices, preview meme selections, SFX event
markers, music and ambience plan); Preflight (validate script, assets,
language, animation capabilities, timeline, output configuration);
Render (Generate Draft, real progress, preview MP4, warnings/errors,
approve/reject Draft); Delivery (local artifact links, Google Drive
links, upload status, retry failed uploads không cần re-render).

# 10. IMMUTABLE SCRIPT SNAPSHOT

Mọi production stage phải dùng cùng approved script snapshot. Enforce:

```text
editor_hash == analysis_hash == storyboard_hash == preflight_hash
            == render_job_hash == output_manifest_hash
```

Script thay đổi thì approval trước đó vô hiệu. Render request với hash
không khớp phải bị reject. Không bao giờ render một cached story không
liên quan. Không bao giờ báo success dựa trên hidden sample script.
Output manifest phải ghi đúng script version đã sinh MP4.

# 11. AUTOMATIC DRAFT PRODUCTION

Khi user bấm Generate Draft: freeze approved script snapshot; tạo
production job; resolve mọi asset bắt buộc; sinh giọng Việt; sinh
animation timeline; chạy renderer Motion Canvas + Three.js thật; sinh
SFX, ambience, music và memes đồng bộ; sinh subtitle tiếng Việt; mix
audio; encode MP4; chạy technical và semantic validation; lưu Draft và
artifact hỗ trợ; upload Draft lên Google Drive; trả clickable Drive
link về frontend. User không cần chạy FFmpeg, tự ráp asset hay chạy
terminal cho mỗi video.

# 12. GOOGLE DRIVE AUTO-UPLOAD

Tích hợp Google Drive delivery trực tiếp vào production pipeline.
Root cố định: `1HFOuxsP6ir_vLiMFX0o7VMyuersAYVSm`. Dùng authorized
Google Drive OAuth connection hoặc service account có quyền tới folder
đích. Không hardcode access tokens, passwords hay secrets. Nếu thiếu
authentication, hiện frontend connection action rõ ràng.

Per-project folder structure (tạo tự động dưới root):

```text
AI_CLIP_STUDIO_ROOT/
    PROJECT_ID/
        01_SCRIPT/
        02_STORYBOARD/
        03_AUDIO/
        04_DRAFT/
        05_QA_REPORTS/
        06_MASTER/
```

Required uploads: **01_SCRIPT** (original script, normalized script,
script hash, production request manifest); **02_STORYBOARD** (scene
plan, shot plan, character manifest, location manifest, audio event
plan); **03_AUDIO** (dialogue, narration, Foley, ambience, music, meme
stems, final mix); **04_DRAFT** (draft MP4, contact sheet, preview
metadata); **05_QA_REPORTS** (preflight, timeline validation, animation
checks, language checks, audio sync report, render provenance, known
limitations); **06_MASTER** (approved final Master MP4, final subtitles,
final production manifest).

Không upload failed Draft thành approved Master. Failed production có
thể upload logs/diagnostics với FAILED status rõ ràng.

Upload integrity: sau upload xác nhận file tồn tại trong folder đích,
verify file size và integrity metadata có được, lưu Drive file ID, lưu
Drive URL vào production database, hiện URL trong frontend, hỗ trợ
retry không duplicate upload, giữ local artifact tới khi delivery
thành công được xác nhận.

# 13. HUMAN APPROVAL BEFORE MASTER

Draft production và Draft upload tự động sau khi user bắt đầu job.
Master publication mặc định phải có approval của người: Draft Ready →
User Review → Approve Master → Master Render/Finalize → Drive Upload.
Nếu user reject Draft: giữ script gốc, ghi feedback, xác định stage
sản xuất lỗi, regenerate chỉ asset bị ảnh hưởng khi an toàn,
revalidate mọi output phụ thuộc, sinh Draft mới có version. Không bao
giờ coi Draft là approved chỉ vì automated scoring đạt ngưỡng số.

# 14. QUALITY GATES

Hard failures: wrong script rendered; wrong output language; static
slideshow thay vì actual animation; missing required character
movement; deformed character rigs; floating/teleporting props; incorrect
location hoặc historical period; speech cut off; incorrect speaker
assignment; metadata bị TTS đọc; SFX không align với visual events;
broken subtitles; corrupt/incomplete MP4; false PASS results; incorrect
Google Drive destination. Weighted quality score không override hard
failure. Dùng rendered frames thật, decoded audio thật và output files
thật làm evidence.

# 15. GENERALIZATION TESTS

Engine phải test trên nhiều unseen script với yêu cầu khác nhau rõ rệt,
ít nhất: indoor conversation; physical object exchange; outdoor action
sequence; historical environment; modern environment; comedy scene với
meme cues; serious scene không có meme cue không phù hợp; multi-
character dialogue scene. Không viết custom renderer code giữa các
test. Không hardcode expected scene counts hay character names vào
production engine. Test phải chứng minh cùng một pipeline khái quát qua
các story.

# 16. IMPLEMENTATION STRATEGY

Không rewrite toàn bộ project mù. Audit codebase hiện có trước, xác
định reusable components. Giữ capability đang chạy. Implement tính năng
thiếu thành reusable modules. Dùng isolated development branch hoặc
worktree. Cung cấp diffs và automated regression tests. Với mỗi tính
năng mới: implement, unit test, integration test, render small proof,
inspect actual frames và audio, run regression tests, integrate vào
frontend hiện có, document remaining limitations. Không push GitHub tới
khi có đúng repository permissions. Không bypass repository permissions.

# 17. REQUIRED FINAL ACCEPTANCE TEST

Chạy toàn bộ workflow qua frontend thật. Input: một Vietnamese script
chưa từng thấy. Chuỗi kỳ vọng: Paste Script → Analyze Script →
Generate Storyboard → Resolve Characters and Environments → Plan Real
Animation → Generate Vietnamese Voices → Resolve Contextual Audio →
Run Preflight → Render Audiovisual Draft → Validate Actual MP4 →
Upload Draft to Google Drive → Return Clickable Drive Link → Human
Review → Approve Master → Finalize Master → Upload Master to Google
Drive.

Không manual code editing. Không per-story Antigravity prompt. Không
manually assembled slideshow. Không English voice fallback. Không
unrelated demonstration scene.

Final deliverables: updated working frontend; updated backend; reusable
universal animation engine; Vietnamese voice pipeline; event-driven
audio engine; integrated Draft/Master workflow; automatic Google Drive
uploader; production status và progress reporting; test results; real
rendered MP4 evidence; Drive folder links; source diff và commit SHA;
remaining known limitations.

Final status — báo đúng một trong: `IMPLEMENTATION_IN_PROGRESS` /
`BLOCKED_WITH_EXPLICIT_REASON` / `END_TO_END_DRAFT_READY_FOR_REVIEW` /
`MASTER_APPROVED_AND_UPLOADED`. Không bao giờ claim success mà không
verify output artifacts thật.

**The final product must be a universal script-to-cinematic-animation
studio, not a slideshow generator and not a one-story demo.**
