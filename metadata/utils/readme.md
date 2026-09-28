# Metadata utilities

Utilities are organized by data domain. Add a section below when introducing a new utility folder.

## Models

The `models` folder contains scripts for generating standalone HEC-HMS and HEC-RAS STAC Items and for adding derived Parquet assets, version metadata, and source-asset lineage to an existing Item.

## Terrain

The `terrain` folder contains utilities for building STAC metadata for terrain data.

## Basin data

The `basin-data` folder contains a command-line utility for generating a STAC Collection from an S3 prefix with one Item per zip archive. It reads geospatial content directly from S3, writes mirrored STAC outputs, keeps item/collection links relative, stores zip-specific analysis on each item, and places non-zip shared files as collection-level assets.
