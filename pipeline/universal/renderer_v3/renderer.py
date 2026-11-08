from __future__ import annotations

from dataclasses import dataclass, field
import random
from PIL import Image, ImageDraw, ImageFilter
from .assets import AssetRendererV3
from .character import CharacterPerformanceRendererV3
from .materials import MaterialRendererV2


@dataclass
class RenderSpec:
    title: str = "Universal scene"
    location: str = "office"
    action: str = "REACH"
    intensity: str = "NORMAL"
    emotion: str = "FOCUSED"
    palette: tuple = ('#31343b', '#78614a', '#d6b36a', '#9eb7c3')
    hero_asset: str = 'TABLE'
    material: str = 'WOOD'
    atmosphere: str = 'DUST'
    lighting_story: str = 'WINDOW_LEFT'
    foreground: str = 'POST'
    seed: int = 1
    props: list[str] = field(default_factory=lambda: ['CHAIR', 'PAPER', 'LAMP', 'BOOK'])
    layout_kind: str = 'ROOM'
    horizon: int = 510
    actor_x: int = 780
    hero_x: int = 1180
    landmark_x: int = 960
    environment_only: bool = False
    # Backwards-compatible staging & storytelling extensions:
    actor_y: int = 835
    actor_orientation: str = 'THREE_QUARTER_RIGHT'
    secondary_actor_x: Optional[int] = None
    secondary_actor_y: int = 835
    secondary_action: Optional[str] = None
    secondary_intensity: str = 'NORMAL'
    secondary_orientation: str = 'THREE_QUARTER_LEFT'
    secondary_emotion: Optional[str] = None
    human_traces: list[str] = field(default_factory=lambda: ['CUP', 'PAPER'])
    landmark_feature: Optional[str] = None


def rgb(h):
    h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))+(255,)


