import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
} from "remotion";

export const FPS = 24;
export const TOTAL = 24 * 30;
export const SHOTS: Array<{ id: string; from: number; duration: number }> = [];
export const SFX: Array<{ id: string; from: number; src: string }> = [];

export type MotionScene = {
  id: string;
  text: string;
  shot?: string;
  camera?: string;
  emotion?: string;
  tone?: string;
  sfx?: string;
  speaker?: string;
  character?: string;
  listener?: string;
  location?: string;
  year?: string;
  eraVariant?: string;
  costume?: string;
  prop?: string;
  visualGag?: string;
  visualMode?: string;
  durationFrames: number;
};

export type CaptionWord = {
  text: string;
  startFrame: number;
  endFrame: number;
};

export type RicksStyleDraftProps = {
  bgm?: boolean;
  scenes: MotionScene[];
  captionWords: CaptionWord[];
  durationInFrames: number;
  variantSeed?: number;
  editStyle?: string;
};

const C = {
  ink: "#101827",
  cream: "#F8F3E6",
  paper: "#EFE6D2",
  yellow: "#FFD34E",
  coral: "#FF655D",
  cyan: "#50D7E3",
  blue: "#4A66A0",
  green: "#6A8F6B",
  fieldGrey: "#596352",
  bavarianBlue: "#3A5A78",
  trenchMud: "#5B4838",
  hospitalWhite: "#EBF2F5",
  woodBrown: "#6E472B",
};

const CaptionContext = React.createContext<CaptionWord[]>([]);

