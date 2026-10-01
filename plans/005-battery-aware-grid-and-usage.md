# Plan 005: Use the inverter's own grid power and load readings (battery-aware)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **This plan has a mandatory human checkpoint.** Part A (steps 1–2) builds a
> discovery script. A human with real iSolarCloud credentials must then run it
> and fill in the "Discovery results" table below. **Do not start Part B until
> that table is filled in.** If it's empty when you reach Part B, mark the plan
> BLOCKED ("waiting for discovery results") and stop.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- isolarcloud/isolarcloud.py README.md`
> Plans 003/004 legitimately change `isolarcloud.py` (SOC line ~158, date line
> ~88, the history section). Any change inside `POINT_IDS` or `_parse_metrics`
> other than the SOC line is drift and a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (changes the headline numbers; depends on live API facts)
- **Depends on**: plans/001 and plans/003 (both DONE). Part A DONE; Part B revised 2026-10-01 after the live discovery run.
- **Category**: bug
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

The plugin targets Sungrow hybrid systems with a battery (it shows battery
SOC), but it *derives* grid flow and household usage from solar and load
alone, ignoring the battery:

- **Live grid power** is computed as `load − pv`. At night, with the battery
  covering a 1 kW load, the dashboard says "Now 1 kW in" and the chart draws
  a red import line, while the real grid flow is about 0. At midday, solar
  charging the battery is shown as export. The chart's Import/Export series are
  recorded from the same wrong value.
- **"Used Today"** is computed as `solar − export + import`, which silently
  includes whatever went into the battery. Midday it over-reports by the
  battery's net charge. **"Self Use"** inherits the same error.

Sungrow exposes plant-level points that already account for the battery.
GoSungrow's published point list names `p83549` "Grid active power", and
`p83011` / `p83097` are daily consumption candidates. We haven't confirmed
which ones this account returns, or their units and sign. Part A finds out.
Part B switches to them, falling back to today's derivation when they're
missing.

## Current state

`isolarcloud/isolarcloud.py:19-28`:

```python
# Plant-level measuring point IDs (device_type = 11)
POINT_IDS = [
    "83022",  # Daily Yield of Plant (Wh)
    "83024",  # Plant Total Yield (Wh)
    "83033",  # Plant Power (W)
    "83072",  # Feed-in Energy Today (Wh)
    "83102",  # Energy Purchased Today (Wh)
    "83106",  # Load Power (W)
    "83252",  # Battery Level (SOC) (%)
]
```

`isolarcloud/isolarcloud.py:110-150` (`_parse_metrics`, abridged; line 158
may already read `int(round(...))` if plan 003 landed):

```python
    def _parse_metrics(self, device_points, plant_name):
        """Extract display metrics from the device real-time data point map."""

        def pf(key, default=0.0):
            """Parse a point value to float."""
            try:
                return float(device_points.get(key, default))
            except (TypeError, ValueError):
                return default

        # Values from the API are in Wh for energy, W for power
        today_energy_wh = pf("p83022")
        ...
        load_power_w = pf("p83106")
        ...
        # Net power: positive = importing, negative = exporting
        net_power_w = load_power_w - pv_power_w

        # Home usage today: solar consumed locally + grid import
        today_load = round(today_energy - today_grid_feed + today_grid_import, 1)
        if today_load < 0:
            today_load = 0.0

        # Self-sufficiency: proportion of load covered by solar
        self_sufficiency = 0.0
        if today_load > 0 and today_energy > 0:
            solar_self_used = today_energy - today_grid_feed
            if solar_self_used > 0:
                self_sufficiency = round((solar_self_used / today_load) * 100, 1)
