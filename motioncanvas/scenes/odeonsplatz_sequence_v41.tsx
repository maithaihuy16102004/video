import { Circle, Line, Node, Rect, Txt, makeScene2D } from '@motion-canvas/2d';
import {
  all,
  chain,
  createRef,
  createSignal,
  easeInCubic,
  easeInOutCubic,
  easeOutCubic,
  linear,
  waitFor,
} from '@motion-canvas/core';
import { ThreeWorldAdapter } from '../three/ThreeWorldAdapter';
import { ThreeWorldNode } from '../three/ThreeWorldNode';
import { StickCharacter } from '../components/StickCharacter';
import { CrowdField } from '../components/CrowdField';
import pkg from '../projects/episode01_package_v41.json';
import { ProductionScenePackageV41 } from '../contract/ProductionScenePackage';

const scenePackage = pkg as unknown as ProductionScenePackageV41;

/**
 * Universal Motion Canvas V4.1: Cinematic Storytelling Sequence (26.50s).
 *
 * Demonstrates:
 * 1. Persistent 3D Odeonsplatz World (Three.js WebGL & Camera Projection).
 * 2. 6 Story-Motivated Camera Viewpoints (Beats A through F).
 * 3. Expressive Data-Driven Stickman Performance (Walk, Slow down, Notice, Look, Approach, Resolve).
 * 4. Dynamic Event-Driven Crowd Field (Passing -> Noticing -> Surging -> Reading -> Cheering).
 * 5. Physical Object Interaction with Mobilization Decree on Litfaßsäule Pillar.
 * 6. Strictly Synchronized Native VietNeu First-Person Narration (1.00x speed, zero atempo).
 */
