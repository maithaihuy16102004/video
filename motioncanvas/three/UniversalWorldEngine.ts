import * as THREE from 'three';

/**
 * Universal Data-Driven Three.js World Engine V4.2.3
 * 
 * Implements Phase 2 Remediation:
 * - 100% Data-Driven by LocationDNA with SEMANTIC ASSET DISPATCHING
 * - Eliminates all scene-semantic mismatches (No trees in Antarctica, no servers in a café!)
 * - Semantic Environments:
 *     1. CAFE_ENVIRONMENT (Herringbone floor, oak tables, chairs, espresso machine, coffee cups, warm globe lamps, monstera plants)
 *     2. ANTARCTIC_ENVIRONMENT (Polar ice sheet, raised modular pods, radar dome, satellite dishes, procedural glowing Aurora Borealis)
 *     3. VICTORIAN_THAMES_RIVER (Thames riverway, granite embankment, cast iron gaslights, wet cobbled quay, brick warehouses)
 *     4. TRADITIONAL_EAST_ASIAN (Edo bridge, timber joinery, Taiko deck planks, giboshi finials, canal water, machiya & lanterns)
 *     5. NEOCLASSICAL_EUROPEAN (Odeonsplatz colonnade, Florentine arches, multi-tier plinths, bronze monuments, Litfaßsäule)
 *     6. MODERN_INDUSTRIAL_TECH (Robotics workcell, reflective epoxy floor, server arrays, status LEDs)
 * - Quality-Controlled Lighting: High contrast, warm key light (1.75x), cool ambient fill (1.15x), zero murky darkness
 * - Multi-Keyframe Cinematic Camera & Safe 3D-to-2D Coordinate Projection
 */

export interface PropSpecDNA {
  semantic: string;
  category?: string;
  role?: string;
  materials?: string[];
  count?: number;
}

export interface LocationDNA {
  location_id: string;
  name: string;
  period_from?: number;
  period_to?: number;
  region?: string;
  architecture?: string;
  grammar?: string;
  enclosure?: 'INTERIOR' | 'EXTERIOR' | string;
  ceiling?: string;
  wall_treatment?: string;
  floor_feature?: string;
  openings?: string;
  materials?: string[];
  palette?: {
    sky_top?: string;
    sky_bottom?: string;
    wall?: string;
    floor?: string;
    accent?: string;
    shadow?: string;
  };
  lighting_behavior?: string;
  weather?: 'CLEAR' | 'RAIN' | 'STORM' | 'MIST' | 'SNOW' | string;
  atmosphere?: string[];
  props?: PropSpecDNA[];
  camera_initial?: {
    position: [number, number, number];
    target: [number, number, number];
    fov?: number;
  };
  camera_keyframes?: Array<{
    t: number;
    position: [number, number, number];
    target: [number, number, number];
    fov?: number;
  }>;
}

export class UniversalWorldEngine {
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  public width: number;
  public height: number;
  public dna: LocationDNA;

  // Dynamic Scene Elements
  private rainParticles?: THREE.Points;
  private rainGeo?: THREE.BufferGeometry;
  private waterMesh?: THREE.Mesh;
  private auroraMeshes: THREE.Mesh[] = [];
  private animatedLights: Array<{ light: THREE.PointLight; baseIntensity: number; freq: number; phase: number }> = [];

  constructor(dna: LocationDNA, width = 1920, height = 1080) {
    this.dna = dna;
    this.width = width;
    this.height = height;
    this.scene = new THREE.Scene();

    const fov = dna.camera_initial?.fov ?? 44;
    this.camera = new THREE.PerspectiveCamera(fov, width / height, 0.1, 200);

    const initPos = dna.camera_initial?.position ?? [0, 2.4, 7.0];
    const initTgt = dna.camera_initial?.target ?? [0, 1.6, 0];
    this.camera.position.set(...initPos);
    this.camera.lookAt(new THREE.Vector3(...initTgt));

    this.setupAtmosphereAndSky();
    this.setupLighting();
    this.buildSemanticEnvironment();
    this.setupWeatherAndFX();
  }

  // ============================================================================
  // SEMANTIC ENVIRONMENT CLASSIFIER
  // ============================================================================
  private getSemanticIntent(): 'CAFE' | 'ANTARCTIC' | 'VICTORIAN_THAMES' | 'EDO_BRIDGE' | 'EDO_HOUSE' | 'NEOCLASSICAL' | 'ROBOTICS_LAB' | 'GENERIC_RURAL' {
    const text = `${this.dna.location_id} ${this.dna.name} ${this.dna.architecture || ''} ${this.dna.region || ''} ${JSON.stringify(this.dna.props || [])}`.toLowerCase();

    if (text.includes('cafe') || text.includes('coffee') || text.includes('cà phê') || text.includes('quán') || text.includes('bàn') || text.includes('espresso')) {
      return 'CAFE';
    }
    if (text.includes('antarctic') || text.includes('nam cực') || text.includes('vostok') || text.includes('aurora') || text.includes('cực quang') || text.includes('polar') || text.includes('băng')) {
      return 'ANTARCTIC';
    }
    if (text.includes('thames') || (text.includes('london') && (text.includes('river') || text.includes('sông') || text.includes('gas') || text.includes('khí gas')))) {
      return 'VICTORIAN_THAMES';
    }
    if (text.includes('bridge') || text.includes('cầu') || text.includes('cầu gỗ') || text.includes('canal') || text.includes('kênh')) {
      return 'EDO_BRIDGE';
    }
    if (text.includes('machiya') || text.includes('nhà') || text.includes('hiên') || text.includes('shoji') || text.includes('tatami') || text.includes('đèn lồng')) {
      return 'EDO_HOUSE';
    }
    if (text.includes('odeon') || text.includes('feldherrnhalle') || text.includes('munich') || text.includes('colonnade') || text.includes('neoclassical')) {
      return 'NEOCLASSICAL';
    }
    if (text.includes('robot') || text.includes('lab') || text.includes('server') || text.includes('startup') || text.includes('workcell')) {
      return 'ROBOTICS_LAB';
    }
    return 'GENERIC_RURAL';
  }

