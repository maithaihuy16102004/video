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

export interface SceneElementDepthRecord {
  id: string;
  name: string;
  type: 'environment_background' | 'foreground_object' | 'character' | 'handheld_prop' | 'standalone_prop';
  worldPosition: [number, number, number];
  cameraDistance: number;
  viewZ: number;
  screenBounds?: { x1: number; y1: number; x2: number; y2: number };
}

export interface OcclusionEvent {
  characterId: string;
  foregroundObjectId: string;
  characterDepth: number;
  objectDepth: number;
  depthDelta: number; // positive = character is behind object
  overlapScreen: boolean;
  isOccluded: boolean;
}

export interface DepthSortResult {
  depthSortedElements: SceneElementDepthRecord[];
  occlusionEvents: OcclusionEvent[];
  activeOccluders: THREE.Object3D[];
  actorDepths: Record<string, number>;
}

export interface OverheadStructureDef {
  id: string;
  name: string;
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  clearanceY: number;
  description: string;
}

export interface CameraFramingAudit {
  timeSeconds: number;
  cameraPosition: [number, number, number];
  cameraTarget: [number, number, number];
  skyFraction: number;
  lowerMiddleThirdOccupied: boolean;
  characterHeadScreenY: number;
  characterFeetScreenY: number;
  overheadStructureViolation: boolean;
  overheadStructureName?: string;
  foregroundStructureCoverage?: number;
  foregroundStructureViolation?: boolean;
  isClaustrophobicReveal: boolean;
  passed: boolean;
}

export class UniversalWorldEngine {
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  public width: number;
  public height: number;
  public dna: LocationDNA;

  // Foreground & Dynamic Depth Elements
  public foregroundElements: THREE.Object3D[] = [];
  public fallingSandalMesh?: THREE.Mesh;
  public storyPropGroup?: THREE.Group;
  public hasForegroundLayer = true;
  private originalVisibilities: Map<THREE.Object3D, boolean> = new Map();
  public lastDepthSortResult?: DepthSortResult;
  public lastOcclusionEvents: OcclusionEvent[] = [];

  // Dynamic Scene Elements
  private rainParticles?: THREE.Points;
  private rainGeo?: THREE.BufferGeometry;
  private waterMesh?: THREE.Mesh;
  private auroraMeshes: THREE.Mesh[] = [];
  private animatedLights: Array<{ light: THREE.PointLight; baseIntensity: number; freq: number; phase: number }> = [];
  private brokenPlank?: THREE.Mesh;
  private brokenPlankBaseX = -0.2;
  private brokenPlankBaseY = 2.65;

  constructor(dna: LocationDNA, width = 1920, height = 1080) {
    this.dna = dna;
    this.width = width;
    this.height = height;
    this.scene = new THREE.Scene();

    const fov = dna.camera_initial?.fov ?? 44;
    this.camera = new THREE.PerspectiveCamera(fov, width / height, 0.1, 200);

    const initPos = dna.camera_initial?.position ?? this.getDefaultCameraPosition();
    const initTgt = dna.camera_initial?.target ?? this.getDefaultCameraTarget();
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
  private getSemanticIntent():
    | 'CAFE'
    | 'ANTARCTIC'
    | 'VICTORIAN_THAMES'
    | 'EDO_BRIDGE'
    | 'EDO_HOUSE'
    | 'NEOCLASSICAL'
    | 'ROBOTICS_LAB'
    | 'RAIL_STATION'
    | 'HOSPITAL_ER'
    | 'DESERT_STATION'
    | 'GENERIC_RURAL' {
    const text = `${this.dna.location_id} ${this.dna.name} ${this.dna.architecture || ''} ${this.dna.region || ''} ${JSON.stringify(this.dna.props || [])}`.toLowerCase();

    // 1. Explicit Category Anchor (highest reliability)
    const locId = (this.dna.location_id || '').toUpperCase();
    const arch = (this.dna.architecture || '').toUpperCase();
    if (locId.includes('CAFE') || arch === 'CAFE') return 'CAFE';
    if (locId.includes('EDO_HOUSE') || locId.includes('HOUSE') || arch === 'EDO_HOUSE') return 'EDO_HOUSE';
    if (locId.includes('EDO_BRIDGE') || locId.includes('BRIDGE') || arch === 'EDO_BRIDGE') return 'EDO_BRIDGE';
    if (locId.includes('ANTARCTIC') || arch === 'ANTARCTIC') return 'ANTARCTIC';
    if (locId.includes('VICTORIAN_THAMES') || locId.includes('THAMES') || arch === 'VICTORIAN_THAMES') return 'VICTORIAN_THAMES';
    if (locId.includes('RAIL_STATION') || locId.includes('TRAIN') || arch === 'RAIL_STATION') return 'RAIL_STATION';
    if (locId.includes('HOSPITAL_ER') || locId.includes('HOSPITAL') || arch === 'HOSPITAL_ER') return 'HOSPITAL_ER';
    if (locId.includes('DESERT_STATION') || locId.includes('DESERT') || arch === 'DESERT_STATION') return 'DESERT_STATION';
    if (locId.includes('ROBOTICS_LAB') || arch === 'ROBOTICS_LAB') return 'ROBOTICS_LAB';
    if (locId.includes('NEOCLASSICAL') || arch === 'NEOCLASSICAL') return 'NEOCLASSICAL';

    // 2. Strict Compound Semantic Matching (prevents substring collision like "yêu cầu" -> bridge or "tham gia" -> rail)
    if (/(cà phê|cafe|coffee|espresso|quán cà phê)/i.test(text)) {
      return 'CAFE';
    }
    if (/(nhà ga|ga tàu|ga xe lửa|tàu hỏa|đường ray|railway|train station|shanghai 1930)/i.test(text)) {
      return 'RAIL_STATION';
    }
    if (/(bệnh viện|cấp cứu|phòng cấp cứu|chợ rẫy|phòng mổ|y tá|doctor)/i.test(text)) {
      return 'HOSPITAL_ER';
    }
    if (/(sa mạc|sahara|bão cát|đụn cát|dune)/i.test(text)) {
      return 'DESERT_STATION';
    }
    if (/(nam cực|antarctica|băng tuyết|cực quang|aurora|vostok)/i.test(text)) {
      return 'ANTARCTIC';
    }
    if (/(sông thames|thames|bến cảng london|bờ sông london|victorian)/i.test(text)) {
      return 'VICTORIAN_THAMES';
    }
    if (/(cây cầu|cầu gỗ|qua cầu|bắc qua kênh|kênh nước|edo bridge)/i.test(text)) {
      return 'EDO_BRIDGE';
    }
    if (/(nhà cổ|chiếu tatami|tatami|vách shoji|shoji|hiên nhà|nhà aiko|machiya)/i.test(text)) {
      return 'EDO_HOUSE';
    }
    if (/(quảng trường|odeon|feldherrnhalle|munich|colonnade|neoclassical)/i.test(text)) {
      return 'NEOCLASSICAL';
    }
    if (/(phòng lab robot|robotics|máy chủ server|phòng thí nghiệm robot)/i.test(text)) {
      return 'ROBOTICS_LAB';
    }
    return 'NEOCLASSICAL';
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
      case 'RAIL_STATION':
        skyColorHex = 0x485260; // 1930s Shanghai noir steam night sky
        fogDensity = 0.004;
        break;
      case 'HOSPITAL_ER':
        skyColorHex = 0xDDE4EB; // Clean surgical/clinical envelope
        fogDensity = 0.001;
        break;
      case 'DESERT_STATION':
        skyColorHex = 0xC8A878; // Luminous amber Sahara dust sky
        fogDensity = 0.004;
        break;
      default:
        skyColorHex = 0x768898;
        fogDensity = 0.005;
        break;
    }

    if (this.dna.palette?.sky_top) {
      skyColorHex = parseInt(this.dna.palette.sky_top.replace('#', '0x'), 16);
    }

    const skyCol = new THREE.Color(skyColorHex);
    const hsl = { h: 0, s: 0, l: 0 };
    skyCol.getHSL(hsl);
    if (hsl.l < 0.52) {
      hsl.l = 0.55;
      skyCol.setHSL(hsl.h, Math.min(0.35, hsl.s), hsl.l);
    }

    this.scene.background = skyCol;
    this.scene.fog = new THREE.FogExp2(skyCol, fogDensity);
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
      case 'RAIL_STATION':
        sunColor = 0xFFD28A; // Warm incandescent platform lanterns
        sunIntensity = 2.3;
        sunPos = [3, 9, 5];
        skyColor = 0x68788C;
        groundColor = 0x3A3632;
        ambientIntensity = 1.50;
        break;
      case 'HOSPITAL_ER':
        sunColor = 0xF8FAFC; // Soft clinical overhead lighting
        sunIntensity = 2.5;
        sunPos = [0, 12, 4];
        skyColor = 0xCBD5E1;
        groundColor = 0x64748B;
        ambientIntensity = 1.70;
        break;
      case 'DESERT_STATION':
        sunColor = 0xFFF3D0; // Blazing desert sun
        sunIntensity = 2.8;
        sunPos = [10, 18, 12];
        skyColor = 0xD4A373;
        groundColor = 0xBC6C25;
        ambientIntensity = 1.55;
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
      case 'RAIL_STATION':
        this.buildRailStationEnvironment();
        break;
      case 'HOSPITAL_ER':
        this.buildHospitalErEnvironment();
        break;
      case 'DESERT_STATION':
        this.buildDesertStationEnvironment();
        break;
      case 'ROBOTICS_LAB':
      default:
        this.buildRoboticsLabEnvironment();
        break;
    }

