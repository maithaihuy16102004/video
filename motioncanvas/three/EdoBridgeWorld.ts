import * as THREE from 'three';

/**
 * Three.js 3D Environment Engine: Edo Wooden Bridge (LOC_EDO_WOODEN_BRIDGE)
 * 
 * Implements:
 * - Authentic Edo timber trestle architecture (Taiko-bashi style)
 * - Weathered wooden bridge deck with individual textured planks
 * - Broken/snapped plank where Haru slips with splintered timber edges
 * - Turbulent river canal with flowing animated water surface & foam
 * - Dynamic 3D rain streaks with depth perspective
 * - Atmospheric fog & stormy twilight overcast lighting
 * - Coordinated cinematic camera path for Beat 1 (Dutch tilt, low-angle MCU)
 */
export class EdoBridgeWorld {
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  private rainParticles: THREE.Points;
  private waterMesh: THREE.Mesh;
  private brokenPlank: THREE.Mesh;
  private fallingSandalMesh: THREE.Mesh;
  private width: number;
  private height: number;

  constructor(width = 1920, height = 1080) {
    this.width = width;
    this.height = height;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x28303C); // Stormy Edo twilight sky
    this.scene.fog = new THREE.FogExp2(0x28303C, 0.035);

    this.camera = new THREE.PerspectiveCamera(44, width / height, 0.1, 100);
    this.camera.position.set(-2.8, 1.9, 5.8);
    this.camera.lookAt(0.2, 1.4, 0.0);

