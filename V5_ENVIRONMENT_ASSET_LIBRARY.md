# V5 ENVIRONMENT ASSET LIBRARY
## MODULAR 3D WORLD ENVIRONMENTS & SEMANTIC RESOLVER
**VERSION:** V5.0.0  
**ENGINE COMPONENT:** `motioncanvas/three/UniversalWorldEngine.ts`

---

## 1. SEMANTIC RESOLUTION CONTRACT

The V5 Universal World Engine strictly resolves 3D environments from declarative `LocationDNA`. It enforces semantic consistency to ensure that no irrelevant or immersion-breaking assets ever appear:
- **Zero Server Racks in Cafés**: Cafés strictly construct timber acoustic slats, espresso machines, ceramic cups, and warm globe lamps.
- **Zero Vegetation / Trees in Antarctica**: The polar biome strictly renders sastrugi ice sheets, stilted modular research pods, radomes, and atmospheric Aurora Borealis.
- **Authentic Victorian Thames Embankment**: Granite quay walls, wet cobblestones, cast-iron gaslamps, brick warehouse silhouettes, and dynamic undulating river surface.
- **Authentic Edo River Crossing**: Traditional Taiko timber bridge joinery, deck planks, giboshi bronze finials, machiya townhouses, and paper lanterns.
- **1930s Shanghai Railway Station**: Flagstone passenger platforms, railway ballast, dual steel tracks, wooden sleepers, cast-iron canopy columns, hanging brass lanterns, and vintage luggage trunks.
- **Modern Emergency Room (Chợ Rẫy Hospital)**: Polished hygienic terrazzo floor, hospital gurney bed, IV drip stand with saline bag, cardiac telemetry monitor with glowing green ECG waveform.
- **Sci-Fi Desert Station (Sahara 2050)**: Undulating golden sand dunes, geodesic observation dome with panoramic glass port, photovoltaic solar arrays, and sensor telemetry mast with beacon.

---

## 2. ENVIRONMENT CATALOG & SPECIFICATIONS

| Environment ID | Semantic Archetype | Key Lighting Formula | Ambient & Sky Baseline | Ground & Key Props |
| :--- | :--- | :--- | :--- | :--- |
| **`CAFE`** | Commercial interior | Warm incandescent `0xFFE8CC` (2.4x) | Warm acoustic wood `0xD4B89C` (1.65x) | Herringbone wood floor, espresso bar, acoustic slats |
| **`ANTARCTIC`** | Polar research base | Cold polar blue `0xB0F0FF` (2.0x) | Cyan/emerald aurora `0x64FFDA` (1.45x) | Sastrugi ice sheet, stilted modular pod, radome |
| **`VICTORIAN_THAMES`** | Historical urban riverway | Gaslight amber `0xFFE0B0` (2.2x) | River mist `0x78909C` (1.45x) | Granite embankment, gaslamps, cobbled quay, river |
| **`EDO_BRIDGE`** | Historical river crossing | Overcast daylight `0xF0F8FF` (2.4x) | Storm sky `0x90A4AE` (1.55x) | Taiko timber deck, giboshi finials, canal, rain FX |
| **`EDO_HOUSE`** | Historical interior/residence | Paper lantern `0xFFC46B` (2.4x) | Cedar wood `0xBCAAA4` (1.55x) | Shoji screens, tatami mats, veranda eaves, lanterns |
| **`NEOCLASSICAL`** | Historical European public square | Limestone sun `0xFFF5E6` (2.4x) | Clear Munich sky `0x90CAF9` (1.45x) | Feldherrnhalle arches, stone plinths, Litfaßsäule |
| **`ROBOTICS_LAB`** | Industrial high-tech workcell | Clean fluorescent `0xF0F9FF` (2.6x) | Cleanroom blue `0x7DD3FC` (1.65x) | Reflective epoxy floor, robotic racks, status LEDs |
| **`RAIL_STATION`** | 1930s Urban Noir Station | Lantern amber `0xFFD28A` (2.3x) | Steam mist `0x68788C` (1.50x) | Wet flagstone platform, steel tracks, sleepers, luggage |
| **`HOSPITAL_ER`** | Modern medical emergency room | Clinical white `0xF8FAFC` (2.5x) | Medical mint `0xCBD5E1` (1.70x) | Terrazzo floor, hospital bed, IV pole, ECG monitor |
| **`DESERT_STATION`** | Sci-Fi desert weather station | Blazing desert sun `0xFFF3D0` (2.8x) | Sahara ochre `0xD4A373` (1.55x) | Sand dunes, geodesic dome, solar array, telemetry mast |

---

## 3. PHYSICAL MATERIALS (PBR) & PERFORMANCE

- **Shading Model**: MeshStandardMaterial throughout Three.js scene graph.
- **Roughness Floor**: Never zero; calibrated to realistic physical values:
  - Wet granite / rain-slick stone: $0.35 - 0.40$
  - Timber slats / oak: $0.50 - 0.70$
  - Polished clinical terrazzo / epoxy: $0.22 - 0.28$
  - Desert sand / masonry: $0.85 - 0.92$
- **Metalness Control**:
  - Structural stone / wood: $0.00 - 0.15$
  - Cast-iron lanterns / columns: $0.65 - 0.75$
  - Stainless steel surgical / espresso equipment: $0.80 - 0.85$
- **Tone Mapping & Exposure**: Standardized to `ACESFilmicToneMapping` at exposure `1.45`, guaranteeing mean frame luminance $\ge 0.38$.
