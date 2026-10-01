"""Shared synthetic fixtures for the iSolarCloud characterization tests."""
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

import inkypi_stubs

inkypi_stubs.install()

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def plugin_mod():
    from isolarcloud import isolarcloud

    return isolarcloud


@pytest.fixture
def plugin(plugin_mod, tmp_path, monkeypatch):
    p = plugin_mod.ISolarCloud({"id": "isolarcloud"})
    monkeypatch.setattr(
        p,
        "get_plugin_dir",
        lambda path=None: str(tmp_path / path) if path else str(tmp_path),
    )
    return p


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self.json_data = json_data
        self.text = text

    def json(self):
        if self.json_data is None:
            raise ValueError("not json")
        return self.json_data


class FakeSession:
    def __init__(self):
        self.responses = {}
        self.calls = []

    def queue(self, endpoint, response):
        self.responses.setdefault(endpoint, []).append(response)

    def post(self, url, headers=None, json=None, timeout=None):
        endpoint = url.rsplit("/", 1)[-1]
        self.calls.append({
            "endpoint": endpoint,
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        responses = self.responses.get(endpoint, [])
        if not responses:
            raise AssertionError(f"No response queued for {endpoint}")
        return responses.pop(0)


@pytest.fixture
def fake_session(plugin_mod, monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(plugin_mod, "get_http_session", lambda: session)
    return session


def api_ok(result_data):
    return FakeResponse(200, {
        "result_code": "1",
        "result_msg": "success",
        "result_data": result_data,
    })


class FakeDeviceConfig:
    def __init__(self, env=None, config=None):
        self.env = env if env is not None else {}
        self.config = config if config is not None else {}

    def load_env_key(self, key):
        return self.env.get(key)

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def get_resolution(self):
        return tuple(self.config.get("resolution", (800, 480)))


FULL_ENV = {
    "ISOLARCLOUD_USERNAME": "test-user",
    "ISOLARCLOUD_PASSWORD": "test-pass",
    "ISOLARCLOUD_APPKEY": "test-appkey",
    "ISOLARCLOUD_SECRET": "test-secret",
}

SAMPLE_POINTS = {
    "p83022": "18400",
    "p83024": "12400000",
    "p83033": "3450",
    "p83072": "6200",
    "p83102": "1100",
    "p83106": "2600",
    "p83252": "0.72",
}


def render_dashboard(params):
    env = Environment(
        loader=FileSystemLoader([
            str(ROOT / "isolarcloud" / "render"),
            str(ROOT / "tests" / "fixtures"),
        ]),
        autoescape=select_autoescape(["html", "xml"]),
    )
    return env.get_template("isolarcloud.html").render({
        "plugin_settings": {},
        "static_dir": "static",
        "style_sheets": [],
        "font_faces": [],
        **params,
    })
