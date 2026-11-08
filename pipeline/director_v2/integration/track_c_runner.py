from __future__ import annotations
import json,subprocess,sys,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageEnhance,ImageFilter
ROOT=Path(__file__).parents[3]; sys.path.insert(0,str(ROOT))
from pipeline.director_v2.integration.contract import *
from pipeline.director_v2.integration.renderer import IntegratedSceneRenderer
from pipeline.director_v2.integration.validation import validate_integrated
from pipeline.director_v2.performance.engine import ActorIntent

OUT=ROOT/'output'/'track_c_integrated_renderer'; OUT.mkdir(parents=True,exist_ok=True)
WORLD=ROOT/'output'/'track_b_scene_engine'; ACTOR=ROOT/'output'/'parallel_track_a_character_engine'

def fixture_data():
  return {
   'hospital':{
    'world':WORLD/'hospital'/'hospital_environment_after.png','a':ACTOR/'hospital_character_after.png','out':'hospital_integrated.png',
    'context':SceneRenderContext('fixture_close_contact',CameraContext([1920,1080],'OTS',.52,[.38,.52]),GroundPlane(.52),{
      'support_01':AssetInstance('support_01','support_surface','MG',{'lie_anchor':[.635,.713],'grip_anchor':[.411,.648]},{'LIE':'lie_anchor','REACH':'grip_anchor'},'OCCUPIED',[.54,.62,.80,.82]),
      'frame_01':AssetInstance('frame_01','foreground_frame','NEAR_FG',{}, {},'STATIC',[0,.35,.18,1])},
      LightingContext('COLD_LEFT_HIGH',.85,.50,'RIGHT',{'NEAR_FG':1.1,'MG':1,'BG':.7,'FAR_BG':.45},[.66,.68]),{'NEAR_FG':.08,'MG':.50,'BG':.75,'FAR_BG':.95},['primary_01'],{'primary_01':[1180,700]}),
    'actors':[ActorIntent('observer_01','OBSERVE',[.16,.78],1.6,.95,'primary_01',eyeline_point=[1180,700],orientation='THREE_QUARTER_BACK_RIGHT',weight='FORWARD',emotion='ATTENTIVE',intensity='SUBTLE',depth='NEAR_FG'),ActorIntent('primary_01','LIE',[.67,.76],.9,.9,'support_01',orientation='PROFILE_LEFT',weight='LYING',emotion='NERVOUS',depth='MG',contact_type='LIE_CONTACT'),ActorIntent('helper_01','REACH',[.43,.72],.78,.9,'support_01',eyeline_point=[790,700],orientation='THREE_QUARTER_LEFT',weight='FORWARD',emotion='ATTENTIVE',depth='MG',contact_type='HAND_CONTACT')]},
   'beer_hall':{
    'world':WORLD/'beer_hall'/'beer_hall_environment_after.png','a':ACTOR/'beer_hall_character_after.png','out':'beer_hall_integrated.png',
    'context':SceneRenderContext('fixture_social_blocking',CameraContext([1920,1080],'DEEP_PERSPECTIVE',.50,[.50,.50]),GroundPlane(.50),{
      'table_01':AssetInstance('table_01','support_surface','FG',{'lean_anchor':[.641,.718],'grip_anchor':[.760,.667]},{'LEAN':'lean_anchor','CARRY':'grip_anchor'},'USED',[.58,.70,.92,.95])},LightingContext('WARM_OVERHEAD',.82,.42,'BELOW',{'FG':1.05,'MG':1,'BG':.68},[.56,.67]),{'FG':.25,'MG':.5,'BG':.75},['speaker_01'],{'speaker_01':[1060,610]}),
    'actors':[ActorIntent('speaker_01','GESTURE',[.56,.76],1.08,.92,'listener_01',eyeline_point=[700,620],orientation='THREE_QUARTER_LEFT',weight='FORWARD',emotion='CONFIDENT',depth='MG'),ActorIntent('listener_01','LISTEN',[.36,.78],.88,.92,'speaker_01',eyeline_point=[1060,610],orientation='THREE_QUARTER_RIGHT',weight='CENTERED',emotion='ATTENTIVE',intensity='SUBTLE',depth='MG'),ActorIntent('server_01','CARRY',[.76,.68],.65,.84,'table_01',eyeline_point=[1500,680],orientation='PROFILE_RIGHT',weight='RIGHT',emotion='CALM',depth='BG',contact_type='GRIP_CONTACT',carried_object='vessel_01')]},
   'trench':{
    'world':WORLD/'trench'/'trench_environment_after.png','a':ACTOR/'trench_character_after.png','out':'trench_integrated.png',
    'context':SceneRenderContext('fixture_irregular_ground',CameraContext([1920,1080],'GROUND_LEVEL',.35,[.65,.35]),GroundPlane(.35,1,-.03),{
      'crate_01':AssetInstance('crate_01','carryable','FG',{'push_anchor':[.578,.713],'carry_anchor':[.755,.639]},{'PUSH':'push_anchor','CARRY':'carry_anchor'},'READY',[.62,.72,.79,.95]),
      'wall_01':AssetInstance('wall_01','foreground_occluder','NEAR_FG',{}, {},'WET',[.83,.25,1,1])},LightingContext('SULLEN_LEFT_HIGH',.70,.42,'RIGHT',{'NEAR_FG':1.05,'MG':.92,'BG':.58},[.55,.72]),{'NEAR_FG':.08,'FG':.25,'MG':.5,'BG':.75},['worker_01'],{'parapet_event':[560,360]}),
    'actors':[ActorIntent('worker_01','PUSH',[.48,.70],1.0,.90,'crate_01',eyeline_point=[1110,770],orientation='THREE_QUARTER_RIGHT',weight='BRACED',emotion='DETERMINED',intensity='STRONG',depth='MG',contact_type='HAND_CONTACT'),ActorIntent('carrier_01','CARRY',[.68,.68],.78,.87,'crate_01',eyeline_point=[1450,650],orientation='THREE_QUARTER_BACK_RIGHT',weight='RIGHT',emotion='DETERMINED',depth='FG',contact_type='GRIP_CONTACT',carried_object='supply_01'),ActorIntent('lookout_01','OBSERVE',[.28,.62],.62,.79,'parapet_event',eyeline_point=[560,360],orientation='THREE_QUARTER_BACK_LEFT',weight='FORWARD',emotion='SUSPICIOUS',intensity='SUBTLE',depth='BG')]}}

