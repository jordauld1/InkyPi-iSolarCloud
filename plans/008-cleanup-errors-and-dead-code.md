# Plan 008: Clear network error messages, remove dead values, untrack the unused 12 MB image

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- isolarcloud/ iSolarCloudPluginFrontView.png`
> Other plans change these files. Each step below says what to look for and is
> written to be safe whether or not those plans have landed. Read the live code
> for each step rather than trusting line numbers.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-test-baseline-and-preview.md. Run after 003–007 if they're scheduled, to avoid churn.
- **Category**: tech-debt
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

Three small things, bundled:

1. **Network failures give raw exception text.** If iSolarCloud times out or
   returns an HTML error page with status 200, the user sees something like
   `HTTPSConnectionPool(host=...): Read timed out` or
   `Expecting value: line 1 column 1`. They should see "iSolarCloud
   unreachable". The plugin already wraps HTTP and API errors in friendly
   `RuntimeError`s, and these two paths were missed.
2. **Dead values mislead readers.** A hardcoded `"battery_power": 0.0`
   suggests the feature exists. The `api_gateways` template param is never
   read, because `settings.html` hardcodes the options. Two metrics keys and
   one CSS class are never used.
3. **A 12 MB image nobody references.** `iSolarCloudPluginFrontView.png` is
   12 of the repo's 13 MB, and nothing links to it.

## Current state

`isolarcloud/isolarcloud.py:271-296` (`_SungrowAPI._api_call`):

```python
    def _api_call(self, endpoint, payload):
        """Make a plaintext API call to iSolarCloud."""
        headers = {
            ...
        }
        ...
        url = f"{self.api_base}/{endpoint}"
        session = get_http_session()
        resp = session.post(url, headers=headers, json=payload, timeout=30)

        if resp.status_code != 200:
            logger.error("iSolarCloud API error [%d]: %s", resp.status_code, resp.text[:200])
            raise RuntimeError(f"iSolarCloud API request failed (HTTP {resp.status_code}).")

        result = resp.json()
        result_code = result.get("result_code")
```

InkyPi's shared session (InkyPi `src/utils/http_client.py`) is a
`requests.Session` with `HTTPAdapter(max_retries=3)`, so connection errors
surface as `requests.exceptions.RequestException` subclasses after the retries.

Dead or unused items. Verify each with the grep given before removing it:

| Item | Where | Why it's dead |
|---|---|---|
| `template_params["api_gateways"] = list(API_GATEWAYS.keys())` | `isolarcloud.py:34`, in `generate_settings_template` | `settings.html` never references `api_gateways` |
| `"battery_power": 0.0,` | `_parse_metrics` return dict | hardcoded placeholder. **Only remove it if the literal `0.0` is still there.** Plan 006 makes it real. |
| `"load_power": ...` | `_parse_metrics` return dict | not used by the template or history. The *local variable* `load_power_w` is used and must stay. |
| `"today_self_use": ...` | `_parse_metrics` return dict | not used anywhere |
| `.tile-sub { ... }` | `isolarcloud/render/isolarcloud.css:191-196` | no element has class `tile-sub` |
| `grid_kw` fallback | `isolarcloud.html` chart data | legacy key; plan 004 removes it. Only act if still present. |

Image: `iSolarCloudPluginFrontView.png` at the repo root, tracked, 12,459,824
bytes. `README.md` uses `screenshot.png`, not this file. InkyPi's installer
does a sparse, `blob:none` clone of only the `isolarcloud/` folder, so plugin
users never download it. Only people cloning the repo do.

## Commands you will need

| Purpose | Command (Git Bash; on Linux use `.venv/bin/python`) | Expected |
|---|---|---|
| Tests | `.venv/Scripts/python -m pytest -q` | all pass |

## Scope

**In scope**: `isolarcloud/isolarcloud.py`, `isolarcloud/render/isolarcloud.css`,
`isolarcloud/render/isolarcloud.html` (the `grid_kw` fallback only),
`tests/test_api.py`, `tests/test_metrics.py`, and `iSolarCloudPluginFrontView.png`
(step 4 only, and only with operator approval).

**Out of scope**: rewriting git history to purge the image. That's destructive
and needs a force-push, which is the owner's call. Also out of scope:
`screenshot.png`, which the README uses.

## Git workflow

- Branch: `advisor/008-cleanup`
- Commits: `Wrap network and non-JSON errors from iSolarCloud`, `Remove unused metrics and settings params`, `Untrack unused front-view image` (step 4, only if approved)
- Do NOT push unless instructed.

## Steps

### Step 1: Tests for error wrapping (they fail first)

In `tests/test_api.py`:
1. `test_network_error_is_wrapped`: make `FakeSession.post` raise
   `requests.exceptions.ConnectTimeout("boom")`. Monkeypatch a subclass, or
   queue a callable if your `FakeSession` supports it. Calling `api.login(...)`
   → `RuntimeError` whose message contains `unreachable`.
2. `test_non_json_response_is_wrapped`: `FakeResponse(200, None, "<html>")` → `RuntimeError` containing `unexpected response`.

**Verify**: both fail; everything else passes.

### Step 2: Implement error wrapping

Add `import requests` to the plugin's imports. InkyPi already depends on
`requests`, and `requirements-dev.txt` lists it. Then, in `_api_call`:

```python
        try:
            resp = session.post(url, headers=headers, json=payload, timeout=30)
        except requests.RequestException as e:
            logger.error("iSolarCloud request to %s failed: %s", endpoint, e)
            raise RuntimeError("iSolarCloud unreachable. Check the Pi's network connection and the selected region.") from e
