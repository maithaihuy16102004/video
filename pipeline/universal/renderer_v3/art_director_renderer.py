"""Universal Art Director Vector & Diagnostic Sheet Renderer.

Renders high-fidelity Character Master Bibles and Location Master Bibles using:
- Pure vector geometry (Cairo / PIL) with strict aesthetic controls.
- Head silhouettes with custom jaw, chin, and cheekbone contours (NEVER a simple circle).
- Hair graphic silhouettes with authentic partings, volume masses, and sweep directions.
- Facial anchors (piercing eyes, aquiline nose, downward firm mouth, ears).
- Composable costume silhouettes (caps, helmets, bandages, greatcoats, belts, boots).
- Composable architectural primitives (walls, arches, columns, beams, roads, duckboards, trenches).
- Landmark geometry altering world perspective.
- Diagnostic modes: FULL_COLOR, GRAYSCALE, ARCHITECTURE_SILHOUETTE, TOP_DOWN_GEOGRAPHY.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter, ImageOps

from pipeline.universal.character_engine.master_bible import (
    CharacterAppearanceState,
    CharacterMasterBible,
)
from pipeline.universal.world_engine.master_bible import (
    ArchitecturalElement,
    ArchitecturalPrimitiveType,
    LocationMasterBible,
    LocationTopology,
)


def hex_to_rgba(hex_str: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)
    elif len(h) == 3:
        return (int(h[0]*2, 16), int(h[1]*2, 16), int(h[2]*2, 16), alpha)
    return (50, 50, 50, alpha)


class ArtDirectorRenderer:
    """Master renderer for character turnarounds, architectural silhouettes, and diagnostic sheets."""

    def __init__(self, width: int = 1920, height: int = 1080):
        self.width = width
        self.height = height

    # =========================================================================
    # CHARACTER RENDERING
    # =========================================================================

    def draw_character(
        self,
        d: ImageDraw.ImageDraw,
        state: CharacterAppearanceState,
        cx: float,
        ground_y: float,
        orientation: str = "THREE_QUARTER_RIGHT",
        scale: float = 1.0,
        silhouette_only: bool = False,
        grayscale: bool = False,
        action: str = "STAND",
        intensity: float = 1.0,
    ) -> dict[str, Any]:
        """Draws one character instance adhering to CharacterMasterBible DNA."""
        s = scale * (state.body.standing_height_px / 280.0)
        orient = orientation.upper()
        is_three_quarter = "THREE_QUARTER" in orient
        is_back = ("BACK" in orient) and not is_three_quarter
        is_profile = "PROFILE" in orient
        flip_x = -1.0 if "LEFT" in orient else 1.0

        # Colors
        ink = (22, 20, 24, 255)
        skin = (228, 204, 180, 255) if not silhouette_only else ink
        if grayscale and not silhouette_only:
            skin = (210, 210, 210, 255)

        # Proportions
        total_h = 280.0 * s
        head_h = total_h * state.body.head_to_body_ratio
        head_r = head_h * 0.48

        # Pose & Center of mass
        lean = 0.0
        crouch = 0.0
        if action == "RUN":
            lean = 24.0 * s * flip_x
            crouch = 25.0 * s
        elif action in ("LEAN", "REACH"):
            lean = 18.0 * s * flip_x
        elif action == "FLINCH":
            lean = -15.0 * s * flip_x
            crouch = 18.0 * s

        hip_y = ground_y - (125.0 * s - crouch)
        shoulder_y = ground_y - (245.0 * s - crouch)
        neck_y = shoulder_y - 25.0 * s
        neck_x = cx + lean * 0.8
        head_cx = neck_x + (8.0 * s * flip_x if not is_profile else 14.0 * s * flip_x)
        head_cy = neck_y - head_r * 0.95

        # 1. Contact Shadow
        d.ellipse(
            [cx - 55.0 * s, ground_y - 10.0 * s, cx + 55.0 * s, ground_y + 12.0 * s],
            fill=(18, 16, 20, 80 if not silhouette_only else 255)
        )

        # 2. Boots & Legs
        stride = 28.0 * s
        if action == "RUN":
            stride = 65.0 * s
        elif action == "WALK":
            stride = 42.0 * s

        l_foot = (cx - stride * flip_x, ground_y)
        r_foot = (cx + stride * 0.7 * flip_x, ground_y)
        trouser_color = hex_to_rgba(state.color_palette.get("secondary", "#363f4a"))
        boot_color = hex_to_rgba(state.color_palette.get("trim", "#181513"))
        if silhouette_only:
            trouser_color = boot_color = ink

        lw_leg = max(3, int(state.body.limb_thickness_px * s))
        # Left leg
        d.line([(cx - 10.0 * s * flip_x, hip_y), (l_foot[0] + 5.0 * s, ground_y - 45.0 * s), l_foot], fill=ink if silhouette_only else trouser_color, width=lw_leg)
        # Right leg
        d.line([(cx + 10.0 * s * flip_x, hip_y), (r_foot[0] - 5.0 * s, ground_y - 45.0 * s), r_foot], fill=ink if silhouette_only else trouser_color, width=lw_leg)

        # Boots (distinct block mass with heel)
        for fx, fy in (l_foot, r_foot):
            bw = 24.0 * s
            bh = 12.0 * s
            d.polygon([
                (fx - 6.0 * s * flip_x, fy - bh),
                (fx + bw * flip_x, fy - bh),
                (fx + (bw + 4.0 * s) * flip_x, fy),
                (fx - 6.0 * s * flip_x, fy)
            ], fill=ink if silhouette_only else boot_color, outline=ink)

        # 3. Torso & Costume Silhouette
        jacket_color = hex_to_rgba(state.color_palette.get("primary", "#4d5b6a"))
        if silhouette_only:
            jacket_color = ink
        sw = 42.0 * s * state.body.shoulder_width_ratio
        bw = 34.0 * s

        # Check for greatcoat / trench coat length
        has_greatcoat = any(c.component_type == "COAT" for c in state.costume_components)
        bottom_y = hip_y + (45.0 * s if has_greatcoat else 0.0)

        torso_poly = [
            (neck_x - sw * 0.5, shoulder_y),
            (neck_x + sw * 0.5, shoulder_y),
            (cx + bw * 0.5 + lean * 0.3, bottom_y),
            (cx - bw * 0.5 + lean * 0.3, bottom_y),
        ]
        d.polygon(torso_poly, fill=jacket_color, outline=ink, width=max(2, int(3.5 * s)))

        # Belt & Buckle
        if not silhouette_only and not is_back:
            belt_y = hip_y - 12.0 * s
            d.rectangle([cx - bw * 0.52 + lean * 0.3, belt_y, cx + bw * 0.52 + lean * 0.3, belt_y + 8.0 * s], fill=ink)
            d.rectangle([cx - 5.0 * s + lean * 0.3, belt_y - 1.0 * s, cx + 5.0 * s + lean * 0.3, belt_y + 9.0 * s], fill=(210, 175, 90, 255), outline=ink)

        # 4. Arms & Hands
        l_hand = (cx - 32.0 * s * flip_x + lean * 0.5, hip_y + 15.0 * s)
        r_hand = (cx + 32.0 * s * flip_x + lean * 0.5, hip_y + 15.0 * s)
        if action == "REACH":
            r_hand = (neck_x + 85.0 * s * flip_x, shoulder_y - 10.0 * s)
        elif action == "RUN":
            l_hand = (neck_x - 55.0 * s * flip_x, shoulder_y - 20.0 * s)
            r_hand = (neck_x + 50.0 * s * flip_x, hip_y + 35.0 * s)

        d.line([(neck_x - sw * 0.45, shoulder_y + 5.0 * s), (neck_x - 38.0 * s * flip_x, shoulder_y + 55.0 * s), l_hand], fill=ink if silhouette_only else jacket_color, width=lw_leg)
        d.line([(neck_x + sw * 0.45, shoulder_y + 5.0 * s), (neck_x + 38.0 * s * flip_x, shoulder_y + 55.0 * s), r_hand], fill=ink if silhouette_only else jacket_color, width=lw_leg)
        for hx, hy in (l_hand, r_hand):
            d.ellipse([hx - 7.0 * s, hy - 7.0 * s, hx + 7.0 * s, hy + 7.0 * s], fill=ink if silhouette_only else skin, outline=ink, width=2)

        # 5. Head Silhouette (Custom Jaw / Chin geometry, NOT a round circle!)
        hw = head_r * state.head.width_ratio
        hh = head_r * state.head.height_ratio
        
        # Build angular jaw polygon
        if is_profile:
            # Sharp angular profile silhouette
            chin_x = head_cx + hw * 0.85 * flip_x
            chin_y = head_cy + hh * 0.95
            jaw_x = head_cx - hw * 0.65 * flip_x
            jaw_y = head_cy + hh * 0.65
            head_poly = [
                (head_cx - hw * 0.85 * flip_x, head_cy - hh * 0.4),
                (head_cx - hw * 0.4 * flip_x, head_cy - hh * 1.05),
                (head_cx + hw * 0.4 * flip_x, head_cy - hh * 1.05),
                (head_cx + hw * 0.95 * flip_x, head_cy - hh * 0.2), # Forehead
                (head_cx + hw * 1.25 * flip_x, head_cy + hh * 0.15), # Nose tip protrusion!
                (head_cx + hw * 0.9 * flip_x, head_cy + hh * 0.45), # Upper lip
                (chin_x, chin_y), # Sharp chin
                (jaw_x, jaw_y), # Jaw angle
                (head_cx - hw * 0.85 * flip_x, head_cy + hh * 0.2)
            ]
        elif is_three_quarter:
            # 3/4 Angular jaw with cheekbone protrusion
            head_poly = [
                (head_cx - hw * 0.95, head_cy - hh * 0.4),
                (head_cx - hw * 0.5, head_cy - hh * 1.02),
                (head_cx + hw * 0.5, head_cy - hh * 1.02),
                (head_cx + hw * 1.02, head_cy - hh * 0.35),
                (head_cx + hw * 1.08 * (1.0 if flip_x > 0 else 0.85), head_cy + hh * 0.1), # Cheekbone
                (head_cx + hw * 0.35 * flip_x, head_cy + hh * 1.05), # Angular chin
                (head_cx - hw * 0.75 * flip_x, head_cy + hh * 0.75), # Jaw corner
                (head_cx - hw * 1.02, head_cy + hh * 0.1)
            ]
        else: # Front or Back
            head_poly = [
                (head_cx - hw * 0.92, head_cy - hh * 0.4),
                (head_cx - hw * 0.5, head_cy - hh * 1.02),
                (head_cx + hw * 0.5, head_cy - hh * 1.02),
                (head_cx + hw * 0.92, head_cy - hh * 0.4),
                (head_cx + hw * 0.98, head_cy + hh * 0.1), # Cheeks
                (head_cx + hw * 0.65, head_cy + hh * 0.68), # Jawline
                (head_cx, head_cy + hh * 1.05), # Chin
                (head_cx - hw * 0.65, head_cy + hh * 0.68),
                (head_cx - hw * 0.98, head_cy + hh * 0.1)
            ]

        d.polygon(head_poly, fill=skin, outline=ink, width=max(2, int(3.8 * s)))

        # 6. Ears
        if not is_back and not is_profile:
            ear_x = head_cx - hw * 0.98 if flip_x > 0 else head_cx + hw * 0.98
            d.ellipse([ear_x - 5.0 * s, head_cy - 4.0 * s, ear_x + 5.0 * s, head_cy + 14.0 * s], fill=skin, outline=ink, width=2)

        # 7. Facial Anchors (Piercing eyes, Aquiline nose, Firm mouth)
        if not is_back and not silhouette_only:
            self._draw_facial_anchors(d, state, head_cx, head_cy, hw, hh, s, flip_x, is_profile, is_three_quarter, ink)

        # 8. Graphic Hair Silhouette (Authentic sweep, deep parting, mass volume)
        hair_color = hex_to_rgba(state.hair.color_hex)
        if grayscale and not silhouette_only:
            hair_color = (35, 35, 35, 255)
        if silhouette_only:
            hair_color = ink
        self._draw_hair_silhouette(d, state, head_cx, head_cy, hw, hh, s, flip_x, is_back, is_profile, is_three_quarter, hair_color, ink)

        # 9. Costume Headwear / Bandages
        for comp in state.costume_components:
            if comp.component_type in ("HEADWEAR", "BANDAGE"):
                self._draw_headwear(d, comp, head_cx, head_cy, hw, hh, s, flip_x, is_profile, is_back, ink, silhouette_only)

        return {"head": (head_cx, head_cy), "feet": (l_foot, r_foot), "shoulder": (neck_x, shoulder_y)}

    def _draw_facial_anchors(
        self,
        d: ImageDraw.ImageDraw,
        state: CharacterAppearanceState,
        cx: float,
        cy: float,
        hw: float,
        hh: float,
        s: float,
        flip_x: float,
        is_profile: bool,
        is_three_quarter: bool,
        ink: tuple[int, int, int, int],
    ):
        face = state.face
        eye_y = cy - 2.0 * s
        shift = 10.0 * s * flip_x if is_three_quarter else 0.0

        if is_profile:
            # Single piercing slit eye
            pex = cx + hw * 0.55 * flip_x
            d.line([(pex - 5.0 * s, eye_y - 2.0 * s), (pex + 6.0 * s, eye_y), (pex - 3.0 * s, eye_y + 3.0 * s)], fill=ink, width=max(2, int(2.8 * s)))
            # Strong heavy brow with intense downward slant
            d.line([(pex - 8.0 * s, eye_y - 9.0 * s), (pex + 8.0 * s, eye_y - 6.0 * s)], fill=ink, width=max(2, int(3.5 * s)))
            # Firm downward mouth slit
            mx = cx + hw * 0.5 * flip_x
            my = cy + hh * 0.55
            d.line([(mx - 6.0 * s, my - 2.0 * s), (mx + 8.0 * s, my + 2.0 * s)], fill=ink, width=max(2, int(2.5 * s)))
        else:
            # Pair of piercing eyes
            sp = 14.0 * s * face.eye_spacing_ratio
            lex = cx + shift - sp * 0.5
            rex = cx + shift + sp * 0.5
            for ex in (lex, rex):
                # Slit eye shape
                d.polygon([(ex - 4.5 * s, eye_y), (ex, eye_y - 2.5 * s), (ex + 4.5 * s, eye_y), (ex, eye_y + 2.5 * s)], fill=ink)
                # Heavy dark brow with inward downward slant
                slant = 3.5 * s if ex == lex else -3.5 * s
                if flip_x < 0:
                    slant = -slant
                d.line([(ex - 6.5 * s, eye_y - 9.0 * s - slant * 0.3), (ex + 6.5 * s, eye_y - 9.0 * s + slant * 0.3)], fill=ink, width=max(2, int(3.8 * s)))

            # Aquiline nose bridge
            nx = cx + shift + 2.0 * s * flip_x
            ny = cy + hh * 0.22
            d.line([(nx, eye_y + 2.0 * s), (nx + 4.5 * s * flip_x, ny), (nx - 1.0 * s * flip_x, ny + 3.0 * s)], fill=ink, width=max(2, int(2.5 * s)))

            # Firm downward mouth line
            my = cy + hh * 0.58
            mw = 9.0 * s * face.mouth_width_ratio
            d.line([(cx + shift - mw, my - 1.0 * s), (cx + shift, my + 1.0 * s), (cx + shift + mw, my - 1.0 * s)], fill=ink, width=max(2, int(2.6 * s)))

    def _draw_hair_silhouette(
        self,
        d: ImageDraw.ImageDraw,
        state: CharacterAppearanceState,
        cx: float,
        cy: float,
        hw: float,
        hh: float,
        s: float,
        flip_x: float,
        is_back: bool,
        is_profile: bool,
        is_three_quarter: bool,
        color: tuple[int, int, int, int],
        ink: tuple[int, int, int, int],
    ):
        hair = state.hair
        top_y = cy - hh * (1.0 + hair.top_volume * 0.3)
        l_x = cx - hw * 1.08
        r_x = cx + hw * 1.08

        if is_back:
            # Full crown covering nape of neck
            poly = [
                (l_x, cy - hh * 0.2),
                (cx - hw * 0.6, top_y),
                (cx + hw * 0.6, top_y),
                (r_x, cy - hh * 0.2),
                (r_x - 6.0 * s, cy + hh * 0.45),
                (cx, cy + hh * 0.55),
                (l_x + 6.0 * s, cy + hh * 0.45),
            ]
        elif is_profile:
            # Distinctive angular profile comb
            front_fringe = cx + hw * 0.8 * flip_x
            poly = [
                (cx - hw * 0.85 * flip_x, cy + hh * 0.4),
                (cx - hw * 1.05 * flip_x, cy - hh * 0.3),
                (cx - hw * 0.4 * flip_x, top_y),
                (cx + hw * 0.3 * flip_x, top_y),
                (front_fringe, cy - hh * 0.5), # Prominent side-swept bangs!
                (front_fringe - 8.0 * s * flip_x, cy - hh * 0.15),
                (cx + hw * 0.2 * flip_x, cy - hh * 0.25),
                (cx - hw * 0.4 * flip_x, cy - hh * 0.1),
            ]
        else:
            # Iconic deep-left side part sweeping over right brow!
            part_x = cx - hw * 0.45 * flip_x
            poly = [
                (l_x, cy - hh * 0.25),
                (cx - hw * 0.6, top_y),
                (cx + hw * 0.6, top_y),
                (r_x + 6.0 * s * (1.0 if hair.direction == "SWEEP_RIGHT" else -1.0), cy - hh * 0.1),
                (cx + hw * 0.65 * flip_x, cy - hh * 0.05), # Bangs overhang across brow!
                (part_x, cy - hh * 0.48), # Clean sharp parting line
                (l_x + 4.0 * s, cy - hh * 0.15)
            ]

        d.polygon(poly, fill=color, outline=ink, width=max(2, int(3.2 * s)))

    def _draw_headwear(
        self,
        d: ImageDraw.ImageDraw,
        comp: Any,
        cx: float,
        cy: float,
        hw: float,
        hh: float,
        s: float,
        flip_x: float,
        is_profile: bool,
        is_back: bool,
        ink: tuple[int, int, int, int],
        silhouette_only: bool,
    ):
        name = comp.name.upper()
        cap_y = cy - hh * 0.65
        c_fill = hex_to_rgba(comp.primary_color) if not silhouette_only else ink
        c_sec = hex_to_rgba(comp.secondary_color) if not silhouette_only else ink

        if "STAHLHELM" in name or "HELMET" in name:
            # Dome helmet with curved neck flare
            d.pieslice([cx - hw * 1.2, cap_y - 25.0 * s, cx + hw * 1.2, cap_y + 35.0 * s], 180, 360, fill=c_fill, outline=ink, width=max(2, int(3.5 * s)))
            # Neck flare rim
            d.line([(cx - hw * 1.35, cap_y + 12.0 * s), (cx + hw * 1.35, cap_y + 12.0 * s)], fill=ink, width=max(3, int(4.5 * s)))

        elif "FELDMÜTZE" in name or "CAP" in name or "PEAKED" in name:
            # Field cap crown & band
            d.rectangle([cx - hw * 1.1, cap_y - 12.0 * s, cx + hw * 1.1, cap_y + 12.0 * s], fill=c_fill, outline=ink, width=2)
            # Red cockade / cap band
            if not silhouette_only:
                d.rectangle([cx - hw * 1.1, cap_y + 4.0 * s, cx + hw * 1.1, cap_y + 12.0 * s], fill=c_sec)
                d.ellipse([cx - 4.0 * s, cap_y + 5.0 * s, cx + 4.0 * s, cap_y + 11.0 * s], fill=(220, 40, 40, 255), outline=ink)

        elif "BANDAGE" in name:
            # Medical gauze eye wrap
            b_poly = [
                (cx - hw * 1.1, cy - 15.0 * s),
                (cx + hw * 1.1, cy - 15.0 * s),
                (cx + hw * 1.1, cy + 18.0 * s),
                (cx - hw * 1.1, cy + 18.0 * s),
            ]
            d.polygon(b_poly, fill=(240, 242, 245, 255) if not silhouette_only else ink, outline=ink, width=max(2, int(2.8 * s)))
            if not silhouette_only:
                d.line([(cx - hw * 1.05, cy), (cx + hw * 1.05, cy)], fill=(180, 185, 192, 255), width=2)

    # =========================================================================
    # LOCATION RENDERING
    # =========================================================================

    def render_location(
        self,
        bible: LocationMasterBible,
        mode: str = "FULL_COLOR", # FULL_COLOR, GRAYSCALE, ARCHITECTURE_SILHOUETTE, TOP_DOWN
        characters: list[tuple[CharacterAppearanceState, float, str, str]] | None = None, # (state, x, orient, action)
    ) -> Image.Image:
        """Renders one complete location in specified diagnostic or cinematic mode."""
        im = Image.new("RGBA", (self.width, self.height), (240, 238, 230, 255))
        d = ImageDraw.Draw(im, "RGBA")
        topo = bible.topology
        horiz = topo.horizon_y
        vp = topo.vanishing_point

        is_silhouette = (mode == "ARCHITECTURE_SILHOUETTE")
        is_grayscale = (mode == "GRAYSCALE")
        is_top_down = (mode == "TOP_DOWN")

        if is_top_down:
            return self._render_top_down(bible)

        # 1. Sky / Ceiling Background
        if is_silhouette:
            d.rectangle([0, 0, self.width, self.height], fill=(245, 245, 245, 255))
        else:
            sky_c = hex_to_rgba(bible.color_palette.get("sky_top", "#8ca0b4"))
            sky_b = hex_to_rgba(bible.color_palette.get("sky_bottom", "#dbe5ed"))
            if is_grayscale:
                sky_c = (160, 160, 160, 255)
                sky_b = (210, 210, 210, 255)
            # Sky vertical gradient
            for y in range(int(horiz)):
                t = y / max(1.0, horiz)
                c = tuple(int(sky_c[i]*(1-t) + sky_b[i]*t) for i in range(3)) + (255,)
                d.line([(0, y), (self.width, y)], fill=c)

        # 2. Architectural Primitives (Walls, Columns, Arches, Beams, Facades)
        for elem in sorted(bible.architectural_elements, key=lambda e: (0 if e.depth_layer == "BACKGROUND" else (1 if e.depth_layer == "MIDGROUND" else 2))):
            if is_silhouette:
                fill_color = (40, 40, 40, 255) if elem.depth_layer == "BACKGROUND" else (20, 20, 20, 255)
                stroke_color = (0, 0, 0, 255)
            else:
                fill_color = hex_to_rgba(elem.color_fill)
                stroke_color = hex_to_rgba(elem.color_stroke)
                if is_grayscale:
                    gray_val = int(fill_color[0]*0.299 + fill_color[1]*0.587 + fill_color[2]*0.114)
                    fill_color = (gray_val, gray_val, gray_val, 255)
                    stroke_color = (30, 30, 30, 255)

            # Draw polygon
            d.polygon(elem.polygon, fill=fill_color, outline=stroke_color, width=int(elem.stroke_width))

            # Cut out openings (windows, arch voids)
            for cutout in elem.opening_cutouts:
                cut_fill = (245, 245, 245, 255) if is_silhouette else (230, 238, 245, 255)
                d.polygon(cutout, fill=cut_fill, outline=stroke_color, width=2)
                # Draw window mullions if window
                if not is_silhouette and len(cutout) >= 4:
                    min_x = min(p[0] for p in cutout)
                    max_x = max(p[0] for p in cutout)
                    min_y = min(p[1] for p in cutout)
                    max_y = max(p[1] for p in cutout)
                    d.line([(min_x + (max_x - min_x)*0.5, min_y), (min_x + (max_x - min_x)*0.5, max_y)], fill=stroke_color, width=2)
                    d.line([(min_x, min_y + (max_y - min_y)*0.5), (max_x, min_y + (max_y - min_y)*0.5)], fill=stroke_color, width=2)

        # 3. Landmark Profile (Altering World Geometry)
        if bible.landmark:
            lm = bible.landmark
            if is_silhouette:
                lm_fill = (15, 15, 15, 255)
                lm_stroke = (0, 0, 0, 255)
            else:
                lm_fill = hex_to_rgba(bible.color_palette.get("accent", "#a68852"))
                lm_stroke = (25, 20, 15, 255)
                if is_grayscale:
                    lm_fill = (100, 100, 100, 255)
            d.polygon(lm.geometry_polygon, fill=lm_fill, outline=lm_stroke, width=3)

        # 4. Ground Contour & Perspective
        ground_poly = topo.ground_contour + [(self.width, self.height), (0, self.height)]
        if is_silhouette:
            ground_fill = (50, 50, 50, 255)
            ground_stroke = (10, 10, 10, 255)
        else:
            ground_fill = hex_to_rgba(bible.color_palette.get("floor", "#4a4035"))
            ground_stroke = hex_to_rgba(bible.color_palette.get("shadow", "#181512"))
            if is_grayscale:
                g_val = int(ground_fill[0]*0.299 + ground_fill[1]*0.587 + ground_fill[2]*0.114)
                ground_fill = (g_val, g_val, g_val, 255)

        d.polygon(ground_poly, fill=ground_fill, outline=ground_stroke, width=4)

        # Perspective guidelines to vanishing point
        if not is_silhouette:
            vp_x, vp_y = vp
            for frac in (0.1, 0.25, 0.4, 0.6, 0.75, 0.9):
                d.line([(vp_x, horiz), (frac * self.width, self.height)], fill=(20, 18, 16, 55), width=2)

        # 5. Motivated Directional Lighting Overlay
        if not is_silhouette and not is_grayscale and bible.light_sources:
            light_layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            ld = ImageDraw.Draw(light_layer, "RGBA")
            for ls in bible.light_sources:
                lx, ly = ls.position
                lc = hex_to_rgba(ls.color_hex, int(ls.intensity * 95))
                # Cone of motivated light
                ld.polygon([
                    (lx - 20, ly), (lx + 20, ly),
                    (lx + ls.direction_vector[0] * 700 + 400, self.height),
                    (lx + ls.direction_vector[0] * 700 - 400, self.height)
                ], fill=lc)
            light_layer = light_layer.filter(ImageFilter.GaussianBlur(45))
            im = Image.alpha_composite(im, light_layer)
            d = ImageDraw.Draw(im, "RGBA")

        # 6. Props & Dressing (Only in Full Color / Grayscale, NEVER in Silhouette test!)
        if not is_silhouette:
            self._draw_location_props(d, bible, is_grayscale)

        # 7. Characters (if provided for integration test)
        if characters:
            for char_state, char_x, char_orient, char_act in characters:
                # Calculate grounded foot Y from ground contour
                ground_y = 780.0
                for i in range(len(topo.ground_contour) - 1):
                    p1, p2 = topo.ground_contour[i], topo.ground_contour[i+1]
                    if p1[0] <= char_x <= p2[0]:
                        t = (char_x - p1[0]) / max(1.0, (p2[0] - p1[0]))
                        ground_y = p1[1] * (1 - t) + p2[1] * t
                        break

                self.draw_character(
                    d, char_state, char_x, ground_y,
                    orientation=char_orient, action=char_act,
                    silhouette_only=is_silhouette, grayscale=is_grayscale
                )

        return im

    def _draw_location_props(self, d: ImageDraw.ImageDraw, bible: LocationMasterBible, grayscale: bool):
        """Draws period-accurate prop ecology."""
        ink = (24, 20, 18, 255)
        accent = (185, 145, 80, 255) if not grayscale else (140, 140, 140, 255)

        if bible.location_type == "TRENCH_DUGOUT":
            # Sandbag stack & dispatch table
            d.rectangle([820, 680, 1100, 770], fill=(85, 75, 62, 255), outline=ink, width=3)
            # Hanging kerosene lantern
            d.ellipse([950, 220, 970, 250], fill=(245, 175, 60, 255), outline=ink, width=2)
            d.line([(960, 120), (960, 220)], fill=ink, width=2)
            # White dispatch paper on table
            d.polygon([(920, 675), (960, 672), (965, 688), (925, 690)], fill=(245, 245, 245, 255), outline=ink)

        elif bible.location_type == "URBAN_STREET":
            # Cast iron street lamp
            d.line([(320, 320), (320, 715)], fill=ink, width=6)
            d.ellipse([305, 290, 335, 320], fill=(255, 240, 180, 255) if not grayscale else (200, 200, 200, 255), outline=ink, width=2)
            # Tram tracks in cobblestone
            d.line([(750, 715), (600, 1080)], fill=(80, 80, 85, 255), width=3)
            d.line([(790, 715), (680, 1080)], fill=(80, 80, 85, 255), width=3)

        elif bible.location_type == "MILITARY_HOSPITAL":
            # Row of iron hospital cots
            for bx in (320, 820, 1340):
                d.rectangle([bx, 680, bx + 220, 740], fill=(225, 230, 235, 255), outline=ink, width=2)
                d.line([(bx, 640), (bx, 740)], fill=ink, width=3)
                d.line([(bx + 220, 660), (bx + 220, 740)], fill=ink, width=3)

        elif bible.location_type == "BEER_HALL":
            # Trestle table and beer steins
            d.rectangle([620, 710, 1300, 740], fill=(55, 38, 24, 255), outline=ink, width=3)
            for sx in (720, 880, 1040, 1180):
                d.rectangle([sx, 675, sx + 22, 710], fill=(160, 140, 110, 255), outline=ink, width=2)

    def _render_top_down(self, bible: LocationMasterBible) -> Image.Image:
        """Renders 2D top-down blueprint geography with circulation and boundaries."""
        im = Image.new("RGBA", (self.width, self.height), (24, 30, 42, 255))
        d = ImageDraw.Draw(im, "RGBA")
        grid_color = (40, 52, 70, 255)
        cyan = (80, 210, 235, 255)
        yellow = (245, 205, 80, 255)

        # Blueprint grid
        for x in range(0, self.width, 60):
            d.line([(x, 0), (x, self.height)], fill=grid_color, width=1)
        for y in range(0, self.height, 60):
            d.line([(0, y), (self.width, y)], fill=grid_color, width=1)

        # Title
        d.text((60, 50), f"TOP-DOWN BLUEPRINT GEOGRAPHY: {bible.canonical_name.upper()}", fill=(240, 245, 250, 255))
        d.text((60, 85), f"Construction: {bible.construction_system} | Era: {bible.era_date}", fill=(160, 185, 210, 255))

        # Boundary polygon scaled to center
        cx, cy = self.width * 0.5, self.height * 0.55
        poly_scaled = [(cx + (p[0] - 960) * 0.65, cy + (p[1] - 540) * 0.65) for p in bible.topology.boundary_polygon]
        d.polygon(poly_scaled, outline=cyan, width=4)

        # Architectural elements footprint
        for elem in bible.architectural_elements:
            elem_scaled = [(cx + (p[0] - 960) * 0.65, cy + (p[1] - 540) * 0.65) for p in elem.polygon]
            d.polygon(elem_scaled, fill=(35, 60, 85, 180), outline=(120, 180, 220, 255), width=2)
            # Label
            d.text((elem_scaled[0][0] + 8, elem_scaled[0][1] + 8), elem.primitive.value, fill=(200, 225, 245, 255))

        # Circulation corridor
        if bible.topology.circulation_corridor:
            corridor = [(cx + (p[0] - 960) * 0.65, cy + (p[1] - 540) * 0.65) for p in bible.topology.circulation_corridor]
            d.line(corridor, fill=yellow, width=5)
            d.text((corridor[0][0] + 10, corridor[0][1] - 15), "CIRCULATION AXIS", fill=yellow)

        # Vanishing Point Anchor
        vp_scaled = (cx + (bible.topology.vanishing_point[0] - 960) * 0.65, cy + (bible.topology.vanishing_point[1] - 540) * 0.65)
        d.ellipse([vp_scaled[0] - 8, vp_scaled[1] - 8, vp_scaled[0] + 8, vp_scaled[1] + 8], fill=(255, 60, 60, 255))
        d.text((vp_scaled[0] + 12, vp_scaled[1] - 6), f"VANISHING POINT ({bible.topology.dominant_depth_axis})", fill=(255, 120, 120, 255))

        return im