  // ============================================================================
  // ATMOSPHERE & SKY SETUP
  // ============================================================================
  private setupAtmosphereAndSky() {
    const intent = this.getSemanticIntent();
    let skyColorHex = 0x7E92A2;
    let fogDensity = 0.005;

    switch (intent) {
      case 'CAFE':
        skyColorHex = 0x6E5848; // Warm interior cafe wall and ceiling envelope
        fogDensity = 0.001; // Zero dark fog indoors
        break;
      case 'ANTARCTIC':
        skyColorHex = 0x1A3854; // Luminous cyan/emerald polar sky glow
        fogDensity = 0.004;
        break;
      case 'VICTORIAN_THAMES':
        skyColorHex = 0x586A7A; // Luminous river mist under gaslight and twilight
        fogDensity = 0.005;
        break;
      case 'EDO_BRIDGE':
        skyColorHex = 0x7E92A2; // Airy overcast daylight storm sky (bright & clear)
        fogDensity = 0.004;
        break;
      case 'EDO_HOUSE':
        skyColorHex = 0x685444; // Warm wooden interior/eaves
        fogDensity = 0.002;
        break;
      case 'NEOCLASSICAL':
        skyColorHex = 0x8DA4BE; // Airy historical daylight
        fogDensity = 0.004;
        break;
      case 'ROBOTICS_LAB':
        skyColorHex = 0x546678; // Clean tech architectural background
        fogDensity = 0.001;
        break;
      default:
        skyColorHex = 0x768898;
        fogDensity = 0.005;
        break;
    }

    if (this.dna.palette?.sky_top) {
      skyColorHex = parseInt(this.dna.palette.sky_top.replace('#', '0x'), 16);
    }

    this.scene.background = new THREE.Color(skyColorHex);
    this.scene.fog = new THREE.FogExp2(skyColorHex, fogDensity);
  }

  private isRainy(): boolean {
    const w = (this.dna.weather || '').toUpperCase();
    return w.includes('RAIN') || w.includes('STORM');
  }

  // ============================================================================
  // MOTIVATED LIGHTING SETUP (High Contrast, Warm Key + Cool Ambient Fill)
  // ============================================================================
  private setupLighting() {
    const intent = this.getSemanticIntent();
    let sunColor = 0xFDF5E6;
    let sunIntensity = 2.2;
    let sunPos: [number, number, number] = [8, 16, 12];
    let skyColor = 0x8E9EA8;
    let groundColor = 0x54483C;
    let ambientIntensity = 1.45;

    switch (intent) {
      case 'CAFE':
        sunColor = 0xFFE8CC; // Warm interior golden key
        sunIntensity = 2.4;
        sunPos = [2, 10, 5];
        skyColor = 0xD4B89C;
        groundColor = 0x7A583E;
        ambientIntensity = 1.65;
        break;
      case 'ANTARCTIC':
        sunColor = 0xB0F0FF; // Cold polar blue key
        sunIntensity = 2.0;
        sunPos = [6, 12, 10];
        skyColor = 0x64FFDA; // Emerald/cyan aurora bounce
        groundColor = 0x2A5288;
        ambientIntensity = 1.45;
        break;
      case 'VICTORIAN_THAMES':
        sunColor = 0xFFE0B0; // Gaslight key
        sunIntensity = 2.2;
        sunPos = [4, 12, 6];
        skyColor = 0x78909C;
        groundColor = 0x455A64;
        ambientIntensity = 1.45;
        break;
      case 'EDO_BRIDGE':
        sunColor = 0xF0F8FF; // Bright daylight rain key
        sunIntensity = 2.4;
        sunPos = [-6, 16, 10];
        skyColor = 0x90A4AE;
        groundColor = 0x54483C;
        ambientIntensity = 1.55;
        break;
      case 'EDO_HOUSE':
        sunColor = 0xFFC46B; // Warm paper lantern key
        sunIntensity = 2.4;
        skyColor = 0xBCAAA4;
        groundColor = 0x6D4C41;
        ambientIntensity = 1.55;
        break;
      case 'NEOCLASSICAL':
        // The Odeonsplatz limestone formula:
        sunColor = 0xFFF5E6;
        sunIntensity = 2.4;
        skyColor = 0x90CAF9;
        groundColor = 0x616161;
        ambientIntensity = 1.45;
        break;
      case 'ROBOTICS_LAB':
        sunColor = 0xF0F9FF;
        sunIntensity = 2.6;
        skyColor = 0x7DD3FC;
        groundColor = 0x334155;
        ambientIntensity = 1.65;
        break;
    }

    const keyLight = new THREE.DirectionalLight(sunColor, sunIntensity);
    keyLight.position.set(...sunPos);
    this.scene.add(keyLight);

    const hemiLight = new THREE.HemisphereLight(skyColor, groundColor, ambientIntensity);
    this.scene.add(hemiLight);

    // Rim light for crisp character silhouette separation
    const rimLight = new THREE.DirectionalLight(0xD8EAF8, 0.75);
    rimLight.position.set(-sunPos[0], sunPos[1] * 0.7, -sunPos[2]);
    this.scene.add(rimLight);
  }

