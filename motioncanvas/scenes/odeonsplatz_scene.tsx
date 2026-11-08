import { makeScene2D, Node, Rect, Txt, Circle } from '@motion-canvas/2d';
import {
  all,
  createRef,
  createSignal,
  easeInOutCubic,
  waitFor,
} from '@motion-canvas/core';
import { ThreeWorldAdapter } from '../three/ThreeWorldAdapter';
import { ThreeWorldNode } from '../three/ThreeWorldNode';
import { StickCharacter } from '../components/StickCharacter';
import pkg from '../projects/episode01_package.json';
import { ProductionScenePackage } from '../contract/ProductionScenePackage';

const scenePackage = pkg as unknown as ProductionScenePackage;

/**
 * Universal Motion Canvas Scene: Munich Odeonsplatz 1914 Proof Scene.
 *
 * Demonstrates:
 * 1. 3D Architectural World (Three.js WebGL): Neoclassical Feldherrnhalle loggia with Florentine arches.
 * 2. 2D Research-Grounded StickCharacter: 1914 Hitler with 28% head ratio, dark frock coat, Kaiser mustache.
 * 3. Grounded Contact: Character stands firmly on cobblestones while camera smoothly pans in 3D perspective.
 * 4. Zero Background Re-Drawing on camera cuts.
 * 5. Native VietNeu First-Person Narration timing (11.12s, 1.00x native tempo).
 */
export default makeScene2D(function* (view) {
  const worldAdapter = new ThreeWorldAdapter(scenePackage.scene_world.threejs_environment);
  const timeSignal = createSignal(0);
  const characterRef = createRef<StickCharacter>();
  const captionRef = createRef<Txt>();
  const cameraRef = createRef<Node>();

  // 1. Add 3D Architectural Environment (Three.js WebGL adapter)
  const threeNode = new ThreeWorldNode({
    adapter: worldAdapter,
    timeSignal: () => timeSignal(),
    width: 1920,
    height: 1080,
  });

  // 2. Camera Rig Node
  view.add(
    <Node ref={cameraRef}>
      {threeNode}
      {/* 3. Research-Grounded 2D StickCharacter planted on ground plane (y=280 in centered canvas) */}
      <StickCharacter
        ref={characterRef}
        actor={scenePackage.actors[0]}
        x={-280}
        y={280}
        scale={1.45}
      />
    </Node>
  );

  // 4. Subtitle / Retrospective First-Person Narration Overlay
  view.add(
    <Node y={440}>
      <Rect
        width={1400}
        height={64}
        fill={'rgba(18, 17, 16, 0.78)'}
        radius={12}
        stroke={'#786955'}
        lineWidth={1.5}
      />
      <Txt
        ref={captionRef}
        text={scenePackage.voice_timeline.lines?.[0]?.text ?? (scenePackage.voice_timeline as any).text ?? ''}
        fontFamily={'Segoe UI, sans-serif'}
        fontSize={22}
        fontWeight={700}
        fill={'#F5F0E6'}
      />
    </Node>
  );

  // 5. Watermark / Historical Research Badge
  view.add(
    <Node x={-720} y={-480}>
      <Rect
        width={380}
        height={42}
        fill={'rgba(20, 24, 28, 0.85)'}
        radius={8}
        stroke={'#4A5A6A'}
        lineWidth={1}
      />
      <Txt
        text={'ODEONSPLATZ 1914 · 3D WORLD + STICKMAN V4'}
        fontFamily={'Segoe UI, sans-serif'}
        fontSize={13}
        fontWeight={800}
        fill={'#E6C875'}
      />
    </Node>
  );

  // 6. Execute 11.12-second cinematic sequence
  // Cinematic 3D camera pan & smooth character stance shift
  yield* all(
    // Animate time signal for Three.js 3D perspective camera interpolation
    timeSignal(11.12, 11.12, easeInOutCubic),

    // Camera rig subtle parallax tracking
    cameraRef().position.x(60, 11.12, easeInOutCubic),
    cameraRef().scale(1.08, 11.12, easeInOutCubic),

    // Character performance progression
    (function* () {
      // Phase 1 (0s - 3.8s): Solitary bohemian contemplation
      yield* waitFor(3.8);

      // Phase 2 (3.8s - 7.5s): Subtle reflective lean forward as voiceover reflects
      yield* all(
        characterRef().position.x(-260, 1.2, easeInOutCubic),
        characterRef().rotation(2, 1.2, easeInOutCubic)
      );
      yield* waitFor(2.5);

      // Phase 3 (7.5s - 11.12s): Stance firms as narrator faces urban reality
      yield* all(
        characterRef().position.x(-250, 1.5, easeInOutCubic),
        characterRef().rotation(-1, 1.5, easeInOutCubic)
      );
    })()
  );

  yield* waitFor(0.5);
});
