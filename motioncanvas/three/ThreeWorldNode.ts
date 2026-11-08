import { Node, NodeProps } from '@motion-canvas/2d';
import { ThreeWorldAdapter } from './ThreeWorldAdapter';

export interface ThreeWorldNodeProps extends NodeProps {
  adapter: ThreeWorldAdapter;
  timeSignal: () => number;
  width?: number;
  height?: number;
}

/**
 * ThreeWorldNode: Bridges Three.js 3D WebGL Rendering directly into Motion Canvas 2D Scene Graph.
 *
 * Renders the 3D Odeonsplatz loggia, cobblestone plaza, and lighting into the scene
 * with synchronized camera animation per frame.
 */
export class ThreeWorldNode extends Node {
  private adapter: ThreeWorldAdapter;
  private timeSignal: () => number;
  private offscreenCanvas?: HTMLCanvasElement;
  private canvasWidth: number;
  private canvasHeight: number;

  public constructor(props: ThreeWorldNodeProps) {
    super(props);
    this.adapter = props.adapter;
    this.timeSignal = props.timeSignal;
    this.canvasWidth = props.width ?? 1920;
    this.canvasHeight = props.height ?? 1080;

    if (typeof document !== 'undefined') {
      this.offscreenCanvas = document.createElement('canvas');
      this.offscreenCanvas.width = this.canvasWidth;
      this.offscreenCanvas.height = this.canvasHeight;
    }
  }

  protected override draw(context: CanvasRenderingContext2D): void {
    if (this.offscreenCanvas) {
      const t = this.timeSignal();
      this.adapter.updateCamera(t);
      this.adapter.render(this.offscreenCanvas);
      context.drawImage(
        this.offscreenCanvas,
        -this.canvasWidth / 2,
        -this.canvasHeight / 2,
        this.canvasWidth,
        this.canvasHeight
      );
    }
    this.drawChildren(context);
  }
}
