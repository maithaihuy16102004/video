import * as THREE from 'three';

/**
 * Three.js 3D Environment Engine: Edo Lantern House (LOC_EDO_LANTERN_HOUSE)
 * 
 * Implements:
 * - Traditional Japanese Machiya residence & tea house veranda (engawa)
 * - Cedar wood lattice sliding doors (shoji / koshi)
 * - Traditional clay tile roof eaves (kawara) with rainwater dripping
 * - Glowing paper Chochin lanterns with warm volumetric point light
 * - Polished wet stone pathway & garden gravel
 * - Warm interior candlelight glow contrasting cool exterior rain
 * - Synchronized cinematic camera path for Beat 2 (two-shot intimate framing)
 */
export class EdoHouseWorld {
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  private lanternLight1: THREE.PointLight;
  private lanternLight2: THREE.PointLight;
  private rainParticles: THREE.Points;
  private width: number;
  private height: number;

  constructor(width = 1920, height = 1080) {
    this.width = width;
    this.height = height;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x1C222C); // Night evening drizzle
    this.scene.fog = new THREE.FogExp2(0x1C222C, 0.03);

    this.camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100);
    this.camera.position.set(0.0, 1.8, 6.2);
    this.camera.lookAt(0.0, 1.5, 0.0);

    this.setupLighting();
    this.setupHouseArchitecture();
    this.setupChochinLanterns();
    this.setupRain();
  }

  private setupLighting() {
    // Cool exterior ambient light
    const hemiLight = new THREE.HemisphereLight(0x3B4858, 0x181E24, 0.7);
    this.scene.add(hemiLight);

    // Warm interior candlelight glowing through shoji screens
    const interiorLight = new THREE.PointLight(0xFFA540, 2.2, 10);
    interiorLight.position.set(0.5, 2.4, -2.5);
    this.scene.add(interiorLight);

    // Glowing Red Paper Chochin Lantern Point Lights
    this.lanternLight1 = new THREE.PointLight(0xFF4520, 2.8, 8);
    this.lanternLight1.position.set(-2.2, 2.6, 0.8);
    this.scene.add(this.lanternLight1);

    this.lanternLight2 = new THREE.PointLight(0xFF5525, 2.8, 8);
    this.lanternLight2.position.set(2.2, 2.6, 0.8);
    this.scene.add(this.lanternLight2);
  }

  private setupHouseArchitecture() {
    const darkWood = new THREE.MeshStandardMaterial({ color: 0x2A1E17, roughness: 0.8 });
    const engawaWood = new THREE.MeshStandardMaterial({ color: 0x4D382A, roughness: 0.65 });
    const tileMat = new THREE.MeshStandardMaterial({ color: 0x282A2E, roughness: 0.7 });
    const shojiMat = new THREE.MeshStandardMaterial({
      color: 0xFFF2D8,
      roughness: 0.9,
      emissive: 0x44280E,
      emissiveIntensity: 0.35,
    });

    // 1. Veranda (Engawa) Floor
    const engawaGeo = new THREE.BoxGeometry(10.0, 0.45, 3.2);
    const engawa = new THREE.Mesh(engawaGeo, engawaWood);
    engawa.position.set(0, 0.22, -0.4);
    this.scene.add(engawa);

    // 2. Main Machiya House Wall & Shoji Lattice Screens
    const backWallGeo = new THREE.BoxGeometry(9.6, 3.6, 0.2);
    const backWall = new THREE.Mesh(backWallGeo, shojiMat);
    backWall.position.set(0, 2.2, -1.9);
    this.scene.add(backWall);

    // Lattice frame timber dividers
    for (let x = -4.5; x <= 4.5; x += 1.5) {
      const dividerGeo = new THREE.BoxGeometry(0.14, 3.6, 0.25);
      const div = new THREE.Mesh(dividerGeo, darkWood);
      div.position.set(x, 2.2, -1.88);
      this.scene.add(div);
    }
    for (let y = 0.8; y <= 3.8; y += 0.8) {
      const hDividerGeo = new THREE.BoxGeometry(9.6, 0.12, 0.25);
      const hDiv = new THREE.Mesh(hDividerGeo, darkWood);
      hDiv.position.set(0, y, -1.88);
      this.scene.add(hDiv);
    }

    // 3. Heavy Timber Pillars supporting Eaves
    for (const x of [-4.5, -1.5, 1.5, 4.5]) {
      const pillarGeo = new THREE.BoxGeometry(0.28, 4.0, 0.28);
      const pillar = new THREE.Mesh(pillarGeo, darkWood);
      pillar.position.set(x, 2.0, 1.1);
      this.scene.add(pillar);
    }

    // 4. Overhanging Tile Roof Eaves (Kawara)
    const eaveGeo = new THREE.BoxGeometry(11.4, 0.55, 3.6);
    const eave = new THREE.Mesh(eaveGeo, tileMat);
    eave.position.set(0, 4.1, 0.4);
    eave.rotation.x = 0.18; // Slope downward
    this.scene.add(eave);

    // 5. Stone Pavement & Garden Path
    const stoneGeo = new THREE.PlaneGeometry(24, 16);
    const stoneMat = new THREE.MeshStandardMaterial({ color: 0x1E2228, roughness: 0.5 });
    const ground = new THREE.Mesh(stoneGeo, stoneMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, 0, 4.5);
    this.scene.add(ground);
  }

  private setupChochinLanterns() {
    const lanternMat = new THREE.MeshStandardMaterial({
      color: 0xEE3015,
      roughness: 0.4,
      emissive: 0xDD2810,
      emissiveIntensity: 0.75,
    });
    const capMat = new THREE.MeshStandardMaterial({ color: 0x1A1512, roughness: 0.8 });

    for (const x of [-2.2, 2.2]) {
      // Cylindrical Red Paper Body
      const bodyGeo = new THREE.CylinderGeometry(0.36, 0.36, 0.95, 18);
      const body = new THREE.Mesh(bodyGeo, lanternMat);
      body.position.set(x, 2.6, 0.8);
      this.scene.add(body);

      // Top and bottom black wooden rims
      const rimTopGeo = new THREE.CylinderGeometry(0.40, 0.40, 0.08, 18);
      const rimTop = new THREE.Mesh(rimTopGeo, capMat);
      rimTop.position.set(x, 3.1, 0.8);
      this.scene.add(rimTop);

      const rimBot = new THREE.Mesh(rimTopGeo, capMat);
      rimBot.position.set(x, 2.1, 0.8);
      this.scene.add(rimBot);
    }
  }

  private setupRain() {
    const count = 2500;
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 25;
      positions[i * 3 + 1] = Math.random() * 14;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 20;
    }
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const mat = new THREE.PointsMaterial({
      color: 0xA8C2E0,
      size: 0.10,
      transparent: true,
      opacity: 0.65,
    });
    this.rainParticles = new THREE.Points(geom, mat);
    this.scene.add(this.rainParticles);
  }

  public update(timeSeconds: number) {
    // 1. Rain falling softly
    const pos = this.rainParticles.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < pos.length; i += 3) {
      pos[i + 1] -= 0.45;
      if (pos[i + 1] < 0.0) {
        pos[i + 1] = 14.0;
      }
    }
    this.rainParticles.geometry.attributes.position.needsUpdate = true;

    // 2. Chochin Lantern flicker
    const flicker1 = Math.sin(timeSeconds * 12) * 0.25 + Math.cos(timeSeconds * 7) * 0.15;
    this.lanternLight1.intensity = 2.8 + flicker1;

    const flicker2 = Math.cos(timeSeconds * 10) * 0.25 + Math.sin(timeSeconds * 5) * 0.15;
    this.lanternLight2.intensity = 2.8 + flicker2;

    // 3. Cinematic Camera: Gentle push-in on the veranda where Aiko laughs
    const camP = Math.min(1.0, timeSeconds / 10.0);
    const ease = camP * camP * (3 - 2 * camP);

    this.camera.position.x = -0.3 + ease * 0.6;
    this.camera.position.y = 1.75 + Math.sin(timeSeconds * 0.3) * 0.05;
    this.camera.position.z = 5.8 - ease * 0.9;
    this.camera.lookAt(0.1, 1.45, 0.0);
  }

  public render(renderer: THREE.WebGLRenderer) {
    renderer.render(this.scene, this.camera);
  }
}