const heading = (text: string) => {
  const first = text.split(/(?<=[.!?])\s+/)[0] || text;
  return first
    .replace(/[“”"']/g, "")
    .split(/\s+/)
    .slice(0, 7)
    .join(" ")
    .toUpperCase();
};

// ============================================================================
// SUBTITLE SAFE ZONE (Section 11 - Vertical 9:16 Mobile Safe Zone)
// ============================================================================
const Caption: React.FC<{ text: string; duration: number; tone?: string }> = ({
  text,
  tone = "NEUTRAL",
}) => {
  const f = useCurrentFrame(),
    words = React.useContext(CaptionContext),
    norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9à-ỹđ']/gi, ""),
    tokens = text.split(/\s+/).map(norm).filter(Boolean);

  let start = words.findIndex((w, i) =>
    tokens
      .slice(0, Math.min(4, tokens.length))
      .every((t, j) => words[i + j] && norm(words[i + j].text) === t),
  );
  if (start < 0) start = 0;

  const globalFrame = (words[start]?.startFrame || 0) + f;
  let active = words.findIndex(
    (w) => globalFrame >= w.startFrame && globalFrame < w.endFrame,
  );
  if (active < 0)
    active = Math.max(
      start,
      words.findIndex((w) => w.startFrame > globalFrame) - 1,
    );

  const visible = words.slice(
      Math.max(start, active - 2),
      Math.min(words.length, active + 4),
    ),
    offset = Math.max(start, active - 2);

  const fallbackWords = text.split(/\s+/).slice(0, 8);
  const highlightBg =
    tone === "SERIOUS" || tone === "DARK" ? "#E2B94B" : C.yellow;

  return (
    <div
      style={{
        position: "absolute",
        left: 56,
        right: 56,
        bottom: 155,
        display: "flex",
        justifyContent: "center",
        gap: 10,
        flexWrap: "wrap",
        fontFamily: "Arial, sans-serif",
        fontWeight: 900,
        fontSize: 44,
        lineHeight: 1.12,
        textAlign: "center",
        filter: "drop-shadow(0 8px 0 rgba(16,24,39,0.45))",
        zIndex: 45,
      }}
    >
      {visible.length > 0
        ? visible.map((w, i) => {
            const index = offset + i,
              on = index === active;
            return (
              <span
                key={`${index}-${w.startFrame}`}
                style={{
                  padding: "8px 15px",
                  borderRadius: 14,
                  border: `3px solid ${C.ink}`,
                  color: on ? C.ink : "#FFFFFF",
                  background: on ? highlightBg : "#101827F0",
                  transform: `translateY(${on ? -6 : 0}px) scale(${on ? 1.08 : 1})`,
                }}
              >
                {w.text}
              </span>
            );
          })
        : fallbackWords.map((w, i) => (
            <span
              key={i}
              style={{
                padding: "8px 15px",
                borderRadius: 14,
                border: `3px solid ${C.ink}`,
                color: i === Math.floor(f / 8) % fallbackWords.length ? C.ink : "#FFFFFF",
                background:
                  i === Math.floor(f / 8) % fallbackWords.length
                    ? highlightBg
                    : "#101827F0",
              }}
            >
              {w}
            </span>
          ))}
    </div>
  );
};

// ============================================================================
// PROP DATABASE (Section 20)
// ============================================================================
const PropBadge: React.FC<{ prop?: string; x?: number; y?: number }> = ({
  prop = "PROP_DOCUMENT",
  x = 305,
  y = 415,
}) => {
  switch (prop) {
    case "PROP_LETTER":
      return (
        <g transform={`translate(${x}, ${y}) rotate(-8)`}>
          <rect
            width="84"
            height="58"
            rx="6"
            fill="#FFFDF7"
            stroke={C.ink}
            strokeWidth="8"
          />
          <path d="M4 6L42 34L80 6" fill="none" stroke={C.ink} strokeWidth="7" />
          <circle cx="42" cy="32" r="9" fill="#B53737" />
        </g>
      );
    case "PROP_MEDAL":
      return (
        <g transform={`translate(${x}, ${y})`}>
          <path d="M22 0H46L38 26H30Z" fill="#B53737" stroke={C.ink} strokeWidth="6" />
          <path
            d="M24 26H44V38H56V58H44V70H24V58H12V38H24Z"
            fill="#2B303A"
            stroke="#FFFDF7"
            strokeWidth="5"
          />
        </g>
      );
    case "PROP_BEER_MUG":
      return (
        <g transform={`translate(${x}, ${y})`}>
          <rect
            x="8"
            y="18"
            width="56"
            height="70"
            rx="8"
            fill="#E5A93B"
            stroke={C.ink}
            strokeWidth="8"
          />
          <path
            d="M64 28H82V72H64"
            fill="none"
            stroke={C.ink}
            strokeWidth="8"
          />
          <path
            d="M4 18Q18 2 34 14Q52 2 68 18Z"
            fill="#FFFFFF"
            stroke={C.ink}
            strokeWidth="7"
          />
        </g>
      );
    case "PROP_PAINTBRUSH":
      return (
        <g transform={`translate(${x}, ${y}) rotate(-22)`}>
          <rect x="0" y="25" width="76" height="14" rx="5" fill="#8B5A2B" stroke={C.ink} strokeWidth="6" />
          <path d="M76 22L102 16L98 46L76 40Z" fill="#D94E41" stroke={C.ink} strokeWidth="6" />
        </g>
      );
    case "PROP_NEWSPAPER":
      return (
        <g transform={`translate(${x - 15}, ${y - 10}) rotate(5)`}>
          <rect width="96" height="112" rx="6" fill="#F6EFE2" stroke={C.ink} strokeWidth="8" />
          <rect x="12" y="14" width="72" height="16" fill={C.ink} />
          <path d="M12 44H84M12 62H84M12 80H62" stroke={C.ink} strokeWidth="6" />
        </g>
      );
    case "PROP_MICROPHONE":
      return (
        <g transform={`translate(${x}, ${y - 20})`}>
          <ellipse cx="32" cy="24" rx="18" ry="24" fill="#4A525D" stroke={C.ink} strokeWidth="8" />
          <path d="M32 48V105M12 105H52" stroke={C.ink} strokeWidth="9" />
        </g>
      );
    default:
      return null;
  }
};

// ============================================================================
// STICKMAN CHARACTER IDENTITY & ERA EVOLUTION (Sections 1, 2, 3, 19, 28)
// ============================================================================
const StickmanCharacter: React.FC<{
  action: number;
  side: "left" | "right";
  emotion?: string;
  tone?: string;
  close: boolean;
  persona?: string;
  eraVariant?: string;
  costume?: string;
  prop?: string;
  location?: string;
  speaking?: boolean;
}> = ({
  action,
  side,
  emotion = "curious",
  tone = "NEUTRAL",
  close,
  persona = "narrator",
  eraVariant = "CHARACTER_WWI_SOLDIER",
  costume = "COSTUME_MILITARY",
  prop = "PROP_DOCUMENT",
  location = "munich-1914",
  speaking = true,
}) => {
  const f = useCurrentFrame();
  const isSerious = tone === "SERIOUS" || tone === "DARK";
  const bob = Math.sin(f * (isSerious ? 0.06 : 0.11)) * (isSerious ? 3 : 6);
  const talk = speaking ? 6 + Math.abs(Math.sin(f * 0.68)) * 11 : 3;
  const blink = f % 97 > 91 ? 2 : 12;

  const isHitler = persona === "hitler";
  const soldier = persona.startsWith("soldier");
  const soldier2 = persona === "soldier2";
  const officer = persona === "officer";
  const doctor = persona === "doctor";
  const dap = persona === "dap";
  const narrator = persona === "narrator";

  // Era & Costume Anchors (Sections 3, 6, 18, 19)
  const isYoungCivilian =
    eraVariant === "CHARACTER_YOUNG" || costume === "COSTUME_CIVILIAN";
  const isHospital =
    eraVariant === "CHARACTER_HOSPITAL" ||
    costume === "COSTUME_HOSPITAL" ||
    location === "pasewalk-hospital" ||
    location === "ypres-gas";
  const isPolitical1919 =
    eraVariant === "CHARACTER_EARLY_CAREER" ||
    costume === "COSTUME_POLITICAL" ||
    location === "beer-hall-1919" ||
    location === "munich-1919";

  const coatColor = doctor
    ? "#EDF3F8"
    : isHospital && isHitler
      ? "#DCE6EC"
      : isYoungCivilian && isHitler
        ? "#5E5044"
        : isPolitical1919 && isHitler
          ? "#4B5345"
          : isHitler || soldier || officer
            ? C.fieldGrey
            : dap
              ? "#6E5239"
              : C.bavarianBlue;

  const armSwing = isSerious
    ? Math.sin(f * 0.07 + action) * 9
    : Math.sin(f * 0.13 + action) * 20;
  const legSwing = Math.sin(f * 0.12 + action) * 10;

  // Deadpan / Serious / Excited facial eyebrows
  const browPath =
    tone === "DRY_COMEDY"
      ? "M150 126h50M220 120l48-8" // deadpan raised brow
      : isSerious || emotion === "serious"
        ? "M152 120l46 14M268 120l-46 14" // furrowed serious brow
        : "M155 128q24-16 45 0M220 128q24-16 45 0";

  return (
    <div
      style={{
        position: "absolute",
        [side]: close ? 40 : 55,
        bottom: close ? 190 : 250,
        width: close ? 540 : 420,
        height: close ? 920 : 750,
        transform: `translateY(${bob}px) scaleX(${side === "right" && !close ? -1 : 1})`,
        filter: "drop-shadow(10px 16px 0 rgba(16,24,39,0.28))",
        zIndex: speaking ? 22 : 16,
      }}
    >
      <svg viewBox="0 0 420 760" width="100%" height="100%">
        <g
          stroke={C.ink}
          strokeWidth="14"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {/* Round White Stickman Head (Section 1) */}
          <circle cx="210" cy="145" r="102" fill="#FFFDF8" />

          {/* HAIRSTYLE & HEADWEAR BY ERA (Sections 2, 3, 6) */}
          {isHitler && !isHospital && (
            <>
              {/* Characteristic parted dark hair */}
              <path
                d="M114 130Q122 38 210 40Q292 42 308 118Q262 72 208 82Q162 66 114 130Z"
                fill="#23262E"
              />
              <path d="M194 74Q246 78 286 58" stroke="#23262E" strokeWidth="22" />
            </>
          )}

          {/* WWI Bavarian / German Feldmütze or Stahlhelm */}
          {(soldier || (isHitler && !isYoungCivilian && !isHospital && !isPolitical1919)) && (
            <>
              <path
                d="M104 114Q118 32 210 28Q304 32 316 114Z"
                fill="#616B55"
              />
              <path d="M92 114h236" stroke="#3F4738" strokeWidth="18" />
              <circle cx="210" cy="74" r="10" fill="#C94A38" />
            </>
          )}

          {/* Pasewalk / Ypres Eye & Head Bandage (1918 Gas Attack Continuity) */}
          {isHitler && isHospital && (
            <>
              <rect
                x="106"
                y="84"
                width="208"
                height="52"
                rx="14"
                fill="#FFFFFF"
                stroke={C.ink}
                strokeWidth="12"
              />
              <path d="M112 108h196" stroke="#CBD5E1" strokeWidth="6" />
            </>
          )}

          {/* WWI Officer Peaked Cap */}
          {officer && (
            <>
              <path
                d="M102 110Q125 32 210 32Q295 32 318 110Z"
                fill="#4E5944"
              />
              <path d="M88 110h244" stroke="#1E242B" strokeWidth="18" />
              <circle cx="210" cy="72" r="13" fill="#D5B15A" />
            </>
          )}

          {/* DAP 1919 Beer Hall Fedora / Hat */}
          {dap && (
            <>
              <path
                d="M108 112Q140 38 225 42Q286 45 315 105Z"
                fill="#5C402E"
              />
              <path d="M88 112h244" stroke="#3B281E" strokeWidth="16" />
            </>
          )}

          {/* Eyebrows & Eyes */}
          <path d={browPath} fill="none" />
          {!(isHitler && isHospital && location === "ypres-gas") && (
            <path d={`M172 158v${blink}M248 158v${blink}`} />
          )}

          {/* Moustache Evolution: WWI Handlebar/Trimmed vs 1919 Chaplin-style */}
          {isHitler && (
            <>
              <path
                d={
                  isYoungCivilian || (!isPolitical1919 && !isHospital)
                    ? "M172 188q38-10 76 0" // broader WWI moustache (1914-1917)
                    : "M188 188h44" // narrower 1919 moustache
                }
                strokeWidth="16"
              />
              <path d="M206 154l-8 28 22 2" strokeWidth="7" fill="none" />
            </>
          )}

          {/* Narrator Glasses */}
          {narrator && (
            <>
              <circle cx="174" cy="160" r="26" fill="none" strokeWidth="8" />
              <circle cx="246" cy="160" r="26" fill="none" strokeWidth="8" />
              <path d="M200 160h20" strokeWidth="8" />
            </>
          )}

          {/* Expressive Mouth */}
          {tone === "DRY_COMEDY" && !speaking ? (
            <path d="M186 216h48" strokeWidth="10" />
          ) : (
            <ellipse
              cx="210"
              cy="216"
              rx={isSerious ? 20 : 25}
              ry={talk}
              fill="#7E2E3B"
            />
          )}

          {/* Stickman Spine & Period Tunic/Coat */}
          <path d="M210 248L210 475" />
          <path
            d="M158 296Q210 268 262 296L280 458Q210 486 140 458Z"
            fill={coatColor}
          />

          {/* Costume Details (No WWII anachronisms in 1914-1919!) */}
          {doctor && (
            <>
              <path d="M210 296v155M164 345h92" stroke="#8EA0B5" strokeWidth="7" />
              <circle cx="210" cy="408" r="15" fill="none" stroke="#5F7188" strokeWidth="8" />
            </>
          )}
          {officer && (
            <>
              <path d="M154 328h112" stroke="#D5B15A" strokeWidth="9" />
              <path d="M150 304l34 18M270 304l-34 18" stroke="#D5B15A" strokeWidth="8" />
            </>
          )}
          {/* Iron Cross Ribbon on WWI Soldier Hitler (1914-1918) */}
          {isHitler && !isYoungCivilian && (
            <path d="M196 302L228 355" stroke="#1E242B" strokeWidth="10" />
          )}
          {soldier2 && (
            <path d="M152 304q58 52 116 0" stroke="#9B4B3E" strokeWidth="16" />
          )}

          {/* Stickman Arms */}
          <g transform={`rotate(${armSwing} 162 315)`}>
            <path d="M162 315L78 450" />
            <circle cx="74" cy="455" r="16" fill={C.ink} />
          </g>
          <g transform={`rotate(${-armSwing} 258 315)`}>
            <path d="M258 315L342 450" />
            <circle cx="346" cy="455" r="16" fill={C.ink} />
          </g>

          {/* Stickman Legs + Somme 1916 Leg Bandage Continuity */}
          <g transform={`rotate(${legSwing} 185 465)`}>
            <path d="M185 465L135 665" />
            {isHitler && location === "somme-1916" && (
              <rect
                x="136"
                y="545"
                width="36"
                height="52"
                rx="6"
                fill="#FFFFFF"
                stroke={C.ink}
                strokeWidth="8"
              />
            )}
            <path d="M114 672h54" />
          </g>
          <g transform={`rotate(${-legSwing} 235 465)`}>
            <path d="M235 465L285 665" />
            <path d="M266 672h54" />
          </g>
        </g>

        {/* WWI Rifle for Soldiers */}
        {soldier && (
          <g stroke={C.ink} strokeWidth="10" strokeLinecap="round">
            <path d="M292 315l52 245" />
            <path d="M328 475l34 45" />
          </g>
        )}

        {/* Narrator Historical Chronicle Book */}
        {narrator && (
          <g transform="translate(24 388) rotate(-8)">
            <rect
              width="102"
              height="130"
              rx="10"
              fill="#F5E1B8"
              stroke={C.ink}
              strokeWidth="9"
            />
            <path d="M22 40h58M22 68h58M22 96h42" stroke={C.ink} strokeWidth="7" />
          </g>
        )}

        {/* Prop Anchor */}
        <PropBadge prop={prop} />
      </svg>
    </div>
  );
};

// ============================================================================
// LOCATION IDENTITY SYSTEM & SAME LOCATION DIFFERENT TIME (Sections 4, 5, 16, 17)
// ============================================================================
const HistoricalEnvironment: React.FC<{
  location?: string;
  year?: string;
  tone?: string;
  visualGag?: string;
}> = ({
  location = "munich-1914",
  year = "1914",
  tone = "NEUTRAL",
  visualGag = "NONE",
}) => {
  const f = useCurrentFrame();
  const drift = Math.sin(f * 0.03) * 14;
  const ratX = (f * 3.2) % 340;

  const isTrench = /western-front|somme/.test(location);
  const isGas = location === "ypres-gas";
  const isHospital = location === "pasewalk-hospital";
  const isBeerHall = location === "beer-hall-1919";
  const isPostwar = location === "postwar-germany";
  const isMunich1919 = location === "munich-1919";

  const titleLabel = isBeerHall
    ? "MUNICH · QUÁN BIA DAP · 12/09/1919"
    : isHospital
      ? "BỆNH VIỆN PASEWALK · 11/1918"
      : isGas
        ? "GẦN YPRES, BỈ · KHÍ ĐỘC · 10/1918"
        : location === "somme-1916"
          ? "TRẬN SOMME · MẶT TRẬN PHÍA TÂY · 1916"
          : isTrench
            ? "MẶT TRẬN PHÍA TÂY · CHIẾN HÀO · 1914–1918"
            : isPostwar
              ? "ĐỨC HẬU CHIẾN · KHỦNG HOẢNG · 1918–1919"
              : isMunich1919
                ? "MUNICH · HỖN LOẠN CHÍNH TRỊ · 1919"
                : "MUNICH, BAVARIA · TRƯỚC THẾ CHIẾN · 1914";

  const skyGradient = isGas
    ? "linear-gradient(180deg, #6E7849 0%, #A9B873 55%, #4B4237 55%, #2E2720 100%)"
    : isTrench
      ? "linear-gradient(180deg, #6E7672 0%, #98A09B 55%, #5C4636 55%, #3B2D22 100%)"
      : isHospital
        ? "linear-gradient(180deg, #CFDCE2 0%, #E7F0F4 62%, #B5C2C7 62%, #8C999E 100%)"
        : isBeerHall
          ? "linear-gradient(180deg, #5C3A21 0%, #8A5834 60%, #4E301B 60%, #331F11 100%)"
          : isMunich1919 || isPostwar
            ? "linear-gradient(180deg, #7C7772 0%, #ACA39B 58%, #59534E 58%, #3B3734 100%)"
            : "linear-gradient(180deg, #7FB3D5 0%, #C5DFEE 58%, #827768 58%, #564E44 100%)";

  return (
    <AbsoluteFill style={{ background: skyGradient, zIndex: 0 }}>
      {/* Subtle Paper Grid Texture */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "radial-gradient(rgba(16,24,39,0.08) 2px, transparent 2px)",
          backgroundSize: "34px 34px",
        }}
      />

      {/* MUNICH 1914 vs MUNICH 1919 ARCHITECTURE (Section 5: Same Place, Different Time) */}
      {!isTrench && !isGas && !isHospital && !isBeerHall && (
        <svg
          viewBox="0 0 1080 1920"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        >
          {/* Fraunhofer / Munich twin domes & Fraunkirche silhouette */}
          <g fill={isMunich1919 || isPostwar ? "#5B544F" : "#D6C7B2"} stroke={C.ink} strokeWidth="10">
            <rect x="90" y="540" width="210" height="580" />
            <path d="M80 540L195 390L310 540Z" fill="#8C4A3B" />
            <rect x="330" y="610" width="240" height="510" />
            {/* Iconic Munich twin towers */}
            <rect x="610" y="420" width="110" height="700" />
            <circle cx="665" cy="405" r="58" fill="#5D7B68" />
            <rect x="755" y="440" width="110" height="680" />
            <circle cx="810" cy="425" r="58" fill="#5D7B68" />
          </g>

          {/* 1919 Political Unrest Posters, Smoke & Barricades */}
          {(isMunich1919 || isPostwar) && (
            <g>
              <circle cx={260 + drift} cy="420" r="85" fill="rgba(60,60,60,0.32)" />
              <circle cx={780 - drift} cy="380" r="110" fill="rgba(50,50,50,0.35)" />
              {/* Street Barricade & Posters */}
              <rect x="130" y="960" width="140" height="90" fill="#E6D5B8" stroke={C.ink} strokeWidth="8" />
              <text x="150" y="1015" fontSize="28" fontWeight="900" fill="#B53737">1919!</text>
              <rect x="740" y="945" width="170" height="95" fill="#E6D5B8" stroke={C.ink} strokeWidth="8" />
              <text x="762" y="1002" fontSize="26" fontWeight="900" fill={C.ink}>STREIK</text>
            </g>
          )}
        </svg>
      )}

      {/* WWI TRENCHES & SOMME (Section 4 & 7) */}
      {(isTrench || isGas) && (
        <svg
          viewBox="0 0 1080 1920"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        >
          {/* Distant Artillery Smoke & Explosions */}
          <circle cx={250 + drift} cy="450" r="95" fill="rgba(45,45,45,0.35)" />
          <circle cx={810 - drift} cy="410" r="120" fill="rgba(40,40,40,0.4)" />
          <path
            d="M740 680L790 520L830 650L900 540L865 710Z"
            fill="#F59E0B"
            stroke={C.ink}
            strokeWidth="8"
          />

          {/* Barbed Wire */}
          <path
            d="M0 780Q270 740 540 780Q810 820 1080 770"
            fill="none"
            stroke="#2B2D2F"
            strokeWidth="10"
          />
          <path
            d="M120 750L155 795M340 755L375 800M620 765L655 810M860 750L895 795"
            stroke="#2B2D2F"
            strokeWidth="8"
          />

          {/* Trench Sandbags & Mud Walls */}
          <rect x="0" y="1020" width="1080" height="900" fill={C.trenchMud} stroke={C.ink} strokeWidth="12" />
          {[60, 260, 460, 660, 860].map((x, idx) => (
            <ellipse
              key={idx}
              cx={x}
              cy="1015"
              rx="95"
              ry="38"
              fill="#8D7B65"
              stroke={C.ink}
              strokeWidth="10"
            />
          ))}

          {/* Recurring Trench Rat Gag (Section 17) */}
          {(visualGag.includes("RAT") || location === "western-front") && (
            <g transform={`translate(${120 + ratX}, 1055)`}>
              <ellipse cx="40" cy="22" rx="28" ry="16" fill="#4A4E54" stroke={C.ink} strokeWidth="6" />
              <circle cx="66" cy="18" r="4" fill={C.ink} />
              <path d="M12 24Q-15 15 -22 30" fill="none" stroke="#4A4E54" strokeWidth="6" />
            </g>
          )}
        </svg>
      )}

      {/* YPRES MUSTARD GAS CLOUDS */}
      {isGas && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(circle at 70% 48%, rgba(186, 209, 92, 0.55), transparent 45%), radial-gradient(circle at 25% 58%, rgba(154, 179, 74, 0.5), transparent 50%)",
          }}
        />
      )}

      {/* PASEWALK MILITARY HOSPITAL 1918 */}
      {isHospital && (
        <svg
          viewBox="0 0 1080 1920"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        >
          <rect
            x="90"
            y="380"
            width="900"
            height="860"
            rx="16"
            fill="#F8FAFC"
            stroke={C.ink}
            strokeWidth="12"
          />
          {/* Hospital Window */}
          <rect
            x="160"
            y="460"
            width="280"
            height="340"
            fill="#BAE6FD"
            stroke={C.ink}
            strokeWidth="10"
          />
          <path d="M300 460V800M160 630H440" stroke={C.ink} strokeWidth="10" />
          {/* Red Cross Sign */}
          <circle cx="760" cy="580" r="85" fill="#FFFFFF" stroke={C.ink} strokeWidth="10" />
          <path d="M740 520H780V560H820V600H780V640H740V600H700V560H740Z" fill="#DC2626" />
        </svg>
      )}

      {/* MUNICH BEER HALL 1919 (DAP MEETING) */}
      {isBeerHall && (
        <svg
          viewBox="0 0 1080 1920"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        >
          {/* Warm Wood Paneling & Lanterns */}
          <rect x="70" y="380" width="940" height="880" rx="18" fill="#C89D66" stroke={C.ink} strokeWidth="12" />
          <circle cx="320" cy="480" r="46" fill="#FDE047" stroke={C.ink} strokeWidth="8" />
          <circle cx="760" cy="480" r="46" fill="#FDE047" stroke={C.ink} strokeWidth="8" />
          {/* Wooden Beer Tables */}
          <rect x="110" y="1080" width="860" height="90" fill="#6E4223" stroke={C.ink} strokeWidth="12" />
        </svg>
      )}

      {/* TOP LOCATION & YEAR STAMP (Sections 4, 6, 27) */}
      <div
        style={{
          position: "absolute",
          left: 48,
          right: 48,
          top: 64,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          zIndex: 35,
        }}
      >
        <div
          style={{
            padding: "12px 22px",
            background: "#101827EE",
            color: "#FFFFFF",
            fontSize: 24,
            fontWeight: 900,
            letterSpacing: 2,
            borderRadius: 12,
            borderLeft: `10px solid ${C.yellow}`,
            boxShadow: "0 6px 0 rgba(16,24,39,0.35)",
          }}
        >
          {titleLabel}
        </div>
        <div
          style={{
            padding: "10px 20px",
            background: C.yellow,
            color: C.ink,
            fontSize: 26,
            fontWeight: 900,
            borderRadius: 12,
            border: `4px solid ${C.ink}`,
            boxShadow: "0 6px 0 rgba(16,24,39,0.35)",
          }}
        >
          {year}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ============================================================================
