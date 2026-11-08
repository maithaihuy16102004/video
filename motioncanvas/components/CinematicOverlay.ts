/**
 * Cinematic Motion Graphics & Typography Overlay V4.2.1
 * 
 * Implements Phase 7:
 * - Location & Date Cards (Establishing historical context)
 * - Chapter Titles & Beat Callouts
 * - Safe-Margin Subtitles with Full Vietnamese Unicode support
 * - Dynamic Action Indicators (Never occluding primary characters)
 */

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

  constructor(ctx: CanvasRenderingContext2D, width = 1920, height = 1080) {
    this.ctx = ctx;
    this.width = width;
    this.height = height;
  }

  public draw(data: OverlayData) {
    const ctx = this.ctx;

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

  private drawSubtitle(sub: { speaker: string; text: string; color?: string }) {
    const ctx = this.ctx;
    ctx.save();

    const bottomY = this.height - 85;
    ctx.font = 'bold 28px "Segoe UI", Arial, sans-serif';
    const textW = ctx.measureText(sub.text).width;
    const padX = 28;
    const padY = 14;
    const cardW = Math.min(this.width - 240, textW + padX * 2);
    const cardX = (this.width - cardW) / 2;

    // Dark frosted backing to ensure readability across dark and light scenes
    ctx.fillStyle = 'rgba(12, 14, 18, 0.85)';
    this.roundedRect(ctx, cardX, bottomY - 36, cardW, 56, 8);
    ctx.fill();

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // Speaker tag if dialogue
    if (sub.speaker && sub.speaker !== 'NARRATOR') {
      ctx.fillStyle = sub.color || '#FFC83B';
      ctx.font = 'bold 16px "Segoe UI", Arial, sans-serif';
      ctx.fillText(sub.speaker.toUpperCase(), cardX + 16, bottomY - 44);
    }

    // Subtitle Text (Vietnamese Unicode)
    ctx.fillStyle = '#FFFFFF';
    ctx.font = '600 26px "Segoe UI", Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(sub.text, this.width / 2, bottomY);

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
