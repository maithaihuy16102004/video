from __future__ import annotations
from dataclasses import dataclass, field, asdict
import math
from typing import Any
from PIL import Image, ImageDraw

ORIENTATIONS={"FRONT","BACK","PROFILE_LEFT","PROFILE_RIGHT","THREE_QUARTER_LEFT","THREE_QUARTER_RIGHT","THREE_QUARTER_BACK_LEFT","THREE_QUARTER_BACK_RIGHT"}
WEIGHTS={"CENTERED","LEFT","RIGHT","FORWARD","BACKWARD","SUPPORTED","SEATED","CROUCHED","KNEELING","LYING","BRACED"}
EMOTIONS={"CALM","CONFIDENT","NERVOUS","AFRAID","ANGRY","CONFUSED","EXHAUSTED","SAD","RELIEVED","SUSPICIOUS","SURPRISED","DETERMINED","AWKWARD","ATTENTIVE"}
TARGET_REQUIRED={"POINT","REACH","GRIP","HOLD","CARRY","PULL","PUSH","PLACE","PICK_UP","HAND_OVER","RECEIVE","OPEN","CLOSE","LEAN","SIT","LIE","SUPPORT","HELP","OPERATE","OBSERVE","LOOK"}

@dataclass
class CharacterPerformanceDNA:
    gesture_scale: float=1.0; posture_bias: float=0.0; movement_energy: float=1.0
    personal_space: float=1.0; reaction_scale: float=1.0; dominant_hand: str="RIGHT"; confidence_bias: float=0.0

@dataclass
class ActorIntent:
    actor_id: str; action: str; position: list[float]; scale: float; ground_y: float
    target_id: str=""; target_point: list[float]|None=None; eyeline_point: list[float]|None=None
    orientation: str="FRONT"; weight: str="CENTERED"; emotion: str="CALM"; intensity: str="NORMAL"
    depth: str="SUBJECT"; contact_type: str=""; carried_object: str=""; dna: CharacterPerformanceDNA=field(default_factory=CharacterPerformanceDNA)

@dataclass
class PoseParameters:
    lean_amount: float=0; head_turn: float=0; shoulder_tilt: float=0; hip_tilt: float=0
    arm_extension: float=.35; elbow_bend: float=.45; stride: float=0; crouch_amount: float=0; gesture_scale: float=1

@dataclass
class SolvedActor:
    intent: ActorIntent; params: PoseParameters; joints: dict[str,list[float]]; contacts: dict[str,list[float]]; object_anchor: list[float]|None
    def to_dict(self): return asdict(self)

