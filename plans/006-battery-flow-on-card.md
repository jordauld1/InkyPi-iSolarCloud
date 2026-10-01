# Plan 006: Show live battery charge/discharge on the battery card

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Revised 2026-10-01** after plan 005's live discovery. Plan 005 Part B now
> computes `metrics["battery_power"]` (kW, positive = charging, `None` when
> unavailable), so this plan only changes the template, the preview fixture,
> and possibly one CSS rule.
>
> **Drift check (run first)**: confirm by reading the code that `_parse_metrics`
> returns `"battery_power"` computed from `ESS_CHARGE_POINT` / `ESS_DISCHARGE_POINT`
> (plan 005 Part B landed). Confirm too that the template's battery card still
> matches the excerpt below. Any mismatch is a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/005-battery-aware-grid-and-usage.md Part B; plans/001 (tests and preview tool)
- **Category**: direction
- **Planned at**: commit `b655bb3`, 2026-10-01 (revised the same day)

## Why this matters

The battery card shows state of charge but not what the battery is doing right
now. The Solar and Grid cards both have a "Now X kW" line, and the battery is
the one flow the dashboard doesn't show live. Plan 005 already fetches the
inverter's charging and discharging power, so this is one template line.

## Current state

The battery card, `isolarcloud/render/isolarcloud.html` (around lines 47-54):

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

The Solar card's sub line, which is the pattern to copy:

```html
      <div class="metric-sub">Now {{ metrics.curr_power }} kW</div>
```

`metrics["battery_power"]`: a float in kW, positive while charging, negative
while discharging, or `None` on plants without a hybrid inverter or when
the optional API call failed.

The narrow/portrait layout (`isolarcloud.css`,
`@media (max-aspect-ratio: 1), (max-width: 480px)`) lays each card out as a
single **row** (`flex-direction: row; justify-content: space-between`), so an
extra child adds a fourth item to that row. That's the overflow risk.

`tools/preview.py` builds metrics with
`ISolarCloud(...)._parse_metrics(SAMPLE, "My Solar Plant")`. After plan 005,
`_parse_metrics` takes an optional third argument `ess_points`.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Tests | `<venv python> -m pytest -q` | all pass |
| Preview | `<venv python> tools/preview.py --inkypi <InkyPi path>` | 9 paths; open `preview/index.html` |

## Scope

**In scope**: `isolarcloud/render/isolarcloud.html` (battery card only),
`isolarcloud/render/isolarcloud.css` (only the rule allowed in step 3),
`tests/test_template.py`, `tools/preview.py` (sample data only),
`README.md` (Battery bullet only).

**Out of scope**: `isolarcloud/isolarcloud.py` (plan 005 owns the
computation), adding a battery series to the chart, and restyling other cards.

## Git workflow

- Branch: `advisor/006-battery-flow`
- Commit: `Show live battery charge/discharge on battery card`
- Do NOT push unless instructed.

## Steps

### Step 1: Tests first

`tests/test_template.py` (render with `metrics["battery_power"]` set directly on the metrics dict):
1. `2.1` → contains `Charging 2.1 kW`.
2. `-0.8` → contains `Discharging 0.8 kW`.
3. `0.02` → contains `Idle`. The threshold is 0.05 kW.
4. `None` → contains none of `Charging`, `Discharging` or `Idle`.

**Verify**: the 4 new tests fail (except possibly #4), and the existing ones pass.

### Step 2: Template and preview

Insert inside the battery card, after the battery bar container's closing `</div>`:

```html
      {% if metrics.battery_power is not none %}
      <div class="metric-sub">
        {% if metrics.battery_power > 0.05 %}Charging {{ metrics.battery_power }} kW{% elif metrics.battery_power < -0.05 %}Discharging {{ (metrics.battery_power | abs) }} kW{% else %}Idle{% endif %}
      </div>
      {% endif %}
```

In `tools/preview.py`, pass ess points to `_parse_metrics` so the preview shows
a charging battery:
`{"p13149": "0", "p13121": "850", "p13126": "2100", "p13150": "0"}`.

**Verify**: `<venv python> -m pytest -q` → all pass.

### Step 3: Layout check at all 8 sizes

Run the preview and open `preview/index.html`, or screenshot each frame. For
each of the 8 frames, confirm that no text is clipped or ellipsized, that
nothing overlaps, and that there's no scrollbar.

- If **only** the narrow/portrait frames (`*_vertical`, `400x300_*`) overflow:
  add exactly this inside the existing `@media (max-aspect-ratio: 1), (max-width: 480px)` block,
  then re-check:
  ```css
  .battery-card .battery-bar-container { display: none; }
  ```
- If landscape frames overflow, or that rule doesn't fix the narrow ones:
  STOP and report which frames fail.

If you can't view the preview, say so explicitly in the report. The reviewer will check it.

### Step 4: README

Change the Battery bullet to: `**Battery** — state of charge (%) with visual bar, and live charge/discharge power`.

## Done criteria

- [ ] `<venv python> -m pytest -q` exits 0
- [ ] `grep -n "Discharging" isolarcloud/render/isolarcloud.html` → 1 match
- [ ] The report lists 8 preview frames as OK, or explicitly says the preview wasn't viewed
- [ ] Only in-scope files changed
- [ ] `plans/README.md` row 006 updated

## STOP conditions

- `metrics["battery_power"]` isn't produced by `_parse_metrics` (plan 005 Part B hasn't landed).
- Overflow can't be fixed by the single permitted CSS rule.

## Maintenance notes

- The 0.05 kW idle threshold hides inverter standby noise.
- A battery series on the chart was deliberately left out. The chart already has four series.