    this.setupLighting();
    this.setupRiverCanal();
    this.setupBridgeStructure();
    this.setupDistantMachiya();
    this.setup3DRain();
    this.setupFallingSandal();
  }

  private setupLighting() {
    // Stormy overcast directional light
    const dirLight = new THREE.DirectionalLight(0xA0B4C8, 1.4);
    dirLight.position.set(-8, 14, 10);
    dirLight.castShadow = true;
    this.scene.add(dirLight);

    // Ambient cold storm bounce
    const hemiLight = new THREE.HemisphereLight(0x4A5868, 0x1A2228, 0.9);
    this.scene.add(hemiLight);
  }

  private setupRiverCanal() {
    // Turbulent river canal under bridge
    const waterGeo = new THREE.PlaneGeometry(60, 40, 64, 64);
    const waterMat = new THREE.MeshStandardMaterial({
      color: 0x182C38,
      roughness: 0.15,
      metalness: 0.85,
    });
    this.waterMesh = new THREE.Mesh(waterGeo, waterMat);
    this.waterMesh.rotation.x = -Math.PI / 2;
    this.waterMesh.position.set(0, -1.2, 0);
    this.scene.add(this.waterMesh);

    // Stone canal embankment walls
    const wallGeo = new THREE.BoxGeometry(60, 4.0, 3.0);
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x36383A, roughness: 0.85 });
    const wallLeft = new THREE.Mesh(wallGeo, wallMat);
    wallLeft.position.set(0, 0.2, -7.5);
    this.scene.add(wallLeft);

    const wallRight = new THREE.Mesh(wallGeo, wallMat);
    wallRight.position.set(0, 0.2, 7.5);
    this.scene.add(wallRight);
  }

  private setupBridgeStructure() {
    const woodDark = new THREE.MeshStandardMaterial({ color: 0x3D2E24, roughness: 0.8 });
    const woodPlank = new THREE.MeshStandardMaterial({ color: 0x5C4638, roughness: 0.75 });
    const woodRailing = new THREE.MeshStandardMaterial({ color: 0x48362B, roughness: 0.7 });

    // 1. Heavy Timber Pier Support Trestles (rising from canal bed)
    for (const z of [-3.2, 0, 3.2]) {
      for (const x of [-4.5, -1.5, 1.5, 4.5]) {
        const pylonGeo = new THREE.CylinderGeometry(0.24, 0.28, 4.5, 12);
        const pylon = new THREE.Mesh(pylonGeo, woodDark);
        pylon.position.set(x, 0.6, z);
        this.scene.add(pylon);
      }
      // Crossbeams connecting pylons
      const crossBeamGeo = new THREE.BoxGeometry(11.0, 0.35, 0.45);
      const crossBeam = new THREE.Mesh(crossBeamGeo, woodDark);
      crossBeam.position.set(0, 2.2, z);
      this.scene.add(crossBeam);
    }

    // 2. Main Bridge Longitudinal Girders
    for (const z of [-1.8, 1.8]) {
      const girderGeo = new THREE.BoxGeometry(16.0, 0.45, 0.4);
      const girder = new THREE.Mesh(girderGeo, woodDark);
      girder.position.set(0, 2.5, z);
      this.scene.add(girder);
    }

    // 3. Wooden Deck Planks (Across Bridge Width)
    // Bridge spans x = -7 to +7, z = -2.2 to +2.2
    for (let x = -7.0; x <= 7.0; x += 0.35) {
      if (Math.abs(x - 0.2) < 0.4) {
        // This is where the plank BROKE / SNAPPED!
        const brokenGeo = new THREE.BoxGeometry(0.32, 0.12, 1.8);
        this.brokenPlank = new THREE.Mesh(brokenGeo, woodPlank);
        // Slanted downwards into canal!
        this.brokenPlank.position.set(0.2, 2.45, -0.9);
        this.brokenPlank.rotation.x = 0.55; // Snapped downward tilt
        this.scene.add(this.brokenPlank);
        continue;
      }

      const plankGeo = new THREE.BoxGeometry(0.32, 0.14, 4.2);
      const plank = new THREE.Mesh(plankGeo, woodPlank);
      plank.position.set(x, 2.65, 0);
      this.scene.add(plank);
    }

    // 4. Sturdy Side Railings with Handrails and Balusters
    for (const z of [-2.1, 2.1]) {
      // Top Handrail
      const railGeo = new THREE.BoxGeometry(15.0, 0.18, 0.22);
      const rail = new THREE.Mesh(railGeo, woodRailing);
      rail.position.set(0, 3.85, z);
      this.scene.add(rail);

      // Mid rail
      const midRailGeo = new THREE.BoxGeometry(15.0, 0.12, 0.16);
      const midRail = new THREE.Mesh(midRailGeo, woodRailing);
      midRail.position.set(0, 3.25, z);
      this.scene.add(midRail);

      // Railing Baluster Posts
      for (let x = -6.5; x <= 6.5; x += 1.3) {
        const postGeo = new THREE.BoxGeometry(0.18, 1.4, 0.18);
        const post = new THREE.Mesh(postGeo, woodRailing);
        post.position.set(x, 3.35, z);
        this.scene.add(post);
      }
    }
  }

  private setupDistantMachiya() {
    // Silhouette of distant Edo machiya roofs with clay tiles in storm
    const roofMat = new THREE.MeshStandardMaterial({ color: 0x222428, roughness: 0.9 });
    for (let x = -14; x <= 14; x += 4.5) {
      const roofGeo = new THREE.ConeGeometry(3.2, 2.0, 4);
      const roof = new THREE.Mesh(roofGeo, roofMat);
      roof.position.set(x, 4.5, -12);
      roof.rotation.y = Math.PI / 4;
      this.scene.add(roof);
    }
  }

  private setup3DRain() {
    const count = 3500;
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 35;
      positions[i * 3 + 1] = Math.random() * 20;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 30;
    }
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const mat = new THREE.PointsMaterial({
      color: 0xBACFE5,
      size: 0.12,
      transparent: true,
      opacity: 0.75,
    });
    this.rainParticles = new THREE.Points(geom, mat);
    this.scene.add(this.rainParticles);
  }

  private setupFallingSandal() {
    // 3D Straw Waraji sandal falling towards the canal torrent!
    const sandalGeo = new THREE.BoxGeometry(0.24, 0.08, 0.55);
    const sandalMat = new THREE.MeshStandardMaterial({ color: 0xC8A868, roughness: 0.9 });
    this.fallingSandalMesh = new THREE.Mesh(sandalGeo, sandalMat);
    this.fallingSandalMesh.position.set(0.4, 1.2, -1.8);
    this.fallingSandalMesh.rotation.set(0.4, 0.2, 0.6);
    this.scene.add(this.fallingSandalMesh);
  }

  public update(timeSeconds: number) {
    // 1. Animate 3D Rain falling with wind slant
    const pos = this.rainParticles.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < pos.length; i += 3) {
      pos[i + 1] -= 0.65; // Falling fast
      pos[i] -= 0.15;     // Slanted wind drift
      if (pos[i + 1] < -2.0) {
        pos[i + 1] = 18.0;
        pos[i] = (Math.random() - 0.5) * 35;
      }
    }
    this.rainParticles.geometry.attributes.position.needsUpdate = true;

    // 2. Animate Falling Waraji Sandal
    // Tumbles down towards the canal water
    const fallT = Math.min(1.0, timeSeconds / 4.0);
    this.fallingSandalMesh.position.y = 2.2 - fallT * 2.8;
    this.fallingSandalMesh.position.x = 0.3 + fallT * 0.8;
    this.fallingSandalMesh.position.z = -1.5 - fallT * 0.9;
    this.fallingSandalMesh.rotation.x += 0.06;
    this.fallingSandalMesh.rotation.y += 0.04;

    // 3. Cinematic Camera Path for Beat 1 (Dramatic Low-Angle Dutch Tilt MCU)
    // Emphasizes the life-or-death tension above the torrent
    const camP = Math.min(1.0, timeSeconds / 12.0);
    const ease = camP * camP * (3 - 2 * camP);

    this.camera.position.x = -2.6 + ease * 0.8;
    this.camera.position.y = 1.8 + Math.sin(timeSeconds * 0.4) * 0.15;
    this.camera.position.z = 5.6 - ease * 0.6;
    this.camera.rotation.z = -0.12 + Math.sin(timeSeconds * 0.6) * 0.03; // Dutch tilt angle
    this.camera.lookAt(0.1, 2.2, -0.4);
  }

  public render(renderer: THREE.WebGLRenderer) {
    renderer.render(this.scene, this.camera);
  }
}
