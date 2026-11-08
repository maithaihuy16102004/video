# VISUAL STYLE BIBLE V4.2.2
## Authoritative Cinematic Style, Anatomy, Lighting & Typography Specification
### Universal Motion Canvas × Three.js Production Engine

**Document Version:** 4.2.2  
**Approved Baseline:** Odeonsplatz V4 Three.js + Motion Canvas Proof  
**Engine Architecture:** 100% Data-Driven (`CharacterDNA` + `LocationDNA` -> `UniversalCharacterEngine` + `UniversalWorldEngine`)  

---

## 1. CORE PHILOSOPHY: ZERO MURKINESS, HIGH CONTRAST, READABLE CRAFT

The human review of V4.2.1 correctly identified that dark, muddy, under-lit environments and primitive geometric stick figures destroy production value. The V4 Odeonsplatz proof succeeded because it balanced **historical authenticity**, **organic character construction**, and **clean, high-exposure architectural rendering**.

Every frame rendered by the Universal Engine must satisfy:
1. **Luminance Separation**: Characters must always maintain at least a 3.5:1 luminance contrast ratio against their backdrop. Never place dark navy costumes against dark charcoal walls without rim lighting.
2. **Organic Anatomy**: No raw stick lines with sharp disjointed hinges. All limbs have anatomically motivated thickness, tapered sleeves/cuffs, 2-bone analytical IK flexions, and articulated hands.
3. **Architectural Density**: Backgrounds must feature molded cornices, base plinths, joinery, reflections, and dynamic environmental particles (rain/dust/ripples).
4. **Legibility First**: Every text prop, document scroll, and on-screen card must display authentic, legible Vietnamese Unicode characters. Zero fictional glyphs or unreadable scrawls.

---

## 2. COLOR PALETTES & LIGHTING MATRIX

### 2.1 The Odeonsplatz Benchmark Lighting Formula
To eliminate muddy gloom, every Three.js environment must adhere to this tri-tone lighting model:

| Role | Color (Hex / RGB) | Intensity | Purpose |
| :--- | :--- | :--- | :--- |
| **Warm Key Light** | `#FDF5E6` / `(0.78, 0.74, 0.66)` | 1.6 – 1.85 | Warm directional sunlight / main practical illumination |
| **Cool Sky Fill** | `#6B8096` / `(0.42, 0.38, 0.33)` | 0.95 – 1.15 | Soft ambient bounce preventing black shadow clipping |
| **Ink Line Accents** | `#161412` / `(0.24, 0.21, 0.18)` | Contrast stroke | Structural joints, arch contours, character silhouettes |
| **Rim / Edge Light** | `#D8E4F2` | 0.65 – 0.85 | Separates foreground figures from background architecture |

### 2.2 Material Reflectivity & Specular Ground
- **Wet Cobblestone / Timber Decks**: `roughness: 0.35 - 0.45`, `metalness: 0.15 - 0.25`. Catches specular highlights from sky and practical lights.
- **Modern Epoxy Floors**: `roughness: 0.22`, `metalness: 0.65`. Reflects overhead LED luminaires and server status indicators.
- **Tatami Mats**: `roughness: 0.85`, `metalness: 0.05`. Warm straw texture `#827B5E` with dark woven borders.

---

## 3. CHARACTER ANATOMY & RIGGING SPECIFICATION

### 3.1 Proportions
All characters conform to standard proportions defined in `CharacterDNA`:
- **Head Ratio**: Exactly 0.27 – 0.28 of total standing height (e.g. Head diameter = 72px for a 260px figure).
- **Neck**: Visible tapered trapezoid (width 12px at jaw, 16px at base) connecting skull to collar. Zero floating heads.
- **Shoulders**: Width 48px – 56px based on build (`AVERAGE`, `BROAD`, `SLENDER`).
- **Torso**: Layered organic vector with upper chest, mid-waist taper, and hip foundation.
- **Limb Thickness**: 10px – 13px at upper arm/thigh, tapering to 8px – 10px at forearm/shin.

```
       [ Head: 0.28 Ratio ]
             \      /
          [ Neck 14px ]
         /              \
    [ Shoulder Width: 52px ]
    |                      |
    |   [ Torso Jacket ]   |
    |                      |
    [ Belt / Obi / Sash ]
     /                    \
  [ Left Thigh ]        [ Right Thigh ]
      |                      |
    (Knee)                 (Knee)
      |                      |
  [ Left Shin ]         [ Right Shin ]
      |                      |
  [ Foot / Shoe ]       [ Foot / Shoe ]
```

