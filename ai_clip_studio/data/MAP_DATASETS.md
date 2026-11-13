# Map datasets — research record (Visual Quality Recovery, P4)

Recorded 2026-11-12 by Subagent B. Nothing here is a claim of
historical accuracy. Border geometry is NEVER invented: the map
renderer only draws polygons from a dataset file or caller-supplied
GeoJSON/SVG paths, and every render carries a provenance report.

## Shipped with the engine

### Natural Earth 1:110m Admin 0 Countries (MODERN boundaries)

- File: `natural_earth_110m_europe.json` (51 features, coordinates
  rounded to 0.01 deg, subset = features intersecting
  lon [-12, 45], lat [34, 72]).
- Source: https://www.naturalearthdata.com/downloads/110m-cultural-vectors/
- Mirror used for download:
  https://github.com/martynafford/natural-earth-geojson
  (`110m/cultural/ne_110m_admin_0_countries.json`, 177 features,
  retrieved 2026-11-12, verified: Germany/France/Austria/Russia/
  United Kingdom/Belgium/Serbia all present).
- License: **public domain** (Natural Earth terms: all raster +
  vector map data on naturalearthdata.com is in the public domain).
- Coverage: **MODERN state boundaries. NOT 1914.** Austria-Hungary,
  the German Empire, the Russian Empire and the Ottoman Empire do
  not exist in this dataset. Any render from it MUST carry the
  report note "modern boundaries — not 1914" and an on-frame label
  saying the same. Never present it as a historical map.

## Historical-border candidates — NOT embedded (license / accuracy)

### CShapes 2.0 (ETH Zürich, ICR)

- Covers state borders 1886–2019 (CShapes-Europe from 1816), every
  border change dated; GeoJSON/Shapefile/SQL download.
- Source: https://icr.ethz.ch/data/cshapes/
- Citation: Schvitz, Rüegger, Girardin, Cederman, Weidmann,
  Gleditsch (2022), "Mapping the International System, 1886–2017:
  The CShapes 2.0 Dataset", Journal of Conflict Resolution 66(1).
- License: **CC BY-NC-SA 4.0** (NonCommercial). That is the blocker:
  embedding it in a tool whose output may be monetised on YouTube
  needs an explicit license decision by Mai. NOT downloaded into
  this repo. The renderer raises `MissingHistoricalMapData` and
  names this dataset until a verified copy is supplied with a
  license decision.

### historical-basemaps (André Ourednik)

- World polygon snapshots 2000 BC–2010 as plain GeoJSON; verified
  2026-11-12 that `world_1914.geojson` (142 countries) exists in
  the repo index.
- Source: https://github.com/aourednik/historical-basemaps
- License: **GPL-3.0**. Accuracy caveat from the author: "work in
  progress: verify the maps by comparison to other sources before
  using in academic work." NOT embedded: copyleft + draft accuracy.
  Same handling as CShapes — named in the missing-data error.

## Rule

A historical-mode render (`mode="historical"`) succeeds ONLY when
a dataset file is supplied by the caller with provenance
(`dataset_path` + `provenance` fields) or when a verified dataset
is later added to this directory with a recorded license decision.
Otherwise `render_map` raises `MissingHistoricalMapData`. No
rectangular country cards, ever, in any mode.
