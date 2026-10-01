# Plan 007: Make choosing a power station easy, and fail loudly on a wrong ID

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- isolarcloud/isolarcloud.py isolarcloud/settings.html README.md`
> Other plans change `isolarcloud.py` elsewhere. Confirm the auto-detect block
> and the `get_device_realtime_data` call in `generate_image` still match the
> excerpts below. A mismatch there is a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-test-baseline-and-preview.md
- **Category**: direction (with one bug fix)
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

To pick a plant other than the first, users are told to "find the ID via the
Developer API `getPowerStationList` endpoint", which means making raw API
calls by hand. The plugin already makes that exact call during auto-detect
and throws the list away. Logging it gives users their IDs from
`journalctl -u inkypi`, which is the log command InkyPi's troubleshooting
docs already teach.

A related bug: if a user types a **wrong** `ps_id`, the API returns an empty
`device_point_list`. `get_device_realtime_data` then returns `{}`, and the
dashboard renders "Plant 12345" with every value at 0. That looks like a
dead system rather than a typo. It should raise a clear error instead.

## Current state

`isolarcloud/isolarcloud.py:61-75` (in `generate_image`):

```python
        # Auto-detect ps_id if not provided
        if not ps_id:
            plants = api.get_plant_list(token)
            if not plants:
                raise RuntimeError(
                    "No power stations found on this iSolarCloud account."
                )
            ps_id = str(plants[0]["ps_id"])
            logger.info("Auto-detected Power Station ID: %s (%s)", ps_id, plants[0].get("ps_name", ""))

        # Fetch real-time data
        device_points = api.get_device_realtime_data(token, ps_id, POINT_IDS)

        # Parse metrics
        plant_name = device_points.get("device_name", f"Plant {ps_id}")
```

`_SungrowAPI.get_device_realtime_data` returns `{}` when `device_point_list`
is empty (lines 266-269).

`isolarcloud/settings.html:11-15`:

```html
<div class="form-group">
    <label for="ps_id" class="form-label">Power Station ID:</label>
    <input type="text" id="ps_id" name="ps_id" placeholder="Leave blank to auto-detect" class="form-input">
    <small style="width: 100%; color: var(--text-primary);">Optional. If left blank, the plugin will auto-detect your first power station. For multiple plants, find the ID via the Developer API <code>getPowerStationList</code> endpoint.</small>
</div>
```

README "### 2. Find Your Power Station ID (optional)" (lines 49-55) says the same thing.

Errors raised from `generate_image` as `RuntimeError` are what InkyPi shows
the user when a manual refresh fails. Keep messages short and actionable, in
the style of the existing ones (e.g. `"No power stations found on this iSolarCloud account."`).

Test harness: plan 001's `tests/test_generate_image.py` with `fake_session`,
`api_ok`, `FakeDeviceConfig`, `FULL_ENV`, `SAMPLE_POINTS`. The plugin module
logger is `logging.getLogger("isolarcloud.isolarcloud")` under tests, so use
pytest's `caplog`.

## Commands you will need

| Purpose | Command (Git Bash; on Linux use `.venv/bin/python`) | Expected |
|---|---|---|
| Tests | `.venv/Scripts/python -m pytest -q` | all pass |

## Scope

**In scope**: `isolarcloud/isolarcloud.py` (`generate_image` auto-detect and
fetch block only), `isolarcloud/settings.html` (the `<small>` hint only),
`README.md` (section "2. Find Your Power Station ID"), `tests/test_generate_image.py`.

**Out of scope**: a dropdown of plants in the settings page.
`generate_settings_template` has no access to credentials or `device_config`
in InkyPi's API, so it would need an InkyPi change. Also out of scope: changes
to `_SungrowAPI`.

## Git workflow

- Branch: `advisor/007-plant-selection`
- Commit: `Log all power stations on auto-detect; error on unknown ps_id`
- Do NOT push unless instructed.

## Steps

### Step 1: Tests first

In `tests/test_generate_image.py`:
1. `test_autodetect_logs_all_plants`: `pageList` = `[{"ps_id": 1, "ps_name": "Home"}, {"ps_id": 2, "ps_name": "Shed"}]`.
   With `caplog.at_level(logging.INFO)`, assert the log text contains `1 (Home)` and `2 (Shed)`,
   and a WARNING-level record mentions `Power Station ID` (the "using the first one" notice).
2. `test_autodetect_single_plant_no_warning`: one plant → no WARNING records.
3. `test_unknown_ps_id_raises`: explicit `ps_id "999"`, and `getDeviceRealTimeData` returns
   `{"device_point_list": []}` → `RuntimeError` whose message contains `999` and `leave it blank`.

**Verify**: the 3 new tests fail; everything else passes.

### Step 2: Implement

Replace the auto-detect block and the fetch with:

```python
        # Auto-detect ps_id if not provided
        if not ps_id:
            plants = api.get_plant_list(token)
            if not plants:
                raise RuntimeError(
                    "No power stations found on this iSolarCloud account."
                )
            listing = ", ".join(f"{p.get('ps_id')} ({p.get('ps_name', '')})" for p in plants)
            logger.info("iSolarCloud power stations on this account: %s", listing)
            if len(plants) > 1:
                logger.warning(
                    "Multiple power stations found; using the first. "
                    "Set Power Station ID in the plugin settings to choose another."
                )
            ps_id = str(plants[0]["ps_id"])
            logger.info("Auto-detected Power Station ID: %s (%s)", ps_id, plants[0].get("ps_name", ""))

        # Fetch real-time data
        device_points = api.get_device_realtime_data(token, ps_id, POINT_IDS)
        if not device_points:
            raise RuntimeError(
                f"No data for Power Station ID {ps_id}. "
                "Check the ID, or leave it blank to auto-detect."
            )
```

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass.

### Step 3: Settings hint and README

`settings.html`: replace the `<small>` text with:
`Optional. Leave blank to use your first power station. To choose another, refresh once with it blank, then run <code>journalctl -u inkypi -n 100</code> on the Pi: the log lists every station's ID and name.`
Keep the `<small>` element's existing attributes unchanged.

README section "### 2. Find Your Power Station ID (optional)": replace the
paragraph starting "For accounts with multiple plants" with:

```markdown
For accounts with multiple plants, leave the field blank and refresh the plugin once. The InkyPi log then lists every power station's ID and name:

    journalctl -u inkypi -n 100 | grep "power stations"
```

Keep the existing V3-portal note.

**Verify**: `grep -n "getPowerStationList" isolarcloud/settings.html` → no output;
`grep -n "journalctl" README.md isolarcloud/settings.html` → one match in each.

## Test plan

Three new tests in `tests/test_generate_image.py`, modelled on its existing auto-detect test.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` exits 0
- [ ] Both greps in step 3 give the expected results
- [ ] Only in-scope files changed
- [ ] `plans/README.md` row 007 updated

## STOP conditions

- Evidence that a valid `ps_id` can legitimately return an empty
  `device_point_list` (for example, the plan 005 discovery notes say so at
  night). Report; don't ship the error.
- The excerpts don't match the code.

## Maintenance notes

- If InkyPi ever passes `device_config` to `generate_settings_template`, a
  real plant dropdown becomes possible. That's the proper end state.
- `README.md`'s API Details line about `getPowerStationList` stays accurate:
  the plugin still uses that endpoint.
