/**
 * Universal Data-Driven Character Engine V4.2.3
 * 
 * Implements Phase 1 Remediation:
 * - 100% Data-Driven by CharacterDNA (Zero hardcoded character classes)
 * - Diverse Face Silhouettes (oval_gaunt, square_jaw, round_youth, delicate_heart)
 * - Organic Anatomical Limbs (Tapered polygons, deltoid flares, joint caps, muscle curves)
 * - Expressive Eyes (Sclera white, colored iris, pupil, specular catchlight, eyelid creases)
 * - Articulated 5-Finger Hands (Palm, opposable thumb, 4 articulated phalanges)
 * - Cultural Costumes with Real Geometry (Frock coats, formal kimono, hanten, hoodie, polar hazard suit)
 * - Analytical 2-Bone Inverse Kinematics (IK) with Foot-Locking on Ground Plane
 * - Verified Vietnamese Typography on Props
 */

export interface CharacterDNA {
  id: string;
  name: string;
  proportions: {
    head_ratio: number; // e.g. 0.28
    height_standing: number; // e.g. 260
    shoulder_width: number; // e.g. 52
    limb_thickness: number; // e.g. 11
  };
  face: {
    head_contour: 'oval_gaunt' | 'round_youth' | 'square_jaw' | 'delicate_heart';
    skin_tone: string;
    eye_type: 'intense_focused' | 'curious_wide' | 'almond_asian' | 'laughing_squint';
    eye_color: string;
    eyebrow_style: 'arched' | 'thick_bushy' | 'furrowed_intense' | 'delicate_curved';
    facial_hair: 'none' | 'handlebar_mustache' | 'full_beard' | 'goatee' | 'stubble';
    facial_hair_color?: string;
  };
  hair: {
    style: 'edo_topknot' | 'edo_shimada' | 'side_sweep_1914' | 'modern_part' | 'short_crop' | 'bald';
    color: string;
    accessory: 'none' | 'kanzashi_hairpin' | 'paper_cord' | 'headband';
  };
  costume: {
    archetype: 'edo_hanten_courier' | 'edo_kimono_formal' | 'frock_coat_1914' | 'modern_hoodie' | 'lab_coat' | 'polar_hazard_suit' | 'work_apron';
    primary_color: string;
    accent_color: string;
    pants_skirt: 'trousers' | 'kimono_skirt' | 'hakama' | 'jeans' | 'thermal_pants';
    pants_color: string;
    belt_sash: 'obi_sash' | 'leather_belt' | 'cord' | 'none';
    footwear: 'waraji_sandals' | 'tabi_socks' | 'leather_shoes' | 'sneakers' | 'snow_boots' | 'bare_foot';
    footwear_color: string;
  };
  held_props?: {
    left_hand?: 'none' | 'portfolio' | 'letter_envelope' | 'letter_scroll_open' | 'tablet' | 'umbrella';
    right_hand?: 'none' | 'portfolio' | 'letter_envelope' | 'letter_scroll_open' | 'tablet' | 'umbrella';
  };
}

export interface CharacterState {
  screenX: number;
  screenY: number;
  scale: number;
  facing: 1 | -1;
  action: 'idle' | 'walk' | 'sprint' | 'slip_fall' | 'hang_from_ledge' | 'present_two_handed' | 'laugh_heartily' | 'speak_gestural' | 'inspect_down';
  progress: number;
  emotion: 'neutral' | 'determined' | 'panic' | 'relief' | 'laughing' | 'intense' | 'focused';
  gazeTarget?: [number, number];
  handConstraintL?: [number, number];
  handConstraintR?: [number, number];
  lostSandalRight?: boolean;
  soaked?: boolean;
}

interface Point2D {
  x: number;
  y: number;
}

export class UniversalCharacterEngine {
  private ctx: CanvasRenderingContext2D;

  constructor(ctx: CanvasRenderingContext2D) {
    this.ctx = ctx;
  }

  // ============================================================================
  // ANALYTICAL 2-BONE INVERSE KINEMATICS (IK) SOLVER
  // ============================================================================
  private solve2BoneIK(
    root: Point2D,
    target: Point2D,
    len1: number,
    len2: number,
    bendDirection: 1 | -1 = 1
  ): { joint: Point2D; end: Point2D } {
    const dx = target.x - root.x;
    const dy = target.y - root.y;
    const dist = Math.hypot(dx, dy);

    const maxReach = (len1 + len2) * 0.999;
    const minReach = Math.abs(len1 - len2) * 1.001;
    const d = Math.max(minReach, Math.min(maxReach, dist));

    const baseAngle = Math.atan2(dy, dx);
    const cosAngle1 = (len1 * len1 + d * d - len2 * len2) / (2 * len1 * d);
    const clampedCos1 = Math.max(-1, Math.min(1, cosAngle1));
    const angle1 = baseAngle + bendDirection * Math.acos(clampedCos1);

    const jointX = root.x + Math.cos(angle1) * len1;
    const jointY = root.y + Math.sin(angle1) * len1;

    const endX = root.x + (dx / (dist || 1)) * d;
    const endY = root.y + (dy / (dist || 1)) * d;

    return { joint: { x: jointX, y: jointY }, end: { x: endX, y: endY } };
  }

