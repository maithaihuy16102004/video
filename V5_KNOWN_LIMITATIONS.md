# V5 KNOWN LIMITATIONS & FUTURE ROADMAP
## Premium Stickman Cinematic Engine V5.0

**Workspace:** `D:/Agent`  
**Date:** 2026-11-08  
**Document Version:** 1.0.0

---

## 1. Current System Boundaries & Known Limitations

While the V5.0 engine achieves full autonomous generalization across diverse stories, genres, and environments, the following technical boundaries and operational considerations are documented for production teams:

### 1.1 Character Rigging & Staging Limits
- **Simultaneous On-Screen Actors:** The engine supports up to 4 simultaneous active characters on screen with automated 3D-to-2D depth sorting. Staging large crowds (> 10 named characters) is handled via background silhouette clusters rather than full 12-joint skeletal IK instances.
- **Extreme Perspective Angles:** Characters are rendered as stylized 2D ink figures within a 3D coordinate space. While camera rotation up to $\pm 60^\circ$ yaw and $\pm 35^\circ$ pitch is naturally supported, direct vertical top-down views (bird's eye $90^\circ$) require specialized top-down rig projection.

### 1.2 3D World Kit Coverage
- **Built-in Procedural Environments:** The engine currently features 10 fully procedural Three.js environments (`RAIL_STATION`, `HOSPITAL_ER`, `DESERT_STATION`, `CAFE`, `ANTARCTIC`, `VICTORIAN_THAMES`, `EDO_BRIDGE`, `EDO_HOUSE`, `NEOCLASSICAL`, `ROBOTICS_LAB`).
- **Unseen Historical Settings:** When an unseen script specifies a highly niche setting (e.g. Ancient Maya or 17th Century Amsterdam), the semantic resolver maps it to the closest architectural category (e.g. `NEOCLASSICAL` or `TRADITIONAL_EAST_ASIAN`) unless custom Three.js geometry is declared in the package.

### 1.3 Memory & Sequence Duration
- **Single-Pass Rendering:** Sequences up to 180 seconds render deterministically in a single pass without memory degradation. For full-length documentary features (> 10 minutes), the studio pipeline automatically chunks scenes into 60-second sequence packages before final FFmpeg concatenation.

### 1.4 Voice & Paralinguistic Audio
- **VieNeu-TTS Studio Voices:** 25 high-definition 48kHz Vietnamese voices are supported natively. Natural paralinguistic tags (`[thở dài]`, `[cười]`, `[hắng giọng]`) enrich emotional expression. Scripts containing archaic Sino-Vietnamese dialectal terms may occasionally require phonetic spelling hints for optimal cadence.

---

## 2. V5.1 Enhancement Roadmap

1. **Dynamic Three.js Asset Loader:** Support for external glTF/GLB models to supplement procedural geometry.
2. **Multi-Camera Automated Cutting:** Dynamic real-time switching between master, over-the-shoulder, and reaction close-up shots within a single continuous dialogue beat.
3. **Advanced Cloth Simulation:** Secondary physics on character robes, coats, and hair strands using lightweight Verlet integration.
