/**
 * CharacterDNA: Versioned declarative contract for Premium Stickman characters.
 * Style: PREMIUM STICKMAN CINEMATIC — STYLE B (V5.0)
 * 
 * Characters are purely data-driven configurations. No executable code.
 */

export type HeadContour =
  | 'oval_gaunt'
  | 'round_youth'
  | 'square_jaw'
  | 'delicate_heart'
  | 'athletic_lean';

export type EyeType =
  | 'intense_focused'
  | 'curious_wide'
  | 'almond_asian'
  | 'laughing_squint'
  | 'skeptical_narrow';

export type EyebrowStyle =
  | 'arched'
  | 'thick_bushy'
  | 'furrowed_intense'
  | 'delicate_curved'
  | 'straight_sharp';

export type HairStyle =
  | 'edo_topknot'
  | 'edo_shimada'
  | 'side_sweep_1914'
  | 'modern_crop'
  | 'ponytail_athletic'
  | 'middle_part_scholar'
  | 'bald_clean';

export type CostumeArchetype =
  | 'edo_hanten_courier'
  | 'edo_kimono_formal'
  | 'victorian_frock_coat'
  | 'modern_hoodie'
  | 'polar_hazard_suit'
  | 'lab_coat_clean'
  | 'military_uniform_1914';

export type FootwearType =
  | 'waraji_sandals'
  | 'tabi_socks'
  | 'leather_shoes'
  | 'sneakers'
  | 'snow_boots'
  | 'combat_boots'
  | 'bare_foot';

export type PropAttachment =
  | 'none'
  | 'letter_scroll_sealed'
  | 'letter_scroll_open'
  | 'folded_parchment'
  | 'leather_satchel'
  | 'umbrella_parasol'
  | 'pocket_watch'
  | 'tablet_computer'
  | 'steaming_coffee_cup'
  | 'scientific_scanner'
  | 'walking_cane';

export interface CharacterProportionsV5 {
  readonly headRatio: number;          // e.g. 0.26 - 0.30
  readonly standingHeightPx: number;   // e.g. 250 - 280
  readonly shoulderWidthPx: number;    // e.g. 48 - 60
  readonly limbThicknessPx: number;    // e.g. 9 - 13
  readonly torsoLengthPx: number;      // e.g. 68 - 82
  readonly legLengthPx: number;        // e.g. 110 - 130
}

export interface CharacterDNA_V5 {
  readonly characterId: string;
  readonly canonicalName: string;
  readonly archetypeId:
    | 'young_courier'
    | 'noblewoman'
    | 'detective_scholar'
    | 'tech_founder'
    | 'polar_scientist'
    | 'custom';
  readonly voiceId: string;
  readonly proportions: CharacterProportionsV5;
  readonly face: {
    readonly headContour: HeadContour;
    readonly skinTone: string;
    readonly eyeType: EyeType;
    readonly eyeColor: string;
    readonly eyebrowStyle: EyebrowStyle;
    readonly facialHair: 'none' | 'handlebar_mustache' | 'full_beard' | 'goatee' | 'stubble';
    readonly facialHairColor?: string;
  };
  readonly hair: {
    readonly style: HairStyle;
    readonly color: string;
    readonly accessory: 'none' | 'kanzashi_hairpin' | 'paper_cord' | 'headband' | 'glasses_round' | 'goggles';
  };
  readonly costume: {
    readonly archetype: CostumeArchetype;
    readonly primaryColor: string;
    readonly secondaryColor: string;
    readonly accentColor: string;
    readonly pantsColor: string;
    readonly beltType: 'obi_sash' | 'leather_belt' | 'cord' | 'utility_strap' | 'none';
    readonly footwear: FootwearType;
    readonly footwearColor: string;
  };
  readonly heldProps?: {
    readonly leftHand?: PropAttachment;
    readonly rightHand?: PropAttachment;
  };
}

/**
 * 5 Standard Core Launch Archetypes (100% Data-Driven)
 */
