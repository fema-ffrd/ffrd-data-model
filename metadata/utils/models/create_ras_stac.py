#!/usr/bin/env python3
"""Create standalone STAC Items from an HEC-RAS project."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import boto3
import pystac
from pyproj import CRS
from hecstac.ras.assets import RAS_ASSET_CLASSES
from hecstac.ras.item import RASModelItem
from hecstac.ras.parser import PlanFile, ProjectFile
from hecstac.ras.utils import find_model_files

from stac_utils import (
    configure_aws_environment,
    output_location,
    relative_asset_path,
    resolve_crs,
    write_document,
)


RAS_FILE_TYPE_OVERRIDES = (
    (
        re.compile(r".+\.bco\d{2}(?:\.txt)?$", re.IGNORECASE),
        "UnsteadyComputationOutput",
        "text/plain",
        ["ras-unsteady-computation-output"],
        "HEC-RAS unsteady-flow computation output.",
    ),
    (
        re.compile(r".+\.ic\.o\d{2}$", re.IGNORECASE),
        "InitialConditionsFile",
        "text/plain",
        ["ras-initial-conditions"],
        "Initial conditions file for an unsteady-flow plan.",
    ),
    (
        re.compile(r".+\.zip$", re.IGNORECASE),
        "ModelArchive",
        "application/zip",
        ["ras-model-archive"],
        "Archive containing HEC-RAS model files.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create active-input and/or all-asset STAC Items for an HEC-RAS project."
    )
    parser.add_argument(
        "project", help="Local path or s3:// URI of the HEC-RAS .prj file"
    )
    parser.add_argument(
        "--output", required=True, help="Local output directory or s3:// output prefix"
    )
    parser.add_argument(
        "--projection",
        help="CRS text (for example EPSG:5070), or a local/S3 file containing WKT",
    )
    parser.add_argument(
        "--scope",
        choices=("active", "all", "both"),
        default="active",
        help="Asset scope to generate (default: active)",
    )
    parser.add_argument(
        "--id",
        dest="item_id",
        help="Base STAC Item ID (default: project filename stem)",
    )
    parser.add_argument(
        "--filename", help="Output filename; only valid when generating one scope"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Discover matching project assets recursively",
    )
    parser.add_argument(
        "--no-simplify", action="store_true", help="Do not simplify the model footprint"
    )
    parser.add_argument(
        "--lightweight",
        action="store_true",
        help="Skip footprint calculation and retain hecstac's placeholder geometry",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip PySTAC validation before writing",
    )
    args = parser.parse_args()
    if args.filename and args.scope == "both":
        parser.error("--filename cannot be used with --scope both")
    return args


def sibling_location(parent_file: str, referenced_file: str) -> str:
    """Resolve a model's filename-only reference beside its parent file."""
    if parent_file.startswith("s3://"):
        return f"{parent_file.rsplit('/', 1)[0]}/{Path(referenced_file).name}"
    return str(Path(parent_file).resolve().parent / Path(referenced_file).name)


def active_asset_paths(project: str, discovered: list[str]) -> list[str]:
    """Derive the project, current plan, and that plan's geometry/flow inputs."""
    project_file = ProjectFile(project)
    current_plan = project_file.plan_current
    if current_plan is None:
        raise ValueError(f"HEC-RAS project has no Current Plan: {project}")

    current_plan = sibling_location(project, current_plan)
    plan_file = PlanFile(current_plan)
    required = {
        project,
        current_plan,
        sibling_location(current_plan, plan_file.geometry_file),
        sibling_location(current_plan, plan_file.flow_file),
    }
    discovered_by_name = {Path(path).name.lower(): path for path in discovered}
    selected: list[str] = []

    for required_path in required:
        name = Path(required_path).name.lower()
        if name not in discovered_by_name:
            raise FileNotFoundError(
                f"Active model input was not found: {required_path}"
            )
        selected.append(discovered_by_name[name])

        companion_name = f"{name}.hdf"
        if companion_name in discovered_by_name:
            selected.append(discovered_by_name[companion_name])

    return sorted(set(selected))


