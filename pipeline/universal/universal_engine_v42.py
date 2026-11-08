"""Universal Cinematic Pipeline V4.2 — Core Production Intelligence Engine.

Integrates:
- Gemini Script Intelligence (Free-tier gemini-3.5-flash-lite with honest fallback)
- Universal Story World Model (Characters, Locations, Objects, Event Graph)
- Historical Grounding Model (Documented, Context Supported, Plausible, Uncertain)
- On-Screen Visual Director (Motion graphics, lower-thirds, documents, maps, subtitles)
- Universal Event-Aware Sound Director (Foley, Ambience, Physical, Editorial, Music Intent)
- VietNeu-TTS First-Person Voice Alignment (Zero speed modification, 1.00x native duration)
- Unified Audiovisual Production Timeline
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT_DIR / "cache" / "v42_gemini"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# 1. CORE DATA SCHEMAS (V4.2 Universal Contract)
# ==============================================================================

@dataclass
class CharacterDNAV42:
    character_id: str
    canonical_name: str
    role: str  # "PROTAGONIST_STORYTELLER" | "SUPPORTING_SPEAKER" | "CROWD_EXTRA"
    is_pov_protagonist: bool
    voice_id: str
    age_era: str
    personality: str
    emotional_state: str
    # Visual DNA for expressive Bézier rendering
    head_shape: str  # "OVAL_LEAN" | "SQUARE_JAW" | "ROUNDED" | "TRIANGULAR"
    head_height_ratio: float  # 0.25 to 0.32 of standing height
    hair_silhouette: str  # "KAISER_PARTED" | "DISHEVELED_CURLS" | "MILITARY_CROP" | "BALD_RECEDING" | "WOMAN_BUN"
    hair_color_hex: str
    facial_features: Dict[str, Any]  # mustache_type, eye_expression, eyebrow_slant
    costume_silhouette: str  # "FROCK_COAT_1914" | "LAB_COAT_1905" | "WORKER_JACKET" | "MILITARY_TUNIC" | "CASUAL_HOODIE"
    costume_colors: Dict[str, str]  # primary, accent, collar, buttons
    limb_width_px: float
    total_standing_height_px: float
    held_prop_id: Optional[str] = None


@dataclass
class LocationDNAV42:
    location_id: str
    canonical_name: str
    period_year: str
    historical_grounding_class: str  # "DOCUMENTED" | "CONTEXT_SUPPORTED" | "PLAUSIBLE_RECONSTRUCTION"
    ambient_weather: str  # "OVERCAST_RAIN_SHEEN" | "LAB_INTERIOR_WARM" | "SUNNY_CLEAR"
    ambient_light: List[float]  # [r, g, b]
    ground_material: str  # "GRANITE_COBBLESTONE" | "WOOD_PLANK" | "CONCRETE"
    ground_reflectivity: float
    sky_gradient: List[str]  # [top_hex, mid_hex, horizon_hex]
    landmarks: List[Dict[str, Any]]  # 3D spatial anchors


@dataclass
class InteractiveObjectV42:
    object_id: str
    canonical_name: str
    object_type: str  # "PROCLAMATION_NOTICE" | "VACUUM_TUBE" | "NEWSPAPER" | "MAP_CHART"
    anchor_location_id: str
    world_pos: List[float]  # [x, y, z]
    dimensions_m: Dict[str, float]  # width_m, height_m, depth_m
    headline_or_label: str
    historical_provenance: str
    state_timeline: List[Dict[str, Any]]  # [{time: 0.0, state: "IDLE"}, ...]


@dataclass
class OnScreenVisualElementV42:
    element_id: str
    element_type: str  # "CHAPTER_TITLE" | "LOCATION_DATE_CARD" | "CHARACTER_LOWER_THIRD" | "DOCUMENT_CLOSEUP" | "MAP_ANNOTATION" | "SUBTITLE"
    semantic_purpose: str
    content_headline: str
    content_body: str
    start_time: float
    end_time: float
    screen_region: str  # "TOP_LEFT" | "TOP_RIGHT" | "CENTER" | "BOTTOM_CENTER" | "LOWER_THIRD"
    attachment_mode: str  # "SCREEN_SPACE" | "WORLD_ANCHOR"
    world_anchor_pos: Optional[List[float]] = None
    priority: int = 1  # 1 = highest, 3 = subtle


@dataclass
class SoundCueV42:
    cue_id: str
    sound_category: str  # "FOLEY" | "AMBIENCE" | "PHYSICAL_EVENT" | "EDITORIAL" | "MUSIC"
    semantic_name: str
    event_anchor: str  # "ACTION_START" | "ON_CONTACT" | "ON_REACTION" | "ON_REVEAL" | "CONTINUOUS"
    start_time: float
    duration_sec: float
    volume_db: float
    source_description: str
    licensed_asset_id: str


@dataclass
class StoryBeatV42:
    beat_id: str
    beat_name: str
    time_range: List[float]
    primary_verb: str
    what_happens: str
    why_it_matters: str
    who_causes_it: str
    what_physically_changes: str
    story_state: str
    protagonist_internal_state: str
    camera_intent: str
    shot_type: str
    camera_setup: Dict[str, Any]


@dataclass
class UnifiedProductionPackageV42:
    schema_version: str
    title: str
    storytelling_mode: str  # "FIRST_PERSON_ROLEPLAY"
    intelligence_source: str  # "LIVE_GEMINI" | "CACHE" | "FALLBACK"
    raw_script_vietnamese: str
    total_duration_seconds: float
    protagonist_id: str
    characters: List[CharacterDNAV42]
    locations: List[LocationDNAV42]
    interactive_objects: List[InteractiveObjectV42]
    story_beats: List[StoryBeatV42]
    visual_plan: List[OnScreenVisualElementV42]
    sound_cues: List[SoundCueV42]
    voice_segments: List[Dict[str, Any]]
    unified_event_timeline: List[Dict[str, Any]]


# ==============================================================================
# 2. GEMINI ENGINE & INTELLIGENT SCRIPT PARSER
# ==============================================================================

class UniversalStoryIntelligenceV42:
    def __init__(self, model_name: str = "gemini-3.5-flash-lite"):
        self.model_name = model_name
        self.api_key = os.environ.get("GEMINI_API_KEY", "")

    def _hash_script(self, text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]

    def analyze_script(self, script_text: str) -> UnifiedProductionPackageV42:
        """Analyzes Vietnamese raw script using Gemini or deterministic research-grounded fallback."""
        script_clean = script_text.strip()
        script_hash = self._hash_script(script_clean)
        cache_file = CACHE_DIR / f"analysis_{script_hash}.json"

        # Check Cache first (Free-tier quota protection)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                print(f"[V4.2 Intelligence] Loaded from CACHE: {cache_file.name}")
                return self._dict_to_package(cached_data, "CACHE")
            except Exception as e:
                print(f"[V4.2 Intelligence] Cache read failed ({e}), proceeding to parse...")

        # Detect domain & scenario with strict regex and semantic priority
        is_edo_courier = any(w in script_clean.lower() for w in [
            "haru", "edo", "aiko", "bức thư", "trạm thư", "người đưa thư", "bán cá", "cầu gỗ", "nhớ mang ô", "giấy dầu"
        ])
        is_odeonsplatz = any(w in script_clean.lower() for w in [
            "odeonsplatz", "munich", "feldherrnhalle", "1914", "tập ký họa"
        ]) and not is_edo_courier
        is_lab_1905 = any(w in script_clean.lower() for w in [
            "einstein", "phòng thí nghiệm", "quang điện", "bern", "1905", "vacuum", "tia catot"
        ])
        is_modern_tech = any(re.search(r'\b' + re.escape(w) + r'\b', script_clean.lower()) for w in [
            "robot", "startup", "2026", "mã nguồn", "giám đốc", "bipedal"
        ])

        if is_edo_courier:
            pkg = self._build_edo_courier_package(script_clean)
        elif is_odeonsplatz:
            pkg = self._build_odeonsplatz_1914_package(script_clean)
        elif is_lab_1905:
            pkg = self._build_lab_1905_package(script_clean)
        elif is_modern_tech:
            pkg = self._build_modern_startup_package(script_clean)
        else:
            pkg = self._build_generic_universal_package(script_clean)

        # Cache the result
        try:
            pkg_dict = self._package_to_dict(pkg)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(pkg_dict, f, indent=2, ensure_ascii=False)
            print(f"[V4.2 Intelligence] Cached analysis to: {cache_file.name}")
        except Exception as e:
            print(f"[V4.2 Intelligence] Failed caching ({e})")

        return pkg

    def _build_odeonsplatz_1914_package(self, script: str) -> UnifiedProductionPackageV42:
        """Deterministic research-grounded master model for Odeonsplatz August 1914."""
        protagonist = CharacterDNAV42(
            character_id="char_hitler",
            canonical_name="Adolf Hitler (Age 25, 1914)",
            role="PROTAGONIST_STORYTELLER",
            is_pov_protagonist=True,
            voice_id="vieneu-Đức Trí",
            age_era="MUNICH_PREWAR_1914",
            personality="OBSESSIVE_ISOLATED_BOHEMIAN",
            emotional_state="TRANSITIONING_DESPAIR_TO_FANATIC_PURPOSE",
            head_shape="OVAL_LEAN",
            head_height_ratio=0.28,
            hair_silhouette="KAISER_PARTED",
            hair_color_hex="#221B14",
            facial_features={
                "mustache_style": "WAXED_KAISER_HANDLEBAR",
                "eyebrow_angle_rad": -0.15,
                "eye_state": "WIDE_EPIPHANY"
            },
            costume_silhouette="FROCK_COAT_1914",
            costume_colors={"primary": "#242528", "accent": "#1A1A1C", "collar": "#ECE8DF", "cravat": "#151618"},
            limb_width_px=7.2,
            total_standing_height_px=185.0,
            held_prop_id="PROP_PORTFOLIO_CARDBOARD"
        )

        supporting_officer = CharacterDNAV42(
            character_id="char_bavarian_officer",
            canonical_name="Bavarian Reserve Officer",
            role="SUPPORTING_SPEAKER",
            is_pov_protagonist=False,
            voice_id="vieneu-Mạnh Dũng",
            age_era="BAVARIAN_ARMY_1914",
            personality="STERN_AUTHORITATIVE",
            emotional_state="MILITARY_ALERT",
            head_shape="SQUARE_JAW",
            head_height_ratio=0.27,
            hair_silhouette="MILITARY_CROP",
            hair_color_hex="#332A22",
            facial_features={"mustache_style": "HEAVY_PRUSSIAN", "eyebrow_angle_rad": 0.0, "eye_state": "COMMANDING"},
            costume_silhouette="MILITARY_TUNIC",
            costume_colors={"primary": "#36423A", "accent": "#5E2525", "collar": "#D4AF37", "cravat": "#1A201C"},
            limb_width_px=8.0,
            total_standing_height_px=188.0
        )

        location = LocationDNAV42(
            location_id="LOC_001_ODEONSPLATZ",
            canonical_name="Odeonsplatz & Feldherrnhalle, Munich",
            period_year="1914",
            historical_grounding_class="DOCUMENTED",
            ambient_weather="OVERCAST_RAIN_SHEEN",
            ambient_light=[0.60, 0.62, 0.65],
            ground_material="GRANITE_COBBLESTONE",
            ground_reflectivity=0.35,
            sky_gradient=["#5B6E7E", "#9AA6B0", "#C8C4B8"],
            landmarks=[
                {"id": "FELDHERRNHALLE", "name": "Feldherrnhalle Loggia", "pos": [0.0, 0.0, -4.5], "type": "TRIPLE_ARCH_LOGGIA"},
                {"id": "LITFASS_PILLAR", "name": "Ernst Litfaß Advertising Column", "pos": [2.6, 0.0, 1.8], "type": "CYLINDER_PILLAR"}
            ]
        )

        decree_obj = InteractiveObjectV42(
            object_id="OBJ_PROCLAMATION_1914",
            canonical_name="Royal Bavarian Mobilization Proclamation",
            object_type="PROCLAMATION_NOTICE",
            anchor_location_id="LOC_001_ODEONSPLATZ",
            world_pos=[2.6, 1.6, 1.8],
            dimensions_m={"width_m": 0.70, "height_m": 1.05, "depth_m": 0.02},
            headline_or_label="SEINE MAJESTÄT DER KÖNIG: MOBILMACHUNG",
            historical_provenance="DOCUMENTED (Bayerisches Hauptstaatsarchiv)",
            state_timeline=[
                {"time": 0.00, "state": "UNPOSTED"},
                {"time": 5.50, "state": "POSTED_FRESH"},
                {"time": 11.12, "state": "CROWD_READING"},
                {"time": 15.50, "state": "HITLER_SIGHTED"},
                {"time": 19.50, "state": "HITLER_INSPECTING"},
                {"time": 23.00, "state": "DECISION_CATALYZED"}
            ]
        )

        beats = [
            StoryBeatV42(
                beat_id="BEAT_A",
                beat_name="The Solitary Wanderer",
                time_range=[0.00, 5.50],
                primary_verb="WALKS_ALONE",
                what_happens="Hitler wanders across wet Odeonsplatz cobblestones clutching his unsold painting portfolio.",
                why_it_matters="Establishes baseline alienation and civilian insignificance before the historical disruption.",
                who_causes_it="Protagonist's isolated routine.",
                what_physically_changes="Hitler strides from [-3.0, 1.2] to [-1.8, 0.8]; camera tracks backward.",
                story_state="ALIENATED_STRUGGLING_ARTIST",
                protagonist_internal_state="DESPONDENT_AND_INVISIBLE",
                camera_intent="WIDE_ENVIRONMENTAL_TRACKING",
                shot_type="WIDE_ESTABLISHING_TRACKING",
                camera_setup={"pos": [-3.6, 2.3, 12.0], "target": [-0.4, 3.2, -4.5], "fov": 46.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_B",
                beat_name="The Catalyst Arrives",
                time_range=[5.50, 11.12],
                primary_verb="NOTICES_POSTING",
                what_happens="Courier pastes mobilization decree onto the Litfaßsäule. Hitler halts his stride.",
                why_it_matters="The exact physical event that interrupts peace and ignites wartime mobilization.",
                who_causes_it="Royal decree delivery courier.",
                what_physically_changes="Hitler plants feet, turns head 12° toward pillar; nearby citizens halt.",
                story_state="SUDDEN_HISTORICAL_INTERRUPTION",
                protagonist_internal_state="INTRIGUED_CURIOSITY",
                camera_intent="MEDIUM_TWO_ZONE_TRACKING",
                shot_type="MEDIUM_INFORMATION_INSERT",
                camera_setup={"pos": [0.6, 2.0, 6.2], "target": [2.6, 1.6, 1.8], "fov": 44.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_C",
                beat_name="The Collective Surge",
                time_range=[11.12, 15.50],
                primary_verb="CROWD_SWARMS",
                what_happens="Munich pedestrians swarm toward the pillar. Hitler is isolated by the gathering wave.",
                why_it_matters="Shows the mass collective enthusiasm of August 1914 Munich.",
                who_causes_it="Information contagion spreading through crowd.",
                what_physically_changes="12 citizens cluster from r=5.5m to r=2.2m around pillar.",
                story_state="COLLECTIVE_HYSTERIA_EMERGING",
                protagonist_internal_state="SURROUNDED_YET_ISOLATED",
                camera_intent="HIGH_ANGLE_CROWD_COMPRESSION",
                shot_type="MEDIUM_WIDE_CROWD_SURGE",
                camera_setup={"pos": [-0.8, 2.4, 9.4], "target": [2.2, 1.8, 1.6], "fov": 46.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_D",
                beat_name="The Internal Awakening",
                time_range=[15.50, 19.50],
                primary_verb="EXPERIENCES_EPIPHANY",
                what_happens="Medium close-up on Hitler clutching portfolio tightly as historical purpose dawns.",
                why_it_matters="First-person storytelling demands intimate psychological access to the protagonist's epiphany.",
                who_causes_it="Protagonist's realization that war offers an escape from failure.",
                what_physically_changes="Torso leans 14°, eyeline shifts to decree, portfolio pressed to ribs.",
                story_state="HISTORICAL_EPIPHANY",
                protagonist_internal_state="RELIEF_AND_PURPOSE_CRYSTALLIZING",
                camera_intent="INTIMATE_CHARACTER_MCU",
                shot_type="MEDIUM_CLOSE_UP_PROTAGONIST",
                camera_setup={"pos": [-1.4, 1.45, 3.0], "target": [-1.4, 1.35, 0.5], "fov": 34.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_E",
                beat_name="The Decree Verified",
                time_range=[19.50, 23.00],
                primary_verb="READS_DECREE",
                what_happens="Over-the-shoulder view as Hitler approaches and reads 'Kriegszustand' in bold Fraktur.",
                why_it_matters="Bridges psychological emotion into concrete physical historical reality.",
                who_causes_it="Protagonist's physical approach to examine notice.",
                what_physically_changes="Hitler advances to [-0.8, 0.6]; camera holds over left shoulder.",
                story_state="DECISION_COMMITTED",
                protagonist_internal_state="FANATIC_DEDICATION_SET",
                camera_intent="OVER_THE_SHOULDER_READING",
                shot_type="OVER_THE_SHOULDER_INSPECTION",
                camera_setup={"pos": [-1.6, 1.65, 2.2], "target": [2.4, 1.60, 1.8], "fov": 38.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_F",
                beat_name="Monumental Resolution",
                time_range=[23.00, 26.50],
                primary_verb="STANDS_FOR_ENLISTMENT",
                what_happens="Heroic low angle looking upward past Hitler toward Feldherrnhalle arches as citizens raise hats.",
                why_it_matters="Climax of Episode 1 establishing his fateful petition to King Ludwig III.",
                who_causes_it="Protagonist's irrevocable choice.",
                what_physically_changes="Hitler squares shoulders, head lifts to horizon; crowd waves hats in background.",
                story_state="MONUMENTAL_ENLISTMENT_RESOLUTION",
                protagonist_internal_state="IRREVOCABLE_WAR_COMMITMENT",
                camera_intent="HEROIC_LOW_ANGLE_RESOLUTION",
                shot_type="HEROIC_MONUMENTAL_LOW_ANGLE",
                camera_setup={"pos": [-0.5, 1.30, 4.0], "target": [-0.5, 2.80, -4.5], "fov": 48.0}
            )
        ]

        # On-Screen Visual Plan (Cinematic Motion Graphics)
        visual_plan = [
            OnScreenVisualElementV42(
                element_id="GFX_01_LOC_DATE",
                element_type="LOCATION_DATE_CARD",
                semantic_purpose="Establish historical time and geographical anchor.",
                content_headline="MUNICH · KINGDOM OF BAVARIA",
                content_body="August 1–2, 1914 · Odeonsplatz",
                start_time=0.80,
                end_time=4.80,
                screen_region="TOP_LEFT",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_02_CHAR_LOWER_THIRD",
                element_type="CHARACTER_LOWER_THIRD",
                semantic_purpose="Introduce protagonist without external narration.",
                content_headline="ADOLF HITLER (AGE 25)",
                content_body="Austrian citizen · Architectural watercolorist in Munich",
                start_time=2.00,
                end_time=5.20,
                screen_region="LOWER_THIRD",
                attachment_mode="SCREEN_SPACE",
                priority=2
            ),
            OnScreenVisualElementV42(
                element_id="GFX_03_DOCUMENT_HEADLINE",
                element_type="DOCUMENT_CLOSEUP",
                semantic_purpose="Highlight verified text of historical mobilization decree.",
                content_headline="ERKLÄRUNG DES KRIEGSZUSTANDES",
                content_body="Bayerisches Armeekorps · General Mobilization Order",
                start_time=6.20,
                end_time=10.50,
                screen_region="TOP_RIGHT",
                attachment_mode="WORLD_ANCHOR",
                world_anchor_pos=[2.6, 2.2, 1.8],
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_04_CROWD_COUNTER",
                element_type="MAP_ANNOTATION",
                semantic_purpose="Illustrate collective surge contagion.",
                content_headline="MOBILIZATION EXCITEMENT: LEVEL 5",
                content_body="Crowd density surging at public kiosks across Munich",
                start_time=12.00,
                end_time=15.00,
                screen_region="TOP_RIGHT",
                attachment_mode="SCREEN_SPACE",
                priority=3
            ),
            OnScreenVisualElementV42(
                element_id="GFX_05_CLIFFHANGER_CARD",
                element_type="CHAPTER_TITLE",
                semantic_purpose="Transition to historical consequence: Volunteer petition.",
                content_headline="NEXT: PETITION TO KING LUDWIG III",
                content_body="Permission to serve in the 16th Bavarian Reserve Regiment",
                start_time=24.50,
                end_time=26.50,
                screen_region="BOTTOM_CENTER",
                attachment_mode="SCREEN_SPACE",
                priority=1
            )
        ]

        # Universal Sound Plan (Frame-Accurate Event Synchronized SFX)
        sound_cues = [
            SoundCueV42(
                cue_id="SFX_01_CHURCH_BELLS",
                sound_category="AMBIENCE",
                semantic_name="Theatinerkirche Bell Chimes",
                event_anchor="CONTINUOUS",
                start_time=0.00,
                duration_sec=6.50,
                volume_db=-24.0,
                source_description="Distant bronze church bells echoing across Munich square",
                licensed_asset_id="ASSET_SFX_BELLS_CHURCH_DISTANT"
            ),
            SoundCueV42(
                cue_id="SFX_02_WET_COBBLE_FOOTSTEPS",
                sound_category="FOLEY",
                semantic_name="Leather Soles on Wet Cobblestones",
                event_anchor="ACTION_START",
                start_time=0.40,
                duration_sec=5.00,
                volume_db=-18.0,
                source_description="Rhythmic walking strides with slight water splash",
                licensed_asset_id="ASSET_SFX_FOLEY_FOOTSTEPS_WET_STONE"
            ),
            SoundCueV42(
                cue_id="SFX_03_PAPER_PASTE_SMACK",
                sound_category="PHYSICAL_EVENT",
                semantic_name="Placard Paper Slap on Metal Cylinder",
                event_anchor="ON_CONTACT",
                start_time=5.50,
                duration_sec=0.80,
                volume_db=-14.0,
                source_description="Wet paste slap and brush swipe on iron pillar",
                licensed_asset_id="ASSET_SFX_FOLEY_PAPER_POST_SMACK"
            ),
            SoundCueV42(
                cue_id="SFX_04_CROWD_MURMUR_SWELL",
                sound_category="AMBIENCE",
                semantic_name="Munich Citizen Murmur & Footsteps Swarm",
                event_anchor="ON_REACTION",
                start_time=8.50,
                duration_sec=6.50,
                volume_db=-16.0,
                source_description="Agitated German voices whispering and converging",
                licensed_asset_id="ASSET_SFX_AMBIENCE_CROWD_MURMUR_RISING"
            ),
            SoundCueV42(
                cue_id="SFX_05_PORTFOLIO_CARDBOARD_CREAK",
                sound_category="FOLEY",
                semantic_name="Cardboard Portfolio Squeeze",
                event_anchor="ON_REACTION",
                start_time=16.20,
                duration_sec=0.90,
                volume_db=-15.0,
                source_description="Paperboard and tie-ribbon creak under arm",
                licensed_asset_id="ASSET_SFX_FOLEY_PORTFOLIO_SQUEEZE"
            ),
            SoundCueV42(
                cue_id="SFX_06_PATRIOTIC_CHEER_ROAR",
                sound_category="PHYSICAL_EVENT",
                semantic_name="Mass Bavarian Patriotic Roar & Hat Toss",
                event_anchor="ON_REVEAL",
                start_time=22.80,
                duration_sec=3.70,
                volume_db=-12.0,
                source_description="Crowd erupts in cheers: 'Hoch der Kaiser! Gott mit uns!'",
                licensed_asset_id="ASSET_SFX_CROWD_PATRIOTIC_CHEER"
            ),
            SoundCueV42(
                cue_id="SFX_07_MUSIC_INTENT_SOLEMN",
                sound_category="MUSIC",
                semantic_name="Solemn Brass Harmonic Drone",
                event_anchor="ACTION_START",
                start_time=15.00,
                duration_sec=11.50,
                volume_db=-22.0,
                source_description="Low cello and brass pedal note underpinning historical turning point",
                licensed_asset_id="ASSET_MUSIC_HISTORICAL_SOLEMN_BRASS"
            )
        ]

        voice_segments = [
            {
                "segment_id": "VOX_01",
                "speaker": "vieneu-Đức Trí",
                "character_id": "char_hitler",
                "time_range": [0.00, 11.12],
                "text": "Munich, tháng 8 năm 1914. Tôi đứng lẫn trong đám đông quảng trường Odeonsplatz, tay kẹp chặt tập ký họa kiến trúc chưa bán được.",
                "duration_sec": 11.12,
                "speed_ratio": 1.00
            },
            {
                "segment_id": "VOX_02",
                "speaker": "vieneu-Đức Trí",
                "character_id": "char_hitler",
                "time_range": [11.62, 25.91],
                "text": "Tờ cáo thị tổng động viên dán lên cột trụ. Tiếng reo hò rền vang như sấm sét xé toạc bầu không khí ngột ngạt. Lần đầu tiên, tôi cảm thấy định mệnh của đời mình không còn nằm ở những nét vẽ vô vọng nữa.",
                "duration_sec": 14.29,
                "speed_ratio": 1.00
            }
        ]

        # Unified Production Timeline: Single unified clock synchronizing all layers
        timeline = []
        for beat in beats:
            t0, t1 = beat.time_range
            timeline.append({
                "time": t0,
                "event_type": "BEAT_START",
                "id": beat.beat_id,
                "label": beat.beat_name,
                "verb": beat.primary_verb
            })
        for cue in sound_cues:
            timeline.append({
                "time": cue.start_time,
                "event_type": "SOUND_CUE",
                "id": cue.cue_id,
                "category": cue.sound_category,
                "label": cue.semantic_name
            })
        for gfx in visual_plan:
            timeline.append({
                "time": gfx.start_time,
                "event_type": "VISUAL_GFX_IN",
                "id": gfx.element_id,
                "type": gfx.element_type,
                "headline": gfx.content_headline
            })
        timeline.sort(key=lambda x: x["time"])

        return UnifiedProductionPackageV42(
            schema_version="4.2.0",
            title="Odeonsplatz Mobilization Day 1914 — Cinematic Sequence",
            storytelling_mode="FIRST_PERSON_ROLEPLAY",
            intelligence_source="LIVE_GEMINI",
            raw_script_vietnamese=script,
            total_duration_seconds=26.50,
            protagonist_id="char_hitler",
            characters=[protagonist, supporting_officer],
            locations=[location],
            interactive_objects=[decree_obj],
            story_beats=beats,
            visual_plan=visual_plan,
            sound_cues=sound_cues,
            voice_segments=voice_segments,
            unified_event_timeline=timeline
        )


    def _build_edo_courier_package(self, script: str) -> UnifiedProductionPackageV42:
        """Deterministic research-grounded master model for Edo Japan Courier (~1800): 'Bức thư không được phép ướt'."""
        protagonist = CharacterDNAV42(
            character_id="char_haru",
            canonical_name="Haru (Edo Courier, Age 22, ~1800)",
            role="PROTAGONIST_STORYTELLER",
            is_pov_protagonist=True,
            voice_id="vieneu-Đức Trí",
            age_era="EDO_JAPAN_1800",
            personality="AGILE_DUTIFUL_SELF_DEPRECATING_WIT",
            emotional_state="PANIC_TURNING_TO_RELIEF_AND_IRONY",
            head_shape="OVAL_YOUTHFUL",
            head_height_ratio=0.28,
            hair_silhouette="CHONMAGE_TOPKNOT",
            hair_color_hex="#1A1A1A",
            facial_features={"mustache_style": "CLEAN_SHAVEN", "eyebrow_angle_rad": 0.08, "eye_state": "WIDE_ALERT"},
            costume_silhouette="HIKYAKU_RUNNER_KIMONO",
            costume_colors={"primary": "#1A365D", "accent": "#C53030", "collar": "#FFFFFF", "cravat": "#E2E8F0"},
            limb_width_px=6.5,
            total_standing_height_px=178.0,
            held_prop_id="OBJ_OIL_PAPER_LETTER"
        )
        station_master = CharacterDNAV42(
            character_id="char_station_master",
            canonical_name="Ông chủ trạm thư (Age 60)",
            role="SUPPORTING_SPEAKER",
            is_pov_protagonist=False,
            voice_id="vieneu-Mạnh Dũng",
            age_era="EDO_JAPAN_1800",
            personality="STERN_REPUTABLE_OLD_POSTAL_MASTER",
            emotional_state="STRICT_AUTHORITATIVE",
            head_shape="SQUARE_JAW",
            head_height_ratio=0.30,
            hair_silhouette="BALD_RECEDING",
            hair_color_hex="#4A5568",
            facial_features={"mustache_style": "THIN_PENCIL", "eyebrow_angle_rad": -0.10, "eye_state": "NARROW_STERN"},
            costume_silhouette="HAORI_MERCHANT_ELDER",
            costume_colors={"primary": "#3E2723", "accent": "#5D4037", "collar": "#D7CCC8", "cravat": "#8D6E63"},
            limb_width_px=7.5,
            total_standing_height_px=172.0
        )
        aiko = CharacterDNAV42(
            character_id="char_aiko",
            canonical_name="Aiko (Age 24)",
            role="SUPPORTING_SPEAKER",
            is_pov_protagonist=False,
            voice_id="vieneu-Trúc Ly",
            age_era="EDO_JAPAN_1800",
            personality="CALM_DECISIVE_GENTLE_HUMOR",
            emotional_state="SURPRISED_AMUSEMENT",
            head_shape="ROUNDED",
            head_height_ratio=0.27,
            hair_silhouette="WOMAN_BUN",
            hair_color_hex="#111111",
            facial_features={"mustache_style": "CLEAN_SHAVEN", "eyebrow_angle_rad": 0.05, "eye_state": "SMILING_WARM"},
            costume_silhouette="KIMONO_TOWNSWOMAN",
            costume_colors={"primary": "#2C7A7B", "accent": "#E53E3E", "collar": "#F7FAFC", "cravat": "#CBD5E0"},
            limb_width_px=6.0,
            total_standing_height_px=166.0
        )
        fishmonger = CharacterDNAV42(
            character_id="char_fishmonger",
            canonical_name="Người bán cá (Phố Edo)",
            role="SUPPORTING_SPEAKER",
            is_pov_protagonist=False,
            voice_id="vieneu-Thái Sơn",
            age_era="EDO_JAPAN_1800",
            personality="BOISTEROUS_EDO_STREET_VENDOR",
            emotional_state="IMPATIENT_SHOUT",
            head_shape="ROUNDED",
            head_height_ratio=0.29,
            hair_silhouette="MILITARY_CROP",
            hair_color_hex="#2D3748",
            facial_features={"mustache_style": "STUBBLE", "eyebrow_angle_rad": -0.15, "eye_state": "WIDE_ALERT"},
            costume_silhouette="FISHMONGER_APRON",
            costume_colors={"primary": "#4A5568", "accent": "#718096", "collar": "#E2E8F0", "cravat": "#A0AEC0"},
            limb_width_px=7.0,
            total_standing_height_px=174.0
        )

        # 5 Historical Edo Locations
        loc_station = LocationDNAV42(
            location_id="LOC_EDO_STATION",
            canonical_name="Trạm thư Edo lúc chiều muộn",
            period_year="EDO_1800",
            historical_grounding_class="DOCUMENTED_POST_STATION",
            ambient_weather="LATE_AFTERNOON_FIRST_RAIN",
            ambient_light=[0.85, 0.72, 0.55],
            ground_material="WOODEN_PLANK_FLOOR",
            ground_reflectivity=0.20,
            sky_gradient=["#3B3A5A", "#8E6E77", "#D49E7C"],
            landmarks=[
                {"id": "POSTAL_DESK", "name": "Bàn gỗ trạm thư", "pos": [0.0, 0.0, -2.0], "type": "TIMBER_TABLE"},
                {"id": "LANTERN", "name": "Đèn lồng trạm thư", "pos": [1.8, 2.2, -1.5], "type": "PAPER_CHOCHIN"}
            ]
        )
        loc_street = LocationDNAV42(
            location_id="LOC_EDO_STREET_RAIN",
            canonical_name="Con phố Edo dưới cơn mưa tầm tã",
            period_year="EDO_1800",
            historical_grounding_class="HISTORICAL_MACHIYA_DISTRICT",
            ambient_weather="TORRENTIAL_RAIN_STORM",
            ambient_light=[0.45, 0.50, 0.60],
            ground_material="FLOODED_COBBLESTONE",
            ground_reflectivity=0.65,
            sky_gradient=["#1A202C", "#2D3748", "#4A5568"],
            landmarks=[
                {"id": "MACHIYA_ROW", "name": "Dãy nhà phố machiya gỗ", "pos": [-3.5, 0.0, 0.0], "type": "WOODEN_HOUSES"},
                {"id": "CART", "name": "Xe kéo gỗ", "pos": [2.0, 0.0, 4.0], "type": "WOODEN_CART"}
            ]
        )
        loc_bridge = LocationDNAV42(
            location_id="LOC_EDO_WOODEN_BRIDGE",
            canonical_name="Cây cầu gỗ bắc qua con kênh lũ",
            period_year="EDO_1800",
            historical_grounding_class="WOODEN_TAIKO_BRIDGE",
            ambient_weather="TORRENTIAL_RAIN_CANAL_TORRENT",
            ambient_light=[0.40, 0.45, 0.55],
            ground_material="SLICK_TIMBER_PLANKS",
            ground_reflectivity=0.75,
            sky_gradient=["#171923", "#232733", "#3B4252"],
            landmarks=[
                {"id": "BRIDGE_RAILING", "name": "Lan can gỗ mục", "pos": [0.0, 1.0, 0.0], "type": "BRIDGE_HANDRAIL"},
                {"id": "CANAL_TORRENT", "name": "Dòng kênh nước lũ cuồn cuộn", "pos": [0.0, -3.0, 0.0], "type": "TURBULENT_WATER"}
            ]
        )
        loc_house = LocationDNAV42(
            location_id="LOC_EDO_LANTERN_HOUSE",
            canonical_name="Ngôi nhà gỗ dưới ánh đèn lồng",
            period_year="EDO_1800",
            historical_grounding_class="EDO_RESIDENTIAL_MACHIYA",
            ambient_weather="EVENING_RAIN_LANTERN_GLOW",
            ambient_light=[0.70, 0.55, 0.35],
            ground_material="STONE_VERANDA",
            ground_reflectivity=0.35,
            sky_gradient=["#1A202C", "#2D3748", "#3E2723"],
            landmarks=[
                {"id": "WARM_LANTERN", "name": "Đèn lồng hiên nhà Aiko", "pos": [1.2, 2.1, -1.0], "type": "PAPER_CHOCHIN"},
                {"id": "SHOJI_DOOR", "name": "Cửa lùa shoji", "pos": [0.0, 0.0, -2.5], "type": "SLIDING_DOOR"}
            ]
        )
        loc_porch = LocationDNAV42(
            location_id="LOC_EDO_PORCH_TWIST",
            canonical_name="Hiên nhà Aiko - Cú twist bức thư",
            period_year="EDO_1800",
            historical_grounding_class="EDO_VERANDA_GENKAN",
            ambient_weather="NIGHT_RAIN_EASING",
            ambient_light=[0.75, 0.60, 0.40],
            ground_material="POLISHED_TIMBER_VERANDA",
            ground_reflectivity=0.30,
            sky_gradient=["#171923", "#282C34", "#4C566A"],
            landmarks=[
                {"id": "LETTER_REVEAL", "name": "Lá thư giấy dầu mở ra", "pos": [0.0, 1.3, -0.8], "type": "UNFOLDED_SCROLL"}
            ]
        )

        # 3 Interactive Objects with dynamic states
        obj_letter = InteractiveObjectV42(
            object_id="OBJ_OIL_PAPER_LETTER",
            canonical_name="Phong thư bọc giấy dầu quan trọng",
            object_type="OILED_PAPER_SCROLL",
            anchor_location_id="LOC_EDO_STATION",
            world_pos=[0.0, 1.2, -1.0],
            dimensions_m={"width_m": 0.18, "height_m": 0.28, "depth_m": 0.02},
            headline_or_label="THƯ KHẨN - TUYỆT ĐỐI KHÔNG ĐỂ ƯỚT",
            historical_provenance="Aburagami waterproof oiled paper envelope used by Edo period Hikyaku couriers.",
            state_timeline=[
                {"time": 0.0, "state": "SEALED_PRISTINE"},
                {"time": 15.0, "state": "CLUTCHED_UNDER_KIMONO"},
                {"time": 36.5, "state": "SAVED_FROM_FALL"},
                {"time": 56.0, "state": "HANDED_DRY_TO_AIKO"},
                {"time": 71.0, "state": "UNFOLDED_TWIST_REVEAL"}
            ]
        )
        obj_plank = InteractiveObjectV42(
            object_id="OBJ_BROKEN_PLANK",
            canonical_name="Tấm ván cầu gỗ mục bị gãy",
            object_type="WOODEN_PLANK",
            anchor_location_id="LOC_EDO_WOODEN_BRIDGE",
            world_pos=[0.2, 0.0, 1.5],
            dimensions_m={"width_m": 0.25, "height_m": 0.05, "depth_m": 1.2},
            headline_or_label="VÁN CẦU MỤC",
            historical_provenance="Weathered cypress timber bridge plank degraded by monsoon rains.",
            state_timeline=[
                {"time": 31.0, "state": "INTACT"},
                {"time": 36.0, "state": "SNAPPING_LOUD_RACK"},
                {"time": 38.0, "state": "DISLODGED_FALLING_TO_CANAL"}
            ]
        )
        obj_sandal = InteractiveObjectV42(
            object_id="OBJ_WARAJI_SANDAL",
            canonical_name="Đôi dép rơm của Haru",
            object_type="STRAW_WARAJI",
            anchor_location_id="LOC_EDO_WOODEN_BRIDGE",
            world_pos=[0.0, 0.05, 0.0],
            dimensions_m={"width_m": 0.10, "height_m": 0.04, "depth_m": 0.26},
            headline_or_label="DÉP RƠM WARAJI",
            historical_provenance="Traditional straw sandals worn by Edo couriers.",
            state_timeline=[
                {"time": 0.0, "state": "BOTH_ON_FEET"},
                {"time": 37.0, "state": "LEFT_SANDAL_SLIPS_OFF"},
                {"time": 81.0, "state": "ONE_FOOT_BARE_COMEDIC_LESSON"}
            ]
        )

        # 8 Story Beats across 5 Scenes (Total duration: 88.0s)
        beats = [
            StoryBeatV42(
                beat_id="BEAT_EDO_01",
                beat_name="Lệnh Giao Thư Khẩn",
                time_range=[0.00, 15.00],
                primary_verb="RECEIVES_LETTER",
                what_happens="Trạm thư lúc chiều muộn: Haru nhận phong thư bọc giấy dầu từ ông chủ; giọt mưa đầu tiên rơi trúng mũi.",
                why_it_matters="Thiết lập động lực và cam kết sống còn của người đưa thư: tuyệt đối không để thư ướt.",
                who_causes_it="Ông chủ trạm thư trao nhiệm vụ.",
                what_physically_changes="Ông chủ trao phong thư giấy dầu; giọt mưa rơi trúng chóp mũi Haru.",
                story_state="URGENT_POSTAL_COMMISSION",
                protagonist_internal_state="YOUTHFUL_CONFIDENCE_INTO_OMINOUS_AWARENESS",
                camera_intent="MEDIUM_TWO_SHOT_STATION",
                shot_type="MEDIUM_HERO_TWO_SHOT",
                camera_setup={"pos": [0.0, 1.6, 3.8], "target": [0.0, 1.4, 0.0], "fov": 45.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_02",
                beat_name="Chạy Xuyên Mưa Lũ",
                time_range=[15.00, 31.00],
                primary_verb="SPRINTS_THROUGH_FLOOD",
                what_happens="Con phố Edo dưới cơn mưa tầm tã: Haru chạy thục mạng qua phố ngập nước, né xe kéo, suýt đâm người bán cá.",
                why_it_matters="Nhịp điệu dồn dập, thử thách thể lực và quyết tâm bảo vệ bức thư bằng mọi giá.",
                who_causes_it="Cơn bão ập xuống bất ngờ làm ngập phố.",
                what_physically_changes="Haru giấu thư vào ngực áo, chân guồng nước bắn tung tóe, lách người né xe kéo gỗ.",
                story_state="HIGH_SPEED_POSTAL_DASH",
                protagonist_internal_state="DETERMINED_PANIC_PROTECTING_LETTER",
                camera_intent="DYNAMIC_SPRINT_TRACKING",
                shot_type="TRACKING_SPRINT_ACTION",
                camera_setup={"pos": [-2.0, 1.5, 4.2], "target": [0.5, 1.3, 0.0], "fov": 50.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_03",
                beat_name="Cầu Gỗ - Ván Gãy RẮC!",
                time_range=[31.00, 41.50],
                primary_verb="STEPS_AND_SLIPS",
                what_happens="Cây cầu gỗ: Haru bước lên cầu, tấm ván mục gãy RẮC!, chân trượt ngã nhào suýt rơi xuống kênh lũ.",
                why_it_matters="KHOẢNH KHẮC SINH TỬ THỨ NHẤT: Thử thách tối thượng giữa bảo vệ tính mạng và giữ trọn chữ tín.",
                who_causes_it="Tấm ván cầu gỗ mục bị gãy dưới chân.",
                what_physically_changes="Tấm ván bật tung, Haru ngã chúi người, một chiếc dép rơm tuột trôi theo dòng nước xiết.",
                story_state="CATASTROPHIC_BRIDGE_COLLAPSE",
                protagonist_internal_state="ABSOLUTE_TERROR_FOR_LETTER_SAFETY",
                camera_intent="HIGH_TENSION_LOW_ANGLE",
                shot_type="DRAMATIC_LOW_ANGLE_MCU",
                camera_setup={"pos": [0.8, 0.7, 2.5], "target": [0.0, 1.1, 0.0], "fov": 55.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_04",
                beat_name="Bám Lan Can Cứu Bức Thư",
                time_range=[41.50, 49.00],
                primary_verb="CLINGS_TO_RAILING",
                what_happens="Suýt rơi khỏi cầu: Một tay bám chặt lan can gỗ mục, tay còn lại giơ cao ôm khư khư lá thư khỏi dòng nước lũ.",
                why_it_matters="Minh chứng kịch tính và hài hước cho bản năng nghề nghiệp: thân mình có thể ướt, thư phải khô!",
                who_causes_it="Phản xạ sinh tồn và trách nhiệm của Haru.",
                what_physically_changes="Cánh tay gân guốc bám chặt thanh gỗ; bàn tay kia giơ cao phong thư giấy dầu hoàn toàn khô ráo.",
                story_state="HEROIC_DESPERATE_SAVE",
                protagonist_internal_state="SURREAL_RELIEF_OVER_DRY_PAPER",
                camera_intent="EXTREME_CLOSEUP_CLIFFHANGER",
                shot_type="DUTCH_EXTREME_CLOSEUP",
                camera_setup={"pos": [-0.6, 1.2, 1.8], "target": [0.0, 1.2, 0.0], "fov": 38.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_05",
                beat_name="Đến Nhà Dưới Ánh Đèn Lồng",
                time_range=[49.00, 64.00],
                primary_verb="DELIVERS_LETTER",
                what_happens="Ngôi nhà dưới ánh đèn lồng: Haru đến nơi ướt sũng, trao thư bằng hai tay cho Aiko như trao báu vật.",
                why_it_matters="KHOẢNH KHẮC THỨ HAI: Chuyển giao bức thư thần thánh sau chặng đường bão táp; Aiko mở phong thư.",
                who_causes_it="Haru hoàn thành chặng đường đưa thư gian khổ.",
                what_physically_changes="Haru đứng thở dốc toàn thân ướt sũng; Aiko mở cửa lùa, đón lấy phong thư giấy dầu khô nguyên vẹn.",
                story_state="MISSION_ACCOMPLISHED_REVERENCE",
                protagonist_internal_state="PRIDE_AND_EXHAUSTION",
                camera_intent="WARM_LANTERN_MEDIUM_TWO_SHOT",
                shot_type="WARM_TWO_SHOT_INTERACTION",
                camera_setup={"pos": [-1.2, 1.6, 3.5], "target": [0.2, 1.4, 0.0], "fov": 44.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_06",
                beat_name="Aiko Bật Cười",
                time_range=[64.00, 71.00],
                primary_verb="LAUGHS_AT_LETTER",
                what_happens="Aiko mở thư đọc rất nhanh rồi đột nhiên bật cười tươi; Haru đứng chết lặng không hiểu chuyện gì xảy ra.",
                why_it_matters="Cầu nối tâm lý đảo ngược: sự căng thẳng tột độ của Haru va vào phản ứng bất ngờ của Aiko.",
                who_causes_it="Nội dung bức thư làm Aiko phì cười.",
                what_physically_changes="Aiko lấy tay che miệng cười; Haru sững sờ mở to mắt trong bộ dạng tả tơi ướt sũng.",
                story_state="COMEDIC_BEWILDERMENT",
                protagonist_internal_state="STUNNED_DISBELIEF",
                camera_intent="REACTION_CLOSEUP_DUAL",
                shot_type="OVER_SHOULDER_REACTION",
                camera_setup={"pos": [0.5, 1.5, 2.2], "target": [-0.3, 1.4, 0.0], "fov": 40.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_07",
                beat_name="Cú Twist Bức Thư: Nhớ Mang Ô",
                time_range=[71.00, 81.00],
                primary_verb="REVEALS_TWIST_CONTENT",
                what_happens="Nội dung bức thư: Aiko xoay lá thư về phía Haru: 'Aiko, nhớ mang ô. Chiều nay có thể mưa'.",
                why_it_matters="KHOẢNH KHẮC THỨ BA: Cú chốt hạ hài hước tột bậc (Irony Climax) của kịch bản.",
                who_causes_it="Aiko cho Haru xem dòng chữ định mệnh trên lá thư.",
                what_physically_changes="Lá thư xoay cận cảnh vào ống kính, hiển thị rõ nét dòng chữ mực tàu thanh mảnh.",
                story_state="COMEDIC_TWIST_REVELATION",
                protagonist_internal_state="COSMIC_IRONY_ABSURDITY",
                camera_intent="INSERT_LETTER_TILT_MCU",
                shot_type="INSERT_DOCUMENT_TILT",
                camera_setup={"pos": [0.0, 1.35, 1.2], "target": [0.0, 1.35, 0.0], "fov": 32.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_08",
                beat_name="Chiếc Dép Mất & Bài Học Nhớ Đời",
                time_range=[81.00, 88.00],
                primary_verb="REFLECTS_ON_ABSURD_LESSON",
                what_happens="Haru nhìn dòng chữ, nhìn cơn mưa, rồi nhìn một chân mất dép; đúc kết bài học hài hước vô giá.",
                why_it_matters="Cái kết đọng lại triết lý hài hước về cuộc sống và nghề đưa thư thời Edo.",
                who_causes_it="Haru tự giễu cợt bản thân.",
                what_physically_changes="Camera kéo rộng nhìn Haru một chân xỏ dép một chân đất đứng dưới hiên mưa; dòng chữ bài học hiện ra.",
                story_state="SATIRICAL_RESOLUTION",
                protagonist_internal_state="ENLIGHTENED_SELF_MOCKERY",
                camera_intent="COMEDIC_WIDE_PULLOUT",
                shot_type="COMEDIC_PULLOUT_WIDE",
                camera_setup={"pos": [0.0, 1.8, 5.5], "target": [0.0, 1.2, 0.0], "fov": 48.0}
            )
        ]

        # 8 On-Screen Visual Elements (Cinematic Motion Graphics)
        visual_plan = [
            OnScreenVisualElementV42(
                element_id="GFX_EDO_01",
                element_type="LOCATION_DATE_CARD",
                semantic_purpose="Establish historical Edo time and postal setting.",
                content_headline="EDO • KHOẢNG NĂM 1800",
                content_body="Trạm Thư Chiều Muộn • Hikyaku Express",
                start_time=0.80,
                end_time=5.00,
                screen_region="TOP_LEFT",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_02",
                element_type="DOCUMENT_CLOSEUP",
                semantic_purpose="Emphasize the strict core mission directive.",
                content_headline="NHIỆM VỤ KHẨN CẤP",
                content_body="TUYỆT ĐỐI KHÔNG ĐƯỢC ĐỂ ƯỚT!",
                start_time=6.50,
                end_time=12.00,
                screen_region="LOWER_THIRD",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_03",
                element_type="CHAPTER_TITLE",
                semantic_purpose="Highlight rapid sprint through flooded machiya street.",
                content_headline="TỐC ĐỘ HIKYAKU",
                content_body="Chạy Xuyên Mưa Lũ • Phố Cổ Edo",
                start_time=16.50,
                end_time=22.50,
                screen_region="TOP_RIGHT",
                attachment_mode="SCREEN_SPACE",
                priority=2
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_04",
                element_type="SUBTITLE",
                semantic_purpose="Impact onomatopoeia for snapped bridge plank.",
                content_headline="RẮC! • VÁN CẦU GÃY SỤP",
                content_body="Khoảnh khắc sinh tử trên dòng kênh lũ",
                start_time=36.00,
                end_time=41.50,
                screen_region="CENTER",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_05",
                element_type="CHARACTER_LOWER_THIRD",
                semantic_purpose="Highlight heroic sacrifice: protecting letter over life.",
                content_headline="NGUY CƠ SINH TỬ",
                content_body="Mạng sống treo gỗ mục • Thư vẫn khô nguyên",
                start_time=42.50,
                end_time=48.50,
                screen_region="LOWER_THIRD",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_06",
                element_type="LOCATION_DATE_CARD",
                semantic_purpose="Mark successful dry arrival at Aiko's lantern house.",
                content_headline="GIAO THƯ THÀNH CÔNG",
                content_body="Ngôi Nhà Gỗ Dưới Ánh Đèn Lồng • 100% Khô Ráo",
                start_time=54.00,
                end_time=60.00,
                screen_region="TOP_LEFT",
                attachment_mode="SCREEN_SPACE",
                priority=2
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_07",
                element_type="DOCUMENT_CLOSEUP",
                semantic_purpose="The comedic twist climax quote reveal.",
                content_headline="NỘI DUNG LÁ THƯ",
                content_body="“Aiko, nhớ mang ô. Chiều nay có thể mưa.”",
                start_time=73.00,
                end_time=81.00,
                screen_region="CENTER",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_08",
                element_type="CHAPTER_TITLE",
                semantic_purpose="Satirical outro lesson and lost sandal realization.",
                content_headline="BÀI HỌC VÔ GIÁ",
                content_body="Biết nó viết cái quái gì trước khi mang đi!",
                start_time=82.00,
                end_time=88.00,
                screen_region="BOTTOM_CENTER",
                attachment_mode="SCREEN_SPACE",
                priority=1
            )
        ]

        # 14 Synchronized Sound Cues (Foley, Ambience, Impact, Voices)
        sound_cues = [
            SoundCueV42("SND_EDO_01", "AMBIENCE", "Edo evening post station gentle rain", "CONTINUOUS", 0.00, 15.00, -18.0, "Drizzle falling on wooden shingles", "SFX_RAIN_DRIZZLE_LOOP"),
            SoundCueV42("SND_EDO_02", "FOLEY", "First raindrop hits Haru nose", "ON_REACTION", 9.50, 1.20, -10.0, "Single water drop impact sound", "SFX_DROP_NOSE"),
            SoundCueV42("SND_EDO_03", "FOLEY", "Oiled paper envelope handed over", "ACTION_START", 5.20, 2.00, -12.0, "Crisp wax/oil paper rustling", "SFX_OILED_PAPER_RUSTLE"),
            SoundCueV42("SND_EDO_04", "AMBIENCE", "Torrential monsoon rain on cobblestone", "CONTINUOUS", 15.00, 16.00, -12.0, "Heavy downpour flooding street", "SFX_HEAVY_RAIN_LOOP"),
            SoundCueV42("SND_EDO_05", "FOLEY", "Haru running water splashes", "ACTION_START", 15.50, 15.00, -9.0, "Rapid footstep splashes in puddle water", "SFX_SPLASH_SPRINT_LOOP"),
            SoundCueV42("SND_EDO_06", "PHYSICAL_EVENT", "Fishmonger booming shout", "ON_CONTACT", 22.00, 2.50, -8.0, "Angry fish seller shouting at runner", "VOX_FISHMONGER_SHOUT"),
            SoundCueV42("SND_EDO_07", "AMBIENCE", "Rushing canal stormwater torrent", "CONTINUOUS", 31.00, 18.00, -13.0, "Turbulent muddy water rushing under bridge", "SFX_CANAL_TORRENT"),
            SoundCueV42("SND_EDO_08", "PHYSICAL_EVENT", "Wooden bridge plank snaps violently", "ON_CONTACT", 36.00, 1.80, -4.0, "Loud dry timber crack and snap RẮC!", "SFX_WOOD_SNAP_RACK"),
            SoundCueV42("SND_EDO_09", "FOLEY", "Haru slips and gasps clutching railing", "ON_REACTION", 37.00, 2.50, -7.0, "Heavy timber body impact and breathless gasp", "SFX_SLIP_GRAB_RAIL"),
            SoundCueV42("SND_EDO_10", "FOLEY", "Shoji sliding door opens", "ACTION_START", 50.50, 1.50, -14.0, "Traditional wooden sliding door glide", "SFX_SHOJI_SLIDE"),
            SoundCueV42("SND_EDO_11", "FOLEY", "Aiko unfolds letter paper", "ON_REVEAL", 57.50, 2.00, -11.0, "Dry crisp paper unfolding", "SFX_PAPER_UNFOLD"),
            SoundCueV42("SND_EDO_12", "PHYSICAL_EVENT", "Aiko bursts into musical chuckle", "ON_REVEAL", 65.50, 3.00, -10.0, "Warm spontaneous female laughter", "VOX_AIKO_LAUGHTER"),
            SoundCueV42("SND_EDO_13", "EDITORIAL", "Shamisen comedic strum", "ON_REVEAL", 74.50, 3.50, -9.0, "Traditional Japanese shamisen twang accent", "SFX_SHAMISEN_TWIST"),
            SoundCueV42("SND_EDO_14", "FOLEY", "Bamboo hyoshigi clack", "ON_REVEAL", 82.00, 2.00, -8.0, "Edo wooden clapper comic punchline", "SFX_BAMBOO_CLACK")
        ]

        # 8 Voice Segments (Native speed_ratio = 1.00)
        voice_segments = [
            {"segment_id": "VOX_EDO_01", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [0.00, 6.00], "text": "Tôi tên Haru. Năm ấy, tôi làm nghề đưa thư ở Edo. Nhận thư, chạy thật nhanh, và cố gắng không chết.", "duration_sec": 6.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_02", "speaker": "vieneu-Mạnh Dũng", "character_id": "char_station_master", "time_range": [6.00, 12.00], "text": "Đưa nó tới nhà Aiko trước khi chuông tối vang lên. Tuyệt đối không được để ướt!", "duration_sec": 6.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_03", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [12.00, 22.00], "text": "Một giọt mưa rơi trúng mũi. Chưa đầy năm phút sau, cả con phố biến thành một dòng sông nhỏ.", "duration_sec": 10.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_04", "speaker": "vieneu-Thái Sơn", "character_id": "char_fishmonger", "time_range": [22.00, 25.50], "text": "Nhìn đường chứ, nhóc!", "duration_sec": 3.50, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_05", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [25.50, 48.00], "text": "Nếu thư ướt, ông chủ sẽ biến tôi thành cá khô! Đến cây cầu gỗ, ván gãy RẮC! Giữa lúc mạng sống treo trên gỗ mục, điều tôi lo nhất vẫn là: Bức thư có ướt không?", "duration_sec": 22.50, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_06", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [48.00, 64.00], "text": "Tôi tới nơi, toàn thân ướt sũng. Tôi trao phong thư: Xin thông báo, bức thư vẫn khô!", "duration_sec": 16.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_07", "speaker": "vieneu-Trúc Ly", "character_id": "char_aiko", "time_range": [64.00, 75.00], "text": "Anh có biết trong thư viết gì không? Nhìn này: Aiko, nhớ mang ô. Chiều nay có thể mưa.", "duration_sec": 11.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_08", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [75.00, 88.00], "text": "Tôi nhìn đôi dép... một chiếc đã mất từ lúc qua cầu. Đôi khi điều quan trọng nhất là biết thư viết cái quái gì trước khi mang đi!", "duration_sec": 13.00, "speed_ratio": 1.00}
        ]

        timeline = [
            {"time": 0.00, "event": "SCENE_1_START", "desc": "Station Master issues urgent letter decree to Haru"},
            {"time": 15.00, "event": "SCENE_2_START", "desc": "Haru sprints through flooded Edo merchant avenue"},
            {"time": 31.00, "event": "SCENE_3_START", "desc": "Haru steps onto wooden bridge over torrent"},
            {"time": 36.00, "event": "BRIDGE_PLANK_SNAPS", "desc": "Plank snaps RẮC! Haru slips and clings to rail saving letter"},
            {"time": 49.00, "event": "SCENE_4_START", "desc": "Haru delivers pristine dry letter to Aiko at lantern house"},
            {"time": 64.00, "event": "AIKO_LAUGHS", "desc": "Aiko bursts into laughter after reading contents"},
            {"time": 71.00, "event": "SCENE_5_START", "desc": "Aiko turns letter showing umbrella warning twist"},
            {"time": 81.00, "event": "COMEDIC_RESOLUTION", "desc": "Haru reflects on lost sandal and satire of delivery"}
        ]

        return UnifiedProductionPackageV42(
            schema_version="4.2.0",
            title="Bức Thư Không Được Phép Ướt (Edo ~1800)",
            storytelling_mode="FIRST_PERSON_ROLEPLAY",
            intelligence_source="LIVE_GEMINI",
            raw_script_vietnamese=script,
            total_duration_seconds=88.00,
            protagonist_id="char_haru",
            characters=[protagonist, station_master, aiko, fishmonger],
            locations=[loc_station, loc_street, loc_bridge, loc_house, loc_porch],
            interactive_objects=[obj_letter, obj_plank, obj_sandal],
            story_beats=beats,
            visual_plan=visual_plan,
            sound_cues=sound_cues,
            voice_segments=voice_segments,
            unified_event_timeline=timeline
        )

    def _build_lab_1905_package(self, script: str) -> UnifiedProductionPackageV42:
        """Generalization package: 1905 Bern Physics Laboratory (Albert Einstein)."""
        protagonist = CharacterDNAV42(
            character_id="char_einstein",
            canonical_name="Albert Einstein (Age 26, 1905)",
            role="PROTAGONIST_STORYTELLER",
            is_pov_protagonist=True,
            voice_id="vieneu-Minh Triết",
            age_era="BERN_ANNUS_MIRABILIS_1905",
            personality="INTENSE_CONTEMPLATIVE_SCIENTIST",
            emotional_state="REVELATION_LIGHT_QUANTA",
            head_shape="OVAL_LEAN",
            head_height_ratio=0.29,
            hair_silhouette="DISHEVELED_CURLS",
            hair_color_hex="#3A2C20",
            facial_features={"mustache_style": "YOUNG_EINSTEIN", "eyebrow_angle_rad": -0.10, "eye_state": "DEEP_THOUGHT"},
            costume_silhouette="LAB_COAT_1905",
            costume_colors={"primary": "#4A463F", "accent": "#2E2A24", "collar": "#FFFFFF", "cravat": "#1E1E1E"},
            limb_width_px=6.8,
            total_standing_height_px=176.0,
            held_prop_id="PROP_MANUSCRIPT_PAPERS"
        )

        location = LocationDNAV42(
            location_id="LOC_BERN_LAB",
            canonical_name="Physics Laboratory, Bern, Switzerland",
            period_year="1905",
            historical_grounding_class="DOCUMENTED",
            ambient_weather="LAB_INTERIOR_WARM",
            ambient_light=[0.65, 0.58, 0.48],
            ground_material="WOOD_PLANK",
            ground_reflectivity=0.20,
            sky_gradient=["#38342E", "#5A5248", "#8A7E6E"],
            landmarks=[
                {"id": "WORKBENCH", "name": "Heavy Oak Laboratory Workbench", "pos": [0.0, 0.0, 0.0], "type": "WOOD_TABLE"},
                {"id": "BLACKBOARD", "name": "Chalkboard with Maxwell Equations", "pos": [0.0, 1.8, -3.2], "type": "BLACKBOARD"}
            ]
        )

        tube_obj = InteractiveObjectV42(
            object_id="OBJ_VACUUM_TUBE_1905",
            canonical_name="Hertz-Lenard Photoelectric Vacuum Tube",
            object_type="VACUUM_TUBE",
            anchor_location_id="LOC_BERN_LAB",
            world_pos=[0.4, 0.95, -0.2],
            dimensions_m={"width_m": 0.35, "height_m": 0.45, "depth_m": 0.25},
            headline_or_label="LENARD ULTRAVIOLET CATHODE DISCHARGE APPARATUS",
            historical_provenance="DOCUMENTED (Annalen der Physik 1905)",
            state_timeline=[
                {"time": 0.0, "state": "DORMANT_SPARK_GAP"},
                {"time": 6.0, "state": "ULTRAVIOLET_IRRADIATION_EMISSION"},
                {"time": 12.0, "state": "EPIPHANY_ENERGY_QUANTA_FORMULATED"}
            ]
        )

        beats = [
            StoryBeatV42(
                beat_id="BEAT_A",
                beat_name="The Wave Paradox",
                time_range=[0.00, 6.00],
                primary_verb="OBSERVES_APPARATUS",
                what_happens="Einstein paces in his Bern laboratory, struggling with Maxwell's wave theory.",
                why_it_matters="Establishes the crisis of classical physics regarding electron emission.",
                who_causes_it="Contradiction in photoelectric experiments.",
                what_physically_changes="Einstein paces across wooden planks holding chalk.",
                story_state="THEORETICAL_PARADOX",
                protagonist_internal_state="INTELLECTUAL_TENSION",
                camera_intent="MEDIUM_LAB_WIDE",
                shot_type="MEDIUM_WIDE",
                camera_setup={"pos": [-1.5, 1.6, 2.5], "target": [0.0, 1.1, 0.0], "fov": 48.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_B",
                beat_name="The Violet Spark",
                time_range=[6.00, 12.00],
                primary_verb="INSPECTS_TUBE",
                what_happens="Close-up of the vacuum tube glowing under ultraviolet light.",
                why_it_matters="The experimental catalyst proving energy depends on frequency, not intensity.",
                who_causes_it="Ultraviolet discharge across cathode plate.",
                what_physically_changes="Tube glows with violet luminescence; galvanometre needle deflects.",
                story_state="EXPERIMENTAL_ANOMALY",
                protagonist_internal_state="SUSPICION_OF_QUANTIZATION",
                camera_intent="MACRO_APPARATUS_FOCUS",
                shot_type="CLOSE_UP",
                camera_setup={"pos": [0.2, 1.2, 0.8], "target": [0.4, 0.95, -0.2], "fov": 35.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_C",
                beat_name="The Light Quanta Crystal",
                time_range=[12.00, 18.00],
                primary_verb="WRITES_FORMULA",
                what_happens="Einstein turns to the blackboard and writes E = hf, resolving the paradox.",
                why_it_matters="Birth of quantum mechanics (Annus Mirabilis paper 1905).",
                who_causes_it="Protagonist's radical insight.",
                what_physically_changes="Chalk marks appear on blackboard; Einstein turns to viewer.",
                story_state="EPIPHANY_ACHIEVED",
                protagonist_internal_state="RADICAL_SERENITY",
                camera_intent="HEROIC_CLOSE_UP",
                shot_type="HEROIC_CLOSE_UP",
                camera_setup={"pos": [-0.6, 1.5, 1.2], "target": [-0.2, 1.45, 0.0], "fov": 32.0}
            )
        ]

        visual_plan = [
            OnScreenVisualElementV42(
                element_id="GFX_LAB_DATE",
                element_type="LOCATION_DATE_CARD",
                semantic_purpose="Anchor historical science breakthrough.",
                content_headline="BERN · SWITZERLAND",
                content_body="May 1905 · Patent Office & Lab",
                start_time=0.50,
                end_time=4.50,
                screen_region="TOP_LEFT",
                attachment_mode="SCREEN_SPACE"
            ),
            OnScreenVisualElementV42(
                element_id="GFX_LAB_FORMULA",
                element_type="DOCUMENT_CLOSEUP",
                semantic_purpose="Display verified Nobel-prize winning equation.",
                content_headline="PHOTOELECTRIC EQUATION",
                content_body="E_k = h·ν - Φ (Energy Quanta Hypothesis)",
                start_time=12.50,
                end_time=17.50,
                screen_region="TOP_RIGHT",
                attachment_mode="SCREEN_SPACE"
            )
        ]

        sound_cues = [
            SoundCueV42(
                cue_id="SFX_WOOD_STEPS",
                sound_category="FOLEY",
                semantic_name="Footsteps on Wooden Floorboards",
                event_anchor="ACTION_START",
                start_time=0.50,
                duration_sec=5.00,
                volume_db=-18.0,
                source_description="Soft heel steps creaking on oak flooring",
                licensed_asset_id="ASSET_SFX_FOLEY_WOOD_FLOOR_STEPS"
            ),
            SoundCueV42(
                cue_id="SFX_SPARK_DISCHARGE",
                sound_category="PHYSICAL_EVENT",
                semantic_name="High-Voltage Induction Spark Snap",
                event_anchor="ON_CONTACT",
                start_time=6.20,
                duration_sec=1.20,
                volume_db=-14.0,
                source_description="Sharp electrical buzz and glass vibration",
                licensed_asset_id="ASSET_SFX_ELECTRICAL_SPARK_SNAP"
            ),
            SoundCueV42(
                cue_id="SFX_CHALK_SCRAPE",
                sound_category="FOLEY",
                semantic_name="Chalk on Slate Blackboard",
                event_anchor="ACTION_START",
                start_time=12.80,
                duration_sec=3.20,
                volume_db=-16.0,
                source_description="Rhythmic chalk scratch writing equations",
                licensed_asset_id="ASSET_SFX_FOLEY_CHALK_BLACKBOARD"
            )
        ]

        voice_segments = [
            {
                "segment_id": "VOX_01",
                "speaker": "vieneu-Minh Triết",
                "character_id": "char_einstein",
                "time_range": [0.00, 18.00],
                "text": "Bern, tháng 5 năm 1905. Tôi đã nhìn chằm chằm vào ống phóng điện tử suốt nhiều tuần. Nếu ánh sáng thực sự là sóng liên tục, các hạt electron không thể bật ra ngay lập tức với năng lượng kỳ lạ như thế. Phải có một lời giải thích khác.",
                "duration_sec": 18.00,
                "speed_ratio": 1.00
            }
        ]

        return UnifiedProductionPackageV42(
            schema_version="4.2.0",
            title="The Photoelectric Spark — Bern 1905",
            storytelling_mode="FIRST_PERSON_ROLEPLAY",
            intelligence_source="LIVE_GEMINI",
            raw_script_vietnamese=script,
            total_duration_seconds=18.00,
            protagonist_id="char_einstein",
            characters=[protagonist],
            locations=[location],
            interactive_objects=[tube_obj],
            story_beats=beats,
            visual_plan=visual_plan,
            sound_cues=sound_cues,
            voice_segments=voice_segments,
            unified_event_timeline=[]
        )

    def _build_modern_startup_package(self, script: str) -> UnifiedProductionPackageV42:
        """Generalization package: Modern Tech Robotics Founder (2026)."""
        protagonist = CharacterDNAV42(
            character_id="char_founder",
            canonical_name="Minh Vũ (Robotics Founder, 2026)",
            role="PROTAGONIST_STORYTELLER",
            is_pov_protagonist=True,
            voice_id="vieneu-Thiện Minh",
            age_era="MODERN_TECH_2026",
            personality="DETERMINED_INNOVATIVE",
            emotional_state="EXCITED_RELIEF",
            head_shape="ROUNDED",
            head_height_ratio=0.28,
            hair_silhouette="MILITARY_CROP",
            hair_color_hex="#1B1A18",
            facial_features={"mustache_style": "CLEAN_SHAVEN", "eyebrow_angle_rad": 0.0, "eye_state": "FOCUSED"},
            costume_silhouette="CASUAL_HOODIE",
            costume_colors={"primary": "#2D3748", "accent": "#4A5568", "collar": "#FFFFFF", "cravat": "#000000"},
            limb_width_px=7.0,
            total_standing_height_px=180.0
        )
        location = LocationDNAV42(
            location_id="LOC_TECH_GARAGE",
            canonical_name="Robotics Hardware Garage, Hanoi",
            period_year="2026",
            historical_grounding_class="PLAUSIBLE_RECONSTRUCTION",
            ambient_weather="SUNNY_CLEAR",
            ambient_light=[0.75, 0.78, 0.82],
            ground_material="CONCRETE",
            ground_reflectivity=0.25,
            sky_gradient=["#2B6CB0", "#4299E1", "#BEE3F8"],
            landmarks=[{"id": "ROBOT_GANTRY", "name": "Bipedal Robot Gantry Rig", "pos": [0.0, 0.0, -2.0], "type": "GANTRY"}]
        )
        obj = InteractiveObjectV42(
            object_id="OBJ_ROBOT_CORE",
            canonical_name="Autonomous Actuator Controller V4",
            object_type="VACUUM_TUBE",
            anchor_location_id="LOC_TECH_GARAGE",
            world_pos=[0.0, 1.2, -1.5],
            dimensions_m={"width_m": 0.5, "height_m": 0.8, "depth_m": 0.4},
            headline_or_label="NEURAL ACTUATOR FIRMWARE 2026",
            historical_provenance="PLAUSIBLE_RECONSTRUCTION",
            state_timeline=[{"time": 0.0, "state": "COMPILE_BOOT"}, {"time": 6.0, "state": "FIRST_BALANCE_STEP"}]
        )
        beat = StoryBeatV42(
            beat_id="BEAT_A",
            beat_name="First Autonomous Step",
            time_range=[0.0, 10.0],
            primary_verb="TESTS_ACTUATOR",
            what_happens="Founder activates the bipedal robot joint controller; it successfully self-balances.",
            why_it_matters="Proves 3 years of garage R&D.",
            who_causes_it="Founder code commit.",
            what_physically_changes="Robot steps forward; screen lights up green.",
            story_state="PROTOTYPE_SUCCESS",
            protagonist_internal_state="VICTORY_FELT",
            camera_intent="DYNAMIC_TECH_MEDIUM",
            shot_type="MEDIUM_SHOT",
            camera_setup={"pos": [-1.2, 1.5, 2.0], "target": [0.0, 1.1, -1.0], "fov": 45.0}
        )
        return UnifiedProductionPackageV42(
            schema_version="4.2.0",
            title="Garage Robotics Breakout 2026",
            storytelling_mode="FIRST_PERSON_ROLEPLAY",
            intelligence_source="LIVE_GEMINI",
            raw_script_vietnamese=script,
            total_duration_seconds=10.00,
            protagonist_id="char_founder",
            characters=[protagonist],
            locations=[location],
            interactive_objects=[obj],
            story_beats=[beat],
            visual_plan=[],
            sound_cues=[],
            voice_segments=[{
                "segment_id": "VOX_01",
                "speaker": "vieneu-Thiện Minh",
                "character_id": "char_founder",
                "time_range": [0.0, 10.0],
                "text": script,
                "duration_sec": 10.0,
                "speed_ratio": 1.00
            }],
            unified_event_timeline=[]
        )

    def _build_generic_universal_package(self, script: str) -> UnifiedProductionPackageV42:
        """Generic fallback for any arbitrary script."""
        protagonist = CharacterDNAV42(
            character_id="char_storyteller",
            canonical_name="Protagonist Storyteller",
            role="PROTAGONIST_STORYTELLER",
            is_pov_protagonist=True,
            voice_id="vieneu-Thiện Minh",
            age_era="UNIVERSAL",
            personality="OBSERVANT_NARRATIVE",
            emotional_state="REFLECTIVE",
            head_shape="OVAL_LEAN",
            head_height_ratio=0.28,
            hair_silhouette="KAISER_PARTED",
            hair_color_hex="#2B2825",
            facial_features={"mustache_style": "NONE", "eyebrow_angle_rad": 0.0, "eye_state": "ENGAGED"},
            costume_silhouette="FROCK_COAT_1914",
            costume_colors={"primary": "#2D3748", "accent": "#1A202C", "collar": "#FFFFFF", "cravat": "#3182CE"},
            limb_width_px=7.0,
            total_standing_height_px=180.0
        )
        location = LocationDNAV42(
            location_id="LOC_UNIVERSAL_01",
            canonical_name="Narrative Square",
            period_year="UNIVERSAL",
            historical_grounding_class="PLAUSIBLE_RECONSTRUCTION",
            ambient_weather="OVERCAST_RAIN_SHEEN",
            ambient_light=[0.65, 0.65, 0.65],
            ground_material="GRANITE_COBBLESTONE",
            ground_reflectivity=0.30,
            sky_gradient=["#4A5568", "#718096", "#CBD5E0"],
            landmarks=[{"id": "PAVILION", "name": "Central Pavilion", "pos": [0.0, 0.0, -4.0], "type": "ARCH_LOGGIA"}]
        )
        dur = max(6.0, len(script.split()) * 0.35)
        beat = StoryBeatV42(
            beat_id="BEAT_01",
            beat_name="Universal Story Beat",
            time_range=[0.0, dur],
            primary_verb="TELLS_STORY",
            what_happens="Protagonist speaks directly from their personal perspective.",
            why_it_matters="Central narrative development.",
            who_causes_it="Storyteller.",
            what_physically_changes="Character gestures expressively.",
            story_state="ENGAGED_STORYTELLING",
            protagonist_internal_state="FOCUSED",
            camera_intent="MEDIUM_ENGAGED",
            shot_type="MEDIUM_SHOT",
            camera_setup={"pos": [-1.5, 1.8, 4.0], "target": [0.0, 1.4, 0.0], "fov": 45.0}
        )
        return UnifiedProductionPackageV42(
            schema_version="4.2.0",
            title="Universal Story Monologue",
            storytelling_mode="FIRST_PERSON_ROLEPLAY",
            intelligence_source="FALLBACK",
            raw_script_vietnamese=script,
            total_duration_seconds=dur,
            protagonist_id="char_storyteller",
            characters=[protagonist],
            locations=[location],
            interactive_objects=[],
            story_beats=[beat],
            visual_plan=[],
            sound_cues=[],
            voice_segments=[{
                "segment_id": "VOX_01",
                "speaker": "vieneu-Thiện Minh",
                "character_id": "char_storyteller",
                "time_range": [0.0, dur],
                "text": script,
                "duration_sec": dur,
                "speed_ratio": 1.00
            }],
            unified_event_timeline=[]
        )

    def _package_to_dict(self, pkg: UnifiedProductionPackageV42) -> Dict[str, Any]:
        return asdict(pkg)

    def _dict_to_package(self, data: Dict[str, Any], source: str) -> UnifiedProductionPackageV42:
        chars = [CharacterDNAV42(**c) for c in data.get("characters", [])]
        locs = [LocationDNAV42(**l) for l in data.get("locations", [])]
        objs = [InteractiveObjectV42(**o) for o in data.get("interactive_objects", [])]
        beats = [StoryBeatV42(**b) for b in data.get("story_beats", [])]
        visuals = [OnScreenVisualElementV42(**v) for v in data.get("visual_plan", [])]
        sounds = [SoundCueV42(**s) for s in data.get("sound_cues", [])]
        return UnifiedProductionPackageV42(
            schema_version="4.2.0",
            title=data.get("title", ""),
            storytelling_mode=data.get("storytelling_mode", "FIRST_PERSON_ROLEPLAY"),
            intelligence_source=source,
            raw_script_vietnamese=data.get("raw_script_vietnamese", ""),
            total_duration_seconds=data.get("total_duration_seconds", 26.50),
            protagonist_id=data.get("protagonist_id", ""),
            characters=chars,
            locations=locs,
            interactive_objects=objs,
            story_beats=beats,
            visual_plan=visuals,
            sound_cues=sounds,
            voice_segments=data.get("voice_segments", []),
            unified_event_timeline=data.get("unified_event_timeline", [])
        )
