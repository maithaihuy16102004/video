"""Three Representative Scene Blueprints for the Real Gemini Pixel Test.

Scenes:
- SCENE A: WWI trench environment (GROUND_LEVEL / DEEP_PERSPECTIVE)
- SCENE B: Period hospital/infirmary interior (OTS / MEDIUM-WIDE)
- SCENE C: Munich historical street/public square (LOW_ANGLE / MONUMENTAL)

Preserves original Vietnamese narration for TTS, while generating
rigorous English visual prompts adhering to the 17-tier specification.
"""
from __future__ import annotations

from .blueprint import (
    AtmosphereSpec,
    CameraSpec,
    CharacterSpec,
    CompositionSpec,
    ContinuitySpec,
    CreativeFreedom,
    EnvironmentSpec,
    HistorySpec,
    LightingSpec,
    PerspectiveSpec,
    ReservedZone,
    SceneBlueprint,
    StorySpec,
)


def create_three_real_scenes() -> list[SceneBlueprint]:
    scenes: list[SceneBlueprint] = []

    # -------------------------------------------------------------------------
    # SCENE A: WWI Trench Environment (Ground-Level Deep Corridor)
    # -------------------------------------------------------------------------
    scenes.append(
        SceneBlueprint(
            scene_id="SCENE_A_TRENCH",
            shot_id="SC_A_SH01_TRENCH_GROUND",
            story=StorySpec(
                narration="Ống kính đặt sát mặt bùn lầy chiến hào, nơi từng giọt mưa và vỏ đạn rải rác kể lại nỗi kinh hoàng của chiến sự.",
                previous_beat="Heavy artillery barrage subsides over Flanders sector.",
                current_beat="Visceral aftermath at ground level: mud, water reflections, spent cartridges.",
                next_beat="Infantryman peers cautiously over the parapet berm.",
                purpose="VISCERAL_GROUNDED_WARFARE",
                emotion="CLAUSTROPHOBIC_DREAD",
            ),
            history=HistorySpec(
                year=1916,
                location_id="western_front_trench",
                country="France / Flanders border",
                event_context="Static trench warfare stalemate, Somme sector, autumn 1916.",
                political_military_context="Heavy artillery attritional bombardment.",
                available_technology=["Mauser Gewehr 98 brass casings", "M1916 Stahlhelm", "duckboards"],
                appropriate_architecture=["deep narrow trench with wooden revetments", "sandbag parapet", "revetment hurdles"],
                appropriate_transport=["none in trench ditch"],
                appropriate_props=["spent brass 7.92mm cartridge casings", "broken pine duckboards", "rusted bully beef tin"],
                historical_constraints=["Period 1916 German trench revetment", "No modern plastics or modern debris"],
            ),
            camera=CameraSpec(
                shot_size="GROUND_LEVEL",
                height="GROUND_LEVEL",
                yaw=4.0,
                pitch=6.0,
                lens_feel="WIDE_24MM",
                horizon_y=0.35,
            ),
            perspective=PerspectiveSpec(
                type="ONE_POINT",
                primary_vp=[0.48, 0.35],
                secondary_vp=[1.50, 0.35],
                depth_axis="CENTER_BACK",
            ),
            composition=CompositionSpec(
                visual_focus="PROTAGONIST",
                character_reserved_zone=ReservedZone(x=0.62, y=0.22, width=0.26, height=0.68),
                negative_space_zone={"x": 0.05, "y": 0.05, "width": 0.35, "height": 0.30},
                foreground_occlusion=0.20,
                eyeline="HORIZON",
            ),
            environment=EnvironmentSpec(
                foreground=[
                    "Wet mud puddle directly in foreground reflecting pale slate-grey sky",
                    "Five spent brass rifle cartridge casings half-submerged in wet soil",
                    "Splintered pine duckboard timber plank entering lower left frame",
                ],
                midground=[
                    "Zigzagging trench ditch lined with weathered pine post revetments",
                    "Sodden hemp sandbag firing step lining right trench wall",
                    "Clear walking corridor along muddy duckboards",
                ],
                background=[
                    "Trench trenching receding into diagonal distance toward primary vanishing point",
                    "Tangled coils of rusted barbed wire along upper parapet crest",
                ],
                far_background=[
                    "Low sliver of overcast sky with distant smoke plumes drifting horizontally",
                ],
                storytelling_details=[
                    "Cluster of spent brass Mauser casings fired during recent trench raid",
                    "Fractured wooden trench revetment beam shattered by artillery concussion",
                    "Torn piece of burlap sandbag fluttering wetly in cold wind",
                ],
                secondary_actions=[
                    "Ripples expanding in muddy puddle from cold dripping water droplets",
                ],
            ),
            lighting=LightingSpec(
                key_direction="BACKLIT",
                key_intensity=0.55,
                ambient_level=0.35,
                shadow_direction="LONG_FORWARD",
                color_temperature="COLD_DUSK",
                rim_opportunity=True,
                practical_lights=[],
            ),
            atmosphere=AtmosphereSpec(
                haze="LIGHT_MIST",
                weather="DRIZZLE",
                time_of_day="MORNING",
                volumetric_light=False,
            ),
            continuity=ContinuitySpec(
                location_dna_ref="western_front_trench",
                recurring_features=["pine revetment timbers", "duckboard path", "hemp sandbags"],
                lighting_consistency_key="cold_dawn_overcast",
            ),
            character=CharacterSpec(
                character_id="soldier_protagonist",
                approximate_position=[0.62, 0.45],
                scale=0.58,
                body_orientation="PROFILE_LEFT",
                pose_envelope="KNEEL_GRIEF",
                action="crouched in mud examining ground",
            ),
            negative_constraints=[
                "No human protagonist drawn",
                "No stickman",
                "No high eye-level horizon (horizon MUST be low at 35% for ground level)",
                "No modern materials, no electric wires",
            ],
        )
    )

    # -------------------------------------------------------------------------
    # SCENE B: Period Hospital/Infirmary Interior (Pasewalk 1918)
    # -------------------------------------------------------------------------
    scenes.append(
        SceneBlueprint(
            scene_id="SCENE_B_HOSPITAL",
            shot_id="SC_B_SH02_HOSPITAL_OTS",
            story=StorySpec(
                narration="Bệnh viện quân y Pasewalk, mùa thu 1918. Căn phòng điều trị nồng nặc mùi thuốc sát trùng và sự im lặng u uất.",
                previous_beat="Casualties of mustard gas attack arrive at reserve infirmary.",
                current_beat="Convalescent recovery in stark military hospital room.",
                next_beat="The chaplain delivers news of the Emperor's abdication and armistice.",
                purpose="SOMBER_CONVALESCENCE",
                emotion="INSTITUTIONAL_DESOLATION",
            ),
            history=HistorySpec(
                year=1918,
                location_id="pasewalk_infirmary",
                country="Pomerania, Germany",
                event_context="German military reserve hospital treating mustard gas blindness, October 1918.",
                political_military_context="Imminent collapse of the German war effort.",
                available_technology=["enamel hospital ware", "iron bedframes", "iodine bottles"],
                appropriate_architecture=["tall Prussian casement windows", "distressed white lime plaster", "high ceilings"],
                appropriate_transport=["none indoors"],
                appropriate_props=["black cast iron tubular hospital bed", "folded gauze rolls", "amber medicine vial"],
                historical_constraints=["Authentic 1918 hospital fixtures", "No plastic tubing", "No fluorescent lights"],
            ),
            camera=CameraSpec(
                shot_size="OTS",
                height="EYE_LEVEL",
                yaw=-20.0,
                pitch=-3.0,
                lens_feel="NORMAL_50MM",
                horizon_y=0.52,
            ),
            perspective=PerspectiveSpec(
                type="TWO_POINT",
                primary_vp=[0.65, 0.52],
                secondary_vp=[-0.45, 0.54],
                depth_axis="RIGHT_BACK",
            ),
            composition=CompositionSpec(
                visual_focus="PROTAGONIST",
                character_reserved_zone=ReservedZone(x=0.68, y=0.30, width=0.26, height=0.58),
                negative_space_zone={"x": 0.40, "y": 0.10, "width": 0.20, "height": 0.40},
                foreground_occlusion=0.35,  # Doctor shoulder occupying left third
                eyeline="HORIZON",
            ),
            environment=EnvironmentSpec(
                foreground=[
                    "Uncluttered dark left-third framing space reserved for foreground doctor shoulder silhouette",
                    "Corner of wooden clinical medicine stool in lower frame",
                ],
                midground=[
                    "Cast-iron tubular hospital bed with white cotton sheets and folded wool blanket",
                    "Bedside bedside table holding an enamel tin cup and dark glass medicine bottle",
                    "Scrubbed plain pine floorboards leading diagonally toward window",
                ],
                background=[
                    "Tall arched Prussian casement window with multipaned glass on left wall letting in pale cool daylight",
                    "Distressed lime-plaster whitewashed wall with wooden dado rail along lower third",
                ],
                far_background=[
                    "Open ward doorway revealing empty distant institutional hallway",
                ],
                storytelling_details=[
                    "Amber glass iodine bottle with cork stopper and roll of woven cotton gauze",
                    "Folded newspaper broadsheet with heavy Gothic type resting on bedside stool",
                    "Small porcelain dish with measuring spoon",
                ],
                secondary_actions=[
                    "Subtle shadow of an orderly passing in distant hospital corridor through open doorway",
                ],
            ),
            lighting=LightingSpec(
                key_direction="LEFT_HIGH",
                key_intensity=0.65,
                ambient_level=0.35,
                shadow_direction="BOTTOM_RIGHT",
                color_temperature="COLD_DUSK",
                rim_opportunity=True,
                practical_lights=[],
            ),
            atmosphere=AtmosphereSpec(
                haze="LIGHT_MIST",
                weather="COLD_SUN",
                time_of_day="MORNING",
                volumetric_light=True,
            ),
            continuity=ContinuitySpec(
                location_dna_ref="pasewalk_infirmary",
                recurring_features=["iron tubular bed", "tall casement window", "whitewashed plaster"],
                lighting_consistency_key="pasewalk_cool_morning",
            ),
            character=CharacterSpec(
                character_id="blinded_soldier",
                approximate_position=[0.68, 0.54],
                scale=0.55,
                body_orientation="PROFILE_LEFT",
                pose_envelope="LIE_BED",
                action="resting in bed with head bandage",
            ),
            negative_constraints=[
                "No human patient drawn in bed",
                "No stickman",
                "Keep left third uncluttered for foreground doctor shoulder overlay",
                "No modern medical monitors or modern equipment",
            ],
        )
    )

    # -------------------------------------------------------------------------
    # SCENE C: Munich Historical Street / Public Square (Odeonsplatz 1914)
    # -------------------------------------------------------------------------
    scenes.append(
        SceneBlueprint(
            scene_id="SCENE_C_MUNICH_ODEONSPLATZ",
            shot_id="SC_C_SH03_MUNICH_LOW_ANGLE",
            story=StorySpec(
                narration="Tháng 8 năm 1914 tại Munich. Hàng ngàn người đổ ra quảng trường Odeonsplatz trong cơn cuồng nhiệt tuyên chiến.",
                previous_beat="Declaration of mobilization announced across Bavarian cities.",
                current_beat="Monumental public gathering at Odeonsplatz: imperial stone columns towering above.",
                next_beat="Crowd erupts in cheers as national anthems echo through the loggia.",
                purpose="MONUMENTAL_HISTORICAL_FERVOR",
                emotion="OVERWHELMING_AWE",
            ),
            history=HistorySpec(
                year=1914,
                location_id="munich_odeonsplatz",
                country="Bavaria, Germany",
                event_context="August 2, 1914 mobilization crowd rally outside the Feldherrnhalle in Munich.",
                political_military_context="Outbreak of World War I, nationalistic euphoria.",
                available_technology=["sandstone architecture", "wrought iron lamps", "horse carriages"],
                appropriate_architecture=["Feldherrnhalle massive Corinthian columns", "arched stone portico", "Residenz palace facade"],
                appropriate_transport=["horse-drawn carriage", "yellow Munich tramway (distant)"],
                appropriate_props=["bavarian blue-and-white flags", "stone lion statues", "extra edition newspapers"],
                historical_constraints=["Strict 1914 Wilhelmine/Bavarian era only", "No swastikas", "No modern asphalt roads"],
            ),
            camera=CameraSpec(
                shot_size="LOW_ANGLE",
                height="LOW_ANGLE",
                yaw=-18.0,
                pitch=18.0,
                lens_feel="WIDE_24MM",
                horizon_y=0.28,
            ),
            perspective=PerspectiveSpec(
                type="THREE_POINT",
                primary_vp=[0.72, 0.28],
                secondary_vp=[-0.30, 0.28],
                depth_axis="RIGHT_BACK",
            ),
            composition=CompositionSpec(
                visual_focus="PROTAGONIST",
                character_reserved_zone=ReservedZone(x=0.38, y=0.22, width=0.24, height=0.62),
                negative_space_zone={"x": 0.40, "y": 0.02, "width": 0.55, "height": 0.35},
                foreground_occlusion=0.0,
                eyeline="HIGH_SKY",
            ),
            environment=EnvironmentSpec(
                foreground=[
                    "Granite plaza flagstones in steep upward perspective",
                    "Carved sandstone plinth of the monumental Bavarian lion sculpture on left",
                ],
                midground=[
                    "Towering fluted Corinthian stone columns of the Feldherrnhalle loggia rising dramatically into the sky",
                    "Monumental stone steps ascending toward the open loggia arches",
                ],
                background=[
                    "Ornate neoclassical palace facade with arched windows along Ludwigstraße",
                    "Bavarian blue-and-white lozenge banners hanging from palace balconies",
                ],
                far_background=[
                    "Vibrant blue summer sky with golden midday sunlight striking column capitals",
                    "Distant Baroque church dome silhouette against the clear horizon",
                ],
                storytelling_details=[
                    "Extra-edition mobilization newspapers (Extrablatt) scattered on the stone steps",
                    "Bavarian flag ribbons tied around wrought-iron lamp standard",
                    "Tossed civilian boater hat caught against column base",
                ],
                secondary_actions=[
                    "Distant ambient crowd silhouettes waving hats and cheering beneath distant palace arches",
                ],
            ),
            lighting=LightingSpec(
                key_direction="LEFT_HIGH",
                key_intensity=0.90,
                ambient_level=0.40,
                shadow_direction="BOTTOM_RIGHT",
                color_temperature="GOLDEN_HOUR",
                rim_opportunity=True,
                practical_lights=[],
            ),
            atmosphere=AtmosphereSpec(
                haze="LIGHT_MIST",
                weather="DRY",
                time_of_day="MIDDAY",
                volumetric_light=True,
            ),
            continuity=ContinuitySpec(
                location_dna_ref="munich_odeonsplatz",
                recurring_features=["Feldherrnhalle columns", "granite paving", "stone lion"],
                lighting_consistency_key="warm_summer_1914",
            ),
            character=CharacterSpec(
                character_id="young_hitler_1914",
                approximate_position=[0.38, 0.40],
                scale=0.52,
                body_orientation="BACK",
                pose_envelope="ALERT_STAND",
                action="standing in plaza gazing up at columns",
            ),
            negative_constraints=[
                "No human protagonist drawn in reserved area",
                "No stickman",
                "No eye-level horizon (horizon MUST be low at 28% for dramatic low angle)",
                "No modern vehicles, no asphalt, no modern street signs",
            ],
        )
    )

    return scenes
