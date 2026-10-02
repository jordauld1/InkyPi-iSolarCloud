import pytest

from conftest import SAMPLE_POINTS


def test_sample_metrics(plugin):
    m = plugin._parse_metrics(SAMPLE_POINTS, "My Plant")
    for key, expected in {
        "curr_power": 3.45,
        "grid_power": -0.85,
        "today_energy": 18.4,
        "today_grid_feed": 6.2,
        "today_grid_import": 1.1,
        "today_load": 13.3,
        "self_sufficiency": 91.7,
        "total_energy": 12400.0,
    }.items():
        assert m[key] == pytest.approx(expected)
    assert m["battery_soc"] == 72


def test_no_dead_keys(plugin):
    m = plugin._parse_metrics(SAMPLE_POINTS, "x")
    assert "today_self_use" not in m
    assert "load_power" not in m


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


def test_grid_power_from_ess_import(plugin):
    ess = {"p13149": "1693", "p13121": "0", "p13126": "0", "p13150": "0"}
    m = plugin._parse_metrics(SAMPLE_POINTS, "x", ess)
    assert m["grid_power"] == 1.69


def test_grid_power_from_ess_export(plugin):
    ess = {"p13149": "0", "p13121": "500", "p13126": "0", "p13150": "0"}
    m = plugin._parse_metrics(SAMPLE_POINTS, "x", ess)
    assert m["grid_power"] == -0.5


def test_battery_discharge_not_counted_as_import(plugin):
    points = {"p83033": "0", "p83106": "1000"}
    ess = {"p13149": "0", "p13121": "0", "p13126": "0", "p13150": "1000"}
    m = plugin._parse_metrics(points, "x", ess)
    assert m["grid_power"] == 0.0
    assert m["battery_power"] == -1.0


def test_battery_power_charging(plugin):
    ess = {"p13149": "0", "p13121": "0", "p13126": "2100", "p13150": "0"}
    m = plugin._parse_metrics(SAMPLE_POINTS, "x", ess)
    assert m["battery_power"] == 2.1


def test_fallback_without_ess(plugin):
    m = plugin._parse_metrics(SAMPLE_POINTS, "x")
    assert m["grid_power"] == -0.85
    assert m["battery_power"] is None


def test_today_load_uses_p83118(plugin):
    m = plugin._parse_metrics({**SAMPLE_POINTS, "p83118": "15000"}, "x")
    assert m["today_load"] == 15.0
    assert m["self_sufficiency"] == 92.7


def test_today_load_fallback(plugin):
    m = plugin._parse_metrics(SAMPLE_POINTS, "x")
    assert m["today_load"] == 13.3
    assert m["self_sufficiency"] == 91.7


def test_self_sufficiency_clamped(plugin):
    m = plugin._parse_metrics({"p83118": "1000", "p83102": "3000"}, "x")
    assert m["self_sufficiency"] == 0.0
