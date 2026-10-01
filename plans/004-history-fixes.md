# Plan 004: Keep a full day of chart history per plant, written safely

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- isolarcloud/isolarcloud.py isolarcloud/render/isolarcloud.html .gitignore`
> Plan 003 legitimately changes `isolarcloud.py` lines ~88 and ~158 (date and
> battery SOC). Any other change in the regions excerpted below is drift and
> a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-test-baseline-and-preview.md
- **Category**: bug
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

The dashboard's chart is built from a local `history.json` that gets one
entry per refresh. That file has four problems:

1. **The morning gets cut off at short refresh intervals.** The file is capped
   at 144 entries *before* it's filtered to today. At a 5-minute refresh,
   today's 06:00–12:00 entries are discarded by mid-afternoon.
2. **Plugin instances overwrite each other.** InkyPi lets a user add the
   plugin more than once (for example, two plants in a playlist). Every
   instance appends to the same `history.json`, so both charts mix two plants'
   data.
3. **A crash mid-write corrupts the file.** The file is rewritten in place,
   and a Pi losing power mid-write leaves a truncated file. The plugin
   recovers by silently dropping all of today's history.
4. **Chart data goes into a `<script>` block unescaped.** The arrays are
   assembled with Jinja loops rather than `tojson`, so a malformed history file
   breaks the chart's JavaScript.

## Current state

`isolarcloud/isolarcloud.py:94-97` (in `generate_image`):

```python
            "plugin_settings": settings,
            "plant_name": metrics.get("plant_name", "iSolarCloud"),
            "history": self._record_and_load_history(metrics, now),
        }
```

`isolarcloud/isolarcloud.py:168-215`:

```python
    # ── History recording ────────────────────────────────────────────────

    HISTORY_MAX_ENTRIES = 144  # ~24h at 10-min intervals

    def _history_path(self):
        return self.get_plugin_dir("history.json")

    def _record_and_load_history(self, metrics, now):
        """Append current reading to history file and return entries for today."""
        path = self._history_path()

        # Load existing history
        history = []
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    history = json.load(f)
            except (json.JSONDecodeError, OSError):
                history = []

        # Append current reading
        grid_power = metrics.get("grid_power", 0)
        entry = {
            "ts": now.isoformat(),
            "time": now.strftime("%H:%M"),
            "battery_soc": metrics.get("battery_soc", 0),
            "solar_kw": metrics.get("curr_power", 0),
            "grid_import_kw": round(max(0, grid_power), 2),
            "grid_export_kw": round(abs(min(0, grid_power)), 2),
        }
        history.append(entry)

        # Trim to max entries
        if len(history) > self.HISTORY_MAX_ENTRIES:
            history = history[-self.HISTORY_MAX_ENTRIES:]

        # Filter to today only
        today_str = now.strftime("%Y-%m-%d")
        history = [h for h in history if h["ts"].startswith(today_str)]

        # Save
        try:
            with open(path, "w") as f:
                json.dump(history, f)
        except OSError as e:
            logger.warning("Failed to save history: %s", e)

        return history
