/**
 * Canonical Pose Library & Blending Engine V5.1
 * Part of Universal Cinematic Pipeline V5.1 — Permanent Visual Style B Lock.
 * 
 * Reusable, anatomically verified poses:
 * 1. neutral_standing (Balanced weight, relaxed arms, grounded feet)
 * 2. walking (4-phase locomotion cycle: Contact, Down, Passing, Up)
 * 3. running (Sprinting with flight phase, torso lean, knee drive)
 * 4. holding_object (Single-hand and two-hand grip at sockets)
 * 5. reaching (Arm extension toward target with pelvic counterbalance)
 * 6. speaking (Conversational gestures with thoracic lift)
 * 7. sitting (Hips lowered to chair/bench plane, 90 deg knee bend)
 * 8. falling (Sudden loss of balance, backward or forward flail)
 * 9. recovering (Hands planting on ground, pushing body up)
 */

import { Point2D, CanonicalProportions } from './CanonicalStickmanRig';

export interface PoseTargetFrame {
  torsoTiltAngle: number;
  spineCurve: number;
  hipYOffset: number;
  targetFootL: Point2D;
  targetFootR: Point2D;
  targetHandL: Point2D;
  targetHandR: Point2D;
  poleElbowL?: Point2D;
  poleElbowR?: Point2D;
  headLookAngle: number;
  footLockGround: boolean;
}

export class PoseLibrary {
  /**
   * 1. NEUTRAL STANDING POSE
   * Relaxed, upright posture with weight evenly distributed on both feet.
   */
  public static getNeutralStanding(
    p: CanonicalProportions,
    timeSeconds = 0,
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const breath = Math.sin(timeSeconds * 1.8) * 1.5;
    const footH = p.footHeightPx;
    const shW = p.shoulderWidthPx;
    const hipW = p.hipWidthPx;

    const shoulderY = -(footH + (p.thighLengthPx + p.shinLengthPx) * 0.96 + p.lumbarLengthPx + p.chestLengthPx);

    return {
      torsoTiltAngle: 0.02,
      spineCurve: 0.01,
      hipYOffset: breath * 0.4,
      targetFootL: { x: -hipW * 0.45, y: -footH },
      targetFootR: { x: hipW * 0.45, y: -footH },
      // Hands hang naturally at thigh level with gentle inward curvature
      targetHandL: { x: -shW * 0.52, y: shoulderY + p.upperArmLengthPx + p.forearmLengthPx * 0.85 + breath },
      targetHandR: { x: shW * 0.52, y: shoulderY + p.upperArmLengthPx + p.forearmLengthPx * 0.85 + breath },
      headLookAngle: 0.0,
      footLockGround: true,
    };
  }

  /**
   * 2. WALKING CYCLE
   * 4-phase biomechanical walk cycle:
   * Phase 0.00: Right foot heel strike (Contact), Left foot push-off.
   * Phase 0.25: Right foot takes full weight (Down), Left foot lifts.
   * Phase 0.50: Left foot passes right knee (Passing).
   * Phase 0.75: Left foot extends forward (Up), Right foot rolls to toe.
   */
  public static getWalkCycle(
    p: CanonicalProportions,
    timeSeconds: number,
    strideRate = 5.2,
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const ph = (timeSeconds * strideRate) % (Math.PI * 2);
    const footH = p.footHeightPx;
    const shW = p.shoulderWidthPx;
    const hipW = p.hipWidthPx;
    const stride = p.shinLengthPx * 0.55; // Natural stride amplitude
    const lift = p.shinLengthPx * 0.22;   // Foot clearance height

    const sinPh = Math.sin(ph);
    const cosPh = Math.cos(ph);

    // Hip vertical oscillation (rises during passing, lowers at contact)
    const hipBob = Math.abs(sinPh) * 3.5 - 1.8;

    // Feet trajectory: stance foot moves backwards relative to body, swing foot arcs forward
    const footLX = -sinPh * stride;
    const footRX = sinPh * stride;
    const footLY = cosPh > 0 ? -footH + Math.sin(ph) * lift : -footH;
    const footRY = cosPh < 0 ? -footH - Math.sin(ph) * lift : -footH;

    const shoulderY = -(footH + (p.thighLengthPx + p.shinLengthPx) * 0.96 + p.lumbarLengthPx + p.chestLengthPx);
    const armSwing = p.forearmLengthPx * 0.55;

    return {
      torsoTiltAngle: 0.06 + Math.abs(sinPh) * 0.02,
      spineCurve: 0.02,
      hipYOffset: hipBob,
      targetFootL: { x: footLX, y: Math.max(-footH - lift, Math.min(-footH, footLY)) },
      targetFootR: { x: footRX, y: Math.max(-footH - lift, Math.min(-footH, footRY)) },
      // Opposite arm swings forward with foot (counter-balancing torque)
      targetHandL: { x: -shW * 0.48 + sinPh * armSwing, y: shoulderY + p.upperArmLengthPx + p.forearmLengthPx * 0.75 },
      targetHandR: { x: shW * 0.48 - sinPh * armSwing, y: shoulderY + p.upperArmLengthPx + p.forearmLengthPx * 0.75 },
      headLookAngle: -sinPh * 0.03,
      footLockGround: false, // Managed by swing trajectory
    };
  }

