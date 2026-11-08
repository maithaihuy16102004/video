from __future__ import annotations
from dataclasses import dataclass,field,asdict
from ..renderer_v3 import RenderSpec

@dataclass
class SceneIdentity:
 dominant_shape_language:str;dominant_depth_direction:str;dominant_material:str;architectural_character:str;spatial_density:str;spatial_pressure:str;hero_environment_feature:str;visual_landmark:str;visual_motif:str;environment_condition:str;dominant_light_source:str
@dataclass
class SceneDesignV3:
 scene_id:str;scene_purpose:str;dramatic_question:str;scene_outcome:str;scene_identity:SceneIdentity;production_design:dict;scene_geography:dict;initial_blocking:dict;event_graph:list;information_map:dict;environment_state:dict;lighting_sources:list;depth_design:dict;camera_opportunities:list;asset_requirements:list;visual_progression:list;ideal_scene_design:dict=field(default_factory=dict);capability_fallbacks:list=field(default_factory=list)
 def to_dict(self):return asdict(self)

class SceneArchitect:
 """Renderer-aware adapter boundary; Gemini proposals may enter here before validation."""
 def validate(self,s:SceneDesignV3)->SceneDesignV3:
  if not s.scene_identity.visual_landmark:raise ValueError('visual_landmark required')
  if not s.production_design or not s.scene_geography:raise ValueError('production design and geography required')
  return s

class SceneRendererAdapter:
 def to_render_spec(self,s:SceneDesignV3,environment_only=False)->RenderSpec:
  g=s.scene_geography;b=s.initial_blocking;p=s.production_design;i=s.scene_identity
  return RenderSpec(title=s.scene_id,location=i.architectural_character,action=b.get('action','WAIT'),intensity=b.get('intensity','NORMAL'),emotion=b.get('emotion','FOCUSED'),palette=tuple(p['palette']),hero_asset=g['hero_object']['family'],material=i.dominant_material,atmosphere=p.get('atmosphere','DUST'),lighting_story=i.dominant_light_source,foreground=g.get('foreground',{}).get('family','POST'),seed=g.get('seed',1),props=p['prop_ecology'],layout_kind=g['layout_kind'],horizon=g['horizon'],actor_x=b['actor_x'],hero_x=g['hero_object']['x'],landmark_x=g['landmark']['x'],environment_only=environment_only)
