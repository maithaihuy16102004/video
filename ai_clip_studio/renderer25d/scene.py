"""Scene model for the 2.5D fallback renderer.

A scene is data, not a story: a ground plane, solid boxes (buildings,
furniture, props — each a real 3D box with a centre, a size and a
material colour), point/directional lights, and character anchors.
A character anchor is a WORLD position + a height + an optional draw
callback; the renderer only draws a neutral billboard marker for it
unless a character engine is plugged in — character ART lives in
``ai_clip_studio/animation/character_art.py`` (another agent's file)
and is deliberately not re-implemented here.

Depth layers are assigned from the camera, not from a vignette:
``depth_layers()`` buckets every object by its camera depth into
foreground / midground / background, so a camera move re-buckets
objects honestly. The renderer draws far-to-near (painter's order).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .camera import PerspectiveCamera
from .lighting import DirectionalLight, LightRig, PointLight

Vec3 = tuple[float, float, float]

LAYERS = ("background", "midground", "foreground")


@dataclass
class Box3D:
    """A solid axis-aligned box in the world (building, table, prop).

    ``label`` (v7): optional text drawn on the box's front face
    (+z, facing the camera) -- e.g. a bus-stop sign reading
    "TRẠM XE BUÝT". A sign with no text is a blank dark rectangle;
    the v6 motion test's sign was exactly that, which is why the
    location read as generic boxes. Empty label = no text.
    """
    center: Vec3
    size: Vec3  # (width x, height y, depth z) in world units
    color: tuple[int, int, int] = (120, 110, 100)
    name: str = "box"
    label: str = ""

    def corners(self) -> list[Vec3]:
        cx, cy, cz = self.center
        sx, sy, sz = self.size[0] / 2, self.size[1] / 2, self.size[2] / 2
        return [(cx + dx, cy + dy, cz + dz)
                for dx in (-sx, sx) for dy in (-sy, sy) for dz in (-sz, sz)]

    def ground_pos(self) -> Vec3:
        return (self.center[0], 0.0, self.center[2])

    def height_above_ground(self) -> float:
        return max(0.0, self.center[1] - self.size[1] / 2)

    def base_radius(self) -> float:
        return max(self.size[0], self.size[2]) * 0.55

    def is_flat_ground_slab(self) -> bool:
        """True for a thin slab lying flush ON the ground (a path strip,
        a kerb): it rests on the ground plane and is too thin to cast
        a visible contact shadow of its own. Such a slab must never
        get a contact-shadow ellipse: its footprint is huge (a 14-unit
        path has base_radius 7.7), and the projected ellipse covers
        the whole frame including the sky (Stage 3 dark-daytime bug:
        two slab shadows at alpha 0.55 composited to ~80% darkening
        over a day sky). A raised thin box (a railing bar, an awning)
        is NOT a slab: it hangs above the ground and keeps its shadow.
        """
        return (self.height_above_ground() == 0.0
                and self.size[1] <= 0.2)


# Faces of a box: (corner indices into corners(), outward normal).
# corners() order: dx in (-,+), dy in (-,+), dz in (-,+) -> index =
# (dx_i * 4 + dy_i * 2 + dz_i).
BOX_FACES = [
    ([0, 2, 6, 4], (0.0, 0.0, -1.0)),   # back  (-z)
    ([1, 3, 7, 5], (0.0, 0.0, 1.0)),    # front (+z, faces the camera)
    ([0, 1, 3, 2], (-1.0, 0.0, 0.0)),   # left  (-x)
    ([4, 6, 7, 5], (1.0, 0.0, 0.0)),    # right (+x)
    ([2, 3, 7, 6], (0.0, 1.0, 0.0)),    # top   (+y)
    ([0, 4, 5, 1], (0.0, -1.0, 0.0)),   # bottom(-y, never drawn)
]


@dataclass
class CharacterAnchor:
    """Where a 2D/2.5D character stands in the 3D world.

    ``world_pos`` is the FEET position (y = ground height, usually 0).
    ``height`` is the character's world height; the renderer projects
    feet and head and draws the billboard between them. ``label`` is
    only for debug frames, never a story name in the engine itself.
    """
    world_pos: Vec3
    height: float = 1.7
    label: str = "character"


@dataclass
class Scene25D:
    """Everything a frame needs: world + lights + camera."""
    boxes: list[Box3D] = field(default_factory=list)
    characters: list[CharacterAnchor] = field(default_factory=list)
    lights: LightRig = field(default_factory=LightRig)
    camera: PerspectiveCamera = field(default_factory=PerspectiveCamera)
    sky_top: tuple[int, int, int] = (16, 28, 52)
    sky_bottom: tuple[int, int, int] = (58, 84, 124)
    ground_color: tuple[int, int, int] = (38, 38, 44)
    ground_extent: float = 30.0  # ground plane half-size in world units

    def depth_layers(self) -> dict[str, list]:
        """Bucket boxes + characters by camera depth.

        Thresholds are relative to the camera's own depth range in this
        scene, so the same world re-buckets when the camera moves.
        Returns {"background": [...], "midground": [...], "foreground":
        [...]} with items as (kind, object, depth).
        """
        items = []
        for b in self.boxes:
            items.append(("box", b, self.camera.depth_of(b.center)))
        for c in self.characters:
            items.append(("character", c, self.camera.depth_of(c.world_pos)))
        if not items:
            return {layer: [] for layer in LAYERS}
        depths = sorted(d for _, _, d in items)
        lo, hi = depths[0], depths[-1]
        span = max(hi - lo, 1e-6)
        out: dict[str, list] = {layer: [] for layer in LAYERS}
        for kind, obj, d in items:
            frac = (d - lo) / span  # 0 = nearest, 1 = farthest
            layer = ("foreground" if frac < 0.33 else
                     "midground" if frac < 0.66 else "background")
            out[layer].append((kind, obj, d))
        return out

    def to_dict(self) -> dict:
        return {
            "boxes": [{"name": b.name, "center": list(b.center),
                       "size": list(b.size), "color": list(b.color)}
                      for b in self.boxes],
            "characters": [{"label": c.label, "world_pos": list(c.world_pos),
                            "height": c.height} for c in self.characters],
            "camera": self.camera.to_dict(),
            "sky_top": list(self.sky_top),
            "sky_bottom": list(self.sky_bottom),
        }
