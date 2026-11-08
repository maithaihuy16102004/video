"""Location Master Asset & Reuse Engine for Environment Plates.

Implements the mandatory 6-step search cascade before any Gemini image call:
1. Search Cache
2. Search Location Master
3. Check Compatible Camera Axis
4. Check Compatible Perspective
5. Check Crop/Reframe Possibility
6. Generate only if missing
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class EnvironmentMaster:
    master_id: str
    location_id: str
    era: str
    time_of_day: str
    weather: str
    camera_axis: str                 # FORWARD | REVERSE | LATERAL | DOWNWARD | UPWARD
    perspective_family: str          # ONE_POINT | TWO_POINT | WORM_EYE | HIGH_ANGLE
    asset_path: Optional[str] = None
    cache_key: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    model: str = "gemini-3.1-flash-lite-image"
    status: str = "PLANNED"          # PLANNED | GENERATED | CACHED | REUSED | FAILED


@dataclass
class ShotEnvironmentBinding:
    shot_id: str
    shot_type: str
    master_id: str
    is_master: bool
    reuse_op: str                    # DIRECT | CROP | REFRAME | PARALLAX | OCCLUDE
    crop_box: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0) # (x, y, w, h)
    effective_horizon_y: float = 0.58
    effective_camera_pitch: float = 0.0
    effective_camera_yaw: float = 0.0


@dataclass
class EnvironmentReuseLedger:
    total_shots: int = 0
    unique_environment_assets: int = 0
    reused_environment_assets: int = 0
    gemini_image_calls: int = 0
    cache_hits: int = 0
    estimated_cost: float = 0.0
    shots_per_environment_asset: float = 0.0
    masters: list[dict[str, Any]] = field(default_factory=list)
    bindings: list[dict[str, Any]] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


class EnvironmentMasterReuseResolver:
    """Resolves environment asset assignments across shots with intelligent reuse."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.masters: dict[str, EnvironmentMaster] = {}
        self.bindings: list[ShotEnvironmentBinding] = []
        self.cache_index: dict[str, Path] = {}
        self._load_cache_index()

    def _load_cache_index(self):
        for p in self.cache_dir.glob("*.png"):
            self.cache_index[p.stem] = p

    def compute_master_key(
        self,
        location_id: str,
        era: str,
        time_of_day: str,
        weather: str,
        camera_axis: str,
        perspective_family: str,
    ) -> str:
        raw = f"{location_id}:{era}:{time_of_day}:{weather}:{camera_axis}:{perspective_family}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
        return f"MASTER_{location_id}_{camera_axis}_{h}"

    def register_or_reuse_master(
        self,
        shot_id: str,
        shot_type: str,
        location_id: str,
        era: str,
        time_of_day: str,
        weather: str,
        camera_height: str,
        camera_pitch: float,
        camera_yaw: float,
        horizon_y: float,
        perspective_type: str,
        foreground_occlusion: float = 0.0,
    ) -> ShotEnvironmentBinding:
        # Determine camera axis
        c_h = camera_height.upper()
        if "LOW" in c_h or camera_pitch > 12.0:
            cam_axis = "UPWARD_WORM"
            persp_fam = "WORM_EYE"
        elif "HIGH" in c_h or camera_pitch < -15.0:
            cam_axis = "DOWNWARD_CRANE"
            persp_fam = "HIGH_ANGLE"
        elif "GROUND" in c_h:
            cam_axis = "GROUND_AXIS"
            persp_fam = "WORM_EYE"
        elif "ONE_POINT" in perspective_type.upper() or "CORRIDOR" in perspective_type.upper():
            cam_axis = "FORWARD_DEEP"
            persp_fam = "ONE_POINT_CORRIDOR"
        else:
            cam_axis = "LATERAL_TWO_POINT"
            persp_fam = "TWO_POINT"

        # Step 2: Search existing Location Masters for compatibility
        compatible_master: Optional[EnvironmentMaster] = None
        for m in self.masters.values():
            if (
                m.location_id == location_id
                and m.era == era
                and m.camera_axis == cam_axis
                and m.perspective_family == persp_fam
            ):
                compatible_master = m
                break

        if compatible_master is None:
            # Need to create a new Master
            master_id = self.compute_master_key(location_id, era, time_of_day, weather, cam_axis, persp_fam)
            cache_key = hashlib.sha256(f"{master_id}:{era}".encode()).hexdigest()[:16]

            master = EnvironmentMaster(
                master_id=master_id,
                location_id=location_id,
                era=era,
                time_of_day=time_of_day,
                weather=weather,
                camera_axis=cam_axis,
                perspective_family=persp_fam,
                cache_key=cache_key,
                status="PLANNED",
            )
            self.masters[master_id] = master
            compatible_master = master
            is_master = True
            reuse_op = "DIRECT"
            crop_box = (0.0, 0.0, 1.0, 1.0)
        else:
            # Step 5: Check crop / reframe possibility
            is_master = False
            if "CLOSE" in shot_type.upper():
                reuse_op = "CROP"
                crop_box = (0.18, 0.15, 0.64, 0.70)
            elif foreground_occlusion >= 0.25:
                reuse_op = "OCCLUDE"
                crop_box = (0.0, 0.0, 1.0, 1.0)
            elif "WIDE" in shot_type.upper():
                reuse_op = "PARALLAX"
                crop_box = (0.05, 0.05, 0.90, 0.90)
            else:
                reuse_op = "REFRAME"
                crop_box = (0.10, 0.08, 0.80, 0.84)

        binding = ShotEnvironmentBinding(
            shot_id=shot_id,
            shot_type=shot_type,
            master_id=compatible_master.master_id,
            is_master=is_master,
            reuse_op=reuse_op,
            crop_box=crop_box,
            effective_horizon_y=horizon_y,
            effective_camera_pitch=camera_pitch,
            effective_camera_yaw=camera_yaw,
        )
        self.bindings.append(binding)
        return binding

    def compile_reuse_ledger(self, gemini_calls: int = 0) -> EnvironmentReuseLedger:
        total = len(self.bindings)
        unique = len(self.masters)
        reused = total - unique
        cache_hits = sum(1 for m in self.masters.values() if m.status == "CACHED")
        cost_per_call = 0.003  # Flash-lite image pricing approx $0.003
        est_cost = gemini_calls * cost_per_call
        ratio = (total / unique) if unique > 0 else 1.0

        return EnvironmentReuseLedger(
            total_shots=total,
            unique_environment_assets=unique,
            reused_environment_assets=reused,
            gemini_image_calls=gemini_calls,
            cache_hits=cache_hits,
            estimated_cost=round(est_cost, 4),
            shots_per_environment_asset=round(ratio, 2),
            masters=[asdict(m) for m in self.masters.values()],
            bindings=[asdict(b) for b in self.bindings],
        )