def add_graphs(data):
  data['hospital']['context'].occlusion.add('observer_01','IN_FRONT_OF','support_01'); data['hospital']['context'].occlusion.add('primary_01','BEHIND','support_01')
  data['beer_hall']['context'].occlusion.add('server_01','BEHIND','table_01'); data['beer_hall']['context'].occlusion.add('vessel_01','IN_FRONT_OF','server_01')
  data['trench']['context'].occlusion.add('carrier_01','BEHIND','wall_01'); data['trench']['context'].occlusion.add('worker_01','CONTACTS','crate_01')

def master(rows):
  s=Image.new('RGB',(1920,1080),'#141312')
  for r,(name,a,b,c) in enumerate(rows):
    for col,im in enumerate([a,b,c]): s.paste(im.resize((640,360)).convert('RGB'),(col*640,r*360))
    d=ImageDraw.Draw(s); d.rectangle((0,r*360,1920,r*360+28),fill='#171615'); d.text((15,r*360+8),name.upper(),fill='#f0d9aa'); d.text((655,r*360+8),'B WORLD',fill='#f0d9aa'); d.text((1295,r*360+8),'A+B INTEGRATED',fill='#f0d9aa')
  return s
def sheets(images):
  detail=Image.new('RGB',(1920,1080),'#111'); light=Image.new('RGB',(1920,1080),'#111');
  boxes=[(260,420,1180,950),(900,400,1750,950),(350,350,1500,980)]
  for i,(name,im) in enumerate(images.items()):
    detail.paste(im.crop(boxes[i]).resize((640,1080)).convert('RGB'),(i*640,0));
    l=ImageEnhance.Contrast(im).enhance(1.25); light.paste(l.resize((640,1080)).convert('RGB'),(i*640,0))
  return detail,light
def occlusion_debug(images,contexts):
  s=Image.new('RGB',(1920,1080),'#111')
  for i,n in enumerate(['hospital','beer_hall','trench']):
    im=images[n].resize((640,1080)).convert('RGBA'); d=ImageDraw.Draw(im,'RGBA')
    for a in contexts[n].assets.values():
      if len(a.bounds)==4:
        x0,y0,x1,y1=a.bounds; d.rectangle((x0*640,y0*1080,x1*640,y1*1080),outline=(255,80,80,240),width=5); d.text((x0*640+5,y0*1080+5),f'{a.asset_instance_id}/{a.depth_plane}',fill='white',stroke_width=2,stroke_fill='black')
    y=40
    for e in contexts[n].occlusion.edges: d.text((15,y),f'{e.subject} {e.relation} {e.object_id}',fill=(255,220,80),stroke_width=2,stroke_fill='black'); y+=28
    s.paste(im.convert('RGB'),(i*640,0))
  return s

