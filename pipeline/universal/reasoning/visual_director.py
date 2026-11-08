"""Visual Direction Provider & Gemini Visual Director.

Core Philosophy:
GEMINI SHOULD THINK.
CODE SHOULD VERIFY.
RENDERER SHOULD EXECUTE.

Responsibilities:
1. VisualDirectorContextPack: Compact, structured prompt payload.
2. VisualConcept: Creative visual ideas (viewer position concept, dominant subject,
   visual metaphor, lighting story, environmental wear) BEFORE camera derivation.
3. LocationMasterPlan: World-space layout, architecture, and "why this place looks this way".
4. ProposedCinematography: Gemini decides 1, 2, 3, 5, 8 shots based on story complexity (NO forced 6 shots).
5. Robust caching and Gemini call ledger tracking without exposing keys.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from env_secrets import get_gemini_api_key, redact  # noqa: E402
from ..schemas import LocationMasterPlan, UModel, VisualConcept


class VisualDirectorContextPack(UModel):
    """Compact context pack provided to Gemini for scene design."""
    script_segment: str
    story_summary: str = ""
    previous_story_state: dict[str, Any] = {}
    next_story_intent: str = ""
    character_bibles: dict[str, Any] = {}
    location_bible: dict[str, Any] = {}
    historical_constraints: list[str] = []
    available_assets: list[str] = []
    available_actions: list[str] = []
    previous_shots: list[dict[str, Any]] = []
    continuity_state: dict[str, Any] = {}
    target_aspect_ratio: str = "16:9"
    visual_style_bible: dict[str, Any] = {}
    retention_intent: str = "ENGAGING"
    emotional_intent: str = "CALM"
    comedy_level: float = 0.5


class GeminiCallRecord(UModel):
    timestamp: str
    stage: str
    model: str
    input_hash: str
    cache_hit: bool
    latency_sec: float
    success: bool
    error: Optional[str] = None
    fallback_used: bool
    purpose: str


class GeminiCallLedger:
    """Records all Gemini API utilization for auditability without logging secrets."""
    _records: list[GeminiCallRecord] = []

    @classmethod
    def record(
        cls,
        stage: str,
        model: str,
        input_hash: str,
        cache_hit: bool,
        latency_sec: float,
        success: bool,
        error: Optional[str] = None,
        fallback_used: bool = False,
        purpose: str = "",
    ) -> None:
        rec = GeminiCallRecord(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            stage=stage,
            model=model,
            input_hash=input_hash,
            cache_hit=cache_hit,
            latency_sec=round(latency_sec, 3),
            success=success,
            error=redact(error) if error else None,
            fallback_used=fallback_used,
            purpose=purpose,
        )
        cls._records.append(rec)

    @classmethod
    def get_records(cls) -> list[dict[str, Any]]:
        return [r.dump() for r in cls._records]

    @classmethod
    def clear(cls) -> None:
        cls._records.clear()


class VisualDirectionProvider(ABC):
    """Abstract interface for creative visual direction."""

    @abstractmethod
    def direct_scene(self, context: VisualDirectorContextPack) -> VisualConcept:
        """Derive creative visual concept for a story beat."""
        pass

    @abstractmethod
    def design_location_master(self, location_id: str, context: dict[str, Any]) -> LocationMasterPlan:
        """Design production layout and architectural master plan."""
        pass

    @abstractmethod
    def propose_cinematography(
        self,
        concept: VisualConcept,
        geography: dict[str, Any],
        context: VisualDirectorContextPack,
    ) -> list[dict[str, Any]]:
        """Propose purposeful shot sequence (Gemini decides shot count: 1 to 5+)."""
        pass


class DeterministicVisualDirectionProvider(VisualDirectionProvider):
    """High-quality deterministic fallback when Gemini is disabled or offline."""

    def direct_scene(self, context: VisualDirectorContextPack) -> VisualConcept:
        text = context.script_segment
        t_low = text.lower()
        purpose = context.retention_intent or "INFORMATION"

        # Determine visual metaphor & primary visual idea without camera-first thinking
        if any(k in t_low for k in ("wire", "cable", "snap", "break", "storm")):
            idea = "Severed tension line whips through gale winds against desolate mountain crest, isolating the human figures against the abyss."
            metaphor = "The fragile thread of human communication severed by unyielding nature."
            obj = "snapped cable"
            hidden = "Whether the signal loop can be bridged before night falls."
            reveal = "The physical fracture point high on the timber support."
        elif any(k in t_low for k in ("document", "seal", "table", "office", "official")):
            idea = "Two men separated by the immense expanse of a polished oak conference table, where a red wax seal holds the fate of nations."
            metaphor = "The weight of formal decrees dwarfing the mortal men tasked with signing them."
            obj = "sealed dispatch document"
            hidden = "The specific ministerial signature on the inner parchment."
            reveal = "The cracked wax seal and bold black ink endorsement."
        elif any(k in t_low for k in ("bakery", "oven", "switch", "timer", "bread")):
            idea = "Shadows swallow the artisan bakehouse as cold brick ovens loom; emergency glow of an electrical breaker box calls for urgent action."
            metaphor = "Human craft sustained against mechanical darkness by collective grit."
            obj = "tripped electrical switch lever"
            hidden = "Which specific fuse circuit tripped the heating banks."
            reveal = "The dual copper breaker levers thrown back into active circuit."
        else:
            idea = f"Story moment grounded in authentic physical environment: '{text[:60]}...'"
            metaphor = "Contrast between character intent and environmental resistance."
            obj = "hero narrative asset"
            hidden = "The immediate causal outcome."
            reveal = "Physical result of character intervention."

        return VisualConcept(
            story_function=purpose,
            emotional_target=context.emotional_intent or "FOCUSED",
            visual_metaphor=metaphor,
            primary_visual_idea=idea,
            viewer_position_concept="Grounded physical observer immersed within the scene space.",
            dominant_subject="primary actor",
            important_object=obj,
            hidden_information=hidden,
            reveal_information=reveal,
            environment_storytelling="Physical signs of wear, weathered tools, and natural lighting cues.",
            character_performance_intent="Controlled, purposeful body language displaying determination and tension.",
            lighting_story={"direction": "KEY_LEFT", "contrast": "HIGH", "source": "NATURAL_WINDOW"},
            depth_story={"planes": ["NEAR_FG", "FG", "MG", "BG", "FAR_BG"], "dominant_plane": "MG"},
            color_story={"palette_mood": "MUTED_AUTHENTIC", "accent": "WARM_HIGHLIGHT"},
            visual_contrast="High spatial separation between hero character and environment depth.",
            shot_sequence_strategy="Deconstruct beat into setup, physical action, and resulting consequence.",
        )

    def design_location_master(self, location_id: str, context: dict[str, Any]) -> LocationMasterPlan:
        enclosure = context.get("enclosure", "EXTERIOR")
        name = context.get("name", location_id)
        return LocationMasterPlan(
            location_id=location_id,
            name=name,
            enclosure=enclosure,
            why_this_place_looks_this_way="Built from utilitarian materials designed to endure regional climate and heavy human use.",
            architecture_style="Period functional architecture with authentic joinery and masonry.",
            materials=["WOOD", "METAL", "STONE", "GLASS"],
            spatial_layout={
                "bounds": [-10.0, -10.0, 10.0, 10.0],
                "ground_y": 0.78,
                "focal_center": [0.0, 0.0, 2.0],
            },
            interaction_surfaces=[{"name": "main_surface", "pos": [0.0, -0.4, 1.8], "type": "TABLE_OR_BENCH"}],
            walkable_zones=[[-8.0, -8.0, 8.0, 8.0]],
            occluders=[{"name": "foreground_post_or_jamb", "pos": [-2.5, 0.0, 0.5]}],
            light_sources=[{"name": "primary_daylight_or_lantern", "pos": [-4.0, 5.0, 2.0], "type": "KEY"}],
            camera_accessible_zones=["ESTABLISHING_ZONE", "TABLE_SIDE_ZONE", "OBJECT_SIDE_ZONE", "ACTOR_REAR_ZONE"],
            hero_props=["primary_hero_apparatus"],
            environmental_wear="WEATHERED_WITH_SURFACE_PATINA",
            human_traces="Worn handrails, scuffed flooring, tool rests, and organized paperwork.",
        )

    def propose_cinematography(
        self,
        concept: VisualConcept,
        geography: dict[str, Any],
        context: VisualDirectorContextPack,
    ) -> list[dict[str, Any]]:
        # Decide shot count dynamically based on beat purpose (NOT forced 6 shots!)
        purpose = concept.story_function.upper()
        if purpose in ("LOCATION", "ARRIVAL"):
            count = 1
        elif purpose in ("ACTION", "PAYOFF", "REVEAL"):
            count = 2  # Action execution + consequence
        elif purpose in ("CAUSE", "TENSION"):
            count = 2  # Disruption + actor realization
        else:
            count = 1

        shots = []
        for i in range(count):
            shot_id = f"SHOT_{i+1:02d}"
            if i == 0 and count > 1:
                cam_shot = "MEDIUM_WIDE" if "LOCATION" not in purpose else "ENVIRONMENT_ESTABLISHING"
                p_intent = "Character approaches and assesses the situation with intense focus."
                cut_mot = "ACTION_PREPARATION"
            else:
                cam_shot = "CLOSE_UP" if purpose in ("REVEAL", "EFFECT") else "MEDIUM"
                p_intent = "Character executes decisive intervention on the hero object."
                cut_mot = "NEW_INFORMATION"

            shots.append({
                "shot_id": shot_id,
                "shot": cam_shot,
                "viewer_position": "EYE",
                "camera_height": "EYE" if cam_shot != "LOW_ANGLE" else "LOW",
                "camera_distance": 1.0,
                "yaw_deg": 12.0 if i % 2 == 1 else -12.0,
                "pitch_deg": 0.0,
                "lens_intent": "NORMAL" if cam_shot == "MEDIUM" else ("WIDE_IMMERSIVE" if "WIDE" in cam_shot else "PORTRAIT"),
                "primary_focus": f"OBJECT:{concept.important_object}" if i == count - 1 else "ACTOR:lead",
                "foreground_subject": "foreground_post_or_jamb" if i == 0 else "NONE",
                "middle_subject": "actors",
                "background_subject": "architecture",
                "negative_space": "LOOK_DIRECTION",
                "cut_motivation": cut_mot,
                "performance_intent": p_intent,
                "lighting_focus": "SUBJECT_KEY",
            })
        return shots


class GeminiVisualDirectionProvider(VisualDirectionProvider):
    """Gemini-powered creative visual direction with caching and fallback."""

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        cache_dir: Optional[Path] = None,
        timeout: int = 45,
    ) -> None:
        self.model = model
        self.cache_dir = cache_dir or (_PIPELINE_DIR / "cache" / "visual_direction")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.fallback = DeterministicVisualDirectionProvider()

    def _cache_key(self, payload: dict[str, Any]) -> str:
        s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def _call_gemini_json(self, stage: str, system: str, user_prompt: str, purpose: str) -> Optional[dict[str, Any]]:
        key = get_gemini_api_key(required=False)
        if not key:
            GeminiCallLedger.record(stage, self.model, "NO_KEY", False, 0.0, False, "NO_KEY", True, purpose)
            return None

        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
        }
        in_hash = self._cache_key(payload)
        cache_file = self.cache_dir / f"{stage}_{in_hash}.json"

        # Check Cache
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                GeminiCallLedger.record(stage, self.model, in_hash, True, 0.001, True, None, False, purpose)
                return cached
            except Exception:
                pass

        # Network Call
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t0
            text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
            parsed = json.loads(text)

            # Save to Cache
            cache_file.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            GeminiCallLedger.record(stage, self.model, in_hash, False, elapsed, True, None, False, purpose)
            return parsed

        except Exception as e:
            elapsed = time.perf_counter() - t0
            GeminiCallLedger.record(stage, self.model, in_hash, False, elapsed, False, str(e), True, purpose)
            return None

    def direct_scene(self, context: VisualDirectorContextPack) -> VisualConcept:
        system = (
            "You are a master Historical Cinematic Visual Director & Production Designer. "
            "Think deeply about the narrative beat BEFORE proposing cameras or technical settings. "
            "DO NOT use camera-first thinking (e.g. 'Use a low angle' is forbidden; instead describe "
            "the visual metaphor, viewer position concept, and what the viewer must feel and discover). "
            "Respond strictly in valid JSON matching the VisualConcept schema."
        )
        prompt = (
            f"STORY BEAT:\n{context.script_segment}\n\n"
            f"STORY CONTEXT:\n{context.story_summary}\n\n"
            f"EMOTION TARGET:\n{context.emotional_intent}\n\n"
            "Return JSON with fields:\n"
            "- story_function: dramatic purpose\n"
            "- emotional_target: intended audience feeling\n"
            "- visual_metaphor: poetic / narrative visual metaphor\n"
            "- primary_visual_idea: concrete vivid visual description (NO camera enums)\n"
            "- viewer_position_concept: where the audience physically feels placed in the scene\n"
            "- dominant_subject: main character or asset\n"
            "- important_object: specific physical prop that matters\n"
            "- hidden_information: what is obscured or unresolved\n"
            "- reveal_information: what new truth is revealed\n"
            "- environment_storytelling: historical wear, traces of human presence, tools\n"
            "- character_performance_intent: specific nuanced acting intent (e.g. 'hesitates before reaching')\n"
            "- lighting_story: dict with direction, mood, and light source motivation\n"
            "- depth_story: dict with foreground, midground, background roles\n"
            "- color_story: dict with palette tone and accent\n"
            "- visual_contrast: what visual elements create tension\n"
            "- shot_sequence_strategy: how this beat should visually progress"
        )
        res = self._call_gemini_json("direct_scene", system, prompt, "Derive VisualConcept from Beat")
        if res:
            try:
                return VisualConcept(**res)
            except Exception:
                pass
        return self.fallback.direct_scene(context)

    def design_location_master(self, location_id: str, context: dict[str, Any]) -> LocationMasterPlan:
        system = (
            "You are an Architectural Production Designer. Describe a specific, historically authentic "
            "location master plan. Avoid generic rooms or generic terrain. Explain WHY this particular place "
            "looks the way it does, with environmental wear and human traces. Respond strictly in valid JSON."
        )
        prompt = (
            f"LOCATION ID: {location_id}\n"
            f"ENCLOSURE: {context.get('enclosure', 'EXTERIOR')}\n"
            f"NAME: {context.get('name', location_id)}\n\n"
            "Return JSON matching LocationMasterPlan:\n"
            "- location_id, name, enclosure\n"
            "- why_this_place_looks_this_way: specific historical/practical explanation\n"
            "- architecture_style: period construction details\n"
            "- materials: list of primary materials (WOOD, METAL, STONE, GLASS, etc.)\n"
            "- spatial_layout: world dimensions and interaction surfaces\n"
            "- interaction_surfaces: list of usable tables, workbenches, or obstacles\n"
            "- walkable_zones: 2D bounding boxes where actors can move\n"
            "- occluders: list of physical pillars, door jambs, or revetment posts that can frame the camera\n"
            "- light_sources: list of physical windows, lanterns, lamps, or atmospheric sources\n"
            "- camera_accessible_zones: valid camera zones\n"
            "- hero_props: key interactable objects\n"
            "- environmental_wear: patina, soot, rust, wood splintering, dampness\n"
            "- human_traces: signs of daily work, discarded drafts, tools, footprints"
        )
        res = self._call_gemini_json("design_location_master", system, prompt, f"Design Master Plan for {location_id}")
        if res:
            try:
                return LocationMasterPlan(**res)
            except Exception:
                pass
        return self.fallback.design_location_master(location_id, context)

    def propose_cinematography(
        self,
        concept: VisualConcept,
        geography: dict[str, Any],
        context: VisualDirectorContextPack,
    ) -> list[dict[str, Any]]:
        system = (
            "You are an Elite Director of Photography and Cinematographer. Based on the established "
            "VisualConcept and SceneGeography, propose a purposeful shot sequence. "
            "CRITICAL: Do NOT force a fixed 6-shot template. Decide how many shots are truly needed (1, 2, 3, or 5). "
            "Every shot must communicate unique information, action, or emotion; eliminate redundant coverage. "
            "Respond strictly in valid JSON array of shots."
        )
        prompt = (
            f"PRIMARY VISUAL IDEA:\n{concept.primary_visual_idea}\n\n"
            f"IMPORTANT OBJECT: {concept.important_object}\n"
            f"PERFORMANCE INTENT: {concept.character_performance_intent}\n"
            f"VIEWER POSITION CONCEPT: {concept.viewer_position_concept}\n\n"
            "Return a JSON array of shot objects with fields:\n"
            "- shot_id: string (e.g. SHOT_01, SHOT_02)\n"
            "- shot: Camera size (e.g. ENVIRONMENT_ESTABLISHING, WIDE, MEDIUM_WIDE, MEDIUM, CLOSE_UP, OBJECT_INSERT, OTS)\n"
            "- viewer_position: height and perspective intent\n"
            "- camera_height: EYE, LOW, HIGH, GROUND\n"
            "- camera_distance: float in meters (0.6 to 3.0)\n"
            "- yaw_deg, pitch_deg\n"
            "- lens_intent: WIDE_IMMERSIVE, NORMAL, PORTRAIT, MACRO\n"
            "- primary_focus: subject or object instance\n"
            "- foreground_subject: named occluder from geography or NONE\n"
            "- middle_subject, background_subject\n"
            "- negative_space: LOOK_DIRECTION or REVEAL\n"
            "- cut_motivation: narrative reason for cutting to this shot\n"
            "- performance_intent: nuanced actor beat for this specific shot\n"
            "- lighting_focus: where lighting directs attention"
        )
        res = self._call_gemini_json("propose_cinematography", system, prompt, "Propose Dynamic Cinematography")
        if isinstance(res, list) and len(res) > 0:
            return res
        elif isinstance(res, dict) and "shots" in res and isinstance(res["shots"], list):
            return res["shots"]
        return self.fallback.propose_cinematography(concept, geography, context)
