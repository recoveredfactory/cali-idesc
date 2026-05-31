from pathlib import Path

from cali_geo.defs.catalog import parse_capabilities
from cali_geo.defs.config import partition_key, typename

FIXTURE = Path(__file__).parent / "fixtures" / "wfs_capabilities.xml"


def _records():
    return parse_capabilities(FIXTURE.read_bytes())


def test_parses_all_layers():
    records = _records()
    assert len(records) == 357


def test_keys_are_filesystem_safe_and_reversible():
    for r in _records():
        assert ":" not in r["key"]
        assert "__" in r["key"]
        # round-trips back to the original typename
        assert typename(r["key"]) == r["typename"]
        assert partition_key(r["typename"]) == r["key"]


def test_records_carry_metadata():
    by_key = {r["key"]: r for r in _records()}
    sample = by_key["catastro__cat_bas_construcciones"]
    assert sample["workspace"] == "catastro"
    assert sample["layer"] == "cat_bas_construcciones"
    assert sample["title_es"]
    assert sample["default_crs"].endswith("6249")
    assert sample["bbox"] and len(sample["bbox"]) == 4


def test_expected_workspace_spread():
    workspaces = {r["workspace"] for r in _records()}
    assert "pot_2014" in workspaces
    assert "dapm" in workspaces
    assert len(workspaces) == 23
