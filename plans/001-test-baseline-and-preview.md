# Plan 001: Establish a test suite, CI and a render preview tool

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat b655bb3..HEAD -- isolarcloud/ .gitignore README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (adds files only; no plugin code changes)
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `b655bb3`, 2026-10-01

## Why this matters

This repo is an InkyPi plugin with zero tests and no CI. Every later plan
(display fixes, battery-aware grid power, history fixes) changes numbers that
end up on a wall-mounted e-ink screen, where a regression is only noticed days
later. This plan adds (a) a pytest suite that runs **without** an InkyPi
checkout by stubbing the two InkyPi modules the plugin imports, (b) a GitHub
Actions workflow, and (c) a small preview script that renders the dashboard
HTML at every supported display size so layout changes can be eyeballed in a
browser. The tests in this plan are *characterization* tests: they pin
today's behaviour, bugs included, so later plans change behaviour on purpose.

## Current state

Repo layout (everything tracked):

```
.gitignore
LICENSE.md
README.md
iSolarCloudPluginFrontView.png
screenshot.png
isolarcloud/
  icon.png
  isolarcloud.py          ← the whole plugin (296 lines)
  plugin-info.json
  settings.html
  render/isolarcloud.css
  render/isolarcloud.html ← Jinja template, extends InkyPi's "plugin.html"
```

There is no `tests/`, no `requirements*.txt`, no `.github/`.

The plugin's only imports from InkyPi (`isolarcloud/isolarcloud.py:1-2`):

```python
from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
```

Other imports are stdlib plus `pytz`.

Key code the tests will exercise (`isolarcloud/isolarcloud.py`):

- `ISolarCloud.generate_image(self, settings, device_config)` (lines 38-106):
  loads 4 env keys via `device_config.load_env_key(...)`, logs in, optionally
  auto-detects `ps_id` from `get_plant_list`, calls `get_device_realtime_data`,
  then `_parse_metrics`, then `_record_and_load_history(metrics, now)`, then
  `self.render_image(dimensions, "isolarcloud.html", "isolarcloud.css", template_params)`.
- `ISolarCloud._parse_metrics(self, device_points, plant_name)` (lines 110-166):
  pure function from a dict like `{"p83022": "18400", ...}` to a metrics dict.
- `ISolarCloud._record_and_load_history(self, metrics, now)` (lines 175-215):
  reads/writes `self.get_plugin_dir("history.json")`.
- `_SungrowAPI` (lines 220-296): `login`, `get_plant_list`,
  `get_device_realtime_data`, `_api_call`. `_api_call` does
  `session = get_http_session()` then
  `session.post(url, headers=headers, json=payload, timeout=30)`.

How InkyPi itself builds the Jinja environment for plugins (from InkyPi's
`src/plugins/base_plugin/base_plugin.py:47-52`; mirror this in tests):

```python
loader = FileSystemLoader([self.render_dir, BASE_PLUGIN_RENDER_DIR])
self.env = Environment(
    loader=loader,
    autoescape=select_autoescape(['html', 'xml'])
)
```

InkyPi's base `plugin.html` wraps the plugin's `{% block content %}` and links
the stylesheets in `style_sheets`, declares `font_faces`, and reads
`plugin_settings.*`. InkyPi passes `static_dir` (absolute path to
`src/static`) — the template loads `{{static_dir}}/scripts/chart.js`.

Exact current outputs of `_parse_metrics` (verified by running the code at
`b655bb3`). Use these as test expectations:

