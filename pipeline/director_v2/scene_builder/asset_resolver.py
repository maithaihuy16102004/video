"""Asset Reuse Resolver: Checks Location Masters, Camera Axes, and Perspective Reframe.

Enforces:
1. "DIRECTOR DESIGNS, GEMINI BUILDS, BUT DON'T CALL GEMINI BLINDLY."
2. 6-Step Reuse Cascade:
   Cache -> Location Master -> Compatible Camera Axis -> Compatible Perspective -> Reframe/Crop -> Generate.
3. Generates environment_reuse_report.json.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .blueprint import SceneBlueprint


@dataclass
class LocationMaster:
    master_id: str
    location_id: str
    name: str
    plate_path: Path
    camera_height: str
    camera_yaw: float
    camera_pitch: float
    horizon_y: float
    perspective_type: str
    materials: list[str] = field(default_factory=list)
    palette: list[str] = field(default_factory=list)
    landmarks: list[str] = field(default_factory=list)


@dataclass
class ReuseDecision:
    shot_id: str
    location_id: str
    action: str              # "GENERATE_NEW_MASTER", "GENERATE_VARIANT", "REUSE_EXACT", "REUSE_REFRAME"
    source_master_id: str | None = None
    source_plate_path: str | None = None
    crop_box: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0, 1.0])
    reason: str = ""


class AssetResolver:
    """Manages Location Masters and resolves asset reuse before calling generation APIs."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.masters: dict[str, LocationMaster] = {}
        self.decisions: list[ReuseDecision] = []

    def register_master(self, master: LocationMaster) -> None:
        self.masters[master.master_id] = master

    def resolve_blueprint(self, bp: SceneBlueprint) -> ReuseDecision:
        loc_id = bp.history.location_id
        shot_id = bp.shot_id
        shot_size = bp.camera.shot_size
        cam_height = bp.camera.height
        cam_yaw = bp.camera.yaw
        cam_pitch = bp.camera.pitch
        horizon_y = bp.camera.horizon_y
        persp_type = bp.perspective.type

        # 1. Search for existing master in this location
        matching_masters = [m for m in self.masters.values() if m.location_id == loc_id]

        if not matching_masters:
            # First time location appears -> Must generate Location Master
            master_id = f"MASTER_{loc_id.upper()}_01"
            decision = ReuseDecision(
                shot_id=shot_id,
                location_id=loc_id,
                action="GENERATE_NEW_MASTER",
                source_master_id=master_id,
                reason=f"First appearance of {loc_id}. Establishing authoritative Location Visual DNA.",
            )
            self.decisions.append(decision)
            return decision

        # 2. Check for compatible camera axis and perspective across existing masters
        for master in matching_masters:
            yaw_diff = abs(master.camera_yaw - cam_yaw)
            pitch_diff = abs(master.camera_pitch - cam_pitch)
            height_match = (master.camera_height == cam_height)
            horizon_diff = abs(master.horizon_y - horizon_y)

            # Case A: POV periscope reframe from EXTREME_WIDE battlefield master
            if "POV" in shot_size and "western_front" in loc_id:
                crop_box = [0.15, 0.15, 0.70, 0.70]
                decision = ReuseDecision(
                    shot_id=shot_id,
                    location_id=loc_id,
                    action="REUSE_REFRAME",
                    source_master_id=master.master_id,
                    source_plate_path=str(master.plate_path),
                    crop_box=crop_box,
                    reason=f"Reframing center horizon of {master.master_id} into periscope POV aperture (reusing established No Man's Land terrain).",
                )
                self.decisions.append(decision)
                return decision

            # Case B: OTS shot reframe in established interior room (Pasewalk Hospital)
            if "OTS" in shot_size and "pasewalk_hospital" in loc_id:
                crop_box = [0.0, 0.0, 1.0, 1.0]
                decision = ReuseDecision(
                    shot_id=shot_id,
                    location_id=loc_id,
                    action="REUSE_REFRAME",
                    source_master_id=master.master_id,
                    source_plate_path=str(master.plate_path),
                    crop_box=crop_box,
                    reason=f"Reusing hospital ward plate from {master.master_id} with foreground doctor OTS silhouette overlay.",
                )
                self.decisions.append(decision)
                return decision

            # Case C: Reframe deep perspective / tavern arcade from beer hall master
            if "DEEP_PERSPECTIVE" in shot_size and "beer_hall_munich" in loc_id:
                crop_box = [0.0, 0.0, 1.0, 1.0]
                decision = ReuseDecision(
                    shot_id=shot_id,
                    location_id=loc_id,
                    action="REUSE_REFRAME",
                    source_master_id=master.master_id,
                    source_plate_path=str(master.plate_path),
                    crop_box=crop_box,
                    reason=f"Reusing established tavern woodwork and arches from {master.master_id} for deep corridor staging.",
                )
                self.decisions.append(decision)
                return decision

            # Case D: Medium or Close reframe from wide master
            if height_match and yaw_diff <= 25.0 and pitch_diff <= 15.0 and horizon_diff <= 0.15:
                if shot_size in ("MEDIUM", "CLOSE"):
                    rx = max(0.0, min(0.60, bp.composition.character_reserved_zone.x - 0.20))
                    ry = max(0.0, min(0.50, horizon_y - 0.25))
                    crop_box = [round(rx, 3), round(ry, 3), 0.65, 0.65]
                    decision = ReuseDecision(
                        shot_id=shot_id,
                        location_id=loc_id,
                        action="REUSE_REFRAME",
                        source_master_id=master.master_id,
                        source_plate_path=str(master.plate_path),
                        crop_box=crop_box,
                        reason=f"Reframing {shot_size} from compatible master {master.master_id} (yaw diff {yaw_diff:.1f}°, horizon match).",
                    )
                    self.decisions.append(decision)
                    return decision

        # 3. If no compatible reframe found, generate a distinct camera variant while referencing master DNA
        variant_master_id = f"VARIANT_{loc_id.upper()}_{cam_height}_{len(matching_masters)+1:02d}"
        decision = ReuseDecision(
            shot_id=shot_id,
            location_id=loc_id,
            action="GENERATE_VARIANT",
            source_master_id=matching_masters[0].master_id,
            reason=f"Distinct camera geometry ({cam_height}, pitch {cam_pitch:+.1f}°, yaw {cam_yaw:+.1f}°). Conditioning on Location Master {matching_masters[0].master_id} for continuity.",
        )
        self.decisions.append(decision)
        return decision

    def generate_reuse_report(self, output_path: Path) -> Path:
        """Saves environment_reuse_report.json."""
        total_shots = len(self.decisions)
        new_masters = sum(1 for d in self.decisions if d.action == "GENERATE_NEW_MASTER")
        variants = sum(1 for d in self.decisions if d.action == "GENERATE_VARIANT")
        reused = sum(1 for d in self.decisions if "REUSE" in d.action)
        reuse_rate = (reused / total_shots * 100.0) if total_shots else 0.0

        report = {
            "total_shots_evaluated": total_shots,
            "unique_environment_generations": new_masters + variants,
            "new_location_masters": new_masters,
            "angle_variants_generated": variants,
            "reused_or_reframed_assets": reused,
            "asset_reuse_rate_percent": round(reuse_rate, 2),
            "average_shots_per_environment_asset": round(total_shots / max(1, new_masters + variants), 2),
            "decisions": [asdict(d) for d in self.decisions],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path
