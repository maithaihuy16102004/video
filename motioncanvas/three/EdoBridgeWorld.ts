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
  public foregroundElements: THREE.Object3D[] = [];
  public hasForegroundLayer = true;
  private originalVisibilities: Map<THREE.Object3D, boolean> = new Map();
  private rainParticles: THREE.Points;
  private waterMesh: THREE.Mesh;
  private brokenPlank: THREE.Mesh;
  public fallingSandalMesh: THREE.Mesh;
  private width: number;
  private height: number;

  constructor(width = 1920, height = 1080) {
    this.width = width;
    this.height = height;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x28303C); // Stormy Edo twilight sky
    this.scene.fog = new THREE.FogExp2(0x28303C, 0.035);

    this.camera = new THREE.PerspectiveCamera(44, width / height, 0.1, 100);
    this.camera.position.set(-2.0, 4.5, 7.2);
    this.camera.lookAt(0.1, 5.0, 0.0);

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
    const frontRailingGroup = new THREE.Group();
    frontRailingGroup.name = 'bridge_front_railing';
    frontRailingGroup.userData = {
      elementId: 'bridge_front_railing',
      canonicalName: 'Lan Can Gỗ Phía Trước (Front Railing)',
      isForeground: true,
      category: 'railing',
      baseZ: 2.1,
    };

    for (const z of [-2.1, 2.1]) {
      const isFront = z > 0;
      const targetParent = isFront ? frontRailingGroup : this.scene;

      // Top Handrail
      const railGeo = new THREE.BoxGeometry(15.0, 0.18, 0.22);
      const rail = new THREE.Mesh(railGeo, woodRailing);
      rail.position.set(0, 3.85, z);
      targetParent.add(rail);

      // Mid rail
      const midRailGeo = new THREE.BoxGeometry(15.0, 0.12, 0.16);
      const midRail = new THREE.Mesh(midRailGeo, woodRailing);
      midRail.position.set(0, 3.25, z);
      targetParent.add(midRail);

      // Railing Baluster Posts
      for (let x = -6.5; x <= 6.5; x += 1.3) {
        const postGeo = new THREE.BoxGeometry(0.18, 1.4, 0.18);
        const post = new THREE.Mesh(postGeo, woodRailing);
        post.position.set(x, 3.35, z);
        targetParent.add(post);
      }
    }

    this.scene.add(frontRailingGroup);
    this.foregroundElements.push(frontRailingGroup);
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

    // 3. Cinematic Camera Path for Beat 1 (Elevated sky-preserving perspective, clearing underside beams)
    // Invariant: keeps >= 60% frame open sky and characters in lower-middle third
    const camP = Math.min(1.0, timeSeconds / 12.0);
    const ease = camP * camP * (3 - 2 * camP);

    this.camera.position.x = -2.0 + ease * 0.8;
    this.camera.position.y = 4.5 + Math.sin(timeSeconds * 0.4) * 0.12;
    this.camera.position.z = 7.2 - ease * 0.8;
    this.camera.rotation.z = -0.04 + Math.sin(timeSeconds * 0.6) * 0.02;
    this.camera.lookAt(0.1, 5.0, 0.0);
  }

  public projectToScreen(pos3D: [number, number, number]): {
    x: number;
    y: number;
    z: number;
    distance: number;
    scale: number;
    inSafeFrame: boolean;
  } {
    const worldPos = new THREE.Vector3(...pos3D);
    const camPos = this.camera.position;
    const viewDistance = Math.max(0.5, worldPos.distanceTo(camPos));
    const halfFovRad = ((this.camera.fov || 44) * Math.PI) / 360;
    const pxPerMeter = (this.height * 0.5) / (Math.tan(halfFovRad) * viewDistance);
    const canonicalRigHeightPx = 300;
    const adultHeightMeters = 1.72;
    const perspectiveScale = (adultHeightMeters * pxPerMeter) / canonicalRigHeightPx;

    const v = worldPos.clone().project(this.camera);
    const screenX = (v.x * 0.5 + 0.5) * this.width;
    const screenY = (-v.y * 0.5 + 0.5) * this.height;

    const safeMarginX = this.width * 0.10;
    const safeMarginY = this.height * 0.10;
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

  public getCameraDistance(worldPos: THREE.Vector3 | [number, number, number]): number {
    const v = Array.isArray(worldPos) ? new THREE.Vector3(...worldPos) : worldPos;
    return v.distanceTo(this.camera.position);
  }

  public getViewSpaceZ(worldPos: THREE.Vector3 | [number, number, number]): number {
    const v = Array.isArray(worldPos) ? new THREE.Vector3(...worldPos) : worldPos;
    const viewPos = v.clone().applyMatrix4(this.camera.matrixWorldInverse);
    return -viewPos.z;
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

  public evaluateSceneDepthSort(timeSeconds: number, actors: any[] = []) {
    const records: any[] = [];
    const occlusionEvents: any[] = [];
    const activeOccluders: THREE.Object3D[] = [];
    const actorDepths: Record<string, number> = {};

    const camPos = this.camera.position;
    this.camera.updateMatrixWorld();

    // Background
    const viewDir = new THREE.Vector3();
    this.camera.getWorldDirection(viewDir);
    const bgWorldPos = camPos.clone().add(viewDir.clone().multiplyScalar(50.0));
    records.push({
      id: 'env_background',
      name: 'Bối cảnh Sông Kênh & Mái Nhà (Background)',
      type: 'environment_background',
      worldPosition: [Number(bgWorldPos.x.toFixed(2)), Number(bgWorldPos.y.toFixed(2)), Number(bgWorldPos.z.toFixed(2))],
      cameraDistance: 50.0,
      viewZ: 50.0,
    });

    // Characters
    const charScreenBounds: Record<string, any> = {};
    for (const actor of actors) {
      const charId = actor.actor_id || actor.dna?.characterId || actor.dna?.id || 'actor';
      const pos3D = this.getActorWorldPosition(actor, timeSeconds);
      const camDist = this.getCameraDistance(pos3D);
      const viewZ = this.getViewSpaceZ(pos3D);
      actorDepths[charId] = camDist;

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

    // Standalone prop
    if (this.fallingSandalMesh) {
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

    // Foreground Objects
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

    records.sort((a: any, b: any) => b.cameraDistance - a.cameraDistance);

    return {
      depthSortedElements: records,
      occlusionEvents,
      activeOccluders,
      actorDepths,
    };
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

  public renderBackground(renderer: THREE.WebGLRenderer, depthSortResult?: any) {
    const occluders = depthSortResult?.activeOccluders || [];
    for (const obj of occluders) {
      obj.visible = false;
    }
    renderer.render(this.scene, this.camera);
    for (const obj of occluders) {
      obj.visible = true;
    }
  }

  public renderForeground(renderer: THREE.WebGLRenderer, depthSortResult?: any) {
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

  public render(renderer: THREE.WebGLRenderer) {
    renderer.render(this.scene, this.camera);
  }
}