  /**
   * 3. RUNNING CYCLE (Sprint / Haste)
   * High dynamic lean, strong arm drive, flight phase where both feet leave ground.
   */
  public static getRunCycle(
    p: CanonicalProportions,
    timeSeconds: number,
    strideRate = 9.5,
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const ph = (timeSeconds * strideRate) % (Math.PI * 2);
    const footH = p.footHeightPx;
    const shW = p.shoulderWidthPx;
    const stride = p.thighLengthPx * 0.95;
    const lift = p.thighLengthPx * 0.65;

    const sinPh = Math.sin(ph);
    const cosPh = Math.cos(ph);

    const shoulderY = -(footH + (p.thighLengthPx + p.shinLengthPx) * 0.96 + p.lumbarLengthPx + p.chestLengthPx);

    // Stride feet
    const footLX = -sinPh * stride;
    const footRX = sinPh * stride;
    const footLY = cosPh > 0 ? -footH + Math.abs(cosPh) * lift : -footH;
    const footRY = cosPh < 0 ? -footH + Math.abs(cosPh) * lift : -footH;

    const armDrive = p.upperArmLengthPx * 0.85;

    return {
      torsoTiltAngle: 0.24, // Strong forward athletic lean
      spineCurve: 0.06,
      hipYOffset: Math.sin(ph * 2) * 6.5,
      targetFootL: { x: footLX, y: Math.min(-footH, footLY) },
      targetFootR: { x: footRX, y: Math.min(-footH, footRY) },
      targetHandL: {
        x: -shW * 0.45 + sinPh * armDrive,
        y: shoulderY + p.upperArmLengthPx * 0.85 - cosPh * 25,
      },
      targetHandR: {
        x: shW * 0.45 - sinPh * armDrive,
        y: shoulderY + p.upperArmLengthPx * 0.85 + cosPh * 25,
      },
      headLookAngle: 0.12,
      footLockGround: false,
    };
  }

  /**
   * 4. HOLDING OBJECT (Single-Hand or Two-Hand)
   * Positions hand(s) precisely at prop grip socket.
   */
  public static getHoldingObject(
    p: CanonicalProportions,
    mode: 'single_hand_right' | 'two_handed_front',
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const footH = p.footHeightPx;
    const shW = p.shoulderWidthPx;
    const hipW = p.hipWidthPx;
    const shoulderY = -(footH + (p.thighLengthPx + p.shinLengthPx) * 0.96 + p.lumbarLengthPx + p.chestLengthPx);

    if (mode === 'two_handed_front') {
      return {
        torsoTiltAngle: 0.06,
        spineCurve: 0.02,
        hipYOffset: 0,
        targetFootL: { x: -hipW * 0.45, y: -footH },
        targetFootR: { x: hipW * 0.45, y: -footH },
        // Both hands meet in front of chest holding the open letter/prop
        targetHandL: { x: 12 * facing, y: shoulderY + p.chestLengthPx * 0.75 },
        targetHandR: { x: 26 * facing, y: shoulderY + p.chestLengthPx * 0.75 },
        headLookAngle: 0.22, // Eyes looking down at held object
        footLockGround: true,
      };
    }

    // Single-hand right holding
    return {
      torsoTiltAngle: 0.04,
      spineCurve: 0.01,
      hipYOffset: 0,
      targetFootL: { x: -hipW * 0.45, y: -footH },
      targetFootR: { x: hipW * 0.45, y: -footH },
      targetHandL: { x: -shW * 0.52, y: shoulderY + p.upperArmLengthPx + p.forearmLengthPx * 0.75 },
      targetHandR: { x: 28 * facing, y: shoulderY + p.chestLengthPx * 0.9 },
      headLookAngle: 0.05,
      footLockGround: true,
    };
  }

