# NID Dams STAC Collection

`create_nid_collection.py` turns NID GeoJSON into a
**STAC 1.1 Collection with one Item per dam**. Each Item has a WGS84 point
geometry and a single-dam GeoJSON data asset. The Collection links all 239
Items and retains a link to the original NAD83 (EPSG:4269) inventory.

Allegheny watershed (HUC-4 0501) NID GeoJSON is included as an example
input dataset.

## Generate the catalog

From the repository root, using [uv](https://docs.astral.sh/uv/) and `pyproj`:

```bash
uv run --no-project --with pyproj python metadata/utils/dams/create_nid_collection.py \
  metadata/utils/dams/0501_allegheny_nid-dams.geojson
```

The default output sits beside the source file:

| Output | Contents |
| --- | --- |
| `0501_allegheny_nid-dams.collection.json` | Collection and links to every Item. |
| `0501_allegheny_nid-dams.collection-items/` | One `.json` Item and one `.geojson` data asset per dam. |

Links within this layout are relative. The generated Collection and Item
**JSON files are Git-ignored**; regenerate them before publishing. The
original inventory and per-dam GeoJSON assets retain all source attributes
and field names.

## What is in an Item?

Items expose 26 searchable NID attributes with snake_case names. Of these,
13 numeric measurements (or `null` if missing) use a flat `dam:` prefix:

| Group | Fields | Units |
| --- | --- | --- |
| Dam size | `dam:dam_height_ft`, `dam:hydraulic_height_ft`, `dam:structural_height_ft`, `dam:nid_height_ft`, `dam:dam_length_ft`, `dam:spillway_width_ft` | Feet |
| Structure volume | `dam:volume_cubic_yards` | Cubic yards |
| Storage | `dam:nid_storage_acre_ft`, `dam:max_storage_acre_ft`, `dam:normal_storage_acre_ft` | Acre-feet |
| Area | `dam:surface_area_acres`, `dam:drainage_area_sq_miles` | Acres; square miles |
| Discharge | `dam:max_discharge_cubic_ft_second` | Cubic feet per second |

Maximum discharge is a **reported maximum, not a live flow reading**. The
other attributes include `nid_id`, location, purpose, dam type, hazard,
condition, and source agency. STAC's `datetime` and `title` keep their
standard names. `dam:` is a local namespace, **not a declared STAC
extension**.

### FFRD-derived fields

The generator also calculates:

| Prefix | What it means |
| --- | --- |
| `ffrd:` | Reproducible values derived from the NID fields: `flood_pool_fraction`, `data_emergency_action_plan`, `data_operations_manual_likely`, `breach_structure_class`, and `recommended_breach_method`. |
| `ffrd_screening:` | Heuristics for size, storage, flood control, hydrologic influence, infrastructure, candidate analyses, hydraulic type, and modeling priority. **These are not official FFRD scoping decisions.** |

Flood-pool fraction is `(max storage - normal storage) / max storage`. It is
`null` if either value is missing or max storage is zero.
`data_operations_manual_likely` indicates a USACE source agency; it **does
not confirm** that an operations manual exists.

The breach class uses primary dam type and structural height: earth dams
over 30 ft map to `EarthenDamGT30ft`, other known-height earth dams to
`EarthenDamLE30ft`, concrete types to `ConcreteDam`, and other known types
to `Other`. These map respectively to `UserDefined`,
`SimplifiedPhysical`, `FixedWidth`, and `UniqueCase` breach methods.

Screening uses structural-height thresholds of 50 and 100 ft,
max-storage thresholds of 1,000, 10,000, and 100,000 acre-ft, and
drainage-area thresholds of 50 and 250 sq miles. Flood-control dominance
starts at a flood-pool fraction of 0.75. `TypeA` is suggested only for
USACE-sourced flood-risk-reduction dams with at least 10,000 acre-ft of max
storage. The modeling-priority score combines hazard, storage, purpose, and
drainage; priorities 1, 2, 3, and 4 begin at scores of 12, 8, 4, and below 4.

Missing measurements yield `null` for affected classifications and scores,
not an assumed lowest category. An OR-based screening flag is true if any
known condition is true, `null` if the answer remains uncertain, and false
otherwise. `ffrd:` and `ffrd_screening:` are local property namespaces, not
declared STAC extensions.

## Source, photos, and dates

The source inventory was retrieved from
[NID downloads](https://nid.sec.usace.army.mil/nid/#/downloads) on
**2026-09-30**. The Collection links to the
[NID homepage](https://nid.sec.usace.army.mil/nid/#/), and both Collection
and Items link to downloads with `rel=via`. Each Item also links to its
[NID dam page](https://nid.sec.usace.army.mil/nid/#/dams/system/PA00118)
with `rel=related`.

Item `source_retrieved_on` records the download date. Item `datetime` is
instead midnight UTC on that record's `dataUpdated` date; the Collection
temporal extent spans these **record update dates**, not construction or
observation dates.

Items with a photo have a `thumbnail` asset using the NID API's
`thumbnailUrl`. The URLs live in `thumbnail_urls.json` so normal generation
works offline. To fetch them again, add `--refresh-thumbnails`; the command
requires API access and fails if a photo-flagged record lacks a valid
thumbnail. Items without a photo have no thumbnail asset.

**Source quirks:** Item IDs use `nidId-fid` because one `nidId` appears
twice. Two records have HUC4 values outside `0501`; the script preserves all
239 records and computes the Collection extent from them.

## Publish within a larger catalog

```bash
uv run --no-project --with pyproj python metadata/utils/dams/create_nid_collection.py \
  metadata/utils/dams/0501_allegheny_nid-dams.geojson \
  --output /path/to/catalog/dams/collection.json \
  --source-href https://example.org/data/0501_allegheny_nid-dams.geojson \
  --parent-href https://example.org/catalog/allegheny-0501.json \
  --root-href https://example.org/catalog/catalog.json
```

Publish the Collection JSON **and** its adjacent `collection-items/`
directory. Add a `rel=child` link from the containing Catalog; this script
does not edit that Catalog. Publish the original inventory separately if
using `--source-href`; otherwise keep its relative path to the Collection
intact. `--id` changes the Collection ID. Without `--root-href`, a supplied
`--parent-href` is treated as the root Catalog.

The Collection uses `license: other` because the source license has not
been established. Confirm and update it before publication.