    // Build Narrative Story Prop on Opposing Third (Documentary Visual Signature)
    this.buildStoryProp(intent);
  }

  // ============================================================================
  // NARRATIVE STORY PROP BUILDER (Rule of Thirds opposing character)
  // ============================================================================
  private buildStoryProp(intent: string) {
    const propGroup = new THREE.Group();
    propGroup.name = 'story_prop_hero';

    if (intent === 'EDO_BRIDGE' || intent === 'EDO_HOUSE') {
      // Story Prop: Edo Milestone Stone Pillar + Glowing Paper Lantern + Sealed Imperial Scroll
      propGroup.userData = {
        elementId: 'story_prop_edo_scroll_pillar',
        canonicalName: 'Cột Mốc Lịch Sử & Cuộn Thư Niêm Phong Hoàng Gia (Edo Milestone & Imperial Scroll)',
        isStoryProp: true,
      };

      // 1. Weathered Stone Milestone Pillar (Staged on opposing right third)
      const stoneMat = new THREE.MeshStandardMaterial({
        color: 0x5C5852,
        roughness: 0.85,
        metalness: 0.1,
      });
      const pillar = new THREE.Mesh(new THREE.BoxGeometry(0.38, 1.4, 0.38), stoneMat);
      pillar.position.set(0, 0.7, 0);
      propGroup.add(pillar);

      // Engraved Kanji Placard on Pillar
      const woodPlateMat = new THREE.MeshStandardMaterial({
        color: 0x8C7052,
        roughness: 0.65,
      });
      const placard = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.65, 0.04), woodPlateMat);
      placard.position.set(0, 0.85, 0.20);
      propGroup.add(placard);

      // 2. Glowing Paper Lantern (Andon / Chochin) atop milestone
      const lanternFrameMat = new THREE.MeshStandardMaterial({
        color: 0x2A221C,
        roughness: 0.7,
      });
      const lanternPaperMat = new THREE.MeshStandardMaterial({
        color: 0xFFE8B0,
        emissive: 0xFFAA33,
        emissiveIntensity: 0.75,
        roughness: 0.4,
      });

      // Wooden Lantern Roof
      const roof = new THREE.Mesh(new THREE.ConeGeometry(0.32, 0.16, 4), lanternFrameMat);
      roof.rotation.y = Math.PI / 4;
      roof.position.set(0, 1.62, 0);
      propGroup.add(roof);

      // Glowing Lantern Body
      const lanternBody = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.32, 0.26), lanternPaperMat);
      lanternBody.position.set(0, 1.40, 0);
      propGroup.add(lanternBody);

      // Point Light casting warm amber glow onto story prop & surrounding scene
      const lanternLight = new THREE.PointLight(0xFFB04A, 1.8, 4.5);
      lanternLight.position.set(0, 1.40, 0.1);
      propGroup.add(lanternLight);

      // 3. Sealed Imperial Scroll Resting on Milestone Plinth
      const scrollPaperMat = new THREE.MeshStandardMaterial({
        color: 0xEDE2CE,
        roughness: 0.5,
      });
      const redRibbonMat = new THREE.MeshStandardMaterial({
        color: 0xBD2020,
        roughness: 0.35,
        metalness: 0.2,
      });

      const scrollCylinder = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.34, 16), scrollPaperMat);
      scrollCylinder.rotation.z = Math.PI / 2;
      scrollCylinder.rotation.y = 0.25;
      scrollCylinder.position.set(0, 1.44, 0.14);
      propGroup.add(scrollCylinder);

      // Red Wax Imperial Seal Band
      const seal = new THREE.Mesh(new THREE.CylinderGeometry(0.048, 0.048, 0.06, 16), redRibbonMat);
      seal.rotation.z = Math.PI / 2;
      seal.rotation.y = 0.25;
      seal.position.set(0, 1.44, 0.14);
      propGroup.add(seal);

      // Position on right third (X = +1.15) to balance Haru on left third (X = -1.0)
      const isBridge = intent === 'EDO_BRIDGE';
      propGroup.position.set(1.15, isBridge ? 2.65 : 0.45, 0.0);

    } else if (intent === 'CAFE') {
      // Steaming Brass Espresso Machine with Glowing Amber Portafilter
      propGroup.userData = {
        elementId: 'story_prop_espresso_machine',
        canonicalName: 'Máy Pha Cà Phê Đồng Cổ Điển (Classic Brass Espresso Machine)',
        isStoryProp: true,
      };
      const brassMat = new THREE.MeshStandardMaterial({ color: 0xD4AF37, roughness: 0.25, metalness: 0.9 });
      const boiler = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.65, 24), brassMat);
      boiler.position.set(0, 0.35, 0);
      propGroup.add(boiler);

      const dome = new THREE.Mesh(new THREE.SphereGeometry(0.28, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), brassMat);
      dome.position.set(0, 0.67, 0);
      propGroup.add(dome);

      const amberLight = new THREE.PointLight(0xFFA500, 1.5, 3.0);
      amberLight.position.set(0, 0.4, 0.3);
      propGroup.add(amberLight);

      propGroup.position.set(1.15, 0.95, 0.2);

    } else if (intent === 'ROBOTICS_LAB') {
      // Glowing Cybernetic Bipedal Chassis
      propGroup.userData = {
        elementId: 'story_prop_robot_chassis',
        canonicalName: 'Khung Xương Robot Hình Người (Cybernetic Bipedal Chassis)',
        isStoryProp: true,
      };
      const frameMat = new THREE.MeshStandardMaterial({ color: 0x3A4454, roughness: 0.35, metalness: 0.8 });
      const core = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.7, 0.25), frameMat);
      core.position.set(0, 0.8, 0);
      propGroup.add(core);

      const glowMat = new THREE.MeshStandardMaterial({ color: 0x00E5FF, emissive: 0x00C8FF, emissiveIntensity: 1.2 });
      const powerCell = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.25, 16), glowMat);
      powerCell.position.set(0, 0.8, 0.14);
      propGroup.add(powerCell);

      const cyanLight = new THREE.PointLight(0x00E5FF, 2.0, 4.0);
      cyanLight.position.set(0, 0.8, 0.3);
      propGroup.add(cyanLight);

      propGroup.position.set(1.15, 0.0, 0.3);
    } else {
      // Default Narrative Prop Landmark
      propGroup.userData = {
        elementId: 'story_prop_landmark',
        canonicalName: 'Biểu Tượng Cốt Truyện (Narrative Story Landmark)',
        isStoryProp: true,
      };
      const m = new THREE.MeshStandardMaterial({ color: 0xA08060, roughness: 0.6 });
      const box = new THREE.Mesh(new THREE.BoxGeometry(0.4, 1.2, 0.4), m);
      box.position.set(0, 0.6, 0);
      propGroup.add(box);
      propGroup.position.set(1.15, 1.0, 0.0);
    }

    this.scene.add(propGroup);
    this.storyPropGroup = propGroup;
  }

  // ----------------------------------------------------------------------------
  // 1. CAFE ENVIRONMENT (Hanoi Modern Coffee / Creative Tech Gathering)
  // ----------------------------------------------------------------------------
  private buildCafeEnvironment() {
    // 1. Herringbone Wood Floor with Warm Specular Sheen
    const floorGeo = new THREE.PlaneGeometry(36, 26);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x8D6E50,
      roughness: 0.35,
      metalness: 0.18,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, 0);
    this.scene.add(floor);

    // 2. Contemporary Acoustic Slatted Timber Back Wall
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x7D6858, roughness: 0.75 });
    const backWall = new THREE.Mesh(new THREE.BoxGeometry(32, 7.5, 0.2), wallMat);
    backWall.position.set(0, 3.75, -5.5);
    this.scene.add(backWall);

    // Vertical wooden decorative acoustic slats
    const slatMat = new THREE.MeshStandardMaterial({ color: 0xC4A482, roughness: 0.5 });
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

    // 4. Hero Café Tables & Chairs (Accurate Human Scale: Table 0.72m, Chair 0.45m)
    const tableTopMat = new THREE.MeshStandardMaterial({ color: 0x5D4037, roughness: 0.4, metalness: 0.2 });
    const castIronMat = new THREE.MeshStandardMaterial({ color: 0x1A1A1A, roughness: 0.7, metalness: 0.8 });

    // Center Meeting Table (Ergonomic Café Proportions: Diameter 0.84m, Height 0.72m)
    const centerTable = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.05, 24), tableTopMat);
    centerTable.position.set(0, 0.72, 0.2);
    this.scene.add(centerTable);

    const tablePedestal = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.20, 0.69, 16), castIronMat);
    tablePedestal.position.set(0, 0.35, 0.2);
    this.scene.add(tablePedestal);

    // Ergonomic Café Chairs (Seat height 0.45m, Width 0.46m)
    for (const [cx, cz, rot] of [[-0.75, 0.2, Math.PI / 2], [0.75, 0.2, -Math.PI / 2]]) {
      const chairSeat = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.05, 0.46), tableTopMat);
      chairSeat.position.set(cx, 0.45, cz);
      this.scene.add(chairSeat);

      const chairBack = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.45, 0.04), tableTopMat);
      chairBack.position.set(cx + (cx < 0 ? -0.22 : 0.22), 0.70, cz);
      this.scene.add(chairBack);

      // Chair Legs
      for (const [lx, lz] of [[-0.18, -0.18], [-0.18, 0.18], [0.18, -0.18], [0.18, 0.18]]) {
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.43, 8), castIronMat);
        leg.position.set(cx + lx, 0.22, cz + lz);
        this.scene.add(leg);
      }
    }

    // Ceramic Coffee Mugs on Table (Accurate 10cm height)
    const ceramicMat = new THREE.MeshStandardMaterial({ color: 0xFAF0E6, roughness: 0.25, metalness: 0.1 });
    const mug1 = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.05, 0.10, 16), ceramicMat);
    mug1.position.set(-0.20, 0.79, 0.15);
    this.scene.add(mug1);

    const mug2 = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.05, 0.10, 16), ceramicMat);
    mug2.position.set(0.20, 0.79, 0.25);
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
    const graniteMat = new THREE.MeshStandardMaterial({ color: 0x8E949E, roughness: 0.65 });
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
      color: 0x80858E,
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
    const stoneMat = new THREE.MeshStandardMaterial({ color: 0x8A8E94, roughness: 0.75 });
    const wallBack = new THREE.Mesh(new THREE.BoxGeometry(70, 4.5, 3.5), stoneMat);
    wallBack.position.set(0, 0.4, -8.0);
    this.scene.add(wallBack);

    // 2. High-Detail Arched Wooden Bridge (Taiko-bashi)
    const timberDarkMat = new THREE.MeshStandardMaterial({ color: 0x645042, roughness: 0.75 });
    const timberPlankMat = new THREE.MeshStandardMaterial({ color: 0x9E846C, roughness: 0.55, metalness: 0.15 });
    const bronzeFittingMat = new THREE.MeshStandardMaterial({ color: 0xB59D68, roughness: 0.35, metalness: 0.85 });

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

    // Bridge Deck Planks (With Dynamic Broken Plank at x = -0.2)
    for (let x = -11.0; x <= 11.0; x += 0.45) {
      const yArch = 2.65 - (x * x) * 0.007;
      if (Math.abs(x - (-0.2)) < 0.25) {
        // Dynamic broken plank where Haru slips at t=4.5s
        this.brokenPlank = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.20, 4.1), timberPlankMat);
        this.brokenPlank.position.set(x, yArch, 0);
        this.brokenPlankBaseX = x;
        this.brokenPlankBaseY = yArch;
        this.scene.add(this.brokenPlank);
      } else {
        const plank = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.22, 4.1), timberPlankMat);
        plank.position.set(x, yArch, 0);
        this.scene.add(plank);
      }
    }

    // Handrails, Balusters & Bronze Giboshi Finials
    const frontRailingGroup = new THREE.Group();
    frontRailingGroup.name = 'bridge_front_railing';
    frontRailingGroup.userData = {
      elementId: 'bridge_front_railing',
      canonicalName: 'Lan Can Gỗ Phía Trước (Front Bridge Railing)',
      isForeground: true,
      category: 'railing',
      baseZ: 2.05,
    };

    for (const z of [-2.05, 2.05]) {
      const isFront = z > 0;
      const targetParent = isFront ? frontRailingGroup : this.scene;

      const rail = new THREE.Mesh(new THREE.BoxGeometry(24, 0.25, 0.25), timberDarkMat);
      rail.position.set(0, 3.7, z);
      targetParent.add(rail);

      for (let x = -10; x <= 10; x += 1.25) {
        const yArch = 2.65 - (x * x) * 0.007;
        const baluster = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 1.15, 8), timberDarkMat);
        baluster.position.set(x, yArch + 0.55, z);
        targetParent.add(baluster);

        if (Math.abs(x) === 10 || Math.abs(x) === 0) {
          const cap = new THREE.Mesh(new THREE.SphereGeometry(0.18, 12, 12), bronzeFittingMat);
          cap.position.set(x, 3.9, z);
          targetParent.add(cap);
        }
      }
    }

    this.scene.add(frontRailingGroup);
    this.foregroundElements.push(frontRailingGroup);

    // Dynamic 3D Falling Waraji Sandal Prop
    const sandalGeo = new THREE.BoxGeometry(0.24, 0.08, 0.55);
    const sandalMat = new THREE.MeshStandardMaterial({ color: 0xC8A868, roughness: 0.9 });
    this.fallingSandalMesh = new THREE.Mesh(sandalGeo, sandalMat);
    this.fallingSandalMesh.position.set(0.4, 1.2, -1.8);
    this.fallingSandalMesh.rotation.set(0.4, 0.2, 0.6);
    this.fallingSandalMesh.visible = false;
    this.scene.add(this.fallingSandalMesh);
  }

  // ----------------------------------------------------------------------------
  // 5. EDO HOUSE ENVIRONMENT (Period-Authentic Japanese Interior & Engawa)
  // ----------------------------------------------------------------------------
  private buildEdoHouseEnvironment() {
    // 1. Garden Ground & Cobblestones (Y = 0.0)
    const gardenMat = new THREE.MeshStandardMaterial({ color: 0x363028, roughness: 0.85 });
    const gardenFloor = new THREE.Mesh(new THREE.PlaneGeometry(35, 12), gardenMat);
    gardenFloor.rotation.x = -Math.PI / 2;
    gardenFloor.position.set(0, 0, 4.0);
    this.scene.add(gardenFloor);

    // Stepping stones (Kutsunugi-ishi)
    const stoneMat = new THREE.MeshStandardMaterial({ color: 0x5A544C, roughness: 0.9 });
    for (const sx of [-1.2, 0.0, 1.2]) {
      const stepStone = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.52, 0.22, 12), stoneMat);
      stepStone.position.set(sx, 0.11, 1.4);
      this.scene.add(stepStone);
    }

    // 2. Raised Wooden Veranda (Engawa) at Y = 0.45
    const cedarMat = new THREE.MeshStandardMaterial({ color: 0x8D6E50, roughness: 0.35, metalness: 0.1 });
    const engawa = new THREE.Mesh(new THREE.BoxGeometry(26, 0.18, 2.2), cedarMat);
    engawa.position.set(0, 0.36, 0.3);
    this.scene.add(engawa);

    // Veranda support posts
    const postDarkMat = new THREE.MeshStandardMaterial({ color: 0x4E3629, roughness: 0.65 });
    for (let px = -11; px <= 11; px += 3.5) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.45, 0.16), postDarkMat);
      post.position.set(px, 0.22, 1.2);
      this.scene.add(post);
    }

    // 3. Authentic 8-Mat Tatami Room (Y = 0.45, z < -0.6)
    const tatamiMatMat = new THREE.MeshStandardMaterial({ color: 0xC6B88E, roughness: 0.65 }); // Rush straw
    const heriBorderMat = new THREE.MeshStandardMaterial({ color: 0x243324, roughness: 0.5 }); // Dark green/black cloth border

    // Traditional 8-mat layout (Mats are 1.8m x 0.9m x 0.06m)
    const matPositions = [
      [-0.9, -1.5, 0], [0.9, -1.5, 0],
      [-1.8, -2.4, Math.PI / 2], [1.8, -2.4, Math.PI / 2],
      [-0.9, -3.3, 0], [0.9, -3.3, 0],
      [-1.8, -4.2, Math.PI / 2], [1.8, -4.2, Math.PI / 2]
    ];
    for (const [tx, tz, trot] of matPositions) {
      const mat = new THREE.Mesh(new THREE.BoxGeometry(0.88, 0.05, 1.78), tatamiMatMat);
      mat.position.set(tx, 0.46, tz);
      mat.rotation.y = trot;
      this.scene.add(mat);

      // Long-edge cloth borders (Heri)
      for (const edgeOffset of [-0.43, 0.43]) {
        const border = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.055, 1.78), heriBorderMat);
        border.position.set(tx + edgeOffset, 0.465, tz);
        border.rotation.y = trot;
        this.scene.add(border);
      }
    }

    // 4. Hinoki Timber Pillars & Upper Beam Lintel (Kamoi)
    for (const colX of [-6.2, -2.2, 2.2, 6.2]) {
      const pillar = new THREE.Mesh(new THREE.BoxGeometry(0.22, 3.4, 0.22), postDarkMat);
      pillar.position.set(colX, 2.15, -0.7);
      this.scene.add(pillar);
    }
    const lintelBeam = new THREE.Mesh(new THREE.BoxGeometry(16, 0.22, 0.24), postDarkMat);
    lintelBeam.position.set(0, 3.75, -0.7);
    this.scene.add(lintelBeam);

    // 5. Authentic Shoji Sliding Screens with Kumiko Latticework Grid
    const shojiPaperMat = new THREE.MeshStandardMaterial({
      color: 0xFCF8EE,
      roughness: 0.55,
      emissive: 0x664422,
      emissiveIntensity: 0.42,
    });
    const shojiFrameMat = new THREE.MeshStandardMaterial({ color: 0x3E2723, roughness: 0.6 });

    // Shoji panels in background
    for (let sx = -5.0; sx <= 5.0; sx += 2.5) {
      const paperPanel = new THREE.Mesh(new THREE.BoxGeometry(2.4, 3.2, 0.04), shojiPaperMat);
      paperPanel.position.set(sx, 2.05, -5.2);
      this.scene.add(paperPanel);

      // Outer timber frame
      const frameL = new THREE.Mesh(new THREE.BoxGeometry(0.08, 3.2, 0.06), shojiFrameMat);
      frameL.position.set(sx - 1.16, 2.05, -5.18);
      this.scene.add(frameL);
      const frameR = new THREE.Mesh(new THREE.BoxGeometry(0.08, 3.2, 0.06), shojiFrameMat);
      frameR.position.set(sx + 1.16, 2.05, -5.18);
      this.scene.add(frameR);

      // Fine Kumiko horizontal & vertical wooden grid
      for (let gy = 0.8; gy <= 3.3; gy += 0.35) {
        const hSlat = new THREE.Mesh(new THREE.BoxGeometry(2.35, 0.025, 0.05), shojiFrameMat);
        hSlat.position.set(sx, gy, -5.18);
        this.scene.add(hSlat);
      }
      for (let gx = sx - 0.9; gx <= sx + 0.9; gx += 0.45) {
        const vSlat = new THREE.Mesh(new THREE.BoxGeometry(0.025, 3.15, 0.05), shojiFrameMat);
        vSlat.position.set(gx, 2.05, -5.18);
        this.scene.add(vSlat);
      }
    }

    // 6. Traditional Low Wooden Chabudai Tea Table & Ceramic Set
    const lacquerMat = new THREE.MeshStandardMaterial({ color: 0x2A1810, roughness: 0.25, metalness: 0.4 });
    const chabudai = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 0.04, 20), lacquerMat);
    chabudai.position.set(0, 0.68, -2.4);
    this.scene.add(chabudai);
    for (const [lx, lz] of [[-0.3, -0.3], [-0.3, 0.3], [0.3, -0.3], [0.3, 0.3]]) {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.02, 0.18, 8), lacquerMat);
      leg.position.set(lx, 0.57, -2.4 + lz);
      this.scene.add(leg);
    }

    // Ceramic Kyusu teapot & cups on table
    const celadonMat = new THREE.MeshStandardMaterial({ color: 0xA4C3B2, roughness: 0.3, metalness: 0.2 });
    const teapot = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.09, 0.12, 12), celadonMat);
    teapot.position.set(-0.12, 0.76, -2.4);
    this.scene.add(teapot);
    const teacup = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.03, 0.06, 12), celadonMat);
    teacup.position.set(0.12, 0.73, -2.35);
    this.scene.add(teacup);

    // 7. Hanging Red/Warm Chochin & Andon Paper Lanterns with Warm Candlelight
    const lanternPaperMat = new THREE.MeshStandardMaterial({
      color: 0xCC2B2B, // Festive vermillion red washi
      roughness: 0.4,
      emissive: 0xFF5522,
      emissiveIntensity: 0.75,
    });
    const frontLanternGroup = new THREE.Group();
    frontLanternGroup.name = 'house_front_lanterns';
    frontLanternGroup.userData = {
      elementId: 'house_front_lanterns',
      canonicalName: 'Đèn Lồng Đỏ Phía Trước (Front Chochin Lanterns)',
      isForeground: true,
      category: 'lantern',
      baseZ: -0.4,
    };

    for (const lx of [-2.8, 2.8]) {
      const lantern = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.24, 0.65, 16), lanternPaperMat);
      lantern.position.set(lx, 2.85, -0.4);
      frontLanternGroup.add(lantern);

      const lanternCap = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.05, 16), lacquerMat);
      lanternCap.position.set(lx, 3.20, -0.4);
      frontLanternGroup.add(lanternCap);

      const lanternLight = new THREE.PointLight(0xFFA544, 2.8, 8.5);
      lanternLight.position.set(lx, 2.85, -0.4);
      this.scene.add(lanternLight);
      this.animatedLights.push({ light: lanternLight, baseIntensity: 2.8, freq: 3.2, phase: Math.abs(lx) });
    }
    this.scene.add(frontLanternGroup);
    this.foregroundElements.push(frontLanternGroup);
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
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x788698, roughness: 0.22, metalness: 0.45 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, 0);
    this.scene.add(floor);

    const rackMat = new THREE.MeshStandardMaterial({ color: 0x586678, roughness: 0.45, metalness: 0.6 });
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

  // ----------------------------------------------------------------------------
  // 8. RAILWAY STATION ENVIRONMENT (Shanghai 1930s Night Train Platform)
  // ----------------------------------------------------------------------------
  private buildRailStationEnvironment() {
    // 1. Wet Platform Floor (Flagstone with specular rain sheen)
    const platGeo = new THREE.PlaneGeometry(36, 12);
    const platMat = new THREE.MeshStandardMaterial({ color: 0x505860, roughness: 0.38, metalness: 0.25 });
    const platform = new THREE.Mesh(platGeo, platMat);
    platform.rotation.x = -Math.PI / 2;
    platform.position.set(0, 0.45, 1.5);
    this.scene.add(platform);

    // Platform edge coping stones
    const edgeMat = new THREE.MeshStandardMaterial({ color: 0xD4B886, roughness: 0.5 });
    const edge = new THREE.Mesh(new THREE.BoxGeometry(36, 0.5, 0.4), edgeMat);
    edge.position.set(0, 0.25, -4.3);
    this.scene.add(edge);

    // 2. Track Ballast Bed & Steel Railway Tracks
    const ballastMat = new THREE.MeshStandardMaterial({ color: 0x32353A, roughness: 0.9 });
    const ballast = new THREE.Mesh(new THREE.PlaneGeometry(36, 8), ballastMat);
    ballast.rotation.x = -Math.PI / 2;
    ballast.position.set(0, 0.0, -8.2);
    this.scene.add(ballast);

    // Wooden railway cross-ties (sleepers)
    const sleeperMat = new THREE.MeshStandardMaterial({ color: 0x3A2B20, roughness: 0.85 });
    for (let x = -16; x <= 16; x += 1.2) {
      const sleeper = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.15, 3.2), sleeperMat);
      sleeper.position.set(x, 0.08, -8.0);
      this.scene.add(sleeper);
    }

    // Steel rails
    const railMat = new THREE.MeshStandardMaterial({ color: 0xA8B2BC, roughness: 0.25, metalness: 0.85 });
    for (const rz of [-8.9, -7.1]) {
      const rail = new THREE.Mesh(new THREE.BoxGeometry(36, 0.2, 0.12), railMat);
      rail.position.set(0, 0.22, rz);
      this.scene.add(rail);
    }

    // 3. Station Brick Wall & Canopy Columns
    const brickMat = new THREE.MeshStandardMaterial({ color: 0x5C382C, roughness: 0.8 });
    const backWall = new THREE.Mesh(new THREE.BoxGeometry(36, 8.0, 0.5), brickMat);
    backWall.position.set(0, 4.4, 7.2);
    this.scene.add(backWall);

    // Cast-iron canopy columns
    const ironMat = new THREE.MeshStandardMaterial({ color: 0x242830, roughness: 0.45, metalness: 0.7 });
    for (const cx of [-10, 0, 10]) {
      const col = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.26, 6.0, 16), ironMat);
      col.position.set(cx, 3.45, 1.2);
      this.scene.add(col);

      // Hanging vintage lantern
      const lanternMat = new THREE.MeshStandardMaterial({ color: 0xD4A017, metalness: 0.8 });
      const lantern = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.8, 0.6), lanternMat);
      lantern.position.set(cx, 5.2, 0.6);
      this.scene.add(lantern);

      const lampLight = new THREE.PointLight(0xFFB042, 2.2, 12);
      lampLight.position.set(cx, 4.8, 0.6);
      this.scene.add(lampLight);
      this.animatedLights.push({ light: lampLight, baseIntensity: 2.2, freq: 5.0, phase: Math.abs(cx) });
    }

    // Vintage leather luggage trunks
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5A3825, roughness: 0.6 });
    const trunk1 = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.8, 0.9), trunkMat);
    trunk1.position.set(-3.5, 0.85, 3.2);
    this.scene.add(trunk1);
  }

  // ----------------------------------------------------------------------------
  // 9. HOSPITAL EMERGENCY ROOM (Chợ Rẫy Hospital ER / Modern Medical)
  // ----------------------------------------------------------------------------
  private buildHospitalErEnvironment() {
    // 1. Clinical Reflective Terrazzo Floor
    const floorGeo = new THREE.PlaneGeometry(36, 26);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0xD8DFE6, roughness: 0.25, metalness: 0.20 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, 0);
    this.scene.add(floor);

    // 2. Hospital Partition Wall & Dado Rail
    const wallMat = new THREE.MeshStandardMaterial({ color: 0xF0F4F8, roughness: 0.7 });
    const backWall = new THREE.Mesh(new THREE.BoxGeometry(32, 7.5, 0.2), wallMat);
    backWall.position.set(0, 3.75, -5.5);
    this.scene.add(backWall);

    // Mint green hygienic bumper rail
    const bumperMat = new THREE.MeshStandardMaterial({ color: 0x52B788, roughness: 0.4 });
    const bumper = new THREE.Mesh(new THREE.BoxGeometry(32, 0.35, 0.1), bumperMat);
    bumper.position.set(0, 1.8, -5.35);
    this.scene.add(bumper);

    // 3. Hospital Patient Bed / Gurney
    const bedFrameMat = new THREE.MeshStandardMaterial({ color: 0xE2E8F0, roughness: 0.3, metalness: 0.6 });
    const bed = new THREE.Mesh(new THREE.BoxGeometry(4.2, 0.6, 2.2), bedFrameMat);
    bed.position.set(-3.5, 1.1, -2.5);
    this.scene.add(bed);

    // White mattress & pillow
    const linenMat = new THREE.MeshStandardMaterial({ color: 0xFFFFFF, roughness: 0.8 });
    const mattress = new THREE.Mesh(new THREE.BoxGeometry(4.0, 0.35, 2.0), linenMat);
    mattress.position.set(-3.5, 1.55, -2.5);
    this.scene.add(mattress);

    const pillow = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.25, 1.4), linenMat);
    pillow.position.set(-5.0, 1.8, -2.5);
    this.scene.add(pillow);

    // 4. Stainless Steel IV Drip Stand
    const steelMat = new THREE.MeshStandardMaterial({ color: 0xD0D7DE, roughness: 0.2, metalness: 0.85 });
    const ivPole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 4.5, 12), steelMat);
    ivPole.position.set(-1.0, 2.25, -2.2);
    this.scene.add(ivPole);

    const salineBagMat = new THREE.MeshStandardMaterial({ color: 0xE0F2FE, transparent: true, opacity: 0.75 });
    const salineBag = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.5, 0.15), salineBagMat);
    salineBag.position.set(-1.0, 4.0, -2.2);
    this.scene.add(salineBag);

    // 5. Vital Signs Telemetry Monitor (ECG Waveform Screen)
    const monitorMat = new THREE.MeshStandardMaterial({ color: 0x1E293B, roughness: 0.3 });
    const monitor = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.9, 0.3), monitorMat);
    monitor.position.set(-0.2, 2.8, -3.2);
    this.scene.add(monitor);

    // Glowing green screen
    const screenMat = new THREE.MeshBasicMaterial({ color: 0x00FF88 });
    const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.0, 0.7), screenMat);
    screen.position.set(-0.2, 2.8, -3.04);
    this.scene.add(screen);

    const monitorLight = new THREE.PointLight(0x00FF88, 1.5, 5);
    monitorLight.position.set(-0.2, 2.8, -2.8);
    this.scene.add(monitorLight);
    this.animatedLights.push({ light: monitorLight, baseIntensity: 1.5, freq: 3.0, phase: 0.5 });
  }

  // ----------------------------------------------------------------------------
  // 10. DESERT OBSERVATION STATION (Sahara 2050 Weather Station)
  // ----------------------------------------------------------------------------
  private buildDesertStationEnvironment() {
    // 1. Undulating Golden Sand Dune Terrain
    const sandGeo = new THREE.PlaneGeometry(50, 40, 24, 24);
    const pos = sandGeo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const u = pos.getX(i);
      const v = pos.getY(i);
      const duneHeight = Math.sin(u * 0.15) * 1.8 + Math.cos(v * 0.2) * 1.2;
      pos.setZ(i, duneHeight);
    }
    sandGeo.computeVertexNormals();

    const sandMat = new THREE.MeshStandardMaterial({ color: 0xD4A373, roughness: 0.9, metalness: 0.05 });
    const terrain = new THREE.Mesh(sandGeo, sandMat);
    terrain.rotation.x = -Math.PI / 2;
    terrain.position.set(0, 0, 0);
    this.scene.add(terrain);

    // 2. Futuristic Geodesic Weather Dome
    const domeMat = new THREE.MeshStandardMaterial({ color: 0xEEF2F6, roughness: 0.35, metalness: 0.5 });
    const dome = new THREE.Mesh(new THREE.SphereGeometry(5.2, 24, 16, 0, Math.PI * 2, 0, Math.PI * 0.5), domeMat);
    dome.position.set(-7.5, 0.5, -6.5);
    this.scene.add(dome);

    // Panoramic observation port
    const glassMat = new THREE.MeshStandardMaterial({ color: 0x0EA5E9, roughness: 0.1, metalness: 0.85 });
    const windowBand = new THREE.Mesh(new THREE.CylinderGeometry(4.2, 4.8, 1.2, 24, 1, true, 0, Math.PI), glassMat);
    windowBand.position.set(-7.5, 3.2, -6.5);
    this.scene.add(windowBand);

    // 3. Solar Photovoltaic Array
    const panelMat = new THREE.MeshStandardMaterial({ color: 0x1E3A8A, roughness: 0.2, metalness: 0.8 });
    for (const sx of [3.5, 7.5]) {
      const panel = new THREE.Mesh(new THREE.BoxGeometry(3.2, 0.1, 2.0), panelMat);
      panel.rotation.x = 0.45;
      panel.position.set(sx, 1.8, -4.5);
      this.scene.add(panel);

      const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 1.8), domeMat);
      stand.position.set(sx, 0.9, -4.5);
      this.scene.add(stand);
    }

    // 4. Telemetry Sensor Mast with Flashing Beacon
    const mastMat = new THREE.MeshStandardMaterial({ color: 0x64748B, roughness: 0.4, metalness: 0.7 });
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.18, 9.0, 12), mastMat);
    mast.position.set(6.5, 4.5, -7.0);
    this.scene.add(mast);

    const beaconLight = new THREE.PointLight(0xEF4444, 2.5, 15);
    beaconLight.position.set(6.5, 9.2, -7.0);
    this.scene.add(beaconLight);
    this.animatedLights.push({ light: beaconLight, baseIntensity: 2.5, freq: 6.0, phase: 0.0 });
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

    // 5. Dynamic Bridge Plank Snap Simulation (Haru slips at t = 4.5s)
    if (this.brokenPlank) {
      if (timeSeconds < 4.5) {
        this.brokenPlank.position.set(this.brokenPlankBaseX, this.brokenPlankBaseY, 0);
        this.brokenPlank.rotation.set(0, 0, 0);
      } else {
        // Plank violently snaps, pivots down 45 degrees, revealing a dark gap in the bridge deck
        const dt = Math.min(3.0, timeSeconds - 4.5);
        this.brokenPlank.rotation.z = -0.78 * Math.min(1.0, dt * 4.0);
        this.brokenPlank.position.y = this.brokenPlankBaseY - 0.55 * Math.min(1.0, dt * 3.0);
        this.brokenPlank.position.x = this.brokenPlankBaseX + 0.18 * Math.min(1.0, dt * 3.0);
      }
    }

    // 6. Dynamic Falling Waraji Sandal
    if (this.fallingSandalMesh) {
      if (timeSeconds < 4.5) {
        this.fallingSandalMesh.visible = false;
      } else {
        this.fallingSandalMesh.visible = true;
        const fallT = Math.min(1.0, (timeSeconds - 4.5) / 4.0);
        this.fallingSandalMesh.position.y = 2.4 - fallT * 3.2;
        this.fallingSandalMesh.position.x = 0.25 + fallT * 0.9;
        this.fallingSandalMesh.position.z = -0.5 - fallT * 1.2;
        this.fallingSandalMesh.rotation.x += 0.06;
        this.fallingSandalMesh.rotation.y += 0.04;
      }
    }

    // 7. Camera Keyframe Interpolation
    this.updateCamera(timeSeconds);
  }

  public getDefaultCameraPosition(): [number, number, number] {
    const intent = this.getSemanticIntent();
    switch (intent) {
      case 'EDO_BRIDGE':
        return [-2.0, 4.5, 7.2];
      case 'RAIL_STATION':
        return [2.0, 2.4, 5.8];
      case 'CAFE':
        return [-1.5, 1.9, 6.8];
      case 'HOSPITAL_ER':
        return [0.0, 1.9, 6.8];
      case 'DESERT_STATION':
        return [-3.0, 2.6, 6.8];
      case 'ANTARCTIC':
        return [-3.0, 2.8, 7.0];
      case 'VICTORIAN_THAMES':
        return [-2.0, 3.0, 6.8];
      case 'EDO_HOUSE':
        return [0.0, 2.4, 7.2];
      case 'ROBOTICS_LAB':
        return [-1.5, 1.9, 6.8];
      case 'NEOCLASSICAL':
      default:
        return [-2.0, 2.6, 7.2];
    }
  }

  public getDefaultCameraTarget(): [number, number, number] {
    const intent = this.getSemanticIntent();
    switch (intent) {
      case 'EDO_BRIDGE':
        return [0.1, 5.0, 0.0];
      case 'RAIL_STATION':
        return [-0.6, 2.75, -0.8];
      case 'CAFE':
        return [0.0, 2.25, 0.0];
      case 'HOSPITAL_ER':
        return [0.1, 2.25, 0.0];
      case 'DESERT_STATION':
        return [0.2, 3.05, -1.0];
      case 'ANTARCTIC':
        return [0.0, 3.25, 0.0];
      case 'VICTORIAN_THAMES':
        return [0.0, 3.48, 0.0];
      case 'EDO_HOUSE':
        return [0.0, 2.80, 0.0];
      case 'ROBOTICS_LAB':
        return [0.0, 2.25, 0.0];
      case 'NEOCLASSICAL':
      default:
        return [0.0, 3.05, 0.0];
    }
  }

  public getOverheadStructures(): OverheadStructureDef[] {
    const intent = this.getSemanticIntent();
    switch (intent) {
      case 'EDO_BRIDGE':
        return [
          {
            id: 'edo_bridge_deck_underpass',
            name: 'Edo Wooden Bridge Deck & Underside Beams',
            minX: -12.0,
            maxX: 12.0,
            minZ: -2.8,
            maxZ: 2.8,
            clearanceY: 2.65,
            description: 'Camera framed beneath the bridge deck/underpass'
          }
        ];
      case 'RAIL_STATION':
        return [
          {
            id: 'rail_pedestrian_underpass',
            name: 'Shanghai Station Pedestrian Tunnel Underpass',
            minX: -8.0,
            maxX: 8.0,
            minZ: -3.0,
            maxZ: 3.0,
            clearanceY: 2.20,
            description: 'Camera framed inside low pedestrian underpass'
          },
          {
            id: 'train_shed_canopy_low',
            name: 'Platform Canopy Low Eaves',
            minX: -16.0,
            maxX: 16.0,
            minZ: -5.0,
            maxZ: 5.0,
            clearanceY: 2.10,
            description: 'Camera tucked under platform canopy eaves looking up'
          }
        ];
      case 'EDO_HOUSE':
        return [
          {
            id: 'edo_house_veranda_eaves',
            name: 'Engawa Low Timber Roof Eaves',
            minX: -6.0,
            maxX: 6.0,
            minZ: -1.0,
            maxZ: 3.0,
            clearanceY: 1.60,
            description: 'Camera framed beneath low house eaves'
          }
        ];
      case 'CAFE':
        return [
          {
            id: 'cafe_pergola_awning',
            name: 'Low Acoustic Timber Ceiling & Awning',
            minX: -8.0,
            maxX: 8.0,
            minZ: -3.5,
            maxZ: 3.5,
            clearanceY: 1.70,
            description: 'Camera framed under low café ceiling structure'
          }
        ];
      case 'NEOCLASSICAL':
        return [
          {
            id: 'colonnade_portico_ceiling',
            name: 'Neoclassical Colonnade Portico',
            minX: -14.0,
            maxX: 14.0,
            minZ: -2.5,
            maxZ: 2.5,
            clearanceY: 2.40,
            description: 'Camera framed beneath portico ceiling'
          }
        ];
      default:
        return [];
    }
  }

  public checkOverheadStructure(camPos: [number, number, number], isClaustrophobic: boolean): {
    violated: boolean;
    structureId?: string;
    structureName?: string;
    clearanceY?: number;
    isPermitted: boolean;
  } {
    const structures = this.getOverheadStructures();
    for (const s of structures) {
      if (
        camPos[0] >= s.minX &&
        camPos[0] <= s.maxX &&
        camPos[2] >= s.minZ &&
        camPos[2] <= s.maxZ &&
        camPos[1] < s.clearanceY
      ) {
        if (isClaustrophobic) {
          return {
            violated: false,
            structureId: s.id,
            structureName: s.name,
            clearanceY: s.clearanceY,
            isPermitted: true,
          };
        } else {
          return {
            violated: true,
            structureId: s.id,
            structureName: s.name,
            clearanceY: s.clearanceY,
            isPermitted: false,
          };
        }
      }
    }
    return { violated: false, isPermitted: false };
  }

  public evaluateCameraFraming(timeSeconds: number, actors: any[] = [], shotTag?: string): CameraFramingAudit {
    const camPos = [this.camera.position.x, this.camera.position.y, this.camera.position.z] as [number, number, number];
    const isClaustrophobic = shotTag === 'claustrophobic/reveal' ||
      shotTag === 'claustrophobic' ||
      shotTag === 'reveal' ||
      (this.dna as any).shot_tag === 'claustrophobic/reveal' ||
      (this.dna as any).shot_tag === 'claustrophobic' ||
      (this.dna as any).shot_tag === 'reveal' ||
      (this.dna as any).composition === 'claustrophobic' ||
      (this.dna as any).composition === 'reveal';

    // 1. Check overhead structure clearance
    const overheadCheck = this.checkOverheadStructure(camPos, isClaustrophobic);

    // 2. Measure foreground/overhead structure screen height coverage (Rule 6: max 35%)
    let maxForegroundCoverage = 0;
    let excessiveStructureName: string | undefined;
    const structs = this.getOverheadStructures();
    for (const s of structs) {
      if (s.clearanceY <= camPos[1]) continue; // Structure is beneath camera, not an overhead structure
      const pts: Array<[number, number, number]> = [
        [s.minX, s.clearanceY, s.minZ],
        [s.maxX, s.clearanceY, s.minZ],
        [s.minX, s.clearanceY, s.maxZ],
        [s.maxX, s.clearanceY, s.maxZ],
        [s.minX, s.clearanceY + 0.8, s.minZ],
        [s.maxX, s.clearanceY + 0.8, s.maxZ],
      ];
      let sMinY = this.height;
      let sMaxY = 0;
      let inFrustum = false;
      const camDir = new THREE.Vector3();
      this.camera.getWorldDirection(camDir);

      for (const p of pts) {
        const v = new THREE.Vector3(...p);
        const toPt = v.sub(this.camera.position);
        if (toPt.dot(camDir) > 0.1) {
          inFrustum = true;
          const proj = this.projectToScreen(p);
          if (proj.y < sMinY) sMinY = proj.y;
          if (proj.y > sMaxY) sMaxY = proj.y;
        }
      }
      if (inFrustum && sMaxY > sMinY) {
        const span = Math.max(0, Math.min(this.height, sMaxY) - Math.max(0, sMinY));
        const cov = span / this.height;
        if (cov > maxForegroundCoverage) {
          maxForegroundCoverage = cov;
          if (cov > 0.35) {
            excessiveStructureName = s.name;
          }
        }
      }
    }

    const foregroundViolation = (maxForegroundCoverage > 0.35) && !isClaustrophobic;

    // 3. Project actors to screen
    let minHeadY = this.height;
    let maxFeetY = 0;

    for (const actor of actors) {
      const pos3D = this.getActorWorldPosition(actor, timeSeconds);
      const feetProj = this.projectToScreen(pos3D);
      const headPos3D: [number, number, number] = [pos3D[0], pos3D[1] + 1.72, pos3D[2]];
      const headProj = this.projectToScreen(headPos3D);

      if (headProj.y < minHeadY) minHeadY = headProj.y;
      if (feetProj.y > maxFeetY) maxFeetY = feetProj.y;
    }

    if (actors.length === 0) {
      const gy = this.getGroundHeight(0, 0);
      const feetProj = this.projectToScreen([0, gy, 0]);
      const headProj = this.projectToScreen([0, gy + 1.72, 0]);
      minHeadY = headProj.y;
      maxFeetY = feetProj.y;
    }

    const skyFraction = minHeadY / this.height;
    const lowerMiddleThirdOccupied = minHeadY >= (0.38 * this.height) && maxFeetY <= (1.05 * this.height);
    const passed = (skyFraction >= 0.58 || isClaustrophobic) && !overheadCheck.violated && !foregroundViolation;

    return {
      timeSeconds,
      cameraPosition: [Number(camPos[0].toFixed(2)), Number(camPos[1].toFixed(2)), Number(camPos[2].toFixed(2))],
      cameraTarget: this.dna.camera_initial?.target ?? this.getDefaultCameraTarget(),
      skyFraction: Number(skyFraction.toFixed(3)),
      lowerMiddleThirdOccupied,
      characterHeadScreenY: Number(minHeadY.toFixed(1)),
      characterFeetScreenY: Number(maxFeetY.toFixed(1)),
      overheadStructureViolation: overheadCheck.violated,
      overheadStructureName: overheadCheck.structureName,
      foregroundStructureCoverage: Number(maxForegroundCoverage.toFixed(3)),
      foregroundStructureViolation: foregroundViolation,
      isClaustrophobicReveal: isClaustrophobic,
      passed,
    };
  }

  public updateCamera(t: number) {
    const kfs = this.dna.camera_keyframes;
    if (!kfs || kfs.length === 0) {
      const basePos = this.dna.camera_initial?.position ?? this.getDefaultCameraPosition();
      const baseTgt = this.dna.camera_initial?.target ?? this.getDefaultCameraTarget();
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
  // ENVIRONMENT GROUND HEIGHT QUERY (Eliminates Disconnected / Sinking Feet)
  // ============================================================================
  public getGroundHeight(x: number, z: number): number {
    const intent = this.getSemanticIntent();
    switch (intent) {
      case 'RAIL_STATION':
        // Platform floor is at Y = 0.45 for z > -4.0, Track ballast at Y = 0.08 for z <= -4.0
        return z > -4.0 ? 0.45 : 0.08;

      case 'DESERT_STATION': {
        // High-tech observation deck at center / station
        if (Math.hypot(x, z) < 4.0) return 0.65;
        // Undulating sand dunes
        return Math.sin(x * 0.15) * 1.8 + Math.cos(z * 0.2) * 1.2;
      }

      case 'HOSPITAL_ER':
      case 'CAFE':
      case 'ROBOTICS_LAB':
        return 0.0; // Flat polished floor

      case 'EDO_BRIDGE':
        // Bridge deck is at Y = 2.65 for canal crossing
        return 2.65;

      case 'EDO_HOUSE':
        // Wooden engawa porch at Y = 0.45, garden path at Y = 0.0
        return z < 1.0 ? 0.45 : 0.0;

      case 'ANTARCTIC':
        // Raised modular station platform at Y = 0.85, ice sheet at Y = 0.0
        return Math.hypot(x, z) < 5.0 ? 0.85 : 0.0;

      case 'VICTORIAN_THAMES':
        // Embankment stone quay at Y = 1.10
        return 1.10;

      case 'NEOCLASSICAL':
        // Colonnade loggia at Y = 0.65
        return 0.65;

      default:
        return 0.0;
    }
  }

  // ============================================================================
  // COORDINATE PROJECTION: 3D WORLD -> 2D SCREEN PIXELS (Optically Accurate)
  // ============================================================================
  public projectToScreen(pos3D: [number, number, number]): {
    x: number;
    y: number;
    z: number;
    distance: number;
    scale: number;
    inSafeFrame: boolean;
  } {
    const worldPos = new THREE.Vector3(...pos3D);

    // 1. Camera View Space Distance
    const camPos = this.camera.position;
    const viewDistance = Math.max(0.5, worldPos.distanceTo(camPos));

    // 2. Exact Perspective Scale: screen px per meter
    const halfFovRad = ((this.camera.fov || 44) * Math.PI) / 360;
    const pxPerMeter = (this.height * 0.5) / (Math.tan(halfFovRad) * viewDistance);

    // Standard adult character height ~1.72m mapped from canonical 300px rig
    const canonicalRigHeightPx = 300;
    const adultHeightMeters = 1.72;
    const perspectiveScale = (adultHeightMeters * pxPerMeter) / canonicalRigHeightPx;

    // 3. Screen NDC Projection
    const v = worldPos.clone().project(this.camera);
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
      distance: viewDistance,
      scale: Math.max(0.45, Math.min(2.20, perspectiveScale)),
      inSafeFrame,
    };
  }

  // ============================================================================
  // DEPTH-SORTING & OCCLUSION INVARIANT ENGINE
  // "Depth-sort all scene elements (props, characters, environment) by their
  //  z-distance from camera every frame, not just at scene setup.
  //  Re-evaluate occlusion whenever a character's world position changes relative
  //  to a foreground object."
  // ============================================================================
  public getCameraDistance(worldPos: THREE.Vector3 | [number, number, number]): number {
    const v = Array.isArray(worldPos) ? new THREE.Vector3(...worldPos) : worldPos;
    return v.distanceTo(this.camera.position);
  }

  public getViewSpaceZ(worldPos: THREE.Vector3 | [number, number, number]): number {
    const v = Array.isArray(worldPos) ? new THREE.Vector3(...worldPos) : worldPos;
    const viewPos = v.clone().applyMatrix4(this.camera.matrixWorldInverse);
    return -viewPos.z; // Positive distance along camera look vector
  }

  public getActorWorldPosition(actor: any, t: number): [number, number, number] {
    const cues = actor.performance_cues || [];
    let pos = actor.staging?.initial_world_pos || [0, 0, 0];
    if (cues.length > 0) {
      if (t <= cues[0].time) {
        pos = cues[0].pos;
      } else if (t >= cues[cues.length - 1].time) {
        pos = cues[cues.length - 1].pos;
      } else {
        for (let i = 0; i < cues.length - 1; i++) {
          const c0 = cues[i];
          const c1 = cues[i + 1];
          if (t >= c0.time && t <= c1.time) {
            const alpha = (t - c0.time) / (c1.time - c0.time);
            pos = [
              c0.pos[0] + (c1.pos[0] - c0.pos[0]) * alpha,
              c0.pos[1] + (c1.pos[1] - c0.pos[1]) * alpha,
              c0.pos[2] + (c1.pos[2] - c0.pos[2]) * alpha,
            ];
            break;
          }
        }
      }
    }
    return [pos[0], pos[1], pos[2]];
  }

  public getForegroundElements(): THREE.Object3D[] {
    return this.foregroundElements;
  }

  public evaluateSceneDepthSort(
    timeSeconds: number,
    actors: any[] = []
  ): DepthSortResult {
    const records: SceneElementDepthRecord[] = [];
    const occlusionEvents: OcclusionEvent[] = [];
    const activeOccluders: THREE.Object3D[] = [];
    const actorDepths: Record<string, number> = {};

    const camPos = this.camera.position;
    this.camera.updateMatrixWorld();

    // 1. Deep Environment Background Anchor
    const viewDir = new THREE.Vector3();
    this.camera.getWorldDirection(viewDir);
    const bgWorldPos = camPos.clone().add(viewDir.clone().multiplyScalar(50.0));
    records.push({
      id: 'env_background',
      name: 'Bối cảnh Môi trường (Background)',
      type: 'environment_background',
      worldPosition: [Number(bgWorldPos.x.toFixed(2)), Number(bgWorldPos.y.toFixed(2)), Number(bgWorldPos.z.toFixed(2))],
      cameraDistance: 50.0,
      viewZ: 50.0,
    });

    // 2. Evaluate Characters
    const charScreenBounds: Record<string, { x1: number; y1: number; x2: number; y2: number }> = {};
    for (const actor of actors) {
      const charId = actor.actor_id || actor.dna?.characterId || actor.dna?.id || 'actor';
      const pos3D = this.getActorWorldPosition(actor, timeSeconds);
      const camDist = this.getCameraDistance(pos3D);
      const viewZ = this.getViewSpaceZ(pos3D);
      actorDepths[charId] = camDist;

      // Project 3D to Screen Coordinates
      const proj = this.projectToScreen(pos3D);
      const charWidth = 60 * proj.scale;
      const charHeight = 280 * proj.scale;
      const bounds = {
        x1: proj.x - charWidth * 0.5,
        y1: proj.y - charHeight,
        x2: proj.x + charWidth * 0.5,
        y2: proj.y,
      };
      charScreenBounds[charId] = bounds;

      records.push({
        id: charId,
        name: actor.dna?.name || actor.dna?.canonicalName || charId,
        type: 'character',
        worldPosition: [Number(pos3D[0].toFixed(2)), Number(pos3D[1].toFixed(2)), Number(pos3D[2].toFixed(2))],
        cameraDistance: Number(camDist.toFixed(3)),
        viewZ: Number(viewZ.toFixed(3)),
        screenBounds: bounds,
      });

      // Handheld Props parented to character
      const heldProps = actor.dna?.heldProps || actor.dna?.held_props || {};
      for (const hand of ['rightHand', 'leftHand', 'right_hand', 'left_hand']) {
        const propType = heldProps[hand];
        if (propType && propType !== 'none') {
          records.push({
            id: `${charId}_prop_${propType}`,
            name: `Prop ${propType} (${charId})`,
            type: 'handheld_prop',
            worldPosition: [Number(pos3D[0].toFixed(2)), Number((pos3D[1] + 0.8).toFixed(2)), Number(pos3D[2].toFixed(2))],
            cameraDistance: Number(camDist.toFixed(3)),
            viewZ: Number(viewZ.toFixed(3)),
          });
        }
      }
    }

    // 3. Standalone Props / Scene Objects
    if (this.fallingSandalMesh && this.fallingSandalMesh.visible) {
      const sandalPos = new THREE.Vector3();
      this.fallingSandalMesh.getWorldPosition(sandalPos);
      const sandalDist = this.getCameraDistance(sandalPos);
      const sandalViewZ = this.getViewSpaceZ(sandalPos);
      records.push({
        id: 'prop_waraji_sandal',
        name: 'Dép Rơm Waraji Rơi',
        type: 'standalone_prop',
        worldPosition: [Number(sandalPos.x.toFixed(2)), Number(sandalPos.y.toFixed(2)), Number(sandalPos.z.toFixed(2))],
        cameraDistance: Number(sandalDist.toFixed(3)),
        viewZ: Number(sandalViewZ.toFixed(3)),
      });
    }

    // 4. Foreground Environment Objects
    const fgElements = this.getForegroundElements();
    for (const obj of fgElements) {
      const objId = obj.userData?.elementId || obj.name || 'foreground_object';
      const box = new THREE.Box3().setFromObject(obj);
      const objPos = new THREE.Vector3();
      if (!box.isEmpty()) {
        box.getCenter(objPos);
      } else {
        obj.getWorldPosition(objPos);
      }
      const objDist = this.getCameraDistance(objPos);
      const objViewZ = this.getViewSpaceZ(objPos);

      // Estimate object screen bounds by projecting geometry extents
      let objBounds: { x1: number; y1: number; x2: number; y2: number };
      if (!box.isEmpty()) {
        const corners = [
          new THREE.Vector3(box.min.x, box.min.y, box.min.z),
          new THREE.Vector3(box.min.x, box.max.y, box.min.z),
          new THREE.Vector3(box.max.x, box.min.y, box.min.z),
          new THREE.Vector3(box.max.x, box.max.y, box.min.z),
          new THREE.Vector3(box.min.x, box.min.y, box.max.z),
          new THREE.Vector3(box.min.x, box.max.y, box.max.z),
          new THREE.Vector3(box.max.x, box.min.y, box.max.z),
          new THREE.Vector3(box.max.x, box.max.y, box.max.z),
        ];
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const c of corners) {
          const p = this.projectToScreen([c.x, c.y, c.z]);
          minX = Math.min(minX, p.x);
          minY = Math.min(minY, p.y);
          maxX = Math.max(maxX, p.x);
          maxY = Math.max(maxY, p.y);
        }
        objBounds = { x1: minX, y1: minY, x2: maxX, y2: maxY };
      } else {
        const projObj = this.projectToScreen([objPos.x, objPos.y, objPos.z]);
        objBounds = {
          x1: projObj.x - 280 * projObj.scale,
          y1: projObj.y - 140 * projObj.scale,
          x2: projObj.x + 280 * projObj.scale,
          y2: projObj.y + 140 * projObj.scale,
        };
      }

      records.push({
        id: objId,
        name: obj.userData?.canonicalName || objId,
        type: 'foreground_object',
        worldPosition: [Number(objPos.x.toFixed(2)), Number(objPos.y.toFixed(2)), Number(objPos.z.toFixed(2))],
        cameraDistance: Number(objDist.toFixed(3)),
        viewZ: Number(objViewZ.toFixed(3)),
        screenBounds: objBounds,
      });

      // 5. Re-evaluate Occlusion between each character and this foreground object
      for (const actor of actors) {
        const charId = actor.actor_id || actor.dna?.characterId || actor.dna?.id || 'actor';
        const charDist = actorDepths[charId] || 0;
        const depthDelta = charDist - objDist;
        const cBounds = charScreenBounds[charId];

        const overlapScreen = cBounds ? (
          cBounds.x1 < objBounds.x2 &&
          cBounds.x2 > objBounds.x1 &&
          cBounds.y1 < objBounds.y2 &&
          cBounds.y2 > objBounds.y1
        ) : true;

        // Character is occluded if it is BEHIND the foreground object (depthDelta > 0)
        // AND spatially overlapping
        const isOccluded = depthDelta > 0.05 && overlapScreen;

        occlusionEvents.push({
          characterId: charId,
          foregroundObjectId: objId,
          characterDepth: Number(charDist.toFixed(3)),
          objectDepth: Number(objDist.toFixed(3)),
          depthDelta: Number(depthDelta.toFixed(3)),
          overlapScreen,
          isOccluded,
        });

        if (isOccluded && !activeOccluders.includes(obj)) {
          activeOccluders.push(obj);
        }
      }
    }

    // 5. Narrative Story Prop (Hero Landmark)
    if (this.storyPropGroup) {
      const box = new THREE.Box3().setFromObject(this.storyPropGroup);
      const propPos = new THREE.Vector3();
      if (!box.isEmpty()) {
        box.getCenter(propPos);
      } else {
        this.storyPropGroup.getWorldPosition(propPos);
      }
      const propDist = this.getCameraDistance(propPos);
      const propViewZ = this.getViewSpaceZ(propPos);

      records.push({
        id: this.storyPropGroup.userData?.elementId || 'story_prop_hero',
        name: this.storyPropGroup.userData?.canonicalName || 'Story Prop',
        type: 'standalone_prop',
        worldPosition: [Number(propPos.x.toFixed(2)), Number(propPos.y.toFixed(2)), Number(propPos.z.toFixed(2))],
        cameraDistance: Number(propDist.toFixed(3)),
        viewZ: Number(propViewZ.toFixed(3)),
      });
    }

    // 6. Depth-sort all elements by z-distance from camera (descending: furthest to nearest)
    records.sort((a, b) => b.cameraDistance - a.cameraDistance);

    const result: DepthSortResult = {
      depthSortedElements: records,
      occlusionEvents,
      activeOccluders,
      actorDepths,
    };

    this.lastDepthSortResult = result;
    this.lastOcclusionEvents = occlusionEvents;

    return result;
  }

  public setOnlyForegroundVisible(foregroundObjects: THREE.Object3D[]) {
    this.originalVisibilities.clear();
    const fgSet = new Set<THREE.Object3D>();
    for (const fg of foregroundObjects) {
      fgSet.add(fg);
      fg.traverse((child) => fgSet.add(child));
    }

    this.scene.traverse((obj) => {
      if ((obj as any).isLight) return;
      this.originalVisibilities.set(obj, obj.visible);
      obj.visible = fgSet.has(obj);
    });
  }

  public restoreAllVisibility() {
    this.originalVisibilities.forEach((vis, obj) => {
      obj.visible = vis;
    });
    this.originalVisibilities.clear();
  }

  public renderBackground(
    renderer: THREE.WebGLRenderer,
    depthSortResult?: DepthSortResult
  ) {
    const occluders = depthSortResult?.activeOccluders || [];
    for (const obj of occluders) {
      obj.visible = false;
    }
    renderer.render(this.scene, this.camera);
    for (const obj of occluders) {
      obj.visible = true;
    }
  }

  public renderForeground(
    renderer: THREE.WebGLRenderer,
    depthSortResult?: DepthSortResult
  ) {
    const occluders = depthSortResult?.activeOccluders || [];
    if (occluders.length === 0) return;

    this.setOnlyForegroundVisible(occluders);

    const oldBg = this.scene.background;
    this.scene.background = null;
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    renderer.render(this.scene, this.camera);

    this.restoreAllVisibility();
    this.scene.background = oldBg;
  }

  // ============================================================================
  // RENDER INVOCATION
  // ============================================================================
  public render(renderer: THREE.WebGLRenderer) {
    renderer.render(this.scene, this.camera);
  }
}