| Input `device_points` | Key outputs |
|---|---|
| `{"p83022": "18400", "p83024": "12400000", "p83033": "3450", "p83072": "6200", "p83102": "1100", "p83106": "2600", "p83252": "0.72"}` | `curr_power 3.45`, `grid_power -0.85`, `load_power 2.6`, `battery_soc 72` (currently the float `72.0`), `today_energy 18.4`, `today_grid_feed 6.2`, `today_grid_import 1.1`, `today_load 13.3`, `self_sufficiency 91.7`, `total_energy 12400.0` |
| `{}` | every numeric value `0.0` |
| `{"p83033": "0", "p83106": "1000", "p83252": "0.5", "p83022": "0", "p83102": "3000"}` | `grid_power 1.0`, `battery_soc 50`, `today_load 3.0`, `self_sufficiency 0.0` |
| `{"p83252": "--", "p83033": None}` | `battery_soc 0`, `curr_power 0.0` (unparseable → default) |

Repo conventions: 4-space indent, `logger = logging.getLogger(__name__)`,
section comments like `# ── Metrics parsing ───...`, plain functions/classes,
no type hints. Commit messages are sentence-case imperative, e.g.
`Fix CSS: override base template padding/margins so dvh units fill viewport correctly`.

## Commands you will need

Create a local virtualenv once (`.venv/` is already in `.gitignore`):

| Purpose | Command (Git Bash on Windows) | Linux/macOS equivalent | Expected |
|---|---|---|---|
| Create venv | `python -m venv .venv` | same | exit 0 |
| Install dev deps | `.venv/Scripts/python -m pip install -r requirements-dev.txt` | `.venv/bin/python -m pip ...` | exit 0 |
| Tests | `.venv/Scripts/python -m pytest -q` | `.venv/bin/python -m pytest -q` | all pass |
| Preview | `.venv/Scripts/python tools/preview.py --inkypi ../InkyPi` | `.venv/bin/python ...` | prints 9 paths, exit 0 |

Python 3.11+ (InkyPi runs on Raspberry Pi OS Bookworm, Python 3.11).

## Scope

**In scope** (create unless stated):
- `requirements-dev.txt`
- `pytest.ini`
- `tests/inkypi_stubs.py`
- `tests/conftest.py`
- `tests/fixtures/plugin.html`
- `tests/test_metrics.py`, `tests/test_history.py`, `tests/test_api.py`,
  `tests/test_generate_image.py`, `tests/test_template.py`
- `tools/preview.py`
- `.github/workflows/tests.yml`
- `.gitignore` (append `preview/`)
- `README.md` (append a "Development" section only)

**Out of scope** (do NOT touch):
- Everything under `isolarcloud/`. This plan must not change plugin
  behaviour. If a test you write fails against current code, the test is
  wrong, not the plugin; fix the test to match the "Current state" table.
- Do not add an `__init__.py` to `isolarcloud/`. InkyPi's installer copies
  that folder verbatim into its plugins dir; it is imported there as
  `plugins.isolarcloud.isolarcloud`.
- Do not vendor or copy any InkyPi source files into this repo.

## Git workflow

- Branch: `advisor/001-test-baseline`
- One commit per step is fine. Message style: `Add pytest harness with InkyPi stubs`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Dev requirements and pytest config

Create `requirements-dev.txt`:

```
pytest>=7.0
pytz
jinja2>=3.0
requests
```

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = .
```

`pythonpath = .` puts the repo root on `sys.path`, so `from isolarcloud import isolarcloud`
imports `isolarcloud/isolarcloud.py` as a namespace package.

**Verify**: `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt` → exit 0.

### Step 2: InkyPi stubs, shared by tests and the preview tool

Create `tests/inkypi_stubs.py`:

```python
"""Minimal stand-ins for the two InkyPi modules the plugin imports.

Lets the plugin be imported and tested without an InkyPi checkout.
Call install() before importing isolarcloud.isolarcloud.
"""
import sys
import types


class StubBasePlugin:
    def __init__(self, config, **dependencies):
        self.config = config

    def get_plugin_id(self):
        return self.config.get("id")

    def get_plugin_dir(self, path=None):
        raise RuntimeError("get_plugin_dir must be patched in tests")

    def generate_settings_template(self):
        return {"settings_template": "isolarcloud/settings.html"}

    def render_image(self, dimensions, html_file, css_file=None, template_params=None):
        raise RuntimeError("render_image must be patched in tests")


