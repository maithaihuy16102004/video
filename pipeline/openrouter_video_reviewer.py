"""Vision fallback reviewer for three local video drafts. Reads the API key from env only."""
from __future__ import annotations
import argparse, base64, json, os, re, urllib.request
from pathlib import Path

RUBRIC="""Score each draft out of 100: hook first 3 seconds 15; pacing/pattern interrupts 15; character acting 15; visuals support narration 10; humor/payoff 10; story clarity 10; subtitles 10; novelty 5; voice/sound 5; likely retention 5. Hard fail unintended branding, unreadable/cut subtitles, repetitive slideshow feel, or misleading science. Choose potential, never claim guaranteed virality."""

def data_url(path:Path)->str:
    return "data:image/png;base64,"+base64.b64encode(path.read_bytes()).decode("ascii")

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--out",required=True);a=p.parse_args();job=Path(a.job);key=os.getenv("OPENROUTER_API_KEY","").strip()
    if not key: raise SystemExit("OPENROUTER_API_KEY is not configured")
    contacts=sorted(job.glob("draft-*-contact.png"))
    if len(contacts)!=3: raise SystemExit("Expected three draft contact sheets")
    content=[{"type":"text","text":f"You are a strict YouTube animation editor. Compare the three contact sheets in order Draft 1..3. {RUBRIC} Return ONLY JSON: {{\"approved\":boolean,\"winner\":0-2,\"winner_score\":number,\"ranking\":[0-2],\"scores\":[number,number,number],\"reasons\":[string,string,string],\"required_fixes\":[string]}}. approved may be true only when winner_score >=85 and no hard fail."}]
    content += [{"type":"image_url","image_url":{"url":data_url(path)}} for path in contacts]
    body=json.dumps({"model":os.getenv("OPENROUTER_REVIEW_MODEL","openai/gpt-4o"),"temperature":0.1,"messages":[{"role":"user","content":content}]}).encode()
    req=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",data=body,method="POST",headers={"Authorization":f"Bearer {key}","HTTP-Referer":"http://127.0.0.1:4173","X-Title":"Local Video QA","Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as response: result=json.loads(response.read().decode("utf-8"))
    text=result["choices"][0]["message"]["content"];match=re.search(r"\{.*\}",text,re.S)
    if not match: raise RuntimeError("Reviewer did not return JSON")
    review=json.loads(match.group(0));review["provider"]="openrouter";review["model"]=os.getenv("OPENROUTER_REVIEW_MODEL","openai/gpt-4o")
    Path(a.out).write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps({"approved":review.get("approved"),"winner":review.get("winner"),"winner_score":review.get("winner_score")}))

if __name__=="__main__":main()