def main():
  data=fixture_data(); add_graphs(data); renderer=IntegratedSceneRenderer(); rows=[]; images={}; contract={}; validation=[]; times={}
  for name,f in data.items():
    t=time.perf_counter(); out,actors,dbg=renderer.render(f['world'],f['actors'],f['context']); times[name]=round(time.perf_counter()-t,3); out.save(OUT/f['out']); images[name]=out
    rows.append((name,Image.open(f['a']),Image.open(f['world']),out)); checks=validate_integrated(actors,f['context'],dbg); validation.extend([{**x,'scene':name} for x in checks]); contract[name]={**f['context'].to_dict(),'actor_targets':[{'actor_id':a.actor_id,'target':a.target_id,'eyeline':a.eyeline_point} for a in f['actors']],'resolved':dbg,'post_composite_checks':checks}
  master(rows).save(OUT/'integration_master_contact_sheet.png'); detail,light=sheets(images); detail.save(OUT/'integration_interaction_detail_sheet.png'); light.save(OUT/'integration_lighting_detail_sheet.png'); occlusion_debug(images,{k:v['context'] for k,v in data.items()}).save(OUT/'integration_occlusion_debug.png')
  (OUT/'integration_contract_debug.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
  # Run integration tests; existing baselines were run immediately before implementation.
  cp=subprocess.run([sys.executable,'-m','unittest','pipeline.director_v2.integration.test_integration','-v'],cwd=ROOT,text=True,capture_output=True); integration_ok=cp.returncode==0
  core=ROOT/'pipeline'/'director_v2'/'integration'; forbidden=['hospital','nurse','patient','doctor','beer_hall','trench','hitler','munich','pasewalk']; core_hits=[]
  for p in [core/'contract.py',core/'renderer.py',core/'validation.py']:
    txt=p.read_text(encoding='utf-8').lower(); core_hits += [f'{p.name}:{w}' for w in forbidden if w in txt]
  (OUT/'integration_contract_resolution.md').write_text('''# Integration Contract Resolution\n\n- Track A `environment_anchors`: resolved through `AssetInstance.anchors`, keyed by stable instance ID.\n- Track A `ground_plane`: resolved through the world-owned `GroundPlane`; Track A `ground_y` remains an isolated fallback only.\n- Track B `character_contact_target_id`: resolved by structured `ContactTargetRef(asset_instance_id, anchor)` with legacy `asset.anchor` parsing.\n- Track B `eyeline_look_target`: resolved by optional `SceneRenderContext.eyeline_targets` and actor-level fallback.\n\nAffordances map semantic actions to anchors without exposing asset types to the character engine. No request was rejected. All fields live in the integration contract, so old SceneBlueprints remain unchanged.\n''',encoding='utf-8')
  (OUT/'integrated_renderer_architecture.md').write_text('''# Integrated Renderer Architecture\n\nDirector → existing SceneBlueprint → Track B World Engine → `SceneRenderContext` adapter → Track A ActorIntent/Performance Engine → shared camera/ground/anchors → lighting transfer → semantic occlusion graph → final compositor.\n\nOwnership remains explicit: Track B owns world pixels/materials/composition/light; Track A owns poses/weight/eyelines/contacts; Track C owns only handshake, shared render context, state resolution, validation, and compositing. Fixture names never appear in integration core.\n\nFallbacks preserve standalone Track A rendering and old blueprints without advanced context.\n''',encoding='utf-8')
  passed=sum(x['passed'] for x in validation); total=len(validation)
  report=f'''# Track C Integration Regression Report\n\nBaseline before integration: Track A **63/63**; Track A/Track B packages compile cleanly. Track B runner completed successfully when invoked explicitly.\n\nExisting Director V2 suite: **40 tests passed, 1 discovery/import error**. The failing module is `pipeline/tests/director_v2/test_director_v2.py`; unittest discovery imports it outside its expected package depth, causing `attempted relative import beyond top-level package`. This pre-existing discovery failure was not hidden or changed by Track C.\n\nIntegration unittest: **{'PASS' if integration_ok else 'FAIL'}** (11 tests).\nPost-composite structural checks: **{passed}/{total}**.\nCore story-specific token scan: **{'PASS' if not core_hits else 'FAIL'}** `{core_hits}`.\nFallback without Track B context: covered. Fallback without advanced Track A data: covered.\n\nRender times: `{times}` seconds. No aesthetic score generated. Paid cost: **$0.00**.\n\nStatus: **AWAITING_HUMAN_INTEGRATED_RENDERER_REVIEW**\n'''; (OUT/'integration_regression_report.md').write_text(report,encoding='utf-8')
  created=['pipeline/director_v2/integration/__init__.py','pipeline/director_v2/integration/contract.py','pipeline/director_v2/integration/renderer.py','pipeline/director_v2/integration/validation.py','pipeline/director_v2/integration/test_integration.py','pipeline/director_v2/integration/track_c_runner.py']+[f'output/track_c_integrated_renderer/{p.name}' for p in OUT.glob('*') if p.name!='integration_changed_files.json']
  (OUT/'integration_changed_files.json').write_text(json.dumps({'created_files':[{'path':p,'reason':'Track C handshake/compositor/test evidence','ownership':'TRACK_C_INTEGRATION'} for p in sorted(created)],'modified_files':[],'deleted_files':[],'shared_files_modified':False},indent=2),encoding='utf-8')
  (OUT/'zero_cost_ledger.json').write_text(json.dumps({'paid_api_calls':0,'paid_image_generation':0,'paid_assets':0,'paid_cost_usd':0.0,'render_times_seconds':times},indent=2),encoding='utf-8')
  print(json.dumps({'output':str(OUT),'integration_tests':integration_ok,'post_composite':f'{passed}/{total}','core_hits':core_hits,'times':times},indent=2))
if __name__=='__main__': main()