```

`isolarcloud/render/isolarcloud.html:114-122` (chart data):

```html
{% if history|length > 1 %}
<script src="{{static_dir}}/scripts/chart.js" charset="UTF-8"></script>
<script>
document.addEventListener("DOMContentLoaded", function() {
  const labels = [{% for h in history %}"{{ h.time }}"{% if not loop.last %}, {% endif %}{% endfor %}];
  const batterySoc = [{% for h in history %}{{ h.battery_soc }}{% if not loop.last %}, {% endif %}{% endfor %}];
  const solarPower = [{% for h in history %}{{ h.solar_kw }}{% if not loop.last %}, {% endif %}{% endfor %}];
  const gridImport = [{% for h in history %}{{ h.grid_import_kw|default(h.grid_kw|default(0)) }}{% if not loop.last %}, {% endif %}{% endfor %}];
  const gridExport = [{% for h in history %}{{ h.grid_export_kw|default(0) }}{% if not loop.last %}, {% endif %}{% endfor %}];
```

The template also uses `history|length > 1` at lines 75 and 114 to decide
whether to show the chart. Keep `history` as a template param so those checks still work.

`.gitignore` contains `**/history.json`.

`ps_id` comes from the user-typed plugin setting (`settings.get("ps_id", "").strip()`)
or from the API. It must be sanitized before it goes into a filename.

InkyPi's own templates use `tojson` for JS data, e.g. InkyPi
`src/plugins/calendar/render/calendar.html:22`: `const events = {{ events | tojson }};`.

Test harness: plan 001's `tests/test_history.py` currently calls
`plugin._record_and_load_history(metrics, now)` and checks
`tmp_path / "history.json"`. This plan changes the signature and filename, so
update those tests as described below.

## Commands you will need

| Purpose | Command (Git Bash; on Linux use `.venv/bin/python`) | Expected |
|---|---|---|
| Tests | `.venv/Scripts/python -m pytest -q` | all pass |
| Preview (optional visual) | `.venv/Scripts/python tools/preview.py --inkypi ../InkyPi` | 9 paths |

## Scope

**In scope**: `isolarcloud/isolarcloud.py` (the history section, plus the
`template_params` block in `generate_image`), `isolarcloud/render/isolarcloud.html`
(lines 114-122 only), `.gitignore`, `tests/test_history.py`,
`tests/test_template.py`, `tests/test_generate_image.py`. Also
`tools/preview.py`, but only if Step 3 makes it necessary.

**Out of scope**: the chart's options, colours and datasets (lines 124-236 of
the template); `_parse_metrics`; the API client. Don't backfill history from
the API; that's plan 009.

## Git workflow

- Branch: `advisor/004-history-fixes`
- Commits: `Keep full day of history per plant`, `Pass chart data to template via tojson`
- Do NOT push unless instructed.

## Steps

### Step 1: Tests for the new behaviour (they fail first)

In `tests/test_history.py`:
- Change existing calls to `plugin._record_and_load_history(metrics, now, "4242")`
  and existing file assertions to `tmp_path / "history_4242.json"`.
- Add `test_full_day_kept_at_short_intervals`: pre-seed `history_4242.json`
  with 200 entries for today, at 1-minute spacing from 06:00, then call once
  at 12:00. Assert the result has 201 entries and `result[0]["time"] == "06:00"`.
- Add `test_cap_applies_after_today_filter`: pre-seed 1500 entries for today
  (timestamps can repeat; only `ts` date prefix matters) plus 10 for yesterday.
  Assert `len(result) == plugin.HISTORY_MAX_ENTRIES` and every entry's `ts` starts with today's date.
- Add `test_history_is_per_plant`: call with ps_id `"1"` then `"2"`. Assert
  each call returns 1 entry and both `history_1.json` and `history_2.json` exist.
- Add `test_ps_id_is_sanitized`: call with ps_id `"../../evil"`. Assert no file
  exists outside `tmp_path`, and exactly one `history_*.json` file exists in
  `tmp_path` whose name contains only `[A-Za-z0-9_-]` between `history_` and `.json`.
- Add `test_non_list_json_treated_as_empty`: pre-seed `{"a": 1}` → returns 1 entry.
- Add `test_malformed_entries_dropped`: pre-seed `[{"no_ts": 1}, "x", {"ts": "<today>T07:00:00+10:00", "time": "07:00"}]`.
  The result has 2 entries (the valid one and the new one), and no exception is raised.
- Add `test_legacy_history_file_removed`: pre-seed `tmp_path / "history.json"`,
  then call once. Assert it no longer exists.

**Verify**: `.venv/Scripts/python -m pytest -q tests/test_history.py` → the new and changed tests fail; nothing errors at collection.

### Step 2: Rewrite the history section

Replace the history section of `isolarcloud.py` (from the `# ── History recording`
comment to the end of `_record_and_load_history`) with code that does the
following. Keep the section comment and the repo's style.

```python
    HISTORY_MAX_ENTRIES = 1440  # one day at 1-minute refreshes

    def _history_path(self, ps_id):
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(ps_id)) or "default"
        return self.get_plugin_dir(f"history_{safe_id}.json")

    def _record_and_load_history(self, metrics, now, ps_id):
        """Append current reading to this plant's history file and return today's entries."""
```

Behaviour, in order:
1. `path = self._history_path(ps_id)`.
2. Load. If the file is missing, unreadable, invalid JSON or not a `list`, use `[]`.
3. Keep only entries that are `dict`s whose `str(h.get("ts", ""))` starts with
   `now.strftime("%Y-%m-%d")`. **Filter first.**
4. Append the new entry. Use the same keys and formulas as today's code.
5. Cap: `history = history[-self.HISTORY_MAX_ENTRIES:]`.
6. Atomic save: write JSON to `path + ".tmp"`, then `os.replace(tmp, path)`.
   On `OSError`, log `logger.warning("Failed to save history: %s", e)` as today.
7. Best-effort cleanup of the pre-plan shared file: `legacy = self.get_plugin_dir("history.json")`.
   If it exists, `os.remove` it inside `try/except OSError: pass`.
8. Return `history`.

Add `import re` to the imports, keeping them in the existing order style.

In `generate_image`, change the call to `self._record_and_load_history(metrics, now, ps_id)`.

In `.gitignore`, change `**/history.json` to `**/history*.json` and add a line `**/history*.json.tmp`.

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass except any
`test_generate_image.py` test that asserted `history.json`. Update that
assertion to `history_<id>.json`, then all pass.

### Step 3: Chart data via `tojson`

In `generate_image`, add a `chart` key to `template_params`, built from `history`:

```python
        history = self._record_and_load_history(metrics, now, ps_id)
        ...
            "history": history,
            "chart": {
                "labels": [h.get("time", "") for h in history],
                "battery_soc": [h.get("battery_soc", 0) for h in history],
                "solar_kw": [h.get("solar_kw", 0) for h in history],
                "grid_import_kw": [h.get("grid_import_kw", 0) for h in history],
                "grid_export_kw": [h.get("grid_export_kw", 0) for h in history],
            },
```

In `isolarcloud/render/isolarcloud.html`, replace the five `const ... = [...]` lines (118-122) with:

```html
  const labels = {{ chart.labels | tojson }};
  const batterySoc = {{ chart.battery_soc | tojson }};
  const solarPower = {{ chart.solar_kw | tojson }};
  const gridImport = {{ chart.grid_import_kw | tojson }};
  const gridExport = {{ chart.grid_export_kw | tojson }};
```

This drops the legacy `grid_kw` fallback on purpose: files written before this
plan are no longer read (step 2, item 7).

Update `tests/test_template.py`: wherever it builds params with `history`, also
pass a matching `chart` dict. Add `test_chart_data_is_json`. Use a history whose
`time` is `'06:00"</script>'`. Assert the rendered HTML does **not** contain
`"</script>` immediately after `06:00`, and that it contains `</script>`
(Jinja's `tojson` escapes `<` and `>`).

If `tools/preview.py` exists and builds template params itself, add the same
`chart` dict there, built the same way.

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass.
`grep -n "for h in history" isolarcloud/render/isolarcloud.html` → no output.

## Test plan

Covered in steps 1 and 3: 7 new history tests and 1 new template test.
Model new tests on the existing ones in `tests/test_history.py`.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` exits 0
- [ ] `grep -n "HISTORY_MAX_ENTRIES = 144" isolarcloud/isolarcloud.py` → no output
- [ ] `grep -n "grid_kw" isolarcloud/render/isolarcloud.html` → no output
- [ ] `grep -n "os.replace" isolarcloud/isolarcloud.py` → 1 match
- [ ] `grep -n "history\*.json" .gitignore` → match
- [ ] Only in-scope files changed
- [ ] `plans/README.md` row 004 updated

## STOP conditions

- `generate_image` has drifted such that `ps_id` isn't in scope at the history
  call (for example, someone moved auto-detection). Report; don't restructure `generate_image`.
- If plan 009 (API history backfill) has already landed and replaced local
  history, this plan is moot. Mark REJECTED with that reason.

## Maintenance notes

- Upgrading users lose the current day's chart once, because the old shared
  file is deleted. That is acceptable for a same-day chart. Mention it in the
  commit message body.
- A 1440-entry file is about 150 KB. If someone sets very short refresh
  intervals for days, the cap still bounds the file.
- Plan 009 may replace local history with API-sourced series. If so, keep the
  `chart` param shape so the template doesn't change again.
