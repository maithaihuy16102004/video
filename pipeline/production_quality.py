"""Quality gates and planning helpers for the canonical local video pipeline.

The goal of this module is deliberately small: prevent a technically valid
render from being mistaken for a good video.  It is dependency-free so both
the Python/Pillow renderer and the Director/Remotion path can use it.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


def normalize_topic_key(value: str) -> str:
    """Return a stable ASCII key for Vietnamese and punctuation-heavy topics."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    ascii_text = ascii_text.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_text)).strip("_")


def select_preset(topic: str, presets: dict[str, dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
    """Select a preset by phrase/token coverage, never by a single loose token."""
    topic_key = normalize_topic_key(topic)
    topic_tokens = set(topic_key.split("_"))
    best: tuple[float, str] | None = None
    for raw_key in presets:
        key = normalize_topic_key(raw_key)
        key_tokens = set(key.split("_"))
        phrase_match = key in topic_key or topic_key in key
        coverage = len(topic_tokens & key_tokens) / max(1, len(key_tokens))
        score = 2.0 if phrase_match else coverage
        # Two meaningful matching tokens or 75% coverage avoids accidental routes.
        if not phrase_match and not (len(topic_tokens & key_tokens) >= 2 and coverage >= 0.75):
            continue
        if best is None or score > best[0]:
            best = (score, raw_key)
    if best is None:
        return None, None
    return best[1], copy.deepcopy(presets[best[1]])


def enrich_scene_plan(config: dict[str, Any], topic: str, max_visual_beat: float = 3.5) -> dict[str, Any]:
    """Attach an explicit edit plan consumed by renderers and quality checks."""
    config = copy.deepcopy(config)
    scenes = config.get("scenes", [])
    for index, scene in enumerate(scenes):
        role = "hook" if index == 0 else "cta" if index == len(scenes) - 1 else "body"
        headline = str(scene.get("headline", scene.get("title", topic))).replace("\n", " ")
        spoken = str(scene.get("spoken", ""))
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", spoken) if s.strip()]
        visual_prompts = [
            f"{topic}; {headline}; cinematic establishing shot; no text",
            f"{topic}; {sentences[0] if sentences else headline}; concrete visual evidence; no presenter",
            f"{topic}; {sentences[-1] if sentences else headline}; detail shot with clear subject; no text",
        ]
        concept_text = normalize_topic_key(f"{headline} {spoken}")
        if any(k in concept_text for k in ("mang_no_ron", "bo_nao_ai", "ngon_ngu_lon")):
            visual_language = "neural_network"
        elif any(k in concept_text for k in ("robot", "tu_dong", "nha_may", "phau_thuat")):
            visual_language = "automation"
        elif any(k in concept_text for k in ("dao_duc", "kiem_soat", "sinh_tu", "ranh_gioi")):
            visual_language = "ethics_balance"
        elif any(k in concept_text for k in ("vu_tru", "hanh_tinh", "khong_gian", "van_minh")):
            visual_language = "orbital_future"
        elif any(k in concept_text for k in ("tai_chinh", "tien", "dau_tu", "lai_kep")):
            visual_language = "data_chart"
        elif any(k in concept_text for k in ("ho_den", "chan_troi_su_kien", "diem_ky_di")):
            visual_language = "black_hole"
        else:
            visual_language = "data_stream"
        beat_duration = max(1.6, min(max_visual_beat, float(scene.get("duration", 8)) / 3))
        scene["edit_plan"] = {
            "role": role,
            "card_mode": "title" if role in {"hook", "cta"} else "minimal",
            "max_visual_beat_seconds": max_visual_beat,
            "visual_prompts": visual_prompts,
            "visual_beats": [
                {"role": "establish", "prompt": visual_prompts[0], "duration": beat_duration},
                {"role": "evidence", "prompt": visual_prompts[1], "duration": beat_duration},
                {"role": "resolve", "prompt": visual_prompts[2], "duration": beat_duration},
            ],
            "motion_arc": ["anticipate", "act", "settle"],
            "camera_pattern": ["wide", "detail", "wide"],
            "hold_seconds": 0.6 if role == "body" else 1.0,
            "transition": "hard_cut" if index else "cold_open",
            "asset_source": "generated_or_licensed_stock",
            "visual_language": visual_language,
        }
    config["pipeline"] = {
        "canonical": "director_asset_renderer",
        "render_priority": ["remotion", "hyperframes", "ffmpeg"],
        "topic_key": normalize_topic_key(topic),
    }
    return config


@dataclass
class QualityReport:
    passed: bool
    errors: list[str]
    warnings: list[str]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_plan(config: dict[str, Any]) -> QualityReport:
    errors: list[str] = []
    warnings: list[str] = []
    scenes = config.get("scenes") or []
    if len(scenes) < 3:
        errors.append("Kịch bản phải có ít nhất 3 cảnh.")
    unique_spoken = {str(s.get("spoken", "")).strip() for s in scenes}
    if len(unique_spoken) != len(scenes):
        errors.append("Có lời thoại trùng giữa các cảnh.")
    for idx, scene in enumerate(scenes, 1):
        plan = scene.get("edit_plan") or {}
        prompts = plan.get("visual_prompts") or []
        if len(prompts) < 3:
            errors.append(f"Cảnh {idx} thiếu tối thiểu 3 visual beats.")
        beats = plan.get("visual_beats") or []
        roles = [str(beat.get("role", "")) for beat in beats if isinstance(beat, dict)]
        if roles != ["establish", "evidence", "resolve"]:
            errors.append(f"Cảnh {idx} phải có nhịp establish → evidence → resolve.")
        if plan.get("motion_arc") != ["anticipate", "act", "settle"]:
            errors.append(f"Cảnh {idx} thiếu motion arc anticipate → act → settle.")
        if float(plan.get("hold_seconds", 0)) < 0.5:
            errors.append(f"Cảnh {idx} thiếu tối thiểu 0,5 giây nghỉ sau điểm nhấn.")
        if float(plan.get("max_visual_beat_seconds", 99)) > 4.0:
            errors.append(f"Cảnh {idx} có nhịp hình dài hơn 4 giây.")
        if plan.get("card_mode") == "title" and idx not in {1, len(scenes)}:
            warnings.append(f"Cảnh {idx} dùng title card ngoài hook/CTA.")
        if not str(scene.get("spoken", "")).strip():
            errors.append(f"Cảnh {idx} không có lời thoại.")
    languages = [str((s.get("edit_plan") or {}).get("visual_language", "")) for s in scenes]
    if len(scenes) >= 4 and len(set(languages)) < max(3, len(scenes) // 2):
        warnings.append("Ngôn ngữ hình ảnh lặp nhiều; cần tăng độ đa dạng theo nội dung.")
    metrics = {
        "gate_scope": "plan_structure_only",
        "creative_approval": "requires_frame_review",
        "scene_count": len(scenes),
        "visual_beat_count": sum(len((s.get("edit_plan") or {}).get("visual_prompts") or []) for s in scenes),
        "structured_visual_beat_count": sum(len((s.get("edit_plan") or {}).get("visual_beats") or []) for s in scenes),
        "unique_visual_languages": len(set(languages)),
        "minimum_hold_seconds": min((float((s.get("edit_plan") or {}).get("hold_seconds", 0)) for s in scenes), default=0),
        "canonical_pipeline": (config.get("pipeline") or {}).get("canonical"),
    }
    return QualityReport(not errors, errors, warnings, metrics)


def write_quality_report(config: dict[str, Any], output: str | Path) -> QualityReport:
    report = validate_plan(config)
    Path(output).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def generate_contact_sheet(video: str | Path, output: str | Path, columns: int = 3, rows: int = 3) -> Path:
    """Create an approval contact sheet sampled uniformly across the render."""
    video, output = Path(video), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        check=True, capture_output=True, text=True,
    )
    duration = max(0.1, float(probe.stdout.strip()))
    frames = columns * rows
    interval = duration / (frames + 1)
    vf = f"fps=1/{interval:.6f},scale=360:-1,tile={columns}x{rows}:padding=8:margin=8"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", vf, "-frames:v", "1", str(output)],
        check=True,
    )
    return output


def evaluate_render_metrics(probe: dict[str, Any], loudness: dict[str, Any] | None = None) -> QualityReport:
    """Evaluate the rendered file itself, not just its plan."""
    errors: list[str] = []
    warnings: list[str] = []
    streams = probe.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if (width, height) != (1080, 1920):
        errors.append(f"Sai khung dọc: {width}x{height}; yêu cầu 1080x1920.")
    fps_raw = str(video.get("r_frame_rate", "0/1"))
    try:
        num, den = fps_raw.split("/", 1)
        fps = float(num) / max(float(den), 1e-9)
    except (ValueError, ZeroDivisionError):
        fps = 0
    if abs(fps - 30) > 0.05:
        errors.append(f"Sai frame rate: {fps:.3f}; yêu cầu 30 fps.")
    if not audio:
        errors.append("Thành phẩm không có audio stream.")
    duration = float((probe.get("format") or {}).get("duration", 0) or 0)
    if duration < 8:
        errors.append("Thành phẩm ngắn bất thường (<8 giây).")
    if loudness:
        integrated = float(loudness.get("input_i", -99))
        true_peak = float(loudness.get("input_tp", 99))
        if not -15.0 <= integrated <= -13.0:
            errors.append(f"Loudness {integrated:.2f} LUFS ngoài dải -14±1 LUFS.")
        if true_peak > -1.0:
            errors.append(f"True peak {true_peak:.2f} dBTP vượt -1.0 dBTP.")
        if float(loudness.get("input_lra", 0)) < 1.5:
            warnings.append("Audio quá phẳng (LRA <1.5 LU); nên kiểm tra độ sống của nhạc/SFX.")
    metrics = {"gate_scope": "render_technical_only", "creative_approval": "requires_independent_review", "width": width, "height": height, "fps": fps, "duration": duration, "has_audio": bool(audio)}
    if loudness:
        metrics.update({"integrated_lufs": float(loudness.get("input_i", -99)), "true_peak_dbtp": float(loudness.get("input_tp", 99)), "lra_lu": float(loudness.get("input_lra", 0))})
    return QualityReport(not errors, errors, warnings, metrics)


def inspect_render(video: str | Path, output: str | Path) -> QualityReport:
    video = Path(video)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    ).stdout)
    loud = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video), "-af", "loudnorm=I=-14:LRA=7:TP=-1.5:print_format=json", "-f", "null", "NUL"],
        capture_output=True, text=True,
    )
    match = re.search(r'\{\s*"input_i".*?\}', loud.stderr, re.S)
    loudness = json.loads(match.group(0)) if match else None
    report = evaluate_render_metrics(probe, loudness)
    Path(output).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report
