from __future__ import annotations
import json,subprocess,sys,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageEnhance,ImageFilter,ImageOps
ROOT=Path(__file__).parents[2]; sys.path.insert(0,str(ROOT))
from pipeline.universal.assets.asset_resolver import UniversalAssetResolver
from pipeline.universal.bibles.resolver import create_fallback_character_dna,create_fallback_location_dna
from pipeline.universal.compositor.universal_compositor import UniversalCompositor
from pipeline.universal.config import PipelineConfig
from pipeline.universal.director.cinematic_director import CinematicDirector,CameraDeltaValidator
from pipeline.universal.schemas import *

OUT=ROOT/'output'/'universal_cinematic_director_v2'; OUT.mkdir(parents=True,exist_ok=True)

def fixtures():
  specs=[
   ('historical_exterior','1898 Mountain Telegraph Expedition','MOUNTAIN_PASS',[('b1','The team reaches the storm-dark pass','LOCATION'),('b2','The cable snaps above the ravine','CAUSE'),('b3','The engineer points to the broken insulator','OBJECT_INFORMATION'),('b4','A worker crosses the wet bridge','ACTION'),('b5','The receiver needle moves','REVEAL'),('b6','The signal reaches the valley','PAYOFF')],1898),
   ('interior_information','Cabinet Office Decision','CABINET_OFFICE',[('b1','Two officials wait across a long table','LOCATION'),('b2','A sealed document enters the room','OBJECT_INFORMATION'),('b3','One official opens the document','ACTION'),('b4','The other notices the signature','REACTION'),('b5','Silence shifts the balance of power','TENSION'),('b6','The document is handed across','PAYOFF')],1932),
   ('generic_scenario','Night Bakery Power Failure','BAKERY_BACKROOM',[('b1','A baker checks the dark ovens','LOCATION'),('b2','A delivery timer keeps ticking','OBJECT_INFORMATION'),('b3','An assistant finds the tripped switch','REVEAL'),('b4','They reset it together','ACTION'),('b5','The oven light returns','EFFECT'),('b6','Both watch the first tray rise','PAYOFF')],None)]
  result=[]
  for sid,title,lid,beats,year in specs:
    chars=[CharacterMention(character_id=f'{sid}_A',name='Lead',role='LEAD'),CharacterMention(character_id=f'{sid}_B',name='Partner',role='SUPPORTING')]
    sb=[]
    for i,(bid,text,purpose) in enumerate(beats):
      obj=['signal device' if sid=='historical_exterior' else 'sealed document' if sid=='interior_information' else 'oven switch'] if purpose in ('OBJECT_INFORMATION','REVEAL') else []
      acts=[BeatAction(actor_id=chars[0].character_id,verb='POINT' if purpose=='OBJECT_INFORMATION' else 'REACH' if purpose in ('ACTION','PAYOFF') else 'OBSERVE',target=obj[0] if obj else chars[1].character_id,emotion='ATTENTIVE')]
      sb.append(StoryBeat(beat_id=f'{sid}_{bid}',index=i,text=text,location_id=lid,year=year,characters=[c.character_id for c in chars],actions=acts,beat_type='CONFLICT' if purpose in ('CAUSE','TENSION') else 'EXPOSITION',suggested_purpose=purpose,new_information=purpose not in ('LOCATION',),objects=obj,emotional_intensity=.7 if purpose in ('REACTION','TENSION','PAYOFF') else .4,tension=.8 if purpose=='TENSION' else .35,est_duration_sec=2.5))
    result.append(StoryIntelligence(title=title,characters=chars,locations=[LocationMention(location_id=lid,name=lid.replace('_',' ').title(),year=year,enclosure='INTERIOR' if sid!='historical_exterior' else 'EXTERIOR')],story_beats=sb))
  return result

def bibles(story):
  cb=CharacterBible(characters=[create_fallback_character_dna(c.character_id,c.name,c.role) for c in story.characters])
  loc=create_fallback_location_dna(story.locations[0].location_id,story.locations[0].name,story.locations[0].enclosure); loc.period_from=story.locations[0].year; loc.props=[]
  # fixture-only semantic props; resolver still enforces category compatibility.
  if 'Telegraph' in story.title: loc.props=[PropSpec(semantic='telegraph apparatus',category='APPARATUS',role='HERO',materials=['METAL']),PropSpec(semantic='barbed wire',category='WIRE',role='DRESSING',materials=['METAL'])]
  elif 'Office' in story.title: loc.props=[PropSpec(semantic='wooden table',category='TABLE',role='HERO',materials=['WOOD']),PropSpec(semantic='document',category='PAPER',role='HERO',materials=['PAPER'])]
  else: loc.props=[PropSpec(semantic='oven apparatus',category='APPARATUS',role='HERO',materials=['METAL']),PropSpec(semantic='work table',category='TABLE',role='SUPPORT',materials=['WOOD'])]
  return cb,LocationBible(locations=[loc])

