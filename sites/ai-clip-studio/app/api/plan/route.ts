import { NextResponse } from "next/server";

const emotions = ["curious", "serious", "intrigued", "excited", "confident"];
const shots = [
  "extreme close-up",
  "over-shoulder",
  "orbit medium",
  "insert shot",
  "dutch close-up",
  "low angle",
  "top-down",
  "hero medium",
];
const sfxList = [
  "whoosh-cinematic",
  "artillery-boom",
  "riser-short",
  "impact-bass",
  "medal-chime",
  "beer-hall-clink",
];
const femaleNames = new Set([
  "linh",
  "anna",
  "emma",
  "sarah",
  "mary",
  "jenny",
  "sonia",
  "aria",
  "alice",
  "lisa",
  "melania",
  "hillary",
]);

function inferContextualSfx(text: string, idx: number): string {
  const t = text.toLowerCase();
  if (/(pháo|nổ|somme|bắn|đạn|xóa cả khu vực)/.test(t)) return "artillery-boom";
  if (/(khí độc|ypres|mù)/.test(t)) return "gas-hiss";
  if (/(bệnh viện|pasewalk|hồi phục)/.test(t)) return "hospital-clock";
  if (/(quán bia|dap|đảng công nhân)/.test(t)) return "beer-hall-clink";
  if (/(huân chương|thập tự sắt)/.test(t)) return "medal-chime";
  return sfxList[idx % sfxList.length];
}