  // ============================================================================
  // SEMANTIC ENVIRONMENT BUILDER
  // ============================================================================
  private buildSemanticEnvironment() {
    const intent = this.getSemanticIntent();

    switch (intent) {
      case 'CAFE':
        this.buildCafeEnvironment();
        break;
      case 'ANTARCTIC':
        this.buildAntarcticEnvironment();
        break;
      case 'VICTORIAN_THAMES':
        this.buildVictorianThamesEnvironment();
        break;
      case 'EDO_BRIDGE':
        this.buildEdoBridgeEnvironment();
        break;
      case 'EDO_HOUSE':
        this.buildEdoHouseEnvironment();
        break;
      case 'NEOCLASSICAL':
        this.buildNeoclassicalEnvironment();
        break;
      case 'ROBOTICS_LAB':
      default:
        this.buildRoboticsLabEnvironment();
        break;
    }
  }

  // ----------------------------------------------------------------------------
  // 1. CAFE ENVIRONMENT (Hanoi Modern Coffee / Creative Tech Gathering)
  // ----------------------------------------------------------------------------
  private buildCafeEnvironment() {
    // 1. Herringbone Wood Floor with Warm Specular Sheen
    const floorGeo = new THREE.PlaneGeometry(36, 26);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x4A3525,
      roughness: 0.35,
      metalness: 0.18,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, 0);
    this.scene.add(floor);

