from __future__ import annotations
import hashlib,re,json
from pathlib import Path
from .schemas import *

ACTION_MAP={'reads':'READ','read':'READ','đọc':'READ','walks':'WALK','walk':'WALK','đi':'WALK','runs':'RUN','run':'RUN','chạy':'RUN','sits':'SIT','sit':'SIT','ngồi':'SIT','leans':'LEAN','lean':'LEAN','cúi':'LEAN','reaches':'REACH','reach':'REACH','vươn':'REACH','pulls':'PULL','pull':'PULL','kéo':'PULL','opens':'REACH','open':'REACH','mở':'REACH','argues':'ARGUE','argue':'ARGUE','tranh luận':'ARGUE','inspects':'CROUCH','inspect':'CROUCH','kiểm tra':'CROUCH'}

def _lines(script):return [x.strip() for x in script.splitlines() if x.strip()]
def _canonical_entities(script):
    meta_stop = {
        'TẬP', 'CẢNH', 'PHẦN', 'SCENE', 'CHƯƠNG', 'HỒI', 'THỜI GIAN', 'ĐỊA ĐIỂM',
        'BỐI CẢNH', 'CHÍNH TRỊ', 'TITLE', 'LƯU Ý', 'GHI CHÚ', 'EPISODE', 'PROLOGUE', 'ACT'
    }
    # Exclude title lines and metadata headers from entity scanning
    body_lines = []
    for l in script.splitlines():
        cl = re.sub(r'[*#_`]', '', l).strip()
        if re.match(r'^(TẬP|CẢNH|PHẦN|SCENE|CHƯƠNG|HỒI|EPISODE)\s*\d+', cl, re.I):
            continue
        body_lines.append(cl)
    body_text = '\n'.join(body_lines)

    names = []
    # 1. Explicit dialogue lines: Name: text
    for line in body_lines:
        m = re.match(r'^([A-ZÀ-ỸĐa-zà-ỹ0-9 _-]{2,30}):\s*(.+)', line)
        if m:
            prefix = m.group(1).strip()
            first_tok = prefix.upper().split()[0]
            if first_tok not in meta_stop:
                cname = prefix.title()
                if 'Hitler' in cname: cname = 'Adolf Hitler'
                if cname not in names:
                    names.append(cname)

    # 2. Lead character for first person roleplay
    if 'tôi' in body_text.lower() or 'hitler' in body_text.lower():
        if 'Adolf Hitler' not in names:
            names.insert(0, 'Adolf Hitler')

    # 3. Known historical supporting figures (only if explicitly in body text)
    known_supporting = [
        r'\bAnton Drexler\b', r'\bDietrich Eckart\b', r'\bKarl Harrer\b',
        r'\bGottfried Feder\b', r'\bErnst Röhm\b', r'\bFranz von Epp\b',
        r'\bLudwig III\b'
    ]
    for kp in known_supporting:
        m = re.search(kp, body_text, re.I)
        if m:
            matched = m.group(0).title()
            if matched not in names:
                names.append(matched)

    if not names:
        names = ['Adolf Hitler']
    return names[:8]
def _locations(script):
 loc=[]
 for raw in _lines(script):
  m=re.search(r'\[(?:SCENE|CẢNH)?\s*[-—:]?\s*([^\]]+)\]',raw,re.I)
  if m:loc.append(m.group(1).strip())
  for p in re.findall(r'\b(?:in|at|inside|near|tại|trong|ở)\s+(?:the\s+)?([A-ZĐa-zà-ỹ][\wÀ-ỹ -]{2,35})',raw):loc.append(p.strip(' .,'))
 out=[]
 for x in loc:
  if x and x not in out:out.append(x)
 return out[:15] or ['Primary Setting']
def _loc_traits(name):
 low=name.lower();
 if any(k in low for k in ('lab','workshop','engine','xưởng','phòng máy')):return ('WORKSHOP','industrial structural bays',['METAL','BRICK'],['MACHINE','TOOL','WIRE','CRATE'],['large working machine'],['WINDOW','LAMP'])
 if any(k in low for k in ('mountain','pass','ridge','núi','đèo','forest')):return ('EXTERIOR','terrain corridor',['STONE','MUD'],['ROCK','VEGETATION','POST'],['terrain gateway'],['SUN','MOON'])
 if any(k in low for k in ('hospital','clinic','bedroom','ward','bệnh viện','phòng ngủ')):return ('INTIMATE_INTERIOR','quiet vertical enclosure',['PLASTER','FABRIC','WOOD'],['BED','CUP','LAMP','CLOTH'],['tall window beside bed'],['WINDOW','LAMP'])
 if any(k in low for k in ('senate','council','hall','assembly','hội trường')):return ('INSTITUTIONAL','tiered public chamber',['STONE','WOOD'],['CHAIR','TABLE','BOOK','PAPER'],['rows of benches'],['WINDOW','LAMP'])
 return ('INTERIOR','specific occupied enclosure',['WOOD','PLASTER'],['TABLE','CHAIR','PAPER','BOOK','LAMP'],['dominant opening or furniture axis'],['WINDOW','LAMP'])