```

and in the returned dict: `"grid_power": round(net_power_w / 1000, 2)`.
The template and history treat `grid_power > 0` as importing and `< 0` as exporting.

The API client (`_SungrowAPI`, lines 220-296) and how it calls the Open API:
`POST {api_base}/{endpoint}` with JSON body and headers
`{"Content-Type": "application/json;charset=UTF-8", "sys_code": "901", "x-access-key": <secret>, "token": <token when present>}`.
`login` takes `{"appkey", "user_account", "user_password"}` and returns
`result_data.token` with `login_state == "1"`. `getDeviceRealTimeData` takes
`{"appkey", "token", "device_type": 11, "point_id_list": [...], "ps_key_list": ["<ps_id>_11_0_0"]}`
and returns `result_data.device_point_list[0].device_point` = `{"p83022": "...", "device_name": "...", ...}`.
Regional base URLs are in `API_GATEWAYS` (lines 12-17).

Point names published by GoSungrow (https://github.com/MickMake/GoSungrow/blob/master/EXAMPLES.md).
GoSungrow normalizes values to kW/kWh, but this plugin receives raw W/Wh:

| Point | Name |
|---|---|
| 83002 | Inverter AC Power |
| 83006 | Meter Daily Yield |
| 83011 | Meter E-daily Consumption |
| 83022 | Daily Yield of Plant |
| 83024 | Plant Total Yield |
| 83032 | Meter AC Power |
| 83033 | Plant Power |
| 83072 | Daily Feed-in Energy |
| 83097 | Daily Load Energy Consumption from PV |
| 83102 | Daily Purchased Energy |
| 83106 | Load Power |
| 83119 | Daily Feed-in Energy (PV) |
| 83252 | Battery Level (SOC) |
| 83549 | Grid active power |

## Commands you will need

| Purpose | Command (Git Bash; on Linux use `.venv/bin/python`) | Expected |
|---|---|---|
| Tests | `.venv/Scripts/python -m pytest -q` | all pass |
| Discovery (human, real creds) | `ISOLARCLOUD_USERNAME=... ISOLARCLOUD_PASSWORD=... ISOLARCLOUD_APPKEY=... ISOLARCLOUD_SECRET=... ISOLARCLOUD_REGION=australia .venv/Scripts/python tools/discover_points.py` | prints plants and points |

## Scope

**In scope**: `tools/discover_points.py` (create), `tests/test_discover_points.py` (create),
`isolarcloud/isolarcloud.py` (`POINT_IDS`, `_parse_metrics`, new module constants),
`tests/test_metrics.py`, `README.md` (Dashboard bullets only), and this plan
file's "Discovery results" table (the human fills it in; you only read it).

**Out of scope**:
- Battery charge/discharge display. That's plan 006, which reuses this plan's discovery output.
- The template, CSS and history code: they already consume `grid_power`
  (positive = import), so they need no change.
- Never print, log or write credentials or the session token anywhere.

## Git workflow

- Branch: `advisor/005-battery-aware-grid`
- Commits: `Add iSolarCloud point discovery script` (Part A), `Use inverter grid power and load energy` (Part B)
- Do NOT push unless instructed.

## Part A — discovery script

### Step 1: Write `tools/discover_points.py`

A standalone script using only `requests` (do **not** import the plugin or
InkyPi). Behaviour:

- Reads `ISOLARCLOUD_USERNAME`, `ISOLARCLOUD_PASSWORD`, `ISOLARCLOUD_APPKEY`,
  `ISOLARCLOUD_SECRET` from the environment. Optionally reads
  `ISOLARCLOUD_REGION` (one of `global`, `europe`, `australia`, `international`;
  default `global`, with the same URLs as `API_GATEWAYS` in the plugin) and
  `ISOLARCLOUD_PS_ID`. If any of the four credentials are missing, print which
  key names are missing (names only) and `sys.exit(2)`.
- CLI flags: `--start 83001`, `--end 83999`, `--chunk 50`, `--delay 0.5` (seconds between calls).
- `api_call(base, endpoint, payload, secret, token=None)`: the same headers
  and error handling as the plugin's `_api_call`. Raise `RuntimeError` with
  `result_msg` on a non-`"1"` result code.
- Logs in. Calls `getPowerStationList` (`curPage` 1, `size` 100) and prints a
  "Plants" section: one line per plant, `ps_id  ps_name`. Uses
  `ISOLARCLOUD_PS_ID` if set, otherwise the first plant.
- For point ids `start..end` in chunks of `chunk`, calls
  `getDeviceRealTimeData` (device_type 11, `ps_key_list` `["<ps_id>_11_0_0"]`)
  and collects every key matching `^p\d+$` whose value is not `None`, `""` or `"--"`.
  If a chunk returns an API error, print `chunk <a>-<b>: <msg>` and continue.
- Prints a "Points" section sorted by id: `p83549   -812.0   Grid active power`,
  with the name taken from a `KNOWN_NAMES` dict holding the table in "Current
  state" (blank when unknown).
- Prints a footer reminding the user to fill in the table in `plans/005-battery-aware-grid-and-usage.md`.
- Never prints the password, appkey, secret or token.

Keep `parse_points(device_point)` (dict → sorted list of `(id, value)`) and
`chunks(start, end, size)` as pure functions so they can be tested.

**Verify**: `.venv/Scripts/python tools/discover_points.py; echo $?` with no env vars set → lists the 4 missing key names, then `2`.

### Step 2: Tests for the pure parts

`tests/test_discover_points.py` imports the script with
`importlib.util.spec_from_file_location("discover_points", ROOT / "tools" / "discover_points.py")`.
Tests:
1. `chunks(83001, 83010, 4)` → `[(83001, 83004), (83005, 83008), (83009, 83010)]` (inclusive ranges).
2. `parse_points({"p83549": "-812", "p83011": None, "p83097": "--", "device_name": "x", "p83252": "0"})` → `[("83252", "0"), ("83549", "-812")]`.

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass.

**Then stop.** Mark this plan `BLOCKED (waiting for discovery results)` in
`plans/README.md` and report: "Part A done. A human must run
`tools/discover_points.py` and fill in the Discovery results table."

## Discovery results (filled in 2026-10-01 from a live run; the plan was revised to match)

Ran `tools/discover_points.py` (plant level, device_type 11) plus a device-level
scan and a day of 5-minute history, against the owner's account (Residential
ESS, one Sungrow hybrid inverter). App reference at the same moment: solar 0 W,
load 1.8 kW, battery 0% and idle, grid **importing** 1.8 kW; today production
4.3 kWh and consumption 7.9 kWh.

**Key finding: there is no plant-level grid power point.** `p83549` isn't
returned for this plant. Live grid and battery power only exist as
**device-level** points on the hybrid inverter (device_type 14). Find its
`ps_key` with the Open API `getDeviceList` (`{"appkey", "token", "ps_id", "curPage": 1, "size": 100}`,
which returns `result_data.pageList[]` with `device_type` and `ps_key`, e.g. `"<ps_id>_14_1_1"`).

| Quantity | Point | Level | Unit | Sign / notes | Evidence |
|---|---|---|---|---|---|
| Grid import power | `p13149` | device 14 | W | always ≥ 0 | 1693 at night, equal to load, with pv 0 and battery idle (app: importing 1.8 kW) |
| Grid export power | `p13121` | device 14 | W | always ≥ 0 | 52 at 16:00 while exporting |
| Battery charging power | `p13126` | device 14 | W | always ≥ 0 | 1993 at 16:00 with pv 2859 |
| Battery discharging power | `p13150` | device 14 | W | always ≥ 0 | 1378 at 18:00 with pv 0 |
| Daily load energy | `p83118` | plant (11) | Wh | | 8000. GoSungrow names it "Energy Used"; the app showed 7.9 kWh |

Validation: across 94 five-minute samples today,
`pv(p83033) + import + discharge − (load(p13119) + export + charge)` stayed
within ±108 W, and the daily counters balance exactly (4.3 + 3.2 + 2.6 = 8.0 + 0.0 + 2.1).

## Part B — use the discovered points (revised design)

Part A is already merged. Its files, `tools/discover_points.py` and
`tests/test_discover_points.py`, are out of scope for Part B.

Design: after the plant call, make two more Open API calls. `getDeviceList`
finds the hybrid inverter (`device_type` 14). `getDeviceRealTimeData` reads
its four power points. Grid power is `import − export`, and battery power is
`charge − discharge`. Both are exact, with no sign ambiguity. If the plant has
no device_type 14, or either call fails, **fall back** to today's battery-blind
derivation and log a warning. The dashboard must never fail because of these
optional calls.

**Revised scope for Part B**: `isolarcloud/isolarcloud.py`,
`tests/test_metrics.py`, `tests/test_api.py`, `tests/test_generate_image.py`,
and `README.md` (Dashboard bullets and the API Details paragraph only).

### Step 3: Tests first

`tests/test_api.py`:
1. `test_device_list`: queue `getDeviceList` → `api_ok({"pageList": [{"device_type": 14, "ps_key": "1_14_1_1"}]})`.
   `api.get_device_list("tok", "1")` returns that list, and the request JSON has `ps_id == "1"`, `curPage == 1`, `size == 100`.
2. `test_realtime_data_for_device`: `api.get_device_realtime_data("tok", "1", ["13149"], device_type=14, ps_key="1_14_1_1")`
   sends `device_type == 14` and `ps_key_list == ["1_14_1_1"]`.
   The existing call without these kwargs still sends `"<ps_id>_11_0_0"` and 11. Don't change that test.

`tests/test_metrics.py`. `_parse_metrics` gains an optional third argument `ess_points`:
3. `test_grid_power_from_ess_import`: `SAMPLE_POINTS` + ess `{"p13149": "1693", "p13121": "0", "p13126": "0", "p13150": "0"}` → `grid_power == 1.69`.
4. `test_grid_power_from_ess_export`: ess `{"p13149": "0", "p13121": "500", "p13126": "0", "p13150": "0"}` → `grid_power == -0.5`.
5. `test_battery_discharge_not_counted_as_import`: night, plant `{"p83033": "0", "p83106": "1000"}`, ess import 0, export 0, charge 0, discharge 1000
   → `grid_power == 0.0` (the old formula gives 1.0) and `battery_power == -1.0`.
6. `test_battery_power_charging`: ess charge 2100, discharge 0 (import/export 0) → `battery_power == 2.1`.
7. `test_fallback_without_ess`: `_parse_metrics(SAMPLE_POINTS, "x")`, no ess → `grid_power == -0.85` (unchanged) and `battery_power is None`.
8. `test_today_load_uses_p83118`: `SAMPLE_POINTS` + `{"p83118": "15000"}` → `today_load == 15.0`, `self_sufficiency == 92.7`.
9. `test_today_load_fallback`: `SAMPLE_POINTS` → `today_load == 13.3`, `self_sufficiency == 91.7` (unchanged).
10. `test_self_sufficiency_clamped`: `{"p83118": "1000", "p83102": "3000"}` → `self_sufficiency == 0.0`.

`tests/test_generate_image.py`:
- Change the helper `queue_realtime` so it also queues
  `fake_session.queue("getDeviceList", api_ok({"pageList": []}))` (no ESS → fallback). All existing tests must keep passing unchanged.
- 11. `test_ess_points_used`: queue login, plant realtime (`SAMPLE_POINTS`), `getDeviceList` with
  `[{"device_type": 22, "ps_key": "777_22_247_1"}, {"device_type": 14, "ps_key": "777_14_1_1"}]`, then a second
  `getDeviceRealTimeData` returning device_point `{"p13149": "0", "p13121": "300", "p13126": "1000", "p13150": "0"}`.
  Run with `ps_id "777"`. Assert the second realtime call used `ps_key_list == ["777_14_1_1"]` and `device_type == 14`;
  `template_params["metrics"]["grid_power"] == -0.3`; and `template_params["metrics"]["battery_power"] == 1.0`.
  (The per-endpoint FIFO in `FakeSession` serves the plant response first, then the device one.)
- 12. `test_ess_failure_falls_back`: the same, but `getDeviceList` returns `FakeResponse(200, {"result_code": "E00001", "result_msg": "nope"})`
  and there's no second realtime response. `generate_image` still returns the sentinel, and `metrics["grid_power"] == -0.85`.

**Verify**: the new tests fail, and every pre-existing test passes.

### Step 4: Implement

1. Constants after `POINT_IDS`, matching its comment style:
   ```python
   # Hybrid inverter (device_type 14) power points, all W and >= 0
   ESS_DEVICE_TYPE = 14
   ESS_IMPORT_POINT = "13149"     # Purchased power (from grid)
   ESS_EXPORT_POINT = "13121"     # Export power (to grid)
   ESS_CHARGE_POINT = "13126"     # Battery charging power
   ESS_DISCHARGE_POINT = "13150"  # Battery discharging power
   ESS_POINT_IDS = [ESS_IMPORT_POINT, ESS_EXPORT_POINT, ESS_CHARGE_POINT, ESS_DISCHARGE_POINT]
   ```
   Append `"83118",  # Daily Load Consumption (Wh)` to `POINT_IDS`.
