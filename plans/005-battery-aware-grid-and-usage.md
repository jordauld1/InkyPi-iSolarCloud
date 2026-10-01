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
- **Depends on**: plans/001-test-baseline-and-preview.md. Plan 003 should land first (same function, trivial conflict otherwise).
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

## Discovery results (filled in by a human)

> **For the human running the script:** run it twice if you can: once in
> daylight while the iSolarCloud app's energy-flow screen shows power going
> **to** the grid, and once at night while it shows power coming **from** the
> grid (or with the battery discharging). Each time, note the app's own
> numbers alongside the script output. Paste only the rows you used, not your
> ps_id.
>
> - **Grid power point**: the point whose magnitude matches the app's grid
>   flow. Note whether it is positive or negative while *importing*, and
>   whether it is in W (matches `p83106` load in size) or kW.
> - **Daily load energy point**: the point matching the app's "Consumption
>   today". Note Wh or kWh.
> - **Battery power** (for plan 006): the point(s) matching the app's battery
>   flow. There may be one signed point, or separate charge and discharge points.

| Quantity | Point id | Unit | Sign / notes | Sample (script value ↔ app value) |
|---|---|---|---|---|
| Grid power | | W / kW | `+` or `-` when importing | |
| Daily load energy | | Wh / kWh | | |
| Battery power (signed) *or* charge power | | W / kW | sign when charging | |
| Battery discharge power (if separate) | | W / kW | | |

## Part B — use the discovered points

Only start when the first two rows of the table above are filled in. If the
**Grid power** row says "not found", do steps 3–4 for daily load only,
leave the grid derivation unchanged, and note that in the report.

### Step 3: Tests first

In `tests/test_metrics.py` add (substituting the discovered ids, sign and units):
1. `test_grid_power_uses_grid_point_when_present`: a night case,
   `{"p83033": "0", "p83106": "1000", "p<GRID>": <value meaning ~0 W>, ...}` → `grid_power == 0.0`
   (not `1.0`, which is what the battery-blind formula gives).
2. `test_grid_power_import_sign`: the grid point at a value meaning 500 W *importing* → `grid_power == 0.5`.
3. `test_grid_power_export_sign`: the grid point at a value meaning 500 W *exporting* → `grid_power == -0.5`.
4. `test_grid_power_falls_back_without_point`: `SAMPLE_POINTS` (no grid point) → `grid_power == -0.85`, unchanged.
5. `test_today_load_uses_load_point`: `SAMPLE_POINTS` plus the load point meaning 15.0 kWh → `today_load == 15.0`,
   and `self_sufficiency == round((15.0 - 1.1) / 15.0 * 100, 1)` (= 92.7).
6. `test_today_load_falls_back_without_point`: `SAMPLE_POINTS` → `today_load == 13.3`, `self_sufficiency == 91.7`, unchanged.
7. `test_self_sufficiency_clamped`: load point meaning 1.0 kWh with import 3.0 kWh → `self_sufficiency == 0.0` (never negative).

**Verify**: the new tests fail, and the old ones pass.

### Step 4: Implement

Add module constants after `POINT_IDS`, filled from the table:

```python
# Battery-aware points (confirmed against a live account, see plans/005)
GRID_POWER_POINT = "<id>"        # grid active power
GRID_POWER_IMPORT_SIGN = <1|-1>  # multiply so that positive = importing
GRID_POWER_TO_W = <1|1000>       # 1 if the point is W, 1000 if kW
LOAD_ENERGY_POINT = "<id>"       # daily household consumption
LOAD_ENERGY_TO_WH = <1|1000>     # 1 if Wh, 1000 if kWh
```

Append both ids to `POINT_IDS` with trailing comments, in the existing style.

In `_parse_metrics`:
- Add a helper next to `pf`:
  ```python
        def pf_opt(key):
            """Parse a point value to float, or None if missing/unparseable."""
            try:
                value = device_points.get(key)
                return None if value is None else float(value)
            except (TypeError, ValueError):
                return None
  ```
- Grid: `grid_raw = pf_opt(f"p{GRID_POWER_POINT}")`. If not `None`,
  `net_power_w = grid_raw * GRID_POWER_TO_W * GRID_POWER_IMPORT_SIGN`.
  Otherwise keep `net_power_w = load_power_w - pv_power_w`, with the comment
  `# Fallback: ignores battery flow`.
- Load: `load_raw = pf_opt(f"p{LOAD_ENERGY_POINT}")`. If not `None`,
  `today_load = round(max(load_raw * LOAD_ENERGY_TO_WH / 1000, 0.0), 1)`.
  Otherwise use the existing derivation, with the comment `# Fallback: includes battery charge`.
- Self-sufficiency, with one formula for both paths:
  ```python
        # Self-sufficiency: share of household use not drawn from the grid
        self_sufficiency = 0.0
        if today_load > 0:
            self_sufficiency = round(min(max((today_load - today_grid_import) / today_load * 100, 0.0), 100.0), 1)
  ```
  On the fallback path this equals the old formula, because the old load
  derivation is `solar − export + import`. Test 6 proves it.

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass.

### Step 5: README wording

In `README.md`'s Dashboard bullets, change:
- `**Used Today** — total household consumption today` → `**Used Today** — household consumption today, as reported by the inverter`
- `**Self Use** — percentage of load covered by solar` → `**Self Use** — share of today's household use not drawn from the grid (solar plus battery)`

**Verify**: `grep -n "not drawn from the grid" README.md` → 1 match.

## Test plan

- Part A: 2 tests for the discovery script's pure functions.
- Part B: 7 metric tests: grid point used, both signs, fallback, load point used, load fallback, clamp.
  Model them on the existing `tests/test_metrics.py`.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` exits 0
- [ ] `tools/discover_points.py` with no env exits 2 and prints no secret values
- [ ] `grep -n "GRID_POWER_POINT\|LOAD_ENERGY_POINT" isolarcloud/isolarcloud.py` → constants defined and used
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
