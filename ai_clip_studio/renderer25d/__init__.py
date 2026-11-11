"""2.5D fallback renderer: real perspective projection in pure Python.

Public surface: :class:`renderer25d.camera.PerspectiveCamera`,
:class:`renderer25d.scene.Scene25D`, :class:`renderer25d.lighting.LightRig`,
:func:`renderer25d.render.render_frame`.
"""
from .camera import PerspectiveCamera
from .lighting import DirectionalLight, LightRig, PointLight, contact_shadow, shade
from .render import render_frame, render_proof_frames
from .scene import Box3D, CharacterAnchor, Scene25D

__all__ = [
    "PerspectiveCamera", "Scene25D", "Box3D", "CharacterAnchor",
    "LightRig", "DirectionalLight", "PointLight", "contact_shadow", "shade",
    "render_frame", "render_proof_frames",
]
