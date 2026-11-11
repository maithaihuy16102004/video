"""Shared animation primitives for AI Clip Studio.

Canonical home of the V51 12-joint stickman rig (copied from the frozen
test render in ~/workspace/acceptance_loop/v4/rig.py, which stays untouched
so the v4 evidence remains reproducible). New work should import from here.
"""
from .rig import Stickman, walk_pose, interp_keys, smoothstep, lerp  # noqa: F401
from .primitives import compile_actions, PRIMITIVES  # noqa: F401

__all__ = ["Stickman", "walk_pose", "interp_keys", "smoothstep", "lerp",
           "compile_actions", "PRIMITIVES"]