class IllustratedRendererV3:
    width=1920;height=1080
    def __init__(self):self.assets=AssetRendererV3();self.characters=CharacterPerformanceRendererV3();self.materials=MaterialRendererV2()

    def render(self,spec:RenderSpec,v3=True,debug=None):
        random.seed(spec.seed); im=Image.new('RGBA',(self.width,self.height),rgb(spec.palette[0]));d=ImageDraw.Draw(im,'RGBA');w,h=self.width,self.height; horizon=spec.horizon
        # FAR_BG/BG: directional gradient and architectural structure
        for y in range(horizon):
            t=y/horizon; c=tuple(int(rgb(spec.palette[3])[i]*(1-t)+rgb(spec.palette[0])[i]*t) for i in range(3));d.line((0,y,w,y),fill=c+(255,))
        wall=rgb(spec.palette[1]);d.rectangle((0,130,w,horizon),fill=wall)
        if v3:
            self.materials.apply(d,(0,130,w,horizon),'PLASTER',spec.seed,.75)
            # leading architecture and line hierarchy
            vp=spec.landmark_x
            beams=(80,420,1510,1870) if spec.layout_kind=='HALL' else (150,520,1400,1770)
            for x in beams:d.line((vp,horizon,x,130),fill=(45,39,35,150),width=5)
            if spec.layout_kind=='PASS': d.polygon([(0,130),(620,horizon),(0,horizon)],fill=(58,58,53,255));d.polygon([(w,130),(1260,horizon),(w,horizon)],fill=(68,66,58,255))
            elif spec.layout_kind=='CROWD':
                for yy in (260,350,440): d.line((120,yy,w-120,yy),fill=(48,38,32,220),width=22)
            elif spec.layout_kind=='INTIMATE': d.rectangle((0,130,620,horizon),fill=(52,48,44,255))
            d.rectangle((0,120,w,150),fill=(43,36,31,255));d.line((0,horizon,w,horizon),fill=(30,27,25,255),width=7)
            # visual landmark feature at perspective convergence
            if spec.landmark_feature:
                self.assets.draw(d, spec.landmark_feature, spec.landmark_x, horizon - 25, 1.25, variant=spec.seed % 3, seed=spec.seed + 40)
        # floor perspective
        floor=tuple(max(0,int(c*.58)) for c in rgb(spec.palette[1])[:3])+(255,);d.rectangle((0,horizon,w,h),fill=floor)
        for i in range(15):d.line((spec.landmark_x,horizon,i*w/14,h),fill=(28,25,23,100 if v3 else 45),width=3 if v3 else 1)
        for i in range(9):
            y=horizon+((i/8)**1.7)*(h-horizon);d.line((0,y,w,y),fill=(31,28,25,80),width=2)
        if v3:self.materials.apply(d,(0,horizon,w,h),spec.material,spec.seed+10,.7)
        # actual light source and falloff
        light=Image.new('RGBA',im.size,(0,0,0,0));ld=ImageDraw.Draw(light,'RGBA');left='LEFT' in spec.lighting_story
        sx=240 if left else 1680; accent=rgb(spec.palette[2]);ld.polygon([(sx,140),(sx+220 if left else sx-220,140),(1370 if left else 550,900),(450 if left else 1470,900)],fill=accent[:3]+((65 if v3 else 18),))
        light=light.filter(ImageFilter.GaussianBlur(35 if v3 else 80));im.alpha_composite(light);d=ImageDraw.Draw(im,'RGBA')
        # coherent prop ecology and ground contact
        placements=[(spec.props[i%len(spec.props)],180+i*330+(spec.landmark_x-960)*.22,650+(i%2)*80,.72+(i%3)*.08) for i in range(min(5,len(spec.props)))]
        for i,(fam,x,y,sc) in enumerate(placements):self.assets.draw(d,fam,x,y,sc,variant=i,seed=spec.seed+i)
        # hero object with detail budget
        self.assets.draw(d,spec.hero_asset,spec.hero_x,710,1.45 if v3 else 1.0,hero=True,seed=spec.seed+90)
        # character contacts hero object for reach/pull/brace/lean
        contact=(spec.hero_x-105,620) if spec.action in ('REACH','PULL','BRACE','LEAN') else None
        if not spec.environment_only:
            self.characters.draw(d,spec.actor_x,spec.actor_y,spec.action,spec.intensity,spec.actor_orientation,1.35 if v3 else 1.0,spec.emotion,False,-1 if left else 1,contact)
            # secondary staged actor if provided
            if spec.secondary_actor_x is not None and spec.secondary_action:
                sec_contact=(spec.hero_x+95,620) if spec.secondary_action in ('REACH','PULL','BRACE','LEAN') else None
                self.characters.draw(d,spec.secondary_actor_x,spec.secondary_actor_y,spec.secondary_action,spec.secondary_intensity,spec.secondary_orientation,1.30 if v3 else 1.0,spec.secondary_emotion or spec.emotion,False,1 if left else -1,sec_contact)
        # human traces / story accent
        if v3:
            traces=spec.human_traces if spec.human_traces else ['CUP','PAPER']
            t1=traces[0] if len(traces)>0 else 'CUP'
            t2=traces[1] if len(traces)>1 else 'PAPER'
            self.assets.draw(d,t1,1325,655,.55,seed=spec.seed)
            self.assets.draw(d,t2,1110,620,.6,hero=True,seed=spec.seed)
            # foreground physically located
            self.assets.draw(d,spec.foreground,95,850,2.15,seed=spec.seed+7)
            # atmosphere in depth
            rng=random.Random(spec.seed); atmo={'DUST':(240,220,170,65),'FOG':(210,220,225,38),'SMOKE':(110,110,105,45),'EMBERS':(247,113,38,100)}.get(spec.atmosphere,(230,220,190,35))
            for i in range(80):
                x=rng.randrange(w);y=rng.randrange(160,h);r=rng.choice((1,2,3,5));d.ellipse((x-r,y-r,x+r,y+r),fill=atmo)
            # shadow mass and vignette
            shade=Image.new('RGBA',im.size,(0,0,0,0));sd=ImageDraw.Draw(shade,'RGBA');sd.rectangle((0,0,380,h),fill=(10,10,15,75));sd.rectangle((1540,0,w,h),fill=(10,10,15,95));shade=shade.filter(ImageFilter.GaussianBlur(70));im.alpha_composite(shade)
        if debug=='DEPTH':
            dd=ImageDraw.Draw(im,'RGBA'); colors=[(255,60,60,70),(255,180,20,70),(40,220,90,70),(30,130,255,70),(140,60,230,70)]
            for i,(name,y0,y1) in enumerate([('FAR_BG',0,180),('BG',180,510),('MG',510,720),('FG',720,900),('NEAR_FG',900,1080)]):dd.rectangle((0,y0,w,y1),fill=colors[i]);dd.text((24,y0+16),name,fill='white',stroke_width=2,stroke_fill='black')
        elif debug=='LIGHT':
            dd=ImageDraw.Draw(im,'RGBA');dd.ellipse((sx-30,110,sx+30,170),fill=(255,244,175,255));dd.line((sx,140,780,700),fill=(255,238,130,230),width=12);dd.text((sx+40,110),spec.lighting_story,fill='white',stroke_width=2,stroke_fill='black')
        return im.convert('RGB')