2. `_SungrowAPI`:
   - Add `get_device_list(self, token, ps_id)` (`getDeviceList`, payload as above) → `result_data.pageList` or `[]`.
   - Change `get_device_realtime_data(self, token, ps_id, point_ids, device_type=11, ps_key=None)`.
     `ps_key` defaults to `f"{ps_id}_11_0_0"`, and the payload's `device_type` uses the argument.
3. `ISolarCloud._fetch_ess_points(self, api, token, ps_id)`: call `get_device_list`, pick the first
   device with `str(d.get("device_type")) == str(ESS_DEVICE_TYPE)` and a non-empty `ps_key`, then
   return `api.get_device_realtime_data(token, ps_id, ESS_POINT_IDS, device_type=ESS_DEVICE_TYPE, ps_key=key)`.
   Return `{}` if there's no such device. Wrap the whole body in `try/except RuntimeError as e`:
   log `logger.warning("iSolarCloud battery/grid points unavailable, using estimates: %s", e)` and return `{}`.
4. In `generate_image`, right after the plant `get_device_realtime_data` call:
   `ess_points = self._fetch_ess_points(api, token, ps_id)`. Then pass it:
   `metrics = self._parse_metrics(device_points, plant_name, ess_points)`.
5. `_parse_metrics(self, device_points, plant_name, ess_points=None)`:
   - Add a helper `pf_opt(points, key)`, returning a float or `None` when the key is missing or unparseable.
   - `imp = pf_opt(ess, f"p{ESS_IMPORT_POINT}")`, `exp = ...`. If **both** are not `None`,
     `net_power_w = imp - exp`. Otherwise keep `net_power_w = load_power_w - pv_power_w`,
     with the comment `# Fallback: ignores battery flow`.
   - `chg`, `dis` the same way. If **either** is not `None`,
     `battery_power = round(((chg or 0.0) - (dis or 0.0)) / 1000, 2)`; otherwise `battery_power = None`.
     Return it as `"battery_power"`, replacing the hardcoded `0.0`. Positive means charging.
   - Load: `load_wh = pf_opt(device_points, "p83118")`. If not `None`,
     `today_load = round(max(load_wh / 1000, 0.0), 1)`. Otherwise use the existing derivation,
     with the comment `# Fallback: includes battery charge`.
   - Self-sufficiency (one formula for both paths; on the fallback path it equals the old one):
     ```python
             # Self-sufficiency: share of household use not drawn from the grid
             self_sufficiency = 0.0
             if today_load > 0:
                 self_sufficiency = round(min(max((today_load - today_grid_import) / today_load * 100, 0.0), 100.0), 1)
     ```

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass.

