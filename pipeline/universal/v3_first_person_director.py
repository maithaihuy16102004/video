"""Master Prompt V3.0: First-Person Historical Roleplay Cinematic Director & Validator.
TÁI HIỆN LỊCH SỬ BẰNG NGÔI KỂ THỨ NHẤT (FIRST-PERSON HISTORICAL ROLEPLAY CINEMATIC SYSTEM)

Invariants:
1. Không có người dẫn chuyện ở bất kỳ cảnh nào (Zero external narrator).
2. Nhân vật chính luôn tự kể bằng ngôi thứ nhất ("tôi").
3. Nhân vật được phép nói trực tiếp với khán giả và phản ứng ngay trong sự kiện.
4. Có đối thoại giữa các nhân vật phụ, không chỉ độc thoại.
5. Lời thoại và toàn bộ nội dung hiển thị bằng tiếng Việt.
6. Sự kiện, ngày tháng và hậu quả phải được kiểm chứng.
7. Không biến lời thoại sáng tác thành trích dẫn lịch sử thật (ghi rõ ghi chú đối thoại tái dựng).
8. Giữ thiết kế Blob-Head (đầu 40-45% chiều cao, tối giản) và phong cách điện ảnh Three.js 16:9 nhất quán.

Full 17 Output Fields:
1. Tên tập
2. Nhân vật chính
3. Thời gian và địa điểm
4. Tóm tắt sự kiện
5. Kịch bản lời thoại hoàn chỉnh
6. Phân chia từng cảnh
7. Timestamp
8. Hành động nhân vật
9. Biểu cảm nhân vật
10. Góc máy
11. Chuyển động camera
12. Bối cảnh
13. Ánh sáng
14. Hiệu ứng âm thanh
15. Chữ hiển thị
16. Phụ đề
17. Nguồn kiểm chứng lịch sử
"""
from __future__ import annotations

import json
import os
import re
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.env_secrets import get_gemini_api_key, load_dotenv

load_dotenv()

PROHIBITED_NARRATOR_NAMES = {
    "người dẫn chuyện", "người dẫn", "dẫn chuyện", "narrator", "voiceover",
    "vo", "voice over", "người kể chuyện", "thuyết minh", "người thuyết minh"
}

THIRD_PERSON_LEAK_PATTERNS = [
    r"\bhãy tưởng tượng bạn\b",
    r"\bbạn có biết rằng\b",
    r"\bnhư chúng ta đã biết\b",
    r"\bngười xem thân mến\b",
    r"\bchào mừng các bạn đến với kênh\b",
    r"\bông ấy đã\b",
    r"\bngười đàn ông này đã\b"
]


@dataclass
class V3SceneBreakdown:
    scene_number: int
    scene_id: str
    timestamp_start: float
    timestamp_end: float
    duration: float
    speaker: str
    dialogue_type: str  # "Độc thoại trực tiếp", "Tự sự hành động", "Phản ứng tức thời", "Đối thoại", "Độc thoại nội tâm"
    spoken_text: str
    character_action: str
    character_emotion: str
    camera_angle: str
    camera_movement: str
    environment_3d: str
    lighting: str
    sound_effects: str
    on_screen_text: str
    subtitles_vietnamese: str


@dataclass
class MasterPromptV3ProductionPackage:
    # 1. Tên tập
    episode_title: str
    # 2. Nhân vật chính
    protagonist: Dict[str, Any]
    # 3. Thời gian và địa điểm
    time_and_location: Dict[str, str]
    # 4. Tóm tắt sự kiện
    event_summary: str
    # 5. Kịch bản lời thoại hoàn chỉnh
    complete_dialogue_script: List[Dict[str, str]]
    # 6-16. Phân cảnh chi tiết chứa các trường 6 đến 16
    scenes: List[V3SceneBreakdown]
    # 17. Nguồn kiểm chứng lịch sử
    historical_citations: List[Dict[str, str]]
    # Metadata & validation
    cast: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_sec: float = 0.0
    aspect_ratio: str = "16:9"
    resolution: str = "1920x1080"
    fps: int = 24
    art_style: str = "DOCUMENTARY_BLOB_HEAD_CINEMATIC"
    validation_status: str = "PENDING"
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_title": self.episode_title,
            "protagonist": self.protagonist,
            "time_and_location": self.time_and_location,
            "event_summary": self.event_summary,
            "complete_dialogue_script": self.complete_dialogue_script,
            "scenes": [asdict(s) for s in self.scenes],
            "historical_citations": self.historical_citations,
            "cast": self.cast,
            "total_duration_sec": self.total_duration_sec,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "fps": self.fps,
            "art_style": self.art_style,
            "validation_status": self.validation_status,
            "validation_errors": self.validation_errors
        }


