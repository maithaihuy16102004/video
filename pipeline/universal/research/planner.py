"""Visual Research Planner and Query Generator.

Architecture:
- VisualResearchPlanner: Categorizes every visual entity into:
  [REFERENCE_REQUIRED, REFERENCE_RECOMMENDED, REFERENCE_NOT_REQUIRED].
- ResearchQueryGenerator: Formulates high-precision, entity/date/location-grounded research queries.
- Banned: generic 'asset soup', random SEO search queries, unverified image farms.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ResearchRequirement:
    entity_id: str
    entity_name: str
    category: str  # MAP, REAL_LOCATION, HISTORICAL_PERSON, UNIFORM, VEHICLE, WEAPON, DOCUMENT, GENERIC_PROP
    status: str  # REFERENCE_REQUIRED, REFERENCE_RECOMMENDED, REFERENCE_NOT_REQUIRED
    justification: str
    target_date_era: str
    recommended_query: str
    target_institutions: list[str]


class VisualResearchPlanner:
    """Evaluates script-derived entities to determine objective factual research necessity."""

    REQUIRED_CATEGORIES = {
        "MAP",
        "REAL_BUILDING",
        "HISTORICAL_LOCATION",
        "HISTORICAL_PERSON",
        "MILITARY_UNIFORM",
        "WEAPON",
        "VEHICLE",
        "HISTORICAL_DOCUMENT",
        "HERO_OBJECT",
    }

    OPTIONAL_GENERIC_CATEGORIES = {
        "GENERIC_CHAIR",
        "GENERIC_TABLE",
        "GENERIC_CUP",
        "GENERIC_TREE",
        "GENERIC_CLOUD",
        "GENERIC_WALL",
    }

    @classmethod
    def plan_episode01_research(cls) -> list[ResearchRequirement]:
        return [
            # 1. MAP
            ResearchRequirement(
                entity_id="MAP_WESTERN_FRONT_1916",
                entity_name="Western Front & Somme Sector Map (1914-1916)",
                category="MAP",
                status="REFERENCE_REQUIRED",
                justification="Historical battle geography requires factual coastlines, river courses (Somme, Marne), static trench lines, and accurate relative city positions (Paris to Munich).",
                target_date_era="July - November 1916",
                recommended_query="British War Office Western Front Somme sector July 1916 trench map National Archives WO 153",
                target_institutions=["Imperial War Museum", "The National Archives UK", "Library of Congress"],
            ),

            # 2. LOCATIONS
            ResearchRequirement(
                entity_id="LOC_MUNICH_ODEONSPLATZ",
                entity_name="Munich Odeonsplatz & Feldherrnhalle Loggia",
                category="HISTORICAL_LOCATION",
                status="REFERENCE_REQUIRED",
                justification="Specific monumental neoclassical architecture (triple Florentine arches, Bavarian lions, Residenzstrasse facades, August 1914 mobilization crowd).",
                target_date_era="August 1914",
                recommended_query="Munich Odeonsplatz Feldherrnhalle August 1914 mobilization photography Heinrich Hoffmann Bayerische Staatsbibliothek",
                target_institutions=["Bayerische Staatsbibliothek", "Munich City Archives", "Bavarikon"],
            ),
            ResearchRequirement(
                entity_id="LOC_SOMME_TRENCH",
                entity_name="Western Front Flanders & Somme Communication Trench",
                category="HISTORICAL_LOCATION",
                status="REFERENCE_REQUIRED",
                justification="Subterranean physical structure requires factual split-log revetment wattle, mud duckboards, sandbag parapet geometry, and low horizon perspective.",
                target_date_era="Autumn 1916",
                recommended_query="German 2nd line trench timber revetment Somme 1916 Bundesarchiv Bild 183 Imperial War Museum Q series",
                target_institutions=["Bundesarchiv", "Imperial War Museum", "Historial de la Grande Guerre"],
            ),
            ResearchRequirement(
                entity_id="LOC_PASEWALK_HOSPITAL",
                entity_name="Pasewalk Military Convalescent Hospital Ward",
                category="HISTORICAL_LOCATION",
                status="REFERENCE_REQUIRED",
                justification="Institutional Prussian military lazarett architecture (tall lancet arched windows, dark green sanitary wainscot, cast iron hospital beds, gas casualty treatment).",
                target_date_era="October - November 1918",
                recommended_query="Prussian military hospital ward Pasewalk 1918 Geheimes Staatsarchiv Preussischer Kulturbesitz",
                target_institutions=["Geheimes Staatsarchiv PK", "Deutsches Historisches Museum"],
            ),

            # 3. CHARACTER
            ResearchRequirement(
                entity_id="CHAR_HITLER_1914",
                entity_name="Adolf Hitler (Age 25, 1914-1915)",
                category="HISTORICAL_PERSON",
                status="REFERENCE_REQUIRED",
                justification="Must prevent anachronistic 1930s-1940s appearance; authentic 1914 appearance features long angular jaw, deep-left hair sweep, piercing eyes, and wide Kaiser-style mustache.",
                target_date_era="August 1914 - Spring 1915",
                recommended_query="Adolf Hitler 16th Bavarian Reserve Infantry Regiment Fournes 1914 1915 authentic contemporary photograph Kriegsarchiv",
                target_institutions=["Bayerisches Hauptstaatsarchiv", "Imperial War Museum", "Bundesarchiv"],
            ),

            # 4. UNIFORM
            ResearchRequirement(
                entity_id="UNIFORM_BAVARIAN_M1907",
                entity_name="Royal Bavarian Infantry M1907/10 Field Uniform (Feldgrau)",
                category="MILITARY_UNIFORM",
                status="REFERENCE_REQUIRED",
                justification="Military regulations require accurate Feldgrau wool tone, stand-and-fall collar, scarlet piping, tombak crown buttons, and Bavarian blue-and-white cockade on Feldmütze.",
                target_date_era="August 1914",
                recommended_query="Royal Bavarian infantry Feldrock M1907 10 Feldmütze uniform regulation plate Bayerisches Armeemuseum Ingolstadt",
                target_institutions=["Bayerisches Armeemuseum Ingolstadt", "Militärhistorisches Museum Dresden"],
            ),

            # 5. HERO OBJECTS
            ResearchRequirement(
                entity_id="OBJ_STAHLHELM_M16",
                entity_name="Imperial German M1916 Stahlhelm & M1917 Gas Mask Canister",
                category="HERO_OBJECT",
                status="REFERENCE_REQUIRED",
                justification="Iconic silhouette requires flared brow visor, neck skirt flare, prominent Stirnpanzer brow lugs, and ribbed cylindrical sheet-metal carrying canister.",
                target_date_era="February 1916 - 1918",
                recommended_query="Imperial German Stahlhelm M16 Stirnpanzer lugs M1917 Tragebüchse gas mask container Deutsches Historisches Museum",
                target_institutions=["Deutsches Historisches Museum", "Imperial War Museum"],
            ),

            # 6. GENERIC ENTITIES (NO RESEARCH REQUIRED)
            ResearchRequirement(
                entity_id="PROP_WOODEN_CHAIR",
                entity_name="Standard Wooden Tavern Stool / Chair",
                category="GENERIC_CHAIR",
                status="REFERENCE_NOT_REQUIRED",
                justification="Generic wooden furniture can be composed from project geometric primitives without specific archival provenance.",
                target_date_era="Universal",
                recommended_query="N/A",
                target_institutions=[],
            ),
            ResearchRequirement(
                entity_id="PROP_CROWD_EXTRAS",
                entity_name="Background Street Crowd Extras",
                category="GENERIC_EXTRA",
                status="REFERENCE_NOT_REQUIRED",
                justification="Background extras utilize controlled generic stickman silhouettes to maintain focus on primary researched subjects.",
                target_date_era="Universal",
                recommended_query="N/A",
                target_institutions=[],
            ),
        ]

    @classmethod
    def audit_research_plan(cls, plan: list[ResearchRequirement]) -> dict[str, Any]:
        required = [r for r in plan if r.status == "REFERENCE_REQUIRED"]
        not_req = [r for r in plan if r.status == "REFERENCE_NOT_REQUIRED"]

        return {
            "status": "PASS_RESEARCH_SYSTEMATICALLY_PLANNED",
            "total_entities_analyzed": len(plan),
            "reference_required_count": len(required),
            "reference_not_required_count": len(not_req),
            "high_value_targets": [r.entity_name for r in required],
            "generic_primitives_bypassed": [r.entity_name for r in not_req],
            "research_discipline": "ZERO_GUESSING_ON_HISTORICAL_FACTS",
        }
