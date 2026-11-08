"""Director Designer: Generates high-fidelity SceneBlueprints from story and history.

The Director decides:
- Story Purpose & Narration Beat
- Camera Height, Pitch, Yaw, Lens, and Horizon
- Perspective System (1-Point, 2-Point, Depth Corridor)
- Compositional Hierarchy & Character Reserved Space
- 4-Tier Depth Plan (Foreground, Midground, Background, Far-Background)
- Lighting Intent (Direction, Intensity, Shadows, Color Temp)
- Storytelling Details (1-3 grounded narrative anchors)
- Historical Boundaries & Negative Constraints
"""
from __future__ import annotations

from typing import Any

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


class DirectorDesigner:
    """The authoritative Story and Visual Architect."""

    def __init__(self) -> None:
        self._location_dnas: dict[str, dict[str, Any]] = {
            "western_front": {
                "name": "Western Front Trench Sector",
                "materials": ["wet mud", "rough pine revetment timbers", "hemp sandbags", "rusty barbed wire"],
                "palette": ["mud brown", "slate grey", "cold olive", "charcoal"],
                "landmarks": ["shattered blasted tree trunks", "duckboard zigzag", "parapet firing step"],
            },
            "munich_odeonsplatz": {
                "name": "Munich Odeonsplatz & Feldherrnhalle",
                "materials": ["neoclassical sandstone", "granite cobblestones", "wrought iron", "bavarian flags"],
                "palette": ["warm sandstone ochre", "cobblestone grey", "deep royal blue", "golden sunlight"],
                "landmarks": ["Feldherrnhalle arched loggia", "stone lions", "Theatinerkirche towers in distance"],
            },
            "pasewalk_hospital": {
                "name": "Pasewalk Military Hospital",
                "materials": ["distressed white lime plaster", "black cast iron bedframes", "scrubbed pine floorboards"],
                "palette": ["institutional chalk white", "pale seafoam grey", "iron black", "cold morning daylight"],
                "landmarks": ["tall arched casement window", "iron infirmary bedstead", "enamel washbasin stand"],
            },
            "beer_hall_munich": {
                "name": "Bürgerbräukeller Beer Hall",
                "materials": ["dark oiled oak beams", "whitewashed brick arches", "ceramic stoneware", "brass lamps"],
                "palette": ["dark walnut brown", "amber lantern glow", "brick terra cotta", "smoky ochre"],
                "landmarks": ["deep arcade of timber pillars", "long tavern trestle tables", "brass hanging oil lamps"],
            },
        }

    def get_location_dna(self, loc_id: str) -> dict[str, Any]:
        return self._location_dnas.get(loc_id, self._location_dnas["western_front"])

    def create_10_shot_prototype_blueprints(self) -> list[SceneBlueprint]:
        """Creates the 10 representative Blueprints spanning all camera & location archetypes."""
        blueprints: list[SceneBlueprint] = []

        # -------------------------------------------------------------------------
        # SHOT 1: EXTREME_WIDE (Western Front Trench 1916)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_01_WESTERN_FRONT",
                shot_id="S01_SH01_EXTREME_WIDE",
                story=StorySpec(
                    narration="Mặt trận phía Tây năm 1916. Một vùng đất hoang tàn trải dài dưới làn sương dày đặc và tiếng pháo rền rĩ từ xa.",
                    previous_beat="Opening titles: The Great War erupts across Europe.",
                    current_beat="Desolate scale of the Western Front trench line.",
                    next_beat="Close look into the everyday survival of soldiers.",
                    purpose="ESTABLISH_SCALE_AND_DESOLATION",
                    emotion="COLD_DREAD",
                ),
                history=HistorySpec(
                    year=1916,
                    location_id="western_front",
                    country="France / Flanders Border",
                    event_context="Battle of the Somme era static trench warfare.",
                    political_military_context="Stalemate along the Western Front.",
                    available_technology=["entrenching tools", "field telephones", "heavy howitzers", "Mauser Gewehr 98"],
                    appropriate_architecture=["zigzag dugouts", "log bunkers", "revetment hurdles"],
                    appropriate_transport=["horse-drawn supply carts", "narrow-gauge trench railway"],
                    appropriate_props=["wooden duckboards", "barbed wire spools", "perforated steel trench plates"],
                    historical_constraints=["No steel helmets before 1916 M1916 Stahlhelm", "No modern asphalt", "No electric pylons"],
                ),
                camera=CameraSpec(
                    shot_size="EXTREME_WIDE",
                    height="EYE_LEVEL",
                    yaw=0.0,
                    pitch=0.0,
                    lens_feel="WIDE_24MM",
                    horizon_y=0.60,
                ),
                perspective=PerspectiveSpec(
                    type="TWO_POINT",
                    primary_vp=[0.50, 0.60],
                    secondary_vp=[-0.40, 0.62],
                    depth_axis="CENTER_BACK",
                ),
                composition=CompositionSpec(
                    visual_focus="ENVIRONMENT",
                    character_reserved_zone=ReservedZone(x=0.72, y=0.52, width=0.12, height=0.20),
                    negative_space_zone={"x": 0.05, "y": 0.05, "width": 0.50, "height": 0.40},
                    foreground_occlusion=0.0,
                    eyeline="HORIZON",
                ),
                environment=EnvironmentSpec(
                    foreground=["shattered barbed wire post entered from lower right", "charred stump silhouette"],
                    midground=["crater filled with stagnant muddy water", "submerged sandbag firing step", "mud mound"],
                    background=["endless zigzagging trench lines receding diagonally", "ruined stone farm wall fragment"],
                    far_background=["smoky grey sky", "distant rolling artillery smoke puffs on horizon"],
                    storytelling_details=["abandoned broken wagon wheel half buried in mud", "tangled telephone wire trailing in crater"],
                    secondary_actions=["faint silhouettes of distant supply carriers ducking behind parapet"],
                ),
                lighting=LightingSpec(
                    key_direction="BACKLIT",
                    key_intensity=0.45,
                    ambient_level=0.35,
                    shadow_direction="LONG_FORWARD",
                    color_temperature="COLD_DUSK",
                    rim_opportunity=True,
                    practical_lights=[],
                ),
                atmosphere=AtmosphereSpec(
                    haze="HEAVY_FOG",
                    weather="MUDDY_FREEZE",
                    time_of_day="DAWN",
                    volumetric_light=False,
                ),
                continuity=ContinuitySpec(
                    location_dna_ref="western_front",
                    recurring_features=["zigzag mud trench", "pine timber framing", "barbed wire"],
                    lighting_consistency_key="cold_dawn_overcast",
                ),
                character=CharacterSpec(
                    character_id="soldier_protagonist",
                    approximate_position=[0.72, 0.64],
                    scale=0.18,
                    body_orientation="PROFILE_LEFT",
                    pose_envelope="ALERT_STAND",
                    action="watch horizon",
                ),
                negative_constraints=[
                    "No human protagonist painted in plate", "No stickman", "No modern buildings", "No power lines", "No vibrant colors"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 2: WIDE (Munich Odeonsplatz 1914)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_02_MUNICH_MOBILIZATION",
                shot_id="S02_SH02_WIDE",
                story=StorySpec(
                    narration="Tháng 8 năm 1914 tại Munich. Hàng ngàn người đổ ra quảng trường Odeonsplatz trong cơn cuồng nhiệt tuyên chiến.",
                    previous_beat="Assassination of Archduke Franz Ferdinand triggers mobilization.",
                    current_beat="Jubilant war frenzy in Munich public square.",
                    next_beat="Volunteering for military service at recruitment office.",
                    purpose="CAPTURE_HISTORICAL_EUPHORIA",
                    emotion="MANIC_EXCITEMENT",
                ),
                history=HistorySpec(
                    year=1914,
                    location_id="munich_odeonsplatz",
                    country="Bavaria, Germany",
                    event_context="General mobilization declaration rally at Odeonsplatz August 2, 1914.",
                    political_military_context="Outbreak of World War I, nationalistic fervor.",
                    available_technology=["electric tramways", "print newspapers", "early motorcars", "gas streetlamps"],
                    appropriate_architecture=["Feldherrnhalle open loggia", "Theatinerkirche baroque facade", "neoclassical columns"],
                    appropriate_transport=["horse carriage", "yellow Munich tramcar"],
                    appropriate_props=["black top hats", "boater hats", "fluttering Bavarian and Imperial flags", "newspapers"],
                    historical_constraints=["1914 clothing only", "No Nazi swastikas", "No asphalt roadways"],
                ),
                camera=CameraSpec(
                    shot_size="WIDE",
                    height="EYE_LEVEL",
                    yaw=-12.0,
                    pitch=-2.0,
                    lens_feel="WIDE_24MM",
                    horizon_y=0.56,
                ),
                perspective=PerspectiveSpec(
                    type="TWO_POINT",
                    primary_vp=[0.68, 0.56],
                    secondary_vp=[-0.35, 0.58],
                    depth_axis="RIGHT_BACK",
                ),
                composition=CompositionSpec(
                    visual_focus="PROTAGONIST",
                    character_reserved_zone=ReservedZone(x=0.52, y=0.38, width=0.18, height=0.46),
                    negative_space_zone={"x": 0.05, "y": 0.05, "width": 0.40, "height": 0.35},
                    foreground_occlusion=0.0,
                    eyeline="HORIZON",
                ),
                environment=EnvironmentSpec(
                    foreground=["cobblestone square pavement", "cast iron streetlamp base on left"],
                    midground=["monumental stone steps of Feldherrnhalle", "bronze statues under vaulted arches"],
                    background=["grand sandstone facade of Residenz street", "fluttering flags from palace windows"],
                    far_background=["blue summer sky with puffy white clouds", "ornate church spires"],
                    storytelling_details=["extra edition newspapers scattered on cobblestones", "Bavarian flag hung from balcony"],
                    secondary_actions=["dense crowd silhouettes cheering and raising hats in background and flanks"],
                ),
                lighting=LightingSpec(
                    key_direction="LEFT_HIGH",
                    key_intensity=0.85,
                    ambient_level=0.45,
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
                    recurring_features=["Feldherrnhalle loggia", "granite cobblestones", "Bavarian flags"],
                    lighting_consistency_key="warm_summer_1914",
                ),
                character=CharacterSpec(
                    character_id="young_hitler_1914",
                    approximate_position=[0.52, 0.60],
                    scale=0.42,
                    body_orientation="FRONT_THREE_QUARTER",
                    pose_envelope="ORATE_FIST",
                    action="cheering with crowd",
                ),
                negative_constraints=[
                    "No main stickman painted", "No modern cars", "No plastic", "No post-1918 flags", "No photorealistic human faces"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 3: MEDIUM (Pasewalk Military Hospital 1918)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_03_PASEWALK_HOSPITAL",
                shot_id="S03_SH03_MEDIUM",
                story=StorySpec(
                    narration="Bệnh viện quân y Pasewalk, mùa thu 1918. Căn phòng điều trị nồng nặc mùi thuốc sát trùng và sự im lặng u uất.",
                    previous_beat="Mustard gas attack at Ypres temporarily blinds the soldier.",
                    current_beat="Convalescence and isolation in the military infirmary.",
                    next_beat="The news of the Armistice and the revolution breaks.",
                    purpose="INTIMATE_CONVALESCENCE",
                    emotion="SULLEN_DESPAIR",
                ),
                history=HistorySpec(
                    year=1918,
                    location_id="pasewalk_hospital",
                    country="Pomerania, Germany",
                    event_context="Military Lazarett Pasewalk treating gas blindness victims, October 1918.",
                    political_military_context="Collapsing German war effort, impending armistice.",
                    available_technology=["enamel hospital ware", "iodine antiseptics", "carbolic acid", "linseed oil lamps"],
                    appropriate_architecture=["tall Prussian institutional casement windows", "lime plaster walls", "high ceilings"],
                    appropriate_transport=["Red Cross hospital train (distant)"],
                    appropriate_props=["black iron tubular hospital bed", "gauze rolls", "dark amber medicine bottles"],
                    historical_constraints=["1918 hospital equipment", "No plastic tubing", "No fluorescent tubes"],
                ),
                camera=CameraSpec(
                    shot_size="MEDIUM",
                    height="EYE_LEVEL",
                    yaw=14.0,
                    pitch=0.0,
                    lens_feel="NORMAL_50MM",
                    horizon_y=0.50,
                ),
                perspective=PerspectiveSpec(
                    type="ONE_POINT",
                    primary_vp=[0.38, 0.50],
                    secondary_vp=[1.40, 0.50],
                    depth_axis="CENTER_BACK",
                ),
                composition=CompositionSpec(
                    visual_focus="PROTAGONIST",
                    character_reserved_zone=ReservedZone(x=0.58, y=0.28, width=0.25, height=0.60),
                    negative_space_zone={"x": 0.08, "y": 0.10, "width": 0.35, "height": 0.50},
                    foreground_occlusion=0.0,
                    eyeline="HORIZON",
                ),
                environment=EnvironmentSpec(
                    foreground=["corner of bedside wooden medicine stool on lower right"],
                    midground=["black iron hospital bed with white cotton sheets and blanket", "bare floorboards"],
                    background=["tall multipaned hospital casement window on left wall letting in pale grey light"],
                    far_background=["distressed white lime plaster wall with peeling paint", "water-stained ceiling beam"],
                    storytelling_details=["amber iodine bottle and folded gauze bandages on stool", "tin drinking cup"],
                    secondary_actions=["subtle shadow of an orderly passing in distant hospital corridor through open door"],
                ),
                lighting=LightingSpec(
                    key_direction="LEFT_HIGH",
                    key_intensity=0.60,
                    ambient_level=0.30,
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
                    location_dna_ref="pasewalk_hospital",
                    recurring_features=["iron bedframe", "tall Prussian window", "distressed white wall"],
                    lighting_consistency_key="pasewalk_cool_morning",
                ),
                character=CharacterSpec(
                    character_id="blinded_soldier",
                    approximate_position=[0.58, 0.54],
                    scale=0.60,
                    body_orientation="PROFILE_LEFT",
                    pose_envelope="LIE_BED",
                    action="recovering in bed with head bandage",
                ),
                negative_constraints=[
                    "No character painted in bed", "No stickman", "No modern hospital gear", "No modern electronics", "No warm cozy tones"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 4: CLOSE/REACTION (Bürgerbräukeller Beer Hall Munich 1919)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_04_MUNICH_BEER_HALL",
                shot_id="S04_SH04_CLOSE_REACTION",
                story=StorySpec(
                    narration="Một quán bia ngột ngạt ở Munich cuối năm 1919. Những tờ truyền đơn chính trị chuyền tay dưới ánh đèn dầu.",
                    previous_beat="Discharged from army into a bitter, defeated post-war Munich.",
                    current_beat="Attending an underground German Workers' Party meeting.",
                    next_beat="Rising to speak and electrifying the tavern crowd.",
                    purpose="INTENSE_POLITICAL_AWAKENING",
                    emotion="FEVERISH_CALCULATING",
                ),
                history=HistorySpec(
                    year=1919,
                    location_id="beer_hall_munich",
                    country="Munich, Bavaria",
                    event_context="Early DAP political gathering in Munich tavern cellar, autumn 1919.",
                    political_military_context="Post-Versailles unrest, Bavarian Soviet Republic aftermath.",
                    available_technology=["kerosene oil lamps", "gas chandeliers", "cast iron stoves", "typewriters"],
                    appropriate_architecture=["vaulted Bavarian tavern ceilings", "rustic oak timber paneling", "sturdy brick arches"],
                    appropriate_transport=["trolley", "bicycles"],
                    appropriate_props=["stoneware salt-glazed beer steins", "crumpled pamphlets", "tobacco pipes", "ashtrays"],
                    historical_constraints=["1919 period only", "No swastikas yet (early DAP period)", "No neon signs"],
                ),
                camera=CameraSpec(
                    shot_size="CLOSE",
                    height="EYE_LEVEL",
                    yaw=8.0,
                    pitch=-3.0,
                    lens_feel="TELE_85MM",
                    horizon_y=0.44,
                ),
                perspective=PerspectiveSpec(
                    type="ONE_POINT",
                    primary_vp=[0.52, 0.44],
                    secondary_vp=[1.80, 0.44],
                    depth_axis="CENTER_BACK",
                ),
                composition=CompositionSpec(
                    visual_focus="PROTAGONIST",
                    character_reserved_zone=ReservedZone(x=0.50, y=0.20, width=0.36, height=0.72),
                    negative_space_zone={"x": 0.05, "y": 0.05, "width": 0.35, "height": 0.40},
                    foreground_occlusion=0.15,
                    eyeline="HORIZON",
                ),
                environment=EnvironmentSpec(
                    foreground=["blurred rim of stoneware beer stein in extreme lower left"],
                    midground=["rustic oak table with wood grain texture and spilled froth", "carved chair back"],
                    background=["dark stained wooden wall wainscoting", "chalkboard with handwritten beer prices crossed out"],
                    far_background=["warm haze of tobacco smoke", "distant warm silhouette of chandelier brass arm"],
                    storytelling_details=["political flyer with German Gothic Fraktur script on table", "spent matchstick"],
                    secondary_actions=["wisp of tobacco smoke lazily curling up near table edge"],
                ),
                lighting=LightingSpec(
                    key_direction="OVERHEAD",
                    key_intensity=0.80,
                    ambient_level=0.30,
                    shadow_direction="BOTTOM_LEFT",
                    color_temperature="WARM_INDOOR",
                    rim_opportunity=True,
                    practical_lights=["overhead brass gas lamp"],
                ),
                atmosphere=AtmosphereSpec(
                    haze="SMOKE_DUST",
                    weather="DRY",
                    time_of_day="NIGHT",
                    volumetric_light=True,
                ),
                continuity=ContinuitySpec(
                    location_dna_ref="beer_hall_munich",
                    recurring_features=["dark oak wainscoting", "beer steins", "brass lamps"],
                    lighting_consistency_key="beer_hall_warm_amber",
                ),
                character=CharacterSpec(
                    character_id="agitator",
                    approximate_position=[0.50, 0.48],
                    scale=0.82,
                    body_orientation="FRONT_THREE_QUARTER",
                    pose_envelope="THINK_CHIN",
                    action="deep scrutiny of political pamphlet",
                ),
                negative_constraints=[
                    "No protagonist drawn", "No stickman", "No modern beer bottles", "No electric neon", "No modern printed fonts"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 5: LOW_ANGLE (Munich Odeonsplatz 1914)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_05_MONUMENTAL_ODEONSPLATZ",
                shot_id="S05_SH05_LOW_ANGLE",
                story=StorySpec(
                    narration="Góc nhìn thấp áp đảo, những cột trụ đá sừng sững vươn lên bầu trời Bavaria giữa không khí biến động.",
                    previous_beat="Crowd surges into the plaza.",
                    current_beat="Overwhelming visual grandeur of imperial architecture towering over the individual.",
                    next_beat="Young men swept up in the monumentality of destiny.",
                    purpose="OVERWHELMING_MONUMENTALITY",
                    emotion="IMPERIAL_AWE",
                ),
                history=HistorySpec(
                    year=1914,
                    location_id="munich_odeonsplatz",
                    country="Bavaria, Germany",
                    event_context="Odeonsplatz monumentality during war rally August 1914.",
                    political_military_context="Imperial architectural authority.",
                    available_technology=["hewn sandstone architecture", "wrought iron railings"],
                    appropriate_architecture=["Feldherrnhalle massive Corinthian columns", "arched stone vaults"],
                    appropriate_transport=["none in this frame"],
                    appropriate_props=["bavarian standards", "stone lion plinth"],
                    historical_constraints=["Period stone architecture only", "No modern street signs"],
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
                    visual_focus="ENVIRONMENT",
                    character_reserved_zone=ReservedZone(x=0.38, y=0.22, width=0.24, height=0.62),
                    negative_space_zone={"x": 0.40, "y": 0.02, "width": 0.55, "height": 0.35},
                    foreground_occlusion=0.0,
                    eyeline="HIGH_SKY",
                ),
                environment=EnvironmentSpec(
                    foreground=["granite flagstones rising steeply in perspective"],
                    midground=["massive fluted stone column base towering upward", "stone lion pedestal edge"],
                    background=["sweeping triumphal arch overhead vaulting across frame", "carved stone frieze"],
                    far_background=["dramatic blue sky with golden sunlight catching column capitals"],
                    storytelling_details=["patriotic black-white-red and blue-white ribbons tied to iron balustrade"],
                    secondary_actions=["fluttering banner corners caught in summer wind"],
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
                    action="looking up in wonder",
                ),
                negative_constraints=[
                    "No stickman drawn", "No modern buildings", "No eye level horizon (must be low 28%)", "No flat perspective"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 6: HIGH_ANGLE (Western Front Trench 1916)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_06_TRENCH_CONFINEMENT",
                shot_id="S06_SH06_HIGH_ANGLE",
                story=StorySpec(
                    narration="Nhìn từ trên cao xuống rãnh chiến hào ngập bùn, người lính như bị giam cầm giữa những bức tường đất ẩm ướt.",
                    previous_beat="Heavy shelling forces soldiers into muddy revetments.",
                    current_beat="Claustrophobia and entrapment inside the muddy trench ditch.",
                    next_beat="Waiting endlessly for the artillery whistle.",
                    purpose="CLAUSTROPHOBIC_ENTRAPMENT",
                    emotion="OPPRESSIVE_DESPERATION",
                ),
                history=HistorySpec(
                    year=1916,
                    location_id="western_front",
                    country="France / Flanders",
                    event_context="High downward perspective on Somme trench ditch.",
                    political_military_context="Attrition warfare, trench claustrophobia.",
                    available_technology=["trench pumps", "duckboards", "wicker revetments"],
                    appropriate_architecture=["deep narrow trench trenching", "traverse revetments"],
                    appropriate_transport=["none"],
                    appropriate_props=["ammunition boxes", "mess tins", "trench spade"],
                    historical_constraints=["Authentic 1916 German trench revetment", "No modern plastics"],
                ),
                camera=CameraSpec(
                    shot_size="HIGH_ANGLE",
                    height="HIGH_ANGLE",
                    yaw=10.0,
                    pitch=-24.0,
                    lens_feel="WIDE_24MM",
                    horizon_y=0.84,
                ),
                perspective=PerspectiveSpec(
                    type="TWO_POINT",
                    primary_vp=[0.42, 0.84],
                    secondary_vp=[1.35, 0.82],
                    depth_axis="CENTER_BACK",
                ),
                composition=CompositionSpec(
                    visual_focus="PROTAGONIST",
                    character_reserved_zone=ReservedZone(x=0.52, y=0.50, width=0.22, height=0.44),
                    negative_space_zone={"x": 0.05, "y": 0.05, "width": 0.40, "height": 0.35},
                    foreground_occlusion=0.0,
                    eyeline="DOWN_GROUND",
                ),
                environment=EnvironmentSpec(
                    foreground=["overhanging sandbag parapet cutting across top edge of frame"],
                    midground=["mud-churned trench floor with broken wooden duckboards half afloat", "slanted timber struts"],
                    background=["revetment woven wicker hurdles lining trench walls", "recessed dugout shelter doorway"],
                    far_background=["narrow sliver of mud terrain at very top right"],
                    storytelling_details=["discarded rusted bully beef tin in mud puddle", "entrenching tool planted in trench bank"],
                    secondary_actions=["water droplets dripping from sandbag lip creating ripples in puddle"],
                ),
                lighting=LightingSpec(
                    key_direction="OVERHEAD",
                    key_intensity=0.50,
                    ambient_level=0.35,
                    shadow_direction="LONG_FORWARD",
                    color_temperature="SULLEN_OVERCAST",
                    rim_opportunity=False,
                    practical_lights=[],
                ),
                atmosphere=AtmosphereSpec(
                    haze="LIGHT_MIST",
                    weather="MUDDY_FREEZE",
                    time_of_day="MIDDAY",
                    volumetric_light=False,
                ),
                continuity=ContinuitySpec(
                    location_dna_ref="western_front",
                    recurring_features=["pine revetments", "sandbags", "duckboards in mud"],
                    lighting_consistency_key="cold_dawn_overcast",
                ),
                character=CharacterSpec(
                    character_id="trench_runner",
                    approximate_position=[0.52, 0.74],
                    scale=0.48,
                    body_orientation="PROFILE_RIGHT",
                    pose_envelope="DUCK_COVER",
                    action="crouched low against trench wall",
                ),
                negative_constraints=[
                    "No stickman drawn", "No eye-level horizon (must be high 84%)", "No clean dry ground", "No bright sunny sky"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 7: GROUND_LEVEL (Western Front Trench 1916)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_07_TRENCH_MUD_LEVEL",
                shot_id="S07_SH07_GROUND_LEVEL",
                story=StorySpec(
                    narration="Ống kính đặt sát mặt bùn lầy, nơi từng giọt mưa và vỏ đạn rải rác kể lại nỗi kinh hoàng của chiến sự.",
                    previous_beat="Shell explosion shakes the parapet.",
                    current_beat="Microscopic reality of mud, spent brass, and survival inches from the earth.",
                    next_beat="Looking up to see smoke drifting.",
                    purpose="VISCERAL_GROUNDED_TERROR",
                    emotion="VISCERAL_IMMEDIACY",
                ),
                history=HistorySpec(
                    year=1916,
                    location_id="western_front",
                    country="France / Flanders",
                    event_context="WWI trench floor macro view during bombardment lull.",
                    political_military_context="Mud as the primary enemy.",
                    available_technology=["7.92×57mm Mauser cartridges", "M1916 steel helmets"],
                    appropriate_architecture=["trench floor duckboards", "ground timber base"],
                    appropriate_transport=["none"],
                    appropriate_props=["spent brass shell casings", "muddy leather boot heels", "canteen"],
                    historical_constraints=["German brass shell casings 1916", "No modern debris"],
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
                    eyeline="UP_EYELINE",
                ),
                environment=EnvironmentSpec(
                    foreground=["macro wet mud puddle reflecting grey clouds right in camera lens", "scattered brass rifle cartridges"],
                    midground=["splintered wet pine duckboard planks leading into screen", "trench wall rising up"],
                    background=["sandbags and timber revetment posts receding in one-point corridor"],
                    far_background=["smoky grey sky visible above low horizon line"],
                    storytelling_details=["five spent brass Mauser casings half sunk in mud", "fractured bayonet scabbard tip"],
                    secondary_actions=["rain ripples trembling across foreground puddle surface"],
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
                    location_dna_ref="western_front",
                    recurring_features=["duckboards", "mud puddle", "pine revetments"],
                    lighting_consistency_key="cold_dawn_overcast",
                ),
                character=CharacterSpec(
                    character_id="soldier_protagonist",
                    approximate_position=[0.62, 0.45],
                    scale=0.58,
                    body_orientation="PROFILE_LEFT",
                    pose_envelope="KNEEL_GRIEF",
                    action="kneeling in mud checking equipment",
                ),
                negative_constraints=[
                    "No stickman drawn", "No high horizon (must be ground level 35%)", "No clean ground", "No plastic"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 8: OTS (Pasewalk Military Hospital 1918)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_08_HOSPITAL_DIAGNOSIS",
                shot_id="S08_SH08_OTS",
                story=StorySpec(
                    narration="Góc quay qua vai bác sĩ quân y, quan sát người thương binh đang suy sụp khi đón nhận tin đình chiến.",
                    previous_beat="Doctor enters the ward holding the medical chart and newspaper.",
                    current_beat="Delivering the grim reality of military defeat to the recovering patient.",
                    next_beat="Patient grasps the bedsheets in speechless shock.",
                    purpose="DRAMATIC_CONFRONTATION_NEWS",
                    emotion="STUNNED_BETRAYAL",
                ),
                history=HistorySpec(
                    year=1918,
                    location_id="pasewalk_hospital",
                    country="Pomerania, Germany",
                    event_context="November 1918 German capitulation announced in hospital wards.",
                    political_military_context="Dolchstoßlegende (stab-in-the-back) myth origin moment.",
                    available_technology=["medical clipboard", "fountain pens", "stethoscope tubing"],
                    appropriate_architecture=["tall whitewashed hospital ward"],
                    appropriate_transport=["none"],
                    appropriate_props=["doctor white coat silhouette", "clinical iron bed"],
                    historical_constraints=["1918 medical uniform silhouette", "Authentic Pasewalk infirmary"],
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
                    foreground=["clean left-third silhouette space reserved for doctor shoulder and collar"],
                    midground=["hospital bed frame with patient sitting upright", "side table with glass water carafe"],
                    background=["whitewashed wall with wooden dado rail", "tall arched hospital window letting in grey light"],
                    far_background=["open ward doorway revealing empty distant hallway"],
                    storytelling_details=["folded Vorwärts socialist newspaper showing bold armistice headline on stool"],
                    secondary_actions=["distant orderly closing double doors at end of hallway"],
                ),
                lighting=LightingSpec(
                    key_direction="RIGHT_HIGH",
                    key_intensity=0.65,
                    ambient_level=0.35,
                    shadow_direction="BOTTOM_LEFT",
                    color_temperature="COLD_DUSK",
                    rim_opportunity=True,
                    practical_lights=[],
                ),
                atmosphere=AtmosphereSpec(
                    haze="NONE",
                    weather="COLD_SUN",
                    time_of_day="MIDDAY",
                    volumetric_light=False,
                ),
                continuity=ContinuitySpec(
                    location_dna_ref="pasewalk_hospital",
                    recurring_features=["iron bedstead", "Prussian window", "lime plaster"],
                    lighting_consistency_key="pasewalk_cool_morning",
                ),
                character=CharacterSpec(
                    character_id="blinded_soldier",
                    approximate_position=[0.68, 0.54],
                    scale=0.55,
                    body_orientation="PROFILE_LEFT",
                    pose_envelope="ORATE_FIST",
                    action="clenching fists in disbelief",
                ),
                negative_constraints=[
                    "No patient drawn in bed", "No stickman", "Keep left third uncluttered for OTS shoulder overlay"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 9: POV (Western Front Trench 1916)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_09_PERISCOPE_POV",
                shot_id="S09_SH09_POV",
                story=StorySpec(
                    narration="Điểm nhìn chủ quan từ khe quan sát kính tiềm vọng ra bãi mìn không người và hàng rào kẽm gai rách nát.",
                    previous_beat="Soldier raises mirror periscope above the trench parapet.",
                    current_beat="First-person view across the terrifying expanse of No Man's Land.",
                    next_beat="Lowering periscope as enemy sniper bullet clips the mirror.",
                    purpose="SUBJECTIVE_TERROR_POV",
                    emotion="HEART_STOPPING_VULNERABILITY",
                ),
                history=HistorySpec(
                    year=1916,
                    location_id="western_front",
                    country="France / Flanders",
                    event_context="No Man's Land viewed through German box periscope (Grabenspiegel).",
                    political_military_context="Lethal sniper surveillance along trench berm.",
                    available_technology=["trench periscope Grabenspiegel", "Maxim MG08", "star shells"],
                    appropriate_architecture=["sandbag firing slit", "No Man's Land craterfield"],
                    appropriate_transport=["none"],
                    appropriate_props=["barbed wire stakes", "corrugated iron sheets"],
                    historical_constraints=["Authentic 1916 No Man's Land", "No protagonist in POV frame"],
                ),
                camera=CameraSpec(
                    shot_size="POV",
                    height="EYE_LEVEL",
                    yaw=0.0,
                    pitch=0.0,
                    lens_feel="TELE_85MM",
                    horizon_y=0.50,
                ),
                perspective=PerspectiveSpec(
                    type="ONE_POINT",
                    primary_vp=[0.50, 0.50],
                    secondary_vp=[1.60, 0.50],
                    depth_axis="CENTER_BACK",
                ),
                composition=CompositionSpec(
                    visual_focus="ENVIRONMENT",
                    character_reserved_zone=ReservedZone(x=0.50, y=0.50, width=0.0, height=0.0),  # NO character in POV
                    negative_space_zone={"x": 0.05, "y": 0.05, "width": 0.90, "height": 0.90},
                    foreground_occlusion=0.0,
                    eyeline="HORIZON",
                ),
                environment=EnvironmentSpec(
                    foreground=["circular optical periscope vignette masking frame edges", "rough sandbags framing bottom slit"],
                    midground=["tangled maze of rusted barbed wire concertina coils on wooden screw pickets"],
                    background=["water-filled shell craters with charred earth ridges", "skeletal remains of a blasted orchard"],
                    far_background=["distant enemy trench sandbag line under smoky yellowish sky"],
                    storytelling_details=["torn khaki uniform scrap snagged on barbed wire barb", "spent flare canister casing"],
                    secondary_actions=["smoke drifting slowly from left to right across crater lip"],
                ),
                lighting=LightingSpec(
                    key_direction="BACKLIT",
                    key_intensity=0.50,
                    ambient_level=0.30,
                    shadow_direction="LONG_FORWARD",
                    color_temperature="COLD_DUSK",
                    rim_opportunity=False,
                    practical_lights=[],
                ),
                atmosphere=AtmosphereSpec(
                    haze="SMOKE_DUST",
                    weather="DRY",
                    time_of_day="DUSK",
                    volumetric_light=False,
                ),
                continuity=ContinuitySpec(
                    location_dna_ref="western_front",
                    recurring_features=["barbed wire", "shell craters", "mud terrain"],
                    lighting_consistency_key="cold_dawn_overcast",
                ),
                character=CharacterSpec(
                    character_id="none_pov",
                    approximate_position=[0.50, 0.50],
                    scale=0.0,
                    body_orientation="FRONT_THREE_QUARTER",
                    pose_envelope="ALERT_STAND",
                    action="first person point of view",
                ),
                negative_constraints=[
                    "NO human figures in foreground", "NO stickman", "Keep center view open across No Man's Land"
                ],
            )
        )

        # -------------------------------------------------------------------------
        # SHOT 10: DEEP_PERSPECTIVE / FOREGROUND_OCCLUSION (Beer Hall Munich 1919)
        # -------------------------------------------------------------------------
        blueprints.append(
            SceneBlueprint(
                scene_id="SC_10_BEER_HALL_CORRIDOR",
                shot_id="S10_SH10_DEEP_PERSPECTIVE",
                story=StorySpec(
                    narration="Hàng cột gỗ sâu hun hút trong quán bia Munich, tiền cảnh bị chắn bởi bàn gỗ và những cốc bia bốc hơi men.",
                    previous_beat="The speech gains momentum as listeners turn from their drinks.",
                    current_beat="Deep spatial drama: the orator commands the hall from deep within the architectural arcade.",
                    next_beat="Roaring approval shaking the beer hall rafters.",
                    purpose="DEEP_SPATIAL_COMMAND",
                    emotion="MAGNETIC_INTENSITY",
                ),
                history=HistorySpec(
                    year=1919,
                    location_id="beer_hall_munich",
                    country="Munich, Bavaria",
                    event_context="Bürgerbräukeller / Hofbräukeller interior spatial depth.",
                    political_military_context="Early political rallies in tavern beer cellars.",
                    available_technology=["gas lighting", "heavy timber architecture"],
                    appropriate_architecture=["Bavarian barrel arches", "thick timber post and lintel", "cross-vaulted bays"],
                    appropriate_transport=["none"],
                    appropriate_props=["large salt-glazed beer mugs with pewter lids", "wooden benches", "ashtrays"],
                    historical_constraints=["1919 German beer hall authentic architectural proportion"],
                ),
                camera=CameraSpec(
                    shot_size="DEEP_PERSPECTIVE",
                    height="EYE_LEVEL",
                    yaw=-16.0,
                    pitch=0.0,
                    lens_feel="WIDE_24MM",
                    horizon_y=0.54,
                ),
                perspective=PerspectiveSpec(
                    type="ONE_POINT",
                    primary_vp=[0.70, 0.54],
                    secondary_vp=[-0.50, 0.54],
                    depth_axis="RIGHT_BACK",
                ),
                composition=CompositionSpec(
                    visual_focus="PROTAGONIST",
                    character_reserved_zone=ReservedZone(x=0.65, y=0.34, width=0.22, height=0.54),
                    negative_space_zone={"x": 0.05, "y": 0.05, "width": 0.40, "height": 0.45},
                    foreground_occlusion=0.28,  # Rustic table and beer mugs occluding lower third
                    eyeline="HORIZON",
                ),
                environment=EnvironmentSpec(
                    foreground=["rustic heavy oak tavern table edge in lower foreground", "two ceramic salt-glazed beer steins"],
                    midground=["carved timber pillar framing left side", "long trestle table leading eye into depth"],
                    background=["repeating rhythmic arcade of dark wooden arches receding diagonally into right vanishing point"],
                    far_background=["distant back wall with warm illuminated menu board", "soft crowd murmur silhouettes"],
                    storytelling_details=["half-emptied beer mug with froth foam", "crumpled party membership leaflet on bench"],
                    secondary_actions=["ambient silhouettes of tavern patrons seated along distant benches"],
                ),
                lighting=LightingSpec(
                    key_direction="OVERHEAD",
                    key_intensity=0.85,
                    ambient_level=0.32,
                    shadow_direction="BOTTOM_LEFT",
                    color_temperature="WARM_INDOOR",
                    rim_opportunity=True,
                    practical_lights=["overhead brass gas chandeliers spaced down the corridor"],
                ),
                atmosphere=AtmosphereSpec(
                    haze="SMOKE_DUST",
                    weather="DRY",
                    time_of_day="NIGHT",
                    volumetric_light=True,
                ),
                continuity=ContinuitySpec(
                    location_dna_ref="beer_hall_munich",
                    recurring_features=["dark oak arcade", "beer steins", "vaulted arches"],
                    lighting_consistency_key="beer_hall_warm_amber",
                ),
                character=CharacterSpec(
                    character_id="orator",
                    approximate_position=[0.65, 0.52],
                    scale=0.50,
                    body_orientation="PROFILE_LEFT",
                    pose_envelope="ORATE_FIST",
                    action="standing on chair orating to the hall",
                ),
                negative_constraints=[
                    "No protagonist drawn", "No stickman", "Ensure strong one-point corridor depth recession"
                ],
            )
        )

        return blueprints
