import pytest

from conftest import SAMPLE_POINTS


def test_sample_metrics(plugin):
    m = plugin._parse_metrics(SAMPLE_POINTS, "My Plant")
    for key, expected in {
        "curr_power": 3.45,
        "grid_power": -0.85,
        "load_power": 2.6,
        "today_energy": 18.4,
        "today_grid_feed": 6.2,
        "today_grid_import": 1.1,
        "today_load": 13.3,
        "self_sufficiency": 91.7,
        "total_energy": 12400.0,
    }.items():
        assert m[key] == pytest.approx(expected)
    assert m["battery_soc"] == 72


def test_battery_soc_is_int(plugin):
    value = plugin._parse_metrics(SAMPLE_POINTS, "x")["battery_soc"]
    assert value == 72
    assert isinstance(value, int)


def test_battery_soc_clamped_high(plugin):
    assert plugin._parse_metrics({"p83252": "1.2"}, "x")["battery_soc"] == 100


def test_battery_soc_clamped_low(plugin):
    assert plugin._parse_metrics({"p83252": "-0.1"}, "x")["battery_soc"] == 0


def test_battery_soc_rounds(plugin):
    value = plugin._parse_metrics({"p83252": "0.725"}, "x")["battery_soc"]
    assert isinstance(value, int)
    assert 72 <= value <= 73


def test_empty_points(plugin):
    m = plugin._parse_metrics({}, "My Plant")
    for key in (
        "curr_power", "grid_power", "today_energy", "today_load",
        "self_sufficiency", "battery_soc",
    ):
        assert m[key] == 0


def test_night_metrics(plugin):
    points = {
        "p83033": "0", "p83106": "1000", "p83252": "0.5",
        "p83022": "0", "p83102": "3000",
    }
    m = plugin._parse_metrics(points, "My Plant")
    assert m["grid_power"] == pytest.approx(1.0)
    assert m["today_load"] == pytest.approx(3.0)
    assert m["self_sufficiency"] == pytest.approx(0.0)
    assert m["battery_soc"] == 50


def test_unparseable_points(plugin):
    m = plugin._parse_metrics({"p83252": "--", "p83033": None}, "My Plant")
    assert m["battery_soc"] == 0
    assert m["curr_power"] == pytest.approx(0.0)


def test_plant_name(plugin):
    m = plugin._parse_metrics(SAMPLE_POINTS, "My Plant")
    assert m["plant_name"] == "My Plant"
