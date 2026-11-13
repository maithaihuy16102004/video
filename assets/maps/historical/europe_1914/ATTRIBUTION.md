# Attribution — Europe 1914 boundaries (ohm_1914_europe)

This dataset is a pinned, simplified extract of OpenHistoricalMap
boundary relations. Attribution is a CONDITION of the ATLAS license
verdict (LICENSE_VERDICT_OHM_1914.md): the map renderer must carry a
credit line on every rendered map frame, and this file must ship with
the dataset.

## Base data

Map data © OpenHistoricalMap contributors
(https://www.openhistoricalmap.org), in the public domain under a
Creative Commons CC0 dedication, unless noted otherwise. Extract:
Overpass API query (admin_level=2, start_date <= 1914-07-28 <
end_date, bbox lat 35–60 / lon −12–40), OSM base 2026-11-12T14:19:31Z,
response SHA-256
c61c0cf1c0f6cd6667fe27e74cf7b3aa7a39330ae344a1f13c1855339554d134.

## CC BY 4.0 segments (273 of 312 tagged member ways)

The following boundary segments are licensed CC BY 4.0 (Creative
Commons Attribution 4.0 International). Commercial use, modification
and redistribution are permitted with attribution. Per-element
`license=*` tags were verified on the pinned extract; no ShareAlike,
NonCommercial or NoDerivatives element was found.

| Ways | Source (verbatim `source` tag) | Authority |
|-----:|-------------------------------|-----------|
| 194 | https://centrodedescargas.cnig.es/CentroDescargas/catalogo.do?Serie=LILIM | IGN CNIG (Spain) — Límites |
| 41 | Administrative units municipalities from Kartverket (Norwegian Mapping Authority) / Kartverket Administrative enheter | Kartverket (Norway) |
| 20 | https://ipi.eprostor.gov.si/jgp/data | Surveying and Mapping Authority of the Republic of Slovenia (eProstor) |
| 18 | https://data.humdata.org/dataset/cod-ab-ukr | UN OCHA Humanitarian Data Exchange — COD-AB Ukraine |

The remaining 39 tagged ways are CC0; untagged elements fall under the
OHM CC0 dedication quoted above.

## Required on-frame credit line

Every rendered map frame using this dataset must carry:

> Map data © OpenHistoricalMap contributors (CC0, unless noted);
> boundary segments © IGN CNIG, Kartverket, eProstor Slovenia, UN OCHA HDX (CC BY 4.0).

## What this dataset is NOT

- It is not the live OpenHistoricalMap database: re-running the query
  may return different data. Only the pinned extract (hash above) is
  verified.
- Coastlines derive from the boundary relations' own outer rings. No
  separate OpenStreetMap coastline import (CC BY-SA 2.0) is included
  or permitted without separate verification.
- No route geometries are included. Routes need separate sourcing or
  explicitly labeled illustrative routes.