// VISUAL STORYTELLING OVERLAYS: MAPS, METAPHORS & DRY COMEDY GAGS (Sections 12, 13, 24, 26)
// ============================================================================
const VisualStoryOverlay: React.FC<{ scene: MotionScene }> = ({ scene }) => {
  const f = useCurrentFrame();
  const mode = scene.visualMode || "DIRECT_ACTION";
  const gag = scene.visualGag || "NONE";

  if (mode === "MAP") {
    return (
      <div
        style={{
          position: "absolute",
          left: 85,
          right: 85,
          top: 410,
          height: 430,
          borderRadius: 28,
          background: "#F4EBD9",
          border: `10px solid ${C.ink}`,
          boxShadow: "14px 14px 0 rgba(16,24,39,0.35)",
          padding: 28,
          zIndex: 25,
        }}
      >
        <div style={{ fontSize: 26, fontWeight: 900, color: C.ink, letterSpacing: 2 }}>
          BẢN ĐỒ CHIẾN LƯỢC · {scene.year || "1914–1918"}
        </div>
        <svg viewBox="0 0 800 300" width="100%" height="85%">
          <path
            d="M90 220Q220 80 410 130Q590 175 710 85"
            fill="none"
            stroke="#8B7355"
            strokeWidth="18"
            strokeDasharray="18 12"
          />
          <circle cx="240" cy="150" r="24" fill="#DC2626" stroke={C.ink} strokeWidth="7" />
          <text x="195" y="205" fontSize="26" fontWeight="900" fill={C.ink}>SOMME</text>
          <circle cx="480" cy="145" r="26" fill={C.yellow} stroke={C.ink} strokeWidth="7" />
          <text x="430" y="200" fontSize="26" fontWeight="900" fill={C.ink}>MUNICH</text>
          <path
            d="M150 110L340 138"
            stroke="#DC2626"
            strokeWidth="12"
            strokeLinecap="round"
          />
        </svg>
      </div>
    );
  }

  if (gag === "NO_EXIT_BUTTON") {
    return (
      <div
        style={{
          position: "absolute",
          left: 140,
          right: 140,
          top: 430,
          padding: "24px 32px",
          borderRadius: 22,
          background: "#101827F2",
          border: `8px solid ${C.yellow}`,
          color: "#FFFFFF",
          textAlign: "center",
          fontWeight: 900,
          fontSize: 32,
          zIndex: 28,
          transform: `scale(${0.96 + Math.sin(f * 0.2) * 0.04})`,
        }}
      >
        ⚠️ GAME QUÁ DÀI · KHÔNG TÌM THẤY NÚT "THOÁT VỀ MÀN HÌNH CHÍNH"
      </div>
    );
  }

  if (gag === "CHAOS_ARROWS") {
    return (
      <div
        style={{
          position: "absolute",
          left: 110,
          right: 110,
          top: 420,
          padding: "20px 28px",
          borderRadius: 22,
          background: "#FFFDF8",
          border: `8px solid ${C.ink}`,
          textAlign: "center",
          fontWeight: 900,
          fontSize: 30,
          color: C.ink,
          zIndex: 28,
        }}
      >
        💬 GROUP CHAT CHÍNH TRỊ 1919 · MỌI THÀNH VIÊN ĐỀU CÓ SÚNG
      </div>
    );
  }

  if (gag === "EMPTY_WALLET") {
    return (
      <div
        style={{
          position: "absolute",
          right: 85,
          top: 450,
          padding: "18px 26px",
          borderRadius: 20,
          background: "#FFFDF8",
          border: `8px solid ${C.ink}`,
          fontWeight: 900,
          fontSize: 28,
          color: C.ink,
          zIndex: 28,
          transform: `rotate(${Math.sin(f * 0.12) * 4}deg)`,
        }}
      >
        👛 VÍ RỖNG: 0 MARK · SỰ NGHIỆP: ???
      </div>
    );
  }

  return null;
};

