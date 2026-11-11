"""Ricks-style story director for 16:9 YouTube.

Adapts the Universal Cinematic Pipeline V5.0 story director to the
format that made Ricks Clips work, without copying that channel:

* one true story, told in plain language
* a hook in the first 3 seconds
* one idea per shot, 3.0-6.5 seconds per shot
* a twist at 70-85% of the runtime, then a short payoff
* native 1920x1080, 24 fps — never a cropped 9:16 Short

The renderer stays data-driven (V5 principle): a script goes in,
a ProductionScenePackage comes out. No per-story renderer code.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "youtube_16x9.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Shot:
    shot_id: str
    shot_number: int
    shot_type: str
    duration_sec: float
    purpose: str
    story_beat_id: str
    script_line: str
    camera_is_pov: bool = False
    location_id: str = "LOC_GENERIC"
    visible_state: str = ""
    staging: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScenePackage:
    title: str
    slug: str
    aspect_ratio: str
    width: int
    height: int
    fps: int
    hook: str
    twist: str
    payoff: str
    shots: list[Shot] = field(default_factory=list)
    total_duration_sec: float = 0.0
    script_sha256: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["shots"] = [s.to_dict() for s in self.shots]
        return d


# Words that look like structure but are not story content. V5 learned
# this the hard way with Vietnamese scripts: never split on these.
META_KEYWORDS = {
    "TẬP", "BƯỚC", "HẾT", "LƯU Ý", "PHONG CÁCH", "KỊCH BẢN",
    "CHAPTER", "STEP", "NOTE", "STYLE", "SCRIPT", "END",
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")


def _clean_lines(script: str) -> list[str]:
    lines: list[str] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        head = line.split(":", 1)[0].strip().upper()
        if head in META_KEYWORDS:
            continue
        lines.append(line)
    return lines


def _sentences(script: str) -> list[str]:
    parts: list[str] = []
    for line in _clean_lines(script):
        parts.extend(p for p in _SENTENCE_SPLIT.split(line) if p.strip())
    return [p.strip() for p in parts]


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled-story"


def _shot_type_for(index: int, total: int) -> str:
    if index == 0:
        return "HOOK_CLOSEUP"
    if index == total - 1:
        return "PAYOFF_WIDE"
    if index == total - 2:
        return "TWIST_REVEAL"
    return "MEDIUM_ACTION"


class RicksStyleDirector:
    """Turn a raw script into a 16:9 shot plan with a hook and a twist.

    The director does NOT call any AI service. It is the deterministic,
    testable core: given the same script and config it always returns
    the same package. AI script intelligence (Gemini in V5) can supply
    the hook/twist/story text; this class validates and stages it.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        story = self.config["story"]
        self.shot_min = float(story["shot_duration_sec"]["min"])
        self.shot_max = float(story["shot_duration_sec"]["max"])
        self.shot_target = float(story["shot_duration_sec"]["target"])
        self.hook_seconds = float(story["hook_seconds"])
        twist = story["twist_position_pct"]
        self.twist_min = float(twist["min"]) / 100.0
        self.twist_max = float(twist["max"]) / 100.0

    def analyze_script(self, script: str, title: str) -> ScenePackage:
        if not script or not script.strip():
            raise ValueError("script must not be empty")
        if not title or not title.strip():
            raise ValueError("title must not be empty")

        sentences = _sentences(script)
        if len(sentences) < 3:
            raise ValueError(
                "script needs at least 3 sentences: a hook, a middle, and a payoff"
            )

        hook = sentences[0]
        payoff = sentences[-1]
        # Twist: the sentence that changes what the viewer believed.
        # Deterministically pick the sentence nearest 75% through the
        # script — callers that know the real twist should pass it in
        # via build_package_with_twist() instead of relying on this.
        twist_index = max(1, math.ceil((len(sentences) - 1) * 0.75))
        twist = sentences[twist_index]

        shots: list[Shot] = []
        for i, sentence in enumerate(sentences):
            beat = "hook" if i == 0 else "payoff" if i == len(sentences) - 1 else (
                "twist" if i == twist_index else "escalation"
            )
            shots.append(
                Shot(
                    shot_id=f"SH{ i + 1:02d}",
                    shot_number=i + 1,
                    shot_type=_shot_type_for(i, len(sentences)),
                    duration_sec=self.shot_target,
                    purpose=beat.upper(),
                    story_beat_id=f"BEAT_{i + 1:02d}_{beat.upper()}",
                    script_line=sentence,
                    staging={
                        "action_description": sentence,
                        "ideas_per_shot": 1,
                        "caption": sentence,
                    },
                )
            )

        total = round(len(shots) * self.shot_target, 2)
        video = self.config["video"]
        return ScenePackage(
            title=title.strip(),
            slug=_slug(title),
            aspect_ratio=video["aspect_ratio"],
            width=int(video["width"]),
            height=int(video["height"]),
            fps=int(video["fps"]),
            hook=hook,
            twist=twist,
            payoff=payoff,
            shots=shots,
            total_duration_sec=total,
            script_sha256=hashlib.sha256(script.encode("utf-8")).hexdigest(),
        )

    def validate(self, package: ScenePackage) -> list[str]:
        """Return a list of problems. Empty list means the package passes."""
        problems: list[str] = []
        if package.aspect_ratio != "16:9":
            problems.append(f"wrong aspect ratio: {package.aspect_ratio} (must be 16:9)")
        if (package.width, package.height) != (1920, 1080):
            problems.append(
                f"wrong resolution: {package.width}x{package.height} (must be 1920x1080)"
            )
        if not package.hook:
            problems.append("no hook: first shot must state the hook in under 3 seconds")
        if package.shots and package.shots[0].duration_sec > self.hook_seconds + 1.5:
            problems.append("hook shot is too long to land in the first 3 seconds")
        for shot in package.shots:
            if shot.duration_sec > self.shot_max:
                problems.append(f"{shot.shot_id} is too long: {shot.duration_sec}s (max {self.shot_max}s)")
            if shot.duration_sec < self.shot_min:
                problems.append(f"{shot.shot_id} is too short: {shot.duration_sec}s (min {self.shot_min}s)")
            if len(shot.script_line) > 120:
                problems.append(f"{shot.shot_id} packs more than one idea into a shot")
        if package.total_duration_sec > 0:
            twist_at = self._twist_position(package)
            if twist_at is not None and not (self.twist_min <= twist_at <= self.twist_max):
                problems.append(
                    f"twist lands at {twist_at:.0%} of the runtime "
                    f"(must be {self.twist_min:.0%}-{self.twist_max:.0%})"
                )
        return problems

    @staticmethod
    def _twist_position(package: ScenePackage) -> float | None:
        elapsed = 0.0
        for shot in package.shots:
            if shot.purpose == "TWIST":
                return (elapsed + shot.duration_sec / 2) / package.total_duration_sec
            elapsed += shot.duration_sec
        return None


if __name__ == "__main__":
    script_path = Path(sys.argv[1])
    title = sys.argv[2] if len(sys.argv) > 2 else script_path.stem
    pkg = RicksStyleDirector().analyze_script(
        script_path.read_text(encoding="utf-8"), title
    )
    problems = RicksStyleDirector().validate(pkg)
    print(json.dumps(pkg.to_dict(), indent=2, ensure_ascii=False))
    if problems:
        print("\nVALIDATION PROBLEMS:", file=sys.stderr)
        for p in problems:
            print(f" - {p}", file=sys.stderr)
        raise SystemExit(1)
