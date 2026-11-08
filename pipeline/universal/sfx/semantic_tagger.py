"""SFX Semantic Tagger and Gemini Integration.

Produces rich SFXSemanticProfile instances:
- Classification: PHYSICAL, EDITORIAL, AMBIENT, REACTION, MUSICAL, HYBRID
- Families: IMPACT, DOOR, FOOTSTEP, DRAMATIC_STING, COMEDY, SPOKEN_REACTION, etc.
- Tone Gates: comedy_level, seriousness_compatibility, historical_scene_compatibility
- Safety: meme_strength, contains_voice, contains_music
- Rules: best_use_cases, bad_use_cases, timing_anchor, mix_priority

Employs hash caching, $0.00 spend discipline, and deterministic fallback on quota/offline.
"""
from __future__ import annotations

import abc
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_ROOT_DIR = Path(__file__).resolve().parents[3]
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from pipeline.env_secrets import get_gemini_api_key, redact

from .sfx_types import (
    ApprovalState,
    AudioAnalysisProfile,
    CatalogMode,
    MixPriority,
    PrimaryFamily,
    SFXClassification,
    SFXMetadata,
    SFXSemanticProfile,
    TimingAnchor,
)


class SFXSemanticTagger(abc.ABC):
    """Abstract interface for audio semantic profiling."""

    @abc.abstractmethod
    def tag_sound(self, meta: SFXMetadata, audio: Optional[AudioAnalysisProfile] = None) -> SFXSemanticProfile:
        pass


