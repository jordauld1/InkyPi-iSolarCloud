"""Synthetic minute-history coverage; no live iSolarCloud calls."""
from datetime import datetime, timedelta
import json

import pytz


PLANT_KEY = "1_11_0_0"
ESS_KEY = "1_14_1_1"
TZ = pytz.timezone("Australia/Brisbane")
NOW = TZ.localize(datetime(2026, 10, 1, 7, 10))


class FakeApi:
    """Serves minute rows per ps_key, filtered to the requested window; records calls."""

    def __init__(self, rows_by_key, fail=False):
        self.rows_by_key = rows_by_key
        self.fail = fail
        self.calls = []

    def get_minute_data(self, token, ps_key, point_ids, start_ts, end_ts, interval=5):
        self.calls.append((ps_key, start_ts, end_ts))
        if self.fail:
            raise RuntimeError("iSolarCloud: Error:the query time interval exceeds the maximum limit")
        return [
            r for r in self.rows_by_key.get(ps_key, [])
            if start_ts <= r["time_stamp"] <= end_ts
        ]


def minute_rows(start_hour=0, start_minute=0, end_hour=7, end_minute=5):
    start = datetime(2026, 10, 1, start_hour, start_minute)
    end = datetime(2026, 10, 1, end_hour, end_minute)
    rows = []
    while start <= end:
        rows.append({
            "time_stamp": start.strftime("%Y%m%d%H%M%S"),
            "p83033": "100", "p83252": "0.5", "p83106": "400",
        })
        start += timedelta(minutes=5)
    return rows


def local_history(plugin, now=NOW):
    return plugin._record_and_load_history({}, now, "1")


def backfill(plugin, api, history, ess_key=ESS_KEY, now=NOW):
    return plugin._backfill_history(api, "tok", "1", ess_key, now, TZ, history)


def test_cold_start_chunks(plugin):
    api = FakeApi({PLANT_KEY: minute_rows(), ESS_KEY: minute_rows()})
    backfill(plugin, api, local_history(plugin))
    expected = [
        ("20261001000000", "20261001030000"),
        ("20261001030000", "20261001060000"),
        ("20261001060000", "20261001071000"),
    ]
    assert api.calls == [
        (key, start, end)
        for key in (PLANT_KEY, ESS_KEY)
        for start, end in expected
    ]


def test_entries_converted(plugin):
    stamp = "20261001064500"
    api = FakeApi({
        PLANT_KEY: [{"time_stamp": stamp, "p83033": "2859", "p83252": "0.021", "p83106": "723"}],
        ESS_KEY: [{"time_stamp": stamp, "p13149": "0", "p13121": "52"}],
    })
    result = backfill(plugin, api, local_history(plugin))
    entry = next(h for h in result if h["time"] == "06:45")
    assert entry["solar_kw"] == 2.86
    assert entry["battery_soc"] == 2
    assert entry["grid_import_kw"] == 0.0
    assert entry["grid_export_kw"] == 0.05
    assert entry["src"] == "api"
    assert entry["ts"].startswith("2026-10-01T06:45:00+10:00")


def test_no_ess_derives_grid(plugin):
    api = FakeApi({PLANT_KEY: [{
        "time_stamp": "20261001064500", "p83033": "0", "p83252": "0.5", "p83106": "1000",
    }]})
    result = backfill(plugin, api, local_history(plugin), ess_key=None)
    entry = next(h for h in result if h.get("src") == "api")
    assert entry["grid_import_kw"] == 1.0
    assert entry["grid_export_kw"] == 0.0
    assert all(key == PLANT_KEY for key, _, _ in api.calls)


def test_live_entry_kept_after_last_api_sample(plugin):
    api = FakeApi({PLANT_KEY: minute_rows()})
    live = local_history(plugin)[-1]
    result = backfill(plugin, api, [live], ess_key=None)
    assert result[-1] == live
    assert "src" not in result[-1]

    early = {**live, "ts": TZ.localize(datetime(2026, 10, 1, 7)).isoformat(), "time": "07:00"}
    result = backfill(plugin, api, [early], ess_key=None)
    assert early not in result
    assert result[-1]["time"] == "07:05"


def test_incremental_fetch(plugin):
    prior = [{
        "ts": TZ.localize(datetime(2026, 10, 1, 6, 55)).isoformat(),
        "time": "06:55", "src": "api", "solar_kw": 0.1,
    }]
    with open(plugin._history_path("1"), "w") as f:
        json.dump(prior, f)
    history = local_history(plugin)
    api = FakeApi({PLANT_KEY: minute_rows(6, 55), ESS_KEY: minute_rows(6, 55)})
    result = backfill(plugin, api, history)
    assert api.calls == [
        (PLANT_KEY, "20261001065500", "20261001071000"),
        (ESS_KEY, "20261001065500", "20261001071000"),
    ]
    api_times = [h["time"] for h in result if h.get("src") == "api"]
    assert len(api_times) == len(set(api_times))


def test_day_rollover(plugin):
    yesterday = [{
        "ts": TZ.localize(datetime(2026, 9, 30, 23, 55)).isoformat(),
        "time": "23:55", "src": "api",
    }]
    with open(plugin._history_path("1"), "w") as f:
        json.dump(yesterday, f)
    history = local_history(plugin)
    api = FakeApi({})
    backfill(plugin, api, history, ess_key=None)
    assert api.calls[0] == (PLANT_KEY, "20261001000000", "20261001030000")


def test_failure_falls_back(plugin, caplog):
    history = local_history(plugin)
    api = FakeApi({}, fail=True)
    with caplog.at_level("WARNING"):
        result = backfill(plugin, api, history)
    assert result == history
    assert "history unavailable" in caplog.text


def test_gap_rows(plugin):
    api = FakeApi({PLANT_KEY: minute_rows(5)})
    result = backfill(plugin, api, local_history(plugin), ess_key=None)
    api_entries = [h for h in result if h.get("src") == "api"]
    assert api_entries[0]["time"] == "05:00"


def test_max_chunks(plugin):
    now = TZ.localize(datetime(2026, 10, 1, 23, 55))
    api = FakeApi({})
    backfill(plugin, api, local_history(plugin, now), now=now)
    assert len([call for call in api.calls if call[0] == PLANT_KEY]) <= 8
    assert len([call for call in api.calls if call[0] == ESS_KEY]) <= 8


def test_merged_history_saved(plugin):
    api = FakeApi({PLANT_KEY: minute_rows(6, 45, 7, 5)})
    result = backfill(plugin, api, local_history(plugin), ess_key=None)
    with open(plugin._history_path("1")) as f:
        saved = json.load(f)
    assert saved == result
    assert any(h.get("src") == "api" for h in saved)
