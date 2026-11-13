"""Historical map renderer — reusable, provenance-first.

Visual Quality Recovery, P4. Renders geographical maps from REAL
polygon data only. Countries are drawn as polygons from a dataset
(GeoJSON) or caller-supplied SVG paths — NEVER as rectangular
information cards (the Ep1 draft defect: region names on rectangles
presented as a map).

Modes:

* ``"modern"`` — Natural Earth 1:110m Admin 0 Countries, public
  domain, shipped under ``ai_clip_studio/data/``. The report and
  the frame itself state "modern boundaries — not 1914". Modern
  boundaries must never be presented as historical.
* ``"historical"`` — requires a verified historical-border dataset
  file supplied by the caller (``dataset_path`` + ``provenance``)
  or registered under ``ai_clip_studio/data/``. NO historical
  dataset is embedded: the two known candidates both carry license
  / accuracy caveats (CShapes 2.0 is CC BY-NC-SA 4.0; Ourednik
  historical-basemaps is GPL-3.0 and self-described draft — see
  ``data/MAP_DATASETS.md``). Without a dataset file, historical
  mode raises ``MissingHistoricalMapData`` — loudly, naming the
  candidates and what to supply. Border geometry is never invented.
* ``"supplied"`` — caller-supplied GeoJSON (``geojson``) or SVG
  path strings (``svg_paths``). Provenance comes from the caller;
  when the caller supplies none, the report marks provenance
  "caller-supplied, unverified".

Public API (ATLAS wiring contract):

    img, report = render_map(map_spec)

``map_spec`` fields: ``mode``, ``year`` (historical), ``dataset_ref``
or ``dataset_path``, ``geojson``, ``svg_paths``, ``highlight``
([{region, color, label}]), ``labels`` ([{text, lon, lat} |
{text, region}]), ``route`` ({points: [[lon, lat], ...],
progress_t | timeline_sync: {t, duration}, color, schematic}),
``framing`` ({lon_min, lon_max, lat_min, lat_max} or "auto"),
``size``, ``style`` ({land, water, border, label_color}).

Route animation: ``progress_t`` in [0,1] (or derived from
``timeline_sync``) draws the travelled portion solid, the remainder
faint, and a marker at the current position. Routes are schematic
polylines between real coordinates unless the caller supplies a
surveyed path and says so; the report records ``schematic: True``
by default.

Projection: equirectangular with cos(mean latitude) correction —
honest for regional maps at this scale, documented, not a survey
projection.
"""
from __future__ import annotations

import json
import math
import os
import re

from PIL import Image, ImageDraw, ImageFont

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data")

# Datasets the engine knows about. "embedded" files ship in
# ai_clip_studio/data/; "not_embedded" entries are research records
# only — the renderer names them in the missing-data error.
DATASETS = {
    "natural_earth_110m_europe": {
        "file": "natural_earth_110m_europe.json",
        "name": "Natural Earth 1:110m Admin 0 Countries",
        "source_url": "https://www.naturalearthdata.com/downloads/"
                      "110m-cultural-vectors/",
        "license": "Public domain",
        "date": "2026-11-12 (retrieved)",
        "coverage": "modern",
        "status": "embedded",
    },
    "cshapes_2.0": {
        "file": None,
        "name": "CShapes 2.0 (ETH Zürich ICR)",
        "source_url": "https://icr.ethz.ch/data/cshapes/",
        "license": "CC BY-NC-SA 4.0 (NonCommercial — needs a license "
                   "decision before any monetised use)",
        "date": "1886-2019",
        "coverage": "historical",
        "status": "not_embedded",
    },
    "historical_basemaps_1914": {
        "file": None,
        "name": "historical-basemaps, world_1914.geojson (A. Ourednik)",
        "source_url": "https://github.com/aourednik/historical-basemaps",
        "license": "GPL-3.0; author warns: draft, verify before use",
        "date": "1914 snapshot",
        "coverage": "historical",
        "status": "not_embedded",
    },
}

MODERN_BOUNDARY_NOTE = "modern boundaries — not 1914"

_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
)


class MissingHistoricalMapData(Exception):
    """No verified historical-border dataset is available.

    Raised by historical-mode renders when no dataset file can be
    found. The message names the known candidates, their licenses,
    and exactly what file + provenance the caller must supply. This
    is deliberate: a fake historical map is worse than no map."""


