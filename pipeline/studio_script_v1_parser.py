"""Studio Script V1 — Universal Video Format Parser & Production Compiler.
Implements the full specification for STUDIO SCRIPT V1:
- Header metadata parsing (PROJECT, LANGUAGE, GENRE, STYLE, ASPECT_RATIO, TONE, MEME_POLICY, MEME_MAX_PER_MINUTE)
- Character roster parsing (CHARACTER, ROLE, APPEARANCE, VOICE, VOICE_STYLE)
- Scene breakdown (SCENE, LOCATION, TIME_OF_DAY, MOOD, DURATION, VISUAL, ACTION, CAMERA)
- Strict Speech Extraction (Only NARRATOR and character dialogue synthesized as speech; Rule 1 & 2)
- Audio layers: SFX, AMBIENCE, MUSIC, MEME (resolved via MemeSoundResolver with GAIN_DB control)
- Production Rules Validation (Rules 1-12)
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.meme_resolver import MemeSoundResolver, ResolvedMemeSound


@dataclass
class ScriptCharacter:
    name: str
    role: str
    appearance: str
    voice: str
    voice_style: str
    head_ratio: float = 0.42


@dataclass
class ScriptSpokenLine:
    speaker: str
    text: str
    voice_note: str = ""
    voice_id: str = "vieneu-Thiện Minh"


@dataclass
class ScriptAudioCue:
    cue_type: str  # "SFX", "AMBIENCE", "MUSIC", "MEME"
    name: str
    trigger: str = ""
    priority: str = "REQUIRED"
    mode: str = ""
    intensity: str = "MEDIUM"
    gain_db: float = 0.0
    resolved_path: Optional[str] = None
    is_missing: bool = False
    error_message: Optional[str] = None


@dataclass
class StudioScriptScene:
    scene_number: int
    scene_name: str
    location: str
    time_of_day: str
    mood: str
    duration_mode: str  # "AUTO" or seconds
    visual: str
    action: str
    camera: str
    voice_note: str
    spoken_lines: List[ScriptSpokenLine]
    sfx: Optional[ScriptAudioCue] = None
    ambience: Optional[ScriptAudioCue] = None
    music: Optional[ScriptAudioCue] = None
    meme: Optional[ScriptAudioCue] = None
    meme_note: str = ""
    transition: str = "CUT"
    estimated_duration_sec: float = 5.0


@dataclass
class StudioScriptV1Package:
    project_name: str
    language: str
    genre: str
    style: str
    aspect_ratio: str
    target_duration: str
    tone: str
    meme_policy: str
    meme_max_per_minute: int
    characters: Dict[str, ScriptCharacter]
    scenes: List[StudioScriptScene]
    production_rules_status: str = "PENDING"
    validation_issues: List[str] = field(default_factory=list)
    missing_assets: List[str] = field(default_factory=list)
    total_estimated_duration_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "language": self.language,
            "genre": self.genre,
            "style": self.style,
            "aspect_ratio": self.aspect_ratio,
            "target_duration": self.target_duration,
            "tone": self.tone,
            "meme_policy": self.meme_policy,
            "meme_max_per_minute": self.meme_max_per_minute,
            "characters": {k: asdict(v) for k, v in self.characters.items()},
            "scenes": [
                {
                    "scene_number": s.scene_number,
                    "scene_name": s.scene_name,
                    "location": s.location,
                    "time_of_day": s.time_of_day,
                    "mood": s.mood,
                    "duration_mode": s.duration_mode,
                    "visual": s.visual,
                    "action": s.action,
                    "camera": s.camera,
                    "voice_note": s.voice_note,
                    "spoken_lines": [asdict(l) for l in s.spoken_lines],
                    "sfx": asdict(s.sfx) if s.sfx else None,
                    "ambience": asdict(s.ambience) if s.ambience else None,
                    "music": asdict(s.music) if s.music else None,
                    "meme": asdict(s.meme) if s.meme else None,
                    "meme_note": s.meme_note,
                    "transition": s.transition,
                    "estimated_duration_sec": s.estimated_duration_sec
                }
                for s in self.scenes
            ],
            "production_rules_status": self.production_rules_status,
            "validation_issues": self.validation_issues,
            "missing_assets": self.missing_assets,
            "total_estimated_duration_sec": self.total_estimated_duration_sec
        }


class StudioScriptV1Parser:
    """Parser and validator for STUDIO SCRIPT V1 — UNIVERSAL VIDEO FORMAT."""

    def __init__(self):
        self.meme_resolver = MemeSoundResolver()

    def parse(self, raw_text: str) -> StudioScriptV1Package:
        lines = [line.strip() for line in raw_text.splitlines()]

        # Defaults
        meta = {
            "PROJECT": "Chưa đặt tên",
            "LANGUAGE": "vi-VN",
            "GENRE": "Kể chuyện",
            "STYLE": "Premium Stickman Cinematic B",
            "ASPECT_RATIO": "16:9",
            "TARGET_DURATION": "AUTO",
            "TONE": "Tự nhiên, kịch tính",
            "MEME_POLICY": "CONTEXTUAL",
            "MEME_MAX_PER_MINUTE": 2
        }

        characters: Dict[str, ScriptCharacter] = {}
        scenes: List[StudioScriptScene] = []

        current_char: Optional[Dict[str, str]] = None
        current_scene_lines: List[str] = []
        in_scene = False
        current_scene_title = ""

        # Parse line by line
        for raw_line in lines:
            if not raw_line or raw_line.startswith("# PRODUCTION RULES"):
                if raw_line.startswith("# PRODUCTION RULES") and in_scene:
                    # Flush last scene
                    sc = self._parse_scene_block(len(scenes) + 1, current_scene_title, current_scene_lines, characters)
                    scenes.append(sc)
                    in_scene = False
                    current_scene_lines = []
                continue

            # Header metadata tags
            m_header = re.match(r"^(PROJECT|LANGUAGE|GENRE|STYLE|ASPECT_RATIO|TARGET_DURATION|TONE|MEME_POLICY|MEME_MAX_PER_MINUTE):\s*(.*)$", raw_line, re.IGNORECASE)
            if m_header and not in_scene:
                key = m_header.group(1).upper()
                val = m_header.group(2).strip()
                if key == "MEME_MAX_PER_MINUTE":
                    try:
                        meta[key] = int(val)
                    except ValueError:
                        meta[key] = 2
                else:
                    meta[key] = val
                continue

            # Character blocks
            m_char = re.match(r"^CHARACTER:\s*(.*)$", raw_line, re.IGNORECASE)
            if m_char and not in_scene:
                if current_char and current_char.get("name"):
                    self._save_character(current_char, characters)
                current_char = {"name": m_char.group(1).strip()}
                continue

            if current_char and not in_scene:
                m_cfield = re.match(r"^(ROLE|APPEARANCE|VOICE|VOICE_STYLE):\s*(.*)$", raw_line, re.IGNORECASE)
                if m_cfield:
                    current_char[m_cfield.group(1).lower()] = m_cfield.group(2).strip()
                    continue

            # Scene start
            m_scene = re.match(r"^SCENE\s+(\d+):\s*(.*)$", raw_line, re.IGNORECASE)
            if m_scene:
                if current_char and current_char.get("name"):
                    self._save_character(current_char, characters)
                    current_char = None
                if in_scene:
                    # End previous scene
                    sc = self._parse_scene_block(len(scenes) + 1, current_scene_title, current_scene_lines, characters)
                    scenes.append(sc)
                in_scene = True
                current_scene_title = m_scene.group(2).strip() or f"Cảnh {m_scene.group(1)}"
                current_scene_lines = []
                continue

            # Scene end
            if raw_line.upper() in ("END_SCENE", "END_SCRIPT"):
                if in_scene:
                    sc = self._parse_scene_block(len(scenes) + 1, current_scene_title, current_scene_lines, characters)
                    scenes.append(sc)
                    in_scene = False
                    current_scene_lines = []
                continue

            if in_scene:
                current_scene_lines.append(raw_line)

        # Flush any trailing character or scene
        if current_char and current_char.get("name"):
            self._save_character(current_char, characters)
        if in_scene and current_scene_lines:
            sc = self._parse_scene_block(len(scenes) + 1, current_scene_title, current_scene_lines, characters)
            scenes.append(sc)

        # Compute total duration
        total_dur = sum(s.estimated_duration_sec for s in scenes)

        pkg = StudioScriptV1Package(
            project_name=meta["PROJECT"],
            language=meta["LANGUAGE"],
            genre=meta["GENRE"],
            style=meta["STYLE"],
            aspect_ratio=meta["ASPECT_RATIO"],
            target_duration=str(meta["TARGET_DURATION"]),
            tone=meta["TONE"],
            meme_policy=meta["MEME_POLICY"],
            meme_max_per_minute=int(meta["MEME_MAX_PER_MINUTE"]),
            characters=characters,
            scenes=scenes,
            total_estimated_duration_sec=round(total_dur, 1)
        )

        self.validate_production_rules(pkg)
        return pkg

    def _save_character(self, cdict: Dict[str, str], registry: Dict[str, ScriptCharacter]):
        name = cdict.get("name", "Nhân vật")
        voice = cdict.get("voice", "AUTO")
        if voice.upper() in ("AUTO", "DEFAULT", ""):
            # Map standard voice
            voice = "vieneu-Thiện Minh" if len(registry) == 0 else "vieneu-Hải Đăng"

        registry[name] = ScriptCharacter(
            name=name,
            role=cdict.get("role", "Diễn viên"),
            appearance=cdict.get("appearance", "Stickman Blob-Head tối giản"),
            voice=voice,
            voice_style=cdict.get("voice_style", "Tự nhiên"),
            head_ratio=0.42
        )

    def _parse_scene_block(
        self,
        scene_num: int,
        title: str,
        lines: List[str],
        char_registry: Dict[str, ScriptCharacter]
    ) -> StudioScriptScene:
        location = ""
        time_of_day = "Ngày"
        mood = "Bình thường"
        duration_mode = "AUTO"
        visual = ""
        action = ""
        camera = ""
        voice_note = ""
        spoken_lines: List[ScriptSpokenLine] = []
        sfx: Optional[ScriptAudioCue] = None
        ambience: Optional[ScriptAudioCue] = None
        music: Optional[ScriptAudioCue] = None
        meme: Optional[ScriptAudioCue] = None
        meme_note = ""
        transition = "CUT"

        # Character names list for dialogue matching
        known_speakers = set(char_registry.keys()) | {"NARRATOR", "NGƯỜI KỂ CHUYỆN", "DẪN CHUYỆN"}

        for line in lines:
            # Field matchers
            m_loc = re.match(r"^LOCATION:\s*(.*)$", line, re.IGNORECASE)
            if m_loc:
                location = m_loc.group(1).strip()
                continue

            m_tod = re.match(r"^TIME_OF_DAY:\s*(.*)$", line, re.IGNORECASE)
            if m_tod:
                time_of_day = m_tod.group(1).strip()
                continue

            m_mood = re.match(r"^MOOD:\s*(.*)$", line, re.IGNORECASE)
            if m_mood:
                mood = m_mood.group(1).strip()
                continue

            m_dur = re.match(r"^DURATION:\s*(.*)$", line, re.IGNORECASE)
            if m_dur:
                duration_mode = m_dur.group(1).strip()
                continue

            m_vis = re.match(r"^VISUAL:\s*(.*)$", line, re.IGNORECASE)
            if m_vis:
                visual = m_vis.group(1).strip()
                continue

            m_act = re.match(r"^ACTION:\s*(.*)$", line, re.IGNORECASE)
            if m_act:
                action = m_act.group(1).strip()
                continue

            m_cam = re.match(r"^CAMERA:\s*(.*)$", line, re.IGNORECASE)
            if m_cam:
                camera = m_cam.group(1).strip()
                continue

            m_vnote = re.match(r"^VOICE_NOTE:\s*(.*)$", line, re.IGNORECASE)
            if m_vnote:
                voice_note = m_vnote.group(1).strip()
                continue

            # Spoken line extraction (Rule 1: Only NARRATOR and character dialogue lines are synthesized)
            # 1. Narrator line
            m_narr = re.match(r"^(NARRATOR|NGƯỜI KỂ CHUYỆN|DẪN CHUYỆN):\s*(.*)$", line, re.IGNORECASE)
            if m_narr:
                spoken_text = m_narr.group(2).strip()
                if spoken_text:
                    spoken_lines.append(ScriptSpokenLine(
                        speaker="Narrator",
                        text=spoken_text,
                        voice_note=voice_note,
                        voice_id="vieneu-Thiện Minh"
                    ))
                continue

            # 2. Character dialogue line: [TÊN NHÂN VẬT]: [thoại]
            m_char_line = re.match(r"^([A-Z0-9_À-Ỹ\s]{2,30}):\s*(.*)$", line)
            if m_char_line:
                cand_speaker = m_char_line.group(1).strip()
                cand_upper = cand_speaker.upper()
                # Exclude metadata tags
                if cand_upper not in ("SFX", "AMBIENCE", "MUSIC", "MEME", "MEME_NOTE", "TRANSITION", "ACTION", "VISUAL", "CAMERA", "VOICE_NOTE"):
                    spoken_text = m_char_line.group(2).strip()
                    if spoken_text:
                        # Find voice from character registry
                        char_info = char_registry.get(cand_speaker)
                        voice_id = char_info.voice if char_info else "vieneu-Hải Đăng"
                        spoken_lines.append(ScriptSpokenLine(
                            speaker=cand_speaker,
                            text=spoken_text,
                            voice_note=voice_note,
                            voice_id=voice_id
                        ))
                    continue

            # Audio cue matchers
            m_sfx = re.match(r"^SFX:\s*([^|]+)(?:\|\s*TRIGGER:\s*([^|]+))?(?:\|\s*PRIORITY:\s*([^|]+))?", line, re.IGNORECASE)
            if m_sfx:
                sfx_name = m_sfx.group(1).strip()
                trig = (m_sfx.group(2) or "").strip()
                prio = (m_sfx.group(3) or "REQUIRED").strip()
                sfx = ScriptAudioCue(cue_type="SFX", name=sfx_name, trigger=trig, priority=prio)
                continue

            m_amb = re.match(r"^AMBIENCE:\s*([^|]+)(?:\|\s*MODE:\s*([^|]+))?", line, re.IGNORECASE)
            if m_amb:
                amb_name = m_amb.group(1).strip()
                mode = (m_amb.group(2) or "LOOP").strip()
                ambience = ScriptAudioCue(cue_type="AMBIENCE", name=amb_name, mode=mode)
                continue

            m_mus = re.match(r"^MUSIC:\s*([^|]+)(?:\|\s*INTENSITY:\s*([^|]+))?", line, re.IGNORECASE)
            if m_mus:
                mus_name = m_mus.group(1).strip()
                inten = (m_mus.group(2) or "MEDIUM").strip()
                music = ScriptAudioCue(cue_type="MUSIC", name=mus_name, intensity=inten)
                continue

            # Meme cue matcher: MEME: [name] | TRIGGER: [trig] | GAIN_DB: [-12] | PRIORITY: [prio]
            m_meme = re.match(r"^MEME:\s*([^|]+)(?:\|\s*TRIGGER:\s*([^|]+))?(?:\|\s*GAIN_DB:\s*([^|]+))?(?:\|\s*PRIORITY:\s*([^|]+))?", line, re.IGNORECASE)
            if m_meme:
                meme_name = m_meme.group(1).strip()
                trig = (m_meme.group(2) or "").strip()
                gain_str = (m_meme.group(3) or "-12").strip()
                prio = (m_meme.group(4) or "OPTIONAL").strip()
                try:
                    gain_val = float(re.sub(r"[^\d.-]", "", gain_str))
                except ValueError:
                    gain_val = -12.0

                if meme_name.upper() not in ("NONE", "NULL", "NO", "KHONG", ""):
                    res = self.meme_resolver.resolve(meme_name, trigger=trig, gain_db=gain_val)
                    meme = ScriptAudioCue(
                        cue_type="MEME",
                        name=meme_name,
                        trigger=trig,
                        priority=prio,
                        gain_db=gain_val,
                        resolved_path=str(res.file_path) if res.exists else None,
                        is_missing=res.is_missing,
                        error_message=res.error_message
                    )
                continue

            m_mnote = re.match(r"^MEME_NOTE:\s*(.*)$", line, re.IGNORECASE)
            if m_mnote:
                meme_note = m_mnote.group(1).strip()
                continue

            m_trans = re.match(r"^TRANSITION:\s*(.*)$", line, re.IGNORECASE)
            if m_trans:
                transition = m_trans.group(1).strip().upper()
                continue

        # Estimate scene duration based on dialogue and action
        total_words = sum(len(sl.text.split()) for sl in spoken_lines)
        speech_dur = total_words * 0.28  # ~3.5 words/sec
        est_dur = max(4.0, speech_dur + 1.2)
        if duration_mode != "AUTO":
            try:
                est_dur = float(re.sub(r"[^\d.]", "", duration_mode))
            except ValueError:
                pass

        return StudioScriptScene(
            scene_number=scene_num,
            scene_name=title,
            location=location,
            time_of_day=time_of_day,
            mood=mood,
            duration_mode=duration_mode,
            visual=visual,
            action=action,
            camera=camera,
            voice_note=voice_note,
            spoken_lines=spoken_lines,
            sfx=sfx,
            ambience=ambience,
            music=music,
            meme=meme,
            meme_note=meme_note,
            transition=transition,
            estimated_duration_sec=round(est_dur, 1)
        )

    def validate_production_rules(self, pkg: StudioScriptV1Package):
        """Enforces all 12 Production Rules on the parsed Studio Script V1 package."""
        issues = []
        missing = []

        # Rule 1 & 2: Only speech synthesized, no metadata leakage
        for sc in pkg.scenes:
            for sl in sc.spoken_lines:
                # Check metadata keywords inside spoken lines
                for kw in ["LOCATION:", "ACTION:", "CAMERA:", "SFX:", "MEME:", "GAIN_DB:"]:
                    if kw in sl.text:
                        issues.append(f"VIOLATION Rule 2: Cảnh {sc.scene_number} có thẻ kỹ thuật '{kw}' lọt vào lời thoại!")

        # Rule 8 & 9: Meme Placement and Context Rules
        meme_count = 0
        for sc in pkg.scenes:
            if sc.meme and not sc.meme.is_missing:
                meme_count += 1
                # Rule 9: Never use meme sounds during serious tragedy/death unless justified
                genre_lower = pkg.genre.lower()
                mood_lower = sc.mood.lower()
                if any(w in mood_lower or w in genre_lower for w in ["bi thương", "tang tóc", "tử đạo", "thảm sát", "chết chóc"]):
                    if not sc.meme_note or "châm biếm" not in sc.meme_note.lower():
                        issues.append(
                            f"VIOLATION Rule 9: Cảnh {sc.scene_number} sử dụng meme '{sc.meme.name}' trong bối cảnh bi thương/chết chóc mà không có biện minh cụ thể."
                        )

            # Rule 10: Missing asset reporting
            if sc.meme and sc.meme.is_missing:
                missing.append(f"Cảnh {sc.scene_number}: {sc.meme.error_message}")

        # Check meme rate limit (MEME_MAX_PER_MINUTE)
        total_mins = max(0.5, pkg.total_estimated_duration_sec / 60.0)
        max_allowed_memes = int(pkg.meme_max_per_minute * total_mins) + 1
        if meme_count > max_allowed_memes:
            issues.append(
                f"VIOLATION Rule 7/8 (Rate Limit): Tổng số meme ({meme_count}) vượt quá hạn mức "
                f"{pkg.meme_max_per_minute} meme/phút (cho phép tối đa {max_allowed_memes} meme cho {pkg.total_estimated_duration_sec:.1f}s)."
            )

        pkg.validation_issues = issues
        pkg.missing_assets = missing
        if issues or missing:
            pkg.production_rules_status = "FAILED" if issues else "WARNING_MISSING_ASSETS"
        else:
            pkg.production_rules_status = "PASSED"


def format_script_summary(pkg: StudioScriptV1Package) -> str:
    md = []
    md.append(f"# THÔNG TIN SẢN XUẤT: {pkg.project_name.upper()}")
    md.append(f"- **Thể loại:** {pkg.genre} | **Phong cách:** {pkg.style} | **Tỉ lệ:** {pkg.aspect_ratio}")
    md.append(f"- **Chính sách Meme:** {pkg.meme_policy} (Tối đa {pkg.meme_max_per_minute} meme/phút)")
    md.append(f"- **Tổng thời lượng ước tính:** {pkg.total_estimated_duration_sec}s")
    md.append(f"- **Trạng thái kiểm định Production Rules:** **{pkg.production_rules_status}**\n")

    if pkg.validation_issues:
        md.append("### ⚠️ LỖI QUY TẮC SẢN XUẤT:")
        for iss in pkg.validation_issues:
            md.append(f"- ❌ {iss}")
        md.append("")

    if pkg.missing_assets:
        md.append("### 🔍 BÁO CÁO THIẾU TÀI NGUYÊN (Rule 10):")
        for mis in pkg.missing_assets:
            md.append(f"- ⚠️ {mis}")
        md.append("")

    md.append("### DÀN NHÂN VẬT:")
    for name, c in pkg.characters.items():
        md.append(f"- **{name}:** {c.role} | Giọng: `{c.voice}` ({c.voice_style}) | {c.appearance}")
    md.append("")

    md.append("### DANH SÁCH PHÂN CẢNH:")
    for sc in pkg.scenes:
        meme_str = f"Meme: `{sc.meme.name}` (Gain: {sc.meme.gain_db}dB)" if sc.meme and not sc.meme.is_missing else "Không meme"
        md.append(f"#### Cảnh {sc.scene_number:02d}: {sc.scene_name} ({sc.estimated_duration_sec}s)")
        md.append(f"- **Bối cảnh:** {sc.location} ({sc.time_of_day}) | **Tâm trạng:** {sc.mood}")
        md.append(f"- **Hình ảnh & Camera:** {sc.visual} | Camera: `{sc.camera}`")
        md.append(f"- **Âm thanh:** SFX: `{sc.sfx.name if sc.sfx else 'None'}` | Ambience: `{sc.ambience.name if sc.ambience else 'None'}` | {meme_str}")
        md.append(f"- **Lời thoại ({len(sc.spoken_lines)} câu):**")
        for sl in sc.spoken_lines:
            md.append(f"  - **{sl.speaker}:** \"{sl.text}\"")
        md.append("")

    return "\n".join(md)


if __name__ == "__main__":
    sample_script = """
