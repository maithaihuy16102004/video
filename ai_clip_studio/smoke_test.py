"""Smoke test — runs the REAL orchestrator, no separate render path.

Usage:
    python -m ai_clip_studio.smoke_test --script <file>
    python -m ai_clip_studio.smoke_test --script <file> --jobs-dir <dir>

It uses UniversalProductionPipeline exactly as the API does
(server.py /api/production/draft). When a real dependency is missing
(Gemini key, VieNeu, Chrome), it FAILS with that dependency's
diagnostic and prints the stage where the job stopped — it never
mocks a render, never claims success.

Exit code 0 only when the job reaches END_TO_END_DRAFT_READY_FOR_REVIEW
or MASTER_APPROVED_AND_UPLOADED.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .orchestrator import (
    UniversalProductionPipeline, STATUS_DRAFT_READY, STATUS_MASTER,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI Clip Studio smoke test")
    ap.add_argument("--script", required=True, help="Path to a script file")
    ap.add_argument("--jobs-dir", default=None)
    ap.add_argument("--language", default="vi-VN")
    ap.add_argument("--aspect-ratio", default="16:9")
    args = ap.parse_args(argv)

    script_path = Path(args.script)
    if not script_path.exists():
        print(f"ERROR: script file not found: {script_path}", file=sys.stderr)
        return 2
    script = script_path.read_text(encoding="utf-8")
    jobs_root = Path(args.jobs_dir) if args.jobs_dir else (
        Path(__file__).resolve().parent.parent / "jobs")
    pipeline = UniversalProductionPipeline(jobs_root)
    job = pipeline.run(script, language=args.language,
                       aspect_ratio=args.aspect_ratio)
    print(json.dumps(job.to_dict(), indent=2, ensure_ascii=False))
    print(f"\nFINAL STATUS: {job.status}")
    if job.blocked_reason:
        print(f"BLOCKED: {job.blocked_reason}")
    print(f"Job dir: {job.job_dir}")
    return 0 if job.status in (STATUS_DRAFT_READY, STATUS_MASTER) else 1


if __name__ == "__main__":
    raise SystemExit(main())
