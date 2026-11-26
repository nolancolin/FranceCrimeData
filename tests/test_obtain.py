import hashlib

import pytest

from delinquance.obtain import build_manifest, check_hash, find_resource

METADATA = {
    "id": "ds",
    "title": " Base ",
    "last_modified": "2026-07-09",
    "license": "lov2",
    "resources": [
        {"id": "a", "title": "A", "url": "https://x/a.csv", "last_modified": "2026-07-01"},
        {"id": "b", "title": "B", "url": "https://x/b.csv", "last_modified": "2026-07-02"},
    ],
}


def test_find_resource_by_id():
    assert find_resource(METADATA, "b")["url"] == "https://x/b.csv"
    with pytest.raises(LookupError):
        find_resource(METADATA, "missing")


def test_check_hash(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes(b"abc")
    check_hash(path, hashlib.sha1(b"abc").hexdigest(), "sha1")
    with pytest.raises(ValueError):
        check_hash(path, "0" * 40, "sha1")


def test_manifest_records_version(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes(b"abc")
    manifest = build_manifest(METADATA, METADATA["resources"][0], path)
    assert manifest["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert manifest["resource_url"] == "https://x/a.csv"
    assert manifest["dataset_title"] == "Base"
