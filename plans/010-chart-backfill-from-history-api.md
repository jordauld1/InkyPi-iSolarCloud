# Plan 010: Fill the chart from iSolarCloud's 5-minute history

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report; do not improvise. When done, update the status row for this plan
> in `plans/README.md`, unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8606da5..HEAD -- isolarcloud/ tests/conftest.py`
> Plans 006 (template battery line), 007 (auto-detect logging and the "No data
> for Power Station ID" check in `generate_image`) and 008 (cleanup) may have
> landed; those changes are expected. Any change to `_fetch_ess_points`, the
> history section, or the `chart` block in `generate_image` is drift and a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (adds API calls on every refresh; must never break the dashboard)
- **Depends on**: plans 004, 005 (DONE), 009 (spike, DONE: recommendation Go)
- **Category**: direction
- **Planned at**: commit `8606da5`, 2026-10-02

## Why this matters

The chart only gets one point per refresh. At InkyPi's default 1-hour cycle,
that's about 12 points across daylight, and the history resets whenever the
plugin is reinstalled. iSolarCloud stores 5-minute samples for every plant.
Plan 009's spike (`plans/009-spike-findings.md`) proved they can be fetched
with the plugin's existing auth. After this plan, every refresh shows a smooth
5-minute curve for the whole day, including battery-aware grid import/export,
whatever the refresh rate. The local history file becomes a cache plus a fallback.

## Facts from the spike (verified live on 2026-10-01; do not re-derive)

- Endpoint: `POST {api_base}/getDevicePointMinuteDataList` (same base URL and headers as every other call; go through `_SungrowAPI._api_call`).
- Payload (exact field names; other shapes fail):
  ```json
  {"appkey": "...", "token": "...",
   "ps_key_list": ["<ps_key>"],
   "points": "p83033,p83252,p83106",
   "start_time_stamp": "20261001185000",
   "end_time_stamp": "20261001215000",
   "minute_interval": 5}
  ```
  `points` is a comma-separated string with the `p` prefix. Timestamps are `%Y%m%d%H%M%S` in **plant-local time**.
- **Maximum window is 3 hours.** A 4-hour or longer window returns `result_code "010"` ("exceeds the maximum limit"), which `_api_call` raises as `RuntimeError`.
- Response: `result_data` is an object keyed by ps_key, and each value is a list of rows:
  `{"time_stamp": "20261001214500", "p83033": "0.0", "p83252": "0.0"}`. Values are strings.
- Invalid points or future windows return success with no rows. Data gaps are just missing rows.
- Units match the real-time points: `p83033` solar W, `p83252` SOC as a fraction (0.021 = 2.1%), `p83106` load W.
  Hybrid inverter (device_type 14) points: `p13149` import W, `p13121` export W (both ≥ 0).
- About 0.6 s per call.

## Current state

`isolarcloud/isolarcloud.py` at `8606da5`:

`generate_image` (lines 80-113, abridged):

```python
        # Fetch real-time data
        device_points = api.get_device_realtime_data(token, ps_id, POINT_IDS)
        ess_points = self._fetch_ess_points(api, token, ps_id)
        ...
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        ...
        history = self._record_and_load_history(metrics, now, ps_id)

        template_params = {
            ...
            "history": history,
            "chart": {
                "labels": [h.get("time", "") for h in history],
                "battery_soc": [h.get("battery_soc", 0) for h in history],
                "solar_kw": [h.get("solar_kw", 0) for h in history],
                "grid_import_kw": [h.get("grid_import_kw", 0) for h in history],
                "grid_export_kw": [h.get("grid_export_kw", 0) for h in history],
            },
        }
```

`_fetch_ess_points` (lines 127-140):

```python
    def _fetch_ess_points(self, api, token, ps_id):
        try:
            devices = api.get_device_list(token, ps_id)
            for device in devices:
                key = device.get("ps_key")
                if str(device.get("device_type")) == str(ESS_DEVICE_TYPE) and key:
                    return api.get_device_realtime_data(
                        token, ps_id, ESS_POINT_IDS, device_type=ESS_DEVICE_TYPE, ps_key=key,
                    )
            return {}
        except RuntimeError as e:
            logger.warning("iSolarCloud battery/grid points unavailable, using estimates: %s", e)
            return {}
