"""Environment Artist prompt builder for Gemini Image API (DRAFT_VISUAL mode).

Enforces the Master Environment Generation Rule:
- EMPTY HISTORICAL ENVIRONMENT PLATE: Pure background plate WITHOUT any main protagonist.
- Camera compliance: shot type, camera height, yaw, pitch, horizon, vanishing point, and depth axis.
- Strict negative constraints: no stickman, no character, no text, no watermark.
"""
from __future__ import annotations

from typing import Any


def build_environment_plate_prompt(
    location_name: str,
    location_description: str,
    year: int | str,
    shot_type: str,
    camera_height: str,
    camera_pitch: float,
    camera_yaw: float,
    horizon_y: float,
    perspective_type: str,
    depth_axis: str = "Z_INTO_SCREEN",
    historical_constraints: list[str] | None = None,
    atmosphere: str = "atmospheric haze",
    time_of_day: str = "overcast daytime",
    weather: str = "foggy cold",
) -> tuple[str, str]:
    """Generates (positive_prompt, negative_prompt) strictly for an EMPTY environment plate."""
    constraints = historical_constraints or []
    c_h = camera_height.upper()

    # 1. Camera height & perspective framing description
    if "LOW" in c_h or "WORM" in c_h or camera_pitch > 10.0:
        angle_desc = f"Extreme Low-Angle Worm's-Eye View looking UPWARDS from the ground (pitch +{camera_pitch:.0f}°). The horizon is very low near the bottom {horizon_y * 100:.0f}% of frame, making architecture and defensive ramparts loom tall into the expansive sky."
    elif "HIGH" in c_h or "CRANE" in c_h or camera_pitch < -15.0:
        angle_desc = f"High-Angle Crane Shot looking DOWNWARDS onto the ground (pitch {camera_pitch:.0f}°). The horizon is positioned high near the top {horizon_y * 100:.0f}% of frame, exposing an expansive downward view of the ground terrain, mud, cobblestones, and trenches."
    elif "GROUND" in c_h:
        angle_desc = f"Ground-Level Camera resting directly on the dirt and mud puddles (horizon at {horizon_y * 100:.0f}%). Foreground earth, rocks, and mud textures dominate the lower third."
    else:
        angle_desc = f"Eye-Level Cinematic Framing with natural horizon placed at {horizon_y * 100:.0f}% of frame height."

    # 2. Yaw & vanishing point direction
    if camera_yaw < -10.0:
        yaw_desc = f"Angled camera rotated {abs(camera_yaw):.0f}° to the left; perspective lines and walls converge diagonally toward the right side of the canvas."
    elif camera_yaw > 10.0:
        yaw_desc = f"Angled camera rotated {camera_yaw:.0f}° to the right; perspective lines and walls converge diagonally toward the left side of the canvas."
    else:
        yaw_desc = "Frontal camera perspective with symmetrical vanishing lines converging into the center distance."

    # 3. Perspective type description
    if "ONE_POINT" in perspective_type.upper() or "CORRIDOR" in perspective_type.upper():
        persp_desc = f"Strict One-Point Perspective deep corridor recession along {depth_axis} axis, creating extreme tunneling depth toward a single vanishing point."
    elif "ZIGZAG" in perspective_type.upper():
        persp_desc = "Deep zig-zagging geometric defensive trenches receding into the distance across multiple depth planes."
    else:
        persp_desc = f"Two-Point Perspective architectural composition with dynamic diagonal depth planes along {depth_axis}."

    # 4. Assemble the positive prompt
    pos_lines = [
        "A MASTERWORK CINEMATIC HISTORICAL CONCEPT ART ENVIRONMENT PLATE.",
        f"EMPTY HISTORICAL LOCATION: {location_name} ({year}).",
        f"Bối cảnh: {location_description}.",
        f"Atmosphere & Weather: {atmosphere}, {time_of_day}, {weather}.",
        f"Camera Shot Type: {shot_type}.",
        f"Camera Geometry: {angle_desc}",
        f"Camera Orientation: {yaw_desc}",
        f"Perspective System: {persp_desc}",
        "HISTORICAL ACCURACY CONSTRAINTS: " + ("; ".join(constraints[:3]) if constraints else "Authentic period architecture and accurate historical materials."),
        "ENVIRONMENT CONTENT ONLY: Authentic period architecture, historical terrain, weathered wooden beams, cobblestones, sandbags, distant smoke, atmospheric lighting, volumetric light rays.",
        "MANDATORY REQUIREMENT: EMPTY STAGE / BACKGROUND PLATE ONLY. NO human protagonist, NO main characters, NO stickman characters in foreground. Stage is clear and ready for character compositing.",
    ]

    positive_prompt = "\n".join(pos_lines)

    # 5. Strict negative prompt
    negative_prompt = (
        "human protagonist, main character, stickman, cartoon stick figure, people in foreground, "
        "faces, portrait, talking head, modern vehicles, asphalt, electrical pylons, "
        "text, watermark, logo, subtitles, frames, borders, blurry edges, distortion, flat stage backdrop"
    )

    return positive_prompt, negative_prompt
