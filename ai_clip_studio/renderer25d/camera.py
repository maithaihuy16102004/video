"""Real 2.5D perspective camera for the frame-by-frame fallback renderer.

This is NOT the old flat PIL renderer (crop/zoom + vignette). Every
screen position here is computed from a real 3D world coordinate
(x, y, z) through a perspective camera: focal length from the vertical
field of view, a look-at view basis, and perspective division by depth.
Consequences that the tests prove, not just claim:

* the same object placed at a larger depth projects smaller and higher
  (towards the horizon) than at a smaller depth;
* when the camera moves sideways, near layers shift across the screen
  faster than far layers (parallax) — the shift is exactly ``f * dx *
  (1/z_near - 1/z_far)`` in the linearised form, and the projection
  itself is what the renderer uses, not a faked per-layer multiplier;
* an object behind the camera (depth <= near plane) is reported as
  not visible instead of being drawn mirrored or garbage.

Coordinate convention (matches the Motion Canvas / Three.js side,
``motioncanvas25d/World25D.ts``): y is up, ground is the y=0 plane,
+z points TOWARDS the default camera, -z is into the scene (far).
Camera looks from ``position`` towards ``target``; ``up`` is +y.
"""
from __future__ import annotations

import math

Vec3 = tuple[float, float, float]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec3) -> Vec3:
    n = math.sqrt(_dot(a, a))
    if n == 0:
        raise ValueError("zero-length vector has no direction")
    return (a[0] / n, a[1] / n, a[2] / n)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class PerspectiveCamera:
    """A pinhole perspective camera in a 3D world.

    ``fov_deg`` is the VERTICAL field of view. ``aspect`` is width/height.
    ``near`` is the closest visible depth; anything at or behind it is
    not projectable.
    """

    def __init__(self, position: Vec3 = (0.0, 2.4, 12.0),
                 target: Vec3 = (0.0, 1.5, 0.0),
                 fov_deg: float = 46.0, aspect: float = 16 / 9,
                 near: float = 0.1, far: float = 100.0,
                 up: Vec3 = (0.0, 1.0, 0.0)):
        self.position = tuple(float(v) for v in position)
        self.target = tuple(float(v) for v in target)
        self.fov_deg = float(fov_deg)
        self.aspect = float(aspect)
        self.near = float(near)
        self.far = float(far)
        self.up = tuple(float(v) for v in up)
        self._basis()

    # -- basis ---------------------------------------------------------
    def _basis(self):
        fwd = _norm(_sub(self.target, self.position))
        right = _norm(_cross(fwd, self.up))
        cam_up = _cross(right, fwd)
        self._fwd, self._right, self._up = fwd, right, cam_up

    def focal_px(self, height_px: int) -> float:
        """Focal length in pixels for a frame ``height_px`` tall."""
        return (height_px / 2.0) / math.tan(math.radians(self.fov_deg) / 2.0)

    # -- projection ----------------------------------------------------
    def view_coords(self, point: Vec3) -> tuple[float, float, float]:
        """Camera-space (x right, y up, z forward/depth) of a world point."""
        d = _sub(tuple(float(v) for v in point), self.position)
        return (_dot(d, self._right), _dot(d, self._up), _dot(d, self._fwd))

    def depth_of(self, point: Vec3) -> float:
        return self.view_coords(point)[2]

    def project(self, point: Vec3, width_px: int, height_px: int):
        """Project a world point to screen pixels.

        Returns ``(x, y, scale, visible)`` where ``scale`` is pixels per
        world unit at that depth (``focal / depth``) and ``visible`` is
        False when the point is behind the near plane. Screen origin is
        the top-left corner, y grows downwards.
        """
        xc, yc, zc = self.view_coords(point)
        if zc <= self.near:
            return (0.0, 0.0, 0.0, False)
        f = self.focal_px(height_px)
        x = width_px / 2.0 + f * xc / zc
        y = height_px / 2.0 - f * yc / zc
        return (x, y, f / zc, True)

    def project_size(self, world_size: float, point: Vec3,
                     height_px: int) -> float:
        """Screen height in pixels of a world-sized object at ``point``."""
        _, _, scale, visible = self.project(point, 1, height_px)
        return scale * world_size if visible else 0.0

    def parallax_shift_px(self, point: Vec3, dx_world: float,
                          height_px: int) -> float:
        """Screen shift (px) of ``point`` when the camera dollies sideways
        by ``dx_world``. Near points shift more than far points — this is
        the perspective parallax, computed from the projection itself.
        """
        _, _, scale, visible = self.project(point, 1, height_px)
        if not visible:
            return 0.0
        return -scale * dx_world

    # -- moves / keyframes ---------------------------------------------
    def moved(self, dpos: Vec3 = (0.0, 0.0, 0.0),
              dtarget: Vec3 = (0.0, 0.0, 0.0)) -> "PerspectiveCamera":
        """A copy of this camera translated by ``dpos`` / ``dtarget``."""
        return PerspectiveCamera(
            tuple(a + b for a, b in zip(self.position, dpos)),
            tuple(a + b for a, b in zip(self.target, dtarget)),
            self.fov_deg, self.aspect, self.near, self.far, self.up)

    @staticmethod
    def interpolate(cam_a: "PerspectiveCamera",
                    cam_b: "PerspectiveCamera", t: float) -> "PerspectiveCamera":
        """Linear keyframe interpolation (Motion Canvas timeline parity):
        position, target and fov lerp; t is clamped to [0, 1]."""
        t = min(1.0, max(0.0, float(t)))
        return PerspectiveCamera(
            tuple(_lerp(a, b, t) for a, b in zip(cam_a.position, cam_b.position)),
            tuple(_lerp(a, b, t) for a, b in zip(cam_a.target, cam_b.target)),
            _lerp(cam_a.fov_deg, cam_b.fov_deg, t),
            _lerp(cam_a.aspect, cam_b.aspect, t),
            cam_a.near, cam_a.far, cam_a.up)

    def to_dict(self) -> dict:
        return {"position": list(self.position), "target": list(self.target),
                "fov_deg": self.fov_deg, "aspect": self.aspect,
                "near": self.near, "far": self.far}
