from __future__ import annotations
import json,time
from dataclasses import asdict
from pathlib import Path
from PIL import Image,ImageDraw,ImageEnhance,ImageFilter,ImageChops
import sys
ROOT=Path(__file__).parents[3]; sys.path.insert(0,str(ROOT))
from pipeline.director_v2.performance.blocking import ActorBlockingPlan,HandContactAnchor,InteractionSolver,PerformancePlan

OUT=ROOT/'output'/'hospital_performance_test'; OUT.mkdir(parents=True,exist_ok=True)
BASE=ROOT/'output'/'renderer_bakeoff'/'D_paper_rough_svg_texture.png'; CURRENT=ROOT/'output'/'hospital_vitality_test'/'Hospital_V2_Balanced.png'; W,H=1920,1080

def plans():
    return PerformancePlan('S02_HOSPITAL_OTS','BALANCED',1918,[
      ActorBlockingPlan('DOCTOR_FG','PRIMARY_PARTNER',[.16,.58],'NEAR_FOREGROUND','THREE_QUARTER_BACK_RIGHT','PATIENT_MAIN','PATIENT_MAIN','LOOK_DOWN_RIGHT','FORWARD','LEAN_IN','PATIENT_MAIN','GESTURE_SUBTLE','CONCERNED','SUBTLE','DIAGONAL_RIGHT','HIGH',[HandContactAnchor('RIGHT','PATIENT_MAIN','attention_anchor',[.49,.62],'GESTURE_TOWARD')],[],['doctor','main_bed']),
      ActorBlockingPlan('PATIENT_MAIN','PRIMARY',[.66,.70],'SUBJECT_PLANE','PROFILE_LEFT','DOCTOR_FG','DOCTOR_FG','LOOK_UP_LEFT','LYING','REACT','MAIN_BED','REACT_TOWARD','TENSE_LISTENING','SUBTLE','RECLINED_LEFT','HIGH',[],[],['blanket','patient','bed_rail']),
      ActorBlockingPlan('NURSE_01','SECONDARY',[.44,.66],'SECONDARY_PLANE','THREE_QUARTER_RIGHT','PATIENT_02','BLANKET_02','LOOK_DOWN_LEFT','FORWARD','LEAN_IN','BLANKET_02','ADJUST_BLANKET','FOCUSED','NORMAL','DIAGONAL_LEFT','MEDIUM',[HandContactAnchor('LEFT','BLANKET_02','left_grip',[.36,.65],'GRIP'),HandContactAnchor('RIGHT','BED_02','rail_anchor',[.40,.67],'STABILIZE')],[[.42,.75],[.47,.76]],['back_arm','blanket','front_hand','bed_rail']),
      ActorBlockingPlan('ORDERLY_BG','BACKGROUND',[.70,.55],'BACKGROUND','THREE_QUARTER_BACK_RIGHT','CORRIDOR_EXIT','CORRIDOR_EXIT','LOOK_FORWARD_RIGHT','RIGHT_LEG','WALK_INTO_DEPTH','BASIN_01','CARRY_BASIN','TASK_FOCUSED','NORMAL','DIAGONAL_RIGHT','LOW',[HandContactAnchor('LEFT','BASIN_01','left_handle',[.69,.52],'HOLD'),HandContactAnchor('RIGHT','BASIN_01','right_handle',[.73,.52],'HOLD')],[[.68,.60],[.72,.59]],['far_arm','torso','basin','near_arm']),
    ],['DOCTOR_FG → PATIENT_MAIN','PATIENT_MAIN → DOCTOR_FG','NURSE_01 → BLANKET_02','ORDERLY_BG → CORRIDOR_EXIT'],['PATIENT_MAIN','DOCTOR_FG','NURSE_01','ORDERLY_BG'])