### Step 5: README wording

In `README.md`'s Dashboard bullets, change:
- `**Used Today** — total household consumption today` → `**Used Today** — household consumption today, as reported by the inverter`
- `**Self Use** — percentage of load covered by solar` → `**Self Use** — share of today's household use not drawn from the grid (solar plus battery)`

In the "API Details" section, after the paragraph that mentions `getDeviceRealTimeData`, add one paragraph:
`On hybrid (battery) systems it also reads the inverter's grid and battery power via getDeviceList and getDeviceRealTimeData, so live grid flow accounts for the battery.`

**Verify**: `grep -n "not drawn from the grid" README.md` → 1 match; `grep -n "getDeviceList" README.md` → 1 match.

## Test plan

- Part A: 2 tests for the discovery script's pure functions.
- Part B: 12 tests (2 API, 8 metrics, 2 generate_image), as listed in step 3.
  Model them on the existing tests in the same files.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` exits 0
- [ ] `tools/discover_points.py` with no env exits 2 and prints no secret values
- [ ] `grep -n "ESS_POINT_IDS\|_fetch_ess_points" isolarcloud/isolarcloud.py` → defined and used
- [ ] `grep -n '"battery_power": 0.0' isolarcloud/isolarcloud.py` → no output
- [ ] The Discovery results table is filled in (by the human) before the Part B commit
- [ ] Only in-scope files changed
- [ ] `plans/README.md` row 005 updated (BLOCKED after Part A, DONE after Part B)

## STOP conditions

- The Discovery results table is empty when you reach Part B. Mark BLOCKED.
- Neither a grid power point nor a daily load point was found. Report, and
  suggest the alternative: derive grid from a battery power point
  (`grid = load − pv + battery_charge − battery_discharge`). Do not implement it unprompted.
- The human's notes show the grid point's sign flipping inconsistently
  between samples. Report; don't guess.
- `getDeviceRealTimeData` rejects chunks of 50 for every chunk. Report the
  error text; the human can retry with `--chunk 10`.

## Maintenance notes

- Fallbacks are deliberate. Plants without a meter may not report the grid
  point, and they keep the old behaviour.
- History entries recorded before this change used the old grid derivation.
  Today's chart may show a step at the deploy time, and that's expected.
- Reviewer: check the sign constant against the human's samples, and that
  no credential or token can reach stdout in `discover_points.py`.