export default makeScene2D(function* (view) {
  const worldAdapter = new ThreeWorldAdapter(scenePackage.scene_world.threejs_environment);
  const timeSignal = createSignal(0);
  const activeShotIndex = createSignal(1);
  const characterRef = createRef<StickCharacter>();
  const subtitleRef = createRef<Txt>();
  const shotBadgeRef = createRef<Txt>();
  const cameraRigRef = createRef<Node>();

  // 1. Add 3D Architectural Environment (Three.js WebGL adapter)
  const threeNode = new ThreeWorldNode({
    adapter: worldAdapter,
    timeSignal: () => timeSignal(),
    width: 1920,
    height: 1080,
  });

  // Projector helper
  const projectWorld = (pos: [number, number, number]) => worldAdapter.projectToScreen(pos);

  // 2. Crowd Field (Munich Citizens)
  const crowdNode = new CrowdField({
    citizens: scenePackage.crowd_field.citizens,
    timelineStates: scenePackage.crowd_field.timeline_states,
    timeSignal: () => timeSignal(),
    projector: projectWorld,
  });

  // 3. Protagonist StickCharacter (Adolf Hitler 1914)
  const charNode = (
    <StickCharacter
      ref={characterRef}
      actor={scenePackage.actors[0]}
      position={() => {
        const t = timeSignal();
        // Dynamic character world position interpolated across cues
        let charWorldX = -3.0;
        let charWorldZ = 1.2;
        if (t < 5.5) {
          const p = t / 5.5;
          charWorldX = -3.0 + p * 1.2;
          charWorldZ = 1.2 - p * 0.4;
        } else if (t < 11.12) {
          const p = (t - 5.5) / 5.62;
          charWorldX = -1.8 + p * 0.3;
          charWorldZ = 0.8 - p * 0.2;
        } else if (t < 19.5) {
          charWorldX = -1.5;
          charWorldZ = 0.6;
        } else if (t < 23.0) {
          const p = (t - 19.5) / 3.5;
          charWorldX = -1.5 + p * 0.9;
          charWorldZ = 0.6 + p * 0.2;
        } else {
          charWorldX = -0.6;
          charWorldZ = 0.8;
        }
        const proj = projectWorld([charWorldX, 0.0, charWorldZ]);
        return [proj.x, proj.y];
      }}
      scale={() => {
        const t = timeSignal();
        let charWorldX = -3.0;
        let charWorldZ = 1.2;
        if (t < 5.5) {
          const p = t / 5.5;
          charWorldX = -3.0 + p * 1.2;
          charWorldZ = 1.2 - p * 0.4;
        } else if (t < 19.5) {
          charWorldX = -1.5;
          charWorldZ = 0.6;
        } else {
          charWorldX = -0.6;
          charWorldZ = 0.8;
        }
        const proj = projectWorld([charWorldX, 0.0, charWorldZ]);
        return proj.scale;
      }}
    />
  );

  // Assemble Scene Hierarchy
  view.add(
    <Node ref={cameraRigRef}>
      {threeNode}
      {crowdNode}
      {charNode}
    </Node>
  );

  // 4. Subtitle / Retrospective First-Person Narration Overlay
  view.add(
    <Node y={450}>
      <Rect
        width={1460}
        height={72}
        fill={'rgba(16, 15, 14, 0.82)'}
        radius={12}
        stroke={'#786852'}
        lineWidth={1.5}
      />
      <Txt
        ref={subtitleRef}
        text={() => {
          const t = timeSignal();
          if (t < 11.12) {
            return scenePackage.voice_timeline.lines[0]?.text ?? '';
          } else if (t < 11.62) {
            return '...';
          } else {
            return scenePackage.voice_timeline.lines[2]?.text ?? '';
          }
        }}
        fontFamily={'Segoe UI, sans-serif'}
        fontSize={22}
        fontWeight={700}
        fill={'#F7F3EA'}
      />
    </Node>
  );

  // 5. Cinematic Telemetry & Beat Indicator HUD
  view.add(
    <Node x={-640} y={-470}>
      <Rect
        width={540}
        height={54}
        fill={'rgba(18, 22, 26, 0.88)'}
        radius={8}
        stroke={'#E6C875'}
        lineWidth={1.5}
      />
      <Txt
        ref={shotBadgeRef}
        text={() => {
          const idx = activeShotIndex();
          const shot = scenePackage.shots[idx - 1];
          return `SHOT ${idx}/6: ${shot?.beat_id ?? 'BEAT'} · ${shot?.shot_type ?? ''}`;
        }}
        fontFamily={'Segoe UI, sans-serif'}
        fontSize={13}
        fontWeight={800}
        fill={'#E6C875'}
      />
    </Node>
  );

  // Top-Right Telemetry
  view.add(
    <Node x={660} y={-470}>
      <Rect
        width={500}
        height={54}
        fill={'rgba(18, 22, 26, 0.88)'}
        radius={8}
        stroke={'#58789A'}
        lineWidth={1.2}
      />
      <Txt
        text={() => `V4.1 CINEMATIC STORY SEQUENCE · t = ${timeSignal().toFixed(1)}s / 26.5s`}
        fontFamily={'Segoe UI, sans-serif'}
        fontSize={13}
        fontWeight={700}
        fill={'#8BB5E8'}
      />
    </Node>
  );

  // 6. Execute 26.50-Second Multi-Shot Sequence
  // Shot 1: Beat A [0.0s – 5.5s] - Wide Environmental Establishing Tracking
  activeShotIndex(1);
  yield* all(
    timeSignal(5.5, 5.5, linear),
    characterRef().walkPhase(Math.PI * 6, 5.5, linear),
    characterRef().torsoLean(4, 1.2, easeInOutCubic)
  );

  // Shot 2: Beat B [5.5s – 11.12s] - Medium Information Insert Tracking
  activeShotIndex(2);
  yield* all(
    timeSignal(11.12, 5.62, linear),
    characterRef().walkPhase(Math.PI * 7.5, 2.5, easeOutCubic),
    characterRef().torsoLean(0, 2.0, easeInOutCubic)
  );

  // Shot 3: Beat C [11.12s – 15.5s] - Mid-Wide Crowd Field Surge
  activeShotIndex(3);
  yield* all(
    timeSignal(15.5, 4.38, linear),
    characterRef().headTurn(0.18, 1.8, easeOutCubic),
    characterRef().eyelineOffset(1.0, 1.5, easeOutCubic)
  );

  // Shot 4: Beat D [15.5s – 19.5s] - Protagonist Reaction Low-Angle
  activeShotIndex(4);
  yield* all(
    timeSignal(19.5, 4.0, linear),
    characterRef().torsoLean(8, 2.0, easeInOutCubic),
    characterRef().headTurn(0.24, 2.0, easeInOutCubic)
  );

  // Shot 5: Beat E [19.5s – 23.0s] - Over-The-Shoulder Decision Inspection
  activeShotIndex(5);
  yield* all(
    timeSignal(23.0, 3.5, linear),
    characterRef().walkPhase(Math.PI * 9.5, 2.0, easeInOutCubic),
    characterRef().torsoLean(12, 2.5, easeInOutCubic)
  );

  // Shot 6: Beat F [23.0s – 26.5s] - Heroic Perspective Monumental Resolution
  activeShotIndex(6);
  yield* all(
    timeSignal(26.5, 3.5, linear),
    characterRef().torsoLean(-4, 1.8, easeInOutCubic),
    characterRef().headTurn(-0.06, 1.8, easeInOutCubic)
  );

  yield* waitFor(0.5);
});