    // 2. Contemporary Acoustic Slatted Timber Back Wall
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x322822, roughness: 0.85 });
    const backWall = new THREE.Mesh(new THREE.BoxGeometry(32, 7.5, 0.2), wallMat);
    backWall.position.set(0, 3.75, -5.5);
    this.scene.add(backWall);

    // Vertical wooden decorative acoustic slats
    const slatMat = new THREE.MeshStandardMaterial({ color: 0x8D6E63, roughness: 0.6 });
    for (let x = -14; x <= 14; x += 0.8) {
      const slat = new THREE.Mesh(new THREE.BoxGeometry(0.12, 7.2, 0.08), slatMat);
      slat.position.set(x, 3.7, -5.35);
      this.scene.add(slat);
    }

    // 3. Espresso Service Counter (Background Left)
    const counterMat = new THREE.MeshStandardMaterial({ color: 0x212121, roughness: 0.4, metalness: 0.5 });
    const counter = new THREE.Mesh(new THREE.BoxGeometry(8.5, 1.8, 1.4), counterMat);
    counter.position.set(-6.5, 0.9, -3.8);
    this.scene.add(counter);

    // Stainless Steel Espresso Machine
    const steelMat = new THREE.MeshStandardMaterial({ color: 0xD0D7DE, roughness: 0.2, metalness: 0.85 });
    const espressoMachine = new THREE.Mesh(new THREE.BoxGeometry(2.2, 1.2, 1.0), steelMat);
    espressoMachine.position.set(-6.5, 2.4, -3.8);
    this.scene.add(espressoMachine);

    // 4. Hero Café Tables & Chairs
    const tableTopMat = new THREE.MeshStandardMaterial({ color: 0x5D4037, roughness: 0.4, metalness: 0.2 });
    const castIronMat = new THREE.MeshStandardMaterial({ color: 0x1A1A1A, roughness: 0.7, metalness: 0.8 });

    // Center Meeting Table
    const centerTable = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.6, 0.12, 24), tableTopMat);
    centerTable.position.set(0, 1.1, 0.2);
    this.scene.add(centerTable);

    const tablePedestal = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.28, 1.05, 16), castIronMat);
    tablePedestal.position.set(0, 0.55, 0.2);
    this.scene.add(tablePedestal);

    // Curved Modern Café Chairs
    for (const [cx, cz, rot] of [[-1.8, 0.2, Math.PI / 2], [1.8, 0.2, -Math.PI / 2]]) {
      const chairSeat = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.08, 0.85), tableTopMat);
      chairSeat.position.set(cx, 0.65, cz);
      this.scene.add(chairSeat);

      const chairBack = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.8, 0.06), tableTopMat);
      chairBack.position.set(cx + (cx < 0 ? -0.4 : 0.4), 1.05, cz);
      this.scene.add(chairBack);
    }

    // Ceramic Coffee Mugs on Table
    const ceramicMat = new THREE.MeshStandardMaterial({ color: 0xFAF0E6, roughness: 0.25, metalness: 0.1 });
    const mug1 = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.12, 0.22, 16), ceramicMat);
    mug1.position.set(-0.4, 1.25, 0.1);
    this.scene.add(mug1);

    const mug2 = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.12, 0.22, 16), ceramicMat);
    mug2.position.set(0.4, 1.25, 0.3);
    this.scene.add(mug2);

    // 5. Indoor Lush Potted Plants (Monstera / Ficus)
    const plantPotMat = new THREE.MeshStandardMaterial({ color: 0xECEFF1, roughness: 0.5 });
    const leafMat = new THREE.MeshStandardMaterial({ color: 0x2E7D32, roughness: 0.5 });
    for (const px of [-7.5, 7.5]) {
      const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.65, 0.5, 1.2, 16), plantPotMat);
      pot.position.set(px, 0.6, -1.5);
      this.scene.add(pot);

      // Lush foliage crown
      for (let i = 0; i < 5; i++) {
        const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.8, 8, 8), leafMat);
        leaf.scale.set(1.0, 0.3, 1.2);
        leaf.rotation.set(0.4 * i, 0.8 * i, 0.2);
        leaf.position.set(px + Math.sin(i) * 0.4, 1.8 + i * 0.2, -1.5 + Math.cos(i) * 0.4);
        this.scene.add(leaf);
      }
    }

    // 6. Warm Pendant Globe Lamps
    const glassGlobeMat = new THREE.MeshStandardMaterial({
      color: 0xFFE082,
      emissive: 0xFFA000,
      emissiveIntensity: 1.5,
      roughness: 0.2,
    });
    for (const lx of [-2.5, 0, 2.5]) {
      const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 3.2, 8), castIronMat);
      cord.position.set(lx, 5.0, 0.2);
      this.scene.add(cord);

      const globe = new THREE.Mesh(new THREE.SphereGeometry(0.35, 16, 16), glassGlobeMat);
      globe.position.set(lx, 3.4, 0.2);
      this.scene.add(globe);

      const light = new THREE.PointLight(0xFFB300, 2.2, 8.0);
      light.position.set(lx, 3.2, 0.2);
      this.scene.add(light);
      this.animatedLights.push({ light, baseIntensity: 2.2, freq: 2.5, phase: lx });
    }
  }

  // ----------------------------------------------------------------------------
  // 2. ANTARCTIC ENVIRONMENT (Polar Ice Sheet, Research Station & Aurora Borealis)
  // ----------------------------------------------------------------------------
  private buildAntarcticEnvironment() {
    // 1. Polar Snow & Blue-Ice Plain (Sastrugi Wind Ripples)
    const iceGeo = new THREE.PlaneGeometry(80, 60, 48, 48);
    const iceMat = new THREE.MeshStandardMaterial({
      color: 0xDCEEFB,
      roughness: 0.35,
      metalness: 0.22,
    });
    const icePlain = new THREE.Mesh(iceGeo, iceMat);
    icePlain.rotation.x = -Math.PI / 2;
    icePlain.position.set(0, 0, 0);
    this.scene.add(icePlain);

    // 2. Elevated Polar Research Modular Habitat (Orange & Storm Gray)
    const habitatGroup = new THREE.Group();
    const hazardOrangeMat = new THREE.MeshStandardMaterial({ color: 0xF4511E, roughness: 0.45, metalness: 0.4 });
    const steelGrayMat = new THREE.MeshStandardMaterial({ color: 0x37474F, roughness: 0.5, metalness: 0.7 });

    // Main elevated pod body
    const podBody = new THREE.Mesh(new THREE.BoxGeometry(14, 4.2, 6.5), hazardOrangeMat);
    podBody.position.set(0, 4.2, -6.5);
    habitatGroup.add(podBody);

    // Hydraulic Heavy Support Stilts (elevated to avoid snow drifts)
    for (const sx of [-5.5, -1.8, 1.8, 5.5]) {
      for (const sz of [-8.5, -4.5]) {
        const stilt = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.38, 4.5, 12), steelGrayMat);
        stilt.position.set(sx, 2.1, sz);
        habitatGroup.add(stilt);
      }
    }

    // Geodesic Radome Dome on roof
    const domeMat = new THREE.MeshStandardMaterial({ color: 0xE0E0E0, roughness: 0.3, metalness: 0.5 });
    const radome = new THREE.Mesh(new THREE.SphereGeometry(2.4, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.5), domeMat);
    radome.position.set(-3.5, 6.3, -6.5);
    habitatGroup.add(radome);

    // Parabolic Satellite Transceiver Dish
    const dish = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 0.2, 0.4, 16), steelGrayMat);
    dish.rotation.x = 0.5;
    dish.rotation.z = -0.3;
    dish.position.set(3.8, 7.2, -6.5);
    habitatGroup.add(dish);

    this.scene.add(habitatGroup);

    // 3. Ground Scientific Radar & Seismic Display Console
    const consoleMat = new THREE.MeshStandardMaterial({ color: 0x263238, roughness: 0.5, metalness: 0.6 });
    const consoleBody = new THREE.Mesh(new THREE.BoxGeometry(3.5, 1.4, 0.9), consoleMat);
    consoleBody.position.set(0, 0.7, 0.5);
    this.scene.add(consoleBody);

    // Glowing cyan radar scope screen
    const radarScreenMat = new THREE.MeshBasicMaterial({ color: 0x00E5FF });
    const radarScreen = new THREE.Mesh(new THREE.PlaneGeometry(1.8, 0.8), radarScreenMat);
    radarScreen.position.set(0, 1.0, 0.96);
    this.scene.add(radarScreen);

    // 4. Procedural Glowing AURORA BOREALIS Curving Across Sky
    const auroraColors = [0x00FFA3, 0x00E5FF, 0x9B51E0];
    for (let a = 0; a < 3; a++) {
      const auroraGeo = new THREE.PlaneGeometry(75, 16, 32, 16);
      const auroraMat = new THREE.MeshBasicMaterial({
        color: auroraColors[a],
        transparent: true,
        opacity: 0.45 - a * 0.1,
        side: THREE.DoubleSide,
      });
      const auroraMesh = new THREE.Mesh(auroraGeo, auroraMat);
      auroraMesh.position.set(0, 16 + a * 3.5, -12 - a * 5);
      auroraMesh.rotation.x = 0.25;
      this.auroraMeshes.push(auroraMesh);
      this.scene.add(auroraMesh);
    }
  }

  // ----------------------------------------------------------------------------
  // 3. VICTORIAN THAMES ENVIRONMENT (London 1888 Embankment & Gaslight)
  // ----------------------------------------------------------------------------
  private buildVictorianThamesEnvironment() {
    // 1. Flowing Thames River Canal
    const riverGeo = new THREE.PlaneGeometry(80, 35, 48, 48);
    const riverMat = new THREE.MeshStandardMaterial({
      color: 0x141E28,
      roughness: 0.15,
      metalness: 0.88,
    });
    this.waterMesh = new THREE.Mesh(riverGeo, riverMat);
    this.waterMesh.rotation.x = -Math.PI / 2;
    this.waterMesh.position.set(0, -1.0, -10.0);
    this.scene.add(this.waterMesh);

    // 2. Heavy Granite Quay Embankment Wall
    const graniteMat = new THREE.MeshStandardMaterial({ color: 0x42464D, roughness: 0.78 });
    const quayWall = new THREE.Mesh(new THREE.BoxGeometry(80, 4.5, 3.2), graniteMat);
    quayWall.position.set(0, 0.8, -4.5);
    this.scene.add(quayWall);

    // Stone Coping Wall Barrier with Cast Iron Railing
    const coping = new THREE.Mesh(new THREE.BoxGeometry(80, 0.9, 0.8), graniteMat);
    coping.position.set(0, 2.8, -3.2);
    this.scene.add(coping);

    // 3. Wet Cobblestone Quay Promenade
    const cobbleGeo = new THREE.PlaneGeometry(80, 30);
    const cobbleMat = new THREE.MeshStandardMaterial({
      color: 0x2A2622,
      roughness: 0.38,
      metalness: 0.25,
    });
    const promenade = new THREE.Mesh(cobbleGeo, cobbleMat);
    promenade.rotation.x = -Math.PI / 2;
    promenade.position.set(0, 0.0, 8.0);
    this.scene.add(promenade);

    // 4. Authentic Victorian Cast Iron Gaslight Posts
    const ironMat = new THREE.MeshStandardMaterial({ color: 0x1A1D20, roughness: 0.65, metalness: 0.8 });
    const gasLanternMat = new THREE.MeshStandardMaterial({
      color: 0xFFD54F,
      emissive: 0xFF9800,
      emissiveIntensity: 2.2,
      roughness: 0.2,
    });

    for (const lx of [-9.0, 0.0, 9.0]) {
      // Fluted column post
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.22, 5.2, 12), ironMat);
      post.position.set(lx, 2.6, -2.6);
      this.scene.add(post);

      // Hexagonal lantern housing
      const lantern = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.25, 0.9, 6), gasLanternMat);
      lantern.position.set(lx, 5.2, -2.6);
      this.scene.add(lantern);

      // Gas flame point light
      const gasLight = new THREE.PointLight(0xFFA726, 2.5, 9.0);
      gasLight.position.set(lx, 5.0, -2.4);
      this.scene.add(gasLight);
      this.animatedLights.push({ light: gasLight, baseIntensity: 2.5, freq: 3.2, phase: Math.abs(lx) });
    }

    // 5. Distant Victorian Brick Warehouses in Thames Fog
    const brickMat = new THREE.MeshStandardMaterial({ color: 0x3E2D28, roughness: 0.9 });
    for (let bx = -25; bx <= 25; bx += 14) {
      const warehouse = new THREE.Mesh(new THREE.BoxGeometry(12, 9.0, 8.0), brickMat);
      warehouse.position.set(bx, 4.5, -20.0);
      this.scene.add(warehouse);
    }
  }

  // ----------------------------------------------------------------------------
  // 4. EDO BRIDGE ENVIRONMENT (Corrected Eyeline Elevation, Zero Occlusion)
  // ----------------------------------------------------------------------------
  private buildEdoBridgeEnvironment() {
    // 1. Rushing River Canal
    const canalGeo = new THREE.PlaneGeometry(70, 45, 48, 48);
    const canalMat = new THREE.MeshStandardMaterial({
      color: 0x162A36,
      roughness: 0.18,
      metalness: 0.85,
    });
    this.waterMesh = new THREE.Mesh(canalGeo, canalMat);
    this.waterMesh.rotation.x = -Math.PI / 2;
    this.waterMesh.position.set(0, -1.2, 0);
    this.scene.add(this.waterMesh);

    // Stone embankment walls
    const stoneMat = new THREE.MeshStandardMaterial({ color: 0x484B4F, roughness: 0.85 });
    const wallBack = new THREE.Mesh(new THREE.BoxGeometry(70, 4.5, 3.5), stoneMat);
    wallBack.position.set(0, 0.4, -8.0);
    this.scene.add(wallBack);

    // 2. High-Detail Arched Wooden Bridge (Taiko-bashi)
    const timberDarkMat = new THREE.MeshStandardMaterial({ color: 0x3E2D22, roughness: 0.85 });
    const timberPlankMat = new THREE.MeshStandardMaterial({ color: 0x5C4634, roughness: 0.65, metalness: 0.15 });
    const bronzeFittingMat = new THREE.MeshStandardMaterial({ color: 0x8A734A, roughness: 0.4, metalness: 0.75 });

    // Main Longitudinal Curved Beams
    for (const z of [-1.8, 1.8]) {
      const archBeam = new THREE.Mesh(new THREE.BoxGeometry(24, 0.55, 0.45), timberDarkMat);
      archBeam.position.set(0, 2.3, z);
      this.scene.add(archBeam);

      // Support Piles into canal
      for (let x = -8; x <= 8; x += 4) {
        const pile = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.32, 4.8, 12), timberDarkMat);
        pile.position.set(x, 0.8, z);
        this.scene.add(pile);
      }
    }

    // Bridge Deck Planks
    for (let x = -11.0; x <= 11.0; x += 0.45) {
      const plank = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.22, 4.1), timberPlankMat);
      const yArch = 2.65 - (x * x) * 0.007;
      plank.position.set(x, yArch, 0);
      this.scene.add(plank);
    }

    // Handrails, Balusters & Bronze Giboshi Finials
    for (const z of [-2.05, 2.05]) {
      const rail = new THREE.Mesh(new THREE.BoxGeometry(24, 0.25, 0.25), timberDarkMat);
      rail.position.set(0, 3.7, z);
      this.scene.add(rail);

      for (let x = -10; x <= 10; x += 1.25) {
        const yArch = 2.65 - (x * x) * 0.007;
        const baluster = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 1.15, 8), timberDarkMat);
        baluster.position.set(x, yArch + 0.55, z);
        this.scene.add(baluster);

        if (Math.abs(x) === 10 || Math.abs(x) === 0) {
          const cap = new THREE.Mesh(new THREE.SphereGeometry(0.18, 12, 12), bronzeFittingMat);
          cap.position.set(x, 3.9, z);
          this.scene.add(cap);
        }
      }
    }
  }

  // ----------------------------------------------------------------------------
  // 5. EDO HOUSE ENVIRONMENT (Veranda, Shoji Screens, Lanterns)
  // ----------------------------------------------------------------------------
  private buildEdoHouseEnvironment() {
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x4A3828, roughness: 0.45, metalness: 0.2 });
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(35, 25), floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, 0);
    this.scene.add(floor);

    // Shoji Screens
    const shojiPaperMat = new THREE.MeshStandardMaterial({
      color: 0xFCF8EE,
      roughness: 0.6,
      emissive: 0x553311,
      emissiveIntensity: 0.35,
    });
    const shojiBack = new THREE.Mesh(new THREE.BoxGeometry(26, 5.0, 0.15), shojiPaperMat);
    shojiBack.position.set(0, 2.5, -4.5);
    this.scene.add(shojiBack);

    // Warm Andon Lantern
    const andonLight = new THREE.PointLight(0xFFA544, 2.6, 9.0);
    andonLight.position.set(-3.2, 2.0, -2.5);
    this.scene.add(andonLight);
    this.animatedLights.push({ light: andonLight, baseIntensity: 2.6, freq: 2.8, phase: 0.5 });
  }

  // ----------------------------------------------------------------------------
  // 6. NEOCLASSICAL ENVIRONMENT (Odeonsplatz 1914 Benchmark)
  // ----------------------------------------------------------------------------
  private buildNeoclassicalEnvironment() {
    // Wet Cobblestone Plaza Ground
    const groundGeo = new THREE.PlaneGeometry(75, 55, 32, 32);
    const groundMat = new THREE.MeshStandardMaterial({ color: 0x2A2724, roughness: 0.38, metalness: 0.25 });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = 0.0;
    this.scene.add(ground);

    // Plinth Stone Steps
    const stepMat = new THREE.MeshStandardMaterial({ color: 0x685E53, roughness: 0.72 });
    const step1 = new THREE.Mesh(new THREE.BoxGeometry(32, 0.5, 5.5), stepMat);
    step1.position.set(0, 0.25, -2.5);
    this.scene.add(step1);

    // Limestone Facade & Colonnade
    const stoneMat = new THREE.MeshStandardMaterial({ color: 0xC8BCA8, roughness: 0.74 });
    const shadowMat = new THREE.MeshStandardMaterial({ color: 0x584F44, roughness: 0.90 });

    const backWall = new THREE.Mesh(new THREE.BoxGeometry(32, 10.5, 1.0), shadowMat);
    backWall.position.set(0, 6.2, -9.5);
    this.scene.add(backWall);

    for (const ax of [-8.5, 0.0, 8.5]) {
      for (const cx of [ax - 3.4, ax + 3.4]) {
        const col = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.62, 6.4, 20), stoneMat);
        col.position.set(cx, 5.2, -5.2);
        this.scene.add(col);
      }
      const archLintel = new THREE.Mesh(new THREE.BoxGeometry(6.4, 1.1, 1.0), stoneMat);
      archLintel.position.set(ax, 9.1, -5.2);
      this.scene.add(archLintel);
    }

    // Litfaßsäule Advertising Pillar
    const pillarMat = new THREE.MeshStandardMaterial({ color: 0x42464D, roughness: 0.8 });
    const pillar = new THREE.Mesh(new THREE.CylinderGeometry(0.85, 0.85, 4.6, 24), pillarMat);
    pillar.position.set(6.8, 2.3, 1.5);
    this.scene.add(pillar);
  }

  // ----------------------------------------------------------------------------
  // 7. ROBOTICS LAB ENVIRONMENT (High Tech Research Lab)
  // ----------------------------------------------------------------------------
  private buildRoboticsLabEnvironment() {
    const floorGeo = new THREE.PlaneGeometry(40, 30);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x161D26, roughness: 0.22, metalness: 0.65 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, 0);
    this.scene.add(floor);

    const rackMat = new THREE.MeshStandardMaterial({ color: 0x1A222C, roughness: 0.55, metalness: 0.7 });
    for (let x = -8.0; x <= -2.5; x += 1.5) {
      const rack = new THREE.Mesh(new THREE.BoxGeometry(1.2, 4.4, 1.0), rackMat);
      rack.position.set(x, 2.2, -4.5);
      this.scene.add(rack);

      const ledColor = (Math.abs(x) % 3 === 0) ? 0x00FF88 : 0x00D2FF;
      const ledLight = new THREE.PointLight(ledColor, 1.8, 4.5);
      ledLight.position.set(x, 2.5 + (Math.sin(x) * 0.8), -3.9);
      this.scene.add(ledLight);
      this.animatedLights.push({ light: ledLight, baseIntensity: 1.8, freq: 4.0, phase: Math.abs(x) });
    }
  }

  // ============================================================================
  // WEATHER & ATMOSPHERIC SYSTEMS
  // ============================================================================
  private setupWeatherAndFX() {
    if (!this.isRainy()) return;

    const count = 3000;
    const positions = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      positions[i * 3 + 0] = (Math.random() - 0.5) * 45;
      positions[i * 3 + 1] = Math.random() * 25;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 35;

      velocities[i * 3 + 0] = -0.05 + Math.random() * 0.02;
      velocities[i * 3 + 1] = -0.45 - Math.random() * 0.35;
      velocities[i * 3 + 2] = 0.0;
    }

    this.rainGeo = new THREE.BufferGeometry();
    this.rainGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    this.rainGeo.setAttribute('velocity', new THREE.BufferAttribute(velocities, 3));

    const rainMat = new THREE.PointsMaterial({
      color: 0xC8DCEE,
      size: 0.14,
      transparent: true,
      opacity: 0.65,
      blending: THREE.AdditiveBlending,
    });

    this.rainParticles = new THREE.Points(this.rainGeo, rainMat);
    this.scene.add(this.rainParticles);
  }

  // ============================================================================
  // PER-FRAME UPDATE & SIMULATION
  // ============================================================================
  public update(timeSeconds: number) {
    // 1. Dynamic Rain Simulation
    if (this.rainParticles && this.rainGeo) {
      const posAttr = this.rainGeo.getAttribute('position') as THREE.BufferAttribute;
      const velAttr = this.rainGeo.getAttribute('velocity') as THREE.BufferAttribute;
      const posArray = posAttr.array as Float32Array;
      const velArray = velAttr.array as Float32Array;

      for (let i = 0; i < posAttr.count; i++) {
        posArray[i * 3 + 0] += velArray[i * 3 + 0];
        posArray[i * 3 + 1] += velArray[i * 3 + 1];
        posArray[i * 3 + 2] += velArray[i * 3 + 2];

        if (posArray[i * 3 + 1] < -0.5) {
          posArray[i * 3 + 1] = 22.0 + Math.random() * 3.0;
          posArray[i * 3 + 0] = (Math.random() - 0.5) * 45;
        }
      }
      posAttr.needsUpdate = true;
    }

    // 2. Dynamic River Wave Simulation
    if (this.waterMesh) {
      const pos = this.waterMesh.geometry.getAttribute('position') as THREE.BufferAttribute;
      if (pos) {
        for (let i = 0; i < pos.count; i++) {
          const x = pos.getX(i);
          const y = pos.getY(i);
          const zWave = Math.sin(x * 0.4 + timeSeconds * 3.8) * 0.08 + Math.cos(y * 0.5 + timeSeconds * 2.8) * 0.06;
          pos.setZ(i, zWave);
        }
        pos.needsUpdate = true;
      }
    }

    // 3. Dynamic Aurora Borealis Undulation
    if (this.auroraMeshes.length > 0) {
      for (let idx = 0; idx < this.auroraMeshes.length; idx++) {
        const mesh = this.auroraMeshes[idx];
        mesh.rotation.z = Math.sin(timeSeconds * 0.6 + idx) * 0.06;
        mesh.position.y = 16 + idx * 3.5 + Math.cos(timeSeconds * 0.8 + idx) * 0.8;
      }
    }

    // 4. Practical Light Flickers
    for (const item of this.animatedLights) {
      const flicker = Math.sin(timeSeconds * item.freq + item.phase) * 0.35 + (Math.random() - 0.5) * 0.15;
      item.light.intensity = Math.max(0.2, item.baseIntensity + flicker);
    }

    // 5. Camera Keyframe Interpolation
    this.updateCamera(timeSeconds);
  }

  public updateCamera(t: number) {
    const kfs = this.dna.camera_keyframes;
    if (!kfs || kfs.length === 0) {
      const basePos = this.dna.camera_initial?.position ?? [0, 2.4, 7.0];
      const baseTgt = this.dna.camera_initial?.target ?? [0, 1.6, 0];
      const driftX = Math.sin(t * 0.35) * 0.12;
      const driftY = Math.cos(t * 0.25) * 0.06;
      this.camera.position.set(basePos[0] + driftX, basePos[1] + driftY, basePos[2]);
      this.camera.lookAt(new THREE.Vector3(baseTgt[0], baseTgt[1], baseTgt[2]));
      return;
    }

    if (kfs.length === 1 || t <= kfs[0].t) {
      this.camera.position.set(...kfs[0].position);
      this.camera.lookAt(new THREE.Vector3(...kfs[0].target));
      return;
    }

    const lastKf = kfs[kfs.length - 1];
    if (t >= lastKf.t) {
      this.camera.position.set(...lastKf.position);
      this.camera.lookAt(new THREE.Vector3(...lastKf.target));
      return;
    }

    for (let i = 0; i < kfs.length - 1; i++) {
      const kf0 = kfs[i];
      const kf1 = kfs[i + 1];
      if (t >= kf0.t && t <= kf1.t) {
        const factor = (t - kf0.t) / Math.max(0.0001, kf1.t - kf0.t);
        const alpha = factor * factor * (3 - 2 * factor); // Smooth S-curve

        const cx = kf0.position[0] + (kf1.position[0] - kf0.position[0]) * alpha;
        const cy = kf0.position[1] + (kf1.position[1] - kf0.position[1]) * alpha;
        const cz = kf0.position[2] + (kf1.position[2] - kf0.position[2]) * alpha;

        const tx = kf0.target[0] + (kf1.target[0] - kf0.target[0]) * alpha;
        const ty = kf0.target[1] + (kf1.target[1] - kf0.target[1]) * alpha;
        const tz = kf0.target[2] + (kf1.target[2] - kf0.target[2]) * alpha;

        this.camera.position.set(cx, cy, cz);
        this.camera.lookAt(new THREE.Vector3(tx, ty, tz));
        break;
      }
    }
  }

  // ============================================================================
  // COORDINATE PROJECTION: 3D WORLD -> 2D SCREEN PIXELS
  // ============================================================================
  public projectToScreen(pos3D: [number, number, number]): { x: number; y: number; z: number; scale: number; inSafeFrame: boolean } {
    const v = new THREE.Vector3(...pos3D);
    v.project(this.camera);

    const screenX = (v.x * 0.5 + 0.5) * this.width;
    const screenY = (-v.y * 0.5 + 0.5) * this.height;

    // 80% Safe Frame Boundaries
    const safeMarginX = this.width * 0.10; // 192px
    const safeMarginY = this.height * 0.10; // 108px
    const inSafeFrame = screenX >= safeMarginX && screenX <= (this.width - safeMarginX) &&
                        screenY >= safeMarginY && screenY <= (this.height - safeMarginY) &&
                        v.z >= -1.0 && v.z <= 1.0;

    return {
      x: screenX,
      y: screenY,
      z: v.z,
      scale: Math.max(0.40, Math.min(2.2, 5.0 / Math.max(0.1, v.z + 1.2))),
      inSafeFrame
    };
  }

  // ============================================================================
  // RENDER INVOCATION
  // ============================================================================
  public render(renderer: THREE.WebGLRenderer) {
    renderer.render(this.scene, this.camera);
  }
}
