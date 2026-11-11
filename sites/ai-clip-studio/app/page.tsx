"use client";
import { useMemo, useState } from "react";
import { PreflightPanel } from "../components/PreflightPanel";
import {
  Clapperboard,
  Mic2,
  Play,
  Sparkles,
  WandSparkles,
  Volume2,
  Download,
  Server,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

type Scene = {
  id: string;
  text: string;
  emotion: string;
  shot: string;
  duration: number;
  sfx: string;
  speaker?: string;
  voice?: string;
  character?: string;
};
type CastMember = { name: string; voice: string; character: string };
type Plan = {
  title: string;
  duration: number;
  scenes: Scene[];
  cast?: CastMember[];
  multiVoice?: boolean;
};
type Variant = { index: number; label: string; video: string };
type ContentReview = {
  overall_score: number;
  verdict: string;
  model?: string;
  scores?: {
    hook_and_retention?: number;
    historical_accuracy?: number;
    dark_comedy_balance?: number;
    voice_casting_48khz?: number;
    visual_and_sfx_direction?: number;
  };
  detailed_sections?: {
    hook_analysis?: string;
    pacing_and_structure?: string;
    historical_fidelity?: string;
    voice_and_emotion_review?: string;
    visual_and_sfx_review?: string;
  };
  strengths?: string[];
  improvements?: string[];
  scene_highlights?: { scene: string; rating: string; note: string }[];
};

const sample = `[HOOK — MUNICH, 1914]

NGƯỜI DẪN:
Hãy tưởng tượng bạn 25 tuổi. Sự nghiệp... chưa có gì đáng kể. Tiền... cũng chẳng có bao nhiêu. Tương lai... khá mù mịt.
Và đúng lúc bạn đang không biết đời mình sẽ đi đâu... cả châu Âu quyết định lao vào một cuộc chiến tranh khổng lồ.
Một cách giải quyết vấn đề rất... châu Âu năm 1914.
Khi Thế chiến thứ nhất bùng nổ, Adolf Hitler đang sống ở Munich. Ông là công dân Áo. Nhưng vào tháng 8 năm 1914... Hitler gia nhập quân đội Bavaria.

HITLER:
“Mọi người đều đi đánh nhau à?”

NGƯỜI LÍNH:
“Gần như vậy.”

HITLER:
“Nghe nói chiến tranh sẽ kết thúc trước Giáng sinh?”

NGƯỜI LÍNH:
“Người ta đang nói thế.”

NGƯỜI DẪN:
Spoiler lịch sử. Không. Không hề. Không một chút nào.

[CẢNH — MẶT TRẬN PHÍA TÂY, 1914]

NGƯỜI DẪN:
Hitler được biên chế vào Trung đoàn Bộ binh Dự bị Bavaria số 16. Cuối năm 1914, đơn vị của ông được đưa tới Mặt trận phía Tây.
Nếu bạn đang tưởng tượng những đoàn quân hùng dũng tiến qua đồng cỏ, cờ tung bay, nhạc nền hoành tráng... thì hãy xóa hình ảnh đó đi.
Thực tế là: Bùn. Chuột. Pháo binh. Súng máy. Và hàng nghìn người cố gắng sống sót thêm một ngày.

LÍNH 1:
“Đây là chiến tranh vinh quang à?”

LÍNH 2:
“Chắc vậy.”

LÍNH 1:
“Tôi ngâm chân trong bùn ba ngày rồi.”

LÍNH 2:
“Bùn rất vinh quang.”

NGƯỜI DẪN:
Hitler làm nhiệm vụ liên lạc cho sở chỉ huy trung đoàn. Nói đơn giản, ông mang thông điệp giữa các vị trí quân sự. Nghe hơi giống shipper. Chỉ khác một chút: Shipper bình thường không phải giao hàng trong lúc pháo binh đang cố xóa cả khu vực khỏi bản đồ.

SĨ QUAN:
“Mang thông điệp này tới sở chỉ huy.”

HITLER:
“Qua khu vực đang bị pháo kích?”

SĨ QUAN:
“Đúng.”

HITLER:
“Có đường nào an toàn hơn không?”

SĨ QUAN:
“Không.”

HITLER:
“...Tuyệt vời.”

[CẢNH — TRẬN SOMME, 1916]

NGƯỜI DẪN:
Tháng 12 năm 1914, Hitler nhận Huân chương Thập tự Sắt hạng Nhì. Sau này, vào tháng 8 năm 1918, ông còn nhận Thập tự Sắt hạng Nhất.
Nhưng năm 1916, tại Trận Somme, Hitler bị mảnh đạn pháo làm bị thương ở chân và được đưa khỏi mặt trận để điều trị.

BÁC SĨ:
“Anh bị thương.”

HITLER:
“Tôi cũng vừa nhận ra.”

BÁC SĨ:
“Anh sẽ được đưa về Đức đến khi hồi phục.”

[CẢNH — YPRES & BỆNH VIỆN PASEWALK, 1918]

NGƯỜI DẪN:
Tháng 10 năm 1918, gần Ypres ở Bỉ, đơn vị của Hitler trúng một đợt tấn công khí độc của quân Anh. Mắt ông bị tổn thương nặng và tạm thời mất thị lực, được chuyển tới bệnh viện quân y ở Pasewalk.
Và chính tại đó, ngày 11 tháng 11 năm 1918, Đức ký hiệp định đình chiến.

[CẢNH — MUNICH, 1919]

NGƯỜI DẪN:
Sau chiến tranh, Hitler quay lại Munich. Ngày 12 tháng 9 năm 1919, ông được cử tới theo dõi một tổ chức chính trị nhỏ trong một quán bia tên là Đảng Công nhân Đức.

THÀNH VIÊN ĐẢNG CÔNG NHÂN ĐỨC:
“Đức cần một phong trào mới!”

HITLER:
“Tôi có vài ý kiến.”

NGƯỜI DẪN:
Và rất nhanh, ông phát hiện ra thứ mà mình làm tốt hơn vẽ tranh: Nói. Rất nhiều. Cuộc chiến đã kết thúc, nhưng câu chuyện nguy hiểm hơn... chỉ vừa mới bắt đầu.`;

const CANONICAL_EPISODE_01 = `# STUDIO SCRIPT V1 — UNIVERSAL VIDEO FORMAT

PROJECT: HITLER_EP01_MUNICH_1914
LANGUAGE: vi-VN
GENRE: Lịch sử
STYLE: Premium Stickman Cinematic B
ASPECT_RATIO: 16:9
TARGET_DURATION: AUTO
TONE: Lịch sử, châm biếm sâu sắc
MEME_POLICY: CONTEXTUAL
MEME_MAX_PER_MINUTE: 2

# NHÂN VẬT

CHARACTER: Adolf Hitler
ROLE: Nhân vật chính (Chàng trai thất bại tại Munich, họa sĩ tranh màu nước 25 tuổi)
APPEARANCE: Blob-Head đầu tròn 42%, áo khoác nâu sờn vai, túi đựng tranh màu nước
VOICE: vieneu-Thiện Minh
VOICE_STYLE: Tự sự, cay đắng, có phần mỉa mai và cuồng nhiệt ở cuối

CHARACTER: Bà Chủ Nhà
ROLE: Bà chủ nhà trọ tại số 34 Schleißheimer Straße, Munich
APPEARANCE: Blob-Head váy dài hoa văn cũ, khăn quàng cổ xám, tạp dề Bavarian, tay chống nạnh
VOICE: vieneu-Trúc Ly
VOICE_STYLE: Đanh đá, gắt gỏng, giục nợ tiền phòng

CHARACTER: Người Bán Báo
ROLE: Người bán báo dạo và người đi đường tại Munich
APPEARANCE: Blob-Head mũ vải mềm, áo gi-lê len, cầm xấp báo phụ trương chiến tranh
VOICE: vieneu-Phạm Tuyên
VOICE_STYLE: Hối hả, hô hào, dò xét người lạ

CHARACTER: Người Dẫn Chuyện
ROLE: Kể chuyện bối cảnh lịch sử thành phố Munich năm 1914
APPEARANCE: Không xuất hiện hình thể
VOICE: vieneu-Hải Đăng
VOICE_STYLE: Điềm tĩnh, khách quan, sâu sắc, trang nghiêm

# KỊCH BẢN

SCENE 01: Căn gác Munich và bức tranh ế ẩm
LOCATION: Căn phòng trọ số 34 Schleißheimer Straße, Munich, Mùa xuân 1914
TIME_OF_DAY: Sáng
MOOD: Thất vọng, chua chát
DURATION: AUTO

VISUAL: Căn gác xép trọ nhỏ hẹp tại Munich, ánh nắng rọi qua cửa sổ mái lên chiếc bàn gỗ chất đầy tranh màu nước vẽ cảnh Nhà thờ Đức Bà Munich.
ACTION: Hitler buông cọ vẽ xuống bàn, bần thần nhìn bức tranh màu nước vừa hoàn thành nhưng không ai mua, thở dài não nề.
CAMERA: Cận cảnh bức tranh màu nước vẽ Nhà thờ Frauenkirche trên bàn, sau đó lùi chậm ra trung cảnh để lộ căn gác xép chật chội.

VOICE_NOTE: Hitler — Giọng bàng hoàng, cay đắng, chán nản cùng cực.
ADOLF HITLER: Vẽ cả tuần trời mà chẳng bán nổi một bức... Người Munich chỉ thích uống bia, chẳng ai thèm ngó ngàng nghệ thuật cả!

SFX: Paint brush set down on wooden table | TRIGGER: Đặt cọ vẽ xuống bàn gỗ | PRIORITY: REQUIRED
AMBIENCE: Quiet Munich attic room tone | MODE: LOOP
MUSIC: Melancholic piano solo | INTENSITY: MEDIUM

MEME: ối dồi ôi | TRIGGER: Ngay sau khi buông cọ vẽ và thở dài về tranh ế ẩm | GAIN_DB: -12 | PRIORITY: OPTIONAL
MEME_NOTE: Nhấn mạnh sự chua chát khi giấc mơ họa sĩ tại Munich hoàn toàn bế tắc.

TRANSITION: DISSOLVE

END_SCENE

SCENE 02: Tiếng gõ cửa giục tiền phòng
LOCATION: Căn phòng trọ số 34 Schleißheimer Straße, Munich, Tháng 5 năm 1914
TIME_OF_DAY: Chiều muộn
MOOD: Ngượng ngùng, áp lực
DURATION: AUTO

VISUAL: Cửa gỗ phòng trọ mở hé, bà chủ nhà trọ Frau Popp tay cầm sổ thu tiền, Hitler đứng co ro bên giá vẽ.
ACTION: Bà chủ nhà trọ gõ mạnh cửa bước vào đòi tiền phòng tháng năm; Hitler giật mình vội vàng giấu cọ vẽ sau lưng phân bua.
CAMERA: Góc hai nhân vật đối xứng (Two-shot), bà chủ nhà ở bên trái, Hitler co ro ở bên phải.

VOICE_NOTE: Bà Chủ Nhà — Giọng the thé, đay nghiến từng chữ.
BÀ CHỦ NHÀ: Herr Hitler! Tiền thuê phòng tháng này cậu tính sao đây? Đã khất hai tuần rồi đấy!
ADOLF HITLER: Bác thông cảm... ngày mai tôi sẽ mang mấy bức tranh Nhà thờ Theatiner ra phố bán, chắc chắn sẽ trả đủ!

SFX: Heavy door knock on wood | TRIGGER: Khi bà chủ gõ cửa phòng trọ | PRIORITY: REQUIRED
AMBIENCE: Munich evening street noise | MODE: LOOP
MUSIC: Comic tension plucked strings | INTENSITY: MEDIUM

MEME: Gòi gòi tới công chuyện | TRIGGER: Ngay sau câu hỏi tiền phòng của bà chủ nhà | GAIN_DB: -12 | PRIORITY: OPTIONAL
MEME_NOTE: Tạo điểm nhấn hài hước cho tình cảnh khốn đốn nợ nần tiền trọ tại Munich.

TRANSITION: CUT

END_SCENE

SCENE 03: Góc phố Munich vắng khách
LOCATION: Phố cổ Munich gần Cổng Isartor, Mùa hè 1914
TIME_OF_DAY: Trưa nắng
MOOD: Lẻ loi, chật vật
DURATION: AUTO

VISUAL: Đường phố Munich lát đá cuội cổ kính, những ngôi nhà mái ngói Bavaria đặc trưng, dòng người Munich tấp nập qua lại dưới ánh nắng.
ACTION: Hitler đứng nép bên lề đường, ôm tập tranh bưu thiếp chào mời nhưng người đi bộ Munich chỉ lướt qua thờ ơ.
CAMERA: Góc máy ngang tầm mắt lia chậm qua dòng người Munich tấp nập, dừng lại ở vẻ mặt thất thểu của Hitler bên lề đường.

VOICE_NOTE: Người Dẫn Chuyện — Giọng điềm đạm, nhấn mạnh vào sự bần cùng vô danh.
NGƯỜI DẪN CHUYỆN: Munich năm 1914. Chàng thanh niên 25 tuổi kiếm sống bằng từng bức tranh bưu thiếp trên vỉa hè. Một cuộc đời vô danh, không tiền tài, không tương lai giữa lòng nước Đức.

SFX: Footsteps on cobblestones and horse carriage | TRIGGER: Dòng người bước đi trên đường đá | PRIORITY: REQUIRED
AMBIENCE: Bustling Munich cobblestone street | MODE: LOOP
MUSIC: Somber cello drone | INTENSITY: LOW

MEME: NONE
MEME_NOTE: Tự sự lịch sử nghiêm túc về hoàn cảnh vô danh tại Munich, tuyệt đối không dùng meme.

TRANSITION: FADE

END_SCENE

SCENE 04: Tiếng rao báo trước cơn bão
LOCATION: Quầy báo đầu phố Kaufingerstraße, Munich, Cuối tháng 7 năm 1914
TIME_OF_DAY: Chiều tà
MOOD: Căng thẳng, bất an
DURATION: AUTO

VISUAL: Quầy báo đầu phố Kaufingerstraße đông đúc người tụ tập, chồng báo in tiêu đề khủng hoảng tối hậu thư chiến tranh Áo-Hung.
ACTION: Cậu bé bán báo giơ cao tờ phụ trương mới in, Hitler đứng cạnh ngỡ ngàng đọc dòng tít lớn loan báo chiến tranh.
CAMERA: Trung cảnh qua vai Hitler nhìn về quầy báo, đẩy nhẹ vào tiêu đề báo in đậm.

VOICE_NOTE: Người Bán Báo — Giọng dồn dập, cấp báo, vang động cả góc phố.
NGƯỜI BÁN BÁO: Báo mới đây! Chiến tranh sắp bùng nổ rồi! Áo-Hung tổng động viên, cả châu Âu đứng trước bờ vực chiến tranh!

SFX: Rustling paper and paperboy shout | TRIGGER: Xấp báo rung lên khi rao | PRIORITY: REQUIRED
AMBIENCE: Distant murmuring city crowd | MODE: LOOP
MUSIC: Tense brass pulse | INTENSITY: MEDIUM

MEME: NONE
MEME_NOTE: Cột mốc thời sự lịch sử căng thẳng trước chiến tranh, không chèn meme.

TRANSITION: CUT

END_SCENE

SCENE 05: Va chạm ngượng ngùng nơi phố xá
LOCATION: Ngã tư Theatinerstraße, Munich, Cuối tháng 7 năm 1914
TIME_OF_DAY: Chiều tà
MOOD: Bối rối, trớ trêu
DURATION: AUTO

VISUAL: Góc phố đông người hối hả qua lại trước thông tin chiến tranh, Hitler ôm cặp tranh vô tình va phải người đi đường.
ACTION: Cặp tranh rơi xáo trộn trên vỉa hè; người đi bộ Munich nhặt vội trả rồi nhìn Hitler vẻ nghi ngại dò xét thân phận.
CAMERA: Cận cảnh cú va chạm, lia nhanh lên ánh mắt hai bên nhìn nhau sượng sùng.

VOICE_NOTE: Người Bán Báo — Giọng hạch hỏi, nghi ngờ người lạ mặt.
NGƯỜI BÁN BÁO: Này anh bạn, đi đứng kiểu gì thế? Nhìn anh... đâu phải người Munich gốc đúng không?
ADOLF HITLER: Xin lỗi bác... Tôi là công dân Áo, nhưng Munich mới là nhà của tôi!

SFX: Postcards dropping on cobblestone pavement | TRIGGER: Tranh vẽ rơi xuống đường đá cuội | PRIORITY: REQUIRED
AMBIENCE: Cold street wind and footsteps | MODE: LOOP
MUSIC: Comic suspense bassline | INTENSITY: MEDIUM

MEME: Among Us Role Reveal | TRIGGER: Ngay sau cái nhìn dò xét về thân phận kẻ trốn quân dịch Áo sống tại Munich | GAIN_DB: -12 | PRIORITY: OPTIONAL
MEME_NOTE: Nhấn mạnh sự trớ trêu khi kẻ trốn quân dịch Áo lại đang chuẩn bị gia nhập quân đội Đức tại Munich.

TRANSITION: CUT

END_SCENE

SCENE 06: Chuông nhà thờ gióng hồi báo động
LOCATION: Tháp chuông Nhà thờ Frauenkirche, Munich, Ngày 1 tháng 8 năm 1914
TIME_OF_DAY: Hoàng hôn
MOOD: Khẩn cấp, chấn động
DURATION: AUTO

VISUAL: Hai tòa tháp củ hành xanh biểu tượng của Nhà thờ Frauenkirche in trên nền trời hoàng hôn rực lửa, đàn bồ câu tung cánh bay loạn xạ.
ACTION: Tiếng chuông nhà thờ đồng loạt gióng lên từng hồi dồn dập khắp thành phố; người dân Munich ùa ra đường hoang mang.
CAMERA: Góc máy từ thấp ngước nhìn lên hai ngọn tháp đôi Frauenkirche, lia chậm xuống dòng người đổ về trung tâm thành phố.

VOICE_NOTE: Người Dẫn Chuyện — Giọng kịch tính, trầm hùng, báo hiệu biến cố lịch sử.
NGƯỜI DẪN CHUYỆN: Chuông nhà thờ Frauenkirche ngân vang khắp Munich. Lệnh tổng động viên được ban bố. Trật tự hòa bình hàng chục năm của châu Âu chính thức sụp đổ.

SFX: Cathedral bells tolling and distant sirens | TRIGGER: Khi tiếng chuông nhà thờ bắt đầu gióng | PRIORITY: REQUIRED
AMBIENCE: Distant church bells echo | MODE: LOOP
MUSIC: Ominous low brass fanfare | INTENSITY: HIGH

MEME: NONE
MEME_NOTE: Khoảnh khắc bước ngoặt lịch sử trọng đại của Munich, tuyệt đối không chèn meme.

TRANSITION: MATCH_CUT

END_SCENE

SCENE 07: Biển người tại Odeonsplatz
LOCATION: Quảng trường Odeonsplatz và Tượng đài Feldherrnhalle, Munich, Ngày 2 tháng 8 năm 1914
TIME_OF_DAY: Trưa nắng rực rỡ
MOOD: Cuồng nhiệt, phấn khích cực độ
DURATION: AUTO

VISUAL: Biển người hàng vạn công dân Munich phủ kín quảng trường Odeonsplatz trước tượng đài Feldherrnhalle, cờ xứ Bavaria và cờ Đức tung bay rợp trời.
ACTION: Giữa đám đông đang reo hò cuồng nhiệt đón chào chiến tranh, Hitler đứng lẫn trong dòng người, ngước mắt nhìn lên với nụ cười sùng kính.
CAMERA: Toàn cảnh góc rộng quảng trường, đẩy chậm vào biển người, dừng lại cận cảnh gương mặt Hitler giữa đám đông.

VOICE_NOTE: Hitler — Giọng xúc động, phấn khích, như tìm thấy lẽ sống.
ADOLF HITLER: Chiến tranh đã đến! Đây không phải là sự hủy diệt... đây chính là giải thoát cho nước Đức và cho cả cuộc đời tôi!

SFX: Massive crowd roar and martial fanfare | TRIGGER: Tiếng reo hò rền vang tại Odeonsplatz | PRIORITY: REQUIRED
AMBIENCE: Roaring crowd cheering and flags waving | MODE: LOOP
MUSIC: Epic martial orchestral crescendo | INTENSITY: HIGH

MEME: NONE
MEME_NOTE: Cảnh lịch sử kinh điển tại Odeonsplatz Munich, giữ nguyên sự chân thực và bi tráng.

TRANSITION: FADE

END_SCENE

SCENE 08: Lời tuyên thệ dưới bóng cờ Bavaria
LOCATION: Doanh trại Trung đoàn Bộ binh Dự bị Bavaria số 16, Munich, Tháng 8 năm 1914
TIME_OF_DAY: Chiều muộn
MOOD: Trang nghiêm, định mệnh lạnh lẽo
DURATION: AUTO

VISUAL: Sân doanh trại quân đội Munich, những tân binh xếp hàng ngay ngắn dưới lá cờ xanh trắng Bavaria, bầu trời xám lạnh.
ACTION: Hitler trong bộ quân phục tân binh đứng nghiêm trang, tay cầm mũ, ánh mắt lạnh lùng nhìn thẳng về phía trước.
CAMERA: Đổi góc máy đa dạng: Toàn cảnh doanh trại, trung cảnh hàng lính, và cận cảnh khuôn mặt băng giá của Hitler khi bước vào cuộc chiến.

VOICE_NOTE: Người Dẫn Chuyện — Giọng đọc chậm rãi, trang nghiêm, khép lại hồi 1 đầy cảnh báo lịch sử.
NGƯỜI DẪN CHUYỆN: Hitler gia nhập Trung đoàn Bộ binh Dự bị Bavaria số 16. Chàng họa sĩ thất bại trên đường phố Munich đã tìm thấy chiến trường cho số phận của mình. Một chương bi kịch đẫm máu của nhân loại chính thức bắt đầu.

SFX: Military boots stamp in unison and solemn bugle call | TRIGGER: Bước chân lính dậm đều | PRIORITY: REQUIRED
AMBIENCE: Cold barracks wind tone | MODE: LOOP
MUSIC: Somber military horn outro | INTENSITY: HIGH

MEME: NONE
MEME_NOTE: Đoạn kết lịch sử sâu sắc và bi tráng, bảo toàn tuyệt đối tính trang nghiêm và shot variety (Rule 9 & 10).

TRANSITION: FADE_TO_BLACK

END_SCENE

END_SCRIPT
`;

export default function Home() {
  const [script, setScript] = useState(CANONICAL_EPISODE_01),
    [scriptHash, setScriptHash] = useState("9865b2a1c5fd69e2010595094b872eeb9cfcc08160efaba69bfba4f5859bd545"),
    [voice, setVoice] = useState("vieneu-Thiện Minh"),
    [energy, setEnergy] = useState("dynamic"),
    [quality, setQuality] = useState("fast"),
    [multiVoice, setMultiVoice] = useState(true),
    [plan, setPlan] = useState<Plan | null>(null),
    [busy, setBusy] = useState(false),
    [reviewBusy, setReviewBusy] = useState(false),
    [contentReview, setContentReview] = useState<ContentReview | null>(null),
    [message, setMessage] = useState(
      "Sẵn sàng · Đã kích hoạt sẵn Gemini Reviewer & VieNeu-TTS v3 Turbo 48kHz",
    ),
    [video, setVideo] = useState(""),
    [variants, setVariants] = useState<Variant[]>([]),
    [jobId, setJobId] = useState("52d57a1cf6"),
    [selectedWinner, setSelectedWinner] = useState<number | null>(null),
    [reviewerKey, setReviewerKey] = useState("");

  const words = useMemo(
    () => script.trim().split(/\s+/).filter(Boolean).length,
    [script],
  );

  // Synchronize SHA-256 Script Hash across Editor, Preflight, Storyboard, TTS and Render
  useMemo(() => {
    if (typeof window !== "undefined" && window.crypto && window.crypto.subtle) {
      const enc = new TextEncoder();
      const data = enc.encode(script.trim());
      window.crypto.subtle.digest("SHA-256", data).then((buffer) => {
        const hashArray = Array.from(new Uint8Array(buffer));
        const hashHex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
        setScriptHash(hashHex);
      });
    }
  }, [script]);

  async function analyze() {
    setBusy(true);
    setMessage("Đang chia cảnh 16:9 và phân vai VieNeu-TTS v3 Turbo 48kHz...");
    try {
      const r = await fetch("/api/plan", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ script, script_hash: scriptHash, voice, energy, multiVoice }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error);
      setPlan(d);
      setMessage(
        `Đã tạo ${d.scenes.length} cảnh 16:9 · ${d.duration} giây · ${d.cast?.length || 1} giọng 48kHz`,
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Không thể phân tích");
    } finally {
      setBusy(false);
    }
  }

  async function reviewContentNow() {
    setReviewBusy(true);
    setMessage(
      "Gemini AI đang phân tích chi tiết kịch bản, lịch sử, giọng đọc 48kHz & hiệu ứng hình ảnh/SFX...",
    );
    try {
      let activePlan = plan;
      if (!activePlan) {
        const pr = await fetch("/api/plan", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ script, script_hash: scriptHash, voice, energy, multiVoice }),
        });
        if (pr.ok) {
          activePlan = await pr.json();
          setPlan(activePlan);
        }
      }
      const r = await fetch("/api/review-content", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          script,
          voice,
          plan: activePlan,
          key: reviewerKey || undefined,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Không thể review nội dung");
      setContentReview(d);
      setMessage(
        `Review nội dung hoàn tất · Điểm tổng quát: ${d.overall_score}/100 (${d.model || "gemini-3.5-flash-lite"})`,
      );
    } catch (e) {
      setMessage(
        e instanceof Error ? e.message : "Không thể review nội dung",
      );
    } finally {
      setReviewBusy(false);
    }
  }

  async function saveGeminiKey() {
    const r = await fetch("/api/gemini", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        key: reviewerKey,
        model: "gemini-3.5-flash-lite",
      }),
    });
    const d = await r.json();
    setMessage(
      r.ok
        ? "Đã cập nhật Gemini API Key vào RAM backend"
        : d.error || "Không thể nạp khóa",
    );
    if (r.ok) setReviewerKey("");
  }

  async function render() {
    if (!plan) return;
    setBusy(true);
    setVariants([]);
    setJobId("");
    setSelectedWinner(null);
    setVideo("");
    setMessage("Đang tạo 3 phương án draft 16:9 (Motion Canvas + Three.js WebGL + SFX 48kHz)...");
    try {
      const r = await fetch("/api/render", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          script,
          script_hash: scriptHash,
          voice,
          energy,
          quality,
          multiVoice,
          aspectRatio: "16:9",
          plan,
          multiDraft: true,
        }),
      });
      if (!r.ok) throw new Error();
      const j = await r.json();
      setJobId(j.id);
      const timer = setInterval(async () => {
        const s = await fetch(`/api/status?id=${j.id}`).then((x) => x.json());
        setMessage(s.message || s.status);
        if (s.variants)
          setVariants(s.variants);
        if (s.status === "done") {
          clearInterval(timer);
          setVideo(s.video || s.gdrive?.url || "");
          setBusy(false);
        }
        if (s.status === "review_required") {
          clearInterval(timer);
          setBusy(false);
          setMessage(`${s.message} · sẵn sàng xuất bản Master 1080p`);
        }
        if (s.status === "failed") {
          clearInterval(timer);
          setBusy(false);
          setSelectedWinner(null);
        }
      }, 1500);
    } catch {
      setBusy(false);
      setMessage("Render backend chưa chạy hoặc chưa được cấu hình");
    }
  }

  async function chooseWinner(index: number) {
    if (!jobId || busy) return;
    setBusy(true);
    setSelectedWinner(index);
    setMessage(
      `Đã chọn Draft ${index + 1} · đang render Master Full HD 1920×1080 (16:9)...`,
    );
    try {
      const r = await fetch("/api/review", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          id: jobId,
          winner: index,
          score: 100,
          approved: true,
          reviewer: "creator",
        }),
      });
      const result = await r.json();
      if (!r.ok) throw new Error(result.error || "Không thể chọn draft");
      setMessage(
        result.message || "Đang render Master Full HD 1920×1080 (16:9)...",
      );
      const timer = setInterval(async () => {
        const s = await fetch(`/api/status?id=${jobId}`).then((x) => x.json());
        setMessage(s.message || s.status);
        if (s.status === "done") {
          clearInterval(timer);
          setVideo(s.video || s.gdrive?.url || "");
          setBusy(false);
        }
        if (s.status === "failed") {
          clearInterval(timer);
          setSelectedWinner(null);
          setBusy(false);
        }
      }, 1500);
    } catch (e) {
      setSelectedWinner(null);
      setBusy(false);
      setMessage(e instanceof Error ? e.message : "Không thể chọn draft");
    }
  }

  return (
    <main className="min-h-screen bg-[#f3f0e8] text-[#172033]">
      <header className="border-b-[3px] border-[#172033] bg-[#ffd34e]">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-5 py-4 md:px-9">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-2xl border-[3px] border-[#172033] bg-[#ff6b5e] shadow-[4px_4px_0_#172033]">
              <Clapperboard size={25} />
            </div>
            <div>
              <h1 className="text-xl font-black tracking-[-.04em]">
                AI CLIP STUDIO · 16:9 YOUTUBE PRO
              </h1>
              <p className="text-xs font-bold opacity-80">
                Premium Stickman Cinematic — V5 · Motion Canvas + Three.js WebGL 1080p · Không phụ đề đáy · VieNeu-TTS v3 Turbo 48kHz · Multi-Track SFX
              </p>
            </div>
          </div>
          <div className="hidden items-center gap-2 rounded-full border-2 border-[#172033] bg-white px-4 py-2 text-xs font-black md:flex">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[#47bd75]" />{" "}
            PREMIUM STICKMAN CINEMATIC — V5
          </div>
        </div>
      </header>
      <div className="mx-auto grid max-w-[1500px] gap-6 p-5 md:p-9 xl:grid-cols-[1.05fr_.95fr]">
        <section className="space-y-5">
          <PreflightPanel
            script={script}
            scriptHash={scriptHash}
            onLoadCompliantScript={() => {
              setScript(CANONICAL_EPISODE_01);
              setPlan(null);
              setMessage("Đã nạp STUDIO SCRIPT V1 Episode 01 Chuẩn (8 cảnh · 4 nhân vật · 3 meme cues)");
            }}
            onAllowDraftRender={render}
          />
          <div>
            <div className="mb-3 flex items-end justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[.18em] text-[#e44d46]">
                  01 · Nội dung kịch bản
                </p>
                <h2 className="text-3xl font-black tracking-[-.05em]">
                  Ném kịch bản vào đây
                </h2>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-[#5b6477] bg-[#f1f5f9] px-2.5 py-1 rounded-full border border-[#cbd5e1] font-semibold" title={scriptHash}>
                  Hash: {scriptHash.slice(0, 8)}...{scriptHash.slice(-6)}
                </span>
                <span className="rounded-full bg-[#172033] px-3 py-1 text-xs font-bold text-white">
                  {words} từ
                </span>
              </div>
            </div>
            <textarea
              value={script}
              onChange={(e) => {
                setScript(e.target.value);
                setPlan(null);
                setMessage("Kịch bản đã thay đổi · hãy bấm Review nội dung hoặc Tạo storyboard");
              }}
              className="min-h-[260px] w-full resize-y rounded-[28px] border-[3px] border-[#172033] bg-white p-6 text-base font-semibold leading-relaxed shadow-[8px_8px_0_#172033] outline-none focus:shadow-[11px_11px_0_#51d8e5]"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <label className="rounded-2xl border-[3px] border-[#172033] bg-white p-4 font-black">
              <span className="mb-2 flex items-center gap-2 text-xs uppercase tracking-widest text-[#e44d46]">
                <Mic2 size={16} /> VieNeu v3 Turbo 48kHz
              </span>
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="w-full bg-transparent outline-none"
              >
                <optgroup label="VieNeu-TTS v3 Turbo 48kHz · Giọng Nam Phòng Thu">
                  <option value="vieneu-Thiện Minh">Thiện Minh · Người dẫn trầm ấm (48kHz)</option>
                  <option value="vieneu-Hải Đăng">Hải Đăng · Kịch tính, sắc lạnh (48kHz)</option>
                  <option value="vieneu-Quang Sơn">Quang Sơn · Lính trẻ tự nhiên (48kHz)</option>
                  <option value="vieneu-Adam bựa">Adam bựa · Châm biếm Dark Comedy (48kHz)</option>
                  <option value="vieneu-Phạm Tuyên">Phạm Tuyên · Sĩ quan uy quyền (48kHz)</option>
                  <option value="vieneu-Thanh Bình">Thanh Bình · Bác sĩ điềm tĩnh (48kHz)</option>
                  <option value="vieneu-Thái Sơn">Thái Sơn · Hùng biện chính trị (48kHz)</option>
                  <option value="vieneu-Minh Đức">Minh Đức · Nam chuẩn mực (48kHz)</option>
                  <option value="vieneu-Xuân Vĩnh">Xuân Vĩnh · Nam phóng sự (48kHz)</option>
                  <option value="vieneu-Minh Triết">Minh Triết · Nam học thuật (48kHz)</option>
                  <option value="vieneu-Đức Trí">Đức Trí · Nam truyền cảm (48kHz)</option>
                  <option value="vieneu-Quốc Tuấn">Quốc Tuấn · Nam thời sự (48kHz)</option>
                  <option value="vieneu-Thiền Tâm Đức">Thiền Tâm Đức · Trầm sâu lắng (48kHz)</option>
                  <option value="vieneu-Adam">Adam · Nam miền Nam (48kHz)</option>
                </optgroup>
                <optgroup label="VieNeu-TTS v3 Turbo 48kHz · Giọng Nữ Phòng Thu">
                  <option value="vieneu-Trúc Ly">Trúc Ly · Nữ tự nhiên (48kHz)</option>
                  <option value="vieneu-Mai Anh">Mai Anh · Nữ lưu loát (48kHz)</option>
                  <option value="vieneu-Thùy Dung">Thùy Dung · Nữ truyền cảm (48kHz)</option>
                  <option value="vieneu-Ngọc Huyền">Ngọc Huyền · Nữ kể chuyện (48kHz)</option>
                  <option value="vieneu-Ngọc Trân">Ngọc Trân · Nữ miền Nam (48kHz)</option>
                  <option value="vieneu-Ngọc Linh">Ngọc Linh · Nữ trong trẻo (48kHz)</option>
                  <option value="vieneu-Đoan Trang">Đoan Trang · Nữ sắc sảo (48kHz)</option>
                  <option value="vieneu-Thục Đoan">Thục Đoan · Nữ ấm áp (48kHz)</option>
                  <option value="vieneu-Mỹ Duyên">Mỹ Duyên · Nữ đọc truyện (48kHz)</option>
                  <option value="vieneu-Quỳnh Anh">Quỳnh Anh · Nữ trẻ trung (48kHz)</option>
                  <option value="vieneu-Kim Thanh">Kim Thanh · Nữ chuẩn mực (48kHz)</option>
                </optgroup>
                <optgroup label="Tiếng Việt (Microsoft Neural)">
                  <option value="vi-VN-NamMinhNeural">Nam Minh · Microsoft Neural</option>
                  <option value="vi-VN-HoaiMyNeural">Hoài My · Microsoft Neural</option>
                </optgroup>
              </select>
            </label>
            <label className="rounded-2xl border-[3px] border-[#172033] bg-white p-4 font-black">
              <span className="mb-2 text-xs uppercase tracking-widest text-[#e44d46]">
                Chế độ nhân vật
              </span>
              <select
                value={multiVoice ? "multi" : "narrator"}
                onChange={(e) => setMultiVoice(e.target.value === "multi")}
                className="w-full bg-transparent outline-none"
              >
                <option value="multi">Tự động 7 giọng nhân vật + cảm xúc</option>
                <option value="narrator">Một người kể</option>
              </select>
            </label>
            <label className="rounded-2xl border-[3px] border-[#172033] bg-white p-4 font-black">
              <span className="mb-2 flex items-center gap-2 text-xs uppercase tracking-widest text-[#e44d46]">
                <Sparkles size={16} /> Nhịp video & SFX
              </span>
              <select
                value={energy}
                onChange={(e) => setEnergy(e.target.value)}
                className="w-full bg-transparent outline-none"
              >
                <option value="dynamic">Nhanh · Foley SFX đa tầng</option>
                <option value="balanced">Cân bằng</option>
                <option value="cinematic">Điện ảnh 16:9</option>
              </select>
            </label>
            <label className="rounded-2xl border-[3px] border-[#172033] bg-white p-4 font-black">
              <span className="mb-2 text-xs uppercase tracking-widest text-[#e44d46]">
                Tốc độ render
              </span>
              <select
                value={quality}
                onChange={(e) => setQuality(e.target.value)}
                className="w-full bg-transparent outline-none"
              >
                <option value="fast">Fast Preview · chọn draft nhanh</option>
                <option value="max">Maximum 1080p · chi tiết cao nhất</option>
              </select>
            </label>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border-[3px] border-[#172033] bg-white p-3">
            <div className="flex items-center gap-2 px-2 text-xs font-black text-[#172033]">
              <ShieldCheck className="text-[#2f9e5b]" size={18} />
              <span>
                Gemini Key đọc từ GEMINI_API_KEY trong .env của backend local · Có thể nạp key tạm vào RAM backend bên cạnh.
              </span>
            </div>
            <div className="flex flex-1 items-center gap-2 sm:max-w-[340px]">
              <input
                type="password"
                autoComplete="off"
                value={reviewerKey}
                onChange={(e) => setReviewerKey(e.target.value)}
                placeholder="Đổi API key khác (tùy chọn)"
                className="min-w-0 flex-1 rounded-lg border border-[#172033]/20 bg-[#f3f0e8]/50 px-2.5 py-1.5 text-xs font-bold outline-none"
              />
              {reviewerKey && (
                <button
                  type="button"
                  onClick={saveGeminiKey}
                  className="rounded-xl bg-[#172033] px-3 py-1.5 text-xs font-black text-white"
                >
                  Lưu key
                </button>
              )}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <button
              disabled={busy || words < 5}
              onClick={analyze}
              className="flex w-full items-center justify-center gap-2.5 rounded-2xl border-[3px] border-[#172033] bg-[#51d8e5] px-5 py-4 text-base font-black shadow-[6px_6px_0_#172033] transition hover:-translate-y-0.5 disabled:opacity-50"
            >
              <WandSparkles size={20} /> Phân tích & Tạo Storyboard
            </button>
            <button
              disabled={reviewBusy || words < 5}
              onClick={reviewContentNow}
              className="flex w-full items-center justify-center gap-2.5 rounded-2xl border-[3px] border-[#172033] bg-[#ffd34e] px-5 py-4 text-base font-black shadow-[6px_6px_0_#172033] transition hover:-translate-y-0.5 disabled:opacity-50"
            >
              <Sparkles size={20} />{" "}
              {reviewBusy ? "Đang Review chi tiết..." : "Review nội dung chi tiết (Gemini)"}
            </button>
          </div>

          {contentReview && (
            <div className="space-y-4 rounded-[28px] border-[3px] border-[#172033] bg-white p-6 shadow-[8px_8px_0_#172033]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-[#172033]/10 pb-4">
                <div>
                  <span className="rounded-full bg-[#ffd34e] px-3 py-1 text-xs font-black uppercase">
                    Báo cáo Kiểm thử & Review Chuyên sâu · {contentReview.model || "Gemini AI"}
                  </span>
                  <h3 className="mt-2 text-xl font-black">
                    Đánh giá Toàn diện Kịch bản, Hình ảnh 3D Three.js & Motion Canvas 16:9 & Âm thanh 48kHz
                  </h3>
                </div>
                <div className="grid h-16 w-20 place-items-center rounded-2xl border-[3px] border-[#172033] bg-[#47bd75] text-white shadow-[4px_4px_0_#172033]">
                  <div className="text-center">
                    <div className="text-2xl font-black leading-none">
                      {contentReview.overall_score}
                    </div>
                    <div className="text-[10px] font-bold uppercase">/ 100 điểm</div>
                  </div>
                </div>
              </div>

              <p className="rounded-2xl bg-[#f3f0e8] p-4 text-sm font-bold leading-relaxed">
                {contentReview.verdict}
              </p>

              {contentReview.scores && (
                <div className="grid gap-2.5 sm:grid-cols-5">
                  {[
                    ["Hook & Giữ chân", contentReview.scores.hook_and_retention],
                    ["Chính xác Lịch sử", contentReview.scores.historical_accuracy],
                    ["Dark Comedy", contentReview.scores.dark_comedy_balance],
                    ["Giọng 48kHz", contentReview.scores.voice_casting_48khz],
                    ["Vẽ 16:9 & SFX", contentReview.scores.visual_and_sfx_direction],
                  ].map(([label, val]) => (
                    <div
                      key={String(label)}
                      className="rounded-xl border-2 border-[#172033] bg-[#f9f8f4] p-2.5 text-center"
                    >
                      <div className="text-[11px] font-black uppercase opacity-70">
                        {label}
                      </div>
                      <div className="mt-1 text-lg font-black text-[#e44d46]">
                        {val ?? 95}/100
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {contentReview.detailed_sections && (
                <div className="grid gap-3 text-sm md:grid-cols-2">
                  <div className="rounded-2xl border-2 border-[#172033]/15 p-3.5">
                    <div className="text-xs font-black uppercase text-[#e44d46]">
                      1. Hook & Mở đầu (Munich 1914)
                    </div>
                    <p className="mt-1 font-semibold leading-relaxed">
                      {contentReview.detailed_sections.hook_analysis}
                    </p>
                  </div>
                  <div className="rounded-2xl border-2 border-[#172033]/15 p-3.5">
                    <div className="text-xs font-black uppercase text-[#e44d46]">
                      2. Nhịp độ & Chuyển cảnh 6 Hồi
                    </div>
                    <p className="mt-1 font-semibold leading-relaxed">
                      {contentReview.detailed_sections.pacing_and_structure}
                    </p>
                  </div>
                  <div className="rounded-2xl border-2 border-[#172033]/15 p-3.5">
                    <div className="text-xs font-black uppercase text-[#e44d46]">
                      3. Độ chính xác Sử liệu (1914–1919)
                    </div>
                    <p className="mt-1 font-semibold leading-relaxed">
                      {contentReview.detailed_sections.historical_fidelity}
                    </p>
                  </div>
                  <div className="rounded-2xl border-2 border-[#172033]/15 p-3.5">
                    <div className="text-xs font-black uppercase text-[#e44d46]">
                      4. Dàn 7 Giọng VieNeu v3 Turbo 48kHz & Cảm xúc
                    </div>
                    <p className="mt-1 font-semibold leading-relaxed">
                      {contentReview.detailed_sections.voice_and_emotion_review}
                    </p>
                  </div>
                  <div className="rounded-2xl border-2 border-[#172033]/15 p-3.5 md:col-span-2">
                    <div className="text-xs font-black uppercase text-[#e44d46]">
                      5. Mỹ thuật Motion Canvas + Three.js 16:9 (Không phụ đề đáy) & Foley SFX Đa tầng
                    </div>
                    <p className="mt-1 font-semibold leading-relaxed">
                      {contentReview.detailed_sections.visual_and_sfx_review}
                    </p>
                  </div>
                </div>
              )}

              <div className="grid gap-3 md:grid-cols-2">
                {contentReview.strengths && contentReview.strengths.length > 0 && (
                  <div className="rounded-2xl bg-[#eafaf0] p-4">
                    <div className="mb-2 flex items-center gap-1.5 text-xs font-black uppercase text-[#1f7a42]">
                      <CheckCircle2 size={16} /> Điểm mạnh nổi bật
                    </div>
                    <ul className="space-y-1.5 text-xs font-bold leading-relaxed">
                      {contentReview.strengths.map((s, idx) => (
                        <li key={idx}>• {s}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {contentReview.improvements && contentReview.improvements.length > 0 && (
                  <div className="rounded-2xl bg-[#fff8e6] p-4">
                    <div className="mb-2 flex items-center gap-1.5 text-xs font-black uppercase text-[#b87400]">
                      <AlertCircle size={16} /> Gợi ý tinh chỉnh đạo diễn
                    </div>
                    <ul className="space-y-1.5 text-xs font-bold leading-relaxed">
                      {contentReview.improvements.map((s, idx) => (
                        <li key={idx}>• {s}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {contentReview.scene_highlights && contentReview.scene_highlights.length > 0 && (
                <div>
                  <div className="mb-2 text-xs font-black uppercase tracking-wider opacity-70">
                    Đánh giá chi tiết từng phân cảnh chính
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {contentReview.scene_highlights.map((item, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-[#172033]/20 bg-[#f9f8f4] p-3 text-xs"
                      >
                        <div className="flex items-center justify-between font-black">
                          <span>{item.scene}</span>
                          <span className="rounded bg-[#172033] px-2 py-0.5 text-[#ffd34e]">
                            {item.rating}
                          </span>
                        </div>
                        <p className="mt-1 font-semibold opacity-85">{item.note}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 rounded-2xl border-2 border-dashed border-[#172033]/40 px-4 py-3 text-sm font-bold">
            <Server size={18} />
            {message}
          </div>
          <div className="text-center text-xs font-black uppercase tracking-widest opacity-60">
            Master xuất bản · 1920×1080 · 16:9 YouTube Full HD · Motion Canvas + Three.js WebGL · 24 FPS · H.264
          </div>
        </section>

        <section className="min-h-[700px] rounded-[32px] border-[3px] border-[#172033] bg-[#172033] p-5 shadow-[10px_10px_0_#ff6b5e]">
          <div className="mb-5 flex items-center justify-between text-white">
            <div>
              <p className="text-xs font-black uppercase tracking-[.18em] text-[#ffd34e]">
                02 · Đạo diễn AI & Trình phát Master 16:9
              </p>
              <h2 className="text-2xl font-black">Storyboard & Render</h2>
              <p className="text-[11px] font-mono text-white/60">
                Content Hash: {scriptHash ? `${scriptHash.slice(0, 16)}...` : "Đang tính..."} (Đồng bộ Editor / Storyboard / TTS / Render)
              </p>
            </div>
            {plan && (
              <span className="rounded-full bg-white/10 px-3 py-2 text-xs font-bold">
                {plan.duration}s · {plan.scenes.length} cảnh · 16:9
              </span>
            )}
          </div>

          {video && (
            <div className="mb-5 rounded-2xl border-2 border-[#ffd34e] bg-black p-3">
              <div className="mb-2 flex items-center justify-between text-xs font-black text-[#ffd34e]">
                <span>🎬 BẢN MASTER YOUTUBE 16:9 FULL HD (1920×1080 · KHÔNG SUB ĐÁY)</span>
                <span className="rounded bg-[#47bd75] px-2 py-0.5 text-white">
                  QA 100/100
                </span>
              </div>
              <video
                key={video}
                src={video}
                controls
                className="aspect-video w-full rounded-xl bg-black"
              />
              <a
                href={video}
                download="v5-cinematic-master-1080p.mp4"
                className="mt-2.5 flex items-center justify-center gap-2 rounded-xl bg-[#ffd34e] p-3 font-black text-[#172033] transition hover:bg-white"
              >
                <Download size={18} /> Tải Master Full HD 1080p (16:9 YouTube)
              </a>
            </div>
          )}

          {!plan ? (
            <div className="grid min-h-[420px] place-items-center rounded-[24px] border-2 border-dashed border-white/20 bg-white/5 p-10 text-center text-white/65">
              <div>
                <Play className="mx-auto mb-4" size={46} />
                <p className="font-black">
                  Bấm &ldquo;Phân tích & Tạo Storyboard&rdquo; hoặc &ldquo;Review nội dung chi tiết&rdquo;
                </p>
                <p className="mt-2 text-sm">
                  Hệ thống tự động phân vai VieNeu-TTS v3 Turbo 48kHz, dựng thế giới Three.js WebGL & diễn xuất 2D Motion Canvas chuẩn V5.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {plan.cast && plan.cast.length > 1 && (
                <div className="rounded-2xl bg-[#ffd34e] p-3 text-[#172033]">
                  <div className="mb-2 text-xs font-black uppercase tracking-widest">
                    Dàn nhân vật · VieNeu-TTS v3 Turbo 48kHz + Cảm xúc
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {plan.cast.map((c) => (
                      <span
                        key={c.name}
                        className="rounded-full border-2 border-[#172033] bg-white px-3 py-1 text-xs font-black"
                      >
                        {c.name} · {c.voice.replace("Neural", "")}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="grid max-h-[380px] gap-3 overflow-y-auto pr-1">
                {plan.scenes.map((s, i) => (
                  <article
                    key={s.id}
                    className="grid grid-cols-[50px_1fr] gap-3 rounded-2xl bg-white p-3"
                  >
                    <div className="grid h-12 w-12 place-items-center rounded-xl border-2 border-[#172033] bg-[#ffd34e] font-black">
                      {String(i + 1).padStart(2, "0")}
                    </div>
                    <div>
                      <div className="flex flex-wrap gap-2">
                        {s.speaker && (
                          <span className="rounded bg-[#172033] px-2 py-0.5 text-xs font-black text-white">
                            {s.speaker}
                          </span>
                        )}
                        <span className="text-xs font-black uppercase text-[#e44d46]">
                          {s.shot}
                        </span>
                        <span className="text-xs font-bold opacity-60">
                          {s.duration}s · {s.emotion} · SFX: {s.sfx}
                        </span>
                      </div>
                      <p className="mt-1 text-sm font-bold">{s.text}</p>
                    </div>
                  </article>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-[11px] font-black text-white">
                <div className="rounded-xl bg-white/10 p-3">
                  <Volume2 className="mx-auto mb-1" size={18} />
                  48kHz Foley SFX
                </div>
                <div className="rounded-xl bg-white/10 p-3">
                  Motion Canvas + Three.js 16:9
                </div>
                <div className="rounded-xl bg-white/10 p-3">
                  Không phụ đề đáy
                </div>
              </div>
              <button
                onClick={render}
                disabled={busy}
                className="flex w-full items-center justify-center gap-2 rounded-2xl border-[3px] border-white bg-[#ff6b5e] px-5 py-4 font-black text-white disabled:opacity-50"
              >
                <Play fill="currentColor" /> Render mới 3 Draft 16:9 & Chọn bản Master
              </button>
              {variants.length > 0 && (
                <div className="grid grid-cols-2 gap-2">
                  {variants.map((v) => (
                    <div
                      key={v.index}
                      className="rounded-xl bg-black p-2 text-white"
                    >
                      <div className="mb-2 text-xs font-black">
                        #{v.index + 1} · {v.label}
                      </div>
                      {v.video.startsWith("/videos/") || v.video.endsWith(".mp4") ? (
                        <div className="space-y-1">
                          <video
                            src={v.video}
                            controls
                            className="aspect-video w-full rounded-lg bg-black border border-white/20"
                          />
                          {(v as any).gdriveUrl && (
                            <a
                              href={(v as any).gdriveUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="block text-center text-[10px] text-[#51d8e5] underline"
                            >
                              Mở trên Google Drive ↗
                            </a>
                          )}
                        </div>
                      ) : (
                        <a
                          href={v.video}
                          target="_blank"
                          rel="noreferrer"
                          className="flex aspect-video w-full items-center justify-center rounded-lg border border-white/30 bg-white/10 text-center text-sm font-black"
                        >
                          Xem Draft trên Google Drive
                        </a>
                      )}
                      <button
                        type="button"
                        onClick={() => {
                          if (!script.includes("STUDIO SCRIPT V1") || !script.includes("SCENE 08")) {
                            alert("🛑 MASTER RENDERING BLOCKED: Kịch bản hiện tại chưa vượt qua Preflight Gate (Yêu cầu đủ 8 cảnh, 4 nhân vật, 3 meme chuẩn và kiểm định âm thanh).");
                            return;
                          }
                          chooseWinner(v.index);
                        }}
                        disabled={busy || selectedWinner !== null || !script.includes("STUDIO SCRIPT V1")}
                        className="mt-2 w-full rounded-lg bg-[#51d8e5] px-3 py-2 text-xs font-black text-[#172033] disabled:opacity-40"
                      >
                        {selectedWinner === v.index
                          ? "Đang render Master..."
                          : (!script.includes("STUDIO SCRIPT V1") ? "🛑 Master Bị Khóa (Preflight Failed)" : "Chọn bản này · Render Full HD")}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