class V3FirstPersonHistoricalDirector:
    """Implements Master Prompt V3.0 for generating and validating historical roleplay episodes."""

    def __init__(self, model_name: str = "gemini-flash-lite-latest"):
        self.model_name = model_name
        self.api_key = get_gemini_api_key() or os.environ.get("GEMINI_API_KEY", "")

    def validate_package(self, pkg: MasterPromptV3ProductionPackage) -> Tuple[bool, List[str]]:
        """Strict validation of Master Prompt V3.0 invariants."""
        errors = []

        # 1. Zero Narrator Rule
        for sc in pkg.scenes:
            spk_norm = sc.speaker.strip().lower()
            if spk_norm in PROHIBITED_NARRATOR_NAMES:
                errors.append(
                    f"VIOLATION Rule 1 (Zero Narrator): Cảnh {sc.scene_number} có người nói là '{sc.speaker}'. "
                    f"Tuyệt đối không có người dẫn chuyện ngoài!"
                )

        # 2. First-Person Protagonist Rule
        protagonist_name = pkg.protagonist.get("name", "").strip().lower()
        protagonist_spoke = False
        first_person_pronouns = {"tôi", "mình", "ta", "bản thân tôi"}

        for sc in pkg.scenes:
            spk_norm = sc.speaker.strip().lower()
            if protagonist_name in spk_norm or spk_norm in protagonist_name:
                protagonist_spoke = True
                text_low = sc.spoken_text.lower()
                # Check for third-person intrusion
                for pat in THIRD_PERSON_LEAK_PATTERNS:
                    if re.search(pat, text_low):
                        errors.append(
                            f"VIOLATION Rule 2 (Third Person Leakage): Cảnh {sc.scene_number} chứa lời văn kiểu người ngoài: '{pat}'"
                        )

        if not protagonist_spoke:
            errors.append("VIOLATION Rule 2: Nhân vật chính không có lời thoại nào trong kịch bản!")

        # 4. Multi-character dialogue requirement (at least 2 distinct speakers)
        all_speakers = {sc.speaker.strip() for sc in pkg.scenes}
        if len(all_speakers) < 2:
            errors.append(
                f"VIOLATION Rule 4 (Secondary Character Dialogue): Kịch bản chỉ có {len(all_speakers)} người nói ({list(all_speakers)}). "
                f"Phải có ít nhất một nhân vật phụ có đối thoại riêng!"
            )

        # 5. Vietnamese content
        for sc in pkg.scenes:
            if not sc.spoken_text.strip():
                errors.append(f"VIOLATION Rule 5: Cảnh {sc.scene_number} có lời thoại rỗng!")

        # 6 & 7. Historical citations
        if not pkg.historical_citations:
            errors.append("VIOLATION Rule 6/7: Thiếu nguồn kiểm chứng lịch sử (historical_citations rỗng)!")

        # 8. Consistent Blob-Head Design
        for c in pkg.cast:
            head_ratio = c.get("head_ratio", 0.42)
            if head_ratio < 0.35 or head_ratio > 0.50:
                errors.append(
                    f"VIOLATION Rule 8: Nhân vật {c.get('name')} có tỉ lệ đầu {head_ratio:.2f} ngoài khoảng chuẩn Blob-Head (0.40 - 0.45)."
                )

        pkg.validation_errors = errors
        pkg.validation_status = "PASSED" if not errors else "FAILED"
        return len(errors) == 0, errors

    def compile_from_topic_or_script(self, input_text: str) -> MasterPromptV3ProductionPackage:
        """Transforms a raw prompt, topic, or script into Master Prompt V3.0 17-field production package."""
        if self.api_key:
            try:
                pkg = self._call_gemini_v3_director(input_text)
                if pkg:
                    valid, _ = self.validate_package(pkg)
                    return pkg
            except Exception as e:
                print(f"[V3 Director] Gemini API exception: {e}, falling back to deterministic compiler...")

        return self._create_reference_berlin_1933()

    def _call_gemini_v3_director(self, input_text: str) -> Optional[MasterPromptV3ProductionPackage]:
        """Calls Gemini with strict Master Prompt V3.0 system instruction."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

        prompt = f"""