  /**
   * 5. REACHING POSE
   * Extended arm reaching toward external target, body counterbalanced.
   */
  public static getReaching(
    p: CanonicalProportions,
    reachTargetX = 55,
    reachTargetY = -120,
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const footH = p.footHeightPx;
    const shW = p.shoulderWidthPx;
    const hipW = p.hipWidthPx;
    const shoulderY = -(footH + (p.thighLengthPx + p.shinLengthPx) * 0.96 + p.lumbarLengthPx + p.chestLengthPx);

    return {
      torsoTiltAngle: 0.18 * facing,
      spineCurve: 0.04,
      hipYOffset: -2,
      targetFootL: { x: -hipW * 0.65, y: -footH },
      targetFootR: { x: hipW * 0.45, y: -footH },
      targetHandL: { x: -shW * 0.65 * facing, y: shoulderY + p.chestLengthPx * 1.1 },
      // Reach target clamped by rig IK solver
      targetHandR: { x: reachTargetX * facing, y: reachTargetY },
      headLookAngle: 0.20 * facing,
      footLockGround: true,
    };
  }

  /**
   * 6. SPEAKING / DIALOGUE POSE
   * Subtly gestures with one hand while standing grounded.
   */
  public static getSpeaking(
    p: CanonicalProportions,
    timeSeconds: number,
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const ph = timeSeconds * 3.5;
    const footH = p.footHeightPx;
    const shW = p.shoulderWidthPx;
    const hipW = p.hipWidthPx;
    const shoulderY = -(footH + (p.thighLengthPx + p.shinLengthPx) * 0.96 + p.lumbarLengthPx + p.chestLengthPx);

    return {
      torsoTiltAngle: 0.04 + Math.sin(ph) * 0.02,
      spineCurve: 0.02,
      hipYOffset: 0,
      targetFootL: { x: -hipW * 0.5, y: -footH },
      targetFootR: { x: hipW * 0.5, y: -footH },
      targetHandL: { x: -shW * 0.52, y: shoulderY + p.upperArmLengthPx + p.forearmLengthPx * 0.8 },
      // Gestural speaking hand
      targetHandR: {
        x: (shW * 0.55 + Math.sin(ph) * 14) * facing,
        y: shoulderY + p.chestLengthPx * 0.65 + Math.cos(ph) * 10,
      },
      headLookAngle: Math.sin(ph * 0.7) * 0.06,
      footLockGround: true,
    };
  }

  /**
   * 7. SITTING POSE
   * Thighs horizontal, knees bent 90 degrees, feet flat on floor.
   */
  public static getSitting(
    p: CanonicalProportions,
    seatHeightPx = 52,
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const footH = p.footHeightPx;
    const shW = p.shoulderWidthPx;
    const hipW = p.hipWidthPx;
    const hipRestY = -(footH + (p.thighLengthPx + p.shinLengthPx) * 0.96);
    const targetHipY = -seatHeightPx;

    const shoulderY = targetHipY - (p.lumbarLengthPx + p.chestLengthPx);

    return {
      torsoTiltAngle: -0.04,
      spineCurve: 0.04,
      hipYOffset: targetHipY - hipRestY,
      // Feet planted forward of seat
      targetFootL: { x: p.thighLengthPx * 0.65 * facing - hipW * 0.3, y: -footH },
      targetFootR: { x: p.thighLengthPx * 0.65 * facing + hipW * 0.3, y: -footH },
      // Hands resting on knees
      targetHandL: { x: (p.thighLengthPx * 0.65 - 10) * facing, y: targetHipY + 8 },
      targetHandR: { x: (p.thighLengthPx * 0.65 + 10) * facing, y: targetHipY + 8 },
      headLookAngle: 0.0,
      footLockGround: true,
    };
  }

