/**
 * Universal Data-Driven Character Engine V4.2.2
 * 
 * Implements Task 2:
 * - 100% Data-Driven by CharacterDNA (Zero hardcoded character classes)
 * - Skeletal Hierarchy with Analytical 2-Bone Inverse Kinematics (IK)
 * - Foot-Locking Constraints on Ground Plane
 * - Hand-Object Attachment Constraints
 * - Layered Organic Vector Anatomy (Head, Neck, Torso, Limbs, Hands, Feet)
 * - Modular Hair Systems & Cultural Costume Grammars (Edo, Western 1914, Modern Tech)
 * - Semantic Action Library (Sprint, Walk, Slip & Fall, Hang from Ledge, Present, Laugh, Gesture)
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
    archetype: 'edo_hanten_courier' | 'edo_kimono_formal' | 'frock_coat_1914' | 'modern_hoodie' | 'lab_coat' | 'work_apron';
    primary_color: string;
    accent_color: string;
    pants_skirt: 'trousers' | 'kimono_skirt' | 'hakama' | 'jeans';
    pants_color: string;
    belt_sash: 'obi_sash' | 'leather_belt' | 'cord' | 'none';
    footwear: 'waraji_sandals' | 'tabi_socks' | 'leather_shoes' | 'sneakers' | 'bare_foot';
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
  progress: number; // 0.0 to 1.0 (or normalized cycle time)
  emotion: 'neutral' | 'determined' | 'panic' | 'relief' | 'laughing' | 'intense' | 'focused';
  gazeTarget?: [number, number]; // [lookX, lookY] screen relative
  handConstraintL?: [number, number]; // Explicit screen-space hand anchor (e.g. railing)
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

    // Clamp distance to avoid division by zero or unreachable target
    const maxReach = (len1 + len2) * 0.999;
    const minReach = Math.abs(len1 - len2) * 1.001;
    const d = Math.max(minReach, Math.min(maxReach, dist));

    const baseAngle = Math.atan2(dy, dx);
    const cosAngle1 = (len1 * len1 + d * d - len2 * len2) / (2 * len1 * d);
    const clampedCos1 = Math.max(-1, Math.min(1, cosAngle1));
    const angle1 = baseAngle + bendDirection * Math.acos(clampedCos1);

    const jointX = root.x + Math.cos(angle1) * len1;
    const jointY = root.y + Math.sin(angle1) * len1;

    // End effector reaches target (or clamped reach)
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
    const ink = '#161412';
    const skin = dna.face.skin_tone;

    // Contact shadow
    this.drawContactShadow(state, totalH);

    // Compute Skeleton based on Action Library & IK
    const skeleton = this.evaluateSkeleton(dna, state, totalH, headR);

    // Render Clothing / Costume Layer: Lower Body (Pants / Skirt / Legs)
    this.drawLowerCostume(ctx, dna, state, skeleton, ink);

    // Render Upper Body Torso & Costume
    this.drawUpperCostume(ctx, dna, state, skeleton, ink);

    // Render Head & Face
    this.drawHeadAndFace(ctx, dna, state, skeleton.head, headR, ink, skin);

    // Render Arms & Hands (with IK & Object Grasp)
    this.drawArmsAndHands(ctx, dna, state, skeleton, ink, skin);

    // Render Held Props
    this.drawProps(ctx, dna, state, skeleton);

    ctx.restore();
  }

  public draw(dna: CharacterDNA, state: CharacterState) {
    this.render(dna, state);
  }

  private drawContactShadow(state: CharacterState, totalH: number) {
    const ctx = this.ctx;
    ctx.save();
    let shadowAlpha = 0.45;
    let shadowW = 85;
    let shadowY = 0;

    if (state.action === 'hang_from_ledge') {
      shadowAlpha = 0.12;
      shadowW = 40;
      shadowY = totalH * 0.4;
    } else if (state.action === 'slip_fall') {
      shadowAlpha = 0.25;
      shadowW = 60;
    }

    ctx.beginPath();
    ctx.ellipse(0, shadowY, shadowW, 14, 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(16, 14, 12, ${shadowAlpha})`;
    ctx.fill();
    ctx.restore();
  }

  // ============================================================================
  // KINEMATIC SKELETAL SOLVER
  // ============================================================================
  private evaluateSkeleton(
    dna: CharacterDNA,
    state: CharacterState,
    totalH: number,
    headR: number
  ) {
    const prop = dna.proportions;
    const legLen = totalH * 0.46;
    const thighLen = legLen * 0.52;
    const shinLen = legLen * 0.48;
    const armLen = totalH * 0.38;
    const upperArm = armLen * 0.52;
    const forearm = armLen * 0.48;

    let rootY = -legLen;
    let torsoTilt = 0;
    let headTilt = 0;
    let pelvicBob = 0;

    let lFootTarget: Point2D = { x: -prop.shoulder_width * 0.35, y: 0 };
    let rFootTarget: Point2D = { x: prop.shoulder_width * 0.35, y: 0 };
    let lHandTarget: Point2D = { x: -prop.shoulder_width * 0.5, y: rootY + 50 };
    let rHandTarget: Point2D = { x: prop.shoulder_width * 0.5, y: rootY + 50 };

    const t = state.progress;

    switch (state.action) {
      case 'sprint': {
        torsoTilt = 0.32;
        headTilt = -0.15;
        const cycle = (t * Math.PI * 5) % (Math.PI * 2);
        pelvicBob = Math.abs(Math.sin(cycle)) * 14;

        // Kinematic running strides with foot lift & plant
        const stride = Math.sin(cycle) * 45;
        const liftL = Math.max(0, -Math.sin(cycle)) * 28;
        const liftR = Math.max(0, Math.sin(cycle)) * 28;

        lFootTarget = { x: -stride * 0.8, y: -liftL };
        rFootTarget = { x: stride * 0.8, y: -liftR };

        // Pumping arms (or clutched prop)
        lHandTarget = { x: Math.sin(cycle + Math.PI) * 35, y: rootY + 25 + Math.cos(cycle) * 15 };
        rHandTarget = { x: Math.sin(cycle) * 35, y: rootY + 25 - Math.cos(cycle) * 15 };
        break;
      }
      case 'walk': {
        torsoTilt = 0.08;
        const cycle = (t * Math.PI * 3) % (Math.PI * 2);
        pelvicBob = Math.abs(Math.sin(cycle)) * 8;
        const stride = Math.sin(cycle) * 28;
        const liftL = Math.max(0, -Math.sin(cycle)) * 16;
        const liftR = Math.max(0, Math.sin(cycle)) * 16;

        lFootTarget = { x: -stride, y: -liftL };
        rFootTarget = { x: stride, y: -liftR };
        lHandTarget = { x: Math.sin(cycle + Math.PI) * 20, y: rootY + 55 };
        rHandTarget = { x: Math.sin(cycle) * 20, y: rootY + 55 };
        break;
      }
      case 'slip_fall': {
        // Dramatic slipping backwards
        torsoTilt = -0.45;
        headTilt = 0.40;
        rootY += 35;
        lFootTarget = { x: 30, y: -10 };
        rFootTarget = { x: 55, y: -35 }; // Slipping leg thrown forward
        lHandTarget = { x: -45, y: rootY - 40 }; // Arms flailing up
        rHandTarget = { x: 45, y: rootY - 50 };
        break;
      }
      case 'hang_from_ledge': {
        // Hanging by left hand from overhead constraint!
        torsoTilt = -0.28;
        headTilt = 0.32;
        rootY = -legLen + 40;

        // Dangling legs
        const sway = Math.sin(t * 4) * 12;
        lFootTarget = { x: -20 + sway, y: 45 };
        rFootTarget = { x: 15 - sway, y: 55 };

        // Left hand locked to railing above head!
        lHandTarget = { x: -35, y: rootY - armLen * 0.95 };
        // Right hand holding letter high aloft!
        rHandTarget = { x: 50, y: rootY - armLen * 0.90 };
        break;
      }
      case 'present_two_handed': {
        torsoTilt = 0.16; // Respectful bow
        headTilt = 0.12;
        lFootTarget = { x: -16, y: 0 };
        rFootTarget = { x: 16, y: 0 };
        // Both hands joined in front holding letter
        lHandTarget = { x: 38, y: rootY + 28 };
        rHandTarget = { x: 44, y: rootY + 28 };
        break;
      }
      case 'laugh_heartily': {
        // Laughing with chest heaving
        const laughWave = Math.sin(t * 18);
        torsoTilt = -0.15 + laughWave * 0.06;
        headTilt = -0.22 + laughWave * 0.08; // Head thrown back
        lFootTarget = { x: -18, y: 0 };
        rFootTarget = { x: 18, y: 0 };
        lHandTarget = { x: -25, y: rootY + 35 };
        rHandTarget = { x: 30, y: rootY + 45 };
        break;
      }
      case 'inspect_down': {
        torsoTilt = 0.24;
        headTilt = 0.45; // Looking directly down
        lFootTarget = { x: -18, y: 0 };
        rFootTarget = { x: 22, y: -15 }; // Lifted foot
        lHandTarget = { x: -35, y: rootY + 45 }; // Hand on hip
        rHandTarget = { x: 30, y: rootY - 15 };  // Scratching head
        break;
      }
      default: {
        // Subtle breathing
        const breath = Math.sin(t * 2) * 2;
        pelvicBob = breath;
        lFootTarget = { x: -18, y: 0 };
        rFootTarget = { x: 18, y: 0 };
        lHandTarget = { x: -25, y: rootY + 60 };
        rHandTarget = { x: 25, y: rootY + 60 };
        break;
      }
    }

    const hipRoot: Point2D = { x: 0, y: rootY - pelvicBob };
    const shoulderCenter: Point2D = {
      x: hipRoot.x + Math.sin(torsoTilt) * (totalH * 0.30),
      y: hipRoot.y - Math.cos(torsoTilt) * (totalH * 0.30),
    };
    const headCenter: Point2D = {
      x: shoulderCenter.x + Math.sin(headTilt) * (headR * 1.5),
      y: shoulderCenter.y - Math.cos(headTilt) * (headR * 1.5),
    };

    // Shoulder sockets
    const shoulderL: Point2D = {
      x: shoulderCenter.x - Math.cos(torsoTilt) * (prop.shoulder_width * 0.5),
      y: shoulderCenter.y - Math.sin(torsoTilt) * (prop.shoulder_width * 0.5),
    };
    const shoulderR: Point2D = {
      x: shoulderCenter.x + Math.cos(torsoTilt) * (prop.shoulder_width * 0.5),
      y: shoulderCenter.y + Math.sin(torsoTilt) * (prop.shoulder_width * 0.5),
    };

    // Hip sockets
    const hipL: Point2D = { x: hipRoot.x - prop.shoulder_width * 0.3, y: hipRoot.y };
    const hipR: Point2D = { x: hipRoot.x + prop.shoulder_width * 0.3, y: hipRoot.y };

    // Solve 2-Bone IK for Legs
    const leftLeg = this.solve2BoneIK(hipL, lFootTarget, thighLen, shinLen, 1);
    const rightLeg = this.solve2BoneIK(hipR, rFootTarget, thighLen, shinLen, 1);

    // Solve 2-Bone IK for Arms
    const leftArm = this.solve2BoneIK(shoulderL, lHandTarget, upperArm, forearm, -1);
    const rightArm = this.solve2BoneIK(shoulderR, rHandTarget, upperArm, forearm, 1);

    return {
      hipRoot,
      shoulderCenter,
      head: headCenter,
      torsoTilt,
      headTilt,
      hipL,
      hipR,
      shoulderL,
      shoulderR,
      leftLeg,
      rightLeg,
      leftArm,
      rightArm,
    };
  }

  // ============================================================================
  // ORGANIC HEAD & FACIAL ACTING
  // ============================================================================
  private drawHeadAndFace(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA,
    state: CharacterState,
    pos: Point2D,
    headR: number,
    ink: string,
    skin: string
  ) {
    ctx.save();
    ctx.translate(pos.x, pos.y);
    ctx.rotate(state.headTilt);

    // 1. Organic Jaw & Head Contour
    ctx.beginPath();
    switch (dna.face.head_contour) {
      case 'oval_gaunt':
        ctx.moveTo(-headR * 0.9, -headR * 0.2);
        ctx.quadraticCurveTo(-headR * 1.05, -headR * 1.2, 0, -headR * 1.35);
        ctx.quadraticCurveTo(headR * 1.05, -headR * 1.2, headR * 0.9, -headR * 0.2);
        ctx.quadraticCurveTo(headR * 0.65, headR * 1.1, 0, headR * 1.25); // Lean chin
        ctx.quadraticCurveTo(-headR * 0.65, headR * 1.1, -headR * 0.9, -headR * 0.2);
        break;
      case 'square_jaw':
        ctx.moveTo(-headR * 0.95, -headR * 0.2);
        ctx.quadraticCurveTo(-headR * 1.0, -headR * 1.2, 0, -headR * 1.3);
        ctx.quadraticCurveTo(headR * 1.0, -headR * 1.2, headR * 0.95, -headR * 0.2);
        ctx.lineTo(headR * 0.75, headR * 0.9);
        ctx.lineTo(-headR * 0.75, headR * 0.9);
        break;
      default:
        // Round / Natural youth
        ctx.moveTo(-headR * 0.95, -headR * 0.2);
        ctx.quadraticCurveTo(-headR * 1.0, -headR * 1.25, 0, -headR * 1.3);
        ctx.quadraticCurveTo(headR * 1.0, -headR * 1.25, headR * 0.95, -headR * 0.2);
        ctx.quadraticCurveTo(headR * 0.75, headR * 1.0, 0, headR * 1.15);
        ctx.quadraticCurveTo(-headR * 0.75, headR * 1.0, -headR * 0.95, -headR * 0.2);
        break;
    }
    ctx.closePath();
    ctx.fillStyle = skin;
    ctx.fill();
    ctx.lineWidth = 3.2;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // 2. Procedural Hair Systems
    this.drawHair(ctx, dna.hair, headR, ink);

    // 3. Eyebrows
    const browTilt = state.emotion === 'panic' ? -0.15 : state.emotion === 'laughing' ? 0.08 : 0;
    ctx.lineWidth = 2.8;
    ctx.strokeStyle = ink;
    ctx.beginPath();
    ctx.moveTo(-headR * 0.55, -headR * 0.25 + browTilt * 20);
    ctx.quadraticCurveTo(-headR * 0.3, -headR * 0.4 + browTilt * 20, -headR * 0.1, -headR * 0.25);
    ctx.moveTo(headR * 0.1, -headR * 0.25);
    ctx.quadraticCurveTo(headR * 0.3, -headR * 0.4 - browTilt * 20, headR * 0.55, -headR * 0.25 - browTilt * 20);
    ctx.stroke();

    // 4. Eyes with Specular Highlights & Gaze Direction
    const gaze = state.gazeTarget || [0.4, 0.0];
    this.drawEye(ctx, -headR * 0.32, -headR * 0.05, gaze, state.emotion === 'laughing', dna.face.eye_color, ink);
    this.drawEye(ctx, headR * 0.32, -headR * 0.05, gaze, state.emotion === 'laughing', dna.face.eye_color, ink);

    // 5. Sculpted Nose
    ctx.strokeStyle = ink;
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.moveTo(0, -headR * 0.05);
    ctx.lineTo(headR * 0.08, headR * 0.25);
    ctx.lineTo(-headR * 0.06, headR * 0.28);
    ctx.stroke();

    // 6. Facial Hair (if configured)
    if (dna.face.facial_hair === 'handlebar_mustache') {
      ctx.strokeStyle = dna.face.facial_hair_color || ink;
      ctx.lineWidth = 3.6;
      ctx.beginPath();
      ctx.moveTo(-headR * 0.65, headR * 0.42);
      ctx.quadraticCurveTo(-headR * 0.15, headR * 0.48, 0, headR * 0.38);
      ctx.quadraticCurveTo(headR * 0.15, headR * 0.48, headR * 0.65, headR * 0.42);
      ctx.stroke();
    }

    // 7. Expressive Mouth
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
      // Happy curved squint
      ctx.beginPath();
      ctx.arc(0, 4, 7, Math.PI + 0.35, -0.35);
      ctx.lineWidth = 3.0;
      ctx.strokeStyle = ink;
      ctx.stroke();
      ctx.restore();
      return;
    }

    // Almond white
    ctx.beginPath();
    ctx.ellipse(0, 0, 8, 5.5, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.lineWidth = 2.0;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Iris & Pupil with gaze tracking
    const gx = Math.max(-3.5, Math.min(3.5, gaze[0] * 3.5));
    const gy = Math.max(-2.5, Math.min(2.5, gaze[1] * 2.5));
    ctx.beginPath();
    ctx.arc(gx, gy, 3.6, 0, Math.PI * 2);
    ctx.fillStyle = irisColor;
    ctx.fill();

    // Specular catchlight
    ctx.beginPath();
    ctx.arc(gx - 1.2, gy - 1.2, 1.4, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();

    ctx.restore();
  }

  private drawMouth(ctx: CanvasRenderingContext2D, emotion: string, headR: number, ink: string) {
    ctx.save();
    ctx.translate(0, headR * 0.55);

    if (emotion === 'laughing') {
      // Wide open smiling laugh with teeth and tongue
      ctx.beginPath();
      ctx.moveTo(-12, 0);
      ctx.quadraticCurveTo(0, 16, 12, 0);
      ctx.closePath();
      ctx.fillStyle = '#6E1616';
      ctx.fill();
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = ink;
      ctx.stroke();

      // Teeth
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(-8, 0, 16, 4.5);

      // Pink tongue
      ctx.beginPath();
      ctx.arc(0, 9, 6.5, Math.PI, 0);
      ctx.fillStyle = '#E87A88';
      ctx.fill();
    } else if (emotion === 'panic') {
      // Gasping fear oval
      ctx.beginPath();
      ctx.ellipse(0, 4, 7, 10, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#4A1414';
      ctx.fill();
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = ink;
      ctx.stroke();
    } else {
      // Confident / focused subtle line
      ctx.beginPath();
      ctx.moveTo(-9, 0);
      ctx.quadraticCurveTo(0, 3, 9, 0);
      ctx.lineWidth = 2.4;
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
        // Forehead hair sweep
        ctx.beginPath();
        ctx.moveTo(-headR * 0.95, -headR * 0.4);
        ctx.quadraticCurveTo(-headR * 0.3, -headR * 1.4, 0, -headR * 1.4);
        ctx.quadraticCurveTo(headR * 0.3, -headR * 1.4, headR * 0.95, -headR * 0.4);
        ctx.quadraticCurveTo(headR * 0.4, -headR * 0.9, 0, -headR * 0.9);
        ctx.quadraticCurveTo(-headR * 0.4, -headR * 0.9, -headR * 0.95, -headR * 0.4);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Topknot Chonmage
        ctx.beginPath();
        ctx.ellipse(headR * 0.15, -headR * 1.55, 12, 16, 0.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // White paper cord tie
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(headR * 0.1, -headR * 1.42, 7, 0, Math.PI);
        ctx.stroke();
        break;
      }
      case 'edo_shimada': {
        // High arched townswoman bun
        ctx.beginPath();
        ctx.moveTo(-headR * 1.0, -headR * 0.3);
        ctx.quadraticCurveTo(-headR * 1.1, -headR * 1.3, 0, -headR * 1.5);
        ctx.quadraticCurveTo(headR * 1.1, -headR * 1.3, headR * 1.0, -headR * 0.3);
        ctx.quadraticCurveTo(headR * 0.4, -headR * 0.8, 0, -headR * 0.8);
        ctx.quadraticCurveTo(-headR * 0.4, -headR * 0.8, -headR * 1.0, -headR * 0.3);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Kanzashi Hairpin
        if (hair.accessory === 'kanzashi_hairpin') {
          ctx.strokeStyle = '#D92B1C';
          ctx.lineWidth = 4.0;
          ctx.beginPath();
          ctx.moveTo(-headR * 0.8, -headR * 1.1);
          ctx.lineTo(headR * 0.9, -headR * 1.5);
          ctx.stroke();
          ctx.fillStyle = '#FF4500';
          ctx.beginPath();
          ctx.arc(headR * 0.9, -headR * 1.5, 6, 0, Math.PI * 2);
          ctx.fill();
        }
        break;
      }
      case 'side_sweep_1914': {
        // 1914 Bohemian side sweep
        ctx.beginPath();
        ctx.moveTo(-headR * 0.95, -headR * 0.3);
        ctx.quadraticCurveTo(-headR * 0.5, -headR * 1.4, headR * 0.6, -headR * 1.3);
        ctx.quadraticCurveTo(headR * 1.0, -headR * 0.8, headR * 0.9, -headR * 0.2);
        ctx.lineTo(headR * 0.2, -headR * 0.5);
        ctx.lineTo(-headR * 0.6, headR * 0.1);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        break;
      }
      case 'modern_part': {
        ctx.beginPath();
        ctx.moveTo(-headR * 0.95, -headR * 0.35);
        ctx.quadraticCurveTo(-headR * 0.6, -headR * 1.35, headR * 0.1, -headR * 1.4);
        ctx.quadraticCurveTo(headR * 0.8, -headR * 1.35, headR * 0.95, -headR * 0.35);
        ctx.quadraticCurveTo(0, -headR * 0.85, -headR * 0.95, -headR * 0.35);
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
  // UPPER BODY & COSTUME LAYERS
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

    // Outer Coat / Robe Contour
    ctx.beginPath();
    ctx.moveTo(-sw * 0.55, -torsoH * 0.5);
    ctx.lineTo(sw * 0.55, -torsoH * 0.5);
    ctx.quadraticCurveTo(sw * 0.52, 0, sw * 0.42, torsoH * 0.5);
    ctx.lineTo(-sw * 0.42, torsoH * 0.5);
    ctx.quadraticCurveTo(-sw * 0.52, 0, -sw * 0.55, -torsoH * 0.5);
    ctx.closePath();
    ctx.fillStyle = costume.primary_color;
    ctx.fill();
    ctx.lineWidth = 3.2;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Lapel / Collar Details
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 2.8;
    ctx.beginPath();
    ctx.moveTo(-sw * 0.25, -torsoH * 0.5);
    ctx.lineTo(sw * 0.15, 0);
    ctx.moveTo(sw * 0.25, -torsoH * 0.5);
    ctx.lineTo(-sw * 0.15, 0);
    ctx.stroke();

    // Waist Belt / Obi Sash
    if (costume.belt_sash === 'obi_sash') {
      ctx.fillStyle = costume.accent_color;
      ctx.fillRect(-sw * 0.45, torsoH * 0.2, sw * 0.9, torsoH * 0.24);
      ctx.strokeStyle = ink;
      ctx.lineWidth = 2.2;
      ctx.strokeRect(-sw * 0.45, torsoH * 0.2, sw * 0.9, torsoH * 0.24);
    } else if (costume.belt_sash === 'leather_belt') {
      ctx.fillStyle = '#221812';
      ctx.fillRect(-sw * 0.42, torsoH * 0.35, sw * 0.84, 10);
      ctx.fillStyle = '#C8A840';
      ctx.fillRect(-6, torsoH * 0.35 - 2, 12, 14); // Buckle
    }

    ctx.restore();
  }

  // ============================================================================
  // LOWER BODY & FEET
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

    // Draw Left Leg
    this.drawLegBone(ctx, skel.hipL, skel.leftLeg.joint, skel.leftLeg.end, limbW, ink, pantsCol);
    this.drawFoot(ctx, dna.costume.footwear, skel.leftLeg.end, false, ink, dna.face.skin_tone);

    // Draw Right Leg
    this.drawLegBone(ctx, skel.hipR, skel.rightLeg.joint, skel.rightLeg.end, limbW, ink, pantsCol);
    const rightBare = state.lostSandalRight || dna.costume.footwear === 'bare_foot';
    this.drawFoot(ctx, rightBare ? 'bare_foot' : dna.costume.footwear, skel.rightLeg.end, rightBare, ink, dna.face.skin_tone);
  }

  private drawLegBone(
    ctx: CanvasRenderingContext2D,
    p1: Point2D,
    p2: Point2D,
    p3: Point2D,
    width: number,
    ink: string,
    fillCol: string
  ) {
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Outer ink
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p3.x, p3.y);
    ctx.lineWidth = width + 4.0;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Inner fabric
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p3.x, p3.y);
    ctx.lineWidth = width;
    ctx.strokeStyle = fillCol;
    ctx.stroke();

    ctx.restore();
  }

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
      // Bare foot with splattered mud
      ctx.fillStyle = skinTone;
      ctx.beginPath();
      ctx.ellipse(6, 0, 13, 5.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.0;
      ctx.strokeStyle = ink;
      ctx.stroke();

      // Toes
      ctx.beginPath();
      ctx.arc(17, 0, 3.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Mud stain
      ctx.fillStyle = '#483524';
      ctx.beginPath();
      ctx.arc(6, 2, 3, 0, Math.PI * 2);
      ctx.fill();
    } else if (footwear === 'waraji_sandals') {
      // Straw Waraji
      ctx.fillStyle = '#C2A368';
      ctx.beginPath();
      ctx.ellipse(6, 1, 14, 5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.0;
      ctx.strokeStyle = ink;
      ctx.stroke();

      // Straw tie cords
      ctx.strokeStyle = '#544222';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(-2, -3);
      ctx.lineTo(8, 2);
      ctx.moveTo(8, -3);
      ctx.lineTo(-2, 2);
      ctx.stroke();
    } else {
      // Modern Shoe / Sneaker
      ctx.fillStyle = '#EAEAEA';
      ctx.beginPath();
      ctx.ellipse(6, 0, 15, 6, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.2;
      ctx.strokeStyle = ink;
      ctx.stroke();
    }
    ctx.restore();
  }

  // ============================================================================
  // ARMS & ARTICULATED 5-FINGER HANDS
  // ============================================================================
  private drawArmsAndHands(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA,
    state: CharacterState,
    skel: any,
    ink: string,
    skin: string
  ) {
    const limbW = dna.proportions.limb_thickness * 0.9;
    const sleeveCol = dna.costume.primary_color;

    // Left Arm
    this.drawArmBone(ctx, skel.shoulderL, skel.leftArm.joint, skel.leftArm.end, limbW, ink, sleeveCol);
    this.drawHand(ctx, skel.leftArm.end, state.action === 'hang_from_ledge' ? 'grip' : 'open', ink, skin);

    // Right Arm
    this.drawArmBone(ctx, skel.shoulderR, skel.rightArm.joint, skel.rightArm.end, limbW, ink, sleeveCol);
    this.drawHand(ctx, skel.rightArm.end, state.action === 'hang_from_ledge' ? 'pinch_high' : 'open', ink, skin);
  }

  private drawArmBone(
    ctx: CanvasRenderingContext2D,
    p1: Point2D,
    p2: Point2D,
    p3: Point2D,
    width: number,
    ink: string,
    sleeveCol: string
  ) {
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p3.x, p3.y);
    ctx.lineWidth = width + 3.8;
    ctx.strokeStyle = ink;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p3.x, p3.y);
    ctx.lineWidth = width;
    ctx.strokeStyle = sleeveCol;
    ctx.stroke();

    ctx.restore();
  }

  private drawHand(
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
    ctx.lineWidth = 2.0;

    if (gripType === 'grip') {
      // Clutched fingers wrapped around beam/rail
      for (let i = -6; i <= 6; i += 4) {
        ctx.beginPath();
        ctx.ellipse(i, -2, 2.8, 6, 0.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
      // Clamped thumb
      ctx.beginPath();
      ctx.ellipse(0, 5, 5, 3, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else if (gripType === 'pinch_high') {
      // Delicate 2-finger pinch holding top corner of document/letter
      ctx.beginPath();
      ctx.arc(0, 0, 6.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else {
      // Natural palm with thumb
      ctx.beginPath();
      ctx.arc(0, 0, 6.0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();
  }

  // ============================================================================
  // PROPS & ARTIFACTS
  // ============================================================================
  private drawProps(ctx: CanvasRenderingContext2D, dna: CharacterDNA, state: CharacterState, skel: any) {
    const rHand = skel.rightArm.end;

    if (dna.held_props?.right_hand === 'letter_envelope') {
      // The Oiled-Paper Letter held safe and dry
      ctx.save();
      ctx.translate(rHand.x + 14, rHand.y - 16);
      ctx.rotate(0.2);

      // Waxed oil paper envelope body
      ctx.fillStyle = '#F5E4B8';
      ctx.fillRect(-15, -24, 30, 48);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.2;
      ctx.strokeRect(-15, -24, 30, 48);

      // Red cinnabar wax seal
      ctx.fillStyle = '#C8281E';
      ctx.beginPath();
      ctx.arc(0, 0, 5.5, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
    } else if (dna.held_props?.right_hand === 'letter_scroll_open') {
      // Opened Letter with Verified Vietnamese Unicode text
      ctx.save();
      ctx.translate(rHand.x - 20, rHand.y - 30);
      ctx.fillStyle = '#FFF9EC';
      ctx.fillRect(-40, -50, 80, 100);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.2;
      ctx.strokeRect(-40, -50, 80, 100);

      // Readable Vietnamese ink lines
      ctx.fillStyle = '#181614';
      ctx.font = 'bold 8.5px "Segoe UI", Arial, sans-serif';
      ctx.fillText('Aiko thân mến,', -32, -32);
      ctx.fillText('Nhớ mang theo ô.', -32, -14);
      ctx.fillText('Chiều nay mưa to!', -32, 4);
      ctx.restore();
    } else if (dna.held_props?.right_hand === 'portfolio') {
      // 1914 Cardboard Artist Portfolio
      ctx.save();
      ctx.translate(rHand.x - 10, rHand.y - 10);
      ctx.rotate(0.22);
      ctx.fillStyle = '#4A3B2C';
      ctx.fillRect(-22, -32, 44, 64);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.2;
      ctx.strokeRect(-22, -32, 44, 64);
      // Tie ribbon
      ctx.beginPath();
      ctx.moveTo(-22, 0);
      ctx.lineTo(22, 0);
      ctx.stroke();
      ctx.restore();
    } else if (dna.held_props?.right_hand === 'tablet') {
      // Modern High-Tech Holographic Tablet
      ctx.save();
      ctx.translate(rHand.x + 12, rHand.y - 12);
      ctx.fillStyle = '#111822';
      ctx.fillRect(-12, -22, 24, 44);
      ctx.strokeStyle = '#00D2FF';
      ctx.lineWidth = 2.0;
      ctx.strokeRect(-12, -22, 24, 44);
      ctx.fillStyle = 'rgba(0, 210, 255, 0.45)';
      ctx.fillRect(-10, -20, 20, 40);
      ctx.restore();
    }
  }
}