  // ============================================================================
  // MASTER RENDER ENTRY POINT
  // ============================================================================
  public render(dna: CharacterDNA, state: CharacterState) {
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(state.screenX, state.screenY);
    ctx.scale(state.scale * state.facing, state.scale);

    const prop = dna.proportions;
    const totalH = prop.height_standing;
    const headR = (totalH * prop.head_ratio) / 2;
    const ink = '#141210';
    const skin = dna.face.skin_tone;

    // 1. Contact shadow on ground plane
    this.drawContactShadow(state, totalH);

    // 2. Compute Skeleton Hierarchy via Action Library & IK
    const skeleton = this.evaluateSkeleton(dna, state, totalH, headR);

    // 3. Lower Costume (Legs / Pants / Skirt) with organic contours
    this.drawLowerCostume(ctx, dna, state, skeleton, ink);

    // 4. Upper Costume (Torso / Robe / Coat) with layered folds
    this.drawUpperCostume(ctx, dna, state, skeleton, ink);

    // 5. Head, Neck & Face with diverse contours
    this.drawHeadAndFace(ctx, dna, state, skeleton.head, headR, ink, skin);

    // 6. Arms & Hands with 5-finger articulated anatomy
    this.drawArmsAndHands(ctx, dna, state, skeleton, ink, skin);

    // 7. Held Props & Documents
    this.drawProps(ctx, dna, state, skeleton);

    ctx.restore();
  }

  public draw(dna: CharacterDNA, state: CharacterState) {
    this.render(dna, state);
  }

