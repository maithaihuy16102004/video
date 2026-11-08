# V5 VISUAL STYLE BIBLE
## PERMANENT ART DIRECTION LOCK: PREMIUM STICKMAN CINEMATIC — STYLE B
**ENGINE VERSION:** V5.0.0 Universal Engine  
**STATUS:** ACTIVE AND AUTHORITATIVE  
**APPLICATION SCOPE:** Motion Canvas (2D Scene Graph & Characters) + Three.js (3D World Architecture & Lighting)

---

## 1. CORE PHILOSOPHY & MANDATE

The permanent visual style of the application is **PREMIUM STICKMAN CINEMATIC — STYLE B**.

It achieves a high-end graphic novel aesthetic:
- **Expressive 2D Stickman Characters**: Simplified yet deeply expressive characters with distinct silhouettes, articulate 5-finger hands, organic tapered limbs, and nuanced facial features (pupils, eyebrows, emotive mouths).
- **Rich Stylized 3D Environments**: Built in Three.js with authentic historical/spatial grounding, physical materials (PBR roughness/metalness), motivated cinematic lighting, and atmospheric depth.
- **Zero Silhouette Confusion**: Every character archetype is immediately recognizable from silhouette alone, even without color.
- **Unified Deterministic Renderer**: Rendered exclusively via Motion Canvas 3.17.2 + Three.js WebGL in headless Chrome, synchronized with 48kHz multi-track VietNeu-TTS and Foley SFX.
- **Strict Prohibition**: No raw pipe-cleaner stick figures, no realistic human faces, no generic anime, and zero PyCairo/Pillow/OpenCV final frame generation.

---

## 2. CHARACTER ANATOMY & RIG CONTRACT

### 2.1 12-Joint Skeletal Hierarchy
All characters utilize a shared, fully articulated 12-joint skeletal rig:
1. `Root`: Base ground contact and hip center.
2. `Torso`: Flexible spinal column with organic lean and breath expansion.
3. `Neck`: Articulated pivot connecting torso to skull.
4. `Head`: Distinctive head contour (oval_gaunt, square_jaw, round_youth, delicate_heart).
5. `Left / Right Shoulders`: Deltoid flares with dynamic scapular positioning.
6. `Left / Right Elbows`: Analytical 2-bone IK hinge with smooth joint caps.
7. `Left / Right Wrists`: Dual-axis rotational joints.
8. `Left / Right Hands`: Articulated palm, opposable thumb, and 4 expressive phalanges.
9. `Left / Right Hips`: Pelvic socket anchors.
10. `Left / Right Knees`: Forward/backward analytical IK joints with natural bend limits.
11. `Left / Right Ankles`: Rotational tarsal anchors.
12. `Left / Right Feet`: Ground-locked plantar contacts with natural roll (heel-strike to toe-off).

### 2.2 Linework and Organic Polygons
- **Contour Stroke Width**: `3.8px` (vector antialiased).
- **Torso Silhouette**: `3.5px` stroke with intentional costume drapery.
- **Tapered Limbs**: Upper arm/thigh tapered smoothly to forearm/calf using Bézier quadrilaterals rather than simple stroked lines.
- **Joint Caps**: Rounded caps (`round` join and `round` cap) preventing sharp needle artifacts during extreme flexion.
- **Variable Weight**: Deltoid and quadriceps swell organically with load and anticipation.

### 2.3 Expressive Stylized Facial System
- **Eyes**: Sclera base, colored iris, dark pupil, specular catchlight, and dynamic eyelid creases.
- **Eyebrows**: Articulated Bézier curves capable of arched skepticism, intense furrowing, surprise, and grief.
- **Mouth Shapes**: Multi-phoneme visemes (neutral, open speech, wide smile, strained grimace, shock, determination).
- **Head Contours**:
  - `round_youth`: Youthful, optimistic, wide eyes (e.g. Haru the courier).
  - `delicate_heart`: Refined, elegant, arched brows (e.g. Aiko).
  - `oval_gaunt`: Intellectual, weary, sharp cheekbones (e.g. Victorian scholar/detective Arthur).
  - `square_jaw`: Resolute, grounded, strong jawline (e.g. Tech founder Minh).
  - `athletic_lean`: Dynamic, alert, streamlined profile (e.g. Polar specialist Elena).