class GeminiSFXSemanticTagger(SFXSemanticTagger):
    """Gemini-powered semantic sound tagger with hash caching and deterministic fallback."""

    DEFAULT_MODEL = "gemini-3.8-flash"
    SCHEMA_VERSION = "2026.11-SFX-V1"

    def __init__(self, ledger_path: Optional[Path] = None, timeout: int = 5):
        self.model = self.DEFAULT_MODEL
        self.ledger_path = ledger_path or Path("output/sfx_cache/gemini_sfx_call_ledger.json")
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.call_records: list[dict[str, Any]] = []
        self._consecutive_failures = 0
        self._circuit_open = False
        self._cache: dict[str, dict[str, Any]] = {}
        if self.ledger_path.is_file():
            try:
                data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
                for entry in data.get("records", []):
                    self._cache[entry["hash_key"]] = entry.get("profile", {})
                self.call_records = data.get("records", [])
            except Exception:
                self._cache = {}

    def tag_sound(self, meta: SFXMetadata, audio: Optional[AudioAnalysisProfile] = None) -> SFXSemanticProfile:
        dur = audio.duration_seconds if audio else 1.0
        hash_input = f"{self.SCHEMA_VERSION}\0{meta.source_id}\0{meta.display_name}\0{meta.source_language}\0{dur}"
        hash_key = hashlib.sha256(hash_input.encode()).hexdigest()[:24]

        # 1. Check persistent cache
        if hash_key in self._cache:
            profile_dict = self._cache[hash_key]
            return self._dict_to_profile(profile_dict)

        # 2. Try Gemini API (with circuit breaker)
        key = get_gemini_api_key(required=False)
        if key and not self._circuit_open:
            try:
                profile = self._call_gemini_api(key, meta, audio)
                self._record_call(hash_key, meta.source_id, "GEMINI_API", asdict(profile))
                self._consecutive_failures = 0
                return profile
            except Exception as e:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 2:
                    self._circuit_open = True
                safe_name = meta.display_name.encode("ascii", "replace").decode("ascii")
                try:
                    print(f"[SFXTagger] Gemini call bypassed for {safe_name}: {redact(str(e))}")
                except Exception:
                    pass

        # 3. Deterministic Knowledge Base Fallback
        profile = self._get_deterministic_profile(meta, audio)
        self._record_call(hash_key, meta.source_id, "DETERMINISTIC_GROUNDED_RULESET", asdict(profile))
        return profile

    def _call_gemini_api(self, api_key: str, meta: SFXMetadata, audio: Optional[AudioAnalysisProfile]) -> SFXSemanticProfile:
        dur_str = f"{audio.duration_seconds:.2f}s" if audio else "unknown"
        is_perc = audio.is_percussive if audio else True
        prompt = f"""You are the Master Sound Designer and Audio Semantic Analyst for a documentary animation pipeline.
Analyze this sound effect entry:
Source ID: {meta.source_id}
Display Title: {meta.display_name}
Source Category: {meta.source_category}
Language: {meta.source_language}
Duration: {dur_str}, Percussive: {is_perc}

Return a structured JSON with:
- canonical_name: normalized name
- classification: one of ["PHYSICAL", "EDITORIAL", "AMBIENT", "REACTION", "MUSICAL", "HYBRID"]
- primary_family: one of ["IMPACT", "PUNCH", "METAL_IMPACT", "DROP", "BREAK", "FOOTSTEP", "DOOR", "PAPER", "WEAPON_EVENT", "COMEDY", "SURPRISE", "DRAMATIC_STING", "UI", "MUSICAL_STING", "MEME_REACTION", "SPOKEN_REACTION"]
- secondary_families: list of strings
- physical_event: what physical real-world action this represents (if any)
- editorial_intent: editor's storytelling goal (e.g. comedic irony, tension spike, reveal)
- emotion: emotion evoked
- energy: 0.0 to 1.0
- intensity: 0.0 to 1.0
- attack_type: "sharp" or "gradual"
- duration_class: "micro", "short", "medium", or "long"
- comedy_level: 0.0 (serious) to 1.0 (pure slapstick/meme)
- seriousness_compatibility: 0.0 (forbidden in serious/tragic scenes) to 1.0 (fully safe)
- historical_scene_compatibility: 0.0 to 1.0
- spoken_content: transcribed words if spoken
- language: "vi", "en", or "none"
- contains_music: boolean
- contains_voice: boolean
- meme_strength: 0.0 to 1.0
- intrusiveness: 0.0 to 1.0
- best_use_cases: list of 2-3 bullet descriptions
- bad_use_cases: list of 2-3 forbidden scenarios
- timing_anchor: one of ["ON_CONTACT", "PRE_CONTACT", "POST_CONTACT", "ON_REVEAL", "ON_REACTION", "ON_CUT"]
- default_mix_priority: one of ["P0", "P1", "P2", "P3", "P4"]
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
        parsed = json.loads(text)
        return self._dict_to_profile(parsed, meta.source_id)

    def _get_deterministic_profile(self, meta: SFXMetadata, audio: Optional[AudioAnalysisProfile]) -> SFXSemanticProfile:
        """Deterministic semantic profiles matching human sound designer expertise."""
        name_low = meta.display_name.lower()
        sid = meta.source_id

        # 1. VINE BOOM
        if "vine boom" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Vine Boom Impact Sting",
                classification=SFXClassification.EDITORIAL,
                primary_family=PrimaryFamily.DRAMATIC_STING,
                secondary_families=["MEME_REACTION", "IMPACT"],
                physical_event="",
                editorial_intent="Ironic punctuation of dramatic realization, shock, or absurd revelation",
                emotion="shock",
                energy=0.95,
                intensity=0.90,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.85,
                seriousness_compatibility=0.0,  # STRICTLY FORBIDDEN in serious scenes
                historical_scene_compatibility=0.1,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=1.0,
                intrusiveness=0.85,
                best_use_cases=["Awkward comedic revelations", "Ego puncture moments", "Dry satire punchline"],
                bad_use_cases=["Death, injury, hospital, bombardment, mass casualties", "Serious historical exposition"],
                timing_anchor=TimingAnchor.ON_REVEAL,
                default_mix_priority=MixPriority.P3_EDITORIAL_ACCENT,
                approval_state=ApprovalState.APPROVED,
                confidence=0.98,
            )

        # 2. METAL IMPACT / PIPE
        elif "metal" in name_low or "pipe" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Metal Pipe Clang",
                classification=SFXClassification.PHYSICAL,
                primary_family=PrimaryFamily.METAL_IMPACT,
                secondary_families=["IMPACT", "DROP"],
                physical_event="Heavy hollow metal object drops and clatters on hard stone/concrete floor",
                editorial_intent="Physical equipment drop or metal impact in factory/trench",
                emotion="startle",
                energy=0.85,
                intensity=0.80,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.10,
                seriousness_compatibility=0.90,
                historical_scene_compatibility=0.95,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.10,
                intrusiveness=0.70,
                best_use_cases=["Heavy steel helmet or canteen dropped on floor", "Industrial/trench equipment clatter"],
                bad_use_cases=["Quiet hospital rooms", "Solemn character reflection"],
                timing_anchor=TimingAnchor.ON_CONTACT,
                default_mix_priority=MixPriority.P1_IMPORTANT_ACTION,
                approval_state=ApprovalState.APPROVED,
                confidence=0.97,
            )

        # 3. PUNCH / PHYSICAL HIT
        elif "punch" in name_low or "hit" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Heavy Punch Impact",
                classification=SFXClassification.PHYSICAL,
                primary_family=PrimaryFamily.PUNCH,
                secondary_families=["IMPACT", "HIT"],
                physical_event="Fist strikes body flesh or solid surface",
                editorial_intent="Visceral physical impact of physical combat or slapstick brawl",
                emotion="aggression",
                energy=0.80,
                intensity=0.75,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.30,
                seriousness_compatibility=0.85,
                historical_scene_compatibility=0.95,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.10,
                intrusiveness=0.60,
                best_use_cases=["Tavern brawl", "Physical struggle", "Bavarian beer hall scuffle"],
                bad_use_cases=["Verbal debate", "Intimate emotional dialog"],
                timing_anchor=TimingAnchor.ON_CONTACT,
                default_mix_priority=MixPriority.P0_CRITICAL_PHYSICAL,
                approval_state=ApprovalState.APPROVED,
                confidence=0.96,
            )

        # 4. SPOKEN & VIRAL MEMES (Anime Wow, ối dồi ôi, trời ơi cứu tui, ghê chưa, 10 điểm, baby laughing, fart)
        elif any(k in name_low for k in ("anime wow", "wow", "baby laughing", "fart", "ối dồi ôi", "trời ơi", "ghê chưa", "10 điểm", "mệt mỏi")):
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name=meta.display_name,
                classification=SFXClassification.REACTION,
                primary_family=PrimaryFamily.SPOKEN_REACTION,
                secondary_families=["MEME_REACTION", "COMEDY"],
                physical_event="",
                editorial_intent="Spoken comedic reaction tag to highlight absurd situation",
                emotion="amused_shock",
                energy=0.85,
                intensity=0.70,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.95,
                seriousness_compatibility=0.0,  # FORBIDDEN in serious historical scenes
                historical_scene_compatibility=0.05,
                spoken_content=meta.display_name,
                language="vi",
                contains_music=False,
                contains_voice=True,           # CRITICAL: contains_voice = True!
                meme_strength=0.95,
                intrusiveness=0.90,            # High intrusiveness: DO NOT play over primary voice narration!
                best_use_cases=["Quick satirical editorial pause", "Non-historical social comedy skits"],
                bad_use_cases=["WW1 battlefield, hospital, mobilization speech", "Any moment narration is speaking"],
                timing_anchor=TimingAnchor.ON_REACTION,
                default_mix_priority=MixPriority.P4_OPTIONAL_EMBELLISHMENT,
                approval_state=ApprovalState.RESTRICTED,
                confidence=0.99,
            )

        # 5. DOOR SLAM
        elif "door" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Heavy Wooden Door Slam",
                classification=SFXClassification.PHYSICAL,
                primary_family=PrimaryFamily.DOOR,
                secondary_families=["IMPACT", "MECHANICAL"],
                physical_event="Heavy timber architectural door slams shut into frame",
                editorial_intent="Physical exit/entry boundary or abrupt narrative termination",
                emotion="finality",
                energy=0.75,
                intensity=0.70,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.20,
                seriousness_compatibility=0.95,
                historical_scene_compatibility=1.0,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.05,
                intrusiveness=0.55,
                best_use_cases=["Hospital room door closing", "Headquarters office door shut", "Leaving beer hall"],
                bad_use_cases=["Open battlefield scenes without architecture"],
                timing_anchor=TimingAnchor.ON_CONTACT,
                default_mix_priority=MixPriority.P1_IMPORTANT_ACTION,
                approval_state=ApprovalState.APPROVED,
                confidence=0.98,
            )

        # 6. SAD VIOLIN
        elif "sad violin" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Sad Violin Meme Sting",
                classification=SFXClassification.MUSICAL,
                primary_family=PrimaryFamily.MUSICAL_STING,
                secondary_families=["COMEDY", "MEME_REACTION"],
                physical_event="",
                editorial_intent="Mock sympathy / exaggerated ironic weeping",
                emotion="mock_sadness",
                energy=0.40,
                intensity=0.60,
                attack_type="gradual",
                duration_class="medium",
                comedy_level=0.90,
                seriousness_compatibility=0.0, # FORBIDDEN in genuine tragedies
                historical_scene_compatibility=0.10,
                spoken_content="",
                language="none",
                contains_music=True,
                contains_voice=False,
                meme_strength=0.95,
                intrusiveness=0.75,
                best_use_cases=["Petty personal inconvenience framed comically", "Failed minor ambition"],
                bad_use_cases=["Genuine wartime death or blinding", "National disaster"],
                timing_anchor=TimingAnchor.ON_REACTION,
                default_mix_priority=MixPriority.P3_EDITORIAL_ACCENT,
                approval_state=ApprovalState.APPROVED,
                confidence=0.98,
            )

        # 7. DUN DUN DUN (Dramatic Sting)
        elif "dun dun" in name_low or "shocked" in name_low or "among us" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Dramatic Tension Hit (Dun Dun Dun)",
                classification=SFXClassification.EDITORIAL,
                primary_family=PrimaryFamily.DRAMATIC_STING,
                secondary_families=["SURPRISE", "TENSION"],
                physical_event="",
                editorial_intent="Sudden dramatic escalation, plot twist, or foreboding warning",
                emotion="suspense",
                energy=0.85,
                intensity=0.80,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.40,
                seriousness_compatibility=0.80,
                historical_scene_compatibility=0.75,
                spoken_content="",
                language="none",
                contains_music=True,
                contains_voice=False,
                meme_strength=0.60,
                intrusiveness=0.70,
                best_use_cases=["Ominous political foreshadowing", "Unexpected historical turning point"],
                bad_use_cases=["Casual everyday dialogue", "Calm scenic exposition"],
                timing_anchor=TimingAnchor.ON_REVEAL,
                default_mix_priority=MixPriority.P3_EDITORIAL_ACCENT,
                approval_state=ApprovalState.APPROVED,
                confidence=0.96,
            )

        # 8. DING / CHIME / UI
        elif "ding" in name_low or "chime" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Clean Service Bell Ding",
                classification=SFXClassification.HYBRID,
                primary_family=PrimaryFamily.UI,
                secondary_families=["REVEAL", "COMEDY"],
                physical_event="Small brass counter bell struck with striker",
                editorial_intent="Lightbulb idea / notification ping / clean mental realization",
                emotion="clarity",
                energy=0.50,
                intensity=0.50,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.50,
                seriousness_compatibility=0.60,
                historical_scene_compatibility=0.70,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.30,
                intrusiveness=0.40,
                best_use_cases=["Idea popping into head", "Point score confirmation"],
                bad_use_cases=["Warfront bombardments"],
                timing_anchor=TimingAnchor.ON_REVEAL,
                default_mix_priority=MixPriority.P3_EDITORIAL_ACCENT,
                approval_state=ApprovalState.APPROVED,
                confidence=0.97,
            )

        # 9. PAPER RUSTLE / STAMP
        elif "paper" in name_low or "stamp" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Paper Handling and Ink Stamp",
                classification=SFXClassification.PHYSICAL,
                primary_family=PrimaryFamily.PAPER,
                secondary_families=["OBJECT_MOVE", "IMPACT"],
                physical_event="Paper document sliding across desk and ink stamp impact",
                editorial_intent="Official bureaucratic procedure, enlistment registration, or signing document",
                emotion="procedural",
                energy=0.45,
                intensity=0.50,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.10,
                seriousness_compatibility=0.95,
                historical_scene_compatibility=1.0,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.05,
                intrusiveness=0.35,
                best_use_cases=["Recruitment office", "Bavarian enlistment registration", "Signing war decrees"],
                bad_use_cases=["High explosive battlefield scenes"],
                timing_anchor=TimingAnchor.ON_CONTACT,
                default_mix_priority=MixPriority.P1_IMPORTANT_ACTION,
                approval_state=ApprovalState.APPROVED,
                confidence=0.98,
            )

        # 10. CLOTH / POCKET MOVEMENT
        elif "cloth" in name_low or "pocket" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Coat Cloth Pocket Movement",
                classification=SFXClassification.PHYSICAL,
                primary_family=PrimaryFamily.CLOTH,
                secondary_families=["OBJECT_MOVE"],
                physical_event="Turning out fabric coat pocket looking for money",
                editorial_intent="Highlight financial emptiness and personal struggle",
                emotion="dry_disappointment",
                energy=0.35,
                intensity=0.40,
                attack_type="gradual",
                duration_class="short",
                comedy_level=0.30,
                seriousness_compatibility=0.90,
                historical_scene_compatibility=1.0,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.05,
                intrusiveness=0.30,
                best_use_cases=["Empty pocket check", "Adjusting trench coat", "Quiet character action"],
                bad_use_cases=["Loud combat bursts"],
                timing_anchor=TimingAnchor.ON_CONTACT,
                default_mix_priority=MixPriority.P2_ENVIRONMENT_FOLEY,
                approval_state=ApprovalState.APPROVED,
                confidence=0.97,
            )

        # 11. CROWD CHEERING / GATHERING
        elif "crowd" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Distant Crowd Cheering",
                classification=SFXClassification.AMBIENT,
                primary_family=PrimaryFamily.CROWD,
                secondary_families=["ENVIRONMENT"],
                physical_event="Mass patriotic gathering in European city square",
                editorial_intent="Collective wartime hysteria and public mobilization atmosphere",
                emotion="triumphant_fervor",
                energy=0.70,
                intensity=0.65,
                attack_type="swelling",
                duration_class="medium",
                comedy_level=0.15,
                seriousness_compatibility=0.90,
                historical_scene_compatibility=0.95,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.05,
                intrusiveness=0.50,
                best_use_cases=["Munich Odeonsplatz August 1914", "Public mobilization speech"],
                bad_use_cases=["Intimate one-on-one whisper"],
                timing_anchor=TimingAnchor.ACTION_START,
                default_mix_priority=MixPriority.P2_ENVIRONMENT_FOLEY,
                approval_state=ApprovalState.APPROVED,
                confidence=0.98,
            )

        # 12. MARCHING BOOTS / FOOTSTEPS
        elif "march" in name_low or "boot" in name_low or "footstep" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Infantry Boots Marching",
                classification=SFXClassification.PHYSICAL,
                primary_family=PrimaryFamily.FOOTSTEP,
                secondary_families=["ENVIRONMENT"],
                physical_event="Rhythmic heavy leather soldier boots marching on cobblestone and mud",
                editorial_intent="Inexorable military mobilization toward the Western Front",
                emotion="determination",
                energy=0.65,
                intensity=0.60,
                attack_type="sharp",
                duration_class="medium",
                comedy_level=0.05,
                seriousness_compatibility=1.0,
                historical_scene_compatibility=1.0,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.0,
                intrusiveness=0.45,
                best_use_cases=["Troop movements", "Munich mobilization", "Trench approaches"],
                bad_use_cases=["Casual indoor comedy"],
                timing_anchor=TimingAnchor.ON_CONTACT,
                default_mix_priority=MixPriority.P2_ENVIRONMENT_FOLEY,
                approval_state=ApprovalState.APPROVED,
                confidence=0.99,
            )

        # 13. RECORD SCRATCH (Editorial Freeze Frame / Contrast)
        elif "record scratch" in name_low or "scratch" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Record Scratch Freeze Frame Hit",
                classification=SFXClassification.EDITORIAL,
                primary_family=PrimaryFamily.MUSICAL_STING,
                secondary_families=["COMEDY", "TRANSITION"],
                physical_event="",
                editorial_intent="Abrupt stop punctuation when expectations clash with historical reality",
                emotion="dry_irony",
                energy=0.75,
                intensity=0.70,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.70,
                seriousness_compatibility=0.20,
                historical_scene_compatibility=0.30,
                spoken_content="",
                language="none",
                contains_music=True,
                contains_voice=False,
                meme_strength=0.60,
                intrusiveness=0.65,
                best_use_cases=["Protagonist retrospective realization: 'Không hề!'", "Expectation vs reality freeze frame"],
                bad_use_cases=["Fatal poison gas attack", "Solemn hospital surrender announcement"],
                timing_anchor=TimingAnchor.ON_REVEAL,
                default_mix_priority=MixPriority.P3_EDITORIAL_ACCENT,
                approval_state=ApprovalState.APPROVED,
                confidence=0.98,
            )

        # 14. AWKWARD CRICKET SILENCE
        elif "cricket" in name_low:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name="Awkward Cricket Chirp Beat",
                classification=SFXClassification.EDITORIAL,
                primary_family=PrimaryFamily.COMEDY,
                secondary_families=["REACTION"],
                physical_event="",
                editorial_intent="Deadpan pause highlighting naive or foolish assumption",
                emotion="awkward_deadpan",
                energy=0.30,
                intensity=0.35,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.75,
                seriousness_compatibility=0.10,
                historical_scene_compatibility=0.20,
                spoken_content="",
                language="none",
                contains_music=False,
                contains_voice=False,
                meme_strength=0.50,
                intrusiveness=0.40,
                best_use_cases=["Soldier dialogue: 'Nghe nói kết thúc trước Giáng sinh?' -> Silence"],
                bad_use_cases=["Serious battle carnage"],
                timing_anchor=TimingAnchor.ON_REACTION,
                default_mix_priority=MixPriority.P3_EDITORIAL_ACCENT,
                approval_state=ApprovalState.APPROVED,
                confidence=0.97,
            )

        # 15. GENERAL FOLEY / ENVIRONMENT (DEFAULT FALLBACK)
        else:
            return SFXSemanticProfile(
                sfx_id=sid,
                canonical_name=meta.display_name,
                classification=SFXClassification.PHYSICAL,
                primary_family=PrimaryFamily.OBJECT_MOVE,
                secondary_families=["ENVIRONMENT"],
                physical_event=f"Physical interaction related to {meta.display_name}",
                editorial_intent="Acoustic environmental presence and physical tactility",
                emotion="neutral",
                energy=0.50,
                intensity=0.50,
                attack_type="sharp",
                duration_class="short",
                comedy_level=0.20,
                seriousness_compatibility=0.85,
                historical_scene_compatibility=0.85,
                spoken_content="",
                language=meta.source_language,
                contains_music=False,
                contains_voice=False,
                meme_strength=0.15,
                intrusiveness=0.45,
                best_use_cases=["General scene Foley support"],
                bad_use_cases=[],
                timing_anchor=TimingAnchor.ON_CONTACT,
                default_mix_priority=MixPriority.P2_ENVIRONMENT_FOLEY,
                approval_state=ApprovalState.APPROVED,
                confidence=0.90,
            )

    def _dict_to_profile(self, d: dict[str, Any], default_id: str = "sfx_unknown") -> SFXSemanticProfile:
        cls_val = d.get("classification", "PHYSICAL")
        fam_val = d.get("primary_family", "IMPACT")
        anchor_val = d.get("timing_anchor", "ON_CONTACT")
        prio_val = d.get("default_mix_priority", "P2")

        return SFXSemanticProfile(
            sfx_id=d.get("sfx_id", default_id),
            canonical_name=d.get("canonical_name", "Unknown Sound"),
            classification=SFXClassification(cls_val) if cls_val in SFXClassification._value2member_map_ else SFXClassification.PHYSICAL,
            primary_family=PrimaryFamily(fam_val) if fam_val in PrimaryFamily._value2member_map_ else PrimaryFamily.IMPACT,
            secondary_families=d.get("secondary_families", []),
            physical_event=d.get("physical_event", ""),
            editorial_intent=d.get("editorial_intent", ""),
            emotion=d.get("emotion", "neutral"),
            energy=float(d.get("energy", 0.5)),
            intensity=float(d.get("intensity", 0.5)),
            attack_type=d.get("attack_type", "sharp"),
            duration_class=d.get("duration_class", "short"),
            comedy_level=float(d.get("comedy_level", 0.0)),
            seriousness_compatibility=float(d.get("seriousness_compatibility", 0.5)),
            historical_scene_compatibility=float(d.get("historical_scene_compatibility", 0.5)),
            spoken_content=d.get("spoken_content", ""),
            language=d.get("language", "none"),
            contains_music=bool(d.get("contains_music", False)),
            contains_voice=bool(d.get("contains_voice", False)),
            meme_strength=float(d.get("meme_strength", 0.0)),
            intrusiveness=float(d.get("intrusiveness", 0.5)),
            best_use_cases=d.get("best_use_cases", []),
            bad_use_cases=d.get("bad_use_cases", []),
            timing_anchor=TimingAnchor(anchor_val) if anchor_val in TimingAnchor._value2member_map_ else TimingAnchor.ON_CONTACT,
            default_mix_priority=MixPriority(prio_val) if prio_val in MixPriority._value2member_map_ else MixPriority.P2_ENVIRONMENT_FOLEY,
            approval_state=ApprovalState.APPROVED,
            confidence=float(d.get("confidence", 0.95)),
        )

    def _record_call(self, hash_key: str, source_id: str, source: str, profile_dict: dict[str, Any]) -> None:
        rec = {
            "timestamp": "2026-11-08T13:40:00+07:00",
            "hash_key": hash_key,
            "source_id": source_id,
            "analysis_source": source,
            "model": self.model if source == "GEMINI_API" else "none",
            "profile": profile_dict,
        }
        self._cache[hash_key] = profile_dict
        self.call_records.append(rec)
        data = {
            "version": self.SCHEMA_VERSION,
            "total_calls": len(self.call_records),
            "gemini_api_count": sum(1 for r in self.call_records if r["analysis_source"] == "GEMINI_API"),
            "deterministic_rule_count": sum(1 for r in self.call_records if r["analysis_source"] != "GEMINI_API"),
            "records": self.call_records,
        }
        self.ledger_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
