from __future__ import annotations
import json,time,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
ROOT=Path(__file__).parents[3]; sys.path.insert(0,str(ROOT))
from pipeline.director_v2.performance.engine import ActorIntent,CharacterPerformanceDNA,CharacterPerformanceEngine,validate_actor

OUT=ROOT/'output'/'parallel_track_a_character_engine'; OUT.mkdir(parents=True,exist_ok=True)
SRC=ROOT/'output'/'zero_cost_visual_test'; W,H=1920,1080
REGISTRY={"version":"1.0","actions":{}}
for verb in "STAND WALK RUN TURN LOOK OBSERVE LISTEN SPEAK WHISPER ARGUE POINT GESTURE READ WRITE REACH GRIP HOLD CARRY PULL PUSH PLACE PICK_UP HAND_OVER RECEIVE OPEN CLOSE LEAN SIT RISE CROUCH KNEEL LIE DUCK BRACE HIDE CLIMB FALL SUPPORT HELP OPERATE SALUTE REACT FLINCH FREEZE".split():
    REGISTRY['actions'][verb]={"target_required":verb in "LOOK OBSERVE POINT REACH GRIP HOLD CARRY PULL PUSH PLACE PICK_UP HAND_OVER RECEIVE OPEN CLOSE LEAN SIT LIE SUPPORT HELP OPERATE".split(),"whole_body":verb in "WALK RUN CARRY PULL PUSH LEAN RISE CROUCH KNEEL LIE DUCK BRACE CLIMB FALL SUPPORT HELP".split()}

def fixtures():
    dna=CharacterPerformanceDNA()
    return {
      'HOSPITAL':[
        ActorIntent('DOCTOR','OBSERVE',[.22,.76],1.55,.98,'PATIENT',[1180,720],[1180,720],'THREE_QUARTER_BACK_RIGHT','FORWARD','ATTENTIVE','SUBTLE','NEAR_FOREGROUND'),
        ActorIntent('PATIENT','REACT',[.68,.77],.95,.82,'DOCTOR',[470,610],[470,610],'PROFILE_LEFT','LYING','NERVOUS','SUBTLE','SUBJECT','LIE_CONTACT'),
        ActorIntent('NURSE','REACH',[.47,.72],.78,.89,'BED_RAIL',[820,720],[780,700],'THREE_QUARTER_LEFT','FORWARD','ATTENTIVE','NORMAL','SECONDARY','HAND_CONTACT'),
      ],
      'BEER_HALL':[
        ActorIntent('SPEAKER','GESTURE',[.56,.76],1.1,.92,'LISTENER',[700,610],[700,610],'THREE_QUARTER_LEFT','FORWARD','CONFIDENT','NORMAL','SUBJECT'),
        ActorIntent('LISTENER','LISTEN',[.36,.78],.9,.92,'SPEAKER',[1070,610],[1070,610],'THREE_QUARTER_RIGHT','CENTERED','ATTENTIVE','SUBTLE','SECONDARY'),
        ActorIntent('WAITER','CARRY',[.76,.66],.65,.82,'TABLE',[1500,760],[1500,760],'PROFILE_RIGHT','RIGHT','CALM','NORMAL','BACKGROUND','GRIP_CONTACT','STEINS'),
      ],
      'TRENCH':[
        ActorIntent('SOLDIER_A','PUSH',[.48,.70],1.0,.90,'CRATE',[1100,760],[1100,760],'THREE_QUARTER_RIGHT','BRACED','DETERMINED','STRONG','SUBJECT','HAND_CONTACT'),
        ActorIntent('SOLDIER_B','CARRY',[.68,.68],.78,.87,'SUPPLY_POINT',[1450,650],[1450,650],'THREE_QUARTER_BACK_RIGHT','RIGHT','DETERMINED','NORMAL','SECONDARY','GRIP_CONTACT','AMMO_BOX'),
        ActorIntent('LOOKOUT','OBSERVE',[.28,.62],.62,.79,'PARAPET',[560,360],[560,360],'THREE_QUARTER_BACK_LEFT','FORWARD','SUSPICIOUS','SUBTLE','BACKGROUND'),
      ]}

def paths(name):
    m={'HOSPITAL':('S02_HOSPITAL_OTS','S02_HOSPITAL_OTS_SH02_OTS_WARD_env.png','S02_HOSPITAL_OTS_composite.png'),'BEER_HALL':('S04_BEER_HALL_DEEP','S04_BEER_HALL_DEEP_SH04_DEEP_PERSPECTIVE_env.png','S04_BEER_HALL_DEEP_composite.png'),'TRENCH':('S01_TRENCH_GROUND','S01_TRENCH_GROUND_SH01_GROUND_LEVEL_env.png','S01_TRENCH_GROUND_composite.png')}[name]
    return SRC/m[0]/m[1],SRC/m[0]/m[2]

def contact_sheet(rows):
    s=Image.new('RGB',(1920,1080),'#151412'); rh=360
    for i,(name,before,after) in enumerate(rows):
      s.paste(before.resize((960,rh)).convert('RGB'),(0,i*rh)); s.paste(after.resize((960,rh)).convert('RGB'),(960,i*rh)); d=ImageDraw.Draw(s); d.rectangle((0,i*rh,1920,i*rh+34),fill=(20,19,18)); d.text((18,i*rh+10),f'{name} BEFORE',fill='#ead9b7'); d.text((978,i*rh+10),f'{name} AFTER',fill='#ead9b7')
    return s

