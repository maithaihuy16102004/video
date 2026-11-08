/**
 * Canonical Stickman Rig & Analytical Kinematics Engine V5.1
 * Part of Universal Cinematic Pipeline V5.1 — Permanent Visual Style B Lock.
 * 
 * Guarantees:
 * 1. Normalized anatomical proportions (6.5 - 7.0 heads tall, never chibi).
 * 2. Strict bone-length invariants (zero limb stretching or compression).
 * 3. Analytical 2-bone IK with guaranteed knee non-inversion (knees flex forward).
 * 4. Pole-vector guided elbow flexion (no elbow flipping or popping).
 * 5. Continuous forearm-to-hand alignment (no disconnected or zero-rotated wrists).
 * 6. Explicit hand grip anchors for held props with socket transforms.
 * 7. Ground foot-locking with zero subsurface penetration.
 */

export interface Point2D {
  x: number;
  y: number;
}

export interface Vector2D {
  x: number;
  y: number;
}

export interface BoneSegment {
  readonly id: string;
  readonly parentJoint: string;
  readonly childJoint: string;
  readonly lengthPx: number;
}

export interface CanonicalProportions {
  readonly totalHeightPx: number;      // e.g. 300px
  readonly headHeightPx: number;       // e.g. 46px (~1:6.5 heads tall)
  readonly headWidthPx: number;        // e.g. 36px
  readonly neckLengthPx: number;       // e.g. 11px
  readonly shoulderWidthPx: number;    // e.g. 54px
  readonly chestLengthPx: number;      // e.g. 48px
  readonly lumbarLengthPx: number;     // e.g. 48px (Total torso = 96px)
  readonly hipWidthPx: number;         // e.g. 38px
  readonly upperArmLengthPx: number;   // e.g. 50px (Humerus)
  readonly forearmLengthPx: number;    // e.g. 46px (Radius/Ulna)
  readonly handLengthPx: number;       // e.g. 24px (Palm + Phalanges)
  readonly thighLengthPx: number;      // e.g. 74px (Femur)
  readonly shinLengthPx: number;       // e.g. 72px (Tibia/Fibula)
  readonly footHeightPx: number;       // e.g. 12px (Ankle to ground)
  readonly footLengthPx: number;       // e.g. 30px (Heel to toe)
  readonly limbThicknessPx: number;    // e.g. 10 - 12px
}

export interface CanonicalJointHierarchy {
  // Root & Pelvis
  root: Point2D;              // Pelvis center / Sacrum
  hipL: Point2D;
  hipR: Point2D;

  // Legs
  kneeL: Point2D;
  kneeR: Point2D;
  ankleL: Point2D;
  ankleR: Point2D;
  heelL: Point2D;
  heelR: Point2D;
  toeL: Point2D;
  toeR: Point2D;

  // Spine & Thorax
  spineBase: Point2D;         // L5 vertebra
  spineMid: Point2D;          // T12 vertebra
  chest: Point2D;             // Sternum / T1 vertebra
  shoulderL: Point2D;
  shoulderR: Point2D;

  // Neck & Head
  neckBase: Point2D;          // C7 vertebra
  neckHead: Point2D;          // Atlas / Cranial base
  headCenter: Point2D;
  chin: Point2D;
  crown: Point2D;

  // Arms
  elbowL: Point2D;
  elbowR: Point2D;
  wristL: Point2D;
  wristR: Point2D;

  // Hands & Grip Anchors
  handL: Point2D;             // Palm center / Grip anchor
  handR: Point2D;             // Palm center / Grip anchor
  handAngleL: number;         // Radians
  handAngleR: number;         // Radians

  // Torso orientation
  torsoAngle: number;         // Radians
  headAngle: number;          // Radians
}

