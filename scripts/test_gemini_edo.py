import json
import os
import sys
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
from pipeline.env_secrets import get_gemini_api_key, load_dotenv

load_dotenv()
api_key = get_gemini_api_key()

prompt = """Phân tích kịch bản sau:
Tiêu đề: BỨC THƯ KHÔNG ĐƯỢC PHÉP ƯỚT
Bối cảnh: Edo Nhật Bản 1800.
Nhân vật: Haru (đưa thư 22t, kể chuyện ngôi 1), Ông chủ trạm thư (60t, nghiêm), Aiko (24t, nhận thư), Người bán cá (quát).
5 Cảnh:
1. Trạm thư hoàng hôn: Nhận thư bọc giấy dầu, hạt mưa đầu tiên.
2. Phố Edo mưa bão: Chạy né xe kéo, người bán cá quát.
3. Cầu gỗ: Ván gãy RẮC!, suýt rơi xuống dòng kênh, ôm chặt thư.
4. Nhà Aiko đèn lồng: Trao thư ướt sũng, Aiko mở thư rồi bật cười.
5. Cú twist: Thư dặn nhớ mang ô. Haru nhìn chiếc dép mất.

Hãy trả về JSON có cấu trúc chính xác sau:
{
  "title": "Bức Thư Không Được Phép Ướt",
  "genre": "HISTORICAL_FICTION_COMEDY",
  "total_duration": 80,
  "protagonist": {
    "id": "char_haru",
    "name": "Haru",
    "role": "PROTAGONIST_STORYTELLER",
    "voice": "vieneu-Đức Trí",
    "age": 22,
    "description": "Người đưa thư trẻ, nhanh nhẹn, hóm hỉnh"
  },
  "supporting_cast": [
    {"id": "char_station_master", "name": "Ông chủ trạm thư", "role": "STATION_MASTER", "voice": "vieneu-Mạnh Dũng", "age": 60},
    {"id": "char_aiko", "name": "Aiko", "role": "RECIPIENT", "voice": "vieneu-Trúc Ly", "age": 24},
    {"id": "char_fishmonger", "name": "Người bán cá", "role": "STREET_VENDOR", "voice": "vieneu-Thái Sơn", "age": 40}
  ],
  "locations": [
    {"id": "LOC_EDO_STATION", "name": "Trạm thư Edo hoàng hôn", "weather": "DRIZZLE"},
    {"id": "LOC_EDO_STREET_RAIN", "name": "Phố cổ Edo mưa bão", "weather": "HEAVY_RAIN"},
    {"id": "LOC_EDO_WOODEN_BRIDGE", "name": "Cây cầu gỗ bắc qua kênh", "weather": "TORRENTIAL_RAIN"},
    {"id": "LOC_EDO_LANTERN_HOUSE", "name": "Ngôi nhà gỗ dưới ánh đèn lồng", "weather": "NIGHT_RAIN"},
    {"id": "LOC_EDO_PORCH_TWIST", "name": "Hiên nhà Aiko - Cú twist", "weather": "RAIN_STOPPING"}
  ],
  "scenes": [
    {
      "scene_id": 1,
      "title": "Trạm thư lúc chiều muộn",
      "duration": 15,
      "shot": "MEDIUM_HERO",
      "location": "LOC_EDO_STATION",
      "action": "Haru nhận phong thư giấy dầu từ ông chủ, một giọt mưa rơi trúng mũi.",
      "dialogue": "Ông chủ dặn không được để ướt. Haru nhận ra ngày đẹp để bắt đầu thảm họa.",
      "sfx": ["rain_drip_single", "paper_envelope_rustle"]
    },
    {
      "scene_id": 2,
      "title": "Con phố Edo dưới cơn mưa",
      "duration": 16,
      "shot": "TRACKING_SPRINT",
      "location": "LOC_EDO_STREET_RAIN",
      "action": "Haru chạy thục mạng qua phố ngập nước, né xe kéo, suýt đâm người bán cá.",
      "dialogue": "Người bán cá hét: Nhìn đường chứ nhóc! Haru lo nếu thư ướt sẽ bị biến thành cá khô.",
      "sfx": ["heavy_rain_loop", "footstep_water_splashes", "vendor_shout"]
    },
    {
      "scene_id": 3,
      "title": "Cây cầu gỗ - Ván gãy suýt rơi",
      "duration": 18,
      "shot": "DRAMATIC_LOW_ANGLE_MCU",
      "location": "LOC_EDO_WOODEN_BRIDGE",
      "action": "Ván cầu gãy RẮC!, Haru ngã nhào, một tay bám lan can, một tay ôm chặt phong thư khỏi rơi xuống dòng kênh lũ.",
      "dialogue": "Giữa lúc mạng sống treo trên thanh gỗ mục, Haru chỉ lo thư có ướt không.",
      "sfx": ["wood_snap_crack", "rush_water_torrent", "gasp_effort", "bridge_groan"]
    },
    {
      "scene_id": 4,
      "title": "Ngôi nhà dưới ánh đèn lồng",
      "duration": 15,
      "shot": "WARM_TWO_SHOT",
      "location": "LOC_EDO_LANTERN_HOUSE",
      "action": "Haru tới nơi ướt sũng, trao thư bằng hai tay. Aiko mở thư đọc rồi bất ngờ bật cười.",
      "dialogue": "Haru tự hào vì thư vẫn khô, nhưng đứng sững khi thấy Aiko bật cười.",
      "sfx": ["lantern_creak", "door_slide", "paper_unfold", "female_chuckle"]
    },
    {
      "scene_id": 5,
      "title": "Cú twist: Nhớ mang ô",
      "duration": 16,
      "shot": "COMEDIC_CLOSEUP_TILT",
      "location": "LOC_EDO_PORCH_TWIST",
      "action": "Aiko quay lá thư: 'Aiko, nhớ mang ô. Chiều nay có thể mưa'. Haru nhìn chiếc dép rơm đã mất từ lúc qua cầu.",
      "dialogue": "Bài học quý giá: Biết thư viết cái quái gì trước khi mang đi!",
      "sfx": ["comic_bamboo_hit", "rain_diminish", "shamisen_twang"]
    }
  ]
}
"""

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
body = json.dumps({
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
}).encode("utf-8")

req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    res_text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(res_text)
    print("SUCCESSFUL GEMINI PARSE!")
    print("Title:", parsed.get("title"))
    print("Total duration:", parsed.get("total_duration"))
    print("Protagonist:", parsed.get("protagonist", {}).get("name"), "Voice:", parsed.get("protagonist", {}).get("voice"))
    print("Supporting cast:", [c.get("name") for c in parsed.get("supporting_cast", [])])
    print("Scenes count:", len(parsed.get("scenes", [])))
    for s in parsed.get("scenes", []):
        print(f"  Scene {s.get('scene_id')}: {s.get('title')} ({s.get('duration')}s) - Shot: {s.get('shot')}")
