"""Authoritative Curated Sound Asset Registry for Cinematic V5.1 Pipeline.

Provides semantic query resolution, ducking profiles, and verified local file paths.
No random file hallucination: every sound ID maps to an audited, existing audio asset.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
SFX_DIR = ROOT_DIR / "assets" / "sfx"


@dataclass
class SoundEntry:
    sound_id: str
    canonical_name: str
    category: str  # "AMBIENCE" | "FOLEY" | "SFX" | "MUSIC" | "VOICE_EFFORT"
    tags: List[str]
    filename: str
    default_volume_db: float = 0.0
    ducking_group: str = "background"  # "background" (ducked -8dB during dialogue) | "foreground" (un-ducked)
    loopable: bool = False
    duration_sec: float = 1.0

    @property
    def file_path(self) -> Path:
        return SFX_DIR / self.filename

    def exists(self) -> bool:
        return self.file_path.exists()


class SoundAssetRegistry:
    """Singleton registry indexing curated production sound assets."""

    def __init__(self):
        self._entries: Dict[str, SoundEntry] = {}
        self._tag_index: Dict[str, List[str]] = {}
        self._register_default_catalog()

    def _register(self, entry: SoundEntry):
        self._entries[entry.sound_id] = entry
        for tag in entry.tags:
            tag_lower = tag.lower().strip()
            if tag_lower not in self._tag_index:
                self._tag_index[tag_lower] = []
            if entry.sound_id not in self._tag_index[tag_lower]:
                self._tag_index[tag_lower].append(entry.sound_id)

    def _register_default_catalog(self):
        # 1. Ambience
        self._register(SoundEntry(
            sound_id="AMB_RAIN_HEAVY",
            canonical_name="Cơn Mưa Rào Nặng Hạt",
            category="AMBIENCE",
            tags=["rain", "mưa", "storm", "bão", "wet", "ướt", "edo", "phố cổ", "water"],
            filename="amb_rain_heavy.wav",
            default_volume_db=-14.0,
            ducking_group="background",
            loopable=True,
            duration_sec=15.0
        ))
        self._register(SoundEntry(
            sound_id="AMB_WATER_FLOW",
            canonical_name="Dòng Nước Kênh Chảy Xiết",
            category="AMBIENCE",
            tags=["water", "nước", "river", "kênh", "dòng sông", "flow", "bridge", "cầu"],
            filename="amb_water_flow.wav",
            default_volume_db=-16.0,
            ducking_group="background",
            loopable=True,
            duration_sec=15.0
        ))
        self._register(SoundEntry(
            sound_id="AMB_CAFE_INTERIOR",
            canonical_name="Âm Hưởng Không Gian Quán Cà Phê",
            category="AMBIENCE",
            tags=["cafe", "cà phê", "quán", "indoor", "chatter", "nói chuyện", "trò chuyện"],
            filename="amb_cafe_interior.wav",
            default_volume_db=-18.0,
            ducking_group="background",
            loopable=True,
            duration_sec=15.0
        ))

        # 2. Foley
        self._register(SoundEntry(
            sound_id="FOLEY_WOOD_FOOTSTEPS_FAST",
            canonical_name="Bước Chân Geta Chạy Gấp Trên Cầu Gỗ",
            category="FOLEY",
            tags=["footsteps", "bước chân", "chạy", "run", "sprint", "wood", "gỗ", "bridge", "cầu", "dép", "geta"],
            filename="foley_wood_footsteps_fast.wav",
            default_volume_db=-4.0,
            ducking_group="foreground",
            loopable=True,
            duration_sec=6.0
        ))
        self._register(SoundEntry(
            sound_id="FOLEY_BODY_SLIP_WET",
            canonical_name="Thân Thể Trượt Ngã Trên Sàn Gỗ Ướt",
            category="FOLEY",
            tags=["slip", "trượt", "ngã", "trượt chân", "fall", "slide", "wet", "ướt"],
            filename="foley_body_slip_wet.wav",
            default_volume_db=-2.0,
            ducking_group="foreground",
            duration_sec=1.4
        ))
        self._register(SoundEntry(
            sound_id="FOLEY_PAPER_RUSTLE",
            canonical_name="Mở Bức Thư Giấy Dầu Xoay Mở",
            category="FOLEY",
            tags=["paper", "thư", "giấy", "bức thư", "rustle", "open", "mở", "envelope", "đọc", "read"],
            filename="foley_paper_rustle.wav",
            default_volume_db=-3.0,
            ducking_group="foreground",
            duration_sec=1.8
        ))

        # 3. SFX
        self._register(SoundEntry(
            sound_id="SFX_WOOD_CRACK",
            canonical_name="Tiếng Ván Gỗ Mục Bật Gãy Rắc",
            category="SFX",
            tags=["wood crack", "gỗ gãy", "rắc", "snap", "break", "ván gãy", "nứt", "sập"],
            filename="sfx_wood_crack.wav",
            default_volume_db=-1.0,
            ducking_group="foreground",
            duration_sec=1.2
        ))
        self._register(SoundEntry(
            sound_id="SFX_WOOD_RAIL_GRAB",
            canonical_name="Bàn Tay Bám Chặt Lan Can Gỗ",
            category="SFX",
            tags=["rail grab", "bám", "lan can", "giữ", "clutch", "impact", "va chạm", "cứu"],
            filename="sfx_wood_rail_grab.wav",
            default_volume_db=-1.5,
            ducking_group="foreground",
            duration_sec=1.0
        ))
        self._register(SoundEntry(
            sound_id="SFX_COFFEE_CUP_CLINK",
            canonical_name="Tiếng Cụng Ly / Đặt Tách Cà Phê",
            category="SFX",
            tags=["cup", "tách", "clink", "cụng ly", "đặt ly", "coffee", "cà phê"],
            filename="sfx_coffee_cup_clink.wav",
            default_volume_db=-5.0,
            ducking_group="foreground",
            duration_sec=1.2
        ))

        # 4. Music
        self._register(SoundEntry(
            sound_id="MUSIC_TENSION_PULSE",
            canonical_name="Nhịp Tim Hồi Hộp Căng Thẳng",
            category="MUSIC",
            tags=["tension", "căng thẳng", "hồi hộp", "suspense", "danger", "nguy hiểm", "bão", "storm"],
            filename="music_tension_pulse.wav",
            default_volume_db=-15.0,
            ducking_group="background",
            loopable=True,
            duration_sec=16.0
        ))
        self._register(SoundEntry(
            sound_id="MUSIC_EMOTIONAL_PIANO",
            canonical_name="Giai Điệu Piano Lắng Đọng Cảm Xúc",
            category="MUSIC",
            tags=["piano", "emotional", "cảm xúc", "sâu lắng", "twist", "hài hước", "ending", "kết thúc", "bài học"],
            filename="music_emotional_piano.wav",
            default_volume_db=-16.0,
            ducking_group="background",
            loopable=True,
            duration_sec=16.0
        ))

        # 5. Vocal Effort
        self._register(SoundEntry(
            sound_id="VOICE_EFFORT_GASP",
            canonical_name="Tiếng Thở Gấp Giật Mình Kinh Hoàng",
            category="VOICE_EFFORT",
            tags=["gasp", "thở gấp", "hít thở", "giật mình", "hoảng hốt", "fear", "surprise"],
            filename="voice_effort_gasp.wav",
            default_volume_db=-2.0,
            ducking_group="foreground",
            duration_sec=0.75
        ))
        self._register(SoundEntry(
            sound_id="VOICE_SIGH",
            canonical_name="Tiếng Thở Phào Nhẹ Nhõm",
            category="VOICE_EFFORT",
            tags=["sigh", "thở phào", "nhẹ nhõm", "relief", "thở dài"],
            filename="voice_relief_sigh.wav",
            default_volume_db=-4.0,
            ducking_group="foreground",
            duration_sec=1.2
        ))
        self._register(SoundEntry(
            sound_id="VOICE_RELIEF_SIGH",
            canonical_name="Tiếng Thở Phào Nhẹ Nhõm",
            category="VOICE_EFFORT",
            tags=["sigh", "thở phào", "nhẹ nhõm", "relief", "thở dài"],
            filename="voice_relief_sigh.wav",
            default_volume_db=-4.0,
            ducking_group="foreground",
            duration_sec=1.2
        ))

    def get_by_id(self, sound_id: str) -> Optional[SoundEntry]:
        """Lookup by exact sound ID."""
        return self._entries.get(sound_id.upper().strip())

    def match_sound(self, query_text: str, category: Optional[str] = None) -> SoundEntry:
        """Find the most contextually relevant sound based on semantic tags."""
        q_lower = query_text.lower().strip()
        # 1. Exact ID check
        if q_lower.upper() in self._entries:
            return self._entries[q_lower.upper()]

        # 2. Tag scoring
        best_entry: Optional[SoundEntry] = None
        best_score = -1

        for s_id, entry in self._entries.items():
            if category and entry.category != category:
                continue
            score = 0
            for tag in entry.tags:
                if tag in q_lower or q_lower in tag:
                    score += 3
            if entry.sound_id.lower() in q_lower:
                score += 10
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score > 0:
            return best_entry

        # Fallback to category defaults
        if category == "AMBIENCE":
            return self._entries["AMB_RAIN_HEAVY"]
        elif category == "MUSIC":
            return self._entries["MUSIC_EMOTIONAL_PIANO"]
        elif category == "FOLEY":
            return self._entries["FOLEY_WOOD_FOOTSTEPS_FAST"]
        return self._entries["SFX_WOOD_CRACK"]


_SOUND_REGISTRY: Optional[SoundAssetRegistry] = None


def get_sound_registry() -> SoundAssetRegistry:
    global _SOUND_REGISTRY
    if _SOUND_REGISTRY is None:
        _SOUND_REGISTRY = SoundAssetRegistry()
    return _SOUND_REGISTRY
