# Plan 009: iSolarCloud history spike findings

Run on 2026-10-01 between 21:45 and 22:10 AEST against the owner's account
(one Residential ESS plant, Australia gateway), using `tools/probe_history.py`
and two scratch probes built on the same request conventions. The plant ID is
omitted throughout. The Developer Portal docs were not read; every answer below
comes from live behaviour.

## 1. Endpoint: which Open API endpoint returns per-point time series for a plant?

Answer: `POST {gateway}/openapi/getDevicePointMinuteDataList` works with the
plugin's existing plaintext V1 auth (same headers, `appkey` + `token` in the
body). It serves both the plant (`<ps_id>_11_0_0`) and individual devices, such
as the hybrid inverter (`<ps_id>_14_1_1`). No other endpoint was needed.

## 2. Request shape: exact parameters, timestamp format and timezone, intervals, and maximum range

Answer: param style `a` is the one that works:

```json
{"appkey": "...", "token": "...",
 "ps_key_list": ["<ps_id>_11_0_0"],
 "points": "p83033,p83252",
 "start_time_stamp": "20261001185000",
 "end_time_stamp": "20261001215000",
 "minute_interval": 5}
```

- `ps_key_list` is required. Style `b` (single `ps_key`) returns `result_code 009`, `er_missing_parameter:ps_key_list`.
- `points` must carry the `p` prefix. Style `c` (bare IDs) returns success with an empty `result_data`.
- Timestamps are `yyyyMMddHHmmss` in **plant-local time**. A request for 18:50 to 21:50 local returned samples stamped 18:55 to 21:45.
- Only `minute_interval: 5` was tested.
- **Maximum range is about 3 hours.** Windows of 3.0 and 3.1 hours succeed. 4, 6, 8, 12 and 22 hours all return `result_code 010`, "the query time interval exceeds the maximum limit". A full day therefore needs up to 8 calls in 3-hour chunks.

## 3. Response shape: series keys, timestamps, and units for solar, SOC, grid, and battery power

Answer: `result_data` is an object keyed by ps_key, and each value is a list of
rows: `{"time_stamp": "20261001214500", "p83033": "0.0", "p83252": "0.0"}`.
Values are strings in the same units as the real-time endpoint:

- Solar `p83033` is in W.
- SOC `p83252` (plant) / `p13141` (inverter) is a fraction (0.021 means 2.1%).
- The plant has no grid power point. Grid and battery come from the inverter
  device (see plan 005): import `p13149`, export `p13121`, charge `p13126` and
  discharge `p13150`, all in W and ≥ 0.

Validation: across 94 samples,
`pv + import + discharge − (load + export + charge)` stayed within ±108 W, so the
series are consistent enough to chart.

## 4. Cost: response time, payload size for 00:00 to now, and documented rate limits

Answer: each call took 0.5 to 0.7 s, and 3 hours of 2 points was about 3.1 KB.
A full day from midnight is up to 8 calls per ps_key. The chart needs both the
plant key (solar, SOC) and the inverter key (grid, battery), so that's up to 16
calls (about 10 s) for a cold start. An incremental fetch (only since the last
stored sample) is 2 calls per refresh. Rate limits weren't checked; that needs
the Developer Portal docs.

## 5. Freshness: delay between the latest sample and real time

Answer: at most about 5 minutes. A 21:50 query returned 21:45 as its latest
sample.

## 6. Failure modes: future range, invalid point, and excessive range

Answer:
- **Future range**: `result_code 1`, returning only the past samples inside the window. A window entirely in the future returns an empty `result_data`.
- **Invalid point** (`p99999`): `result_code 1` with an empty `result_data`. It does not error.
- **Excessive range** (over about 3 h): `result_code 010` with the "maximum limit" message.
- **Data gaps**: today's plant and inverter series have no rows before about 14:00,
  although the API accepted the requests. Gaps are simply missing rows, so a
  consumer must not assume a continuous series.

## Recommendation: Go, with an incremental design

The endpoint fixes exactly the weaknesses of the local-only chart:
- a coarse series at InkyPi's default hourly refresh;
- history lost on reinstall;
- no record of grid and battery flow before plan 005.

It also gives battery-aware import and export history, because it reads the
same inverter points as plan 005. Build it as follows:

- Keep plan 004's per-plant local history file as the store and the fallback. It becomes a cache of API samples rather than one-sample-per-refresh.
- On each refresh, fetch from the latest cached `time_stamp` (or 00:00 on a cold start or a new day) to now, in chunks of at most 3 hours, for both ps_keys. Merge rows by `time_stamp`, then drop rows from previous days.
- Map rows onto the existing `chart` template contract (`labels`, `battery_soc`, `solar_kw`, `grid_import_kw`, `grid_export_kw`), so the template doesn't change. Labels come from `time_stamp` as `HH:MM`.
- Read the inverter's ps_key from the same `getDeviceList` result plan 005 already fetches (pass it through instead of calling it twice). Without a hybrid inverter, chart solar and SOC only, and keep deriving grid from the existing fallback.
- Treat every history call as optional. On any `RuntimeError`, log a warning and fall back to appending the current real-time reading to the local cache, as today. Use the existing 30 s timeout, and cap the cold-start backfill at 8 chunks per key.
- Extra API calls per day: at a 1-hour refresh, about 2 per refresh plus one cold start, so roughly 50 a day. At a 5-minute refresh, 2 per refresh, so roughly 580 a day. Check the Developer Portal's published limits before release. If they're tight, fetch history only every Nth refresh.
- Tests: a fake session returning chunked rows, covering a cold start (8 chunks), an incremental fetch, a day rollover, a gap in rows, a failure falling back to local append, and an empty series.

This should be a separate build plan (plan 010), written against the code after
plans 004 and 005 have landed.