def limb(d,pts,color,w): d.line(pts,fill=color,width=w,joint='curve')
def head(d,c,r,look,color,w):
    x,y=c; d.ellipse((x-r,y-r,x+r,y+r),fill=(220,211,193,245),outline=color,width=w)
    dx={'LEFT':-1,'RIGHT':1}.get('LEFT' if 'LEFT' in look else 'RIGHT' if 'RIGHT' in look else '',0); dy=-1 if 'UP' in look else 1 if 'DOWN' in look else 0
    d.ellipse((x+dx*r*.45-2,y+dy*r*.3-2,x+dx*r*.45+3,y+dy*r*.3+3),fill=color)
def render(cinematic=False,debug=None):
    base=Image.open(BASE).convert('RGBA')
    # performance staging layer
    a=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(a,'RGBA')
    # secondary bed and state-changing blanket
    d.rounded_rectangle((275,590,865,760),18,fill=(166,150,127,210),outline=(57,52,47,220),width=9)
    d.ellipse((330,592,388,650),fill=(220,210,190,245),outline=(65,58,52,230),width=5)
    d.line((350,625,465,670),fill=(65,61,56,220),width=8); d.line((465,670,655,670),fill=(65,61,56,220),width=8)
    blanket=[(390,625),(725,610),(820,690),(655,735),(405,705)]
    d.polygon(blanket,fill=(135,151,143,235),outline=(64,70,66,230))
    # Nurse: forward diagonal, bent knees, two real contacts
    ink=(58,57,53,225); lw=8; hx,hy=865,480; head(d,(hx,hy),28,'LOOK_DOWN_LEFT',ink,lw)
    limb(d,[(855,508),(825,565),(790,625)],ink,lw) # spine/line of action
    limb(d,[(840,535),(750,575),(690,625)],ink,lw) # grip blanket
    limb(d,[(842,540),(815,600),(770,670)],ink,lw) # stabilize rail
    limb(d,[(790,625),(750,735),(715,810)],ink,lw); limb(d,[(790,625),(835,720),(885,790)],ink,lw)
    d.ellipse((700,797,745,814),fill=(45,44,41,190)); d.ellipse((872,781,915,798),fill=(45,44,41,190))
    # contact hands over blanket/rail and pulled blanket ridge
    d.ellipse((678,613,704,639),fill=(210,193,171,245),outline=ink,width=4); d.ellipse((758,657,784,681),fill=(210,193,171,245),outline=ink,width=4)
    d.line((685,627,820,690),fill=(211,207,183,150),width=7)
    # Orderly moving into depth carrying basin with both hands
    bg=(91,91,85,155); head(d,(1320,410),18,'LOOK_RIGHT',bg,4); limb(d,[(1318,429),(1340,485),(1375,535)],bg,5)
    limb(d,[(1332,460),(1370,490),(1400,500)],bg,5); limb(d,[(1332,460),(1350,505),(1390,500)],bg,5)
    limb(d,[(1375,535),(1348,585),(1320,620)],bg,5); limb(d,[(1375,535),(1418,570),(1450,590)],bg,5)
    d.ellipse((1375,485,1435,515),fill=(150,155,147,195),outline=bg,width=4); d.ellipse((1300,608,1350,624),fill=(45,45,42,65)); d.ellipse((1430,580,1475,596),fill=(45,45,42,55))
    # main patient on existing bed: torso tension, head turn and raised reacting hand
    hero=(45,47,48,235); px,py=1180,735; d.line((1120,718,1305,736),fill=hero,width=10); head(d,(1085,700),34,'LOOK_UP_LEFT',hero,7)
    limb(d,[(1135,718),(1088,665),(1045,640)],hero,8); d.ellipse((1032,628,1058,653),fill=(211,195,174,245),outline=hero,width=4)
    # blanket overlap and rail in front = semantic occlusion
    d.polygon([(1150,730),(1435,720),(1535,790),(1220,820)],fill=(176,185,171,215),outline=(72,72,66,205))
    d.line((1090,825,1565,825),fill=(54,50,45,240),width=12)
    # FG doctor, cropped back/shoulder with leaned head and directed gesture
    d.ellipse((-70,130,410,610),fill=(42,44,45,248),outline=(20,21,22,250),width=15)
    d.polygon([(-80,460),(290,430),(530,1080),(-100,1080)],fill=(46,48,49,250),outline=(20,21,22,250))
    d.line((230,560,520,655),fill=(40,42,43,245),width=34); d.line((520,655,690,625),fill=(40,42,43,245),width=29); d.ellipse((672,610,710,645),fill=(171,153,131,240),outline=(42,40,38,245),width=6)
    # hierarchy lighting, hero first; nurse secondary; orderly suppressed
    glow=Image.new('RGBA',(W,H),(0,0,0,0)); gd=ImageDraw.Draw(glow,'RGBA'); gd.ellipse((930,500,1650,960),fill=(245,229,183,34)); gd.ellipse((570,430,1030,850),fill=(224,226,200,18)); glow=glow.filter(ImageFilter.GaussianBlur(35))
    out=Image.alpha_composite(Image.alpha_composite(base,glow),a)
    if cinematic:
        # closer camera while preserving OTS and all four actors
        out=out.crop((90,70,1810,1038)).resize((W,H),Image.Resampling.LANCZOS)
        vign=Image.new('RGBA',(W,H),(0,0,0,0)); vd=ImageDraw.Draw(vign,'RGBA'); vd.rectangle((0,0,W,H),outline=(20,18,17,75),width=75); out=Image.alpha_composite(out,vign)
    if debug: return make_debug(out,debug,cinematic)
    return out