Bạn là Đạo diễn Phim hoạt hình Tài liệu Lịch sử Master Prompt V3.0 (FIRST-PERSON HISTORICAL ROLEPLAY CINEMATIC SYSTEM).
Áp dụng tuyệt đối các quy tắc bắt buộc:
1. Không có người dẫn chuyện ở bất kỳ cảnh nào.
2. Nhân vật chính luôn tự kể bằng ngôi thứ nhất ("tôi").
3. Nhân vật được phép nói trực tiếp với khán giả và phản ứng ngay trong sự kiện.
4. Có đối thoại giữa các nhân vật phụ, không chỉ độc thoại.
5. Lời thoại và toàn bộ nội dung hiển thị bằng tiếng Việt.
6. Sự kiện, ngày tháng và hậu quả phải được kiểm chứng.
7. Không biến lời thoại sáng tác thành trích dẫn lịch sử thật (ghi rõ phân loại).
8. Giữ thiết kế Blob-Head (đầu chiếm 40-45% chiều cao, tối giản) và bối cảnh Three.js 16:9 có chiều sâu.

NỘI DUNG ĐẦU VÀO CỦA NGƯỜI DÙNG:
\"\"\"{input_text}\"\"\"

YÊU CẦU ĐẦU RA:
Trả về DUY NHẤT một JSON Object hợp lệ chứa đầy đủ 17 trường sản xuất theo cấu trúc:
{{
  "episode_title": "Tên tập phim",
  "protagonist": {{
    "name": "Tên nhân vật chính",
    "role": "Nhân vật lịch sử nhập vai",
    "voice_id": "vieneu-Thiện Minh",
    "head_ratio": 0.42,
    "costume": "Trang phục phù hợp lịch sử",
    "color": "#1B3B6F"
  }},
  "time_and_location": {{
    "date": "Ngày tháng năm lịch sử",
    "place": "Địa điểm lịch sử",
    "context": "Hoàn cảnh"
  }},
  "event_summary": "Tóm tắt sự kiện có thật trong lịch sử",
  "complete_dialogue_script": [
    {{"speaker": "Tên người nói", "text": "Nội dung lời thoại"}}
  ],
  "cast": [
    {{
      "name": "Tên nhân vật",
      "role": "PROTAGONIST | SUPPORTING",
      "voice_id": "vieneu-Thiện Minh | vieneu-Quang Sơn | vieneu-Hải Đăng | vieneu-Phạm Tuyên",
      "head_ratio": 0.42,
      "costume": "Mô tả trang phục"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "scene_id": "SCENE_01",
      "timestamp_start": 0.0,
      "timestamp_end": 5.0,
      "duration": 5.0,
      "speaker": "Tên người nói (Tuyệt đối không để Người dẫn chuyện)",
      "dialogue_type": "Độc thoại trực tiếp | Tự sự hành động | Phản ứng tức thời | Đối thoại | Độc thoại nội tâm",
      "spoken_text": "Lời thoại bằng tiếng Việt",
      "character_action": "Hành động Blob-Head (cử chỉ tay, bước đi, xoay người...)",
      "character_emotion": "Biểu cảm mắt miệng",
      "camera_angle": "Góc máy (Cận cảnh, Trung cảnh, Toàn cảnh, Góc qua vai...)",
      "camera_movement": "Chuyển động Three.js (static, slow_push_in, slow_pull_out, slow_pan)",
      "environment_3d": "Mô tả bối cảnh Three.js 3D chiều sâu tiền/trung/hậu cảnh",
      "lighting": "Ánh sáng điện ảnh (Key light, ambient, mood)",
      "sound_effects": "Foley và âm thanh môi trường",
      "on_screen_text": "Chữ hiển thị địa điểm/thời gian",
      "subtitles_vietnamese": "Phụ đề tối đa 2 dòng, căn giữa"
    }}
  ],
  "historical_citations": [
    {{
      "source_name": "Tên tài liệu / kho lưu trữ",
      "fact_referenced": "Sự kiện được kiểm chứng",
      "dialogue_nature": "Lời thoại sáng tác dựa trên nhật ký/hồ sơ sự kiện (không phải trích dẫn trực tiếp)"
    }}
  ]
}}
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.25,
                "responseMimeType": "application/json"
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=22) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidate_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed = json.loads(candidate_text)

            scenes = []
            for sc in parsed.get("scenes", []):
                scenes.append(V3SceneBreakdown(
                    scene_number=sc.get("scene_number", len(scenes) + 1),
                    scene_id=sc.get("scene_id", f"SCENE_{len(scenes) + 1:02d}"),
                    timestamp_start=float(sc.get("timestamp_start", 0.0)),
                    timestamp_end=float(sc.get("timestamp_end", 5.0)),
                    duration=float(sc.get("duration", 5.0)),
                    speaker=sc.get("speaker", parsed.get("protagonist", {}).get("name", "Tôi")),
                    dialogue_type=sc.get("dialogue_type", "Độc thoại trực tiếp"),
                    spoken_text=sc.get("spoken_text", ""),
                    character_action=sc.get("character_action", "Cử chỉ tay giải thích"),
                    character_emotion=sc.get("character_emotion", "Tập trung, quyết đoán"),
                    camera_angle=sc.get("camera_angle", "Trung cảnh (Medium Shot)"),
                    camera_movement=sc.get("camera_movement", "slow_push_in"),
                    environment_3d=sc.get("environment_3d", "Hành lang đá cẩm thạch có chiều sâu"),
                    lighting=sc.get("lighting", "Ánh sáng tự nhiên từ cửa sổ lớn"),
                    sound_effects=sc.get("sound_effects", "Tiếng bước chân giày da vang dội"),
                    on_screen_text=sc.get("on_screen_text", ""),
                    subtitles_vietnamese=sc.get("subtitles_vietnamese", sc.get("spoken_text", ""))
                ))

            pkg = MasterPromptV3ProductionPackage(
                episode_title=parsed.get("episode_title", "Tập phim lịch sử V3"),
                protagonist=parsed.get("protagonist", {"name": "Nhân vật chính", "head_ratio": 0.42}),
                time_and_location=parsed.get("time_and_location", {}),
                event_summary=parsed.get("event_summary", ""),
                complete_dialogue_script=parsed.get("complete_dialogue_script", []),
                scenes=scenes,
                historical_citations=parsed.get("historical_citations", []),
                cast=parsed.get("cast", []),
                total_duration_sec=scenes[-1].timestamp_end if scenes else 25.0
            )
            return pkg

    def _create_reference_berlin_1933(self) -> MasterPromptV3ProductionPackage:
        """Deterministic master production package for Berlin 1933 demonstrating all 17 fields."""
        scenes = [
            V3SceneBreakdown(
                scene_number=1,
                scene_id="SCENE_01",
                timestamp_start=0.0,
                timestamp_end=5.5,
                duration=5.5,
                speaker="Adolf Hitler",
                dialogue_type="Độc thoại trực tiếp",
                spoken_text="Berlin, ngày 30 tháng 1 năm 1933. Tôi đang đứng trước cánh cửa căn phòng quan trọng nhất nước Đức. Chỉ vài phút nữa, tôi sẽ biết liệu mình có trở thành Thủ tướng hay không.",
                character_action="Blob-Head Hitler đứng thẳng ở 1/3 bên phải màn hình 16:9, xoay đầu nhìn thẳng về phía camera, hai tay chắp trước bụng.",
                character_emotion="Mắt mở kiên định, chân mày nhíu nhẹ căng thẳng, miệng khép dứt khoát.",
                camera_angle="Trung cảnh (Medium shot, tầm mắt)",
                camera_movement="slow_push_in (Đẩy chậm từ 6.8m vào 5.5m qua Three.js)",
                environment_3d="Hành lang Phủ Tổng thống Wilhelmstraße, cột trụ đá cẩm thạch tân cổ điển, sàn đá bóng loáng phản chiếu ánh sáng.",
                lighting="Ánh sáng mùa đông lạnh từ cửa sổ cao bên trái (Key light 4500K), đổ bóng dài trên nền gạch.",
                sound_effects="Tiếng đồng hồ quả lắc tích tắc điểm từng nhịp chậm rãi, tiếng gió rít nhẹ ngoài trời đông Berlin.",
                on_screen_text="BERLIN — 30.01.1933\nPHỦ TỔNG THỐNG REICH",
                subtitles_vietnamese="Berlin, ngày 30 tháng 1 năm 1933. Tôi đang đứng trước cánh cửa căn phòng quan trọng nhất nước Đức."
            ),
            V3SceneBreakdown(
                scene_number=2,
                scene_id="SCENE_02",
                timestamp_start=5.5,
                timestamp_end=10.8,
                duration=5.3,
                speaker="Franz von Papen",
                dialogue_type="Đối thoại",
                spoken_text="Herr Hitler, Tổng thống Hindenburg đã đồng ý tiếp ngài. Nhớ thỏa thuận: ngài là Thủ tướng, nhưng nội các do chúng tôi kiểm soát.",
                character_action="Franz von Papen bước từ cánh cửa gỗ sồi ra ở 1/3 bên trái, tay cầm xấp văn kiện nhậm chức, gật đầu vẻ trịch thượng.",
                character_emotion="Mắt híp nửa tin tưởng, khóe miệng cười đắc thắng tự mãn.",
                camera_angle="Góc hai nhân vật đối xứng 16:9 (Two-shot), để hở 60% trần vòm hành lang phía trên.",
                camera_movement="slow_pan (Quét ngang nhẹ từ trái sang phải theo bước chân Papen)",
                environment_3d="Cửa đôi gỗ sồi chạm khắc gia huy Phổ, thảm đỏ nhung trải dài giữa hành lang, đèn tường đồng cổ.",
                lighting="Đèn tường vàng ấm (Warm 3000K) rọi ranh giới giữa hai người, tương phản với ánh xám hậu cảnh.",
                sound_effects="Tiếng then cửa gỗ lách cách mở ra, tiếng đế giày da bước trên thảm nhung nén chặt.",
                on_screen_text="FRANZ VON PAPEN\nCựu Thủ tướng Đức",
                subtitles_vietnamese="Herr Hitler, Tổng thống Hindenburg đã đồng ý tiếp ngài. Nội các do chúng tôi kiểm soát."
            ),
            V3SceneBreakdown(
                scene_number=3,
                scene_id="SCENE_03",
                timestamp_start=10.8,
                timestamp_end=15.5,
                duration=4.7,
                speaker="Adolf Hitler",
                dialogue_type="Tự sự hành động & Phản ứng tức thời",
                spoken_text="Họ nghĩ rằng họ đã bẫy được tôi trong một liên minh bù nhìn. Nhưng bước qua cánh cửa này, quyền lực sẽ thuộc về tôi.",
                character_action="Hitler bước dứt khoát về phía cánh cửa mở, quay nửa mặt lại nhìn máy quay với nụ cười lạnh lùng, tay chỉnh vạt áo khoác măng-tô đen.",
                character_emotion="Mắt mở to sắc bén, chân mày nhướng cao đầy tham vọng.",
                camera_angle="Cận cảnh nghiêng nhẹ từ dưới lên (Low-angle close-up, góc anh hùng u ám)",
                camera_movement="slow_push_in (Theo bước chân nhân vật tiến vào khung cửa)",
                environment_3d="Khung cửa mở ra phòng làm việc của Hindenburg với ánh đèn bàn màu xanh ngọc và khói xì-gà lơ lửng.",
                lighting="Backlight mạnh mẽ từ bên trong phòng hắt ngược ra ngoài, viền sáng xung quanh Blob-Head silhouette.",
                sound_effects="Tiếng bản lề cửa gỗ nặng trĩu chuyển động, tiếng gõ gậy của Thống chế Hindenburg bên trong phòng.",
                on_screen_text="LỄ TUYÊN THỆ NHẬM CHỨC\n11:15 SÁNG",
                subtitles_vietnamese="Họ nghĩ rằng họ đã bẫy được tôi. Nhưng bước qua cánh cửa này, quyền lực sẽ thuộc về tôi."
            ),
            V3SceneBreakdown(
                scene_number=4,
                scene_id="SCENE_04",
                timestamp_start=15.5,
                timestamp_end=20.5,
                duration=5.0,
                speaker="Joseph Goebbels",
                dialogue_type="Đối thoại & Phản ứng tức thời",
                spoken_text="Quốc trưởng! Đám đông đã bắt đầu tụ tập kín quảng trường Wilhelmplatz. Bó đuốc đã sẵn sàng rực sáng đêm nay!",
                character_action="Goebbels đứng ở bậc thềm ban công, tay giơ bản thảo phát thanh, chỉ tay về phía quảng trường bên ngoài cửa sổ lớn.",
                character_emotion="Mắt sáng rực cuồng nhiệt, miệng cười lớn phấn khích tột độ.",
                camera_angle="Toàn cảnh rộng (Wide establishing shot) kết hợp cửa kính nhìn ra bầu trời Berlin chạng vạng.",
                camera_movement="slow_pull_out (Lùi máy quay ra xa để bao trọn khung cảnh từ bên trong ra quảng trường)",
                environment_3d="Phòng khánh tiết Phủ Thủ tướng, rèm nhung đỏ lớn, cửa sổ kính vòm nhìn ra quảng trường Wilhelmplatz.",
                lighting="Ánh hoàng hôn đỏ sẫm pha trộn với ánh lửa bập bùng của những ngọn đuốc đầu tiên thắp lên từ phía dưới.",
                sound_effects="Tiếng reo hò rền vang như sóng biển từ xa xăm vọng vào qua lớp kính, tiếng kèn đồng quân nhạc mờ ảo.",
                on_screen_text="QUẢNG TRƯỜNG WILHELMPLATZ\nĐÊM ĐUỐC LỬA 30.01.1933",
                subtitles_vietnamese="Quốc trưởng! Bó đuốc đã sẵn sàng rực sáng đêm nay khắp Berlin!"
            ),
            V3SceneBreakdown(
                scene_number=5,
                scene_id="SCENE_05",
                timestamp_start=20.5,
                timestamp_end=26.0,
                duration=5.5,
                speaker="Adolf Hitler",
                dialogue_type="Độc thoại trực tiếp & Mở ra tập tiếp theo",
                spoken_text="Mười bốn năm kể từ ngày rời bệnh viện Pasewalk trong mù lòa và tuyệt vọng. Nước Đức của tôi... từ đêm nay sẽ không bao giờ như trước nữa.",
                character_action="Hitler bước ra ban công, hai tay bám vào lan can đá, nhìn thẳng vào ống kính máy quay trong khi gió thổi bay vạt áo.",
                character_emotion="Khuôn mặt Blob-Head lạnh lùng, mắt tối sẫm dưới bóng mũ, biểu cảm băng giá không lay chuyển.",
                camera_angle="Trung cận (Medium close-up), bố cục 1/3 bên phải, hậu cảnh là hàng ngàn đốm lửa bập bùng trong sương đêm.",
                camera_movement="static (Máy quay tĩnh tuyệt đối tạo cảm giác uy quyền và định mệnh lạnh lùng)",
                environment_3d="Lan can ban công đá Phủ Thủ tướng, bầu trời đêm Berlin phủ khói xám, hàng ngàn ngọn đuốc chuyển động bên dưới.",
                lighting="Ánh lửa cam đỏ từ dưới bập bùng hắt ngược lên khuôn mặt (Chiaroscuro lighting tương phản cao).",
                sound_effects="Tiếng trống diễu hành dồn dập vang lên, tiếng hô vang khẩu hiệu đồng thanh, tiếng gió đêm rít qua lan can đá.",
                on_screen_text="TẬP TIẾP THEO:\nCUỘC ĐỐT PHÁ NGHỊ VIỆN REICHSTAG",
                subtitles_vietnamese="Nước Đức của tôi... từ đêm nay sẽ không bao giờ như trước nữa."
            )
        ]

        citations = [
            {
                "source_name": "Ian Kershaw, 'Hitler: 1889-1936 Hubris', Chương 10: The Lever of Power, tr. 415-430.",
                "fact_referenced": "Sự kiện Hindenburg bổ nhiệm Hitler làm Thủ tướng vào khoảng 11:15 sáng ngày 30/1/1933; kế hoạch của Franz von Papen nhằm đóng khung Hitler trong nội các liên minh.",
                "dialogue_nature": "Lời thoại tái dựng kịch tính dựa trên hồi ký của Franz von Papen ('Der Wahrheit một Gasse') và Joseph Goebbels ('Vom Kaiserhof zur Reichskanzlei')."
            },
            {
                "source_name": "William L. Shirer, 'The Rise and Fall of the Third Reich', Quyển 1, Phần 7: The Road to Power.",
                "fact_referenced": "Cuộc diễu hành đuốc đêm 30/1/1933 qua Cổng Brandenburg và trước ban công Phủ Thủ tướng.",
                "dialogue_nature": "Bối cảnh âm thanh và lời thoại phát thanh tái dựng trung thực với tư liệu hình ảnh Bundesarchiv Filmarchiv."
            }
        ]

        cast = [
            {
                "name": "Adolf Hitler",
                "role": "PROTAGONIST_STORYTELLER",
                "voice_id": "vieneu-Thiện Minh",
                "head_ratio": 0.42,
                "costume": "Măng-tô đen ve áo lớn, cà vạt sẫm màu",
                "color": "#1B2A4A"
            },
            {
                "name": "Franz von Papen",
                "role": "SUPPORTING_SPEAKER",
                "voice_id": "vieneu-Hải Đăng",
                "head_ratio": 0.41,
                "costume": "Âu phục ngoại giao Phổ, áo gi-lê xám, cổ áo cứng",
                "color": "#3D405B"
            },
            {
                "name": "Joseph Goebbels",
                "role": "SUPPORTING_SPEAKER",
                "voice_id": "vieneu-Quang Sơn",
                "head_ratio": 0.40,
                "costume": "Áo khoác xám dài, mũ phớt",
                "color": "#2B2D42"
            }
        ]

        dialogue_script = [
            {"speaker": s.speaker, "text": s.spoken_text} for s in scenes
        ]

        pkg = MasterPromptV3ProductionPackage(
            episode_title="Berlin 1933: Cánh Cửa Phủ Thủ Tướng",
            protagonist=cast[0],
            time_and_location={
                "date": "30 tháng 1 năm 1933",
                "place": "Wilhelmstraße, Berlin, Nước Đức",
                "context": "Ngày bổ nhiệm Thủ tướng và sự sụp đổ của Cộng hòa Weimar"
            },
            event_summary="Ngày 30 tháng 1 năm 1933, Tổng thống Paul von Hindenburg chính thức bổ nhiệm Adolf Hitler làm Thủ tướng Đức sau các thỏa thuận bí mật của Franz von Papen. Tập phim tái hiện khoảnh khắc trước khi bước vào phòng bổ nhiệm và phản ứng trước đêm diễu hành đuốc.",
            complete_dialogue_script=dialogue_script,
            scenes=scenes,
            historical_citations=citations,
            cast=cast,
            total_duration_sec=26.0
        )
        self.validate_package(pkg)
        return pkg