def detail_sheet(afters,debugs):
    s=Image.new('RGB',(1920,1080),'white'); tiles=[]
    for n in ['HOSPITAL','BEER_HALL','TRENCH']:
      im=debugs[n]; tiles.append(im.crop((350,300,1550,980)).resize((640,540)))
    for i,t in enumerate(tiles): s.paste(t.convert('RGB'),(i*640,0))
    for i,n in enumerate(['HOSPITAL','BEER_HALL','TRENCH']): s.paste(afters[n].crop((400,450,1500,1000)).resize((640,540)).convert('RGB'),(i*640,540))
    return s

def silhouette_sheet(engine,solved_by):
    s=Image.new('RGB',(1920,1080),'white');
    for i,n in enumerate(['HOSPITAL','BEER_HALL','TRENCH']):
      blank=Image.new('RGBA',(1920,1080),(255,255,255,255)); rendered=engine.render(blank,solved_by[n]); mask=ImageChops.difference(rendered.convert('RGB'),blank.convert('RGB')).convert('L').point(lambda v:255 if v>12 else 0); sil=Image.new('RGB',(1920,1080),'white'); sil.paste((0,0,0),mask=mask); sil=sil.resize((640,1080)); s.paste(sil,(i*640,0)); ImageDraw.Draw(s).text((i*640+20,20),n,fill='red')
    return s

def main():
    eng=CharacterPerformanceEngine(); fx=fixtures(); rows=[]; afters={}; debugs={}; solved_by={}; checks=[]; times={}
    for name,intents in fx.items():
      env,bef=paths(name); t=time.perf_counter(); solved=[eng.solve(i) for i in intents]; base=Image.open(env); after=eng.render(base,solved); debug=eng.render(base,solved,True); times[name]=round(time.perf_counter()-t,3)
      before=Image.open(bef); rows.append((name,before,after)); after.save(OUT/f'{name.lower()}_character_after.png'); afters[name]=after; debugs[name]=debug; solved_by[name]=solved
      for a in solved: checks.extend(validate_actor(a))
    contact_sheet(rows).save(OUT/'character_engine_contact_sheet.png'); detail_sheet(afters,debugs).save(OUT/'character_engine_detail_sheet.png'); silhouette_sheet(eng,solved_by).save(OUT/'character_engine_silhouette_sheet.png')
    dbg=Image.new('RGB',(1920,1080),'#171717')
    for i,n in enumerate(['HOSPITAL','BEER_HALL','TRENCH']): dbg.paste(debugs[n].resize((640,1080)).convert('RGB'),(i*640,0))
    dbg.save(OUT/'character_engine_debug_sheet.png')
    (OUT/'character_action_registry.json').write_text(json.dumps(REGISTRY,indent=2),encoding='utf-8')
    summary={"checks":checks,"summary":{"total":len(checks),"passed":sum(c['passed'] for c in checks),"failed":sum(not c['passed'] for c in checks)}}; (OUT/'character_validation_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (OUT/'track_a_contract_requests.json').write_text(json.dumps({"requests":[{"requested_field":"character_layer_input.environment_anchors","reason":"Generic contacts need optional normalized affordance anchors without owning environment schemas","expected_type":"dict[str, [float,float]]","consumer":"CharacterPerformanceEngine adapter","backward_compatibility_impact":"NONE; optional adapter input with defaults"},{"requested_field":"character_layer_input.ground_plane","reason":"Perspective-aware grounding benefits from a read-only ground-plane descriptor","expected_type":"optional object","consumer":"grounding adapter","backward_compatibility_impact":"NONE; current ground_y fallback remains"}]},indent=2),encoding='utf-8')
    (OUT/'character_performance_architecture.md').write_text('''# Track A — Generic Character Performance Engine\n\nPipeline: ActorIntent → semantic action registry → parametric pose solver → body-weight/orientation → eyeline → contact/object attachment → depth-aware Stickman layer → structural validation.\n\nThe engine is story-agnostic. Hospital, beer hall, and trench are fixtures only. It reads environment pixels and optional anchors but owns no environment, camera, lighting, location, material, or composition contracts. Actions use reusable verbs and whole-body parameters rather than location-specific pose names.\n\nNo external dependency or repository was added. Paid cost: **$0.00**.\n\nStatus: **AWAITING_PARALLEL_TRACK_A_REVIEW**\n''',encoding='utf-8')
    created=['pipeline/director_v2/performance/engine.py','pipeline/director_v2/performance/track_a_regression.py']+[f'output/parallel_track_a_character_engine/{p.name}' for p in OUT.glob('*') if p.name!='track_a_changed_files.json']
    manifest={"created_files":[{"path":p,"reason":"Track A character engine implementation/evidence","ownership_category":"CHARACTER_PERFORMANCE"} for p in sorted(created)],"modified_files":[{"path":"pipeline/director_v2/performance/__init__.py","reason":"Export generic Track A engine classes","ownership_category":"CHARACTER_PERFORMANCE","SHARED_FILE_MODIFIED":False}],"deleted_files":[],"SHARED_FILE_MODIFIED":False,"explanation":"No shared SceneBlueprint, environment, location, camera, lighting, composition, or asset schema was modified by this Track A task."}
    (OUT/'track_a_changed_files.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (OUT/'zero_cost_ledger.json').write_text(json.dumps({'paid_api_calls':0,'paid_image_generation':0,'paid_assets':0,'paid_cost_usd':0.0,'render_times_seconds':times},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT),'validation':summary['summary'],'times':times},indent=2))
if __name__=='__main__': main()