function dialoguePlan(script: string, defaultVoice: string) {
  const blocks: { name: string; text: string }[] = [];
  let current = "",
    buffer: string[] = [];
  const flush = () => {
    if (current && buffer.length) {
      const text = buffer.join(" ").trim();
      let chunk = "";
      for (const sentence of text.split(/(?<=[.!?…])\s+/)) {
        const next = (chunk + " " + sentence).trim();
        if (chunk && next.split(/\s+/).length > 22) {
          blocks.push({ name: current, text: chunk });
          chunk = sentence;
        } else chunk = next;
      }
      if (chunk) blocks.push({ name: current, text: chunk });
    }
    buffer = [];
  };
  const IGNORED_NAME_PREFIXES = [
    "tập", "cảnh", "hồi", "phần", "bước", "lưu ý", "chú ý", "lịch sử", "thời gian",
    "năm", "hết", "ghi chú", "hướng dẫn", "nhân vật", "bối cảnh", "phong cách",
    "ngôi kể", "dark comedy", "ước tính", "bài học", "nội dung", "yêu cầu",
    "trạm", "con phố", "cây cầu", "ngôi nhà", "đây là", "hãy", "không", "đoạn",
    "chính trị", "thời", "lưu", "đây", "ngôi", "dark", "hã", "hư", "hú", "iế", "hế", "bướ",
    "scene", "act", "chapter", "note", "prompt", "test", "haru (kể", "haru kể"
  ];

  for (const raw of script.split(/\n+/)) {
    const line = raw.trim().replace(/^[-*#_~`“”•\d.]+|[*#_~`“”]+$/g, "").trim();
    const m = line.match(/^([A-ZÀ-ỸĐ0-9][A-ZÀ-ỸĐ0-9 ._\-()]{1,42}):\s*(.*)$/i);
    if (m) {
      const rawSpeaker = m[1].trim();
      const cleanSpeaker = rawSpeaker.replace(/\(.*?\)/g, "").trim();
      const lowerClean = cleanSpeaker.toLowerCase();
      const isHeader = IGNORED_NAME_PREFIXES.some((p) => lowerClean.startsWith(p) || lowerClean === p);
      if (!isHeader && cleanSpeaker.length >= 2 && cleanSpeaker.length <= 32 && !/^\d+$/.test(cleanSpeaker)) {
        flush();
        current = cleanSpeaker;
        if (m[2].trim()) buffer.push(m[2].trim());
      }
    } else if (
      line &&
      !line.startsWith("[") &&
      !line.startsWith("---") &&
      !line.startsWith("**") &&
      !line.startsWith("##") &&
      current
    )
      buffer.push(line);
  }
  flush();
  const names = [...new Set(blocks.map((m) => m.name))];
  if (names.length < 2) return null;
  const vietnamese =
    defaultVoice.startsWith("vi-") || defaultVoice.startsWith("vieneu-");
  let fi = 0,
    mi = 0;
  const femaleVoices = vietnamese
    ? [
        "vieneu-Trúc Ly",
        "vieneu-Mai Anh",
        "vieneu-Thùy Dung",
        "vieneu-Ngọc Huyền",
        "vieneu-Mỹ Duyên",
        "vieneu-Gia Hân",
        "vieneu-Khánh Ngân",
        "vieneu-Hồng Nhung",
        "vieneu-Bích Ngọc",
        "vieneu-Cẩm Tú",
        "vieneu-Thảo Vy",
        "vieneu-Hải Yến",
      ]
    : ["en-US-AriaNeural", "en-GB-SoniaNeural"];
  const maleVoices = vietnamese
    ? [
        "vieneu-Thiện Minh",
        "vieneu-Hải Đăng",
        "vieneu-Quang Sơn",
        "vieneu-Minh Đức",
        "vieneu-Adam bựa",
        "vieneu-Phạm Tuyên",
        "vieneu-Thanh Bình",
        "vieneu-Thái Sơn",
        "vieneu-Đan Trường",
        "vieneu-Bảo Long",
        "vieneu-Quốc Bảo",
        "vieneu-Văn Khải",
        "vieneu-Hoàng Nam",
      ]
    : ["en-GB-RyanNeural", "en-US-GuyNeural", "en-US-ChristopherNeural"];
  const roleVoices: Record<string, string> = {
    narrator: "vieneu-Thiện Minh",
    hitler: "vieneu-Hải Đăng",
    soldier: "vieneu-Quang Sơn",
    soldier1: "vieneu-Minh Đức",
    soldier2: "vieneu-Adam bựa",
    officer: "vieneu-Phạm Tuyên",
    doctor: "vieneu-Thanh Bình",
    dap: "vieneu-Thái Sơn",
    haru: "vieneu-Đức Trí",
    aiko: "vieneu-Trúc Ly",
    ong_chu: "vieneu-Mạnh Dũng",
    ban_ca: "vieneu-Thái Sơn",
  };
  const usedVoices = new Set<string>();
  const cast = names.map((name) => {
    const normalized = name.toLowerCase(),
      key = normalized
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-z]/g, "");
    const female =
      !/(lính|sĩ quan|bác sĩ|hitler|người dẫn|thành viên|ông chủ|bán cá|haru)/.test(normalized) &&
      (femaleNames.has(key) || normalized.includes("aiko") || normalized.includes("cô"));
    const character = key.includes("haru")
      ? "haru"
      : key.includes("aiko")
        ? "aiko"
        : normalized.includes("ông chủ") || normalized.includes("chủ trạm")
          ? "ong_chu"
          : normalized.includes("bán cá")
            ? "ban_ca"
            : key.includes("trump")
              ? "trump"
              : key.includes("hitler")
                ? "hitler"
                : normalized.includes("dẫn")
                  ? "narrator"
                  : normalized.includes("bác sĩ")
                    ? "doctor"
                    : normalized.includes("sĩ quan")
                      ? "officer"
                      : normalized.includes("lính 1")
                        ? "soldier1"
                        : normalized.includes("lính 2")
                          ? "soldier2"
                          : normalized.includes("lính")
                            ? "soldier"
                            : normalized.includes("dap") || normalized.includes("đảng")
                              ? "dap"
                              : female
                                ? "female"
                                : "male";
    let voice =
      vietnamese && roleVoices[character]
        ? roleVoices[character]
        : female
          ? femaleVoices[fi++ % femaleVoices.length]
          : maleVoices[mi++ % maleVoices.length];
    if (usedVoices.has(voice)) {
      const pool = female ? femaleVoices : maleVoices;
      for (const candidate of pool) {
        if (!usedVoices.has(candidate)) {
          voice = candidate;
          break;
        }
      }
    }
    usedVoices.add(voice);
    const styles: { [key: string]: [string, string] } = {
      narrator: ["-4%", "+0Hz"],
      hitler: ["-3%", "-5Hz"],
      soldier: ["-2%", "+2Hz"],
      soldier1: ["-6%", "-3Hz"],
      soldier2: ["-5%", "-4Hz"],
      officer: ["-6%", "-6Hz"],
      doctor: ["-4%", "+1Hz"],
      dap: ["-3%", "-2Hz"],
    };
    const [rate, pitch] = styles[character] || ["-3%", "+0Hz"];
    return { name, voice, character, rate, pitch };
  });
  const byName = Object.fromEntries(cast.map((c) => [c.name, c]));
  const scenes = blocks.map((m, i) => {
    const c = byName[m.name];
    const text = m.text;
    const tLow = text.toLowerCase();
    const shot =
      tLow.includes("pháo kích") || tLow.includes("thông điệp")
        ? "pov"
        : tLow.includes("tuyệt vời") ||
            tLow.includes("spoiler") ||
            tLow.includes("vinh quang") ||
            tLow.includes("nhận ra")
          ? "reaction close-up"
          : tLow.includes("giáng sinh") || tLow.includes("tưởng tượng")
            ? "low angle"
            : tLow.includes("khổng lồ") || tLow.includes("mặt trận")
              ? "extreme wide"
              : i % 2 === 0
                ? "two-shot"
                : "over-shoulder";
    return {
      id: `dialogue_${String(i + 1).padStart(3, "0")}`,
      text,
      speaker: c.name,
      voice: c.voice,
      character: c.character,
      listener: cast[(cast.indexOf(c) + 1) % cast.length]?.character,
      emotion: ["curious", "serious", "intrigued", "excited"][i % 4],
      shot,
      duration: Number(
        Math.min(9.5, Math.max(2.6, text.split(/\s+/).length / 2.15)).toFixed(1),
      ),
      sfx: inferContextualSfx(text, i),
    };
  });
  return { cast, scenes };
}

