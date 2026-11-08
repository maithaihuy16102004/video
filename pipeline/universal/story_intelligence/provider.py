from __future__ import annotations
from abc import ABC,abstractmethod
import json,time
from pathlib import Path

class ScriptIntelligenceProvider(ABC):
 @abstractmethod
 def analyze(self,script:str,context:dict)->tuple[dict,dict]:...

class GeminiScriptIntelligenceProvider(ScriptIntelligenceProvider):
 def __init__(self,reasoner,cache_dir:Path,model='gemini-3-flash-preview'):
  self.reasoner=reasoner;self.cache_dir=cache_dir;self.model=model;cache_dir.mkdir(parents=True,exist_ok=True)
 def analyze(self,script,context):
  t=time.time();prompt='Extract canonical characters, locations, dates, events, objects, relationships, actions and visual identity/location traits from this complete script. Resolve aliases/coreference. Return JSON only.\n'+script
  try:
   data=self.reasoner.complete_json('story_world_entities','You are universal script intelligence.',prompt,context)
   return data,{'stage':'story_world','model':self.model,'latency':round(time.time()-t,3),'success':True,'fallback':False,'429':False}
  except Exception as e:
   return {},{'stage':'story_world','model':self.model,'latency':round(time.time()-t,3),'success':False,'fallback':True,'429':'429' in str(e),'error':type(e).__name__}