class CharacterPerformanceEngine:
    def solve(self,intent: ActorIntent)->SolvedActor:
        p=self._parameters(intent); x=intent.position[0]*1920; gy=intent.ground_y*1080; s=150*intent.scale
        side=-1 if "LEFT" in intent.orientation else 1; lean=p.lean_amount*s
        hip=[x+lean*.25,gy-s*.58]; shoulder=[x+lean,gy-s*1.22]; neck=[shoulder[0],shoulder[1]-s*.12]
        head=[neck[0]+p.head_turn*s*.18,neck[1]-s*.22]
        spread=s*(.16+.36*p.stride); shift={"LEFT":-s*.12,"RIGHT":s*.12,"FORWARD":side*s*.08,"BACKWARD":-side*s*.08}.get(intent.weight,0)
        hip[0]+=shift; foot_l=[x-spread,gy]; foot_r=[x+spread,gy-(s*.08 if p.stride else 0)]
        if intent.weight in {"CROUCHED","KNEELING"}: hip[1]+=s*(.30+.25*p.crouch_amount); shoulder[1]+=s*.2
        if intent.weight=="LYING":
            hip=[x+s*.35,gy-s*.18]; shoulder=[x-s*.28,gy-s*.28]; neck=[x-s*.40,gy-s*.31]; head=[x-s*.55,gy-s*.34]; foot_l=[x+s*.9,gy-s*.12]; foot_r=[x+s*.72,gy-s*.08]
        target=intent.target_point or [shoulder[0]+side*s*.9,shoulder[1]+s*.2]
        ex=p.arm_extension; bend=p.elbow_bend
        hand_r=[target[0],target[1]] if intent.action in TARGET_REQUIRED and intent.target_point else [shoulder[0]+side*s*(.35+ex),shoulder[1]+s*.35]
        elbow_r=[shoulder[0]+(hand_r[0]-shoulder[0])*(.45-bend*.12),shoulder[1]+(hand_r[1]-shoulder[1])*.45-side*s*.12*bend]
        hand_l=[shoulder[0]-side*s*.28,shoulder[1]+s*.48]; elbow_l=[shoulder[0]-side*s*.22,shoulder[1]+s*.22]
        obj=None
        if intent.action=="CARRY":
            obj=[shoulder[0]+side*s*.48,shoulder[1]+s*.40]; hand_r=[obj[0]+side*s*.24,obj[1]]; hand_l=[obj[0]-side*s*.24,obj[1]]
            elbow_r=[shoulder[0]+side*s*.35,shoulder[1]+s*.22]; elbow_l=[shoulder[0]-side*s*.10,shoulder[1]+s*.25]
        if intent.action in {"PUSH","PULL"}:
            hand_l=[target[0],target[1]+s*.12]; elbow_l=[shoulder[0]+(hand_l[0]-shoulder[0])*.5,shoulder[1]+s*.08]
        if intent.weight=="LYING": elbow_l=[shoulder[0]-s*.10,shoulder[1]-s*.18]; hand_l=[shoulder[0]-s*.34,shoulder[1]-s*.25]
        knee_l=[hip[0]+(foot_l[0]-hip[0])*.48-side*s*.08,hip[1]+(foot_l[1]-hip[1])*.48]
        knee_r=[hip[0]+(foot_r[0]-hip[0])*.52+side*s*.08,hip[1]+(foot_r[1]-hip[1])*.52]
        joints={"head":head,"neck":neck,"shoulder":shoulder,"hip":hip,"elbow_l":elbow_l,"hand_l":hand_l,"elbow_r":elbow_r,"hand_r":hand_r,"knee_l":knee_l,"foot_l":foot_l,"knee_r":knee_r,"foot_r":foot_r}
        contacts={"foot_l":foot_l,"foot_r":foot_r}
        if intent.contact_type: contacts[intent.contact_type.lower()]=hand_r
        return SolvedActor(intent,p,joints,contacts,obj)

    def _parameters(self,i:ActorIntent)->PoseParameters:
        intensity={"SUBTLE":.65,"NORMAL":1.0,"STRONG":1.35,"EXTREME":1.7}.get(i.intensity,1)
        p=PoseParameters(gesture_scale=i.dna.gesture_scale*intensity)
        action=i.action
        if action in {"WALK","RUN","CLIMB"}: p.lean_amount=.12*intensity; p.stride=.55 if action=="WALK" else .9
        if action in {"REACH","GRIP","HOLD","PLACE","HAND_OVER","RECEIVE","POINT"}: p.lean_amount=.16*intensity; p.arm_extension=.9; p.elbow_bend=.35
        if action=="CARRY": p.lean_amount=.08; p.arm_extension=.65; p.elbow_bend=.78; p.stride=.38
        if action=="PUSH": p.lean_amount=.36*intensity; p.arm_extension=1; p.stride=.55
        if action=="PULL": p.lean_amount=-.28*intensity; p.arm_extension=.9; p.stride=.50
        if action in {"CROUCH","DUCK","HIDE"}: p.crouch_amount=.8; p.lean_amount=.2
        if action in {"LISTEN","OBSERVE","LOOK","REACT"}: p.head_turn=.8 if i.eyeline_point else .35; p.lean_amount=.06
        if action in {"ARGUE","SPEAK","GESTURE"}: p.arm_extension=.72; p.elbow_bend=.55; p.lean_amount=.18*intensity
        emotion={"AFRAID":(-.20,.85),"ANGRY":(.20,.9),"EXHAUSTED":(-.14,.25),"CONFIDENT":(.06,.65),"NERVOUS":(-.06,.35),"ATTENTIVE":(.08,.55)}
        if i.emotion in emotion: p.lean_amount+=emotion[i.emotion][0]*i.dna.reaction_scale; p.gesture_scale*=emotion[i.emotion][1]
        p.shoulder_tilt=.10 if i.weight in {"LEFT","RIGHT","FORWARD"} else 0; p.hip_tilt=-p.shoulder_tilt*.7
        return p

    def render(self,im:Image.Image,actors:list[SolvedActor],debug=False)->Image.Image:
        out=im.convert('RGBA'); d=ImageDraw.Draw(out,'RGBA')
        depth_style={"NEAR_FOREGROUND":((25,26,27,245),13),"SUBJECT":((48,47,44,235),8),"SECONDARY":((65,64,59,205),6),"BACKGROUND":((88,88,82,145),4)}
        for a in sorted(actors,key=lambda z:z.intent.scale):
            j=a.joints; color,w=depth_style.get(a.intent.depth,depth_style["SUBJECT"]); s=150*a.intent.scale
            # contact shadow first
            d.ellipse((j['foot_l'][0]-s*.25,j['foot_l'][1]-s*.04,j['foot_r'][0]+s*.25,max(j['foot_l'][1],j['foot_r'][1])+s*.05),fill=(25,24,22,55))
            for chain in [(j['neck'],j['shoulder'],j['hip']),(j['shoulder'],j['elbow_l'],j['hand_l']),(j['shoulder'],j['elbow_r'],j['hand_r']),(j['hip'],j['knee_l'],j['foot_l']),(j['hip'],j['knee_r'],j['foot_r'])]: d.line(chain,fill=color,width=w,joint='curve')
            r=s*.19; hx,hy=j['head']; d.ellipse((hx-r,hy-r,hx+r,hy+r),fill=(221,211,191,235),outline=color,width=w)
            if a.intent.eyeline_point:
                ex=1 if a.intent.eyeline_point[0]>hx else -1; ey=1 if a.intent.eyeline_point[1]>hy else -1; d.ellipse((hx+ex*r*.42-2,hy+ey*r*.22-2,hx+ex*r*.42+3,hy+ey*r*.22+3),fill=color)
            if a.object_anchor:
                ox,oy=a.object_anchor; d.ellipse((ox-s*.32,oy-s*.12,ox+s*.32,oy+s*.12),fill=(142,149,141,210),outline=color,width=max(2,w//2))
            if debug:
                d.text((hx+r+5,hy-r),f"{a.intent.actor_id}\n{a.intent.action}/{a.intent.weight}\n{a.intent.orientation}",fill=(255,220,90,255),stroke_width=2,stroke_fill=(0,0,0,230))
                if a.intent.eyeline_point: d.line((hx,hy,*a.intent.eyeline_point),fill=(255,210,40,180),width=3)
                for n,p in a.contacts.items(): d.ellipse((p[0]-7,p[1]-7,p[0]+7,p[1]+7),fill=(255,70,80,255))
        return out

def validate_actor(a:SolvedActor)->list[dict[str,Any]]:
    i=a.intent; checks=[]
    def add(name,ok,detail): checks.append({"check":name,"actor_id":i.actor_id,"passed":bool(ok),"detail":detail})
    add("ACTION_HAS_TARGET_IF_REQUIRED",i.action not in TARGET_REQUIRED or bool(i.target_id or i.target_point),i.action)
    hand_contact=i.contact_type in {"HAND_CONTACT","GRIP_CONTACT"} and i.action!="CARRY"
    if hand_contact and i.target_point:
        h=a.joints['hand_r']; dist=math.dist(h,i.target_point); add("HAND_CONTACT_DISTANCE",dist<=3,f"distance={dist:.2f}px")
    else: add("HAND_CONTACT_DISTANCE",True,"not applicable")
    fy=i.ground_y*1080; add("FOOT_ON_GROUND",i.weight=="LYING" or min(abs(a.joints['foot_l'][1]-fy),abs(a.joints['foot_r'][1]-fy))<15,f"ground_y={fy:.1f}")
    add("OBJECT_ATTACHMENT_VALID",i.action!="CARRY" or a.object_anchor is not None,i.carried_object or "not applicable")
    add("EYELINE_DIRECTION_VALID",i.action not in {"LOOK","OBSERVE","LISTEN","REACT"} or i.eyeline_point is not None,str(i.eyeline_point))
    p=a.params; add("POSE_PARAMETERS_VALID",all(-2<=v<=2 for v in asdict(p).values()),str(asdict(p)))
    add("NO_FLOATING_ACTOR",i.weight=="LYING" or max(a.joints['foot_l'][1],a.joints['foot_r'][1])>=fy-15,"ground contact")
    return checks
