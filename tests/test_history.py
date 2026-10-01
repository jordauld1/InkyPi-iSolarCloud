import json
from datetime import datetime, timedelta

import pytest
import pytz


@pytest.fixture
def now():
    return pytz.timezone("Australia/Brisbane").localize(datetime(2026, 3, 15, 12, 0))


def test_first_history_entry(plugin, tmp_path, now):
    history = plugin._record_and_load_history(
        {"battery_soc": 72, "curr_power": 3.45, "grid_power": -0.85}, now,
    )
    assert len(history) == 1
    assert history[0]["time"] == "12:00"
    assert history[0]["grid_import_kw"] == pytest.approx(0)
    assert history[0]["grid_export_kw"] == pytest.approx(0.85)
    assert history[0]["solar_kw"] == pytest.approx(3.45)
    assert history[0]["battery_soc"] == 72
    assert (tmp_path / "history.json").exists()


def test_grid_import(plugin, now):
    history = plugin._record_and_load_history({"grid_power": 1.2}, now)
    assert history[0]["grid_import_kw"] == pytest.approx(1.2)
    assert history[0]["grid_export_kw"] == pytest.approx(0)


def test_yesterday_is_filtered(plugin, tmp_path, now):
    (tmp_path / "history.json").write_text(
        json.dumps([{"ts": "2026-03-14T23:50:00+10:00"}]), encoding="utf-8",
    )
    history = plugin._record_and_load_history({}, now)
    assert len(history) == 1
    assert history[0]["time"] == "12:00"


def test_invalid_json_is_ignored(plugin, tmp_path, now):
    (tmp_path / "history.json").write_text("not json", encoding="utf-8")
    history = plugin._record_and_load_history({}, now)
    assert len(history) == 1


def test_entries_remain_in_time_order(plugin, now):
    plugin._record_and_load_history({}, now)
    history = plugin._record_and_load_history({}, now + timedelta(minutes=10))
    assert len(history) == 2
    assert history[0]["time"] == "12:00"
    assert history[1]["time"] == "12:10"