```

The history section (lines 225-285): `HISTORY_MAX_ENTRIES = 1440`;
`_history_path(ps_id)` returns `history_<safe id>.json`; and
`_record_and_load_history(metrics, now, ps_id)` loads, keeps today's dict
entries, appends a live entry, caps, saves atomically (`.tmp` then `os.replace`),
deletes the legacy `history.json`, and returns the list. Each entry has the keys
`ts` (ISO with offset), `time` (`HH:MM`), `battery_soc` (int %), `solar_kw`,
`grid_import_kw` and `grid_export_kw`.

`_SungrowAPI` methods: `login`, `get_plant_list`, `get_device_list`,
`get_device_realtime_data(token, ps_id, point_ids, device_type=11, ps_key=None)`,
and `_api_call(endpoint, payload)`, which raises `RuntimeError` on HTTP or API errors.

Tests: `tests/conftest.py` `FakeSession` serves queued responses per endpoint
(FIFO) and raises `AssertionError` when none is queued.
`tests/test_generate_image.py` has helpers `capture_render`, `queue_login` and
`queue_realtime` (the last also queues an empty `getDeviceList`), plus a
`FixedDatetime` pattern in `test_current_date_not_zero_padded` for freezing `now`.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Tests | `<venv python> -m pytest -q` | all pass |
| Preview | `<venv python> tools/preview.py --inkypi <InkyPi path>` | 9 paths |

## Scope

**In scope**: `isolarcloud/isolarcloud.py`, `tests/conftest.py` (FakeSession
default responses only), `tests/test_generate_image.py`, `tests/test_api.py`,
`tests/test_backfill.py` (create), and `README.md` (the chart sentence and API Details only).

**Out of scope**: the template and CSS (the `chart` contract stays as is),
`tools/preview.py`, `tools/*` scripts, and plan files. Don't change real-time
metric parsing.

## Git workflow

- Branch: `advisor/010-chart-backfill`
- Commits: `Add minute-data API call and backfill`, `Use API history for the chart`
- Do NOT push unless instructed.

## Steps

### Step 1: API method (test first)

`tests/test_api.py` gets `test_minute_data`. Queue `getDevicePointMinuteDataList` →
`api_ok({"1_11_0_0": [{"time_stamp": "20261001120000", "p83033": "100"}]})`.
Call `api.get_minute_data("tok", "1_11_0_0", ["83033", "83252"], "20261001090000", "20261001120000")`.
Assert that it returns the list of rows, and that the request JSON has
`ps_key_list == ["1_11_0_0"]`, `points == "p83033,p83252"`, the two timestamps,
`minute_interval == 5`, and a `token` header of `"tok"`. Add a second case where
`result_data` is `{}` → returns `[]`.

Implement in `_SungrowAPI`:

```python
    def get_minute_data(self, token, ps_key, point_ids, start_ts, end_ts, interval=5):
        """Return 5-minute history rows for one ps_key (window must be <= 3 hours)."""
```

The payload is as in "Facts". Return `(result.get("result_data") or {}).get(ps_key) or []`.

**Verify**: `<venv python> -m pytest -q tests/test_api.py` → all pass.

### Step 2: Return the inverter ps_key from `_fetch_ess_points`

Rename it to `_fetch_ess(self, api, token, ps_id)` and return a tuple
`(ps_key, points)`: `(key, realtime_points)` when the inverter is found,
`(None, {})` otherwise and on `RuntimeError` (same warning). Update the one
caller in `generate_image`: `ess_key, ess_points = self._fetch_ess(api, token, ps_id)`.
Behaviour is otherwise unchanged.

**Verify**: `<venv python> -m pytest -q` → all pass. Existing tests don't call the method directly; if one does, update only the call shape.

### Step 3: Backfill logic (tests first, in a new file)

Create `tests/test_backfill.py`. Use a **fake API object**, not `FakeSession`:

```python
class FakeApi:
    """Serves minute rows per ps_key, filtered to the requested window; records calls."""
    def __init__(self, rows_by_key, fail=False):
        self.rows_by_key = rows_by_key  # {ps_key: [row, ...]}
        self.fail = fail
        self.calls = []
    def get_minute_data(self, token, ps_key, point_ids, start_ts, end_ts, interval=5):
        self.calls.append((ps_key, start_ts, end_ts))
        if self.fail:
            raise RuntimeError("iSolarCloud: Error:the query time interval exceeds the maximum limit")
        return [r for r in self.rows_by_key.get(ps_key, []) if start_ts <= r["time_stamp"] <= end_ts]
```

Use `tz = pytz.timezone("Australia/Brisbane")` and `now = tz.localize(datetime(2026, 10, 1, 7, 10))`.
Plant key `"1_11_0_0"`, inverter key `"1_14_1_1"`. Use a helper to make rows
every 5 minutes from 00:00 to 07:05.

Signature under test:
`plugin._backfill_history(api, token, ps_id, ess_key, now, tz, history)` → the merged list (also saved to the history file).
`history` is what `_record_and_load_history` returned, i.e. today's local entries ending with the live reading.

Tests:
1. `test_cold_start_chunks`: empty local history apart from the live entry. The API calls
   are, for each key, windows `000000-030000`, `030000-060000`, `060000-071000`
   (timestamps formatted `20261001HHMMSS`): 3 calls per key and 6 in total, plant key first.
2. `test_entries_converted`: plant row `{"time_stamp": "20261001064500", "p83033": "2859", "p83252": "0.021", "p83106": "723"}`
   with inverter row `{"time_stamp": "20261001064500", "p13149": "0", "p13121": "52"}` → an entry with
   `time == "06:45"`, `solar_kw == 2.86`, `battery_soc == 2`, `grid_import_kw == 0.0`, `grid_export_kw == 0.05`, `src == "api"`, and a
   `ts` that starts with `"2026-10-01T06:45:00+10:00"`.
3. `test_no_ess_derives_grid`: `ess_key=None`, plant row with pv 0 and load 1000 → `grid_import_kw == 1.0`, `grid_export_kw == 0.0`;
   only the plant key is called.
4. `test_live_entry_kept_after_last_api_sample`: API rows to 07:05, live entry at 07:10 → the last element is the live entry (no `src` key).
   A live entry at 07:00 (before the last API row) is dropped.
5. `test_incremental_fetch`: pre-save the history file with API entries (`src: "api"`) up to 06:55 today.
   Calls are one per key, starting at `20261001065500` and ending `20261001071000`.
   The result has no duplicate `time` values for API entries.
6. `test_day_rollover`: the history file holds API entries from yesterday; `history` passed in has only today's live entry → cold start from 00:00 today.
7. `test_failure_falls_back`: `FakeApi(..., fail=True)` → returns the `history` argument unchanged, logs a WARNING containing `history unavailable`, and raises nothing.
8. `test_gap_rows`: rows only from 05:00 → entries start at 05:00, with no error.
9. `test_max_chunks`: `now` at 23:55 with no API entries → at most 8 calls per key.
10. `test_merged_history_saved`: after a cold start, the saved file contains the API entries (so the next refresh is incremental).

Implement `_backfill_history` and its helpers in the history section. Rules:
- Constants: `HISTORY_CHUNK = timedelta(hours=3)`, `HISTORY_MAX_CHUNKS = 8`,
  `HISTORY_PLANT_POINTS = ["83033", "83252", "83106"]`, `HISTORY_ESS_POINTS = [ESS_IMPORT_POINT, ESS_EXPORT_POINT]`.
  Add `from datetime import timedelta` (keep `datetime`).
- `start` = the latest `ts` among entries with `src == "api"` in `history` (parse with `datetime.fromisoformat`),
  or midnight today (`tz.localize(datetime(now.year, now.month, now.day))`) when there are none.
  Fetch `[start, now]` in consecutive windows of at most 3 hours (the last one ends at `now`), at most 8 windows per key,
  plant key first, then the inverter key if `ess_key`. Format with `%Y%m%d%H%M%S` in plant-local time (`astimezone(tz)`).
- Join rows by `time_stamp`. For each plant row, build an API entry:
  `solar_kw = round(pv / 1000, 2)`, `battery_soc = int(round(min(max(soc * 100, 0), 100)))`.
  If the inverter row for the same `time_stamp` exists, `grid_import_kw = round(imp / 1000, 2)` and `grid_export_kw = round(exp / 1000, 2)`.
  Otherwise derive `net = load - pv`: `import = max(net, 0)` and `export = max(-net, 0)` (rounded /1000, 2 dp).
  Unparseable values count as 0. `ts = tz.localize(datetime.strptime(time_stamp, "%Y%m%d%H%M%S")).isoformat()`, `time = HH:MM`, `src = "api"`.
- Merge: the API entries already in `history` plus the new ones, de-duplicated by `ts` (new wins); then
  the non-API entries from `history` whose `ts` is later than the latest API `ts`. Sort by
  parsed `ts`, apply `HISTORY_MAX_ENTRIES`, save with the same atomic write as
  `_record_and_load_history` (extract a small `_save_history(path, history)` helper and use it in both places), and return.
- Wrap the fetch in `try/except RuntimeError as e`:
  `logger.warning("iSolarCloud history unavailable, using local readings: %s", e)` and `return history`.

**Verify**: `<venv python> -m pytest -q tests/test_backfill.py` → 10 passed; the full suite passes.

### Step 4: Wire it into `generate_image`, and keep the old tests working

- After `history = self._record_and_load_history(metrics, now, ps_id)`, add:
  `history = self._backfill_history(api, token, ps_id, ess_key, now, tz, history)`.
- Extract the `chart` dict into a `@staticmethod _chart_series(history)` and use it in `template_params`.
- `tests/conftest.py`: give `FakeSession` a `self.defaults = {}` and a `default(endpoint, response)` method.
  When an endpoint's queue is empty and a default exists, return the default instead of raising. Behaviour is otherwise unchanged.
- `tests/test_generate_image.py`: in `queue_realtime`, also call
  `fake_session.default("getDevicePointMinuteDataList", api_ok({}))` (no rows → chart from local readings, as before).
  All existing tests must pass without other changes.
- Add `test_generate_image_uses_api_history`: freeze `now` at `2026-10-01 00:20` in `UTC` (FixedDatetime pattern),
  with explicit `ps_id "777"`, no inverter (empty `getDeviceList`), and queue one minute-data response
  `api_ok({"777_11_0_0": [{"time_stamp": "20261001000500", "p83033": "0", "p83252": "0.5", "p83106": "400"}, {"time_stamp": "20261001001000", "p83033": "0", "p83252": "0.5", "p83106": "400"}]})`.
  Assert `template_params["chart"]["labels"][:2] == ["00:05", "00:10"]` and that `chart["grid_import_kw"][0] == 0.4`.

**Verify**: `<venv python> -m pytest -q` → all pass.

### Step 5: README

- Replace the sentence "Over the course of a day, a timeseries chart builds up showing battery SOC, solar generation, grid import, and grid export." with:
  "A chart shows today's battery SOC, solar generation, grid import and grid export at 5-minute resolution, fetched from iSolarCloud's history on each refresh (falling back to the plugin's own readings if history is unavailable)."
- In API Details, add one sentence: "Chart history comes from getDevicePointMinuteDataList, fetched incrementally in windows of up to 3 hours."

**Verify**: `grep -n "getDevicePointMinuteDataList" README.md` → 1 match.

## Test plan

Step 1 adds 2 API tests, step 3 adds 10 backfill tests, and step 4 adds 1
wiring test. All existing tests keep passing, with `FakeSession` defaults the
only harness change.

## Done criteria

- [ ] `<venv python> -m pytest -q` exits 0
- [ ] `grep -n "_backfill_history\|get_minute_data\|_chart_series" isolarcloud/isolarcloud.py` → each defined and used
- [ ] `grep -n "_fetch_ess_points" isolarcloud/ tests/ -r` → no output
- [ ] Only in-scope files changed
- [ ] `plans/README.md` row 010 updated

## STOP conditions

- The drift check shows `_fetch_ess_points`, the history section or the `chart` block changed.
- Existing tests can only pass by changing their assertions (not just the `queue_realtime` helper).
- The design needs a template change.

## Maintenance notes

- Steady state is 1 to 2 extra API calls per refresh (plant, plus inverter if present). A cold start (first refresh of the day, or after a reinstall) is up to 16 calls, about 10 s.
- If Sungrow publishes tight rate limits, fetch history every Nth refresh. The cache makes that safe.
- API entries carry `src: "api"`. Live readings don't, and they're only kept after the latest API sample.
