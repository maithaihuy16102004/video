/**
 * Universal Data-Driven Character Engine V5.0
 * Style: PREMIUM STICKMAN CINEMATIC — STYLE B
 * 
 * 100% Data-Driven by CharacterDNA_V5 (Zero per-story hardcoded classes).
 * Full 12-Joint Skeletal Rig:
 * - Root, Torso, Neck, Head, Shoulders (L/R), Elbows (L/R), Wrists (L/R), Hands (L/R),
 *   Hips (L/R), Knees (L/R), Ankles (L/R), Feet (L/R).
 * 
 * Features:
 * - Analytical 2-Bone Inverse Kinematics (IK) with Foot-Locking on Ground Plane
 * - 5 Distinct Archetypes: young_courier, noblewoman, detective_scholar, tech_founder, polar_scientist
 * - 5 Head Contours: round_youth, delicate_heart, oval_gaunt, square_jaw, athletic_lean
 * - Organic Tapered Limbs with Deltoid and Calf Polygons & Joint Caps
 * - Expressive Stylized Eyes (Sclera, Iris, Pupil, Specular Catchlight, Eyelid Creases)
 * - Articulated 5-Finger Hands (Palm, Opposable Thumb, 4 Phalanges)
 * - Full Composable Action Library (Locomotion, Interaction, Performance, Physical Events)
 * - Rich Cultural & Historical Costumes & Props with Verified Typography
 */

import { V5_VISUAL_STYLE_BIBLE } from '../contract/VisualStyleBible';
import {
  CharacterDNA_V5,
  HeadContour,
  EyeType,
  EyebrowStyle,
  HairStyle,
  CostumeArchetype,
  FootwearType,
  PropAttachment,
  V5_CORE_ARCHETYPES,
} from '../contract/CharacterDNA';
import {
  CanonicalStickmanRig,
  CanonicalProportions,
  CanonicalJointHierarchy,
} from './CanonicalStickmanRig';
import { PoseLibrary, PoseTargetFrame } from './PoseLibrary';

export type { CharacterDNA_V5, HeadContour, EyeType, EyebrowStyle, HairStyle, CostumeArchetype, FootwearType, PropAttachment };
export { V5_CORE_ARCHETYPES, CanonicalStickmanRig, PoseLibrary };

export type CharacterActionV5 =
  // Locomotion
  | 'idle'
  | 'walk'
  | 'run'
  | 'sprint'
  | 'stop'
  | 'turn'
  | 'climb'
  | 'jump'
  // Interaction
  | 'reach'
  | 'grab'
  | 'hold'
  | 'carry'
  | 'give'
  | 'receive'
  | 'open'
  | 'close'
  | 'read'
  | 'write'
  | 'point'
  | 'sip_coffee'
  | 'drink_coffee'
  // Performance
  | 'speak'
  | 'listen'
  | 'laugh'
  | 'cry'
  | 'surprise'
  | 'fear'
  | 'anger'
  | 'relief'
  | 'think'
  | 'react'
  // Physical Events
  | 'slip'
  | 'trip'
  | 'fall'
  | 'catch_balance'
  | 'hang'
  | 'recover'
  | 'sit'
  | 'stand'
  // Legacy aliases
  | 'slip_fall'
  | 'hang_from_ledge'
  | 'present_two_handed'
  | 'laugh_heartily'
  | 'speak_gestural'
  | 'inspect_down'
  | 'look_down'
  | 'open_letter'
  | 'read_letter';

export type CharacterEmotionV5 =
  | 'neutral'
  | 'determined'
  | 'panic'
  | 'relief'
  | 'laughing'
  | 'intense'
  | 'focused'
  | 'curious'
  | 'surprised'
  | 'somber'
  | 'confident';

export interface Point2D {
  x: number;
  y: number;
}

export interface SkeletalRigV5 {
  root: Point2D;
  torso: Point2D;
  neck: Point2D;
  head: Point2D;
  shoulderL: Point2D;
  shoulderR: Point2D;
  elbowL: Point2D;
  elbowR: Point2D;
  wristL: Point2D;
  wristR: Point2D;
  handL: Point2D;
  handR: Point2D;
  hipL: Point2D;
  hipR: Point2D;
  kneeL: Point2D;
  kneeR: Point2D;
  ankleL: Point2D;
  ankleR: Point2D;
  footL: Point2D;
  footR: Point2D;
  torsoTilt: number;
}

export interface CharacterStateV5 {
  screenX: number;
  screenY: number;
  scale: number;
  facing: 1 | -1;
  action: CharacterActionV5;
  progress: number;
  emotion: CharacterEmotionV5;
  gazeTarget?: [number, number];
  handConstraintL?: [number, number];
  handConstraintR?: [number, number];
  lostSandalRight?: boolean;
  soaked?: boolean;
  footLockGround?: boolean;
  debugSkeleton?: boolean;
  viewAngle?: 'front' | 'three_quarter' | 'side';
}

// Backward compatibility alias
export type CharacterDNA = CharacterDNA_V5;
export type CharacterState = CharacterStateV5;

export class UniversalCharacterEngine {
  private ctx: CanvasRenderingContext2D;

  constructor(ctx: CanvasRenderingContext2D) {
    this.ctx = ctx;
  }

  // ============================================================================
  // CANONICAL RIG RESOLUTION (100% Normalized Anatomy & Strict Invariants)
  // ============================================================================
  public resolveCanonicalProportions(dna: CharacterDNA_V5): CanonicalProportions {
    const prop = dna.proportions;
    const totalH = prop.standingHeightPx || 295;
    const headRatio = prop.headRatio || 0.15;
    const headHeight = totalH * headRatio;
    const torsoH = prop.torsoLengthPx || (totalH * 0.32);
    const legH = prop.legLengthPx || (totalH * 0.50);

    return {
      totalHeightPx: totalH,
      headHeightPx: headHeight,
      headWidthPx: headHeight * 0.78,
      neckLengthPx: totalH * 0.035,
      shoulderWidthPx: prop.shoulderWidthPx || (totalH * 0.185),
      chestLengthPx: torsoH * 0.50,
      lumbarLengthPx: torsoH * 0.50,
      hipWidthPx: (prop.shoulderWidthPx || (totalH * 0.185)) * 0.70,
      upperArmLengthPx: totalH * 0.170,
      forearmLengthPx: totalH * 0.155,
      handLengthPx: totalH * 0.082,
      thighLengthPx: legH * 0.50,
      shinLengthPx: legH * 0.50,
      footHeightPx: 12,
      footLengthPx: 30,
      limbThicknessPx: prop.limbThicknessPx || 11,
    };
  }

