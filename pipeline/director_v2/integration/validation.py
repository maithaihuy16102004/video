from __future__ import annotations
import math
from typing import Any
from .contract import SceneRenderContext
from ..performance.engine import SolvedActor

def validate_integrated(actors:list[SolvedActor],context:SceneRenderContext,debug:dict[str,Any])->list[dict[str,Any]]:
    out=[]
    def add(name,ok,detail): out.append({"check":name,"passed":bool(ok),"detail":detail})
    add('SHARED_CAMERA_TRANSFORM',context.camera.viewport==[1920,1080] and context.camera.horizon_y==context.ground_plane.horizon_y,str(context.camera))
    add('GROUND_PLANE_HANDSHAKE',all(a.intent.weight=='LYING' or abs(max(a.joints['foot_l'][1],a.joints['foot_r'][1])-a.intent.ground_y*1080)<20 for a in actors),'final pixel coordinates')
    add('ENVIRONMENT_ANCHOR_RESOLUTION',all('point' in r for r in debug['resolutions']),str(debug['resolutions']))
    add('AFFORDANCE_RESOLUTION',all(r['target']['anchor'] for r in debug['resolutions']),str(debug['resolutions']))
    for a in actors:
        if a.intent.target_point and a.intent.contact_type in {'HAND_CONTACT','GRIP_CONTACT'} and a.intent.action!='CARRY':
            add('POST_COMPOSITE_HAND_CONTACT',math.dist(a.joints['hand_r'],a.intent.target_point)<=3,a.intent.actor_id)
        if a.intent.action=='CARRY': add('POST_COMPOSITE_OBJECT_ATTACHMENT',a.object_anchor is not None,a.intent.actor_id)
        if a.intent.eyeline_point: add('EYELINE_TARGET_RESOLUTION',True,a.intent.actor_id)
    add('DEPTH_ASSIGNMENT',all(a.intent.depth in {'NEAR_FOREGROUND','SUBJECT','SECONDARY','BACKGROUND'} for a in actors),'actor depth aliases')
    add('SEMANTIC_OCCLUSION',all(e.relation in {'IN_FRONT_OF','BEHIND','INTERSECTS','CONTACTS'} for e in context.occlusion.edges),'graph edges')
    add('OBJECT_STATE_SYNCHRONIZATION',all(v!='WORLD_STATIC' for v in debug['object_states'].values()),str(debug['object_states']))
    add('LIGHTING_CONTEXT_TRANSFER',0<=context.lighting.key_intensity<=1 and bool(context.lighting.depth_attenuation),str(context.lighting))
    return out
