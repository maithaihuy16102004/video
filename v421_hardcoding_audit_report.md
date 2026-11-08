# FORENSIC AUDIT OF V4.2.1: DATA-DRIVEN VS HARDCODING ASSESSMENT

**Author:** Antigravity Universal Systems Engineer  
**Workspace:** `D:/Agent`  
**Date:** November 8, 2026  
**Status:** AUDIT COMPLETE — ADMISSION OF HARDCODING & DATA-DRIVEN ARCHITECTURE DEVIATION  

---

## 1. EXECUTIVE ASSESSMENT & VERDICT

The human reviewer's rejection of V4.2.1 is **100% technically and architecturally accurate**:
* Although V4.2.1 successfully replaced the offline PyCairo frame loop with headless Chrome WebGL Three.js + 2D canvas, **the implementation was NOT truly data-driven**.
* Instead of building a universal compiler that translates an arbitrary `ProductionScenePackage` into procedural Three.js worlds and CharacterDNA instances, three separate hardcoded scenes were constructed directly in TypeScript:
  1. `motioncanvas/three/EdoBridgeWorld.ts` (Hardcoded bridge trestles, broken plank at x=0.2, canal)
  2. `motioncanvas/three/EdoHouseWorld.ts` (Hardcoded machiya veranda, shoji positions, chochin lanterns)
  3. `motioncanvas/three/ModernLabWorld.ts` (Hardcoded server racks, robot chassis, glass partition)
  4. `render_runner.html`: Contains hardcoded scene dispatchers (`renderEdoBridgeCharacters`, `renderEdoHouseCharacters`, `renderModernLabCharacters`) with manual keyframe numbers and specific character references (`haru`, `aiko`, `founder`).

**Verdict: FAILED GENERALIZATION TEST.**  
This architecture could not render a 4th or 5th unseen script without manual source-code editing.

---

## 2. CALL-CHAIN & SOURCE-CODE TRACE OF THE HARDCODING

### 2.1. The Dispatch Flaw in `render_runner.html`
* **File:** `D:/Agent/render_runner.html`
* **Lines 49–60:**
  ```javascript
  window.setupScene = function(sceneType, config = {}) {
    if (sceneType === 'edo_bridge') {
      activeWorld = new EdoBridgeWorld(w, h);
    } else if (sceneType === 'edo_house') {
      activeWorld = new EdoHouseWorld(w, h);
    } else if (sceneType === 'modern_lab') {
      activeWorld = new ModernLabWorld(w, h);
    }
  };
  ```
  *Analysis:* `sceneType` was an enumerated hardcoded string instead of ingesting a dynamic `LocationDNA` specification.

* **Lines 73–81:**
  ```javascript
  if (activeSceneType === 'edo_bridge') {
    renderEdoBridgeCharacters(timeSeconds, camera);
  } else if (activeSceneType === 'edo_house') {
    renderEdoHouseCharacters(timeSeconds, camera);
  } else if (activeSceneType === 'modern_lab') {
    renderModernLabCharacters(timeSeconds, camera);
  }
  ```
  *Analysis:* Character acting, camera positions, dialogue subtitles, and props were hardcoded per scene rather than being evaluated from the `EventGraph`, `ActorEntity`, and `ActionCue` timeline in the `ProductionScenePackage`.

---

### 2.2. Character Geometry & Anatomical Shortcomings
* **File:** `motioncanvas/components/PremiumStickCharacter.ts`
  * Head contour was still a stylized 2D path drawn directly in canvas without a unified skeletal hierarchy.
  * Limb animation used trigonometric sine oscillations instead of an Inverse Kinematics (IK) solver with foot-locking constraints and ground contact.
  * Clothing was drawn as ad-hoc shapes around the limbs rather than modular `CostumeDNA` layers.
  * On-screen letter in `drawOpenLetter()` contained Japanese kanji that appeared disconnected from the story script rather than rendered dynamically from the `ProductionScenePackage`'s document asset contract.

---

### 2.3. World Architecture & Visual Sparseness
* **Files:** `EdoBridgeWorld.ts`, `EdoHouseWorld.ts`, `ModernLabWorld.ts`
  * Architecture was built with isolated boxes and cylinders placed manually in 3D coordinates.
  * Lighting used low ambient fill (`0.035` fog, dark background colors `#28303C`, `#1C222C`), leading to dark, muddy, and visually sparse images where characters and actions were difficult to read.
  * Lack of a procedural architectural grammar meant every new location required an entirely new TypeScript file.

---

## 3. REQUIRED ROOT-LEVEL REMEDIATION

To achieve **ONE reusable application, ONE production renderer, MANY different stories, ZERO source-code edits per story**, we must implement:

1. **`UniversalCharacterEngine.ts`**:
   * A single, modular vector character engine driven 100% by `CharacterDNA`.
   * True skeletal hierarchy (Root, Spine, Neck, Head, Shoulder, Elbow, Wrist, 5 Fingers, Hip, Knee, Ankle, Foot).
   * 2D Analytical Inverse Kinematics (IK) with foot locking on ground plane.
   * Modular clothing and accessories layers.
   * Dynamic action library (`sprint`, `walk`, `slip_fall`, `climb_hang`, `present_item`, `laugh`, `gestural_talk`, `idle_observe`).
   * New characters require **ZERO TypeScript edits** — only JSON `CharacterDNA`.

2. **`UniversalWorldEngine.ts`**:
   * A single procedural Three.js world engine driven 100% by `LocationDNA`.
   * Procedural architectural grammars:
     - `TRADITIONAL_EAST_ASIAN` (Post-and-beam, bracket sets, curved tile eaves, shoji/lattice, paper lanterns, engawa verandas, arched wooden bridges).
     - `NEOCLASSICAL_EUROPEAN` (Podiums, stone colonnades, Corinthian capitals, Florentine arches, entablatures, statues).
     - `MODERN_INDUSTRIAL_TECH` (Reflective floors, server arrays, structural gantries, glass partitions, conduit rails, diagnostic lights).
     - `RURAL_OUTDOOR` (Embankments, waterways, terrain, foliage, fences).
   * Motivated cinematic lighting presets (Overcast daylight, Golden hour, Night lanterns, Interior candlelight, High-tech clinical).
   * High visual density, rich materials (PBR standard with proper roughness and metalness), and atmospheric fog/rain.
   * New environments require **ZERO TypeScript edits** — only JSON `LocationDNA`.

3. **Unified Scene Orchestrator in `render_runner.html`**:
   * Ingests the full `ProductionScenePackage` JSON dynamically.
   * Generates world from `package.scene_world.location_dna`.
   * Spawns all actors from `package.actors` using `CharacterDNA`.
   * Drives camera along keyframes from `package.camera.keyframes`.
   * Evaluates character actions and subtitles from `package.story_beats` and `package.unified_event_timeline`.
   * Renders frames deterministically.