def make_debug(im,kind,cinematic=False):
    x=im.copy(); d=ImageDraw.Draw(x,'RGBA')
    if kind=='staging':
      boxes=[('DOCTOR FG',(0,100,520,1075),'#ff665e'),('PATIENT PRIMARY',(970,590,1580,880),'#ffd84f'),('NURSE SECONDARY',(640,430,930,830),'#58db91'),('ORDERLY BG',(1260,360,1500,640),'#67a9ff')]
      for n,b,c in boxes: d.rectangle(b,outline=c,width=7); d.text((b[0]+8,b[1]+8),n,fill=c,stroke_width=2,stroke_fill='black')
      for p,q in [((350,330),(1085,700)),((1085,700),(350,330)),((865,480),(700,625)),((1320,410),(1540,430))]: d.line((p,q),fill=(255,220,70,230),width=5)
      d.text((40,40),'DEPTH / ACTION / EYELINE / PRIORITY / OCCLUSION',fill='white',stroke_width=2,stroke_fill='black')
    elif kind=='interaction':
      anchors=[('BLANKET GRIP',(690,625)),('BED RAIL',(770,670)),('BASIN L',(1390,500)),('BASIN R',(1400,500)),('PATIENT REACT',(1045,640)),('FOOT L',(715,810)),('FOOT R',(885,790))]
      for n,(px,py) in anchors: d.ellipse((px-12,py-12,px+12,py+12),fill=(255,75,85,255),outline='white',width=3); d.text((px+14,py-8),n,fill='white',stroke_width=2,stroke_fill='black')
      d.text((40,40),'SEMANTIC CONTACT ANCHORS',fill='white',stroke_width=2,stroke_fill='black')
    return x

def silhouette():
    staged=render(False).convert('RGB'); base=Image.open(BASE).convert('RGB')
    delta=ImageChops.difference(staged,base).convert('L').point(lambda v: 255 if v>18 else 0)
    im=Image.new('RGB',(W,H),'white'); im.paste((0,0,0),mask=delta)
    d=ImageDraw.Draw(im); d.text((40,40),'POSE SILHOUETTE READABILITY — ACTORS + INTERACTION SHAPES',fill=(210,30,30)); return im
def contact_sheet(cur,perf,cine):
    s=Image.new('RGB',(1920,1080),(18,17,16)); ims=[cur,perf,cine]; names=['CURRENT V2 BALANCED','PERFORMANCE UPGRADE','PERFORMANCE + CINEMATIC STAGING']
    for i,(im,n) in enumerate(zip(ims,names)):
      w=640; panel=im.resize((640,1080)); s.paste(panel.convert('RGB'),(i*w,0)); ImageDraw.Draw(s).rectangle((i*w+12,18,i*w+620,64),fill=(15,15,15)); ImageDraw.Draw(s).text((i*w+28,32),n,fill=(245,225,184))
    return s
