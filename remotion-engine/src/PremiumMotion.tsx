import React from "react";
import {
  AbsoluteFill,
  CalculateMetadataFunction,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
// The previous Latin-only Space Grotesk subset caused Vietnamese diacritics to
// fall back glyph-by-glyph to a serif font. Arial is available in the local
// Windows render environment and contains the full Vietnamese character set.
const fontFamily = "Arial, sans-serif";

export type VisualLanguage =
  | "data_stream" | "neural_network" | "automation"
  | "ethics_balance" | "orbital_future" | "data_chart" | "black_hole";

export interface PremiumScene {
  badge: string;
  headline: string;
  subtext: string;
  spoken: string;
  duration: number;
  accent: string;
  visualLanguage: VisualLanguage;
  visualBeats?: Array<{role: "establish" | "evidence" | "resolve"; prompt: string; duration: number}>;
  motionArc?: string[];
  cameraPattern?: string[];
  holdSeconds?: number;
}

export interface PremiumMotionProps {
  [key: string]: unknown;
  scenes: PremiumScene[];
  artDirection?: "neo-editorial" | "paper-tech" | "glass-future" | "signal-noir";
}

const DIRECTIONS = {
  "neo-editorial": {bg: "#F3EFE7", ink: "#11131A", surface: "#FFFDF8", grid: "rgba(17,19,26,.08)"},
  "paper-tech": {bg: "#E7E0D2", ink: "#171513", surface: "#F9F4EA", grid: "rgba(23,21,19,.10)"},
  "glass-future": {bg: "#07101D", ink: "#F4F8FF", surface: "rgba(16,30,50,.76)", grid: "rgba(180,220,255,.08)"},
  "signal-noir": {bg: "#050506", ink: "#F5F1E8", surface: "#111113", grid: "rgba(255,255,255,.06)"},
} as const;

const ease = (v: number) => v * v * (3 - 2 * v);
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const phase = (p: number, from: number, to: number) => ease(clamp01((p - from) / (to - from)));

const Neural: React.FC<{accent: string; progress: number}> = ({accent, progress}) => {
  const layers = [4, 7, 7, 4];
  const nodes = layers.flatMap((count, layer) =>
    Array.from({length: count}, (_, i) => ({layer, x: 105 + layer * 250, y: 150 + ((i + 1) * 700) / (count + 1)})),
  );
  return <svg viewBox="0 0 960 1000" style={{width: "100%", height: "100%", overflow: "visible"}}>
    {nodes.flatMap((a, ai) => nodes.filter((b) => b.layer === a.layer + 1).map((b, bi) => {
      if ((ai * 3 + bi) % 4 !== 0) return null;
      const connection = phase(progress, .18 + ((ai + bi) % 5) * .035, .48 + ((ai + bi) % 5) * .035);
      return <line key={`${ai}-${bi}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={accent} strokeWidth={2 + connection * 2} opacity={(0.08 + connection * .55) * phase(progress, 0, .22)}/>;
    }))}
    {nodes.map((n, i) => {
      const appear = interpolate(progress, [i / nodes.length, Math.min(1, i / nodes.length + .2)], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
      const thought = phase(progress, .34 + (i % 7) * .025, .58 + (i % 7) * .025);
      const r = 9 + thought * 5;
      return <g key={i} opacity={appear}><circle cx={n.x} cy={n.y} r={r * 2.4} fill={accent} opacity=".10"/><circle cx={n.x} cy={n.y} r={r} fill={accent}/><circle cx={n.x} cy={n.y} r="4" fill="white"/></g>;
    })}
  </svg>;
};

const Automation: React.FC<{accent: string; progress: number}> = ({accent, progress}) => {
  const reach = phase(progress, .12, .48);
  const place = phase(progress, .48, .76);
  const elbowX = 390 + reach * 115 - place * 35;
  const handY = 505 + reach * 150 - place * 55;
  return <svg viewBox="0 0 960 1000" style={{width: "100%", height: "100%"}}>
    <defs><filter id="glow"><feGaussianBlur stdDeviation="10" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
    <g transform={`translate(${(1-progress)*-180} 0)`} opacity={progress}>
      <rect x="30" y="750" width="900" height="110" rx="55" fill="#101B2A" stroke={accent} strokeWidth="5"/>
      {Array.from({length: 6},(_,i) => {const arrive=phase(progress,.08+i*.055,.30+i*.055);return <g key={i} transform={`translate(${55+i*150} ${(1-arrive)*95})`} opacity={arrive}><rect x="0" y="650" width="125" height="100" rx="16" fill={accent} opacity=".75"/><path d="M18 680h89M18 710h54" stroke="white" strokeWidth="8" opacity=".7"/></g>})}
      <path d={`M180 620 L${elbowX} 380 L690 ${handY}`} fill="none" stroke="white" strokeWidth="58" strokeLinecap="round" strokeLinejoin="round"/>
      <path d={`M180 620 L${elbowX} 380`} fill="none" stroke={accent} strokeWidth="28" strokeLinecap="round"/>
      {[[180,620],[elbowX,380],[690,handY]].map((p,i)=><circle key={i} cx={p[0]} cy={p[1]} r="48" fill="#07101D" stroke={accent} strokeWidth="10" filter="url(#glow)"/>)}
    </g>
  </svg>;
};

const Ethics: React.FC<{accent: string; progress: number}> = ({accent, progress}) => {
  const challenge = phase(progress, .12, .42);
  const alignment = phase(progress, .48, .82);
  const tilt = challenge * 11 - alignment * 11;
  return <svg viewBox="0 0 960 1000" style={{width:"100%",height:"100%"}}>
    <g transform={`rotate(${tilt} 480 400) scale(${.75+.25*progress})`} style={{transformOrigin:"480px 400px"}}>
      <circle cx="480" cy="420" r="290" fill="none" stroke={accent} strokeWidth="4" opacity=".3"/>
      <circle cx="480" cy="420" r="220" fill="none" stroke={accent} strokeWidth="2" opacity=".16"/>
      <path d="M480 250V780M160 390H800" stroke="currentColor" strokeWidth="20" strokeLinecap="round"/>
      <path d="M180 390L90 650H270ZM780 390L690 650H870Z" fill="none" stroke={accent} strokeWidth="12"/>
      <text x="180" y="700" textAnchor="middle" fontSize="42" fontWeight="700" fill="currentColor">HUMAN</text>
      <text x="780" y="700" textAnchor="middle" fontSize="42" fontWeight="700" fill="currentColor">AGI</text>
    </g>
  </svg>;
};

const Orbital: React.FC<{accent:string;progress:number}> = ({accent,progress}) => {
  const orbit=phase(progress,.08,.58); const launch=phase(progress,.48,.82); const a=-1.6+orbit*3.7;
  return <svg viewBox="0 0 960 1000" style={{width:"100%",height:"100%"}}>
    <defs><radialGradient id="planet"><stop offset="0" stopColor="white"/><stop offset=".22" stopColor={accent}/><stop offset="1" stopColor="#08121F"/></radialGradient></defs>
    <g opacity={progress} transform={`scale(${.85+.15*progress})`} style={{transformOrigin:"480px 500px"}}>
      <circle cx="480" cy="510" r="210" fill="url(#planet)"/>
      {[0,1,2].map(i=><ellipse key={i} cx="480" cy="510" rx={300+i*75} ry={110+i*42} fill="none" stroke="currentColor" opacity={.12+i*.08} strokeWidth="4"/>)}
      <circle cx={480+Math.cos(a)*370} cy={510+Math.sin(a)*145} r="25" fill="white"/>
      <g transform={`translate(${650+launch*170} ${250-launch*240}) rotate(${12+launch*24})`}><path d="M0-100L-45 40L0 15L45 40Z" fill="white"/><path d="M-18 32L0 ${55+launch*75}L18 32Z" fill={accent} opacity={.45+launch*.55}/></g>
    </g>
  </svg>;
};

const DataStream: React.FC<{accent:string;progress:number}> = ({accent,progress}) => {
  const gather=phase(progress,.08,.58); const resolve=phase(progress,.58,.84);
  return <svg viewBox="0 0 960 1000" style={{width:"100%",height:"100%"}}>{Array.from({length:22},(_,i)=>{
    const startX=-180+(i%4)*90; const targetX=210+(i%6)*105; const y=80+i*40; const x=startX+(targetX-startX)*gather; const w=(80+(i*47)%280)*(1-resolve*.55);
    return <g key={i} opacity={phase(progress, i*.012, .22+i*.012)*(.24+(i%5)*.13)}><line x1={x-w} y1={y} x2={x} y2={y} stroke={accent} strokeWidth={5+(i%3)*2}/><circle cx={x} cy={y} r={5+(i%4)+resolve*3} fill={accent}/></g>;
  })}</svg>;
};

const Visual: React.FC<{scene:PremiumScene;progress:number}> = ({scene,progress}) => {
  if(scene.visualLanguage==="neural_network") return <Neural accent={scene.accent} progress={progress}/>;
  if(scene.visualLanguage==="automation") return <Automation accent={scene.accent} progress={progress}/>;
  if(scene.visualLanguage==="ethics_balance") return <Ethics accent={scene.accent} progress={progress}/>;
  if(scene.visualLanguage==="orbital_future") return <Orbital accent={scene.accent} progress={progress}/>;
  return <DataStream accent={scene.accent} progress={progress}/>;
};

const WordCaptions: React.FC<{text:string; accent:string; durationFrames:number}> = ({text,accent,durationFrames}) => {
  const frame=useCurrentFrame(); const words=text.split(/\s+/); const active=Math.min(words.length-1,Math.floor(frame/durationFrames*words.length));
  const start=Math.max(0,active-2); const page=words.slice(start,start+4);
  return <div style={{position:"absolute",left:70,right:70,bottom:260,display:"flex",justifyContent:"center",gap:10,flexWrap:"wrap",fontSize:76,fontWeight:700,textTransform:"uppercase",letterSpacing:"-.025em"}}>
    {page.map((w,i)=>{const idx=start+i;return <span key={`${idx}-${w}`} style={{color:idx===active?"#061019":"white",background:idx===active?accent:"rgba(0,0,0,.72)",padding:"8px 14px",borderRadius:10,boxShadow:idx===active?`0 0 34px ${accent}66`:"none"}}>{w}</span>})}
  </div>;
};

const PremiumSceneView: React.FC<{scene:PremiumScene; index:number; total:number; direction:keyof typeof DIRECTIONS}> = ({scene,index,total,direction}) => {
  const frame=useCurrentFrame(); const {fps}=useVideoConfig(); const durationFrames=Math.round(scene.duration*fps); const theme=DIRECTIONS[direction];
  const outro=interpolate(frame,[durationFrames-14,durationFrames],[1,0],{extrapolateLeft:"clamp",extrapolateRight:"clamp"});
  const timeline=clamp01(frame/Math.max(1,durationFrames-1));
  const holdRatio=clamp01((scene.holdSeconds ?? .6)/Math.max(scene.duration,1));
  const fadeRatio=14/Math.max(durationFrames,1);
  const motionEnd=Math.max(.7,1-holdRatio-fadeRatio);
  const visualProgress=clamp01((timeline+.08)/motionEnd);
  const cameraModes=scene.cameraPattern?.length === 3 ? scene.cameraPattern : ["wide","detail","wide"];
  const detailStrength=cameraModes[1] === "detail" ? 1 : .55;
  const detailPush=phase(timeline,.18,.44)*(1-phase(timeline,.58,motionEnd))*detailStrength;
  const camera=1.025+detailPush*.055-phase(timeline,.66,motionEnd)*.025;
  const intro=phase(timeline,0,.06);
  const beatLabels=(scene.visualBeats?.length === 3 ? scene.visualBeats.map((beat)=>beat.role) : ["establish","evidence","resolve"])
    .map((role)=>role === "establish" ? "THIẾT LẬP" : role === "evidence" ? "BẰNG CHỨNG" : "KẾT LUẬN");
  const beats=scene.visualBeats?.length === 3 ? scene.visualBeats : [];
  const beatWeights=beats.length === 3 ? beats.map((beat)=>Math.max(.1,beat.duration)) : [1,1,1];
  const beatTotal=beatWeights.reduce((sum,value)=>sum+value,0);
  const beatCut1=beatWeights[0]/beatTotal;
  const beatCut2=(beatWeights[0]+beatWeights[1])/beatTotal;
  const activeBeat=timeline<beatCut1?0:timeline<beatCut2?1:2;
  const semanticEvidence=beats[activeBeat]?.prompt.split(";")[1]?.trim() || (activeBeat===0?scene.headline.replace(/\n/g," "):scene.subtext);
  const evidenceText=semanticEvidence.length>92?`${semanticEvidence.slice(0,89).trim()}…`:semanticEvidence;
  const headlineLines=scene.headline.split("\n");
  return <AbsoluteFill style={{background:theme.bg,color:theme.ink,fontFamily,overflow:"hidden",opacity:outro}}>
    <AbsoluteFill style={{backgroundImage:`linear-gradient(${theme.grid} 1px,transparent 1px),linear-gradient(90deg,${theme.grid} 1px,transparent 1px)`,backgroundSize:"64px 64px",transform:`scale(${camera})`}}/>
    <div style={{position:"absolute",width:700,height:700,borderRadius:"50%",right:-260,top:-250,background:scene.accent,filter:"blur(120px)",opacity:.18}}/>
    <div style={{position:"absolute",left:54,top:58,fontSize:25,fontWeight:700,letterSpacing:".12em",color:scene.accent}}>{String(index+1).padStart(2,"0")} / {String(total).padStart(2,"0")}</div>
    <div style={{position:"absolute",left:54,right:54,top:112,transform:`translateY(${(1-intro)*-70}px)`,opacity:intro}}>
      <div style={{fontSize:25,fontWeight:700,letterSpacing:".11em",color:scene.accent,marginBottom:20}}>{scene.badge}</div>
      {headlineLines.map((line,i)=><div key={line} style={{fontSize:76,lineHeight:.98,fontWeight:700,letterSpacing:"-.055em",transform:`translateX(${(1-intro)*(i%2?70:-70)}px)`,opacity:interpolate(intro,[i*.12,1],[0,1],{extrapolateLeft:"clamp",extrapolateRight:"clamp"})}}>{line}</div>)}
      <div style={{height:5,width:`${phase(timeline,.02,.2)*100}%`,background:scene.accent,marginTop:28,boxShadow:`0 0 24px ${scene.accent}`}}/>
    </div>
    <div style={{position:"absolute",left:42,right:42,top:500,bottom:420,color:theme.ink,transform:`translateY(${(1-intro)*120}px) scale(${camera})`,transformOrigin:"50% 55%",opacity:.28+.72*intro}}><Visual scene={scene} progress={visualProgress}/></div>
    <div style={{position:"absolute",right:54,bottom:470,width:600,textAlign:"right",fontSize:32,lineHeight:1.25,opacity:.78,transform:`translateY(${(1-intro)*18}px)`}}><span style={{color:scene.accent,fontWeight:700,letterSpacing:".08em",fontSize:22}}>{beatLabels[activeBeat]} · </span>{evidenceText}</div>
    <div style={{position:"absolute",left:54,top:445,display:"flex",gap:10,opacity:.75}}>{beatLabels.map((label,i)=><div key={label} title={label} style={{height:4,width:i===activeBeat?88:28,borderRadius:3,background:i<=activeBeat?scene.accent:"rgba(255,255,255,.16)"}}/>)}</div>
    <WordCaptions text={scene.spoken} accent={scene.accent} durationFrames={durationFrames}/>
  </AbsoluteFill>;
};

export const PremiumMotion: React.FC<PremiumMotionProps> = ({scenes,artDirection="glass-future"}) => {
  const {fps}=useVideoConfig(); let cursor=0;
  return <AbsoluteFill>{scenes.map((scene,index)=>{const from=Math.round(cursor*fps);const duration=Math.max(1,Math.round(scene.duration*fps));cursor+=scene.duration;return <Sequence key={`${index}-${scene.badge}`} from={from} durationInFrames={duration}><PremiumSceneView scene={scene} index={index} total={scenes.length} direction={artDirection}/></Sequence>})}</AbsoluteFill>;
};

export const calculatePremiumMetadata: CalculateMetadataFunction<PremiumMotionProps> = async ({props}) => ({durationInFrames:Math.max(1,Math.round((props.scenes||[]).reduce((n,s)=>n+s.duration,0)*30))});