def _no_session():
    raise RuntimeError("get_http_session must be patched in tests")


def install():
    base_plugin = types.ModuleType("plugins.base_plugin.base_plugin")
    base_plugin.BasePlugin = StubBasePlugin
    http_client = types.ModuleType("utils.http_client")
    http_client.get_http_session = _no_session

    modules = {
        "plugins": types.ModuleType("plugins"),
        "plugins.base_plugin": types.ModuleType("plugins.base_plugin"),
        "plugins.base_plugin.base_plugin": base_plugin,
        "utils": types.ModuleType("utils"),
        "utils.http_client": http_client,
    }
    for name, module in modules.items():
        sys.modules.setdefault(name, module)
```

**Verify**: `.venv/Scripts/python -c "import sys; sys.path[:0]=['.','tests']; import inkypi_stubs; inkypi_stubs.install(); from isolarcloud import isolarcloud; print(isolarcloud.ISolarCloud.__name__)"` → prints `ISolarCloud`.

### Step 3: conftest with fixtures and fakes

Create `tests/fixtures/plugin.html` containing exactly:

```
{% block content %}{% endblock %}
```

Create `tests/conftest.py`. It must call `inkypi_stubs.install()` at import
time (before any test imports the plugin) and provide:

- `ROOT = Path(__file__).resolve().parent.parent`
- fixture `plugin_mod` → returns the imported module `isolarcloud.isolarcloud`
  (`from isolarcloud import isolarcloud`).
- fixture `plugin(plugin_mod, tmp_path, monkeypatch)` → an
  `ISolarCloud({"id": "isolarcloud"})` instance with `get_plugin_dir` patched:
  `monkeypatch.setattr(p, "get_plugin_dir", lambda path=None: str(tmp_path / path) if path else str(tmp_path))`.
  Patch `get_plugin_dir`, **not** `_history_path`: a later plan changes `_history_path`'s signature.
- class `FakeResponse(status_code, json_data=None, text="")` with `.status_code`,
  `.text`, and `.json()` that returns `json_data`, or raises `ValueError("not json")`
  when `json_data is None`.
- class `FakeSession` with `queue(endpoint, response)` (FIFO per endpoint name,
  e.g. `"login"`) and `post(url, headers=None, json=None, timeout=None)` that
  takes `endpoint = url.rsplit("/", 1)[-1]`, appends
  `{"endpoint", "url", "headers", "json", "timeout"}` to `self.calls`, and pops
  the next queued response for that endpoint (raise `AssertionError` if none queued).
- fixture `fake_session(plugin_mod, monkeypatch)` → a `FakeSession` with
  `monkeypatch.setattr(plugin_mod, "get_http_session", lambda: session)`.
  (Patch the name **in the plugin module**, because it did `from utils.http_client import get_http_session`.)
- helper `api_ok(result_data)` → `FakeResponse(200, {"result_code": "1", "result_msg": "success", "result_data": result_data})`.
- class `FakeDeviceConfig(env=None, config=None)` with
  `load_env_key(key)` → `env.get(key)`, `get_config(key, default=None)` → `config.get(key, default)`,
  `get_resolution()` → `tuple(config.get("resolution", (800, 480)))`.
- constant `FULL_ENV` = the four keys `ISOLARCLOUD_USERNAME`, `ISOLARCLOUD_PASSWORD`,
  `ISOLARCLOUD_APPKEY`, `ISOLARCLOUD_SECRET` mapped to obviously fake strings
  (`"test-user"`, `"test-pass"`, `"test-appkey"`, `"test-secret"`).
- constant `SAMPLE_POINTS` = the first input row of the "Current state" table.
- helper `render_dashboard(params)` → builds
  `Environment(loader=FileSystemLoader([str(ROOT / "isolarcloud" / "render"), str(ROOT / "tests" / "fixtures")]), autoescape=select_autoescape(["html", "xml"]))`
  and returns `env.get_template("isolarcloud.html").render({"plugin_settings": {}, "static_dir": "static", "style_sheets": [], "font_faces": [], **params})`.

Make the fakes and helpers importable from tests (`from conftest import FakeResponse, api_ok, ...`).
pytest puts `tests/` on `sys.path` because `tests/` has no `__init__.py`; do not add one.

**Verify**: `.venv/Scripts/python -m pytest -q` → `no tests ran` (exit code 5) and no import errors.

### Step 4: Characterization tests

Write these tests. Assert individual keys, never whole-dict equality: later
plans add and remove keys. Use `pytest.approx` for floats.

`tests/test_metrics.py` (call `plugin._parse_metrics(points, "My Plant")`):
1. `SAMPLE_POINTS` → every value in the first row of the "Current state" table.
   For SOC assert `m["battery_soc"] == 72` (true for both `72.0` and `72`).
2. `{}` → `curr_power`, `grid_power`, `today_energy`, `today_load`, `self_sufficiency`, `battery_soc` all `== 0`.
3. The night row → `grid_power == 1.0`, `today_load == 3.0`, `self_sufficiency == 0.0`, `battery_soc == 50`.
4. The unparseable row → `battery_soc == 0`, `curr_power == 0.0`.
5. `m["plant_name"] == "My Plant"`.

`tests/test_history.py` (use `now = pytz.timezone("Australia/Brisbane").localize(datetime(2026, 3, 15, 12, 0))`):
1. The first call with `{"battery_soc": 72, "curr_power": 3.45, "grid_power": -0.85}` returns a
   1-element list whose entry has `time == "12:00"`, `grid_import_kw == 0`,
   `grid_export_kw == 0.85`, `solar_kw == 3.45`, `battery_soc == 72`; and
   `tmp_path / "history.json"` now exists.
2. Positive `grid_power` 1.2 → `grid_import_kw == 1.2`, `grid_export_kw == 0`.
3. Pre-seed `history.json` with one entry whose `ts` is `"2026-03-14T23:50:00+10:00"`
   (yesterday) → result has only today's entry.
4. Pre-seed `history.json` with the text `not json` → returns 1 entry, no exception.
5. Two calls 10 minutes apart → second call returns 2 entries in time order.

`tests/test_api.py` (construct `plugin_mod._SungrowAPI("https://example.test/openapi", "test-appkey", "test-secret")`, use `fake_session`):
1. `login` success: queue `api_ok({"token": "tok", "login_state": "1"})` → returns `"tok"`;
   the recorded call's URL is `https://example.test/openapi/login`, headers include
   `x-access-key == "test-secret"` and `sys_code == "901"`, and there is no `token` header.
