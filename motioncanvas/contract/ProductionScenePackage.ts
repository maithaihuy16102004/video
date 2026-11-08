/**
 * ProductionScenePackage: Canonical Contract between Python Pipeline and Motion Canvas V4 / V4.1.
 *
 * Python is the single brain for research, story, and casting.
 * TypeScript validates and executes the visual scene graph without duplicating reasoning.
 */

export interface StoryBeat {
  beat_id: string;
  beat_name?: string;
  time_range?: [number, number];
  primary_verb: string;
  what_happens: string;
  why_it_matters: string;
  who_causes_it: string;
  what_physically_changes: string;
  protagonist_want: string;
  obstacle: string;
  protagonist_knows: string;
  protagonist_not_knows: string;
  location_id: string;
  story_state?: string;
}

export interface ThreeJsArchitecture {
  facade_style: string;
  stone_type: string;
  stone_color: string;
  shadow_stone_color: string;
  z_facade?: number;
  arches: Array<{
    id: string;
    x: number;
    base_y?: number;
    width: number;
    height: number;
    apex_radius: number;
  }>;
  columns: Array<{
    id: string;
    x: number;
    radius: number;
    height: number;
  }>;
  statues: Array<{
    name: string;
    side: 'LEFT' | 'RIGHT';
    pos?: [number, number, number];
    color?: string;
  }>;
  lions?: Array<{
    side: 'LEFT' | 'RIGHT';
    pos: [number, number, number];
  }>;
}

export interface ThreeJsEnvironment {
  enabled: boolean;
  scene_type: string;
  camera_initial?: {
    position: [number, number, number];
    target: [number, number, number];
    fov: number;
  };
  camera_keyframes?: Array<{
    t: number;
    position: [number, number, number];
    target: [number, number, number];
  }>;
  lighting: {
    sun: { color: string; intensity: number; position: [number, number, number] };
    sky_ambient: { color: string; intensity: number };
    ground_bounce: { color: string; intensity: number };
  };
  architecture: ThreeJsArchitecture;
  street_furniture?: {
    litfass_pillar?: {
      id: string;
      pos: [number, number, number];
      radius: number;
      height: number;
      color: string;
      placard_color: string;
    };
  };
}

export interface SceneWorld {
  location_id: string;
  canonical_name: string;
  historical_era: string;
  dimensions: { width: number; height: number };
  ground_plane: {
    y_ground_canvas: number;
    material: string;
    reflectivity: number;
    primary_color: string;
    mortar_color: string;
  };
  threejs_environment: ThreeJsEnvironment;
}

export interface CharacterProportions {
  head_to_body_ratio: number;
  head_diameter_px: number;
  total_standing_height_px: number;
  limb_width_px: number;
}

export interface CharacterDNA {
  head_shape: string;
  hair_color: string;
  hair_style: string;
  facial_hair: string;
  eye_anchors?: string[];
  costume: {
    model: string;
    frock_coat_color: string;
    collar_color: string;
    cravat_color: string;
    trousers_color: string;
  };
}

export interface ActorEntity {
  character_id: string;
  canonical_name: string;
  role: string;
  voice_id: string;
  render_type: string;
  proportions: CharacterProportions;
  dna: CharacterDNA;
  staging: {
    initial_world_pos?: [number, number, number];
    world_3d_anchor?: [number, number, number];
    canvas_initial_x?: number;
    canvas_initial_y?: number;
    scale?: number;
    facing?: 'LEFT' | 'RIGHT';
    posture?: string;
    hand_held_prop?: {
      type: string;
      color: string;
      hand: 'LEFT' | 'RIGHT';
      width: number;
      height: number;
    };
  };
  performance_timeline?: Array<{
    t: number;
    action: string;
    intensity: number;
    emotion: string;
  }>;
  performance_cues?: Array<{
    time: number;
    action: string;
    pos: [number, number, number];
    torso_lean: number;
    head_angle: number;
    eyeline: string;
  }>;
}

export interface CitizenEntity {
  id: string;
  type: string;
  base_x: number;
  base_z: number;
  height_px: number;
  hat: string;
  color: string;
}

export interface CrowdTimelineState {
  t_start: number;
  state: string;
  cluster_radius: number;
  attention_ratio: number;
  description: string;
}

export interface CrowdFieldConfig {
  enabled: boolean;
  anchor_object_id: string;
  citizens: CitizenEntity[];
  timeline_states: CrowdTimelineState[];
}

export interface InteractiveObject {
  object_id: string;
  canonical_name: string;
  attached_to_id: string;
  world_pos: [number, number, number];
  dimensions: { width_m: number; height_m: number };
  headline_text: string;
  state_timeline: Array<{
    time: number;
    state: string;
  }>;
}

export interface ShotPlanItem {
  shot_index: number;
  shot_id: string;
  beat_id: string;
  time_range: [number, number];
  duration_sec: number;
  shot_type: string;
  camera: {
    start_pos: [number, number, number];
    end_pos: [number, number, number];
    start_tgt: [number, number, number];
    end_tgt: [number, number, number];
    fov: number;
  };
  story_purpose: string;
  why_cut_earned: string;
}

export interface VoiceLineRecord {
  line_id: string;
  text: string;
  start_sec: number;
  end_sec: number;
  shots: number[];
}

export interface SFXCueRecord {
  sfx_id: string;
  time_sec: number;
  category: string;
  event: string;
  volume: number;
  description: string;
}

export interface HistoricalGroundingRecord {
  entity: string;
  grounding_class: 'DOCUMENTED' | 'CONTEXT_SUPPORTED' | 'PLAUSIBLE_RECONSTRUCTION' | 'UNCERTAIN' | 'UNKNOWN';
  citation: string;
}

export interface ProductionScenePackageV41 {
  schema_version: string;
  project_id: string;
  sequence_id: string;
  storytelling_mode: string;
  primary_pov_character_id: string;
  total_sequence_duration_seconds: number;
  fps: number;
  story_beats: StoryBeat[];
  event_graph: Array<{
    event_id: string;
    beat_id: string;
    cause: string;
    action: string;
    physical_delta: string;
    consequence: string;
  }>;
  scene_world: SceneWorld;
  actors: ActorEntity[];
  crowd_field: CrowdFieldConfig;
  interactive_objects: InteractiveObject[];
  shots: ShotPlanItem[];
  voice_timeline: {
    audio_file: string;
    speaker_id: string;
    voice_id: string;
    speed_ratio: number;
    total_duration_sec: number;
    lines: VoiceLineRecord[];
  };
  sfx_timeline: SFXCueRecord[];
  historical_grounding: HistoricalGroundingRecord[];
}

export interface OnScreenVisualElement {
  id: string;
  type: 'CHAPTER_TITLE' | 'LOCATION_DATE_CARD' | 'CHARACTER_LOWER_THIRD' | 'DOCUMENT_CLOSEUP' | 'MAP_ANNOTATION' | 'SUBTITLE';
  semantic_purpose: string;
  content_headline: string;
  content_body: string;
  start_time: number;
  end_time: number;
  screen_region: 'TOP_LEFT' | 'TOP_RIGHT' | 'CENTER' | 'BOTTOM_CENTER' | 'LOWER_THIRD';
  priority?: number;
}

export interface ProductionScenePackageV42 extends ProductionScenePackageV41 {
  visual_plan?: OnScreenVisualElement[];
}

export type ProductionScenePackage = ProductionScenePackageV42;

