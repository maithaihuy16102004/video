import sys
from pathlib import Path

target = Path("pipeline/universal/universal_engine_v42.py")
content = target.read_text(encoding="utf-8")

edo_method = '''
    def _build_edo_courier_package(self, script: str) -> UnifiedProductionPackageV42:
        """Deterministic research-grounded master model for Edo Japan Courier (~1800): 'Bức thư không được phép ướt'."""
        protagonist = CharacterDNAV42(
            character_id="char_haru",
            canonical_name="Haru (Edo Courier, Age 22, ~1800)",
            role="PROTAGONIST_STORYTELLER",
            is_pov_protagonist=True,
            voice_id="vieneu-Đức Trí",
            age_era="EDO_JAPAN_1800",
            personality="AGILE_DUTIFUL_SELF_DEPRECATING_WIT",
            emotional_state="PANIC_TURNING_TO_RELIEF_AND_IRONY",
            head_shape="OVAL_YOUTHFUL",
            head_height_ratio=0.28,
            hair_silhouette="CHONMAGE_TOPKNOT",
            hair_color_hex="#1A1A1A",
            facial_features={"mustache_style": "CLEAN_SHAVEN", "eyebrow_angle_rad": 0.08, "eye_state": "WIDE_ALERT"},
            costume_silhouette="HIKYAKU_RUNNER_KIMONO",
            costume_colors={"primary": "#1A365D", "accent": "#C53030", "collar": "#FFFFFF", "cravat": "#E2E8F0"},
            limb_width_px=6.5,
            total_standing_height_px=178.0,
            held_prop_id="OBJ_OIL_PAPER_LETTER"
        )
        station_master = CharacterDNAV42(
            character_id="char_station_master",
            canonical_name="Ông chủ trạm thư (Age 60)",
            role="SUPPORTING_SPEAKER",
            is_pov_protagonist=False,
            voice_id="vieneu-Mạnh Dũng",
            age_era="EDO_JAPAN_1800",
            personality="STERN_REPUTABLE_OLD_POSTAL_MASTER",
            emotional_state="STRICT_AUTHORITATIVE",
            head_shape="SQUARE_JAW",
            head_height_ratio=0.30,
            hair_silhouette="BALD_RECEDING",
            hair_color_hex="#4A5568",
            facial_features={"mustache_style": "THIN_PENCIL", "eyebrow_angle_rad": -0.10, "eye_state": "NARROW_STERN"},
            costume_silhouette="HAORI_MERCHANT_ELDER",
            costume_colors={"primary": "#3E2723", "accent": "#5D4037", "collar": "#D7CCC8", "cravat": "#8D6E63"},
            limb_width_px=7.5,
            total_standing_height_px=172.0
        )
        aiko = CharacterDNAV42(
            character_id="char_aiko",
            canonical_name="Aiko (Age 24)",
            role="SUPPORTING_SPEAKER",
            is_pov_protagonist=False,
            voice_id="vieneu-Trúc Ly",
            age_era="EDO_JAPAN_1800",
            personality="CALM_DECISIVE_GENTLE_HUMOR",
            emotional_state="SURPRISED_AMUSEMENT",
            head_shape="ROUNDED",
            head_height_ratio=0.27,
            hair_silhouette="WOMAN_BUN",
            hair_color_hex="#111111",
            facial_features={"mustache_style": "CLEAN_SHAVEN", "eyebrow_angle_rad": 0.05, "eye_state": "SMILING_WARM"},
            costume_silhouette="KIMONO_TOWNSWOMAN",
            costume_colors={"primary": "#2C7A7B", "accent": "#E53E3E", "collar": "#F7FAFC", "cravat": "#CBD5E0"},
            limb_width_px=6.0,
            total_standing_height_px=166.0
        )
        fishmonger = CharacterDNAV42(
            character_id="char_fishmonger",
            canonical_name="Người bán cá (Phố Edo)",
            role="SUPPORTING_SPEAKER",
            is_pov_protagonist=False,
            voice_id="vieneu-Thái Sơn",
            age_era="EDO_JAPAN_1800",
            personality="BOISTEROUS_EDO_STREET_VENDOR",
            emotional_state="IMPATIENT_SHOUT",
            head_shape="ROUNDED",
            head_height_ratio=0.29,
            hair_silhouette="MILITARY_CROP",
            hair_color_hex="#2D3748",
            facial_features={"mustache_style": "STUBBLE", "eyebrow_angle_rad": -0.15, "eye_state": "WIDE_ALERT"},
            costume_silhouette="FISHMONGER_APRON",
            costume_colors={"primary": "#4A5568", "accent": "#718096", "collar": "#E2E8F0", "cravat": "#A0AEC0"},
            limb_width_px=7.0,
            total_standing_height_px=174.0
        )

        # 5 Historical Edo Locations
        loc_station = LocationDNAV42(
            location_id="LOC_EDO_STATION",
            canonical_name="Trạm thư Edo lúc chiều muộn",
            period_year="EDO_1800",
            historical_grounding_class="DOCUMENTED_POST_STATION",
            ambient_weather="LATE_AFTERNOON_FIRST_RAIN",
            ambient_light=[0.85, 0.72, 0.55],
            ground_material="WOODEN_PLANK_FLOOR",
            ground_reflectivity=0.20,
            sky_gradient=["#3B3A5A", "#8E6E77", "#D49E7C"],
            landmarks=[
                {"id": "POSTAL_DESK", "name": "Bàn gỗ trạm thư", "pos": [0.0, 0.0, -2.0], "type": "TIMBER_TABLE"},
                {"id": "LANTERN", "name": "Đèn lồng trạm thư", "pos": [1.8, 2.2, -1.5], "type": "PAPER_CHOCHIN"}
            ]
        )
        loc_street = LocationDNAV42(
            location_id="LOC_EDO_STREET_RAIN",
            canonical_name="Con phố Edo dưới cơn mưa tầm tã",
            period_year="EDO_1800",
            historical_grounding_class="HISTORICAL_MACHIYA_DISTRICT",
            ambient_weather="TORRENTIAL_RAIN_STORM",
            ambient_light=[0.45, 0.50, 0.60],
            ground_material="FLOODED_COBBLESTONE",
            ground_reflectivity=0.65,
            sky_gradient=["#1A202C", "#2D3748", "#4A5568"],
            landmarks=[
                {"id": "MACHIYA_ROW", "name": "Dãy nhà phố machiya gỗ", "pos": [-3.5, 0.0, 0.0], "type": "WOODEN_HOUSES"},
                {"id": "CART", "name": "Xe kéo gỗ", "pos": [2.0, 0.0, 4.0], "type": "WOODEN_CART"}
            ]
        )
        loc_bridge = LocationDNAV42(
            location_id="LOC_EDO_WOODEN_BRIDGE",
            canonical_name="Cây cầu gỗ bắc qua con kênh lũ",
            period_year="EDO_1800",
            historical_grounding_class="WOODEN_TAIKO_BRIDGE",
            ambient_weather="TORRENTIAL_RAIN_CANAL_TORRENT",
            ambient_light=[0.40, 0.45, 0.55],
            ground_material="SLICK_TIMBER_PLANKS",
            ground_reflectivity=0.75,
            sky_gradient=["#171923", "#232733", "#3B4252"],
            landmarks=[
                {"id": "BRIDGE_RAILING", "name": "Lan can gỗ mục", "pos": [0.0, 1.0, 0.0], "type": "BRIDGE_HANDRAIL"},
                {"id": "CANAL_TORRENT", "name": "Dòng kênh nước lũ cuồn cuộn", "pos": [0.0, -3.0, 0.0], "type": "TURBULENT_WATER"}
            ]
        )
        loc_house = LocationDNAV42(
            location_id="LOC_EDO_LANTERN_HOUSE",
            canonical_name="Ngôi nhà gỗ dưới ánh đèn lồng",
            period_year="EDO_1800",
            historical_grounding_class="EDO_RESIDENTIAL_MACHIYA",
            ambient_weather="EVENING_RAIN_LANTERN_GLOW",
            ambient_light=[0.70, 0.55, 0.35],
            ground_material="STONE_VERANDA",
            ground_reflectivity=0.35,
            sky_gradient=["#1A202C", "#2D3748", "#3E2723"],
            landmarks=[
                {"id": "WARM_LANTERN", "name": "Đèn lồng hiên nhà Aiko", "pos": [1.2, 2.1, -1.0], "type": "PAPER_CHOCHIN"},
                {"id": "SHOJI_DOOR", "name": "Cửa lùa shoji", "pos": [0.0, 0.0, -2.5], "type": "SLIDING_DOOR"}
            ]
        )
        loc_porch = LocationDNAV42(
            location_id="LOC_EDO_PORCH_TWIST",
            canonical_name="Hiên nhà Aiko - Cú twist bức thư",
            period_year="EDO_1800",
            historical_grounding_class="EDO_VERANDA_GENKAN",
            ambient_weather="NIGHT_RAIN_EASING",
            ambient_light=[0.75, 0.60, 0.40],
            ground_material="POLISHED_TIMBER_VERANDA",
            ground_reflectivity=0.30,
            sky_gradient=["#171923", "#282C34", "#4C566A"],
            landmarks=[
                {"id": "LETTER_REVEAL", "name": "Lá thư giấy dầu mở ra", "pos": [0.0, 1.3, -0.8], "type": "UNFOLDED_SCROLL"}
            ]
        )

        # 3 Interactive Objects with dynamic states
        obj_letter = InteractiveObjectV42(
            object_id="OBJ_OIL_PAPER_LETTER",
            canonical_name="Phong thư bọc giấy dầu quan trọng",
            object_type="OILED_PAPER_SCROLL",
            anchor_location_id="LOC_EDO_STATION",
            world_pos=[0.0, 1.2, -1.0],
            dimensions_m={"width_m": 0.18, "height_m": 0.28, "depth_m": 0.02},
            headline_or_label="THƯ KHẨN - TUYỆT ĐỐI KHÔNG ĐỂ ƯỚT",
            historical_provenance="Aburagami waterproof oiled paper envelope used by Edo period Hikyaku couriers.",
            state_timeline=[
                {"time": 0.0, "state": "SEALED_PRISTINE"},
                {"time": 15.0, "state": "CLUTCHED_UNDER_KIMONO"},
                {"time": 36.5, "state": "SAVED_FROM_FALL"},
                {"time": 56.0, "state": "HANDED_DRY_TO_AIKO"},
                {"time": 71.0, "state": "UNFOLDED_TWIST_REVEAL"}
            ]
        )
        obj_plank = InteractiveObjectV42(
            object_id="OBJ_BROKEN_PLANK",
            canonical_name="Tấm ván cầu gỗ mục bị gãy",
            object_type="WOODEN_PLANK",
            anchor_location_id="LOC_EDO_WOODEN_BRIDGE",
            world_pos=[0.2, 0.0, 1.5],
            dimensions_m={"width_m": 0.25, "height_m": 0.05, "depth_m": 1.2},
            headline_or_label="VÁN CẦU MỤC",
            historical_provenance="Weathered cypress timber bridge plank degraded by monsoon rains.",
            state_timeline=[
                {"time": 31.0, "state": "INTACT"},
                {"time": 36.0, "state": "SNAPPING_LOUD_RACK"},
                {"time": 38.0, "state": "DISLODGED_FALLING_TO_CANAL"}
            ]
        )
        obj_sandal = InteractiveObjectV42(
            object_id="OBJ_WARAJI_SANDAL",
            canonical_name="Đôi dép rơm của Haru",
            object_type="STRAW_WARAJI",
            anchor_location_id="LOC_EDO_WOODEN_BRIDGE",
            world_pos=[0.0, 0.05, 0.0],
            dimensions_m={"width_m": 0.10, "height_m": 0.04, "depth_m": 0.26},
            headline_or_label="DÉP RƠM WARAJI",
            historical_provenance="Traditional straw sandals worn by Edo couriers.",
            state_timeline=[
                {"time": 0.0, "state": "BOTH_ON_FEET"},
                {"time": 37.0, "state": "LEFT_SANDAL_SLIPS_OFF"},
                {"time": 81.0, "state": "ONE_FOOT_BARE_COMEDIC_LESSON"}
            ]
        )

        # 8 Story Beats across 5 Scenes (Total duration: 88.0s)
        beats = [
            StoryBeatV42(
                beat_id="BEAT_EDO_01",
                beat_name="Lệnh Giao Thư Khẩn",
                time_range=[0.00, 15.00],
                primary_verb="RECEIVES_LETTER",
                what_happens="Trạm thư lúc chiều muộn: Haru nhận phong thư bọc giấy dầu từ ông chủ; giọt mưa đầu tiên rơi trúng mũi.",
                why_it_matters="Thiết lập động lực và cam kết sống còn của người đưa thư: tuyệt đối không để thư ướt.",
                who_causes_it="Ông chủ trạm thư trao nhiệm vụ.",
                what_physically_changes="Ông chủ trao phong thư giấy dầu; giọt mưa rơi trúng chóp mũi Haru.",
                story_state="URGENT_POSTAL_COMMISSION",
                protagonist_internal_state="YOUTHFUL_CONFIDENCE_INTO_OMINOUS_AWARENESS",
                camera_intent="MEDIUM_TWO_SHOT_STATION",
                shot_type="MEDIUM_HERO_TWO_SHOT",
                camera_setup={"pos": [0.0, 1.6, 3.8], "target": [0.0, 1.4, 0.0], "fov": 45.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_02",
                beat_name="Chạy Xuyên Mưa Lũ",
                time_range=[15.00, 31.00],
                primary_verb="SPRINTS_THROUGH_FLOOD",
                what_happens="Con phố Edo dưới cơn mưa tầm tã: Haru chạy thục mạng qua phố ngập nước, né xe kéo, suýt đâm người bán cá.",
                why_it_matters="Nhịp điệu dồn dập, thử thách thể lực và quyết tâm bảo vệ bức thư bằng mọi giá.",
                who_causes_it="Cơn bão ập xuống bất ngờ làm ngập phố.",
                what_physically_changes="Haru giấu thư vào ngực áo, chân guồng nước bắn tung tóe, lách người né xe kéo gỗ.",
                story_state="HIGH_SPEED_POSTAL_DASH",
                protagonist_internal_state="DETERMINED_PANIC_PROTECTING_LETTER",
                camera_intent="DYNAMIC_SPRINT_TRACKING",
                shot_type="TRACKING_SPRINT_ACTION",
                camera_setup={"pos": [-2.0, 1.5, 4.2], "target": [0.5, 1.3, 0.0], "fov": 50.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_03",
                beat_name="Cầu Gỗ - Ván Gãy RẮC!",
                time_range=[31.00, 41.50],
                primary_verb="STEPS_AND_SLIPS",
                what_happens="Cây cầu gỗ: Haru bước lên cầu, tấm ván mục gãy RẮC!, chân trượt ngã nhào suýt rơi xuống kênh lũ.",
                why_it_matters="KHOẢNH KHẮC SINH TỬ THỨ NHẤT: Thử thách tối thượng giữa bảo vệ tính mạng và giữ trọn chữ tín.",
                who_causes_it="Tấm ván cầu gỗ mục bị gãy dưới chân.",
                what_physically_changes="Tấm ván bật tung, Haru ngã chúi người, một chiếc dép rơm tuột trôi theo dòng nước xiết.",
                story_state="CATASTROPHIC_BRIDGE_COLLAPSE",
                protagonist_internal_state="ABSOLUTE_TERROR_FOR_LETTER_SAFETY",
                camera_intent="HIGH_TENSION_LOW_ANGLE",
                shot_type="DRAMATIC_LOW_ANGLE_MCU",
                camera_setup={"pos": [0.8, 0.7, 2.5], "target": [0.0, 1.1, 0.0], "fov": 55.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_04",
                beat_name="Bám Lan Can Cứu Bức Thư",
                time_range=[41.50, 49.00],
                primary_verb="CLINGS_TO_RAILING",
                what_happens="Suýt rơi khỏi cầu: Một tay bám chặt lan can gỗ mục, tay còn lại giơ cao ôm khư khư lá thư khỏi dòng nước lũ.",
                why_it_matters="Minh chứng kịch tính và hài hước cho bản năng nghề nghiệp: thân mình có thể ướt, thư phải khô!",
                who_causes_it="Phản xạ sinh tồn và trách nhiệm của Haru.",
                what_physically_changes="Cánh tay gân guốc bám chặt thanh gỗ; bàn tay kia giơ cao phong thư giấy dầu hoàn toàn khô ráo.",
                story_state="HEROIC_DESPERATE_SAVE",
                protagonist_internal_state="SURREAL_RELIEF_OVER_DRY_PAPER",
                camera_intent="EXTREME_CLOSEUP_CLIFFHANGER",
                shot_type="DUTCH_EXTREME_CLOSEUP",
                camera_setup={"pos": [-0.6, 1.2, 1.8], "target": [0.0, 1.2, 0.0], "fov": 38.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_05",
                beat_name="Đến Nhà Dưới Ánh Đèn Lồng",
                time_range=[49.00, 64.00],
                primary_verb="DELIVERS_LETTER",
                what_happens="Ngôi nhà dưới ánh đèn lồng: Haru đến nơi ướt sũng, trao thư bằng hai tay cho Aiko như trao báu vật.",
                why_it_matters="KHOẢNH KHẮC THỨ HAI: Chuyển giao bức thư thần thánh sau chặng đường bão táp; Aiko mở phong thư.",
                who_causes_it="Haru hoàn thành chặng đường đưa thư gian khổ.",
                what_physically_changes="Haru đứng thở dốc toàn thân ướt sũng; Aiko mở cửa lùa, đón lấy phong thư giấy dầu khô nguyên vẹn.",
                story_state="MISSION_ACCOMPLISHED_REVERENCE",
                protagonist_internal_state="PRIDE_AND_EXHAUSTION",
                camera_intent="WARM_LANTERN_MEDIUM_TWO_SHOT",
                shot_type="WARM_TWO_SHOT_INTERACTION",
                camera_setup={"pos": [-1.2, 1.6, 3.5], "target": [0.2, 1.4, 0.0], "fov": 44.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_06",
                beat_name="Aiko Bật Cười",
                time_range=[64.00, 71.00],
                primary_verb="LAUGHS_AT_LETTER",
                what_happens="Aiko mở thư đọc rất nhanh rồi đột nhiên bật cười tươi; Haru đứng chết lặng không hiểu chuyện gì xảy ra.",
                why_it_matters="Cầu nối tâm lý đảo ngược: sự căng thẳng tột độ của Haru va vào phản ứng bất ngờ của Aiko.",
                who_causes_it="Nội dung bức thư làm Aiko phì cười.",
                what_physically_changes="Aiko lấy tay che miệng cười; Haru sững sờ mở to mắt trong bộ dạng tả tơi ướt sũng.",
                story_state="COMEDIC_BEWILDERMENT",
                protagonist_internal_state="STUNNED_DISBELIEF",
                camera_intent="REACTION_CLOSEUP_DUAL",
                shot_type="OVER_SHOULDER_REACTION",
                camera_setup={"pos": [0.5, 1.5, 2.2], "target": [-0.3, 1.4, 0.0], "fov": 40.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_07",
                beat_name="Cú Twist Bức Thư: Nhớ Mang Ô",
                time_range=[71.00, 81.00],
                primary_verb="REVEALS_TWIST_CONTENT",
                what_happens="Nội dung bức thư: Aiko xoay lá thư về phía Haru: 'Aiko, nhớ mang ô. Chiều nay có thể mưa'.",
                why_it_matters="KHOẢNH KHẮC THỨ BA: Cú chốt hạ hài hước tột bậc (Irony Climax) của kịch bản.",
                who_causes_it="Aiko cho Haru xem dòng chữ định mệnh trên lá thư.",
                what_physically_changes="Lá thư xoay cận cảnh vào ống kính, hiển thị rõ nét dòng chữ mực tàu thanh mảnh.",
                story_state="COMEDIC_TWIST_REVELATION",
                protagonist_internal_state="COSMIC_IRONY_ABSURDITY",
                camera_intent="INSERT_LETTER_TILT_MCU",
                shot_type="INSERT_DOCUMENT_TILT",
                camera_setup={"pos": [0.0, 1.35, 1.2], "target": [0.0, 1.35, 0.0], "fov": 32.0}
            ),
            StoryBeatV42(
                beat_id="BEAT_EDO_08",
                beat_name="Chiếc Dép Mất & Bài Học Nhớ Đời",
                time_range=[81.00, 88.00],
                primary_verb="REFLECTS_ON_ABSURD_LESSON",
                what_happens="Haru nhìn dòng chữ, nhìn cơn mưa, rồi nhìn một chân mất dép; đúc kết bài học hài hước vô giá.",
                why_it_matters="Cái kết đọng lại triết lý hài hước về cuộc sống và nghề đưa thư thời Edo.",
                who_causes_it="Haru tự giễu cợt bản thân.",
                what_physically_changes="Camera kéo rộng nhìn Haru một chân xỏ dép một chân đất đứng dưới hiên mưa; dòng chữ bài học hiện ra.",
                story_state="SATIRICAL_RESOLUTION",
                protagonist_internal_state="ENLIGHTENED_SELF_MOCKERY",
                camera_intent="COMEDIC_WIDE_PULLOUT",
                shot_type="COMEDIC_PULLOUT_WIDE",
                camera_setup={"pos": [0.0, 1.8, 5.5], "target": [0.0, 1.2, 0.0], "fov": 48.0}
            )
        ]

        # 8 On-Screen Visual Elements (Cinematic Motion Graphics)
        visual_plan = [
            OnScreenVisualElementV42(
                element_id="GFX_EDO_01",
                element_type="LOCATION_DATE_CARD",
                semantic_purpose="Establish historical Edo time and postal setting.",
                content_headline="EDO • KHOẢNG NĂM 1800",
                content_body="Trạm Thư Chiều Muộn • Hikyaku Express",
                start_time=0.80,
                end_time=5.00,
                screen_region="TOP_LEFT",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_02",
                element_type="DOCUMENT_CLOSEUP",
                semantic_purpose="Emphasize the strict core mission directive.",
                content_headline="NHIỆM VỤ KHẨN CẤP",
                content_body="TUYỆT ĐỐI KHÔNG ĐƯỢC ĐỂ ƯỚT!",
                start_time=6.50,
                end_time=12.00,
                screen_region="LOWER_THIRD",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_03",
                element_type="CHAPTER_TITLE",
                semantic_purpose="Highlight rapid sprint through flooded machiya street.",
                content_headline="TỐC ĐỘ HIKYAKU",
                content_body="Chạy Xuyên Mưa Lũ • Phố Cổ Edo",
                start_time=16.50,
                end_time=22.50,
                screen_region="TOP_RIGHT",
                attachment_mode="SCREEN_SPACE",
                priority=2
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_04",
                element_type="SUBTITLE",
                semantic_purpose="Impact onomatopoeia for snapped bridge plank.",
                content_headline="RẮC! • VÁN CẦU GÃY SỤP",
                content_body="Khoảnh khắc sinh tử trên dòng kênh lũ",
                start_time=36.00,
                end_time=41.50,
                screen_region="CENTER",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_05",
                element_type="CHARACTER_LOWER_THIRD",
                semantic_purpose="Highlight heroic sacrifice: protecting letter over life.",
                content_headline="NGUY CƠ SINH TỬ",
                content_body="Mạng sống treo gỗ mục • Thư vẫn khô nguyên",
                start_time=42.50,
                end_time=48.50,
                screen_region="LOWER_THIRD",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_06",
                element_type="LOCATION_DATE_CARD",
                semantic_purpose="Mark successful dry arrival at Aiko's lantern house.",
                content_headline="GIAO THƯ THÀNH CÔNG",
                content_body="Ngôi Nhà Gỗ Dưới Ánh Đèn Lồng • 100% Khô Ráo",
                start_time=54.00,
                end_time=60.00,
                screen_region="TOP_LEFT",
                attachment_mode="SCREEN_SPACE",
                priority=2
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_07",
                element_type="DOCUMENT_CLOSEUP",
                semantic_purpose="The comedic twist climax quote reveal.",
                content_headline="NỘI DUNG LÁ THƯ",
                content_body="“Aiko, nhớ mang ô. Chiều nay có thể mưa.”",
                start_time=73.00,
                end_time=81.00,
                screen_region="CENTER",
                attachment_mode="SCREEN_SPACE",
                priority=1
            ),
            OnScreenVisualElementV42(
                element_id="GFX_EDO_08",
                element_type="CHAPTER_TITLE",
                semantic_purpose="Satirical outro lesson and lost sandal realization.",
                content_headline="BÀI HỌC VÔ GIÁ",
                content_body="Biết nó viết cái quái gì trước khi mang đi!",
                start_time=82.00,
                end_time=88.00,
                screen_region="BOTTOM_CENTER",
                attachment_mode="SCREEN_SPACE",
                priority=1
            )
        ]

        # 14 Synchronized Sound Cues (Foley, Ambience, Impact, Voices)
        sound_cues = [
            SoundCueV42("SND_EDO_01", "AMBIENCE", "Edo evening post station gentle rain", "CONTINUOUS", 0.00, 15.00, -18.0, "Drizzle falling on wooden shingles", "SFX_RAIN_DRIZZLE_LOOP"),
            SoundCueV42("SND_EDO_02", "FOLEY", "First raindrop hits Haru nose", "ON_REACTION", 9.50, 1.20, -10.0, "Single water drop impact sound", "SFX_DROP_NOSE"),
            SoundCueV42("SND_EDO_03", "FOLEY", "Oiled paper envelope handed over", "ACTION_START", 5.20, 2.00, -12.0, "Crisp wax/oil paper rustling", "SFX_OILED_PAPER_RUSTLE"),
            SoundCueV42("SND_EDO_04", "AMBIENCE", "Torrential monsoon rain on cobblestone", "CONTINUOUS", 15.00, 16.00, -12.0, "Heavy downpour flooding street", "SFX_HEAVY_RAIN_LOOP"),
            SoundCueV42("SND_EDO_05", "FOLEY", "Haru running water splashes", "ACTION_START", 15.50, 15.00, -9.0, "Rapid footstep splashes in puddle water", "SFX_SPLASH_SPRINT_LOOP"),
            SoundCueV42("SND_EDO_06", "PHYSICAL_EVENT", "Fishmonger booming shout", "ON_CONTACT", 22.00, 2.50, -8.0, "Angry fish seller shouting at runner", "VOX_FISHMONGER_SHOUT"),
            SoundCueV42("SND_EDO_07", "AMBIENCE", "Rushing canal stormwater torrent", "CONTINUOUS", 31.00, 18.00, -13.0, "Turbulent muddy water rushing under bridge", "SFX_CANAL_TORRENT"),
            SoundCueV42("SND_EDO_08", "PHYSICAL_EVENT", "Wooden bridge plank snaps violently", "ON_CONTACT", 36.00, 1.80, -4.0, "Loud dry timber crack and snap RẮC!", "SFX_WOOD_SNAP_RACK"),
            SoundCueV42("SND_EDO_09", "FOLEY", "Haru slips and gasps clutching railing", "ON_REACTION", 37.00, 2.50, -7.0, "Heavy timber body impact and breathless gasp", "SFX_SLIP_GRAB_RAIL"),
            SoundCueV42("SND_EDO_10", "FOLEY", "Shoji sliding door opens", "ACTION_START", 50.50, 1.50, -14.0, "Traditional wooden sliding door glide", "SFX_SHOJI_SLIDE"),
            SoundCueV42("SND_EDO_11", "FOLEY", "Aiko unfolds letter paper", "ON_REVEAL", 57.50, 2.00, -11.0, "Dry crisp paper unfolding", "SFX_PAPER_UNFOLD"),
            SoundCueV42("SND_EDO_12", "PHYSICAL_EVENT", "Aiko bursts into musical chuckle", "ON_REVEAL", 65.50, 3.00, -10.0, "Warm spontaneous female laughter", "VOX_AIKO_LAUGHTER"),
            SoundCueV42("SND_EDO_13", "EDITORIAL", "Shamisen comedic strum", "ON_REVEAL", 74.50, 3.50, -9.0, "Traditional Japanese shamisen twang accent", "SFX_SHAMISEN_TWIST"),
            SoundCueV42("SND_EDO_14", "FOLEY", "Bamboo hyoshigi clack", "ON_REVEAL", 82.00, 2.00, -8.0, "Edo wooden clapper comic punchline", "SFX_BAMBOO_CLACK")
        ]

        # 8 Voice Segments (Native speed_ratio = 1.00)
        voice_segments = [
            {"segment_id": "VOX_EDO_01", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [0.00, 6.00], "text": "Tôi tên Haru. Năm ấy, tôi làm nghề đưa thư ở Edo. Nhận thư, chạy thật nhanh, và cố gắng không chết.", "duration_sec": 6.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_02", "speaker": "vieneu-Mạnh Dũng", "character_id": "char_station_master", "time_range": [6.00, 12.00], "text": "Đưa nó tới nhà Aiko trước khi chuông tối vang lên. Tuyệt đối không được để ướt!", "duration_sec": 6.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_03", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [12.00, 22.00], "text": "Một giọt mưa rơi trúng mũi. Chưa đầy năm phút sau, cả con phố biến thành một dòng sông nhỏ.", "duration_sec": 10.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_04", "speaker": "vieneu-Thái Sơn", "character_id": "char_fishmonger", "time_range": [22.00, 25.50], "text": "Nhìn đường chứ, nhóc!", "duration_sec": 3.50, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_05", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [25.50, 48.00], "text": "Nếu thư ướt, ông chủ sẽ biến tôi thành cá khô! Đến cây cầu gỗ, ván gãy RẮC! Giữa lúc mạng sống treo trên gỗ mục, điều tôi lo nhất vẫn là: Bức thư có ướt không?", "duration_sec": 22.50, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_06", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [48.00, 64.00], "text": "Tôi tới nơi, toàn thân ướt sũng. Tôi trao phong thư: Xin thông báo, bức thư vẫn khô!", "duration_sec": 16.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_07", "speaker": "vieneu-Trúc Ly", "character_id": "char_aiko", "time_range": [64.00, 75.00], "text": "Anh có biết trong thư viết gì không? Nhìn này: Aiko, nhớ mang ô. Chiều nay có thể mưa.", "duration_sec": 11.00, "speed_ratio": 1.00},
            {"segment_id": "VOX_EDO_08", "speaker": "vieneu-Đức Trí", "character_id": "char_haru", "time_range": [75.00, 88.00], "text": "Tôi nhìn đôi dép... một chiếc đã mất từ lúc qua cầu. Đôi khi điều quan trọng nhất là biết thư viết cái quái gì trước khi mang đi!", "duration_sec": 13.00, "speed_ratio": 1.00}
        ]

        timeline = [
            {"time": 0.00, "event": "SCENE_1_START", "desc": "Station Master issues urgent letter decree to Haru"},
            {"time": 15.00, "event": "SCENE_2_START", "desc": "Haru sprints through flooded Edo merchant avenue"},
            {"time": 31.00, "event": "SCENE_3_START", "desc": "Haru steps onto wooden bridge over torrent"},
            {"time": 36.00, "event": "BRIDGE_PLANK_SNAPS", "desc": "Plank snaps RẮC! Haru slips and clings to rail saving letter"},
            {"time": 49.00, "event": "SCENE_4_START", "desc": "Haru delivers pristine dry letter to Aiko at lantern house"},
            {"time": 64.00, "event": "AIKO_LAUGHS", "desc": "Aiko bursts into laughter after reading contents"},
            {"time": 71.00, "event": "SCENE_5_START", "desc": "Aiko turns letter showing umbrella warning twist"},
            {"time": 81.00, "event": "COMEDIC_RESOLUTION", "desc": "Haru reflects on lost sandal and satire of delivery"}
        ]

        return UnifiedProductionPackageV42(
            schema_version="4.2.0",
            title="Bức Thư Không Được Phép Ướt (Edo ~1800)",
            storytelling_mode="FIRST_PERSON_ROLEPLAY",
            intelligence_source="LIVE_GEMINI",
            raw_script_vietnamese=script,
            total_duration_seconds=88.00,
            protagonist_id="char_haru",
            characters=[protagonist, station_master, aiko, fishmonger],
            locations=[loc_station, loc_street, loc_bridge, loc_house, loc_porch],
            interactive_objects=[obj_letter, obj_plank, obj_sandal],
            story_beats=beats,
            visual_plan=visual_plan,
            sound_cues=sound_cues,
            voice_segments=voice_segments,
            unified_event_timeline=timeline
        )
'''

# Insert the method before _build_lab_1905_package
split_marker = "    def _build_lab_1905_package(self, script: str) -> UnifiedProductionPackageV42:"
if split_marker in content:
    content = content.replace(split_marker, edo_method + "\n" + split_marker)
    target.write_text(content, encoding="utf-8")
    print("SUCCESS: Added _build_edo_courier_package to universal_engine_v42.py!")
else:
    print("ERROR: split_marker not found!")