  /**
   * 8. FALLING POSE (Slip & Fall)
   * Center of mass displaced, legs buckling, arms flailing for purchase.
   */
  public static getFalling(
    p: CanonicalProportions,
    timeSeconds: number,
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const footH = p.footHeightPx;
    const shW = p.shoulderWidthPx;
    const hipW = p.hipWidthPx;
    const shoulderY = -(footH + (p.thighLengthPx + p.shinLengthPx) * 0.96 + p.lumbarLengthPx + p.chestLengthPx);

    return {
      torsoTiltAngle: -0.55 * facing, // Sudden backward tilt
      spineCurve: -0.12,
      hipYOffset: 25,                 // Hips dropping toward floor
      targetFootL: { x: 35 * facing, y: -footH - 18 }, // Feet kicked out
      targetFootR: { x: 65 * facing, y: -footH - 8 },
      targetHandL: { x: -45 * facing, y: shoulderY - 20 }, // Arms flailing up
      targetHandR: { x: 45 * facing, y: shoulderY - 35 },
      headLookAngle: -0.40 * facing,
      footLockGround: false,
    };
  }

  /**
   * 9. RECOVERING POSE
   * Planting hands on ground plane, bracing weight, regaining balance.
   */
  public static getRecovering(
    p: CanonicalProportions,
    timeSeconds: number,
    facing: 1 | -1 = 1
  ): PoseTargetFrame {
    const footH = p.footHeightPx;
    const hipW = p.hipWidthPx;

    return {
      torsoTiltAngle: 0.42 * facing,  // Forward crouch
      spineCurve: 0.14,
      hipYOffset: 32,                 // Low crouch
      targetFootL: { x: -hipW * 0.8, y: -footH },
      targetFootR: { x: hipW * 0.4, y: -footH },
      // Hands braced near ground
      targetHandL: { x: -20 * facing, y: -footH - 2 },
      targetHandR: { x: 30 * facing, y: -footH - 2 },
      headLookAngle: 0.25 * facing,
      footLockGround: true,
    };
  }

  /**
   * POSE BLENDER
   * Hermite smoothstep interpolation between any two pose frames.
   */
  public static blendPoses(
    poseA: PoseTargetFrame,
    poseB: PoseTargetFrame,
    alpha: number // [0, 1]
  ): PoseTargetFrame {
    // Hermite S-curve
    const t = Math.max(0, Math.min(1, alpha));
    const smoothT = t * t * (3 - 2 * t);

    const lerp = (a: number, b: number) => a + (b - a) * smoothT;
    const lerpPt = (p1: Point2D, p2: Point2D): Point2D => ({
      x: lerp(p1.x, p2.x),
      y: lerp(p1.y, p2.y),
    });

    return {
      torsoTiltAngle: lerp(poseA.torsoTiltAngle, poseB.torsoTiltAngle),
      spineCurve: lerp(poseA.spineCurve, poseB.spineCurve),
      hipYOffset: lerp(poseA.hipYOffset, poseB.hipYOffset),
      targetFootL: lerpPt(poseA.targetFootL, poseB.targetFootL),
      targetFootR: lerpPt(poseA.targetFootR, poseB.targetFootR),
      targetHandL: lerpPt(poseA.targetHandL, poseB.targetHandL),
      targetHandR: lerpPt(poseA.targetHandR, poseB.targetHandR),
      headLookAngle: lerp(poseA.headLookAngle, poseB.headLookAngle),
      footLockGround: smoothT < 0.5 ? poseA.footLockGround : poseB.footLockGround,
    };
  }
}
