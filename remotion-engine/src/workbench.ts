import {RicksStyleDraft, SHOTS, SFX, TOTAL} from "./RicksStyleDraft";

export const WORKBENCH={
  name:"Ricks-style Vietnamese edutainment draft",
  fps:30,width:1080,height:1920,total:TOTAL,background:"#F6F0E4",
  shots:SHOTS.map((s)=>({...s,component:RicksStyleDraft})),
  transitions:[],captions:[],overlays:[],
  sfx:SFX.map((s)=>({...s,duration:80})),
  bgm:[{from:0,duration:TOTAL,src:"ricks-draft/audio/bgm.mp3",volume:.09}],
  original:RicksStyleDraft,
};
