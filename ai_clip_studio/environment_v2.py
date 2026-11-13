"""Environment Engine V2 — reusable semantic environment construction.

Visual Quality Recovery, P3. Replaces the generic box environments
(one keyword -> the same few boxes) with environments COMPOSED from
location trait data: facades with real roofs, windows and doors
ATTACHED to walls, street furniture, foreground occluders, midground
staging and background depth — selected from an archetype catalog by
the trait text, never by a script, project or location id.

Public API (ATLAS wiring contract):

    pkg = build_environment(location_traits, period, time_of_day, style)
    img = render_environment(pkg, camera, size=(1920, 1080))
    boxes = to_box_dicts(pkg)   # -> Box3D(**d) for product_renderer

``location_traits`` is a §15.3 location trait block (or a V1
``v1_locations`` entry): ``features`` / ``foreground`` /
``midground`` / ``background`` / ``palette`` / ``lighting`` /
``weather`` / ``type`` / ``architecture`` / ``geography``. The
engine reads ONLY those fields; ids and names are copied into
provenance, never used for selection.

Determinism: the layout seed derives from the canonical trait JSON,
so the same traits always build the same package.

Attachment validation: every window/door/roof/furniture element
carries an ``attachment`` record; ``validate_attachments(pkg)``
recomputes each attached element's world position from its parent
and reports any element floating off its wall, door not reaching
the ground, or roof not sitting on its wall. Shipped archetypes
validate clean (asserted by tests).

Period constraints: ``validate_period(elements, period)`` rejects
anachronisms from the documented ``ANACHRONISM_RULES`` list
(LED before 1962, neon before 1910, motor cars before 1885, glass
curtain walls before 1950, ...). Archetypes also declare a period
range; building outside it is reported in the package, never
silently corrected.

Map locations (trait ``type`` naming a map) are NOT environments:
``build_environment`` returns a ``map_deferred`` package and the
caller must use ``map_renderer``. No rectangular country cards are
ever produced here.

Stylisation limits (honest): this is the 2D-projection proof
renderer — boxes, gable prisms and blobs projected through a real
PerspectiveCamera with Lambert shading. It is not a 3D mesh
renderer; the Motion Canvas + Three.js path remains the real-3D
future. Canopies, smoke and domes are flat-shaded blobs by design.

Scene-local isolation (Semantic Engine Upgrade §6, B2): ``ScopedState``
implements the ``semantic_contracts`` scope mechanism (PROJECT / SCENE /
SHOT / EVENT / CHARACTER / PROP, SHOT -> SCENE -> PROJECT inheritance
via ``resolve_scoped_attribute``). Scene change resets SHOT scope;
project change resets everything below PROJECT; entity values are
keyed by scene + entity so nothing leaks sideways or across scenes
without an explicit ``carry_over``. ``build_environment_scoped``
builds from store-resolved weather/lighting with per-attribute
provenance, and ``render_environment(..., scoped_state=...)`` draws
the deterministic rain overlay ONLY when the scoped state resolves
rain for the current scene — there is no job-level rain flag on this
side of the boundary (the product_flow ``any()`` rainy flag is
ATLAS-owned and must be rewired to per-scene resolution).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .lighting import (
    energy_glow_to_point_light,
    light_for,
    point_light_gain,
    point_light_spec_to_light,
    rig_for,
    shade_with_points,
    shadow_ellipse_spec,
)
from .paint_textures import (
    MIN_FACE_PX,
    facade_window_layout,
    ground_texture_for,
    paste_textured_quad,
    texture_for_material,
)
from .renderer25d.camera import PerspectiveCamera
from .renderer25d.scene import BOX_FACES
from .semantic_contracts import (
    SCOPE_INHERITANCE,
    StateScope,
    resolve_scoped_attribute,
)

# ---------------------------------------------------------------------------
# Colour-name table (trait palettes name colours in words)
# ---------------------------------------------------------------------------
COLOR_NAMES = {
    "cream": (235, 222, 190), "white": (242, 240, 234),
    "gray": (128, 128, 128), "grey": (128, 128, 128),
    "muted brown": (122, 96, 70), "brown": (110, 80, 52),
    "mud brown": (96, 74, 52), "mud": (96, 74, 52),
    "sand": (210, 188, 150), "stone": (168, 160, 146),
    "marble": (238, 234, 224), "terracotta": (178, 98, 66),
    "olive": (112, 116, 62), "green": (84, 110, 66),
    "blue": (70, 110, 160), "sea blue": (58, 110, 150),
    "sky blue": (135, 180, 220), "red": (150, 50, 44),
    "brick": (142, 74, 58), "brick red": (142, 74, 58),
    "black": (30, 30, 32), "dark": (48, 48, 52),
    "gold": (212, 172, 84), "yellow": (230, 200, 90),
    "beige": (214, 196, 160), "tan": (188, 158, 118),
    "charcoal": (52, 54, 58), "slate": (96, 108, 122),
    "pale": (226, 222, 210), "ivory": (240, 236, 220),
    "magenta": (178, 60, 120), "pink": (220, 150, 170),
    "khaki": (164, 150, 108), "ochre": (196, 148, 66),
}


def _parse_color_name(text):
    """A trait palette word -> RGB, or None when unknown."""
    if not isinstance(text, str):
        return None
    return COLOR_NAMES.get(text.strip().lower().rstrip("."))


def _blend(c1, c2, t: float):
    return tuple(int(round(c1[i] * (1 - t) + c2[i] * t)) for i in range(3))


# ---------------------------------------------------------------------------
# Period handling
# ---------------------------------------------------------------------------
ERA_YEARS = {
    "ancient greece": -400, "ancient greek": -400,
    "ancient rome": -100, "ancient roman": -100,
    "ancient egypt": -1200, "ancient": -1000,
    "medieval": 1200, "middle ages": 1200,
    "renaissance": 1500, "victorian": 1880,
    "prehistoric": -10000,
}

# (element kind or material token, not-before year, note). An element
# carrying the token in a scene set before the year is an
# anachronism. The list is intentionally conservative: only
# technologies with a clear introduction date. Mythological periods
# ("mythological", "timeless") disable the check entirely.
ANACHRONISM_RULES = (
    ("led", 1962, "LED lighting did not exist before 1962"),
    ("neon_sign", 1910, "neon signage did not exist before 1910"),
    ("automobile", 1885, "motor cars did not exist before 1885"),
    ("airplane", 1903, "airplanes did not exist before 1903"),
    ("glass_curtain", 1950, "glass curtain walls before 1950"),
    ("smartphone", 2007, "smartphones did not exist before 2007"),
    ("satellite_dish", 1962, "satellite dishes before 1962"),
    ("plastic_furniture", 1950, "plastic furniture before 1950"),
    ("billboard_led", 1990, "LED billboards before 1990"),
    ("traffic_light", 1914, "electric traffic lights before 1914"),
    ("television", 1927, "television sets before 1927"),
    ("concrete_tower", 1900, "reinforced-concrete towers before 1900"),
)


def parse_period_year(period) -> int | None:
    """A period value -> a year (int, negative = BCE), or None.

    Accepts "1914", "Late 1914", "1914-1918" (start year), "500 BC",
    named eras ("Ancient Greece"), and None. "mythological" /
    "timeless" return None (no constraint). Never raises."""
    if period is None:
        return None
    text = str(period).strip().lower()
    if not text or text in ("mythological", "timeless", "myth", "unknown"):
        return None
    for era, year in ERA_YEARS.items():
        if era in text:
            return year
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    if len(digits) >= 3:
        year = int(digits[:4])
        if "bc" in text or "bce" in text:
            year = -year
        return year
    return None


def validate_period(elements, period) -> list[str]:
    """Anachronism errors for ``elements`` at ``period`` (may be []).

    Checks element kind/material tokens against ANACHRONISM_RULES
    and each element's own ``not_before`` tag when present. A period
    that parses to None imposes no constraint."""
    year = parse_period_year(period)
    if year is None:
        return []
    errors = []
    for el in elements:
        tokens = {str(el.get("kind", "")).lower(),
                  str(el.get("material", "")).lower()}
        tokens |= {str(t).lower() for t in el.get("extra", {}).get("tags", [])}
        for token, not_before, note in ANACHRONISM_RULES:
            if token in tokens and year < not_before:
                errors.append(
                    f"anachronism: element {el.get('id')} ({token}) "
                    f"in period {period}: {note}")
        nb = el.get("extra", {}).get("not_before")
        if isinstance(nb, int) and year < nb:
            errors.append(
                f"anachronism: element {el.get('id')} not_before={nb} "
                f"in period {period}")
    return errors


# ---------------------------------------------------------------------------
# Archetype catalog (general, data-selected)
# ---------------------------------------------------------------------------
# Each archetype: keywords scored against trait text, a period range,
# facade/material defaults, furniture vocabulary and a builder key.
# No archetype names any real place; selection is by generic words.
ARCHETYPES = {
    "EUROPEAN_STREET_1900": {
        "keywords": ("phố", "street", "mặt tiền", "facade", "trát vữa",
                     "plaster", "mái dốc", "pitched", "cửa hàng",
                     "shop", "đô thị", "urban", "cobblestone",
                     "đá lát", "townhouse", "vỉa hè", "sidewalk",
                     "cột đèn", "kiến trúc đô thị", "chung cư"),
        "period_range": (1850, 1950),
        "facade_colors": [(226, 210, 178), (214, 196, 168),
                          (198, 182, 158), (232, 220, 196)],
        "roof_color": (128, 62, 52),
        "ground_color": (132, 124, 110),
        "ground_kind": "cobblestone",
        "builder": "_build_european_street",
    },
    "GREEK_PALACE": {
        "keywords": ("cung điện", "palace", "cột đá", "column",
                     "cẩm thạch", "marble", "đền", "temple",
                     "hy lạp", "greek", "athens", "pediment",
                     "đầu hồi", "acropolis", "agora", "đền thờ",
                     "đỉnh olympus", "núi olympus", "mount olympus",
                     "mountain olympus"),
        "period_range": (None, None),
        "facade_colors": [(238, 234, 224), (232, 226, 212)],
        "roof_color": (178, 98, 66),
        "ground_color": (206, 196, 176),
        "ground_kind": "pale_stone",
        "builder": "_build_greek_palace",
    },
    "MEDITERRANEAN_ISLAND": {
        "keywords": ("đảo", "island", "địa trung hải", "mediterranean",
                     "biển", "sea", "whitewash", "vôi trắng",
                     "mái vòm", "dome", "ô liu", "olive", "aegean",
                     "bờ biển", "coast"),
        "period_range": (None, None),
        "facade_colors": [(244, 242, 236), (240, 236, 226)],
        "roof_color": (70, 110, 170),
        "ground_color": (216, 198, 160),
        "ground_kind": "sand",
        "builder": "_build_mediterranean_island",
    },
    "CAVE": {
        "keywords": ("hang", "cave", "thạch nhũ", "stalactite",
                     "grotto", "underground", "dưới lòng đất",
                     "đuốc", "torch", "hang động", "cavern"),
        "period_range": (None, None),
        "facade_colors": [(74, 66, 60), (62, 56, 52)],
        "roof_color": (52, 46, 42),
        "ground_color": (70, 62, 56),
        "ground_kind": "dark_stone",
        # A cave is dark by nature: it overrides the sky palette
        # regardless of time of day, and is exempt from the day
        # luminance floor (see test_lighting / proof notes).
        "light_override": {"sky_top": (26, 24, 22),
                           "sky_bottom": (52, 48, 44)},
        "builder": "_build_cave",
    },
    "BARRACKS": {
        "keywords": ("doanh trại", "barracks", "sân tập", "parade",
                     "quân đội", "military", "thao trường",
                     "barrack", "gạch", "brick", "trại lính",
                     "khu quân sự"),
        "period_range": (1700, None),
        "facade_colors": [(150, 84, 64), (142, 74, 58)],
        "roof_color": (88, 84, 80),
        "ground_color": (150, 136, 112),
        "ground_kind": "packed_earth",
        "builder": "_build_barracks",
    },
    "TRENCH": {
        "keywords": ("chiến hào", "trench", "bao cát", "sandbag",
                     "bùn", "mud", "hào", "ván gỗ", "duckboard",
                     "khói pháo", "no man's land", "tuyến hào",
                     "chiến trường", "battlefield"),
        "period_range": (1900, 1950),
        "facade_colors": [(122, 102, 72), (110, 92, 66)],
        "roof_color": (96, 82, 62),
        "ground_color": (96, 74, 52),
        "ground_kind": "mud",
        "builder": "_build_trench",
    },
    "FOREST": {
        "keywords": ("rừng", "forest", "woods", "tán cây", "canopy",
                     "undergrowth", "bụi rậm", "clearing", "trảng",
                     "cây cổ thụ", "khu rừng", "woodland"),
        "period_range": (None, None),
        "facade_colors": [(96, 110, 70)],
        "roof_color": (70, 88, 52),
        "ground_color": (104, 96, 66),
        "ground_kind": "forest_floor",
        "builder": "_build_forest",
    },
    "MODERN_CITY": {
        "keywords": ("thành phố hiện đại", "modern city", "cao ốc",
                     "skyscraper", "glass tower", "chung cư cao tầng",
                     "billboard", "biển quảng cáo", "giao lộ",
                     "intersection", "đường nhựa", "asphalt",
                     "tòa nhà cao tầng", "downtown"),
        "period_range": (1950, None),
        "facade_colors": [(150, 162, 176), (132, 144, 158),
                          (168, 176, 186)],
        "roof_color": (90, 96, 104),
        "ground_color": (110, 108, 104),
        "ground_kind": "asphalt",
        "builder": "_build_modern_city",
    },
    "INTERIOR_GENERIC": {
        "keywords": ("nội thất", "interior", "văn phòng", "office",
                     "phòng làm việc", "study", "phòng khách",
                     "parlour", "parlor", "bàn gỗ", "ghế gỗ",
                     "tủ hồ sơ", "filing cabinet", "throne room",
                     "phòng ngai vàng", "indoor", "trong nhà"),
        "period_range": (None, None),
        "facade_colors": [(216, 200, 170), (206, 190, 160)],
        "roof_color": (120, 100, 80),
        "ground_color": (146, 118, 84),
        "ground_kind": "wood_floor",
        "builder": "_build_interior",
    },
    "COUNTRYSIDE_ROAD": {
        "keywords": ("đồng quê", "countryside", "cánh đồng",
                     "đường đất", "dirt road", "country road",
                     "con đường đất", "hành quân", "march",
                     "nông thôn", "rural", "cây trụi lá", "bare tree",
                     "hàng rào", "địa hình thấp", "lowland",
                     "làng quê", "village", "đồng ruộng", "farmland"),
        "period_range": (None, None),
        "facade_colors": [(222, 208, 178)],
        "roof_color": (128, 62, 52),
        "ground_color": (132, 126, 88),
        "ground_kind": "packed_earth",
        "builder": "_build_countryside_road",
    },
    "FORGE": {
        # The Cyclops forge (T4): a divine blacksmith workshop.
        # "đe" (anvil) is word-boundary matched — the substring
        # would false-positive on "đem" (to bring). See
        # _WORD_KEYWORDS in the selection code.
        "keywords": ("lò rèn", "forge", "xưởng rèn", "thợ rèn",
                     "lò nung", "lò lửa", "blacksmith", "anvil",
                     "cái đe", "chiếc đe", "đe", "búa", "cyclops",
                     "furnace", "bellows", "bễ thổi", "quench",
                     "ironworks", "xưởng đúc", "tia lửa",
                     "rèn kiếm", "rèn vũ khí"),
        "period_range": (None, None),
        "facade_colors": [(96, 90, 84), (84, 78, 72)],
        "roof_color": (52, 46, 42),
        "ground_color": (70, 62, 56),
        "ground_kind": "dark_stone",
        "light_override": {"sky_top": (64, 48, 40),
                           "sky_bottom": (120, 96, 74)},
        # The forge mouth is a real light source (Test F): a warm
        # point light at the firemouth position. The falloff
        # (renderer25d default k=0.08) pools warm light on the
        # floor before the furnace, the back wall, and the anvil
        # station. JSON-safe spec dicts; see point_lights in the
        # package built by build_environment.
        "point_lights": [{"id": "forge_mouth_glow",
                          "position": (-3.2, 1.0, -5.75),
                          "intensity": 1.2, "falloff_k": 0.08,
                          "color": (255, 140, 40)}],
        "builder": "_build_forge",
    },
    "SHOPHOUSE_STREET": {
        # Modern Vietnamese shophouse (nhà ống) street: narrow
        # tall shophouses with awnings and sign boards — never
        # glass towers (MODERN_CITY) for this street type.
        "keywords": ("nhà ống", "shophouse", "nhà phố", "phố việt",
                     "việt nam hiện đại", "sài gòn", "hà nội",
                     "biển hiệu", "mái hiên", "awning", "xe máy",
                     "motorbike", "scooter", "hẻm", "quán cà phê",
                     "chợ đêm", "khu chợ", "ban công", "balcony",
                     "vỉa hè", "sidewalk"),
        "period_range": (1950, None),
        "facade_colors": [(232, 214, 170), (214, 190, 160),
                          (196, 178, 150), (226, 200, 178),
                          (206, 196, 168)],
        "roof_color": (110, 100, 92),
        "ground_color": (110, 108, 104),
        "ground_kind": "asphalt",
        "builder": "_build_shophouse_street",
    },
}

ARCHETYPE_ORDER = tuple(ARCHETYPES.keys())

GENERIC_NEUTRAL = "GENERIC_NEUTRAL"

_MAP_TYPE_WORDS = ("map", "bản đồ", "atlas", "geographical")


def _trait_text(traits: dict) -> str:
    """All trait text, lowercased, in one string.

    Used ONLY for builder gating (e.g. the interior builder's
    desk/cabinet rules), never for archetype selection — selection
    reads structured fields with weights (see
    :func:`_weighted_field_texts`)."""
    parts = []
    for key in ("features", "distinctive_features", "foreground",
                "midground", "background", "name", "geography",
                "architecture", "type", "lighting", "weather",
                "period"):
        value = traits.get(key)
        if isinstance(value, (list, tuple)):
            parts.extend(str(v) for v in value)
        elif value:
            parts.append(str(value))
    render_traits = traits.get("render_traits")
    if isinstance(render_traits, dict):
        for key in ("setting", "location_keyword"):
            if render_traits.get(key):
                parts.append(str(render_traits[key]))
    fields = traits.get("fields")
    if isinstance(fields, dict):
        parts.extend(str(v) for v in fields.values())
    return " ".join(parts).lower()


# ---------------------------------------------------------------------------
# Structured landmark selection (Phase E, task 5).
#
# Archetype selection reads STRUCTURED location-trait fields with
# weights (REQUIRED_LOCATION_TRAITS in cinematic_contracts), never
# keywords alone. A keyword counts ONCE, at the highest-weight
# field it appears in, so a landmarks/architecture declaration
# always beats incidental words in foreground/background text.
#
# The ``location_keyword`` default is EXCLUDED whenever any other
# selectable trait text exists: shot-block defaults
# (``location_keyword: "street"``) must never override declared
# trait data — the T4 defect that staged the Cyclops forge as a
# European street is impossible by construction. Only when the
# keyword is the SOLE selectable input does it score (weight 1,
# last-resort tiebreak), and the provenance records that.
# Ids and names are NEVER selection inputs.
# ---------------------------------------------------------------------------
_SELECTION_FIELD_WEIGHTS = {
    "landmarks": 5,
    "identity": 4, "geography": 4, "architecture": 4,
    "type": 3,
    "features": 2, "distinctive_features": 2, "materials": 2,
    "foreground": 1, "midground": 1, "background": 1,
    "conditions": 1, "lighting": 1, "weather": 1, "period": 1,
}

# V1 adapter ``fields`` block keys, same weights. NAME is never a
# selection input; unknown keys score at weight 1.
_FIELDS_KEY_WEIGHTS = {
    "LANDMARKS": 5,
    "IDENTITY": 4, "HISTORICAL_REFERENCE": 4, "ARCHITECTURE": 4,
    "TYPE": 3,
    "DISTINCTIVE_FEATURES": 2, "MATERIALS": 2,
    "FOREGROUND": 1, "MIDGROUND": 1, "BACKGROUND": 1,
    "CONDITIONS": 1, "WEATHER": 1, "TIME_OF_DAY": 1, "YEAR": 1,
}

# Keywords matched as whole words only (substring matching would
# false-positive: "đe" inside "đem"). Matched with a Unicode
# word-boundary regex; every other keyword is a substring match.
_WORD_KEYWORDS = frozenset({"đe"})


def _field_values(value) -> list[str]:
    """A trait field value -> list of lowercased strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out.extend(_field_values(v))
        return out
    if isinstance(value, dict):
        out = []
        for v in value.values():
            out.extend(_field_values(v))
        return out
    text = str(value).strip()
    return [text.lower()] if text else []


def _weighted_field_texts(traits: dict) -> list[tuple[int, str, str]]:
    """Selectable trait text as ``(weight, field, text)`` triples.

    Reads top-level structured fields, ``render_traits.setting``,
    and the V1 ``fields`` block. Excludes ids, names, and
    ``location_keyword`` (see the module note above)."""
    out = []
    for key, weight in _SELECTION_FIELD_WEIGHTS.items():
        for text in _field_values(traits.get(key)):
            out.append((weight, key, text))
    render_traits = traits.get("render_traits")
    if isinstance(render_traits, dict):
        for text in _field_values(render_traits.get("setting")):
            out.append((1, "setting", text))
    fields = traits.get("fields")
    if isinstance(fields, dict):
        for key, value in fields.items():
            if str(key).upper() == "NAME":
                continue
            weight = _FIELDS_KEY_WEIGHTS.get(str(key).upper(), 1)
            for text in _field_values(value):
                out.append((weight, f"fields.{key}", text))
    return out


def _keyword_matches(keyword: str, text: str) -> bool:
    """Substring match, except word keywords (whole-word regex)."""
    if keyword in _WORD_KEYWORDS:
        return re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)",
                         text) is not None
    return keyword in text


def _keyword_weight(keyword: str, texts) -> int:
    """Highest field weight whose text contains ``keyword`` (0)."""
    best = 0
    for weight, _field, text in texts:
        if _keyword_matches(keyword, text):
            best = max(best, weight)
    return best