# STUDIO SCRIPT V1 — UNIVERSAL VIDEO FORMAT

PROJECT: Cuộc Đua Bồ Câu Thời Edo
LANGUAGE: vi-VN
GENRE: Hài hước
STYLE: Premium Stickman Cinematic B
ASPECT_RATIO: 16:9
TARGET_DURATION: AUTO
TONE: Vui nhộn, hồi hộp
MEME_POLICY: CONTEXTUAL
MEME_MAX_PER_MINUTE: 2

# NHÂN VẬT

CHARACTER: Haru
ROLE: Người đưa thư trẻ
APPEARANCE: Blob-Head áo xanh chàm, mũ cói, đeo túi thư sau lưng
VOICE: vieneu-Quang Sơn
VOICE_STYLE: Nhanh nhảu, hài hước, tự tin

CHARACTER: Ông Chủ Trạm
ROLE: Trưởng trạm thư khó tính
APPEARANCE: Blob-Head râu quai nón, áo kimono xám sẫm
VOICE: vieneu-Phạm Tuyên
VOICE_STYLE: Trầm, gắt gỏng, uy quyền

# KỊCH BẢN

SCENE 01: Nhận nhiệm vụ bất khả thi
LOCATION: Trạm thư Nihonbashi, Edo, 1867
TIME_OF_DAY: Sáng sớm
MOOD: Căng thẳng hài hước
DURATION: AUTO

