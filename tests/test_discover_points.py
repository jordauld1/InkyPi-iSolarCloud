"""Tests for the discovery script's pure helpers."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "discover_points", ROOT / "tools" / "discover_points.py"
)
discover_points = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discover_points)


def test_chunks_uses_inclusive_ranges():
    assert discover_points.chunks(83001, 83010, 4) == [
        (83001, 83004),
        (83005, 83008),
        (83009, 83010),
    ]


def test_parse_points_keeps_populated_points_in_id_order():
    assert discover_points.parse_points({
        "p83549": "-812",
        "p83011": None,
        "p83097": "--",
        "device_name": "x",
        "p83252": "0",
    }) == [("83252", "0"), ("83549", "-812")]
