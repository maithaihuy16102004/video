"""Illustrated Reconstruction Renderer for Research-Grounded Visual Assets.

Renders all required side-by-side comparison sheets and the primary master review sheet:
1. episode01_research_grounded_visual_master.png (PRIMARY REVIEW SHEET: 3-column Master Comparison)
2. episode01_location_reference_vs_render.png (3 Real Locations: Odeonsplatz, Somme, Pasewalk)
3. episode01_character_reference_vs_stickman.png (Hitler 1914 Age 25 Portrait vs Stickman Turnaround)
4. episode01_costume_reference_vs_render.png (Bavarian Uniform Reference vs Render)
5. episode01_hero_object_reference_vs_render.png (Stahlhelm M16 & Canister Reference vs Render)
6. episode01_map_reference_sheet.png
7. episode01_character_reference_sheet.png
8. episode01_location_reference_sheet.png
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .fact_models import VisualFactRepository
from .map_pipeline import MapResearchPipeline


class IllustratedReconstructionRenderer:
    """Renders research-grounded visual assets and comparison review sheets."""

    def __init__(self, references_dir: Path, output_dir: Path):
        self.ref_dir = references_dir
        self.out_dir = output_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.map_pipeline = MapResearchPipeline()

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        font_names = ["arialbd.ttf" if bold else "arial.ttf", "timesbd.ttf" if bold else "times.ttf"]
        for fn in font_names:
            try:
                return ImageFont.truetype(f"C:/Windows/Fonts/{fn}", size)
            except Exception:
                continue
        return ImageFont.load_default()

    # =========================================================================
    # INDIVIDUAL RECONSTRUCTION RENDERS
    # =========================================================================

    def render_odeonsplatz_reconstruction(self, w: int = 960, h: int = 540) -> Image.Image:
        """Renders illustrated Odeonsplatz & Feldherrnhalle in the project's visual style."""
        img = Image.new("RGB", (w, h), "#EAE3D2")
        draw = ImageDraw.Draw(img)

        # Sky
        draw.rectangle([0, 0, w, int(h * 0.40)], fill="#D2E2EE")

        # Flanking classical facades (perspective walls)
        left_wall = [(0, int(h * 0.15)), (int(w * 0.18), int(h * 0.35)), (int(w * 0.18), int(h * 0.65)), (0, int(h * 0.85))]
        draw.polygon(left_wall, fill="#C4B8A0", outline="#504538", width=2)
        right_wall = [(w, int(h * 0.15)), (int(w * 0.82), int(h * 0.35)), (int(w * 0.82), int(h * 0.65)), (w, int(h * 0.85))]
        draw.polygon(right_wall, fill="#C4B8A0", outline="#504538", width=2)

        # Cobblestone Plaza Floor
        plaza_pts = [(0, int(h * 0.85)), (int(w * 0.18), int(h * 0.65)), (int(w * 0.82), int(h * 0.65)), (w, int(h * 0.85)), (w, h), (0, h)]
        draw.polygon(plaza_pts, fill="#A89E8D", outline="#504538", width=2)
        # Cobblestone grid lines
        for y in range(int(h * 0.66), h, 18):
            draw.line([(0, y + int((y - h*0.65)*0.3)), (w, y + int((y - h*0.65)*0.3))], fill="#8C8272", width=1)

        # Feldherrnhalle Main Loggia Structure (Neoclassical Triple Arches)
        fh_x1, fh_y1 = int(w * 0.18), int(h * 0.22)
        fh_x2, fh_y2 = int(w * 0.82), int(h * 0.65)
        # Main limestone block
        draw.rectangle([fh_x1, fh_y1, fh_x2, fh_y2], fill="#D8CEBC", outline="#3E3428", width=3)

        # Entablature & Pediment cornice
        draw.rectangle([fh_x1 - 10, fh_y1 - 20, fh_x2 + 10, fh_y1], fill="#C2B5A0", outline="#3E3428", width=2)
        draw.line([(fh_x1 - 10, fh_y1 - 10), (fh_x2 + 10, fh_y1 - 10)], fill="#8C7D6B", width=1)

        # 3 Monumental Florentine Round Arches
        arch_w = (fh_x2 - fh_x1) // 3
        arch_h = int((fh_y2 - fh_y1) * 0.75)
        arch_y_base = fh_y2 - 10

        for i in range(3):
            ax1 = fh_x1 + i * arch_w + 14
            ax2 = fh_x1 + (i + 1) * arch_w - 14
            ay_top = fh_y1 + 35
            # Dark interior recessed shadow
            draw.rectangle([ax1, ay_top + (ax2 - ax1) // 2, ax2, arch_y_base], fill="#4A4035", outline="#2A2218", width=2)
            draw.chord([ax1, ay_top, ax2, ay_top + (ax2 - ax1)], start=180, end=0, fill="#4A4035", outline="#2A2218", width=2)

            # Arch keystone
            draw.polygon([( (ax1 + ax2)//2 - 6, ay_top - 4 ), ( (ax1 + ax2)//2 + 6, ay_top - 4 ), ( (ax1 + ax2)//2, ay_top + 10 )], fill="#AA9E88")

            # Outer arches contain bronze statues of Tilly & Wrede
            if i == 0 or i == 2:
                sx = (ax1 + ax2) // 2
                draw.rectangle([sx - 10, arch_y_base - 18, sx + 10, arch_y_base], fill="#222520")
                draw.ellipse([sx - 6, arch_y_base - 55, sx + 6, arch_y_base - 40], fill="#1B3328")
                draw.rectangle([sx - 9, arch_y_base - 40, sx + 9, arch_y_base - 18], fill="#1B3328")
                draw.line([(sx - 4, arch_y_base - 18), (sx - 4, arch_y_base)], fill="#1B3328", width=3)
                draw.line([(sx + 4, arch_y_base - 18), (sx + 4, arch_y_base)], fill="#1B3328", width=3)

        # Balustrade & Front steps
        draw.rectangle([fh_x1 - 15, fh_y2, fh_x2 + 15, fh_y2 + 20], fill="#B8AC96", outline="#3E3428", width=2)
        # Bavarian Lions on plinths
        draw.rectangle([fh_x1 - 14, fh_y2 - 12, fh_x1 + 6, fh_y2], fill="#8A7E6C", outline="#3E3428", width=1)
        draw.rectangle([fh_x2 - 6, fh_y2 - 12, fh_x2 + 14, fh_y2], fill="#8A7E6C", outline="#3E3428", width=1)

        # August 1914 Mobilization Crowd (Dense silhouettes with Edwardian hats)
        crowd_y_base = int(h * 0.88)
        import random
        rng = random.Random(1914)
        for cx in range(int(w * 0.08), int(w * 0.92), 16):
            cy = crowd_y_base + rng.randint(-15, 25)
            # Body suit silhouette
            draw.rectangle([cx - 5, cy - 35, cx + 5, cy], fill="#26221E")
            # Head
            draw.ellipse([cx - 4, cy - 46, cx + 4, cy - 36], fill="#D89A78")
            # Hat: Bowler or Straw boater
            if rng.random() > 0.4:
                # Bowler
                draw.ellipse([cx - 6, cy - 50, cx + 6, cy - 44], fill="#181410")
                draw.line([(cx - 8, cy - 45), (cx + 8, cy - 45)], fill="#181410", width=2)
            else:
                # Straw boater
                draw.rectangle([cx - 7, cy - 48, cx + 7, cy - 44], fill="#D0C090")
                draw.line([(cx - 9, cy - 44), (cx + 9, cy - 44)], fill="#A89060", width=2)

            # Tossed hats in the air (celebrating mobilization)
            if rng.random() > 0.82:
                ty = cy - rng.randint(65, 110)
                draw.ellipse([cx - 5, ty, cx + 5, ty + 4], fill="#181410")

        # Architectural and Historical Labels
        draw.text((20, 20), "MUNICH ODEONSPLATZ & FELDHERRNHALLE", fill="#1C1814", font=self._get_font(18, bold=True))
        draw.text((20, 44), "August 1914 Mobilization Proclamation Scene | Factual Triple Florentine Arches", fill="#5A5042", font=self._get_font(13))

        return img

    def render_somme_trench_reconstruction(self, w: int = 960, h: int = 540) -> Image.Image:
        """Renders illustrated Somme subterranean trench in the project's visual style."""
        img = Image.new("RGB", (w, h), "#3B3834")
        draw = ImageDraw.Draw(img)

        # Low Subterranean Horizon at 35% height
        horizon_y = int(h * 0.35)

        # Overcast mist sky
        draw.rectangle([0, 0, w, horizon_y], fill="#8A9298")
        # Distant battle smoke and mist
        for sx in range(0, w, 40):
            draw.ellipse([sx - 30, horizon_y - 25, sx + 50, horizon_y + 10], fill="#7A8086")

        # Sandbag Parapet Lip (top of trench walls)
        draw.rectangle([0, horizon_y, w, horizon_y + 35], fill="#6A5D4A", outline="#2A241A", width=2)
        for bx in range(0, w, 28):
            draw.ellipse([bx, horizon_y - 4, bx + 26, horizon_y + 16], fill="#786852", outline="#2A241A", width=1)
            draw.ellipse([bx + 12, horizon_y + 12, bx + 38, horizon_y + 32], fill="#645642", outline="#2A241A", width=1)

        # Left Trench Wall: Vertical Split Pine Timber Revetments
        left_wall = [(0, horizon_y + 35), (int(w * 0.32), horizon_y + 80), (int(w * 0.28), h), (0, h)]
        draw.polygon(left_wall, fill="#4A3D2D", outline="#1E1710", width=2)
        # Vertical split logs on left wall
        for lx in range(0, int(w * 0.30), 14):
            ly_top = horizon_y + 35 + int(lx * 0.15)
            draw.line([(lx, ly_top), (lx, h)], fill="#30261A", width=3)
            draw.line([(lx + 2, ly_top), (lx + 2, h)], fill="#5C4D38", width=1)

        # Right Trench Wall: Timber & Wicker Wattle Revetment
        right_wall = [(w, horizon_y + 35), (int(w * 0.68), horizon_y + 80), (int(w * 0.72), h), (w, h)]
        draw.polygon(right_wall, fill="#4A3D2D", outline="#1E1710", width=2)
        # Vertical split logs on right wall
        for rx in range(int(w * 0.70), w, 14):
            ry_top = horizon_y + 80 - int((rx - w * 0.70) * 0.15)
            draw.line([(rx, ry_top), (rx, h)], fill="#30261A", width=3)
            draw.line([(rx + 2, ry_top), (rx + 2, h)], fill="#5C4D38", width=1)

        # Dugout Entrance (right wall recessed shelter)
        dug_x1, dug_y1 = int(w * 0.76), horizon_y + 90
        dug_x2, dug_y2 = int(w * 0.90), int(h * 0.85)
        draw.rectangle([dug_x1, dug_y1, dug_x2, dug_y2], fill="#15120E", outline="#0A0806", width=2)
        draw.arc([dug_x1, dug_y1 - 20, dug_x2, dug_y1 + 20], start=180, end=0, fill="#2E2820", width=3)

        # Trench Floor: Picardy Mud & Wooden Duckboards (Grabenrost)
        floor_pts = [(int(w * 0.28), h), (int(w * 0.32), horizon_y + 80), (int(w * 0.68), horizon_y + 80), (int(w * 0.72), h)]
        draw.polygon(floor_pts, fill="#342D24", outline="#1E1710", width=2)

        # Raised Wooden Duckboards in center
        db_top_w = 40
        db_bot_w = 160
        db_x_center = w // 2
        for step_y in range(horizon_y + 85, h, 14):
            progress = (step_y - (horizon_y + 85)) / (h - (horizon_y + 85))
            cur_w = int(db_top_w + progress * (db_bot_w - db_top_w))
            draw.rectangle([db_x_center - cur_w//2, step_y, db_x_center + cur_w//2, step_y + 8], fill="#625442", outline="#201A12", width=1)
            # Center drainage gap between duckboard slats
            draw.line([(db_x_center, step_y), (db_x_center, step_y + 8)], fill="#1E1710", width=1)

        # Mud puddles with specular light sheen
        draw.ellipse([db_x_center - 80, int(h * 0.82), db_x_center - 30, int(h * 0.88)], fill="#25211B", outline="#453E32", width=1)
        draw.ellipse([db_x_center + 40, int(h * 0.75), db_x_center + 90, int(h * 0.80)], fill="#25211B", outline="#453E32", width=1)

        # Communication Telephone Wires strung along wall posts
        draw.line([(0, horizon_y + 60), (int(w * 0.32), horizon_y + 95)], fill="#100E0C", width=2)
        draw.line([(0, horizon_y + 70), (int(w * 0.32), horizon_y + 105)], fill="#100E0C", width=1)

        # Labels
        draw.text((20, 20), "WESTERN FRONT: SOMME COMMUNICATION TRENCH", fill="#F0ECE4", font=self._get_font(18, bold=True))
        draw.text((20, 44), "Subterranean Perspective (Horizon: 35%) | Split Pine Revetment & Duckboard Path", fill="#D0C8B8", font=self._get_font(13))

        return img

    def render_pasewalk_hospital_reconstruction(self, w: int = 960, h: int = 540) -> Image.Image:
        """Renders illustrated Pasewalk Reservelazarett hospital ward in the project's visual style."""
        img = Image.new("RGB", (w, h), "#E8ECE8")
        draw = ImageDraw.Draw(img)

        # Upper Wall: Whitewashed Lime Plaster
        horizon_y = int(h * 0.55)
        wainscot_y = int(h * 0.60)

        # Back Wall
        draw.rectangle([0, 0, w, wainscot_y], fill="#F0F4F0")
        # Sanitary Oil Wainscoting (Dark Green lower wall)
        draw.rectangle([0, wainscot_y, w, int(h * 0.75)], fill="#2B483A", outline="#16261E", width=2)
        # Wooden Floorboards
        draw.rectangle([0, int(h * 0.75), w, h], fill="#B8A892", outline="#504230", width=2)
        for fy in range(int(h * 0.76), h, 16):
            draw.line([(0, fy), (w, fy)], fill="#96856E", width=1)

        # Tall Prussian Lancet Arched Windows on Back Wall
        win_w = 90
        win_h = 190
        win_y = 60
        for win_x in [int(w * 0.22), int(w * 0.50) - win_w//2, int(w * 0.78) - win_w]:
            # Arched window frame
            draw.rectangle([win_x, win_y + win_w//2, win_x + win_w, win_y + win_h], fill="#C2D8E4", outline="#2C3A32", width=3)
            draw.chord([win_x, win_y, win_x + win_w, win_y + win_w], start=180, end=0, fill="#C2D8E4", outline="#2C3A32", width=3)
            # Window mullions & panes
            draw.line([(win_x + win_w//2, win_y), (win_x + win_w//2, win_y + win_h)], fill="#2C3A32", width=2)
            draw.line([(win_x, win_y + win_h//3), (win_x + win_w, win_y + win_h//3)], fill="#2C3A32", width=1)
            draw.line([(win_x, win_y + 2*win_h//3), (win_x + win_w, win_y + 2*win_h//3)], fill="#2C3A32", width=1)
            # Pale daylight beam cast on floor
            light_beam = [(win_x - 10, int(h * 0.75)), (win_x + win_w + 10, int(h * 0.75)), (win_x + win_w + 40, h), (win_x - 40, h)]
            draw.polygon(light_beam, fill="#D8E2D6")

        # Cast-Iron Hospital Beds along the Ward
        for bed_x, bed_y, scale in [(int(w * 0.12), int(h * 0.72), 0.9), (int(w * 0.44), int(h * 0.73), 1.0), (int(w * 0.76), int(h * 0.72), 0.9)]:
            bw, bh = int(140 * scale), int(60 * scale)
            # Bed frame (black iron pipe)
            draw.rectangle([bed_x, bed_y, bed_x + bw, bed_y + bh], fill="#FFFFFF", outline="#1A1A1A", width=2)
            # Headboard & Footboard
            draw.line([(bed_x, bed_y - 25), (bed_x, bed_y + bh + 15)], fill="#1A1A1A", width=3)
            draw.line([(bed_x + bw, bed_y - 15), (bed_x + bw, bed_y + bh + 15)], fill="#1A1A1A", width=3)
            # Pillow & Blanket
            draw.rectangle([bed_x + 5, bed_y + 5, bed_x + 35, bed_y + bh - 5], fill="#EAEAEA")
            draw.rectangle([bed_x + 35, bed_y + 5, bed_x + bw - 5, bed_y + bh - 5], fill="#687262") # Field grey hospital blanket

        # Center Bed Figure: Convalescent Patient with Eye Bandage (Hitler at Pasewalk 1918)
        px = int(w * 0.44) + 25
        py = int(h * 0.73) - 10
        # Seated torso in hospital gown
        draw.rectangle([px, py - 45, px + 22, py + 10], fill="#EAEAEA", outline="#202020", width=2)
        # Head
        draw.ellipse([px + 2, py - 70, px + 20, py - 46], fill="#D89A78", outline="#202020", width=1)
        # White Gauze Eye Bandage wrapped around eyes/head
        draw.rectangle([px, py - 62, px + 22, py - 52], fill="#FFFFFF", outline="#888888", width=1)
        # Hair tuft sticking out above bandage
        draw.arc([px + 2, py - 74, px + 18, py - 64], start=180, end=0, fill="#2C2218", width=3)

        # Labels
        draw.text((20, 20), "PASEWALK MILITARY CONVALESCENT HOSPITAL (RESERVELAZARETT)", fill="#16261E", font=self._get_font(18, bold=True))
        draw.text((20, 44), "October - November 1918 | Prussian Arched Windows & Sanitary Wainscot", fill="#385244", font=self._get_font(13))

        return img

    def render_character_turnaround(self, w: int = 960, h: int = 540) -> Image.Image:
        """Renders illustrated stickman turnaround (FRONT, 3/4, PROFILE) of Hitler 1914 Age 25."""
        img = Image.new("RGB", (w, h), "#F4F1EA")
        draw = ImageDraw.Draw(img)

        # Title
        draw.text((w // 2 - 280, 20), "ADOLF HITLER (AGE 25, 1914 MUNICH ENLISTMENT)", fill="#1C1814", font=self._get_font(20, bold=True))
        draw.text((w // 2 - 320, 48), "Illustrated Stickman Turnaround | Research-Grounded 1914 Physiognomy & Kaiser Handlebar", fill="#5A5042", font=self._get_font(14))

        # 3 View Panels: Front, 3/4 View, Profile
        views = [
            ("FRONT VIEW", int(w * 0.20)),
            ("THREE-QUARTER VIEW", int(w * 0.50)),
            ("PROFILE VIEW (LEFT)", int(w * 0.80)),
        ]

        ground_y = int(h * 0.84)
        head_r = 30
        body_h = 130
        leg_h = 120

        for title, cx in views:
            # Pedestal Shadow
            draw.ellipse([cx - 45, ground_y - 8, cx + 45, ground_y + 8], fill="#D8D0C4")
            draw.text((cx - 50, ground_y + 20), title, fill="#2C241C", font=self._get_font(14, bold=True))

            hip_y = ground_y - leg_h
            neck_y = hip_y - body_h
            head_cy = neck_y - head_r

            # Legs (Wool trousers & black laced boots)
            if "PROFILE" in title:
                draw.line([(cx, hip_y), (cx + 8, ground_y)], fill="#2C2420", width=8)
                draw.polygon([(cx + 4, ground_y - 6), (cx + 22, ground_y), (cx + 2, ground_y)], fill="#111111")
            else:
                draw.line([(cx - 10, hip_y), (cx - 14, ground_y)], fill="#2C2420", width=7)
                draw.line([(cx + 10, hip_y), (cx + 14, ground_y)], fill="#2C2420", width=7)
                draw.polygon([(cx - 22, ground_y), (cx - 8, ground_y), (cx - 14, ground_y - 8)], fill="#111111")
                draw.polygon([(cx + 8, ground_y), (cx + 22, ground_y), (cx + 14, ground_y - 8)], fill="#111111")

            # Torso: Edwardian Dark Wool Suit Jacket & Stiff White Collar
            torso_box = [cx - 18, neck_y, cx + 18, hip_y]
            draw.rectangle(torso_box, fill="#242220", outline="#111111", width=2)
            # White shirt collar V-notch
            draw.polygon([(cx - 6, neck_y), (cx + 6, neck_y), (cx, neck_y + 16)], fill="#F5F5F5")
            draw.line([(cx, neck_y + 16), (cx, neck_y + 36)], fill="#151515", width=3) # Dark tie

            # Arms
            if "PROFILE" in title:
                draw.line([(cx, neck_y + 10), (cx + 10, neck_y + 70), (cx + 4, hip_y + 20)], fill="#242220", width=6)
            else:
                draw.line([(cx - 16, neck_y + 10), (cx - 24, neck_y + 70), (cx - 20, hip_y + 15)], fill="#242220", width=5)
                draw.line([(cx + 16, neck_y + 10), (cx + 24, neck_y + 70), (cx + 20, hip_y + 15)], fill="#242220", width=5)

            # Neck
            draw.line([(cx, neck_y), (cx, neck_y - 6)], fill="#D89A78", width=8)

            # Head Contour (Gaunt, Angular 25-Year-Old Face)
            draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill="#E4AA86", outline="#201A14", width=2)

            # Eyes (Intense, staring expression)
            if "FRONT" in title:
                draw.ellipse([cx - 12, head_cy - 4, cx - 6, head_cy + 2], fill="#1C3852")
                draw.ellipse([cx + 6, head_cy - 4, cx + 12, head_cy + 2], fill="#1C3852")
                draw.line([(cx - 14, head_cy - 8), (cx - 4, head_cy - 6)], fill="#221C16", width=2)
                draw.line([(cx + 4, head_cy - 6), (cx + 14, head_cy - 8)], fill="#221C16", width=2)
            elif "THREE" in title:
                draw.ellipse([cx - 4, head_cy - 4, cx + 2, head_cy + 2], fill="#1C3852")
                draw.ellipse([cx + 12, head_cy - 4, cx + 18, head_cy + 2], fill="#1C3852")
                draw.line([(cx - 6, head_cy - 8), (cx + 4, head_cy - 6)], fill="#221C16", width=2)
                draw.line([(cx + 10, head_cy - 6), (cx + 20, head_cy - 8)], fill="#221C16", width=2)
            else: # Profile
                draw.ellipse([cx + 10, head_cy - 4, cx + 16, head_cy + 2], fill="#1C3852")
                draw.line([(cx + 8, head_cy - 8), (cx + 18, head_cy - 6)], fill="#221C16", width=2)
                # Nose prominence
                draw.polygon([(cx + head_r - 2, head_cy - 6), (cx + head_r + 10, head_cy + 6), (cx + head_r - 4, head_cy + 10)], fill="#E4AA86")

            # 1914 HAIR: Sharp Left Part, Dark Brown Sweep Across Crown
            hair_pts = [(cx - head_r - 2, head_cy), (cx - head_r + 4, head_cy - head_r - 4), (cx + head_r + 2, head_cy - head_r + 2), (cx + head_r - 2, head_cy)]
            draw.polygon(hair_pts, fill="#2C2016")
            draw.arc([cx - head_r - 2, head_cy - head_r - 4, cx + head_r + 2, head_cy + 4], start=170, end=350, fill="#18120C", width=3)
            # Long sweep over left forehead
            draw.arc([cx - head_r + 6, head_cy - head_r + 2, cx + 8, head_cy - 2], start=210, end=330, fill="#2C2016", width=4)

            # 1914 MUSTACHE: Wide Imperial Handlebar extending past mouth corners (NOT Toothbrush!)
            if "FRONT" in title:
                draw.line([(cx - 18, head_cy + 12), (cx, head_cy + 15), (cx + 18, head_cy + 12)], fill="#1E1610", width=4)
                draw.line([(cx - 18, head_cy + 12), (cx - 22, head_cy + 8)], fill="#1E1610", width=2) # Tapered upward tip
                draw.line([(cx + 18, head_cy + 12), (cx + 22, head_cy + 8)], fill="#1E1610", width=2)
            elif "THREE" in title:
                draw.line([(cx - 10, head_cy + 12), (cx + 6, head_cy + 15), (cx + 22, head_cy + 11)], fill="#1E1610", width=4)
                draw.line([(cx + 22, head_cy + 11), (cx + 26, head_cy + 7)], fill="#1E1610", width=2)
            else: # Profile
                draw.polygon([(cx + head_r - 6, head_cy + 12), (cx + head_r + 14, head_cy + 11), (cx + head_r + 16, head_cy + 6), (cx + head_r - 2, head_cy + 16)], fill="#1E1610")

        # Era Warning Callout at bottom
        draw.rectangle([w // 2 - 380, h - 50, w // 2 + 380, h - 14], fill="#FFE8E8", outline="#CC0000", width=2)
        draw.text((w // 2 - 360, h - 42), "CRITICAL FACT VERIFICATION: 1914 Kaiser Handlebar Mustache (Toothbrush prohibited for 1914).", fill="#880000", font=self._get_font(13, bold=True))

        return img

    def render_costume_reconstruction(self, w: int = 960, h: int = 540) -> Image.Image:
        """Renders illustrated Bavarian M1907/10 Feldgrau uniform reconstruction."""
        img = Image.new("RGB", (w, h), "#EBE5D8")
        draw = ImageDraw.Draw(img)

        # Title
        draw.text((40, 20), "BAVARIAN 16th RIR (LIST) M1907/10 FELDROCK RECONSTRUCTION", fill="#1C1814", font=self._get_font(18, bold=True))
        draw.text((40, 46), "Archival Grounding: Armeemuseum Ingolstadt & AKO 1897 Regulations", fill="#5A5042", font=self._get_font(13))

        # Left: Illustrated Mannequin Tunic
        mx, my = 260, 280
        # M1907/10 Feldrock Body (Bavarian Feldgrau Wool #4B5344)
        tunic_pts = [(mx - 70, my - 160), (mx + 70, my - 160), (mx + 85, my + 90), (mx - 85, my + 90)]
        draw.polygon(tunic_pts, fill="#4B5344", outline="#20251D", width=3)

        # Red Infantry Piping (Hochrot) along front fly
        draw.line([(mx, my - 160), (mx, my + 90)], fill="#8B1E1E", width=4)
        # Tombac matte crowned buttons
        for by in range(my - 130, my + 80, 38):
            draw.ellipse([mx - 5, by - 5, mx + 5, by + 5], fill="#B89448", outline="#302010", width=1)

        # Turnback Stand-and-Fall Collar with Red Piping
        draw.rectangle([mx - 45, my - 180, mx + 45, my - 158], fill="#3E4537", outline="#20251D", width=2)
        draw.rectangle([mx - 43, my - 180, mx + 43, my - 176], fill="#8B1E1E")

        # Brandenburg Cuffs with 3 Buttons on Flap
        for side, cx in [(-1, mx - 80), (1, mx + 80)]:
            draw.rectangle([cx - 15, my + 45, cx + 15, my + 80], fill="#3E4537", outline="#20251D", width=2)
            draw.rectangle([cx - 4, my + 48, cx + 4, my + 77], fill="#8B1E1E") # Red flap edge
            for cby in [my + 53, my + 63, my + 73]:
                draw.ellipse([cx - 2, cby - 2, cx + 2, cby + 2], fill="#B89448")

        # Bavarian Leather Belt & Ammo Pouches
        draw.rectangle([mx - 86, my + 10, mx + 86, my + 32], fill="#4A3420", outline="#1F140A", width=2)
        # Bavarian "IN TREUE FEST" Crown Buckle
        draw.rectangle([mx - 18, my + 8, mx + 18, my + 34], fill="#C5A454", outline="#1F140A", width=2)
        draw.text((mx - 14, my + 12), "BAV", fill="#1F140A", font=self._get_font(11, bold=True))

        # Right: Detail Callouts & Insignia
        call_x = 520
        # 1. Dual Cockades
        draw.text((call_x, 100), "HEADWEAR: M1910 KRÄTZCHEN FIELD CAP", fill="#202020", font=self._get_font(15, bold=True))
        # Reich Cockade (Top)
        draw.ellipse([call_x + 20, 130, call_x + 50, 160], fill="#FFFFFF", outline="#111111", width=3) # Black outer
        draw.ellipse([call_x + 26, 136, call_x + 44, 154], fill="#FFFFFF") # White ring
        draw.ellipse([call_x + 31, 141, call_x + 39, 149], fill="#CC0000") # Red center
        draw.text((call_x + 65, 138), "Reich Cockade (Black-White-Red)", fill="#333333", font=self._get_font(13))

        # Bavarian State Cockade (Band)
        draw.ellipse([call_x + 20, 175, call_x + 50, 205], fill="#FFFFFF", outline="#4080B0", width=3)
        draw.ellipse([call_x + 31, 186, call_x + 39, 194], fill="#3080D0") # Bavarian Sky Blue
        draw.text((call_x + 65, 183), "Bavarian State Cockade (White & Sky Blue)", fill="#333333", font=self._get_font(13, bold=True))

        # 2. Fabric Swatch
        draw.text((call_x, 230), "PRIMARY FABRIC: BAVARIAN FELDGRAU", fill="#202020", font=self._get_font(15, bold=True))
        draw.rectangle([call_x + 20, 260, call_x + 80, 310], fill="#4B5344", outline="#111111", width=2)
        draw.text((call_x + 95, 265), "Hex: #4B5344 (Bavarian Wool)", fill="#333333", font=self._get_font(13))
        draw.text((call_x + 95, 285), "Distinct from Prussian lighter stone-grey", fill="#666666", font=self._get_font(12))

        # 3. Belt Buckle Motto
        draw.text((call_x, 340), "BELT BUCKLE: IN TREUE FEST", fill="#202020", font=self._get_font(15, bold=True))
        draw.rectangle([call_x + 20, 370, call_x + 70, 405], fill="#C5A454", outline="#111111", width=2)
        draw.text((call_x + 85, 375), "Bavarian Motto 'In Treue Fest'", fill="#333333", font=self._get_font(13, bold=True))
        draw.text((call_x + 85, 393), "Distinct from Prussian 'Gott Mit Uns'", fill="#666666", font=self._get_font(12))

        return img

    def render_hero_object_reconstruction(self, w: int = 960, h: int = 540) -> Image.Image:
        """Renders illustrated Stahlhelm M16 and Gas Mask Canister."""
        img = Image.new("RGB", (w, h), "#EAE5D9")
        draw = ImageDraw.Draw(img)

        # Title
        draw.text((40, 20), "STAHLHELM M16 & CORRUGATED GAS MASK CANISTER RECONSTRUCTION", fill="#1C1814", font=self._get_font(18, bold=True))
        draw.text((40, 46), "Archival Grounding: Deutsches Historisches Museum & Imperial War Museum", fill="#5A5042", font=self._get_font(13))

        # Left: Stahlhelm M16 Profile
        hx, hy = 260, 280
        # Helmet Bell Dome (Field Grey Steel #485244)
        helmet_pts = [
            (hx - 140, hy + 40), # Flared rear neck apron
            (hx - 110, hy - 20), # Sloping rear dome
            (hx - 40, hy - 90),  # Crown apex
            (hx + 40, hy - 85),  # Forward slope
            (hx + 100, hy - 15), # Brow brow ridge
            (hx + 130, hy + 10), # Front visor tip
            (hx + 80, hy + 25),  # Visor under-rim
            (hx - 20, hy + 35),  # Ear cutout
            (hx - 120, hy + 45), # Apron lower edge
        ]
        draw.polygon(helmet_pts, fill="#424D40", outline="#182016", width=4)
        # Surface specular highlight
        draw.arc([hx - 80, hy - 75, hx + 60, hy - 30], start=200, end=340, fill="#626E60", width=4)

        # CRITICAL FACT: Twin Stirnpanzer Ventilation Lugs (Horns)
        draw.rectangle([hx + 10, hy - 35, hx + 24, hy - 18], fill="#303A2E", outline="#182016", width=2)
        draw.ellipse([hx + 20, hy - 32, hx + 24, hy - 21], fill="#182016") # Central vent hole
        draw.text((hx - 60, hy + 65), "STAHLHELM MODELL 1916", fill="#182016", font=self._get_font(15, bold=True))
        draw.text((hx - 60, hy + 85), "• Deep flared neck apron", fill="#384236", font=self._get_font(13))
        draw.text((hx - 60, hy + 103), "• Stirnpanzer side lugs (horns)", fill="#8A1515", font=self._get_font(13, bold=True))

        # Right: Corrugated Gas Mask Canister & Lederschutzmaske 17
        cx, cy = 680, 280
        # Canister Body (Galvanized metal with vertical corrugations)
        can_w, can_h = 100, 200
        draw.rectangle([cx - can_w//2, cy - can_h//2, cx + can_w//2, cy + can_h//2], fill="#4A524A", outline="#1A201A", width=3)
        # Hinged lid
        draw.rectangle([cx - can_w//2 - 6, cy - can_h//2 - 20, cx + can_w//2 + 6, cy - can_h//2], fill="#384038", outline="#1A201A", width=2)
        draw.rectangle([cx - 15, cy - can_h//2 - 2, cx + 15, cy - can_h//2 + 8], fill="#B8A468") # Latch
        # Vertical corrugation fluting
        for fx in range(cx - can_w//2 + 12, cx + can_w//2, 14):
            draw.line([(fx, cy - can_h//2 + 4), (fx, cy + can_h//2 - 4)], fill="#2E342E", width=3)
            draw.line([(fx + 2, cy - can_h//2 + 4), (fx + 2, cy + can_h//2 - 4)], fill="#687268", width=1)
        # Canvas Carrying Strap
        draw.line([(cx - can_w//2 - 2, cy - 40), (cx - 80, cy - 100), (cx + 80, cy - 100), (cx + can_w//2 + 2, cy - 40)], fill="#8C7D55", width=4)

        draw.text((cx - 120, cy + can_h//2 + 20), "TRAGBÜCHSE 17 (GAS MASK CANISTER)", fill="#182016", font=self._get_font(15, bold=True))
        draw.text((cx - 120, cy + can_h//2 + 42), "• Corrugated structural fluting ridges", fill="#384236", font=self._get_font(13))
        draw.text((cx - 120, cy + can_h//2 + 60), "• Spring catch closure and webbed strap", fill="#384236", font=self._get_font(13))

        return img

    # =========================================================================
    # PRIMARY REVIEW SHEETS RENDERING
    # =========================================================================

    def render_master_review_sheet(self, output_path: Path) -> Image.Image:
        """Renders episode01_research_grounded_visual_master.png (PRIMARY REVIEW SHEET).

        Structure:
        3-Column Layout:
        Column 1: ARCHIVAL REFERENCE (Primary source photo / plate)
        Column 2: FACT MODEL SUMMARY (Observed vs Inferred vs Prohibited)
        Column 3: FINAL RECONSTRUCTION (Project's illustrated visual asset)
        """
        W, H = 2400, 3200
        canvas = Image.new("RGB", (W, H), "#1A1A1A")
        draw = ImageDraw.Draw(canvas)

        # Header Title
        draw.text((W // 2 - 620, 30), "EPISODE 01: RESEARCH-GROUNDED VISUAL MASTER", fill="#FFFFFF", font=self._get_font(36, bold=True))
        draw.text((W // 2 - 580, 78), "FACT FIRST  →  DESIGN SECOND  →  CINEMA THIRD  →  MOTION LAST", fill="#4AE080", font=self._get_font(20, bold=True))
        draw.text((W // 2 - 480, 110), "Epistemological Separation: Archival Evidence  |  Fact Model Bible  |  Illustrated Reconstruction", fill="#AAAAAA", font=self._get_font(16))

        # Column Headers
        col_w1, col_w2, col_w3 = 700, 700, 840
        x1 = 50
        x2 = x1 + col_w1 + 30
        x3 = x2 + col_w2 + 30
        head_y = 150

        draw.rectangle([x1, head_y, x1 + col_w1, head_y + 45], fill="#2B3A4A")
        draw.text((x1 + 20, head_y + 12), "1. ARCHIVAL PRIMARY REFERENCE", fill="#FFFFFF", font=self._get_font(18, bold=True))

        draw.rectangle([x2, head_y, x2 + col_w2, head_y + 45], fill="#4A3A2B")
        draw.text((x2 + 20, head_y + 12), "2. FACT MODEL BIBLE (TRUTH RULES)", fill="#FFFFFF", font=self._get_font(18, bold=True))

        draw.rectangle([x3, head_y, x3 + col_w3, head_y + 45], fill="#2B4A33")
        draw.text((x3 + 20, head_y + 12), "3. ILLUSTRATED RECONSTRUCTION", fill="#FFFFFF", font=self._get_font(18, bold=True))

        # 5 Rows of Comparison
        # Row 1: Historical Map (Somme 1916)
        # Row 2: Location 1 (Odeonsplatz 1914)
        # Row 3: Location 2 (Somme Trench 1916)
        # Row 4: Character (Hitler 1914 Age 25)
        # Row 5: Bavarian Uniform & Stahlhelm M16
        row_h = 560
        rows = [
            (
                "ROW 1: HISTORICAL MAP — WESTERN FRONT & SOMME SECTOR (1916)",
                self.ref_dir / "maps/western_front_1914_1916_somme.png",
                [
                    "OBSERVED CARTOGRAPHIC FACTS:",
                    "• Continuous 700km front line: Nieuwpoort to Swiss border.",
                    "• Somme river courses westward past Péronne and Amiens.",
                    "• Ypres Salient eastward bulge clearly distinct from Picardy.",
                    "• Relative coordinates: Munich (SE) vs. Somme front (NW).",
                    "",
                    "PROHIBITED PROCEDURAL ERRORS:",
                    "• Zero arbitrary sinusoidal zig-zags or random straight lines.",
                    "• Zero displaced rivers or fantasy country borders.",
                ],
                self.map_pipeline.render_historical_map(output_path.parent / "temp_map_master.png"),
            ),
            (
                "ROW 2: LOCATION — MUNICH ODEONSPLATZ & FELDHERRNHALLE (1914)",
                self.ref_dir / "locations/munich_odeonsplatz_feldherrnhalle_1914.png",
                [
                    "OBSERVED ARCHITECTURAL FACTS:",
                    "• Triple Florentine round arches of Feldherrnhalle loggia.",
                    "• Bronze commander statues (Tilly & Wrede) in outer arches.",
                    "• Wide granite cobblestone plaza leading to Residenzstrasse.",
                    "• August 1914 crowd in dark Edwardian suits, bowler/boater hats.",
                    "",
                    "PROHIBITED PROCEDURAL ERRORS:",
                    "• Zero generic classical columns with flat lintels.",
                    "• Zero modern flags or post-1933 memorial plaques.",
                ],
                self.render_odeonsplatz_reconstruction(w=col_w3, h=row_h - 60),
            ),
            (
                "ROW 3: LOCATION — SOMME SUBTERRANEAN COMMUNICATION TRENCH (1916)",
                self.ref_dir / "locations/western_front_somme_trench_1916.png",
                [
                    "OBSERVED STRUCTURAL FACTS:",
                    "• Low subterranean horizon (35% canvas height).",
                    "• Split vertical pine timber revetments retaining chalk walls.",
                    "• Raised wooden duckboard walkway over drainage mud sumps.",
                    "• Sandbag parapet crest with overcast Picardy rain mist.",
                    "",
                    "PROHIBITED PROCEDURAL ERRORS:",
                    "• Zero flat surface dirt stages without vertical trench depth.",
                    "• Zero clean concrete bunkers (uncommon at frontline Somme).",
                ],
                self.render_somme_trench_reconstruction(w=col_w3, h=row_h - 60),
            ),
            (
                "ROW 4: CHARACTER — ADOLF HITLER (AGE 25, 1914 MUNICH ENLISTMENT)",
                self.ref_dir / "characters/hitler_1914_munich_civilian.png",
                [
                    "OBSERVED PHYSIOGNOMY (1914):",
                    "• Age 25 lean youth: gaunt cheeks, long jaw, sunken eyes.",
                    "• Deep left-side hair part swept across forehead.",
                    "• WIDE KAISER HANDLEBAR MUSTACHE with tapered upward tips.",
                    "",
                    "CRITICAL ERA PROHIBITIONS (1914):",
                    "• STRICTLY PROHIBITED: 1930s toothbrush mustache.",
                    "• STRICTLY PROHIBITED: Heavy middle-aged jowls or round face.",
                    "• STRICTLY PROHIBITED: NSDAP swastika armband or IC 1st Class.",
                ],
                self.render_character_turnaround(w=col_w3, h=row_h - 60),
            ),
            (
                "ROW 5: COSTUME & HERO OBJECT — BAVARIAN UNIFORM & STAHLHELM M16",
                self.ref_dir / "costumes/bavarian_infantry_feldgrau_m1907_1914.png",
                [
                    "OBSERVED ARTIFACT SPECIFICATIONS:",
                    "• Bavarian M1907/10 Feldrock wool tunic in feldgrau (#4B5344).",
                    "• Red infantry piping (collar, fly, Brandenburg cuff flaps).",
                    "• Dual cockades: Reich (crown) & Bavaria White/Blue (band).",
                    "• Stahlhelm M16: Flared neck apron & twin stirnpanzer side lugs.",
                    "• Gas Mask Canister: Galvanized corrugated vertical fluting.",
                    "",
                    "PROHIBITED ANACRONISMS:",
                    "• Zero smooth WWII M35 helmets (must have WWI side horns).",
                ],
                self.render_costume_reconstruction(w=col_w3, h=row_h - 60),
            ),
        ]

        curr_y = head_y + 55
        for title, ref_path, fact_lines, recon_img in rows:
            # Row Header
            draw.rectangle([x1, curr_y, x3 + col_w3, curr_y + 30], fill="#262626")
            draw.text((x1 + 10, curr_y + 6), title, fill="#E0D5C0", font=self._get_font(15, bold=True))
            content_y = curr_y + 35

            # Column 1: Reference Image
            draw.rectangle([x1, content_y, x1 + col_w1, content_y + row_h - 45], fill="#111111", outline="#333333", width=2)
            if ref_path.is_file():
                try:
                    ref_img = Image.open(ref_path)
                    ref_resized = ref_img.resize((col_w1 - 10, row_h - 55))
                    canvas.paste(ref_resized, (x1 + 5, content_y + 5))
                except Exception as e:
                    draw.text((x1 + 20, content_y + 50), f"Error loading ref: {e}", fill="#FF6666")

            # Column 2: Fact Model Summary Box
            draw.rectangle([x2, content_y, x2 + col_w2, content_y + row_h - 45], fill="#22201D", outline="#504535", width=2)
            ty = content_y + 16
            for line in fact_lines:
                if "PROHIBITED" in line or "CRITICAL" in line:
                    draw.text((x2 + 20, ty), line, fill="#FF6666", font=self._get_font(14, bold=True))
                elif "OBSERVED" in line:
                    draw.text((x2 + 20, ty), line, fill="#66DDAA", font=self._get_font(14, bold=True))
                elif line.startswith("•"):
                    draw.text((x2 + 25, ty), line, fill="#EAE0D0", font=self._get_font(13))
                else:
                    draw.text((x2 + 20, ty), line, fill="#C0B4A0", font=self._get_font(13))
                ty += 22

            # Column 3: Reconstruction Render
            draw.rectangle([x3, content_y, x3 + col_w3, content_y + row_h - 45], fill="#111111", outline="#206030", width=2)
            recon_resized = recon_img.resize((col_w3 - 10, row_h - 55))
            canvas.paste(recon_resized, (x3 + 5, content_y + 5))

            curr_y += row_h + 10

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, "PNG")
        return canvas

    def render_location_comparison_sheet(self, output_path: Path) -> Image.Image:
        """Renders episode01_location_reference_vs_render.png (3 Real Locations)."""
        W, H = 2000, 1800
        canvas = Image.new("RGB", (W, H), "#181818")
        draw = ImageDraw.Draw(canvas)

        draw.text((W // 2 - 480, 25), "EPISODE 01: LOCATION REFERENCE VS. ILLUSTRATED RECONSTRUCTION", fill="#FFFFFF", font=self._get_font(28, bold=True))
        draw.text((W // 2 - 400, 65), "Archival Grounding of Three Real Historical Spaces | Zero Generic Stage Assembly", fill="#AAAAAA", font=self._get_font(16))

        locs = [
            (
                "LOCATION 1: MUNICH ODEONSPLATZ & FELDHERRNHALLE (AUGUST 1914)",
                self.ref_dir / "locations/munich_odeonsplatz_feldherrnhalle_1914.png",
                self.render_odeonsplatz_reconstruction(w=940, h=480),
                "Factual Triple Florentine Arches | Edwardian Crowd | Neoclassical Perspective",
            ),
            (
                "LOCATION 2: SOMME SECOND-LINE COMMUNICATION TRENCH (OCTOBER 1916)",
                self.ref_dir / "locations/western_front_somme_trench_1916.png",
                self.render_somme_trench_reconstruction(w=940, h=480),
                "Subterranean Horizon (35%) | Vertical Split Pine Revetment | Raised Duckboard Walkway",
            ),
            (
                "LOCATION 3: PASEWALK MILITARY CONVALESCENT HOSPITAL (OCTOBER 1918)",
                self.ref_dir / "locations/pasewalk_military_hospital_1918.png",
                self.render_pasewalk_hospital_reconstruction(w=940, h=480),
                "Prussian Arched Lancet Windows | Dark Green Sanitary Wainscot | Iron Cot Perspective",
            ),
        ]

        curr_y = 110
        panel_w = 950
        panel_h = 510

        for title, ref_path, recon_img, fact_note in locs:
            draw.rectangle([40, curr_y, W - 40, curr_y + 32], fill="#262E38")
            draw.text((50, curr_y + 6), title, fill="#FFFFFF", font=self._get_font(16, bold=True))
            draw.text((W - 650, curr_y + 8), fact_note, fill="#80D090", font=self._get_font(13))

            content_y = curr_y + 38
            # Left: Archival Reference
            draw.rectangle([40, content_y, 40 + panel_w, content_y + panel_h], fill="#0A0A0A", outline="#444444", width=2)
            draw.rectangle([45, content_y + 5, 45 + 260, content_y + 35], fill="#8A1515")
            draw.text((55, content_y + 11), "ARCHIVAL REFERENCE", fill="#FFFFFF", font=self._get_font(14, bold=True))
            if ref_path.is_file():
                ref_img = Image.open(ref_path).resize((panel_w - 10, panel_h - 45))
                canvas.paste(ref_img, (45, content_y + 40))

            # Right: Reconstruction
            rx = W - panel_w - 40
            draw.rectangle([rx, content_y, rx + panel_w, content_y + panel_h], fill="#0A0A0A", outline="#207030", width=2)
            draw.rectangle([rx + 5, content_y + 5, rx + 5 + 320, content_y + 35], fill="#156025")
            draw.text((rx + 15, content_y + 11), "ILLUSTRATED RECONSTRUCTION", fill="#FFFFFF", font=self._get_font(14, bold=True))
            canvas.paste(recon_img.resize((panel_w - 10, panel_h - 45)), (rx + 5, content_y + 40))

            curr_y += panel_h + 50

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, "PNG")
        return canvas

    def render_character_comparison_sheet(self, output_path: Path) -> Image.Image:
        """Renders episode01_character_reference_vs_stickman.png."""
        W, H = 1920, 1080
        canvas = Image.new("RGB", (W, H), "#1A1A1A")
        draw = ImageDraw.Draw(canvas)

        draw.text((W // 2 - 460, 20), "EPISODE 01: CHARACTER REFERENCE VS. STICKMAN TURNAROUND", fill="#FFFFFF", font=self._get_font(28, bold=True))
        draw.text((W // 2 - 400, 60), "Adolf Hitler (1914 Munich Civilian, Age 25) | Historical Fact Model Integration", fill="#AAAAAA", font=self._get_font(16))

        panel_w = 900
        panel_h = 920
        panel_y = 110

        # Left: Archival Reference & Fact Model Audit
        left_x = 40
        draw.rectangle([left_x, panel_y, left_x + panel_w, panel_y + panel_h], fill="#22201D", outline="#504535", width=3)
        draw.rectangle([left_x + 10, panel_y + 10, left_x + panel_w - 10, panel_y + 50], fill="#8A1515")
        draw.text((left_x + 20, panel_y + 18), "ARCHIVAL REFERENCE & HISTORICAL EVIDENCE (1914)", fill="#FFFFFF", font=self._get_font(18, bold=True))

        ref_path = self.ref_dir / "characters/hitler_1914_munich_civilian.png"
        if ref_path.is_file():
            ref_img = Image.open(ref_path).resize((panel_w - 20, 480))
            canvas.paste(ref_img, (left_x + 10, panel_y + 60))

        # Fact Model Callouts Box below photo
        box_y = panel_y + 550
        draw.rectangle([left_x + 20, box_y, left_x + panel_w - 20, panel_y + panel_h - 20], fill="#151412", outline="#8C7355", width=2)
        draw.text((left_x + 35, box_y + 16), "CHARACTER FACT MODEL TRUTH RULES (FACT_CHAR_HITLER_1914):", fill="#E0C080", font=self._get_font(16, bold=True))
        draw.text((left_x + 35, box_y + 46), "• EXACT AGE: 25 years old (August 1914 Munich mobilization).", fill="#FFFFFF", font=self._get_font(14))
        draw.text((left_x + 35, box_y + 70), "• PHYSIOGNOMY: Gaunt, sunken cheeks, sharp angular jaw, intense deep-set blue-grey eyes.", fill="#FFFFFF", font=self._get_font(14))
        draw.text((left_x + 35, box_y + 94), "• HAIR: Dark brown hair parted deeply on the left, swept back across forehead.", fill="#FFFFFF", font=self._get_font(14))
        draw.text((left_x + 35, box_y + 118), "• MUSTACHE: Wide Kaiser Wilhelm-style handlebar mustache extending past lips.", fill="#55FF55", font=self._get_font(14, bold=True))
        draw.text((left_x + 35, box_y + 150), "ANACHRONISM WARNING (PROHIBITED IN 1914):", fill="#FF5555", font=self._get_font(15, bold=True))
        draw.text((left_x + 35, box_y + 176), "• NO 1930s 'toothbrush' mustache (Hitler only trimmed mustache in 1916 for gas mask fit).", fill="#FF8888", font=self._get_font(13))
        draw.text((left_x + 35, box_y + 200), "• NO middle-aged jowls, round face, or Nazi party badges.", fill="#FF8888", font=self._get_font(13))

        # Right: Stickman Turnaround Reconstruction
        right_x = W - panel_w - 40
        draw.rectangle([right_x, panel_y, right_x + panel_w, panel_y + panel_h], fill="#0A0A0A", outline="#207030", width=3)
        draw.rectangle([right_x + 10, panel_y + 10, right_x + panel_w - 10, panel_y + 50], fill="#156025")
        draw.text((right_x + 20, panel_y + 18), "STICKMAN TURNAROUND RECONSTRUCTION (FRONT / 3-QUARTER / PROFILE)", fill="#FFFFFF", font=self._get_font(18, bold=True))

        turnaround = self.render_character_turnaround(w=panel_w - 20, h=panel_h - 70)
        canvas.paste(turnaround, (right_x + 10, panel_y + 60))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, "PNG")
        return canvas

    def render_costume_comparison_sheet(self, output_path: Path) -> Image.Image:
        """Renders episode01_costume_reference_vs_render.png."""
        W, H = 1920, 1080
        canvas = Image.new("RGB", (W, H), "#1A1A1A")
        draw = ImageDraw.Draw(canvas)

        draw.text((W // 2 - 460, 20), "EPISODE 01: COSTUME REFERENCE VS. RECONSTRUCTION", fill="#FFFFFF", font=self._get_font(28, bold=True))
        draw.text((W // 2 - 420, 60), "Royal Bavarian 16th RIR (List) M1907/10 Feldrock | Bavarian Regulation Compliance", fill="#AAAAAA", font=self._get_font(16))

        panel_w = 900
        panel_h = 920
        panel_y = 110

        # Left: Archival Reference
        left_x = 40
        draw.rectangle([left_x, panel_y, left_x + panel_w, panel_y + panel_h], fill="#22201D", outline="#504535", width=3)
        draw.rectangle([left_x + 10, panel_y + 10, left_x + panel_w - 10, panel_y + 50], fill="#8A1515")
        draw.text((left_x + 20, panel_y + 18), "ARCHIVAL REGULATION UNIFORM PLATE (1914)", fill="#FFFFFF", font=self._get_font(18, bold=True))

        ref_path = self.ref_dir / "costumes/bavarian_infantry_feldgrau_m1907_1914.png"
        if ref_path.is_file():
            ref_img = Image.open(ref_path).resize((panel_w - 20, panel_h - 70))
            canvas.paste(ref_img, (left_x + 10, panel_y + 60))

        # Right: Reconstruction
        right_x = W - panel_w - 40
        draw.rectangle([right_x, panel_y, right_x + panel_w, panel_y + panel_h], fill="#0A0A0A", outline="#207030", width=3)
        draw.rectangle([right_x + 10, panel_y + 10, right_x + panel_w - 10, panel_y + 50], fill="#156025")
        draw.text((right_x + 20, panel_y + 18), "ILLUSTRATED COSTUME & INSIGNIA RECONSTRUCTION", fill="#FFFFFF", font=self._get_font(18, bold=True))

        recon_img = self.render_costume_reconstruction(w=panel_w - 20, h=panel_h - 70)
        canvas.paste(recon_img, (right_x + 10, panel_y + 60))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, "PNG")
        return canvas

    def render_hero_object_comparison_sheet(self, output_path: Path) -> Image.Image:
        """Renders episode01_hero_object_reference_vs_render.png."""
        W, H = 1920, 1080
        canvas = Image.new("RGB", (W, H), "#1A1A1A")
        draw = ImageDraw.Draw(canvas)

        draw.text((W // 2 - 460, 20), "EPISODE 01: HERO OBJECT REFERENCE VS. RECONSTRUCTION", fill="#FFFFFF", font=self._get_font(28, bold=True))
        draw.text((W // 2 - 400, 60), "German Stahlhelm M16 & Gas Mask Canister | Museum Specimen Grounding", fill="#AAAAAA", font=self._get_font(16))

        panel_w = 900
        panel_h = 920
        panel_y = 110

        # Left: Archival Reference
        left_x = 40
        draw.rectangle([left_x, panel_y, left_x + panel_w, panel_y + panel_h], fill="#22201D", outline="#504535", width=3)
        draw.rectangle([left_x + 10, panel_y + 10, left_x + panel_w - 10, panel_y + 50], fill="#8A1515")
        draw.text((left_x + 20, panel_y + 18), "MUSEUM ARTIFACT SPECIMENS (DHM / IWM 1916)", fill="#FFFFFF", font=self._get_font(18, bold=True))

        ref_path = self.ref_dir / "objects/stahlhelm_m16_gasmask_canister.png"
        if ref_path.is_file():
            ref_img = Image.open(ref_path).resize((panel_w - 20, panel_h - 70))
            canvas.paste(ref_img, (left_x + 10, panel_y + 60))

        # Right: Reconstruction
        right_x = W - panel_w - 40
        draw.rectangle([right_x, panel_y, right_x + panel_w, panel_y + panel_h], fill="#0A0A0A", outline="#207030", width=3)
        draw.rectangle([right_x + 10, panel_y + 10, right_x + panel_w - 10, panel_y + 50], fill="#156025")
        draw.text((right_x + 20, panel_y + 18), "ILLUSTRATED WEAPON & GEAR RECONSTRUCTION", fill="#FFFFFF", font=self._get_font(18, bold=True))

        recon_img = self.render_hero_object_reconstruction(w=panel_w - 20, h=panel_h - 70)
        canvas.paste(recon_img, (right_x + 10, panel_y + 60))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, "PNG")
        return canvas

    def render_all_deliverables(self) -> dict[str, Path]:
        """Renders all primary visual sheets and reference sheets."""
        results = {}

        # 1. Primary Review Sheet
        p1 = self.out_dir / "episode01_research_grounded_visual_master.png"
        self.render_master_review_sheet(p1)
        results["master_review_sheet"] = p1

        # 2. Historical Map Proof
        p2 = self.out_dir / "episode01_historical_map_proof.png"
        self.map_pipeline.render_historical_map(p2)
        results["map_proof"] = p2

        # 3. Map Generic vs Researched
        p3 = self.out_dir / "episode01_map_generic_vs_researched.png"
        self.map_pipeline.render_generic_vs_researched_comparison(p3)
        results["map_comparison"] = p3

        # 4. Location Reference vs Render
        p4 = self.out_dir / "episode01_location_reference_vs_render.png"
        self.render_location_comparison_sheet(p4)
        results["location_comparison"] = p4

        # 5. Character Reference vs Stickman
        p5 = self.out_dir / "episode01_character_reference_vs_stickman.png"
        self.render_character_comparison_sheet(p5)
        results["character_comparison"] = p5

        # 6. Costume Reference vs Render
        p6 = self.out_dir / "episode01_costume_reference_vs_render.png"
        self.render_costume_comparison_sheet(p6)
        results["costume_comparison"] = p6

        # 7. Hero Object Reference vs Render
        p7 = self.out_dir / "episode01_hero_object_reference_vs_render.png"
        self.render_hero_object_comparison_sheet(p7)
        results["hero_object_comparison"] = p7

        # Reference sheets (copies from curated reference plates)
        for name, src_rel in [
            ("episode01_map_reference_sheet.png", "maps/western_front_1914_1916_somme.png"),
            ("episode01_character_reference_sheet.png", "characters/hitler_1914_munich_civilian.png"),
            ("episode01_location_reference_sheet.png", "locations/munich_odeonsplatz_feldherrnhalle_1914.png"),
        ]:
            src_p = self.ref_dir / src_rel
            dst_p = self.out_dir / name
            if src_p.is_file():
                img = Image.open(src_p)
                img.save(dst_p, "PNG")
                results[name] = dst_p

        return results