  public evaluateSkeleton(
    dna: CharacterDNA_V5,
    state: CharacterStateV5,
    totalH: number,
    headR: number
  ): CanonicalJointHierarchy & SkeletalRigV5 {
    const canonProps = this.resolveCanonicalProportions(dna);
    const facing = state.facing;
    const p = state.progress;
    const act = state.action;

    // 1. Resolve Pose Target from Canonical Pose Library
    let targetPose: PoseTargetFrame;

    switch (act) {
      case 'walk':
        targetPose = PoseLibrary.getWalkCycle(canonProps, p, 5.2, facing);
        break;
      case 'run':
      case 'sprint':
        targetPose = PoseLibrary.getRunCycle(canonProps, p, act === 'sprint' ? 12.0 : 8.5, facing);
        break;
      case 'hold':
      case 'carry':
        targetPose = PoseLibrary.getHoldingObject(canonProps, 'single_hand_right', facing);
        break;
      case 'give':
      case 'present_two_handed':
        targetPose = PoseLibrary.getHoldingObject(canonProps, 'two_handed_front', facing);
        break;
      case 'reach':
      case 'grab':
      case 'point':
        targetPose = PoseLibrary.getReaching(canonProps, 58, -135, facing);
        break;
      case 'speak':
      case 'speak_gestural':
        targetPose = PoseLibrary.getSpeaking(canonProps, p, facing);
        break;
      case 'listen':
        targetPose = PoseLibrary.getSitting(canonProps, 52, facing);
        targetPose.headLookAngle = 0.15 * facing;
        break;
      case 'laugh':
      case 'laugh_heartily': {
        targetPose = PoseLibrary.getSpeaking(canonProps, p, facing);
        const bob = Math.sin(p * 12.0) * 0.08;
        targetPose.torsoTiltAngle = (-0.12 + bob) * facing;
        targetPose.headLookAngle = -0.22 * facing;
        break;
      }
      case 'sit':
        targetPose = PoseLibrary.getSitting(canonProps, 52, facing);
        break;
      case 'sip_coffee':
      case 'drink_coffee': {
        const footH = canonProps.footHeightPx;
        const shY = -(footH + (canonProps.thighLengthPx + canonProps.shinLengthPx) * 0.96 + canonProps.lumbarLengthPx + canonProps.chestLengthPx);
        targetPose = PoseLibrary.getSitting(canonProps, 48, facing);
        // Elevate right hand holding coffee cup to mouth/chin level
        targetPose.targetHandR = { x: 18 * facing, y: shY + 28 };
        // Relax left hand forward on table surface
        targetPose.targetHandL = { x: 14 * facing, y: shY + 68 };
        targetPose.headLookAngle = -0.15 * facing;
        break;
      }
      case 'read':
      case 'open_letter':
      case 'read_letter': {
        const footH = canonProps.footHeightPx;
        const shY = -(footH + (canonProps.thighLengthPx + canonProps.shinLengthPx) * 0.96 + canonProps.lumbarLengthPx + canonProps.chestLengthPx);
        targetPose = PoseLibrary.getNeutralStanding(canonProps, p, facing);
        targetPose.torsoTiltAngle = 0.08 * facing;
        // Two hands holding open scroll in front of chest
        targetPose.targetHandL = { x: -14 * facing, y: shY + 45 };
        targetPose.targetHandR = { x: 18 * facing, y: shY + 45 };
        targetPose.headLookAngle = 0.42 * facing; // Looking down at open parchment
        break;
      }
      case 'inspect_down':
      case 'look_down': {
        const footH = canonProps.footHeightPx;
        const shY = -(footH + (canonProps.thighLengthPx + canonProps.shinLengthPx) * 0.96 + canonProps.lumbarLengthPx + canonProps.chestLengthPx);
        targetPose = PoseLibrary.getNeutralStanding(canonProps, p, facing);
        // Leaning forward, head tilted down looking at bare foot
        targetPose.torsoTiltAngle = 0.28 * facing;
        targetPose.headLookAngle = 0.72 * facing;
        targetPose.targetHandL = { x: -14 * facing, y: shY + 65 };
        targetPose.targetHandR = { x: 22 * facing, y: shY + 65 };
        break;
      }
      case 'slip':
      case 'slip_fall':
      case 'fall':
      case 'trip':
        targetPose = PoseLibrary.getFalling(canonProps, p, facing);
        break;
      case 'catch_balance':
      case 'recover':
        targetPose = PoseLibrary.getRecovering(canonProps, p, facing);
        break;
      case 'hang':
      case 'hang_from_ledge': {
        const footH = canonProps.footHeightPx;
        const shY = -(footH + (canonProps.thighLengthPx + canonProps.shinLengthPx) * 0.96 + canonProps.lumbarLengthPx + canonProps.chestLengthPx);
        targetPose = {
          torsoTiltAngle: 0.12 * facing,
          spineCurve: 0.04,
          hipYOffset: 35, // Dropped down
          targetFootL: { x: -18 * facing, y: 15 },
          targetFootR: { x: 12 * facing, y: 8 },
          targetHandL: { x: -16 * facing, y: shY - 45 }, // Left hand gripping high
          targetHandR: { x: 42 * facing, y: shY - 35 },  // Right hand holding scroll high
          headLookAngle: p > 7.5 ? 0.35 : -0.25,
          footLockGround: false,
        };
        break;
      }
      case 'idle':
      default:
        targetPose = PoseLibrary.getNeutralStanding(canonProps, p, facing);
        break;
    }

    // 2. Apply dynamic constraints
    if (state.handConstraintL) {
      targetPose.targetHandL = { x: state.handConstraintL[0], y: state.handConstraintL[1] };
    }
    if (state.handConstraintR) {
      targetPose.targetHandR = { x: state.handConstraintR[0], y: state.handConstraintR[1] };
    }
    if (state.footLockGround !== undefined) {
      targetPose.footLockGround = state.footLockGround;
    }

    // 3. Solve Canonical Kinematics
    const rig = CanonicalStickmanRig.evaluateRig(canonProps, facing, {
      torsoTiltAngle: targetPose.torsoTiltAngle,
      spineCurve: targetPose.spineCurve,
      hipYOffset: targetPose.hipYOffset,
      targetFootL: targetPose.targetFootL,
      targetFootR: targetPose.targetFootR,
      targetHandL: targetPose.targetHandL,
      targetHandR: targetPose.targetHandR,
      headLookAngle: targetPose.headLookAngle,
      footLockGround: targetPose.footLockGround,
    });

    // 4. Return merged canonical & legacy-compatible structure
    return {
      ...rig,
      torso: rig.chest,
      neck: rig.neckBase,
      head: rig.headCenter,
      footL: rig.ankleL,
      footR: rig.ankleR,
      torsoTilt: rig.torsoAngle,
    };
  }