export const V5_CORE_ARCHETYPES: Record<string, CharacterDNA_V5> = {
  young_courier: {
    characterId: 'char_courier_haru',
    canonicalName: 'Haru (Người Đưa Thư)',
    archetypeId: 'young_courier',
    voiceId: 'vieneu-Quang Sơn',
    proportions: {
      headRatio: 0.28,
      standingHeightPx: 250,
      shoulderWidthPx: 50,
      limbThicknessPx: 10,
      torsoLengthPx: 70,
      legLengthPx: 115,
    },
    face: {
      headContour: 'round_youth',
      skinTone: '#F5DEB3',
      eyeType: 'curious_wide',
      eyeColor: '#2C1D11',
      eyebrowStyle: 'straight_sharp',
      facialHair: 'none',
    },
    hair: {
      style: 'edo_topknot',
      color: '#1A1A1A',
      accessory: 'paper_cord',
    },
    costume: {
      archetype: 'edo_hanten_courier',
      primaryColor: '#1B3B6F', // Indigo hanten
      secondaryColor: '#E8D8B8', // Bleached hemp lining
      accentColor: '#D9381E', // Crimson crest
      pantsColor: '#283655',
      beltType: 'cord',
      footwear: 'waraji_sandals',
      footwearColor: '#C4A482',
    },
    heldProps: {
      rightHand: 'letter_scroll_sealed',
      leftHand: 'leather_satchel',
    },
  },

  noblewoman: {
    characterId: 'char_noble_aiko',
    canonicalName: 'Aiko (Tiểu Thư)',
    archetypeId: 'noblewoman',
    voiceId: 'vieneu-Trúc Ly',
    proportions: {
      headRatio: 0.26,
      standingHeightPx: 260,
      shoulderWidthPx: 46,
      limbThicknessPx: 9,
      torsoLengthPx: 74,
      legLengthPx: 122,
    },
    face: {
      headContour: 'delicate_heart',
      skinTone: '#FFF5EE',
      eyeType: 'almond_asian',
      eyeColor: '#3B2F2F',
      eyebrowStyle: 'delicate_curved',
      facialHair: 'none',
    },
    hair: {
      style: 'edo_shimada',
      color: '#0F0F14',
      accessory: 'kanzashi_hairpin',
    },
    costume: {
      archetype: 'edo_kimono_formal',
      primaryColor: '#800020', // Burgundy silk
      secondaryColor: '#FFD700', // Gold embroidery
      accentColor: '#FF69B4', // Peach blossom sash
      pantsColor: '#800020',
      beltType: 'obi_sash',
      footwear: 'tabi_socks',
      footwearColor: '#FFFFFF',
    },
    heldProps: {
      leftHand: 'umbrella_parasol',
    },
  },

  detective_scholar: {
    characterId: 'char_scholar_arthur',
    canonicalName: 'Arthur (Thám Tử / Học Giả)',
    archetypeId: 'detective_scholar',
    voiceId: 'vieneu-Hải Đăng',
    proportions: {
      headRatio: 0.25,
      standingHeightPx: 275,
      shoulderWidthPx: 56,
      limbThicknessPx: 11,
      torsoLengthPx: 80,
      legLengthPx: 128,
    },
    face: {
      headContour: 'oval_gaunt',
      skinTone: '#EFE6DD',
      eyeType: 'intense_focused',
      eyeColor: '#3A506B',
      eyebrowStyle: 'furrowed_intense',
      facialHair: 'handlebar_mustache',
      facialHairColor: '#4A3B32',
    },
    hair: {
      style: 'side_sweep_1914',
      color: '#4A3B32',
      accessory: 'glasses_round',
    },
    costume: {
      archetype: 'victorian_frock_coat',
      primaryColor: '#2B2D42', // Charcoal wool
      secondaryColor: '#8D99AE', // Slate waistcoat
      accentColor: '#D90429', // Crimson cravat
      pantsColor: '#1F2022',
      beltType: 'leather_belt',
      footwear: 'leather_shoes',
      footwearColor: '#1A1110',
    },
    heldProps: {
      leftHand: 'pocket_watch',
      rightHand: 'walking_cane',
    },
  },

  tech_founder: {
    characterId: 'char_founder_minh',
    canonicalName: 'Minh (Kỹ Sư Công Nghệ)',
    archetypeId: 'tech_founder',
    voiceId: 'vieneu-Thiện Minh',
    proportions: {
      headRatio: 0.27,
      standingHeightPx: 265,
      shoulderWidthPx: 58,
      limbThicknessPx: 11,
      torsoLengthPx: 75,
      legLengthPx: 124,
    },
    face: {
      headContour: 'square_jaw',
      skinTone: '#F3DFC1',
      eyeType: 'curious_wide',
      eyeColor: '#1B1B1B',
      eyebrowStyle: 'straight_sharp',
      facialHair: 'stubble',
      facialHairColor: '#222222',
    },
    hair: {
      style: 'modern_crop',
      color: '#1C1D21',
      accessory: 'none',
    },
    costume: {
      archetype: 'modern_hoodie',
      primaryColor: '#3D5A80', // Tech blue hoodie
      secondaryColor: '#E0FBFC', // Pale mint inner tee
      accentColor: '#EE6C4D', // Burnt orange drawstrings
      pantsColor: '#293241', // Dark selvedge denim
      beltType: 'leather_belt',
      footwear: 'sneakers',
      footwearColor: '#FFFFFF',
    },
    heldProps: {
      rightHand: 'steaming_coffee_cup',
      leftHand: 'tablet_computer',
    },
  },

  polar_scientist: {
    characterId: 'char_scientist_elena',
    canonicalName: 'Elena (Chuyên Gia Nam Cực)',
    archetypeId: 'polar_scientist',
    voiceId: 'vieneu-Mai Anh',
    proportions: {
      headRatio: 0.26,
      standingHeightPx: 265,
      shoulderWidthPx: 52,
      limbThicknessPx: 12,
      torsoLengthPx: 76,
      legLengthPx: 120,
    },
    face: {
      headContour: 'athletic_lean',
      skinTone: '#FCEADE',
      eyeType: 'intense_focused',
      eyeColor: '#4895EF',
      eyebrowStyle: 'arched',
      facialHair: 'none',
    },
    hair: {
      style: 'ponytail_athletic',
      color: '#A0522D',
      accessory: 'goggles',
    },
    costume: {
      archetype: 'polar_hazard_suit',
      primaryColor: '#F77F00', // High-vis Arctic orange
      secondaryColor: '#FCBF49', // Reflective yellow accents
      accentColor: '#003049', // Thermal sealing strips
      pantsColor: '#D62828',
      beltType: 'utility_strap',
      footwear: 'snow_boots',
      footwearColor: '#1B1B1B',
    },
    heldProps: {
      rightHand: 'scientific_scanner',
    },
  },
};

export default V5_CORE_ARCHETYPES;