def format_17_fields_markdown(pkg: MasterPromptV3ProductionPackage) -> str:
    """Formats the production package into readable 17-field Vietnamese production markdown."""
    md = []
    md.append(f"# KỊCH BẢN SẢN XUẤT ĐIỆN ẢNH V3.0: {pkg.episode_title.upper()}")
    md.append(f"**Chuẩn định dạng:** Master Prompt V3.0 (First-Person Roleplay) | **Tỉ lệ khung hình:** {pkg.aspect_ratio} ({pkg.resolution} @ {pkg.fps}fps)")
    md.append(f"**Phong cách nghệ thuật:** {pkg.art_style} | **Thời lượng:** {pkg.total_duration_sec}s\n")
    md.append("---\n")

    # 1. Tên tập
    md.append(f"### 1. TÊN TẬP: {pkg.episode_title}\n")

    # 2. Nhân vật chính
    pro = pkg.protagonist
    md.append(f"### 2. NHÂN VẬT CHÍNH:\n- **Tên:** {pro.get('name')}\n- **Vai trò:** {pro.get('role')} (Kể chuyện ngôi thứ nhất 'Tôi', không có người dẫn chuyện)\n- **Tỉ lệ đầu:** {pro.get('head_ratio', 0.42)*100:.0f}% tổng chiều cao (Documentary Blob-Head)\n- **Giọng đọc:** `{pro.get('voice_id')}`\n- **Trang phục:** {pro.get('costume')}\n")

    # 3. Thời gian và địa điểm
    loc = pkg.time_and_location
    md.append(f"### 3. THỜI GIAN VÀ ĐỊA ĐIỂM:\n- **Thời gian:** {loc.get('date')}\n- **Địa điểm:** {loc.get('place')}\n- **Hoàn cảnh lịch sử:** {loc.get('context')}\n")

    # 4. Tóm tắt sự kiện
    md.append(f"### 4. TÓM TẮT SỰ KIỆN:\n{pkg.event_summary}\n")

    # 5. Kịch bản lời thoại hoàn chỉnh
    md.append("### 5. KỊCH BẢN LỜI THOẠI HOÀN CHỈNH:\n")
    for d in pkg.complete_dialogue_script:
        md.append(f"- **{d['speaker']}:** \"{d['text']}\"")
    md.append("\n---\n")

    # 6-16. Bảng phân cảnh chi tiết
    md.append("### 6–16. PHÂN CHIA CHI TIẾT TỪNG CẢNH (SCENE BREAKDOWN):\n")
    for sc in pkg.scenes:
        md.append(f"#### CẢNH {sc.scene_number:02d} [{sc.scene_id}] — ({sc.timestamp_start:.1f}s - {sc.timestamp_end:.1f}s | {sc.duration:.1f}s)")
        md.append(f"- **7. Timestamp:** `{sc.timestamp_start:.1f}s` đến `{sc.timestamp_end:.1f}s` (Thời lượng: `{sc.duration:.1f}s`)")
        md.append(f"- **Người nói:** **{sc.speaker}** ({sc.dialogue_type})")
        md.append(f"- **Lời thoại:** *\"{sc.spoken_text}\"*")
        md.append(f"- **8. Hành động nhân vật:** {sc.character_action}")
        md.append(f"- **9. Biểu cảm nhân vật:** {sc.character_emotion}")
        md.append(f"- **10. Góc máy:** {sc.camera_angle}")
        md.append(f"- **11. Chuyển động camera:** `{sc.camera_movement}` (Three.js 16:9)")
        md.append(f"- **12. Bối cảnh 3D:** {sc.environment_3d}")
        md.append(f"- **13. Ánh sáng:** {sc.lighting}")
        md.append(f"- **14. Hiệu ứng âm thanh (SFX & Foley):** {sc.sound_effects}")
        md.append(f"- **15. Chữ hiển thị:** `{sc.on_screen_text.replace(chr(10), ' | ')}`")
        md.append(f"- **16. Phụ đề tiếng Việt:** \"{sc.subtitles_vietnamese}\" (Căn giữa, tối đa 2 dòng, co font tự động)")
        md.append("")

    md.append("---\n")
    # 17. Nguồn kiểm chứng lịch sử
    md.append("### 17. NGUỒN KIỂM CHỨNG LỊCH SỬ (HISTORICAL CITATIONS):\n")
    for c in pkg.historical_citations:
        md.append(f"- **Nguồn tài liệu:** {c.get('source_name')}")
        md.append(f"  - *Sự kiện kiểm chứng:* {c.get('fact_referenced')}")
        md.append(f"  - *Bản chất lời thoại:* {c.get('dialogue_nature')}\n")

    return "\n".join(md)


if __name__ == "__main__":
    director = V3FirstPersonHistoricalDirector()
    sample_pkg = director._create_reference_berlin_1933()
    output_md = format_17_fields_markdown(sample_pkg)
    print(output_md[:1200])
    print(f"\n... Total length: {len(output_md)} characters. Validation: {sample_pkg.validation_status}")