def build_story_world_model(script_text:str,provider=None,project_context=None)->StoryWorldModel:
 h=hashlib.sha256(script_text.encode()).hexdigest();provider_data={};audit=[]
 if provider:
  provider_data,entry=provider.analyze(script_text,project_context or {});audit.append(entry)
 names=_canonical_entities(script_text);locs=_locations(script_text);chars={}
 years=sorted(set(re.findall(r'\b(?:17|18|19|20)\d{2}\b',script_text))) or ['UNSPECIFIED']
 for i,n in enumerate(names,1):
  cid=f'CHARACTER_{i:03d}';aliases=[n.split()[0]] if len(n.split())>1 else []
  anchors=['distinct head silhouette','context-derived hair shape','recognizable costume silhouette','consistent posture']
  variants=[{'time':y,'age_band':'context-derived','changes':['age','costume','role'] if j else ['baseline identity']} for j,y in enumerate(years)]
  chars[cid]=CharacterEntity(character_id=cid,canonical_name=n,aliases=aliases,story_role='LEAD' if i==1 else 'SUPPORTING',importance='PRIMARY' if i==1 else 'SUPPORTING',identity_anchors=anchors,appearance_confidence=.55,age_timeline=variants,appearance_timeline=variants,costume_timeline=[{'time':y,'description':'occupation/date/location appropriate attire'} for y in years],hair_timeline=[{'time':y,'description':'identity-preserving contextual hair'} for y in years],performance_profile={'baseline':'script-derived','gesture':'semantic action'},continuity_rules=['preserve identity anchors across time','costume changes require context'],uncertainties=['exact appearance requires Gemini/context/reference'],provenance={'identity_anchors':Provenance(source='PLAUSIBLE_RECONSTRUCTION',confidence=.55,evidence='script role and visual simplification')},ideal_character_design={'description':'script/context interpreted illustrated identity'},executable_character_dna={'hair_shape':'CONTEXTUAL','head_shape':'OVAL','body_proportion':'ROLE_BASED','costume_family':'CONTEXTUAL'})
 locations={}
 for i,n in enumerate(locs,1):
  typ,arch,mats,props,land,lights=_loc_traits(n);lid=f'LOCATION_{i:03d}';locations[lid]=LocationEntity(location_id=lid,canonical_name=n,aliases=['the room'] if typ.endswith('INTERIOR') else [],location_type=typ,time_periods=years,architecture=arch,materials=mats,layout_intent='supports event, movement and landmark',landmarks=land,prop_ecology=props,human_traces=['moved object','evidence of recent use'],lighting_sources=lights,continuity_rules=['architecture and landmark persist between shots'],executable_location_dna={'enclosure':typ,'architecture':arch,'materials':mats,'prop_ecology':props,'landmark':land[0]})
 objects={}; obj_words=re.findall(r'\b(letter|document|machine|chair|door|table|book|lamp|bed|tool|cup|weapon|vehicle|thư|tài liệu|máy|ghế|cửa|bàn|sách|đèn|giường|dụng cụ)\b',script_text,re.I)
 for i,n in enumerate(dict.fromkeys(x.lower() for x in obj_words),1):objects[f'OBJECT_{i:03d}']=ObjectEntity(object_id=f'OBJECT_{i:03d}',name=n,importance='INTERACTION',states=[{'event':0,'state':'INITIAL'}])
 actions=[];sentences=re.split(r'(?<=[.!?])\s+|\n+',script_text);cids=list(chars);oids=list(objects)
 for i,s in enumerate(sentences):
  low=s.lower();pr=[]
  for k,v in ACTION_MAP.items():
   if re.search(r'\b'+re.escape(k)+r'\b',low) and v not in pr:pr.append(v)
  if pr:actions.append(ActionIntent(action_id=f'ACTION_{len(actions)+1:03d}',actor_id=cids[min(i,len(cids)-1)],primitives=pr[:3],object_id=oids[0] if oids else None,emotion='TENSE' if any(k in low for k in ('nervous','angry','sợ','giận')) else 'FOCUSED',eyeline=oids[0] if oids else None,hand_interaction='HOLD' if 'READ' in pr else 'GRIP' if any(x in pr for x in ('REACH','PULL')) else None,source_text=s[:240]))
 scenes=[];events=[];chunks=[x for x in re.split(r'\n\s*\n|(?=\[(?:SCENE|CẢNH))',script_text) if x.strip()]
 for i,ch in enumerate(chunks or [script_text],1):
  sid=f'SCENE_{i:03d}';lid=list(locations)[min(i-1,len(locations)-1)];eids=[]
  for a in [x for x in actions if x.source_text in ch] or actions[:1]:
   eid=f'EVENT_{len(events)+1:03d}';events.append(EventEntity(event_id=eid,scene_id=sid,participants=[a.actor_id],location_id=lid,time_label=years[min(i-1,len(years)-1)],actions=a.primitives,objects=[a.object_id] if a.object_id else [],effect='world/character state advances',information_change='viewer gains event information'));eids.append(eid)
  scenes.append(SceneInstance(scene_id=sid,location_id=lid,character_ids=cids,object_ids=oids,event_ids=eids,script_excerpt=ch[:500]))
 relationships=[{'source':cids[0],'target':x,'type':'UNKNOWN','confidence':.4} for x in cids[1:]]
 status='GEMINI_SUCCESS' if audit and audit[0].get('success') else 'DETERMINISTIC_FALLBACK'
 return StoryWorldModel(script_hash=h,title=next((x for x in _lines(script_text) if len(x)<100),'Untitled Script'),status=status,characters=chars,locations=locations,objects=objects,actions=actions,events=events,relationships=relationships,timeline=[{'time':y,'characters':cids} for y in years],scenes=scenes,continuity_state={'single_source_of_truth':True},provider_audit=audit)
def process_script_to_world(script_text,output_dir,provider=None):
 m=build_story_world_model(script_text,provider);p=Path(output_dir);p.mkdir(parents=True,exist_ok=True);(p/'story_world_model.json').write_text(m.model_dump_json(indent=2),encoding='utf-8');return m
