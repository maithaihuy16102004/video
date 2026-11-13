# Licenses — Europe 1914 boundaries (ohm_1914_europe)

Per-component license record for the pinned OpenHistoricalMap extract
ingested 2026-11-12. This file records the license of each COMPONENT
of the dataset; the full attribution record (with the verbatim source
tags and the required credit line) is ATTRIBUTION.md in this folder,
and the verification evidence is verification_report.json.

## Licensing granularity — read this first

Licensing in this dataset is per boundary SEGMENT (OpenHistoricalMap
member way), not per polygon. A single relation (country polygon) is
stitched from many member ways, and its boundary mixes CC0 segments
with CC BY 4.0 segments. No per-polygon license field is recorded in
boundaries.geojson, because a single license per polygon would be
false. The authoritative record is the segment table below plus the
per-element tag counts in verification_report.json.

## Component 1 — OpenHistoricalMap base data: CC0 1.0 Universal

- Applies to: the base map data, and every element that carries no
  `license=*` tag noting otherwise — including the 39 tagged member
  ways explicitly tagged CC0.
- Dedication: Creative Commons CC0 1.0 Universal public domain
  dedication ("unless noted otherwise"), per
  https://wiki.openstreetmap.org/wiki/OpenHistoricalMap/License
  (verified firsthand 2026-11-12; the Overpass response's
  osm3s.copyright notice states CC0).
- Reference text: ../licenses/CC0-1.0.txt
- Canonical text: https://creativecommons.org/publicdomain/zero/1.0/
- Commercial use, modification and redistribution: PERMITTED,
  without asking permission. Attribution is given as a matter of
  record (see ATTRIBUTION.md), not as a CC0 condition.

## Component 2 — Boundary segments: CC BY 4.0 International

- Applies to: 273 of the 312 tagged member ways in the pinned
  extract, per their `license=*` tags (verified on the pinned
  extract 2026-11-12; zero ShareAlike, NonCommercial or
  NoDerivatives elements found).

| Ways | Authority | Verbatim `source` tag |
|-----:|-----------|-----------------------|
| 194 | IGN CNIG (Spain) — Límites | https://centrodedescargas.cnig.es/CentroDescargas/catalogo.do?Serie=LILIM |
| 41 | Kartverket (Norwegian Mapping Authority) | Administrative units municipalities from Kartverket (Norwegian Mapping Authority) / Kartverket Administrative enheter |
| 20 | Surveying and Mapping Authority of the Republic of Slovenia (eProstor) | https://ipi.eprostor.gov.si/jgp/data |
| 18 | UN OCHA Humanitarian Data Exchange — COD-AB Ukraine | https://data.humdata.org/dataset/cod-ab-ukr |

- License: Creative Commons Attribution 4.0 International
  (CC BY 4.0).
- Reference text: ../licenses/CC-BY-4.0.txt
- Canonical text: https://creativecommons.org/licenses/by/4.0/legalcode
- Commercial use, modification and redistribution: PERMITTED with
  attribution — appropriate credit, a link to the license, and an
  indication of changes made. The on-frame credit line on every
  rendered map frame plus ATTRIBUTION.md satisfy the attribution
  term for rendered video distribution. The credit must not suggest
  any licensor endorses the video or the channel.
- Changes made to these segments: geometry simplification only
  (Douglas-Peucker, tolerance 0.02 deg, ~2.2 km; 902,212 vertices
  reduced to 17,729). No segment was added, removed, re-attributed
  or re-licensed. See metadata.json for the simplification record
  and both checksums (pinned response + derived geometry).

## What is NOT in this dataset

- No separate OpenStreetMap coastline import (CC BY-SA 2.0).
  Coastlines derive only from the boundary relations' own outer
  rings. A coastline import would need separate verification.
- No route geometries. Routes need separate sourcing or explicitly
  labeled illustrative routes.
- No member-node license tags were checked (nodes in boundary
  relations do not normally carry license tags — recorded as a known
  limitation in metadata.json).

## Scope of this record

This record covers ONLY the pinned extract identified by response
SHA-256 c61c0cf1c0f6cd6667fe27e74cf7b3aa7a39330ae344a1f13c1855339554d134
(OSM base 2026-11-12T14:19:31Z) and its derived geometry (SHA-256
438369285496c38340bb363f8fce55e89db74bab1c83ffd65dd499ac20fffba3).
A re-query of the live database requires a new verification process;
this record does not cover any other extract.
