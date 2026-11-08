import { Circle, Line, Node, NodeProps, Rect } from '@motion-canvas/2d';
import { SimpleSignal, createSignal } from '@motion-canvas/core';
import { CitizenEntity, CrowdTimelineState } from '../contract/ProductionScenePackage';

export interface CrowdFieldProps extends NodeProps {
  citizens: CitizenEntity[];
  timelineStates: CrowdTimelineState[];
  pillarWorldPos?: [number, number, number];
  timeSignal: () => number;
  projector: (worldPos: [number, number, number]) => { x: number; y: number; z: number; scale: number };
}

/**
 * CrowdField: Dynamic Event-Driven Crowd of Munich Citizens for Motion Canvas V4.1.
 *
 * Implements seeded variations in height, costume, hat style, and dynamic convergence
 * toward the Litfaßsäule notice pillar driven by story events.
 */
export class CrowdField extends Node {
  private citizensData: CitizenEntity[];
  private states: CrowdTimelineState[];
  private pillarPos: [number, number, number];
  private timeGetter: () => number;
  private projectWorld: (worldPos: [number, number, number]) => { x: number; y: number; z: number; scale: number };

  public constructor(props: CrowdFieldProps) {
    super(props);
    this.citizensData = props.citizens;
    this.states = props.timelineStates;
    this.pillarPos = props.pillarWorldPos ?? [3.2, 0.0, 1.8];
    this.timeGetter = props.timeSignal;
    this.projectWorld = props.projector;

    this.buildCitizens();
  }

  private buildCitizens() {
    for (const cit of this.citizensData) {
      const citNode = new Node({
        position: () => {
          const t = this.timeGetter();
          const pos = this.getCitizenPosition(cit, t);
          const proj = this.projectWorld(pos);
          return [proj.x, proj.y];
        },
        scale: () => {
          const t = this.timeGetter();
          const pos = this.getCitizenPosition(cit, t);
          const proj = this.projectWorld(pos);
          return proj.scale * (cit.height_px / 180.0);
        },
      });

      // Ground shadow
      citNode.add(
        new Circle({
          x: 0,
          y: 0,
          width: 50,
          height: 12,
          fill: 'rgba(10, 10, 10, 0.40)',
        })
      );

      const h = cit.height_px;
      const legH = h * 0.45;
      const torsoH = h * 0.35;
      const headR = (h * 0.20) / 2;
      const ink = '#151413';

      // Legs
      citNode.add(
        new Line({
          points: [
            [-8, -legH],
            [-10, -legH * 0.5],
            [-9, 0],
          ],
          stroke: ink,
          lineWidth: 3.5,
          lineCap: 'round',
        })
      );
      citNode.add(
        new Line({
          points: [
            [8, -legH],
            [10, -legH * 0.5],
            [11, 0],
          ],
          stroke: ink,
          lineWidth: 3.5,
          lineCap: 'round',
        })
      );

      // Torso / Overcoat
      citNode.add(
        new Line({
          points: [
            [-14, -(legH + torsoH)],
            [14, -(legH + torsoH)],
            [16, -legH + 8],
            [-16, -legH + 8],
          ],
          fill: cit.color,
          stroke: ink,
          lineWidth: 2.0,
          closed: true,
        })
      );

      // Arms
      citNode.add(
        new Line({
          points: [
            [-12, -(legH + torsoH - 2)],
            [-18, -(legH + torsoH * 0.5)],
            [-14, -legH],
          ],
          stroke: ink,
          lineWidth: 3.0,
          lineCap: 'round',
        })
      );
      citNode.add(
        new Line({
          points: [
            [12, -(legH + torsoH - 2)],
            [18, -(legH + torsoH * 0.5)],
            [14, -legH],
          ],
          stroke: ink,
          lineWidth: 3.0,
          lineCap: 'round',
        })
      );

      // Head
      const headCenterY = -(legH + torsoH + headR + 2);
      citNode.add(
        new Circle({
          x: 0,
          y: headCenterY,
          width: headR * 2,
          height: headR * 2.2,
          fill: '#E0C2A0',
          stroke: ink,
          lineWidth: 2.2,
        })
      );

      // Hat Style
      if (cit.hat === 'BOWLER') {
        // Bowler hat dome & brim
        citNode.add(
          new Circle({
            x: 0,
            y: headCenterY - headR * 0.6,
            width: headR * 2.1,
            height: headR * 1.5,
            fill: '#1A1A1A',
          })
        );
        citNode.add(
          new Line({
            points: [[-headR * 1.3, headCenterY - headR * 0.1], [headR * 1.3, headCenterY - headR * 0.1]],
            stroke: '#1A1A1A',
            lineWidth: 2.5,
          })
        );
      } else if (cit.hat === 'CAP') {
        // Flat cloth worker cap
        citNode.add(
          new Rect({
            x: 1,
            y: headCenterY - headR * 0.7,
            width: headR * 2.2,
            height: headR * 0.8,
            radius: 3,
            fill: '#34302C',
          })
        );
        citNode.add(
          new Line({
            points: [[0, headCenterY - headR * 0.4], [headR * 1.4, headCenterY - headR * 0.3]],
            stroke: '#1A1A1A',
            lineWidth: 2.5,
          })
        );
      } else if (cit.hat === 'OFFICER' || cit.hat === 'PICKELHAUBE') {
        // Officer peaked / spiked helmet
        citNode.add(
          new Circle({
            x: 0,
            y: headCenterY - headR * 0.7,
            width: headR * 1.9,
            height: headR * 1.4,
            fill: '#242F28',
          })
        );
        citNode.add(
          new Line({
            points: [[0, headCenterY - headR * 1.3], [0, headCenterY - headR * 1.9]],
            stroke: '#D4AF37', // Gold brass spike
            lineWidth: 2.5,
          })
        );
      }

      this.add(citNode);
    }
  }

  private getCitizenPosition(cit: CitizenEntity, t: number): [number, number, number] {
    const px = this.pillarPos[0];
    const pz = this.pillarPos[2];

    if (t < 5.5) {
      // Phase 1: Unhurried passing
      return [cit.base_x, 0.0, cit.base_z];
    } else if (t < 11.12) {
      // Phase 2: Noticing / slowing down
      return [cit.base_x, 0.0, cit.base_z];
    } else if (t < 15.5) {
      // Phase 3: Surging / converging toward pillar
      const alpha = Math.min(1.0, (t - 11.12) / 3.5);
      const ease = alpha * alpha * (3 - 2 * alpha);
      const targetX = px + (cit.base_x - px) * 0.45;
      const targetZ = pz + (cit.base_z - pz) * 0.45;
      return [cit.base_x + (targetX - cit.base_x) * ease, 0.0, cit.base_z + (targetZ - cit.base_z) * ease];
    } else {
      // Phase 4-6: Clustered around pillar
      const targetX = px + (cit.base_x - px) * 0.40;
      const targetZ = pz + (cit.base_z - pz) * 0.40;
      return [targetX, 0.0, targetZ];
    }
  }
}