### 3.2 Articulated Extremities
- **Hands**: 5-finger articulated anatomy supporting semantic grip poses:
  - `open_expressive`: Natural fan with thumb abduction.
  - `tight_grip`: Enclosed fist wrapping around handrails, ropes, or tools.
  - `pinch_high`: Delicate two-finger grip holding document envelopes and paper scrolls.
  - `two_handed_present`: Both palms cupped beneath an offering.
- **Feet & Footwear**:
  - `waraji_sandals`: Woven straw sole with thong cords (`#C29B38`).
  - `tabi_socks`: Split-toe white ceremonial socks (`#FFFFFF`).
  - `leather_shoes`: Polished low-quarter shoes with sole separation line.
  - `sneakers`: Modern rubber-sole athletic shoes with accent trims.
  - `bare_foot`: Anatomical heel and toe contour with dynamic mud splatter when soaked.

---

## 4. ARCHITECTURAL DENSITY & GRAMMARS

### 4.1 Traditional East Asian (`TRADITIONAL_EAST_ASIAN`)
- **Joinery**: Visible post-and-beam mortise and tenon joints (`#3E2D22`).
- **Curved Eaves**: S-curved roof ridges with ornamental tile finials.
- **Shoji Screens**: Translucent mullion grid with warm interior backlighting (`emissive: 0x775522`).
- **Lanterns (Chōchin / Andon)**: Cylindrical and rectangular fixtures with organic sinusoidal flicker (`freq: 2.5 - 4.0 Hz`).
- **Bridges (Taiko-bashi)**: Curved deck with individual planks, vertical balusters, and bronze post finials (giboshi).

### 4.2 Neoclassical European (`NEOCLASSICAL_EUROPEAN`)
- **Plinths**: Multi-tier stepped stone bases (3+ steps).
- **Colonnades**: Fluted columns with molded Tuscan/Corinthian bases and capitals.
- **Florentine Arches**: Molded archivolts with protruding decorative keystones.
- **Statues**: Heroic bronze figures with authentic oxidized verdigris patina (`#36584E`).
- **Street Furniture**: Cylindrical Litfaßsäule advertising columns with readable proclamation placards.

### 4.3 Modern Industrial Tech (`MODERN_INDUSTRIAL_TECH`)
- **Flooring**: Polished reflective epoxy floor with yellow/cyan boundary guidance lines.
- **Server Arrays**: Matte-black rack cabinets with rhythmic pulsing status LEDs (green/cyan).
- **Partitions**: Glass walls with 40% transmission and frosted safety decal bands.
- **Workcells**: Articulated robotic chassis, cable conduits, and holographic target rings.

### 4.4 Rural Outdoor (`RURAL_OUTDOOR`)
- **Terrain**: Multi-textured soil, dirt roads, and grassy embankments.
- **Water**: Animated wave normal displacement with specular sky reflection.
- **Atmosphere**: 3D particle rain (3,000+ depth-sorted streaks) and ground mist.

---

## 5. TYPOGRAPHY & ON-SCREEN GRAPHICS

### 5.1 Document Props
All text rendered on documents, letters, tablets, and placards MUST be genuine, readable Vietnamese Unicode.
- **Edo Courier Letter**:
  - Font: High-contrast legible sans/serif.
  - Body:
    > "Aiko thân mến,  
    > Nhớ mang theo ô.  
    > Chiều nay mưa to!"
  - Wax Seal: Crimson cinnabar seal (`#C8281E`) at envelope junction.
- **Modern Tablet**:
  - Holographic UI with cyan borders (`#00D2FF`), telemetry charts, and battery status.

### 5.2 Subtitles & Motion Graphics
- **Positioning**: Safe-margin bottom center (Y = 945px, Height = 75px).
- **Backdrop**: Semi-transparent dark pill (`rgba(16, 20, 26, 0.82)`) with rounded corners (r = 18px).
- **Typography**: Bold 28px "Segoe UI", Arial, sans-serif with subtle text drop-shadow.
- **Color Coding**:
  - Lead Protagonist: Warm Amber Gold (`#FFD24D`)
  - Secondary / Supporting: Sakura Coral (`#FF8FA3`)
  - Tech / Specialist: Electric Cyan (`#00D2FF`)
  - Authority / Formal: Crisp White (`#F5F5F5`)
