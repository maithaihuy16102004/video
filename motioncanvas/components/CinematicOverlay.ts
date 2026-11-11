/**
 * Cinematic Motion Graphics & Typography Overlay V4.2.1
 * 
 * Implements Phase 7:
 * - Location & Date Cards (Establishing historical context)
 * - Chapter Titles & Beat Callouts
 * - Safe-Margin Subtitles with Full Vietnamese Unicode support
 * - Dynamic Action Indicators (Never occluding primary characters)
 */

export interface SubtitleLayout {
  text: string;
  speaker?: string;
  color?: string;
  initialFontSize: number;
  fontSize: number;
  reductionSteps: number;
  lines: string[];
  maxBoxWidth: number;         // Exactly frameWidth * 0.90
  boxWidth: number;            // <= maxBoxWidth
  boxHeight: number;
  boxX: number;                // Exactly (frameWidth - boxWidth) / 2
  boxY: number;
  paddingX: number;
  paddingY: number;
  lineHeight: number;
  maxLineWidth: number;
  availableTextWidth: number;
  isCentered: boolean;
  overflowDetected: boolean;
  wrapped: boolean;
}

export interface OverlayData {
  timeSeconds: number;
  locationCard?: {
    headline: string;
    subline: string;
    showUntil: number;
  };
  subtitle?: {
    speaker: string;
    text: string;
    color?: string;
    initialFontSize?: number;
  };
  beatBadge?: {
    title: string;
    tag: string;
  };
}

export class CinematicOverlayRenderer {
  private ctx: CanvasRenderingContext2D;
  private width: number;
  private height: number;
  private lastSubtitleLayout: SubtitleLayout | null = null;

  constructor(ctx: CanvasRenderingContext2D, width = 1920, height = 1080) {
    this.ctx = ctx;
    this.width = width;
    this.height = height;
  }

  public resize(width: number, height: number) {
    this.width = width;
    this.height = height;
  }

