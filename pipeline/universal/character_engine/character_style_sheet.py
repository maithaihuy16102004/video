"""Character Style Test Sheet Generator.

Renders a comprehensive visual proof sheet showing:
- 5 different characters (Protagonist, Soldier, Officer, Doctor, Companion)
- 5 different hairstyles
- 5 different costumes / contexts
- 5 different expressions & orientations (Front, 3/4, Profile, Back)
- Proves the system is completely data-driven and not optimized for one historical person.
"""
from __future__ import annotations

from pathlib import Path
import cairo

from .illustrated_stickman_renderer import IllustratedStickmanRenderer
from ..schemas import (
    ActorBlock,
    BodyDNA,
    CharacterDNA,
    CostumeDNA,
    CostumeVariant,
    FaceDNA,
    HairStyleDNA,
    PerformanceDNA,
    ResolvedCharacter,
)


def generate_character_style_sheet(output_path: Path, width: int = 1920, height: int = 1080) -> Path:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surf)

    # 1. Warm editorial paper background
    ctx.set_source_rgb(0.94, 0.93, 0.90)
    ctx.rectangle(0, 0, width, height)
    ctx.fill()

    # Subtle grid lines
    ctx.set_source_rgba(0.2, 0.2, 0.2, 0.06)
    ctx.set_line_width(1.0)
    for y in range(0, height, 60):
        ctx.move_to(0, y)
        ctx.line_to(width, y)
        ctx.stroke()
    for x in range(0, width, 60):
        ctx.move_to(x, 0)
        ctx.line_to(x, height)
        ctx.stroke()

    # Header banner
    ctx.set_source_rgb(0.12, 0.12, 0.14)
    ctx.rectangle(0, 0, width, 90)
    ctx.fill()

    ctx.select_font_face("Georgia", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(32.0)
    ctx.set_source_rgb(0.96, 0.94, 0.88)
    ctx.move_to(45, 55)
    ctx.show_text("PROJECT-WIDE ART DIRECTION: ILLUSTRATED STICKMAN ENGINE")

    ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(16.0)
    ctx.set_source_rgb(0.72, 0.74, 0.78)
    ctx.move_to(1120, 55)
    ctx.show_text("Universal CharacterDNA -> Same Parametric Renderer -> Varied Identity")

    # Define 5 test characters across different roles, periods, and looks
    test_specs = [
        {
            "name": "Historical Protagonist (1914)",
            "role": "HERO",
            "orient": "FRONT",
            "action": "STAND",
            "emotion": "DETERMINED",
            "hair": HairStyleDNA(shape="SWEPT_SIDE", part="LEFT", fringe="SIDE_SWEEP", color="#2a221b"),
            "face": FaceDNA(jaw_shape="SQUARE", brow_shape="ARCHED", nose_style="POINTED", skin_tone="#edd8be"),
            "costume": CostumeDNA(headwear="NONE", upper_garment="JACKET", lower_garment="TROUSERS",
                                  palette={"primary": "#3e4856", "secondary": "#242830", "accent": "#b88a44", "trim": "#111418"}),
            "sub": "Side-swept hair, square jaw, tailored jacket",
        },
        {
            "name": "Frontline Soldier (1916)",
            "role": "SUPPORT",
            "orient": "THREE_QUARTER_RIGHT",
            "action": "DUCK",
            "emotion": "AFRAID",
            "hair": HairStyleDNA(shape="CROPPED", part="NONE", color="#38281e"),
            "face": FaceDNA(jaw_shape="ROUND", brow_shape="FLAT", skin_tone="#decaae"),
            "costume": CostumeDNA(headwear="STEEL_HELMET", upper_garment="MILITARY_TUNIC", lower_garment="TROUSERS",
                                  palette={"primary": "#485244", "secondary": "#32382e", "accent": "#727a68", "trim": "#181a16"}),
            "sub": "Steel helmet, defensive crouch, Feldgrau tunic",
        },
        {
            "name": "Convalescent Patient (1918)",
            "role": "SUPPORT",
            "orient": "PROFILE_RIGHT",
            "action": "STAND",
            "emotion": "EXHAUSTED",
            "hair": HairStyleDNA(shape="FLAT_COMB", color="#241e1a"),
            "face": FaceDNA(jaw_shape="LONG", skin_tone="#f0e2d0"),
            "conditions": ["EYE_BANDAGE"],
            "costume": CostumeDNA(headwear="NONE", upper_garment="HOSPITAL_GOWN", lower_garment="TROUSERS",
                                  palette={"primary": "#62707c", "secondary": "#424a52", "accent": "#8ca0b2", "trim": "#22262a"}),
            "sub": "Medical eye bandage, convalescent posture",
        },
        {
            "name": "Senior Military Officer (1914)",
            "role": "SUPPORT",
            "orient": "THREE_QUARTER_LEFT",
            "action": "POINT",
            "emotion": "ANGRY",
            "hair": HairStyleDNA(shape="CROPPED", color="#4a423a"),
            "face": FaceDNA(jaw_shape="SQUARE", facial_hair="MUSTACHE_THICK", skin_tone="#e4cbb0"),
            "costume": CostumeDNA(headwear="PEAKED_CAP", upper_garment="MILITARY_TUNIC", lower_garment="BREECHES",
                                  palette={"primary": "#364032", "secondary": "#222a1e", "accent": "#c69248", "trim": "#0e120c"}),
            "sub": "Peaked cap, thick mustache, pointing command",
        },
        {
            "name": "Laboratory Scientist (Generic 1890)",
            "role": "HERO",
            "orient": "THREE_QUARTER_RIGHT",
            "action": "OPERATE",
            "emotion": "ATTENTIVE",
            "hair": HairStyleDNA(shape="CURLY", volume=0.8, color="#5a4232"),
            "face": FaceDNA(jaw_shape="POINTED", distinctive_anchors=["SPECTACLES_ROUND"], skin_tone="#eddcc6"),
            "costume": CostumeDNA(headwear="NONE", upper_garment="SHIRT", outerwear="LAB_COAT", lower_garment="TROUSERS",
                                  palette={"primary": "#dedad2", "secondary": "#424650", "accent": "#9a6838", "trim": "#1c1e22"}),
            "sub": "Curly hair, round spectacles, operating stance",
        },
    ]

    renderer = IllustratedStickmanRenderer()
    col_w = width / len(test_specs)
    ground_y = height * 0.78

    for idx, spec in enumerate(test_specs):
        cx = (idx + 0.5) * col_w

        # Column background card
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.65)
        ctx.rectangle(cx - col_w * 0.46, 120, col_w * 0.92, height - 160)
        ctx.fill_preserve()
        ctx.set_source_rgba(0.1, 0.1, 0.12, 0.20)
        ctx.set_line_width(1.5)
        ctx.stroke()

        # Labels
        ctx.select_font_face("Georgia", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(17.0)
        ctx.set_source_rgb(0.12, 0.14, 0.18)
        ctx.move_to(cx - col_w * 0.42, 160)
        ctx.show_text(spec["name"])

        ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        ctx.set_font_size(13.0)
        ctx.set_source_rgb(0.38, 0.42, 0.48)
        ctx.move_to(cx - col_w * 0.42, 185)
        ctx.show_text(f"Action: {spec['action']} | Mood: {spec['emotion']}")

        # Character construction
        resolved = ResolvedCharacter(
            character_id=f"CHAR_TEST_{idx+1}",
            variant_id="V_TEST",
            costume_id="C_TEST",
            age=30,
            hair=spec["hair"],
            face=spec["face"],
            body=BodyDNA(),
            costume=spec["costume"],
            conditions=spec.get("conditions", []),
            performance=PerformanceDNA(),
        )

        actor = ActorBlock(
            character_id=resolved.character_id,
            detail_level=spec["role"],
            action=spec["action"],
            emotion=spec["emotion"],
            orientation=spec["orient"],
            screen_x=cx / width,
            depth=0.3,
            depth_plane="MG",
        )

        # Render character
        renderer.render_character(
            ctx=ctx,
            char=resolved,
            actor=actor,
            screen_x=cx,
            ground_y=ground_y,
            scale=1.12,
            lighting_dx=1.0 if idx % 2 == 0 else -1.0,
        )

        # Subtitle caption
        ctx.select_font_face("Arial", cairo.FONT_SLANT_ITALIC, cairo.FONT_WEIGHT_NORMAL)
        ctx.set_font_size(13.0)
        ctx.set_source_rgb(0.42, 0.38, 0.32)
        ctx.move_to(cx - col_w * 0.42, height - 70)
        ctx.show_text(spec["sub"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    surf.write_to_png(str(output_path))
    return output_path
