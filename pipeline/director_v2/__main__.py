"""CLI entry point for Director V2:

Usage examples:
  # 1. Dry run on a script (10 canonical JSON files, 0 image calls)
  python -m pipeline.director_v2 --script episode.txt --quality standard --dry-run

  # 2. Offline run for tests / local execution
  python -m pipeline.director_v2 --script episode.txt --offline --dry-run

  # 3. Generate missing assets
  python -m pipeline.director_v2 --script episode.txt --quality standard --generate-assets
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_OUTPUT_ROOT, ProjectConfig
from .orchestrator import DirectorV2Orchestrator
from .render.adapters.pycairo_draft import PyCairoDraftAdapter
from .schemas.core import AspectRatio, QualityTier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Director V2 — Script-to-Shot Autonomous Director")
    parser.add_argument("--script", required=True, help="Path to script text file")
    parser.add_argument("--quality", default="STANDARD", choices=["DRAFT", "STANDARD", "MASTER"], help="Quality tier")
    parser.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"], help="Aspect ratio (default 16:9)")
    parser.add_argument("--out", default=None, help="Output directory")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Do not call Image Generation APIs")
    parser.add_argument("--generate-assets", dest="dry_run", action="store_false", help="Generate missing visual assets")
    parser.add_argument("--offline", action="store_true", help="Pure offline mode using heuristic analyzers and mock providers")
    parser.add_argument("--render-draft", action="store_true", help="Also generate pycairo draft render-props.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Script file not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    script_text = script_path.read_text(encoding="utf-8")
    slug = script_path.stem[:32].replace(" ", "_")

    out_dir = Path(args.out) if args.out else DEFAULT_OUTPUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    config = ProjectConfig.for_aspect(
        aspect=args.aspect,
        quality=QualityTier(args.quality),
    )

    orchestrator = DirectorV2Orchestrator(
        config=config,
        output_dir=out_dir,
        offline=args.offline,
        dry_run=args.dry_run,
    )

    artifacts = orchestrator.run(script_text, project_id=slug)

    if args.render_draft:
        from .schemas.manifest import RenderManifest
        rm_path = artifacts.get("render_manifest.json")
        if rm_path and rm_path.exists():
            import json
            rm_data = json.loads(rm_path.read_text(encoding="utf-8"))
            rm = RenderManifest.model_validate(rm_data)
            adapter = PyCairoDraftAdapter()
            spec_path = adapter.prepare_render_spec(rm, out_dir / "draft_spec")
            print(f"Draft spec generated: {spec_path}")

    print("\n--- Director V2 Phase 1 Execution Successful ---")
    print(f"Output directory: {out_dir}")
    for name, p in artifacts.items():
        print(f"  * {name:<26} ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
