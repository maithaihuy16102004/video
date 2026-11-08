"""Scene Geography V3 Engine.

Constructs, validates, and manages physical 3D world space:
- Real coordinates (meters / world units), NOT screen percentages.
- Physical boundaries, walls, ground planes, and openings.
- Persistent WorldObject topology with interaction anchors and affordances.
- Walkable vs Blocked zone collision checks.
- Camera Opportunity Zones physically grounded in the world.
- Top-down visual floorplan rendering.
"""
from __future__ import annotations

import math
from typing import Any, Optional
from PIL import Image, ImageDraw, ImageFont

from .schemas import (
    Affordance,
    CameraOpportunityZone,
    InteractionAnchor,
    SceneGeographyV3,
    WorldObject,
)


class SceneGeographyManager:
    """Manages spatial validation, collision queries, and logical map projection."""

    @staticmethod
    def is_point_in_bounds(pt: list[float], bounds: list[float]) -> bool:
        """Checks if world point [x, y, z] or [x, z] is within [min_x, min_z, max_x, max_z]."""
        x = pt[0]
        z = pt[2] if len(pt) >= 3 else pt[1]
        return bounds[0] <= x <= bounds[2] and bounds[1] <= z <= bounds[3]

    @staticmethod
    def is_walkable(pt: list[float], geo: SceneGeographyV3) -> bool:
        """Checks if a point [x, z] is inside a walkable zone and NOT inside a blocked zone."""
        x = pt[0]
        z = pt[2] if len(pt) >= 3 else pt[1]

        # 1. Must be in bounds
        if not SceneGeographyManager.is_point_in_bounds(pt, geo.bounds_world):
            return False

        # 2. Must not be inside any blocked zone
        for b in geo.blocked_zones:
            if len(b) >= 4:
                if b[0] <= x <= b[2] and b[1] <= z <= b[3]:
                    return False

        # 3. Must be inside at least one walkable zone
        if not geo.walkable_zones:
            return True
        for w in geo.walkable_zones:
            if len(w) >= 4:
                if w[0] <= x <= w[2] and w[1] <= z <= w[3]:
                    return True
        return False

    @staticmethod
    def can_traverse_path(p_start: list[float], p_end: list[float], geo: SceneGeographyV3, steps: int = 10) -> bool:
        """Checks whether a linear path between two points crosses any blocked zone."""
        for i in range(steps + 1):
            t = i / float(steps)
            x = p_start[0] + (p_end[0] - p_start[0]) * t
            z = p_start[2] + (p_end[2] - p_start[2]) * t if len(p_start) >= 3 and len(p_end) >= 3 else p_start[1] + (p_end[1] - p_start[1]) * t
            if not SceneGeographyManager.is_walkable([x, 0.0, z], geo):
                return False
        return True

    @staticmethod
    def find_nearest_interaction_anchor(
        actor_pos: list[float],
        target_obj: WorldObject,
    ) -> tuple[Optional[InteractionAnchor], list[float]]:
        """Finds closest interaction anchor on a world object to an actor."""
        if not target_obj.anchors:
            return None, target_obj.position_world

        best_anchor = None
        min_dist = float("inf")
        best_world_pos = target_obj.position_world

        for a in target_obj.anchors:
            # Anchor world position = obj pos + relative pos
            ax = target_obj.position_world[0] + a.relative_pos[0]
            ay = target_obj.position_world[1] + a.relative_pos[1]
            az = target_obj.position_world[2] + a.relative_pos[2]
            d = math.hypot(actor_pos[0] - ax, (actor_pos[2] if len(actor_pos) >= 3 else actor_pos[1]) - az)
            if d < min_dist:
                min_dist = d
                best_anchor = a
                best_world_pos = [ax, ay, az]

        return best_anchor, best_world_pos

    @staticmethod
    def project_to_screen_coordinates(
        world_pt: list[float],
        cam_zone: CameraOpportunityZone,
        screen_w: int = 1920,
        screen_h: int = 1080,
    ) -> list[float]:
        """Simple deterministic perspective projection from world coords to normalized screen coords [0..1]."""
        # Relative vector from camera
        cam_x, cam_y, cam_z = cam_zone.position_world
        dx = world_pt[0] - cam_x
        dy = (world_pt[1] if len(world_pt) >= 2 else 0.0) - cam_y
        dz = (world_pt[2] if len(world_pt) >= 3 else world_pt[1]) - cam_z

        # Avoid division by zero
        dz_clamped = max(0.4, dz)
        fov_factor = 1.2 if cam_zone.lens_intent == "WIDE_IMMERSIVE" else (2.0 if cam_zone.lens_intent == "TELE_COMPRESSION" else 1.5)

        norm_x = 0.5 + (dx / dz_clamped) * (fov_factor * 0.4)
        norm_y = 0.5 - (dy / dz_clamped) * (fov_factor * 0.4)

        return [max(0.05, min(0.95, round(norm_x, 3))), max(0.05, min(0.95, round(norm_y, 3)))]

    @staticmethod
    def render_top_down_map(
        geo: SceneGeographyV3,
        width: int = 800,
        height: int = 600,
        actors: Optional[list[Any]] = None,
        highlight_cam_zone: Optional[str] = None,
    ) -> Image.Image:
        """Renders a logical architectural schematic of the scene floorplan."""
        im = Image.new("RGB", (width, height), "#0b0d13")
        draw = ImageDraw.Draw(im)

        bounds = geo.bounds_world  # [min_x, min_z, max_x, max_z]
        bw = max(1.0, bounds[2] - bounds[0])
        bh = max(1.0, bounds[3] - bounds[1])

        margin = 40
        plot_w = width - margin * 2
        plot_h = height - margin * 2

        def w2p(x: float, z: float) -> tuple[int, int]:
            px = margin + int(((x - bounds[0]) / bw) * plot_w)
            # z goes down on screen
            pz = margin + int(((z - bounds[1]) / bh) * plot_h)
            return px, pz

        # 1. Draw boundary and grid
        x0, z0 = w2p(bounds[0], bounds[1])
        x1, z1 = w2p(bounds[2], bounds[3])
        draw.rectangle([x0, z0, x1, z1], fill="#111420", outline="#29304a", width=2)

        # Subtle grid lines
        for gx in range(int(bounds[0]), int(bounds[2]) + 1):
            px, _ = w2p(gx, 0)
            draw.line([(px, z0), (px, z1)], fill="#171b2d", width=1)
        for gz in range(int(bounds[1]), int(bounds[3]) + 1):
            _, pz = w2p(0, gz)
            draw.line([(x0, pz), (x1, pz)], fill="#171b2d", width=1)

        # 2. Draw Walkable Zones (subtle blue-gray tint)
        for wz in geo.walkable_zones:
            wx0, wz0 = w2p(wz[0], wz[1])
            wx1, wz1 = w2p(wz[2], wz[3])
            draw.rectangle([wx0, wz0, wx1, wz1], fill="#141c2c", outline="#203350", width=1)

        # 3. Draw Blocked Zones (dense dark hatch pattern/fill)
        for bz in geo.blocked_zones:
            bx0, bz0 = w2p(bz[0], bz[1])
            bx1, bz1 = w2p(bz[2], bz[3])
            draw.rectangle([bx0, bz0, bx1, bz1], fill="#221515", outline="#442222", width=1)

        # 4. Draw Walls & Openings
        for wall in geo.walls:
            pts = wall.get("coords", [])
            if len(pts) >= 4:
                px0, pz0 = w2p(pts[0], pts[1])
                px1, pz1 = w2p(pts[2], pts[3])
                draw.line([(px0, pz0), (px1, pz1)], fill="#6c7a9c", width=4)

        for op in geo.openings:
            pts = op.get("coords", [])
            if len(pts) >= 4:
                px0, pz0 = w2p(pts[0], pts[1])
                px1, pz1 = w2p(pts[2], pts[3])
                # Green dash line for door/window opening
                draw.line([(px0, pz0), (px1, pz1)], fill="#2ecc71", width=3)
                draw.text(((px0 + px1) // 2 - 15, (pz0 + pz1) // 2 - 12), op.get("name", "OPENING")[:8], fill="#2ecc71")

        # 5. Draw World Objects
        for obj in geo.world_objects:
            ox, oz = obj.position_world[0], obj.position_world[2]
            bw_o, bh_o = obj.bounds_3d[0], obj.bounds_3d[2]
            px0, pz0 = w2p(ox - bw_o * 0.5, oz - bh_o * 0.5)
            px1, pz1 = w2p(ox + bw_o * 0.5, oz + bh_o * 0.5)

            color = "#8b5a2b" if "WOOD" in obj.materials else ("#556b2f" if "STONE" in obj.materials else "#4682b4")
            draw.rectangle([px0, pz0, px1, pz1], fill=color, outline="#dcdde1", width=1)
            draw.text((px0 + 4, pz0 + 4), obj.instance_id[:12], fill="#ffffff")

            # Draw anchors
            for a in obj.anchors:
                ax, az = w2p(ox + a.relative_pos[0], oz + a.relative_pos[2])
                draw.ellipse([ax - 3, az - 3, ax + 3, az + 3], fill="#f1c40f")

        # 6. Draw Camera Zones
        for cz in geo.camera_zones:
            cx, cz_coord = cz.position_world[0], cz.position_world[2]
            px, pz = w2p(cx, cz_coord)
            is_hl = cz.zone_id == highlight_cam_zone
            cam_color = "#e74c3c" if is_hl else "#7f8c8d"
            draw.polygon([(px, pz), (px - 8, pz + 14), (px + 8, pz + 14)], fill=cam_color)
            draw.text((px - 20, pz + 16), cz.zone_id[:14], fill=cam_color)

            # View direction ray
            tx, tz = cz.view_target_world[0], cz.view_target_world[2]
            tpx, tpz = w2p(tx, tz)
            draw.line([(px, pz), (tpx, tpz)], fill=cam_color, width=1)

        # 7. Draw Actors if provided
        if actors:
            for act in actors:
                pos = getattr(act, "spawn_point_world", [0.0, 0.0, 2.0])
                apx, apz = w2p(pos[0], pos[2])
                draw.ellipse([apx - 9, apz - 9, apx + 9, apz + 9], fill="#3498db", outline="#ecf0f1", width=2)
                draw.text((apx - 18, apz - 24), getattr(act, "actor_id", "ACTOR")[:10], fill="#3498db")

                # Movement path if present
                path = getattr(act, "movement_path", [])
                if path:
                    curr_p = (apx, apz)
                    for pt in path:
                        nxt_p = w2p(pt[0], pt[2] if len(pt) >= 3 else pt[1])
                        draw.line([curr_p, nxt_p], fill="#9b59b6", width=2)
                        curr_p = nxt_p

        # Title & Legend
        draw.text((margin, 12), f"LOGICAL SCENE MAP: {geo.location_id} ({geo.enclosure})", fill="#f3d08c")
        return im