```

and replace `result = resp.json()` with:

```python
        try:
            result = resp.json()
        except ValueError as e:
            logger.error("iSolarCloud returned non-JSON for %s: %s", endpoint, resp.text[:200])
            raise RuntimeError("iSolarCloud returned an unexpected response. Try again later.") from e
```

Log `endpoint`, not `url` or `payload`. The payload contains the password.

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass.

### Step 3: Remove dead values

For each row in the dead-items table, run the check first and remove the
item only if the check confirms it's unused:

- `grep -rn "api_gateways" isolarcloud/` → only the assignment line → delete that line.
- `grep -n '"battery_power": 0.0' isolarcloud/isolarcloud.py` → if found, delete that line. If not found, skip.
- `grep -rn "load_power\b" isolarcloud/render/ isolarcloud/isolarcloud.py`. If
  the only hit outside `_parse_metrics` locals is the dict key, delete the dict
  key line, keep `load_power_w`, and delete the now-unused local
  `load_power = round(...)` line if nothing else reads it.
- `grep -rn "today_self_use" isolarcloud/` → only the dict key → delete it.
- `grep -rn "tile-sub" isolarcloud/` → only the CSS rule → delete the `.tile-sub { ... }` block.
- `grep -n "grid_kw" isolarcloud/render/isolarcloud.html`. If found, change
  `{{ h.grid_import_kw|default(h.grid_kw|default(0)) }}` to `{{ h.grid_import_kw|default(0) }}`.

In `tests/test_metrics.py`, add `test_no_dead_keys`: the `_parse_metrics(SAMPLE_POINTS, "x")`
result has no `today_self_use` and no `load_power` key. Remove any older
assertions on those two keys. Plan 001 told tests not to assert them, but check anyway.

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass. If `../InkyPi`
exists, `tools/preview.py` still runs (exit 0).

### Step 4: Image (operator approval required)

Ask the operator: *"Untrack `iSolarCloudPluginFrontView.png` (12 MB, unreferenced)? It stays in git history; this only removes it going forward."*
- If they say yes: `git rm iSolarCloudPluginFrontView.png`, then commit.
- If they say no, or there's no operator to ask: skip, and note "image step skipped" in your report.

Before asking, confirm `grep -rn "FrontView" --include=*.md --include=*.html --include=*.py .` → no output.

## Test plan

Two error-path tests and one dead-key test. Model them on the existing tests in `tests/test_api.py` / `tests/test_metrics.py`.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` exits 0
- [ ] `grep -n "requests.RequestException" isolarcloud/isolarcloud.py` → 1 match
- [ ] `grep -rn "api_gateways\|today_self_use\|tile-sub" isolarcloud/` → no output
- [ ] Image either removed with approval, or skipped and reported
- [ ] Only in-scope files changed
- [ ] `plans/README.md` row 008 updated

## STOP conditions

- A grep in step 3 shows the item *is* used somewhere new. Keep it, and report it.
- Wrapping errors would require changing InkyPi's `http_client` (it's out of
  this repo). Report instead.

## Maintenance notes

- Purging the image from history (`git filter-repo --path iSolarCloudPluginFrontView.png --invert-paths`
  plus a force-push) would shrink clones to ~1 MB. It rewrites every commit
  SHA, so it's the owner's decision, not part of this plan.
