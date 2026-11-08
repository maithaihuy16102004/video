from __future__ import annotations
import json, time
from dataclasses import asdict
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT=Path(__file__).parents[3]; OUT=ROOT/'output'/'hospital_vitality_test'; OUT.mkdir(parents=True,exist_ok=True)
BASE=ROOT/'output'/'renderer_bakeoff'/'D_paper_rough_svg_texture.png'
W,H=1920,1080

def line(draw, pts, fill, width): draw.line(pts,fill=fill,width=width,joint='curve')
def actor(draw,x,y,s,action,tone=(62,61,58,220),thin=False):
    lw=max(2,int(7*s*(.65 if thin else 1))); r=22*s
    draw.ellipse((x-r,y-190*s-r,x+r,y-190*s+r),fill=(222,213,195,230),outline=tone,width=lw)
    line(draw,[(x,y-168*s),(x,y-75*s)],tone,lw)
    if action=='CARRY':
        line(draw,[(x,y-145*s),(x+42*s,y-105*s),(x+75*s,y-112*s)],tone,lw); line(draw,[(x,y-145*s),(x+30*s,y-106*s)],tone,lw)
        draw.ellipse((x+48*s,y-122*s,x+104*s,y-96*s),fill=(160,165,155,220),outline=tone,width=max(1,lw//2))
    elif action=='ADJUST':
        line(draw,[(x,y-145*s),(x-55*s,y-108*s)],tone,lw); line(draw,[(x,y-145*s),(x-36*s,y-92*s)],tone,lw)
    elif action=='OPEN_CURTAIN':
        line(draw,[(x,y-145*s),(x+50*s,y-195*s)],tone,lw); line(draw,[(x,y-145*s),(x+30*s,y-100*s)],tone,lw)
    else:
        line(draw,[(x,y-145*s),(x-30*s,y-105*s)],tone,lw); line(draw,[(x,y-145*s),(x+30*s,y-105*s)],tone,lw)
    if action in ('WALK','CARRY'):
        line(draw,[(x,y-75*s),(x-38*s,y)],tone,lw); line(draw,[(x,y-75*s),(x+45*s,y-8*s)],tone,lw)
    else:
        line(draw,[(x,y-75*s),(x-24*s,y)],tone,lw); line(draw,[(x,y-75*s),(x+25*s,y)],tone,lw)

def hospital(density):
    base=Image.open(BASE).convert('RGBA'); base=ImageEnhance.Contrast(base).enhance(.92)
    art=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(art,'RGBA')
    # directional window light and quiet-zone falloff
    d.polygon([(70,120),(610,120),(1260,900),(520,900)],fill=(224,233,224,34))
    # second occupied bed and secondary nurse event
    if density>=1:
        d.rounded_rectangle((230,585,830,755),22,fill=(172,156,132,180),outline=(58,53,47,210),width=8)
        d.line((260,690,800,690),fill=(62,58,52,220),width=9)
        d.ellipse((305,590,355,640),fill=(214,203,185,235),outline=(64,58,52,220),width=5)
        d.polygon([(345,620),(690,610),(770,695),(360,695)],fill=(142,154,143,215),outline=(69,69,61,210))
        actor(d,850,690,.58,'ADJUST',(70,68,63,205),True)
        # used cloth and open chart
        d.polygon([(720,760),(780,746),(815,780),(746,793)],fill=(211,203,184,215),outline=(90,79,67,190))
        d.polygon([(900,720),(988,705),(1002,764),(917,775)],fill=(221,213,191,220),outline=(95,81,66,190))
        d.line((928,725,980,719),fill=(90,80,70,150),width=3)
    # background micro-story: orderly crossing corridor
    if density>=2:
        actor(d,1300,595,.45,'CARRY',(81,82,79,175),True)
        # directional stride shadow
        d.ellipse((1220,585,1415,625),fill=(34,35,36,55))
    # rich: curtain handling and seated visitor reaction, not prop dump
    if density>=3:
        actor(d,1510,650,.48,'OPEN_CURTAIN',(88,84,76,155),True)
        actor(d,1080,760,.42,'OBSERVE',(84,81,75,145),True)
        # drifting curtain as motion cue
        d.polygon([(1580,150),(1770,150),(1715,670),(1640,610),(1680,430),(1595,500)],fill=(208,203,183,90),outline=(100,91,78,120))
        d.arc((1580,340,1780,650),180,330,fill=(130,118,96,100),width=4)
        # lifted paper corner / airflow cue
        d.polygon([(1060,820),(1135,805),(1150,850),(1100,835)],fill=(223,213,190,185),outline=(93,82,65,130))
    # far doorway silhouette, scaled and low contrast
    if density>=2:
        d.rectangle((1700,270,1870,720),fill=(40,43,44,95),outline=(90,91,87,100),width=5)
        actor(d,1785,690,.29,'WALK',(117,116,107,105),True)
    # cropped foreground doctor: active OTS framing, 12-16% frame area
    d.ellipse((-95,220,350,655),fill=(38,39,40,235),outline=(19,20,21,245),width=14)
    d.polygon([(-30,500),(275,465),(465,1080),(-100,1080)],fill=(45,47,48,242),outline=(20,21,22,245))
    # foreground hand/gesture aimed at patient
    d.line((245,600,505,665),fill=(42,43,43,235),width=30)
    d.ellipse((480,640,535,690),fill=(168,151,131,220),outline=(45,43,40,230),width=7)
    # near bedpost for camera presence
    d.line((1860,620,1860,1110),fill=(50,45,40,230),width=30); d.ellipse((1835,585,1885,635),fill=(79,70,58,240))
    # local focus around protagonist
    focus=Image.new('RGBA',(W,H),(0,0,0,0)); fd=ImageDraw.Draw(focus,'RGBA'); fd.ellipse((850,420,1590,980),fill=(244,229,184,24)); focus=focus.filter(ImageFilter.GaussianBlur(28))
    return Image.alpha_composite(Image.alpha_composite(base,focus),art)

def label(im,text):
    out=im.copy(); d=ImageDraw.Draw(out); d.rounded_rectangle((24,24,360,80),12,fill=(22,20,18,210)); d.text((42,39),text,fill=(242,224,188,255)); return out
def contact(current,versions):
    sheet=Image.new('RGB',(1920,1080),(20,18,16)); panels=[current]+versions; names=['CURRENT D','V1 MINIMAL','V2 BALANCED','V3 RICH']
    for i,(im,n) in enumerate(zip(panels,names)):
        thumb=label(im,n).resize((960,540)); sheet.paste(thumb.convert('RGB'),((i%2)*960,(i//2)*540))
    return sheet
def debug(im):
    x=im.copy(); d=ImageDraw.Draw(x,'RGBA')
    zones=[('FG',(0,170,520,1080),(244,90,80,55)),('MG',(520,360,1500,1040),(80,210,120,42)),('BG',(160,240,1650,790),(80,150,245,36)),('FAR_BG',(1450,160,1910,770),(210,120,245,42))]
    for n,b,c in zones: d.rectangle(b,outline=c[:3]+(210,),width=8); d.text((b[0]+12,b[1]+10),n,fill=c[:3]+(255,))
    for text,pos in [('PRIMARY ACTION',(1050,520)),('SECONDARY ACTION',(600,500)),('MICRO-STORY',(1250,390))]: d.text(pos,text,fill=(255,235,120,255),stroke_width=2,stroke_fill=(20,20,20,230))
    path=[(230,450),(1100,620),(450,280),(1320,510)]; d.line(path,fill=(255,210,65,230),width=8); [d.ellipse((a-10,b-10,a+10,b+10),fill=(255,210,65,255)) for a,b in path]
    d.text((720,90),'EYE PATH: FG DOCTOR → PATIENT → WINDOW → NURSE',fill=(255,230,150,255),stroke_width=2,stroke_fill=(20,20,20,220))
    return x
def main():
    current=Image.open(BASE).convert('RGBA'); times={}; versions=[]
    for density,name in [(1,'Hospital_V1_Minimal.png'),(2,'Hospital_V2_Balanced.png'),(3,'Hospital_V3_Rich.png')]:
        t=time.perf_counter(); im=hospital(density); im.save(OUT/name); versions.append(im); times[name]=round(time.perf_counter()-t,3)
    versions[1].save(OUT/'Hospital_OTS_Vitality_Dv2.png')
    contact(current,versions).save(OUT/'hospital_vitality_contact_sheet.png'); debug(versions[2]).save(OUT/'hospital_vitality_debug.png')
    plans={
      'scene_id':'S02_HOSPITAL_OTS','camera_locked':{'shot':'OTS','perspective':'ONE_POINT','horizon':.52,'primary_vp':[.38,.52]},
      'shared_story_moment':{'primary_action':'Bandaged patient reacts toward foreground doctor','secondary_action':'Nurse adjusts blanket on another patient','background_micro_story':'Orderly carries basin through deeper corridor','far_background':'Subtle silhouette crosses doorway','environmental_motion':['partially pulled curtain drifting','paper corner lifting'],'eye_path':['FG_DOCTOR','PATIENT','WINDOW_LIGHT','NURSE']},
      'density_variants':{'V1_MINIMAL':{'activity':'LOW_ACTIVITY','richness':'MINIMAL','events':['primary','secondary']},'V2_BALANCED':{'activity':'MEDIUM_ACTIVITY','richness':'NORMAL','events':['primary','secondary','orderly micro-story','far silhouette']},'V3_RICH':{'activity':'HIGH_ACTIVITY','richness':'RICH','events':['primary','secondary','orderly micro-story','curtain action','visitor reaction','far silhouette']}},
      'prop_states':[{'prop':'document','state':'OPEN'},{'prop':'cloth','state':'USED'},{'prop':'curtain','state':'PARTIALLY_PULLED'}],
      'lighting':{'primary_light_reason':'Cold window light guides eye to protagonist','secondary_light':'Weak warm interior bounce','shadow_zone':'Foreground doctor'},'quiet_zones':[{'x':.42,'y':.04,'width':.22,'height':.20}],'asymmetry_bias':.72
    }
    (OUT/'scene_vitality_plan.json').write_text(json.dumps(plans,indent=2),encoding='utf-8')
    (OUT/'zero_cost_ledger.json').write_text(json.dumps({'paid_apis':0,'paid_assets':0,'gemini_image_calls':0,'paid_cost_usd':0.0,'render_times_seconds':times},indent=2),encoding='utf-8')
    (OUT/'scene_vitality_report.md').write_text('# Hospital Scene Vitality Test\n\nOne locked S02 hospital story moment was rendered at three activity densities. V1 adds one readable secondary action; V2 adds one background micro-story and far-depth life; V3 adds action across all depth planes while preserving a quiet zone and hero focus. Props carry non-default states and light directs the eye to the patient.\n\nNo aesthetic score was generated. Human review should judge occupation, action readability, micro-story clarity, foreground depth, hero clarity, and richness versus clutter.\n\nPaid cost: **$0.00**.\n\nStatus: **AWAITING_HUMAN_SCENE_VITALITY_REVIEW**\n',encoding='utf-8')
    print(json.dumps({'output':str(OUT),'times':times},indent=2))
if __name__=='__main__': main()
