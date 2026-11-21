"""Shared I/O and AWS helpers for the HEC STAC command-line utilities."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from pyproj import CRS


def configure_aws_environment(session: boto3.Session) -> None:
    """Expose boto3's resolved credentials to hecstac's S3 readers."""
    credentials = session.get_credentials()
    if credentials is not None:
        frozen = credentials.get_frozen_credentials()
        os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
        if frozen.token:
            os.environ["AWS_SESSION_TOKEN"] = frozen.token
    region = session.region_name or "us-east-1"
    os.environ.setdefault("AWS_REGION", region)
    os.environ.setdefault("AWS_DEFAULT_REGION", region)


def read_text(location: str, s3_client) -> str:
    """Read UTF-8 text from a local path or S3 URI."""
    if location.startswith("s3://"):
        parsed = urlparse(location)
        return (
            s3_client.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))[
                "Body"
            ]
            .read()
            .decode("utf-8")
        )
    return Path(location).read_text(encoding="utf-8")


def resolve_crs(value: str | None, s3_client) -> CRS | None:
    """Resolve literal CRS text or read it from a local/S3 projection file."""
    if value is None:
        return None
    if value.startswith("s3://") or Path(value).is_file():
        value = read_text(value, s3_client).strip()
    return CRS(value)


def output_location(output: str, filename: str) -> str:
    """Join a filename to a local output directory or S3 prefix."""
    if output.startswith("s3://"):
        return f"{output.rstrip('/')}/{filename}"
    return str(Path(output).expanduser().resolve() / filename)


def write_document(location: str, document: dict, s3_client) -> None:
    """Write a JSON document locally or to S3 with a GeoJSON media type."""
    body = json.dumps(document, indent=2).encode("utf-8")
    if location.startswith("s3://"):
        parsed = urlparse(location)
        s3_client.put_object(
            Bucket=parsed.netloc,
            Key=parsed.path.lstrip("/"),
            Body=body,
            ContentType="application/geo+json",
        )
        return
    path = Path(location)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def relative_asset_path(project: str, asset_href: str) -> str | None:
    """Return an asset path relative to the project directory when nested."""
    if project.startswith("s3://") and asset_href.startswith("s3://"):
        project_uri = urlparse(project)
        asset_uri = urlparse(asset_href)
        if project_uri.netloc != asset_uri.netloc:
            return None
        project_dir = Path(project_uri.path.lstrip("/")).parent
        try:
            relative = Path(asset_uri.path.lstrip("/")).relative_to(project_dir)
        except ValueError:
            return None
    elif not project.startswith("s3://") and not asset_href.startswith("s3://"):
        try:
            relative = (
                Path(asset_href).resolve().relative_to(Path(project).resolve().parent)
            )
        except ValueError:
            return None
    else:
        return None

    return relative.as_posix() if relative.parent != Path(".") else None