2. `login` with `login_state "0"` → `RuntimeError` matching `login failed`.
3. HTTP 500 (`FakeResponse(500, None, "boom")`) → `RuntimeError` matching `HTTP 500`.
4. `result_code "E00003"` with `result_msg "bad appkey"` → `RuntimeError` matching `bad appkey`.
5. `get_device_realtime_data("tok", "123", ["83022"])` → the request JSON has
   `ps_key_list == ["123_11_0_0"]`, `device_type == 11`, and the `token` header is `"tok"`;
   returns the `device_point` dict from `{"device_point_list": [{"device_point": {"p83022": "1"}}]}`.
6. Same call with `{"device_point_list": []}` → returns `{}`.
7. `get_plant_list` → returns `pageList` from `{"pageList": [{"ps_id": 1}]}`.

`tests/test_generate_image.py` (patch `plugin.render_image` with a function that stores its args and returns a sentinel `object()`):
1. Missing env keys (`FakeDeviceConfig(env={})`) → `RuntimeError` matching `credentials not configured`, and no HTTP call was made.
2. Blank `ps_id` → auto-detect: queue login, then `getPowerStationList` returning
   `{"pageList": [{"ps_id": 4242, "ps_name": "Home"}]}`, then `getDeviceRealTimeData`
   returning `SAMPLE_POINTS` plus `"device_name": "Home Plant"`. Assert the realtime call's
   `ps_key_list == ["4242_11_0_0"]`, the returned value is the sentinel, and
   `template_params["plant_name"] == "Home Plant"`.
