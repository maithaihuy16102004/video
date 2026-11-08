# V5 CHARACTER ASSET LIBRARY
## STYLE B: PREMIUM STICKMAN CINEMATIC COMPONENT CATALOG
**VERSION:** V5.0.0  
**IMPLEMENTATION:** `motioncanvas/contract/CharacterDNA.ts` & `motioncanvas/components/UniversalCharacterEngine.ts`

---

## 1. 12-JOINT SKELETAL RIG SPECIFICATION

Every character in the engine is animated through a unified 12-joint skeletal hierarchy:

| Joint Name | Anatomical Role | Degree of Freedom / Solver |
| :--- | :--- | :--- |
| **`Root`** | Pelvic base center & ground height | Translation `(x, y)` |
| **`Torso`** | Spine / chest column & breath sway | Analytical tilt `torsoTilt` |
| **`Neck`** | Sub-cervical pivot | Rotation & offset |
| **`Head`** | Skull contour anchor | 5 distinct silhouettes |
| **`Shoulder (L/R)`** | Scapular deltoid anchors | Bi-lateral offset `(±0.48 * sw)` |
| **`Elbow (L/R)`** | Forearm hinge | Analytical 2-Bone IK solver |
| **`Wrist (L/R)`** | Carpal hinge | Dual-axis rotational joint |
| **`Hand (L/R)`** | 5-finger articulated grip/open | Palm + Thumb + 4 Phalanges |
| **`Hip (L/R)`** | Pelvic acetabulum socket | Bi-lateral anchor `(±0.28 * sw)` |
| **`Knee (L/R)`** | Lower limb hinge | Analytical 2-Bone IK solver |
| **`Ankle (L/R)`** | Tarsal hinge | Rotational foot joint |
| **`Foot (L/R)`** | Ground contact & foot-locking | Clamped to ground plane `y = 0` |

---

## 2. 5 CORE LAUNCH ARCHETYPES (100% DATA-DRIVEN)

### 2.1 Archetype 1: `young_courier` (Edo Young Messenger — Haru)
- **Character ID**: `char_courier_haru`
- **Head Silhouette**: `round_youth` (Youthful, expressive wide eyes).
- **Proportions**: Head ratio `0.28`, standing height `250px`, shoulder width `50px`.
- **Hair**: `edo_topknot` (Chonmage with white paper cord tie).
- **Costume**: `edo_hanten_courier` (Deep indigo hanten robe, bleached hemp collar, crimson crest, dark navy trousers).
- **Footwear**: `waraji_sandals` (Woven straw waraji with dark cords, single-sandal loss state supported).
- **Held Props**: Sealed oiled-paper letter scroll with cinnabar red wax seal (`letter_scroll_sealed`), leather satchel.
- **Voice Mapping**: `vieneu-Quang Sơn` (Natural young spirited voice).

### 2.2 Archetype 2: `noblewoman` (Edo Noble Lady — Aiko)
- **Character ID**: `char_noble_aiko`
- **Head Silhouette**: `delicate_heart` (Refined feminine jawline, almond eyes, delicate brows).
- **Proportions**: Head ratio `0.26`, standing height `260px`, shoulder width `46px`.
- **Hair**: `edo_shimada` (Traditional high shimada coiffure with coral kanzashi hairpin).
- **Costume**: `edo_kimono_formal` (Burgundy silk with gold floral embroidery, peach blossom obi sash with gold obijime cord).
- **Footwear**: `tabi_socks` (Pure white split-toe tabi).
- **Held Props**: Japanese oiled-paper umbrella / parasol (`umbrella_parasol`).
- **Voice Mapping**: `vieneu-Trúc Ly` (Warm, expressive feminine voice).

### 2.3 Archetype 3: `detective_scholar` (Victorian Scholar / Detective — Arthur)
- **Character ID**: `char_scholar_arthur`
- **Head Silhouette**: `oval_gaunt` (High cheekbones, intense gaze, furrowed brow).
- **Proportions**: Head ratio `0.25`, standing height `275px`, shoulder width `56px`.
- **Hair**: `side_sweep_1914` (Side-parted chestnut hair, handlebar mustache).
- **Accessories**: `glasses_round` (Antique round spectacles).
- **Costume**: `victorian_frock_coat` (Charcoal wool frock coat, slate waistcoat, crimson silk cravat, dark wool trousers).
- **Footwear**: `leather_shoes` (Polished black oxford shoes).
- **Held Props**: Brass pocket watch (`pocket_watch`), carved walking cane (`walking_cane`).
- **Voice Mapping**: `vieneu-Hải Đăng` (Crisp, authoritative analytical voice).

### 2.4 Archetype 4: `tech_founder` (Modern Engineer / Developer — Minh)
- **Character ID**: `char_founder_minh`
- **Head Silhouette**: `square_jaw` (Resolute square jaw, straight sharp brows, slight stubble).
- **Proportions**: Head ratio `0.27`, standing height `265px`, shoulder width `58px`.
- **Hair**: `modern_crop` (Contemporary textured short crop).
- **Costume**: `modern_hoodie` (Slate tech-blue hoodie with burnt orange cords, kangaroo pocket, dark selvedge denim jeans).
- **Footwear**: `sneakers` (Minimalist white sneakers).
- **Held Props**: Ceramic coffee mug (`steaming_coffee_cup`), high-res tablet computer (`tablet_computer`).
- **Voice Mapping**: `vieneu-Thiện Minh` (Warm, thoughtful modern voice).

### 2.5 Archetype 5: `polar_scientist` (Arctic / Antarctic Field Specialist — Elena)
- **Character ID**: `char_scientist_elena`
- **Head Silhouette**: `athletic_lean` (Streamlined aerodynamic profile, alert intense blue eyes).
- **Proportions**: Head ratio `0.26`, standing height `265px`, shoulder width `52px`.
- **Hair**: `ponytail_athletic` (High swept ponytail with weather goggles).
- **Accessories**: `goggles` (Polar tinted hazard goggles).
- **Costume**: `polar_hazard_suit` (Arctic safety orange insulated parka with reflective yellow bands and thermal utility harness).
- **Footwear**: `snow_boots` (Deep-tread insulated polar snow boots).
- **Held Props**: Multi-spectral scientific field scanner (`scientific_scanner`).
- **Voice Mapping**: `vieneu-Mai Anh` (Clear, energetic specialist voice).

---

## 3. COMPOSABILITY & EXTENSION RULES

1. **Zero New TypeScript Requirement**: Any unseen script describing a new character (e.g., a 1930s Shanghai stationmaster or a 2050 desert weather operator) is synthesized entirely through `CharacterDNA_V5` JSON by selecting head contour, hairstyle, palette, and costume archetype.
2. **Strict Silhouette Test**: Every character must be unambiguously identifiable as a silhouette under 100% black fill before being approved into production.
3. **No External Dependencies**: All geometry is rendered vectorially through the HTML5 canvas context in Motion Canvas.