// ============================================================================
// SCENE SHOT COMPOSER (Sections 8, 9, 10, 11, 25)
// ============================================================================
const Shot: React.FC<{
  scene: MotionScene;
  index: number;
  start: number;
  total: number;
}> = ({ scene, index, start, total }) => {
  const f = useCurrentFrame();
  const enter = spring({
    frame: f,
    fps: FPS,
    config: { damping: 16, stiffness: 130 },
  });
  const exit = interpolate(
    f,
    [scene.durationFrames - 6, scene.durationFrames],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const shot = (scene.shot || scene.camera || "medium").toLowerCase();
  const close = shot.includes("close");
  const overShoulder = shot.includes("over");
  const insert = shot.includes("insert") || shot.includes("object");
  const topDown = shot.includes("top");
  const lowAngle = shot.includes("low");
  const side: "left" | "right" = index % 2 ? "right" : "left";

  const cameraTransform = topDown
    ? `perspective(1400px) rotateX(12deg) scale(0.94)`
    : lowAngle
      ? `perspective(1200px) translateY(55px) scale(1.12) rotateX(-5deg)`
      : close
        ? `scale(1.14) translateY(35px)`
        : insert
          ? `scale(1.18)`
          : `scale(${1.01 + Math.sin(f * 0.04) * 0.015})`;

  return (
    <AbsoluteFill
      style={{
        background: C.cream,
        overflow: "hidden",
        fontFamily: "Arial, sans-serif",
        transform: `translateX(${exit * (index % 2 ? -90 : 90)}px)`,
      }}
    >
      <HistoricalEnvironment
        location={scene.location}
        year={scene.year}
        tone={scene.tone}
        visualGag={scene.visualGag}
      />

      {/* HEADLINE CARD (Top Middle Safe Zone for 9:16) */}
      <div
        style={{
          position: "absolute",
          left: 48,
          right: 48,
          top: 158,
          padding: "20px 28px",
          borderRadius: 22,
          background: "rgba(255, 253, 248, 0.94)",
          border: `6px solid ${C.ink}`,
          boxShadow: "10px 10px 0 rgba(16,24,39,0.28)",
          transform: `translateY(${(1 - enter) * -50}px)`,
          zIndex: 32,
        }}
      >
        {scene.speaker && (
          <div
            style={{
              display: "inline-block",
              marginBottom: 8,
              padding: "4px 14px",
              borderRadius: 8,
              background: C.ink,
              color: C.yellow,
              fontSize: 20,
              fontWeight: 900,
              letterSpacing: 1.5,
            }}
          >
            {scene.speaker}
          </div>
        )}
        <div
          style={{
            fontSize: 44,
            lineHeight: 1.05,
            fontWeight: 900,
            letterSpacing: -1,
            color: C.ink,
          }}
        >
          {heading(scene.text)}
        </div>
      </div>

      {/* VISUAL METAPHOR / MAP / COMEDY OVERLAY */}
      <VisualStoryOverlay scene={scene} />

      {/* STICKMAN STAGE */}
      <AbsoluteFill
        style={{
          transform: cameraTransform,
          transformOrigin: "center center",
        }}
      >
        <StickmanCharacter
          action={index % 5}
          side={side}
          emotion={scene.emotion}
          tone={scene.tone}
          close={close || overShoulder}
          persona={scene.character}
          eraVariant={scene.eraVariant}
          costume={scene.costume}
          prop={scene.prop}
          location={scene.location}
          speaking
        />
        {scene.listener && !close && (
          <StickmanCharacter
            action={(index + 2) % 5}
            side={side === "left" ? "right" : "left"}
            emotion="curious"
            tone={scene.tone}
            close={false}
            persona={scene.listener}
            location={scene.location}
            speaking={false}
          />
        )}
      </AbsoluteFill>

      {/* SUBTITLES IN SAFE MOBILE ZONE */}
      <Caption text={scene.text} duration={scene.durationFrames} tone={scene.tone} />

      {/* PROGRESS BAR */}
      <div
        style={{
          position: "absolute",
          left: 0,
          bottom: 0,
          height: 14,
          width: `${((start + f) / total) * 100}%`,
          background: C.coral,
          zIndex: 50,
        }}
      />
    </AbsoluteFill>
  );
};

export const RicksStyleDraft: React.FC<RicksStyleDraftProps> = ({
  bgm = true,
  scenes,
  captionWords = [],
  durationInFrames,
  variantSeed = 0,
}) => {
  let cursor = 0;
  return (
    <CaptionContext.Provider value={captionWords}>
      <AbsoluteFill style={{ background: C.cream }}>
        {scenes.map((s, i) => {
          const from = cursor;
          cursor += s.durationFrames;
          return (
            <Sequence
              key={s.id || i}
              from={from}
              durationInFrames={s.durationFrames}
            >
              <Shot
                scene={s}
                index={i + variantSeed}
                start={from}
                total={durationInFrames}
              />
            </Sequence>
          );
        })}
        <Audio src={staticFile("ricks-draft/audio/voice.wav")} volume={1} />
        {bgm && (
          <Audio
            loop
            src={staticFile("ricks-draft/audio/bgm.mp3")}
            volume={(f) =>
              interpolate(
                f,
                [0, 20, durationInFrames - 30, durationInFrames],
                [0, 0.06, 0.06, 0],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
              )
            }
          />
        )}
      </AbsoluteFill>
    </CaptionContext.Provider>
  );
};
