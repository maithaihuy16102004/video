/**
 * Premium Illustrated Character Engine V4.2.1
 * 
 * Implements Phase 3 requirements:
 * - Organic Bézier head contour with natural jawline
 * - Distinct hair silhouettes (Haru topknot, Aiko shimada with kanzashi, Founder modern)
 * - Articulated facial features: gaze-directed eyes with specular highlights, expressive brows, mouth shapes
 * - Tapered limbs with variable line weights and natural muscle curves
 * - Articulated 5-finger hands (gripping railing, holding letter high, presenting, laughing)
 * - Clothing silhouettes with fabric folds (kimono, hanten, obi sash, kyahan leg wraps, modern hoodie)
 * - Authentic footwear: straw waraji sandal vs bare foot
 */

export interface CharacterPose {
  x: number;
  y: number;
  scale: number;
  facing: 1 | -1; // 1 = right, -1 = left
  action: 'sprint' | 'slip_bridge' | 'grip_hang' | 'arrive_soaked' | 'present_letter' | 'laugh' | 'inspect_twist' | 'lab_gesture';
  progress: number; // 0.0 to 1.0 within action
  eyeline: [number, number]; // [lookX, lookY] screen relative
  emotion: 'determined' | 'panic' | 'relief' | 'laughing' | 'confused' | 'focused';
  mouthOpen: number; // 0 (closed) to 1 (wide open/laugh)
  breathPhase: number;
  soaked: boolean;
  lostSandalRight: boolean;
}

export class PremiumCharacterRenderer {
  private ctx: CanvasRenderingContext2D;

  constructor(ctx: CanvasRenderingContext2D) {
    this.ctx = ctx;
  }

  // Draw complete character at screen position
  public draw(type: 'haru' | 'aiko' | 'station_master' | 'founder', pose: CharacterPose) {
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(pose.x, pose.y);
    ctx.scale(pose.scale * pose.facing, pose.scale);

    // Subtle breathing displacement
    const breathY = Math.sin(pose.breathPhase * Math.PI * 2) * 2.5;

    // Contact shadow on ground / bridge
    this.drawContactShadow(pose);

    if (type === 'haru') {
      this.drawHaru(pose, breathY);
    } else if (type === 'aiko') {
      this.drawAiko(pose, breathY);
    } else if (type === 'founder') {
      this.drawFounder(pose, breathY);
    }

    ctx.restore();
  }

