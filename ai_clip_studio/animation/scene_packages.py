"""Scene packages: ONE reusable location definition per place.

Mai's reminder (2026-11-11 23:22): the engine is UNIVERSAL -- a scene
is a data package (3D boxes + sky/ground + characters as data), built
once in the shared engine and rendered by the same renderer for every
script. A test or a story NEVER copies the box list into its own file:
it calls the package with its camera + its characters + its options
and the engine builds the world. (The camera test v9 was first written
with its own copy of the street boxes -- that duplication is exactly
what this module removes.)

A scene package returns a ``renderer25d.scene.Scene25D``. The 2D
overlay detail (street features, awning, bus) lives in
``animation.landmarks`` and is drawn by the caller in the frame loop,
because it is screen-space dressing on top of the 3D world.

Packages
--------
``rainy_street_night`` -- the rainy Vietnamese street corner at night
(the motion-test / Chiec Vi world): 3 distant buildings with lit
windows, lamp + bench + labelled bus-stop sign, kerb + path strips,
foreground crate + railing. FG / MG / BG layers are all populated.
The flat red awning slab was REMOVED in v9 (it read as a floating
bar); the real striped awning is a 2D overlay drawn by the caller.
"""
from __future__ import annotations

from ai_clip_studio.renderer25d.scene import Box3D, Scene25D


def rainy_street_night(camera, characters, *,
                       sky_top=(18, 30, 58),
                       sky_bottom=(110, 124, 150),
                       ground_color=(64, 58, 52),
                       ground_extent=30.0,
                       bus=None):
    """Rainy Vietnamese street corner at night (v9 world, exact).

    ``camera`` -- a ``renderer25d.camera.PerspectiveCamera``.
    ``characters`` -- list of ``CharacterAnchor`` (world positions are
    DATA: the caller places its characters; the package does not know
    Minh, Lan or any story). ``bus`` -- optional dict
    ``{center, size, color, name, label}`` adding a bus box at the
    stop (for a boarding shot); ``None`` = no bus.
    Returns a ``Scene25D``.
    """
    boxes = [
        # Background: 3 distant buildings with LIT WINDOWS (warm
        # boxes on the facades, just in front of the wall).
        Box3D(center=(-4.5, 1.5, -12.0), size=(2.4, 3.0, 1.5),
              color=(74, 88, 118), name="building_left"),
        Box3D(center=(-0.5, 2.0, -14.0), size=(3.2, 4.0, 1.5),
              color=(66, 80, 110), name="building_center"),
        Box3D(center=(4.8, 1.3, -11.0), size=(2.2, 2.6, 1.5),
              color=(80, 94, 124), name="building_right"),
        Box3D(center=(-5.2, 1.6, -11.15), size=(0.5, 0.7, 0.1),
              color=(255, 200, 90), name="window_L1"),
        Box3D(center=(-3.8, 2.4, -11.15), size=(0.5, 0.7, 0.1),
              color=(255, 200, 90), name="window_L2"),
        Box3D(center=(-1.5, 2.0, -13.15), size=(0.5, 0.7, 0.1),
              color=(255, 200, 90), name="window_C1"),
        Box3D(center=(0.5, 3.0, -13.15), size=(0.5, 0.7, 0.1),
              color=(255, 200, 90), name="window_C2"),
        Box3D(center=(4.2, 1.5, -10.15), size=(0.5, 0.7, 0.1),
              color=(255, 200, 90), name="window_R1"),
        Box3D(center=(5.4, 1.5, -10.15), size=(0.5, 0.7, 0.1),
              color=(255, 200, 90), name="window_R2"),
        # Midground: lamp, bench, bus-stop sign (LABELLED), kerb.
        # v9: NO awning slab -- the v7/v8 flat red box read as a
        # floating bar. The 2D awning is drawn by the caller.
        Box3D(center=(4.0, 1.6, -1.5), size=(0.14, 3.2, 0.14),
              color=(30, 32, 40), name="lamp_post"),
        Box3D(center=(4.0, 3.3, -1.5), size=(0.55, 0.22, 0.55),
              color=(255, 211, 78), name="lamp_head"),
        Box3D(center=(2.6, 0.22, -2.5), size=(1.9, 0.45, 0.6),
              color=(122, 74, 43), name="bench"),
        Box3D(center=(0.2, 1.3, -2.0), size=(0.1, 2.6, 0.1),
              color=(30, 32, 40), name="sign_post"),
        Box3D(center=(0.2, 2.7, -2.0), size=(1.0, 0.6, 0.08),
              color=(23, 32, 51), name="bus_stop_sign",
              label="TRẠM XE BUÝT"),
        Box3D(center=(0.0, 0.08, -1.2), size=(14.0, 0.16, 0.6),
              color=(150, 148, 140), name="kerb"),
        # Foreground: a crate and a railing at the frame edges, near
        # the camera (z > 0), plus a path strip the characters walk
        # along. They must not cover the characters: crate at world
        # x 2.2 (screen right edge), railing at world x -3.2 (left).
        Box3D(center=(2.2, 0.25, 1.5), size=(0.5, 0.5, 0.5),
              color=(139, 94, 52), name="crate_fg"),
        Box3D(center=(0.0, 0.05, 1.0), size=(14.0, 0.1, 0.4),
              color=(96, 90, 82), name="path_fg"),
        Box3D(center=(-3.4, 0.5, 1.2), size=(1.8, 0.1, 0.1),
              color=(40, 42, 50), name="railing_fg"),
        Box3D(center=(-4.1, 0.25, 1.2), size=(0.1, 0.5, 0.1),
              color=(40, 42, 50), name="railing_post_l"),
        Box3D(center=(-2.7, 0.25, 1.2), size=(0.1, 0.5, 0.1),
              color=(40, 42, 50), name="railing_post_r"),
    ]
    if bus is not None:
        boxes.append(Box3D(
            center=tuple(bus["center"]), size=tuple(bus["size"]),
            color=tuple(bus.get("color", (36, 84, 138))),
            name=bus.get("name", "bus"),
            label=bus.get("label", "")))
    return Scene25D(
        boxes=boxes,
        characters=list(characters),
        camera=camera,
        sky_top=sky_top, sky_bottom=sky_bottom,
        ground_color=ground_color, ground_extent=ground_extent,
    )


# Registry of scene packages: name -> builder. A new location is a
# new entry here (data + builder), never a copy of a box list in a
# test or a story script. Gemini-supplied locations arrive as data
# through the pipeline; the builder stays generic.
SCENE_PACKAGES = {
    "rainy_street_night": rainy_street_night,
}


def build_scene(package, camera, characters, **options):
    """Build a scene package by name. Raises KeyError for an unknown
    package (same contract as ``landmark_boxes``)."""
    if package not in SCENE_PACKAGES:
        raise KeyError(f"unknown scene package: {package!r} "
                       f"(expected one of {sorted(SCENE_PACKAGES)})")
    return SCENE_PACKAGES[package](camera, characters, **options)


def register_scene_package(name, builder):
    """Register a new scene package at runtime (for Gemini-supplied
    locations: the pipeline builds a builder from structured data and
    registers it; the engine never hardcodes the new location)."""
    SCENE_PACKAGES[name] = builder
