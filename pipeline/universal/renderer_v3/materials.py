from __future__ import annotations

import random
from PIL import ImageDraw


MATERIALS = ("WOOD", "METAL", "PAPER", "GLASS", "FABRIC", "STONE", "MUD", "BRICK", "PLASTER")


class MaterialRendererV2:
    """Deterministic editorial material cues with camera-distance LOD."""

    def apply(self, d: ImageDraw.ImageDraw, box, material: str, seed: int = 1, lod: float = 1.0):
        x0, y0, x1, y1 = map(int, box); rng = random.Random(seed); m = material.upper()
        w, h = max(1, x1-x0), max(1, y1-y0); n = max(2, int(10*lod))
        if m == "WOOD":
            for i in range(n):
                y = y0 + (i+1)*h/(n+1) + rng.randint(-3,3)
                d.line((x0+4,y,x1-4,y+rng.randint(-2,2)), fill=(83,55,35,130), width=max(1,int(2*lod)))
            for x in (x0+5,x1-6): d.line((x,y0+3,x,y1-3), fill=(220,178,111,120), width=2)
        elif m == "METAL":
            d.line((x0+4,y0+4,x0+4,y1-4), fill=(220,228,224,180), width=max(2,int(4*lod)))
            for i in range(n//2):
                x=rng.randint(x0+6,x1-6); y=rng.randint(y0+6,y1-6)
                d.ellipse((x-2,y-2,x+2,y+2), fill=(96,67,42,160))
        elif m == "PAPER":
            for i in range(max(3,n//2)):
                y=y0+10+i*max(5,h//max(4,n//2)); d.line((x0+8,y,x1-9,y), fill=(76,66,56,100), width=1)
            d.line((x1-15,y0,x1,y0+15), fill=(120,105,84,150), width=2)
        elif m == "GLASS":
            d.line((x0+5,y1-8,x1-8,y0+5), fill=(245,252,255,200), width=max(2,int(4*lod)))
            d.line((x0+12,y1-5,x1-4,y0+12), fill=(138,190,211,120), width=2)
        elif m == "FABRIC":
            for i in range(n):
                x=x0+(i+1)*w/(n+1); d.arc((x-10,y0+5,x+10,y1-5),90,270,fill=(72,55,48,90),width=1)
        elif m in ("STONE","BRICK"):
            rows=max(2,int(5*lod)); bh=h/rows
            for r in range(rows):
                y=y0+r*bh; d.line((x0,y,x1,y),fill=(84,74,67,120),width=2)
                step=max(18,int(55/max(.4,lod))); off=(r%2)*step/2
                for x in range(int(x0-off),x1,step): d.line((x,y,x,y+bh),fill=(84,74,67,100),width=1)
        elif m == "PLASTER":
            for i in range(n):
                x=rng.randint(x0,x1); y=rng.randint(y0,y1)
                d.line((x,y,x+rng.randint(-12,12),y+rng.randint(5,18)),fill=(113,98,80,75),width=1)
        elif m == "MUD":
            for i in range(n*2):
                x=rng.randint(x0,x1); y=rng.randint(y0,y1); rx=rng.randint(3,15)
                d.ellipse((x-rx,y-2,x+rx,y+3),fill=(164,143,92,rng.randint(35,100)))