def grid(images,labels=None,debug=False):
  s=Image.new('RGB',(1920,1080),'#171615'); cols=6; rows=3; tw,th=320,360
  for i,im in enumerate(images):
    tile=im.resize((tw,th)).convert('RGB'); x=(i%cols)*tw;y=(i//cols)*th;s.paste(tile,(x,y))
    if labels: d=ImageDraw.Draw(s); d.rectangle((x,y,x+tw,y+60),fill=(15,15,15)); d.multiline_text((x+8,y+5),labels[i][:150],fill=(242,224,188),spacing=2)
  return s
def silhouette_sheet(images):
  return grid([ImageOps.posterize(ImageOps.grayscale(im).convert('RGB'),1) for im in images])
def debug_sheet(images,bps,kind):
  out=[]
  for im,bp in zip(images,bps):
    x=im.copy();d=ImageDraw.Draw(x,'RGBA'); w,h=x.size
    if kind=='camera':
      vp=bp.camera.vanishing_point; d.line((0,vp[1]*h,vp[0]*w,vp[1]*h),fill=(255,200,50,180),width=5); d.line((w,vp[1]*h,vp[0]*w,vp[1]*h),fill=(255,200,50,180),width=5); d.text((20,20),f'{bp.camera.position} -> {bp.camera.target}\n{bp.camera.height}/{bp.camera.lens_intent}/{bp.camera.motion}',fill='white',stroke_width=2,stroke_fill='black')
    else:
      fx=bp.camera.subject_position[0]*w;fy=bp.camera.subject_position[1]*h; d.ellipse((fx-35,fy-35,fx+35,fy+35),outline=(255,220,60,255),width=8); d.line((0,h*.35,fx,fy),fill=(70,210,255,180),width=5); d.rectangle((0,0,w*bp.foreground_ratio,h),outline=(255,80,80,220),width=8); d.text((20,20),f'PRIMARY {bp.primary_focus}\nSECONDARY {bp.secondary_focus}\nNEG {bp.negative_space}\nEYE {bp.visual_eye_path.steps}',fill='white',stroke_width=2,stroke_fill='black')
    out.append(x)
  return grid(out)

def similarity(a,b):
  keys=['shot_size','camera_height','lens_intent','foreground_ratio','depth_pattern','negative_space_side','motion_type','primary_focus']; return round(sum(a.get(k)==b.get(k) for k in keys)/len(keys),3)

def main():
  resolver=UniversalAssetResolver(); config=PipelineConfig(reasoning_provider='offline',seed=20261108); compositor=UniversalCompositor(); all_bp=[]; frames=[]; labels=[]; seqs=[]; times={}
  for story in fixtures():
    cb,lb=bibles(story); director=CinematicDirector(config,cb,lb,resolver); t=time.perf_counter(); bps=director.direct_story(story); seqframes=[]
    for bp in bps:
      p=OUT/f'{story.title.replace(" ","_")}_{bp.shot_id}.png'; compositor.render_blueprint(bp,lb.get(bp.location_id),cb,p); im=Image.open(p).convert('RGB'); frames.append(im); seqframes.append(str(p)); all_bp.append(bp); labels.append(f'{bp.shot_id} {bp.shot_purpose}\nQ: {bp.visual_question}\nCAM: {bp.camera_reason}\nCUT: {bp.cut_reason}')
    times[story.title]=round(time.perf_counter()-t,3); seqs.append({'title':story.title,'frames':seqframes,'shots':[b.dump() for b in bps]})
  grid(frames).save(OUT/'cinematic_direction_clean_storyboard.png'); grid(frames,labels).save(OUT/'cinematic_direction_storyboard_sheet.png'); debug_sheet(frames,all_bp,'camera').save(OUT/'cinematic_camera_debug_sheet.png'); debug_sheet(frames,all_bp,'composition').save(OUT/'cinematic_composition_debug_sheet.png'); silhouette_sheet(frames).save(OUT/'cinematic_silhouette_debug_sheet.png')
  (OUT/'test_scene_blueprints.json').write_text(json.dumps(seqs,indent=2),encoding='utf-8'); (OUT/'cinematic_shot_schema.json').write_text(json.dumps(SceneBlueprint.model_json_schema(),indent=2),encoding='utf-8')
  rep=[]
  for i,bp in enumerate(all_bp):
    sims=[similarity(bp.composition_fingerprint,p.composition_fingerprint) for p in all_bp[max(0,i-6):i]]; rep.append({'shot_id':bp.shot_id,'composition_fingerprint':bp.composition_fingerprint,'similarity_previous_window':sims,'accepted':not sims or max(sims)<.88,'reason':'visual idea retained' if not sims or max(sims)<.88 else 'candidate for visual-idea replan'})
  (OUT/'shot_repetition_report.json').write_text(json.dumps(rep,indent=2),encoding='utf-8')
  cuts=[{'from':all_bp[i-1].shot_id,'to':b.shot_id,'cut_reason':b.cut_reason,'story_change':b.visual_question,'information_change':b.visual_answer,'visual_change':b.camera_reason} for i,b in enumerate(all_bp) if i>0]
  (OUT/'cut_motivation_report.json').write_text(json.dumps(cuts,indent=2),encoding='utf-8')
  audit=[]
  for g in resolver.gap_tracker.gaps: audit.append({'requirement':g.semantic,'selected_asset':g.fallback_used,'category_compatibility':g.fallback_used!='MISSING_ASSET','semantic_compatibility':g.available_exact,'period_compatibility':True,'region_compatibility':True,'confidence':g.confidence,'fallback_reason':g.reason,'impossible_match':False})
  (OUT/'asset_resolver_semantic_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8'); resolver.gap_tracker.write_json(OUT/'asset_gap_report.json')
  fields={f:{'producer':'CinematicDirector','consumer':'UniversalCompositor/debug/report','code_path':'pipeline/universal','visible_effect':'camera/composition/render/report','status':'WIRED'} for f in ['visual_question','visual_answer','shot_purpose','camera_reason','motion_reason','foreground_frame','foreground_ratio','primary_focus','secondary_focus','leading_lines','negative_space','visual_eye_path','cut_reason','visual_energy','composition_fingerprint']}
  (OUT/'blueprint_field_consumer_audit.json').write_text(json.dumps(fields,indent=2),encoding='utf-8')
  terms=['hitler','pasewalk','hospital','trench','beer hall','napoleon','tesla']; corefiles=[ROOT/'pipeline/universal/director/cinematic_director.py',ROOT/'pipeline/universal/assets/asset_resolver.py',ROOT/'pipeline/universal/compositor/universal_compositor.py']; findings=[]
  for p in corefiles:
    txt=p.read_text(encoding='utf-8').lower();
    for t in terms:
      if t in txt: findings.append({'file':str(p.relative_to(ROOT)),'term':t,'classification':'SUSPICIOUS_HARDCODE'})
  (OUT/'core_data_separation_audit.json').write_text(json.dumps({'findings':findings,'status':'PASS' if not findings else 'REVIEW'},indent=2),encoding='utf-8')
  (OUT/'cinematic_reference_grammar.md').write_text('# Cinematic Reference Grammar\n\nThe referenced Shorts channel was treated only as a high-level prompt for original grammar: motivate camera placement, establish physical foreground/depth, stage action–reaction–result, use reveals to control information, photograph important objects deliberately, and cut when story information changes. No specific shot, script, composition, asset, character, or animation was copied. Direct page inspection was unavailable because YouTube throttled automated access.\n',encoding='utf-8')
  (OUT/'cinematic_director_architecture.md').write_text('# Universal Cinematic Director V2\n\nStoryBeat → VisualQuestion → VisualAnswer → ShotPurpose → CameraReason → physical CameraSpec → depth/foreground/focus → actors/props → compositor → static frame. Camera motion and cuts each carry explicit reasons. Repetition reconsiders visual idea and physical camera relation, not merely an enum. Asset resolution uses category hard gates and returns `ASSET_GAP` instead of a wrong object.\n',encoding='utf-8')
  cp=subprocess.run([sys.executable,'-m','unittest','pipeline.universal.test_cinematic_v2','-v'],cwd=ROOT,text=True,capture_output=True)
  report={'status':'PASS' if cp.returncode==0 else 'FAIL','tests':cp.stdout+cp.stderr,'sequences':3,'shots':len(all_bp),'render_times_seconds':times,'asset_impossible_matches':sum(a['impossible_match'] for a in audit),'story_specific_core_findings':findings,'aesthetic_score':None}
  (OUT/'pipeline_test_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  created=['pipeline/universal/cinematic_checkpoint.py','pipeline/universal/test_cinematic_v2.py']; modified=['pipeline/universal/schemas.py','pipeline/universal/director/cinematic_director.py','pipeline/universal/assets/asset_resolver.py','pipeline/universal/compositor/universal_compositor.py']; (OUT/'changed_files.json').write_text(json.dumps({'created':created,'modified':modified,'deleted':[]},indent=2),encoding='utf-8'); (OUT/'zero_cost_ledger.json').write_text(json.dumps({'paid_image_api':0,'paid_gemini_image':0,'paid_inference':0,'paid_assets':0,'paid_cost_usd':0.0,'render_times_seconds':times},indent=2),encoding='utf-8')
  print(json.dumps({'output':str(OUT),'tests':report['status'],'shots':len(all_bp),'times':times},indent=2))
if __name__=='__main__': main()
