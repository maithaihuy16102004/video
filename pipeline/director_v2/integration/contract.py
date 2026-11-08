from __future__ import annotations
from dataclasses import dataclass,field,asdict
from typing import Any

@dataclass(frozen=True)
class ContactTargetRef:
    asset_instance_id:str; anchor:str
    @classmethod
    def parse(cls,value:str|dict[str,str]|"ContactTargetRef"):
        if isinstance(value,cls): return value
        if isinstance(value,dict): return cls(value["asset_instance_id"],value["anchor"])
        a,b=value.split(".",1); return cls(a,b)

@dataclass
class AssetInstance:
    asset_instance_id:str; asset_type:str; depth_plane:str; anchors:dict[str,list[float]]
    affordances:dict[str,str]; state:str="STATIC"; bounds:list[float]=field(default_factory=list)

@dataclass
class GroundPlane:
    horizon_y:float; near_y:float=1.0; slope:float=0.0
    def ground_y_at(self,x:float,depth:float)->float:
        base=self.horizon_y+(self.near_y-self.horizon_y)*(1-depth)
        return max(self.horizon_y,min(self.near_y,base+self.slope*(x-.5)))

@dataclass
class CameraContext:
    viewport:list[int]; shot_size:str; horizon_y:float; primary_vp:list[float]; projection:str="ONE_POINT"; scale:float=1.0

@dataclass
class LightingContext:
    key_direction:str; key_intensity:float; fill:float; shadow_side:str; depth_attenuation:dict[str,float]; local_focus:list[float]

@dataclass
class OcclusionEdge:
    subject:str; relation:str; object_id:str

@dataclass
class OcclusionGraph:
    edges:list[OcclusionEdge]=field(default_factory=list)
    def add(self,subject:str,relation:str,object_id:str): self.edges.append(OcclusionEdge(subject,relation,object_id))

@dataclass
class SceneRenderContext:
    scene_id:str; camera:CameraContext; ground_plane:GroundPlane; assets:dict[str,AssetInstance]
    lighting:LightingContext; depth_planes:dict[str,float]; story_focus:list[str]=field(default_factory=list)
    eyeline_targets:dict[str,list[float]]=field(default_factory=dict); occlusion:OcclusionGraph=field(default_factory=OcclusionGraph)
    def resolve(self,ref:ContactTargetRef|str|dict[str,str])->list[float]:
        r=ContactTargetRef.parse(ref); asset=self.assets[r.asset_instance_id]
        if r.anchor not in asset.anchors: raise KeyError(f"Unknown anchor {r.asset_instance_id}.{r.anchor}")
        point=asset.anchors[r.anchor]
        return [point[0]*self.camera.viewport[0],point[1]*self.camera.viewport[1]] if max(abs(point[0]),abs(point[1]))<=1.0 else point
    def resolve_affordance(self,asset_id:str,action:str)->ContactTargetRef:
        asset=self.assets[asset_id]; anchor=asset.affordances.get(action)
        if not anchor: raise ValueError(f"{asset_id} does not afford {action}")
        return ContactTargetRef(asset_id,anchor)
    def to_dict(self)->dict[str,Any]: return asdict(self)