def detail_sheet(perf,cine):
    boxes=[(0,250,850,900),(560,390,1030,880),(1200,300,1540,680),(620,560,1510,900)]; s=Image.new('RGB',(1920,1080),(15,14,13))
    for i,b in enumerate(boxes):
      src=perf if i<3 else cine; crop=src.crop(b).resize((960,540)); s.paste(crop.convert('RGB'),((i%2)*960,(i//2)*540))
    return s
def main():
    p=plans(); anchors={'BLANKET_02.left_grip':[.36,.65],'BED_02.rail_anchor':[.40,.67],'BASIN_01.left_handle':[.69,.52],'BASIN_01.right_handle':[.73,.52],'PATIENT_MAIN.attention_anchor':[.49,.62]}; solver=InteractionSolver()
    t=time.perf_counter(); perf=render(False); t1=time.perf_counter()-t; t=time.perf_counter(); cine=render(True); t2=time.perf_counter()-t
    cur=Image.open(CURRENT).convert('RGBA'); perf.save(OUT/'Hospital_V2_Performance.png'); cine.save(OUT/'Hospital_V2_Performance_Cinematic.png')
    contact_sheet(cur,perf,cine).save(OUT/'hospital_performance_contact_sheet.png'); detail_sheet(perf,cine).save(OUT/'hospital_performance_detail_sheet.png')
    make_debug(perf,'staging').save(OUT/'hospital_actor_staging_debug.png'); silhouette().save(OUT/'hospital_pose_silhouette_debug.png'); make_debug(perf,'interaction').save(OUT/'hospital_interaction_debug.png')
    (OUT/'actor_blocking_plan.json').write_text(json.dumps({'scene_id':p.scene_id,'vitality_lock':p.vitality_lock,'actors':[asdict(a) for a in p.actors]},indent=2),encoding='utf-8')
    (OUT/'performance_plan.json').write_text(json.dumps(p.to_dict(),indent=2),encoding='utf-8')
    solved=[solver.solve(a,anchors) for a in p.actors]; (OUT/'interaction_report.json').write_text(json.dumps({'asset_anchors':anchors,'solutions':solved},indent=2),encoding='utf-8')
    report=f'''# Hospital Actor Performance Test\n\nVitality remains locked to **BALANCED**. Four existing actors were restaged; none were added.\n\n- Doctor: subtle lean-in gesture toward main patient; OTS crop, dark FG.\n- Main patient: lying with head turn, raised reacting hand, blanket and bed-rail occlusion.\n- Nurse: forward weight, bent knees/elbows, blanket grip and bed-rail stabilization.\n- Orderly: walk-into-depth stride while carrying basin with both hands.\n\nPose families added: semantic LEAN_IN, REACT_TOWARD, ADJUST_BLANKET and CARRY_BASIN variants. Eyelines and interaction targets are recorded in the JSON plans. Occlusion order is actor/action-specific.\n\nCinematic version changes crop from full 1920×1080 to a closer `(90,70)-(1810,1038)` view, preserving OTS and action hierarchy. No dependency changes.\n\nRender times: performance `{t1:.3f}s`; cinematic `{t2:.3f}s`. Paid cost: **$0.00**. No aesthetic score generated.\n\nStatus: **AWAITING_HUMAN_PERFORMANCE_REVIEW**\n'''; (OUT/'performance_test_report.md').write_text(report,encoding='utf-8')
    (OUT/'zero_cost_ledger.json').write_text(json.dumps({'paid_api_calls':0,'paid_image_generation':0,'paid_assets':0,'paid_cost_usd':0.0,'render_times_seconds':{'performance':round(t1,3),'cinematic':round(t2,3)}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT),'render_times':[round(t1,3),round(t2,3)]},indent=2))
if __name__=='__main__': main()
