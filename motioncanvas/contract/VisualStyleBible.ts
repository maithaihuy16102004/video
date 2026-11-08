/**
 * V5 Visual Style Bible: Machine-Readable Tokens and Rules
 * Permanent Style Lock: PREMIUM STICKMAN CINEMATIC — STYLE B (V5.0)
 * 
 * All character rigs, environment builders, cameras, typography,
 * and compositing rules strictly enforce these tokens.
 */

export interface LineworkStyleTokens {
  readonly strokeContourPx: number;
  readonly strokeTorsoPx: number;
  readonly strokeLimbsPx: number;
  readonly strokeFacialFeaturesPx: number;
  readonly strokeAccentsPx: number;
  readonly lineCap: CanvasLineCap;
  readonly lineJoin: CanvasLineJoin;
  readonly bezierSmoothTension: number;
  readonly antiAliasing: boolean;
  readonly minLuminanceFloor: number;
}

export interface CharacterProportionTokens {
  readonly headToBodyRatioDefault: number;
  readonly standingHeightBaselinePx: number;
  readonly shoulderWidthBaselinePx: number;
  readonly limbThicknessBaselinePx: number;
  readonly neckHeightPx: number;
  readonly hipWidthPx: number;
  readonly footLengthPx: number;
  readonly handSpanPx: number;
}

export interface EnvironmentPbrTokens {
  readonly toneMapping: 'ACESFilmicToneMapping';
  readonly toneMappingExposure: number;
  readonly keyToAmbientRatio: number;
  readonly ambientLuminanceFloor: number;
  readonly backgroundLuminanceFloor: number;
  readonly shadowMapType: 'PCFSoftShadowMap';
  readonly defaultRoughness: number;
  readonly defaultMetalness: number;
  readonly depthOfFieldBlurPx: number;
}

export interface CameraStagingTokens {
  readonly safeMarginPercent: number; // e.g. 0.08 (8% safe margin)
  readonly focalLengths: {
    readonly extremeWideMm: number;
    readonly wideMm: number;
    readonly mediumMm: number;
    readonly heroMm: number;
    readonly closeUpMm: number;
    readonly insertMm: number;
  };
  readonly minCharacterScreenHeightPercent: number; // Prevent tiny lost characters
  readonly maxCharacterOcclusionPercent: number; // 0% principal action occlusion allowed
}

export interface MotionGraphicsTypographyTokens {
  readonly titleFontFamily: string;
  readonly subtitleFontFamily: string;
  readonly captionFontFamily: string;
  readonly cardBorderRadiusPx: number;
  readonly cardBorderWidthPx: number;
  readonly badgeElevationShadow: string;
  readonly primaryAccentColor: string;
  readonly secondaryAccentColor: string;
  readonly darkBackgroundOverlay: string;
}

export interface VisualStyleBibleConfig {
  readonly styleName: 'Premium Stickman Cinematic — V5';
  readonly version: '5.0.0';
  readonly linework: LineworkStyleTokens;
  readonly characterProportions: CharacterProportionTokens;
  readonly environment: EnvironmentPbrTokens;
  readonly camera: CameraStagingTokens;
  readonly typography: MotionGraphicsTypographyTokens;
}

export const V5_VISUAL_STYLE_BIBLE: VisualStyleBibleConfig = {
  styleName: 'Premium Stickman Cinematic — V5',
  version: '5.0.0',

  linework: {
    strokeContourPx: 3.8,
    strokeTorsoPx: 3.5,
    strokeLimbsPx: 3.2,
    strokeFacialFeaturesPx: 2.2,
    strokeAccentsPx: 1.8,
    lineCap: 'round',
    lineJoin: 'round',
    bezierSmoothTension: 0.45,
    antiAliasing: true,
    minLuminanceFloor: 0.45,
  },

  characterProportions: {
    headToBodyRatioDefault: 0.28,
    standingHeightBaselinePx: 260,
    shoulderWidthBaselinePx: 54,
    limbThicknessBaselinePx: 11,
    neckHeightPx: 12,
    hipWidthPx: 38,
    footLengthPx: 22,
    handSpanPx: 18,
  },

  environment: {
    toneMapping: 'ACESFilmicToneMapping',
    toneMappingExposure: 1.45,
    keyToAmbientRatio: 2.6,
    ambientLuminanceFloor: 0.48,
    backgroundLuminanceFloor: 0.45,
    shadowMapType: 'PCFSoftShadowMap',
    defaultRoughness: 0.65,
    defaultMetalness: 0.15,
    depthOfFieldBlurPx: 1.8,
  },

  camera: {
    safeMarginPercent: 0.08,
    focalLengths: {
      extremeWideMm: 18,
      wideMm: 24,
      mediumMm: 35,
      heroMm: 50,
      closeUpMm: 85,
      insertMm: 105,
    },
    minCharacterScreenHeightPercent: 0.22,
    maxCharacterOcclusionPercent: 0.0,
  },

  typography: {
    titleFontFamily: '"Cinzel Decorative", "Plus Jakarta Sans", "Be Vietnam Pro", serif',
    subtitleFontFamily: '"Plus Jakarta Sans", "Be Vietnam Pro", sans-serif',
    captionFontFamily: '"Be Vietnam Pro", sans-serif',
    cardBorderRadiusPx: 18,
    cardBorderWidthPx: 3,
    badgeElevationShadow: '4px 4px 0px #172033',
    primaryAccentColor: '#FFD34E',
    secondaryAccentColor: '#FF6B5E',
    darkBackgroundOverlay: 'rgba(23, 32, 51, 0.88)',
  },
};

export default V5_VISUAL_STYLE_BIBLE;
