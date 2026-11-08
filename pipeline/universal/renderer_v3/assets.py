from __future__ import annotations

from PIL import ImageDraw
from .materials import MaterialRendererV2


ASSET_FAMILIES = ("TABLE","CHAIR","DOOR","WINDOW","PAPER","BOOK","LAMP","BED","SHELF","CRATE","BARREL","WIRE","POST","MACHINE","TOOL","CUP","BOTTLE","CLOTH","ROCK","RUBBLE","VEGETATION")


class AssetRendererV3:
    def __init__(self): self.materials=MaterialRendererV2()

    def draw(self,d:ImageDraw.ImageDraw,family:str,x:int,y:int,s:float=1,view:str="THREE_QUARTER",variant:int=0,hero=False,seed=1):
        f=family.upper(); ink=(35,31,29,255); strong=max(2,int(4*s)); sh=(28,22,20,70)
        def box(a,b,c,e,fill,mat=None):
            q=(int(x+a*s),int(y+b*s),int(x+c*s),int(y+e*s)); d.rounded_rectangle(q,radius=max(2,int(3*s)),fill=fill,outline=ink,width=strong)
            if mat:self.materials.apply(d,q,mat,seed+variant,lod=min(1.5,s))
            return q
        d.ellipse((x-60*s,y+38*s,x+65*s,y+58*s),fill=sh)
        if f=="TABLE":
            box(-70,-45,70,-22,(111,74,45,255),"WOOD"); box(-57,-20,-45,50,(75,49,32,255),"WOOD"); box(42,-20,55,50,(75,49,32,255),"WOOD")
        elif f=="CHAIR":
            box(-30,-15,30,3,(116,78,48,255),"WOOD"); d.line((x-25*s,y,x-28*s,y+55*s),fill=ink,width=strong);d.line((x+25*s,y,x+28*s,y+55*s),fill=ink,width=strong);box(-27,-85,27,-70,(112,75,45,255),"WOOD");d.line((x-24*s,y-70*s,x-24*s,y),fill=ink,width=strong);d.line((x+24*s,y-70*s,x+24*s,y),fill=ink,width=strong)
        elif f in ("DOOR","WINDOW"):
            mat="WOOD" if f=="DOOR" else "GLASS"; box(-45,-120,45,48,(85,62,42,255) if f=="DOOR" else (107,157,177,170),mat)
            if f=="WINDOW": d.line((x,y-115*s,x,y+43*s),fill=ink,width=strong);d.line((x-42*s,y-35*s,x+42*s,y-35*s),fill=ink,width=strong)
            else:d.ellipse((x+25*s,y-38*s,x+32*s,y-31*s),fill=(202,164,78,255))
        elif f in ("PAPER","BOOK"):
            box(-38,-42,38,25,(226,214,181,255) if f=="PAPER" else (102,54,45,255),"PAPER" if f=="PAPER" else "FABRIC")
        elif f=="LAMP":
            d.line((x,y-75*s,x,y+35*s),fill=ink,width=strong); d.polygon([(x-32*s,y-65*s),(x+32*s,y-65*s),(x+20*s,y-20*s),(x-20*s,y-20*s)],fill=(232,177,79,230),outline=ink)
        elif f=="BED":
            box(-95,-15,95,35,(199,195,177,255),"FABRIC");d.line((x-95*s,y-55*s,x-95*s,y+50*s),fill=ink,width=strong);d.line((x+95*s,y-55*s,x+95*s,y+50*s),fill=ink,width=strong)
        elif f=="SHELF":
            box(-70,-120,70,45,(93,62,39,255),"WOOD");
            for yy in (-80,-35,10):d.line((x-64*s,y+yy*s,x+64*s,y+yy*s),fill=ink,width=strong)
        elif f in ("CRATE","BARREL"):
            if f=="CRATE":box(-48,-50,48,42,(123,89,54,255),"WOOD");d.line((x-45*s,y-47*s,x+45*s,y+39*s),fill=ink,width=strong)
            else:d.ellipse((x-38*s,y-65*s,x+38*s,y+48*s),fill=(111,73,41,255),outline=ink,width=strong);d.line((x-35*s,y-25*s,x+35*s,y-25*s),fill=ink,width=strong);d.line((x-37*s,y+20*s,x+37*s,y+20*s),fill=ink,width=strong)
        elif f in ("WIRE","POST"):
            if f=="POST":box(-12,-120,12,48,(87,62,42,255),"WOOD")
            else:d.arc((x-70*s,y-55*s,x+70*s,y+50*s),10,330,fill=ink,width=strong)
        elif f=="MACHINE":
            box(-62,-95,62,45,(75,83,87,255),"METAL");d.ellipse((x-30*s,y-72*s,x+30*s,y-12*s),fill=(221,208,171,255),outline=ink,width=strong);d.line((x,y-42*s,x+18*s,y-60*s),fill=(180,50,42,255),width=strong)
        elif f=="TOOL": d.line((x-48*s,y+35*s,x+35*s,y-55*s),fill=(92,59,36,255),width=max(5,strong));d.rectangle((x+18*s,y-70*s,x+52*s,y-45*s),fill=(76,81,82,255),outline=ink,width=strong)
        elif f in ("CUP","BOTTLE"):
            if f=="CUP":box(-25,-40,25,30,(180,164,133,255),"STONE");d.arc((x+15*s,y-30*s,x+48*s,y+18*s),270,90,fill=ink,width=strong)
            else:box(-20,-65,20,35,(75,117,101,200),"GLASS");box(-9,-88,9,-63,(75,117,101,200),"GLASS")
        elif f=="CLOTH": d.polygon([(x-65*s,y-55*s),(x+60*s,y-42*s),(x+48*s,y+45*s),(x-55*s,y+35*s)],fill=(142,94,75,255),outline=ink);self.materials.apply(d,(x-60*s,y-50*s,x+55*s,y+40*s),"FABRIC",seed,s)
        elif f in ("ROCK","RUBBLE"):
            pts=[(x-60*s,y+25*s),(x-35*s,y-42*s),(x+12*s,y-55*s),(x+62*s,y+30*s)];d.polygon(pts,fill=(111,105,94,255),outline=ink)
            if f=="RUBBLE":d.polygon([(x-75*s,y+35*s),(x-55*s,y),(x-25*s,y+38*s)],fill=(92,87,80,255),outline=ink)
        elif f=="VEGETATION":
            d.line((x,y+42*s,x,y-55*s),fill=(54,76,45,255),width=strong)
            for dx,dy in [(-35,-25),(30,-15),(-28,2),(35,12)]:d.ellipse((x+(dx-18)*s,y+(dy-10)*s,x+(dx+18)*s,y+(dy+10)*s),fill=(77,106,60,255),outline=ink,width=max(1,strong//2))
