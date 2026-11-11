"""Generalization runner (not a test double for production):
runs the REAL orchestrator on 3 unseen scripts, twice each:
  Mode A — production, no injections: must fail honestly at the
    first missing real dependency (Gemini).
  Mode B — labelled test doubles: fallback planner (from real
    segmentation), real silent WAV voices, real ffmpeg mp4 render,
    mock Drive client. Proves the 19-stage machinery works end to
    end; does NOT prove the real Motion Canvas render works.
Writes a JSON summary to stdout; the .md report is built from it.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))

from ai_clip_studio.orchestrator import UniversalProductionPipeline
from ai_clip_studio.pipeline import segment_script
from ai_clip_studio.audio_events import load_meme_catalog
from tests.test_orchestrator import (
    fallback_planner, wav_voice_provider, ffmpeg_render_fn,
)
from tests.test_ai_clip_studio import MockDriveClient

SCRIPTS = {
    "G1_indoor_dialogue": (
        "Minh: Chào buổi sáng, Lan.\n"
        "Lan: Chào Minh, mời anh ngồi.\n"
        "Minh mở cửa quán cà phê và bước vào.\n"
        "Minh: Tôi mang lá thư này cho cô.\n"
        "Lan: Cảm ơn anh, tôi sẽ đọc ngay."
    ),
    "G2_outdoor_action": (
        "Haru chạy qua cây cầu gỗ trong cơn mưa.\n"
        "Haru: Cầu rung quá, mình phải bám chặt lan can.\n"
        "Một tấm ván bật tung, Haru ngã xuống rồi bám lấy lan can.\n"
        "Haru: Lá thư không được ướt, mình phải giữ chặt nó."
    ),
    "G3_comedy_meme": (
        "Tuấn: Các bạn ơi, tôi vừa làm xong video bằng AI.\n"
        "Minh cười và nói: Ối dồi ôi, thật không thể tin được.\n"
        "Tuấn gõ cửa rồi mở cửa bước vào phòng.\n"
        "Minh: Gòi gòi tới công chuyện rồi, xem thử nào."
    ),
}

CATALOG = load_meme_catalog(
    Path.home() / "workspace" / "video-upstream" / "assets" / "memes" / "catalog.json")


def main() -> None:
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, script in SCRIPTS.items():
            # Mode A: production, no injections.
            pipe_a = UniversalProductionPipeline(root / f"{name}_prod")
            job_a = pipe_a.run(script, available_voices=("Minh", "Lan", "Haru", "Tuấn", "narrator"))
            # Mode B: test doubles.
            pipe_b = UniversalProductionPipeline(
                root / f"{name}_test",
                planner=fallback_planner,
                voice_provider=wav_voice_provider,
                render_fn=ffmpeg_render_fn,
                drive_client=MockDriveClient(),
                meme_catalog=CATALOG,
            )
            job_b = pipe_b.run(script, available_voices=("Minh", "Lan", "Haru", "Tuấn", "narrator"))
            results[name] = {
                "script_chars": len(script),
                "mode_A_production": {
                    "status": job_a.status,
                    "blocked_reason": job_a.blocked_reason,
                    "stages_passed": [s.stage for s in job_a.stages if s.status.value == "passed"],
                    "stages_failed": [s.stage for s in job_a.stages if s.status.value == "failed"],
                },
                "mode_B_test_doubles": {
                    "status": job_b.status,
                    "blocked_reason": job_b.blocked_reason,
                    "stage_count": len(job_b.stages),
                    "all_passed": all(s.status.value == "passed" for s in job_b.stages),
                    "draft_mp4_bytes": (job_b.job_dir / "draft.mp4").stat().st_size
                    if (job_b.job_dir / "draft.mp4").exists() else 0,
                },
            }
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
