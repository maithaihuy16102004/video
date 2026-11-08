from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from typing import Any
from PIL import Image,ImageDraw,ImageEnhance,ImageFilter
from .contract import SceneRenderContext,ContactTargetRef
from ..performance.engine import ActorIntent,CharacterPerformanceEngine,SolvedActor

DEPTH_ALIAS={"NEAR_FG":"NEAR_FOREGROUND","FG":"NEAR_FOREGROUND","MG":"SUBJECT","BG":"BACKGROUND","FAR_BG":"BACKGROUND"}

class IntegratedSceneRenderer:
    """Generic world→actor→lighting→semantic occlusion compositor."""
    def __init__(self,width:int=1920,height:int=1080): self.width=width; self.height=height; self.characters=CharacterPerformanceEngine()

    def render(self,world:Image.Image|str|Path,intents:list[ActorIntent],context:SceneRenderContext)->tuple[Image.Image,list[SolvedActor],dict[str,Any]]:
        base=Image.open(world).convert('RGBA') if isinstance(world,(str,Path)) else world.convert('RGBA')
        adapted=[]; resolutions=[]
        for intent in intents:
            target=intent.target_point
            if intent.target_id in context.assets:
                ref=context.resolve_affordance(intent.target_id,intent.action); target=context.resolve(ref); resolutions.append({"actor":intent.actor_id,"action":intent.action,"target":ref.__dict__,"point":target})
            elif intent.target_id in context.eyeline_targets and target is None: target=context.eyeline_targets[intent.target_id]
            depth_value=context.depth_planes.get(intent.depth,.5); ground=context.ground_plane.ground_y_at(intent.position[0],depth_value)
            depth=DEPTH_ALIAS.get(intent.depth,intent.depth)
            adapted.append(replace(intent,target_point=target,ground_y=ground,depth=depth,eyeline_point=intent.eyeline_point or target))
        solved=[self.characters.solve(i) for i in adapted]
        transparent=Image.new('RGBA',(self.width,self.height),(0,0,0,0)); layer=self.characters.render(transparent,solved)
        layer=self._apply_world_lighting(layer,context)
        composite=Image.alpha_composite(base,layer)
        composite=self._apply_occlusion(composite,context)
        debug={"resolutions":resolutions,"object_states":self._synchronize_states(adapted,context),"occlusion":[e.__dict__ for e in context.occlusion.edges]}
        return composite,solved,debug

    def _apply_world_lighting(self,layer:Image.Image,c:SceneRenderContext)->Image.Image:
        # Single world-owned lighting context: graphic tint + key rim + local focus only.
        tint=Image.new('RGBA',layer.size,(210,222,232,0) if 'COLD' in c.lighting.key_direction else (244,213,160,0))
        alpha=layer.getchannel('A').point(lambda a:int(a*(.82+.18*c.lighting.key_intensity)))
        tint.putalpha(alpha.point(lambda a:int(a*.10)))
        out=Image.alpha_composite(layer,tint)
        sh=Image.new('RGBA',layer.size,(0,0,0,0)); d=ImageDraw.Draw(sh,'RGBA'); fx,fy=c.lighting.local_focus; d.ellipse((fx*self.width-320,fy*self.height-250,fx*self.width+320,fy*self.height+250),fill=(255,235,185,18)); sh=sh.filter(ImageFilter.GaussianBlur(35))
        return Image.alpha_composite(out,sh)

    def _apply_occlusion(self,im:Image.Image,c:SceneRenderContext)->Image.Image:
        overlay=Image.new('RGBA',im.size,(0,0,0,0)); d=ImageDraw.Draw(overlay,'RGBA')
        for e in c.occlusion.edges:
            if e.relation!='BEHIND' or e.object_id not in c.assets: continue
            asset=c.assets[e.object_id]
            if len(asset.bounds)==4:
                x0,y0,x1,y1=asset.bounds; d.rectangle((x0*self.width,y0*self.height,x1*self.width,y1*self.height),fill=(35,34,32,70))
        return Image.alpha_composite(im,overlay)

    def _synchronize_states(self,intents:list[ActorIntent],c:SceneRenderContext)->dict[str,str]:
        states={k:v.state for k,v in c.assets.items()}
        transitions={"OPEN":"OPEN","CLOSE":"CLOSED","CARRY":"ATTACHED_TO_ACTOR","PULL":"MOVED","PUSH":"MOVED"}
        for i in intents:
            if i.target_id in states and i.action in transitions: states[i.target_id]=transitions[i.action]
        return states

    def fallback_render(self,world:Image.Image,intents:list[ActorIntent])->Image.Image:
        return self.characters.render(world,[self.characters.solve(i) for i in intents])
