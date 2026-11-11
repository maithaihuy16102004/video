// VisualStyleBible16x9.ts — Ricks-style 16:9 YouTube adaptation
// of the V5 Premium Stickman Cinematic Style B.
//
// Locked tokens. Do not override per story. The only things that
// change per story are the JSON scene package (characters, beats,
// locations) — never the renderer, palette, or safe-frame rules.
//
// 16:9 differences from the 9:16 Shorts version:
// - stage is 1920x1080, action safe frame is the inner 84%
// - captions live in the lower third, inside the inner 80% frame,
//   minimum 64px at 1080p, max 2 lines x 42 chars
// - hook visual must be readable in a 320px-wide YouTube thumbnail

export const YOUTUBE_16X9 = {
  width: 1920,
  height: 1080,
  fps: 24,
  aspectRatio: "16:9",
  safeActionMarginPct: 8, // inner 84%
  safeTitleMarginPct: 10, // inner 80%
} as const;

export const PALETTE = {
  backgroundCanvas: "#F3F0E8",
  primaryAccent: "#FFD34E", // cinematic gold
  secondaryAccent: "#FF6B5E", // coral punch
  textInk: "#172033", // deep obsidian blue
  successGreen: "#47BD75",
} as const;

export const CHARACTER = {
  contourStrokePx: 3.8,
  torsoStrokePx: 3.5,
  // Ricks-style readability: fewer, bolder shapes than a realistic
  // render. Silhouette must read at thumbnail size; face must read
  // at 480p. Keep the V5 12-joint rig and 2-bone IK — simplify the
  // costume detail, never the skeleton or the foot-locking.
  joints: 12,
  archetypes: [
    "young_courier",
    "noblewoman",
    "detective_scholar",
    "tech_founder",
    "polar_scientist",
  ],
} as const;

export const LIGHTING = {
  toneMapping: "ACESFilmic",
  exposure: 1.45,
  keyToAmbientRatio: "2.6:1",
  backgroundLuminanceFloor: 0.45,
  actionZoneLuminanceFloor: 0.38,
} as const;

export const CAPTION = {
  minFontPxAt1080p: 64,
  maxCharsPerLine: 42,
  maxLines: 2,
  position: "lower_third_inside_safe_title",
  strokePx: 3,
  shadow: "4px 4px 0px #172033",
} as const;

export const CAMERA = {
  // 16:9 only. No vertical reframing.
  focalLengthsMm: { extremeWide: 18, wide: 24, medium: 35, heroMedium: 50, closeUp: 85 },
  neverObstructAction: true,
} as const;
