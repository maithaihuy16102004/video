/**
 * ThreeWorld25DNode — Motion Canvas 2D node that hosts the Three.js world.
 *
 * Same bridge pattern as upstream `motioncanvas/three/ThreeWorldNode.ts`:
 * the adapter renders WebGL into an offscreen canvas once per frame,
 * and this node draws that canvas into the Motion Canvas 2D scene graph
 * (so 2D stickman characters, drawn by the character engine in the 2D
 * layer, can stand on top of the 3D world at the projected positions
 * from `World25D.characterScreenBoxes()`).
 *
 * The scene that uses this node is `scene25d.tsx`.
 */
import { Node, NodeProps } from '@motion-canvas/2d';
import { World25D, World25DSpec } from './World25D';

export interface ThreeWorld25DNodeProps extends NodeProps {
  spec: World25DSpec;
  timeSignal: () => number;
  width?: number;
  height?: number;
}

export class ThreeWorld25DNode extends Node {
  private world: World25D;
  private timeSignal: () => number;
  private offscreenCanvas?: HTMLCanvasElement;
  private canvasWidth: number;
  private canvasHeight: number;

  public constructor(props: ThreeWorld25DNodeProps) {
    super(props);
    this.world = new World25D(props.spec, props.width ?? 1920, props.height ?? 1080);
    this.timeSignal = props.timeSignal;
    this.canvasWidth = props.width ?? 1920;
    this.canvasHeight = props.height ?? 1080;

    if (typeof document !== 'undefined') {
      this.offscreenCanvas = document.createElement('canvas');
      this.offscreenCanvas.width = this.canvasWidth;
      this.offscreenCanvas.height = this.canvasHeight;
    }
  }

  public characterScreenBoxes() {
    return this.world.characterScreenBoxes();
  }

  protected override draw(context: CanvasRenderingContext2D): void {
    if (this.offscreenCanvas) {
      const t = this.timeSignal();
      this.world.updateCamera(t);
      this.world.render(this.offscreenCanvas);
      context.drawImage(
        this.offscreenCanvas,
        -this.canvasWidth / 2,
        -this.canvasHeight / 2,
        this.canvasWidth,
        this.canvasHeight,
      );
    }
    this.drawChildren(context);
  }
}
