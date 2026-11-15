"""Staging-duplication audit (round-6 detector, R2-C1).

Measures what the planner's subject-scoped repeated-framing
warning cannot: near-duplicate RENDERED framings across ALL shot
pairs -- adjacent, triplets, and non-adjacent A-B-A repeats.
The method is the independent tester's, pinned: per-shot
mid-frame, 160x90 grayscale, mean absolute pixel difference
(MAD); a pair under 12.0 is a near-duplicate.

The audit reads the job's rendered frames (frames/shot_NNN) and
timeline.json. It is a non-gating diagnostic: the planner's
viewpoint-side alternation is the fix; this audit is the
measurement that proves the fix worked (or that a new cluster
appeared). It never invents frames: shots without rendered
frames are skipped and counted.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

MAD_THRESHOLD = 12.0
PROBE_SIZE = (160, 90)


def probe_frame(path) -> np.ndarray:
    """One frame reduced to the comparison probe (grayscale 160x90)."""
    with Image.open(path) as image:
        return np.asarray(
            image.convert("L").resize(PROBE_SIZE), dtype=np.float32)


def flag_duplicate_pairs(frames, threshold=MAD_THRESHOLD):
    """All-pairs MAD over probe frames.

    ``frames`` is a list of (shot_index, probe array). Returns a
    list of {a, b, mad, adjacent} sorted by MAD ascending, keeping
    only pairs under ``threshold``.
    """
    flagged = []
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            a_idx, a_arr = frames[i]
            b_idx, b_arr = frames[j]
            mad = float(np.abs(a_arr - b_arr).mean())
            if mad < threshold:
                flagged.append({
                    "a": int(a_idx), "b": int(b_idx),
                    "mad": round(mad, 2),
                    "adjacent": bool(b_idx == a_idx + 1),
                })
    flagged.sort(key=lambda p: p["mad"])
    return flagged


def _clusters(pairs):
    """Connected components over flagged pairs (triplets+ = clusters)."""
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for pair in pairs:
        parent.setdefault(pair["a"], pair["a"])
        parent.setdefault(pair["b"], pair["b"])
        ra, rb = find(pair["a"]), find(pair["b"])
        if ra != rb:
            parent[ra] = rb
    groups = {}
    for node in parent:
        groups.setdefault(find(node), []).append(node)
    return [sorted(members) for members in groups.values()
            if len(members) >= 2]


def audit_staging_duplication(job_dir, threshold=MAD_THRESHOLD) -> dict:
    """Audit one job directory. Returns the machine-readable report."""
    job_dir = Path(job_dir)
    timeline_path = job_dir / "timeline.json"
    shots = []
    if timeline_path.exists():
        shots = json.loads(
            timeline_path.read_text(encoding="utf-8")).get("shots", [])
    frames = []
    skipped = []
    for index, _shot in enumerate(shots):
        shot_dir = job_dir / "frames" / ("shot_%03d" % index)
        pngs = sorted(shot_dir.glob("*.png")) if shot_dir.exists() else []
        if not pngs:
            skipped.append(index)
            continue
        frames.append((index, probe_frame(pngs[len(pngs) // 2])))
    pairs = flag_duplicate_pairs(frames, threshold=threshold)
    clusters = _clusters(pairs)
    measured = len(frames)
    return {
        "shots_measured": measured,
        "shots_skipped": skipped,
        "pairs_total": measured * (measured - 1) // 2,
        "threshold": threshold,
        "pairs": pairs,
        "pairs_flagged": len(pairs),
        "adjacent_flagged": sum(1 for p in pairs if p["adjacent"]),
        "non_adjacent_flagged": sum(
            1 for p in pairs if not p["adjacent"]),
        "clusters": clusters,
        "triplets_or_larger": [c for c in clusters if len(c) >= 3],
        "passed": len(pairs) == 0,
    }
