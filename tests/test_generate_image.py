from datetime import datetime

import pytest

from conftest import FakeDeviceConfig, FULL_ENV, SAMPLE_POINTS, api_ok


def capture_render(plugin, monkeypatch, result=None):
    captured = {}
    sentinel = result if result is not None else object()

    def render(dimensions, html_file, css_file=None, template_params=None):
        captured["dimensions"] = dimensions
        captured["html_file"] = html_file
        captured["css_file"] = css_file
        captured["template_params"] = template_params
        return sentinel

    monkeypatch.setattr(plugin, "render_image", render)
    return captured, sentinel


def queue_login(fake_session):
    fake_session.queue("login", api_ok({"token": "tok", "login_state": "1"}))


def queue_realtime(fake_session, points=None):
    fake_session.queue("getDeviceRealTimeData", api_ok({
        "device_point_list": [{"device_point": points if points is not None else SAMPLE_POINTS}],
    }))


def test_missing_credentials(plugin, fake_session):
    with pytest.raises(RuntimeError, match="credentials not configured"):
        plugin.generate_image({}, FakeDeviceConfig(env={}))
    assert len(fake_session.calls) == 0


def test_auto_detects_plant(plugin, fake_session, monkeypatch):
    captured, sentinel = capture_render(plugin, monkeypatch)
    queue_login(fake_session)
    fake_session.queue("getPowerStationList", api_ok({
        "pageList": [{"ps_id": 4242, "ps_name": "Home"}],
    }))
    queue_realtime(fake_session, {**SAMPLE_POINTS, "device_name": "Home Plant"})

    result = plugin.generate_image({"ps_id": ""}, FakeDeviceConfig(env=FULL_ENV))

    realtime = next(c for c in fake_session.calls if c["endpoint"] == "getDeviceRealTimeData")
    assert realtime["json"]["ps_key_list"] == ["4242_11_0_0"]
    assert result is sentinel
    assert captured["template_params"]["plant_name"] == "Home Plant"


def test_explicit_plant_skips_lookup(plugin, fake_session, monkeypatch):
    capture_render(plugin, monkeypatch)
    queue_login(fake_session)
    queue_realtime(fake_session)

    plugin.generate_image({"ps_id": "777"}, FakeDeviceConfig(env=FULL_ENV))

    assert all(c["endpoint"] != "getPowerStationList" for c in fake_session.calls)


def test_current_date_not_zero_padded(plugin, plugin_mod, fake_session, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return tz.localize(datetime(2026, 10, 1, 9, 5))

    monkeypatch.setattr(plugin_mod, "datetime", FixedDatetime)
    captured, _ = capture_render(plugin, monkeypatch)
    queue_login(fake_session)
    queue_realtime(fake_session)

    plugin.generate_image({"ps_id": "777"}, FakeDeviceConfig(env=FULL_ENV))

    assert captured["template_params"]["current_date"] == "Thursday, October 1"


def test_no_power_stations(plugin, fake_session):
    queue_login(fake_session)
    fake_session.queue("getPowerStationList", api_ok({"pageList": []}))
    with pytest.raises(RuntimeError, match="No power stations"):
        plugin.generate_image({"ps_id": ""}, FakeDeviceConfig(env=FULL_ENV))


def test_failed_render(plugin, fake_session, monkeypatch):
    monkeypatch.setattr(plugin, "render_image", lambda *args: None)
    queue_login(fake_session)
    queue_realtime(fake_session)
    with pytest.raises(RuntimeError, match="Failed to render"):
        plugin.generate_image({"ps_id": "777"}, FakeDeviceConfig(env=FULL_ENV))


def test_vertical_orientation(plugin, fake_session, monkeypatch):
    captured, _ = capture_render(plugin, monkeypatch)
    queue_login(fake_session)
    queue_realtime(fake_session)
    device = FakeDeviceConfig(
        env=FULL_ENV,
        config={"orientation": "vertical", "resolution": (800, 480), "timezone": "UTC"},
    )

    plugin.generate_image({"ps_id": "777"}, device)

    assert captured["dimensions"] == (480, 800)