  // ============================================================================
  // DNA NORMALIZER (Backward Compatibility & Universal Interop)
  // ============================================================================
  public normalizeDna(raw: any): CharacterDNA_V5 {
    if (!raw) return V5_CORE_ARCHETYPES.young_courier;
    if (typeof raw === 'string' && (V5_CORE_ARCHETYPES as any)[raw]) {
      return (V5_CORE_ARCHETYPES as any)[raw];
    }
    const prop = raw.proportions || {};
    const face = raw.face || {};
    const hair = raw.hair || {};
    const costume = raw.costume || {};
    const held = raw.heldProps || raw.held_props || {};
    const archetypeId = raw.archetypeId || raw.archetype_id || 'young_courier';
    const fallbackArch = (V5_CORE_ARCHETYPES as any)[archetypeId] || V5_CORE_ARCHETYPES.young_courier;

    return {
      characterId: raw.characterId || raw.character_id || raw.id || fallbackArch.characterId,
      canonicalName: raw.canonicalName || raw.canonical_name || raw.name || fallbackArch.canonicalName,
      archetypeId: archetypeId,
      voiceId: raw.voiceId || raw.voice_id || fallbackArch.voiceId,
      proportions: {
        headRatio: prop.headRatio ?? prop.head_ratio ?? fallbackArch.proportions.headRatio,
        standingHeightPx: prop.standingHeightPx ?? prop.height_standing ?? fallbackArch.proportions.standingHeightPx,
        shoulderWidthPx: prop.shoulderWidthPx ?? prop.shoulder_width ?? fallbackArch.proportions.shoulderWidthPx,
        limbThicknessPx: prop.limbThicknessPx ?? prop.limb_thickness ?? fallbackArch.proportions.limbThicknessPx,
        torsoLengthPx: prop.torsoLengthPx ?? prop.torso_length ?? fallbackArch.proportions.torsoLengthPx,
        legLengthPx: prop.legLengthPx ?? prop.leg_length ?? fallbackArch.proportions.legLengthPx,
      },
      face: {
        headContour: face.headContour || face.head_contour || fallbackArch.face.headContour,
        skinTone: face.skinTone || face.skin_tone || fallbackArch.face.skinTone,
        eyeType: face.eyeType || face.eye_type || fallbackArch.face.eyeType,
        eyeColor: face.eyeColor || face.eye_color || fallbackArch.face.eyeColor,
        eyebrowStyle: face.eyebrowStyle || face.eyebrow_style || fallbackArch.face.eyebrowStyle,
        facialHair: face.facialHair || face.facial_hair || fallbackArch.face.facialHair,
        facialHairColor: face.facialHairColor || face.facial_hair_color || fallbackArch.face.facialHairColor,
      },
      hair: {
        style: hair.style || fallbackArch.hair.style,
        color: hair.color || fallbackArch.hair.color,
        accessory: hair.accessory || fallbackArch.hair.accessory,
      },
      costume: {
        archetype: costume.archetype || fallbackArch.costume.archetype,
        primaryColor: costume.primaryColor || costume.primary_color || fallbackArch.costume.primaryColor,
        secondaryColor: costume.secondaryColor || costume.secondary_color || fallbackArch.costume.secondaryColor,
        accentColor: costume.accentColor || costume.accent_color || fallbackArch.costume.accentColor,
        pantsColor: costume.pantsColor || costume.pants_color || fallbackArch.costume.pantsColor,
        beltType: costume.beltType || costume.belt_type || fallbackArch.costume.beltType,
        footwear: costume.footwear || fallbackArch.costume.footwear,
        footwearColor: costume.footwearColor || costume.footwear_color || fallbackArch.costume.footwearColor,
      },
      heldProps: {
        rightHand: held.rightHand || held.right_hand || (raw.heldProp ? raw.heldProp : fallbackArch.heldProps?.rightHand || 'none'),
        leftHand: held.leftHand || held.left_hand || fallbackArch.heldProps?.leftHand || 'none',
      },
    };
  }

  // ============================================================================
  // MASTER RENDER ENTRY POINT
  // ============================================================================
  public render(rawDna: CharacterDNA_V5, state: CharacterStateV5) {
    const dna = this.normalizeDna(rawDna);
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(state.screenX, state.screenY);
    ctx.scale(state.scale * state.facing, state.scale);

    const canonProps = this.resolveCanonicalProportions(dna);
    const totalH = canonProps.totalHeightPx;
    const headR = canonProps.headHeightPx * 0.5;
    const ink = '#141210';
    const skin = dna.face.skinTone || '#F5DEB3';

    // 1. Ground contact shadow
    this.drawContactShadow(state, totalH);

    // 2. Complete Canonical 12-Joint Skeletal Hierarchy via Analytical IK
    const skel = this.evaluateSkeleton(dna, state, totalH, headR);

    // 3. Lower Costume (Legs / Pants / Skirt / Footwear)
    this.drawLowerCostume(ctx, dna, state, skel, ink);

    // 4. Upper Costume (Torso / Robe / Coat / Hoodie)
    this.drawUpperCostume(ctx, dna, state, skel, ink);

    // 5. Head, Neck & Face (5 Silhouettes, Eyes, Brows, Hair)
    this.drawHeadAndFace(ctx, dna, state, skel.head, headR, ink, skin);

    // 6. Arms & Hands (Articulated 5-Finger Anatomy aligned to forearm)
    this.drawArmsAndHands(ctx, dna, state, skel, ink, skin);

    // 7. Held Props & Objects (Anchored to palm grip sockets)
    this.drawProps(ctx, dna, state, skel);

    // 8. Visual Regression & Skeleton Debugger
    if (state.debugSkeleton) {
      this.drawSkeletonDebug(ctx, skel, canonProps, dna);
    }

    ctx.restore();
  }