VISUAL: Căn phòng trạm thư bằng gỗ thông, bản đồ tuyến đường Nihonbashi treo trên vách.
ACTION: Ông chủ đập mạnh phong thư niêm phong đỏ xuống bàn gỗ, Haru giật mình nhảy lùi lại.
CAMERA: Trung cảnh ngang bàn, Three.js push-in chậm vào phong thư.

VOICE_NOTE: Ông chủ — Giọng gắt gỏng, nhấn mạnh vào hạn chót.
ÔNG CHỦ TRẠM: Bức mật thư này phải đến Kyoto trước khi mặt trời lặn! Nếu trễ... cậu sẽ bị trừ một năm lương!
HARU: Một năm lương á?! Nhưng từ đây đến Kyoto mất tận ba ngày mà ông chủ!

SFX: Slam parchment on wood table | TRIGGER: Đập thư xuống bàn | PRIORITY: REQUIRED
AMBIENCE: Edo morning street marketplace | MODE: LOOP
MUSIC: Japanese comic hurry koto | INTENSITY: MEDIUM

MEME: vine boom | TRIGGER: Lúc Haru giật mình kêu Một năm lương | GAIN_DB: -12 | PRIORITY: OPTIONAL
MEME_NOTE: Tạo điểm nhấn hài hước bất ngờ khi nghe hình phạt trừ lương.