---

## 3. 3D ENVIRONMENT & LIGHTING ARCHITECTURE

### 3.1 PBR World Geometry & Depth
Three.js constructs a persistent 3D world with foreground, midground, and background planes:
- **Depth Layers**:
  - *Foreground*: Archways, lanterns, handrails, or blurred framing props (`Z: -1.5` to `-0.5`).
  - *Midground / Action Stage*: Ground plane (`Y: 0.0`), characters, primary interaction objects (`Z: 0.0` to `2.5`).
  - *Background*: Architectural facades, streets, rivers, mountains, skyline (`Z: 3.0` to `35.0`).
- **Surface Materials**: Physical PBR shaders with custom roughness maps (0.55 - 0.75) and controlled metalness (0.05 - 0.20).

### 3.2 Lighting & Exposure Standards
- **Tone Mapping**: `THREE.ACESFilmicToneMapping` with exposure standard `1.45`.
- **Key-to-Ambient Ratio**: Enforced `2.5 : 1` to `3.0 : 1` for crisp volumetric form without crushing shadows.
- **Luminance Floor**:
  - Scene background luminance $\ge 0.45$.
  - Character action zone mean luminance $\ge 0.38$.
  - Dark night scenes use motivated cool moonlight (`#5A7B9C`) with warm incandescent practicals (`#FFAE42`) to maintain readability.
- **Shadows**: `THREE.PCFSoftShadowMap` with 2048×2048 shadow maps and soft bias.

---

## 4. CAMERA & CINEMATOGRAPHY RULES

### 4.1 Compositional Hierarchy
- **Safe Margins**: All critical action occurs within the inner 84% safe frame (8% margin on all borders).
- **Zero Action Occlusion**: Camera viewpoint selection must guarantee that pillars, handrails, walls, and crowds NEVER obstruct the primary character action.
- **Focal Lengths**:
  - *Extreme Wide*: 18mm (Establishing geography and historical scale).
  - *Wide*: 24mm (Environmental staging and multi-character interaction).
  - *Medium*: 35mm (Narrative action and dialogue staging).
  - *Hero Medium*: 50mm (Character performance, emotional inflection).
  - *Close-Up*: 85mm (Internal tension, object inserts, dramatic revelations).

---

## 5. MOTION GRAPHICS & ON-SCREEN GRAPHICS

- **Header / Badges**: Rounded container pills with `3px` solid stroke and `4px 4px 0px #172033` neo-brutalist shadow.
- **Palette Tokens**:
  - *Primary Accent*: `#FFD34E` (Cinematic Gold)
  - *Secondary Accent*: `#FF6B5E` (Coral Punch)
  - *Background Canvas*: `#F3F0E8` (Warm Editorial Parchment)
  - *Text Ink*: `#172033` (Deep Obsidian Blue)
  - *Success Green*: `#47BD75` (Verified Emerald)
- **Typography**: Clean, verified UTF-8 typography with zero character clipping or mangled diacritics.

---

## 6. SOUND DESIGN & AUDIO-VISUAL SYNCHRONIZATION

- **Voice**: VietNeu-TTS v3 Turbo 48kHz native neural synthesis (`speed_ratio = 1.00`). No pitch distortions or accelerated speech.
- **Foley & SFX**: Event-synchronized multi-track audio (footsteps, ambient rain, wooden creaks, paper rustles, mechanical clicks).
- **Ducking**: SFX and background music automatically duck `-14dB` during active speech segments.
- **Master LUFS**: YouTube broadcast standard `-14.0 LUFS` to `-15.2 LUFS`.

---

## 7. AUTOMATION & STYLE ENFORCEMENT

1. The frontend badge must always display: `Premium Stickman Cinematic — V5`.
2. Any newly submitted script automatically inherits these tokens via `VisualStyleBible.ts`.
3. Zero per-story CSS, HTML, or renderer code overrides are permitted.