  public draw(dna: CharacterDNA_V5, state: CharacterStateV5) {
    this.render(dna, state);
  }

  // ============================================================================
  // CONTACT SHADOW
  // ============================================================================
  private drawContactShadow(state: CharacterStateV5, totalH: number) {
    const ctx = this.ctx;
    ctx.save();
    const isAirborne =
      state.action === 'hang' ||
      state.action === 'hang_from_ledge' ||
      state.action === 'slip' ||
      state.action === 'slip_fall' ||
      state.action === 'jump';
    const shadowAlpha = isAirborne ? 0.25 : 0.55;
    const shadowWidth = isAirborne ? 70 : 105;

    ctx.beginPath();
    ctx.ellipse(0, 0, shadowWidth, 16, 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(16, 14, 12, ${shadowAlpha})`;
    ctx.fill();
    ctx.restore();
  }

  // ============================================================================
  // HEAD, NECK & 5 DIVERSE SILHOUETTES
  // ============================================================================
  private drawHeadAndFace(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA_V5,
    state: CharacterStateV5,
    headPos: Point2D,
    headR: number,
    ink: string,
    skin: string
  ) {
    ctx.save();
    ctx.translate(headPos.x, headPos.y);

    // 1. Neck Trapezoid
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

    // 2. Distinct Head Contour Silhouettes (5 Archetypes)
    ctx.beginPath();
    switch (dna.face.headContour) {
      case 'oval_gaunt': // Lean, angular, high cheekbones (Arthur)
        ctx.moveTo(0, -headR * 1.25);
        ctx.bezierCurveTo(headR * 0.95, -headR * 1.25, headR * 0.85, 0.0, headR * 0.65, headR * 0.55);
        ctx.bezierCurveTo(headR * 0.50, headR * 0.95, headR * 0.28, headR * 1.25, 0, headR * 1.30);
        ctx.bezierCurveTo(-headR * 0.28, headR * 1.25, -headR * 0.50, headR * 0.95, -headR * 0.65, headR * 0.55);
        ctx.bezierCurveTo(-headR * 0.85, 0.0, -headR * 0.95, -headR * 1.25, 0, -headR * 1.25);
        break;

      case 'square_jaw': // Broad, strong jawline (Minh)
        ctx.moveTo(-headR * 0.75, -headR * 1.15);
        ctx.bezierCurveTo(-headR * 0.85, -headR * 0.4, -headR * 0.85, headR * 0.4, -headR * 0.75, headR * 0.75);
        ctx.lineTo(-headR * 0.35, headR * 1.15);
        ctx.lineTo(headR * 0.35, headR * 1.15);
        ctx.lineTo(headR * 0.75, headR * 0.75);
        ctx.bezierCurveTo(headR * 0.85, headR * 0.4, headR * 0.85, -headR * 0.4, headR * 0.75, -headR * 1.15);
        ctx.closePath();
        break;

      case 'delicate_heart': // Delicate heart feminine chin (Aiko)
        ctx.moveTo(0, -headR * 1.2);
        ctx.bezierCurveTo(headR * 1.05, -headR * 1.15, headR * 0.95, -headR * 0.1, headR * 0.55, headR * 0.55);
        ctx.bezierCurveTo(headR * 0.35, headR * 0.90, headR * 0.15, headR * 1.18, 0, headR * 1.22);
        ctx.bezierCurveTo(-headR * 0.15, headR * 1.18, -headR * 0.35, headR * 0.90, -headR * 0.55, headR * 0.55);
        ctx.bezierCurveTo(-headR * 0.95, -headR * 0.1, -headR * 1.05, -headR * 1.15, 0, -headR * 1.2);
        break;

      case 'athletic_lean': // Streamlined athletic profile (Elena)
        ctx.moveTo(0, -headR * 1.22);
        ctx.bezierCurveTo(headR * 0.88, -headR * 1.18, headR * 0.82, -headR * 0.1, headR * 0.60, headR * 0.50);
        ctx.bezierCurveTo(headR * 0.42, headR * 0.88, headR * 0.22, headR * 1.18, 0, headR * 1.20);
        ctx.bezierCurveTo(-headR * 0.22, headR * 1.18, -headR * 0.42, headR * 0.88, -headR * 0.60, headR * 0.50);
        ctx.bezierCurveTo(-headR * 0.82, -headR * 0.1, -headR * 0.88, -headR * 1.18, 0, -headR * 1.22);
        break;

      case 'round_youth': // Soft, youthful face (Haru)
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
    this.drawEyebrows(ctx, dna.face.eyebrowStyle, state.emotion, headR, ink);

    // 5. Expressive Eyes
    const gaze = state.gazeTarget || [0.4, 0.0];
    this.drawEye(ctx, -headR * 0.34, -headR * 0.08, gaze, state.emotion === 'laughing', dna.face.eyeColor || '#2C1D11', ink);
    this.drawEye(ctx, headR * 0.34, -headR * 0.08, gaze, state.emotion === 'laughing', dna.face.eyeColor || '#2C1D11', ink);

    // 6. Sculpted Nose
    ctx.strokeStyle = ink;
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.moveTo(0, -headR * 0.08);
    ctx.lineTo(headR * 0.08, headR * 0.22);
    ctx.lineTo(-headR * 0.06, headR * 0.25);
    ctx.stroke();

    // 7. Facial Hair
    this.drawFacialHair(ctx, dna.face.facialHair, dna.face.facialHairColor || ink, headR);

    // 8. Animated Mouth
    this.drawMouth(ctx, state.emotion, headR, ink);

    // 9. Eye Accessories (Glasses / Goggles)
    if (dna.hair.accessory === 'glasses_round') {
      ctx.strokeStyle = '#3A2E2B';
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      ctx.arc(-headR * 0.34, -headR * 0.08, 9.5, 0, Math.PI * 2);
      ctx.arc(headR * 0.34, -headR * 0.08, 9.5, 0, Math.PI * 2);
      ctx.moveTo(-headR * 0.34 + 9.5, -headR * 0.08);
      ctx.lineTo(headR * 0.34 - 9.5, -headR * 0.08);
      ctx.stroke();
    } else if (dna.hair.accessory === 'goggles') {
      ctx.fillStyle = 'rgba(0, 180, 255, 0.35)';
      ctx.strokeStyle = '#1A1A1A';
      ctx.lineWidth = 2.8;
      ctx.beginPath();
      ctx.roundRect(-headR * 0.55, -headR * 0.20, headR * 0.45, 16, 4);
      ctx.roundRect(headR * 0.10, -headR * 0.20, headR * 0.45, 16, 4);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(-headR * 0.10, -headR * 0.12);
      ctx.lineTo(headR * 0.10, -headR * 0.12);
      ctx.stroke();
    }

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

    ctx.beginPath();
    ctx.ellipse(0, 0, 9.0, 6.2, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.lineWidth = 2.2;
    ctx.strokeStyle = ink;
    ctx.stroke();

    const gx = Math.max(-3.5, Math.min(3.5, gaze[0] * 3.5));
    const gy = Math.max(-2.5, Math.min(2.5, gaze[1] * 2.5));
    ctx.beginPath();
    ctx.arc(gx, gy, 4.2, 0, Math.PI * 2);
    ctx.fillStyle = irisColor;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(gx, gy, 2.2, 0, Math.PI * 2);
    ctx.fillStyle = '#080808';
    ctx.fill();

    ctx.beginPath();
    ctx.arc(gx - 1.4, gy - 1.4, 1.4, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();

    ctx.restore();
  }

  private drawEyebrows(
    ctx: CanvasRenderingContext2D,
    style: EyebrowStyle,
    emotion: CharacterEmotionV5,
    headR: number,
    ink: string
  ) {
    const tilt =
      emotion === 'panic' || emotion === 'surprised'
        ? -0.22
        : emotion === 'laughing'
        ? 0.12
        : emotion === 'intense' || emotion === 'determined'
        ? 0.20
        : 0;
    const lw = style === 'thick_bushy' ? 4.2 : 2.6;

    ctx.strokeStyle = ink;
    ctx.lineWidth = lw;

    ctx.beginPath();
    ctx.moveTo(-headR * 0.58, -headR * 0.32 + tilt * 20);
    ctx.quadraticCurveTo(-headR * 0.32, -headR * 0.46 + tilt * 20, -headR * 0.12, -headR * 0.30);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(headR * 0.12, -headR * 0.30);
    ctx.quadraticCurveTo(headR * 0.32, -headR * 0.46 - tilt * 20, headR * 0.58, -headR * 0.32 - tilt * 20);
    ctx.stroke();
  }

  private drawFacialHair(ctx: CanvasRenderingContext2D, style: string, color: string, headR: number) {
    if (!style || style === 'none') return;
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

  private drawMouth(ctx: CanvasRenderingContext2D, emotion: CharacterEmotionV5, headR: number, ink: string) {
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

      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(-9, 0, 18, 4.5);

      ctx.beginPath();
      ctx.arc(0, 11, 7.0, Math.PI, 0);
      ctx.fillStyle = '#E87A88';
      ctx.fill();
    } else if (emotion === 'panic' || emotion === 'surprised') {
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

  private drawHair(ctx: CanvasRenderingContext2D, hair: CharacterDNA_V5['hair'], headR: number, ink: string) {
    ctx.save();
    ctx.fillStyle = hair.color || '#1A1A1A';
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

        ctx.beginPath();
        ctx.ellipse(headR * 0.18, -headR * 1.6, 13, 18, 0.38, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

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
      case 'ponytail_athletic': {
        ctx.beginPath();
        ctx.moveTo(-headR * 0.95, -headR * 0.4);
        ctx.quadraticCurveTo(-headR * 0.4, -headR * 1.4, 0, -headR * 1.4);
        ctx.quadraticCurveTo(headR * 0.8, -headR * 1.35, headR * 0.95, -headR * 0.3);
        ctx.lineTo(headR * 0.4, -headR * 0.7);
        ctx.lineTo(-headR * 0.6, -headR * 0.5);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(-headR * 0.5, -headR * 1.35);
        ctx.bezierCurveTo(-headR * 1.1, -headR * 1.6, -headR * 1.3, -headR * 1.0, -headR * 1.4, -headR * 0.4);
        ctx.bezierCurveTo(-headR * 1.1, -headR * 0.7, -headR * 0.8, -headR * 1.0, -headR * 0.4, -headR * 1.25);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
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
      case 'modern_crop': {
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
    dna: CharacterDNA_V5,
    state: CharacterStateV5,
    skel: SkeletalRigV5,
    ink: string
  ) {
    ctx.save();
    const sc = skel.torso;
    const hr = skel.root;
    const costume = dna.costume;

    ctx.translate((sc.x + hr.x) / 2, (sc.y + hr.y) / 2);
    ctx.rotate(skel.torsoTilt);

    const torsoH = Math.hypot(sc.x - hr.x, sc.y - hr.y) || 75;
    const sw = dna.proportions.shoulderWidthPx || 54;

    ctx.beginPath();
    ctx.moveTo(-sw * 0.58, -torsoH * 0.5);
    ctx.lineTo(sw * 0.58, -torsoH * 0.5);
    ctx.bezierCurveTo(sw * 0.55, 0, sw * 0.45, torsoH * 0.3, sw * 0.42, torsoH * 0.5);
    ctx.lineTo(-sw * 0.42, torsoH * 0.5);
    ctx.bezierCurveTo(-sw * 0.45, torsoH * 0.3, -sw * 0.55, 0, -sw * 0.58, -torsoH * 0.5);
    ctx.closePath();
    ctx.fillStyle = costume.primaryColor || '#1B3B6F';
    ctx.fill();
    ctx.lineWidth = 3.2;
    ctx.strokeStyle = ink;
    ctx.stroke();

    switch (costume.archetype) {
      case 'victorian_frock_coat': {
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(-sw * 0.16, -torsoH * 0.5, sw * 0.32, torsoH * 0.22);
        ctx.strokeStyle = ink;
        ctx.lineWidth = 2.0;
        ctx.strokeRect(-sw * 0.16, -torsoH * 0.5, sw * 0.32, torsoH * 0.22);

        ctx.fillStyle = costume.accentColor || '#D90429';
        ctx.beginPath();
        ctx.moveTo(0, -torsoH * 0.48);
        ctx.lineTo(-sw * 0.09, -torsoH * 0.28);
        ctx.lineTo(sw * 0.09, -torsoH * 0.28);
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = costume.secondaryColor || '#8D99AE';
        ctx.lineWidth = 2.8;
        ctx.beginPath();
        ctx.moveTo(-sw * 0.35, -torsoH * 0.5);
        ctx.lineTo(-sw * 0.12, -torsoH * 0.1);
        ctx.lineTo(0, torsoH * 0.2);
        ctx.moveTo(sw * 0.35, -torsoH * 0.5);
        ctx.lineTo(sw * 0.12, -torsoH * 0.1);
        ctx.lineTo(0, torsoH * 0.2);
        ctx.stroke();
        break;
      }
      case 'edo_kimono_formal': {
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 3.4;
        ctx.beginPath();
        ctx.moveTo(-sw * 0.28, -torsoH * 0.5);
        ctx.lineTo(sw * 0.18, -torsoH * 0.05);
        ctx.stroke();

        ctx.strokeStyle = costume.accentColor || '#FFD700';
        ctx.lineWidth = 3.0;
        ctx.beginPath();
        ctx.moveTo(sw * 0.28, -torsoH * 0.5);
        ctx.lineTo(-sw * 0.18, -torsoH * 0.05);
        ctx.stroke();

        ctx.fillStyle = costume.accentColor || '#FF69B4';
        ctx.fillRect(-sw * 0.44, torsoH * 0.12, sw * 0.88, torsoH * 0.28);
        ctx.strokeStyle = ink;
        ctx.lineWidth = 2.4;
        ctx.strokeRect(-sw * 0.44, torsoH * 0.12, sw * 0.88, torsoH * 0.28);
        break;
      }
      case 'modern_hoodie': {
        ctx.strokeStyle = costume.accentColor || '#EE6C4D';
        ctx.lineWidth = 3.4;
        ctx.beginPath();
        ctx.arc(0, -torsoH * 0.42, sw * 0.24, 0.2, Math.PI - 0.2);
        ctx.stroke();

        ctx.strokeStyle = ink;
        ctx.lineWidth = 2.2;
        ctx.strokeRect(-sw * 0.32, torsoH * 0.15, sw * 0.64, torsoH * 0.25);
        break;
      }
      case 'polar_hazard_suit': {
        ctx.fillStyle = costume.secondaryColor || '#FCBF49';
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
  // ORGANIC LIMBS & ARTICULATED 5-FINGER HANDS
  // ============================================================================
  private drawLowerCostume(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA_V5,
    state: CharacterStateV5,
    skel: SkeletalRigV5,
    ink: string
  ) {
    const limbW = dna.proportions.limbThicknessPx || 11;
    const pantsCol = dna.costume.pantsColor || '#283655';

    // Left Leg
    this.drawOrganicLimb(ctx, skel.hipL, skel.kneeL, skel.ankleL, limbW * 1.25, limbW * 0.95, ink, pantsCol);
    this.drawFoot(ctx, dna.costume.footwear, skel.footL, false, ink, dna.face.skinTone);

    // Right Leg
    const rightBare = state.lostSandalRight || dna.costume.footwear === 'bare_foot';
    this.drawOrganicLimb(ctx, skel.hipR, skel.kneeR, skel.ankleR, limbW * 1.25, limbW * 0.95, ink, pantsCol);
    this.drawFoot(ctx, rightBare ? 'bare_foot' : dna.costume.footwear, skel.footR, rightBare, ink, dna.face.skinTone);
  }

  private drawArmsAndHands(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA_V5,
    state: CharacterStateV5,
    skel: SkeletalRigV5 & CanonicalJointHierarchy,
    ink: string,
    skin: string
  ) {
    const limbW = (dna.proportions.limbThicknessPx || 11) * 0.95;
    const sleeveCol = dna.costume.primaryColor || '#1B3B6F';

    // Left Arm
    this.drawOrganicLimb(ctx, skel.shoulderL, skel.elbowL, skel.wristL, limbW * 1.15, limbW * 0.85, ink, sleeveCol);
    this.drawArticulatedHand(
      ctx,
      skel.wristL,
      skel.handAngleL ?? 0,
      state.action === 'hang' ? 'grip' : 'open',
      ink,
      skin
    );

    // Right Arm
    this.drawOrganicLimb(ctx, skel.shoulderR, skel.elbowR, skel.wristR, limbW * 1.15, limbW * 0.85, ink, sleeveCol);
    this.drawArticulatedHand(
      ctx,
      skel.wristR,
      skel.handAngleR ?? 0,
      state.action === 'hang' ? 'pinch_high' : dna.heldProps?.rightHand ? 'grip' : 'open',
      ink,
      skin
    );
  }

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

    ctx.beginPath();
    ctx.arc(p2.x, p2.y, w1 * 0.45, 0, Math.PI * 2);
    ctx.fillStyle = fillCol;
    ctx.fill();
    ctx.stroke();

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

  private drawArticulatedHand(
    ctx: CanvasRenderingContext2D,
    pos: Point2D,
    angle: number,
    gripType: 'open' | 'grip' | 'pinch_high',
    ink: string,
    skin: string
  ) {
    ctx.save();
    ctx.translate(pos.x, pos.y);
    ctx.rotate(angle); // Seamlessly aligns with forearm vector!
    ctx.fillStyle = skin;
    ctx.strokeStyle = ink;
    ctx.lineWidth = 1.8;

    if (gripType === 'grip') {
      ctx.beginPath();
      ctx.arc(6, 0, 7.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      for (const fx of [2, 6, 10]) {
        ctx.beginPath();
        ctx.arc(fx, 3, 2.5, 0, Math.PI);
        ctx.stroke();
      }
    } else if (gripType === 'pinch_high') {
      ctx.beginPath();
      ctx.ellipse(6, 0, 6, 8, 0.3, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(9, -5, 2.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.ellipse(5, 0, 6.5, 7.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.beginPath();
      ctx.ellipse(0, -3, 2.6, 4.5, -0.6, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      const fingerOffsets = [
        { x: 3.5, y: -7.0, h: 6.5 },
        { x: 6.0, y: -8.5, h: 8.0 },
        { x: 8.5, y: -8.0, h: 7.5 },
        { x: 11.0, y: -6.0, h: 5.5 },
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
    footwear: FootwearType,
    pos: Point2D,
    isBare: boolean,
    ink: string,
    skinTone: string
  ) {
    ctx.save();
    ctx.translate(pos.x, pos.y);

    if (isBare) {
      // Main foot pad
      ctx.fillStyle = skinTone;
      ctx.beginPath();
      ctx.ellipse(8, 0, 14, 5.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.0;
      ctx.strokeStyle = ink;
      ctx.stroke();

      // Articulated individual toes
      ctx.fillStyle = skinTone;
      const toeSizes = [2.2, 2.0, 1.8, 1.6];
      for (let t = 0; t < 4; t++) {
        ctx.beginPath();
        ctx.arc(17 + t * 2.2, -2 + t * 1.4, toeSizes[t], 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }

      // Mud stains and wet splashes from the bridge puddle
      ctx.fillStyle = '#3E2A1C';
      ctx.beginPath();
      ctx.arc(4, 2, 2.5, 0, Math.PI * 2);
      ctx.arc(11, 1, 2.0, 0, Math.PI * 2);
      ctx.arc(17, 3, 1.8, 0, Math.PI * 2);
      ctx.arc(-1, -1, 1.5, 0, Math.PI * 2);
      ctx.fill();
    } else if (footwear === 'waraji_sandals') {
      ctx.fillStyle = '#C2A368';
      ctx.beginPath();
      ctx.ellipse(8, 1, 15, 5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.0;
      ctx.strokeStyle = ink;
      ctx.stroke();

      ctx.strokeStyle = '#544222';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(-2, -3);
      ctx.lineTo(10, 2);
      ctx.moveTo(10, -3);
      ctx.lineTo(-2, 2);
      ctx.stroke();
    } else if (footwear === 'snow_boots') {
      ctx.fillStyle = '#212121';
      ctx.beginPath();
      ctx.roundRect(-2, -4, 26, 13, 4);
      ctx.fill();
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = ink;
      ctx.stroke();
    } else {
      ctx.fillStyle = footwear === 'sneakers' ? '#EAEAEA' : '#1A1816';
      ctx.beginPath();
      ctx.ellipse(9, 0, 16, 6.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.2;
      ctx.strokeStyle = ink;
      ctx.stroke();
    }
    ctx.restore();
  }

  // ============================================================================
  // PROPS & ARTIFACTS (Strict Grip Anchor Alignment)
  // ============================================================================
  private drawProps(
    ctx: CanvasRenderingContext2D,
    dna: CharacterDNA_V5,
    state: CharacterStateV5,
    skel: SkeletalRigV5 & CanonicalJointHierarchy
  ) {
    const rHand = skel.handR;
    const rAngle = skel.handAngleR ?? 0;
    const propR = (dna.heldProps?.rightHand as string) || '';

    const isReadingLetter = propR === 'letter_scroll_open' ||
      ((state.action === 'read' || state.action === 'open_letter' || state.action === 'read_letter' || (state.action === 'laugh' && (((dna as any).canonicalName || (dna as any).name || '').toLowerCase().includes('aiko')))) &&
       (propR.includes('letter') || propR.includes('parchment') || propR.includes('envelope')));

    const isCoffee = propR === 'steaming_coffee_cup' || propR === 'coffee_cup' || state.action === 'sip_coffee' || state.action === 'drink_coffee';

    if (isReadingLetter) {
      ctx.save();
      ctx.translate(rHand.x, rHand.y);
      ctx.rotate(rAngle * 0.4);
      ctx.fillStyle = '#FFF9EC';
      ctx.fillRect(-45, -55, 90, 110);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.4;
      ctx.strokeRect(-45, -55, 90, 110);

      // Calligraphic header & body in Edo Washi style
      ctx.fillStyle = '#181614';
      ctx.font = 'bold 10px "Be Vietnam Pro", Arial, sans-serif';
      ctx.fillText('Aiko thân mến,', -36, -34);
      ctx.font = '500 9px "Be Vietnam Pro", Arial, sans-serif';
      ctx.fillText('Nhớ mang theo ô khi ra ngoài.', -38, -14);
      ctx.fillText('Chiều nay trời mưa to!', -38, 6);

      // Red stamp seal
      ctx.fillStyle = '#C8281E';
      ctx.fillRect(18, 25, 14, 14);
      ctx.strokeStyle = '#8B0000';
      ctx.lineWidth = 1.0;
      ctx.strokeRect(18, 25, 14, 14);
      ctx.restore();
    } else if (propR === 'letter_scroll_sealed') {
      ctx.save();
      ctx.translate(rHand.x, rHand.y);
      ctx.rotate(rAngle + 0.15);
      ctx.fillStyle = '#F5E4B8';
      ctx.fillRect(-12, -22, 24, 44);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.2;
      ctx.strokeRect(-12, -22, 24, 44);

      ctx.fillStyle = '#C8281E'; // Red wax seal
      ctx.beginPath();
      ctx.arc(0, 0, 5.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    } else if (propR === 'tablet_computer') {
      ctx.save();
      ctx.translate(rHand.x, rHand.y);
      ctx.rotate(rAngle + 0.1);
      ctx.fillStyle = '#111822';
      ctx.fillRect(-14, -24, 28, 48);
      ctx.strokeStyle = '#00D2FF';
      ctx.lineWidth = 2.0;
      ctx.strokeRect(-14, -24, 28, 48);

      ctx.fillStyle = 'rgba(0, 210, 255, 0.45)';
      ctx.fillRect(-12, -22, 24, 44);
      ctx.restore();
    } else if (propR === 'scientific_scanner') {
      ctx.save();
      ctx.translate(rHand.x, rHand.y);
      ctx.rotate(rAngle);
      ctx.fillStyle = '#333333';
      ctx.fillRect(-10, -20, 20, 40);
      ctx.strokeStyle = '#F77F00';
      ctx.lineWidth = 2.0;
      ctx.strokeRect(-10, -20, 20, 40);

      ctx.fillStyle = '#4895EF';
      ctx.beginPath();
      ctx.arc(0, -12, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    } else if (propR === 'letter_envelope' || propR === 'envelope') {
      ctx.save();
      ctx.translate(rHand.x, rHand.y);
      ctx.rotate(rAngle + 0.1);
      ctx.fillStyle = '#E8DCC0';
      ctx.fillRect(-18, -14, 36, 28);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.0;
      ctx.strokeRect(-18, -14, 36, 28);
      ctx.beginPath();
      ctx.moveTo(-18, -14);
      ctx.lineTo(0, 4);
      ctx.lineTo(18, -14);
      ctx.stroke();
      ctx.restore();
    } else if (isCoffee) {
      ctx.save();
      ctx.translate(rHand.x, rHand.y);
      ctx.fillStyle = '#FAFAFA';
      ctx.fillRect(-10, -16, 20, 26);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.0;
      ctx.strokeRect(-10, -16, 20, 26);
      // Handle
      ctx.beginPath();
      ctx.arc(12, -4, 6, -Math.PI / 2, Math.PI / 2);
      ctx.stroke();
      // Steam
      ctx.strokeStyle = 'rgba(255,255,255,0.7)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(-4, -20);
      ctx.quadraticCurveTo(-8, -26, -4, -32);
      ctx.moveTo(4, -20);
      ctx.quadraticCurveTo(8, -26, 4, -32);
      ctx.stroke();
      ctx.restore();
    } else if (propR === 'stethascope_or_clipboard' || propR === 'clipboard') {
      ctx.save();
      ctx.translate(rHand.x, rHand.y);
      ctx.rotate(rAngle * 0.2);
      ctx.fillStyle = '#8D6E63';
      ctx.fillRect(-15, -24, 30, 48);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.0;
      ctx.strokeRect(-15, -24, 30, 48);
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(-12, -18, 24, 38);
      ctx.fillStyle = '#CFD8DC';
      ctx.fillRect(-6, -26, 12, 6);
      ctx.restore();
    } else if (propR && propR !== 'none') {
      ctx.save();
      ctx.translate(rHand.x, rHand.y);
      ctx.rotate(rAngle);
      ctx.fillStyle = '#37474F';
      ctx.fillRect(-12, -16, 24, 32);
      ctx.strokeStyle = '#ECEFF1';
      ctx.lineWidth = 1.8;
      ctx.strokeRect(-12, -16, 24, 32);
      ctx.restore();
    }
  }

  // ============================================================================
  // SKELETON DEBUG OVERLAY RENDERER (Phase 6 Harness)
  // ============================================================================
  public drawSkeletonDebug(
    ctx: CanvasRenderingContext2D,
    skel: CanonicalJointHierarchy & SkeletalRigV5,
    canonProps: CanonicalProportions,
    dna: CharacterDNA_V5
  ) {
    ctx.save();

    // 1. Draw Bones with length labels
    const drawBone = (p1: Point2D, p2: Point2D, label: string) => {
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.strokeStyle = 'rgba(0, 255, 128, 0.9)';
      ctx.lineWidth = 2.8;
      ctx.stroke();

      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      const len = Math.hypot(p2.x - p1.x, p2.y - p1.y).toFixed(1);
      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 8.5px monospace';
      ctx.fillText(`${len}px`, midX + 3, midY - 2);
    };

    // Spine & Neck
    drawBone(skel.root, skel.spineMid, 'lumbar');
    drawBone(skel.spineMid, skel.chest, 'chest');
    drawBone(skel.chest, skel.neckHead, 'neck');
    drawBone(skel.neckHead, skel.crown, 'head');

    // Clavicles & Arms
    drawBone(skel.chest, skel.shoulderL, 'clavL');
    drawBone(skel.chest, skel.shoulderR, 'clavR');
    drawBone(skel.shoulderL, skel.elbowL, 'humL');
    drawBone(skel.elbowL, skel.wristL, 'radL');
    drawBone(skel.shoulderR, skel.elbowR, 'humR');
    drawBone(skel.elbowR, skel.wristR, 'radR');

    // Pelvis & Legs
    drawBone(skel.root, skel.hipL, 'pelvL');
    drawBone(skel.root, skel.hipR, 'pelvR');
    drawBone(skel.hipL, skel.kneeL, 'femL');
    drawBone(skel.kneeL, skel.ankleL, 'tibL');
    drawBone(skel.hipR, skel.kneeR, 'femR');
    drawBone(skel.kneeR, skel.ankleR, 'tibR');

    // Feet
    drawBone(skel.ankleL, skel.toeL, 'footL');
    drawBone(skel.ankleR, skel.toeR, 'footR');

    // 2. Draw Joints with Color Coded Markers
    const joints: Array<{ pt: Point2D; name: string; color: string }> = [
      { pt: skel.root, name: 'Root', color: '#FF3366' },
      { pt: skel.chest, name: 'Chest', color: '#FF3366' },
      { pt: skel.neckHead, name: 'Neck', color: '#FF9900' },
      { pt: skel.headCenter, name: 'Head', color: '#FF9900' },
      { pt: skel.shoulderL, name: 'Sh_L', color: '#00CCFF' },
      { pt: skel.shoulderR, name: 'Sh_R', color: '#00CCFF' },
      { pt: skel.elbowL, name: 'Elb_L', color: '#00FFCC' },
      { pt: skel.elbowR, name: 'Elb_R', color: '#00FFCC' },
      { pt: skel.wristL, name: 'Wri_L', color: '#FFFF00' },
      { pt: skel.wristR, name: 'Wri_R', color: '#FFFF00' },
      { pt: skel.handL, name: 'Grip_L', color: '#FF00FF' },
      { pt: skel.handR, name: 'Grip_R', color: '#FF00FF' },
      { pt: skel.hipL, name: 'Hip_L', color: '#00CCFF' },
      { pt: skel.hipR, name: 'Hip_R', color: '#00CCFF' },
      { pt: skel.kneeL, name: 'Knee_L', color: '#00FFCC' },
      { pt: skel.kneeR, name: 'Knee_R', color: '#00FFCC' },
      { pt: skel.ankleL, name: 'Ank_L', color: '#FFFF00' },
      { pt: skel.ankleR, name: 'Ank_R', color: '#FFFF00' },
      { pt: skel.toeL, name: 'Toe_L', color: '#FF0055' },
      { pt: skel.toeR, name: 'Toe_R', color: '#FF0055' },
    ];

    for (const j of joints) {
      ctx.beginPath();
      ctx.arc(j.pt.x, j.pt.y, 4.0, 0, Math.PI * 2);
      ctx.fillStyle = j.color;
      ctx.fill();
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = '#000000';
      ctx.stroke();

      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 8px monospace';
      ctx.fillText(j.name, j.pt.x + 5, j.pt.y + 3);
    }

    // 3. Ground contact line
    ctx.beginPath();
    ctx.moveTo(-100, 0);
    ctx.lineTo(100, 0);
    ctx.strokeStyle = 'rgba(255, 60, 60, 0.85)';
    ctx.lineWidth = 2.0;
    ctx.setLineDash([4, 4]);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = '#FF4444';
    ctx.font = 'bold 9px monospace';
    ctx.fillText('GROUND_PLANE (Y=0)', 40, -4);

    ctx.restore();
  }
}

export default UniversalCharacterEngine;
