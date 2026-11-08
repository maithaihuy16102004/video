from __future__ import annotations

import math
from PIL import ImageDraw


ACTIONS=("WAIT","RUN","LEAN","CROUCH","REACH","PULL","BRACE","READ","ARGUE","FLINCH","SIT","RISE")
INTENSITY={"SUBTLE":.55,"NORMAL":1.0,"STRONG":1.35,"EXTREME":1.7}


class CharacterPerformanceRendererV3:
    """Gesture-line-first illustrated stickman with balance and readable contacts."""
    def pose(self,action,intensity="NORMAL"):
        a=action.upper(); k=INTENSITY.get(intensity.upper(),1); lean={"RUN":18,"LEAN":20,"REACH":14,"BRACE":-14,"PULL":-22,"ARGUE":8,"FLINCH":-16,"RISE":8}.get(a,0)*k
        crouch={"CROUCH":55,"SIT":70,"RISE":35,"FLINCH":24}.get(a,0)*k; stride={"RUN":62,"BRACE":45,"PULL":50,"ARGUE":25}.get(a,22)*k
        arms={"WAIT":((-30,45),(-28,92),(30,45),(28,92)),"RUN":((-42,20),(-60,-12),(38,70),(65,92)),"LEAN":((-40,35),(-70,55),(30,50),(55,70)),"CROUCH":((-42,28),(-55,70),(42,28),(55,70)),"REACH":((-28,34),(-38,72),(45,10),(92,-5)),"PULL":((-42,20),(-78,25),(38,18),(78,22)),"BRACE":((-35,25),(-70,55),(38,18),(78,45)),"READ":((-32,40),(-38,72),(32,40),(38,72)),"ARGUE":((-40,5),(-72,-22),(38,10),(70,-12)),"FLINCH":((-28,-4),(-45,-35),(28,-5),(45,-38)),"SIT":((-34,45),(-42,78),(34,45),(42,78)),"RISE":((-35,38),(-55,72),(35,28),(58,58))}.get(a,((-30,45),(-28,92),(30,45),(28,92)))
        return lean,crouch,stride,arms

    def draw(self,d:ImageDraw.ImageDraw,x,y,action="WAIT",intensity="NORMAL",orientation="THREE_QUARTER_RIGHT",scale=1,emotion="FOCUSED",silhouette=False,light_dir=-1,contact=None):
        lean,crouch,stride,arms=self.pose(action,intensity); s=scale; ink=(27,25,28,255); skin=(225,195,161,255); cloth=(62,74,89,255); shadow=(31,35,44,255)
        hip=(x-int(lean*.35*s),y-int((115-crouch)*s)); shoulder=(x-int(lean*s),y-int((245-crouch)*s)); head=(shoulder[0]-int(lean*.2*s),shoulder[1]-int(70*s)); com=(int((hip[0]+shoulder[0])/2),int((hip[1]+shoulder[1])/2))
        lw=max(3,int(8*s)); d.ellipse((x-55*s,y-9*s,x+55*s,y+12*s),fill=(20,18,20,70))
        # legs and support under COM
        lf=(x-int(stride*s),y); rf=(x+int(stride*.7*s),y); knee_y=int((hip[1]+y)/2)
        for foot,sgn in ((lf,-1),(rf,1)):
            knee=(int((hip[0]+foot[0])/2+sgn*10*s),knee_y+int(crouch*.15*s)); d.line((hip,knee,foot),fill=ink,width=lw,joint="curve");d.line((foot[0]-4*s,foot[1],foot[0]+20*s,foot[1]),fill=ink,width=lw)
        # gesture line, clothing mass
        d.line((head,shoulder,hip),fill=ink,width=max(2,int(4*s)))
        torso=[(shoulder[0]-35*s,shoulder[1]),(shoulder[0]+35*s,shoulder[1]),(hip[0]+27*s,hip[1]),(hip[0]-27*s,hip[1])];d.polygon(torso,fill=ink if silhouette else cloth,outline=ink)
        # action arms; visible contact can override action hand
        for idx,(e,h) in enumerate(((arms[0],arms[1]),(arms[2],arms[3]))):
            ex=shoulder[0]+e[0]*s;ey=shoulder[1]+e[1]*s;hx=shoulder[0]+h[0]*s;hy=shoulder[1]+h[1]*s
            if contact and idx==1:hx,hy=contact
            d.line((shoulder, (ex,ey),(hx,hy)),fill=ink,width=lw,joint="curve");d.ellipse((hx-7*s,hy-7*s,hx+7*s,hy+7*s),fill=ink if silhouette else skin,outline=ink,width=max(1,lw//3))
        # head and orientation-correct simple face
        r=43*s;d.ellipse((head[0]-r,head[1]-r,head[0]+r,head[1]+r),fill=ink if silhouette else skin,outline=ink,width=max(2,int(5*s)))
        if not silhouette:
            # hair silhouette with secondary clumps
            d.pieslice((head[0]-r-2,head[1]-r-8,head[0]+r+2,head[1]+r),180,355,fill=(48,35,29,255),outline=ink,width=2)
            for q in (-24,-8,10,26):d.ellipse((head[0]+q*s-9*s,head[1]-r-4*s,head[0]+q*s+9*s,head[1]-r+15*s),fill=(58,40,31,255))
            if "BACK" not in orientation:
                side=-1 if "LEFT" in orientation else 1; profile="PROFILE" in orientation; eye_y=head[1]-5*s
                eyes=[head[0]+side*15*s] if profile else [head[0]-10*s,head[0]+12*s]
                for ex in eyes:d.ellipse((ex-3*s,eye_y-3*s,ex+3*s,eye_y+3*s),fill=ink)
                brow=-5 if emotion in ("ANGRY","ARGUE") else 2
                d.line((eyes[0]-7*s,eye_y-11*s,eyes[0]+7*s,eye_y-11*s+brow*s),fill=ink,width=max(2,int(3*s)))
                d.arc((head[0]-15*s,head[1]+5*s,head[0]+18*s,head[1]+28*s),10 if emotion in ("HAPPY","ARGUE") else 190,170 if emotion in ("HAPPY","ARGUE") else 350,fill=ink,width=max(2,int(3*s)))
            # light/shadow side and rim
            d.arc((head[0]-r,head[1]-r,head[0]+r,head[1]+r),80 if light_dir<0 else 260,260 if light_dir<0 else 440,fill=(74,65,65,170),width=max(3,int(8*s)))
            d.line((shoulder[0]-light_dir*34*s,shoulder[1],hip[0]-light_dir*25*s,hip[1]),fill=(228,197,118,160),width=max(2,int(4*s)))
        return {"center_of_mass":com,"support":(lf,rf),"gesture_line":[head,shoulder,hip]}

    def render_stickman(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        scale: float = 1.0,
        action: str = "WAIT",
        facing: str = "RIGHT",
        emotion: str = "CALM",
        costume: str = "1914_CIVILIAN",
        hair_color: str = "#2A1E14",
        head_ratio: float = 0.28,
        contact: tuple[int, int] | None = None,
    ) -> dict:
        act_map = {
            "SIGN": "REACH",
            "SPEAK": "ARGUE",
            "LISTEN": "WAIT",
            "POINT": "REACH",
            "CROUCH": "CROUCH",
            "BRACE": "BRACE",
            "WAIT": "WAIT",
            "RUN": "RUN",
            "LEAN": "LEAN",
            "SIT": "SIT",
            "FLINCH": "FLINCH",
        }
        mapped_action = act_map.get(action.upper(), "WAIT")
        orient = "THREE_QUARTER_RIGHT" if "RIGHT" in facing.upper() else ("THREE_QUARTER_LEFT" if "LEFT" in facing.upper() else "FRONT")
        emo_map = {
            "CALM": "FOCUSED",
            "FOCUSED": "FOCUSED",
            "CONFIDENT": "HAPPY",
            "NEUTRAL": "FOCUSED",
            "TENSE": "FLINCH",
            "ANGRY": "ANGRY",
        }
        mapped_emo = emo_map.get(emotion.upper(), "FOCUSED")
        return self.draw(
            draw,
            x=x,
            y=y,
            action=mapped_action,
            intensity="NORMAL",
            orientation=orient,
            scale=scale,
            emotion=mapped_emo,
            contact=contact,
        )

