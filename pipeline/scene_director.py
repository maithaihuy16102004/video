"""LLM Director - Phân rã kịch bản thô thành Scene Director JSON có cấu trúc.
Tuân thủ chuẩn scene_schema.json, tự động áp dụng quy tắc climax_score và nhịp điệu camera/SFX.
"""

import json
import os
import sys
import re
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class LLMDirector:
    def __init__(self, schema_path: str = None):
        if schema_path is None:
            schema_path = str(Path(__file__).parent / "scene_schema.json")
        self.schema_path = schema_path
        with open(schema_path, "r", encoding="utf-8") as f:
            self.schema = json.load(f)

    def _apply_climax_rules(self, timeline_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Áp dụng quy tắc ánh xạ tự động dựa trên climax_score để ép hiệu ứng đồng nhất"""
        for scene in timeline_data:
            score = scene.get("climax_score", 5)
            visual = scene.setdefault("visual_director", {})
            voice = scene.setdefault("voiceover", {})

            # Quy tắc 1-4: Nhẹ nhàng, mở đầu / dẫn nhập
            if 1 <= score <= 4:
                visual["camera_effect"] = "zoom_in_slow"
                if visual.get("transition_effect") not in ["cut", "fade_to_black"]:
                    visual["transition_effect"] = "cut"
                scene["audio_fx"] = {"sfx_insert": "subtle_whoosh", "sfx_timestamp": 0.2}

            # Quy tắc 5-7: Gây cấn, bất ngờ, nhịp tăng
            elif 5 <= score <= 7:
                if visual.get("camera_effect") not in ["zoom_in_fast", "pan_left", "pan_right"]:
                    visual["camera_effect"] = "zoom_in_fast"
                if visual.get("b_roll_overlay_ratio", 0.0) < 0.6:
                    visual["b_roll_overlay_ratio"] = 0.7
                scene["audio_fx"] = {"sfx_insert": "sub_drop", "sfx_timestamp": 0.0}

            # Quy tắc 8-10: Cao trào, bùng nổ, twist
            elif 8 <= score <= 10:
                visual["camera_effect"] = "glitch_shake"
                visual["transition_effect"] = "whip_pan"
                visual["b_roll_overlay_ratio"] = max(visual.get("b_roll_overlay_ratio", 0.8), 0.8)
                voice["speed"] = 1.15
                scene["audio_fx"] = {"sfx_insert": "cinematic_boom_bass", "sfx_timestamp": 0.0}

        return timeline_data

    def _call_http_api(self, prompt: str, system_prompt: str, api_key: str, base_url: str, model: str) -> Optional[str]:
        """Gọi API LLM OpenAI-compatible qua urllib chuẩn (không cần cài thêm sdk)"""
        url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "LLMDirector/1.0"
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[LLMDirector] Lỗi gọi API ({url}): {e}")
            return None

    def _fallback_template_director(self, raw_script: str, topic: str = "Tự động hóa Video AI") -> Dict[str, Any]:
        """Tạo Scene Director JSON mẫu chất lượng cao khi không có API key"""
        print("[LLMDirector] Sử dụng fallback Director Template (offline mode)...")
        sentences = [s.strip() for s in re.split(r"[.\n!?;]+", raw_script) if len(s.strip()) > 8]
        if not sentences:
            sentences = [
                "Bạn có bao giờ tự hỏi điều gì thực sự đứng sau trí tuệ nhân tạo AGI?",
                "Một sự thật đáng kinh ngạc là thuật toán đang thay đổi mọi quy luật sản xuất video.",
                "Hãy sẵn sàng làm chủ công nghệ trước khi bị bỏ lại phía sau."
            ]

        climax_sequence = [3, 8, 5, 9, 4, 7]
        emotions = ["curious", "surprised", "tense", "excited", "serious", "neutral"]
        b_roll_prompts = [
            "cyberpunk glowing synaptic networks, digital data stream 4k",
            "close up shocked eye reflecting binary code glitch effect",
            "futuristic server rack glowing neon blue and purple",
            "cinematic human hand reaching to artificial intelligence core",
            "fast motion viral growth graph glowing holographic display"
        ]

        timeline = []
        for i, text in enumerate(sentences):
            score = climax_sequence[i % len(climax_sequence)]
            emotion = emotions[i % len(emotions)]
            b_roll = b_roll_prompts[i % len(b_roll_prompts)]
            seconds = i * 4
            m = seconds // 60
            s = seconds % 60

            scene = {
                "scene_id": i + 1,
                "timestamp_start": f"{m:02d}:{s:02d}",
                "voiceover": {
                    "text": text,
                    "emotion_tag": emotion,
                    "pitch_modifier": 1.0,
                    "speed": 1.0
                },
                "visual_director": {
                    "avatar_action": "explaining_and_gesturing" if score < 7 else "shocked_expression",
                    "b_roll_prompt": b_roll,
                    "b_roll_overlay_ratio": 0.0 if i == 0 else 0.7,
                    "camera_effect": "zoom_in_slow",
                    "transition_effect": "cut"
                },
                "audio_fx": {
                    "sfx_insert": "subtle_whoosh",
                    "sfx_timestamp": 0.1
                },
                "climax_score": score
            }
            timeline.append(scene)

        result = {
            "video_metadata": {
                "topic": topic,
                "target_pace": "fast_paced",
                "global_bgm": "mysterious_cyberpunk_lofi"
            },
            "timeline": self._apply_climax_rules(timeline)
        }
        return result

    def generate_director_json(
        self,
        raw_script: str,
        client_ai: Any = None,
        topic: str = "Tự động hóa Video AI",
        provider: str = "deepseek"
    ) -> Dict[str, Any]:
        """
        Gọi LLM để phân rã kịch bản thô thành cấu trúc Scene JSON.
        Hỗ trợ client OpenAI/DeepSeek hoặc tự động dùng DEEPSEEK_API_KEY/OPENAI_API_KEY.
        Nếu không có key, tự động dùng template director chất lượng cao.
        """
        system_prompt = (
            "Bạn là một Đạo diễn AI video ngắn (TikTok/Reels/Shorts) chuyên nghiệp. "
            "Hãy phân tích kịch bản thô và phân rã thành các phân cảnh với cấu trúc JSON chuẩn xác tuân theo Schema sau:\n"
            f"{json.dumps(self.schema, ensure_ascii=False, indent=2)}\n\n"
            "YÊU CẦU QUAN TRỌNG VỀ NHỊP ĐIỆU (RETENTION PACING):\n"
            "1. Phân chia mỗi phân cảnh ngắn từ 2-5 giây thoại.\n"
            "2. Biến thiên climax_score (thang điểm 1-10) nhấp nhô liên tục (ví dụ: 3 -> 8 -> 5 -> 9 -> 4) "
            "để tạo sự kịch tính dồn dập, không bao giờ để điểm số đều đều.\n"
            "3. b_roll_overlay_ratio: Cảnh 1 (Hook mở đầu) để 0.0 (Avatar nói 100%). "
            "Các cảnh giải thích tiếp theo để 0.6 - 0.8 (Cắt đè B-roll minh họa).\n"
            "4. Chỉ trả về JSON thuần, không kèm markdown hoặc giải thích."
        )

        user_prompt = f"Chủ đề: {topic}\nKịch bản thô cần phân tích và đạo diễn:\n{raw_script}"

        # 1. Thử dùng client_ai (nếu truyền vào)
        if client_ai is not None:
            try:
                resp = client_ai.chat.completions.create(
                    model="deepseek-chat" if provider == "deepseek" else "gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                data = json.loads(resp.choices[0].message.content)
                data["timeline"] = self._apply_climax_rules(data.get("timeline", []))
                return data
            except Exception as e:
                print(f"[LLMDirector] Lỗi client_ai: {e}")

        # 2. Thử gọi API trực tiếp nếu có env key
        ds_key = os.environ.get("DEEPSEEK_API_KEY")
        oa_key = os.environ.get("OPENAI_API_KEY")

        content = None
        if ds_key:
            content = self._call_http_api(
                prompt=user_prompt,
                system_prompt=system_prompt,
                api_key=ds_key,
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
            )
        elif oa_key:
            content = self._call_http_api(
                prompt=user_prompt,
                system_prompt=system_prompt,
                api_key=oa_key,
                base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            )

        if content:
            try:
                data = json.loads(content)
                if "timeline" in data:
                    data["timeline"] = self._apply_climax_rules(data["timeline"])
                    return data
            except Exception as e:
                print(f"[LLMDirector] Lỗi parse JSON từ LLM: {e}")

        # 3. Fallback sang Template Director thông minh
        return self._fallback_template_director(raw_script, topic=topic)


if __name__ == "__main__":
    director = LLMDirector()
    sample_script = (
        "Bạn đã bao giờ tự hỏi điều gì thực sự đứng sau trí tuệ nhân tạo AGI? "
        "Một sự thật đáng kinh ngạc mà ít người có thể ngờ tới: các mô hình ngôn ngữ đang tự tối ưu hóa mã nguồn. "
        "Nếu bạn không hành động ngay hôm nay, bạn sẽ bị thay thế trong vòng hai năm tới!"
    )
    res = director.generate_director_json(sample_script, topic="Bí mật đằng sau AGI")
    print(json.dumps(res, ensure_ascii=False, indent=2))
