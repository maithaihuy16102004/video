"""Story World Model and Story Beat Engine.

Architecture:
- Verbs create scenes; nouns only create illustrations.
- Canonical StoryWorldModel maintaining persistence across shots.
- StoryBeats answer: What happens? Why it matters? What changed? What viewer learns? Who causes it? Emotional state? Physical event?
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StoryBeat:
    beat_id: str
    section: str
    script_line_ids: list[str]
    primary_verb: str  # The physical action verb (e.g., PAINTS_OBSCURELY, MOBILIZES_CROWD, SIGNS_ENLISTMENT, DECONSTRUCTS_MYTH)
    what_happens: str
    why_it_matters: str
    what_changed: str  # The delta between state A and state B
    what_viewer_learns: str
    who_causes_it: str
    emotional_state: str
    physical_event: str
    character_action: str
    location_id: str
    involved_characters: list[str]
    important_objects: list[str]


@dataclass
class WorldCharacter:
    character_id: str
    name: str
    archetype: str
    historical_role: str
    costume_states: dict[str, str]
    persistent_attributes: dict[str, Any]


@dataclass
class WorldLocation:
    location_id: str
    canonical_name: str
    architecture_type: str
    primary_landmark: str
    materials: list[str]
    motivated_light: str
    circulation_paths: list[str]
    physical_bounds: dict[str, Any]


@dataclass
class WorldObject:
    object_id: str
    name: str
    category: str
    functional_use: str
    current_carrier: str | None


@dataclass
class WorldEvent:
    event_id: str
    name: str
    date_str: str
    location_id: str
    active_characters: list[str]
    impact_on_world: str


@dataclass
class StoryWorldModel:
    characters: dict[str, WorldCharacter]
    locations: dict[str, WorldLocation]
    objects: dict[str, WorldObject]
    events: list[WorldEvent]
    timeline_milestones: list[dict[str, str]]
    continuity_state: dict[str, Any]

    @classmethod
    def build_canonical_model(cls) -> StoryWorldModel:
        characters = {
            "PROTAGONIST_HITLER": WorldCharacter(
                character_id="PROTAGONIST_HITLER",
                name="Adolf Hitler",
                archetype="AUSTRIAN_DRIFTER_BECOMING_SOLDIER",
                historical_role="Austrian-born postcard artist who enlists in the Bavarian army",
                costume_states={
                    "1914_CIVILIAN": "Shabby dark civilian jacket, floppy artist cravat, unkempt trousers",
                    "1914_RECRUIT": "Fitted Feldgrau Bavarian M1907/10 tunic, Feldmütze soft cap, black leather waistbelt",
                    "1916_TRENCH_RUNNER": "Mud-stained M1915 tunic, Stahlhelm M16 helmet, gas mask tin canister, dispatch pouch",
                    "1918_HOSPITAL": "Prussian white hospital patient gown, gauze blindfold over eyes",
                    "1919_AGITATOR": "Demobilization trench coat, civilian collar, trench coat lapels",
                },
                persistent_attributes={
                    "head_silhouette": "ANGULAR_JAW_TAPER",
                    "hair_parting": "DEEP_LEFT_SWEEP_RIGHT",
                    "facial_features": "PIERCING_SLIT_EYES_AQUILINE_NOSE",
                    "head_to_body_ratio": 0.28,
                },
            ),
            "BAVARIAN_RECRUIT_SOLDIER": WorldCharacter(
                character_id="BAVARIAN_RECRUIT_SOLDIER",
                name="Bavarian Enlisted Soldier",
                archetype="AVERAGE_CIVILIAN_SOLDIER",
                historical_role="Local Munich young man joining the war rush with naive enthusiasm",
                costume_states={
                    "1914_RECRUIT": "Standard Bavarian infantry service uniform with blue-and-white cockade",
                },
                persistent_attributes={
                    "head_silhouette": "ROUNDED_SQUARE_JAW",
                    "hair_parting": "SHORT_MILITARY_BUZZ",
                    "head_to_body_ratio": 0.27,
                },
            ),
            "ENLISTMENT_OFFICER": WorldCharacter(
                character_id="ENLISTMENT_OFFICER",
                name="Bavarian Recruitment Officer",
                archetype="BUREAUCRATIC_AUTHORITY",
                historical_role="Officer administering oath of allegiance and regiment assignment",
                costume_states={
                    "1914_OFFICER": "Bavarian officer tunic, high stand collar, Pickelhaube spiked helmet on desk, officer sash",
                },
                persistent_attributes={
                    "head_silhouette": "SHARP_CHISELED_JAW",
                    "facial_hair": "KAISER_WILHELM_UPTURNED_MUSTACHE",
                    "head_to_body_ratio": 0.27,
                },
            ),
        }

        locations = {
            "LOC_001_ODEONSPLATZ": WorldLocation(
                location_id="LOC_001_ODEONSPLATZ",
                canonical_name="Munich Odeonsplatz & Feldherrnhalle, August 1914",
                architecture_type="NEOCLASSICAL_MONUMENTAL_PLAZA",
                primary_landmark="Feldherrnhalle Triple Arched Loggia with Bavarian Lion Statues",
                materials=["CARVED_LIMESTONE", "GRANITE_CURBS", "COBBLESTONES", "WROUGHT_IRON"],
                motivated_light="Warm August overcast daylight filtering between classical facades",
                circulation_paths=["Central Odeonsplatz cobblestone thoroughfare", "Pedestrian sidewalk leading to Loggia steps"],
                physical_bounds={"width": 1920, "height": 1080, "horizon_y": 540},
            ),
            "LOC_002_RECRUITMENT_STATION": WorldLocation(
                location_id="LOC_002_RECRUITMENT_STATION",
                canonical_name="Bavarian War Ministry Recruitment Station, Munich, August 1914",
                architecture_type="NEOCLASSICAL_ADMINISTRATIVE_COURTYARD",
                primary_landmark="Carved Royal Bavarian Crest over Masonry Archway",
                materials=["ASHLAR_STONE", "OAK_DESKS", "CANVAS_BANNERS"],
                motivated_light="Side-raking courtyard afternoon light highlighting enlistment ledger",
                circulation_paths=["Enlistment queue corridor", "Clerk processing table"],
                physical_bounds={"width": 1920, "height": 1080, "horizon_y": 520},
            ),
            "LOC_003_WESTERN_FRONT_TRENCH": WorldLocation(
                location_id="LOC_003_WESTERN_FRONT_TRENCH",
                canonical_name="Western Front Flanders Communication Trench, 1914-1916",
                architecture_type="SUBTERRANEAN_REVETTED_EARTHEN_TRENCH",
                primary_landmark="Shattered Artillery Tree Stump on Sunken Parapet",
                materials=["MUD", "TIMBER_REVETMENT", "SANDBAGS", "CORRUGATED_IRON"],
                motivated_light="Dull mustard-tinted sky with distant artillery flash and dugout lantern",
                circulation_paths=["Zigzag duckboard traverse", "Dugout command entry"],
                physical_bounds={"width": 1920, "height": 1080, "horizon_y": 420},
            ),
        }

        objects = {
            "OBJ_POSTCARD_SKETCHBOOK": WorldObject(
                object_id="OBJ_POSTCARD_SKETCHBOOK",
                name="Handmade Watercolor Postcards of Munich Landmark",
                category="PERSONAL_DOCUMENT",
                functional_use="Selling cheap architectural tourist sketches to survive",
                current_carrier="PROTAGONIST_HITLER",
            ),
            "OBJ_MOBILIZATION_DECREE": WorldObject(
                object_id="OBJ_MOBILIZATION_DECREE",
                name="Imperial War Mobilization Proclamation (Allgemeine Mobilmachung)",
                category="OFFICIAL_POSTER",
                functional_use="Pasted onto limestone walls commanding all able-bodied men to report",
                current_carrier=None,
            ),
            "OBJ_ENLISTMENT_LEDGER": WorldObject(
                object_id="OBJ_ENLISTMENT_LEDGER",
                name="16th Bavarian Reserve Infantry Regiment Roster",
                category="MILITARY_REGISTER",
                functional_use="Official ledger recording recruit name, birth place, and regimental number",
                current_carrier="ENLISTMENT_OFFICER",
            ),
            "OBJ_DIP_PEN": WorldObject(
                object_id="OBJ_DIP_PEN",
                name="Steel Nib Dip Pen with Black Ink",
                category="WRITING_INSTRUMENT",
                functional_use="Signing enlistment oath",
                current_carrier="PROTAGONIST_HITLER",
            ),
            "OBJ_NEWSPAPER_EXTRA": WorldObject(
                object_id="OBJ_NEWSPAPER_EXTRA",
                name="Münchner Neueste Nachrichten War Extra Edition",
                category="PRINT_MEDIA",
                functional_use="Headlines shouting war declaration against Russia and France",
                current_carrier="BAVARIAN_RECRUIT_SOLDIER",
            ),
        }

        events = [
            WorldEvent(
                event_id="EVT_001_CIVILIAN_DRIFT",
                name="Bohemian Drifter in Pre-War Munich",
                date_str="Early Summer 1914",
                location_id="LOC_001_ODEONSPLATZ",
                active_characters=["PROTAGONIST_HITLER"],
                impact_on_world="Protagonist isolated against grand public architecture, unable to find societal role.",
            ),
            WorldEvent(
                event_id="EVT_002_MOBILIZATION_ERUPTION",
                name="Declaration of War & Crowd Eruption",
                date_str="August 1-3, 1914",
                location_id="LOC_001_ODEONSPLATZ",
                active_characters=["PROTAGONIST_HITLER", "BAVARIAN_RECRUIT_SOLDIER"],
                impact_on_world="Civilians flood Odeonsplatz in patriotic euphoria, tearing down individual isolation.",
            ),
            WorldEvent(
                event_id="EVT_003_ENLISTMENT_PLEDGE",
                name="Volunteering for the Bavarian 16th RIR",
                date_str="August 16, 1914",
                location_id="LOC_002_RECRUITMENT_STATION",
                active_characters=["PROTAGONIST_HITLER", "ENLISTMENT_OFFICER", "BAVARIAN_RECRUIT_SOLDIER"],
                impact_on_world="Protagonist sheds civilian vagrancy, formally entering military state apparatus.",
            ),
        ]

        timeline_milestones = [
            {"date": "August 1914", "event": "Mobilization in Munich, enlists in Bavarian 16th RIR"},
            {"date": "October 1914", "event": "First Battle of Ypres, Western Front deployment"},
            {"date": "October 1916", "event": "Wounded at Battle of the Somme"},
            {"date": "October 1918", "event": "Blinded by mustard gas, hospitalized at Pasewalk"},
            {"date": "November 1918", "event": "Armistice signed, Imperial Germany falls"},
            {"date": "September 1919", "event": "Assigned to infiltrate DAP at Sterneckerbräu tavern"},
        ]

        continuity_state = {
            "current_era": "AUGUST_1914",
            "protagonist_costume": "1914_CIVILIAN",
            "protagonist_physical_injuries": "NONE",
            "weather": "WARM_LATE_SUMMER_OVERCAST",
            "active_location": "LOC_001_ODEONSPLATZ",
        }

        return cls(
            characters=characters,
            locations=locations,
            objects=objects,
            events=events,
            timeline_milestones=timeline_milestones,
            continuity_state=continuity_state,
        )


class EpisodeStoryBeats:
    """Story Beat Decomposition for the Contiguous 30-45s Rebuild Section (Munich 1914 Hook)."""

    @classmethod
    def get_target_section_beats(cls) -> list[StoryBeat]:
        return [
            # BEAT 1: THE DRIFTER AT 25 (ESTABLISHMENT & ISOLATION)
            StoryBeat(
                beat_id="BEAT_01_DRIFTER_ISOLATION",
                section="SECTION_01_HOOK_MUNICH_1914",
                script_line_ids=["EP01_L01"],
                primary_verb="PAINTS_OBSCURELY",
                what_happens="25-year-old Hitler stands isolated on Odeonsplatz holding unsold architectural postcard watercolors as the city passes by.",
                why_it_matters="Establishes complete lack of status, purpose, and money before the historical cataclysm.",
                what_changed="Viewer recognizes the mundane, unheroic obscurity of the protagonist before history swept him up.",
                what_viewer_learns="He was not a born dictator or grand figure; he was an anonymous drifter without career or future.",
                who_causes_it="Protagonist's own bohemian failures and Austrian vagrancy.",
                emotional_state="Melancholy, aimless, detached, quietly desperate.",
                physical_event="Hitler looks down at watercolor postcards; pedestrians walk past without noticing him.",
                character_action="Holding postcard folder against chest, looking sideways at indifferent crowd.",
                location_id="LOC_001_ODEONSPLATZ",
                involved_characters=["PROTAGONIST_HITLER"],
                important_objects=["OBJ_POSTCARD_SKETCHBOOK"],
            ),

            # BEAT 2: THE MOBILIZATION EXPLOSION (GEOPOLITICAL CATACLYSM)
            StoryBeat(
                beat_id="BEAT_02_MOBILIZATION_SURGE",
                section="SECTION_01_HOOK_MUNICH_1914",
                script_line_ids=["EP01_L02", "EP01_L03"],
                primary_verb="ERUPTS_IN_WAR_MOBILIZATION",
                what_happens="Crowds surge forward pasting the Imperial War Proclamation onto neoclassical columns; newspapers are thrust into the air.",
                why_it_matters="Personal insignificance is instantly swallowed by the largest imperial conflict in human history.",
                what_changed="State of the world transitions from peaceful civilian boredom into mass collective war euphoria.",
                what_viewer_learns="1914 Europe greeted the outbreak of world war not with dread, but with ecstatic celebration.",
                who_causes_it="European empires mobilizing their millions.",
                emotional_state="Euphoric, manic, chaotic, surging momentum.",
                physical_event="A herald pastes the Allgemeine Mobilmachung poster onto stone ashlar; crowd rushes around protagonist.",
                character_action="Hitler is jostled by surging citizens, his gaze pulled up toward the war proclamation banner.",
                location_id="LOC_001_ODEONSPLATZ",
                involved_characters=["PROTAGONIST_HITLER", "BAVARIAN_RECRUIT_SOLDIER"],
                important_objects=["OBJ_MOBILIZATION_DECREE", "OBJ_NEWSPAPER_EXTRA"],
            ),

            # BEAT 3: THE ENLISTMENT PLEDGE (HISTORICAL TURN & IDENTITY SHIFT)
            StoryBeat(
                beat_id="BEAT_03_ENLISTMENT_PLEDGE",
                section="SECTION_01_HOOK_MUNICH_1914",
                script_line_ids=["EP01_L04", "EP01_L05", "EP01_L06"],
                primary_verb="SIGNS_MILITARY_ROSTER",
                what_happens="Hitler stands before the Bavarian enlistment table under the Feldherrnhalle arches, gripping the pen to sign the regiment roster.",
                why_it_matters="An Austrian national illegally/irregularly volunteers for a German kingdom, trading vagrancy for a military home.",
                what_changed="Protagonist identity shifts from bohemian civilian outsider to enlisted Bavarian soldier.",
                what_viewer_learns="He found his first true belonging and purpose in military conformity.",
                who_causes_it="Hitler voluntarily petitions to join the Bavarian army.",
                emotional_state="Solemn, determined, secretly relieved, desperate to belong.",
                physical_event="Hitler leans over the wooden desk, dipping pen in ink, speaking to fellow recruit in line.",
                character_action="Pen poised over ledger, eyes looking up at the recruit next to him: 'Mọi người đều đi đánh nhau à?'",
                location_id="LOC_001_ODEONSPLATZ",
                involved_characters=["PROTAGONIST_HITLER", "BAVARIAN_RECRUIT_SOLDIER", "ENLISTMENT_OFFICER"],
                important_objects=["OBJ_ENLISTMENT_LEDGER", "OBJ_DIP_PEN"],
            ),

            # BEAT 4: THE DELUSION & REALITY SHOCK (CHRISTMAS MYTH VS HISTORICAL SPOILER)
            StoryBeat(
                beat_id="BEAT_04_DELUSION_AND_SPOILER",
                section="SECTION_01_HOOK_MUNICH_1914",
                script_line_ids=["EP01_L07", "EP01_L08", "EP01_L09"],
                primary_verb="CONFRONTS_HISTORICAL_IRONY",
                what_happens="Recruit shares the myth that war will end before Christmas; protagonist retrospectively reframes the reality with biting hindsight.",
                why_it_matters="Exposes the tragic naivety of the generation about to be slaughtered in Flanders mud.",
                what_changed="Tonal trajectory shatters: romantic delusion collapses into the looming shadow of four years of trench horror.",
                what_viewer_learns="The war they thought would be an autumn adventure became industrial annihilation.",
                who_causes_it="Historical reality and protagonist's retrospective realization.",
                emotional_state="Ironic, chilling, stark realization, foreboding.",
                physical_event="Hitler looks forward into the camera with naive anticipation; the frame's lighting dims to cold slate as the reality check hits.",
                character_action="Protagonist now in recruit Feldmütze soft cap, holding recruit papers, smiling faintly before the reality settles.",
                location_id="LOC_001_ODEONSPLATZ",
                involved_characters=["PROTAGONIST_HITLER", "BAVARIAN_RECRUIT_SOLDIER"],
                important_objects=["OBJ_ENLISTMENT_LEDGER"],
            ),
        ]