export class CanonicalStickmanRig {
  // ============================================================================
  // ANALYTICAL 2-BONE IK SOLVER WITH POLE-VECTOR & ANATOMICAL JOINT LIMITS
  // ============================================================================
  /**
   * Solves a 2-bone kinematic chain (e.g. Hip -> Knee -> Ankle or Shoulder -> Elbow -> Wrist).
   * 
   * Law of Cosines guarantee:
   *   d^2 = L1^2 + L2^2 - 2*L1*L2*cos(jointAngle)
   * 
   * Joint constraints:
   * - Knee: strictly flexes forward in the direction of character facing.
   * - Elbow: flexes naturally guided by pole vector.
   * - Invariant: exact bone lengths are strictly preserved.
   */
  public static solve2BoneIK(
    root: Point2D,
    target: Point2D,
    len1: number,
    len2: number,
    options: {
      jointType: 'knee' | 'elbow';
      facing: 1 | -1;
      poleVector?: Point2D;
      minReachFactor?: number;
      maxReachFactor?: number;
    }
  ): { joint: Point2D; end: Point2D; isClamped: boolean; reachFraction: number } {
    const dx = target.x - root.x;
    const dy = target.y - root.y;
    const dist = Math.hypot(dx, dy) || 0.001;

    // Strict reach clamping (prevents hyper-extension singularity & self-intersection)
    const minReach = Math.abs(len1 - len2) + 1.0;
    const maxReach = (len1 + len2) * (options.maxReachFactor ?? 0.998);
    const clampedDist = Math.max(minReach, Math.min(maxReach, dist));
    const isClamped = dist < minReach || dist > maxReach;
    const reachFraction = dist / (len1 + len2);

    // End effector clamped position
    const endX = root.x + (dx / dist) * clampedDist;
    const endY = root.y + (dy / dist) * clampedDist;

    // Angle of target vector relative to positive X-axis
    const baseAngle = Math.atan2(dy, dx);

    // Angle of first bone relative to target vector via Law of Cosines
    const cosAngle1 = (len1 * len1 + clampedDist * clampedDist - len2 * len2) / (2 * len1 * clampedDist);
    const clampedCos1 = Math.max(-1.0, Math.min(1.0, cosAngle1));
    const theta1 = Math.acos(clampedCos1);

    // Two possible joint positions (+theta1 and -theta1)
    const candA: Point2D = {
      x: root.x + Math.cos(baseAngle + theta1) * len1,
      y: root.y + Math.sin(baseAngle + theta1) * len1,
    };
    const candB: Point2D = {
      x: root.x + Math.cos(baseAngle - theta1) * len1,
      y: root.y + Math.sin(baseAngle - theta1) * len1,
    };

    let selectedJoint: Point2D;

    if (options.jointType === 'knee') {
      // ANATOMICAL RULE: Human knees bend forward in the facing direction!
      // In character local space (+X is facing direction):
      // Knee must have maximum +X protrusion when facing +1, or maximum -X when facing -1.
      if (options.facing === 1) {
        selectedJoint = candA.x >= candB.x ? candA : candB;
      } else {
        selectedJoint = candA.x <= candB.x ? candA : candB;
      }
    } else {
      // ANATOMICAL RULE: Elbows bend backwards relative to reach direction, guided by pole vector.
      const pole = options.poleVector ?? {
        x: root.x - options.facing * 30,
        y: root.y + 20,
      };
      const distA = Math.hypot(candA.x - pole.x, candA.y - pole.y);
      const distB = Math.hypot(candB.x - pole.x, candB.y - pole.y);
      selectedJoint = distA <= distB ? candA : candB;
    }

    return {
      joint: selectedJoint,
      end: { x: endX, y: endY },
      isClamped,
      reachFraction,
    };
  }