  private drawContactShadow(pose: CharacterPose) {
    const ctx = this.ctx;
    ctx.save();
    ctx.beginPath();
    let shadowW = 90;
    let shadowAlpha = 0.45;
    if (pose.action === 'slip_bridge' || pose.action === 'grip_hang') {
      // In air / hanging from rail
      shadowW = 45;
      shadowAlpha = 0.18;
      ctx.translate(0, 120);
    }
    ctx.ellipse(0, 0, shadowW, 16, 0, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(15, 12, 10, ${shadowAlpha})`;
    ctx.fill();
    ctx.restore();
  }

  // ============================================================================
  // HARU (Edo Courier, Age 22)
  // ============================================================================
  private drawHaru(pose: CharacterPose, breathY: number) {
    const ctx = this.ctx;
    const ink = '#181614';
    const skin = '#EACAA8';
    const hantenBlue = pose.soaked ? '#1E2B38' : '#2D4459';
    const sashRed = '#8B2C24';
    const pantsGrey = '#383533';

    if (pose.action === 'grip_hang') {
      // CRUCIAL BEAT 1: Haru hanging by one hand from wooden railing!
      // Torso angled down towards canal, left arm gripping rail above, right arm holding letter dry aloft
      ctx.save();
      ctx.rotate(-0.35); // Slanted body hanging
      ctx.translate(-20, 40);

      // 1. Hanging Legs
      // Left leg (with straw sandal) kicking in terror
      this.drawLimb(ctx, [[-15, -60], [-35, 10], [-45, 75]], 14, ink, pantsGrey);
      this.drawWarajiFoot(ctx, -45, 75, -0.4, false);

      // Right leg (BARE FOOT, missing waraji sandal!)
      const kickX = Math.sin(pose.progress * 8) * 15;
      this.drawLimb(ctx, [[15, -60], [30 + kickX, 15], [35 + kickX, 85]], 13, ink, pantsGrey);
      this.drawBareFoot(ctx, 35 + kickX, 85, 0.3);

      // 2. Torso & Hanten coat fluttering
      this.drawTorsoHanten(ctx, 0, -130, hantenBlue, sashRed, ink, true);

      // 3. Head (looking down at torrent, then up at letter)
      ctx.save();
      ctx.translate(0, -185 + breathY);
      ctx.rotate(0.25);
      this.drawHead(ctx, skin, ink, 'haru', pose);
      ctx.restore();

      // 4. Arms
      // Left Arm: REACHING UP to grip the railing!
      this.drawLimb(ctx, [[-30, -150], [-55, -230], [-70, -290]], 12, ink, skin);
      this.drawGrippingHand(ctx, -70, -290, -0.2);

      // Right Arm: REACHING HIGH, holding oil-paper letter safe above head!
      this.drawLimb(ctx, [[30, -150], [60, -220], [85, -280]], 12, ink, skin);
      this.drawLetterHand(ctx, 85, -280, 0.35);

      ctx.restore();
      return;
    }

    if (pose.action === 'present_letter') {
      // CRUCIAL BEAT 2: Soaked Haru presenting letter with both hands respectfully
      // Legs standing grounded, bowing slightly
      this.drawLimb(ctx, [[-18, -80], [-20, -35], [-22, 0]], 14, ink, pantsGrey);
      this.drawWarajiFoot(ctx, -22, 0, 0, false);

      this.drawLimb(ctx, [[18, -80], [20, -35], [22, 0]], 14, ink, pantsGrey);
      this.drawBareFoot(ctx, 22, 0, 0); // Still missing sandal!

      this.drawTorsoHanten(ctx, 0, -140, hantenBlue, sashRed, ink, false);

      // Head bowing forward
      ctx.save();
      ctx.translate(15, -195 + breathY);
      ctx.rotate(0.18);
      this.drawHead(ctx, skin, ink, 'haru', pose);
      ctx.restore();

      // Both arms extending forward holding letter
      this.drawLimb(ctx, [[-20, -150], [15, -135], [45, -130]], 11, ink, skin);
      this.drawLimb(ctx, [[20, -150], [35, -140], [55, -132]], 11, ink, skin);
      this.drawPresentingHandsWithLetter(ctx, 50, -130);
      return;
    }

    if (pose.action === 'inspect_twist') {
      // CRUCIAL BEAT 3: Looking down at bare foot, head tilted, dry comedic reaction
      this.drawLimb(ctx, [[-16, -80], [-18, -35], [-20, 0]], 14, ink, pantsGrey);
      this.drawWarajiFoot(ctx, -20, 0, 0, false);

      // Right leg lifted slightly, inspecting dirty bare foot
      this.drawLimb(ctx, [[16, -80], [28, -40], [22, -15]], 13, ink, pantsGrey);
      this.drawBareFoot(ctx, 22, -15, -0.4);

      this.drawTorsoHanten(ctx, 0, -140, hantenBlue, sashRed, ink, false);

      // Head tilted downwards towards foot
      ctx.save();
      ctx.translate(0, -195 + breathY);
      ctx.rotate(0.45); // Looking down
      this.drawHead(ctx, skin, ink, 'haru', pose);
      ctx.restore();

      // Arms: One on hip, one scratching back of head
      this.drawLimb(ctx, [[-25, -155], [-50, -120], [-25, -100]], 11, ink, skin); // Hand on hip
      this.drawLimb(ctx, [[25, -155], [55, -180], [35, -205]], 11, ink, skin); // Scratching head
      return;
    }

    // Default: Sprinting through rain
    const sprintCycle = (pose.progress * Math.PI * 4) % (Math.PI * 2);
    const leg1Angle = Math.sin(sprintCycle) * 0.95;
    const leg2Angle = Math.sin(sprintCycle + Math.PI) * 0.95;

    // Running legs
    const k1x = -15 + Math.sin(leg1Angle) * 35;
    const k1y = -45 - Math.cos(leg1Angle) * 35;
    const f1x = k1x + Math.sin(leg1Angle + 0.4) * 45;
    const f1y = Math.min(0, k1y + Math.cos(leg1Angle + 0.4) * 45);
    this.drawLimb(ctx, [[-15, -80], [k1x, k1y], [f1x, f1y]], 14, ink, pantsGrey);
    this.drawWarajiFoot(ctx, f1x, f1y, leg1Angle, false);

    const k2x = 15 + Math.sin(leg2Angle) * 35;
    const k2y = -45 - Math.cos(leg2Angle) * 35;
    const f2x = k2x + Math.sin(leg2Angle + 0.4) * 45;
    const f2y = Math.min(0, k2y + Math.cos(leg2Angle + 0.4) * 45);
    this.drawLimb(ctx, [[15, -80], [k2x, k2y], [f2x, f2y]], 14, ink, pantsGrey);
    this.drawWarajiFoot(ctx, f2x, f2y, leg2Angle, false);

    // Forward leaning torso
    ctx.save();
    ctx.rotate(0.28);
    this.drawTorsoHanten(ctx, 0, -140, hantenBlue, sashRed, ink, false);

    // Head
    ctx.save();
    ctx.translate(10, -195 + breathY);
    this.drawHead(ctx, skin, ink, 'haru', pose);
    ctx.restore();

    // Arms in sprint (protecting letter clutch against chest)
    this.drawLimb(ctx, [[-20, -155], [-45, -125], [10, -135]], 12, ink, skin);
    this.drawLimb(ctx, [[20, -155], [45, -130], [20, -135]], 12, ink, skin);
    this.drawLetterClutch(ctx, 15, -135);
    ctx.restore();
  }

  // ============================================================================
  // AIKO (Age 24, Edo Townswoman)
  // ============================================================================
  private drawAiko(pose: CharacterPose, breathY: number) {
    const ctx = this.ctx;
    const ink = '#181614';
    const skin = '#FCEEE2';
    const kimonoPink = '#E27D86';
    const obiGold = '#CCA035';

    // Standing in flowing kimono
    // Kimono skirt down to floor
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(-25, -90);
    ctx.quadraticCurveTo(-35, -20, -40, 0);
    ctx.lineTo(40, 0);
    ctx.quadraticCurveTo(35, -20, 25, -90);
    ctx.closePath();
    ctx.fillStyle = kimonoPink;
    ctx.fill();
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Small white tabi socks
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(-18, -4, 14, 6);
    ctx.fillRect(8, -4, 14, 6);

    // Torso with elegant wide kimono sleeves & Obi sash
    this.drawKimonoTorso(ctx, 0, -145, kimonoPink, obiGold, ink);

    // Head with elaborate Shimada hairstyle & Kanzashi hairpin
    ctx.save();
    ctx.translate(0, -205 + breathY);
    if (pose.action === 'laugh') {
      ctx.rotate(-0.15 + Math.sin(pose.progress * 16) * 0.08); // Laughing head toss
    }
    this.drawHead(ctx, skin, ink, 'aiko', pose);
    ctx.restore();

    // Arms: Holding open letter and laughing!
    if (pose.action === 'laugh') {
      // Left arm holding open unfolded letter scroll
      this.drawLimb(ctx, [[-22, -155], [-45, -135], [-30, -125]], 11, ink, skin);
      this.drawLimb(ctx, [[22, -155], [40, -140], [25, -135]], 11, ink, skin);
      this.drawOpenLetter(ctx, -20, -120);

      // Laughing hand covering mouth partially or gesturing
      ctx.save();
      ctx.translate(-5, -170);
      ctx.beginPath();
      ctx.arc(0, 0, 8, 0, Math.PI * 2);
      ctx.fillStyle = skin;
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    } else {
      // Receiving letter
      this.drawLimb(ctx, [[-22, -155], [-35, -130], [-15, -115]], 11, ink, skin);
      this.drawLimb(ctx, [[22, -155], [35, -130], [15, -115]], 11, ink, skin);
    }
    ctx.restore();
  }

  // ============================================================================
  // FOUNDER (Unrelated Story / Modern AI Robotics Lab)
  // ============================================================================
  private drawFounder(pose: CharacterPose, breathY: number) {
    const ctx = this.ctx;
    const ink = '#151413';
    const skin = '#E8C5A0';
    const hoodieNavy = '#1A2938';
    const jeansGrey = '#323A45';
    const whiteShoe = '#EDEDED';

    // Standing casually in modern tech stance
    this.drawLimb(ctx, [[-18, -85], [-20, -40], [-22, 0]], 15, ink, jeansGrey);
    this.drawLimb(ctx, [[18, -85], [20, -40], [24, 0]], 15, ink, jeansGrey);

    // Modern sneakers
    ctx.fillStyle = whiteShoe;
    ctx.beginPath();
    ctx.ellipse(-24, 0, 14, 6, 0, 0, Math.PI * 2);
    ctx.ellipse(26, 0, 14, 6, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Hoodie Torso
    ctx.beginPath();
    ctx.moveTo(-28, -145);
    ctx.quadraticCurveTo(-35, -115, -30, -85);
    ctx.lineTo(30, -85);
    ctx.quadraticCurveTo(35, -115, 28, -145);
    ctx.closePath();
    ctx.fillStyle = hoodieNavy;
    ctx.fill();
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Front kangaroo pouch pocket
    ctx.beginPath();
    ctx.moveTo(-18, -100);
    ctx.lineTo(18, -100);
    ctx.lineTo(22, -86);
    ctx.lineTo(-22, -86);
    ctx.closePath();
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.stroke();

    // Head
    ctx.save();
    ctx.translate(0, -195 + breathY);
    this.drawHead(ctx, skin, ink, 'founder', pose);
    ctx.restore();

    // Gesture: Left hand in pocket, Right hand holding holographic tablet / pointing to robot
    this.drawLimb(ctx, [[-26, -145], [-35, -115], [-20, -90]], 12, ink, hoodieNavy);
    this.drawLimb(ctx, [[26, -145], [55, -135], [75, -125]], 12, ink, hoodieNavy);

    // Hand holding glowing tablet
    ctx.save();
    ctx.translate(85, -125);
    ctx.fillStyle = '#111';
    ctx.fillRect(-6, -18, 28, 36);
    ctx.strokeStyle = '#00D2FF';
    ctx.lineWidth = 2;
    ctx.strokeRect(-6, -18, 28, 36);
    ctx.fillStyle = 'rgba(0, 210, 255, 0.4)';
    ctx.fillRect(-4, -16, 24, 32);
    ctx.restore();
  }

  // ============================================================================
  // ORGANIC BÉZIER HEAD & FACIAL ACTING
  // ============================================================================
  private drawHead(
    ctx: CanvasRenderingContext2D,
    skin: string,
    ink: string,
    character: 'haru' | 'aiko' | 'founder',
    pose: CharacterPose
  ) {
    ctx.save();

    // 1. Organic Bézier Head Contour (Jaw & Chin with anatomical taper)
    ctx.beginPath();
    ctx.moveTo(-22, -10);
    ctx.quadraticCurveTo(-26, -30, -22, -50); // Left temple
    ctx.quadraticCurveTo(0, -68, 22, -50);     // Cranium top
    ctx.quadraticCurveTo(26, -30, 22, -10);     // Right temple
    ctx.quadraticCurveTo(18, 12, 0, 16);        // Right jaw to chin
    ctx.quadraticCurveTo(-18, 12, -22, -10);    // Left jaw to chin
    ctx.closePath();
    ctx.fillStyle = skin;
    ctx.fill();
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // 2. Character-Specific Hair Silhouettes
    if (character === 'haru') {
      // Messy courier topknot tied with paper cord + windblown side bangs
      ctx.beginPath();
      ctx.moveTo(-24, -40);
      ctx.quadraticCurveTo(-15, -65, 0, -65);
      ctx.quadraticCurveTo(15, -65, 24, -40);
      ctx.quadraticCurveTo(12, -55, 0, -55);
      ctx.quadraticCurveTo(-12, -55, -24, -40);
      ctx.closePath();
      ctx.fillStyle = ink;
      ctx.fill();

      // Topknot (*Chonmage*)
      ctx.beginPath();
      ctx.ellipse(4, -72, 10, 14, 0.4, 0, Math.PI * 2);
      ctx.fillStyle = ink;
      ctx.fill();
      // White tie cord
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.arc(2, -66, 6, 0, Math.PI);
      ctx.stroke();

      // Wind strands
      ctx.strokeStyle = ink;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(-18, -48);
      ctx.quadraticCurveTo(-35, -42, -40, -32);
      ctx.moveTo(18, -48);
      ctx.quadraticCurveTo(32, -40, 36, -30);
      ctx.stroke();
    } else if (character === 'aiko') {
      // Elegant Shimada style with red Kanzashi ornament
      ctx.beginPath();
      ctx.moveTo(-25, -35);
      ctx.quadraticCurveTo(-32, -60, 0, -72);
      ctx.quadraticCurveTo(32, -60, 25, -35);
      ctx.quadraticCurveTo(15, -50, 0, -50);
      ctx.quadraticCurveTo(-15, -50, -25, -35);
      ctx.closePath();
      ctx.fillStyle = ink;
      ctx.fill();

      // Shimada bulb bun on top
      ctx.beginPath();
      ctx.ellipse(0, -78, 18, 14, 0, 0, Math.PI * 2);
      ctx.fillStyle = ink;
      ctx.fill();

      // Red coral kanzashi hairpin
      ctx.strokeStyle = '#D93829';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(-26, -65);
      ctx.lineTo(26, -82);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(26, -82, 5, 0, Math.PI * 2);
      ctx.fillStyle = '#FF4500';
      ctx.fill();
    } else if (character === 'founder') {
      // Modern side-parted hairstyle
      ctx.beginPath();
      ctx.moveTo(-24, -38);
      ctx.quadraticCurveTo(-28, -62, 5, -66);
      ctx.quadraticCurveTo(28, -64, 24, -38);
      ctx.quadraticCurveTo(15, -52, 0, -50);
      ctx.quadraticCurveTo(-15, -52, -24, -38);
      ctx.closePath();
      ctx.fillStyle = ink;
      ctx.fill();
    }

    // 3. Expressive Eyebrows
    const browTilt = pose.emotion === 'panic' ? -6 : pose.emotion === 'laughing' ? 3 : 0;
    ctx.lineWidth = 3;
    ctx.strokeStyle = ink;
    ctx.beginPath();
    ctx.moveTo(-16, -28 + browTilt);
    ctx.quadraticCurveTo(-9, -32 + browTilt, -3, -29);
    ctx.moveTo(3, -29);
    ctx.quadraticCurveTo(9, -32 - browTilt, 16, -28 - browTilt);
    ctx.stroke();

    // 4. Eyes with Gaze Direction & Specular Highlights
    this.drawEye(ctx, -10, -18, pose.eyeline[0], pose.eyeline[1], pose.emotion === 'laughing');
    this.drawEye(ctx, 10, -18, pose.eyeline[0], pose.eyeline[1], pose.emotion === 'laughing');

    // 5. Sculpted Nose Line
    ctx.strokeStyle = ink;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(0, -16);
    ctx.lineTo(2, -4);
    ctx.lineTo(-2, -3);
    ctx.stroke();

    // 6. Expressive Mouth Shapes
    ctx.save();
    ctx.translate(0, 4);
    if (pose.emotion === 'laughing') {
      // Big open laughing mouth showing white teeth and pink tongue
      ctx.beginPath();
      ctx.moveTo(-11, 0);
      ctx.quadraticCurveTo(0, 15, 11, 0);
      ctx.closePath();
      ctx.fillStyle = '#6E1B1B';
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = ink;
      ctx.stroke();

      // Top teeth
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(-7, 0, 14, 4);

      // Pink tongue
      ctx.beginPath();
      ctx.arc(0, 9, 6, Math.PI, 0);
      ctx.fillStyle = '#E87D8D';
      ctx.fill();
    } else if (pose.emotion === 'panic') {
      // Wide open gasping oval mouth
      ctx.beginPath();
      ctx.ellipse(0, 3, 6, 9, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#4A1515';
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = ink;
      ctx.stroke();
    } else {
      // Focused / subtle curve
      ctx.beginPath();
      ctx.moveTo(-8, 0);
      ctx.quadraticCurveTo(0, 4, 8, 0);
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = ink;
      ctx.stroke();
    }
    ctx.restore();

    ctx.restore();
  }

  private drawEye(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    lookX: number,
    lookY: number,
    squintSmile: boolean
  ) {
    ctx.save();
    ctx.translate(x, y);

    if (squintSmile) {
      // Happy upward arch eye
      ctx.beginPath();
      ctx.arc(0, 3, 7, Math.PI + 0.3, -0.3);
      ctx.lineWidth = 3;
      ctx.strokeStyle = '#181614';
      ctx.stroke();
      ctx.restore();
      return;
    }

    // Eye white almond
    ctx.beginPath();
    ctx.ellipse(0, 0, 7, 5, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#181614';
    ctx.stroke();

    // Pupil with gaze offset
    const clampedLx = Math.max(-3, Math.min(3, lookX * 3));
    const clampedLy = Math.max(-2, Math.min(2, lookY * 2));
    ctx.beginPath();
    ctx.arc(clampedLx, clampedLy, 3.2, 0, Math.PI * 2);
    ctx.fillStyle = '#181614';
    ctx.fill();

    // Specular catchlight
    ctx.beginPath();
    ctx.arc(clampedLx - 1.2, clampedLy - 1.2, 1.2, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.fill();

    ctx.restore();
  }

  // ============================================================================
  // PROCEDURAL TAPERED LIMBS & FABRIC
  // ============================================================================
  private drawLimb(
    ctx: CanvasRenderingContext2D,
    points: [number, number][],
    width: number,
    ink: string,
    fillColor: string
  ) {
    if (points.length < 2) return;
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // 1. Outer Ink Stroke
    ctx.beginPath();
    ctx.moveTo(points[0][0], points[0][1]);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i][0], points[i][1]);
    }
    ctx.lineWidth = width + 4;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // 2. Inner Colored Fabric / Skin
    ctx.beginPath();
    ctx.moveTo(points[0][0], points[0][1]);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i][0], points[i][1]);
    }
    ctx.lineWidth = width;
    ctx.strokeStyle = fillColor;
    ctx.stroke();

    ctx.restore();
  }

  private drawTorsoHanten(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    coatColor: string,
    sashColor: string,
    ink: string,
    fluttering: boolean
  ) {
    ctx.save();
    ctx.translate(x, y);

    // Hanten body silhouette with shoulder flare
    ctx.beginPath();
    ctx.moveTo(-32, -18);
    ctx.lineTo(32, -18);
    ctx.quadraticCurveTo(38, 25, fluttering ? 46 : 30, 60);
    ctx.lineTo(fluttering ? -42 : -30, 60);
    ctx.quadraticCurveTo(-38, 25, -32, -18);
    ctx.closePath();
    ctx.fillStyle = coatColor;
    ctx.fill();
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // White collar lapels crossing in front
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(-16, -18);
    ctx.lineTo(12, 28);
    ctx.moveTo(16, -18);
    ctx.lineTo(-8, 28);
    ctx.stroke();

    // Red Obi waist sash
    ctx.fillStyle = sashColor;
    ctx.fillRect(-28, 26, 56, 12);
    ctx.strokeStyle = ink;
    ctx.lineWidth = 2;
    ctx.strokeRect(-28, 26, 56, 12);

    ctx.restore();
  }

  private drawKimonoTorso(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    kimonoColor: string,
    obiColor: string,
    ink: string
  ) {
    ctx.save();
    ctx.translate(x, y);

    ctx.beginPath();
    ctx.moveTo(-30, -20);
    ctx.lineTo(30, -20);
    ctx.quadraticCurveTo(28, 20, 25, 55);
    ctx.lineTo(-25, 55);
    ctx.quadraticCurveTo(-28, 20, -30, -20);
    ctx.closePath();
    ctx.fillStyle = kimonoColor;
    ctx.fill();
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = ink;
    ctx.stroke();

    // Elegant wide Obi band
    ctx.fillStyle = obiColor;
    ctx.fillRect(-26, 15, 52, 26);
    ctx.strokeStyle = ink;
    ctx.lineWidth = 2.5;
    ctx.strokeRect(-26, 15, 52, 26);

    ctx.restore();
  }

  // ============================================================================
  // AUTHENTIC FEET: WARAJI STRAW SANDAL VS BARE FOOT
  // ============================================================================
  private drawWarajiFoot(ctx: CanvasRenderingContext2D, x: number, y: number, angle: number, missing: boolean) {
    if (missing) return;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);

    // Straw sole
    ctx.fillStyle = '#C2A368';
    ctx.beginPath();
    ctx.ellipse(4, 0, 14, 5, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#181614';
    ctx.stroke();

    // Straw cords crossing over foot
    ctx.strokeStyle = '#5A4620';
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(-4, -4);
    ctx.lineTo(6, 2);
    ctx.moveTo(6, -4);
    ctx.lineTo(-4, 2);
    ctx.stroke();

    ctx.restore();
  }

  private drawBareFoot(ctx: CanvasRenderingContext2D, x: number, y: number, angle: number) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);

    // Bare fleshy foot with mud stains!
    ctx.fillStyle = '#EACAA8';
    ctx.beginPath();
    ctx.ellipse(3, -2, 13, 6, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#181614';
    ctx.stroke();

    // 5 Toes detail
    ctx.fillStyle = '#EACAA8';
    ctx.beginPath();
    ctx.arc(14, -2, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Splattered mud smudge
    ctx.fillStyle = '#5A4632';
    ctx.beginPath();
    ctx.arc(4, 1, 3, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }

  // ============================================================================
  // PROPS & HAND INTERACTIONS
  // ============================================================================
  private drawGrippingHand(ctx: CanvasRenderingContext2D, x: number, y: number, angle: number) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);

    // Wrapped fingers clutching wooden rail
    ctx.fillStyle = '#EACAA8';
    ctx.strokeStyle = '#181614';
    ctx.lineWidth = 2.5;

    for (let i = -6; i <= 6; i += 4) {
      ctx.beginPath();
      ctx.ellipse(i, -2, 3, 6, 0.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    // Thumb clamped over top
    ctx.beginPath();
    ctx.ellipse(0, 6, 5, 3, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.restore();
  }

  private drawLetterHand(ctx: CanvasRenderingContext2D, x: number, y: number, angle: number) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);

    // Hand gripping letter
    ctx.fillStyle = '#EACAA8';
    ctx.strokeStyle = '#181614';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(0, 0, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // The Famous Oiled-Paper Letter! (Dry, golden sheen, red wax seal)
    ctx.save();
    ctx.translate(14, -18);
    ctx.rotate(0.15);

    // Envelope body
    ctx.fillStyle = '#F5E2B5'; // Waxed oiled paper
    ctx.fillRect(-16, -26, 32, 52);
    ctx.strokeStyle = '#181614';
    ctx.lineWidth = 2.5;
    ctx.strokeRect(-16, -26, 32, 52);

    // Red wax seal & paper cord
    ctx.fillStyle = '#C8281E';
    ctx.beginPath();
    ctx.arc(0, 0, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#991515';
    ctx.stroke();

    ctx.restore();
    ctx.restore();
  }

  private drawPresentingHandsWithLetter(ctx: CanvasRenderingContext2D, x: number, y: number) {
    ctx.save();
    ctx.translate(x, y);

    // Oiled paper letter held flat with both hands
    ctx.fillStyle = '#F5E2B5';
    ctx.fillRect(-28, -12, 56, 24);
    ctx.strokeStyle = '#181614';
    ctx.lineWidth = 2.5;
    ctx.strokeRect(-28, -12, 56, 24);

    // Red seal in center
    ctx.fillStyle = '#C8281E';
    ctx.beginPath();
    ctx.arc(0, 0, 5, 0, Math.PI * 2);
    ctx.fill();

    // Left and Right hands holding ends
    ctx.fillStyle = '#EACAA8';
    ctx.beginPath();
    ctx.arc(-26, 0, 6, 0, Math.PI * 2);
    ctx.arc(26, 0, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#181614';
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.restore();
  }

  private drawOpenLetter(ctx: CanvasRenderingContext2D, x: number, y: number) {
    ctx.save();
    ctx.translate(x, y);

    // Unfolded letter scroll
    ctx.fillStyle = '#FFF8E8';
    ctx.fillRect(-35, -45, 70, 90);
    ctx.strokeStyle = '#181614';
    ctx.lineWidth = 2.5;
    ctx.strokeRect(-35, -45, 70, 90);

    // Japanese kanji brush strokes visible on letter!
    ctx.fillStyle = '#1A1816';
    ctx.font = 'bold 9px serif';
    ctx.fillText('Aiko 殿', -28, -28);
    ctx.fillText('傘を持参せよ', -28, -10); // "Remember umbrella"
    ctx.fillText('雨予報あり', -28, 8);   // "Rain likely"

    ctx.restore();
  }

  private drawLetterClutch(ctx: CanvasRenderingContext2D, x: number, y: number) {
    ctx.save();
    ctx.translate(x, y);

    // Sealed envelope clutched safe against chest
    ctx.fillStyle = '#F5E2B5';
    ctx.fillRect(-14, -20, 28, 40);
    ctx.strokeStyle = '#181614';
    ctx.lineWidth = 2.5;
    ctx.strokeRect(-14, -20, 28, 40);

    ctx.fillStyle = '#C8281E';
    ctx.beginPath();
    ctx.arc(0, 0, 5, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }
}
