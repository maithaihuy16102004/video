"""Shared animation primitives for AI Clip Studio.

Canonical home of the V51 12-joint stickman rig (copied from the frozen
test render in ~/workspace/acceptance_loop/v4/rig.py, which stays untouched
so the v4 evidence remains reproducible). New work should import from here.
"""
from .rig import (  # noqa: F401
    Stickman, walk_pose, interp_keys, smoothstep, lerp,
    HEAD_RATIO, HEAD_RATIO_MIN, HEAD_RATIO_MAX, BODY_WIDTH_SCALE,
    bone_lengths, check_bone_lengths, check_foot_contact,
    check_hand_contact, validate_joints, plant_feet, head_track,
    interp_pose, pose_at,
)
from .primitives import compile_actions, PRIMITIVES  # noqa: F401
from .character_art import (  # noqa: F401
    CHARACTER_STYLE, STYLE_VERSION, STYLE_LOCK, PALETTE_V51,
    VIEWS, EXPRESSIONS, EXPRESSION_NAMES,
    TEMPLATES, BODY_VARIANTS, CHARACTER_INSTANCES,
    make_character, make_character_instance,
    blend_expressions, expression_at,
    draw_character_v4, draw_character_v3, draw_character,
    limb_width, outline_width,
)

__all__ = ["Stickman", "walk_pose", "interp_keys", "smoothstep", "lerp",
           "HEAD_RATIO", "HEAD_RATIO_MIN", "HEAD_RATIO_MAX",
           "BODY_WIDTH_SCALE",
           "bone_lengths", "check_bone_lengths", "check_foot_contact",
           "check_hand_contact", "validate_joints", "plant_feet",
           "head_track", "interp_pose", "pose_at",
           "compile_actions", "PRIMITIVES",
           "CHARACTER_STYLE", "STYLE_VERSION", "STYLE_LOCK", "PALETTE_V51",
           "VIEWS", "EXPRESSIONS", "EXPRESSION_NAMES",
           "TEMPLATES", "BODY_VARIANTS", "CHARACTER_INSTANCES",
           "make_character", "make_character_instance",
           "blend_expressions", "expression_at",
           "draw_character_v4", "draw_character_v3", "draw_character",
           "limb_width", "outline_width"]