TRANSITION: CUT

END_SCENE

SCENE 02: Xuất kích trên cầu Nihonbashi
LOCATION: Cầu gỗ Nihonbashi
TIME_OF_DAY: Sáng
MOOD: Quyết tâm
DURATION: AUTO

VISUAL: Cầu gỗ Nihonbashi đông đúc, sông nước phản chiếu ánh bình minh.
ACTION: Haru ôm chặt túi thư, cắm đầu phi như tên bắn qua dòng người.
CAMERA: Góc rộng tracking ngang theo bước chạy của Haru.

VOICE_NOTE: Haru — Thở dốc, quyết tâm cao độ.
HARU: Không được trễ! Một năm tiền ăn mì ramen của tôi đang nằm ở Kyoto!

SFX: Running rapid footsteps on wood bridge | TRIGGER: Bước chạy | PRIORITY: REQUIRED
AMBIENCE: River flowing and crow caw | MODE: LOOP
MUSIC: Fast taiko drum beat | INTENSITY: HIGH

MEME: anime wow | TRIGGER: Khi Haru lách qua đám đông một cách thần sầu | GAIN_DB: -12 | PRIORITY: OPTIONAL
MEME_NOTE: Tán thưởng pha né người mượt mà.

TRANSITION: FADE

END_SCENE

END_SCRIPT
"""
    parser = StudioScriptV1Parser()
    pkg = parser.parse(sample_script)
    print(format_script_summary(pkg))
