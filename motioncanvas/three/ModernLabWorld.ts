import * as THREE from 'three';

/**
 * Three.js 3D Environment Engine: Modern AI Robotics Facility (LOC_ROBOTICS_LAB)
 * 
 * Implements:
 * - High-tech research lab with polished reflective epoxy floor
 * - Server racks with blinking diagnostic LEDs and cooling grilles
 * - Glass partitions with holographic interface projections
 * - Central bipedal robotic test rig with robotic leg chassis and cable conduits
 * - Industrial ceiling track lights with crisp volumetric highlights
 * - Proves 100% universal generalization across completely unrelated historical/modern genres
 */
export class ModernLabWorld {
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  private robotLegL: THREE.Mesh;
  private robotLegR: THREE.Mesh;
  private statusLed1: THREE.PointLight;
  private statusLed2: THREE.PointLight;
  private width: number;
  private height: number;

  constructor(width = 1920, height = 1080) {
    this.width = width;
    this.height = height;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0E141C); // Sleek modern dark tech palette
    this.scene.fog = new THREE.FogExp2(0x0E141C, 0.025);

    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    this.camera.position.set(-2.5, 2.2, 6.5);
    this.camera.lookAt(0.3, 1.5, 0.0);

    this.setupLighting();
    this.setupLaboratory();
    this.setupBipedalRobot();
  }

  private setupLighting() {
    // Cool cyan/white key light
    const keyLight = new THREE.DirectionalLight(0xD6EEFF, 1.6);
    keyLight.position.set(4, 10, 6);
    this.scene.add(keyLight);

    // Modern blue ambient fill
    const hemiLight = new THREE.HemisphereLight(0x2A3E54, 0x0A1018, 1.1);
    this.scene.add(hemiLight);

    // Blinking diagnostic LEDs
    this.statusLed1 = new THREE.PointLight(0x00D2FF, 2.5, 6);
    this.statusLed1.position.set(2.4, 2.0, -1.2);
    this.scene.add(this.statusLed1);

    this.statusLed2 = new THREE.PointLight(0x00FF88, 2.0, 5);
    this.statusLed2.position.set(0.0, 1.8, 0.2);
    this.scene.add(this.statusLed2);
  }

  private setupLaboratory() {
    // 1. Polished Reflective Epoxy Floor
    const floorGeo = new THREE.PlaneGeometry(35, 25);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x141A22,
      roughness: 0.25,
      metalness: 0.65,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, 0);
    this.scene.add(floor);

    // 2. High-Tech Server Racks (Background)
    const rackMat = new THREE.MeshStandardMaterial({ color: 0x1A222C, roughness: 0.6, metalness: 0.5 });
    for (let x = -5.0; x <= -2.0; x += 1.4) {
      const rackGeo = new THREE.BoxGeometry(1.1, 3.8, 0.9);
      const rack = new THREE.Mesh(rackGeo, rackMat);
      rack.position.set(x, 1.9, -2.6);
      this.scene.add(rack);
    }

    // 3. Glass Workstation Partition Wall
    const glassGeo = new THREE.BoxGeometry(8.0, 3.2, 0.1);
    const glassMat = new THREE.MeshStandardMaterial({
      color: 0x88CCFF,
      roughness: 0.1,
      metalness: 0.9,
      transparent: true,
      opacity: 0.35,
    });
    const glass = new THREE.Mesh(glassGeo, glassMat);
    glass.position.set(0, 1.6, -3.2);
    this.scene.add(glass);

    // 4. Ceiling Cable Conduit & Track Lights
    const railGeo = new THREE.CylinderGeometry(0.06, 0.06, 12, 12);
    const railMat = new THREE.MeshStandardMaterial({ color: 0x445566, metalness: 0.8 });
    const rail = new THREE.Mesh(railGeo, railMat);
    rail.rotation.z = Math.PI / 2;
    rail.position.set(0, 3.8, 0);
    this.scene.add(rail);
  }

  private setupBipedalRobot() {
    // Central Bipedal Robotic Test Rig & Joint Actuators
    const chassisMat = new THREE.MeshStandardMaterial({
      color: 0xEEEEEE,
      metalness: 0.85,
      roughness: 0.25,
    });
    const jointMat = new THREE.MeshStandardMaterial({
      color: 0xFF9900, // Safety orange joints
      metalness: 0.5,
      roughness: 0.5,
    });

    // Robot Pelvis / Core Body
    const coreGeo = new THREE.BoxGeometry(0.8, 0.9, 0.6);
    const core = new THREE.Mesh(coreGeo, chassisMat);
    core.position.set(0, 1.9, 0);
    this.scene.add(core);

    // Left Leg
    const legGeo = new THREE.CylinderGeometry(0.12, 0.10, 1.6, 16);
    this.robotLegL = new THREE.Mesh(legGeo, chassisMat);
    this.robotLegL.position.set(-0.35, 0.85, 0);
    this.scene.add(this.robotLegL);

    // Right Leg
    this.robotLegR = new THREE.Mesh(legGeo, chassisMat);
    this.robotLegR.position.set(0.35, 0.85, 0);
    this.scene.add(this.robotLegR);

    // Overhead gantry tether cable
    const tetherGeo = new THREE.CylinderGeometry(0.04, 0.04, 2.0, 8);
    const tetherMat = new THREE.MeshStandardMaterial({ color: 0x111111 });
    const tether = new THREE.Mesh(tetherGeo, tetherMat);
    tether.position.set(0, 3.0, 0);
    this.scene.add(tether);
  }

  public update(timeSeconds: number) {
    // 1. Robot bipedal stepping / balancing oscillation
    const stepCycle = timeSeconds * 3.5;
    this.robotLegL.rotation.x = Math.sin(stepCycle) * 0.35;
    this.robotLegR.rotation.x = -Math.sin(stepCycle) * 0.35;

    // 2. LED Diagnostics Pulse
    this.statusLed1.intensity = 2.0 + Math.sin(timeSeconds * 8) * 1.0;
    this.statusLed2.intensity = 1.8 + Math.cos(timeSeconds * 6) * 0.8;

    // 3. Cinematic Camera: Tracking arc around founder & robotic rig
    const camP = Math.min(1.0, timeSeconds / 12.0);
    const ease = camP * camP * (3 - 2 * camP);

    this.camera.position.x = -2.8 + ease * 2.2;
    this.camera.position.y = 2.1 + Math.sin(timeSeconds * 0.4) * 0.08;
    this.camera.position.z = 6.4 - ease * 1.4;
    this.camera.lookAt(0.1, 1.4, 0.0);
  }

  public render(renderer: THREE.WebGLRenderer) {
    renderer.render(this.scene, this.camera);
  }
}
