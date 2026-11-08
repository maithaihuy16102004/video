"""Scene Compositor: Blends Environment Artwork + Stickman Actor + Foreground Elements.

Enforces:
1. Spatial & Perspective Handshake: Character placed accurately along the Blueprint ground/horizon plane.
2. Lighting Handshake: Character lit consistently with the Environment key light, shadow, and color temperature.
3. Foreground Layers:
   - OTS foreground partner shoulder/head silhouette
   - POV periscope vignette
   - Heavy rustic tavern table / beer steins / sandbag parapets
4. Atmospheric Grade.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cairo

from .blueprint import SceneBlueprint
from .stickman_actor_rig import StickmanActorRig


class SceneCompositor:
    """Composites the final visual frame from Environment plate, Actor Rig, and Foreground occluders."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.s = min(width / 1920.0, height / 1080.0)
        self.actor_rig = StickmanActorRig(width=width, height=height)

    def composite_shot(
        self,
        bp: SceneBlueprint,
        plate_path: Path,
        output_path: Path,
        crop_box: list[float] | None = None,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        w, h = self.width, self.height
        s = self.s
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)

        # 1. LAYER 1: Environment Plate (with optional crop/reframe)
        if plate_path.exists():
            bg_img = cairo.ImageSurface.create_from_png(str(plate_path))
            bw, bh = bg_img.get_width(), bg_img.get_height()
            if crop_box and len(crop_box) == 4 and crop_box != [0.0, 0.0, 1.0, 1.0]:
                cx, cy, cw, ch = crop_box
                src_x = cx * bw
                src_y = cy * bh
                src_w = cw * bw
                src_h = ch * bh
                ctx.save()
                ctx.scale(w / src_w, h / src_h)
                ctx.set_source_surface(bg_img, -src_x, -src_y)
                ctx.paint()
                ctx.restore()
            else:
                ctx.save()
                ctx.scale(w / float(bw), h / float(bh))
                ctx.set_source_surface(bg_img, 0, 0)
                ctx.paint()
                ctx.restore()

        # 2. LAYER 2: Procedural Stickman Actor Rig (with matched lighting and perspective)
        self.actor_rig.render_actor(ctx, bp)

        # 3. LAYER 3: Foreground Occlusion, OTS Silhouette & POV Vignette
        shot_size = bp.camera.shot_size.upper()
        subj_x = bp.character.approximate_position[0]
        ink = (0.06, 0.08, 0.12)

        if "OTS" in shot_size:
            # Over-the-shoulder partner silhouette on opposing third
            ots_left = (subj_x > 0.50)
            edge_x = 0.0 if ots_left else float(w)
            in_dir = 1.0 if ots_left else -1.0
            ctx.save()
            # Doctor / comrade shoulder
            ctx.move_to(edge_x, h * 0.42)
            ctx.curve_to(
                edge_x + in_dir * 240 * s, h * 0.48,
                edge_x + in_dir * 380 * s, h * 0.66,
                edge_x + in_dir * 440 * s, h,
            )
            ctx.line_to(edge_x, h)
            ctx.close_path()
            ctx.set_source_rgba(0.08, 0.09, 0.12, 0.96)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(4 * s)
            ctx.stroke()
            # Head / collar silhouette
            ctx.move_to(edge_x, h * 0.20)
            ctx.curve_to(
                edge_x + in_dir * 180 * s, h * 0.22,
                edge_x + in_dir * 220 * s, h * 0.36,
                edge_x + in_dir * 150 * s, h * 0.44,
            )
            ctx.line_to(edge_x, h * 0.44)
            ctx.close_path()
            ctx.set_source_rgba(0.06, 0.07, 0.10, 0.98)
            ctx.fill()
            ctx.restore()

        elif "POV" in shot_size:
            # First-person view: periscope/binocular aperture vignette + parapet slit
            ctx.save()
            vig = cairo.RadialGradient(w * 0.5, h * 0.5, w * 0.26, w * 0.5, h * 0.5, w * 0.60)
            vig.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, 0.0)
            vig.add_color_stop_rgba(0.85, 0.02, 0.03, 0.05, 0.55)
            vig.add_color_stop_rgba(1.0, 0.01, 0.02, 0.04, 0.95)
            ctx.rectangle(0, 0, w, h)
            ctx.set_source(vig)
            ctx.fill()

            # Trench parapet timber framing lower bottom
            ctx.rectangle(0, h * 0.84, w, h * 0.16)
            ctx.set_source_rgb(0.16, 0.13, 0.10)
            ctx.fill_preserve()
            ctx.set_source_rgb(*ink)
            ctx.set_line_width(5 * s)
            ctx.stroke()
            ctx.restore()

        elif bp.composition.foreground_occlusion >= 0.15:
            # Foreground table or sandbag barricade
            ctx.save()
            fg_h = h * min(0.35, bp.composition.foreground_occlusion)
            fg_top = h - fg_h
            if "beer_hall" in bp.history.location_id:
                # Heavy oak tavern table edge
                ctx.rectangle(0, fg_top, w, fg_h)
                ctx.set_source_rgb(0.18, 0.13, 0.09)
                ctx.fill_preserve()
                ctx.set_source_rgb(*ink)
                ctx.set_line_width(4 * s)
                ctx.stroke()
                # Foreground beer steins
                ctx.rectangle(w * 0.14, fg_top - 55 * s, 65 * s, 85 * s)
                ctx.set_source_rgb(0.72, 0.68, 0.62)
                ctx.fill_preserve()
                ctx.set_source_rgb(*ink)
                ctx.stroke()
            elif "western_front" in bp.history.location_id:
                # Mud parapet and sandbags
                ctx.rectangle(0, fg_top, w, fg_h)
                ctx.set_source_rgb(0.28, 0.24, 0.20)
                ctx.fill_preserve()
                ctx.set_source_rgb(*ink)
                ctx.set_line_width(4 * s)
                ctx.stroke()
            ctx.restore()

        # 4. Atmospheric Cinematic Grade
        ctx.save()
        cin_grade = cairo.RadialGradient(w * 0.5, h * 0.5, w * 0.38, w * 0.5, h * 0.5, w * 0.75)
        cin_grade.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, 0.0)
        cin_grade.add_color_stop_rgba(1.0, 0.02, 0.04, 0.08, 0.32)
        ctx.rectangle(0, 0, w, h)
        ctx.set_source(cin_grade)
        ctx.fill()
        ctx.restore()

        surface.write_to_png(str(output_path))
        return output_path