class MapSpecError(Exception):
    """The map_spec is malformed (missing mode, bad framing, ...)."""


def _load_font(size: int, bold: bool = True):
    paths = _FONT_PATHS if bold else _FONT_PATHS[1:] + _FONT_PATHS[:1]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def load_dataset(dataset_ref: str | None = None,
                 dataset_path: str | None = None) -> dict:
    """Load a GeoJSON dataset by registry ref or explicit path.

    Returns the parsed FeatureCollection dict (with its
    ``provenance`` member when present). Raises MapSpecError for
    unknown refs and FileNotFoundError for missing files."""
    if dataset_path:
        with open(dataset_path, encoding="utf-8") as fh:
            return json.load(fh)
    if dataset_ref is None:
        raise MapSpecError("no dataset_ref or dataset_path given")
    entry = DATASETS.get(dataset_ref)
    if entry is None:
        raise MapSpecError(f"unknown dataset_ref: {dataset_ref!r}")
    if entry["file"] is None:
        raise MapSpecError(
            f"dataset {dataset_ref} is not embedded: {entry['name']} "
            f"({entry['license']}). Supply dataset_path + provenance.")
    path = os.path.join(_DATA_DIR, entry["file"])
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _iter_rings(geometry: dict):
    """Yield (exterior_ring, holes) for Polygon/MultiPolygon."""
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon" and coords:
        yield coords[0], coords[1:]
    elif gtype == "MultiPolygon" and coords:
        for poly in coords:
            if poly:
                yield poly[0], poly[1:]


def _draw_map_label(draw, x, y, text, font, label_color, size):
    """Centred label with a white halo, clamped inside the frame.

    Returns ``(tx, ty, clamped)``: the top-left actually drawn and
    whether clamping moved it. A region centroid can fall outside
    the framing (Russia's centroid sits far east of a Europe
    framing); without the clamp the label is drawn off-frame and
    silently invisible (the missing 'Nga' defect). Clamped labels
    are reported, never silently dropped.
    """
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = x - tw / 2 - bbox[0], y - th / 2 - bbox[1]
    clamped_tx = min(max(tx, 8.0), max(8.0, size[0] - tw - 8.0))
    clamped_ty = min(max(ty, 8.0), max(8.0, size[1] - th - 8.0))
    clamped = (clamped_tx != tx) or (clamped_ty != ty)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((clamped_tx + dx, clamped_ty + dy), text, font=font,
                  fill=(255, 255, 255))
    draw.text((clamped_tx, clamped_ty), text, font=font,
              fill=label_color)
    return clamped_tx, clamped_ty, clamped


def _polygon_centroid(ring):
    """Area-weighted centroid of a ring (lon/lat), fallback: mean."""
    area2 = 0.0
    cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        cross = x0 * y1 - x1 * y0
        area2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area2) < 1e-9:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    return (cx / (3 * area2), cy / (3 * area2))


def _project(lon: float, lat: float, framing: dict, size) -> tuple:
    """Equirectangular projection with cos(mean-lat) correction.

    Pixels-per-degree of latitude fill the frame height; longitude
    degrees are scaled by cos(mean latitude) (their true relative
    length) and the map is centred horizontally. Regional maps keep
    true proportions; this is not a survey projection."""
    lon0, lon1 = framing["lon_min"], framing["lon_max"]
    lat0, lat1 = framing["lat_min"], framing["lat_max"]
    w, h = size
    mean_lat = math.radians((lat0 + lat1) / 2)
    kx = math.cos(mean_lat) or 1.0
    ppd_lat = h / (lat1 - lat0)
    ppd_lon = ppd_lat * kx
    map_w = (lon1 - lon0) * ppd_lon
    x0 = (w - map_w) / 2.0
    x = x0 + (lon - lon0) * ppd_lon
    y = h - (lat - lat0) * ppd_lat
    return (x, y)


def _auto_framing(features, pad_deg: float = 1.5) -> dict:
    lons, lats = [], []
    for feat in features:
        for ring, _ in _iter_rings(feat.get("geometry") or {}):
            for lon, lat in ring:
                lons.append(lon)
                lats.append(lat)
    if not lons:
        raise MapSpecError("no polygon coordinates for auto framing")
    return {"lon_min": min(lons) - pad_deg, "lon_max": max(lons) + pad_deg,
            "lat_min": min(lats) - pad_deg, "lat_max": max(lats) + pad_deg}


