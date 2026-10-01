import json
import re
from datetime import datetime, timedelta

import pytest
import pytz


@pytest.fixture
def now():
    return pytz.timezone("Australia/Brisbane").localize(datetime(2026, 3, 15, 12, 0))


def test_first_history_entry(plugin, tmp_path, now):
    history = plugin._record_and_load_history(
        {"battery_soc": 72, "curr_power": 3.45, "grid_power": -0.85}, now, "4242",
    )
    assert len(history) == 1
    assert history[0]["time"] == "12:00"
    assert history[0]["grid_import_kw"] == pytest.approx(0)
    assert history[0]["grid_export_kw"] == pytest.approx(0.85)
    assert history[0]["solar_kw"] == pytest.approx(3.45)
    assert history[0]["battery_soc"] == 72
    assert (tmp_path / "history_4242.json").exists()


def test_grid_import(plugin, now):
    history = plugin._record_and_load_history({"grid_power": 1.2}, now, "4242")
    assert history[0]["grid_import_kw"] == pytest.approx(1.2)
    assert history[0]["grid_export_kw"] == pytest.approx(0)


def test_yesterday_is_filtered(plugin, tmp_path, now):
    (tmp_path / "history_4242.json").write_text(
        json.dumps([{"ts": "2026-03-14T23:50:00+10:00"}]), encoding="utf-8",
    )
    history = plugin._record_and_load_history({}, now, "4242")
    assert len(history) == 1
    assert history[0]["time"] == "12:00"


def test_invalid_json_is_ignored(plugin, tmp_path, now):
    (tmp_path / "history_4242.json").write_text("not json", encoding="utf-8")
    history = plugin._record_and_load_history({}, now, "4242")
    assert len(history) == 1


def test_entries_remain_in_time_order(plugin, now):
    plugin._record_and_load_history({}, now, "4242")
    history = plugin._record_and_load_history({}, now + timedelta(minutes=10), "4242")
    assert len(history) == 2
    assert history[0]["time"] == "12:00"
    assert history[1]["time"] == "12:10"


def test_full_day_kept_at_short_intervals(plugin, tmp_path, now):
    start = now.replace(hour=6, minute=0)
    entries = [
        {"ts": (start + timedelta(minutes=i)).isoformat(),
         "time": (start + timedelta(minutes=i)).strftime("%H:%M")}
        for i in range(200)
    ]
    (tmp_path / "history_4242.json").write_text(json.dumps(entries), encoding="utf-8")

    result = plugin._record_and_load_history({}, now, "4242")
    assert len(result) == 201
    assert result[0]["time"] == "06:00"


def test_cap_applies_after_today_filter(plugin, tmp_path, now):
    today = now.strftime("%Y-%m-%d")
    entries = ([{"ts": "2026-03-14T07:00:00+10:00"}] * 10
               + [{"ts": f"{today}T07:00:00+10:00"}] * 1500)
    (tmp_path / "history_4242.json").write_text(json.dumps(entries), encoding="utf-8")

    result = plugin._record_and_load_history({}, now, "4242")
    assert len(result) == plugin.HISTORY_MAX_ENTRIES
    assert all(entry["ts"].startswith(today) for entry in result)


def test_history_is_per_plant(plugin, tmp_path, now):
    first = plugin._record_and_load_history({}, now, "1")
    second = plugin._record_and_load_history({}, now, "2")
    assert len(first) == 1
    assert len(second) == 1
    assert (tmp_path / "history_1.json").exists()
    assert (tmp_path / "history_2.json").exists()


def test_ps_id_is_sanitized(plugin, tmp_path, now):
    plugin._record_and_load_history({}, now, "../../evil")
    assert not (tmp_path.parent / "evil.json").exists()
    files = list(tmp_path.glob("history_*.json"))
    assert len(files) == 1
    assert re.fullmatch(r"history_[A-Za-z0-9_-]+\.json", files[0].name)


def test_non_list_json_treated_as_empty(plugin, tmp_path, now):
    (tmp_path / "history_4242.json").write_text('{"a": 1}', encoding="utf-8")
    result = plugin._record_and_load_history({}, now, "4242")
    assert len(result) == 1


def test_malformed_entries_dropped(plugin, tmp_path, now):
    today = now.strftime("%Y-%m-%d")
    entries = [{"no_ts": 1}, "x", {"ts": f"{today}T07:00:00+10:00", "time": "07:00"}]
    (tmp_path / "history_4242.json").write_text(json.dumps(entries), encoding="utf-8")
    result = plugin._record_and_load_history({}, now, "4242")
    assert len(result) == 2
    assert result[0]["time"] == "07:00"


def test_legacy_history_file_removed(plugin, tmp_path, now):
    legacy = tmp_path / "history.json"
    legacy.write_text(json.dumps([{"ts": now.isoformat()}]), encoding="utf-8")
    plugin._record_and_load_history({}, now, "4242")
    assert not legacy.exists()