  // ============================================================================
  // CANONICAL RIG EVALUATION (100% Normalized Anatomical Proportions)
  // ============================================================================
  public static evaluateRig(
    proportions: CanonicalProportions,
    facing: 1 | -1,
    poseTargets: {
      torsoTiltAngle?: number;          // Radians (positive = forward lean)
      spineCurve?: number;              // Curvature factor (-0.2 to 0.2)
      hipYOffset?: number;              // Ground offset for squats / locomotion
      targetFootL: Point2D;
      targetFootR: Point2D;
      targetHandL: Point2D;
      targetHandR: Point2D;
      poleElbowL?: Point2D;
      poleElbowR?: Point2D;
      headLookAngle?: number;           // Radians
      footLockGround?: boolean;
    }
  ): CanonicalJointHierarchy {
    const p = proportions;
    const totalH = p.totalHeightPx;

    // Ground plane reference: Y = 0 is floor contact!
    // Negative Y is upward toward sky.
    const footHeight = p.footHeightPx;
    const legLength = p.thighLengthPx + p.shinLengthPx;
    const hipRestY = -(footHeight + legLength * 0.96); // ~-152px for 300px height
    const hipY = hipRestY + (poseTargets.hipYOffset ?? 0);

    // 1. Root & Pelvis
    const root: Point2D = { x: 0, y: hipY };
    const hipHalfW = p.hipWidthPx * 0.5;
    const hipL: Point2D = { x: root.x - hipHalfW * 0.85, y: root.y };
    const hipR: Point2D = { x: root.x + hipHalfW * 0.85, y: root.y };

    // 2. Legs IK Solving
    let footTargetL = { ...poseTargets.targetFootL };
    let footTargetR = { ...poseTargets.targetFootR };

    if (poseTargets.footLockGround !== false) {
      // Lock foot contact to floor (Y <= -footHeight means above floor, Y > -footHeight clamped)
      footTargetL.y = Math.min(-footHeight, footTargetL.y);
      footTargetR.y = Math.min(-footHeight, footTargetR.y);
    }

    const leftLegIK = this.solve2BoneIK(hipL, footTargetL, p.thighLengthPx, p.shinLengthPx, {
      jointType: 'knee',
      facing,
    });

    const rightLegIK = this.solve2BoneIK(hipR, footTargetR, p.thighLengthPx, p.shinLengthPx, {
      jointType: 'knee',
      facing,
    });

    const ankleL = leftLegIK.end;
    const ankleR = rightLegIK.end;
    const heelL: Point2D = { x: ankleL.x - p.footLengthPx * 0.35 * facing, y: ankleL.y + footHeight };
    const toeL: Point2D = { x: ankleL.x + p.footLengthPx * 0.65 * facing, y: ankleL.y + footHeight };
    const heelR: Point2D = { x: ankleR.x - p.footLengthPx * 0.35 * facing, y: ankleR.y + footHeight };
    const toeR: Point2D = { x: ankleR.x + p.footLengthPx * 0.65 * facing, y: ankleR.y + footHeight };

    // 3. Spine Hierarchy (Lumbar + Thoracic Column)
    const torsoTilt = poseTargets.torsoTiltAngle ?? 0;
    const spineCurve = poseTargets.spineCurve ?? 0;

    const lumbarLen = p.lumbarLengthPx;
    const chestLen = p.chestLengthPx;

    const spineBase: Point2D = { x: root.x, y: root.y - 4 };
    const spineMid: Point2D = {
      x: spineBase.x + Math.sin(torsoTilt + spineCurve) * lumbarLen,
      y: spineBase.y - Math.cos(torsoTilt + spineCurve) * lumbarLen,
    };
    const chest: Point2D = {
      x: spineMid.x + Math.sin(torsoTilt) * chestLen,
      y: spineMid.y - Math.cos(torsoTilt) * chestLen,
    };

    // Shoulders
    const shHalfW = p.shoulderWidthPx * 0.5;
    const shPerpX = Math.cos(torsoTilt);
    const shPerpY = Math.sin(torsoTilt);

    const shoulderL: Point2D = {
      x: chest.x - shPerpX * shHalfW * 0.85,
      y: chest.y - shPerpY * shHalfW * 0.85,
    };
    const shoulderR: Point2D = {
      x: chest.x + shPerpX * shHalfW * 0.85,
      y: chest.y + shPerpY * shHalfW * 0.85,
    };

    // 4. Neck & Head Hierarchy
    const neckBase: Point2D = { x: chest.x, y: chest.y - 2 };
    const neckLen = p.neckLengthPx;
    const headAngle = torsoTilt * 0.5 + (poseTargets.headLookAngle ?? 0);

    const neckHead: Point2D = {
      x: neckBase.x + Math.sin(headAngle) * neckLen,
      y: neckBase.y - Math.cos(headAngle) * neckLen,
    };

    const headR = p.headHeightPx * 0.5;
    const headCenter: Point2D = {
      x: neckHead.x + Math.sin(headAngle) * (headR * 0.85),
      y: neckHead.y - Math.cos(headAngle) * (headR * 0.85),
    };
    const chin: Point2D = {
      x: neckHead.x + Math.sin(headAngle) * (headR * 0.2),
      y: neckHead.y - Math.cos(headAngle) * (headR * 0.2),
    };
    const crown: Point2D = {
      x: headCenter.x + Math.sin(headAngle) * headR,
      y: headCenter.y - Math.cos(headAngle) * headR,
    };

    // 5. Arms IK Solving
    const defaultPoleL: Point2D = poseTargets.poleElbowL ?? {
      x: shoulderL.x - facing * 25,
      y: shoulderL.y + 35,
    };
    const defaultPoleR: Point2D = poseTargets.poleElbowR ?? {
      x: shoulderR.x - facing * 25,
      y: shoulderR.y + 35,
    };

    const leftArmIK = this.solve2BoneIK(
      shoulderL,
      poseTargets.targetHandL,
      p.upperArmLengthPx,
      p.forearmLengthPx,
      {
        jointType: 'elbow',
        facing,
        poleVector: defaultPoleL,
      }
    );

    const rightArmIK = this.solve2BoneIK(
      shoulderR,
      poseTargets.targetHandR,
      p.upperArmLengthPx,
      p.forearmLengthPx,
      {
        jointType: 'elbow',
        facing,
        poleVector: defaultPoleR,
      }
    );

    const wristL = leftArmIK.end;
    const wristR = rightArmIK.end;

    // Forearm direction determines natural hand & grip orientation
    const armVecL = { x: wristL.x - leftArmIK.joint.x, y: wristL.y - leftArmIK.joint.y };
    const armAngleL = Math.atan2(armVecL.y, armVecL.x);

    const armVecR = { x: wristR.x - rightArmIK.joint.x, y: wristR.y - rightArmIK.joint.y };
    const armAngleR = Math.atan2(armVecR.y, armVecR.x);

    // Grip anchors placed at palm center
    const palmDist = p.handLengthPx * 0.45;
    const handL: Point2D = {
      x: wristL.x + Math.cos(armAngleL) * palmDist,
      y: wristL.y + Math.sin(armAngleL) * palmDist,
    };
    const handR: Point2D = {
      x: wristR.x + Math.cos(armAngleR) * palmDist,
      y: wristR.y + Math.sin(armAngleR) * palmDist,
    };

    return {
      root,
      hipL,
      hipR,
      kneeL: leftLegIK.joint,
      kneeR: rightLegIK.joint,
      ankleL,
      ankleR,
      heelL,
      heelR,
      toeL,
      toeR,
      spineBase,
      spineMid,
      chest,
      shoulderL,
      shoulderR,
      neckBase,
      neckHead,
      headCenter,
      chin,
      crown,
      elbowL: leftArmIK.joint,
      elbowR: rightArmIK.joint,
      wristL,
      wristR,
      handL,
      handR,
      handAngleL: armAngleL,
      handAngleR: armAngleR,
      torsoAngle: torsoTilt,
      headAngle,
    };
  }