def _select_archetype_detail(location_traits: dict) -> dict:
    """Full structured-selection detail (see select_archetype)."""
    traits = dict(location_traits or {})
    type_text = str(traits.get("type", "")).lower()
    if any(w in type_text for w in _MAP_TYPE_WORDS):
        return {"archetype": "MAP", "score": 0, "hits": [],
                "fields_used": [], "location_keyword": None,
                "location_keyword_ignored": False,
                "location_keyword_only": False}
    texts = _weighted_field_texts(traits)
    render_traits = traits.get("render_traits")
    location_keyword = None
    if isinstance(render_traits, dict):
        location_keyword = render_traits.get("location_keyword") or None
    has_selectable = any(text.strip() for _, _, text in texts)
    keyword_only = bool(location_keyword) and not has_selectable
    if keyword_only:
        texts = [(1, "location_keyword", str(location_keyword).lower())]
    best_id, best_score, best_hits = GENERIC_NEUTRAL, 0, []
    best_fields = []
    for archetype_id in ARCHETYPE_ORDER:
        keywords = ARCHETYPES[archetype_id]["keywords"]
        hits = []
        score = 0
        fields_used = set()
        for kw in keywords:
            w = _keyword_weight(kw, texts)
            if w > 0:
                hits.append(kw)
                score += w
                for weight, field, text in texts:
                    if weight == w and _keyword_matches(kw, text):
                        fields_used.add(field)
        if score > best_score:
            best_id, best_score, best_hits = archetype_id, score, hits
            best_fields = sorted(fields_used)
    return {"archetype": best_id, "score": best_score,
            "hits": best_hits, "fields_used": best_fields,
            "location_keyword": location_keyword,
            "location_keyword_ignored": bool(location_keyword)
            and has_selectable,
            "location_keyword_only": keyword_only}


def select_archetype(location_traits: dict):
    """Score archetypes against STRUCTURED trait fields.

    Returns ``(archetype_id, score, matched_keywords)``. Selection
    uses field-weighted generic vocabulary only — never ids or
    names, and never the ``location_keyword`` default when trait
    data exists (see the structured-selection note above). Zero
    hits -> GENERIC_NEUTRAL (an honest neutral backdrop, no faked
    identity). Map-type traits return ("MAP", 0, []) so the caller
    can defer to map_renderer."""
    detail = _select_archetype_detail(location_traits or {})
    return (detail["archetype"], detail["score"], detail["hits"])


# ---------------------------------------------------------------------------
# Element construction helpers
# ---------------------------------------------------------------------------
def _el(el_id, kind, layer, geometry, center, size, color, material,
        attachment=None, label="", extra=None):
    return {"id": el_id, "kind": kind, "layer": layer,
            "geometry": geometry, "center": tuple(float(v) for v in center),
            "size": tuple(float(v) for v in size),
            "color": tuple(int(c) for c in color), "material": material,
            "attachment": attachment, "label": label,
            "extra": dict(extra or {})}


def _wall_band(el_id, kind, wall, u0, v0, u1, v1, depth, color,
             material, layer="BG", extra=None):
    """A relief band on a wall face, derived from the wall rect.

    The centre is computed by INVERTING the attachment-validation
    formula, so ``validate_attachments`` recomputes it exactly.
    ``(u0, v0, u1, v1)`` is the local rect (u across, v from the
    top); the band protrudes ``depth`` forward from the face."""
    pw, ph = wall["size"][0], wall["size"][1]
    px, py, pz = wall["center"]
    top = py + ph / 2
    exp_x = px + ((u0 + u1) / 2 - 0.5) * pw
    exp_y = top - (v0 + v1) / 2 * ph
    exp_z = pz + wall["size"][2] / 2 + depth / 2 + 0.02
    return _el(el_id, kind, layer, "box",
               (exp_x, exp_y, exp_z),
               ((u1 - u0) * pw, (v1 - v0) * ph, depth),
               color, material,
               attachment={"parent": wall["id"], "relation": "on_wall",
                           "local_rect": (u0, v0, u1, v1)},
               extra=extra)


def _facade(prefix, rng, x, z, width, stories, colors, roof_color,
            window_color, sign_text="", story_h=1.5, depth=0.8):
    """A facade: wall + gable roof + attached windows + door + relief.

    Window/door world positions are DERIVED from the wall rect via
    the SHARED layout contract (:func:`facade_window_layout` in
    ``paint_textures`` — the same layout the painted windows layer
    uses), so attachment validation can recompute them exactly and
    painted/geometric openings can never disagree. The layout and
    its parameters are recorded on the wall element's
    ``extra["window_layout"]``.

    Relief (P-S2): plinth, cornice, per-window sills + lintels,
    door step + hood, and a ridge chimney — all real 3D elements
    with valid attachments (or a recorded suspension reason for
    the ridge-straddling chimney)."""
    height = stories * story_h
    wall_id = f"{prefix}_wall"
    wall_color = rng.choice(colors)
    wall = _el(wall_id, "facade_wall", "BG", "box",
               (x, height / 2, z), (width, height, depth),
               wall_color, "plaster")
    elements = [wall]
    # Shared window/door grid (even-fraction mode, the 3D grid).
    cols = max(2, int(round(width / 1.1)))
    win_w, win_h = 0.5, 0.85
    door_w, door_h = 0.85, 1.5
    door_u = 0.5 if cols % 2 == 1 else 0.32
    layout = facade_window_layout(
        width, height, grid="even", rows=stories, cols=cols,
        win_w=win_w, win_h=win_h, door_w=door_w, door_h=door_h,
        door_u=door_u)
    wall["extra"]["window_layout"] = {
        "grid": "even", "rows": stories, "cols": cols,
        "win_w": win_w, "win_h": win_h,
        "door_w": door_w, "door_h": door_h, "door_u": door_u,
        "layout": layout,
    }
    roof_h = max(0.5, width * 0.28)
    elements.append(_el(
        f"{prefix}_roof", "gable_roof", "BG", "gable_prism",
        (x, height + roof_h / 2, z), (width + 0.3, roof_h, depth + 0.3),
        roof_color, "roof_tile",
        attachment={"parent": wall_id, "relation": "on_top",
                    "local_rect": None}))
    # Plinth: darker band along the wall base, standing on the
    # ground (the painted plinth in the plaster texture aligns
    # with this geometry — same 0.4 m height).
    elements.append(_el(
        f"{prefix}_plinth", "plinth", "BG", "box",
        (x, 0.2, z), (width + 0.12, 0.4, depth + 0.12),
        _blend(wall_color, (0, 0, 0), 0.18), "stone",
        attachment={"parent": None, "relation": "on_ground",
                    "local_rect": None}))
    # Cornice: protruding band just under the roofline.
    cornice_h = 0.16
    elements.append(_wall_band(
        f"{prefix}_cornice", "cornice", wall,
        0.0, 0.0, 1.0, cornice_h / height, 0.16,
        _blend(wall_color, (0, 0, 0), 0.08), "plaster"))
    # Chimney straddling the gable ridge: embedded 0.25 m into the
    # apex so it reads as planted from every viewpoint (a chimney
    # balanced exactly on the ridge line would float visibly from
    # the side). The suspension reason records why it has no
    # on_top attachment.
    elements.append(_el(
        f"{prefix}_chimney", "chimney", "BG", "box",
        (x, height + roof_h - 0.25 + 0.4, z), (0.4, 0.8, 0.4),
        (142, 74, 58), "brick",
        extra={"suspension": "straddles gable ridge: embedded 0.25 m "
                            "into the roof apex"}))
    front_z = z + depth / 2 + 0.04
    # Windows from the shared layout (metres from the wall's
    # bottom-left corner -> world centre + local rect). The grid
    # iterates rows top-to-bottom, matching the old win_{row}_{col}
    # ids; margins guarantee every window fits inside the wall for
    # facade widths >= 0.85 m and stories >= 1.
    trim_color = _blend(wall_color, (255, 255, 255), 0.18)
    for idx, (wx_m, wy_m, ww_m, wh_m) in enumerate(layout["windows"]):
        row, col = divmod(idx, cols)
        wx = x - width / 2 + wx_m + ww_m / 2
        wy = wy_m + wh_m / 2
        rect = (wx_m / width, 1.0 - (wy_m + wh_m) / height,
                (wx_m + ww_m) / width, 1.0 - wy_m / height)
        elements.append(_el(
            f"{prefix}_win_{row}_{col}", "window", "BG", "box",
            (wx, wy, front_z), (ww_m, wh_m, 0.06),
            window_color, "glass",
            attachment={"parent": wall_id, "relation": "on_wall",
                        "local_rect": rect}))
        # Sill below + lintel hood above, slightly wider than the
        # window, protruding from the face.
        u0, v0, u1, v1 = rect
        su0 = max(0.0, u0 - 0.06 / width)
        su1 = min(1.0, u1 + 0.06 / width)
        sill_v1 = min(1.0, v1 + 0.08 / height)
        if sill_v1 > v1:
            elements.append(_wall_band(
                f"{prefix}_sill_{row}_{col}", "window_sill", wall,
                su0, v1, su1, sill_v1, 0.10, trim_color, "stone"))
        lintel_v0 = max(0.0, v0 - 0.10 / height)
        if lintel_v0 < v0:
            elements.append(_wall_band(
                f"{prefix}_lintel_{row}_{col}", "window_lintel", wall,
                su0, lintel_v0, su1, v0, 0.10, trim_color, "stone"))
    # Door from the shared layout: bottom exactly on the ground.
    door = layout["door"]
    if door is not None:
        dx_m, _dy_m, dw_m, dh_m = door
        dx = x - width / 2 + dx_m + dw_m / 2
        door_rect = (dx_m / width, 1.0 - dh_m / height,
                     (dx_m + dw_m) / width, 1.0)
        elements.append(_el(
            f"{prefix}_door", "door", "BG", "box",
            (dx, dh_m / 2, front_z), (dw_m, dh_m, 0.08),
            (74, 52, 34), "wood",
            attachment={"parent": wall_id, "relation": "on_wall_ground",
                        "local_rect": door_rect}))
        # Door step (ground slab in front of the door) + hood
        # above it (only when the door does not fill the wall —
        # a 1-story facade has no room for a hood).
        elements.append(_el(
            f"{prefix}_doorstep", "door_step", "BG", "box",
            (dx, 0.06, front_z + 0.18), (dw_m + 0.3, 0.12, 0.42),
            (150, 148, 140), "stone",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
        door_top_v = 1.0 - dh_m / height
        hood_v0 = door_top_v - 0.12 / height
        if hood_v0 >= 0.0:
            hu0 = max(0.0, door_rect[0] - 0.1 / width)
            hu1 = min(1.0, door_rect[2] + 0.1 / width)
            elements.append(_wall_band(
                f"{prefix}_doorhood", "door_hood", wall,
                hu0, hood_v0, hu1, door_top_v, 0.12,
                trim_color, "stone"))
    if sign_text:
        sign_y = story_h * 0.92
        v_mid = (height - sign_y) / height
        half_v = 0.2 / height
        elements.append(_el(
            f"{prefix}_sign", "shop_sign", "BG", "box",
            (x, sign_y, front_z + 0.05), (width * 0.6, 0.4, 0.06),
            (28, 34, 48), "painted_wood",
            attachment={"parent": wall_id, "relation": "on_wall",
                        "local_rect": (0.2, v_mid - half_v,
                                       0.8, v_mid + half_v)},
            label=sign_text))
    return elements, wall


def _lamp_post(prefix, x, z, layer="MG", lit=False):
    pole_h = 3.1
    elements = [
        _el(f"{prefix}_pole", "lamp_post", layer, "box",
            (x, pole_h / 2, z), (0.14, pole_h, 0.14), (34, 36, 42),
            "iron", attachment={"parent": None, "relation": "on_ground",
                                "local_rect": None}),
        _el(f"{prefix}_head", "lamp_head", layer, "box",
            (x, pole_h + 0.12, z), (0.5, 0.24, 0.5),
            (255, 211, 78) if lit else (52, 54, 60), "glass",
            attachment={"parent": f"{prefix}_pole", "relation": "on_top",
                        "local_rect": None}),
    ]
    return elements


def _tree(prefix, rng, x, z, layer="BG", scale=1.0, leaf_color=(84, 110, 66)):
    """A tree: trunk + multi-lobe canopy (P-S3).

    The canopy is a central blob on top of the trunk plus three
    satellite lobes overlapping it, so the crown reads as foliage
    mass with depth instead of a single flat blob. Lobe colours
    jitter from the archetype/trait ``leaf_color`` only — never
    from an external palette. Lobe jitter uses an isolated RNG
    seeded from the tree id, so the shared builder RNG stream is
    untouched and layouts stay stable."""
    trunk_h = 2.4 * scale
    lrng = random.Random(f"{prefix}:{scale}:{leaf_color}")
    elements = [
        _el(f"{prefix}_trunk", "tree_trunk", layer, "box",
            (x, trunk_h / 2, z), (0.3 * scale, trunk_h, 0.3 * scale),
            (88, 64, 44), "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}),
        _el(f"{prefix}_canopy", "canopy", layer, "blob",
            (x, trunk_h + 0.85 * scale, z),
            (2.4 * scale, 1.7 * scale, 2.4 * scale),
            leaf_color, "foliage",
            attachment={"parent": f"{prefix}_trunk", "relation": "on_top",
                        "local_rect": None}),
    ]
    core_cy = trunk_h + 0.85 * scale
    for i, (dx, dy, dz) in enumerate(
            ((-0.85, 0.25, 0.15), (0.8, 0.35, -0.2), (0.1, 0.75, 0.3))):
        if i % 2:
            lobe_color = _blend(leaf_color, (255, 255, 220),
                                lrng.uniform(0.0, 0.12))
        else:
            lobe_color = _blend(leaf_color, (0, 0, 0),
                                lrng.uniform(0.0, 0.10))
        elements.append(_el(
            f"{prefix}_lobe{i}", "canopy", layer, "blob",
            (x + dx * scale, core_cy + dy * scale, z + dz * scale),
            (1.5 * scale, 1.1 * scale, 1.5 * scale),
            lobe_color, "foliage",
            attachment={"parent": f"{prefix}_canopy",
                        "relation": "overlaps", "local_rect": None}))
    return elements


def _bush(prefix, rng, x, z, layer="MG", scale=1.0,
          leaf_color=(84, 110, 66)):
    """A shrub: base blob on the ground + two overlapping lobes."""
    lrng = random.Random(f"{prefix}:{scale}:{leaf_color}")
    elements = [
        _el(f"{prefix}_bush", "bush", layer, "blob",
            (x, 0.35 * scale, z),
            (1.4 * scale, 0.7 * scale, 1.1 * scale),
            leaf_color, "foliage",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}),
    ]
    for i, (dx, dy, dz) in enumerate(((-0.45, 0.3, 0.1), (0.45, 0.25, -0.1))):
        elements.append(_el(
            f"{prefix}_bush_lobe{i}", "bush", layer, "blob",
            (x + dx * scale, 0.35 * scale + dy * scale, z + dz * scale),
            (0.9 * scale, 0.55 * scale, 0.8 * scale),
            _blend(leaf_color, (255, 255, 220),
                   lrng.uniform(0.0, 0.10)),
            "foliage",
            attachment={"parent": f"{prefix}_bush",
                        "relation": "overlaps", "local_rect": None}))
    return elements


def _hedge(prefix, x, z, length, layer="MG", height=0.9,
           leaf_color=(96, 110, 66)):
    """A clipped hedge: box core on the ground + blob top dressing
    overlapping it (no floating top)."""
    return [
        _el(f"{prefix}_hedge", "hedgerow", layer, "box",
            (x, height / 2, z), (length, height, 0.8),
            leaf_color, "foliage",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}),
        _el(f"{prefix}_hedge_top", "hedgerow", layer, "blob",
            (x, height + 0.08, z), (length * 0.92, 0.35, 0.7),
            _blend(leaf_color, (255, 255, 220), 0.08), "foliage",
            attachment={"parent": f"{prefix}_hedge",
                        "relation": "overlaps", "local_rect": None}),
    ]


def _column(prefix, x, z, layer, height, color, with_pediment=False):
    shaft_h = height - 0.55
    elements = [
        _el(f"{prefix}_base", "column_base", layer, "box",
            (x, 0.14, z), (0.78, 0.28, 0.78), color, "marble",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}),
        _el(f"{prefix}_shaft", "column", layer, "box",
            (x, 0.28 + shaft_h / 2, z), (0.52, shaft_h, 0.52), color,
            "marble",
            attachment={"parent": f"{prefix}_base", "relation": "on_top",
                        "local_rect": None}),
        _el(f"{prefix}_capital", "column_capital", layer, "box",
            (x, 0.28 + shaft_h + 0.14, z), (0.8, 0.28, 0.8), color,
            "marble",
            attachment={"parent": f"{prefix}_shaft", "relation": "on_top",
                        "local_rect": None}),
    ]
    return elements


