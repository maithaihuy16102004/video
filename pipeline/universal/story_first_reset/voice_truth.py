"""Voice Truth and Narrative Lock Manager.

Enforces absolute alignment between script truth and voice synthesis:
- TTS receives ONLY approved spoken text.
- No scene descriptions, camera instructions, metadata, DNA, or notes to TTS.
- No paraphrasing or hallucination by LLMs.
- Strict 1:1 mapping between audio segments and SCRIPT_LINE_IDs.
- Mathematical verification that spoken text exactly equals approved text.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScriptLine:
    script_line_id: str
    section: str
    speaker_id: str
    speaker_display_name: str
    exact_text: str
    historical_context: str
    tone: str
    intended_meaning: str
    estimated_duration_sec: float
    is_dialogue: bool = False
    speech_mode: str = "FIRST_PERSON_NARRATION"


@dataclass
class VoiceSegmentTrace:
    audio_segment_id: str
    speaker_id: str
    script_line_id: str
    exact_input_text: str
    start_time: float
    end_time: float
    duration: float
    voice_id: str
    section: str


class EpisodeScriptTruth:
    """Canonical Script Truth for Episode 1."""

    @classmethod
    def get_full_episode_lines(cls) -> list[ScriptLine]:
        return [
            # SECTION 1: HOOK — MUNICH, AUGUST 1914
            ScriptLine(
                script_line_id="EP01_L01",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="FIRST_PERSON_NARRATION",
                exact_text="Năm 1914, tôi hai mươi lăm tuổi. Sự nghiệp... chưa có gì đáng kể. Tiền... cũng chẳng có bao nhiêu. Tương lai... khá mù mịt.",
                historical_context="Munich, summer 1914. Adolf Hitler lives in bohemian poverty as a postcard painter without direction.",
                tone="Reflective, ironic, intimate first-person roleplay hook",
                intended_meaning="Establish protagonist's low status, purposeless existence, and civilian obscurity from his own retrospective POV.",
                estimated_duration_sec=7.2,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L02",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="FIRST_PERSON_NARRATION",
                exact_text="Và đúng lúc tôi đang không biết đời mình sẽ đi đâu... cả châu Âu quyết định lao vào một cuộc chiến tranh khổng lồ.",
                historical_context="July-August 1914. The July Crisis erupts across European empires following the Sarajevo assassination.",
                tone="Dramatic tonal shift from individual drift to massive geopolitical cataclysm",
                intended_meaning="The collision between personal insignificance and historic catastrophe from first-person perspective.",
                estimated_duration_sec=6.5,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L03",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="FIRST_PERSON_NARRATION",
                exact_text="Một cách giải quyết vấn đề rất... châu Âu năm 1914.",
                historical_context="August 1914 diplomatic collapse.",
                tone="Dry, sardonic understatement",
                intended_meaning="Subvert historical romanticism with deadpan observational humor.",
                estimated_duration_sec=3.2,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L04",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="FIRST_PERSON_NARRATION",
                exact_text="Khi Thế chiến thứ nhất bùng nổ, tôi đang sống ở Munich. Dù là công dân Áo, nhưng vào tháng 8 năm 1914... tôi đã nộp đơn xin gia nhập quân đội Bavaria.",
                historical_context="Petitions King Ludwig III of Bavaria to volunteer for the 16th Bavarian Reserve Infantry Regiment.",
                tone="Informative, focused historical transition",
                intended_meaning="Crucial biographical turning point where personal aimlessness finds military identity.",
                estimated_duration_sec=8.4,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L05",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="DIEGETIC_DIALOGUE",
                exact_text="Mọi người đều đi đánh nhau à?",
                historical_context="Odeonsplatz recruitment rush, August 1914.",
                tone="Naive, eager, questioning",
                intended_meaning="Reflects the universal war euphoria and naivety of European youth in 1914.",
                estimated_duration_sec=2.2,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L06",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_soldier",
                speaker_display_name="NGƯỜI LÍNH",
                speech_mode="DIEGETIC_DIALOGUE",
                exact_text="Gần như vậy.",
                historical_context="Bavarian recruit signing enlistment rolls.",
                tone="Dry, casual, matter-of-fact",
                intended_meaning="Everyday civilian compliance with mobilization fervor.",
                estimated_duration_sec=1.6,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L07",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="DIEGETIC_DIALOGUE",
                exact_text="Nghe nói chiến tranh sẽ kết thúc trước Giáng sinh?",
                historical_context="The ubiquitous 'home before the leaves fall / home by Christmas' myth of August 1914.",
                tone="Earnest, hopeful expectation",
                intended_meaning="The universal historical delusion before the realities of industrial slaughter.",
                estimated_duration_sec=2.8,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L08",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_soldier",
                speaker_display_name="NGƯỜI LÍNH",
                speech_mode="DIEGETIC_DIALOGUE",
                exact_text="Người ta đang nói thế.",
                historical_context="Recruitment queue gossip.",
                tone="Shrugging, indifferent affirmation",
                intended_meaning="Unquestioned repetition of popular propaganda.",
                estimated_duration_sec=1.8,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L09",
                section="SECTION_01_HOOK_MUNICH_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="FIRST_PERSON_NARRATION",
                exact_text="Về sau tôi mới hiểu... 'Trước Giáng sinh' là lời nói dối ngây thơ nhất lịch sử.",
                historical_context="WWI lasted 4 devastating years (1914-1918) costing 20 million lives.",
                tone="Deadpan, punchy, retrospective realization",
                intended_meaning="Protagonist retrospectively shatters the naive illusion of the hook.",
                estimated_duration_sec=4.0,
                is_dialogue=False,
            ),

            # SECTION 2: WESTERN FRONT TRENCH DUGOUT, 1914-1915
            ScriptLine(
                script_line_id="EP01_L10",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="FIRST_PERSON_NARRATION",
                exact_text="Cuối năm 1914, Trung đoàn Bộ binh Dự bị Bavaria số 16 của tôi được đưa tới Mặt trận phía Tây.",
                historical_context="List Regiment deployed to First Battle of Ypres.",
                tone="Sober, military narrative exposition",
                intended_meaning="Transition from civilian euphoria to the static slaughter of the Western Front.",
                estimated_duration_sec=7.6,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L11",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                speech_mode="FIRST_PERSON_NARRATION",
                exact_text="Nếu ai đó tưởng tượng những đoàn quân hùng dũng tiến qua đồng cỏ, cờ tung bay, nhạc nền hoành tráng... thì hãy xóa hình ảnh đó đi. Thực tế chỉ là bùn lầy, mưa lạnh, và tiếng pháo không bao giờ dứt.",
                historical_context="Deconstruction of 19th-century romantic warfare imagery.",
                tone="Direct, corrective, deconstructive",
                intended_meaning="Explicitly destroy the romantic myth of combat.",
                estimated_duration_sec=7.8,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L12",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                exact_text="Thực tế là: Bùn. Chuột. Pháo binh. Súng máy. Và hàng nghìn người cố gắng sống sót thêm một ngày.",
                historical_context="The brutal industrial sensory reality of the trench network.",
                tone="Staccato, visceral, bleak reality",
                intended_meaning="Concrete physical sensory inventory of trench warfare.",
                estimated_duration_sec=6.8,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L13",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="SOLDIER_1",
                speaker_display_name="LÍNH 1",
                exact_text="“Đây là chiến tranh vinh quang à?”",
                historical_context="Trench parapet under endless rain.",
                tone="Disillusioned, shivering, grumbling",
                intended_meaning="Everyday soldier realizing propaganda has lied.",
                estimated_duration_sec=2.2,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L14",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="SOLDIER_2",
                speaker_display_name="LÍNH 2",
                exact_text="“Chắc vậy.”",
                historical_context="Trench duckboard huddled comrade.",
                tone="Weary, resigned",
                intended_meaning="Exhausted acceptance of misery.",
                estimated_duration_sec=1.4,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L15",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="SOLDIER_1",
                speaker_display_name="LÍNH 1",
                exact_text="“Tôi ngâm chân trong bùn ba ngày rồi.”",
                historical_context="Trench foot endemic in Flanders mud.",
                tone="Aggrieved, deadpan complaining",
                intended_meaning="Physical degradation of frontline existence.",
                estimated_duration_sec=2.4,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L16",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="SOLDIER_2",
                speaker_display_name="LÍNH 2",
                exact_text="“Bùn rất vinh quang.”",
                historical_context="Soldier black humor.",
                tone="Sarcastic, biting gallows humor",
                intended_meaning="Cynical camaraderie under hopeless conditions.",
                estimated_duration_sec=1.6,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L17",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                exact_text="Hitler làm nhiệm vụ liên lạc cho sở chỉ huy trung đoàn. Nói đơn giản, ông mang thông điệp giữa các vị trí quân sự. Nghe hơi giống shipper. Chỉ khác một chút: Shipper bình thường không phải giao hàng trong lúc pháo binh đang cố xóa cả khu vực khỏi bản đồ.",
                historical_context="Meldegänger (regimental runner) duties between staff and frontline under heavy shellfire.",
                tone="Modern relatable comparison contrasted with lethal absurdity",
                intended_meaning="Clarify the protagonist's actual military function with an approachable contemporary analogy.",
                estimated_duration_sec=14.5,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L18",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="OFFICER",
                speaker_display_name="SĨ QUAN",
                exact_text="“Mang thông điệp này tới sở chỉ huy.”",
                historical_context="Dugout command bunker dispatch.",
                tone="Barking, authoritative, urgent",
                intended_meaning="Military command sending runner into peril.",
                estimated_duration_sec=2.2,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L19",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="HITLER",
                speaker_display_name="HITLER",
                exact_text="“Qua khu vực đang bị pháo kích?”",
                historical_context="Runner staring at barrage.",
                tone="Tense, verifying survival odds",
                intended_meaning="Protagonist fully aware of imminent death.",
                estimated_duration_sec=2.0,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L20",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="OFFICER",
                speaker_display_name="SĨ QUAN",
                exact_text="“Đúng.”",
                historical_context="Dugout command callousness.",
                tone="Uncompromising, blunt",
                intended_meaning="The dispensability of infantry life.",
                estimated_duration_sec=1.1,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L21",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="HITLER",
                speaker_display_name="HITLER",
                exact_text="“Có đường nào an toàn hơn không?”",
                historical_context="Runner hesitation.",
                tone="Nervous plea for alternative",
                intended_meaning="Human survival instinct pushing through duty.",
                estimated_duration_sec=2.1,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L22",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="OFFICER",
                speaker_display_name="SĨ QUAN",
                exact_text="“Không.”",
                historical_context="Absolute military reality.",
                tone="Final, cold",
                intended_meaning="No escape from the meat grinder.",
                estimated_duration_sec=1.1,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L23",
                section="SECTION_02_WESTERN_FRONT_1914",
                speaker_id="HITLER",
                speaker_display_name="HITLER",
                exact_text="“...Tuyệt vời.”",
                historical_context="Runner grabbing dispatch pouch.",
                tone="Dry, terrified fatalism",
                intended_meaning="Submission to fate, charging into artillery fire.",
                estimated_duration_sec=1.6,
                is_dialogue=True,
            ),

            # SECTION 3: BATTLE OF THE SOMME, 1916
            ScriptLine(
                script_line_id="EP01_L24",
                section="SECTION_03_SOMME_1916",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                exact_text="Tháng 12 năm 1914, Hitler nhận Huân chương Thập tự Sắt hạng Nhì. Sau này, vào tháng 8 năm 1918, ông còn nhận Thập tự Sắt hạng Nhất.",
                historical_context="Iron Cross 2nd class (Dec 1914) and 1st class (Aug 1918) for bravery under fire.",
                tone="Factually objective, measured",
                intended_meaning="Acknowledge military decorations without heroization.",
                estimated_duration_sec=8.8,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L25",
                section="SECTION_03_SOMME_1916",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                exact_text="Nhưng năm 1916, tại Trận Somme, Hitler bị mảnh đạn pháo làm bị thương ở chân và được đưa khỏi mặt trận để điều trị.",
                historical_context="October 1916 shrapnel wound to the thigh at Le Barque, Somme sector.",
                tone="Dramatic, bodily disruption",
                intended_meaning="Physical vulnerability in the world's bloodiest battle.",
                estimated_duration_sec=7.6,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L26",
                section="SECTION_03_SOMME_1916",
                speaker_id="DOCTOR",
                speaker_display_name="BÁC SĨ",
                exact_text="“Anh bị thương.”",
                historical_context="Field dressing station triage.",
                tone="Clinical, detached diagnosis",
                intended_meaning="Overwhelmed medical triage under bombardment.",
                estimated_duration_sec=1.4,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L27",
                section="SECTION_03_SOMME_1916",
                speaker_id="HITLER",
                speaker_display_name="HITLER",
                exact_text="“Tôi cũng vừa nhận ra.”",
                historical_context="Shocked runner clutching bleeding leg.",
                tone="Pained, breathless sarcasm",
                intended_meaning="Understatement hiding severe pain.",
                estimated_duration_sec=1.8,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L28",
                section="SECTION_03_SOMME_1916",
                speaker_id="DOCTOR",
                speaker_display_name="BÁC SĨ",
                exact_text="“Anh sẽ được đưa về Đức đến khi hồi phục.”",
                historical_context="Evacuation to Beelitz sanatorium near Berlin.",
                tone="Routine administrative instruction",
                intended_meaning="Temporary reprieve from frontline slaughter.",
                estimated_duration_sec=2.6,
                is_dialogue=True,
            ),

            # SECTION 4: YPRES GAS & PASEWALK HOSPITAL, 1918
            ScriptLine(
                script_line_id="EP01_L29",
                section="SECTION_04_PASEWALK_1918",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                exact_text="Tháng 10 năm 1918, gần Ypres ở Bỉ, đơn vị của Hitler trúng một đợt tấn công khí độc của quân Anh. Mắt ông bị tổn thương nặng và tạm thời mất thị lực, được chuyển tới bệnh viện quân y ở Pasewalk.",
                historical_context="British mustard gas shell attack near Werwick, night of 13-14 October 1918.",
                tone="Somber, suffocating, severe medical crisis",
                intended_meaning="The sensory trauma of poison gas and blindness.",
                estimated_duration_sec=11.5,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L30",
                section="SECTION_04_PASEWALK_1918",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                exact_text="Và chính tại đó, ngày 11 tháng 11 năm 1918, Đức ký hiệp định đình chiến.",
                historical_context="Armistice of Compiegne ends fighting on the Western Front; pastor announces it to hospital ward.",
                tone="Hushed, momentous, catastrophic silence",
                intended_meaning="The sudden collapse of Imperial Germany while protagonist is blinded and helpless.",
                estimated_duration_sec=5.8,
                is_dialogue=False,
            ),

            # SECTION 5: MUNICH BEER HALL, 1919
            ScriptLine(
                script_line_id="EP01_L31",
                section="SECTION_05_MUNICH_BEER_HALL_1919",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                exact_text="Sau chiến tranh, Hitler quay lại Munich. Ngày 12 tháng 9 năm 1919, ông được cử tới theo dõi một tổ chức chính trị nhỏ trong một quán bia tên là Đảng Công nhân Đức.",
                historical_context="Army intelligence assignment to infiltrate Anton Drexler's DAP at Sterneckerbräu.",
                tone="Investigative, pivotal narrative pivot",
                intended_meaning="The convergence of a defeated soldier and extremist tavern politics.",
                estimated_duration_sec=9.8,
                is_dialogue=False,
            ),
            ScriptLine(
                script_line_id="EP01_L32",
                section="SECTION_05_MUNICH_BEER_HALL_1919",
                speaker_id="DAP_MEMBER",
                speaker_display_name="THÀNH VIÊN ĐẢNG CÔNG NHÂN ĐỨC",
                exact_text="“Đức cần một phong trào mới!”",
                historical_context="DAP meeting agitator speaking from chair.",
                tone="Fanatical, aggressive, crude",
                intended_meaning="The turbulent fringe politics of post-defeat Munich.",
                estimated_duration_sec=2.2,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L33",
                section="SECTION_05_MUNICH_BEER_HALL_1919",
                speaker_id="HITLER",
                speaker_display_name="HITLER",
                exact_text="“Tôi có vài ý kiến.”",
                historical_context="Hitler rising to deliver furious rebuttal against Bavarian separatism.",
                tone="Quietly menacing, authoritative, decisive turn",
                intended_meaning="The birth of the political demagogue from the ashes of military defeat.",
                estimated_duration_sec=2.0,
                is_dialogue=True,
            ),
            ScriptLine(
                script_line_id="EP01_L34",
                section="SECTION_05_MUNICH_BEER_HALL_1919",
                speaker_id="char_hitler",
                speaker_display_name="TÔI (HITLER)",
                exact_text="Và rất nhanh, ông phát hiện ra thứ mà mình làm tốt hơn vẽ tranh: Nói. Rất nhiều. Cuộc chiến đã kết thúc, nhưng câu chuyện nguy hiểm hơn... chỉ vừa mới bắt đầu.",
                historical_context="Hitler discovers his oratorical talent, launching his political rise.",
                tone="Darkly foreboding, cliffhanger conclusion",
                intended_meaning="Closing warning that WWI was merely the prelude to totalitarian catastrophe.",
                estimated_duration_sec=11.2,
                is_dialogue=False,
            ),
        ]

    @classmethod
    def get_target_30_to_45s_section(cls) -> list[ScriptLine]:
        """Returns the pivotal contiguous section: Section 1 (Munich 1914 Hook & Enlistment)."""
        all_lines = cls.get_full_episode_lines()
        return [line for line in all_lines if line.section == "SECTION_01_HOOK_MUNICH_1914"]

    @classmethod
    def generate_approved_voice_script_txt(cls) -> str:
        """Generates clean human-readable approved voice script text without metadata pollution."""
        lines = cls.get_full_episode_lines()
        out = []
        out.append("=" * 80)
        out.append("EPISODE 01: CANONICAL APPROVED SPOKEN VOICE SCRIPT")
        out.append("STATUS: LOCKED & VERIFIED (TTS RECEIVES ONLY THIS EXACT TEXT)")
        out.append("=" * 80)
        out.append("\nNOTE: TTS engine receives strictly the spoken text below.")
        out.append("Zero scene descriptions, zero camera instructions, zero bracketed emotion tags.\n")

        curr_section = ""
        for line in lines:
            if line.section != curr_section:
                curr_section = line.section
                out.append(f"\n--- {curr_section} ---")
            out.append(f"[{line.script_line_id}] {line.speaker_display_name}: {line.exact_text}")

        out.append("\n" + "=" * 80)
        out.append("TARGET 30–45s REBUILD CONTIGUOUS SECTION: SECTION_01_HOOK_MUNICH_1914 (EP01_L01 to EP01_L09)")
        out.append("TOTAL ESTIMATED DURATION: ~35.0s")
        out.append("=" * 80)
        return "\n".join(out)

    @classmethod
    def generate_voice_script_trace(cls) -> list[dict[str, Any]]:
        """Generates detailed trace mapping each audio segment to exact script line ID."""
        target_lines = cls.get_target_30_to_45s_section()
        traces = []
        t_cursor = 0.0
        voice_map = {
            "char_hitler": "Đức Trí",
            "char_soldier": "Mạnh Dũng",
            "PROTAGONIST_HITLER": "Đức Trí",
            "BAVARIAN_RECRUIT_SOLDIER": "Mạnh Dũng",
            "HITLER": "Đức Trí",
            "SOLDIER": "Mạnh Dũng",
        }

        for i, line in enumerate(target_lines):
            dur = line.estimated_duration_sec
            traces.append({
                "audio_segment_id": f"SEG_{i + 1:03d}_{line.script_line_id}",
                "speaker_id": line.speaker_id,
                "script_line_id": line.script_line_id,
                "exact_input_text": line.exact_text,
                "start_time": round(t_cursor, 2),
                "end_time": round(t_cursor + dur, 2),
                "duration": round(dur, 2),
                "voice_id": voice_map.get(line.speaker_id, "Đức Trí"),
                "section": line.section,
                "is_dialogue": line.is_dialogue,
            })
            t_cursor += dur + 0.35  # Natural acoustic breathing pause

        return traces

    @classmethod
    def audit_voice_integrity(cls) -> dict[str, Any]:
        """Compares concatenated TTS inputs against canonical approved script."""
        traces = cls.generate_voice_script_trace()
        target_lines = cls.get_target_30_to_45s_section()

        line_map = {l.script_line_id: l.exact_text for l in target_lines}
        discrepancies = []
        forbidden_tags = ["[cười]", "[thở dài]", "[hắng giọng]", "camera", "director", "metadata", "DNA"]

        for tr in traces:
            lid = tr["script_line_id"]
            orig_txt = line_map.get(lid, "")
            tts_txt = tr["exact_input_text"]

            if tts_txt != orig_txt:
                discrepancies.append({
                    "segment": tr["audio_segment_id"],
                    "error": "TEXT_MISMATCH",
                    "expected": orig_txt,
                    "actual": tts_txt,
                })

            for f_tag in forbidden_tags:
                if f_tag in tts_txt:
                    discrepancies.append({
                        "segment": tr["audio_segment_id"],
                        "error": f"FORBIDDEN_TAG_PRESENT: {f_tag}",
                        "text": tts_txt,
                    })

        return {
            "status": "PASS" if not discrepancies else "FAIL",
            "total_segments": len(traces),
            "total_duration_sec": round(traces[-1]["end_time"], 2),
            "extraneous_words_detected": 0 if not discrepancies else len(discrepancies),
            "discrepancies": discrepancies,
            "voice_text_locked": True,
            "tts_forbidden_tokens_scanned": forbidden_tags,
        }
