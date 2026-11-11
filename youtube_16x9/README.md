# Video AI — Ricks-style, 16:9 for YouTube

A careful 16:9 adaptation of the Universal Cinematic Pipeline V5.0
(Premium Stickman Cinematic, Style B), re-tuned for the format that
works on Ricks Clips (@RicksClips3000): one true story, a hook in the
first 3 seconds, simple 3D stickman characters, and a surprise ending.

**Not affiliated with Ricks Clips.** No characters, audio, or footage
from that channel are used. This is an original implementation inspired
by the format, built on the project's own V5 engine.

## What changed vs. the Shorts version

|  | Shorts (9:16) | This version (16:9 YouTube) |
|---|---|---|
| Frame | 1080x1920 vertical | **1920x1080, 24 fps, native — never cropped** |
| Shot length | often 11–16 s (Episode01 drafts) | **3.0–6.5 s, target 4.5 s, 1 idea per shot** |
| Structure | long beats | **Hook (0–3 s) → setup → escalation → twist at 70–85% → payoff** |
| Captions | small, edge-to-edge | **lower third, inside 80% safe title, ≥64 px at 1080p, max 2 lines × 42 chars** |
| Audio | — | **48 kHz, AAC 192k, -14 LUFS, true peak -1 dBFS** |
| Export | MP4 | **H.264 High, 12 Mbps, faststart + 1280x720 thumbnail + contact sheet** |
| Gate | — | **Quality gate blocks wrong aspect, wrong resolution, long shots, missing hook/twist, caption overflow** |

## Layout

```
config/youtube_16x9.json        Locked 16:9 profile — single source of truth
pipeline/ricks_story_director.py  Script -> shot plan (hook / twist / payoff)
pipeline/quality_gate_16x9.py    Package + rendered-video checks (ffprobe)
pipeline/render_16x9.py          FFmpeg command builder (1920x1080, -14 LUFS)
motioncanvas/contract/VisualStyleBible16x9.ts  Style B tokens, 16:9 safe frames
examples/script_eiffel_tower_twice.txt        Sample true story (8 sentences)
examples/eiffel_tower_twice_package.json      Generated shot plan for that story
tests/test_16x9.py               11 unit tests
```

## Quick start

```bash
python3 -m unittest discover -s tests -v

# Build a shot plan from any script
python3 pipeline/ricks_story_director.py examples/script_eiffel_tower_twice.txt "He sold the Eiffel Tower. Twice." > out/package.json

# Check it before rendering
python3 -c "import json; from pipeline.quality_gate_16x9 import check_package; print(check_package(json.load(open('out/package.json'))))"
```

The full V5 render path is unchanged and still applies: Motion Canvas +
Three.js WebGL in headless Chrome (1920x1080 @ 24 fps) piped to FFmpeg.
See `config/youtube_16x9.json` and the V5 docs in Drive
(`Universal_Cinematic_Pipeline_V50_Production_Review`) for the engine
architecture. **Do not render final frames with PyCairo, Pillow, or OpenCV.**

## Rules that are locked

1. Render natively at 1920x1080. Never pillarbox or letterbox a 9:16 Short.
2. All critical action inside the inner 84% frame; captions inside 80%.
3. One idea per shot. If a sentence is over 84 characters, split the shot.
4. Twist must land at 70–85% of the runtime.
5. Run the quality gate before uploading. A failed gate means do not publish.
