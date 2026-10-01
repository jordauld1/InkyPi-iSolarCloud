# Plan 006: Show live battery charge/discharge on the battery card

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- isolarcloud/`
> Plans 003, 004, 005 and 008 change these files legitimately. Before starting,
> confirm by reading the code that: `_parse_metrics` returns a `"battery_soc"` int;
> a `GRID_POWER_POINT` constant exists (plan 005 Part B landed); and the
> template's battery card still matches the excerpt below. Any other mismatch is a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/005-battery-aware-grid-and-usage.md (its Discovery
  results table must have a battery power row), plans/001 (tests and preview tool)
- **Category**: direction
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

The battery card shows the state of charge but not what the battery is doing
right now. The Solar and Grid cards both have a "Now X kW" line, and the
battery is the one flow the dashboard doesn't show live. Plan 005's discovery
step identifies the battery power point(s), so adding "Charging 2.1 kW" /
"Discharging 0.8 kW" / "Idle" costs one point and one template line.

## Current state

The battery card, `isolarcloud/render/isolarcloud.html:47-54`:

```html
    <!-- Battery SOC -->
    <div class="metric-card battery-card">
      <div class="metric-label">Battery</div>
      <div class="metric-value">{{ metrics.battery_soc }}<span class="metric-unit">%</span></div>
      <div class="battery-bar-container">
        <div class="battery-bar-fill" style="width: {{ metrics.battery_soc }}%;"></div>
      </div>
    </div>
```

The Solar card's sub line, which is the pattern to copy (`isolarcloud.html:57-61`):

```html
    <div class="metric-card solar-card">
      <div class="metric-label">Solar Today</div>
      <div class="metric-value">{{ metrics.today_energy }}<span class="metric-unit">kWh</span></div>
      <div class="metric-sub">Now {{ metrics.curr_power }} kW</div>
    </div>
```

`_parse_metrics` returns `"battery_power": 0.0` as a hardcoded placeholder
(original line 155). Plan 008 may have removed it. Either way, this plan
defines it properly.

After plan 005, `_parse_metrics` has a `pf_opt(key)` helper (returns float or
`None`) and module constants like `GRID_POWER_POINT` / `GRID_POWER_TO_W`.
Follow that exact style for the battery constants.

The narrow/portrait layout (`isolarcloud.css:200-239`,
`@media (max-aspect-ratio: 1), (max-width: 480px)`) lays each card out as a
single **row** (`flex-direction: row; justify-content: space-between`), so an
extra child adds a fourth item to that row. That's the overflow risk.

## Commands you will need

| Purpose | Command (Git Bash; on Linux use `.venv/bin/python`) | Expected |
|---|---|---|
| Tests | `.venv/Scripts/python -m pytest -q` | all pass |
| Preview | `.venv/Scripts/python tools/preview.py --inkypi ../InkyPi` | 9 paths; open `preview/index.html` |

## Scope

**In scope**: `isolarcloud/isolarcloud.py` (constants, `POINT_IDS`, `_parse_metrics`),
`isolarcloud/render/isolarcloud.html` (battery card only),
`isolarcloud/render/isolarcloud.css` (only the rule allowed in step 4),
`tests/test_metrics.py`, `tests/test_template.py`, `tools/preview.py` (fixture data only),
`README.md` (Battery bullet only).

**Out of scope**: adding a battery series to the chart, changing grid logic,
and restyling other cards.

## Git workflow

- Branch: `advisor/006-battery-flow`
- Commit: `Show live battery charge/discharge on battery card`
- Do NOT push unless instructed.

## Steps

### Step 1: Read the discovery results

Open `plans/005-battery-aware-grid-and-usage.md` and find the "Discovery
results" table's battery rows. One of these cases applies:
- **(a) One signed point**: note its id, unit (W/kW) and the sign when charging.
- **(b) Separate charge and discharge points**: note both ids and units. Both are non-negative magnitudes.
- **(c) Neither row filled, or "not found"**: STOP. Mark BLOCKED ("no battery power point identified").

### Step 2: Tests first

`tests/test_metrics.py`:
1. Charging at 2100 W (expressed in the discovered point's units and sign) → `battery_power == 2.1`.
2. Discharging at 800 W → `battery_power == -0.8`.
3. Point(s) absent → `battery_power is None`.

`tests/test_template.py` (render with `metrics["battery_power"]` set directly):
4. `2.1` → contains `Charging 2.1 kW`.
5. `-0.8` → contains `Discharging 0.8 kW`.
6. `0.02` → contains `Idle`. The threshold is 0.05 kW.
7. `None` → contains neither `Charging`, `Discharging` nor `Idle`.

**Verify**: the new tests fail, and the existing ones pass.

### Step 3: Implement

Constants (case a):
```python
BATTERY_POWER_POINT = "<id>"         # battery power, signed
BATTERY_POWER_CHARGE_SIGN = <1|-1>   # multiply so that positive = charging
BATTERY_POWER_TO_W = <1|1000>
```
or (case b):
```python
BATTERY_CHARGE_POINT = "<id>"
BATTERY_DISCHARGE_POINT = "<id>"
BATTERY_POWER_TO_W = <1|1000>
```
Add the id(s) to `POINT_IDS`. In `_parse_metrics`, compute `battery_power_w`
with `pf_opt`: (a) `value * TO_W * SIGN`; (b) `charge − discharge` when at
least one is present, treating a missing one as 0. The result is `None`
when no point is present. Return
`"battery_power": None if battery_power_w is None else round(battery_power_w / 1000, 2)`,
replacing any existing `"battery_power": 0.0` line.

Template: insert after the battery bar's closing `</div>` and inside the card:

```html
      {% if metrics.battery_power is not none %}
      <div class="metric-sub">
        {% if metrics.battery_power > 0.05 %}Charging {{ metrics.battery_power }} kW{% elif metrics.battery_power < -0.05 %}Discharging {{ (metrics.battery_power | abs) }} kW{% else %}Idle{% endif %}
      </div>
      {% endif %}
