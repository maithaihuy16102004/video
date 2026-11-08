import {
  Circle,
  Line,
  Node,
  NodeProps,
  Rect,
  Txt,
} from '@motion-canvas/2d';
import { SimpleSignal, createSignal } from '@motion-canvas/core';

export interface MapPin {
  id: string;
  name: string;
  coords: [number, number];  // screen canvas [x, y]
  isCapital?: boolean;
}

export interface MarchRoute {
  id: string;
  label: string;
  points: [number, number][];
  color: string;
}

export interface HistoricalMapSceneProps extends NodeProps {
  eraLabel?: string;
  pins?: MapPin[];
  routes?: MarchRoute[];
}

/**
 * HistoricalMapScene: Reusable Cinematic Map Animation Component for V4.2.
 *
 * Implements:
 * - Animated route reveals with line progress signals
 * - Geographic pin highlights and territory boundary lines
 * - Period-authentic styling (Parchment map / military tactical styling)
 * - Coherent typography and safe zones
 */
export class HistoricalMapScene extends Node {
  public readonly routeProgress: SimpleSignal<number>;
  public readonly mapScale: SimpleSignal<number>;

  public constructor(props: HistoricalMapSceneProps) {
    super(props);
    this.routeProgress = createSignal(0);
    this.mapScale = createSignal(1.0);

    // Map parchment base
    const base = new Rect({
      width: 1400,
      height: 750,
      fill: '#D8CEBE',
      stroke: '#4A3E2D',
      lineWidth: 3,
      radius: 6,
    });
    this.add(base);

    // Border grid lines (lat/long styling)
    const grid = new Line({
      points: [
        [-650, -320], [650, -320],
        [650, 320], [-650, 320],
        [-650, -320],
      ],
      stroke: 'rgba(74, 62, 45, 0.4)',
      lineWidth: 1.5,
    });
    this.add(grid);

    // Era Title
    const title = new Txt({
      x: 0,
      y: -330,
      text: props.eraLabel ?? 'THEATRE OF WAR · CENTRAL EUROPE AUGUST 1914',
      fill: '#2B2319',
      fontSize: 16,
      fontWeight: 800,
      fontFamily: 'Georgia, serif',
    });
    this.add(title);

    // Render Routes
    const sampleRoutes = props.routes ?? [
      {
        id: 'ROUTE_16TH_BAVARIAN',
        label: '16th Bavarian Reserve Deployment: Munich -> Lille -> Ypres',
        points: [
          [-280, 160],   // Munich
          [-120, 40],    // Nuremberg
          [-30, -80],    // Frankfurt
          [140, -180],   // Cologne
          [360, -220],   // Lille / Ypres Front
        ],
        color: '#8B263E',
      }
    ];

    for (const route of sampleRoutes) {
      const line = new Line({
        points: route.points,
        stroke: route.color,
        lineWidth: 4,
        lineCap: 'round',
        lineJoin: 'round',
        lineDash: [8, 4],
        end: () => this.routeProgress(),
      });
      this.add(line);

      const label = new Txt({
        x: 0,
        y: 280,
        text: route.label,
        fill: '#8B263E',
        fontSize: 13,
        fontWeight: 700,
        fontFamily: 'Segoe UI, sans-serif',
      });
      this.add(label);
    }

    // Render Pins
    const samplePins: MapPin[] = props.pins ?? [
      { id: 'PIN_MUNICH', name: 'Munich (München)', coords: [-280, 160], isCapital: true },
      { id: 'PIN_BERLIN', name: 'Berlin (Imperial Capital)', coords: [160, -80], isCapital: true },
      { id: 'PIN_VIENNA', name: 'Vienna (Wien)', coords: [-80, 220], isCapital: true },
      { id: 'PIN_YPRES', name: 'Ypres Salient (Flanders)', coords: [360, -220], isCapital: false },
    ];

    for (const pin of samplePins) {
      const dot = new Circle({
        x: pin.coords[0],
        y: pin.coords[1],
        size: pin.isCapital ? 14 : 10,
        fill: pin.isCapital ? '#A32A2A' : '#2A2A2A',
        stroke: '#FFFFFF',
        lineWidth: 2,
      });

      const txt = new Txt({
        x: pin.coords[0],
        y: pin.coords[1] + 16,
        text: pin.name,
        fill: '#1E1914',
        fontSize: 12,
        fontWeight: 700,
        fontFamily: 'Segoe UI, sans-serif',
      });

      this.add(dot);
      this.add(txt);
    }
  }
}
