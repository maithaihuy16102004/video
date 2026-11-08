import {
  Circle,
  Line,
  Node,
  NodeProps,
  Rect,
} from '@motion-canvas/2d';
import { SimpleSignal, createSignal } from '@motion-canvas/core';
import { ActorEntity } from '../contract/ProductionScenePackage';

export interface StickCharacterProps extends NodeProps {
  actor: ActorEntity;
  groundY?: number;
  initialAction?: string;
}

/**
 * StickCharacter: Generic Data-Driven Illustrated Stickman for Motion Canvas V4 / V4.1.
 *
 * Implements strict Character Master Bible proportions (25-32% head-to-body ratio).
 * Supports continuous kinematic walk cycles, head turns, torso lean, and prop clutching.
 * Renders 1914 archival traits (Kaiser handlebar mustache, dark frock coat, cardboard portfolio).
 */
export class StickCharacter extends Node {
  public readonly action: SimpleSignal<string>;
  public readonly walkPhase: SimpleSignal<number>;
  public readonly torsoLean: SimpleSignal<number>;
  public readonly headTurn: SimpleSignal<number>;
  public readonly eyelineOffset: SimpleSignal<number>;

  private actorData: ActorEntity;

  public constructor(props: StickCharacterProps) {
    super(props);
    this.actorData = props.actor;
    this.action = createSignal(props.initialAction ?? 'idle');
    this.walkPhase = createSignal(0);
    this.torsoLean = createSignal(0);
    this.headTurn = createSignal(0);
    this.eyelineOffset = createSignal(0);

    const dna = this.actorData.dna;
    const prop = this.actorData.proportions;
    const headR = prop.head_diameter_px / 2;
    const bodyH = prop.total_standing_height_px;
    const ink = '#151413';
    const skin = '#E8C8A6';
    const coatColor = dna.costume.frock_coat_color;

    // 1. Cast shadow on ground plane
    this.add(
      new Circle({
        x: 0,
        y: 0,
        width: 105,
        height: 18,
        fill: 'rgba(12, 11, 10, 0.50)',
      })
    );

    // 2. Dynamic Legs (Animated by walkPhase signal)
    const hipY = -bodyH * 0.46;
    const kneeY = -bodyH * 0.23;
    const footY = 0;

    // Left leg (with stride kinematics)
    this.add(
      new Line({
        points: () => {
          const ph = this.walkPhase();
          const stride = Math.sin(ph) * 16;
          const lift = Math.max(0, -Math.sin(ph)) * 6;
          return [
            [-14, hipY],
            [-16 - stride * 0.5, kneeY - lift * 0.5],
            [-14 - stride, footY - lift],
            [-4 - stride, footY - lift],
          ];
        },
        stroke: ink,
        lineWidth: prop.limb_width_px,
        lineCap: 'round',
        lineJoin: 'round',
      })
    );

    // Right leg
    this.add(
      new Line({
        points: () => {
          const ph = this.walkPhase();
          const stride = Math.sin(ph + Math.PI) * 16;
          const lift = Math.max(0, -Math.sin(ph + Math.PI)) * 6;
          return [
            [14, hipY],
            [18 - stride * 0.5, kneeY - lift * 0.5],
            [16 - stride, footY - lift],
            [30 - stride, footY - lift],
          ];
        },
        stroke: ink,
        lineWidth: prop.limb_width_px,
        lineCap: 'round',
        lineJoin: 'round',
      })
    );

    // 3. Torso / Bohemian Frock Coat (Responsive to torsoLean)
    const shoulderY = -bodyH * 0.78;
    this.add(
      new Line({
        points: () => {
          const lean = this.torsoLean();
          return [
            [-22 + lean, shoulderY],
            [22 + lean, shoulderY],
            [26 + lean * 0.5, hipY + 14],
            [-26 + lean * 0.5, hipY + 14],
          ];
        },
        fill: coatColor,
        stroke: ink,
        lineWidth: 2.6,
        closed: true,
      })
    );

    // White shirt collar & dark cravat
    this.add(
      new Line({
        points: () => {
          const lean = this.torsoLean();
          return [
            [-8 + lean, shoulderY],
            [lean, shoulderY + 14],
            [8 + lean, shoulderY],
          ];
        },
        stroke: dna.costume.collar_color,
        lineWidth: 2.4,
      })
    );
    this.add(
      new Line({
        points: () => {
          const lean = this.torsoLean();
          return [
            [lean, shoulderY + 4],
            [lean, shoulderY + 22],
          ];
        },
        stroke: dna.costume.cravat_color,
        lineWidth: 3.5,
      })
    );

    // 4. Arms & Hand-Held Prop
    // Left arm holding artist portfolio tucked under arm
    this.add(
      new Line({
        points: () => {
          const lean = this.torsoLean();
          return [
            [-20 + lean, shoulderY + 4],
            [-34 + lean, shoulderY + 36],
            [-24 + lean, shoulderY + 60],
          ];
        },
        stroke: ink,
        lineWidth: prop.limb_width_px,
        lineCap: 'round',
        lineJoin: 'round',
      })
    );

    // Cardboard artist portfolio tucked under left arm
    if (this.actorData.staging.hand_held_prop) {
      const p = this.actorData.staging.hand_held_prop;
      this.add(
        new Rect({
          x: () => -28 + this.torsoLean(),
          y: shoulderY + 56,
          width: p.width,
          height: p.height,
          rotation: 14,
          fill: p.color,
          stroke: ink,
          lineWidth: 2.2,
          radius: 3,
        })
      );
    }

    // Right arm (gestural / swinging with walk)
    this.add(
      new Line({
        points: () => {
          const lean = this.torsoLean();
          const ph = this.walkPhase();
          const swing = Math.sin(ph) * 12;
          return [
            [20 + lean, shoulderY + 4],
            [32 + lean + swing, shoulderY + 32],
            [24 + lean + swing * 1.3, shoulderY + 56],
          ];
        },
        stroke: ink,
        lineWidth: prop.limb_width_px,
        lineCap: 'round',
        lineJoin: 'round',
      })
    );

    // 5. Head Rig (Responsive to headTurn and eyelineOffset)
    const headCenterY = shoulderY - headR - 6;
    const headGroup = new Node({
      position: () => [this.torsoLean(), headCenterY],
      rotation: () => this.headTurn() * (180 / Math.PI),
    });

    // Face oval
    headGroup.add(
      new Circle({
        x: 0,
        y: 0,
        width: headR * 2,
        height: headR * 2.2,
        fill: skin,
        stroke: ink,
        lineWidth: 3.4,
      })
    );

    // Hair Silhouette (Variant based on dna.hair_style)
    if (dna.hair_style === 'DISHEVELED_CURLS') {
      headGroup.add(
        new Line({
          points: [
            [-headR * 1.1, -headR * 0.2],
            [-headR * 0.8, -headR * 1.2],
            [0, -headR * 1.3],
            [headR * 0.8, -headR * 1.2],
            [headR * 1.1, -headR * 0.2],
            [headR * 0.7, -headR * 0.4],
            [0, -headR * 0.5],
            [-headR * 0.7, -headR * 0.4],
          ],
          fill: dna.hair_color,
          stroke: ink,
          lineWidth: 2.2,
          closed: true,
        })
      );
    } else if (dna.hair_style === 'MILITARY_CROP') {
      headGroup.add(
        new Line({
          points: [
            [-headR * 0.95, -headR * 0.3],
            [-headR * 0.8, -headR * 1.0],
            [0, -headR * 1.05],
            [headR * 0.8, -headR * 1.0],
            [headR * 0.95, -headR * 0.3],
            [0, -headR * 0.6],
          ],
          fill: dna.hair_color,
          stroke: ink,
          lineWidth: 2.0,
          closed: true,
        })
      );
    } else {
      // Default side-parted forehead sweep (1914 archival)
      headGroup.add(
        new Line({
          points: [
            [-headR + 2, -headR * 0.4],
            [-headR * 0.4, -headR * 1.1],
            [headR * 0.6, -headR * 0.9],
            [headR * 0.8, -headR * 0.2],
            [headR * 0.2, -headR * 0.3],
            [-headR * 0.6, 2],
          ],
          fill: dna.hair_color,
          stroke: ink,
          lineWidth: 2.2,
          closed: true,
        })
      );
    }

    // Deep-set Intense Eyes
    headGroup.add(
      new Circle({
        x: () => 6 + this.eyelineOffset() * 8,
        y: -4,
        width: 5,
        height: 5,
        fill: ink,
      })
    );

    // Facial Hair / Mustache (Rendered only if specified)
    if (dna.facial_hair !== 'NONE' && dna.facial_hair !== 'CLEAN_SHAVEN') {
      headGroup.add(
        new Line({
          points: [
            [1, 12],
            [6, 15],
            [16, 12],
            [20, 7],
          ],
          stroke: dna.hair_color,
          lineWidth: 3.6,
          lineCap: 'round',
        })
      );
    }

    this.add(headGroup);
  }
}
