/**
 * scene25d.tsx — Motion Canvas scene: 3D world + 2D character layer.
 *
 * The scene takes ONE prop: a `World25DSpec` (built from the scene
 * package by the pipeline, never hardcoded here). The 3D world is
 * rendered by `ThreeWorld25DNode`; the 2D characters are drawn in the
 * Motion Canvas layer on top, positioned each frame from
 * `characterScreenBoxes()` — feet on the ground, head at the projected
 * height, scale from the real camera depth.
 *
 * Character drawing itself is the character engine's job
 * (`UniversalCharacterEngine.ts` / `PremiumStickCharacter.ts`
 * upstream, `animation/character_art.py` + `rig.py` in this repo).
 * This file only places the characters; it does not draw bodies.
 *
 * Duration comes from the timeline (the real voice length), not from
 * a fixed 15s — see the TTS cut-off fix in the V5.1 reconciliation.
 */
import { makeScene2D, useTime } from '@motion-canvas/2d';
import { createRef, Reference } from '@motion-canvas/core';
import { ThreeWorld25DNode } from './ThreeWorld25DNode';
import { World25DSpec } from './World25D';

export interface Scene25DProps {
  spec: World25DSpec;
  durationSeconds: number;
  /** Called every frame with the projected character boxes, so the
   *  caller (character engine) can draw the 2D characters. */
  onCharacterBoxes?: (boxes: Record<string, {
    feetX: number; feetY: number; headY: number;
    heightPx: number; visible: boolean;
  }>) => void;
}

export default makeScene2D(function* (view) {
  const props = view.props as unknown as Scene25DProps;
  const worldRef = createRef<ThreeWorld25DNode>();
  const time = useTime();

  view.add(
    <ThreeWorld25DNode
      ref={worldRef}
      spec={props.spec}
      timeSignal={() => time()}
      width={1920}
      height={1080}
    />,
  );

  // Character layer: positioned from the 3D projection every frame.
  // The actual character drawing is plugged in by the caller via
  // onCharacterBoxes; without it the scene still renders the world,
  // the camera moves and the lights/shadows are real.
  yield* (function* () {
    while (true) {
      const node = worldRef();
      if (node && props.onCharacterBoxes) {
        props.onCharacterBoxes(node.characterScreenBoxes());
      }
      yield;
    }
  })();
});
