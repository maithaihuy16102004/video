/**
 * World25D — generic data-driven Three.js 2.5D world for AI Clip Studio.
 *
 * Pattern follows the upstream code (read-only reference):
 * - `ThreeWorldAdapter.ts`: PerspectiveCamera + DirectionalLight +
 *   HemisphereLight + ground plane with MeshStandardMaterial +
 *   `projectToScreen()` for anchoring 2D characters in 3D space.
 * - `UniversalWorldEngine.ts` (V4.2.3): the world is 100% DATA-DRIVEN
 *   by a location DNA / scene package — no hardcoded Munich, Edo or
 *   lab. This class takes the same idea but with a minimal generic
 *   spec (`World25DSpec`) so ANY scene package can drive it.
 *
 * What this builds, from the spec only:
 * - a real 3D space: ground plane, solid boxes (buildings / furniture /
 *   props) with light-reactive MeshStandardMaterial;
 * - real light sources: key DirectionalLight WITH shadow map, cool
 *   HemisphereLight fill, plus any number of PointLights;
 * - real FG / MG / BG distance: objects sit at different z, the
 *   perspective camera gives parallax for free when it moves;
 * - camera keyframes (position / target / fov) interpolated over time,
 *   exactly like the Motion Canvas timeline drives `updateCamera(t)`;
 * - `projectToScreen()` so 2D stickman characters (drawn by the
 *   Motion Canvas 2D layer) stand at the right place and scale in the
 *   3D world.
 *
 * NOT copied from upstream: no Munich loggia, no Edo bridge, no lab —
 * the geometry here is only boxes + ground + lights from the spec.
 * Nothing in this file names a story, a character or a location.
 */
import * as THREE from 'three';

export interface BoxSpec {
  name: string;
  center: [number, number, number];
  size: [number, number, number];
  color: string;
  roughness?: number;
  metalness?: number;
}

export interface PointLightSpec {
  position: [number, number, number];
  color: string;
  intensity: number;
  distance?: number;
}

export interface CameraKeyframe {
  t: number; // seconds, timeline time
  position: [number, number, number];
  target: [number, number, number];
  fov?: number;
}

export interface CharacterAnchorSpec {
  id: string;
  feet: [number, number, number]; // world position of the feet (y = ground)
  height: number; // world height, for scale
}

export interface World25DSpec {
  sky_top: string;
  sky_bottom: string;
  ground_color: string;
  ground_size: number; // half-extent of the ground plane
  ground_roughness?: number;
  boxes: BoxSpec[];
  key_light: {
    color: string;
    intensity: number;
    position: [number, number, number]; // where the light sits
    target?: [number, number, number];
  };
  ambient_sky: string;
  ambient_ground: string;
  ambient_intensity: number;
  point_lights?: PointLightSpec[];
  camera_initial: { position: [number, number, number]; target: [number, number, number]; fov: number };
  camera_keyframes?: CameraKeyframe[];
  character_anchors?: CharacterAnchorSpec[];
}

export class World25D {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer?: THREE.WebGLRenderer;
  private spec: World25DSpec;
  private width: number;
  private height: number;

  constructor(spec: World25DSpec, width = 1920, height = 1080) {
    this.spec = spec;
    this.width = width;
    this.height = height;
    this.scene = new THREE.Scene();
    // Sky: gradient background colour (top colour; the ground plane
    // and fog give the horizon). A full gradient sky dome is a later
    // art pass, not a geometry requirement.
    this.scene.background = new THREE.Color(spec.sky_top);
    this.scene.fog = new THREE.Fog(new THREE.Color(spec.sky_bottom), 30, 80);

    const init = spec.camera_initial;
    this.camera = new THREE.PerspectiveCamera(
      init.fov, width / height, 0.1, 200,
    );
    this.camera.position.set(...init.position);
    this.camera.lookAt(new THREE.Vector3(...init.target));

    this.buildLights();
    this.buildGround();
    this.buildBoxes();
  }

  // -- lights: real sources, not painted glows -------------------------
  private buildLights() {
    const key = this.spec.key_light;
    const sun = new THREE.DirectionalLight(
      new THREE.Color(key.color), key.intensity,
    );
    sun.position.set(...key.position);
    sun.target.position.set(...(key.target ?? [0, 0, 0]));
    // Real shadow map: this is what the PIL fallback cannot do.
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -20;
    sun.shadow.camera.right = 20;
    sun.shadow.camera.top = 20;
    sun.shadow.camera.bottom = -20;
    sun.shadow.camera.far = 80;
    sun.shadow.bias = -0.0005;
    this.scene.add(sun);
    this.scene.add(sun.target);

    const hemi = new THREE.HemisphereLight(
      new THREE.Color(this.spec.ambient_sky),
      new THREE.Color(this.spec.ambient_ground),
      this.spec.ambient_intensity,
    );
    this.scene.add(hemi);

    for (const p of this.spec.point_lights ?? []) {
      const light = new THREE.PointLight(
        new THREE.Color(p.color), p.intensity,
        p.distance ?? 0, 1.6, // decay ~ physical-ish falloff
      );
      light.position.set(...p.position);
      this.scene.add(light);
    }
  }

