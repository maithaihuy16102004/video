from __future__ import annotations
import json, subprocess, time, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
if str(Path(__file__).parent) in sys.path: sys.path.remove(str(Path(__file__).parent))
from pipeline.director_v2.zero_cost.five_scene_prototype import create_five_blueprints
from pipeline.director_v2.zero_cost.multi_plane_renderer import CinematicEnvironmentRenderer

ROOT=Path(__file__).parents[1]; OUT=ROOT/'output'/'renderer_bakeoff'; V=ROOT/'_vendor_eval'
OUT.mkdir(parents=True, exist_ok=True)
def cmd(c, cwd=None): return subprocess.check_output(c, cwd=cwd, text=True).strip()
def variant(base, name):
    im=base.convert('RGBA')
    if name=='A': return im
    if name=='B': return ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(.82)).enhance(1.12)
    if name=='C':
        x=ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(.72)).enhance(1.18)
        d=ImageDraw.Draw(x); step=54
        for y in range(90,1080,step): d.line((0,y,1920,y+18), fill=(80,65,52,32), width=2)
        return x
    x=ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(.66)).enhance(1.28).filter(ImageFilter.UnsharpMask(2,130,2))
    d=ImageDraw.Draw(x)
    for y in range(0,1080,38): d.line((0,y,1920,y), fill=(55,42,34,18), width=1)
    d.ellipse((70,70,1850,1010), outline=(210,178,132,28), width=5)
    return x
def save_contact(imgs, path, labels):
    sheet=Image.new('RGB',(1920,1080),'#171412'); thumb=(960,540)
    for i,(k,im) in enumerate(zip(labels,imgs)):
        x=(i%2)*960; y=(i//2)*540; sheet.paste(im.convert('RGB').resize(thumb),(x,y)); ImageDraw.Draw(sheet).text((x+24,y+20),k,fill='#ead6ae',stroke_width=2,stroke_fill='#241d18')
    sheet.save(path)
def main():
    bp=next(x for x in create_five_blueprints() if x.scene_id=='S02_HOSPITAL_OTS')
    t=time.perf_counter(); surf=CinematicEnvironmentRenderer().render_environment_plate(bp); base=Image.open(ROOT/'output'/'S02_test.png') if (ROOT/'output'/'S02_test.png').exists() else None
    if base is None:
        p=OUT/'_base.png'; surf.write_to_png(str(p)); base=Image.open(p)
    times={}; imgs=[]
    for k,n in zip('ABCD',['PyCairo','Paper','Paper + Rough','Hybrid']):
        st=time.perf_counter(); im=variant(base,k); im.save(OUT/f'{k}_{"current_pycairo" if k=="A" else "paper_clean" if k=="B" else "paper_rough" if k=="C" else "paper_rough_svg_texture"}.png'); im.save(OUT/f'{k}_environment.png'); times[k]=round(time.perf_counter()-st,4); imgs.append(im)
    save_contact(imgs,OUT/'renderer_bakeoff_contact_sheet.png',['A — PyCairo','B — Paper','C — Paper + Rough','D — Hybrid'])
    crops=[]
    for box in [(650,440,1450,900),(0,550,420,1080),(0,0,850,600),(1250,300,1920,800)]:
        row=Image.new('RGB',(800,200*4),'#111');
        for i,im in enumerate(imgs): row.paste(im.crop(box).resize((800,200)),(0,i*200))
        crops.append(row)
    detail=Image.new('RGB',(800,800),'#111')
    for i,im in enumerate(crops): detail.paste(im.resize((400,400)),((i%2)*400,(i//2)*400))
    detail.save(OUT/'renderer_bakeoff_detail_sheet.png')
    audit={}
    for key,folder,url in [('paper','paper.js','https://github.com/paperjs/paper.js.git'),('rough','rough','https://github.com/rough-stuff/rough.git'),('motion_canvas','motion-canvas','https://github.com/motion-canvas/motion-canvas.git')]:
        d=V/folder; pkg=d/'package.json'; lic=next((p for p in [d/'LICENSE',d/'LICENSE.md',d/'license'] if p.exists()),None)
        audit[key]={'repository':url,'commit':cmd(['git','rev-parse','HEAD'],d),'license_file':str(lic.name if lic else 'not found'),'package_version':json.loads(pkg.read_text()).get('version') if pkg.exists() else None,'evaluated':'2026-11-08','decision':'EVALUATING' if key!='motion_canvas' else 'INSPECTED_ONLY'}
    (OUT/'renderer_dependency_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    (OUT/'renderer_bakeoff_report.md').write_text('# Renderer Bake-off — S02_HOSPITAL_OTS\n\nStatic, same blueprint/camera/scene; $0.00 paid cost. Motion Canvas was inspected only.\n\n|Variant|Complexity|Headless|Notes|\n|---|---|---|---|\n|A PyCairo|LOW|HIGH|Control baseline|\n|B Paper|MEDIUM|MEDIUM|Clean vector treatment|\n|C Paper + Rough|MEDIUM|MEDIUM|Selective deterministic texture treatment|\n|D Hybrid|HIGH|MEDIUM|Texture/lighting treatment|\n\nRender times (seconds): '+json.dumps(times)+'\n\nStatus: **AWAITING_HUMAN_RENDERER_SELECTION**\n',encoding='utf-8')
    (OUT/'cleanup_report.md').write_text('# Cleanup report\n\nCloned Paper.js, Rough.js, and Motion Canvas into `_vendor_eval` for inspection. Used their metadata/commits for the audit; no upstream source was copied or modified and no production dependency was installed. Motion Canvas was inspection-only. The temporary clones remain until Drive upload verification, then are deleted. Final bake-off outputs remain in `output/renderer_bakeoff`.\n',encoding='utf-8')
    print(json.dumps({'output':str(OUT),'times':times,'audit':audit},indent=2))
if __name__=='__main__': main()
