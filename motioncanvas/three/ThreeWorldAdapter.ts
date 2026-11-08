import * as THREE from 'three';
import { ThreeJsEnvironment } from '../contract/ProductionScenePackage';

/**
 * ThreeWorldAdapter: Deterministic 3D Architectural Scene Engine for Motion Canvas V4 / V4.1.
 *
 * Renders authentic 3D spatial depth for Munich Odeonsplatz & Feldherrnhalle:
 * - Triple Florentine arches and stone colonnade
 * - Ground plane with rain-slick cobblestone reflectance
 * - Synchronized 3D perspective camera panning, orbit, and shot cuts
 * - Litfaßsäule advertising pillar & royal mobilization notice
 * - World-to-screen projection for 2D stickman & crowd anchoring
 */
export class ThreeWorldAdapter {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer?: THREE.WebGLRenderer;
  private env: ThreeJsEnvironment;
  private canvas?: HTMLCanvasElement;
  private width: number;
  private height: number;

  constructor(env: ThreeJsEnvironment, width = 1920, height = 1080) {
    this.env = env;
    this.width = width;
    this.height = height;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#4A5664'); // Overcast August 1914 sky

    const initialCam = env.camera_initial ?? {
      position: [-3.5, 2.4, 12.0],
      target: [-0.2, 3.2, -4.5],
      fov: 46
    };
    const [cx, cy, cz] = initialCam.position;
    const [tx, ty, tz] = initialCam.target;
    this.camera = new THREE.PerspectiveCamera(initialCam.fov, width / height, 0.1, 100);
    this.camera.position.set(cx, cy, cz);
    this.camera.lookAt(tx, ty, tz);

    this.buildLighting();
    this.buildGroundPlane();
    this.buildFeldherrnhalleLoggia();
    this.buildStreetFurniture();
  }

  private buildLighting() {
    const sunConf = this.env.lighting.sun;
    const sunLight = new THREE.DirectionalLight(sunConf.color, sunConf.intensity);
    sunLight.position.set(...sunConf.position);
    this.scene.add(sunLight);

    const skyLight = new THREE.HemisphereLight(
      this.env.lighting.sky_ambient.color,
      this.env.lighting.ground_bounce.color,
      this.env.lighting.sky_ambient.intensity
    );
    this.scene.add(skyLight);
  }

  private buildGroundPlane() {
    // Wet cobblestone plaza ground
    const groundGeo = new THREE.PlaneGeometry(70, 50, 32, 32);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x22201e,
      roughness: 0.45,
      metalness: 0.15,
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = 0.0;
    this.scene.add(ground);

    // Stone podium steps rising to the Feldherrnhalle
    const step1Geo = new THREE.BoxGeometry(26, 0.5, 4.5);
    const step1Mat = new THREE.MeshStandardMaterial({ color: 0x544c42, roughness: 0.7 });
    const step1 = new THREE.Mesh(step1Geo, step1Mat);
    step1.position.set(0, 0.25, -2.5);
    this.scene.add(step1);

    const step2Geo = new THREE.BoxGeometry(24, 0.5, 3.8);
    const step2Mat = new THREE.MeshStandardMaterial({ color: 0x62594e, roughness: 0.7 });
    const step2 = new THREE.Mesh(step2Geo, step2Mat);
    step2.position.set(0, 0.75, -3.2);
    this.scene.add(step2);
  }