3. Explicit `ps_id "777"` → no `getPowerStationList` call is made.
4. `getPowerStationList` returns an empty `pageList` → `RuntimeError` matching `No power stations`.
5. `render_image` returns `None` → `RuntimeError` matching `Failed to render`.
6. `config={"orientation": "vertical", "resolution": (800, 480), "timezone": "UTC"}` → `render_image` received dimensions `(480, 800)`.

`tests/test_template.py` (use `render_dashboard`; build `metrics` by calling `plugin._parse_metrics(SAMPLE_POINTS, "My Plant")`):
1. With 2 history entries → output contains `id="solarChart"` and `chart.js`.
2. With 1 history entry → output does not contain `solarChart`.
3. Output contains `18.4` (Solar Today) and `13.3` (Used Today).
4. Output contains `width: 72` (battery bar; true for both `72%` and `72.0%`).
5. With `metrics["total_energy"] = 12400.0` → contains `MWh`; with `500.0` → contains ` kWh` and not `MWh`.

Template params for the rendering tests: `{"metrics": m, "current_date": "Sunday, March 15", "last_refresh": "12:00 PM", "plant_name": "My Plant", "history": [...]}`.
Each history entry: `{"ts": "...", "time": "06:00", "battery_soc": 40, "solar_kw": 0.5, "grid_import_kw": 0.2, "grid_export_kw": 0}`.

**Verify**: `.venv/Scripts/python -m pytest -q` → all pass, at least 28 tests.

### Step 5: Render preview tool

Create `tools/preview.py`: a script that renders the dashboard as standalone
HTML files, using InkyPi's **real** `plugin.html`, CSS, fonts and `chart.js`
from a local InkyPi checkout. Behaviour:

- Args: `--inkypi PATH` (default `../InkyPi`), `--out DIR` (default `preview`).
  If `PATH/src/plugins/base_plugin/render/plugin.html` doesn't exist, print
  `InkyPi checkout not found at PATH` and `sys.exit(2)`.
