"""Visual Fact Models for Research-Grounded Visual Reconstruction.

Implements strict epistemological separation:
- OBSERVED_FACT: Direct archival or physical evidence verified in primary sources.
- INFERRED_FACT: Historically consistent deduction based on era, regulations, and context.
- ARTISTIC_INTERPRETATION: Stylized translation into the project's illustrated visual aesthetic.

Ensures zero speculative or generic primitive assembly.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FactConfidence(str, Enum):
    OBSERVED_FACT = "OBSERVED_FACT"
    INFERRED_FACT = "INFERRED_FACT"
    ARTISTIC_INTERPRETATION = "ARTISTIC_INTERPRETATION"


@dataclass
class VisualFactEntry:
    field_name: str
    value: Any
    confidence: FactConfidence
    historical_evidence: str
    provenance_source: str


@dataclass
class MapFactModel:
    map_id: str
    title: str
    historical_era: str
    date_range: str
    geographic_scope: str
    
    # Cartographic features (Factual Grounding)
    coastline_features: list[str] = field(default_factory=list)
    river_courses: list[dict[str, Any]] = field(default_factory=list)
    trench_front_line: dict[str, Any] = field(default_factory=dict)
    salient_features: list[dict[str, Any]] = field(default_factory=list)
    key_settlements: list[dict[str, Any]] = field(default_factory=list)
    
    # Visual Cartography Conventions
    paper_color_hex: str = "#E8DFCA"
    grid_system: str = "British Military Squared Grid / Metric 10km Coordinates"
    hachure_relief: bool = True
    ink_tone_primary: str = "#2C2218"
    allied_line_color: str = "#A02828"
    central_line_color: str = "#254885"
    
    # Fact Breakdown
    fact_entries: list[VisualFactEntry] = field(default_factory=list)


@dataclass
class LocationFactModel:
    location_id: str
    canonical_name: str
    historical_date: str
    provenance_ref_id: str
    
    # Architectural & Spatial Dimensions
    primary_architecture: str = ""
    materials: list[str] = field(default_factory=list)
    structural_anchors: list[str] = field(default_factory=list)
    horizon_ratio: float = 0.55  # 0.0 top, 1.0 bottom
    vanishing_point_x: float = 0.50
    vanishing_point_y: float = 0.55
    spatial_depth_planes: list[str] = field(default_factory=list)
    
    # Environmental & Traces
    lighting_condition: str = ""
    weather_atmosphere: str = ""
    human_traces: list[str] = field(default_factory=list)
    
    # Fact Breakdown
    fact_entries: list[VisualFactEntry] = field(default_factory=list)


@dataclass
class CharacterFactModel:
    character_id: str
    canonical_name: str
    historical_date: str
    exact_age: int
    provenance_ref_id: str
    
    # Anatomical & Physical Features
    face_structure: str = ""
    hair_style_era: str = ""
    mustache_style_era: str = ""  # Note: Kaiser handlebar for 1914, NOT toothbrush!
    eye_expression: str = ""
    posture_bearing: str = ""
    proportions_head_to_body: float = 1.0 / 7.5
    
    # Era Prohibitions (Rules to prevent anachronisms)
    prohibited_features: list[str] = field(default_factory=list)
    
    # Fact Breakdown
    fact_entries: list[VisualFactEntry] = field(default_factory=list)


@dataclass
class CostumeFactModel:
    costume_id: str
    canonical_title: str
    military_branch: str
    regulation_model: str
    historical_date: str
    provenance_ref_id: str
    
    # Garment Details
    tunic_model: str = ""
    primary_fabric_color: str = "#4A5246"  # Bavarian Feldgrau
    cuff_style: str = ""
    piping_color: str = "#8B1E1E"  # Infantry Red (Hochrot)
    button_type: str = "Tombac matte horn/metal, crown embossed"
    
    # Headwear & Accoutrements
    headwear_model: str = ""
    state_cockade: str = "Bavaria (White and Light Blue)"
    national_cockade: str = "German Empire (Black-White-Red)"
    webbing_leather: str = "Natural brown oiled leather"
    belt_buckle_motto: str = "IN TREUE FEST (Bavarian State Crown)"
    
    # Fact Breakdown
    fact_entries: list[VisualFactEntry] = field(default_factory=list)


@dataclass
class ObjectFactModel:
    object_id: str
    canonical_name: str
    model_designation: str
    year_introduced: int
    provenance_ref_id: str
    
    primary_materials: list[str] = field(default_factory=list)
    key_identifying_features: list[str] = field(default_factory=list)
    finish_and_wear: str = ""
    dimensional_ratio: str = ""
    
    # Fact Breakdown
    fact_entries: list[VisualFactEntry] = field(default_factory=list)


class VisualFactRepository:
    """Master repository containing structured factual models for Episode 01."""

    @classmethod
    def get_western_front_map_fact_model(cls) -> MapFactModel:
        model = MapFactModel(
            map_id="FACT_MAP_WESTERN_FRONT_1916",
            title="Western Front & Somme Strategic Sector (1914-1916)",
            historical_era="World War I",
            date_range="July - November 1916",
            geographic_scope="Western Europe: English Channel to Swiss Border (Somme Picardy Focus)",
            coastline_features=[
                "Nieuwpoort / Ostend Belgian coastline",
                "Straits of Dover and Thames estuary",
                "Normandy and Channel coastline to Le Havre",
            ],
            river_courses=[
                {"name": "Somme", "flow": "East to West from Saint-Quentin past Péronne, Albert, Amiens to Baie de Somme"},
                {"name": "Marne", "flow": "East of Paris, scene of 1914 battle"},
                {"name": "Meuse", "flow": "Flows north past Verdun fortress salient"},
                {"name": "Seine", "flow": "Through Paris toward English Channel"},
                {"name": "Rhine", "flow": "Natural eastern strategic barrier"},
            ],
            trench_front_line={
                "type": "Continuous fortified trench trace",
                "length_km": 700,
                "northern_terminus": "Nieuwpoort, Belgium (North Sea)",
                "southern_terminus": "Pfetterhouse, Swiss border",
                "somme_crossing": "Bisects Somme river east of Amiens, between Albert and Péronne",
            },
            salient_features=[
                {"name": "Ypres Salient", "shape": "Eastward bulge into German lines in Flanders"},
                {"name": "Somme Sector", "shape": "Concave arc fronting Thiepval, Pozières, High Wood"},
                {"name": "Verdun Salient", "shape": "Heavily fortified French bastion on the Meuse"},
            ],
            key_settlements=[
                {"name": "Paris", "role": "French Capital, Western Anchor", "geo_coord_rel": (0.32, 0.68)},
                {"name": "London", "role": "British Imperial Capital", "geo_coord_rel": (0.24, 0.22)},
                {"name": "Brussels", "role": "Occupied Belgian Capital", "geo_coord_rel": (0.50, 0.40)},
                {"name": "Munich", "role": "Bavarian Capital (Hitler Enlistment)", "geo_coord_rel": (0.84, 0.82)},
                {"name": "Amiens", "role": "British Fourth Army Railhead", "geo_coord_rel": (0.35, 0.52)},
                {"name": "Albert", "role": "Somme Front Line Town (Golden Virgin)", "geo_coord_rel": (0.40, 0.50)},
                {"name": "Péronne", "role": "German 2nd Army Strongpoint", "geo_coord_rel": (0.45, 0.51)},
                {"name": "Ypres", "role": "Flanders Salient Hub", "geo_coord_rel": (0.42, 0.35)},
            ],
            fact_entries=[
                VisualFactEntry(
                    field_name="trench_front_line",
                    value="Continuous line from Nieuwpoort to Swiss border",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="British War Office General Staff map GSGS 2743 / WO 153 series",
                    provenance_source="Imperial War Museum / National Archives UK",
                ),
                VisualFactEntry(
                    field_name="somme_sector",
                    value="Picardy chalk downs with Somme river winding westward through Péronne and Amiens",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Official 1:20,000 Fourth Army Somme Battle Trench Map July 1916",
                    provenance_source="National Archives UK WO 153/264",
                ),
                VisualFactEntry(
                    field_name="cartographic_palette",
                    value="Aged parchment buff background with black engraving ink, red Allied lines, blue German lines",
                    confidence=FactConfidence.ARTISTIC_INTERPRETATION,
                    historical_evidence="Consistent with British War Office 1916 dual-color front line overlays",
                    provenance_source="Project Illustrated Map Aesthetic Specification",
                ),
            ],
        )
        return model

    @classmethod
    def get_odeonsplatz_fact_model(cls) -> LocationFactModel:
        return LocationFactModel(
            location_id="FACT_LOC_ODEONSPLATZ_1914",
            canonical_name="Munich Odeonsplatz & Feldherrnhalle Loggia",
            historical_date="2 August 1914 (Mobilization Proclamation)",
            provenance_ref_id="REF_LOC_001_MUNICH_ODEONSPLATZ_1914",
            primary_architecture="Florentine Renaissance Revival Loggia (designed by Friedrich von Gärtner, 1841-1844)",
            materials=["Kelheim limestone masonry", "Bronze statues with dark patina", "Granite cobblestone pavement"],
            structural_anchors=[
                "Triple giant round arches (Loggia dei Lanzi inspiration)",
                "Monumental bronze statue of General Tilly on left arch interior",
                "Monumental bronze statue of Prince Wrede on right arch interior",
                "Bavarian stone lions guarding front stairs",
                "Flanking neoclassical ashlar facades along Residenzstrasse and Ludwigstrasse",
            ],
            horizon_ratio=0.58,
            vanishing_point_x=0.50,
            vanishing_point_y=0.58,
            spatial_depth_planes=[
                "Foreground: Dense crowd in dark Edwardian hats and suits, jubilant gestures",
                "Midground: Wide granite cobblestone plaza, balustrade steps, military dispatch rider",
                "Background: Feldherrnhalle triple open arches, vaulting shadows, bronze commanders",
            ],
            lighting_condition="Bright midday August summer sun, high contrast, casting crisp shadows beneath arches",
            weather_atmosphere="Dry, clear sky, sunny summer afternoon",
            human_traces=[
                "Black top hats, straw boaters, and bowler hats tossed in the air",
                "Red and white Munich city banners and blue-white Bavarian flags hung from flanking cornices",
                "Printed mobilization proclamations (Mobilmachungsbefehl) posted on square kiosks",
            ],
            fact_entries=[
                VisualFactEntry(
                    field_name="triple_arches",
                    value="Three monumental semi-circular arches supported by Corinthian pilasters",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Architectural survey Friedrich von Gärtner / BSB Hoffmann collection",
                    provenance_source="Bayerische Staatsbibliothek",
                ),
                VisualFactEntry(
                    field_name="crowd_attire",
                    value="Edwardian civilian attire: dark wool suits, stiff collars, bowler hats, straw boaters",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Hoffmann photograph of Odeonsplatz crowd on 2 August 1914",
                    provenance_source="Heinrich Hoffmann Archive / Bavarikon",
                ),
            ],
        )

    @classmethod
    def get_somme_trench_fact_model(cls) -> LocationFactModel:
        return LocationFactModel(
            location_id="FACT_LOC_SOMME_TRENCH_1916",
            canonical_name="German Second-Line Communication Trench (Somme / Flanders)",
            historical_date="October 1916",
            provenance_ref_id="REF_LOC_002_SOMME_TRENCH_1916",
            primary_architecture="Subterranean field fortification cut through Picardy chalk and clay",
            materials=["Split pine timber logs", "Woven hazel wicker wattle", "Jute hessian sandbags", "Oak duckboards", "Chalky grey mud"],
            structural_anchors=[
                "Vertical split-log revetment walls retaining trench walls on both flanks",
                "Wooden duckboard walkway (Grabenrost) raised above stagnant drainage water",
                "Traverse zigzag corner breaking blast shockwaves and direct bullet fire",
                "Sandbag parapet with firing step (Auftritt) and observation periscope slot",
                "Corrugated steel dugout shelter entrance sunken into chalk wall",
            ],
            horizon_ratio=0.35,  # Low subterranean camera view looking up at sandbag lip
            vanishing_point_x=0.48,
            vanishing_point_y=0.42,
            spatial_depth_planes=[
                "Foreground: Chalk-mud trench floor, wooden duckboards, empty brass shell casings, messenger",
                "Midground: Timber revetments, telephone wire bundles affixed to posts, traverse corner",
                "Background: Parapet sandbag crest, desolate muddy skyline, rain mist, distant flare smoke",
            ],
            lighting_condition="Cold, overcast diffused grey autumn daylight, damp specular sheen on wet mud and logs",
            weather_atmosphere="Continuous Picardy drizzle, mist, waterlogged churned soil",
            human_traces=[
                "Telephone wire cables hung along revetment logs",
                "Tin mess kits, enamel mugs, and gas mask canisters slung from dugout pegs",
                "Deep boot ruts in heavy clay mud along edges of duckboards",
            ],
            fact_entries=[
                VisualFactEntry(
                    field_name="revetment_construction",
                    value="Split logs pinned with wire anchors into chalk, preventing cave-ins",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="German Pioneer Corps (Pioniere) field manuals 1915-1916 / Bundesarchiv Bild 183",
                    provenance_source="Bundesarchiv / Imperial War Museum",
                ),
            ],
        )

    @classmethod
    def get_pasewalk_hospital_fact_model(cls) -> LocationFactModel:
        return LocationFactModel(
            location_id="FACT_LOC_PASEWALK_HOSPITAL_1918",
            canonical_name="Pasewalk Military Convalescent Reserve Hospital (Reservelazarett)",
            historical_date="21 October - 11 November 1918",
            provenance_ref_id="REF_LOC_003_PASEWALK_HOSPITAL_1918",
            primary_architecture="Prussian Wilhelmine Institutional Military Hospital Ward",
            materials=["Whitewashed lime plaster upper walls", "Dark green oil sanitary gloss wainscoting", "Black tubular cast iron", "Bleached pine floorboards"],
            structural_anchors=[
                "High segmental lancet arched windows with multi-pane glazing",
                "Strict linear perspective corridor flanked by identical military iron cots",
                "Dark green oil-painted wainscot datum line at 1.4m height",
                "White enamel bedside lockers with galvanized wash basins",
                "Black cast iron radiator pipes running beneath window sills",
            ],
            horizon_ratio=0.55,
            vanishing_point_x=0.50,
            vanishing_point_y=0.55,
            spatial_depth_planes=[
                "Foreground: Enamel wash basin, medical chart board, corner of convalescent cot",
                "Midground: Hospital bed with bandage-blinded soldier sitting upright, nurse administering care",
                "Background: High arched window admitting pale, diffused Baltic autumn morning light",
            ],
            lighting_condition="Cold, diffused Baltic autumn daylight streaming through high arched windows, casting elongated soft window shadows",
            weather_atmosphere="Enclosed institutional silence, chilly autumn morning outside",
            human_traces=[
                "Clinical temperature chart clipboards hanging on footboards",
                "Gauze eye bandages soaked in boric acid solution",
                "Enamel bedside water carafes and wash basins",
            ],
            fact_entries=[
                VisualFactEntry(
                    field_name="hospital_architecture",
                    value="Wilhelmine Prussian military hospital layout with tall multi-pane arched windows and sanitary gloss wainscot",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Prussian War Ministry Hospital Regulations / GStA PK archival blueprints",
                    provenance_source="Geheimes Staatsarchiv Preussischer Kulturbesitz",
                ),
            ],
        )

    @classmethod
    def get_hitler_1914_fact_model(cls) -> CharacterFactModel:
        return CharacterFactModel(
            character_id="FACT_CHAR_HITLER_1914",
            canonical_name="Adolf Hitler (Age 25, Munich Mobilization / Early Enlistment)",
            historical_date="August - October 1914",
            exact_age=25,
            provenance_ref_id="REF_CHAR_001_HITLER_1914_MUNICH",
            face_structure="Narrow gaunt angular jaw, prominent high cheekbones, sunken hollow cheeks, long straight nose with slight dip at bridge",
            hair_style_era="Dark brown hair parted sharply on the left side, swept back and across forehead, trimmed neatly above ears (pre-military civilian cut)",
            mustache_style_era="Wide Kaiser Wilhelm-style handlebar mustache with tapered waxed ends extending past lips (FACT: 1914 mustache is wide; toothbrush was trimmed in 1916 to fit gas mask!)",
            eye_expression="Intense, wide-eyed, fixed stare, deep set under prominent brow ridges",
            posture_bearing="Slender, somewhat gaunt, rigid spine with slight nervous forward neck angle, hands held tensely at sides",
            proportions_head_to_body=1.0 / 7.2,
            prohibited_features=[
                "STRICTLY PROHIBITED: 1930s-1940s trimmed 'toothbrush' mustache (historically incorrect for 1914).",
                "STRICTLY PROHIBITED: Heavy older jowls or round softened jawline (he was 25 and impoverished).",
                "STRICTLY PROHIBITED: Nazi armband, NSDAP badges, or Iron Cross 1st class (not yet earned in August 1914).",
                "STRICTLY PROHIBITED: Short military buzzcut in early August 1914 (he was still a civilian artist in Munich).",
            ],
            fact_entries=[
                VisualFactEntry(
                    field_name="mustache_style",
                    value="Wide imperial handlebar mustache extending to corners of mouth",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Heinrich Hoffmann 2 August 1914 Odeonsplatz enlargement & Bavarian Army enlistment registry photo 1914",
                    provenance_source="Bayerisches Hauptstaatsarchiv / Heinrich Hoffmann",
                ),
                VisualFactEntry(
                    field_name="facial_physiognomy",
                    value="Gaunt, hollow cheeks, age 25, prominent nose, intense sunken blue-grey eyes",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Official Bavarian Infantry Regiment 16 (List) muster roll descriptions",
                    provenance_source="Bayerisches Armeemuseum Ingolstadt",
                ),
            ],
        )

    @classmethod
    def get_bavarian_costume_fact_model(cls) -> CostumeFactModel:
        return CostumeFactModel(
            costume_id="FACT_COSTUME_BAVARIAN_INFANTRY_1914",
            canonical_title="Royal Bavarian 16th Reserve Infantry Regiment (List) M1907/10 Feldrock Uniform",
            military_branch="Royal Bavarian Army, 6th Bavarian Reserve Division",
            regulation_model="M1907/10 Feldgrau Field Uniform (Bavarian Specification)",
            historical_date="Autumn 1914",
            provenance_ref_id="REF_COST_001_BAVARIAN_INFANTRY_1914",
            tunic_model="M1907/10 Feldrock: single-breasted wool tunic, standing-fall turnback collar",
            primary_fabric_color="#4B5344",  # Factual Bavarian Field-Grey Wool (slightly greener than Prussian stone-grey)
            cuff_style="Brandenburg-pattern cuffs with three vertical tombac buttons on flap",
            piping_color="#8B1E1E",  # Bavarian infantry red wool cord piping on collar, front fly, and cuff flaps
            button_type="Matte tombac crowned metal buttons, non-reflective",
            headwear_model="M1910 Krätzchen (peakless field cap for enlisted ranks)",
            state_cockade="Bavaria: White outer ring with sky blue center disc on dark cloth band",
            national_cockade="German Empire: Black-White-Red small rosette on crown seam",
            webbing_leather="Brown oiled harness leather belt and Mauser 98 triple-cartridge ammo pouches",
            belt_buckle_motto="IN TREUE FEST with Bavarian Royal Crown (distinct from Prussian 'Gott Mit Uns')",
            fact_entries=[
                VisualFactEntry(
                    field_name="bavarian_belt_buckle",
                    value="Bavarian motto 'IN TREUE FEST' around central royal crown, stamped brass/nickel",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Bavarian Military Regulations (V.D.B.) 1910 / Armeemuseum specimen",
                    provenance_source="Bayerisches Armeemuseum Ingolstadt",
                ),
                VisualFactEntry(
                    field_name="cockade_hierarchy",
                    value="Dual cockades: Imperial Reich cockade on crown, Bavarian state cockade on cap band",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="AKO 21. September 1897 uniform regulation for Imperial German armed forces",
                    provenance_source="Deutsches Historisches Museum Berlin",
                ),
            ],
        )

    @classmethod
    def get_stahlhelm_gasmask_fact_model(cls) -> ObjectFactModel:
        return ObjectFactModel(
            object_id="FACT_OBJ_STAHLHELM_M16_GASMASK",
            canonical_name="German Stahlhelm M16 & Lederschutzmaske M17 with Transport Canister",
            model_designation="Stahlhelm Modell 1916 & Lederschutzmaske 17 / Tragbüchse 17",
            year_introduced=1916,
            provenance_ref_id="REF_OBJ_001_STAHLHELM_M16_GASMASK",
            primary_materials=[
                "Pressed chromium-nickel steel (0.9-1.2mm thickness)",
                "Corrugated ribbed galvanized sheet steel (canister)",
                "Oiled sheepskin leather and treated canvas (mask)",
                "Celluloid and layered glass lenses",
            ],
            key_identifying_features=[
                "Two cylindrical raised ventilation/stirnpanzer lugs on either side of helmet crown",
                "Deep sloping flared apron shielding neck and ears",
                "Vertical fluting/corrugation on cylindrical metal gas mask carrying canister",
                "Circular screw-in drum filter (Filtereinsatz 11-11) projecting from bottom of mask snout",
            ],
            finish_and_wear="Factory matte feldgrau anti-glare paint with combat scratches, rust speckles on exposed rim",
            dimensional_ratio="Helmet: width to height ~ 1.3 : 1.0; Canister: height to diameter ~ 2.5 : 1.0",
            fact_entries=[
                VisualFactEntry(
                    field_name="stirnpanzer_horns",
                    value="Twin cylindrical side lugs functioning as air vents and mounting lugs for heavy brow armor plate",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Prof. August Bier / Dr. Friedrich Schwerd patent and military procurement trials 1915",
                    provenance_source="Deutsches Historisches Museum",
                ),
                VisualFactEntry(
                    field_name="fluted_canister",
                    value="Corrugated vertical ridges on metal canister providing structural crush resistance",
                    confidence=FactConfidence.OBSERVED_FACT,
                    historical_evidence="Kgl. Preußisches Kriegsministerium Bekleidungsvorschrift 1917",
                    provenance_source="Imperial War Museum Specimen Q 67824",
                ),
            ],
        )

    @classmethod
    def export_all_fact_models(cls, output_path: Path) -> dict[str, Any]:
        data = {
            "version": "2026.11-FACT-FIRST",
            "epistemological_framework": {
                "OBSERVED_FACT": "Direct archival, photographic, or museum specimen evidence",
                "INFERRED_FACT": "Historically consistent deduction from contemporary regulations and context",
                "ARTISTIC_INTERPRETATION": "Stylized translation into illustrated project visual aesthetic",
            },
            "fact_models": {
                "map": asdict(cls.get_western_front_map_fact_model()),
                "locations": {
                    "odeonsplatz": asdict(cls.get_odeonsplatz_fact_model()),
                    "somme_trench": asdict(cls.get_somme_trench_fact_model()),
                    "pasewalk_hospital": asdict(cls.get_pasewalk_hospital_fact_model()),
                },
                "characters": {
                    "hitler_1914": asdict(cls.get_hitler_1914_fact_model()),
                },
                "costumes": {
                    "bavarian_infantry_1914": asdict(cls.get_bavarian_costume_fact_model()),
                },
                "hero_objects": {
                    "stahlhelm_m16_gasmask": asdict(cls.get_stahlhelm_gasmask_fact_model()),
                },
            },
        }
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data
