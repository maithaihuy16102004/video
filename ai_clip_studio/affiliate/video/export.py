"""Export: 9:16 reframe + platform profiles, single final encode pass.

The export composes, in ONE ffmpeg invocation:
  replacement filters (text localization) -> transform filters
  (edits) -> reframe to the profile size -> format conversion
  -> libx264 / AAC encode with the profile parameters.

Rules (§18, enforced here):
  * The authorization gate runs FIRST. UNKNOWN or unconfirmed
    authorization refuses the export (``ExportRefusedError``).
  * Source fps is preserved by default. Forcing a profile fps is
    explicit (``fps_mode='force'``) and is recorded as frame
    duplication/dropping — never as a motion improvement.
  * Upscaling is detected and recorded. An upscaled export never
    claims native resolution.
  * No fake 60 fps, no fake 4K. HIGH_QUALITY_MASTER keeps the
    profile resolution; higher resolutions need an explicit custom
    profile and a source that justifies them.
  * One encode pass where practical: replacements + transforms +
    reframe share a single filter graph.

Phase 1 limitation: ``scene_reorder`` cannot be combined with text
replacements in one pass (reordering changes the time mapping the
replacement windows refer to). The combination is refused with a
clear error; run reorder first, then replacements, as two stages.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .capabilities import run_command
from .models import (EXPORT_PRESETS, ExportProfileSpec, ExportResult,
                     ReplacementSpec, TransformOp, export_gate_check)
from .probe import ProbeError, probe_source, sha256_file
from .text_replace import build_replacement_filters
from .transform import build_transform_graph, run_stabilize_detect


class ExportRefusedError(ValueError):
    """Export refused by the authorization gate or an invalid plan."""


def export_profile_for(name: str) -> ExportProfileSpec:
    """Look up a preset by schema name (TIKTOK_REELS, ...)."""
    preset = EXPORT_PRESETS.get(name)
    if preset is None:
        raise ExportRefusedError(
            f"unknown export profile {name!r}; known: "
            f"{sorted(EXPORT_PRESETS)}")
    return preset


def validate_profile(profile: ExportProfileSpec) -> None:
    """Schema AFF014 mirrors: crf / fps / bitrate / resolution ranges."""
    if not 0 <= profile.crf <= 51:
        raise ExportRefusedError(f"crf {profile.crf} must be within 0..51")
    if profile.fps not in (24, 25, 30, 50, 60):
        raise ExportRefusedError(f"fps {profile.fps} must be 24/25/30/50/60")
    if not 96 <= profile.audio_bitrate_kbps <= 320:
        raise ExportRefusedError(
            f"audio bitrate {profile.audio_bitrate_kbps} must be within "
            "96..320 kbps")
    if profile.width <= 0 or profile.height <= 0:
        raise ExportRefusedError("profile resolution must be positive")
    if profile.reframe_strategy not in ("blur_fill", "crop_center", "pad"):
        raise ExportRefusedError(
            f"unknown reframe strategy {profile.reframe_strategy!r}")


def _upscale_expected(source_w: int, source_h: int,
                      profile: ExportProfileSpec) -> tuple[bool, float]:
    """Would the reframe upscale the picture? Returns (upscaled, factor)."""
    if profile.reframe_strategy == "blur_fill":
        factor = min(profile.width / source_w, profile.height / source_h)
    elif profile.reframe_strategy == "crop_center":
        from .transform import reframe_crop_rect
        _, _, cw, ch = reframe_crop_rect(source_w, source_h,
                                         profile.width, profile.height)
        factor = profile.width / cw
    else:  # pad
        factor = min(profile.width / source_w, profile.height / source_h)
    return factor > 1.001, round(factor, 3)


def export_video(video_path: str | Path, output_path: str | Path,
                 profile: ExportProfileSpec | str,
                 authorization_type: str,
                 commercial_rights_confirmed: bool,
                 transforms: list[TransformOp] | None = None,
                 replacements: list[ReplacementSpec] | None = None,
                 audio_filter: str | None = None,
                 work_dir: str | Path | None = None,
                 font_path: str | None = None) -> ExportResult:
    """Run the gated single-pass export. Returns measured ExportResult.

    ``audio_filter`` is an optional ffmpeg audio filter chain supplied
    by the audio-mix stage (Subagent B); when absent, the source audio
    (or the transforms' audio) is encoded to the profile AAC spec.
    """
    if isinstance(profile, str):
        profile = export_profile_for(profile)
    validate_profile(profile)
    allowed, reasons = export_gate_check(authorization_type,
                                         commercial_rights_confirmed)
    if not allowed:
        raise ExportRefusedError("export refused: " + "; ".join(reasons))
    transforms = list(transforms or [])
    replacements = list(replacements or [])
    if replacements and any(op.operation == "scene_reorder"
                            for op in transforms):
        raise ExportRefusedError(
            "scene_reorder cannot be combined with text replacements in "
            "one pass (reordering changes replacement time windows); "
            "run reorder first, then replacements")

    source = probe_source(video_path)
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="aff_exp_"))
    work.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    warnings: list[str] = []
    try:
        # Stabilization detect pre-pass (runs on the source).
        stabilize_file = None
        if any(op.operation == "stabilize" for op in transforms):
            stabilize_file = str(run_stabilize_detect(video_path, work))
            warnings.append("stabilization detect pass ran on the source "
                            "video; the transform joins the final graph")

        # 1) replacement fragment (starts at 0:v).
        rep_complex, rep_label, rep_log = build_replacement_filters(
            replacements, (source.width, source.height), work,
            font_path=font_path, authorization_type=authorization_type,
            commercial_rights_confirmed=commercial_rights_confirmed)

        # 2) transform fragment (chains after replacements). When a
        #    CROP_AND_REFRAME replacement ran, the frame entering the
        #    transform stage is shorter — validate/compute against the
        #    post-replacement size, not the source size.
        eff_w, eff_h = source.width, source.height
        for spec in replacements:
            if spec.mode.name == "CROP_AND_REFRAME":
                eff_h -= int(round(spec.region.bbox.h))
        from dataclasses import replace as _dc_replace
        eff_source = _dc_replace(source, width=eff_w, height=eff_h)
        graph = build_transform_graph(
            transforms, eff_source, stabilize_file=stabilize_file,
            start_label=rep_label if rep_complex else "0:v")

        # 3) reframe to the profile size (unless a reframe op already
        #    produced exactly the profile size).
        already = any(op.operation == "reframe" and
                      int(op.parameters.get("target_w", 0)) == profile.width and
                      int(op.parameters.get("target_h", 0)) == profile.height
                      for op in transforms)
        if not already:
            reframe_op = TransformOp(
                operation="reframe",
                parameters={"target_w": profile.width,
                            "target_h": profile.height,
                            "strategy": profile.reframe_strategy},
                purpose="reframe to the export profile aspect/size")
            reframe_graph = build_transform_graph(
                [reframe_op], source, start_label=graph.video_label)
            graph.filters.extend(reframe_graph.filters)
            graph.video_label = reframe_graph.video_label
            graph.notes.extend(reframe_graph.notes)

        # 4) fps handling + pixel format.
        fps_preserved = True
        if profile.fps_mode == "force" and abs(source.fps - profile.fps) > 0.01:
            graph.video(f"fps={profile.fps}",
                        f"fps forced {source.fps} -> {profile.fps} "
                        "(frames duplicated/dropped; no motion improvement)")
            fps_preserved = False
        elif source.fps not in (24.0, 25.0, 30.0, 50.0, 60.0):
            warnings.append(f"source fps {source.fps} preserved; it is "
                            "outside the usual 24/25/30/50/60 set")
        graph.video(f"format={profile.pixel_format}", "pixel format")

        # Assemble the full filter_complex.
        fragments = []
        if rep_complex:
            fragments.append(rep_complex)
        graph_complex, video_label, audio_label = graph.build()
        if graph_complex:
            fragments.append(graph_complex)
        filter_complex = ";".join(f for f in fragments if f)

        # Audio: mix-stage filter wins (applied to the transformed
        # audio when transforms touched it, else to the source audio);
        # else the transform audio label; else the raw source audio,
        # re-encoded to the profile spec.
        if audio_filter:
            if not source.has_audio and not (audio_label
                                             and audio_label != "0:a"):
                raise ExportRefusedError(
                    "audio_filter supplied but the source has no audio "
                    "stream to mix")
            audio_src = audio_label if audio_label else "0:a"
            filter_complex = (filter_complex + ";" if filter_complex else "") \
                + f"[{audio_src}]{audio_filter}[amix]"
            audio_map: str | None = "[amix]"
        elif audio_label and audio_label != "0:a":
            audio_map = f"[{audio_label}]"
        elif source.has_audio:
            audio_map = "0:a?"
        else:
            audio_map = None

        upscaled, scale_factor = _upscale_expected(
            source.width, source.height, profile)
        if upscaled:
            warnings.append(
                f"source upscaled by {scale_factor}x to reach "
                f"{profile.width}x{profile.height}; no new detail is "
                "created and the output must not be labelled native HD")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        argv = ["ffmpeg", "-v", "error", "-i", str(video_path)]
        if filter_complex:
            argv += ["-filter_complex", filter_complex,
                     "-map", f"[{video_label}]"]
            if audio_map:
                argv += ["-map", audio_map]
        argv += ["-c:v", "libx264", "-crf", str(profile.crf),
                 "-preset", profile.preset,
                 "-pix_fmt", profile.pixel_format]
        if audio_map:
            argv += ["-c:a", profile.audio_codec,
                     "-b:a", f"{profile.audio_bitrate_kbps}k",
                     "-ar", str(profile.audio_sample_rate)]
        argv += ["-colorspace", profile.color_space,
                 "-color_primaries", profile.color_space,
                 "-color_trc", profile.color_space]
        if profile.faststart:
            argv += ["-movflags", "+faststart"]
        argv += ["-y", str(out)]
        proc = run_command(argv, timeout=1800.0)
        if proc.returncode != 0 or not out.is_file():
            raise ProbeError(f"export encode failed: "
                             f"{(proc.stderr or '').strip()[:300]}")

        measured = probe_source(out)
        if (measured.width, measured.height) != (profile.width, profile.height):
            warnings.append(
                f"output is {measured.width}x{measured.height}, expected "
                f"{profile.width}x{profile.height}")
        return ExportResult(
            output_path=str(out), profile_name=profile.name,
            width=measured.width, height=measured.height,
            fps=measured.fps, duration_sec=measured.duration_sec,
            video_codec=measured.video_codec,
            audio_codec=measured.audio_codec,
            file_size_bytes=measured.file_size_bytes,
            sha256=measured.sha256, upscaled=upscaled,
            fps_preserved=fps_preserved,
            transforms_applied=[op.operation for op in transforms],
            replacements_applied=[f"{s.mode.value}:{s.region.text_id}"
                                  for s in replacements],
            warnings=warnings,
            gate={"authorization_type": authorization_type,
                  "commercial_rights_confirmed": commercial_rights_confirmed},
            encode_seconds=round(time.monotonic() - started, 2),
            command=argv)
    finally:
        if work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