function semanticChunks(script: string) {
  const sentences = script
      .split(/(?<=[.!?])\s+|\n+/)
      .map((s) => s.trim())
      .filter(Boolean),
    pieces: string[] = [];
  for (const sentence of sentences) {
    const words = sentence.split(/\s+/);
    if (words.length <= 11) pieces.push(sentence);
    else
      for (let i = 0; i < words.length; i += 9)
        pieces.push(words.slice(i, i + 9).join(" "));
  }
  const chunks: string[] = [];
  let current = "";
  for (const piece of pieces) {
    const combined = (current + " " + piece).trim();
    if (current && combined.split(/\s+/).length > 11) {
      chunks.push(current);
      current = piece;
    } else current = combined;
  }
  if (current) chunks.push(current);
  while (chunks.length > 110) {
    let best = 0,
      bestWords = Infinity;
    for (let i = 0; i < chunks.length - 1; i++) {
      const n = (chunks[i] + " " + chunks[i + 1]).split(/\s+/).length;
      if (n < bestWords) {
        best = i;
        bestWords = n;
      }
    }
    chunks.splice(best, 2, chunks[best] + " " + chunks[best + 1]);
  }
  return chunks;
}

export async function POST(request: Request) {
  try {
    const b = (await request.json()) as {
      script?: string;
      voice?: string;
      energy?: string;
      multiVoice?: boolean;
    };
    const script = (b.script || "").trim();
    if (script.length < 10)
      return NextResponse.json({ error: "Kịch bản quá ngắn" }, { status: 400 });
    try {
      const backend = process.env.RENDER_BACKEND_URL || "http://127.0.0.1:8787";
      const response = await fetch(`${backend}/api/story-world`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(b),
      });
      if (response.ok) return NextResponse.json(await response.json());
    } catch {
      // Backend unavailable: retain the lightweight local planner below.
    }
    const dialogue =
      b.multiVoice !== false
        ? dialoguePlan(script, b.voice || "vieneu-Thiện Minh")
        : null;
    const chunks = semanticChunks(script);
    const scenes =
      dialogue?.scenes ||
      chunks.map((text, i) => ({
        id: `scene_${String(i + 1).padStart(3, "0")}`,
        text,
        emotion:
          emotions[
            Math.min(4, Math.floor(i / Math.max(1, chunks.length / 5)))
          ],
        shot: shots[i % shots.length],
        duration: Number(
          Math.min(5.2, Math.max(2.2, text.split(/\s+/).length / 2.55)).toFixed(
            1,
          ),
        ),
        sfx: inferContextualSfx(text, i),
      }));
    return NextResponse.json({
      title: scenes[0]?.text.slice(0, 42),
      duration: Number(scenes.reduce((n, s) => n + s.duration, 0).toFixed(1)),
      voice: b.voice || "vieneu-Thiện Minh",
      energy: b.energy,
      resolution: "1920x1080",
      aspectRatio: "16:9",
      subtitlesBurnedIn: false,
      scenes,
      cast: dialogue?.cast || [],
      multiVoice: Boolean(dialogue),
      voicePlan: {
        engine: "VieNeu-TTS v3 Turbo 48kHz Studio",
        clarity: "EQ speech + paralinguistic emotion tags ([thở dài], [cười], [hắng giọng])",
        normalization: "YouTube Master -15.2 LUFS",
        ducking: "Multi-track Foley SFX + BGM tự hạ khi có thoại",
      },
    });
  } catch {
    return NextResponse.json({ error: "Dữ liệu không hợp lệ" }, { status: 400 });
  }
}
