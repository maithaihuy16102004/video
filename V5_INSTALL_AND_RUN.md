# V5 INSTALLATION, RUN & OPERATING GUIDE
## Universal Cinematic Video Engine V5.0

**Workspace:** `D:/Agent`  
**Engine Version:** `Premium Stickman Cinematic — V5`

---

## 1. Quick Start (Prerequisites & Services)

The system consists of three co-operating services:
1. **Motion Canvas & Three.js WebGL Runtime** (Port 9000)
2. **Python Universal Studio Backend** (Port 8787)
3. **AI Clip Studio Web UI** (Port 4173)

### Service 1 — Motion Canvas & Three.js Runtime
```powershell
cd D:\Agent
npx vite --port 9000
```
*Health check:* Open `http://localhost:9000/render_runner.html` in browser.

### Service 2 — Python Universal Studio Backend
```powershell
cd D:\Agent
python -X utf8 pipeline/studio_api.py
```
*Health check:* `curl http://127.0.0.1:8787/health`

### Service 3 — Web Studio Frontend
```powershell
cd D:\Agent\sites\ai-clip-studio
npm run dev -- --port 4173
```
*Health check:* Open `http://localhost:4173/` in browser.

---

## 2. Using the System

1. Navigate to `http://localhost:4173/` in your browser.
2. In the left panel (**01 · Nội dung kịch bản**), paste any Vietnamese script.
3. Click **"Phân tích & Tạo Storyboard"**.
   - Gemini Intelligence will automatically discover characters, assign archetypes, detect locations, create 4–8 cinematic beats, and cast 48kHz VieNeu-TTS voices.
   - The cast badges will show real characters only (zero mangled syllables, zero meta-keywords).
4. Click **"Render mới 3 Draft 16:9 & Chọn bản Master"**.
   - The system synthesizes audio via VieNeu-TTS v3 Turbo 48kHz.
   - Puppeteer launches headless Chrome with hardware WebGL acceleration.
   - Three.js renders the 3D environment while Motion Canvas renders the 2D stickman performance.
   - FFmpeg compiles the frames into broadcast-ready H.264 MP4 videos and generates contact sheets.
5. Review the 3 draft options or download the Full HD 1080p Master.

---

## 3. Autonomous CLI Batch Rendering

To render an unseen Vietnamese script directly from the command line:

```powershell
cd D:\Agent

# Step 1: Analyze script and generate ProductionScenePackage
python -X utf8 -c "
from pipeline.universal.v5_story_director import V5UniversalStoryDirector
import json

director = V5UniversalStoryDirector()
pkg = director.analyze_script(open('path/to/script.txt', encoding='utf-8').read())
runner_pkg = director.compile_to_runner_package(pkg)
with open('output/custom_package.json', 'w', encoding='utf-8') as f:
    json.dump(runner_pkg, f, indent=2, ensure_ascii=False)
"

# Step 2: Render deterministic 1080p MP4 via ProductionRenderService
node scripts/production_render_service.mjs `
  --package output/custom_package.json `
  --audio output/audio.wav `
  --out output/custom_master.mp4
```

---

## 4. Key Directories & Contracts

- `motioncanvas/contract/VisualStyleBible.ts`: Design tokens (linework, colors, exposure, lighting).
- `motioncanvas/contract/CharacterDNA.ts`: 12-joint skeletal rig, 5 archetypes, facial features.
- `motioncanvas/components/UniversalCharacterEngine.ts`: 2-bone analytical IK solver, costume & prop renderer.
- `motioncanvas/three/UniversalWorldEngine.ts`: 10 semantic 3D Three.js environments.
- `pipeline/universal/v5_story_director.py`: Gemini intelligence & autonomous semantic extractor.
- `scripts/production_render_service.mjs`: Hardware WebGL Chrome frame capturer & FFmpeg pipe.
