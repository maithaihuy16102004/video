"""Gemini Visual Critic and Advisory Replan Loop.

Advisory + Replan Signal (Does NOT modify pixels directly).
Evaluates rendered drafts against VisualConcept and SceneBlueprint.
Returns structured diagnostic critique identifying WHICH layer failed:
- DIRECTOR
- BLOCKING
- CHARACTER PERFORMANCE
- WORLD
- ASSET
- LIGHTING
- COMPOSITION
"""
from __future__ import annotations

import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from PIL import Image

_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from env_secrets import get_gemini_api_key, redact  # noqa: E402
from ..reasoning.visual_director import GeminiCallLedger
from ..schemas import SceneBlueprint, UModel, VisualConcept
from ..validation.metrics import analyze_rendered_image_space


class VisualCriticReport(UModel):
    """Structured critique output (NO meaningless 8.7/10 beauty score)."""
    communication_pass: bool = True
    composition_issues: list[str] = []
    staging_issues: list[str] = []
    character_issues: list[str] = []
    environment_issues: list[str] = []
    lighting_issues: list[str] = []
    depth_issues: list[str] = []
    asset_issues: list[str] = []
    continuity_issues: list[str] = []
    recommended_replan: list[str] = []  # e.g. ["LIGHTING", "CHARACTER PERFORMANCE"]
    confidence: float = 0.90


class DeterministicVisualCritic:
    """Deterministic visual critic using image-space analysis and blueprint rules."""

    @staticmethod
    def critique(
        image_path: Path | str | Image.Image,
        bp: SceneBlueprint,
        concept: Optional[VisualConcept] = None,
    ) -> VisualCriticReport:
        analysis = analyze_rendered_image_space(image_path)
        comp_issues = []
        light_issues = []
        char_issues = []
        depth_issues = []
        replan_layers = []

        # 1. Lighting & Contrast Check
        if analysis.get("is_flat_monotone", False):
            light_issues.append("Frame contrast is too low; lacks distinct key light modeling.")
            replan_layers.append("LIGHTING")

        # 2. Focus & Quadrant Alignment
        dom_q = analysis.get("dominant_focus_quadrant", "BOTTOM_LEFT")
        if bp.primary_focus.startswith("ACTOR:") and bp.actors:
            target_side = "LEFT" if bp.actors[0].screen_x < 0.5 else "RIGHT"
            if target_side not in dom_q:
                comp_issues.append(f"Visual energy quadrant ({dom_q}) does not align with primary actor ({target_side}).")
                replan_layers.append("COMPOSITION")

        # 3. Depth & Foreground Check
        if bp.foreground_element and analysis.get("detected_foreground_occupancy", 0.0) < 0.02:
            depth_issues.append("Foreground element not clearly detected in edge luminance analysis.")
            replan_layers.append("WORLD")

        # 4. Character Action Check
        if bp.actors:
            act = bp.actors[0].action.upper()
            if act in ("STAND", "OBSERVE") and bp.shot_purpose in ("ACTION", "CONFLICT"):
                char_issues.append("Character action is static despite high-tension beat purpose.")
                replan_layers.append("CHARACTER PERFORMANCE")

        comm_pass = len(replan_layers) == 0

        return VisualCriticReport(
            communication_pass=comm_pass,
            composition_issues=comp_issues,
            staging_issues=[],
            character_issues=char_issues,
            environment_issues=[],
            lighting_issues=light_issues,
            depth_issues=depth_issues,
            asset_issues=[],
            continuity_issues=[],
            recommended_replan=list(set(replan_layers)),
            confidence=0.92,
        )


class GeminiVisualCritic:
    """Multimodal Gemini visual critique stage."""

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        timeout: int = 40,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.fallback = DeterministicVisualCritic()

    def critique(
        self,
        image_path: Path | str,
        bp: SceneBlueprint,
        concept: Optional[VisualConcept] = None,
        style_bible: Optional[dict[str, Any]] = None,
    ) -> VisualCriticReport:
        p = Path(image_path)
        if not p.exists():
            return self.fallback.critique(image_path, bp, concept)

        key = get_gemini_api_key(required=False)
        if not key:
            GeminiCallLedger.record("visual_critic", self.model, "NO_KEY", False, 0.0, False, "NO_KEY", True, "Visual Critique")
            return self.fallback.critique(image_path, bp, concept)

        # Prepare base64 thumbnail to save transport bandwidth
        try:
            im = Image.open(p).convert("RGB")
            im.thumbnail((720, 405), Image.Resampling.LANCZOS)
            import io
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
            b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception:
            return self.fallback.critique(image_path, bp, concept)

        system = (
            "You are an Elite Historical Visual Critic and Advisory Director. "
            "Examine this rendered illustration draft against the intended SceneBlueprint and VisualConcept. "
            "Provide objective, rigorous feedback on communication, composition, staging, and acting. "
            "Identify which specific layer requires replanning (DIRECTOR, BLOCKING, CHARACTER PERFORMANCE, "
            "WORLD, ASSET, LIGHTING, COMPOSITION). Do NOT assign a numerical beauty score. "
            "Respond strictly in valid JSON matching the VisualCriticReport schema."
        )

        prompt_text = (
            f"INTENDED BEAT: {bp.visual_question} -> {bp.visual_answer}\n"
            f"SHOT PURPOSE: {bp.shot_purpose} | CAMERA: {bp.camera.shot}\n"
            f"PRIMARY FOCUS: {bp.primary_focus}\n"
            f"PERFORMANCE INTENT: {bp.performance_intent}\n"
            f"PRIMARY VISUAL IDEA: {concept.primary_visual_idea if concept else 'N/A'}\n\n"
            "Return JSON matching VisualCriticReport:\n"
            "- communication_pass: bool\n"
            "- composition_issues: list[str]\n"
            "- staging_issues: list[str]\n"
            "- character_issues: list[str]\n"
            "- environment_issues: list[str]\n"
            "- lighting_issues: list[str]\n"
            "- depth_issues: list[str]\n"
            "- asset_issues: list[str]\n"
            "- continuity_issues: list[str]\n"
            "- recommended_replan: list[str] (e.g. ['LIGHTING', 'COMPOSITION'])\n"
            "- confidence: float"
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"inlineData": {"mimeType": "image/jpeg", "data": b64_img}},
                        {"text": prompt_text},
                    ],
                }
            ],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }

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
            GeminiCallLedger.record("visual_critic", self.model, "IMG_CALL", False, elapsed, True, None, False, f"Critique {bp.shot_id}")
            return VisualCriticReport(**parsed)
        except Exception as e:
            elapsed = time.perf_counter() - t0
            GeminiCallLedger.record("visual_critic", self.model, "IMG_CALL", False, elapsed, False, str(e), True, f"Critique {bp.shot_id}")
            return self.fallback.critique(image_path, bp, concept)
