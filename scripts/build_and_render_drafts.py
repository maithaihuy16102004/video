"""Build and Render the 3 Authoritative Acceptance Draft MP4s for V5.1 Review.

Test 1: Cảnh đối thoại (Cafe Dialogue - Tuấn & Minh)
Test 2: Cảnh hành động (Bridge Action - Haru suýt rơi khỏi cầu)
Test 3: Cảnh cảm xúc & Cú chốt hài (Aiko mở thư & Cú chốt hài)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Enforce UTF-8 on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.universal.v5_audio_director import get_audio_director
OUTPUT_DIR = ROOT / "output" / "v51_drafts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_draft_1_cafe_dialogue() -> dict:
    """Test 1: Two characters talking in a cafe, distinct voices, coffee clink, ambient chatter."""
    pkg = {
        "project_id": "v51_draft_1_cafe_dialogue",
        "total_sequence_duration_seconds": 15.0,
        "scene_world": {
            "location_id": "LOC_CAFE_HANOI",
            "canonical_name": "Quán Cà Phê Phố Cổ Hà Nội",
            "architecture_style": "CAFE",
            "weather": "CLEAR",
            "threejs_environment": {
                "camera_initial": {"position": [-1.6, 1.7, 4.2], "target": [0.1, 1.1, 0.0], "fov": 42},
                "camera_keyframes": [
                    {"t": 0.0, "position": [-1.6, 1.7, 4.2], "target": [0.1, 1.1, 0.0]},
                    {"t": 5.0, "position": [-0.6, 1.6, 3.2], "target": [0.2, 1.1, -0.1]},
                    {"t": 10.0, "position": [0.6, 1.6, 3.2], "target": [-0.2, 1.1, 0.1]}
                ]
            }
        },
        "actors": [
            {
                "actor_id": "tuan",
                "role": "LEAD",
                "dna": {
                    "id": "tuan",
                    "name": "Tuấn",
                    "proportions": {"headRatio": 0.148, "standingHeightPx": 305, "shoulderWidthPx": 58, "limbThicknessPx": 11, "torsoLengthPx": 100, "legLengthPx": 156},
                    "face": {"headContour": "square_jaw", "skinTone": "#F3DFC1", "eyeType": "curious_wide", "eyeColor": "#1B1B1B", "eyebrowStyle": "straight_sharp", "facialHair": "none"},
                    "hair": {"style": "modern_crop", "color": "#1C1D21", "accessory": "none"},
                    "costume": {"archetype": "modern_hoodie", "primaryColor": "#2B4C7E", "accentColor": "#E0FBFC", "pantsColor": "#1F2937", "footwear": "sneakers"},
                    "heldProps": {"rightHand": "steaming_coffee_cup"}
                },
                "staging": {"initial_world_pos": [-0.65, 0.0, 0.1], "facing": "RIGHT", "posture": "sit"},
                "performance_cues": [
                    {"time": 0.0, "pos": [-0.65, 0.0, 0.1], "action": "sip_coffee", "emotion": "reflective", "facing": 1},
                    {"time": 2.5, "pos": [-0.65, 0.0, 0.1], "action": "speak", "emotion": "excited", "facing": 1},
                    {"time": 4.8, "pos": [-0.58, 0.0, 0.12], "action": "speak_gestural", "emotion": "excited", "facing": 1},
                    {"time": 7.0, "pos": [-0.65, 0.0, 0.1], "action": "listen", "emotion": "focused", "facing": 1},
                    {"time": 9.0, "pos": [-0.60, 0.0, 0.08], "action": "think", "emotion": "focused", "facing": 1},
                    {"time": 10.5, "pos": [-0.65, 0.0, 0.1], "action": "speak", "emotion": "relief", "facing": 1},
                    {"time": 12.8, "pos": [-0.58, 0.0, 0.12], "action": "speak_gestural", "emotion": "relief", "facing": 1}
                ]
            },
            {
                "actor_id": "minh",
                "role": "SUPPORT",
                "dna": {
                    "id": "minh",
                    "name": "Minh",
                    "proportions": {"headRatio": 0.142, "standingHeightPx": 315, "shoulderWidthPx": 56, "limbThicknessPx": 11, "torsoLengthPx": 104, "legLengthPx": 162},
                    "face": {"headContour": "oval_gaunt", "skinTone": "#EFE0D3", "eyeType": "intense_focused", "eyeColor": "#2B2D42", "eyebrowStyle": "straight_sharp", "facialHair": "none"},
                    "hair": {"style": "side_sweep_1914", "color": "#23201D", "accessory": "none"},
                    "costume": {"archetype": "victorian_frock_coat", "primaryColor": "#3D5A80", "accentColor": "#98C1D9", "pantsColor": "#293241", "footwear": "leather_shoes"},
                    "heldProps": {"rightHand": "steaming_coffee_cup"}
                },
                "staging": {"initial_world_pos": [0.65, 0.0, -0.1], "facing": "LEFT", "posture": "sit"},
                "performance_cues": [
                    {"time": 0.0, "pos": [0.65, 0.0, -0.1], "action": "listen", "emotion": "focused", "facing": -1},
                    {"time": 2.5, "pos": [0.60, 0.0, -0.08], "action": "think", "emotion": "curious", "facing": -1},
                    {"time": 5.0, "pos": [0.65, 0.0, -0.1], "action": "sip_coffee", "emotion": "reflective", "facing": -1},
                    {"time": 7.5, "pos": [0.65, 0.0, -0.1], "action": "speak", "emotion": "reflective", "facing": -1},
                    {"time": 9.3, "pos": [0.70, 0.0, -0.12], "action": "speak_gestural", "emotion": "reflective", "facing": -1},
                    {"time": 11.0, "pos": [0.65, 0.0, -0.1], "action": "laugh", "emotion": "happy", "facing": -1},
                    {"time": 13.0, "pos": [0.62, 0.0, -0.08], "action": "listen", "emotion": "happy", "facing": -1}
                ]
            }
        ],
        "storyBeats": [
            {
                "beatId": "BEAT_01",
                "timeRange": [0.0, 5.0],
                "primaryVerb": "speak",
                "whatHappens": "Tuấn đặt tách cà phê, say sưa trình bày ý tưởng khởi nghiệp.",
                "shotType": "MEDIUM_SHOT",
                "emotion": "excited",
                "dialogue": {"speaker": "Tuấn", "text": "Cậu nhìn xem, thuật toán AI này có thể render video tự động chỉ trong vài giây.", "voiceId": "vieneu-Thiện Minh"}
            },
            {
                "beatId": "BEAT_02",
                "timeRange": [5.0, 10.0],
                "primaryVerb": "speak",
                "whatHappens": "Minh chăm chú lắng nghe, gật đầu và đặt ra câu hỏi then chốt.",
                "shotType": "CLOSE_UP",
                "emotion": "reflective",
                "dialogue": {"speaker": "Minh", "text": "Rất ấn tượng đấy... Nhưng liệu cảm xúc giọng nói có tự nhiên như người thật không?", "voiceId": "vieneu-Quang Sơn"}
            },
            {
                "beatId": "BEAT_03",
                "timeRange": [10.0, 15.0],
                "primaryVerb": "laugh",
                "whatHappens": "Cả hai cùng bật cười đồng thuận, không khí quán cà phê ấm cúng.",
                "shotType": "TWO_SHOT",
                "emotion": "happy",
                "dialogue": {"speaker": "Tuấn", "text": "Chắc chắn rồi! Hệ thống VieNeu-TTS v3 Turbo 48kHz đã xử lý trọn vẹn điều đó.", "voiceId": "vieneu-Thiện Minh"}
            }
        ],
        "visual_plan": [
            {"type": "LOCATION_DATE_CARD", "content_headline": "QUÁN CÀ PHÊ HÀ NỘI · 2026", "content_body": "Đối Thoại Khởi Nghiệp Công Nghệ AI", "start_time": 0.0, "end_time": 4.5}
        ],
        "voice_timeline": {
            "lines": [
                {"start_sec": 0.5, "end_sec": 4.8, "speaker": "Tuấn", "text": "Cậu nhìn xem, thuật toán AI này có thể render video tự động chỉ trong vài giây."},
                {"start_sec": 5.2, "end_sec": 9.5, "speaker": "Minh", "text": "Rất ấn tượng đấy... Nhưng liệu cảm xúc giọng nói có tự nhiên như người thật không?"},
                {"start_sec": 9.8, "end_sec": 14.5, "speaker": "Tuấn", "text": "Chắc chắn rồi! Hệ thống VieNeu-TTS v3 Turbo 48kHz đã xử lý trọn vẹn điều đó."}
            ]
        }
    }
    return pkg


def build_draft_2_bridge_action() -> dict:
    """Test 2: Haru running on Edo wooden bridge, wood crack, slip, rail grab, effort gasp."""
    pkg = {
        "project_id": "v51_draft_2_bridge_action",
        "total_sequence_duration_seconds": 15.0,
        "scene_world": {
            "location_id": "LOC_EDO_WOODEN_BRIDGE",
            "canonical_name": "Cây Cầu Gỗ Phố Cổ Edo Dưới Mưa",
            "architecture_style": "EDO_BRIDGE",
            "weather": "RAIN",
            "threejs_environment": {
                "camera_initial": {"position": [-2.2, 3.8, 5.6], "target": [0.1, 2.7, 0.0], "fov": 42},
                "camera_keyframes": [
                    {"t": 0.0, "position": [-2.2, 3.8, 5.6], "target": [0.1, 2.7, 0.0]},
                    {"t": 4.5, "position": [-1.0, 3.5, 4.4], "target": [0.1, 2.5, 0.0]},
                    {"t": 9.0, "position": [-0.3, 3.2, 3.4], "target": [0.2, 2.3, -0.2]}
                ]
            }
        },
        "actors": [
            {
                "actor_id": "haru",
                "role": "LEAD",
                "dna": {
                    "id": "haru",
                    "name": "Haru",
                    "proportions": {"headRatio": 0.155, "standingHeightPx": 290, "shoulderWidthPx": 50, "limbThicknessPx": 10, "torsoLengthPx": 94, "legLengthPx": 148},
                    "face": {"headContour": "round_youth", "skinTone": "#F5D7B5", "eyeType": "curious_wide", "eyeColor": "#241C16", "eyebrowStyle": "arched", "facialHair": "none"},
                    "hair": {"style": "edo_topknot", "color": "#181412", "accessory": "paper_cord"},
                    "costume": {"archetype": "edo_hanten_courier", "primaryColor": "#345577", "accentColor": "#FFFFFF", "pantsColor": "#283648", "footwear": "waraji_sandals"},
                    "heldProps": {"rightHand": "letter_envelope"}
                },
                "staging": {"initial_world_pos": [-1.4, 2.65, 0.0], "facing": "RIGHT", "posture": "run"},
                "performance_cues": [
                    {"time": 0.0, "pos": [-1.4, 2.65, 0.0], "action": "run", "emotion": "sprint", "facing": 1},
                    {"time": 4.5, "pos": [-0.1, 2.65, 0.0], "action": "slip", "emotion": "fear", "facing": 1},
                    {"time": 8.0, "pos": [0.2, 2.15, 0.0], "action": "hang_from_ledge", "emotion": "relief", "facing": 1}
                ]
            }
        ],
        "storyBeats": [
            {
                "beatId": "BEAT_01",
                "timeRange": [0.0, 5.0],
                "primaryVerb": "run",
                "whatHappens": "Haru ôm chặt phong thư, chạy thục mạng qua cây cầu gỗ dưới cơn mưa tầm tã.",
                "shotType": "WIDE_ESTABLISHING",
                "emotion": "sprint",
                "dialogue": {"speaker": "Haru", "text": "Đến cây cầu bắc qua kênh, tôi nhận ra một vấn đề lớn...", "voiceId": "vieneu-Thiện Minh"}
            },
            {
                "beatId": "BEAT_02",
                "timeRange": [5.0, 9.5],
                "primaryVerb": "slip",
                "whatHappens": "RẮC! Một tấm ván gỗ mục bật tung, Haru trượt ngã nhào suýt rơi xuống dòng nước đen ngòm.",
                "shotType": "CLOSE_UP",
                "emotion": "fear",
                "dialogue": {"speaker": "Haru", "text": "RẮC! Tấm ván dưới chân tôi bật tung! Tôi ngã nhào giữa không trung!", "voiceId": "vieneu-Thiện Minh"}
            },
            {
                "beatId": "BEAT_03",
                "timeRange": [9.5, 15.0],
                "primaryVerb": "hang_from_ledge",
                "whatHappens": "Haru kịp bám chặt một tay vào lan can gỗ, tay kia ghì chặt bức thư khô ráo trước ngực.",
                "shotType": "HEROIC_CLOSE_UP",
                "emotion": "relief",
                "dialogue": {"speaker": "Haru", "text": "Thật kỳ lạ... giữa lúc mạng sống treo trên thanh gỗ mục, tôi chỉ lo: Bức thư có bị ướt không?", "voiceId": "vieneu-Thiện Minh"}
            }
        ],
        "visual_plan": [
            {"type": "LOCATION_DATE_CARD", "content_headline": "CẦU GỖ PHỐ EDO · NĂM 1800", "content_body": "Khoảnh Khắc Sinh Tử Trong Cơn Mưa Bão", "start_time": 0.0, "end_time": 4.5}
        ],
        "voice_timeline": {
            "lines": [
                {"start_sec": 0.5, "end_sec": 4.5, "speaker": "Haru", "text": "Đến cây cầu bắc qua kênh, tôi nhận ra một vấn đề lớn..."},
                {"start_sec": 4.8, "end_sec": 9.2, "speaker": "Haru", "text": "RẮC! Tấm ván dưới chân tôi bật tung! Tôi ngã nhào giữa không trung!"},
                {"start_sec": 9.5, "end_sec": 14.6, "speaker": "Haru", "text": "Thật kỳ lạ... giữa lúc mạng sống treo trên thanh gỗ mục, tôi chỉ lo: Bức thư có bị ướt không?"}
            ]
        }
    }
    return pkg


def build_draft_3_emotional_twist() -> dict:
    """Test 3: Aiko reading letter, paper rustle foley, emotional laughter, comedic twist reveal."""
    pkg = {
        "project_id": "v51_draft_3_emotional_twist",
        "total_sequence_duration_seconds": 15.0,
        "scene_world": {
            "location_id": "LOC_EDO_HOUSE_LANTERN",
            "canonical_name": "Ngôi Nhà Dưới Ánh Đèn Lồng Phố Edo",
            "architecture_style": "EDO_HOUSE",
            "weather": "CLEAR",
            "threejs_environment": {
                "camera_initial": {"position": [0.0, 1.8, 6.2], "target": [0.0, 1.2, 0.0], "fov": 42},
                "camera_keyframes": [
                    {"t": 0.0, "position": [0.0, 1.8, 6.2], "target": [0.0, 1.2, 0.0]},
                    {"t": 5.0, "position": [-0.4, 1.7, 5.0], "target": [0.1, 1.2, 0.0]},
                    {"t": 10.0, "position": [0.4, 1.7, 4.2], "target": [-0.1, 1.2, 0.0]}
                ]
            }
        },
        "actors": [
            {
                "actor_id": "haru",
                "role": "LEAD",
                "dna": {
                    "id": "haru",
                    "name": "Haru",
                    "proportions": {"headRatio": 0.155, "standingHeightPx": 290, "shoulderWidthPx": 50, "limbThicknessPx": 10, "torsoLengthPx": 94, "legLengthPx": 148},
                    "face": {"headContour": "round_youth", "skinTone": "#F5D7B5", "eyeType": "curious_wide", "eyeColor": "#241C16", "eyebrowStyle": "arched", "facialHair": "none"},
                    "hair": {"style": "edo_topknot", "color": "#181412", "accessory": "paper_cord"},
                    "costume": {"archetype": "edo_hanten_courier", "primaryColor": "#345577", "accentColor": "#FFFFFF", "pantsColor": "#283648", "footwear": "waraji_sandals"},
                    "heldProps": {"rightHand": "letter_envelope"}
                },
                "staging": {"initial_world_pos": [-0.75, 0.45, 0.2], "facing": "RIGHT", "posture": "stand"},
                "performance_cues": [
                    {"time": 0.0, "pos": [-0.75, 0.45, 0.2], "action": "present_two_handed", "emotion": "serious", "facing": 1},
                    {"time": 5.0, "pos": [-0.75, 0.45, 0.2], "action": "listen", "emotion": "surprise", "facing": 1},
                    {"time": 10.0, "pos": [-0.75, 0.45, 0.2], "action": "inspect_down", "emotion": "relief", "facing": 1}
                ]
            },
            {
                "actor_id": "aiko",
                "role": "SUPPORT",
                "dna": {
                    "id": "aiko",
                    "name": "Aiko",
                    "proportions": {"headRatio": 0.150, "standingHeightPx": 285, "shoulderWidthPx": 46, "limbThicknessPx": 9, "torsoLengthPx": 92, "legLengthPx": 146},
                    "face": {"headContour": "delicate_heart", "skinTone": "#FFF0E5", "eyeType": "almond_asian", "eyeColor": "#2C1E1A", "eyebrowStyle": "delicate_curved", "facialHair": "none"},
                    "hair": {"style": "edo_shimada", "color": "#1C1D21", "accessory": "golden_kanzashi"},
                    "costume": {"archetype": "edo_kimono_formal", "primaryColor": "#8B1E3F", "accentColor": "#E0A96D", "pantsColor": "#4A1224", "footwear": "tabi_socks"},
                    "heldProps": {"rightHand": "folded_parchment"}
                },
                "staging": {"initial_world_pos": [0.75, 0.45, -0.1], "facing": "LEFT", "posture": "stand"},
                "performance_cues": [
                    {"time": 0.0, "pos": [0.75, 0.45, -0.1], "action": "receive", "emotion": "focused", "facing": -1},
                    {"time": 5.0, "pos": [0.75, 0.45, -0.1], "action": "read", "emotion": "emotional", "facing": -1},
                    {"time": 9.0, "pos": [0.75, 0.45, -0.1], "action": "laugh", "emotion": "happy", "facing": -1}
                ]
            }
        ],
        "storyBeats": [
            {
                "beatId": "BEAT_01",
                "timeRange": [0.0, 5.0],
                "primaryVerb": "present_two_handed",
                "whatHappens": "Haru ướt sũng, trịnh trọng trao bức thư khô ráo bằng hai tay cho Aiko dưới ánh đèn lồng.",
                "shotType": "MEDIUM_SHOT",
                "emotion": "serious",
                "dialogue": {"speaker": "Haru", "text": "Tôi trao thư bằng cả hai tay: Xin thông báo... bức thư vẫn tuyệt đối khô ráo!", "voiceId": "vieneu-Thiện Minh"}
            },
            {
                "beatId": "BEAT_02",
                "timeRange": [5.0, 10.0],
                "primaryVerb": "read",
                "whatHappens": "Aiko mở thư, chăm chú đọc từng dòng, rồi bất ngờ bật cười nắc nẻ.",
                "shotType": "CLOSE_UP",
                "emotion": "emotional",
                "dialogue": {"speaker": "Aiko", "text": "Haha! Anh biết trong thư viết gì không? Nhìn này: Aiko, nhớ mang ô, chiều nay có thể mưa!", "voiceId": "vieneu-Trúc Ly"}
            },
            {
                "beatId": "BEAT_03",
                "timeRange": [10.0, 15.0],
                "primaryVerb": "inspect_down",
                "whatHappens": "Cú chốt twist: Haru ngẩn người nhìn dòng chữ, rồi nhìn xuống chân thấy một chiếc dép đã mất từ lúc qua cầu.",
                "shotType": "HEROIC_CLOSE_UP",
                "emotion": "relief",
                "dialogue": {"speaker": "Haru", "text": "Tôi nhìn đôi dép... một chiếc đã mất từ lúc qua cầu. Đôi khi điều quan trọng nhất là biết thư viết cái gì trước khi mang đi!", "voiceId": "vieneu-Thiện Minh"}
            }
        ],
        "visual_plan": [
            {"type": "LOCATION_DATE_CARD", "content_headline": "NHÀ AIKO · PHỐ CỔ EDO", "content_body": "Cú Chốt Bất Ngờ Của Bức Thư Không Được Phép Ướt", "start_time": 0.0, "end_time": 4.5}
        ],
        "voice_timeline": {
            "lines": [
                {"start_sec": 0.5, "end_sec": 4.6, "speaker": "Haru", "text": "Tôi trao thư bằng cả hai tay: Xin thông báo... bức thư vẫn tuyệt đối khô ráo!"},
                {"start_sec": 5.0, "end_sec": 9.6, "speaker": "Aiko", "text": "Haha! Anh biết trong thư viết gì không? Nhìn này: Aiko, nhớ mang ô, chiều nay có thể mưa!"},
                {"start_sec": 9.9, "end_sec": 14.8, "speaker": "Haru", "text": "Tôi nhìn đôi dép... một chiếc đã mất từ lúc qua cầu. Đôi khi điều quan trọng nhất là biết thư viết cái gì trước khi mang đi!"}
            ]
        }
    }
    return pkg


def render_draft(pkg: dict, draft_num: int, label: str):
    print(f"\n==================================================================")
    print(f"COMPOSING & RENDERING DRAFT {draft_num}: {label}")
    print(f"==================================================================")
    
    # 1. Save Package JSON
    pkg_path = OUTPUT_DIR / f"draft_{draft_num}_package.json"
    pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 2. Compose Multi-Track Master Audio (48kHz stereo with voice ducking)
    audio_director = get_audio_director()
    audio_path = OUTPUT_DIR / f"draft_{draft_num}_master_audio.wav"
    audio_res = audio_director.compose_scene_audio(pkg, pkg["total_sequence_duration_seconds"], audio_path)
    print(f"Master audio composed: {audio_path.name}")
    
    # 3. Render 1080p MP4 via Production Render Service
    mp4_path = OUTPUT_DIR / f"draft_{draft_num}_{pkg['project_id']}.mp4"
    cmd = [
        "node",
        str(ROOT / "scripts" / "production_render_service.mjs"),
        "--package", str(pkg_path),
        "--duration", str(pkg["total_sequence_duration_seconds"]),
        "--audio", str(audio_path),
        "--out", str(mp4_path)
    ]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0 or not mp4_path.exists():
        raise RuntimeError(f"Draft {draft_num} render failed: {res.stderr or res.stdout}")
    
    # 4. Generate Contact Sheet
    contact_path = OUTPUT_DIR / f"draft_{draft_num}_contact.png"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(mp4_path),
        "-vf", "fps=1/1.25,scale=480:-1,tile=4x3",
        "-frames:v", "1",
        str(contact_path)
    ], check=True)
    
    print(f"Draft {draft_num} complete! MP4: {mp4_path.name} ({mp4_path.stat().st_size / (1024*1024):.2f} MB)")
    return mp4_path, contact_path


def main():
    start_all = time.time()
    print("Beginning Authoritative Rendering for all 3 V5.1 Acceptance Drafts...")
    from pipeline.pre_upload_quality_gate import PreUploadQualityGate
    gate = PreUploadQualityGate()
    
    d1_pkg = build_draft_1_cafe_dialogue()
    mp4_1, contact_1 = render_draft(d1_pkg, 1, "Cảnh Đối Thoại (Quán Cà Phê)")
    p1, r1 = gate.run_pre_upload_quality_gate(mp4_1, d1_pkg, sibling_mp4_paths=[])
    if not p1:
        mp4_1.unlink(missing_ok=True)
        raise RuntimeError(f"[QUALITY_GATE_FAILED] Draft 1 failed pre-upload quality gate: {r1}")
    
    d2_pkg = build_draft_2_bridge_action()
    mp4_2, contact_2 = render_draft(d2_pkg, 2, "Cảnh Hành Động (Cầu Gỗ - Haru Suýt Rơi)")
    p2, r2 = gate.run_pre_upload_quality_gate(mp4_2, d2_pkg, sibling_mp4_paths=[mp4_1])
    if not p2:
        mp4_2.unlink(missing_ok=True)
        raise RuntimeError(f"[QUALITY_GATE_FAILED] Draft 2 failed pre-upload quality gate: {r2}")
    
    d3_pkg = build_draft_3_emotional_twist()
    mp4_3, contact_3 = render_draft(d3_pkg, 3, "Cảnh Cảm Xúc & Cú Chốt Hài (Aiko Mở Thư & Mất Dép)")
    p3, r3 = gate.run_pre_upload_quality_gate(mp4_3, d3_pkg, sibling_mp4_paths=[mp4_1, mp4_2])
    if not p3:
        mp4_3.unlink(missing_ok=True)
        raise RuntimeError(f"[QUALITY_GATE_FAILED] Draft 3 failed pre-upload quality gate: {r3}")
    
    total_sec = time.time() - start_all
    print(f"\n==================================================================")
    print(f"ALL 3 DRAFTS RENDERED & CERTIFIED FOR YOUTUBE IN {total_sec:.1f}s!")
    print(f"1. {mp4_1.name}")
    print(f"2. {mp4_2.name}")
    print(f"3. {mp4_3.name}")
    print(f"==================================================================")


if __name__ == "__main__":
    main()