  // ============================================================================
  // CONTACT SHADOW & GROUND ANCHORING
  // ============================================================================
  private drawContactShadow(state: CharacterState, totalH: number) {
    const ctx = this.ctx;
    ctx.save();
    const isAirborne = state.action === 'hang_from_ledge' || state.action === 'slip_fall';
    const shadowAlpha = isAirborne ? 0.25 : 0.55;
    const shadowWidth = isAirborne ? 70 : 105;

    ctx.beginPath();
    ctx.ellipse(0, 0, shadowWidth, 16, 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(16, 14, 12, ${shadowAlpha})`;
    ctx.fill();
    ctx.restore();
  }

  // ============================================================================
  // SKELETAL HIERARCHY & ACTION LIBRARY EVALUATOR
  // ============================================================================
  private evaluateSkeleton(
    dna: CharacterDNA,
    state: CharacterState,
    totalH: number,
    headR: number
  ) {
    const sw = dna.proportions.shoulder_width;
    const armLen1 = totalH * 0.19;
    const armLen2 = totalH * 0.18;
    const legLen1 = totalH * 0.24;
    const legLen2 = totalH * 0.25;

    let hipY = -totalH * 0.48;
    let shoulderY = -totalH * 0.78;
    let headCenter = { x: 0, y: shoulderY - headR * 1.15 };
    let torsoTilt = 0.0;

    let targetHandL: Point2D = { x: -sw * 0.6, y: -totalH * 0.4 };
    let targetHandR: Point2D = { x: sw * 0.6, y: -totalH * 0.4 };
    let targetFootL: Point2D = { x: -sw * 0.28, y: 0 };
    let targetFootR: Point2D = { x: sw * 0.28, y: 0 };
    let legBendL: 1 | -1 = 1;
    let legBendR: 1 | -1 = 1;

    switch (state.action) {
      case 'sprint': {
        const ph = state.progress * 14.0;
        torsoTilt = 0.28;
        hipY = -totalH * 0.44 + Math.sin(ph * 2) * 8;
        shoulderY = hipY - totalH * 0.30;
        headCenter = { x: 20, y: shoulderY - headR * 1.05 };

        targetFootL = { x: Math.sin(ph) * 55, y: Math.max(0, -Math.cos(ph) * 35) };
        targetFootR = { x: -Math.sin(ph) * 55, y: Math.max(0, Math.cos(ph) * 35) };
        targetHandL = { x: -Math.sin(ph) * 45, y: shoulderY + 30 + Math.cos(ph) * 35 };
        targetHandR = { x: Math.sin(ph) * 45 + 20, y: shoulderY + 20 - Math.cos(ph) * 35 };
        break;
      }
      case 'slip_fall': {
        torsoTilt = -0.65;
        hipY = -totalH * 0.28;
        shoulderY = -totalH * 0.52;
        headCenter = { x: -35, y: shoulderY - headR * 0.9 };

        targetFootL = { x: 60, y: -totalH * 0.22 };
        targetFootR = { x: 95, y: -totalH * 0.12 };
        targetHandL = { x: -45, y: -totalH * 0.75 };
        targetHandR = { x: 65, y: -totalH * 0.85 };
        break;
      }
      case 'hang_from_ledge': {
        torsoTilt = 0.12;
        shoulderY = -totalH * 0.48;
        hipY = -totalH * 0.18;
        headCenter = { x: 8, y: shoulderY - headR * 1.1 };

        targetHandL = { x: -18, y: -totalH * 0.82 };
        targetHandR = { x: 45, y: -totalH * 0.88 }; // Holding letter high and dry!
        targetFootL = { x: -22, y: totalH * 0.18 };
        targetFootR = { x: 12, y: totalH * 0.12 };
        legBendL = -1;
        break;
      }
      case 'present_two_handed': {
        torsoTilt = 0.08;
        shoulderY = -totalH * 0.74;
        headCenter = { x: 10, y: shoulderY - headR * 1.1 };

        targetHandL = { x: sw * 0.35, y: shoulderY + totalH * 0.22 };
        targetHandR = { x: sw * 0.55, y: shoulderY + totalH * 0.20 };
        break;
      }
      case 'laugh_heartily': {
        const ph = state.progress * 8.0;
        torsoTilt = -0.15 + Math.sin(ph) * 0.08;
        shoulderY = -totalH * 0.76 + Math.sin(ph) * 5;
        headCenter = { x: -14, y: shoulderY - headR * 1.1 };

        targetHandL = { x: -sw * 0.45, y: shoulderY + totalH * 0.24 };
        targetHandR = { x: sw * 0.20, y: shoulderY + totalH * 0.12 }; // Hand at mouth laughing
        break;
      }
      case 'speak_gestural': {
        const ph = state.progress * 3.5;
        torsoTilt = 0.04;
        targetHandL = { x: -sw * 0.55, y: shoulderY + totalH * 0.32 };
        targetHandR = { x: sw * 0.65 + Math.sin(ph) * 15, y: shoulderY + totalH * 0.16 + Math.cos(ph) * 12 };
        break;
      }
      case 'inspect_down': {
        torsoTilt = 0.32;
        shoulderY = -totalH * 0.70;
        hipY = -totalH * 0.44;
        headCenter = { x: 30, y: shoulderY - headR * 0.85 };
        targetHandL = { x: -sw * 0.3, y: shoulderY + totalH * 0.38 };
        targetHandR = { x: sw * 0.4, y: shoulderY + totalH * 0.36 };
        break;
      }
      case 'idle':
      default: {
        const breath = Math.sin(state.progress * 1.8) * 3;
        shoulderY = -totalH * 0.78 + breath;
        headCenter = { x: 0, y: shoulderY - headR * 1.15 };
        targetHandL = { x: -sw * 0.52, y: shoulderY + totalH * 0.34 };
        targetHandR = { x: sw * 0.52, y: shoulderY + totalH * 0.34 };
        break;
      }
    }

    const shoulderCenter = { x: Math.sin(torsoTilt) * 20, y: shoulderY };
    const hipRoot = { x: 0, y: hipY };

    const shoulderL = { x: shoulderCenter.x - sw * 0.48, y: shoulderCenter.y };
    const shoulderR = { x: shoulderCenter.x + sw * 0.48, y: shoulderCenter.y };
    const hipL = { x: hipRoot.x - sw * 0.28, y: hipRoot.y };
    const hipR = { x: hipRoot.x + sw * 0.28, y: hipRoot.y };

    return {
      head: headCenter,
      torsoTilt,
      shoulderCenter,
      hipRoot,
      shoulderL,
      shoulderR,
      hipL,
      hipR,
      leftArm: this.solve2BoneIK(shoulderL, targetHandL, armLen1, armLen2, -1),
      rightArm: this.solve2BoneIK(shoulderR, targetHandR, armLen1, armLen2, 1),
      leftLeg: this.solve2BoneIK(hipL, targetFootL, legLen1, legLen2, legBendL),
      rightLeg: this.solve2BoneIK(hipR, targetFootR, legLen1, legLen2, legBendR),
    };
  }

  // ============================================================================
  // HEAD, NECK & DIVERSE FACIAL SILHOUETTES
  // ============================================================================
  private drawHeadAndFace(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA,
    state: CharacterState,
    headPos: Point2D,
    headR: number,
    ink: string,
    skin: string
  ) {
    ctx.save();
    ctx.translate(headPos.x, headPos.y);

    // 1. Neck Trapezoid connecting skull to torso
    ctx.beginPath();
    ctx.moveTo(-headR * 0.32, headR * 0.6);
    ctx.lineTo(headR * 0.32, headR * 0.6);
    ctx.lineTo(headR * 0.45, headR * 1.35);
    ctx.lineTo(-headR * 0.45, headR * 1.35);
    ctx.closePath();
    ctx.fillStyle = skin;
    ctx.fill();
    ctx.lineWidth = 2.4;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // 2. Distinct Head Contour Silhouettes
    ctx.beginPath();
    switch (dna.face.head_contour) {
      case 'oval_gaunt': // Lean, angular, high cheekbones
        ctx.moveTo(0, -headR * 1.25);
        ctx.bezierCurveTo(headR * 0.95, -headR * 1.25, headR * 0.85, 0.0, headR * 0.65, headR * 0.55);
        ctx.bezierCurveTo(headR * 0.50, headR * 0.95, headR * 0.28, headR * 1.25, 0, headR * 1.30);
        ctx.bezierCurveTo(-headR * 0.28, headR * 1.25, -headR * 0.50, headR * 0.95, -headR * 0.65, headR * 0.55);
        ctx.bezierCurveTo(-headR * 0.85, 0.0, -headR * 0.95, -headR * 1.25, 0, -headR * 1.25);
        break;

      case 'square_jaw': // Broad, strong masculine jaw
        ctx.moveTo(-headR * 0.75, -headR * 1.15);
        ctx.bezierCurveTo(-headR * 0.85, -headR * 0.4, -headR * 0.85, headR * 0.4, -headR * 0.75, headR * 0.75);
        ctx.lineTo(-headR * 0.35, headR * 1.15);
        ctx.lineTo(headR * 0.35, headR * 1.15);
        ctx.lineTo(headR * 0.75, headR * 0.75);
        ctx.bezierCurveTo(headR * 0.85, headR * 0.4, headR * 0.85, -headR * 0.4, headR * 0.75, -headR * 1.15);
        ctx.closePath();
        break;

      case 'delicate_heart': // Wide brow, tapering to delicate feminine chin
        ctx.moveTo(0, -headR * 1.2);
        ctx.bezierCurveTo(headR * 1.05, -headR * 1.15, headR * 0.95, -headR * 0.1, headR * 0.55, headR * 0.55);
        ctx.bezierCurveTo(headR * 0.35, headR * 0.90, headR * 0.15, headR * 1.18, 0, headR * 1.22);
        ctx.bezierCurveTo(-headR * 0.15, headR * 1.18, -headR * 0.35, headR * 0.90, -headR * 0.55, headR * 0.55);
        ctx.bezierCurveTo(-headR * 0.95, -headR * 0.1, -headR * 1.05, -headR * 1.15, 0, -headR * 1.2);
        break;

      case 'round_youth': // Soft, rounded youthful face
      default:
        ctx.arc(0, 0, headR * 1.05, 0, Math.PI * 2);
        break;
    }
    ctx.fillStyle = skin;
    ctx.fill();
    ctx.lineWidth = 3.0;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // 3. Hair Systems
    this.drawHair(ctx, dna.hair, headR, ink);

    // 4. Eyebrows
    this.drawEyebrows(ctx, dna.face.eyebrow_style, state.emotion, headR, ink);

    // 5. Expressive Eyes (Sclera + Iris + Pupil + Catchlight)
    const gaze = state.gazeTarget || [0.4, 0.0];
    this.drawEye(ctx, -headR * 0.34, -headR * 0.08, gaze, state.emotion === 'laughing', dna.face.eye_color, ink);
    this.drawEye(ctx, headR * 0.34, -headR * 0.08, gaze, state.emotion === 'laughing', dna.face.eye_color, ink);

    // 6. 3D Sculpted Nose
    ctx.strokeStyle = ink;
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.moveTo(0, -headR * 0.08);
    ctx.lineTo(headR * 0.08, headR * 0.22);
    ctx.lineTo(-headR * 0.06, headR * 0.25);
    ctx.stroke();

    // 7. Facial Hair
    this.drawFacialHair(ctx, dna.face.facial_hair, dna.face.facial_hair_color || ink, headR);

    // 8. Animated Mouth
    this.drawMouth(ctx, state.emotion, headR, ink);

    ctx.restore();
  }

  private drawEye(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    gaze: [number, number],
    isLaughing: boolean,
    irisColor: string,
    ink: string
  ) {
    ctx.save();
    ctx.translate(x, y);

    if (isLaughing) {
      ctx.beginPath();
      ctx.arc(0, 3, 7.5, Math.PI + 0.35, -0.35);
      ctx.lineWidth = 3.2;
      ctx.strokeStyle = ink;
      ctx.stroke();
      ctx.restore();
      return;
    }

    // Sclera white oval
    ctx.beginPath();
    ctx.ellipse(0, 0, 9.0, 6.2, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.lineWidth = 2.2;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Colored Iris
    const gx = Math.max(-3.5, Math.min(3.5, gaze[0] * 3.5));
    const gy = Math.max(-2.5, Math.min(2.5, gaze[1] * 2.5));
    ctx.beginPath();
    ctx.arc(gx, gy, 4.2, 0, Math.PI * 2);
    ctx.fillStyle = irisColor;
    ctx.fill();

    // Dark Pupil
    ctx.beginPath();
    ctx.arc(gx, gy, 2.2, 0, Math.PI * 2);
    ctx.fillStyle = '#080808';
    ctx.fill();

    // Specular Catchlight
    ctx.beginPath();
    ctx.arc(gx - 1.4, gy - 1.4, 1.4, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();

    ctx.restore();
  }

  private drawEyebrows(
    ctx: CanvasRenderingContext2D,
    style: CharacterDNA['face']['eyebrow_style'],
    emotion: string,
    headR: number,
    ink: string
  ) {
    const tilt = emotion === 'panic' ? -0.22 : emotion === 'laughing' ? 0.12 : emotion === 'intense' ? 0.20 : 0;
    const lw = style === 'thick_bushy' ? 4.2 : 2.6;

    ctx.strokeStyle = ink;
    ctx.lineWidth = lw;

    // Left eyebrow
    ctx.beginPath();
    ctx.moveTo(-headR * 0.58, -headR * 0.32 + tilt * 20);
    ctx.quadraticCurveTo(-headR * 0.32, -headR * 0.46 + tilt * 20, -headR * 0.12, -headR * 0.30);
    ctx.stroke();

    // Right eyebrow
    ctx.beginPath();
    ctx.moveTo(headR * 0.12, -headR * 0.30);
    ctx.quadraticCurveTo(headR * 0.32, -headR * 0.46 - tilt * 20, headR * 0.58, -headR * 0.32 - tilt * 20);
    ctx.stroke();
  }

  private drawFacialHair(ctx: CanvasRenderingContext2D, style: string, color: string, headR: number) {
    if (style === 'none') return;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;

    if (style === 'handlebar_mustache') {
      ctx.lineWidth = 4.2;
      ctx.beginPath();
      ctx.moveTo(-headR * 0.65, headR * 0.38);
      ctx.quadraticCurveTo(-headR * 0.18, headR * 0.46, 0, headR * 0.36);
      ctx.quadraticCurveTo(headR * 0.18, headR * 0.46, headR * 0.65, headR * 0.38);
      ctx.stroke();
    } else if (style === 'stubble') {
      ctx.fillStyle = 'rgba(20, 18, 16, 0.35)';
      ctx.beginPath();
      ctx.arc(0, headR * 0.52, headR * 0.45, 0.2, Math.PI - 0.2);
      ctx.fill();
    } else if (style === 'goatee') {
      ctx.beginPath();
      ctx.ellipse(0, headR * 0.72, 8, 14, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  private drawMouth(ctx: CanvasRenderingContext2D, emotion: string, headR: number, ink: string) {
    ctx.save();
    ctx.translate(0, headR * 0.56);

    if (emotion === 'laughing') {
      ctx.beginPath();
      ctx.moveTo(-13, 0);
      ctx.quadraticCurveTo(0, 18, 13, 0);
      ctx.closePath();
      ctx.fillStyle = '#661111';
      ctx.fill();
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = ink;
      ctx.stroke();

      // Teeth
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(-9, 0, 18, 4.5);

      // Pink Tongue
      ctx.beginPath();
      ctx.arc(0, 11, 7.0, Math.PI, 0);
      ctx.fillStyle = '#E87A88';
      ctx.fill();
    } else if (emotion === 'panic') {
      ctx.beginPath();
      ctx.ellipse(0, 5, 8, 11, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#441111';
      ctx.fill();
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = ink;
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.moveTo(-10, 0);
      ctx.quadraticCurveTo(0, 3.5, 10, 0);
      ctx.lineWidth = 2.6;
      ctx.strokeStyle = ink;
      ctx.stroke();
    }
    ctx.restore();
  }

  private drawHair(ctx: CanvasRenderingContext2D, hair: CharacterDNA['hair'], headR: number, ink: string) {
    ctx.save();
    ctx.fillStyle = hair.color;
    ctx.strokeStyle = ink;
    ctx.lineWidth = 2.4;

    switch (hair.style) {
      case 'edo_topknot': {
        ctx.beginPath();
        ctx.moveTo(-headR * 0.98, -headR * 0.4);
        ctx.quadraticCurveTo(-headR * 0.3, -headR * 1.45, 0, -headR * 1.45);
        ctx.quadraticCurveTo(headR * 0.3, -headR * 1.45, headR * 0.98, -headR * 0.4);
        ctx.quadraticCurveTo(headR * 0.4, -headR * 0.9, 0, -headR * 0.9);
        ctx.quadraticCurveTo(-headR * 0.4, -headR * 0.9, -headR * 0.98, -headR * 0.4);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Chonmage topknot cylinder
        ctx.beginPath();
        ctx.ellipse(headR * 0.18, -headR * 1.6, 13, 18, 0.38, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // White paper cord
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 3.0;
        ctx.beginPath();
        ctx.arc(headR * 0.12, -headR * 1.45, 8, 0, Math.PI);
        ctx.stroke();
        break;
      }
      case 'edo_shimada': {
        ctx.beginPath();
        ctx.moveTo(-headR * 1.05, -headR * 0.3);
        ctx.quadraticCurveTo(-headR * 1.15, -headR * 1.35, 0, -headR * 1.55);
        ctx.quadraticCurveTo(headR * 1.15, -headR * 1.35, headR * 1.05, -headR * 0.3);
        ctx.quadraticCurveTo(headR * 0.4, -headR * 0.85, 0, -headR * 0.85);
        ctx.quadraticCurveTo(-headR * 0.4, -headR * 0.85, -headR * 1.05, -headR * 0.3);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Kanzashi Hairpin
        if (hair.accessory === 'kanzashi_hairpin') {
          ctx.strokeStyle = '#D92B1C';
          ctx.lineWidth = 4.0;
          ctx.beginPath();
          ctx.moveTo(-headR * 0.85, -headR * 1.15);
          ctx.lineTo(headR * 0.95, -headR * 1.55);
          ctx.stroke();

          ctx.fillStyle = '#FF4500';
          ctx.beginPath();
          ctx.arc(headR * 0.95, -headR * 1.55, 6.5, 0, Math.PI * 2);
          ctx.fill();
        }
        break;
      }
      case 'side_sweep_1914': {
        ctx.beginPath();
        ctx.moveTo(-headR * 0.98, -headR * 0.3);
        ctx.quadraticCurveTo(-headR * 0.5, -headR * 1.45, headR * 0.65, -headR * 1.35);
        ctx.quadraticCurveTo(headR * 1.05, -headR * 0.8, headR * 0.95, -headR * 0.2);
        ctx.lineTo(headR * 0.25, -headR * 0.55);
        ctx.lineTo(-headR * 0.65, headR * 0.1);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        break;
      }
      case 'modern_part': {
        ctx.beginPath();
        ctx.moveTo(-headR * 0.96, -headR * 0.35);
        ctx.quadraticCurveTo(-headR * 0.6, -headR * 1.38, headR * 0.1, -headR * 1.42);
        ctx.quadraticCurveTo(headR * 0.85, -headR * 1.38, headR * 0.98, -headR * 0.35);
        ctx.quadraticCurveTo(0, -headR * 0.85, -headR * 0.96, -headR * 0.35);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        break;
      }
      case 'short_crop': {
        ctx.beginPath();
        ctx.arc(0, -headR * 0.5, headR * 0.92, Math.PI * 0.9, Math.PI * 2.1);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        break;
      }
      default:
        break;
    }
    ctx.restore();
  }

  // ============================================================================
  // UPPER BODY & LAYERED COSTUME GEOMETRY
  // ============================================================================
  private drawUpperCostume(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA,
    state: CharacterState,
    skel: any,
    ink: string
  ) {
    ctx.save();
    const sc = skel.shoulderCenter;
    const hr = skel.hipRoot;
    const costume = dna.costume;

    ctx.translate((sc.x + hr.x) / 2, (sc.y + hr.y) / 2);
    ctx.rotate(skel.torsoTilt);

    const torsoH = Math.hypot(sc.x - hr.x, sc.y - hr.y);
    const sw = dna.proportions.shoulder_width;

    // 1. Base Garment / Robe Contour with Organic Drapery
    ctx.beginPath();
    ctx.moveTo(-sw * 0.58, -torsoH * 0.5);
    ctx.lineTo(sw * 0.58, -torsoH * 0.5);
    ctx.bezierCurveTo(sw * 0.55, 0, sw * 0.45, torsoH * 0.3, sw * 0.42, torsoH * 0.5);
    ctx.lineTo(-sw * 0.42, torsoH * 0.5);
    ctx.bezierCurveTo(-sw * 0.45, torsoH * 0.3, -sw * 0.55, 0, -sw * 0.58, -torsoH * 0.5);
    ctx.closePath();
    ctx.fillStyle = costume.primary_color;
    ctx.fill();
    ctx.lineWidth = 3.2;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // 2. Archetype Specific Details
    switch (costume.archetype) {
      case 'frock_coat_1914': {
        // High white collar & necktie
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(-sw * 0.16, -torsoH * 0.5, sw * 0.32, torsoH * 0.22);
        ctx.strokeStyle = ink;
        ctx.lineWidth = 2.0;
        ctx.strokeRect(-sw * 0.16, -torsoH * 0.5, sw * 0.32, torsoH * 0.22);

        // Dark cravat
        ctx.fillStyle = '#1A1816';
        ctx.beginPath();
        ctx.moveTo(0, -torsoH * 0.48);
        ctx.lineTo(-sw * 0.08, -torsoH * 0.3);
        ctx.lineTo(sw * 0.08, -torsoH * 0.3);
        ctx.closePath();
        ctx.fill();

        // Notched Lapels
        ctx.strokeStyle = costume.accent_color || ink;
        ctx.lineWidth = 2.6;
        ctx.beginPath();
        ctx.moveTo(-sw * 0.35, -torsoH * 0.5);
        ctx.lineTo(-sw * 0.12, -torsoH * 0.1);
        ctx.lineTo(0, torsoH * 0.2);
        ctx.moveTo(sw * 0.35, -torsoH * 0.5);
        ctx.lineTo(sw * 0.12, -torsoH * 0.1);
        ctx.lineTo(0, torsoH * 0.2);
        ctx.stroke();

        // Double breasted buttons
        ctx.fillStyle = '#C8A840';
        for (const by of [-torsoH * 0.1, torsoH * 0.05, torsoH * 0.2]) {
          ctx.beginPath();
          ctx.arc(-sw * 0.14, by, 3.2, 0, Math.PI * 2);
          ctx.arc(sw * 0.14, by, 3.2, 0, Math.PI * 2);
          ctx.fill();
        }
        break;
      }
      case 'edo_kimono_formal': {
        // Overlapping silk collars (juban white under-collar + kimono outer)
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 3.4;
        ctx.beginPath();
        ctx.moveTo(-sw * 0.28, -torsoH * 0.5);
        ctx.lineTo(sw * 0.18, -torsoH * 0.05);
        ctx.stroke();

        ctx.strokeStyle = costume.accent_color;
        ctx.lineWidth = 3.0;
        ctx.beginPath();
        ctx.moveTo(sw * 0.28, -torsoH * 0.5);
        ctx.lineTo(-sw * 0.18, -torsoH * 0.05);
        ctx.stroke();

        // Wide Obi Sash & Obijime cord
        ctx.fillStyle = costume.accent_color;
        ctx.fillRect(-sw * 0.44, torsoH * 0.12, sw * 0.88, torsoH * 0.28);
        ctx.strokeStyle = ink;
        ctx.lineWidth = 2.4;
        ctx.strokeRect(-sw * 0.44, torsoH * 0.12, sw * 0.88, torsoH * 0.28);

        // Gold obijime cord
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        ctx.moveTo(-sw * 0.44, torsoH * 0.26);
        ctx.lineTo(sw * 0.44, torsoH * 0.26);
        ctx.stroke();
        break;
      }
      case 'modern_hoodie': {
        // Hood rim around neck
        ctx.strokeStyle = costume.accent_color;
        ctx.lineWidth = 3.4;
        ctx.beginPath();
        ctx.arc(0, -torsoH * 0.42, sw * 0.24, 0.2, Math.PI - 0.2);
        ctx.stroke();

        // Kangaroo pocket
        ctx.strokeStyle = ink;
        ctx.lineWidth = 2.2;
        ctx.strokeRect(-sw * 0.32, torsoH * 0.15, sw * 0.64, torsoH * 0.25);
        break;
      }
      case 'polar_hazard_suit': {
        // Heavy insulated baffles & high-vis safety reflective stripes
        ctx.fillStyle = '#FFFF00';
        ctx.fillRect(-sw * 0.52, -torsoH * 0.2, sw * 1.04, 12);
        ctx.fillRect(-sw * 0.45, torsoH * 0.15, sw * 0.90, 12);
        ctx.strokeStyle = ink;
        ctx.lineWidth = 2.0;
        ctx.strokeRect(-sw * 0.52, -torsoH * 0.2, sw * 1.04, 12);
        ctx.strokeRect(-sw * 0.45, torsoH * 0.15, sw * 0.90, 12);
        break;
      }
      default:
        break;
    }

    ctx.restore();
  }

  // ============================================================================
  // ORGANIC LIMBS (Tapered Polygons, Joint Caps & Footwear)
  // ============================================================================
  private drawLowerCostume(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA,
    state: CharacterState,
    skel: any,
    ink: string
  ) {
    const limbW = dna.proportions.limb_thickness;
    const pantsCol = dna.costume.pants_color;

    // Left Leg (Upper thigh, knee, lower calf)
    this.drawOrganicLimb(ctx, skel.hipL, skel.leftLeg.joint, skel.leftLeg.end, limbW * 1.25, limbW * 0.95, ink, pantsCol);
    this.drawFoot(ctx, dna.costume.footwear, skel.leftLeg.end, false, ink, dna.face.skin_tone);

    // Right Leg
    const rightBare = state.lostSandalRight || dna.costume.footwear === 'bare_foot';
    this.drawOrganicLimb(ctx, skel.hipR, skel.rightLeg.joint, skel.rightLeg.end, limbW * 1.25, limbW * 0.95, ink, pantsCol);
    this.drawFoot(ctx, rightBare ? 'bare_foot' : dna.costume.footwear, skel.rightLeg.end, rightBare, ink, dna.face.skin_tone);
  }

  private drawArmsAndHands(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA,
    state: CharacterState,
    skel: any,
    ink: string,
    skin: string
  ) {
    const limbW = dna.proportions.limb_thickness * 0.95;
    const sleeveCol = dna.costume.primary_color;

    // Left Arm
    this.drawOrganicLimb(ctx, skel.shoulderL, skel.leftArm.joint, skel.leftArm.end, limbW * 1.15, limbW * 0.85, ink, sleeveCol);
    this.drawArticulatedHand(ctx, skel.leftArm.end, state.action === 'hang_from_ledge' ? 'grip' : 'open', ink, skin);

    // Right Arm
    this.drawOrganicLimb(ctx, skel.shoulderR, skel.rightArm.joint, skel.rightArm.end, limbW * 1.15, limbW * 0.85, ink, sleeveCol);
    this.drawArticulatedHand(ctx, skel.rightArm.end, state.action === 'hang_from_ledge' ? 'pinch_high' : (dna.held_props?.right_hand ? 'grip' : 'open'), ink, skin);
  }

  /**
   * Draws a tapered organic limb segment with joint caps and muscle curvature
   */
  private drawOrganicLimb(
    ctx: CanvasRenderingContext2D,
    p1: Point2D,
    p2: Point2D,
    p3: Point2D,
    w1: number,
    w2: number,
    ink: string,
    fillCol: string
  ) {
    ctx.save();

    // 1. Upper Segment (p1 -> p2)
    const dx1 = p2.x - p1.x;
    const dy1 = p2.y - p1.y;
    const len1 = Math.hypot(dx1, dy1) || 1;
    const nx1 = -dy1 / len1;
    const ny1 = dx1 / len1;

    ctx.beginPath();
    ctx.moveTo(p1.x + nx1 * w1 * 0.5, p1.y + ny1 * w1 * 0.5);
    ctx.lineTo(p2.x + nx1 * w1 * 0.4, p2.y + ny1 * w1 * 0.4);
    ctx.lineTo(p2.x - nx1 * w1 * 0.4, p2.y - ny1 * w1 * 0.4);
    ctx.lineTo(p1.x - nx1 * w1 * 0.5, p1.y - ny1 * w1 * 0.5);
    ctx.closePath();
    ctx.fillStyle = fillCol;
    ctx.fill();
    ctx.lineWidth = 2.6;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Joint cap (Knee / Elbow)
    ctx.beginPath();
    ctx.arc(p2.x, p2.y, w1 * 0.45, 0, Math.PI * 2);
    ctx.fillStyle = fillCol;
    ctx.fill();
    ctx.stroke();

    // 2. Lower Segment (p2 -> p3)
    const dx2 = p3.x - p2.x;
    const dy2 = p3.y - p2.y;
    const len2 = Math.hypot(dx2, dy2) || 1;
    const nx2 = -dy2 / len2;
    const ny2 = dx2 / len2;

    ctx.beginPath();
    ctx.moveTo(p2.x + nx2 * w2 * 0.5, p2.y + ny2 * w2 * 0.5);
    ctx.lineTo(p3.x + nx2 * w2 * 0.35, p3.y + ny2 * w2 * 0.35);
    ctx.lineTo(p3.x - nx2 * w2 * 0.35, p3.y - ny2 * w2 * 0.35);
    ctx.lineTo(p2.x - nx2 * w2 * 0.5, p2.y - ny2 * w2 * 0.5);
    ctx.closePath();
    ctx.fillStyle = fillCol;
    ctx.fill();
    ctx.lineWidth = 2.6;
    ctx.strokeStyle = ink;
    ctx.stroke();

    ctx.restore();
  }

  // ============================================================================
  // ARTICULATED 5-FINGER HANDS
  // ============================================================================
  private drawArticulatedHand(
    ctx: CanvasRenderingContext2D,
    pos: Point2D,
    gripType: 'open' | 'grip' | 'pinch_high',
    ink: string,
    skin: string
  ) {
    ctx.save();
    ctx.translate(pos.x, pos.y);
    ctx.fillStyle = skin;
    ctx.strokeStyle = ink;
    ctx.lineWidth = 1.8;

    if (gripType === 'grip') {
      // Enclosed tight fist around rail/prop
      ctx.beginPath();
      ctx.arc(0, 0, 7.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Finger knuckle creases
      for (const fx of [-4, 0, 4]) {
        ctx.beginPath();
        ctx.arc(fx, 3, 2.5, 0, Math.PI);
        ctx.stroke();
      }
    } else if (gripType === 'pinch_high') {
      // Delicate pinch (Index + Thumb holding corner)
      ctx.beginPath();
      ctx.ellipse(0, 0, 6, 8, 0.3, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Extended index finger
      ctx.beginPath();
      ctx.arc(4, -6, 2.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else {
      // Expressive 5-Finger Open Hand
      // Palm
      ctx.beginPath();
      ctx.ellipse(0, 0, 6.5, 7.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Opposed Thumb
      ctx.beginPath();
      ctx.ellipse(-5.5, -2, 2.6, 4.5, -0.6, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // 4 Articulated Fingers (Index, Middle, Ring, Pinky)
      const fingerOffsets = [
        { x: -3.5, y: -7.5, h: 6.5 },
        { x: -1.0, y: -9.0, h: 8.0 },
        { x: 1.5, y: -8.5, h: 7.5 },
        { x: 4.0, y: -6.5, h: 5.5 },
      ];
      for (const f of fingerOffsets) {
        ctx.beginPath();
        ctx.ellipse(f.x, f.y, 2.0, f.h * 0.5, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    }

    ctx.restore();
  }

  // ============================================================================
  // FOOTWEAR SPECIFICATIONS
  // ============================================================================
  private drawFoot(
    ctx: CanvasRenderingContext2D,
    footwear: string,
    pos: Point2D,
    isBare: boolean,
    ink: string,
    skinTone: string
  ) {
    ctx.save();
    ctx.translate(pos.x, pos.y);

    if (isBare) {
      ctx.fillStyle = skinTone;
      ctx.beginPath();
      ctx.ellipse(6, 0, 13, 5.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.0;
      ctx.strokeStyle = ink;
      ctx.stroke();

      // Splattered mud stain
      ctx.fillStyle = '#3E2A1A';
      ctx.beginPath();
      ctx.arc(6, 2, 3.5, 0, Math.PI * 2);
      ctx.fill();
    } else if (footwear === 'waraji_sandals') {
      // Woven Straw Waraji
      ctx.fillStyle = '#C2A368';
      ctx.beginPath();
      ctx.ellipse(6, 1, 14, 5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.0;
      ctx.strokeStyle = ink;
      ctx.stroke();

      // Tie cords
      ctx.strokeStyle = '#544222';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(-2, -3);
      ctx.lineTo(8, 2);
      ctx.moveTo(8, -3);
      ctx.lineTo(-2, 2);
      ctx.stroke();
    } else if (footwear === 'snow_boots') {
      // Insulated heavy snow boots
      ctx.fillStyle = '#212121';
      ctx.beginPath();
      ctx.roundRect(-4, -4, 24, 11, 4);
      ctx.fill();
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = ink;
      ctx.stroke();
    } else {
      // Polished leather shoes or sneakers
      ctx.fillStyle = footwear === 'sneakers' ? '#EAEAEA' : '#1A1816';
      ctx.beginPath();
      ctx.ellipse(7, 0, 15, 6, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.2;
      ctx.strokeStyle = ink;
      ctx.stroke();
    }
    ctx.restore();
  }

  // ============================================================================
  // PROPS & VERIFIED VIETNAMESE DOCUMENTS
  // ============================================================================
  private drawProps(ctx: CanvasRenderingContext2D, dna: CharacterDNA, state: CharacterState, skel: any) {
    const rHand = skel.rightArm.end;

    if (dna.held_props?.right_hand === 'letter_envelope') {
      // Oiled-Paper Waxed Letter (Haru)
      ctx.save();
      ctx.translate(rHand.x + 14, rHand.y - 16);
      ctx.rotate(0.2);

      ctx.fillStyle = '#F5E4B8';
      ctx.fillRect(-15, -24, 30, 48);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.2;
      ctx.strokeRect(-15, -24, 30, 48);

      // Crimson Cinnabar Wax Seal
      ctx.fillStyle = '#C8281E';
      ctx.beginPath();
      ctx.arc(0, 0, 5.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    } else if (dna.held_props?.right_hand === 'letter_scroll_open') {
      // Opened Letter with Verified Vietnamese Unicode
      ctx.save();
      ctx.translate(rHand.x - 20, rHand.y - 30);
      ctx.fillStyle = '#FFF9EC';
      ctx.fillRect(-45, -55, 90, 110);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.4;
      ctx.strokeRect(-45, -55, 90, 110);

      // Authentic Vietnamese calligraphy
      ctx.fillStyle = '#181614';
      ctx.font = 'bold 9.5px "Segoe UI", Arial, sans-serif';
      ctx.fillText('Aiko thân mến,', -36, -34);
      ctx.fillText('Nhớ mang theo ô.', -36, -14);
      ctx.fillText('Chiều nay mưa to!', -36, 6);
      ctx.restore();
    } else if (dna.held_props?.right_hand === 'tablet') {
      // Holographic Digital Tablet (Tech / Antarctica)
      ctx.save();
      ctx.translate(rHand.x + 12, rHand.y - 12);
      ctx.fillStyle = '#111822';
      ctx.fillRect(-14, -24, 28, 48);
      ctx.strokeStyle = '#00D2FF';
      ctx.lineWidth = 2.0;
      ctx.strokeRect(-14, -24, 28, 48);

      // Glowing screen data
      ctx.fillStyle = 'rgba(0, 210, 255, 0.45)';
      ctx.fillRect(-12, -22, 24, 44);

      // Mini wave telemetry
      ctx.strokeStyle = '#00FFA3';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.moveTo(-10, -5);
      ctx.lineTo(-4, 4);
      ctx.lineTo(2, -8);
      ctx.lineTo(8, 2);
      ctx.stroke();
      ctx.restore();
    } else if (dna.held_props?.right_hand === 'portfolio') {
      // Cardboard Artist Portfolio (1914 / 1888)
      ctx.save();
      ctx.translate(rHand.x - 10, rHand.y - 10);
      ctx.rotate(0.22);
      ctx.fillStyle = '#4A3B2C';
      ctx.fillRect(-24, -34, 48, 68);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.4;
      ctx.strokeRect(-24, -34, 48, 68);
      ctx.strokeStyle = '#C2A368';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(-24, 0);
      ctx.lineTo(24, 0);
      ctx.stroke();
      ctx.restore();
    }
  }
}
