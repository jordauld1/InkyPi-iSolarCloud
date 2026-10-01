# Plan 003: Show battery SOC as a whole number, clamped to 0–100

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- isolarcloud/isolarcloud.py isolarcloud/render/isolarcloud.html`
> If either file changed since this plan was written, compare the "Current
> state" excerpts against the live code before proceeding; on a mismatch,
> treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-test-baseline-and-preview.md (test harness)
- **Category**: bug
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

With real API data, the battery card shows **"72.0%"** instead of "72%".
`round(x, 0)` on a float returns a float (`round(72.4, 0) == 72.0`), and Jinja
prints it as `72.0`. The README screenshot used integer mock data, so it hides
the problem. Nothing clamps the value either, so a glitchy reading above 1.0
or below 0 would make the battery bar's `width` exceed 100% or go negative.
While here, the date header prints zero-padded days ("October 01"), which also
looks wrong on the display.

## Current state

`isolarcloud/isolarcloud.py:127` (inside `_parse_metrics`):

```python
        battery_soc = pf("p83252") * 100  # API returns as decimal fraction
```

`isolarcloud/isolarcloud.py:158`:

```python
            "battery_soc": round(battery_soc, 0),
```

`isolarcloud/isolarcloud.py:88` (inside `generate_image`):

```python
        current_date = now.strftime("%A, %B %d")
```

`isolarcloud/render/isolarcloud.html:50-53`:

```html
      <div class="metric-value">{{ metrics.battery_soc }}<span class="metric-unit">%</span></div>
      <div class="battery-bar-container">
        <div class="battery-bar-fill" style="width: {{ metrics.battery_soc }}%;"></div>
      </div>
```

`battery_soc` also flows into the chart history
(`_record_and_load_history`, `"battery_soc": metrics.get("battery_soc", 0)`),
where an int is fine.

Do **not** use `%-d` in `strftime`. It is glibc-only and raises `ValueError` on
Windows, where the tests also run.

Test harness (from plan 001): `tests/conftest.py` provides `plugin`,
`render_dashboard(params)`, `SAMPLE_POINTS` (`p83252` = `"0.72"`). Follow the
style of `tests/test_metrics.py`.

## Commands you will need

| Purpose | Command (Git Bash; on Linux use `.venv/bin/python`) | Expected |
|---|---|---|
| Tests | `.venv/Scripts/python -m pytest -q` | all pass |

## Scope

**In scope**: `isolarcloud/isolarcloud.py` (lines 88, 127, 158 only),
`tests/test_metrics.py`, `tests/test_template.py`, `tests/test_generate_image.py`.

**Out of scope**: the template and CSS (an int renders correctly as is), and
every other metric's rounding. One decimal place is intentional for kWh/kW.

## Git workflow

- Branch: `advisor/003-soc-display`
- Commit: `Show battery SOC as an integer and drop zero-padded day`
- Do NOT push unless instructed.

## Steps

### Step 1: Write failing tests first

In `tests/test_metrics.py` add:
- `test_battery_soc_is_int`: `_parse_metrics(SAMPLE_POINTS, "x")["battery_soc"]` is `72` **and** `isinstance(..., int)`.
- `test_battery_soc_clamped_high`: `{"p83252": "1.2"}` → `100`.
- `test_battery_soc_clamped_low`: `{"p83252": "-0.1"}` → `0`.
- `test_battery_soc_rounds`: `{"p83252": "0.725"}` → `72` or `73` is fine, but it must be an `int`. Assert `isinstance` only, plus `72 <= v <= 73`.

In `tests/test_template.py` add `test_battery_soc_renders_without_decimal`:
render with metrics from `SAMPLE_POINTS` and assert `'72<span class="metric-unit">%' in html`
and `"72.0" not in html`.

In `tests/test_generate_image.py` add `test_current_date_not_zero_padded`:
patch the plugin module's `datetime` so that `datetime.now(tz)` returns
`tz.localize(datetime(2026, 10, 1, 9, 5))` (for example
`monkeypatch.setattr(plugin_mod, "datetime", FixedDatetime)` with a subclass
overriding `now`), run `generate_image` with explicit `ps_id`, and assert
`template_params["current_date"] == "Thursday, October 1"`.

**Verify**: `.venv/Scripts/python -m pytest -q` → the new tests FAIL (int/clamp/render/date), all old tests pass.

### Step 2: Fix SOC

Replace line 158 with:

```python
            "battery_soc": int(round(min(max(battery_soc, 0.0), 100.0))),
```

**Verify**: `.venv/Scripts/python -m pytest -q tests/test_metrics.py tests/test_template.py` → all pass.

### Step 3: Fix the date

Replace line 88 with:

```python
        current_date = f"{now:%A, %B} {now.day}"
```

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass.

## Test plan

Six new tests: int, clamp high, clamp low, rounding type, rendered text, and the date.
The existing characterization test `battery_soc == 72` keeps passing.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` exits 0
- [ ] `grep -n "round(battery_soc, 0)" isolarcloud/isolarcloud.py` → no output
- [ ] `grep -n '%B %d' isolarcloud/isolarcloud.py` → no output
- [ ] Only in-scope files changed (`git status`)
- [ ] `plans/README.md` row 003 updated

## STOP conditions

- `p83252` turns out to be reported as a percentage (0–100) rather than a fraction.
  Signs: the plugin's existing `* 100` would then give values like 7200. Don't
  change the multiplier; report back.
- Any test outside the ones named here starts failing.

## Maintenance notes

- If a later plan adds a battery power or "charging" line (plan 006), it should
  reuse this clamped int, not re-read `p83252`.