def parse_svg_paths(svg_paths) -> list[dict]:
    """Parse minimal SVG path data (M/L/Z, absolute coords) into
    polygon features. Coordinates are taken as (lon, lat) pairs.
    Only the M/L/Z command subset is supported; anything else
    raises MapSpecError naming the unsupported command. Each entry
    is {region, d} or {region, d, label}."""
    features = []
    for entry in svg_paths or []:
        d = str(entry.get("d", "")).strip()
        if not d:
            raise MapSpecError(f"empty SVG path for {entry.get('region')}")
        if re.search(r"[CcQqAaSsTtHhVv]", d):
            raise MapSpecError(
                "unsupported SVG command in path for "
                f"{entry.get('region')!r}: only M/L/Z are supported")
        tokens = re.findall(r"[MLZmlz]|-?\d+(?:\.\d+)?", d)
        ring, current = [], None
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok in ("M", "L", "m", "l"):
                current = tok.upper()
                i += 1
                continue
            if tok in ("Z", "z"):
                current = None
                i += 1
                continue
            lon = float(tok)
            lat = float(tokens[i + 1])
            ring.append((lon, lat))
            i += 2
        if len(ring) < 3:
            raise MapSpecError(
                f"SVG path for {entry.get('region')!r} has fewer than "
                "3 points — not a polygon")
        features.append({
            "type": "Feature",
            "properties": {"NAME": entry.get("region", ""),
                           "label": entry.get("label", "")},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
    return features


def _resolve_progress(route: dict) -> float:
    """progress_t in [0,1]: explicit, or from timeline_sync."""
    if route is None:
        return 0.0
    if "progress_t" in route:
        return min(1.0, max(0.0, float(route["progress_t"])))
    sync = route.get("timeline_sync") or {}
    duration = float(sync.get("duration") or 0)
    if duration > 0:
        return min(1.0, max(0.0, float(sync.get("t") or 0) / duration))
    return 0.0


def _route_points_up_to(points, t: float):
    """Sub-polyline from the start up to fraction ``t`` of length."""
    if t <= 0:
        return [points[0]]
    if t >= 1:
        return list(points)
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                for a, b in zip(points, points[1:]))
    if total == 0:
        return list(points)
    target = total * t
    out = [points[0]]
    walked = 0.0
    for a, b in zip(points, points[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if walked + seg >= target:
            frac = (target - walked) / seg if seg else 0.0
            out.append((a[0] + (b[0] - a[0]) * frac,
                        a[1] + (b[1] - a[1]) * frac))
            return out
        walked += seg
        out.append(b)
    return out


def render_map(map_spec: dict):
    """Render a map frame from real polygon data.

    Returns ``(PIL Image, MapReport dict)``. Raises
    ``MissingHistoricalMapData`` for historical mode without a
    verified dataset, and ``MapSpecError`` for malformed specs.
    The report always carries dataset provenance, the boundary
    note, regions/labels drawn, and route schematic status."""
    spec = dict(map_spec or {})
    mode = str(spec.get("mode", "")).lower()
    if mode not in ("modern", "historical", "supplied"):
        raise MapSpecError(
            f"mode must be 'modern', 'historical' or 'supplied', "
            f"got {spec.get('mode')!r}")
    size = tuple(spec.get("size", (1920, 1080)))
    style = dict(spec.get("style") or {})
    land = tuple(style.get("land", (214, 206, 184)))
    water = tuple(style.get("water", (168, 196, 220)))
    border = tuple(style.get("border", (60, 60, 58)))
    label_color = tuple(style.get("label_color", (30, 30, 30)))

    features, provenance, boundary_note = [], {}, ""
    if mode == "modern":
        entry = DATASETS["natural_earth_110m_europe"]
        data = load_dataset("natural_earth_110m_europe")
        features = data.get("features", [])
        provenance = dict(data.get("provenance") or {})
        provenance.setdefault("dataset", entry["name"])
        provenance.setdefault("source_url", entry["source_url"])
        provenance.setdefault("license", entry["license"])
        boundary_note = MODERN_BOUNDARY_NOTE
    elif mode == "historical":
        dataset_path = spec.get("dataset_path")
        dataset_ref = spec.get("dataset_ref")
        data = None
        if dataset_path and os.path.exists(dataset_path):
            data = load_dataset(dataset_path=dataset_path)
        elif dataset_ref:
            entry = DATASETS.get(dataset_ref)
            if entry is not None and entry["file"]:
                data = load_dataset(dataset_ref)
        if data is None:
            candidates = "; ".join(
                f"{e['name']} ({e['license']}, {e['source_url']})"
                for key, e in DATASETS.items()
                if e["coverage"] == "historical")
            raise MissingHistoricalMapData(
                "No verified historical-border dataset is available "
                f"for year {spec.get('year')!r}. Known candidates: "
                f"{candidates}. To render historical mode, supply "
                "dataset_path pointing at a verified GeoJSON snapshot "
                "plus a provenance dict {dataset, source_url, license, "
                "date} and a recorded license decision. Refusing to "
                "render modern boundaries as historical.")
        features = data.get("features", [])
        provenance = dict(spec.get("provenance") or
                          data.get("provenance") or {})
        if not provenance.get("license"):
            provenance["license"] = "caller-supplied, unverified"
        boundary_note = (
            f"historical boundaries, year {spec.get('year')}, "
            f"source: {provenance.get('dataset', 'caller-supplied')}")
    else:  # supplied
        if spec.get("geojson"):
            data = spec["geojson"]
            if isinstance(data, str):
                data = json.loads(data)
            features = data.get("features", [])
            provenance = dict(spec.get("provenance") or
                              data.get("provenance") or {})
        elif spec.get("svg_paths"):
            features = parse_svg_paths(spec["svg_paths"])
            provenance = dict(spec.get("provenance") or {})
        else:
            raise MapSpecError(
                "supplied mode needs 'geojson' or 'svg_paths'")
        if not provenance.get("license"):
            provenance["license"] = "caller-supplied, unverified"
        boundary_note = provenance.get(
            "boundary_note", "caller-supplied geometry")

    if not features:
        raise MapSpecError("no polygon features to draw")

    framing = spec.get("framing") or "auto"
    if framing == "auto":
        framing = _auto_framing(features)
    else:
        framing = dict(framing)
        for key in ("lon_min", "lon_max", "lat_min", "lat_max"):
            if key not in framing:
                raise MapSpecError(f"framing missing {key}")

    highlight = {}
    for entry in spec.get("highlight") or []:
        name = entry.get("region", "")
        highlight[name.lower()] = {
            "color": tuple(entry.get("color", (232, 180, 90))),
            "label": entry.get("label", name),
        }

    img = Image.new("RGB", size, water)
    draw = ImageDraw.Draw(img)
    regions_drawn = []
    centroids = {}
    best_rings = {}
    highlight_matched = set()
    for feat in features:
        props = feat.get("properties") or {}
        name = str(props.get("NAME", props.get("name", "")))
        key = name.lower()
        fill = highlight.get(key, {}).get("color", land)
        drawn = False
        for ring, holes in _iter_rings(feat.get("geometry") or {}):
            pts = [_project(lon, lat, framing, size) for lon, lat in ring]
            if len(pts) >= 3:
                draw.polygon(pts, fill=fill, outline=border, width=2)
                drawn = True
            for hole in holes:
                hole_pts = [_project(lon, lat, framing, size)
                            for lon, lat in hole]
                if len(hole_pts) >= 3:
                    draw.polygon(hole_pts, fill=water, outline=border,
                                 width=1)
            # Label anchor: the LARGEST ring, not the first. A
            # multi-polygon region's first ring can be a far-flung
            # fragment (Russia's first ring pulls the centroid east
            # of the framing); the largest ring is the main landmass.
            if ring and name:
                prev = best_rings.get(name)
                if prev is None or len(ring) > len(prev):
                    best_rings[name] = ring
        if drawn and name:
            regions_drawn.append(name)
        if drawn and key in highlight:
            highlight_matched.add(key)
    for name, ring in best_rings.items():
        clon, clat = _polygon_centroid(ring)
        centroids[name] = _project(clon, clat, framing, size)

    # Route animation (drawn BEFORE labels so labels stay on top).
    route = spec.get("route") or {}
    route_report = None
    points = route.get("points") or []
    if len(points) >= 2:
        pts = [(float(p[0]), float(p[1])) for p in points]
        t = _resolve_progress(route)
        route_color = tuple(route.get("color", (200, 40, 40)))
        faint = tuple(int(c * 0.45 + 255 * 0.55) for c in route_color)
        full_px = [_project(lon, lat, framing, size) for lon, lat in pts]
        draw.line(full_px, fill=faint, width=4)
        travelled = _route_points_up_to(pts, t)
        travelled_px = [_project(lon, lat, framing, size)
                        for lon, lat in travelled]
        if len(travelled_px) >= 2:
            draw.line(travelled_px, fill=route_color, width=7)
        mx, my = travelled_px[-1]
        r = max(8, size[1] // 90)
        draw.ellipse([mx - r, my - r, mx + r, my + r],
                     fill=route_color, outline=(255, 255, 255), width=3)
        route_report = {"points": pts, "progress_t": round(t, 3),
                        "schematic": bool(route.get("schematic", True)),
                        "note": route.get("note",
                                          "schematic route between real "
                                          "coordinates, not a surveyed "
                                          "march path")}

    # Labels: explicit lon/lat first, then region centroids.
    labels_drawn = []
    label_positions = {}
    labels_clamped = []
    font = _load_font(max(20, size[1] // 30))
    for entry in spec.get("labels") or []:
        text = str(entry.get("text", "")).strip()
        if not text:
            continue
        if "lon" in entry and "lat" in entry:
            x, y = _project(float(entry["lon"]), float(entry["lat"]),
                            framing, size)
        elif entry.get("region") in centroids:
            x, y = centroids[entry["region"]]
        else:
            continue
        tx, ty, clamped = _draw_map_label(
            draw, x, y, text, font, label_color, size)
        labels_drawn.append(text)
        label_positions[text] = (round(tx, 1), round(ty, 1))
        if clamped:
            labels_clamped.append(text)
    # Highlight labels default to region centroids when the caller
    # did not already label that region explicitly.
    explicitly_labeled = {str(e.get("region", "")).lower()
                          for e in spec.get("labels") or []
                          if e.get("region")}
    for key, hl in highlight.items():
        if hl["label"] and hl["label"] not in labels_drawn \
                and key not in explicitly_labeled:
            for name, (x, y) in centroids.items():
                if name.lower() == key:
                    text = hl["label"]
                    tx, ty, clamped = _draw_map_label(
                        draw, x, y, text, font, label_color, size)
                    labels_drawn.append(text)
                    label_positions[text] = (round(tx, 1), round(ty, 1))
                    if clamped:
                        labels_clamped.append(text)
                    break

    # On-frame honesty label (bottom-left): the boundary note is
    # part of the image, not just the report.
    small = _load_font(max(16, size[1] // 48), bold=False)
    draw.text((16, size[1] - 40), boundary_note, font=small,
              fill=(255, 255, 255),
              stroke_width=2, stroke_fill=(40, 40, 40))
    if mode == "modern":
        draw.text((16, size[1] - 72),
                  "Modern state boundaries shown for layout only.",
                  font=small, fill=(255, 255, 255),
                  stroke_width=2, stroke_fill=(40, 40, 40))
    # Attribution line (registry condition): a dataset admitted with
    # an attribution obligation must credit its sources on the frame.
    attribution = str(spec.get("attribution") or "").strip()
    if attribution:
        draw.text((16, size[1] - 104), attribution, font=small,
                  fill=(255, 255, 255),
                  stroke_width=2, stroke_fill=(40, 40, 40))

    report = {
        "mode": mode,
        "year": spec.get("year"),
        "dataset": provenance,
        "boundary_note": boundary_note,
        "attribution": attribution,
        "regions_drawn": regions_drawn,
        "regions_count": len(regions_drawn),
        "labels_drawn": labels_drawn,
        "label_positions": label_positions,
        "labels_clamped": labels_clamped,
        "highlight_matched": sorted(highlight_matched),
        "highlight_unmatched": sorted(
            k for k in highlight if k not in highlight_matched),
        "route": route_report,
        "framing": framing,
        "size": list(size),
        "rectangular_cards": False,
    }
    return img, report