  // -- geometry: ground + solid boxes, light-reactive materials -------
  private buildGround() {
    const geo = new THREE.PlaneGeometry(
      this.spec.ground_size * 2, this.spec.ground_size * 2,
    );
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(this.spec.ground_color),
      roughness: this.spec.ground_roughness ?? 0.85,
      metalness: 0.0,
    });
    const ground = new THREE.Mesh(geo, mat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true; // contact + cast shadows land here
    this.scene.add(ground);
  }

  private buildBoxes() {
    for (const b of this.spec.boxes) {
      const geo = new THREE.BoxGeometry(...b.size);
      const mat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(b.color),
        roughness: b.roughness ?? 0.8,
        metalness: b.metalness ?? 0.0,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(...b.center);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.name = b.name;
      this.scene.add(mesh);
    }
  }

  // -- camera timeline --------------------------------------------------
  updateCamera(t: number) {
    const keys = this.spec.camera_keyframes ?? [];
    if (keys.length === 0) return;
    const sorted = [...keys].sort((a, b) => a.t - b.t);
    if (t <= sorted[0].t) {
      this.applyKeyframe(sorted[0]);
      return;
    }
    if (t >= sorted[sorted.length - 1].t) {
      this.applyKeyframe(sorted[sorted.length - 1]);
      return;
    }
    for (let i = 0; i < sorted.length - 1; i++) {
      const a = sorted[i];
      const b = sorted[i + 1];
      if (t >= a.t && t <= b.t) {
        // smoothstep easing, not linear: the camera must ease in/out
        const raw = (t - a.t) / Math.max(b.t - a.t, 1e-6);
        const k = raw * raw * (3 - 2 * raw);
        const lerp = (u: number, v: number) => u + (v - u) * k;
        this.camera.position.set(
          lerp(a.position[0], b.position[0]),
          lerp(a.position[1], b.position[1]),
          lerp(a.position[2], b.position[2]),
        );
        const tx = lerp(a.target[0], b.target[0]);
        const ty = lerp(a.target[1], b.target[1]);
        const tz = lerp(a.target[2], b.target[2]);
        this.camera.lookAt(new THREE.Vector3(tx, ty, tz));
        if (a.fov !== undefined && b.fov !== undefined) {
          this.camera.fov = lerp(a.fov, b.fov);
          this.camera.updateProjectionMatrix();
        }
        return;
      }
    }
  }

  private applyKeyframe(k: CameraKeyframe) {
    this.camera.position.set(...k.position);
    this.camera.lookAt(new THREE.Vector3(...k.target));
    if (k.fov !== undefined) {
      this.camera.fov = k.fov;
      this.camera.updateProjectionMatrix();
    }
  }

  // -- 2D character anchoring (same contract as upstream projectToScreen)
  projectToScreen(world: [number, number, number]): {
    x: number; y: number; scale: number; visible: boolean;
  } {
    const v = new THREE.Vector3(...world).project(this.camera);
    const visible = v.z < 1; // behind the camera -> z >= 1
    const x = ((v.x + 1) / 2) * this.width;
    const y = ((1 - v.y) / 2) * this.height;
    // scale: pixels per world unit at this depth, from the projection
    const depth = this.camera.position.distanceTo(new THREE.Vector3(...world));
    const focalPx = this.height / 2 / Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    return { x, y, scale: focalPx / Math.max(depth, 0.1), visible };
  }

  characterScreenBoxes(): Record<string, { feetX: number; feetY: number; headY: number; heightPx: number; visible: boolean }> {
    const out: Record<string, { feetX: number; feetY: number; headY: number; heightPx: number; visible: boolean }> = {};
    for (const a of this.spec.character_anchors ?? []) {
      const feet = this.projectToScreen(a.feet);
      const head = this.projectToScreen([a.feet[0], a.feet[1] + a.height, a.feet[2]]);
      out[a.id] = {
        feetX: feet.x, feetY: feet.y, headY: head.y,
        heightPx: Math.max(0, feet.y - head.y),
        visible: feet.visible && head.visible,
      };
    }
    return out;
  }

  // -- rendering ---------------------------------------------------------
  render(canvas: HTMLCanvasElement) {
    if (!this.renderer) {
      this.renderer = new THREE.WebGLRenderer({
        canvas, antialias: true, preserveDrawingBuffer: true,
      });
      this.renderer.setSize(this.width, this.height, false);
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure = 1.1;
    }
    this.renderer.render(this.scene, this.camera);
  }
}