- Put the repo root and `tests/` on `sys.path`, call `inkypi_stubs.install()`,
  import the plugin, and build `metrics` with
  `ISolarCloud({"id": "isolarcloud"})._parse_metrics(SAMPLE, "My Solar Plant")`, where
  `SAMPLE` is the `SAMPLE_POINTS` dict (copy it in; don't import from conftest).
- Build a synthetic `history` of entries every 30 min from 06:00 to 18:00
  (solar a bell curve peaking ~5 kW at 12:00, battery rising 20→95 then falling,
  import >0 only before 08:30 and after 16:30, export peaking ~2.5 kW at 12:00).
  Same entry keys as the plugin writes (`ts`, `time`, `battery_soc`, `solar_kw`,
  `grid_import_kw`, `grid_export_kw`).
- Jinja env: `FileSystemLoader([REPO/isolarcloud/render, INKYPI/src/plugins/base_plugin/render])`,
  `autoescape=select_autoescape(["html", "xml"])`.
- Template params: `metrics`, `history`, `plant_name`, `current_date` ("Sunday, March 15"),
  `last_refresh` ("10:45 PM"), `plugin_settings` `{}`,
  `style_sheets` = `[ (INKYPI/src/plugins/base_plugin/render/plugin.css).as_uri(), (REPO/isolarcloud/render/isolarcloud.css).as_uri() ]`,
  `static_dir` = `(INKYPI/src/static).as_uri()`,
  `font_faces` = for Jost and Dogica, mirroring InkyPi's `src/utils/app_utils.py` `FONT_FAMILIES`:
  Jost normal `Jost.ttf`, Jost bold `Jost-SemiBold.ttf`, Dogica normal `dogicapixel.ttf`,
  Dogica bold `dogicapixelbold.ttf`, each `{"font_family", "font_weight", "font_style": "normal", "url": (INKYPI/src/static/fonts/<file>).as_uri()}`.
  Use `.as_uri()` everywhere: a bare Windows path such as `C:\...` does not load in a browser.
- Sizes: `[(800, 480), (640, 400), (600, 448), (400, 300)]`, each rendered
  `horizontal` (w×h) and `vertical` (h×w), written to `OUT/{w}x{h}_{orientation}.html`
  (8 files), plus `OUT/index.html` containing one `<iframe>` per file with
  `width`/`height` attributes equal to that size, `border:1px solid #888`, a
  caption above each, wrapped with `display:flex; flex-wrap:wrap; gap:16px`.
- Print each written path (9 lines). Exit 0.

Append `preview/` to `.gitignore`.

**Verify**: `.venv/Scripts/python tools/preview.py --inkypi ../InkyPi` → 9 lines of
paths, exit 0. Then `grep -c "<iframe" preview/index.html` → `8`.
If `../InkyPi` doesn't exist on this machine, check that
`.venv/Scripts/python tools/preview.py --inkypi /nonexistent; echo $?` prints the
not-found message and `2`, and report that the visual check was skipped.

### Step 6: CI workflow

Create `.github/workflows/tests.yml`:

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install -r requirements-dev.txt
      - run: python -m pytest -q
```

**Verify**: `.venv/Scripts/python -c "import yaml" 2>/dev/null || echo skip`. YAML
validation is optional; just confirm by reading that the file matches the block above exactly.

### Step 7: README "Development" section

Append to `README.md`, just before `## License`:

```markdown
## Development

Tests run without an InkyPi checkout (InkyPi's modules are stubbed):

    python -m venv .venv
    .venv/bin/python -m pip install -r requirements-dev.txt   # Windows: .venv\Scripts\python
    .venv/bin/python -m pytest -q

To preview the dashboard at every supported display size, with a local InkyPi
checkout alongside this repo:

    .venv/bin/python tools/preview.py --inkypi ../InkyPi

then open `preview/index.html` in a browser.
```

**Verify**: `grep -n "## Development" README.md` → one match, on a line before `## License`.

## Test plan

This plan *is* the test plan. 28+ tests across 5 files, all passing against
unmodified plugin code.

## Done criteria

- [ ] `.venv/Scripts/python -m pytest -q` exits 0 with ≥ 28 passed
- [ ] `git diff --stat b655bb3 -- isolarcloud/` is empty (plugin untouched)
- [ ] `test -f isolarcloud/__init__.py` fails (no `__init__.py` was added)
- [ ] `tools/preview.py` exists; with `../InkyPi` present, `preview/index.html` has 8 iframes
- [ ] `.github/workflows/tests.yml` exists
- [ ] `git status --porcelain` shows only in-scope paths (and `preview/` is not listed, because it is ignored)
- [ ] `plans/README.md` row 001 updated

## STOP conditions

- Importing the plugin through the stubs fails for a reason other than a typo
  in your stub (for example, the plugin gained a new InkyPi import). Report the import.
- A characterization test can't be made to pass without changing `isolarcloud/`:
  the plugin's behaviour differs from the "Current state" table, so the code has drifted.
- `pythonpath` in `pytest.ini` isn't supported (pytest < 7). Report the version; don't work around it with `conftest` path hacks.

## Maintenance notes

- `tests/inkypi_stubs.py` mirrors the slice of InkyPi's API the plugin uses.
  If the plugin starts using another `BasePlugin` method or InkyPi util, add it
  to the stub.
- The preview tool renders with real InkyPi assets but not InkyPi's headless
  Chromium. Final pixel checks still belong on a device or in InkyPi's dev mode.
- Reviewer: check that tests assert behaviour (values), not implementation
  details like call counts, except where the plan asks for them.
