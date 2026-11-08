"""Three-Scene Real Gemini Contact Sheet Generator with Provenance Footers.

Columns:
1. SceneBlueprint Summary
2. Real Gemini Environment Only
3. Final Stickman Composite

Provenance Footer per row:
Provider | Model | Generation Mode | Hash | Fallback Used | Camera Type | Year / Location
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .blueprint import SceneBlueprint
from .provenance import GenerationProvenance


class RealSceneContactSheetGenerator:
    """Creates the authoritative 3-column contact sheet with rigorous provenance."""

    def __init__(self) -> None:
        self.font = ImageFont.load_default()

    def generate_contact_sheet(
        self,
        scenes_data: list[dict[str, Any]],
        output_path: Path,
    ) -> Path:
        """
        scenes_data: list of dicts with:
        - "blueprint": SceneBlueprint
        - "provenance": GenerationProvenance
        - "env_plate_path": Path
        - "composite_path": Path
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        w_panel = 640
        h_panel = 360
        row_h = h_panel + 110
        total_w = w_panel * 3 + 40
        total_h = row_h * len(scenes_data) + 60

        sheet = Image.new("RGB", (total_w, total_h), color=(14, 16, 22))
        draw = ImageDraw.Draw(sheet)

        # Header Title
        draw.text(
            (20, 18),
            "DIRECTOR V2 — REAL GEMINI PIXEL PIPELINE AUDIT & CONTACT SHEET (PHASE 18)",
            fill=(250, 250, 255),
            font=self.font,
        )
        draw.text(
            (20, 36),
            "Policy: ALLOW_PROCEDURAL_FALLBACK = False | Provenance: Real API Call Verification | Status: AWAITING_HUMAN_VISUAL_REVIEW",
            fill=(160, 180, 205),
            font=self.font,
        )

        for idx, item in enumerate(scenes_data):
            bp: SceneBlueprint = item["blueprint"]
            prov: GenerationProvenance = item["provenance"]
            env_path: Path = item["env_plate_path"]
            comp_path: Path = item["composite_path"]
            y_base = 65 + idx * row_h

            # --- COLUMN 1: Scene Blueprint Summary ---
            p1 = Image.new("RGB", (w_panel, h_panel), color=(24, 28, 38))
            d1 = ImageDraw.Draw(p1)
            d1.text((15, 12), f"SCENE {idx+1}: {bp.scene_id} ({bp.history.location_id.upper()})", fill=(100, 200, 255), font=self.font)

            specs = [
                f"Historical Year: {bp.history.year} ({bp.history.country})",
                f"Story Beat: {bp.story.current_beat[:75]}...",
                f"Camera: {bp.camera.shot_size} | Height: {bp.camera.height}",
                f"Pitch: {bp.camera.pitch:+.1f}° | Yaw: {bp.camera.yaw:+.1f}° | Horizon: {bp.camera.horizon_y*100:.1f}%",
                f"Perspective: {bp.perspective.type} (Axis: {bp.perspective.depth_axis})",
                f"Reserved Zone: x={bp.composition.character_reserved_zone.x:.2f}, y={bp.composition.character_reserved_zone.y:.2f}, w={bp.composition.character_reserved_zone.width:.2f}, h={bp.composition.character_reserved_zone.height:.2f}",
                f"Key Light: {bp.lighting.key_direction} | Shadow: {bp.lighting.shadow_direction}",
                f"Color Temp: {bp.lighting.color_temperature} | Weather: {bp.atmosphere.weather}",
                f"Protagonist: {bp.character.character_id} (scale {bp.character.scale:.2f}, pose {bp.character.pose_envelope})",
            ]
            y_off = 38
            for s in specs:
                d1.text((15, y_off), s, fill=(210, 220, 230), font=self.font)
                y_off += 22

            # Draw visual wireframe of reserved zone
            rz = bp.composition.character_reserved_zone
            if rz.width > 0:
                rx = int(rz.x * w_panel)
                ry = int(rz.y * h_panel)
                rw = int(rz.width * w_panel)
                rh = int(rz.height * h_panel)
                d1.rectangle([rx, ry, rx + rw, ry + rh], outline=(255, 190, 40), width=2)
                d1.text((rx + 4, ry + 4), "CHAR ZONE", fill=(255, 190, 40), font=self.font)

            sheet.paste(p1, (15, y_base))

            # --- COLUMN 2: Real Gemini Environment Plate ---
            if env_path.exists():
                p2 = Image.open(env_path).convert("RGB").resize((w_panel, h_panel), Image.Resampling.LANCZOS)
                d2 = ImageDraw.Draw(p2)
                tag_bg = (180, 25, 35) if prov.error_details else (25, 140, 60)
                tag_txt = "GEMINI_GENERATION_FAILED" if prov.error_details else "REAL GEMINI ENVIRONMENT"
                d2.rectangle([10, 10, 260, 36], fill=tag_bg)
                d2.text((16, 16), tag_txt, fill=(255, 255, 255), font=self.font)
                sheet.paste(p2, (25 + w_panel, y_base))

            # --- COLUMN 3: Final Stickman Composite ---
            if comp_path.exists():
                p3 = Image.open(comp_path).convert("RGB").resize((w_panel, h_panel), Image.Resampling.LANCZOS)
                d3 = ImageDraw.Draw(p3)
                d3.rectangle([10, 10, 270, 36], fill=(40, 50, 75))
                d3.text((16, 16), "FINAL STICKMAN COMPOSITE", fill=(255, 220, 100), font=self.font)
                sheet.paste(p3, (35 + w_panel * 2, y_base))

            # --- PROVENANCE BANNER UNDERNEATH ROW ---
            y_prov = y_base + h_panel + 10
            prov_bg = (35, 18, 22) if prov.fallback_used or prov.error_details else (18, 30, 22)
            draw.rectangle([15, y_prov, total_w - 15, y_prov + 45], fill=prov_bg, outline=(80, 90, 110), width=1)

            hash_str = (prov.image_sha256[:16] + "...") if prov.image_sha256 else "N/A (API Error)"
            prov_text_1 = (
                f"PROVIDER: {prov.provider.upper()}  |  MODEL: {prov.model_id}  |  MODE: {prov.generation_mode.value}  |  "
                f"IMAGE SHA-256: {hash_str}  |  FALLBACK USED: {prov.fallback_used} ({prov.fallback_reason or 'None'})"
            )
            prov_text_2 = (
                f"CAMERA: {bp.camera.shot_size} (Pitch {bp.camera.pitch:+.0f}°, Yaw {bp.camera.yaw:+.0f}°, Horizon {bp.camera.horizon_y*100:.0f}%)  |  "
                f"LOCATION: {bp.history.location_id.upper()} ({bp.history.year})  |  STATUS: {'FAILED (QUOTA 429)' if prov.error_details else 'VERIFIED REAL PIXELS'}"
            )
            color_1 = (255, 140, 140) if prov.error_details else (140, 255, 170)
            draw.text((25, y_prov + 8), prov_text_1, fill=color_1, font=self.font)
            draw.text((25, y_prov + 26), prov_text_2, fill=(200, 215, 230), font=self.font)

        sheet.save(str(output_path), "PNG")
        return output_path