# ---------------------------------------------------------------------------
# Archetype builders (each: rng, colors, context -> elements)
# ---------------------------------------------------------------------------
def _build_european_street(rng, ctx):
    elements = []
    colors = ctx["facade_colors"]
    xs = [-7.2, -3.6, 0.2, 3.8, 7.4]
    for i, x in enumerate(xs):
        stories = rng.choice([3, 3, 4])
        z = -11.5 + rng.uniform(-0.8, 0.8)
        els, _ = _facade(f"fac{i}", rng, x, z,
                         rng.uniform(2.8, 3.4), stories, colors,
                         ctx["roof_color"], ctx["window_color"],
                         sign_text=ctx["sign_text"] if i == 2 else "")
        elements.extend(els)
    # Distant roofline silhouette (depth cue, no windows).
    for i, x in enumerate([-10.5, -8.8, 9.2, 11.0]):
        elements.append(_el(
            f"distant{i}", "distant_roofline", "BG", "box",
            (x, 1.6, -19.0), (2.6, 3.2, 1.0), (96, 104, 122), "silhouette"))
    # Street furniture: kerb slabs, lamp posts, bench.
    elements.append(_el("kerb", "kerb", "MG", "box", (0.0, 0.08, -1.2),
                        (16.0, 0.16, 0.6), (150, 148, 140), "stone",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    elements.extend(_lamp_post("lampL", -4.6, -2.2, "MG",
                               lit=ctx["is_night"]))
    elements.extend(_lamp_post("lampR", 4.4, -1.6, "MG",
                               lit=ctx["is_night"]))
    elements.append(_el("bench", "bench", "MG", "box", (2.6, 0.24, -2.6),
                        (1.9, 0.48, 0.6), (122, 74, 43), "wood",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    # Foreground occluders: near lamp post + railing at frame edges.
    # The railing bar stands on two posts (P-S5: no floating bars).
    elements.extend(_lamp_post("lampFG", 5.8, 1.9, "FG",
                               lit=ctx["is_night"]))
    for j, px in enumerate((-6.5, -4.7)):
        elements.append(_el(
            f"railingFG_post{j}", "railing_post", "FG", "box",
            (px, 0.225, 1.6), (0.1, 0.45, 0.1), (40, 42, 50), "iron",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    elements.append(_el("railingFG", "railing", "FG", "box",
                        (-5.6, 0.5, 1.6), (2.2, 0.1, 0.1), (40, 42, 50),
                        "iron",
                        attachment={"parent": "railingFG_post0",
                                    "relation": "on_top",
                                    "local_rect": None}))
    # Trait-led street trees (P-S3): only when the traits declare
    # vegetation — the environment shows what the script declares.
    # ("tree" alone would false-positive inside "street".)
    trait_text = ctx.get("trait_text", "")
    if any(w in trait_text for w in ("cây", " tree ", " trees",
                                     "tree-lined", "cây xanh",
                                     "hàng cây", "bóng cây")):
        leaf = ctx.get("leaf_color") or (84, 110, 66)
        elements.extend(_tree("street_treeL", rng, -5.0, -3.4, "MG",
                              scale=0.9, leaf_color=leaf))
        elements.extend(_tree("street_treeR", rng, 5.2, -4.0, "MG",
                              scale=0.85, leaf_color=leaf))
    return elements


def _build_greek_palace(rng, ctx):
    elements = []
    marble = ctx["facade_colors"][0]
    # Steps + platform (step 0 on the ground, each next on the last).
    for i, w in enumerate((11.0, 10.2, 9.4)):
        att = ({"parent": None, "relation": "on_ground",
                "local_rect": None} if i == 0 else
               {"parent": f"step{i - 1}", "relation": "on_top",
                "local_rect": None})
        elements.append(_el(
            f"step{i}", "steps", "MG", "box",
            (0.0, 0.09 + i * 0.18, -5.2 + i * 0.35),
            (w, 0.18, 1.2), marble, "marble", attachment=att))
    # Colonnade + back wall + pediment.
    col_h = 4.2
    for i, x in enumerate([-4.5, -2.7, -0.9, 0.9, 2.7, 4.5]):
        elements.extend(_column(f"col{i}", x, -8.2, "BG", col_h, marble))
    elements.append(_el(
        "backwall", "facade_wall", "BG", "box", (0.0, 2.4, -9.4),
        (10.6, 4.8, 0.6), _blend(marble, (200, 190, 170), 0.25),
        "marble"))
    elements.append(_el(
        "pediment", "gable_roof", "BG", "gable_prism",
        (0.0, 4.8 + 0.7, -8.2), (11.4, 1.4, 1.4), ctx["roof_color"],
        "roof_tile",
        attachment={"parent": "backwall", "relation": "on_top",
                    "local_rect": None}))
    # Side wings (lower walls with a door each).
    for side, x in (("L", -6.8), ("R", 6.8)):
        elements.append(_el(
            f"wing{side}", "facade_wall", "BG", "box", (x, 1.5, -8.6),
            (2.6, 3.0, 0.8), marble, "marble"))
        elements.append(_el(
            f"wingdoor{side}", "door", "BG", "box", (x, 0.85, -8.15),
            (0.9, 1.7, 0.08), (74, 52, 34), "wood",
            attachment={"parent": f"wing{side}",
                        "relation": "on_wall_ground",
                        "local_rect": (0.32, 0.43, 0.68, 1.0)}))
    # Courtyard furniture + foreground column edge + olive tree.
    elements.append(_el("altar", "altar", "MG", "box", (0.0, 0.5, -3.4),
                        (1.4, 1.0, 0.9), marble, "marble",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    elements.extend(_column("colFG", -5.2, 1.8, "FG", 5.0, marble))
    elements.extend(_tree("olive", rng, 5.6, -1.2, "MG", scale=0.8,
                          leaf_color=(112, 116, 62)))
    # Trait-led mountain peaks (P-S3/E): a mountain palace (Mount
    # Olympus) rises above distant peaks; a palace without mountain
    # traits gets none. Peaks are grounded silhouettes with snow-cap
    # blobs overlapping their apexes.
    trait_text = ctx.get("trait_text", "")
    if any(w in trait_text for w in ("núi", "đỉnh", "olympus", "mây",
                                     "mountain", "peak", "cloud")):
        peak_color = _blend(marble, (140, 160, 190), 0.5)
        for i, (px, pz, pw, ph) in enumerate(
                ((-7.5, -20.0, 7.0, 5.0), (0.5, -22.0, 9.0, 6.5),
                 (7.8, -20.0, 6.0, 4.0))):
            elements.append(_el(
                f"peak{i}", "mountain_peak", "BG", "gable_prism",
                (px, ph / 2, pz), (pw, ph, 2.0), peak_color,
                "silhouette"))
            elements.append(_el(
                f"peak{i}_snow", "snow_cap", "BG", "blob",
                (px, ph - 0.2, pz), (1.8, 0.8, 1.2),
                (242, 244, 248), "silhouette",
                attachment={"parent": f"peak{i}", "relation": "overlaps",
                            "local_rect": None}))
    return elements


def _build_mediterranean_island(rng, ctx):
    elements = []
    white = ctx["facade_colors"][0]
    # Stepped whitewashed cubes on a slope (flat roofs, blue dome).
    houses = [(-6.4, -12.0, 2.6, 2.2, 0.0), (-3.2, -11.0, 3.0, 2.6, 0.3),
              (0.4, -12.4, 2.8, 2.0, 0.0), (3.6, -11.2, 3.2, 2.8, 0.5),
              (6.8, -12.6, 2.6, 2.2, 0.1)]
    for i, (x, z, w, h, lift) in enumerate(houses):
        house_extra = {}
        if lift > 0:
            # P-S5: stepped up a hillside — the lift is terrain,
            # not a floater; the suspension reason records it.
            house_extra["suspension"] = (
                "slope: house stepped up the hillside "
                f"(lift {lift} m)")
        elements.append(_el(
            f"house{i}", "facade_wall", "BG", "box",
            (x, lift + h / 2, z), (w, h, 1.6), white, "whitewash",
            extra=house_extra))
        elements.append(_el(
            f"house{i}_roof", "flat_roof", "BG", "box",
            (x, lift + h + 0.08, z), (w + 0.2, 0.16, 1.8),
            _blend(white, (120, 120, 120), 0.2), "whitewash",
            attachment={"parent": f"house{i}", "relation": "on_top",
                        "local_rect": None}))
        door_u_mid = 0.28
        door_half_u = 0.4 / w
        door_v0 = 1.0 - 1.5 / h
        elements.append(_el(
            f"house{i}_door", "door", "BG", "box",
            (x - w * 0.22, lift + 0.75, z + 0.84), (0.8, 1.5, 0.08),
            (52, 90, 150), "wood",
            attachment={"parent": f"house{i}",
                        "relation": "on_wall_ground",
                        "local_rect": (door_u_mid - door_half_u, door_v0,
                                       door_u_mid + door_half_u, 1.0)}))
        win_u_mid = 0.74
        win_v_mid = 0.38
        elements.append(_el(
            f"house{i}_win", "window", "BG", "box",
            (x + w * 0.24, lift + h * 0.62, z + 0.84),
            (0.55, 0.7, 0.06), (40, 70, 120), "glass",
            attachment={"parent": f"house{i}", "relation": "on_wall",
                        "local_rect": (win_u_mid - 0.275 / w,
                                       win_v_mid - 0.35 / h,
                                       win_u_mid + 0.275 / w,
                                       win_v_mid + 0.35 / h)}))
    # Blue dome on the tallest house.
    elements.append(_el(
        "dome", "dome", "BG", "blob", (3.6, 0.5 + 2.8 + 0.5, -11.2),
        (1.6, 1.0, 1.6), (52, 98, 168), "painted",
        attachment={"parent": "house3", "relation": "on_top",
                    "local_rect": None}))
    # Sea band behind the houses + sand foreground.
    elements.append(_el("sea", "sea", "BG", "box", (0.0, 0.06, -17.0),
                        (44.0, 0.12, 8.0), (58, 110, 150), "water"))
    elements.extend(_tree("olive1", rng, -5.2, -3.0, "MG", scale=0.75,
                          leaf_color=(112, 116, 62)))
    elements.extend(_tree("olive2", rng, 5.0, -4.2, "MG", scale=0.65,
                          leaf_color=(112, 116, 62)))
    elements.append(_el("wallFG", "whitewash_wall", "FG", "box",
                        (-6.2, 0.7, 1.7), (2.6, 1.4, 0.5), white,
                        "whitewash"))
    elements.append(_el("bougainvillea", "flowering_shrub", "FG", "blob",
                        (-5.4, 1.6, 1.7), (1.6, 0.9, 1.0), (178, 60, 120),
                        "foliage",
                        attachment={"parent": "wallFG",
                                    "relation": "overlaps",
                                    "local_rect": None}))
    return elements


def _build_cave(rng, ctx):
    elements = []
    rock = ctx["facade_colors"][0]
    dark = _blend(rock, (0, 0, 0), 0.35)
    # Rock masses: back wall, side walls, ceiling slab.
    elements.append(_el("backrock", "rock_wall", "BG", "box",
                        (0.0, 3.0, -10.0), (16.0, 6.0, 1.2), rock, "rock"))
    elements.append(_el("leftrock", "rock_wall", "BG", "box",
                        (-7.6, 2.6, -5.0), (1.4, 5.2, 9.0), dark, "rock"))
    elements.append(_el("rightrock", "rock_wall", "BG", "box",
                        (7.6, 2.6, -5.0), (1.4, 5.2, 9.0), dark, "rock"))
    elements.append(_el("ceiling", "rock_ceiling", "BG", "box",
                        (0.0, 6.0, -5.0), (16.0, 0.6, 11.0), dark, "rock",
                        extra={"suspension": "ceiling slab: spans the "
                                            "side rock walls"}))
    # Stalactites hanging from the ceiling.
    for i, x in enumerate([-5.2, -2.0, 1.4, 4.6]):
        h = rng.uniform(0.8, 1.6)
        elements.append(_el(
            f"stalactite{i}", "stalactite", "BG", "gable_prism",
            (x, 5.7 - h / 2, -6.0 - (i % 2) * 2.0),
            (0.5, h, 0.5), rock, "rock",
            attachment={"parent": "ceiling", "relation": "hangs_from",
                        "local_rect": None},
            extra={"inverted": True}))
    # Floor rocks + torch + glow blobs.
    for i, (x, z) in enumerate([(-3.4, -3.0), (2.8, -4.4), (0.6, -6.2)]):
        elements.append(_el(
            f"floorrock{i}", "boulder", "MG", "box",
            (x, 0.3, z), (1.1, 0.6, 0.9), dark, "rock",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    # Standing torch (grounded, P-S5) + flame on top of it.
    elements.append(_el("torch", "torch", "MG", "box", (-1.8, 0.7, -7.8),
                        (0.12, 1.4, 0.12), (88, 64, 44), "wood",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    elements.append(_el("flame", "flame", "MG", "blob",
                        (-1.8, 1.75, -7.8), (0.5, 0.7, 0.5),
                        (255, 170, 60), "fire",
                        attachment={"parent": "torch",
                                    "relation": "on_top",
                                    "local_rect": None}))
    elements.append(_el("rockFG", "rock_wall", "FG", "box",
                        (6.4, 1.8, 1.6), (2.0, 3.6, 1.2), dark, "rock"))
    return elements


def _build_barracks(rng, ctx):
    elements = []
    brick = ctx["facade_colors"][0]
    # Long brick building: 2 stories, many windows, pitched roof.
    els, _ = _facade("barrack", rng, 0.0, -11.0, 11.0, 2, [brick],
                     ctx["roof_color"], ctx["window_color"])
    elements.extend(els)
    # Parade ground furniture: fence, flag pole, crates.
    for i, x in enumerate(range(-7, 8, 2)):
        elements.append(_el(
            f"fence{i}", "fence_post", "MG", "box", (float(x), 0.5, -3.0),
            (0.12, 1.0, 0.12), (90, 70, 50), "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    elements.append(_el("fencerail", "fence_rail", "MG", "box",
                        (0.0, 0.85, -3.0), (14.0, 0.08, 0.08),
                        (90, 70, 50), "wood",
                        attachment={"parent": "fence0",
                                    "relation": "overlaps",
                                    "local_rect": None}))
    elements.append(_el("flagpole", "flag_pole", "MG", "box",
                        (5.6, 2.4, -5.0), (0.1, 4.8, 0.1), (60, 60, 64),
                        "iron",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    elements.append(_el("flag", "flag", "MG", "box",
                        (6.15, 4.35, -5.0), (1.0, 0.6, 0.04),
                        (150, 50, 44), "cloth",
                        attachment={"parent": "flagpole",
                                    "relation": "overlaps",
                                    "local_rect": None}))
    for i, (x, z) in enumerate([(-4.2, -2.0), (-3.5, -1.6), (3.2, -2.4)]):
        elements.append(_el(
            f"crate{i}", "crate", "MG", "box", (x, 0.28, z),
            (0.6, 0.56, 0.6), (139, 94, 52), "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    elements.append(_el("fenceFG", "fence_post", "FG", "box",
                        (-6.0, 0.5, 1.7), (0.14, 1.0, 0.14), (90, 70, 50),
                        "wood"))
    return elements


def _build_trench(rng, ctx):
    """A trench CORRIDOR: sandbag walls receding on both sides, a
    duckboard walk down the middle, a back wall closing the view,
    broken tree + low smoke beyond it."""
    elements = []
    sand = (158, 138, 100)

    def _bag(bag_id, x, y, z, layer, parent=None):
        # Ground-row bags stand on the ground; upper rows stack
        # on_top of the bag below (staggered brickwork pattern —
        # on_top checks height only, which is what stacking means).
        att = None
        if parent is not None:
            att = {"parent": parent, "relation": "on_top",
                   "local_rect": None}
        elif abs(y - 0.16) < 0.01:
            att = {"parent": None, "relation": "on_ground",
                   "local_rect": None}
        return _el(
            bag_id, "sandbag", layer, "box", (x, y, z),
            (0.42, 0.3, 0.58) if layer != "BACK" else (0.58, 0.3, 0.42),
            _blend(sand, (120, 100, 70), rng.uniform(0, 0.25)), "sand",
            attachment=att)

    # Side walls receding in z (3 rows, staggered).
    for side, x0 in (("L", -2.6), ("R", 2.6)):
        for row in range(3):
            for i in range(14):
                z = -1.0 - i * 0.62 - (0.3 if row % 2 else 0.0)
                parent = (f"sand{side}{row - 1}_{i}" if row > 0
                          else None)
                elements.append(_bag(
                    f"sand{side}{row}_{i}", x0, 0.16 + row * 0.3, z,
                    "MG" if z > -6 else "BG", parent))
    # Back wall closing the corridor.
    for row in range(3):
        for i in range(9):
            x = -2.5 + i * 0.62 + (0.3 if row % 2 else 0.0)
            parent = f"sandB{row - 1}_{i}" if row > 0 else None
            bag = _bag(f"sandB{row}_{i}", x, 0.16 + row * 0.3, -12.4,
                       "BACK", parent)
            bag["layer"] = "BG"
            elements.append(bag)
    # Shoring beams overhead (resting just above the 0.9-high walls).
    for i, z in enumerate((-4.0, -8.0)):
        elements.append(_el(
            f"beam{i}", "shoring_beam", "BG", "box", (0.0, 1.05, z),
            (5.6, 0.18, 0.3), (96, 74, 50), "wood",
            extra={"suspension": "shoring beam: spans the sandbag "
                                "walls (0.05 m clearance above the "
                                "0.91 m wall top)"}))
    # Duckboards down the middle.
    for i in range(9):
        elements.append(_el(
            f"duck{i}", "duckboard", "MG", "box",
            (rng.uniform(-0.3, 0.3), 0.06, -1.2 - i * 1.15),
            (1.3, 0.12, 0.6), (110, 84, 56), "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    # Puddles on the walk.
    for i, (x, z) in enumerate([(-0.7, -3.4), (0.8, -6.2)]):
        elements.append(_el(
            f"puddle{i}", "puddle", "MG", "blob", (x, 0.05, z),
            (1.1, 0.1, 0.7), (150, 160, 170), "water"))
    # Broken tree + low smoke beyond the back wall.
    elements.append(_el("borkentrunk", "tree_trunk", "BG", "box",
                        (-4.8, 1.1, -14.0), (0.3, 2.2, 0.3), (70, 52, 38),
                        "wood",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    elements.append(_el("brokenbranch", "branch", "BG", "box",
                        (-4.4, 2.0, -14.0), (0.9, 0.14, 0.14),
                        (70, 52, 38), "wood",
                        attachment={"parent": "borkentrunk",
                                    "relation": "overlaps",
                                    "local_rect": None}))
    # Distant artillery smoke: small, high and faint. Large low
    # blobs read as floating balloons in the integrated render.
    for i, (x, z) in enumerate([(-3.5, -17.0), (2.5, -18.0)]):
        elements.append(_el(
            f"smoke{i}", "smoke", "BG", "blob", (x, 3.0 + 0.4 * i, z),
            (2.6, 0.9, 0.8), (168, 166, 160), "smoke",
            extra={"suspension": "airborne: distant artillery smoke"}))
    # Foreground: sandbag edge + side-wall column near the camera.
    for i in range(3):
        parent = f"sandFG{i - 1}" if i > 0 else None
        elements.append(_bag(f"sandFG{i}", -2.6, 0.16 + i * 0.3, 1.9,
                             "FG", parent))
    elements.append(_bag("sandFG3", 2.6, 0.16, 1.9, "FG"))
    return elements


def _build_forest(rng, ctx):
    elements = []
    leaf = ctx.get("leaf_color") or (84, 110, 66)
    # Depth-graded trees: far (small, hazy) to near (large).
    positions = [(-8.0, -14.0, 1.0), (-4.5, -12.0, 1.1), (0.5, -13.0, 1.0),
                 (4.8, -11.5, 1.15), (8.2, -13.5, 1.0), (-6.2, -7.0, 1.25),
                 (-1.8, -6.0, 1.3), (3.0, -6.6, 1.25), (6.6, -7.4, 1.2)]
    for i, (x, z, scale) in enumerate(positions):
        elements.extend(_tree(f"tree{i}", rng, x, z, "BG", scale=scale,
                              leaf_color=leaf))
    # Undergrowth blobs + path slab.
    for i, (x, z) in enumerate([(-3.0, -4.0), (1.2, -3.4), (4.4, -4.6)]):
        elements.append(_el(
            f"under{i}", "undergrowth", "MG", "blob", (x, 0.35, z),
            (1.6, 0.7, 1.2), (74, 96, 58), "foliage"))
    elements.append(_el("path", "path", "MG", "box", (0.0, 0.05, -1.0),
                        (2.2, 0.1, 9.0), (150, 134, 104), "earth",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    # Foreground: big trunk at the frame edge + top foliage.
    elements.extend(_tree("treeFG", rng, -6.4, 1.8, "FG", scale=1.5,
                          leaf_color=leaf))
    elements.append(_el("foliageFG", "canopy", "FG", "blob",
                        (5.8, 4.6, 1.6), (3.0, 1.6, 1.0), leaf,
                        "foliage",
                        extra={"suspension": "canopy overhang: foliage "
                                            "mass entering from above "
                                            "the frame edge"}))
    return elements


def _build_modern_city(rng, ctx):
    elements = []
    glass = (52, 68, 88)
    towers = [(-7.6, -13.0, 3.4, 7.5), (-3.4, -14.5, 4.0, 9.0),
              (1.2, -13.5, 3.6, 6.5), (5.4, -14.0, 4.2, 8.2),
              (8.8, -12.5, 3.0, 5.5)]
    for i, (x, z, w, h) in enumerate(towers):
        elements.append(_el(
            f"tower{i}", "tower", "BG", "box", (x, h / 2, z),
            (w, h, 1.6), ctx["facade_colors"][i % len(ctx["facade_colors"])],
            "glass_curtain"))
        elements.append(_el(
            f"tower{i}_roof", "flat_roof", "BG", "box",
            (x, h + 0.1, z), (w + 0.2, 0.2, 1.8), ctx["roof_color"],
            "concrete",
            attachment={"parent": f"tower{i}", "relation": "on_top",
                        "local_rect": None}))
        # Lit window grid (thin boxes on the front face).
        cols, rows = max(3, int(w / 0.8)), max(4, int(h / 0.9))
        for r in range(rows):
            for c in range(cols):
                if rng.random() < 0.45:
                    continue
                u = 0.1 + 0.8 * (c + 0.5) / cols
                v = 0.08 + 0.84 * (r + 0.5) / rows
                elements.append(_el(
                    f"tower{i}_win_{r}_{c}", "window", "BG", "box",
                    (x + (u - 0.5) * w, h - v * h, z + 0.84),
                    (0.45, 0.55, 0.05),
                    (255, 211, 120) if ctx["is_night"] else glass,
                    "glass",
                    attachment={"parent": f"tower{i}",
                                "relation": "on_wall",
                                "local_rect": (u - 0.06, v - 0.05,
                                               u + 0.06, v + 0.05)}))
    # Street: crosswalk slabs + street lights + billboard (data label).
    for i in range(5):
        elements.append(_el(
            f"cross{i}", "crosswalk", "MG", "box",
            (-2.0 + i * 1.0, 0.06, -1.0), (0.6, 0.12, 2.4),
            (220, 220, 216), "paint",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    elements.extend(_lamp_post("streetL", -4.8, -2.4, "MG",
                               lit=ctx["is_night"]))
    elements.extend(_lamp_post("streetR", 4.8, -2.0, "MG",
                               lit=ctx["is_night"]))
    if ctx["sign_text"]:
        # Billboard mounted on tower2's front face (P-S5: the old
        # free-floating position is gone). Rect derived from the
        # tower2 rect (centre (1.2, 3.25, -13.5), size 3.6 x 6.5
        # x 1.6) so attachment validation recomputes it exactly.
        elements.append(_el(
            "billboard", "billboard", "BG", "box", (1.2, 4.6, -12.58),
            (3.4, 1.6, 0.2), (24, 30, 44), "painted_metal",
            attachment={"parent": "tower2", "relation": "on_wall",
                        "local_rect": (0.0278, 0.1692, 0.9722, 0.4154)},
            label=ctx["sign_text"]))
    elements.append(_el("poleFG", "traffic_pole", "FG", "box",
                        (6.0, 1.6, 1.8), (0.16, 3.2, 0.16), (40, 42, 46),
                        "iron"))
    return elements


def _build_interior(rng, ctx):
    """A generic period interior: room shell + trait-gated furniture.

    Walls, tall windows, rug and lamp always render (a room needs
    them); the desk + chair appear only when the trait text names
    desk/writing work, and the filing cabinet only when it names
    storage/cabinets — the environment shows what the script
    declares, and action staging (W4) supplies furniture the
    actions need beyond that. Window/picture centres are derived
    from wall (u, v) fractions so attachment validation recomputes
    them exactly (same pattern as _facade).
    """
    trait_text = ctx.get("trait_text", "")
    wall_color = ctx["facade_colors"][0]
    elements = []
    wall_id = "room_wall"
    elements.append(_el(wall_id, "room_wall", "BG", "box",
                        (0.0, 2.25, -6.0), (16.0, 4.5, 0.4), wall_color,
                        "plaster"))
    for side, sx in (("L", -7.8), ("R", 7.8)):
        elements.append(_el(
            f"room_side_{side}", "room_wall", "BG", "box",
            (sx, 2.25, -3.0), (0.4, 4.5, 6.4), wall_color, "plaster",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    # Tall windows on the back wall (u/v fractions -> centres).
    # Interior windows show daylight (pale sky), not the dark glass
    # of an exterior facade seen from the street.
    win_w, win_h, win_d = 0.9, 2.2, 0.06
    room_window_color = (170, 195, 220)
    front_z = -6.0 + 0.4 / 2 + win_d / 2 + 0.02
    for i, u in enumerate((0.28, 0.72)):
        v = 0.42
        wx = (u - 0.5) * 16.0
        wy = 4.5 - v * 4.5
        elements.append(_el(
            f"room_win_{i}", "window", "BG", "box",
            (wx, wy, front_z), (win_w, win_h, win_d),
            room_window_color, "glass",
            attachment={"parent": wall_id, "relation": "on_wall",
                        "local_rect": (u - win_w / 16.0 / 2,
                                       v - win_h / 4.5 / 2,
                                       u + win_w / 16.0 / 2,
                                       v + win_h / 4.5 / 2)}))
    # Framed picture / notice on the back wall.
    pic_w, pic_h, pic_d = 1.2, 0.9, 0.06
    pu, pv = 0.5, 0.30
    elements.append(_el(
        "room_picture", "wall_picture", "BG", "box",
        ((pu - 0.5) * 16.0, 4.5 - pv * 4.5, front_z),
        (pic_w, pic_h, pic_d), (60, 52, 44), "wood",
        attachment={"parent": wall_id, "relation": "on_wall",
                    "local_rect": (pu - pic_w / 16.0 / 2,
                                   pv - pic_h / 4.5 / 2,
                                   pu + pic_w / 16.0 / 2,
                                   pv + pic_h / 4.5 / 2)}))
    # Rug (flat slab, no shadow): muted madder red, never dominant.
    elements.append(_el("room_rug", "rug", "MG", "box",
                        (0.6, 0.03, -0.8), (4.5, 0.06, 3.0),
                        (118, 58, 52), "cloth"))
    # Floor lamp.
    elements.append(_el("room_lamp_pole", "lamp_post", "MG", "box",
                        (-2.5, 0.85, -2.0), (0.08, 1.7, 0.08),
                        (40, 36, 32), "iron",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    elements.append(_el("room_lamp_shade", "lamp_shade", "MG", "box",
                        (-2.5, 1.85, -2.0), (0.4, 0.3, 0.4),
                        (255, 220, 140), "cloth",
                        attachment={"parent": "room_lamp_pole",
                                    "relation": "on_top",
                                    "local_rect": None}))
    has_desk = any(w in trait_text for w in (
        "bàn", "desk", "viết", "write", "bureau", "writing"))
    has_cabinet = any(w in trait_text for w in (
        "tủ", "cabinet", "hồ sơ", "filing", "shelf", "kệ"))
    if has_desk:
        # Desk: two pedestals + top; chair facing it.
        for j, px in enumerate((0.35, 2.05)):
            elements.append(_el(
                f"desk_pedestal_{j}", "desk_pedestal", "MG", "box",
                (px, 0.37, -1.2), (0.5, 0.74, 0.9), (96, 62, 36),
                "wood",
                attachment={"parent": None, "relation": "on_ground",
                            "local_rect": None}))
        elements.append(_el(
            "desk_top", "desk", "MG", "box",
            (1.2, 0.78, -1.2), (2.2, 0.08, 1.0), (122, 74, 43), "wood",
            attachment={"parent": "desk_pedestal_0",
                        "relation": "on_top", "local_rect": None}))
        elements.append(_el(
            "desk_paper", "paper_stack", "MG", "box",
            (0.9, 0.84, -1.1), (0.45, 0.04, 0.3), (238, 234, 222),
            "paper",
            attachment={"parent": "desk_top", "relation": "on_top",
                        "local_rect": None}))
        elements.append(_el(
            "desk_ink", "ink_bottle", "MG", "box",
            (1.7, 0.89, -1.4), (0.12, 0.14, 0.12), (20, 20, 28),
            "glass",
            attachment={"parent": "desk_top", "relation": "on_top",
                        "local_rect": None}))
        elements.append(_el(
            "chair_base", "chair", "MG", "box",
            (1.2, 0.205, -0.35), (0.5, 0.41, 0.5), (96, 62, 36),
            "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
        elements.append(_el(
            "chair_seat", "chair", "MG", "box",
            (1.2, 0.45, -0.35), (0.55, 0.08, 0.55), (122, 74, 43),
            "wood",
            attachment={"parent": "chair_base", "relation": "on_top",
                        "local_rect": None}))
        elements.append(_el(
            "chair_back", "chair", "MG", "box",
            (1.2, 0.85, -0.12), (0.55, 0.8, 0.08), (96, 62, 36),
            "wood",
            attachment={"parent": "chair_seat", "relation": "overlaps",
                        "local_rect": None}))
    if has_cabinet:
        elements.append(_el(
            "room_cabinet", "cabinet", "MG", "box",
            (-4.6, 0.9, -5.4), (1.4, 1.8, 0.5), (88, 58, 34), "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
        elements.append(_el(
            "cabinet_papers", "paper_stack", "MG", "box",
            (-4.6, 1.85, -5.4), (0.5, 0.1, 0.35), (238, 234, 222),
            "paper",
            attachment={"parent": "room_cabinet", "relation": "on_top",
                        "local_rect": None}))
    return elements


def _build_countryside_road(rng, ctx):
    """A rural dirt road: fields, bare trees, fence, distant cottage.

    The march/journey environment — never a trench. Bare trees
    (trunk + limb boxes, no foliage) read as late-autumn/winter;
    the road is a long dirt slab receding to a treeline.
    """
    elements = [
        _el("dirt_road", "road", "MG", "box",
            (0.3, 0.04, -8.0), (2.6, 0.08, 22.0), (150, 128, 92),
            "packed_earth"),
        _el("field_L", "field", "BG", "box",
            (-6.0, 0.02, -8.0), (9.0, 0.04, 22.0), (128, 138, 84),
            "grass"),
        _el("field_R", "field", "BG", "box",
            (6.5, 0.02, -8.0), (8.0, 0.04, 22.0), (158, 146, 96),
            "grass"),
    ]
    # Bare trees: trunk + two asymmetric limb boxes, no foliage.
    # Limb lengths/heights vary per tree so they read as branches,
    # not utility-pole crossarms. Limbs overlap their trunk (P-S5).
    for i, (tx, tz) in enumerate(
            [(-4.5, -6.0), (4.8, -9.0), (-6.5, -13.0), (6.0, -16.0)]):
        elements.append(_el(
            f"bare_tree_{i}", "tree_trunk", "BG", "box",
            (tx, 1.1, tz), (0.18, 2.2, 0.18), (74, 58, 44), "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
        for j, dx in enumerate((-0.4, 0.35)):
            limb_len = rng.uniform(0.7, 1.0)
            elements.append(_el(
                f"bare_limb_{i}_{j}", "branch", "BG", "box",
                (tx + dx, 1.85 + 0.15 * j + rng.uniform(0, 0.1), tz),
                (limb_len, 0.08, 0.08),
                (74, 58, 44), "wood",
                attachment={"parent": f"bare_tree_{i}",
                            "relation": "overlaps",
                            "local_rect": None}))
    # Fence along the road's right edge.
    for i, fz in enumerate(range(-2, -15, -3)):
        elements.append(_el(
            f"road_fence_{i}", "fence_post", "MG", "box",
            (2.2, 0.5, float(fz)), (0.12, 1.0, 0.12), (90, 70, 50),
            "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    elements.append(_el("road_fence_rail", "fence_rail", "MG", "box",
                        (2.2, 0.85, -8.0), (0.08, 0.08, 12.0),
                        (90, 70, 50), "wood",
                        attachment={"parent": "road_fence_0",
                                    "relation": "overlaps",
                                    "local_rect": None}))
    # Hedgerows (P-S3: real hedge builder, not bare blobs).
    leaf = ctx.get("leaf_color") or (96, 110, 66)
    for i, (hx, hz) in enumerate(
            [(-3.5, -5.0), (5.5, -7.0), (-5.0, -11.0)]):
        elements.extend(_hedge(f"hedge_{i}", hx, hz, 2.2, "MG",
                               height=1.0, leaf_color=leaf))
    # Distant treeline masses.
    for i, mx in enumerate((-6.0, 0.5, 6.5)):
        elements.append(_el(
            f"treeline_{i}", "distant_mass", "BG", "box",
            (mx, 0.8, -19.0), (4.0, 1.6, 0.8), (72, 84, 58),
            "silhouette"))
    # Distant cottage: single-story facade + gable roof.
    els, _ = _facade("cottage", rng, -6.5, -13.0, 3.2, 1,
                     ctx["facade_colors"], ctx["roof_color"],
                     ctx["window_color"])
    elements.extend(els)
    # Foreground: fence post + overhanging bare branch.
    elements.append(_el("fenceFG", "fence_post", "FG", "box",
                        (-3.6, 0.5, 1.7), (0.14, 1.0, 0.14),
                        (90, 70, 50), "wood"))
    elements.append(_el("branchFG", "branch", "FG", "box",
                        (3.8, 2.6, 1.8), (1.6, 0.1, 0.1),
                        (74, 58, 44), "wood",
                        extra={"suspension": "overhang: bare branch "
                                            "entering from above the "
                                            "frame edge"}))
    return elements


def _build_forge(rng, ctx):
    """A divine blacksmith forge (the Cyclops forge, T4): stone
    workshop shell, furnace with fire mouth and chimney stack,
    anvil centre-stage, workbench, bellows, quench barrel, and a
    tool rack on the back wall. Test F additions: a brighter
    firemouth core (the glow source made visible), a glowing hot
    ingot on the anvil, quench steam, a coal pile, and bench
    tools (hammer + tongs). Every element is grounded,
    attached, or suspension-reasoned (P-S5)."""
    elements = []
    stone = ctx["facade_colors"][0]
    dark = _blend(stone, (0, 0, 0), 0.3)
    iron = (64, 66, 70)
    # Workshop shell: back + side stone walls, grounded.
    backwall = _el("forge_backwall", "stone_wall", "BG", "box",
                   (0.0, 2.6, -9.0), (15.0, 5.2, 0.8), stone, "stone")
    elements.append(backwall)
    for side, sx in (("L", -7.2), ("R", 7.2)):
        elements.append(_el(
            f"forge_side_{side}", "stone_wall", "BG", "box",
            (sx, 2.2, -5.0), (0.8, 4.4, 8.0), dark, "stone"))
    # Furnace: stone mass + cap + fire mouth + chimney + smoke.
    elements.append(_el(
        "furnace", "furnace", "BG", "box", (-3.2, 0.9, -6.5),
        (2.2, 1.8, 1.4), dark, "stone",
        attachment={"parent": None, "relation": "on_ground",
                    "local_rect": None}))
    elements.append(_el(
        "furnace_cap", "furnace", "BG", "box", (-3.2, 2.05, -6.5),
        (1.6, 0.5, 1.0), dark, "stone",
        attachment={"parent": "furnace", "relation": "on_top",
                    "local_rect": None}))
    elements.append(_el(
        "firemouth", "fire", "BG", "blob", (-3.2, 1.0, -5.75),
        (1.0, 0.7, 0.3), (255, 140, 40), "fire",
        attachment={"parent": "furnace", "relation": "overlaps",
                    "local_rect": None}))
    elements.append(_el(
        "furnace_stack", "chimney", "BG", "box", (-3.2, 3.5, -6.5),
        (0.7, 2.4, 0.7), dark, "stone",
        attachment={"parent": "furnace_cap", "relation": "on_top",
                    "local_rect": None}))
    elements.append(_el(
        "forge_smoke", "smoke", "BG", "blob", (-3.2, 5.3, -6.5),
        (1.4, 0.9, 0.8), (120, 112, 104), "smoke",
        extra={"suspension": "forge smoke rises from the chimney"}))
    # Anvil centre-stage: base + body + top, all stacked.
    elements.append(_el(
        "anvil_base", "anvil", "MG", "box", (0.6, 0.15, -3.2),
        (0.7, 0.3, 0.5), iron, "iron",
        attachment={"parent": None, "relation": "on_ground",
                    "local_rect": None}))
    elements.append(_el(
        "anvil_body", "anvil", "MG", "box", (0.6, 0.5, -3.2),
        (0.5, 0.4, 0.4), iron, "iron",
        attachment={"parent": "anvil_base", "relation": "on_top",
                    "local_rect": None}))
    elements.append(_el(
        "anvil_top", "anvil", "MG", "box", (0.6, 0.78, -3.2),
        (1.1, 0.16, 0.34), (84, 88, 94), "iron",
        attachment={"parent": "anvil_body", "relation": "on_top",
                    "local_rect": None}))
    # Workbench: two legs + top.
    for j, px in enumerate((2.6, 4.0)):
        elements.append(_el(
            f"bench_leg_{j}", "workbench", "MG", "box",
            (px, 0.37, -4.6), (0.18, 0.74, 0.7), (96, 62, 36),
            "wood",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
    elements.append(_el(
        "bench_top", "workbench", "MG", "box", (3.3, 0.78, -4.6),
        (1.9, 0.08, 0.8), (122, 74, 43), "wood",
        attachment={"parent": "bench_leg_0", "relation": "on_top",
                    "local_rect": None}))
    # Bellows beside the furnace + quench barrel.
    elements.append(_el(
        "bellows", "bellows", "MG", "box", (-1.4, 0.35, -6.2),
        (0.9, 0.7, 0.6), (122, 74, 43), "wood",
        attachment={"parent": None, "relation": "on_ground",
                    "local_rect": None}))
    elements.append(_el(
        "bellows_top", "bellows", "MG", "box", (-1.4, 0.78, -6.2),
        (0.8, 0.16, 0.5), (150, 100, 60), "wood",
        attachment={"parent": "bellows", "relation": "on_top",
                    "local_rect": None}))
    elements.append(_el(
        "quench_barrel", "barrel", "MG", "box", (4.8, 0.45, -2.8),
        (0.7, 0.9, 0.7), (96, 62, 36), "wood",
        attachment={"parent": None, "relation": "on_ground",
                    "local_rect": None}))
    elements.append(_el(
        "quench_water", "water_surface", "MG", "blob", (4.8, 0.94, -2.8),
        (0.55, 0.08, 0.55), (120, 150, 170), "water",
        attachment={"parent": "quench_barrel", "relation": "on_top",
                    "local_rect": None}))
    # Tool rack on the back wall + hanging tools.
    elements.append(_wall_band(
        "toolrack", "tool_rack", backwall,
        0.62, 0.25, 0.86, 0.42, 0.08, (96, 62, 36), "wood"))
    for j, tu in enumerate((0.65, 0.72, 0.79)):
        elements.append(_wall_band(
            f"tool_{j}", "hanging_tool", backwall,
            tu, 0.42, tu + 0.04, 0.62, 0.06, iron, "iron"))
    # Foreground: barrel edge + tool crate, both grounded.
    elements.append(_el(
        "barrelFG", "barrel", "FG", "box", (-5.4, 0.45, 1.7),
        (0.7, 0.9, 0.7), (96, 62, 36), "wood",
        attachment={"parent": None, "relation": "on_ground",
                    "local_rect": None}))
    elements.append(_el(
        "crateFG", "crate", "FG", "box", (5.6, 0.3, 1.8),
        (0.7, 0.6, 0.7), (122, 74, 43), "wood",
        attachment={"parent": None, "relation": "on_ground",
                    "local_rect": None}))
    # Test F: the glow source made visible — a brighter core
    # inside the firemouth, at the declared point-light position.
    elements.append(_el(
        "firemouth_core", "fire", "BG", "blob", (-3.2, 1.0, -5.65),
        (0.55, 0.4, 0.2), (255, 200, 90), "fire",
        attachment={"parent": "firemouth", "relation": "overlaps",
                    "local_rect": None}))
    # Hot ingot resting on the anvil top (glowing workpiece).
    elements.append(_el(
        "hot_ingot", "ingot", "MG", "box", (0.6, 0.89, -3.2),
        (0.5, 0.06, 0.12), (255, 110, 25), "iron",
        attachment={"parent": "anvil_top", "relation": "on_top",
                    "local_rect": None}))
    # Quench steam rising from the barrel water surface.
    elements.append(_el(
        "quench_steam", "steam", "MG", "blob", (4.8, 1.5, -2.8),
        (0.5, 0.5, 0.4), (200, 205, 210), "smoke",
        extra={"suspension": "steam rises from the quench barrel"}))
    # Coal pile on the ground beside the furnace.
    elements.append(_el(
        "coal_pile", "coal", "BG", "blob", (-4.9, 0.25, -6.3),
        (1.0, 0.5, 0.8), (30, 28, 26), "stone",
        attachment={"parent": None, "relation": "on_ground",
                    "local_rect": None}))
    # Bench tools: hammer + tongs resting on the workbench top.
    elements.append(_el(
        "bench_hammer", "hammer", "MG", "box", (2.9, 0.86, -4.6),
        (0.4, 0.08, 0.12), iron, "iron",
        attachment={"parent": "bench_top", "relation": "on_top",
                    "local_rect": None}))
    elements.append(_el(
        "bench_tongs", "tongs", "MG", "box", (3.8, 0.845, -4.5),
        (0.5, 0.05, 0.08), (90, 90, 95), "iron",
        attachment={"parent": "bench_top", "relation": "on_top",
                    "local_rect": None}))
    # Controlled sparks above the anvil (B2): a fixed-count,
    # seeded, bounded spark field, animated by render frame
    # index. Ambient forge activity; strike-synchronized bursts
    # are ATLAS's action-driven wiring, not this element.
    elements.append(_el(
        "anvil_sparks", "sparks", "MG", "sparks",
        (0.6, 0.95, -3.2), (1.2, 0.9, 0.5), (255, 200, 90), "fire",
        extra={"suspension": "sparks rise from the strike point",
               "spark_count": 14, "spark_seed": 20261112,
               "spark_lifetime": 18}))
    return elements


def _build_shophouse_street(rng, ctx):
    """A modern Vietnamese shophouse (nhà ống) street: narrow tall
    facades with awnings and vertical sign boards, kerb, lamps,
    parked motorbikes, and a foreground shopfront corner. Never
    glass towers."""
    elements = []
    colors = ctx["facade_colors"]
    awning_colors = [(178, 60, 60), (60, 110, 150), (200, 150, 50),
                     (70, 130, 80)]
    xs = [-6.8, -3.9, -0.8, 2.4, 5.6]
    for i, x in enumerate(xs):
        w = rng.uniform(2.2, 2.9)
        stories = rng.choice([3, 4, 4])
        z = -10.5 + rng.uniform(-0.6, 0.6)
        els, wall = _facade(
            f"shop{i}", rng, x, z, w, stories, colors,
            ctx["roof_color"], ctx["window_color"])
        elements.extend(els)
        height = stories * 1.5
        # Awning over the ground floor, protruding from the face.
        awn_y = 1.7
        v_c = (height - awn_y) / height
        half_v = 0.06 / height
        elements.append(_wall_band(
            f"shop{i}_awning", "awning", wall,
            0.05, v_c - half_v, 0.95, v_c + half_v, 0.7,
            awning_colors[i % len(awning_colors)], "cloth"))
        # Vertical sign board on the face; text only from data.
        elements.append(_wall_band(
            f"shop{i}_vsign", "vertical_sign", wall,
            0.80, 0.12, 0.96, 0.52, 0.08, (28, 34, 48),
            "painted_wood"))
        if ctx["sign_text"] and i == 2:
            elements[-1]["label"] = ctx["sign_text"]
    # Distant roofline silhouettes (depth cue, no windows).
    for i, x in enumerate([-10.0, -8.4, 8.8, 10.4]):
        elements.append(_el(
            f"distant{i}", "distant_roofline", "BG", "box",
            (x, 1.6, -18.0), (2.6, 3.2, 1.0), (96, 104, 122),
            "silhouette"))
    # Kerb, lamps, parked motorbikes.
    elements.append(_el("kerb", "kerb", "MG", "box", (0.0, 0.08, -1.2),
                        (16.0, 0.16, 0.6), (150, 148, 140), "stone",
                        attachment={"parent": None,
                                    "relation": "on_ground",
                                    "local_rect": None}))
    elements.extend(_lamp_post("lampL", -4.6, -2.2, "MG",
                               lit=ctx["is_night"]))
    elements.extend(_lamp_post("lampR", 4.4, -1.6, "MG",
                               lit=ctx["is_night"]))
    for j, (mx, mz) in enumerate(((-2.2, -3.2), (3.4, -2.6))):
        elements.append(_el(
            f"motorbike{j}", "motorbike", "MG", "box",
            (mx, 0.28, mz), (0.95, 0.56, 0.3), (36, 38, 44), "iron",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}))
        elements.append(_el(
            f"motorbike{j}_bar", "motorbike", "MG", "box",
            (mx + 0.3, 0.60, mz), (0.3, 0.08, 0.08), (36, 38, 44),
            "iron",
            attachment={"parent": f"motorbike{j}", "relation": "on_top",
                        "local_rect": None}))
    # Foreground: shopfront corner + hanging sign + potted shrub.
    fg_wall = _el("shopFG", "facade_wall", "FG", "box",
                  (-6.0, 1.2, 1.7), (2.2, 2.4, 0.5),
                  colors[0], "plaster")
    elements.append(fg_wall)
    elements.append(_wall_band(
        "shopFG_sign", "vertical_sign", fg_wall,
        0.55, 0.15, 0.9, 0.6, 0.08, (28, 34, 48), "painted_wood",
        layer="FG"))
    elements.extend(_bush("shrubFG", rng, 5.8, 1.9, "FG", scale=0.6,
                          leaf_color=ctx.get("leaf_color")
                          or (84, 110, 66)))
    return elements


def _build_generic_neutral(rng, ctx):
    elements = [
        _el("horizon_mass_L", "distant_mass", "BG", "box",
            (-6.0, 1.2, -16.0), (5.0, 2.4, 1.0), (140, 142, 148),
            "silhouette"),
        _el("horizon_mass_R", "distant_mass", "BG", "box",
            (6.0, 1.0, -16.0), (5.0, 2.0, 1.0), (140, 142, 148),
            "silhouette"),
        _el("ground_mark", "ground_mark", "MG", "box",
            (0.0, 0.05, -1.0), (3.0, 0.1, 0.6), (150, 148, 140),
            "stone",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None}),
    ]
    return elements


_BUILDERS = {
    "EUROPEAN_STREET_1900": _build_european_street,
    "GREEK_PALACE": _build_greek_palace,
    "MEDITERRANEAN_ISLAND": _build_mediterranean_island,
    "CAVE": _build_cave,
    "BARRACKS": _build_barracks,
    "TRENCH": _build_trench,
    "FOREST": _build_forest,
    "MODERN_CITY": _build_modern_city,
    "INTERIOR_GENERIC": _build_interior,
    "COUNTRYSIDE_ROAD": _build_countryside_road,
    "FORGE": _build_forge,
    "SHOPHOUSE_STREET": _build_shophouse_street,
    GENERIC_NEUTRAL: _build_generic_neutral,
}


# ---------------------------------------------------------------------------
# Semantic landmarks (Phase E, task 5).
#
# Landmarks come ONLY from the structured ``landmarks`` trait field
# (top-level or the V1 ``fields`` block) — never from keywords in
# free text, never invented. Each registry kind names generic
# vocabulary phrases and a builder; builders place grounded,
# attached geometry in the far background band (statues and
# furnaces in the midground band) and tag every element with the
# landmark kind so negative constraints can address them.
# ---------------------------------------------------------------------------
def _landmark_mountain_peak(prefix, x, z, rng, ctx):
    color = _blend(ctx["facade_colors"][0], (140, 160, 190), 0.5)
    return [
        _el(f"{prefix}_peak", "mountain_peak", "BG", "gable_prism",
            (x, 2.5, z), (7.0, 5.0, 2.0), color, "silhouette",
            extra={"landmark": "mountain_peak",
                   "tags": ["mountain_peak", "mountain"]}),
        _el(f"{prefix}_snow", "snow_cap", "BG", "blob",
            (x, 4.8, z), (1.8, 0.8, 1.2), (242, 244, 248), "silhouette",
            attachment={"parent": f"{prefix}_peak",
                        "relation": "overlaps", "local_rect": None},
            extra={"landmark": "mountain_peak",
                   "tags": ["mountain_peak", "snow"]}),
    ]


def _landmark_temple_front(prefix, x, z, rng, ctx):
    marble = ctx["facade_colors"][0]
    elements = []
    for i, dx in enumerate((-2.4, -0.8, 0.8, 2.4)):
        elements.extend(_column(f"{prefix}_col{i}", x + dx, z, "BG",
                                3.6, marble))
    cap_top = 0.28 + (3.6 - 0.55) + 0.28
    elements.append(_el(
        f"{prefix}_entablature", "entablature", "BG", "box",
        (x, cap_top + 0.2, z), (6.4, 0.4, 0.9), marble, "marble",
        attachment={"parent": f"{prefix}_col1_capital",
                    "relation": "on_top", "local_rect": None},
        extra={"landmark": "temple_front", "tags": ["temple_front"]}))
    elements.append(_el(
        f"{prefix}_pediment", "gable_roof", "BG", "gable_prism",
        (x, cap_top + 0.4 + 0.5, z), (6.8, 1.0, 1.0),
        ctx["roof_color"], "roof_tile",
        attachment={"parent": f"{prefix}_entablature",
                    "relation": "on_top", "local_rect": None},
        extra={"landmark": "temple_front", "tags": ["temple_front"]}))
    for el in elements:
        el["extra"].setdefault("landmark", "temple_front")
        el["extra"].setdefault("tags", ["temple_front"])
    return elements


def _landmark_city_gate(prefix, x, z, rng, ctx):
    stone = _blend(ctx["facade_colors"][0], (120, 116, 108), 0.3)
    return [
        _el(f"{prefix}_towerL", "gate_tower", "BG", "box",
            (x - 1.6, 2.2, z), (1.4, 4.4, 1.4), stone, "stone",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None},
            extra={"landmark": "city_gate", "tags": ["city_gate"]}),
        _el(f"{prefix}_towerR", "gate_tower", "BG", "box",
            (x + 1.6, 2.2, z), (1.4, 4.4, 1.4), stone, "stone",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None},
            extra={"landmark": "city_gate", "tags": ["city_gate"]}),
        _el(f"{prefix}_lintel", "gate_lintel", "BG", "box",
            (x, 4.7, z), (4.6, 0.6, 1.2), stone, "stone",
            attachment={"parent": f"{prefix}_towerL",
                        "relation": "on_top", "local_rect": None},
            extra={"landmark": "city_gate", "tags": ["city_gate"]}),
    ]


def _landmark_bridge(prefix, x, z, rng, ctx):
    stone = _blend(ctx["facade_colors"][0], (120, 116, 108), 0.3)
    return [
        _el(f"{prefix}_pier", "bridge_pier", "BG", "box",
            (x, 0.8, z), (1.0, 1.6, 1.0), stone, "stone",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None},
            extra={"landmark": "bridge", "tags": ["bridge"]}),
        _el(f"{prefix}_deck", "bridge_deck", "BG", "box",
            (x, 1.75, z), (7.0, 0.3, 1.6), stone, "stone",
            attachment={"parent": f"{prefix}_pier",
                        "relation": "on_top", "local_rect": None},
            extra={"landmark": "bridge", "tags": ["bridge"]}),
        _el(f"{prefix}_rail", "bridge_rail", "BG", "box",
            (x, 2.15, z + 0.7), (7.0, 0.5, 0.08),
            _blend(stone, (0, 0, 0), 0.2), "stone",
            attachment={"parent": f"{prefix}_deck",
                        "relation": "on_top", "local_rect": None},
            extra={"landmark": "bridge", "tags": ["bridge"]}),
    ]


def _landmark_tower(prefix, x, z, rng, ctx):
    stone = _blend(ctx["facade_colors"][0], (120, 116, 108), 0.3)
    return [
        _el(f"{prefix}_shaft", "tower", "BG", "box",
            (x, 3.5, z), (1.8, 7.0, 1.8), stone, "stone",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None},
            extra={"landmark": "tower", "tags": ["tower"]}),
        _el(f"{prefix}_cap", "tower_cap", "BG", "box",
            (x, 7.2, z), (2.2, 0.4, 2.2), ctx["roof_color"],
            "roof_tile",
            attachment={"parent": f"{prefix}_shaft",
                        "relation": "on_top", "local_rect": None},
            extra={"landmark": "tower", "tags": ["tower"]}),
    ]


def _landmark_statue(prefix, x, z, rng, ctx):
    stone = ctx["facade_colors"][0]
    return [
        _el(f"{prefix}_pedestal", "statue_pedestal", "MG", "box",
            (x, 0.5, z), (1.0, 1.0, 1.0), stone, "stone",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None},
            extra={"landmark": "statue", "tags": ["statue"]}),
        _el(f"{prefix}_figure", "statue", "MG", "blob",
            (x, 1.9, z), (0.9, 1.8, 0.9),
            _blend(stone, (0, 0, 0), 0.08), "stone",
            attachment={"parent": f"{prefix}_pedestal",
                        "relation": "on_top", "local_rect": None},
            extra={"landmark": "statue", "tags": ["statue"]}),
    ]


def _landmark_waterfall(prefix, x, z, rng, ctx):
    rock = _blend(ctx["facade_colors"][0], (90, 88, 84), 0.4)
    return [
        _el(f"{prefix}_cliff", "cliff", "BG", "box",
            (x, 2.5, z), (4.0, 5.0, 1.2), rock, "rock",
            extra={"landmark": "waterfall", "tags": ["waterfall"]}),
        _el(f"{prefix}_falls", "waterfall", "BG", "blob",
            (x, 2.2, z + 0.7), (1.1, 4.2, 0.3), (190, 210, 226),
            "water",
            attachment={"parent": f"{prefix}_cliff",
                        "relation": "overlaps", "local_rect": None},
            extra={"landmark": "waterfall", "tags": ["waterfall"]}),
        _el(f"{prefix}_foam", "foam", "BG", "blob",
            (x, 0.15, z + 0.7), (1.6, 0.3, 0.8), (232, 240, 246),
            "water",
            extra={"landmark": "waterfall", "tags": ["waterfall"]}),
    ]


def _landmark_lighthouse(prefix, x, z, rng, ctx):
    white = (240, 238, 230)
    return [
        _el(f"{prefix}_shaft", "lighthouse", "BG", "box",
            (x, 3.0, z), (1.4, 6.0, 1.4), white, "plaster",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None},
            extra={"landmark": "lighthouse", "tags": ["lighthouse"]}),
        _el(f"{prefix}_lamp_room", "lamp_room", "BG", "box",
            (x, 6.3, z), (1.0, 0.6, 1.0), (52, 54, 58), "glass",
            attachment={"parent": f"{prefix}_shaft",
                        "relation": "on_top", "local_rect": None},
            extra={"landmark": "lighthouse", "tags": ["lighthouse"]}),
        _el(f"{prefix}_lamp_glow", "lamp_glow", "BG", "blob",
            (x, 6.85, z), (0.7, 0.5, 0.7), (255, 220, 140), "glass",
            attachment={"parent": f"{prefix}_lamp_room",
                        "relation": "on_top", "local_rect": None},
            extra={"landmark": "lighthouse", "tags": ["lighthouse"]}),
    ]


def _landmark_furnace(prefix, x, z, rng, ctx):
    dark = _blend(ctx["facade_colors"][0], (0, 0, 0), 0.35)
    return [
        _el(f"{prefix}_furnace", "furnace", "MG", "box",
            (x, 0.9, z), (2.0, 1.8, 1.2), dark, "stone",
            attachment={"parent": None, "relation": "on_ground",
                        "local_rect": None},
            extra={"landmark": "furnace", "tags": ["furnace"]}),
        _el(f"{prefix}_fire", "fire", "MG", "blob",
            (x, 1.0, z + 0.65), (0.9, 0.7, 0.3), (255, 140, 40),
            "fire",
            attachment={"parent": f"{prefix}_furnace",
                        "relation": "overlaps", "local_rect": None},
            extra={"landmark": "furnace", "tags": ["furnace"]}),
    ]


LANDMARKS = {
    "mountain_peak": {
        "keywords": ("núi", "mountain", "peak", "đỉnh", "núi cao",
                     "dãy núi", "núi xa"),
        "builder": _landmark_mountain_peak, "band": "BG",
    },
    "temple_front": {
        "keywords": ("đền", "temple", "đền thờ", "pediment",
                     "đầu hồi", "acropolis", "mặt tiền đền"),
        "builder": _landmark_temple_front, "band": "BG",
    },
    "city_gate": {
        "keywords": ("cổng thành", "city gate", "cổng", "gatehouse",
                     "cổng làng"),
        "builder": _landmark_city_gate, "band": "BG",
    },
    "bridge": {
        "keywords": ("cây cầu", "chiếc cầu", "bridge", "cầu đá",
                     "cầu gỗ", "cầu treo"),
        "builder": _landmark_bridge, "band": "BG",
    },
    "tower": {
        "keywords": ("tháp", "tower", "tháp canh", "watchtower",
                     "tháp chuông"),
        "builder": _landmark_tower, "band": "BG",
    },
    "statue": {
        "keywords": ("tượng", "statue", "tượng đá", "tượng đài",
                     "bức tượng"),
        "builder": _landmark_statue, "band": "MG",
    },
    "waterfall": {
        "keywords": ("thác nước", "waterfall", "thác", "cascade"),
        "builder": _landmark_waterfall, "band": "BG",
    },
    "lighthouse": {
        "keywords": ("hải đăng", "lighthouse", "ngọn hải đăng"),
        "builder": _landmark_lighthouse, "band": "BG",
    },
    "furnace": {
        "keywords": ("lò lửa", "furnace", "lò nung", "lò rèn"),
        "builder": _landmark_furnace, "band": "MG",
    },
}

_LANDMARK_ORDER = tuple(LANDMARKS.keys())

# Far-band / mid-band staging slots for landmarks (world x/z).
_LANDMARK_SLOTS_BG = [(-7.0, -18.0), (0.5, -20.0), (7.5, -18.0),
                      (-3.5, -19.0), (3.5, -19.0)]
_LANDMARK_SLOTS_MG = [(-5.5, -7.0), (5.5, -7.0), (0.0, -8.5)]


def _landmark_field_texts(traits: dict) -> list[str]:
    """Landmark declarations: the ``landmarks`` field only."""
    texts = _field_values(traits.get("landmarks"))
    fields = traits.get("fields")
    if isinstance(fields, dict):
        for key, value in fields.items():
            if str(key).upper() == "LANDMARKS":
                texts.extend(_field_values(value))
    return texts


def select_landmarks(location_traits: dict) -> list[str]:
    """Landmark kinds declared by the ``landmarks`` trait field.

    Registry order, deduplicated. An empty landmarks field yields
    no landmarks — the engine never invents them."""
    texts = _landmark_field_texts(location_traits or {})
    if not texts:
        return []
    joined = " ".join(texts)
    return [kind for kind in _LANDMARK_ORDER
            if any(kw in joined for kw in LANDMARKS[kind]["keywords"])]


def build_landmarks(location_traits: dict, rng, ctx) -> list[dict]:
    """Landmark elements for the declared landmark kinds."""
    kinds = select_landmarks(location_traits or {})
    elements = []
    bg_i = mg_i = 0
    for kind in kinds:
        spec = LANDMARKS[kind]
        if spec["band"] == "MG":
            x, z = _LANDMARK_SLOTS_MG[mg_i % len(_LANDMARK_SLOTS_MG)]
            mg_i += 1
        else:
            x, z = _LANDMARK_SLOTS_BG[bg_i % len(_LANDMARK_SLOTS_BG)]
            bg_i += 1
        elements.extend(spec["builder"](f"lm_{kind}", x, z, rng, ctx))
    return elements


# ---------------------------------------------------------------------------
# Negative constraints (Phase E, task 5).
#
# ``negative_constraints`` (or the V1 alias ``forbidden``) names what
# must NOT appear. Element-level constraints DROP matching elements
# and record every drop in provenance — never silently. Matching is
# whole-word on element kind/material tokens plus a small synonym
# map for everyday phrasing ("ô tô" -> automobile). Selection-level
# constraints ("don't substitute Vienna for Munich") match no
# element kind; they are recorded as no-match and are enforced by
# trait-driven selection itself, not by dropping.
# ---------------------------------------------------------------------------
_CONSTRAINT_SYNONYMS = {
    "ô tô": "automobile", "xe hơi": "automobile",
    "xe ô tô": "automobile", "đèn led": "led",
    "biển quảng cáo": "billboard", "nhà kính": "glass_curtain",
    "điện thoại": "smartphone", "xe tăng": "tank",
    "máy bay": "airplane", "đèn neon": "neon_sign",
}


def _field_raw_values(value) -> list[str]:
    """A trait field value -> list of strings, case PRESERVED.

    Unlike :func:`_field_values` (lowercased, for matching), this
    keeps the script's exact wording for provenance: negative
    constraints are reported verbatim so a human can trace each
    decision back to the script. Matching normalizes separately.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out.extend(_field_raw_values(v))
        return out
    if isinstance(value, dict):
        out = []
        for v in value.values():
            out.extend(_field_raw_values(v))
        return out
    return [str(value)]


def _constraint_field_texts(traits: dict) -> list[str]:
    """Negative-constraint declarations (both field names).

    Texts keep the script's exact wording; dedupe is
    case-insensitive (the same constraint often appears both
    top-level and in fields, possibly with different casing)."""
    texts = []
    for key in ("negative_constraints", "forbidden"):
        for value in _field_raw_values(traits.get(key)):
            texts.extend(p.strip() for p in value.split(";") if p.strip())
    fields = traits.get("fields")
    if isinstance(fields, dict):
        for key, value in fields.items():
            if str(key).upper() in ("NEGATIVE_CONSTRAINTS", "FORBIDDEN"):
                for v in _field_raw_values(value):
                    texts.extend(p.strip() for p in v.split(";")
                                 if p.strip())
    seen, deduped = set(), []
    for text in texts:
        key = text.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(text)
    return deduped


def _element_search_text(el: dict) -> str:
    parts = [str(el.get("kind", "")), str(el.get("material", "")),
             str(el.get("label", ""))]
    parts.extend(str(t) for t in el.get("extra", {}).get("tags", []))
    return " ".join(parts).lower()


def _constraint_matches(constraint: str, el: dict) -> str | None:
    """The token that makes ``constraint`` match ``el``, or None."""
    text = _element_search_text(el)
    tokens = set()
    for part in text.split():
        tokens.add(part)
        tokens.update(part.split("_"))
    for phrase, token in _CONSTRAINT_SYNONYMS.items():
        if phrase in constraint and token in tokens:
            return token
    for token in sorted(tokens):
        if len(token) < 3:
            continue
        if re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)",
                     constraint):
            return token
    label = str(el.get("label", "")).strip().lower()
    if label and len(constraint) >= 4 and constraint in label:
        return f"label:{label}"
    return None


def apply_negative_constraints(elements: list[dict],
                               constraints) -> tuple[list[dict], dict]:
    """Drop elements matching negative constraints.

    Returns ``(kept_elements, report)`` where the report lists every
    constraint (in its ORIGINAL wording), the elements it dropped
    (with the matched token), and constraints that matched nothing.
    Matching uses a normalized form (lowercase, trailing period
    stripped); the report keeps the original text so a human can
    trace each decision back to the script. Pure: the input list
    is never mutated."""
    if isinstance(constraints, str):
        constraints = [constraints]
    pairs = []
    for c in constraints or []:
        original = str(c).strip()
        text = original.lower().rstrip(".")
        if text:
            pairs.append((original, text))
    dropped = []
    kept = []
    for el in elements:
        hit = None
        for original, constraint in pairs:
            token = _constraint_matches(constraint, el)
            if token is not None:
                hit = (original, token)
                break
        if hit is not None:
            dropped.append({"element_id": el.get("id"),
                            "constraint": hit[0],
                            "matched": hit[1]})
        else:
            kept.append(el)
    dropped_constraints = {d["constraint"] for d in dropped}
    report = {
        "constraints": [original for original, _t in pairs],
        "dropped": dropped,
        "dropped_count": len(dropped),
        "no_match": [original for original, _t in pairs
                     if original not in dropped_constraints],
    }
    return kept, report


# ---------------------------------------------------------------------------
# Attachment validation
# ---------------------------------------------------------------------------
def _aabbs_overlap(a: dict, b: dict, eps: float = 0.05) -> bool:
    """True when two elements' AABBs intersect (``eps`` tolerance,
    so edge-touching counts: a flag touching its pole, a rail
    meeting a post)."""
    for k in range(3):
        a_lo = a["center"][k] - a["size"][k] / 2
        a_hi = a["center"][k] + a["size"][k] / 2
        b_lo = b["center"][k] - b["size"][k] / 2
        b_hi = b["center"][k] + b["size"][k] / 2
        if a_lo > b_hi + eps or b_lo > a_hi + eps:
            return False
    return True


def validate_attachments(pkg: dict) -> list[str]:
    """Recompute every attached element's position from its parent.

    Checks: parent exists; ``on_wall`` local rects inside [0,1] and
    the element centre matches the rect-derived world position;
    ``on_wall_ground`` doors reach the ground (bottom y == parent
    bottom); ``on_top`` elements sit on the parent's top face;
    ``on_ground`` elements rest on y == 0; ``overlaps`` elements
    intersect their parent's AABB (foliage lobes, rails through
    posts, branches into trunks); ``hangs_from`` elements hang
    with their top on the parent's bottom face (stalactites).
    Unknown relations are errors, never ignored.

    FLOATING GEOMETRY (P-S5): an element with NO attachment whose
    bottom sits above the ground line (0.06 tolerance) and which
    carries no recorded ``extra["suspension"]`` reason is a
    floater and is reported LOUDLY here — the same list the
    package validation already surfaces, so no floater can ship
    silently. Legitimately suspended elements (ceilings, smoke,
    overhangs, slope-stepped houses, ridge chimneys) MUST carry
    a ``suspension`` reason string saying why. Returns a list of
    error strings (empty = valid). Tolerances are 0.06 world
    units."""
    elements = {el["id"]: el for el in pkg.get("elements", [])}
    errors = []
    for el in pkg.get("elements", []):
        att = el.get("attachment")
        if not att:
            bottom = el["center"][1] - el["size"][1] / 2
            if bottom > 0.06 and not el.get("extra", {}).get("suspension"):
                errors.append(
                    f"{el['id']}: floating element (bottom y="
                    f"{bottom:.2f}) with no attachment and no "
                    f"recorded suspension reason")
            continue
        parent_id = att.get("parent")
        relation = att.get("relation")
        if parent_id is None:
            if relation == "on_ground":
                bottom = el["center"][1] - el["size"][1] / 2
                if abs(bottom) > 0.06:
                    errors.append(
                        f"{el['id']}: on_ground bottom y={bottom:.2f} != 0")
            elif relation not in ("on_ground",):
                errors.append(
                    f"{el['id']}: relation {relation!r} without a parent")
            continue
        parent = elements.get(parent_id)
        if parent is None:
            errors.append(f"{el['id']}: parent {parent_id} missing")
            continue
        if relation == "on_top":
            bottom = el["center"][1] - el["size"][1] / 2
            top = parent["center"][1] + parent["size"][1] / 2
            if abs(bottom - top) > 0.06:
                errors.append(
                    f"{el['id']}: on_top bottom {bottom:.2f} != "
                    f"parent top {top:.2f}")
        elif relation == "hangs_from":
            top = el["center"][1] + el["size"][1] / 2
            parent_bottom = parent["center"][1] - parent["size"][1] / 2
            if abs(top - parent_bottom) > 0.06:
                errors.append(
                    f"{el['id']}: hangs_from top {top:.2f} != "
                    f"parent bottom {parent_bottom:.2f}")
        elif relation == "overlaps":
            if not _aabbs_overlap(el, parent):
                errors.append(
                    f"{el['id']}: overlaps parent {parent_id} but "
                    f"AABBs do not intersect")
        elif relation in ("on_wall", "on_wall_ground"):
            rect = att.get("local_rect")
            if not rect or len(rect) != 4:
                errors.append(f"{el['id']}: on_wall without local_rect")
                continue
            u0, v0, u1, v1 = (float(v) for v in rect)
            if not (0.0 <= u0 < u1 <= 1.0 and 0.0 <= v0 < v1 <= 1.0):
                errors.append(
                    f"{el['id']}: local_rect {rect} outside wall [0,1]")
                continue
            pw, ph = parent["size"][0], parent["size"][1]
            px, py, pz = parent["center"]
            top = py + ph / 2
            exp_x = px + ((u0 + u1) / 2 - 0.5) * pw
            exp_y = top - (v0 + v1) / 2 * ph
            exp_z = pz + parent["size"][2] / 2 + el["size"][2] / 2 + 0.02
            cx, cy, cz = el["center"]
            if abs(cx - exp_x) > 0.06 or abs(cy - exp_y) > 0.06:
                errors.append(
                    f"{el['id']}: centre ({cx:.2f},{cy:.2f}) != "
                    f"rect-derived ({exp_x:.2f},{exp_y:.2f})")
            if abs(cz - exp_z) > 0.12:
                errors.append(
                    f"{el['id']}: z {cz:.2f} not on parent face "
                    f"{exp_z:.2f}")
            if relation == "on_wall_ground":
                # A door reaches the ground its parent stands on: the
                # parent's bottom face (0 on flat ground, higher for
                # a house stepped up a slope).
                bottom = cy - el["size"][1] / 2
                parent_bottom = py - ph / 2
                if abs(bottom - parent_bottom) > 0.06:
                    errors.append(
                        f"{el['id']}: door bottom y={bottom:.2f} != "
                        f"parent bottom {parent_bottom:.2f}")
        else:
            errors.append(
                f"{el['id']}: unknown attachment relation "
                f"{relation!r}")
    return errors


# ---------------------------------------------------------------------------
# Package construction
# ---------------------------------------------------------------------------
def _seed_for(traits: dict, period, time_of_day: str) -> int:
    canonical = json.dumps({"traits": traits, "period": str(period),
                            "tod": time_of_day}, sort_keys=True,
                           ensure_ascii=False, default=str)
    return int(hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8],
               16)


def build_environment(location_traits: dict, period: str = "",
                      time_of_day: str = "day", style: dict | None = None
                      ) -> dict:
    """Build an EnvironmentPackage from location trait data.

    Returns ``{archetype, layers, elements, palette, light,
    point_lights, provenance, validation, period_errors,
    ground}``. ``point_lights`` is the archetype's declared
    JSON-safe point-light specs (empty for archetypes without
    lights); the renderer turns them into a LightRig, and the
    Motion Canvas emitter may consume the same specs (ATLAS
    wiring). ``layers``
    maps FG/MG/BG to element-id lists in draw order. Map-type
    traits return a ``map_deferred`` package (no elements) — the
    caller must use map_renderer. Never raises on trait data: an
    empty/unknown trait block yields GENERIC_NEUTRAL."""
    traits = dict(location_traits or {})
    style = dict(style or {})
    detail = _select_archetype_detail(traits)
    archetype_id, score, hits = (detail["archetype"], detail["score"],
                                 detail["hits"])
    if archetype_id == "MAP":
        return {"archetype": "MAP", "kind": "map_deferred",
                "layers": {"FG": [], "MG": [], "BG": []}, "elements": [],
                "palette": {}, "light": {}, "point_lights": [],
                "ground": {},
                "provenance": {"trait_source": traits.get("id") or
                               traits.get("location_id") or "anonymous",
                               "archetype": "MAP",
                               "matched_keywords": [],
                               "selection_fields": [],
                               "location_keyword":
                                   detail["location_keyword"],
                               "location_keyword_ignored": False,
                               "location_keyword_only": False,
                               "landmarks": [],
                               "landmark_elements": [],
                               "negative_constraints": [],
                               "negative_constraints_applied": [],
                               "negative_constraints_no_match": [],
                               "note": "map location — use map_renderer"},
                "validation": [], "period_errors": []}
    period_value = period or traits.get("period") or ""
    tod = time_of_day or "day"
    seed = style.get("seed", _seed_for(traits, period_value, tod))
    rng = random.Random(seed)
    spec = ARCHETYPES.get(archetype_id)
    if spec is None:
        spec = {"facade_colors": [(170, 168, 164)],
                "roof_color": (120, 118, 114),
                "ground_color": (130, 126, 120),
                "ground_kind": "neutral",
                "period_range": (None, None)}
    # Trait palette tints the archetype colours (30% blend).
    palette_words = traits.get("palette") or traits.get("color_palette") or []
    if isinstance(palette_words, str):
        palette_words = [p.strip() for p in palette_words.split(",")]
    trait_colors = [_parse_color_name(p) for p in palette_words]
    trait_colors = [c for c in trait_colors if c is not None]
    facade_colors = list(spec["facade_colors"])
    if trait_colors:
        tint = trait_colors[0]
        facade_colors = [_blend(c, tint, 0.3) for c in facade_colors]
    # Trait-led vegetation palette (P-S3): a green-dominant trait
    # colour becomes the generic leaf colour; specific foliage
    # (olives) keeps its own colour.
    leaf_color = next((c for c in trait_colors
                       if c[1] > c[0] and c[1] > c[2]), None)
    mood = style.get("mood") or (traits.get("render_traits") or {}).get(
        "mood") or "warm"
    weather = traits.get("weather") or ""
    light = light_for(tod, mood, weather)
    for key, value in (spec.get("light_override") or {}).items():
        light[key] = value
    is_night = light["time_of_day"] == "night"
    window_color = (255, 200, 90) if is_night else (52, 66, 88)
    sign_text = ""
    for key in ("sign_text", "signage", "shop_sign", "shop_name"):
        if isinstance(traits.get(key), str) and traits[key].strip():
            sign_text = traits[key].strip()
            break
        if isinstance(style.get(key), str) and style[key].strip():
            sign_text = style[key].strip()
            break
    ctx = {"facade_colors": facade_colors,
           "roof_color": spec["roof_color"],
           "window_color": window_color, "is_night": is_night,
           "sign_text": sign_text, "leaf_color": leaf_color,
           "trait_text": _trait_text(traits)}
    builder = _BUILDERS[archetype_id]
    elements = builder(rng, ctx)
    # Declared landmarks (structured field only, never invented).
    landmark_kinds = select_landmarks(traits)
    landmark_elements = build_landmarks(traits, rng, ctx)
    elements.extend(landmark_elements)
    # Caller-supplied extra elements (validated, never trusted).
    for extra in style.get("extra_elements") or []:
        if isinstance(extra, dict) and "id" in extra and "kind" in extra:
            elements.append(extra)
    # Negative constraints drop matching elements, loudly reported.
    constraint_texts = _constraint_field_texts(traits)
    elements, constraint_report = apply_negative_constraints(
        elements, constraint_texts)
    layers = {"FG": [e["id"] for e in elements if e["layer"] == "FG"],
              "MG": [e["id"] for e in elements if e["layer"] == "MG"],
              "BG": [e["id"] for e in elements if e["layer"] == "BG"]}
    pkg = {"archetype": archetype_id, "kind": "environment",
           "layers": layers, "elements": elements,
           "palette": {"facade": facade_colors,
                       "roof": spec["roof_color"],
                       "ground": spec["ground_color"],
                       "trait_colors": trait_colors},
           "light": light,
           "point_lights": [dict(pl) for pl in
                            (spec.get("point_lights") or [])],
           "ground": {"kind": spec["ground_kind"],
                      "color": spec["ground_color"]},
           "provenance": {"trait_source": traits.get("id") or
                          traits.get("location_id") or "anonymous",
                          "archetype": archetype_id,
                          "matched_keywords": hits,
                          "match_score": score, "seed": seed,
                          "selection_fields": detail["fields_used"],
                          "location_keyword":
                              detail["location_keyword"],
                          "location_keyword_ignored":
                              detail["location_keyword_ignored"],
                          "location_keyword_only":
                              detail["location_keyword_only"],
                          "landmarks": landmark_kinds,
                          "landmark_elements":
                              [e["id"] for e in landmark_elements],
                          "negative_constraints":
                              constraint_report["constraints"],
                          "negative_constraints_applied":
                              constraint_report["dropped"],
                          "negative_constraints_no_match":
                              constraint_report["no_match"],
                          "fallback": archetype_id == GENERIC_NEUTRAL},
           "validation": [], "period_errors": []}
    pkg["validation"] = validate_attachments(pkg)
    period_errors = validate_period(elements, period_value)
    lo, hi = spec["period_range"]
    year = parse_period_year(period_value)
    if year is not None:
        if lo is not None and year < lo:
            period_errors.append(
                f"archetype {archetype_id} period range starts {lo}, "
                f"requested {year}")
        if hi is not None and year > hi:
            period_errors.append(
                f"archetype {archetype_id} period range ends {hi}, "
                f"requested {year}")
    pkg["period_errors"] = period_errors
    return pkg


def to_box_dicts(pkg: dict) -> list[dict]:
    """Box-geometry elements -> Box3D kwargs for product_renderer.

    ATLAS wiring: ``[Box3D(**d) for d in to_box_dicts(pkg)]``.
    Non-box geometries (gable prisms, blobs) are NOT convertible and
    are excluded — the 2D renderer draws them via render_environment
    or the Motion Canvas path consumes the package directly."""
    out = []
    for el in pkg.get("elements", []):
        if el.get("geometry") != "box":
            continue
        out.append({"center": tuple(el["center"]), "size": tuple(el["size"]),
                    "color": tuple(el["color"]), "name": el["id"],
                    "label": el.get("label", "")})
    return out


# ---------------------------------------------------------------------------
# Rendering (2D projection proof renderer)
# ---------------------------------------------------------------------------
_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
)


def _load_font(size: int):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _horizon_y(camera, width: int, height: int) -> float:
    ys = []
    for c in ((-25.0, 0.0, -25.0), (25.0, 0.0, -25.0)):
        _, y, _, vis = camera.project(c, width, height)
        if vis:
            ys.append(y)
    if not ys:
        return 0.0
    return min(max(min(ys), 0.0), float(height))


def _draw_label_on_face(draw, quad, text):
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w < 8 or h < 8 or not text:
        return
    size = max(10, int(h * 0.55))
    font = _load_font(size)
    while size > 10:
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= w * 0.92:
            break
        size -= 2
        font = _load_font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (x0 + x1) / 2 - tw / 2 - bbox[0]
    ty = (y0 + y1) / 2 - th / 2 - bbox[1]
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((tx + dx, ty + dy), text, font=font, fill=(20, 20, 20))
    draw.text((tx, ty), text, font=font, fill=(255, 210, 0))


def _box_faces(camera, center, size, width, height):
    """Projected visible faces: [(depth, pts, normal, centre)]."""
    cx, cy, cz = center
    sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
    corners = [(cx + dx, cy + dy, cz + dz)
               for dx in (-sx, sx) for dy in (-sy, sy) for dz in (-sz, sz)]
    proj = [camera.project(c, width, height) for c in corners]
    faces = []
    for idxs, normal in BOX_FACES:
        if normal == (0.0, -1.0, 0.0):
            continue
        to_cam = (camera.position[0] - cx, camera.position[1] - cy,
                  camera.position[2] - cz)
        if (normal[0] * to_cam[0] + normal[1] * to_cam[1]
                + normal[2] * to_cam[2]) <= 0:
            continue
        pts, ok = [], True
        for i in idxs:
            x, y, _, vis = proj[i]
            if not vis:
                ok = False
                break
            pts.append((x, y))
        if not ok:
            continue
        depth = sum(camera.depth_of(corners[i]) for i in idxs) / len(idxs)
        centre = tuple(sum(corners[i][k] for i in idxs) / len(idxs)
                       for k in range(3))
        faces.append((depth, pts, normal, centre))
    return faces


def _element_seed(el: dict) -> int:
    """Deterministic texture seed from the element id (stable across
    processes, unlike ``hash()``). Same element -> same texture in
    every shot and every run; distinct elements differ."""
    key = el.get("id") or str((el.get("center"), el.get("size")))
    return int.from_bytes(hashlib.sha256(str(key).encode()).digest()[:4],
                          "big")


def _face_texture(el: dict, normal, pts, wm: float, hm: float):
    """Texture for one projected face, or None when the face keeps
    the flat fill (unmapped material, or too small on screen for
    texture detail to read). ``pts`` are the projected quad points;
    ``wm``/``hm`` the face's world size in metres."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if max(xs) - min(xs) < MIN_FACE_PX or max(ys) - min(ys) < MIN_FACE_PX:
        return None
    return texture_for_material(el.get("material", ""), el["color"],
                                wm, hm, _element_seed(el))


def _draw_box_element(img, draw, el, camera, rig, width, height,
                      textures=True):
    faces = _box_faces(camera, el["center"], el["size"], width, height)
    front_pts = None
    for depth, pts, normal, centre in sorted(faces, key=lambda f: -f[0]):
        colour = shade_with_points(el["color"], rig, centre, normal)
        outline = tuple(int(c * 0.6) for c in colour)
        tex = None
        if textures:
            # Face world size follows the dominant normal axis.
            ax = max(range(3), key=lambda k: abs(normal[k]))
            size = el["size"]
            wm, hm = ((size[0], size[1]) if ax == 2 else
                      (size[2], size[1]) if ax == 0 else
                      (size[0], size[2]))
            tex = _face_texture(el, normal, pts, wm, hm)
        if tex is not None:
            # Tinted-texture path (B2): neutral ambient+key factor
            # plus the per-channel point-light gain, so a blue
            # pulse cools a stone wall instead of only brightening
            # it. With no point lights the gain is unit and the
            # factor equals the old total irradiance — identical.
            key_irr = (rig.key.irradiance(centre, normal)
                       if rig.key else 0.0)
            neutral = float(rig.ambient) + float(key_irr)
            paste_textured_quad(
                img, pts, tex, neutral,
                point_light_gain(rig, centre, normal))
            draw.polygon(pts, outline=outline)
        else:
            draw.polygon(pts, fill=colour, outline=outline)
        if normal == (0.0, 0.0, 1.0):
            front_pts = pts
    if el.get("label") and front_pts:
        _draw_label_on_face(draw, front_pts, el["label"])


def _draw_gable_prism(img, draw, el, camera, rig, width, height,
                      textures=True):
    """A gable roof: front triangle + two slope quads. ``extra``
    ``inverted`` draws it hanging (stalactite). Roof-tile slopes
    get the painted roof texture (v = eave -> apex); the gable
    triangle keeps the flat fill."""
    cx, cy, cz = el["center"]
    sx, sy, sz = el["size"][0] / 2, el["size"][1] / 2, el["size"][2] / 2
    inverted = bool(el.get("extra", {}).get("inverted"))
    if inverted:
        apex_y, base_y = cy - sy, cy + sy
    else:
        apex_y, base_y = cy + sy, cy - sy
    # Cross-section triangle in the x/y plane, extruded along z.
    tri_front = [(cx - sx, base_y, cz + sz), (cx + sx, base_y, cz + sz),
                 (cx, apex_y, cz + sz)]
    tri_back = [(cx - sx, base_y, cz - sz), (cx + sx, base_y, cz - sz),
                (cx, apex_y, cz - sz)]
    quads = [
        ([tri_front[0], tri_front[2], tri_back[2], tri_back[0]],
         (-0.7, 0.7, 0.0) if not inverted else (-0.7, -0.7, 0.0)),
        ([tri_front[1], tri_back[1], tri_back[2], tri_front[2]],
         (0.7, 0.7, 0.0) if not inverted else (0.7, -0.7, 0.0)),
    ]
    faces = []
    for pts3, normal in quads:
        pts, ok = [], True
        for p in pts3:
            x, y, _, vis = camera.project(p, width, height)
            if not vis:
                ok = False
                break
            pts.append((x, y))
        if ok:
            depth = sum(camera.depth_of(p) for p in pts3) / len(pts3)
            centre = tuple(sum(p[k] for p in pts3) / len(pts3)
                           for k in range(3))
            faces.append((depth, pts, normal, centre))
    pts, ok = [], True
    for p in tri_front:
        x, y, _, vis = camera.project(p, width, height)
        if not vis:
            ok = False
            break
        pts.append((x, y))
    if ok:
        depth = sum(camera.depth_of(p) for p in tri_front) / 3
        centre = tuple(sum(p[k] for p in tri_front) / 3 for k in range(3))
        faces.append((depth, pts, (0.0, 0.0, 1.0), centre))
    for depth, pts, normal, centre in sorted(faces, key=lambda f: -f[0]):
        n = math.sqrt(sum(v * v for v in normal)) or 1.0
        unit = tuple(v / n for v in normal)
        colour = shade_with_points(el["color"], rig, centre, unit)
        outline = tuple(int(c * 0.6) for c in colour)
        tex = None
        if textures and abs(normal[0]) > 0.5:
            # Slope quad (not the gable triangle): slope length x depth.
            slope_len = math.hypot(sx, sy)
            tex = _face_texture(el, normal, pts, slope_len, 2 * sz)
        if tex is not None:
            # Tinted-texture path (B2): see _draw_box_element.
            key_irr = (rig.key.irradiance(centre, unit)
                       if rig.key else 0.0)
            neutral = float(rig.ambient) + float(key_irr)
            paste_textured_quad(
                img, pts, tex, neutral,
                point_light_gain(rig, centre, unit))
            draw.polygon(pts, outline=outline)
        else:
            draw.polygon(pts, fill=colour, outline=outline)


def _draw_blob(img, draw, el, camera, rig, width, height):
    x, y, scale, vis = camera.project(el["center"], width, height)
    if not vis:
        return
    rx = el["size"][0] / 2 * scale
    ry = el["size"][1] / 2 * scale
    if rx < 1 or ry < 1:
        return
    colour = shade_with_points(el["color"], rig, el["center"],
                               (0.0, 0.0, 1.0))
    outline = tuple(int(c * 0.6) for c in colour)
    draw.ellipse([x - rx, y - ry, x + rx, y + ry], fill=colour,
                 outline=outline)


# Controlled sparks (B2): a fixed-count, seeded, bounded spark
# field over a strike point. Every spark is a pure function of
# (seed, index, frame): no randomness at draw time, no state
# carried between frames, so the same frame index always renders
# the same sparks and the field can be re-measured exactly.
# "Controlled" means: the count is fixed by the element, every
# spark stays inside a documented envelope, sparks are born and
# die on a fixed lifetime (no accumulation), and the field is
# ambient forge activity — strike-synchronized bursts belong to
# ATLAS's action-driven wiring, not to this element.
_SPARK_VY_MIN = 0.03    # world units per frame (upward)
_SPARK_VY_MAX = 0.07
_SPARK_VX_MAX = 0.02
_SPARK_VZ_MAX = 0.01
_SPARK_GRAVITY = 0.0012  # world units per frame^2 (downward)
_SPARK_HOT = (255, 230, 170)
_SPARK_EMBER = (255, 120, 30)


def spark_positions(el, frame: int):
    """World positions + ages of a sparks element's field at a frame.

    ``el`` is a ``geometry == "sparks"`` element; its ``extra``
    carries ``spark_count`` (default 14), ``spark_seed`` (int)
    and ``spark_lifetime`` (frames, default 18). Returns a list
    of ``(position, age_frac, velocity)`` with ``age_frac`` 0 at
    birth and 1 at death. Positions stay inside the envelope:
    x/z within the element footprint + 0.4 world units, y from
    the element bottom to ``center_y + size_y/2 + vy_max *
    lifetime``. Deterministic: same (element, frame) -> same
    list, always. ``frame`` must be a finite number >= 0.
    """
    extra = el.get("extra", {}) or {}
    count = int(extra.get("spark_count", 14))
    lifetime = int(extra.get("spark_lifetime", 18))
    seed = int(extra.get("spark_seed", 1))
    if count < 0 or lifetime <= 0:
        raise ValueError(
            f"sparks element {el.get('id')!r}: spark_count must be "
            f">= 0 and spark_lifetime > 0, got {count}/{lifetime}")
    frame_f = float(frame)
    if not math.isfinite(frame_f) or frame_f < 0:
        raise ValueError(f"spark frame must be >= 0, got {frame!r}")
    frame_i = int(math.floor(frame_f))
    cx, cy, cz = (float(v) for v in el["center"])
    sx, sy, sz = (float(v) for v in el["size"])
    out = []
    for i in range(count):
        rng = random.Random(seed * 100003 + i)
        birth = rng.randrange(lifetime)
        ox = cx + rng.uniform(-sx / 4.0, sx / 4.0)
        oz = cz + rng.uniform(-sz / 4.0, sz / 4.0)
        oy = cy - sy / 2.0
        vx = rng.uniform(-_SPARK_VX_MAX, _SPARK_VX_MAX)
        vy = rng.uniform(_SPARK_VY_MIN, _SPARK_VY_MAX)
        vz = rng.uniform(-_SPARK_VZ_MAX, _SPARK_VZ_MAX)
        age = (frame_i - birth) % lifetime
        t = float(age)
        pos = (ox + vx * t,
               oy + vy * t - 0.5 * _SPARK_GRAVITY * t * t,
               oz + vz * t)
        out.append((pos, age / lifetime, (vx, vy, vz)))
    return out


def _draw_sparks(img, draw, el, camera, rig, width, height,
                 spark_frame: int = 0):
    """Draw a sparks element: short bright streaks, unshaded.

    Sparks are emissive (they ARE light), so they draw at full
    colour with no Lambert shading. Each spark is a 2-frame
    motion streak from its position back along its velocity,
    cooling from hot white-yellow to ember orange with age.
    Streaks whose endpoints both fall outside the frame are
    skipped by the projection visibility check."""
    line_w = 2 if width >= 1280 else 1
    for pos, age_frac, vel in spark_positions(el, spark_frame):
        tail = (pos[0] - vel[0] * 2.0, pos[1] - vel[1] * 2.0,
                pos[2] - vel[2] * 2.0)
        x0, y0, _, vis0 = camera.project(tail, width, height)
        x1, y1, _, vis1 = camera.project(pos, width, height)
        if not (vis0 or vis1):
            continue
        colour = tuple(
            int(round(_SPARK_HOT[ch] * (1.0 - age_frac)
                      + _SPARK_EMBER[ch] * age_frac))
            for ch in range(3))
        draw.line([(x0, y0), (x1, y1)], fill=colour, width=line_w)


# ---------------------------------------------------------------------------
# Sight-line culling + foreground composition (P-S5 / P-S12)
# ---------------------------------------------------------------------------
def _camera_basis(camera):
    """(right, up, fwd) unit vectors from position/target/up."""
    def _sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def _cross(a, b):
        return (a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    def _norm(a):
        n = math.sqrt(sum(v * v for v in a))
        if n == 0:
            raise ValueError("zero-length vector has no direction")
        return tuple(v / n for v in a)

    fwd = _norm(_sub(camera.target, camera.position))
    right = _norm(_cross(fwd, camera.up))
    return right, _cross(right, fwd), fwd


def sight_lines_for_camera(camera, size=(1920, 1080), targets=None):
    """One ray set per shot (P-S5).

    Cameras are FIXED within a shot, so the sight lines collapse to
    a single set computed once per shot and reused for every frame.
    ``targets`` is either a list of world points (one ray per
    point, same order — for subject occlusion tests) or a list of
    ``(nx, ny)`` normalized screen pairs in [-1, 1] (rays through
    those frame points). Default: 5 rays through the frame centre
    and the four (+/-1/3, +/-1/3) points. Returns a list of
    ``(origin, direction)`` tuples with unit directions."""
    origin = tuple(float(v) for v in camera.position)
    right, up, fwd = _camera_basis(camera)
    tan_half = math.tan(math.radians(camera.fov_deg) / 2.0)
    aspect = float(size[0]) / max(1, float(size[1]))

    def _ray_through_ndc(nx, ny):
        d = tuple(fwd[k] + right[k] * nx * tan_half * aspect
                  + up[k] * ny * tan_half for k in range(3))
        n = math.sqrt(sum(v * v for v in d))
        return (origin, tuple(v / n for v in d))

    if targets is None:
        targets = [(0.0, 0.0), (-1.0 / 3, 1.0 / 3), (1.0 / 3, 1.0 / 3),
                   (-1.0 / 3, -1.0 / 3), (1.0 / 3, -1.0 / 3)]
        return [_ray_through_ndc(nx, ny) for nx, ny in targets]
    rays = []
    for t in targets:
        if len(t) == 3:
            d = tuple(float(t[k]) - origin[k] for k in range(3))
            n = math.sqrt(sum(v * v for v in d))
            if n == 0:
                continue
            rays.append((origin, tuple(v / n for v in d)))
        else:
            rays.append(_ray_through_ndc(float(t[0]), float(t[1])))
    return rays


def ray_aabb_intersect(origin, direction, center, size):
    """Slab test: distance from ``origin`` to the AABB entry point,
    or None when the ray misses (or starts inside, returning 0.0
    only when the origin is outside and the box is ahead)."""
    tmin, tmax = 0.0, float("inf")
    for k in range(3):
        lo = center[k] - size[k] / 2
        hi = center[k] + size[k] / 2
        d = direction[k]
        if abs(d) < 1e-12:
            if origin[k] < lo or origin[k] > hi:
                return None
            continue
        t1 = (lo - origin[k]) / d
        t2 = (hi - origin[k]) / d
        if t1 > t2:
            t1, t2 = t2, t1
        tmin = max(tmin, t1)
        tmax = min(tmax, t2)
        if tmin > tmax:
            return None
    return tmin


def sightline_occlusion(pkg: dict, rays, subject_points):
    """Which environment elements block the sight lines to subjects.

    ``rays`` is the one-per-shot set from
    :func:`sight_lines_for_camera` with ``targets=subject_points``
    (same order). An element OCCLUDES subject ``i`` when the ray
    hits its AABB strictly before the subject depth. Returns a
    report: per-subject occluder ids in depth order, and the
    subjects with a clear line. Nothing is removed — occlusion is
    reported for the planner/QA to act on (an FG occluder over a
    subject is a P-S12 defect; a BG wall behind the subject is
    not, because the ray reaches the subject first)."""
    elements = list(pkg.get("elements", []))
    report = {"subjects": [], "occluded_subjects": [],
              "clear_subjects": []}
    for i, point in enumerate(subject_points or []):
        if i >= len(rays):
            break
        origin, direction = rays[i]
        subj_dist = math.dist(origin, point)
        occluders = []
        for el in elements:
            t = ray_aabb_intersect(origin, direction, el["center"],
                                   el["size"])
            if t is not None and t < subj_dist - 0.05:
                occluders.append((round(t, 3), el["id"]))
        occluders.sort()
        entry = {"subject_index": i,
                 "subject_point": [round(float(v), 3) for v in point],
                 "occluders": [el_id for _t, el_id in occluders],
                 "occluded": bool(occluders)}
        report["subjects"].append(entry)
        if occluders:
            report["occluded_subjects"].append(i)
        else:
            report["clear_subjects"].append(i)
    return report


def _segments_intersect(p1, p2, p3, p4) -> bool:
    """True when segments p1-p2 and p3-p4 intersect (2D)."""
    def _orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if v > 0:
            return 1
        if v < 0:
            return -1
        return 0

    def _on_segment(a, b, c):
        return (min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
                and min(a[1], c[1]) <= b[1] <= max(a[1], c[1]))

    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return ((d1 == 0 and _on_segment(p3, p1, p4))
            or (d2 == 0 and _on_segment(p3, p2, p4))
            or (d3 == 0 and _on_segment(p1, p3, p2))
            or (d4 == 0 and _on_segment(p1, p4, p2)))


def frustum_cull(pkg: dict, camera, size=(1920, 1080), margin_px=8):
    """(kept_ids, culled_ids, report): elements fully outside the
    frustum, computed from ONE camera (fixed within a shot).

    An element is culled only when ALL of its AABB corners project
    behind the camera, or when (all corners in front) no corner
    lands in the frame and no projected AABB edge crosses the
    frame rectangle — the edge test matters for long elements
    (kerbs, rails, walls) whose corners are all off-frame while
    their middle spans the frame. A box straddling the near plane
    (some corners behind) is always kept: its projection is
    unbounded. The report lists every culled id and why
    (``behind_camera`` / ``off_frame``); culling is never silent.
    Callers pass ``culled_ids`` as ``exclude_ids`` to
    :func:`render_environment` to skip them. Note: an off-frame
    element can still cast a shadow into the frame, so excluding
    culled ids may change pixels where a shadow falls — the
    shadow is a real effect of the element, not a cull error."""
    width, height = int(size[0]), int(size[1])
    rect = [(-margin_px, -margin_px), (width + margin_px, -margin_px),
            (width + margin_px, height + margin_px),
            (-margin_px, height + margin_px)]
    rect_edges = [(rect[i], rect[(i + 1) % 4]) for i in range(4)]

    def _in_rect(p):
        return (-margin_px <= p[0] <= width + margin_px
                and -margin_px <= p[1] <= height + margin_px)

    kept, culled, reasons = [], [], {}
    for el in pkg.get("elements", []):
        cx, cy, cz = el["center"]
        sx, sy, sz = (el["size"][0] / 2, el["size"][1] / 2,
                      el["size"][2] / 2)
        corners = []
        any_behind = False
        for dx in (-sx, sx):
            for dy in (-sy, sy):
                for dz in (-sz, sz):
                    x, y, _s, vis = camera.project(
                        (cx + dx, cy + dy, cz + dz), width, height)
                    if not vis:
                        any_behind = True
                    else:
                        corners.append((x, y))
        if not corners:
            culled.append(el["id"])
            reasons[el["id"]] = "behind_camera"
            continue
        if any_behind:
            kept.append(el["id"])  # straddles the near plane: keep
            continue
        # 12 AABB edges over the 8 corners, in (-,+) x/y/z order.
        idx = [(0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1),
               (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)]
        pos = {key: corners[i] for i, key in enumerate(idx)}
        visible = any(_in_rect(p) for p in corners)
        if not visible:
            for a_key in idx:
                for k in range(3):
                    b_key = list(a_key)
                    b_key[k] = 1 - b_key[k]
                    b_key = tuple(b_key)
                    if a_key < b_key:
                        seg = (pos[a_key], pos[b_key])
                        if any(_segments_intersect(
                                seg[0], seg[1], e0, e1)
                                for e0, e1 in rect_edges):
                            visible = True
                            break
                if visible:
                    break
        if visible:
            kept.append(el["id"])
        else:
            culled.append(el["id"])
            reasons[el["id"]] = "off_frame"
    return kept, culled, {"culled": reasons,
                          "kept_count": len(kept),
                          "culled_count": len(culled)}


def _projected_bbox(el: dict, camera, width: int, height: int):
    """Screen bbox (x0, y0, x1, y1) of an element's AABB corners,
    or None when every corner is behind the camera."""
    cx, cy, cz = el["center"]
    sx, sy, sz = (el["size"][0] / 2, el["size"][1] / 2,
                  el["size"][2] / 2)
    pts = []
    for dx in (-sx, sx):
        for dy in (-sy, sy):
            for dz in (-sz, sz):
                x, y, _s, vis = camera.project(
                    (cx + dx, cy + dy, cz + dz), width, height)
                if vis:
                    pts.append((x, y))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def validate_fg_composition(pkg: dict, camera, size=(1920, 1080),
                            subject_boxes=None) -> dict:
    """P-S12 foreground composition validation.

    ``subject_boxes`` is a list of screen rects ``(x0, y0, x1, y1)``
    for the subjects' STANDING boxes (the F2 rule: framing is
    anchored to the standing extent, never the live pose). Rules:

    * an FG element fully off-frame is an ERROR — its occlusion
      never appears (the W2 frustum-fit defect class);
    * an FG element overlapping a subject standing box is an
      ERROR — foreground must frame the subject, never cover it
      (R2 Q4: FG never overlaps the standing box);
    * an FG element covering more than 40% of the frame area is
      an ERROR — it dominates the shot instead of staging it.

    ``edge_fraction`` (the element's largest extent as a fraction
    of the frame edge it runs along) is REPORTED per element; the
    P-S12 staging band is 10-25% of one frame edge, informational
    only — outside the band is not an error by itself. Without
    ``subject_boxes`` the standing-box check is skipped and
    reported as such, never faked."""
    width, height = int(size[0]), int(size[1])
    frame_area = float(width * height)
    boxes = [tuple(float(v) for v in b) for b in (subject_boxes or [])]
    errors, warnings, elements = [], [], []
    for el in pkg.get("elements", []):
        if el.get("layer") != "FG":
            continue
        bbox = _projected_bbox(el, camera, width, height)
        if bbox is None:
            errors.append(f"FG element {el['id']} is behind the camera")
            elements.append({"id": el["id"], "in_frame": False,
                             "edge_fraction": 0.0, "area_fraction": 0.0,
                             "overlaps_standing_box": False})
            continue
        x0, y0, x1, y1 = bbox
        ix0, iy0 = max(x0, 0.0), max(y0, 0.0)
        ix1, iy1 = min(x1, float(width)), min(y1, float(height))
        in_frame = ix1 > ix0 and iy1 > iy0
        area_fraction = ((ix1 - ix0) * (iy1 - iy0) / frame_area
                         if in_frame else 0.0)
        edge_fraction = max((x1 - x0) / width, (y1 - y0) / height)
        overlaps = False
        for (sx0, sy0, sx1, sy1) in boxes:
            if ix0 < sx1 and ix1 > sx0 and iy0 < sy1 and iy1 > sy0:
                overlaps = True
                break
        if not in_frame:
            errors.append(f"FG element {el['id']} is fully off-frame "
                          f"(bbox {[round(v, 1) for v in bbox]})")
        if overlaps:
            errors.append(f"FG element {el['id']} overlaps a subject "
                          f"standing box (P-S12/F2)")
        if area_fraction > 0.40:
            errors.append(f"FG element {el['id']} covers "
                          f"{area_fraction:.0%} of the frame (>40%)")
        if in_frame and not 0.10 <= edge_fraction <= 0.25:
            warnings.append(
                f"FG element {el['id']} edge_fraction "
                f"{edge_fraction:.2f} outside the 10-25% staging band")
        elements.append({"id": el["id"], "in_frame": in_frame,
                         "edge_fraction": round(edge_fraction, 3),
                         "area_fraction": round(area_fraction, 3),
                         "overlaps_standing_box": overlaps,
                         "bbox": [round(v, 1) for v in bbox]})
    return {"errors": errors, "warnings": warnings,
            "elements": elements,
            "standing_box_check": ("checked" if boxes else
                                   "skipped: no subject boxes supplied"),
            "ok": not errors}


def _visible_half_width(camera, z: float, y: float,
                        width: int, height: int) -> float:
    """Half-width of the camera frustum (world x) at depth ``z``.

    Binary search on the projected edge: the largest |x| whose
    projection stays inside the frame. Used to keep foreground
    occluders inside the frame (see fit_foreground_to_frustum).
    """
    def _px(x):
        px, _, _, vis = camera.project((x, y, z), width, height)
        return px if vis else float("inf")

    lo, hi = 0.0, 30.0
    if _px(0.0) >= width:
        return 0.0
    for _ in range(28):
        mid = (lo + hi) / 2.0
        if _px(mid) < width:
            lo = mid
        else:
            hi = mid
    return lo


def fit_foreground_to_frustum(pkg: dict, camera, size=(1920, 1080),
                              edge: float = 0.92) -> dict:
    """Pull foreground elements inside the camera frustum (W2).

    Foreground occluders are staged in world coordinates, but the
    video cameras' frustum at the foreground plane is narrower
    than the proof camera's: B's FG staging (|x| up to 6.4) projects
    off-frame for every shot camera, so the occlusion never
    appears. This clamps FG elements' x to ``edge`` x the visible
    half-width at their own (y, z), x-only, so same-x groups (a
    lamp pole + head, a column + pediment) move together and
    attachments hold. Elements already in-frame and all non-FG
    elements are untouched. Returns a NEW package dict; the input
    is never mutated. Callers pass the WIDEST shot camera
    (establishing, eye-level) as the reference so staging is
    stable across every shot of the location. Every adjustment is
    recorded in the returned package's ``provenance["fg_fit"]``
    (moved ids + from/to x + the reference camera) — never silent.
    """
    width, height = int(size[0]), int(size[1])
    cache: dict[tuple[float, float], float] = {}

    def _half_width(y, z):
        key = (round(float(y), 2), round(float(z), 2))
        if key not in cache:
            cache[key] = _visible_half_width(camera, z, y, width, height)
        return cache[key]

    new_elements = []
    moved = []
    for el in pkg.get("elements", []):
        if el.get("layer") != "FG":
            new_elements.append(el)
            continue
        cx, cy, cz = (float(v) for v in el["center"])
        limit = _half_width(cy, cz) * edge
        if limit <= 0 or abs(cx) <= limit:
            new_elements.append(el)
            continue
        new_x = (1.0 if cx >= 0 else -1.0) * limit
        moved.append({"id": el["id"],
                      "from_x": round(cx, 3), "to_x": round(new_x, 3),
                      "y": round(cy, 3), "z": round(cz, 3)})
        moved_el = dict(el)
        moved_el["center"] = (new_x, cy, cz)
        new_elements.append(moved_el)
    out = dict(pkg)
    out["elements"] = new_elements
    # P-S12: every fit adjustment is recorded in provenance, never
    # silent. The input package (and its provenance) is not mutated.
    provenance = dict(pkg.get("provenance") or {})
    provenance["fg_fit"] = {
        "moved": moved,
        "moved_count": len(moved),
        "edge": edge,
        "reference_camera": {
            "position": [round(float(v), 3)
                         for v in camera.position],
            "target": [round(float(v), 3) for v in camera.target],
            "fov_deg": float(camera.fov_deg),
        },
        "size": [width, height],
    }
    out["provenance"] = provenance
    return out


def _draw_element(img, draw, el, camera, rig, width, height,
                  textures=True, spark_frame: int = 0):
    """Dispatch one environment element to its geometry drawer."""
    geom = el.get("geometry", "box")
    if geom == "box":
        _draw_box_element(img, draw, el, camera, rig, width, height,
                          textures)
    elif geom == "gable_prism":
        _draw_gable_prism(img, draw, el, camera, rig, width, height,
                          textures)
    elif geom == "blob":
        _draw_blob(img, draw, el, camera, rig, width, height)
    elif geom == "sparks":
        _draw_sparks(img, draw, el, camera, rig, width, height,
                     spark_frame)


# Ground-painting bands (P-S2/P-S6): z-edges of the strips the
# ground texture is painted in, near to far. Bands are narrow near
# the camera (where perspective stretches them) and wider far away.
_GROUND_BAND_EDGES = (4.0, 2.0, 0.0, -2.0, -4.0, -6.0, -8.0, -11.0,
                      -14.0, -18.0, -22.0, -26.0)
_GROUND_HALF_WIDTH = 16.0

# Ground-glow subdivision (Test F): when the rig carries point
# lights, each ground band is painted in this many strips across
# x, each strip tinted by the point-light gain at its ground
# midpoint. 8 strips over 32 world units = 4 m per strip: fine
# enough that the falloff reads as a smooth pool, coarse enough
# to stay cheap. Only used on the point-light path; the plain
# path paints each band in one quad, exactly as before.
_GROUND_GLOW_SEGMENTS = 8


def _tint_texture_slice(tex, gain):
    """A texture slice multiplied per-channel by ``gain`` (>= 1).

    Per-channel 256-entry LUTs through PIL ``point`` (no numpy
    in this codebase). Returns a new image; ``tex`` is untouched.
    A unit gain returns the slice unchanged."""
    if gain == (1.0, 1.0, 1.0):
        return tex
    rgb = tex.convert("RGB")
    bands = []
    for ch in range(3):
        g = gain[ch]
        lut = [min(255, int(round(i * g))) for i in range(256)]
        bands.append(rgb.getchannel(ch).point(lut))
    return Image.merge("RGB", bands)


def _paint_ground_band_glow(img, corners, tex, rig, z_near, z_far):
    """Paint one ground band with point-light falloff.

    The band's texture is sliced into ``_GROUND_GLOW_SEGMENTS``
    horizontal strips; each strip is pasted into its sub-quad
    tinted by the point-light gain at the strip's ground
    midpoint (normal up). Slicing the SAME texture preserves the
    pattern scale and continuity across strips — the tint varies,
    the stones do not repeat. ``corners`` follows the
    ``_paint_ground`` order: left-near, left-far, right-far,
    right-near."""
    tw, th = tex.size
    n = _GROUND_GLOW_SEGMENTS
    for j in range(n):
        t0, t1 = j / n, (j + 1) / n

        def _lerp(a, b, t):
            return (a[0] + (b[0] - a[0]) * t,
                    a[1] + (b[1] - a[1]) * t)

        strip = [_lerp(corners[0], corners[3], t0),
                 _lerp(corners[1], corners[2], t0),
                 _lerp(corners[1], corners[2], t1),
                 _lerp(corners[0], corners[3], t1)]
        mx = -_GROUND_HALF_WIDTH + (t0 + t1) / 2 * 2 * _GROUND_HALF_WIDTH
        mz = (z_near + z_far) / 2.0
        gain = point_light_gain(rig, (mx, 0.0, mz), (0.0, 1.0, 0.0))
        x0 = int(t0 * tw)
        x1 = max(x0 + 1, int(t1 * tw))
        slice_tex = _tint_texture_slice(tex.crop((x0, 0, x1, th)), gain)
        paste_textured_quad(img, strip, slice_tex, 1.0)


def _paint_ground(img, camera, width, height, horizon, ground_kind,
                  ground_color, rig=None) -> bool:
    """Paint ground-plane texture bands over the gradient fill.

    Each band gets the ground painter for ``ground_kind`` tinted
    with the gradient colour at the band's screen height, so the
    texture detail shows inside the band while the band-to-band
    progression preserves the depth cue. Bands whose corners fall
    behind the camera are skipped (the gradient shows through).
    Returns True when at least one band was painted; kinds with
    no painter (``neutral`` and unknown) return False immediately
    and keep the gradient. Deterministic: band seeds derive from
    the kind + colour.

    ``rig`` (optional): when the rig carries point lights, each
    band is painted through ``_paint_ground_band_glow`` so the
    floor shows the lights' falloff; with no point lights (or no
    rig) the output is exactly the previous single-quad path."""
    ground_dark = tuple(int(c * 0.72) for c in ground_color)
    seed_base = int.from_bytes(
        hashlib.sha256(
            f"ground:{ground_kind}:{tuple(ground_color)}".encode()
        ).digest()[:4], "big")
    painted = False
    for i in range(len(_GROUND_BAND_EDGES) - 1):
        z_near, z_far = _GROUND_BAND_EDGES[i], _GROUND_BAND_EDGES[i + 1]
        corners = []
        ok = True
        for gx, gz in ((-_GROUND_HALF_WIDTH, z_near),
                       (-_GROUND_HALF_WIDTH, z_far),
                       (_GROUND_HALF_WIDTH, z_far),
                       (_GROUND_HALF_WIDTH, z_near)):
            x, y, _, vis = camera.project((gx, 0.0, gz), width, height)
            if not vis:
                ok = False
                break
            corners.append((x, y))
        if not ok:
            continue
        y_mid = sum(p[1] for p in corners) / 4.0
        t = (y_mid - horizon) / max(1.0, height - horizon)
        t = min(1.0, max(0.0, t))
        band_color = tuple(
            int(round(ground_color[k] * (1 - t) + ground_dark[k] * t))
            for k in range(3))
        tex = ground_texture_for(ground_kind, band_color, 32.0,
                                 abs(z_near - z_far), seed_base + i)
        if tex is None:
            return False
        if rig is not None and getattr(rig, "points", None):
            _paint_ground_band_glow(img, corners, tex, rig,
                                    z_near, z_far)
        else:
            paste_textured_quad(img, corners, tex, 1.0)
        painted = True
    return painted


def render_environment(pkg: dict, camera, size=(1920, 1080),
                       draw_layers=("BG", "MG", "FG"), transparent=False,
                       textures=True, exclude_ids=None,
                       energy_glow=None, spark_frame: int = 0,
                       scoped_state=None, rain_frame: int = 0
                       ) -> Image.Image:
    """Render an EnvironmentPackage to a PIL image.

    Sky gradient + ground plane + all elements far-to-near through
    the given PerspectiveCamera, Lambert-shaded by the package
    light. Contact shadows are ratio-capped (lighting contract)
    and clipped to the ground. ``camera`` may be a PerspectiveCamera
    or a ``(position, target, fov_deg)`` tuple. This is the 2D
    proof renderer ATLAS wires for background layers; the Motion
    Canvas path consumes the package, not this image.

    ``textures=True`` (default) paints procedural surface textures
    (plaster/brick/stone/marble walls, roof tiles) onto faces large
    enough on screen for the detail to read; ``textures=False``
    reproduces the exact pre-P-S1 flat-fill behaviour (A/B proofs,
    escape hatch). Texture seeds derive from element ids, so the
    same package renders identically every run.

    W2 wiring: ``draw_layers`` restricts which layers are drawn
    (the background pass uses BG+MG; the foreground-occlusion pass
    uses FG only). ``transparent=True`` renders ONLY the requested
    layers onto a transparent RGBA canvas — no sky, ground, grid
    or shadows — for compositing over the characters (the
    foreground-occlusion layer). Shadows always cover every layer
    in the opaque pass, so foreground occluders' contact shadows
    stay under the characters, as in the Scene25D path.

    When ``textures=True`` and the ground kind has a painter, the
    ground plane is painted in texture bands tinted with the
    gradient colour, and the perspective grid lines are skipped
    (the texture carries the surface cue); kinds without a
    painter keep the gradient + grid. ``exclude_ids`` skips the
    named elements (and their shadows) entirely — the rendering
    side of :func:`frustum_cull`; nothing is culled automatically.

    Point lights (Test F): the rig is built from the package's
    ``point_lights`` specs (e.g. the FORGE forge-mouth glow) plus,
    when given, one ``energy_glow`` record. The record must be in
    WORLD space (3-element ``source_position``); a pixel-space
    record (the prop system's native shape) must first pass
    through ``lighting.pixel_glow_to_world_glow`` — passing it
    here raises loudly instead of inventing a depth (see
    :func:`lighting.validate_energy_glow`). Faces shade with the
    colored falloff and the ground shows the light pools. With
    no point lights and no ``energy_glow`` the output is exactly
    the previous behaviour.

    ``spark_frame`` (B2) is the frame index driving ``sparks``
    elements (deterministic per frame; default 0). Other
    geometries ignore it.

    ``scoped_state`` (B2, §6 isolation) is a ``ScopedState``: when
    given, the opaque pass draws the deterministic rain overlay
    ONLY if the store resolves rain for the current scene/shot
    (``rain`` key, else rain tokens in resolved ``weather``).
    ``scoped_state=None`` (default) never draws rain. ``rain_frame``
    animates the streak fall. The transparent (layer) pass never
    draws rain — for layered renders ATLAS composites
    :func:`rain_overlay` over the final frame.
    """
    width, height = int(size[0]), int(size[1])
    excluded = set(exclude_ids or ())
    if not isinstance(camera, PerspectiveCamera):
        position, target, fov = camera
        camera = PerspectiveCamera(position=position, target=target,
                                   fov_deg=fov, aspect=width / height)
    light = pkg.get("light") or light_for("day", "warm")
    points = [point_light_spec_to_light(pl)
              for pl in (pkg.get("point_lights") or [])]
    if energy_glow is not None:
        points.append(energy_glow_to_point_light(energy_glow))
    rig = rig_for(light, points=points) if points else rig_for(light)
    sky_top = tuple(light.get("sky_top", (122, 168, 214)))
    sky_bottom = tuple(light.get("sky_bottom", (205, 224, 240)))
    ground_color = tuple(pkg.get("ground", {}).get("color", (122, 112, 96)))
    if transparent:
        # Foreground-occlusion pass: elements only, transparent canvas.
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        _wanted = tuple(draw_layers)
        for el in sorted(pkg.get("elements", []),
                         key=lambda e: camera.depth_of(e["center"]),
                         reverse=True):
            if el.get("layer") not in _wanted:
                continue
            if el["id"] in excluded:
                continue
            _draw_element(img, draw, el, camera, rig, width, height,
                          textures, spark_frame)
        return img
    img = Image.new("RGB", (width, height), sky_bottom)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line([(0, y), (width, y)],
                  fill=tuple(int(round(sky_top[i] * (1 - t)
                                       + sky_bottom[i] * t))
                             for i in range(3)))
    horizon = _horizon_y(camera, width, height)
    ground_dark = tuple(int(c * 0.72) for c in ground_color)
    for y in range(int(horizon), height):
        t = (y - horizon) / max(1, height - horizon)
        draw.line([(0, y), (width, y)],
                  fill=tuple(int(round(ground_color[i] * (1 - t)
                                       + ground_dark[i] * t))
                             for i in range(3)))
    # Faint perspective ground grid (surface material cue + depth):
    # grid lines on the ground plane, projected through the camera.
    # Skipped for mud/forest floor (no paved surface to suggest),
    # and skipped entirely when the ground was texture-painted.
    ground_painted = False
    if textures:
        ground_painted = _paint_ground(
            img, camera, width, height, horizon,
            pkg.get("ground", {}).get("kind", "neutral"), ground_color,
            rig=rig)
    if not ground_painted and pkg.get("ground", {}).get("kind") in (
            "cobblestone", "asphalt", "packed_earth", "pale_stone",
            "sand", "neutral", "dark_stone", "wood_floor"):
        grid_color = tuple(int(c * 0.82) for c in ground_color)
        for gx in range(-15, 16, 3):
            pts = []
            for gz in range(4, -26, -2):
                x, y, _, vis = camera.project(
                    (float(gx), 0.0, float(gz)), width, height)
                if vis:
                    pts.append((x, y))
            if len(pts) >= 2:
                draw.line(pts, fill=grid_color, width=1)
        for gz in range(2, -26, -3):
            pts = []
            for gx in range(-16, 17, 2):
                x, y, _, vis = camera.project(
                    (float(gx), 0.0, float(gz)), width, height)
                if vis:
                    pts.append((x, y))
            if len(pts) >= 2:
                draw.line(pts, fill=grid_color, width=1)
    elements = [e for e in pkg.get("elements", [])
                if e["id"] not in excluded]
    # Contact shadows first (on the ground, under the elements),
    # clipped to below the horizon. Shadow darkness falls with
    # layer distance (atmospheric perspective): BG 0.5, MG 0.8,
    # FG 1.0 — distant shadows are softer, never black blobs.
    _LAYER_SHADOW = {"BG": 0.5, "MG": 0.8, "FG": 1.0}
    shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_layer)
    for el in elements:
        if el.get("geometry") != "box":
            continue
        bottom = el["center"][1] - el["size"][1] / 2
        if bottom > 0.06:
            continue  # floating element: no ground contact shadow
        is_slab = el["size"][1] <= 0.2 and abs(bottom) <= 0.02
        if is_slab:
            continue
        foot = (el["center"][0], 0.0, el["center"][2])
        _, _, pscale, vis = camera.project(foot, width, height)
        if not vis:
            continue
        half_w_px = el["size"][0] / 2 * pscale
        half_d_px = el["size"][2] / 2 * pscale
        spec = shadow_ellipse_spec(
            foot, 0.0, max(el["size"][0], el["size"][2]) * 0.55,
            rig.key, camera, (width, height), half_w_px,
            is_ground_slab=is_slab,
            footprint_half_depth_px=half_d_px)
        if spec is None:
            continue
        px, py = spec["center_px"]
        alpha = int(255 * spec["alpha"]
                    * _LAYER_SHADOW.get(el.get("layer"), 0.8))
        sdraw.ellipse([px - spec["rx_px"], py - spec["ry_px"],
                       px + spec["rx_px"], py + spec["ry_px"]],
                      fill=(0, 0, 0, alpha))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(4))
    if horizon > 0:
        ImageDraw.Draw(shadow_layer).rectangle(
            [0, 0, width, int(horizon)], fill=(0, 0, 0, 0))
    img = Image.alpha_composite(img.convert("RGBA"), shadow_layer).convert("RGB")
    draw = ImageDraw.Draw(img)
    # Elements far-to-near by camera depth of centre, restricted to
    # the requested layers (default: all three).
    def _depth(el):
        return camera.depth_of(el["center"])
    for el in sorted(elements, key=_depth, reverse=True):
        if el.get("layer") not in draw_layers:
            continue
        _draw_element(img, draw, el, camera, rig, width, height,
                      textures, spark_frame)
    if scoped_state is not None and _scoped_rain(scoped_state):
        img = Image.alpha_composite(
            img.convert("RGBA"),
            rain_overlay((width, height), frame=rain_frame)).convert("RGB")
    return img


# ---------------------------------------------------------------------------
# Scene-local state isolation (Semantic Engine Upgrade §6, B2)
# ---------------------------------------------------------------------------
# The proven leak this closes: product_flow computed ONE job-level
# ``rainy`` flag (any scene mentioning rain) and applied a rain bed to
# the whole timeline, so trench rain leaked into the Munich scene.
# The scope mechanism below is the environment-side half of the fix:
# weather / lighting / rain resolve per scene through the contract's
# SHOT -> SCENE -> PROJECT chain, and NOTHING crosses a scene
# boundary without an explicit carry_over() call. ATLAS owns the
# product_flow rewiring (per-scene rain beds from the same store);
# this module never consults a job-level flag.
#
# Storage model: every scope's values are keyed by the entity they
# belong to (project id / scene id / shot id / scene+entity id).
# "Reset" is destructive where the contract mandates it: changing
# scene DELETES the outgoing scene's shot entries; changing project
# DELETES the outgoing project's scene/shot/entity entries (no
# carry-over across projects exists). SCENE + entity values survive
# a scene change keyed under their scene — unreachable from the new
# scene, but readable by an explicit carry_over / carry_over_entity,
# which is the only sanctioned crossing. PROJECT values are project
# facts keyed by project id and survive a project switch
# unreachable-but-intact (returning to the project restores its
# defaults; nothing from it resolves while another project is
# current). Re-entering the SAME scene/shot id is a no-op, not a
# reset — a reset happens on CHANGE, per the contract wording.

RAIN_TOKENS = ("rain", "mưa")
RAIN_SEED = 20261112
RAIN_STREAKS_PER_MEGAPIXEL = 80

# Environment attributes resolved through a ScopedState. ``rain``
# (bool) is the explicit switch; when unset, rain is inferred from
# rain tokens in resolved ``weather``. ``time_of_day`` / ``mood``
# feed light_for() via build_environment_scoped().
ENVIRONMENT_SCOPE_KEYS = ("weather", "rain", "time_of_day", "mood")

_ENTITY_SCOPES = (StateScope.EVENT, StateScope.CHARACTER,
                  StateScope.PROP)


def rain_overlay(size, frame: int = 0, seed: int = RAIN_SEED
                 ) -> Image.Image:
    """Deterministic falling-rain streak layer (RGBA, transparent).

    Same ``(size, frame, seed)`` -> byte-identical pixels; the
    frame index only shifts streaks downward (wrap period ~51
    frames at 24 fps for 1080p, so looped rain visibly repeats
    only across a >2 s hold). Streak count scales with frame
    area. Overcast weather (no rain tokens) never reaches this
    function — see :func:`_scoped_rain`.
    """
    width, height = int(size[0]), int(size[1])
    frame = int(frame)
    rng = random.Random(int(seed))
    count = max(24, int(width * height / 1_000_000
                        * RAIN_STREAKS_PER_MEGAPIXEL))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    span = height + 40
    for i in range(count):
        x0 = rng.uniform(-20.0, width + 20.0)
        y0 = rng.uniform(-40.0, height)
        length = rng.uniform(16.0, 30.0)
        speed = rng.uniform(18.0, 26.0)
        y = (y0 + frame * speed) % span - 20.0
        if i % 5 == 0:
            draw.line([(x0, y), (x0 - 5.0, y + length)],
                      fill=(205, 220, 240, 110), width=2)
        else:
            draw.line([(x0, y), (x0 - 5.0, y + length)],
                      fill=(205, 220, 240, 90), width=1)
    return layer


def _scoped_rain(store: "ScopedState") -> bool:
    """True only when the store resolves rain for the current shot.

    An explicit ``rain`` value (even False) wins over ``weather``:
    a dry interior shot inside a rainy scene sets SHOT rain=False.
    Without a ``rain`` value, rain tokens in resolved ``weather``
    count; overcast/cloudy wording without rain tokens does not.
    """
    rain, _source = store.resolve_with_source("rain")
    if rain is not None:
        return bool(rain)
    weather, _source = store.resolve_with_source("weather")
    if isinstance(weather, str):
        text = weather.lower()
        return any(tok in text for tok in RAIN_TOKENS)
    return False


class ScopedState:
    """Scene-local state store (semantic_contracts §6).

    ATLAS wiring: one store per production job. The scene-graph
    builder calls ``begin_project`` / ``begin_scene`` /
    ``begin_shot`` as the job walks the script, and ``set``s each
    scene's weather/lighting/costume/prop attributes at SCENE
    scope (or tighter) from the graph. ``build_environment_scoped``
    and ``render_environment(scoped_state=...)`` resolve through
    this store. Nothing here reads script text or trait dicts —
    the store holds resolved values only, so a keyword in one
    scene can never become state in another.

    Identity vs state: CHARACTER identity (who someone IS) lives
    in the scene graph, not here. CHARACTER scope here holds
    scene-local STATE (e.g. costume state); it is keyed by
    scene + character, so a military costume set in the trench
    scene cannot resolve for the same character in a civilian
    scene. PROP scope likewise holds scene-local prop state; a
    held prop crosses a scene boundary only via
    ``carry_over_entity`` with the graph's explicit declaration.
    """

    def __init__(self) -> None:
        self._project_values: dict[str, dict] = {}
        self._scene_values: dict[tuple, dict] = {}
        self._shot_values: dict[tuple, dict] = {}
        self._entity_values: dict[tuple, dict] = {}
        self._project_id: str | None = None
        self._scene_id: str | None = None
        self._shot_id: str | None = None
        self._carryover_log: list[dict] = []

    # -- position ---------------------------------------------------
    @property
    def project_id(self) -> str | None:
        return self._project_id

    @property
    def scene_id(self) -> str | None:
        return self._scene_id

    @property
    def shot_id(self) -> str | None:
        return self._shot_id

    @property
    def carryover_log(self) -> tuple[dict, ...]:
        return tuple(self._carryover_log)

    def begin_project(self, project_id: str) -> None:
        """Move to a project. A CHANGE resets everything below
        PROJECT for the outgoing project (its scene/shot/entity
        entries are deleted). Re-entering the same id is a no-op.
        """
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        if project_id == self._project_id:
            return
        old = self._project_id
        if old is not None:
            for store in (self._scene_values, self._shot_values):
                for key in [k for k in store if k[0] == old]:
                    del store[key]
            for key in [k for k in self._entity_values
                        if k[1] == old]:
                del self._entity_values[key]
        self._project_id = project_id
        self._scene_id = None
        self._shot_id = None

    def begin_scene(self, scene_id: str) -> None:
        """Move to a scene. A CHANGE resets SHOT scope (the
        outgoing scene's shot entries are deleted). SCENE and
        entity values stay keyed under their scene: unreachable
        from the new scene, readable only via explicit carry-over.
        Requires a current project; same id is a no-op."""
        if self._project_id is None:
            raise ValueError("begin_project() before begin_scene()")
        if not isinstance(scene_id, str) or not scene_id.strip():
            raise ValueError("scene_id must be a non-empty string")
        if scene_id == self._scene_id:
            return
        old = self._scene_id
        if old is not None:
            # SHOT scope resets (deleted); SCENE + entity values
            # stay keyed under the old scene — unreachable from the
            # new scene, but readable by an explicit carry_over /
            # carry_over_entity. Deleting them here would make
            # carry-over impossible by construction.
            for key in [k for k in self._shot_values
                        if k[0] == self._project_id and k[1] == old]:
                del self._shot_values[key]
        self._scene_id = scene_id
        self._shot_id = None

    def begin_shot(self, shot_id: str) -> None:
        """Move to a shot. Requires a current scene; each shot id
        starts with an empty SHOT scope (per-shot overrides never
        leak into the next shot). Same id is a no-op."""
        if self._scene_id is None:
            raise ValueError("begin_scene() before begin_shot()")
        if not isinstance(shot_id, str) or not shot_id.strip():
            raise ValueError("shot_id must be a non-empty string")
        self._shot_id = shot_id

    # -- writes -----------------------------------------------------
    def set(self, scope, key: str, value, entity_id: str | None = None
            ) -> None:
        """Set a scoped value. ``scope`` is a StateScope (or its
        string value). PROJECT/SCENE/SHOT write to the CURRENT
        entity (begin_* first, else ValueError). EVENT/CHARACTER/
        PROP require ``entity_id`` and store under the current
        scene + entity. Setting ``None`` unsets the key."""
        scope = StateScope(scope)
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        if scope is StateScope.PROJECT:
            if self._project_id is None:
                raise ValueError("begin_project() before setting "
                                 "PROJECT scope")
            target = self._project_values.setdefault(self._project_id,
                                                     {})
        elif scope is StateScope.SCENE:
            if self._scene_id is None:
                raise ValueError("begin_scene() before setting "
                                 "SCENE scope")
            target = self._scene_values.setdefault(
                (self._project_id, self._scene_id), {})
        elif scope is StateScope.SHOT:
            if self._shot_id is None:
                raise ValueError("begin_shot() before setting "
                                 "SHOT scope")
            target = self._shot_values.setdefault(
                (self._project_id, self._scene_id, self._shot_id), {})
        elif scope in _ENTITY_SCOPES:
            if self._project_id is None:
                raise ValueError("begin_project() before setting "
                                 "entity scope")
            if not isinstance(entity_id, str) or not entity_id.strip():
                raise ValueError(f"{scope.value} scope requires "
                                 "entity_id")
            target = self._entity_values.setdefault(
                (scope, self._project_id, self._scene_id, entity_id),
                {})
        else:  # pragma: no cover - StateScope is closed
            raise ValueError(f"unknown scope: {scope!r}")
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value

    # -- reads ------------------------------------------------------
    def _chain_values(self, key: str) -> dict:
        """Current SHOT/SCENE/PROJECT values for ``key`` (present
        scopes only), for resolve_scoped_attribute()."""
        values: dict[StateScope, object] = {}
        if self._shot_id is not None:
            shot = self._shot_values.get(
                (self._project_id, self._scene_id, self._shot_id), {})
            if key in shot:
                values[StateScope.SHOT] = shot[key]
        if self._scene_id is not None:
            scene = self._scene_values.get(
                (self._project_id, self._scene_id), {})
            if key in scene:
                values[StateScope.SCENE] = scene[key]
        if self._project_id is not None:
            project = self._project_values.get(self._project_id, {})
            if key in project:
                values[StateScope.PROJECT] = project[key]
        return values

    def resolve(self, key: str, entity_scope=None,
                entity_id: str | None = None):
        """Nearest-scope-wins value for ``key``.

        With ``entity_scope``/``entity_id`` the entity value (if
        set for the current scene + entity) wins over the chain;
        otherwise the SHOT -> SCENE -> PROJECT chain decides via
        the contract's ``resolve_scoped_attribute``. Returns None
        when nothing is set anywhere (never a neighbouring
        scene's or entity's value).
        """
        value, _source = self.resolve_with_source(
            key, entity_scope, entity_id)
        return value

    def resolve_with_source(self, key: str, entity_scope=None,
                            entity_id: str | None = None):
        """(value, source-scope-name-or-None). The value agrees
        with :meth:`resolve` exactly (pinned by tests); the source
        is provenance for build/render records."""
        if entity_scope is not None:
            entity_scope = StateScope(entity_scope)
            if entity_scope not in _ENTITY_SCOPES:
                raise ValueError("entity_scope must be EVENT, "
                                 "CHARACTER or PROP")
            if not isinstance(entity_id, str) or not entity_id.strip():
                raise ValueError("entity resolve requires entity_id")
            entity = self._entity_values.get(
                (entity_scope, self._project_id, self._scene_id,
                 entity_id), {})
            if key in entity:
                return entity[key], entity_scope.value
        chain = self._chain_values(key)
        value = resolve_scoped_attribute(chain)
        source = None
        for scope in SCOPE_INHERITANCE:
            if scope in chain:
                source = scope.value
                break
        return value, source

    # -- explicit carry-over ----------------------------------------
    def carry_over(self, key: str, from_scene_id: str):
        """Copy a SCENE-scope value from ``from_scene_id`` into the
        current scene, and log it. The ONLY way a scene attribute
        crosses a scene boundary. Raises KeyError when the source
        scene has no such value (no silent default) and ValueError
        without a current scene or when source == current scene.
        """
        if self._scene_id is None:
            raise ValueError("begin_scene() before carry_over()")
        if from_scene_id == self._scene_id:
            raise ValueError("carry_over source must differ from "
                             "the current scene")
        source = self._scene_values.get(
            (self._project_id, from_scene_id), {})
        if key not in source:
            raise KeyError(f"no SCENE value {key!r} in scene "
                           f"{from_scene_id!r} to carry over")
        value = source[key]
        self.set(StateScope.SCENE, key, value)
        self._carryover_log.append(
            {"key": key, "from_scene_id": from_scene_id,
             "to_scene_id": self._scene_id, "value": value})
        return value

    def carry_over_entity(self, scope, entity_id: str, key: str,
                          from_scene_id: str):
        """Copy an entity-scope value from ``from_scene_id`` into
        the current scene for the same entity, and log it. The
        ONLY way entity state (e.g. a held prop) crosses a scene
        boundary — the scene graph must declare the carry-over."""
        scope = StateScope(scope)
        if scope not in _ENTITY_SCOPES:
            raise ValueError("carry_over_entity scope must be EVENT, "
                             "CHARACTER or PROP")
        if self._scene_id is None:
            raise ValueError("begin_scene() before carry_over_entity()")
        if from_scene_id == self._scene_id:
            raise ValueError("carry_over source must differ from "
                             "the current scene")
        source = self._entity_values.get(
            (scope, self._project_id, from_scene_id, entity_id), {})
        if key not in source:
            raise KeyError(f"no {scope.value} value {key!r} for "
                           f"{entity_id!r} in scene {from_scene_id!r}")
        value = source[key]
        self.set(scope, key, value, entity_id=entity_id)
        self._carryover_log.append(
            {"key": key, "scope": scope.value, "entity_id": entity_id,
             "from_scene_id": from_scene_id,
             "to_scene_id": self._scene_id, "value": value})
        return value

    def snapshot(self) -> dict:
        """JSON-safe position + key inventory + carry-over log
        (values in the log are stringified when not JSON-safe)."""
        def _safe(value):
            try:
                json.dumps(value)
                return value
            except (TypeError, ValueError):
                return str(value)

        scene = self._scene_values.get(
            (self._project_id, self._scene_id), {})
        shot = self._shot_values.get(
            (self._project_id, self._scene_id, self._shot_id), {})
        project = self._project_values.get(self._project_id, {})
        return {
            "project_id": self._project_id,
            "scene_id": self._scene_id,
            "shot_id": self._shot_id,
            "project_keys": sorted(project),
            "scene_keys": sorted(scene),
            "shot_keys": sorted(shot),
            "entity_entries": len(self._entity_values),
            "carryover_log": [
                {k: _safe(v) for k, v in entry.items()}
                for entry in self._carryover_log],
        }


def resolve_environment_attributes(store: ScopedState,
                                   keys=ENVIRONMENT_SCOPE_KEYS) -> dict:
    """Resolve environment attributes for the store's current
    shot/scene/project. Returns ``{key: {"value", "source"}}``
    with ``source`` the winning scope name (or None when unset).
    Pure read — no store mutation, no trait access."""
    resolved = {}
    for key in keys:
        value, source = store.resolve_with_source(key)
        resolved[key] = {"value": value, "source": source}
    return resolved


def build_environment_scoped(store: ScopedState,
                             location_traits: dict, period: str = "",
                             time_of_day: str | None = None,
                             style: dict | None = None) -> dict:
    """Build an EnvironmentPackage from store-resolved attributes.

    Precedence per attribute: store-resolved value (SHOT > SCENE >
    PROJECT) wins over the trait field; an explicit ``time_of_day``
    argument wins over the store; otherwise the trait/default path
    of :func:`build_environment` applies. Provenance records the
    source of ``weather`` / ``time_of_day`` / ``mood`` / ``rain``
    under ``provenance.scoped_resolution`` plus the scope position
    under ``provenance.scope`` — a later reader can tell whether
    the rain in a render came from the scene's own declaration or
    from a neighbouring scene's leak (the latter must be
    impossible: the store only resolves the current scene).

    Requires a current scene (ValueError otherwise): an
    environment without a scene position has no isolation
    guarantee to offer.
    """
    if store.scene_id is None:
        raise ValueError("ScopedState has no current scene; "
                         "begin_scene() before building")
    resolved = resolve_environment_attributes(store)
    traits = dict(location_traits or {})
    style = dict(style or {})
    sources: dict[str, str] = {}

    weather = resolved["weather"]
    if weather["value"] is not None:
        traits["weather"] = weather["value"]
        sources["weather"] = weather["source"]
    elif traits.get("weather"):
        sources["weather"] = "trait"
    else:
        sources["weather"] = "default"

    if time_of_day is not None:
        tod = time_of_day
        sources["time_of_day"] = "argument"
    elif resolved["time_of_day"]["value"] is not None:
        tod = resolved["time_of_day"]["value"]
        sources["time_of_day"] = resolved["time_of_day"]["source"]
    else:
        tod = "day"
        sources["time_of_day"] = "default"

    if resolved["mood"]["value"] is not None:
        style["mood"] = resolved["mood"]["value"]
        sources["mood"] = resolved["mood"]["source"]
    else:
        sources["mood"] = "trait_or_default"

    sources["rain"] = (resolved["rain"]["source"]
                       if resolved["rain"]["value"] is not None
                       else "unresolved")

    pkg = build_environment(traits, period, tod, style)
    pkg["provenance"]["scope"] = {
        "project_id": store.project_id,
        "scene_id": store.scene_id,
        "shot_id": store.shot_id,
    }
    pkg["provenance"]["scoped_resolution"] = sources
    return pkg
