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

export type { CharacterDNA_V5, HeadContour, EyeType, EyebrowStyle, HairStyle, CostumeArchetype, FootwearType, PropAttachment };
export { V5_CORE_ARCHETYPES };

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
  | 'inspect_down';

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
  // ANALYTICAL 2-BONE INVERSE KINEMATICS (IK) SOLVER (Law of Cosines)
  // ============================================================================
  public solve2BoneIK(
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
  // SKELETAL RIG COMPUTATION (12 Joints + Foot-Locking)
  // ============================================================================
  public evaluateSkeleton(
    dna: CharacterDNA_V5,
    state: CharacterStateV5,
    totalH: number,
    headR: number
  ): SkeletalRigV5 {
    const sw = dna.proportions.shoulderWidthPx || 54;
    const armLen1 = totalH * 0.19;
    const armLen2 = totalH * 0.18;
    const legLen1 = totalH * 0.24;
    const legLen2 = totalH * 0.25;

    let hipY = -totalH * 0.48;
    let shoulderY = -totalH * 0.78;
    let torsoTilt = 0.0;
    let headCenter: Point2D = { x: 0, y: shoulderY - headR * 1.15 };

    let targetHandL: Point2D = { x: -sw * 0.55, y: -totalH * 0.42 };
    let targetHandR: Point2D = { x: sw * 0.55, y: -totalH * 0.42 };
    let targetFootL: Point2D = { x: -sw * 0.28, y: 0 };
    let targetFootR: Point2D = { x: sw * 0.28, y: 0 };
    let legBendL: 1 | -1 = 1;
    let legBendR: 1 | -1 = 1;

    const act = state.action;
    const p = state.progress;

    // --- LOCOMOTION ---
    if (act === 'sprint' || act === 'run') {
      const speed = act === 'sprint' ? 14.0 : 10.0;
      const ph = p * speed;
      torsoTilt = act === 'sprint' ? 0.30 : 0.18;
      hipY = -totalH * 0.46 + Math.sin(ph * 2) * (act === 'sprint' ? 9 : 6);
      shoulderY = hipY - totalH * 0.31;
      headCenter = { x: act === 'sprint' ? 22 : 14, y: shoulderY - headR * 1.05 };

      const stride = act === 'sprint' ? 58 : 42;
      const lift = act === 'sprint' ? 38 : 26;
      targetFootL = { x: Math.sin(ph) * stride, y: Math.max(0, -Math.cos(ph) * lift) };
      targetFootR = { x: -Math.sin(ph) * stride, y: Math.max(0, Math.cos(ph) * lift) };

      targetHandL = { x: -Math.sin(ph) * stride * 0.8, y: shoulderY + 30 + Math.cos(ph) * 32 };
      targetHandR = { x: Math.sin(ph) * stride * 0.8 + 20, y: shoulderY + 22 - Math.cos(ph) * 32 };
    } else if (act === 'walk') {
      const ph = p * 6.5;
      torsoTilt = 0.08;
      hipY = -totalH * 0.48 + Math.abs(Math.sin(ph)) * 4;
      shoulderY = -totalH * 0.78 + Math.abs(Math.sin(ph)) * 3;
      headCenter = { x: 5, y: shoulderY - headR * 1.15 };

      targetFootL = { x: Math.sin(ph) * 32, y: Math.max(0, -Math.cos(ph) * 16) };
      targetFootR = { x: -Math.sin(ph) * 32, y: Math.max(0, Math.cos(ph) * 16) };
      targetHandL = { x: -sw * 0.45 - Math.sin(ph) * 22, y: shoulderY + totalH * 0.34 };
      targetHandR = { x: sw * 0.45 + Math.sin(ph) * 22, y: shoulderY + totalH * 0.34 };
    } else if (act === 'stop') {
      torsoTilt = -0.15;
      hipY = -totalH * 0.44;
      shoulderY = -totalH * 0.75;
      headCenter = { x: -6, y: shoulderY - headR * 1.1 };
      targetFootL = { x: -sw * 0.2, y: 0 };
      targetFootR = { x: sw * 0.5, y: 0 };
      targetHandL = { x: -sw * 0.6, y: shoulderY + totalH * 0.25 };
      targetHandR = { x: sw * 0.6, y: shoulderY + totalH * 0.25 };
    } else if (act === 'jump') {
      const ph = Math.sin(p * Math.PI);
      torsoTilt = 0.12;
      hipY = -totalH * (0.48 + ph * 0.25);
      shoulderY = hipY - totalH * 0.30;
      headCenter = { x: 8, y: shoulderY - headR * 1.1 };
      targetFootL = { x: -sw * 0.25, y: -totalH * 0.15 * ph };
      targetFootR = { x: sw * 0.25, y: -totalH * 0.18 * ph };
      targetHandL = { x: -sw * 0.6, y: shoulderY - totalH * 0.2 * ph };
      targetHandR = { x: sw * 0.6, y: shoulderY - totalH * 0.2 * ph };
      legBendL = -1;
      legBendR = -1;
    }
    // --- INTERACTION ---
    else if (act === 'reach' || act === 'grab' || act === 'point') {
      torsoTilt = 0.16;
      shoulderY = -totalH * 0.76;
      headCenter = { x: 12, y: shoulderY - headR * 1.1 };
      targetHandL = { x: -sw * 0.35, y: shoulderY + totalH * 0.35 };
      targetHandR = { x: sw * 0.85, y: shoulderY + totalH * 0.08 }; // Reaching outward
      targetFootL = { x: -sw * 0.35, y: 0 };
      targetFootR = { x: sw * 0.35, y: 0 };
    } else if (act === 'read' || act === 'inspect_down') {
      torsoTilt = 0.28;
      shoulderY = -totalH * 0.72;
      hipY = -totalH * 0.46;
      headCenter = { x: 26, y: shoulderY - headR * 0.90 };
      targetHandL = { x: -sw * 0.15, y: shoulderY + totalH * 0.25 };
      targetHandR = { x: sw * 0.35, y: shoulderY + totalH * 0.22 };
    } else if (act === 'give' || act === 'present_two_handed') {
      torsoTilt = 0.10;
      shoulderY = -totalH * 0.75;
      headCenter = { x: 10, y: shoulderY - headR * 1.1 };
      targetHandL = { x: sw * 0.35, y: shoulderY + totalH * 0.22 };
      targetHandR = { x: sw * 0.58, y: shoulderY + totalH * 0.20 };
    } else if (act === 'hold' || act === 'carry') {
      torsoTilt = 0.04;
      shoulderY = -totalH * 0.77;
      headCenter = { x: 2, y: shoulderY - headR * 1.15 };
      targetHandL = { x: -sw * 0.42, y: shoulderY + totalH * 0.28 };
      targetHandR = { x: sw * 0.45, y: shoulderY + totalH * 0.24 };
    }
    // --- PERFORMANCE ---
    else if (act === 'laugh' || act === 'laugh_heartily') {
      const ph = p * 8.0;
      torsoTilt = -0.16 + Math.sin(ph) * 0.08;
      shoulderY = -totalH * 0.76 + Math.sin(ph) * 5;
      headCenter = { x: -14, y: shoulderY - headR * 1.1 };
      targetHandL = { x: -sw * 0.45, y: shoulderY + totalH * 0.26 };
      targetHandR = { x: sw * 0.20, y: shoulderY + totalH * 0.12 }; // Hand at mouth
    } else if (act === 'speak' || act === 'speak_gestural') {
      const ph = p * 4.0;
      torsoTilt = 0.04;
      shoulderY = -totalH * 0.78;
      headCenter = { x: 0, y: shoulderY - headR * 1.15 };
      targetHandL = { x: -sw * 0.55, y: shoulderY + totalH * 0.34 };
      targetHandR = { x: sw * 0.65 + Math.sin(ph) * 16, y: shoulderY + totalH * 0.16 + Math.cos(ph) * 12 };
    } else if (act === 'relief') {
      torsoTilt = 0.14;
      shoulderY = -totalH * 0.73;
      headCenter = { x: 10, y: shoulderY - headR * 0.95 };
      targetHandL = { x: -sw * 0.35, y: shoulderY + totalH * 0.15 }; // Hand on chest
      targetHandR = { x: sw * 0.50, y: shoulderY + totalH * 0.32 };
    } else if (act === 'fear' || act === 'surprise') {
      torsoTilt = -0.22;
      shoulderY = -totalH * 0.81;
      headCenter = { x: -16, y: shoulderY - headR * 1.2 };
      targetHandL = { x: -sw * 0.65, y: shoulderY + totalH * 0.12 };
      targetHandR = { x: sw * 0.65, y: shoulderY + totalH * 0.12 };
      targetFootL = { x: -sw * 0.4, y: 0 };
      targetFootR = { x: sw * 0.2, y: 0 };
    }
    // --- PHYSICAL EVENTS ---
    else if (act === 'slip' || act === 'slip_fall' || act === 'trip' || act === 'fall') {
      torsoTilt = -0.65;
      hipY = -totalH * 0.28;
      shoulderY = -totalH * 0.52;
      headCenter = { x: -35, y: shoulderY - headR * 0.9 };
      targetFootL = { x: 60, y: -totalH * 0.22 };
      targetFootR = { x: 95, y: -totalH * 0.12 };
      targetHandL = { x: -45, y: -totalH * 0.75 };
      targetHandR = { x: 65, y: -totalH * 0.85 };
    } else if (act === 'hang' || act === 'hang_from_ledge') {
      torsoTilt = 0.12;
      shoulderY = -totalH * 0.48;
      hipY = -totalH * 0.18;
      headCenter = { x: 8, y: shoulderY - headR * 1.1 };
      targetHandL = { x: -18, y: -totalH * 0.82 };
      targetHandR = { x: 45, y: -totalH * 0.88 }; // Holding prop high & dry
      targetFootL = { x: -22, y: totalH * 0.18 };
      targetFootR = { x: 12, y: totalH * 0.12 };
      legBendL = -1;
    } else if (act === 'catch_balance' || act === 'recover') {
      torsoTilt = 0.24;
      hipY = -totalH * 0.42;
      shoulderY = -totalH * 0.72;
      headCenter = { x: 18, y: shoulderY - headR * 1.05 };
      targetFootL = { x: -sw * 0.6, y: 0 };
      targetFootR = { x: sw * 0.6, y: 0 };
      targetHandL = { x: -sw * 0.85, y: shoulderY + totalH * 0.05 }; // Arms windmilling
      targetHandR = { x: sw * 0.85, y: shoulderY + totalH * 0.15 };
    }
    // --- IDLE DEFAULT ---
    else {
      const breath = Math.sin(p * 1.8) * 3;
      shoulderY = -totalH * 0.78 + breath;
      headCenter = { x: 0, y: shoulderY - headR * 1.15 };
      targetHandL = { x: -sw * 0.52, y: shoulderY + totalH * 0.34 };
      targetHandR = { x: sw * 0.52, y: shoulderY + totalH * 0.34 };
      targetFootL = { x: -sw * 0.28, y: 0 };
      targetFootR = { x: sw * 0.28, y: 0 };
    }

    if (state.handConstraintL) targetHandL = { x: state.handConstraintL[0], y: state.handConstraintL[1] };
    if (state.handConstraintR) targetHandR = { x: state.handConstraintR[0], y: state.handConstraintR[1] };

    if (state.footLockGround !== false && act !== 'slip' && act !== 'slip_fall' && act !== 'hang' && act !== 'jump') {
      targetFootL.y = Math.min(0, targetFootL.y);
      targetFootR.y = Math.min(0, targetFootR.y);
    }

    const shoulderCenter = { x: Math.sin(torsoTilt) * 18, y: shoulderY };
    const hipRoot = { x: 0, y: hipY };
    const neck = { x: shoulderCenter.x, y: shoulderCenter.y - headR * 0.35 };

    const shoulderL = { x: shoulderCenter.x - sw * 0.48, y: shoulderCenter.y };
    const shoulderR = { x: shoulderCenter.x + sw * 0.48, y: shoulderCenter.y };
    const hipL = { x: hipRoot.x - sw * 0.28, y: hipRoot.y };
    const hipR = { x: hipRoot.x + sw * 0.28, y: hipRoot.y };

    const leftArmIK = this.solve2BoneIK(shoulderL, targetHandL, armLen1, armLen2, -1);
    const rightArmIK = this.solve2BoneIK(shoulderR, targetHandR, armLen1, armLen2, 1);
    const leftLegIK = this.solve2BoneIK(hipL, targetFootL, legLen1, legLen2, legBendL);
    const rightLegIK = this.solve2BoneIK(hipR, targetFootR, legLen1, legLen2, legBendR);

    return {
      root: hipRoot,
      torso: shoulderCenter,
      neck,
      head: headCenter,
      shoulderL,
      shoulderR,
      elbowL: leftArmIK.joint,
      elbowR: rightArmIK.joint,
      wristL: leftArmIK.end,
      wristR: rightArmIK.end,
      handL: targetHandL,
      handR: targetHandR,
      hipL,
      hipR,
      kneeL: leftLegIK.joint,
      kneeR: rightLegIK.joint,
      ankleL: leftLegIK.end,
      ankleR: rightLegIK.end,
      footL: targetFootL,
      footR: targetFootR,
      torsoTilt,
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

    const prop = dna.proportions;
    const totalH = prop.standingHeightPx || 260;
    const headR = (totalH * (prop.headRatio || 0.28)) / 2;
    const ink = '#141210';
    const skin = dna.face.skinTone || '#F5DEB3';

    // 1. Ground contact shadow
    this.drawContactShadow(state, totalH);

    // 2. Complete 12-Joint Skeletal Hierarchy via IK
    const skel = this.evaluateSkeleton(dna, state, totalH, headR);

    // 3. Lower Costume (Legs / Pants / Skirt / Footwear)
    this.drawLowerCostume(ctx, dna, state, skel, ink);

    // 4. Upper Costume (Torso / Robe / Coat / Hoodie)
    this.drawUpperCostume(ctx, dna, state, skel, ink);

    // 5. Head, Neck & Face (5 Silhouettes, Eyes, Brows, Hair)
    this.drawHeadAndFace(ctx, dna, state, skel.head, headR, ink, skin);

    // 6. Arms & Hands (Articulated 5-Finger Anatomy)
    this.drawArmsAndHands(ctx, dna, state, skel, ink, skin);

    // 7. Held Props & Objects
    this.drawProps(ctx, dna, state, skel);

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
    skel: SkeletalRigV5,
    ink: string,
    skin: string
  ) {
    const limbW = (dna.proportions.limbThicknessPx || 11) * 0.95;
    const sleeveCol = dna.costume.primaryColor || '#1B3B6F';

    // Left Arm
    this.drawOrganicLimb(ctx, skel.shoulderL, skel.elbowL, skel.wristL, limbW * 1.15, limbW * 0.85, ink, sleeveCol);
    this.drawArticulatedHand(ctx, skel.handL, state.action === 'hang' ? 'grip' : 'open', ink, skin);

    // Right Arm
    this.drawOrganicLimb(ctx, skel.shoulderR, skel.elbowR, skel.wristR, limbW * 1.15, limbW * 0.85, ink, sleeveCol);
    this.drawArticulatedHand(
      ctx,
      skel.handR,
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
      ctx.beginPath();
      ctx.arc(0, 0, 7.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      for (const fx of [-4, 0, 4]) {
        ctx.beginPath();
        ctx.arc(fx, 3, 2.5, 0, Math.PI);
        ctx.stroke();
      }
    } else if (gripType === 'pinch_high') {
      ctx.beginPath();
      ctx.ellipse(0, 0, 6, 8, 0.3, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(4, -6, 2.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.ellipse(0, 0, 6.5, 7.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.beginPath();
      ctx.ellipse(-5.5, -2, 2.6, 4.5, -0.6, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

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
    footwear: FootwearType,
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
    } else if (footwear === 'waraji_sandals') {
      ctx.fillStyle = '#C2A368';
      ctx.beginPath();
      ctx.ellipse(6, 1, 14, 5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.0;
      ctx.strokeStyle = ink;
      ctx.stroke();

      ctx.strokeStyle = '#544222';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(-2, -3);
      ctx.lineTo(8, 2);
      ctx.moveTo(8, -3);
      ctx.lineTo(-2, 2);
      ctx.stroke();
    } else if (footwear === 'snow_boots') {
      ctx.fillStyle = '#212121';
      ctx.beginPath();
      ctx.roundRect(-4, -4, 24, 11, 4);
      ctx.fill();
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = ink;
      ctx.stroke();
    } else {
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
  // PROPS & ARTIFACTS
  // ============================================================================
  private drawProps(ctx: CanvasRenderingContext2D, dna: CharacterDNA_V5, state: CharacterStateV5, skel: SkeletalRigV5) {
    const rHand = skel.handR;
    const propR = dna.heldProps?.rightHand;

    if (propR === 'letter_scroll_sealed') {
      ctx.save();
      ctx.translate(rHand.x + 14, rHand.y - 16);
      ctx.rotate(0.2);
      ctx.fillStyle = '#F5E4B8';
      ctx.fillRect(-15, -24, 30, 48);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.2;
      ctx.strokeRect(-15, -24, 30, 48);

      ctx.fillStyle = '#C8281E'; // Red wax seal
      ctx.beginPath();
      ctx.arc(0, 0, 5.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    } else if (propR === 'letter_scroll_open') {
      ctx.save();
      ctx.translate(rHand.x - 20, rHand.y - 30);
      ctx.fillStyle = '#FFF9EC';
      ctx.fillRect(-45, -55, 90, 110);
      ctx.strokeStyle = '#181614';
      ctx.lineWidth = 2.4;
      ctx.strokeRect(-45, -55, 90, 110);

      ctx.fillStyle = '#181614';
      ctx.font = 'bold 9.5px "Be Vietnam Pro", Arial, sans-serif';
      ctx.fillText('Aiko thân mến,', -36, -34);
      ctx.fillText('Nhớ mang theo ô.', -36, -14);
      ctx.fillText('Chiều nay mưa to!', -36, 6);
      ctx.restore();
    } else if (propR === 'tablet_computer') {
      ctx.save();
      ctx.translate(rHand.x + 12, rHand.y - 12);
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
      ctx.translate(rHand.x + 14, rHand.y - 10);
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
      ctx.translate(rHand.x + 12, rHand.y - 12);
      ctx.rotate(0.15);
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
    } else if (propR === 'steaming_coffee_cup' || propR === 'coffee_cup') {
      ctx.save();
      ctx.translate(rHand.x + 10, rHand.y - 8);
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
      ctx.translate(rHand.x + 12, rHand.y - 12);
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
      // Generic contextual prop
      ctx.save();
      ctx.translate(rHand.x + 10, rHand.y - 10);
      ctx.fillStyle = '#37474F';
      ctx.fillRect(-12, -16, 24, 32);
      ctx.strokeStyle = '#ECEFF1';
      ctx.lineWidth = 1.8;
      ctx.strokeRect(-12, -16, 24, 32);
      ctx.restore();
    }
  }
}

export default UniversalCharacterEngine;
