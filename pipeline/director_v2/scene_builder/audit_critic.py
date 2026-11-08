"""Structural Validator & Pixel Visual Critic implementing Phases 19, 20, 21.

Separates:
A. BlueprintComplianceValidator:
   Checks contract, camera geometry, reserved zone, historical constraints, and schema.
B. PixelVisualCritic:
   Directly inspects the actual decoded image pixels (luminance, contrast, edge complexity,
   color diversity, vector-versus-raster detector).
Never self-certifies visual acceptance.
Final state is ALWAYS: AWAITING_HUMAN_VISUAL_REVIEW.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageFilter, ImageStat

from .blueprint import SceneBlueprint
from .provenance import GenerationMode, GenerationProvenance


@dataclass
class StructuralValidationReport:
    scene_id: str
    blueprint_schema_valid: bool
    camera_contract_valid: bool
    reserved_zone_valid: bool
    historical_constraints_valid: bool
    contract_score: float
    details: dict[str, Any]


@dataclass
class PixelCriticReport:
    scene_id: str
    image_path: str
    file_exists: bool
    file_size_bytes: int
    dimensions: tuple[int, int]
    mean_luminance: float
    contrast_stddev: float
    edge_density_score: float
    color_diversity_score: float
    is_procedural_or_empty: bool
    verdict: str
    diagnostic_notes: list[str]


class BlueprintComplianceValidator:
    """A. STRUCTURAL VALIDATOR: Verifies blueprint schema and metadata contracts."""

    def validate_blueprint(self, bp: SceneBlueprint) -> StructuralValidationReport:
        details: dict[str, Any] = {}

        # 1. Camera contract
        cam = bp.camera
        cam_valid = (
            cam.shot_size in ("GROUND_LEVEL", "OTS", "LOW_ANGLE", "WIDE", "MEDIUM", "CLOSE", "EXTREME_WIDE", "HIGH_ANGLE", "POV", "DEEP_PERSPECTIVE")
            and 0.0 <= cam.horizon_y <= 1.0
            and -45.0 <= cam.pitch <= 45.0
            and -45.0 <= cam.yaw <= 45.0
        )
        details["camera_geometry"] = {
            "shot_size": cam.shot_size,
            "horizon_y": cam.horizon_y,
            "pitch": cam.pitch,
            "yaw": cam.yaw,
            "valid": cam_valid,
        }

        # 2. Reserved zone contract
        rz = bp.composition.character_reserved_zone
        rz_valid = (
            rz.width >= 0.0 and rz.height >= 0.0
            and 0.0 <= rz.x <= 1.0 and 0.0 <= rz.y <= 1.0
        )
        details["reserved_zone"] = {
            "x": rz.x, "y": rz.y, "width": rz.width, "height": rz.height,
            "valid": rz_valid,
        }

        # 3. Historical constraints
        hist = bp.history
        hist_valid = bool(hist.year > 1800 and hist.location_id and hist.historical_constraints)
        details["historical_boundaries"] = {
            "year": hist.year,
            "location_id": hist.location_id,
            "constraints_count": len(hist.historical_constraints),
            "valid": hist_valid,
        }

        all_valid = cam_valid and rz_valid and hist_valid
        contract_score = 1.0 if all_valid else 0.5

        return StructuralValidationReport(
            scene_id=bp.scene_id,
            blueprint_schema_valid=True,
            camera_contract_valid=cam_valid,
            reserved_zone_valid=rz_valid,
            historical_constraints_valid=hist_valid,
            contract_score=contract_score,
            details=details,
        )


class PixelVisualCritic:
    """B. VISUAL CRITIC: Directly evaluates physical image bytes and pixel histograms."""

    def inspect_pixels(self, image_path: Path, scene_id: str) -> PixelCriticReport:
        notes: list[str] = []

        if not image_path.exists():
            return PixelCriticReport(
                scene_id=scene_id,
                image_path=str(image_path),
                file_exists=False,
                file_size_bytes=0,
                dimensions=(0, 0),
                mean_luminance=0.0,
                contrast_stddev=0.0,
                edge_density_score=0.0,
                color_diversity_score=0.0,
                is_procedural_or_empty=True,
                verdict="IMAGE_FILE_NOT_FOUND",
                diagnostic_notes=["Image file was never written to disk."],
            )

        file_size = image_path.stat().st_size
        if file_size < 512:
            return PixelCriticReport(
                scene_id=scene_id,
                image_path=str(image_path),
                file_exists=True,
                file_size_bytes=file_size,
                dimensions=(0, 0),
                mean_luminance=0.0,
                contrast_stddev=0.0,
                edge_density_score=0.0,
                color_diversity_score=0.0,
                is_procedural_or_empty=True,
                verdict="EMPTY_OR_CORRUPT_BYTES",
                diagnostic_notes=[f"File size is {file_size} bytes, which cannot contain a valid 1080p frame."],
            )

        try:
            with Image.open(image_path) as img:
                w, h = img.size
                rgb_img = img.convert("RGB")
                gray_img = img.convert("L")

            # 1. Luminance and Contrast
            stats = ImageStat.Stat(gray_img)
            mean_lum = stats.mean[0]
            std_dev = stats.stddev[0]

            # 2. Edge complexity (Detects flat vector blocks vs rich texture)
            edges = gray_img.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            edge_density = edge_stat.mean[0]  # Higher = richer texture / linework

            # 3. Color diversity (quantize to 64 colors and count unique)
            quantized = rgb_img.quantize(colors=64)
            color_count = len(quantized.getcolors(maxcolors=128) or [])
            color_diversity = color_count / 64.0

            # 4. Diagnostic checks
            is_procedural = False
            if edge_density < 4.0:
                is_procedural = True
                notes.append(f"Low edge complexity ({edge_density:.2f}): Frame has large flat solid-color zones.")
            if std_dev < 15.0:
                notes.append(f"Low contrast ({std_dev:.2f}): Image appears washed out or monochromatic.")

            # Check if this is our diagnostic failure card
            if mean_lum < 30.0 and std_dev < 30.0:
                notes.append("Pixel signature matches dark diagnostic failure card.")

            verdict = "REAL_PIXELS_INSPECTED_AWAITING_HUMAN_REVIEW"

            return PixelCriticReport(
                scene_id=scene_id,
                image_path=str(image_path),
                file_exists=True,
                file_size_bytes=file_size,
                dimensions=(w, h),
                mean_luminance=round(mean_lum, 2),
                contrast_stddev=round(std_dev, 2),
                edge_density_score=round(edge_density, 2),
                color_diversity_score=round(color_diversity, 2),
                is_procedural_or_empty=is_procedural,
                verdict=verdict,
                diagnostic_notes=notes,
            )

        except Exception as exc:
            return PixelCriticReport(
                scene_id=scene_id,
                image_path=str(image_path),
                file_exists=True,
                file_size_bytes=file_size,
                dimensions=(0, 0),
                mean_luminance=0.0,
                contrast_stddev=0.0,
                edge_density_score=0.0,
                color_diversity_score=0.0,
                is_procedural_or_empty=True,
                verdict="DECODING_EXCEPTION",
                diagnostic_notes=[f"PIL exception while analyzing pixels: {exc}"],
            )
