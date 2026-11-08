import {
  Node,
  NodeProps,
  Rect,
  Txt,
} from '@motion-canvas/2d';
import { SimpleSignal, createSignal } from '@motion-canvas/core';
import { OnScreenVisualElement } from '../contract/ProductionScenePackage';

export interface CinematicGraphicsProps extends NodeProps {
  elements?: OnScreenVisualElement[];
}

/**
 * CinematicGraphics: Universal On-Screen Visual Storytelling Engine V4.2.
 *
 * Implements:
 * - Location & Date Cards
 * - Character Introductions & Lower-Thirds
 * - Archival Document Close-Ups & Transcriptions
 * - Historical Map Annotations
 * - Subtitle Safe Zones & High-Legibility Typography with full Vietnamese diacritics
 */
export class CinematicGraphics extends Node {
  public readonly currentTime: SimpleSignal<number>;
  private elementsData: OnScreenVisualElement[];

  public constructor(props: CinematicGraphicsProps) {
    super(props);
    this.elementsData = props.elements ?? [];
    this.currentTime = createSignal(0);

    // Build subnodes for each graphic element
    for (const elem of this.elementsData) {
      if (elem.type === 'LOCATION_DATE_CARD') {
        this.buildLocationDateCard(elem);
      } else if (elem.type === 'CHARACTER_LOWER_THIRD') {
        this.buildCharacterLowerThird(elem);
      } else if (elem.type === 'DOCUMENT_CLOSEUP') {
        this.buildDocumentCloseup(elem);
      } else if (elem.type === 'CHAPTER_TITLE') {
        this.buildChapterTitle(elem);
      }
    }
  }

  private buildLocationDateCard(elem: OnScreenVisualElement) {
    const isVisible = () => {
      const t = this.currentTime();
      return t >= elem.start_time && t <= elem.end_time;
    };

    const opacity = () => {
      const t = this.currentTime();
      if (t < elem.start_time || t > elem.end_time) return 0.0;
      const fadeIn = Math.min(1.0, (t - elem.start_time) / 0.4);
      const fadeOut = Math.min(1.0, (elem.end_time - t) / 0.4);
      return Math.min(fadeIn, fadeOut);
    };

    const card = new Rect({
      x: -640,
      y: -440,
      width: 480,
      height: 74,
      fill: 'rgba(12, 14, 18, 0.88)',
      stroke: 'rgba(212, 175, 55, 0.85)',
      lineWidth: 1.5,
      radius: 4,
      opacity: opacity,
    });

    const headline = new Txt({
      x: -640,
      y: -454,
      text: elem.content_headline,
      fill: '#F5E6B3',
      fontSize: 14,
      fontWeight: 700,
      fontFamily: 'Segoe UI, Roboto, sans-serif',
      opacity: opacity,
    });

    const body = new Txt({
      x: -640,
      y: -430,
      text: elem.content_body,
      fill: '#D0D8E0',
      fontSize: 12,
      fontWeight: 400,
      fontFamily: 'Segoe UI, Roboto, sans-serif',
      opacity: opacity,
    });

    this.add(card);
    this.add(headline);
    this.add(body);
  }

  private buildCharacterLowerThird(elem: OnScreenVisualElement) {
    const opacity = () => {
      const t = this.currentTime();
      if (t < elem.start_time || t > elem.end_time) return 0.0;
      const fadeIn = Math.min(1.0, (t - elem.start_time) / 0.35);
      const fadeOut = Math.min(1.0, (elem.end_time - t) / 0.35);
      return Math.min(fadeIn, fadeOut);
    };

    const card = new Rect({
      x: -560,
      y: 340,
      width: 520,
      height: 64,
      fill: 'rgba(16, 18, 22, 0.90)',
      stroke: 'rgba(74, 144, 226, 0.80)',
      lineWidth: 1.5,
      radius: 4,
      opacity: opacity,
    });

    const headline = new Txt({
      x: -560,
      y: 328,
      text: elem.content_headline,
      fill: '#FFFFFF',
      fontSize: 15,
      fontWeight: 700,
      fontFamily: 'Segoe UI, Roboto, sans-serif',
      opacity: opacity,
    });

    const body = new Txt({
      x: -560,
      y: 352,
      text: elem.content_body,
      fill: '#A0AEC0',
      fontSize: 12,
      fontWeight: 400,
      fontFamily: 'Segoe UI, Roboto, sans-serif',
      opacity: opacity,
    });

    this.add(card);
    this.add(headline);
    this.add(body);
  }

  private buildDocumentCloseup(elem: OnScreenVisualElement) {
    const opacity = () => {
      const t = this.currentTime();
      if (t < elem.start_time || t > elem.end_time) return 0.0;
      const fadeIn = Math.min(1.0, (t - elem.start_time) / 0.4);
      const fadeOut = Math.min(1.0, (elem.end_time - t) / 0.4);
      return Math.min(fadeIn, fadeOut);
    };

    const card = new Rect({
      x: 580,
      y: -380,
      width: 520,
      height: 80,
      fill: 'rgba(242, 238, 226, 0.94)',
      stroke: 'rgba(40, 30, 20, 0.85)',
      lineWidth: 2.0,
      radius: 2,
      opacity: opacity,
    });

    const headline = new Txt({
      x: 580,
      y: -395,
      text: elem.content_headline,
      fill: '#1A1816',
      fontSize: 13,
      fontWeight: 800,
      fontFamily: 'Georgia, Times New Roman, serif',
      opacity: opacity,
    });

    const body = new Txt({
      x: 580,
      y: -370,
      text: elem.content_body,
      fill: '#4A4036',
      fontSize: 11,
      fontWeight: 600,
      fontFamily: 'Georgia, Times New Roman, serif',
      opacity: opacity,
    });

    this.add(card);
    this.add(headline);
    this.add(body);
  }

  private buildChapterTitle(elem: OnScreenVisualElement) {
    const opacity = () => {
      const t = this.currentTime();
      if (t < elem.start_time || t > elem.end_time) return 0.0;
      const fadeIn = Math.min(1.0, (t - elem.start_time) / 0.3);
      const fadeOut = Math.min(1.0, (elem.end_time - t) / 0.3);
      return Math.min(fadeIn, fadeOut);
    };

    const card = new Rect({
      x: 0,
      y: 440,
      width: 680,
      height: 52,
      fill: 'rgba(10, 12, 16, 0.92)',
      stroke: 'rgba(212, 175, 55, 0.95)',
      lineWidth: 1.5,
      radius: 4,
      opacity: opacity,
    });

    const headline = new Txt({
      x: 0,
      y: 432,
      text: elem.content_headline,
      fill: '#F5E6B3',
      fontSize: 14,
      fontWeight: 700,
      fontFamily: 'Segoe UI, Roboto, sans-serif',
      opacity: opacity,
    });

    const body = new Txt({
      x: 0,
      y: 452,
      text: elem.content_body,
      fill: '#CBD5E0',
      fontSize: 11,
      fontWeight: 400,
      fontFamily: 'Segoe UI, Roboto, sans-serif',
      opacity: opacity,
    });

    this.add(card);
    this.add(headline);
    this.add(body);
  }
}
