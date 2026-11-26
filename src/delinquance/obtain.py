"""Obtain: download the SSMSI departmental base and the map outline, with a version manifest."""

import hashlib
import json
import logging
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from delinquance import RAW_DIR, REPORTS_DIR

log = logging.getLogger(__name__)

API = "https://www.data.gouv.fr/api/1/datasets/621df2954fa5a3b5a023e23c/"
DEP_RESOURCE_ID = "2b27a675-e3bf-41ef-a852-5fb9ab483967"
# Simplified department outlines (IGN Admin Express, Licence Ouverte), pinned to one commit.
GEOJSON_URL = (
    "https://raw.githubusercontent.com/gregoiredavid/france-geojson/"
    "5d34ee6d0140c29f785fdb047d9329f1aab58833/departements-version-simplifiee.geojson"
)
GEOJSON_SHA256 = "c08a1ad48299763b50ef649f05a911c1021500c94719a1aa22a9d06191e43fc3"

RAW_CSV = RAW_DIR / "delinquance_departements.csv"
RAW_GEOJSON = RAW_DIR / "departements.geojson"
MANIFEST = REPORTS_DIR / "data_version.json"


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def find_resource(metadata: dict, resource_id: str) -> dict:
    """Return the resource with this id, so a renamed file URL is still found."""
    for resource in metadata["resources"]:
        if resource["id"] == resource_id:
            return resource
    raise LookupError(f"resource {resource_id} not found in dataset {metadata.get('id')}")


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    digest.update(path.read_bytes())
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        dest.write_bytes(response.read())
    log.info("downloaded %s (%d bytes)", dest.name, dest.stat().st_size)


def check_hash(path: Path, expected: str, algorithm: str) -> None:
    actual = file_hash(path, algorithm)
    if actual != expected:
        raise ValueError(f"{path.name}: {algorithm} {actual} does not match {expected}")


def build_manifest(metadata: dict, resource: dict, csv_path: Path) -> dict:
    return {
        "dataset_id": metadata["id"],
        "dataset_title": metadata["title"].strip(),
        "dataset_last_modified": metadata["last_modified"],
        "license": metadata.get("license"),
        "resource_id": resource["id"],
        "resource_title": resource["title"],
        "resource_url": resource["url"],
        "resource_last_modified": resource["last_modified"],
        "sha256": file_hash(csv_path),
        "size_bytes": csv_path.stat().st_size,
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "geojson_url": GEOJSON_URL,
        "geojson_sha256": GEOJSON_SHA256,
    }


def run() -> None:
    metadata = fetch_json(API)
    resource = find_resource(metadata, DEP_RESOURCE_ID)
    log.info("dataset last modified %s", metadata["last_modified"])
    download(resource["url"], RAW_CSV)
    checksum = resource.get("checksum") or {}
    if checksum.get("type") and checksum.get("value"):
        check_hash(RAW_CSV, checksum["value"], checksum["type"])
    download(GEOJSON_URL, RAW_GEOJSON)
    check_hash(RAW_GEOJSON, GEOJSON_SHA256, "sha256")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(metadata, resource, RAW_CSV)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    log.info("wrote %s", MANIFEST.relative_to(MANIFEST.parents[1]))
