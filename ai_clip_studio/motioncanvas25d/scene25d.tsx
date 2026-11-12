/**
 * scene25d.tsx — Motion Canvas scene: 3D world + 2D character layer.
 *
 * The scene takes ONE input: a `World25DSpec` (built from the scene
 * package by the pipeline's spec emitter,
 * `ai_clip_studio/motioncanvas_spec.py`, never hardcoded here) plus
 * the scene duration in seconds. Motion Canvas scenes have no props
 * mechanism (`makeScene2D` takes only a runner, and `View2D` has no
 * `props`), so the spec is supplied through `configureScene25D`,
 * called from the Motion Canvas project file before the scene runs:
 *
 *   import scene25d, { configureScene25D } from './scene25d';
 *   import specJson from './world25d_spec.json'; // one scene spec
 *   configureScene25D({
 *     spec: specJson.world,
 *     durationSeconds: specJson.duration_seconds,
 *   });
 *   export default makeProject({ scenes: [scene25d] });
 *
 * The 3D world is rendered by `ThreeWorld25DNode`; the 2D characters
 * are drawn in the Motion Canvas layer on top, positioned each frame
 * from `characterScreenBoxes()` — feet on the ground, head at the
 * projected height, scale from the real camera depth. Time is driven
 * by a signal tweened over the scene duration (the upstream pattern:
 * `timeSignal(duration, duration)`), so the scene ends exactly at
 * `durationSeconds` and the world node reads the current time every
 * frame.
 *
 * Character drawing itself is the character engine's job
 * (`UniversalCharacterEngine.ts` / `PremiumStickCharacter.ts`
 * upstream, `animation/character_art.py` + `rig.py` in this repo).
 * This file only places the characters; it does not draw bodies.
 * The optional `onCharacterBoxes` callback receives the projected
 * boxes every frame (invoked by the node during draw, in sync with
 * the rendered camera state) so the caller can draw the characters.
 *
 * Duration comes from the timeline (the real voice length), not from
 * a fixed 15s — see the TTS cut-off fix in the V5.1 reconciliation.
 */
import { makeScene2D } from '@motion-canvas/2d';
import { createSignal } from '@motion-canvas/core';
import { ThreeWorld25DNode } from './ThreeWorld25DNode';
import { CharacterScreenBox, World25DSpec } from './World25D';

export interface Scene25DProps {
  spec: World25DSpec;
  durationSeconds: number;
  /** Called every frame with the projected character boxes, so the
   *  caller (character engine) can draw the 2D characters. */
  onCharacterBoxes?: (boxes: Record<string, CharacterScreenBox>) => void;
}

let activeProps: Scene25DProps | null = null;

/**
 * Supply the spec + duration this scene renders. Must be called from
 * the Motion Canvas project file before the scene runs; the scene
 * throws a clear error if it was never configured, instead of
 * rendering a hardcoded world.
 */
export function configureScene25D(props: Scene25DProps): void {
  if (!props || !props.spec) {
    throw new Error(
      'scene25d: configureScene25D requires a World25DSpec (props.spec).',
    );
  }
  if (!(props.durationSeconds > 0)) {
    throw new Error(
      'scene25d: configureScene25D requires durationSeconds > 0 '
      + `(got ${props.durationSeconds}).`,
    );
  }
  activeProps = props;
}

export default makeScene2D(function* (view) {
  if (!activeProps) {
    throw new Error(
      'scene25d: configureScene25D({spec, durationSeconds}) must be '
      + 'called from the Motion Canvas project file before this scene '
      + 'runs. The spec comes from the pipeline (world25d_spec.json); '
      + 'this scene never hardcodes one.',
    );
  }
  const props = activeProps;
  const timeSignal = createSignal(0);

  view.add(
    <ThreeWorld25DNode
      spec={props.spec}
      timeSignal={() => timeSignal()}
      width={1920}
      height={1080}
      onCharacterBoxes={props.onCharacterBoxes}
    />,
  );

  // Drive the world clock from 0 to the real scene duration, then
  // end. Without the tween the scene would never terminate; with it
  // the render lasts exactly durationSeconds at any project fps.
  // The 3D world renders even without onCharacterBoxes: the camera
  // moves (or cuts, per the spec's keyframes) and the lights/shadows
  // are real; only the 2D character layer is absent.
  yield* timeSignal(props.durationSeconds, props.durationSeconds);
});