```

In `tools/preview.py`, add the battery point(s) to the sample data so the
preview shows "Charging …".

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass.

### Step 4: Layout check at all 8 sizes

Run the preview and open `preview/index.html`. For each of the 8 frames,
confirm that no text is clipped or ellipsized, that nothing overlaps, and that
there's no scrollbar. The cards in the landscape sizes now hold 4 lines: label,
value, bar and sub.

- If **only** the narrow/portrait frames (`*_vertical`, `400x300_*`) overflow:
  add exactly this inside the existing `@media (max-aspect-ratio: 1), (max-width: 480px)` block,
  then re-check:
  ```css
  .battery-card .battery-bar-container { display: none; }
  ```
  (In the row layout, the number and the "Charging" text carry the
  information, so the bar is the one to drop.)
- If landscape frames overflow, or the rule above doesn't fix the narrow
  ones: STOP and report with which frames fail. Don't redesign the card.

If `../InkyPi` isn't available, skip the visual check and say so explicitly in the report.

**Verify**: the preview check is described in your report frame by frame (8 lines, OK/FAIL).

### Step 5: README

Change the Battery bullet to: `**Battery** — state of charge (%) with visual bar, and live charge/discharge power`.

## Test plan

Seven new tests (3 metrics, 4 template), plus a manual preview check across 8 sizes.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` exits 0
- [ ] `grep -n '"battery_power": 0.0' isolarcloud/isolarcloud.py` → no output
- [ ] The report lists 8 preview frames as OK, or explicitly says the preview was skipped
- [ ] Only in-scope files changed
- [ ] `plans/README.md` row 006 updated

## STOP conditions

- The discovery table has no battery data (case c).
- Overflow can't be fixed by the single permitted CSS rule.
- Plan 005 Part B hasn't landed (`pf_opt` / `GRID_POWER_POINT` missing).

## Maintenance notes

- The 0.05 kW idle threshold hides inverter standby noise. If users report
  "Idle" while charging slowly, lower it.
- A natural follow-up is a battery power series on the chart. That was
  deliberately left out, because the chart already has four series on a
  monochrome-ish panel.