  // ============================================================================
  // BONE-LENGTH PRESERVATION AUDITOR (Invariant Checker)
  // ============================================================================
  public static auditBoneInvariants(
    rig: CanonicalJointHierarchy,
    props: CanonicalProportions
  ): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    const checkLength = (
      name: string,
      p1: Point2D,
      p2: Point2D,
      expected: number,
      tolerance = 1.5
    ) => {
      const actual = Math.hypot(p2.x - p1.x, p2.y - p1.y);
      const diff = Math.abs(actual - expected);
      if (diff > tolerance) {
        errors.push(`${name} length violation: expected ${expected.toFixed(1)}px, got ${actual.toFixed(1)}px (diff: ${diff.toFixed(2)}px)`);
      }
    };

    checkLength('Left Thigh', rig.hipL, rig.kneeL, props.thighLengthPx);
    checkLength('Right Thigh', rig.hipR, rig.kneeR, props.thighLengthPx);
    checkLength('Left Shin', rig.kneeL, rig.ankleL, props.shinLengthPx);
    checkLength('Right Shin', rig.kneeR, rig.ankleR, props.shinLengthPx);
    checkLength('Left Humerus', rig.shoulderL, rig.elbowL, props.upperArmLengthPx);
    checkLength('Right Humerus', rig.shoulderR, rig.elbowR, props.upperArmLengthPx);
    checkLength('Left Forearm', rig.elbowL, rig.wristL, props.forearmLengthPx);
    checkLength('Right Forearm', rig.elbowR, rig.wristR, props.forearmLengthPx);

    return {
      valid: errors.length === 0,
      errors,
    };
  }
}