  private buildFeldherrnhalleLoggia() {
    const arch = this.env.architecture;
    const zBase = arch.z_facade ?? -4.5;
    const stoneMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(arch.stone_color),
      roughness: 0.75,
    });
    const innerShadowMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(arch.shadow_stone_color),
      roughness: 0.9,
    });

    // 1. Back Wall of the Loggia (deep interior shadow)
    const backWallGeo = new THREE.BoxGeometry(24, 11, 0.8);
    const backWall = new THREE.Mesh(backWallGeo, innerShadowMat);
    backWall.position.set(0, 5.5, zBase - 5.5);
    this.scene.add(backWall);

    // 2. Ceiling / Vault
    const ceilingGeo = new THREE.BoxGeometry(24, 0.6, 5.5);
    const ceiling = new THREE.Mesh(ceilingGeo, innerShadowMat);
    ceiling.position.set(0, 10.2, zBase - 2.8);
    this.scene.add(ceiling);

    // 3. Neoclassical Classical Columns (Kehlheim Limestone)
    for (const col of arch.columns) {
      const colGeo = new THREE.CylinderGeometry(col.radius * 0.92, col.radius, col.height, 24);
      const colMesh = new THREE.Mesh(colGeo, stoneMat);
      colMesh.position.set(col.x, col.height / 2 + 1.5, zBase + 0.3);
      this.scene.add(colMesh);

      // Column Base
      const baseGeo = new THREE.BoxGeometry(col.radius * 2.4, 0.6, col.radius * 2.4);
      const baseMesh = new THREE.Mesh(baseGeo, stoneMat);
      baseMesh.position.set(col.x, 1.8, zBase + 0.3);
      this.scene.add(baseMesh);

      // Capital
      const capGeo = new THREE.BoxGeometry(col.radius * 2.6, 0.7, col.radius * 2.6);
      const capMesh = new THREE.Mesh(capGeo, stoneMat);
      capMesh.position.set(col.x, col.height + 1.5, zBase + 0.3);
      this.scene.add(capMesh);
    }

    // 4. Florentine Arches above Columns
    for (const a of arch.arches) {
      const archRingGeo = new THREE.TorusGeometry(a.apex_radius, 0.35, 16, 32, Math.PI);
      const archMesh = new THREE.Mesh(archRingGeo, stoneMat);
      archMesh.position.set(a.x, 7.8, zBase + 0.3);
      this.scene.add(archMesh);
    }

    // 5. Neoclassical Entablature & Attic Pediment
    const entablatureGeo = new THREE.BoxGeometry(24, 2.0, 1.4);
    const entablature = new THREE.Mesh(entablatureGeo, stoneMat);
    entablature.position.set(0, 10.4, zBase + 0.3);
    this.scene.add(entablature);

    // 6. Bronze Commander Statues (Count Tilly & Prince Wrede)
    for (const s of arch.statues) {
      const xPos = s.side === 'LEFT' ? -5.8 : 5.8;
      const pedGeo = new THREE.BoxGeometry(1.4, 2.0, 1.4);
      const pedMat = new THREE.MeshStandardMaterial({ color: 0x443c32, roughness: 0.8 });
      const ped = new THREE.Mesh(pedGeo, pedMat);
      ped.position.set(xPos, 2.0, zBase - 3.2);
      this.scene.add(ped);

      const statueGeo = new THREE.CylinderGeometry(0.35, 0.55, 2.4, 16);
      const statueMat = new THREE.MeshStandardMaterial({ color: 0x1a261f, metalness: 0.85, roughness: 0.3 });
      const statue = new THREE.Mesh(statueGeo, statueMat);
      statue.position.set(xPos, 4.2, zBase - 3.2);
      this.scene.add(statue);
    }

    // 7. Bavarian Bronze Lions
    if (arch.lions) {
      for (const l of arch.lions) {
        const lionPedGeo = new THREE.BoxGeometry(1.6, 1.5, 2.0);
        const lionPedMat = new THREE.MeshStandardMaterial({ color: 0x52483d, roughness: 0.7 });
        const lionPed = new THREE.Mesh(lionPedGeo, lionPedMat);
        lionPed.position.set(l.pos[0], l.pos[1], l.pos[2]);
        this.scene.add(lionPed);

        const lionBodyGeo = new THREE.BoxGeometry(1.1, 0.9, 1.6);
        const lionMat = new THREE.MeshStandardMaterial({ color: 0x302820, metalness: 0.6, roughness: 0.5 });
        const lion = new THREE.Mesh(lionBodyGeo, lionMat);
        lion.position.set(l.pos[0], l.pos[1] + 1.2, l.pos[2]);
        this.scene.add(lion);
      }
    }
  }

  private buildStreetFurniture() {
    const furn = this.env.street_furniture;
    if (!furn || !furn.litfass_pillar) return;

    const lp = furn.litfass_pillar;
    const pillarMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(lp.color), roughness: 0.8 });
    const geo = new THREE.CylinderGeometry(lp.radius, lp.radius, lp.height, 24);
    const mesh = new THREE.Mesh(geo, pillarMat);
    mesh.position.set(lp.pos[0], lp.height / 2, lp.pos[2]);
    this.scene.add(mesh);

    // Top cap
    const capGeo = new THREE.ConeGeometry(lp.radius * 1.15, 0.7, 24);
    const capMat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.6 });
    const cap = new THREE.Mesh(capGeo, capMat);
    cap.position.set(lp.pos[0], lp.height + 0.35, lp.pos[2]);
    this.scene.add(cap);

    // Royal Proclamation Placard ("Kriegszustand") attached to pillar
    const placardGeo = new THREE.PlaneGeometry(0.70, 1.05);
    const placardMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(lp.placard_color),
      roughness: 0.9,
    });
    const placard = new THREE.Mesh(placardGeo, placardMat);
    placard.position.set(lp.pos[0] - lp.radius - 0.02, 1.6, lp.pos[2]);
    placard.rotation.y = -Math.PI / 2;
    this.scene.add(placard);
  }

  /**
   * Sets camera to explicit 3D world coordinates.
   */
  public setCamera(pos: [number, number, number], target: [number, number, number], fov = 46) {
    this.camera.position.set(...pos);
    this.camera.lookAt(...target);
    this.camera.fov = fov;
    this.camera.updateProjectionMatrix();
  }

  /**
   * Projects any 3D world coordinate into 2D centered canvas coordinates [canvasX, canvasY]
   * and provides distance-based scale factor for grounded stick characters & props.
   */
  public projectToScreen(worldPos: [number, number, number]): { x: number; y: number; z: number; scale: number } {
    const v = new THREE.Vector3(...worldPos);
    v.project(this.camera);

    const canvasX = v.x * (this.width / 2);
    const canvasY = -v.y * (this.height / 2);

    const camPos = this.camera.position;
    const dist = Math.hypot(worldPos[0] - camPos.x, worldPos[1] - camPos.y, worldPos[2] - camPos.z);
    const focal = 1.0 / Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2);
    const scale = (focal / Math.max(0.1, dist)) * 1.55;

    return { x: canvasX, y: canvasY, z: dist, scale };
  }

  public updateCamera(t: number) {
    const kfs = this.env.camera_keyframes;
    if (!kfs || kfs.length === 0) return;

    if (t <= kfs[0].t) {
      this.camera.position.set(...kfs[0].position);
      this.camera.lookAt(...kfs[0].target);
      return;
    }
    if (t >= kfs[kfs.length - 1].t) {
      const last = kfs[kfs.length - 1];
      this.camera.position.set(...last.position);
      this.camera.lookAt(...last.target);
      return;
    }

    let i = 0;
    while (i < kfs.length - 1 && kfs[i + 1].t < t) i++;
    const k0 = kfs[i];
    const k1 = kfs[i + 1];
    const progress = (t - k0.t) / (k1.t - k0.t);
    const smoothT = progress * progress * (3 - 2 * progress);

    const px = k0.position[0] + (k1.position[0] - k0.position[0]) * smoothT;
    const py = k0.position[1] + (k1.position[1] - k0.position[1]) * smoothT;
    const pz = k0.position[2] + (k1.position[2] - k0.position[2]) * smoothT;

    const tx = k0.target[0] + (k1.target[0] - k0.target[0]) * smoothT;
    const ty = k0.target[1] + (k1.target[1] - k0.target[1]) * smoothT;
    const tz = k0.target[2] + (k1.target[2] - k0.target[2]) * smoothT;

    this.camera.position.set(px, py, pz);
    this.camera.lookAt(tx, ty, tz);
  }

  public render(canvas: HTMLCanvasElement): void {
    if (!this.renderer || this.canvas !== canvas) {
      this.canvas = canvas;
      this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
      this.renderer.setSize(canvas.width, canvas.height, false);
      this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure = 1.08;
    }
    this.renderer.render(this.scene, this.camera);
  }
}