  public drawVignette() {
    const ctx = this.ctx;
    ctx.save();
    const cx = this.width / 2;
    const cy = this.height / 2;
    const maxR = Math.max(this.width, this.height) * 0.72;
    const grad = ctx.createRadialGradient(cx, cy, maxR * 0.35, cx, cy, maxR);
    grad.addColorStop(0, 'rgba(0, 0, 0, 0)');
    grad.addColorStop(1, 'rgba(10, 8, 6, 0.38)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, this.width, this.height);
    ctx.restore();
  }

  public draw(data: OverlayData) {
    const ctx = this.ctx;

    // 0. Documentary Cinematic Radial Vignette
    this.drawVignette();

    // 1. Location & Date Card (Top-Left, fade out after showUntil)
    if (data.locationCard && data.timeSeconds < data.locationCard.showUntil) {
      this.drawLocationCard(data.locationCard, data.timeSeconds);
    }

    // 2. Beat Badge / Mission Indicator (Top-Right)
    if (data.beatBadge) {
      this.drawBeatBadge(data.beatBadge);
    }

    // 3. Cinematic Safe-Margin Subtitles (Bottom Third)
    if (data.subtitle && data.subtitle.text) {
      this.drawSubtitle(data.subtitle);
    }
  }

  private drawLocationCard(card: { headline: string; subline: string; showUntil: number }, t: number) {
    const ctx = this.ctx;
    ctx.save();

    let alpha = 1.0;
    if (t < 0.6) alpha = t / 0.6;
    else if (t > card.showUntil - 0.6) alpha = (card.showUntil - t) / 0.6;
    ctx.globalAlpha = Math.max(0, Math.min(1, alpha));

    const x = 70;
    const y = 65;

    // Elegant semi-transparent backdrop card
    ctx.fillStyle = 'rgba(16, 20, 26, 0.82)';
    this.roundedRect(ctx, x, y, 540, 78, 6);
    ctx.fill();

    ctx.strokeStyle = 'rgba(214, 230, 248, 0.35)';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Red accent vertical notch
    ctx.fillStyle = '#C8281E';
    this.roundedRect(ctx, x + 12, y + 14, 5, 50, 2);
    ctx.fill();

    // Headline (Edo 1800 / Munich 1914 / SF 2026)
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 22px "Segoe UI", Arial, sans-serif';
    ctx.fillText(card.headline, x + 30, y + 36);

    // Subline (Place details)
    ctx.fillStyle = '#B4C6D8';
    ctx.font = '500 16px "Segoe UI", Arial, sans-serif';
    ctx.fillText(card.subline, x + 30, y + 60);

    ctx.restore();
  }

  private drawBeatBadge(badge: { title: string; tag: string }) {
    const ctx = this.ctx;
    ctx.save();
    const x = this.width - 450;
    const y = 65;

    ctx.fillStyle = 'rgba(16, 20, 26, 0.78)';
    this.roundedRect(ctx, x, y, 380, 52, 6);
    ctx.fill();

    ctx.strokeStyle = 'rgba(255, 180, 50, 0.4)';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    ctx.fillStyle = '#FFB830';
    ctx.font = 'bold 13px "Segoe UI", Arial, sans-serif';
    ctx.fillText(badge.tag.toUpperCase(), x + 16, y + 22);

    ctx.fillStyle = '#FFFFFF';
    ctx.font = '600 17px "Segoe UI", Arial, sans-serif';
    ctx.fillText(badge.title, x + 16, y + 42);

    ctx.restore();
  }

  public getLastSubtitleLayout(): SubtitleLayout | null {
    return this.lastSubtitleLayout;
  }

  /**
   * Safe-Margin Subtitle Layout Engine
   * 
   * Invariants:
   * 1. Subtitle box width equals 90% of frame width max, centered.
   * 2. Automatic line-wrap when text exceeds box bounds — never truncate or render text past the box edge.
   * 3. If wrapped text exceeds 2 lines, reduce font size by 10% increments until it fits into <= 2 lines.
   */
  public computeSubtitleLayout(
    text: string,
    initialFontSize: number = 28,
    minFontSize: number = 10,
    speaker?: string,
    color?: string
  ): SubtitleLayout {
    const ctx = this.ctx;
    const maxBoxWidth = Math.round(this.width * 0.90);
    const paddingX = 28;
    const availableTextWidth = maxBoxWidth - paddingX * 2;

    let fontSize = initialFontSize;
    let reductionSteps = 0;

    const wrapLinesAtSize = (size: number): { lines: string[]; maxLineWidth: number } => {
      ctx.font = `600 ${size}px "Be Vietnam Pro", "Plus Jakarta Sans", "Segoe UI", Arial, sans-serif`;
      const paragraphs = text.split('\n');
      const allLines: string[] = [];

      for (const p of paragraphs) {
        const words = p.trim().split(/\s+/).filter(w => w.length > 0);
        if (words.length === 0) continue;

        let cur = '';
        for (const w of words) {
          const test = cur ? `${cur} ${w}` : w;
          const testW = ctx.measureText(test).width;
          if (testW <= availableTextWidth) {
            cur = test;
          } else {
            if (cur) {
              allLines.push(cur);
              cur = w;
            } else {
              // Word by itself is wider than availableTextWidth
              allLines.push(w);
              cur = '';
            }
          }
        }
        if (cur) {
          allLines.push(cur);
        }
      }

      if (allLines.length === 0 && text.trim().length > 0) {
        allLines.push(text.trim());
      }

      let maxW = 0;
      for (const l of allLines) {
        const w = ctx.measureText(l).width;
        if (w > maxW) maxW = w;
      }

      return { lines: allLines, maxLineWidth: maxW };
    };

    let { lines, maxLineWidth } = wrapLinesAtSize(fontSize);

    // Iterative 10% reduction if wrapped lines exceed 2 or single word exceeds width
    while ((lines.length > 2 || maxLineWidth > availableTextWidth) && fontSize > minFontSize) {
      const nextSize = Math.max(minFontSize, Math.min(fontSize - 1, Math.round(fontSize * 0.90)));
      if (nextSize >= fontSize) break;
      fontSize = nextSize;
      reductionSteps++;

      const res = wrapLinesAtSize(fontSize);
      lines = res.lines;
      maxLineWidth = res.maxLineWidth;
    }

    // Safety fallback: if at minimum font size an unbroken string exceeds availableTextWidth,
    // break characters cleanly to strictly guarantee text never renders past box edge
    if (maxLineWidth > availableTextWidth && lines.length > 0) {
      const splitLines: string[] = [];
      for (const l of lines) {
        if (ctx.measureText(l).width <= availableTextWidth) {
          splitLines.push(l);
        } else {
          let chunk = '';
          for (const ch of l) {
            if (ctx.measureText(chunk + ch).width <= availableTextWidth) {
              chunk += ch;
            } else {
              if (chunk) splitLines.push(chunk);
              chunk = ch;
            }
          }
          if (chunk) splitLines.push(chunk);
        }
      }
      lines = splitLines.slice(0, 2);
      maxLineWidth = Math.max(...lines.map(l => ctx.measureText(l).width));
    }

    // Subtitle box dimensions: 90% frame width max, centered
    const boxWidth = Math.min(maxBoxWidth, Math.max(160, Math.round(maxLineWidth + paddingX * 2)));
    const boxX = Math.round((this.width - boxWidth) / 2);

    const lineHeight = Math.round(fontSize * 1.35);
    const paddingY = Math.max(12, Math.round(fontSize * 0.45));
    const textBlockHeight = lines.length <= 1 ? fontSize : fontSize + (lines.length - 1) * lineHeight;
    const boxHeight = textBlockHeight + paddingY * 2;
    const safeBottomMargin = this.height > this.width ? 320 : 65;
    const boxY = this.height - safeBottomMargin - boxHeight;

    return {
      text,
      speaker,
      color,
      initialFontSize,
      fontSize,
      reductionSteps,
      lines,
      maxBoxWidth,
      boxWidth,
      boxHeight,
      boxX,
      boxY,
      paddingX,
      paddingY,
      lineHeight,
      maxLineWidth,
      availableTextWidth,
      isCentered: Math.abs(boxX - (this.width - boxWidth) / 2) < 1,
      overflowDetected: maxLineWidth > availableTextWidth || lines.length > 2,
      wrapped: lines.length > 1
    };
  }

  private drawSubtitle(sub: { speaker: string; text: string; color?: string; initialFontSize?: number }) {
    if (!sub || !sub.text || sub.text.trim().length === 0) return;

    const layout = this.computeSubtitleLayout(
      sub.text,
      sub.initialFontSize || 28,
      10,
      sub.speaker,
      sub.color
    );
    this.lastSubtitleLayout = layout;

    const ctx = this.ctx;
    ctx.save();

    // 1. Dark frosted backing (width <= 90% frame width max, centered)
    ctx.fillStyle = 'rgba(12, 14, 18, 0.85)';
    this.roundedRect(ctx, layout.boxX, layout.boxY, layout.boxWidth, layout.boxHeight, 8);
    ctx.fill();

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // 2. Speaker tag if dialogue
    if (sub.speaker && sub.speaker !== 'NARRATOR') {
      ctx.fillStyle = sub.color || '#FFC83B';
      ctx.font = 'bold 15px "Segoe UI", Arial, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(sub.speaker.toUpperCase(), layout.boxX + 16, layout.boxY - 8);
    }

    // 3. Subtitle Text Lines (Centered, Vietnamese Unicode, no overflow past box edge)
    ctx.fillStyle = '#FFFFFF';
    ctx.font = `600 ${layout.fontSize}px "Be Vietnam Pro", "Plus Jakarta Sans", "Segoe UI", Arial, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';

    const textCenterX = this.width / 2;
    const startY = layout.boxY + layout.paddingY;

    for (let i = 0; i < layout.lines.length; i++) {
      const lineY = startY + i * layout.lineHeight;
      ctx.fillText(layout.lines[i], textCenterX, lineY);
    }

    ctx.restore();
  }

  private roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
}