def ras_file_type(asset_href: str) -> tuple[str, str | None, list[str], str] | None:
    """Return file type, media type, roles, and description for a RAS asset."""
    for pattern, file_type, media_type, roles, description in RAS_FILE_TYPE_OVERRIDES:
        if pattern.fullmatch(asset_href):
            return file_type, media_type, roles, description

    # Prefer specific compound suffixes (for example .p01.hdf and .ic.o01)
    # over broad suffixes such as .hdf, .o01, and .txt.
    classes = sorted(RAS_ASSET_CLASSES, key=lambda cls: len(cls.regex_parse_str), reverse=True)
    for asset_class in classes:
        if re.fullmatch(asset_class.regex_parse_str, asset_href, re.IGNORECASE):
            return (
                asset_class.__name__.removesuffix("Asset"),
                getattr(asset_class, "__media_type__", None),
                list(asset_class.__roles__),
                asset_class.__description__,
            )
    return None


def apply_ras_file_types(document: dict) -> None:
    """Apply consistent hecstac file-type metadata to serialized assets."""
    for asset in document["assets"].values():
        classification = ras_file_type(asset["href"])
        if classification is None:
            continue
        file_type, media_type, roles, description = classification
        if file_type == "Prj" and asset.get("roles") == ["ras-project"]:
            file_type = "ProjectFile"
            media_type = asset.get("type")
            roles = asset["roles"]
            description = asset.get("description", description)
        asset["hecstac:file_type"] = file_type
        if media_type:
            asset["type"] = media_type
        if roles:
            asset["roles"] = roles
        asset["description"] = description


def create_item(
    project: str,
    assets: list[str],
    item_id: str,
    crs: CRS | None,
    projection_source: str | None,
    scope: str,
    destination: str,
    simplify_geometry: bool,
    lightweight: bool,
    validate: bool,
    s3_client,
) -> dict:
    item = RASModelItem.from_prj(
        ras_project_file=project,
        stac_id=item_id,
        crs=crs,
        simplify_geometry=simplify_geometry,
        assets=assets,
    )
    item.set_self_href(destination)
    item.properties["hecstac:asset_scope"] = scope
    item.properties["hecstac:asset_count"] = len(item.assets)
    if projection_source:
        item.properties["hecstac:projection_source"] = projection_source

    document = item.to_dict(lightweight=lightweight)
    apply_ras_file_types(document)
    for asset in document["assets"].values():
        relative_path = relative_asset_path(project, asset["href"])
        if relative_path:
            asset["hecstac:relative_path"] = relative_path
    if validate:
        pystac.Item.from_dict(document).validate()
    write_document(destination, document, s3_client)
    return document


def main() -> None:
    args = parse_args()
    session = boto3.Session()
    configure_aws_environment(session)
    s3_client = session.client("s3")

    project = args.project
    base_id = args.item_id or Path(project).stem
    crs = resolve_crs(args.projection, s3_client)
    discovered = find_model_files(project, recursive=args.recursive)
    if not discovered:
        raise FileNotFoundError(f"No matching model assets found for {project}")

    scopes = ("active", "all") if args.scope == "both" else (args.scope,)
    for scope in scopes:
        assets = (
            active_asset_paths(project, discovered) if scope == "active" else discovered
        )
        item_id = f"{base_id}-active-inputs" if scope == "active" else base_id
        filename = args.filename or f"{item_id}.json"
        destination = output_location(args.output, filename)
        document = create_item(
            project=project,
            assets=assets,
            item_id=item_id,
            crs=crs,
            projection_source=args.projection,
            scope="active-inputs" if scope == "active" else "all-matching-assets",
            destination=destination,
            simplify_geometry=not args.no_simplify,
            lightweight=args.lightweight,
            validate=not args.no_validate,
            s3_client=s3_client,
        )
        print(f"Wrote {destination} ({len(document['assets'])} assets)")


if __name__ == "__main__":
    main()
