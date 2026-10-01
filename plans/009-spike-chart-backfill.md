# Plan 009 (spike): Can the chart be filled from iSolarCloud's own history?

> **Executor instructions**: This is a **spike**. The deliverable is a probe
> script plus a findings document, **not** a change to the plugin. Follow the
> steps, honour the STOP conditions, and update `plans/README.md` when done.
> Do not modify anything under `isolarcloud/`.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- isolarcloud/isolarcloud.py`
> Only read the plugin for its API-call conventions. Drift there doesn't
> block this spike, but note it in the findings.

## Status

- **Priority**: P3
- **Effort**: M (spike); the build that follows is likely M
- **Risk**: LOW (no plugin changes)
- **Depends on**: plans/005-battery-aware-grid-and-usage.md Part A (reuses its
  login/API helper pattern and its point findings). Also needs a human with real credentials.
- **Category**: direction
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

Right now, the chart only gets one point per refresh. InkyPi's default plugin
cycle is **1 hour** (`plugin_cycle_interval_seconds` defaults to 3600 in
InkyPi `src/refresh_task.py:76`), which gives about 12 coarse points across
daylight. The history file is also deleted when the plugin is reinstalled or
updated (`inkypi plugin install` runs `rm -rf` on the plugin folder), and it
starts empty after any outage. iSolarCloud already stores 5-minute data for
every plant. If one API call per refresh can return today's series, the chart
would be complete and smooth whatever the refresh rate, and the local history
file could become a fallback only.

This spike answers whether that's possible and what it costs, so a build
plan can be written with facts instead of guesses.

## Questions the spike must answer

1. **Endpoint**: which Open API endpoint returns per-point time series for a
   plant? The leading candidate is `getDevicePointMinuteDataList`
   (GoSungrow wraps an endpoint of this name at
   `/v1/commonService/getDevicePointMinuteDataList`, with `ps_key`, `points`,
   `start_time_stamp`, `end_time_stamp`). The Open API path is probably
   `{gateway}/openapi/getDevicePointMinuteDataList`, but its parameter names
   (`ps_key_list`? `points`? `minute_interval`?) are **unverified**. The
   authoritative source is the API documentation in the iSolarCloud Developer
   Portal (https://developer.isolarcloud.com), which needs the owner's login.
2. **Request shape** that works: exact parameter names, timestamp format
   (likely `yyyyMMddHHmmss`), whether timestamps are plant-local time or UTC,
   allowed intervals, and the maximum range per call.
3. **Response shape**: how series are keyed, how timestamps come back, and the
   units for the points the dashboard charts: solar `83033`, SOC `83252`, the
   grid power point found in plan 005, and the battery power point if found.
4. **Cost**: response time and payload size for 00:00→now. Are there
   documented rate limits for this endpoint?
5. **Freshness**: how far behind real time is the last returned sample?
6. **Failure modes**: what comes back for a future range, an invalid point,
   or too long a range?

## Current state

The API conventions to copy (`isolarcloud/isolarcloud.py`, `_SungrowAPI`):
`POST {api_base}/{endpoint}` with a JSON body that always includes `appkey`
(and `token` after login), plus headers
`Content-Type: application/json;charset=UTF-8`, `sys_code: 901`,
`x-access-key: <secret>` and `token: <token>`. Success is
`result_code == "1"`, and the data is under `result_data`. The plant key for
device_type 11 is `"<ps_id>_11_0_0"`.

Today's chart contract (keep it so a later build doesn't touch the template):
history entries `{"ts", "time": "HH:MM", "battery_soc", "solar_kw", "grid_import_kw", "grid_export_kw"}`.
If plan 004 has landed, `generate_image` also passes a `chart` dict of
parallel arrays (`labels`, `battery_soc`, `solar_kw`, `grid_import_kw`, `grid_export_kw`).

If plan 005 Part A has landed, `tools/discover_points.py` already has an
`api_call` helper and env-var handling. Reuse that pattern (copy it; don't
import across scripts).

## Scope

**In scope**: `tools/probe_history.py` (create), `plans/009-spike-findings.md` (create).

**Out of scope**: everything under `isolarcloud/`, tests, and README. No
plugin changes in this plan.

## Git workflow

- Branch: `advisor/009-history-spike`
- Commit: `Add iSolarCloud history probe and spike findings`
- Do NOT push unless instructed.

## Steps

### Step 1: Probe script

Create `tools/probe_history.py`, standalone with `requests` only. It uses the
same env vars as `discover_points.py`, exits 2 listing missing key names
(names only), and never prints secrets or the token. Behaviour:

- Logs in, and resolves `ps_id` (env `ISOLARCLOUD_PS_ID` or the first plant).
- Flags: `--endpoint` (default `getDevicePointMinuteDataList`),
  `--points` (comma list, default `83033,83252`), `--interval` (default 5),
  `--hours` (default 6: window = now−hours → now, plant-local),
  `--param-style` (`a` | `b` | `c`, default `a`), and `--raw` (dump the full JSON response).
- Request body variants, to cope with the unknown parameter names. Every body also includes `appkey` and `token`:
  - `a`: `{"ps_key_list": [ps_key], "points": "p83033,p83252", "start_time_stamp": "yyyyMMddHHmmss", "end_time_stamp": "...", "minute_interval": 5}`
  - `b`: as `a`, but `"ps_key": ps_key` (single string) instead of `ps_key_list`
  - `c`: as `a`, but `"points"` without the `p` prefix (`"83033,83252"`)
- Prints the HTTP status, `result_code`, `result_msg`, elapsed ms, response
  size in bytes, the top-level keys of `result_data`, and, if a series is
  found, the first and last 3 samples per point.
- The endpoint is a flag on purpose: if the portal docs name a different
  endpoint, the human can try it without editing code.

**Verify**: `.venv/Scripts/python tools/probe_history.py; echo $?` with no env → missing key names, then `2`.

### Step 2: Hand over to the human, then stop

Write `plans/009-spike-findings.md` with the six questions above as headings,
each with an empty "Answer:" line. Add a "How to run" section:

1. Open the iSolarCloud Developer Portal's API documentation. Find the
   endpoint for device point minute/history data, and note its name and
   required parameters under question 1.
2. Run `tools/probe_history.py` with `--param-style a`, then `b`, then `c`
   (and `--endpoint <name>` if the docs say otherwise) until one returns
   `result_code 1` with data. Paste the non-secret output under the right
   question. Remove your ps_id from anything you paste.
3. Run once more with `--hours 24` and once with a window ending in the
   future (edit `--hours` or add a flag) to answer questions 4–6.

Mark the plan `BLOCKED (waiting for spike run)` in `plans/README.md` and stop.

### Step 3: After the human fills in answers (same or later session)

Add a "Recommendation" section to `plans/009-spike-findings.md`. Choose one:
- **Go**: describe the build in 5–10 bullets. Fetch today's series in
  `generate_image`, map it onto the existing `chart` contract, fall back to
  local history on any API error, and add a short timeout. Estimate how many
  extra API calls a day this makes at a 1-hour refresh and at a 5-minute refresh.
- **No-go**: state why (for example, the endpoint isn't on the Open API, or
  rate limits are too tight). Name the cheapest alternative, such as raising
  the history cap or keeping history outside the plugin folder so reinstalls
  don't wipe it.

Then mark the plan DONE. A follow-up build plan is written separately by
whoever reviews these findings.

## Done criteria

- [ ] `tools/probe_history.py` exists, exits 2 with no env, and never prints secrets
- [ ] `plans/009-spike-findings.md` exists with the six questions
- [ ] After the human run: every question has an answer, and a Go/No-go recommendation is written
- [ ] `git diff --stat -- isolarcloud/` is empty
- [ ] `plans/README.md` row 009 updated (BLOCKED, then DONE)

## STOP conditions

- All three param styles and the documented endpoint return errors. Record
  the exact `result_msg` values in the findings and recommend No-go/needs-support.
- The portal docs say the endpoint needs a different auth mode (for example,
  RSA-encrypted requests). Record that and stop. The plugin uses the
  plaintext V1 mode, and switching modes is a separate decision.

## Maintenance notes

- If this goes ahead, the README's "does not persist tokens / authenticates
  on each refresh" note stays true. One extra call per refresh is the only change.
- Plan 004's per-plant local history then becomes the fallback path. Keep it
  rather than deleting it.
