"""Universal Motion Canvas Bridge V4.1: Cinematic Story Sequence Engine.

Exports strict data contracts for the 6-beat causal storytelling sequence:
BEAT A -> BEAT B -> BEAT C -> BEAT D -> BEAT E -> BEAT F.

Full persistence of 3D Odeonsplatz world, data-driven StickCharacter performance,
dynamic CrowdField states, and physical object interaction (OBJ_PROCLAMATION_1914).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ProductionScenePackageV41:
    schema_version: str = "2026.11-V4.1-CINEMATIC-SEQUENCE"
    project_id: str = "episode01_munich_1914"
    sequence_id: str = "SEQ_001_ODEONSPLATZ_MOBILIZATION"
    storytelling_mode: str = "FIRST_PERSON_ROLEPLAY"
    primary_pov_character_id: str = "char_hitler"
    total_sequence_duration_seconds: float = 26.50
    fps: int = 24

    # 1. Sequence Beats & Event Graph
    story_beats: list[dict[str, Any]] = field(default_factory=list)
    event_graph: list[dict[str, Any]] = field(default_factory=list)

    # 2. Persistent 3D World Model
    scene_world: dict[str, Any] = field(default_factory=dict)

    # 3. Actors (Protagonist + Supporting)
    actors: list[dict[str, Any]] = field(default_factory=list)

    # 4. Crowd Field (Event-Driven Dynamic Citizen Field)
    crowd_field: dict[str, Any] = field(default_factory=dict)

    # 5. Interactive Physical Objects
    interactive_objects: list[dict[str, Any]] = field(default_factory=list)

    # 6. Shot Plan (6 Story-Motivated Viewpoints)
    shots: list[dict[str, Any]] = field(default_factory=list)

    # 7. Voice Timeline (Strictly 1.00x native duration)
    voice_timeline: dict[str, Any] = field(default_factory=dict)

    # 8. Causal SFX Timeline
    sfx_timeline: list[dict[str, Any]] = field(default_factory=list)

    # 9. Historical Visual Grounding
    historical_grounding: list[dict[str, Any]] = field(default_factory=list)

    def export_json(self, output_path: Path) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data


def build_v41_package() -> ProductionScenePackageV41:
    pkg = ProductionScenePackageV41(
        schema_version="2026.11-V4.1-CINEMATIC-SEQUENCE",
        project_id="episode01_munich_1914",
        sequence_id="SEQ_001_ODEONSPLATZ_MOBILIZATION",
        storytelling_mode="FIRST_PERSON_ROLEPLAY",
        primary_pov_character_id="char_hitler",
        total_sequence_duration_seconds=26.50,
        fps=24,
        story_beats=[
            {
                "beat_id": "BEAT_A_ISOLATED_INDIVIDUAL",
                "beat_name": "The Isolated Individual",
                "time_range": [0.0, 5.5],
                "primary_verb": "DRIFTS_IN_OBSCURITY",
                "what_happens": "25-year-old bohemian drifter Hitler walks alone through Odeonsplatz, clutching thin cardboard portfolio.",
                "why_it_matters": "Establishes baseline low status and profound civilian insignificance before world war erupts.",
                "who_causes_it": "Protagonist's own bohemian failures and European economic obscurity.",
                "what_physically_changes": "Protagonist walks along cobblestones from plaza left toward center.",
                "protagonist_want": "Direction, validation, an escape from humiliating poverty.",
                "obstacle": "Lack of career, money, prospects, and formal citizenship.",
                "viewer_learns": "Hitler in August 1914 was an awkward, obscure loner dwarfed by Bavarian architecture.",
                "protagonist_knows": "He is broke and directionless at age 25.",
                "protagonist_not_knows": "A continent-wide catastrophe will erupt in days.",
                "location_id": "LOC_001_ODEONSPLATZ",
                "story_state": "STATE_01_OBSCURE_CIVILIAN_BOHEMIAN"
            },
            {
                "beat_id": "BEAT_B_INFORMATION_ARRIVES",
                "beat_name": "Information Arrives",
                "time_range": [5.5, 11.12],
                "primary_verb": "PROCLAMATION_POSTED",
                "what_happens": "A royal Bavarian mobilization decree ('Kriegszustand') is posted on the Odeonsplatz Litfaßsäule pillar; Hitler decelerates.",
                "why_it_matters": "The external world intrudes violently on individual aimlessness.",
                "who_causes_it": "Imperial Austro-Hungarian and German mobilization declarations.",
                "what_physically_changes": "New physical object OBJ_PROCLAMATION_1914 appears on the advertising pillar; Hitler pauses.",
                "protagonist_want": "To understand what the commotion is about.",
                "obstacle": "Distance from the pillar and crowded plaza.",
                "viewer_learns": "Munich is suddenly placed under martial law / mobilization.",
                "protagonist_knows": "Something unprecedented has occurred in the city center.",
                "protagonist_not_knows": "This single event will provide him with an army uniform and life purpose.",
                "location_id": "LOC_001_ODEONSPLATZ",
                "story_state": "STATE_02_MOBILIZATION_DECREE_POSTED"
            },
            {
                "beat_id": "BEAT_C_CROWD_FIELD_SURGE",
                "beat_name": "The Crowd Changes",
                "time_range": [11.12, 15.5],
                "primary_verb": "CROWD_CONVERGES",
                "what_happens": "Munich citizens across the square stop walking, turn heads, and surge toward the pillar, forming an agitated collective.",
                "why_it_matters": "Demonstrates the collective psychological shift from peacetime peace to wartime fever.",
                "who_causes_it": "The urgent headline of the mobilization decree.",
                "what_physically_changes": "Crowd density surges from 4 sparse walkers to 16 agitated citizens clustered at the pillar.",
                "protagonist_want": "To see what the crowd is reacting to.",
                "obstacle": "Growing crowd barrier.",
                "viewer_learns": "The public mood in Munich is electric, anxious, and rapidly unifying.",
                "protagonist_knows": "The entire city is turning toward a single focal point.",
                "protagonist_not_knows": "How rapidly this enthusiasm will consume Europe.",
                "location_id": "LOC_001_ODEONSPLATZ",
                "story_state": "STATE_03_PUBLIC_AGITATION_AND_CONVERGENCE"
            },
            {
                "beat_id": "BEAT_D_PROTAGONIST_REACTION",
                "beat_name": "The Protagonist Reacts",
                "time_range": [15.5, 19.5],
                "primary_verb": "TURNS_ATTENTION_AND_AWAKENS",
                "what_happens": "Hitler's head and eyeline snap toward the surging crowd; his body rotates, gripping his portfolio tightly.",
                "why_it_matters": "The protagonist's subjective consciousness connects with the collective historical event.",
                "who_causes_it": "The roar and rush of the crowd.",
                "what_physically_changes": "Hitler rotates torso 35°, changes facial expression from sullen apathy to intense focus.",
                "protagonist_want": "To comprehend the scale of the crisis.",
                "obstacle": "His own habitual detachment and outsider status.",
                "viewer_learns": "For the first time, the protagonist's eyes are alive with purpose.",
                "protagonist_knows": "War has finally broken out across European empires.",
                "protagonist_not_knows": "He will soon volunteer for King Ludwig III's regiment.",
                "location_id": "LOC_001_ODEONSPLATZ",
                "story_state": "STATE_04_WAR_REALIZATION_AND_ATTENTION"
            },
            {
                "beat_id": "BEAT_E_DECISION_INSPECTION",
                "beat_name": "The Decision Forms",
                "time_range": [19.5, 23.0],
                "primary_verb": "INSPECTS_AND_RESOLVES",
                "what_happens": "Hitler approaches the edge of the crowd, leans forward, and reads the bold royal decree text.",
                "why_it_matters": "Catalyzes the internal decision to abandon bohemian drift and seek military service.",
                "who_causes_it": "The explicit wording of the royal proclamation.",
                "what_physically_changes": "Hitler steps forward 2 strides, leans torso 14°, eyeline locks to notice headline.",
                "protagonist_want": "A way out of obscurity; a cause larger than his personal misery.",
                "obstacle": "He is an Austrian national with no legal right to serve in Bavaria.",
                "viewer_learns": "The protagonist sees war not as a horror, but as an escape from personal failure.",
                "protagonist_knows": "The old civilian life is over.",
                "protagonist_not_knows": "The catastrophic trench reality that awaits in Flanders.",
                "location_id": "LOC_001_ODEONSPLATZ",
                "story_state": "STATE_05_PERSONAL_RESOLUTION_CATALYZED"
            },
            {
                "beat_id": "BEAT_F_MONUMENTAL_RESOLUTION",
                "beat_name": "Transition to Consequence",
                "time_range": [23.0, 26.5],
                "primary_verb": "STANDS_RESOLUTE_FOR_ENLISTMENT",
                "what_happens": "Hitler stands resolute in front of the monumental Feldherrnhalle arches as the crowd waves hats, setting up his enlistment petition.",
                "why_it_matters": "Completes the transformation from isolated bohemian outcast to future soldier of the 16th Bavarian Reserve.",
                "who_causes_it": "Protagonist's crystallization of purpose.",
                "what_physically_changes": "Hitler squares shoulders, head lifts to horizon; crowd in background raises hats in patriotic fervor.",
                "protagonist_want": "To enlist immediately in the Bavarian army.",
                "obstacle": "Draft bureaucracy and Austrian citizenship check.",
                "viewer_learns": "The stage is set for his fateful petition to King Ludwig III.",
                "protagonist_knows": "He will go to the recruitment bureau tomorrow morning.",
                "protagonist_not_knows": "That within 90 days half his regiment will be dead at Ypres.",
                "location_id": "LOC_001_ODEONSPLATZ",
                "story_state": "STATE_06_RESOLUTION_TOWARD_ENLISTMENT"
            }
        ],
        event_graph=[
            {"event_id": "EVT_01", "beat_id": "BEAT_A", "cause": "Bohemian failure", "action": "Solitary walk across Odeonsplatz", "physical_delta": "Hitler moves along cobblestones", "consequence": "Vulnerable isolated baseline"},
            {"event_id": "EVT_02", "beat_id": "BEAT_B", "cause": "Mobilization declared", "action": "Notice posted on Litfaßsäule pillar", "physical_delta": "OBJ_PROCLAMATION_1914 appears", "consequence": "Public shock"},
            {"event_id": "EVT_03", "beat_id": "BEAT_C", "cause": "Notice visible", "action": "Passersby halt and surge to pillar", "physical_delta": "Crowd density multiplies 4x", "consequence": "Agitated social field"},
            {"event_id": "EVT_04", "beat_id": "BEAT_D", "cause": "Crowd roar", "action": "Hitler turns head and clutches portfolio", "physical_delta": "Body rotates 35°, eyeline shifts", "consequence": "Protagonist awakened"},
            {"event_id": "EVT_05", "beat_id": "BEAT_E", "cause": "Curiosity and need", "action": "Hitler approaches and reads decree", "physical_delta": "Hitler steps forward, leans in", "consequence": "Internal decision forms"},
            {"event_id": "EVT_06", "beat_id": "BEAT_F", "cause": "Decision reached", "action": "Hitler stands resolute in front of loggia", "physical_delta": "Shoulders square, chin lifts", "consequence": "Leads to enlistment petition"}
        ],
        scene_world={
            "location_id": "LOC_001_ODEONSPLATZ",
            "canonical_name": "Munich Odeonsplatz & Feldherrnhalle",
            "historical_era": "August 1914",
            "dimensions": {"width": 1920, "height": 1080},
            "ground_plane": {
                "y_ground_canvas": 760,
                "material": "GRANITE_COBBLESTONE",
                "reflectivity": 0.35,
                "primary_color": "#282624",
                "mortar_color": "#181716"
            },
            "threejs_environment": {
                "enabled": True,
                "scene_type": "ARCHITECTURAL_LOGGIA_AND_PLAZA_3D",
                "architecture": {
                    "facade_style": "FLORENTINE_NEOCLASSICAL_FELDHERRNHALLE",
                    "stone_type": "KELLHEIM_LIMESTONE",
                    "stone_color": "#CBB89D",
                    "shadow_stone_color": "#6E6050",
                    "z_facade": -4.5,
                    "arches": [
                        {"id": "ARCH_LEFT", "x": -5.8, "base_y": 1.5, "width": 4.4, "height": 7.5, "radius": 2.2},
                        {"id": "ARCH_CENTER", "x": 0.0, "base_y": 1.5, "width": 5.2, "height": 8.2, "radius": 2.6},
                        {"id": "ARCH_RIGHT", "x": 5.8, "base_y": 1.5, "width": 4.4, "height": 7.5, "radius": 2.2}
                    ],
                    "columns": [
                        {"id": "COL_1", "x": -8.2, "radius": 0.65, "height": 8.1},
                        {"id": "COL_2", "x": -2.8, "radius": 0.65, "height": 8.1},
                        {"id": "COL_3", "x": 2.8, "radius": 0.65, "height": 8.1},
                        {"id": "COL_4", "x": 8.2, "radius": 0.65, "height": 8.1}
                    ],
                    "statues": [
                        {"name": "Count Tilly Bronze Monument", "side": "LEFT", "pos": [-5.8, 1.8, -7.7]},
                        {"name": "Prince Wrede Bronze Monument", "side": "RIGHT", "pos": [5.8, 1.8, -7.7]}
                    ],
                    "lions": [
                        {"side": "LEFT", "pos": [-11.2, 1.5, -3.3]},
                        {"side": "RIGHT", "pos": [11.2, 1.5, -3.3]}
                    ]
                },
                "street_furniture": {
                    "litfass_pillar": {
                        "id": "OBJ_LITFASS_PILLAR",
                        "pos": [3.2, 0.0, 1.8],
                        "radius": 0.85,
                        "height": 3.4,
                        "color": "#4A4640",
                        "placard_color": "#F0E8D6"
                    }
                },
                "lighting": {
                    "sun": {"color": "#FFF2DA", "intensity": 1.35, "position": [16, 24, 14]},
                    "sky_ambient": {"color": "#6E8092", "intensity": 0.60},
                    "ground_bounce": {"color": "#38322B", "intensity": 0.28}
                }
            }
        },
        actors=[
            {
                "character_id": "char_hitler",
                "canonical_name": "Adolf Hitler",
                "role": "PROTAGONIST_NARRATOR",
                "voice_id": "Đức Trí",
                "render_type": "STICK_CHARACTER_2D_PROJECTED",
                "proportions": {
                    "head_to_body_ratio": 0.28,
                    "head_diameter_px": 54,
                    "total_standing_height_px": 192,
                    "limb_width_px": 4.5
                },
                "dna": {
                    "head_shape": "ANGULAR_OVAL_LEAN",
                    "hair_color": "#221A14",
                    "hair_style": "1914_SIDE_PARTED_FOREHEAD_SWEEP",
                    "facial_hair": "1914_WIDE_KAISER_MUSTACHE_DROOPING",
                    "costume": {
                        "model": "1914_CIVILIAN_BOHEMIAN",
                        "frock_coat_color": "#262C33",
                        "collar_color": "#ECE8DE",
                        "cravat_color": "#181A1D",
                        "trousers_color": "#202428"
                    }
                },
                "staging": {
                    "initial_world_pos": [-3.0, 0.0, 1.2],
                    "hand_held_prop": {
                        "type": "ARTIST_PORTFOLIO",
                        "color": "#423324",
                        "hand": "LEFT",
                        "width": 42,
                        "height": 54
                    }
                },
                "performance_cues": [
                    {"time": 0.0,  "action": "WALK", "pos": [-3.0, 0.0, 1.2], "torso_lean": 4.0, "head_angle": 0.0, "eyeline": "FORWARD"},
                    {"time": 5.5,  "action": "SLOW_DOWN", "pos": [-1.8, 0.0, 0.8], "torso_lean": 1.0, "head_angle": 0.0, "eyeline": "FORWARD"},
                    {"time": 8.0,  "action": "PAUSE", "pos": [-1.5, 0.0, 0.6], "torso_lean": -2.0, "head_angle": 0.0, "eyeline": "FORWARD"},
                    {"time": 11.5, "action": "NOTICE_HEAD_TURN", "pos": [-1.5, 0.0, 0.6], "torso_lean": 2.0, "head_angle": 0.12, "eyeline": "TOWARD_PILLAR"},
                    {"time": 16.0, "action": "CLUTCH_PORTFOLIO_AND_ROTATE", "pos": [-1.4, 0.0, 0.5], "torso_lean": 6.0, "head_angle": 0.18, "eyeline": "TOWARD_PILLAR"},
                    {"time": 20.0, "action": "APPROACH_AND_LEAN_IN", "pos": [-0.6, 0.0, 0.8], "torso_lean": 12.0, "head_angle": 0.22, "eyeline": "READING_DECREE"},
                    {"time": 23.5, "action": "STAND_RESOLUTE", "pos": [-0.4, 0.0, 0.6], "torso_lean": -4.0, "head_angle": -0.06, "eyeline": "TOWARD_HORIZON"}
                ]
            }
        ],
        crowd_field={
            "enabled": True,
            "anchor_object_id": "OBJ_LITFASS_PILLAR",
            "citizens": [
                {"id": "CIT_01", "type": "BOURGEOIS_BOWLER", "base_x": 4.8, "base_z": 2.2, "height_px": 182, "hat": "BOWLER", "color": "#28292B"},
                {"id": "CIT_02", "type": "WORKER_CAP", "base_x": 2.2, "base_z": 1.4, "height_px": 174, "hat": "CAP", "color": "#383632"},
                {"id": "CIT_03", "type": "OFFICER_PEAK", "base_x": 3.8, "base_z": 1.0, "height_px": 188, "hat": "OFFICER", "color": "#2F3B34"},
                {"id": "CIT_04", "type": "STUDENT_BARE", "base_x": 4.2, "base_z": 2.8, "height_px": 178, "hat": "NONE", "color": "#3D372E"},
                {"id": "CIT_05", "type": "ELDERLY_GENT", "base_x": 1.6, "base_z": 2.5, "height_px": 170, "hat": "TOPHAT", "color": "#1C1D1F"},
                {"id": "CIT_06", "type": "MERCHANT_COAT", "base_x": 5.2, "base_z": 1.6, "height_px": 184, "hat": "BOWLER", "color": "#332B25"},
                {"id": "CIT_07", "type": "WORKER_CAP", "base_x": 2.8, "base_z": 3.0, "height_px": 176, "hat": "CAP", "color": "#2B3036"},
                {"id": "CIT_08", "type": "NEWSBOY", "base_x": 3.0, "base_z": 0.6, "height_px": 158, "hat": "FLATCAP", "color": "#473D31"},
                {"id": "CIT_09", "type": "CLERK_FROCK", "base_x": 4.5, "base_z": 0.8, "height_px": 175, "hat": "BOWLER", "color": "#222528"},
                {"id": "CIT_10", "type": "CIVILIAN_WALKER", "base_x": -4.2, "base_z": 2.0, "height_px": 180, "hat": "BOWLER", "color": "#303236"},
                {"id": "CIT_11", "type": "CIVILIAN_WALKER", "base_x": -2.5, "base_z": 3.5, "height_px": 172, "hat": "CAP", "color": "#2A2826"},
                {"id": "CIT_12", "type": "SOLDIER_RESERVE", "base_x": 5.8, "base_z": 3.2, "height_px": 186, "hat": "PICKELHAUBE", "color": "#354038"}
            ],
            "timeline_states": [
                {"t_start": 0.0,  "state": "PASSING", "cluster_radius": 5.5, "attention_ratio": 0.15, "description": "Citizens stroll unhurriedly across square."},
                {"t_start": 5.5,  "state": "NOTICING", "cluster_radius": 4.0, "attention_ratio": 0.65, "description": "Passersby halt, heads turning toward newly posted decree."},
                {"t_start": 11.12,"state": "SURGING",  "cluster_radius": 2.2, "attention_ratio": 0.95, "description": "Citizens converge rapidly into a dense crowd at the pillar."},
                {"t_start": 15.5, "state": "READING",  "cluster_radius": 1.8, "attention_ratio": 1.00, "description": "Crowd reads headline and debates in agitated clusters."},
                {"t_start": 19.5, "state": "EXCITED_DEBATE", "cluster_radius": 1.9, "attention_ratio": 0.90, "description": "Wartime excitement and murmurs sweep through the crowd."},
                {"t_start": 23.0, "state": "PATRIOTIC_CHEER", "cluster_radius": 2.4, "attention_ratio": 0.85, "description": "Citizens raise hats and cheer as wartime mobilization begins."}
            ]
        },
        interactive_objects=[
            {
                "object_id": "OBJ_PROCLAMATION_1914",
                "canonical_name": "Royal Bavarian Mobilization Proclamation (Kriegszustand)",
                "attached_to_id": "OBJ_LITFASS_PILLAR",
                "world_pos": [3.2, 1.6, 1.8],
                "dimensions": {"width_m": 0.70, "height_m": 1.05},
                "headline_text": "SEINE MAJESTÄT DER KÖNIG: MOBILMACHUNG",
                "state_timeline": [
                    {"time": 0.0,  "state": "UNPOSTED"},
                    {"time": 5.5,  "state": "POSTED_FRESH"},
                    {"time": 11.12,"state": "CROWD_READING"},
                    {"time": 15.5, "state": "HITLER_SIGHTED"},
                    {"time": 19.5, "state": "HITLER_INSPECTING"},
                    {"time": 23.0, "state": "DECISION_CATALYZED"}
                ]
            }
        ],
        shots=[
            {
                "shot_index": 1,
                "shot_id": "SHOT_01_ISOLATED_INDIVIDUAL",
                "beat_id": "BEAT_A_ISOLATED_INDIVIDUAL",
                "time_range": [0.0, 5.5],
                "duration_sec": 5.5,
                "shot_type": "WIDE_ENVIRONMENTAL_ESTABLISHING_TRACKING",
                "camera": {
                    "start_pos": [-3.6, 2.3, 12.0],
                    "end_pos": [-2.2, 2.2, 10.5],
                    "start_tgt": [-0.4, 3.2, -4.5],
                    "end_tgt": [0.0, 3.1, -4.5],
                    "fov": 46.0
                },
                "story_purpose": "Establishes Munich Odeonsplatz and the protagonist's profound civilian insignificance dwarfed by neoclassical loggia.",
                "why_cut_earned": "First shot: establishes physical space, human scale, and solitary baseline status."
            },
            {
                "shot_index": 2,
                "shot_id": "SHOT_02_INFORMATION_ARRIVES",
                "beat_id": "BEAT_B_INFORMATION_ARRIVES",
                "time_range": [5.5, 11.12],
                "duration_sec": 5.62,
                "shot_type": "MEDIUM_INFORMATION_INSERT_TRACKING",
                "camera": {
                    "start_pos": [1.8, 2.0, 6.2],
                    "end_pos": [2.2, 1.9, 5.0],
                    "start_tgt": [3.2, 1.6, 1.8],
                    "end_tgt": [3.2, 1.6, 1.8],
                    "fov": 42.0
                },
                "story_purpose": "Introduces the inciting incident: the royal Bavarian mobilization decree slapped onto the Litfaßsäule pillar.",
                "why_cut_earned": "Reveals critical new story information (mobilization decree object) that was invisible in the wide establishing shot."
            },
            {
                "shot_index": 3,
                "shot_id": "SHOT_03_CROWD_FIELD_SURGE",
                "beat_id": "BEAT_C_CROWD_FIELD_SURGE",
                "time_range": [11.12, 15.5],
                "duration_sec": 4.38,
                "shot_type": "MID_WIDE_CROWD_CONVERGENCE",
                "camera": {
                    "start_pos": [-0.6, 2.4, 9.2],
                    "end_pos": [0.4, 2.3, 7.8],
                    "start_tgt": [2.4, 1.9, 1.6],
                    "end_tgt": [2.8, 1.8, 1.7],
                    "fov": 45.0
                },
                "story_purpose": "Demonstrates the collective social eruption: citizens across Odeonsplatz rush together toward the proclamation.",
                "why_cut_earned": "Shows physical delta in social field: from scattered pedestrians to unified agitated crowd."
            },
            {
                "shot_index": 4,
                "shot_id": "SHOT_04_PROTAGONIST_REACTION",
                "beat_id": "BEAT_D_PROTAGONIST_REACTION",
                "time_range": [15.5, 19.5],
                "duration_sec": 4.0,
                "shot_type": "MEDIUM_REACTION_LOW_ANGLE",
                "camera": {
                    "start_pos": [-2.0, 1.8, 3.4],
                    "end_pos": [-1.8, 1.75, 2.8],
                    "start_tgt": [-1.2, 1.6, 0.4],
                    "end_tgt": [-1.2, 1.6, 0.4],
                    "fov": 38.0
                },
                "story_purpose": "Captures protagonist's psychological turning point: body turn, eyeline snapping to crowd, clutching portfolio to chest.",
                "why_cut_earned": "Reveals inner character change and emotional awakening that cannot be seen from crowd wide shot."
            },
            {
                "shot_index": 5,
                "shot_id": "SHOT_05_DECISION_INSPECTION",
                "beat_id": "BEAT_E_DECISION_INSPECTION",
                "time_range": [19.5, 23.0],
                "duration_sec": 3.5,
                "shot_type": "OVER_THE_SHOULDER_INSPECTION",
                "camera": {
                    "start_pos": [-0.2, 1.9, 3.2],
                    "end_pos": [0.6, 1.85, 2.6],
                    "start_tgt": [2.8, 1.7, 1.8],
                    "end_tgt": [3.1, 1.6, 1.8],
                    "fov": 40.0
                },
                "story_purpose": "Direct interaction: Hitler approaches the crowd and reads the mobilization decree, catalyzing his personal decision.",
                "why_cut_earned": "Shows direct spatial proximity between protagonist and inciting information object."
            },
            {
                "shot_index": 6,
                "shot_id": "SHOT_06_MONUMENTAL_RESOLUTION",
                "beat_id": "BEAT_F_MONUMENTAL_RESOLUTION",
                "time_range": [23.0, 26.5],
                "duration_sec": 3.5,
                "shot_type": "HEROIC_PERSPECTIVE_MONUMENTAL_RESOLUTION",
                "camera": {
                    "start_pos": [0.4, 1.65, 4.8],
                    "end_pos": [1.0, 1.75, 4.2],
                    "start_tgt": [-0.2, 3.4, -4.5],
                    "end_tgt": [-0.2, 3.4, -4.5],
                    "fov": 48.0
                },
                "story_purpose": "Resolution: Hitler stands resolute before the monumental Feldherrnhalle arches as crowd waves hats; transitions toward enlistment.",
                "why_cut_earned": "Consequence state change: protagonist transformed from directionless drifter to determined volunteer."
            }
        ],
        voice_timeline={
            "audio_file": "output/motioncanvas_proof_v41/episode01_v41_voice_proof.wav",
            "speaker_id": "char_hitler",
            "voice_id": "Đức Trí",
            "speed_ratio": 1.0,
            "total_duration_sec": 26.50,
            "lines": [
                {
                    "line_id": "EP01_FP_01",
                    "text": "Năm 1914, tôi hai mươi lăm tuổi. Sự nghiệp... chưa có gì đáng kể. Tiền... cũng chẳng có bao nhiêu. Tương lai... khá mù mịt.",
                    "start_sec": 0.0,
                    "end_sec": 11.12,
                    "shots": [1, 2]
                },
                {
                    "line_id": "EP01_FP_INTER_PAUSE",
                    "text": "[inter-phrase pause]",
                    "start_sec": 11.12,
                    "end_sec": 11.62,
                    "shots": [3]
                },
                {
                    "line_id": "EP01_FP_02",
                    "text": "Và đúng lúc tôi đang không biết đời mình sẽ đi đâu... cả châu Âu quyết định lao vào một cuộc chiến tranh khổng lồ. Một cách giải quyết vấn đề rất... châu Âu năm 1914.",
                    "start_sec": 11.62,
                    "end_sec": 25.91,
                    "shots": [3, 4, 5, 6]
                }
            ]
        },
        sfx_timeline=[
            {"sfx_id": "SFX_01", "time_sec": 0.8,  "category": "PHYSICAL", "event": "FOOTSTEP_COBBLESTONE", "volume": 0.35, "description": "Solitary wet leather shoe contacts granite."},
            {"sfx_id": "SFX_02", "time_sec": 6.2,  "category": "OBJECT",   "event": "PAPER_POST_AND_RUSTLE", "volume": 0.50, "description": "Mobilization placard slapped onto Litfaßsäule pillar."},
            {"sfx_id": "SFX_03", "time_sec": 11.8, "category": "CROWD",    "event": "CROWD_MURMUR_SWELL", "volume": 0.45, "description": "Excited German murmur and shuffling footsteps converge."},
            {"sfx_id": "SFX_04", "time_sec": 16.2, "category": "PHYSICAL", "event": "FABRIC_RUSTLE_AND_BREATH", "volume": 0.40, "description": "Hitler clutches portfolio to chest; sharp intake of breath."},
            {"sfx_id": "SFX_05", "time_sec": 20.1, "category": "OBJECT",   "event": "PAPER_LEAFLET_FLUTTER", "volume": 0.35, "description": "Citizen rustles newspaper extra in debate."},
            {"sfx_id": "SFX_06", "time_sec": 24.0, "category": "AMBIENT",  "event": "DISTANT_CHEER_BELL", "volume": 0.40, "description": "Distant patriotic cheer and church bell tolling across Munich."}
        ],
        historical_grounding=[
            {
                "entity": "Feldherrnhalle Florentine Triple Arch",
                "grounding_class": "DOCUMENTED",
                "citation": "Bavarian State Archives, Munich City Planning 1841-1844; modeled on Loggia dei Lanzi in Florence."
            },
            {
                "entity": "Litfaßsäule Notice Pillar on Odeonsplatz",
                "grounding_class": "DOCUMENTED",
                "citation": "Photographic archive Heinrich Hoffmann 1914; Munich police regulations on public war proclamations."
            },
            {
                "entity": "Mobilization Decree 'Kriegszustand' August 1914",
                "grounding_class": "DOCUMENTED",
                "citation": "Bayerisches Gesetz- und Verordnungsblatt, August 1, 1914."
            },
            {
                "entity": "Hitler Bohemian Civilian Clothing & Cardboard Portfolio",
                "grounding_class": "CONTEXT_SUPPORTED",
                "citation": "Ian Kershaw 'Hubris' Ch. 3; Josef Greiner memoirs; Austrian Meldeamt records 1914."
            },
            {
                "entity": "Hitler 1914 Kaiser Handlebar Mustache (curving outward)",
                "grounding_class": "DOCUMENTED",
                "citation": "Hoffmann August 1914 Odeonsplatz mobilization crowd photograph; Bavarian RIR 16 regimental portrait 1914."
            },
            {
                "entity": "Crowd Patriotic Enthusiasm in Munich August 1914",
                "grounding_class": "DOCUMENTED",
                "citation": "Thomas Mann diary August 1914; Christopher Clark 'The Sleepwalkers'."
            },
            {
                "entity": "Hitler Exact Micro-Staging / Path across Plaza",
                "grounding_class": "PLAUSIBLE_RECONSTRUCTION",
                "citation": "Reconstructed dramatic staging based on his known presence in the August 1914 Odeonsplatz rally."
            }
        ]
    )
    return pkg


def main():
    pkg = build_v41_package()
    p_projects = Path("projects/episode01/production_scene_package_v41.json")
    pkg.export_json(p_projects)
    print(f"Exported canonical V4.1 package to: {p_projects}")

    p_mc = Path("motioncanvas/projects/episode01_package_v41.json")
    pkg.export_json(p_mc)
    print(f"Synced V4.1 package to Motion Canvas: {p_mc}")


if __name__ == "__main__":
    main()
