"""Real light + shadow for the 2.5D fallback renderer.

Two things the old flat renderer faked with a vignette are computed
here from geometry:

* **Light falloff.** A point light's irradiance at a surface falls with
  distance (``1 / (1 + k*d^2)``) and with the angle between the surface
  normal and the light direction (Lambert cosine). A directional light
  (sun/moon) has no distance falloff but keeps the cosine term, so
  faces turned away from the light are genuinely darker. ``shade()``
  turns a base RGB colour and a surface point+normal into the lit RGB.

* **Contact shadows.** A shadow is NOT a fixed dark blob under an
  object. It is cast from the object's ground position along the
  directional light's ground-projected direction, and its offset,
  spread and darkness all depend on the object's HEIGHT above the
  ground: a lifted object casts a shadow that is further away, larger
  (more scattered) and lighter than the same object resting on the
  ground. ``contact_shadow()`` returns exactly that, and the renderer
  draws it as a blurred ellipse — so when an object moves or jumps,
  its shadow moves with it, in the direction the light dictates.

The Motion Canvas + Three.js renderer does the same physics with a
real shadow map (see ``motioncanvas25d/World25D.ts``); this module is
the analytic 2D-projection equivalent, and the capability matrix in
``ai_clip_studio/renderer25d/README.md`` says so honestly.
"""
from __future__ import annotations

import math

Vec3 = tuple[float, float, float]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: Vec3) -> Vec3:
    n = math.sqrt(_dot(a, a))
    if n == 0:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


class PointLight:
    """A light with a real position in the world (lamp, lantern, ...)."""

    def __init__(self, position: Vec3, intensity: float = 1.0,
                 falloff_k: float = 0.08,
                 color: tuple[int, int, int] = (255, 220, 160)):
        self.position = tuple(float(v) for v in position)
        self.intensity = float(intensity)
        self.falloff_k = float(falloff_k)
        self.color = tuple(int(c) for c in color)

    def irradiance(self, point: Vec3, normal: Vec3) -> float:
        to_light = _sub(self.position, tuple(float(v) for v in point))
        dist = math.sqrt(_dot(to_light, to_light))
        if dist == 0:
            return self.intensity
        cos = max(0.0, _dot(_norm(to_light), _norm(normal)))
        return self.intensity * cos / (1.0 + self.falloff_k * dist * dist)


class DirectionalLight:
    """A far light (sun / moon / street-light wash): direction only.

    ``direction`` is the direction the light TRAVELS (from the light
    towards the scene), e.g. (0.3, -1.0, 0.2) means "from up-left-front,
    shining down". No distance falloff; faces get the cosine term.
    """

    def __init__(self, direction: Vec3, intensity: float = 1.0,
                 color: tuple[int, int, int] = (255, 244, 214)):
        self.direction = _norm(tuple(float(v) for v in direction))
        self.intensity = float(intensity)
        self.color = tuple(int(c) for c in color)

    def irradiance(self, point: Vec3, normal: Vec3) -> float:  # noqa: ARG002
        cos = max(0.0, _dot(tuple(-d for d in self.direction), _norm(normal)))
        return self.intensity * cos

    def ground_direction(self) -> tuple[float, float]:
        """Unit (x, z) direction the shadow is cast along on the ground."""
        gx, gz = self.direction[0], self.direction[2]
        n = math.hypot(gx, gz)
        if n < 1e-6:  # light straight down: shadow stays under the object
            return (0.0, 0.0)
        return (gx / n, gz / n)

    def elevation_factor(self) -> float:
        """How steeply the light comes down: 1 = straight down, 0 = level.
        A low sun casts a long shadow; a high sun casts a short one."""
        return max(0.0, -self.direction[1])


class LightRig:
    """Ambient + one directional (key) light + any number of point lights."""

    def __init__(self, ambient: float = 0.25,
                 key: DirectionalLight | None = None,
                 points: list[PointLight] | None = None):
        self.ambient = float(ambient)
        # Default key light comes from the CAMERA side, slightly above:
        # direction of travel (-z) means front faces (+z normal) are lit.
        self.key = key or DirectionalLight((0.35, -1.0, -0.3), 1.0)
        self.points = list(points or [])

    def irradiance(self, point: Vec3, normal: Vec3) -> float:
        total = self.ambient
        total += self.key.irradiance(point, normal)
        for p in self.points:
            total += p.irradiance(point, normal)
        return total


def shade(base_rgb: tuple[int, int, int], irradiance: float) -> tuple[int, int, int]:
    """Apply an irradiance value (0..~2) to a base colour, clamped."""
    f = _clamp01(irradiance)
    return tuple(min(255, max(0, int(round(c * f)))) for c in base_rgb)


def contact_shadow(object_ground_pos: Vec3, height_above_ground: float,
                   base_radius: float,
                   light: DirectionalLight) -> dict:
    """Shadow of an object standing ``height_above_ground`` above y=0.

    Returns the shadow's ground centre (x, z), its ellipse radii and its
    alpha (0..1). Rules, all from the light geometry:

    * offset along the light's ground direction grows with height and
      with how low the light is: ``height * (1 - elevation) / elevation``;
    * the ellipse grows (light scatters) with height: ``radius * (1 +
      0.35 * height)``;
    * the shadow gets lighter with height: ``alpha 0.55 -> 0.18``.
    A resting object (height 0) has a tight dark shadow right under it.
    """
    gx, gz = light.ground_direction()
    elev = max(0.15, light.elevation_factor())
    spread = (1.0 - elev) / elev  # low sun -> long shadow
    offset = float(height_above_ground) * spread
    cx = float(object_ground_pos[0]) + gx * offset
    cz = float(object_ground_pos[2]) + gz * offset
    grow = 1.0 + 0.35 * float(height_above_ground)
    alpha = 0.55 * math.exp(-0.55 * float(height_above_ground))
    return {"center": (cx, cz),
            "radius_x": float(base_radius) * grow,
            "radius_z": float(base_radius) * 0.62 * grow,
            "alpha": round(max(0.10, alpha), 3),
            "offset_world": round(offset, 3)}
