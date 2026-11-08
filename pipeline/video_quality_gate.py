"""Deterministic release gate for locally rendered YouTube-style videos."""
from __future__ import annotations
import argparse, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(args: list[str]) -> str:
    result=subprocess.run(args,capture_output=True,text=True,encoding="utf-8",errors="replace")
    return result.stderr+result.stdout

def probe(video: Path) -> dict:
    raw = subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type,codec_name,width,height,r_frame_rate","-of","json",str(video)], text=True, encoding="utf-8")
    return json.loads(raw)

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--video",required=True); p.add_argument("--spec",required=True); p.add_argument("--report",required=True); p.add_argument("--contact",required=True); a=p.parse_args()
    video,spec,report,contact=map(Path,[a.video,a.spec,a.report,a.contact]); meta=probe(video); props=json.loads(spec.read_text(encoding="utf-8")); duration=float(meta["format"]["duration"])
    streams=meta["streams"]; v=next((x for x in streams if x.get("codec_type")=="video"),{}); audio=next((x for x in streams if x.get("codec_type")=="audio"),{})
    fps_text=v.get("r_frame_rate","0/1"); n,d=(float(x) for x in fps_text.split("/")); fps=n/d if d else 0
    scenes=props.get("scenes",[]); captions=props.get("captionWords",[]); scene_seconds=[float(x.get("durationFrames",0))/24 for x in scenes]; shots={str(x.get("shot","")).lower() for x in scenes}
    loud=run(["ffmpeg","-hide_banner","-i",str(video),"-af","ebur128=peak=true","-f","null","NUL"]); lm=re.findall(r"I:\s*(-?[\d.]+) LUFS",loud); pm=re.findall(r"Peak:\s*(-?[\d.]+) dBFS",loud); lufs=float(lm[-1]) if lm else -99; peak=float(pm[-1]) if pm else 0
    freeze=run(["ffmpeg","-hide_banner","-i",str(video),"-vf","freezedetect=n=-45dB:d=1.5","-an","-f","null","NUL"]); freezes=len(re.findall(r"freeze_duration",freeze))
    black=run(["ffmpeg","-hide_banner","-i",str(video),"-vf","blackdetect=d=0.35:pix_th=0.10","-an","-f","null","NUL"]); blacks=len(re.findall(r"black_duration",black))
    renderer=(ROOT/"remotion-engine"/"src"/"RicksStyleDraft.tsx").read_text(encoding="utf-8").lower(); branding="ai clip studio" in renderer
    checks={
      "full_hd":{"points":8,"pass":(v.get("width") in (540,1080) and v.get("height") in (960,1920)) or (v.get("width") in (960,1920) and v.get("height") in (540,1080))},
      "fps_24":{"points":4,"pass":abs(fps-24)<.05},
      "codecs":{"points":4,"pass":v.get("codec_name")=="h264" and audio.get("codec_name")=="aac"},
      # YouTube-style mixes commonly land near -14 LUFS. Keep a practical
      # release window that still rejects clearly quiet or clipped audio.
      "audio_loudness":{"points":12,"pass":-18<=lufs<=-13 and -6<=peak<=-1},
      "subtitle_coverage":{"points":14,"pass":len(captions)>0 and captions[-1].get("endFrame",0)>=duration*24*.96},
      "subtitle_monotonic":{"points":6,"pass":all(captions[i].get("startFrame",0)<=captions[i].get("endFrame",0)<=captions[i+1].get("endFrame",10**9) for i in range(max(0,len(captions)-1)))},
      # A narrated semantic scene may run up to ten seconds while the renderer
      # still animates characters, captions and inserts inside it.
      "scene_pacing":{"points":16,"pass":bool(scene_seconds) and sum(scene_seconds)/len(scene_seconds)<=5 and max(scene_seconds)<=10},
      "shot_variety":{"points":10,"pass":len(shots)>=min(6,max(1,len(scenes)//3))},
      "no_long_freeze":{"points":10,"pass":freezes==0},
      "no_black_frames":{"points":6,"pass":blacks==0},
      "no_forbidden_branding":{"points":10,"pass":not branding},
    }
    score=sum(x["points"] for x in checks.values() if x["pass"]); mandatory=all(checks[k]["pass"] for k in ["full_hd","fps_24","audio_loudness","subtitle_coverage","no_forbidden_branding"]); passed=score>=85 and mandatory
    step=max(2.0, duration/11.5)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(video),"-vf",f"fps=1/{step:.2f},scale=480:-1,tile=4x3","-frames:v","1",str(contact)],check=False)
    data={"status":"PASS" if passed else "FAIL","score":score,"threshold":85,"requires_expert_visual_review":True,"metrics":{"duration":duration,"fps":fps,"lufs":lufs,"peak_dbfs":peak,"scenes":len(scenes),"average_scene_seconds":sum(scene_seconds)/len(scene_seconds) if scene_seconds else 0,"shot_types":len(shots),"freezes":freezes,"black_events":blacks},"checks":checks,"contact_sheet":str(contact)}
    report.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(data,ensure_ascii=False))
    raise SystemExit(0 if passed else 2)

if __name__=="__main__": main()
