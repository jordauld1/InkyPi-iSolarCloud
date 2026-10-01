from datetime import datetime
import logging

import pytest

from conftest import FakeDeviceConfig, FakeResponse, FULL_ENV, SAMPLE_POINTS, api_ok


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
    fake_session.queue("getDeviceList", api_ok({"pageList": []}))


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


def test_autodetect_logs_all_plants(plugin, fake_session, monkeypatch, caplog):
    capture_render(plugin, monkeypatch)
    queue_login(fake_session)
    fake_session.queue("getPowerStationList", api_ok({
        "pageList": [
            {"ps_id": 1, "ps_name": "Home"},
            {"ps_id": 2, "ps_name": "Shed"},
        ],
    }))
    queue_realtime(fake_session)

    with caplog.at_level(logging.INFO):
        plugin.generate_image({"ps_id": ""}, FakeDeviceConfig(env=FULL_ENV))

    assert "1 (Home)" in caplog.text
    assert "2 (Shed)" in caplog.text
    assert any(
        record.levelno == logging.WARNING and "Power Station ID" in record.message
        for record in caplog.records
    )


def test_autodetect_single_plant_no_warning(plugin, fake_session, monkeypatch, caplog):
    capture_render(plugin, monkeypatch)
    queue_login(fake_session)
    fake_session.queue("getPowerStationList", api_ok({
        "pageList": [{"ps_id": 1, "ps_name": "Home"}],
    }))
    queue_realtime(fake_session)

    with caplog.at_level(logging.INFO):
        plugin.generate_image({"ps_id": ""}, FakeDeviceConfig(env=FULL_ENV))

    assert "iSolarCloud power stations on this account: 1 (Home)" in caplog.text
    assert not any(record.levelno == logging.WARNING for record in caplog.records)


def test_unknown_ps_id_raises(plugin, fake_session):
    queue_login(fake_session)
    fake_session.queue("getDeviceRealTimeData", api_ok({"device_point_list": []}))

    with pytest.raises(RuntimeError) as error:
        plugin.generate_image({"ps_id": "999"}, FakeDeviceConfig(env=FULL_ENV))

    assert "999" in str(error.value)
    assert "leave it blank" in str(error.value)
    assert all(c["endpoint"] != "getDeviceList" for c in fake_session.calls)


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


def test_ess_points_used(plugin, fake_session, monkeypatch):
    captured, sentinel = capture_render(plugin, monkeypatch)
    queue_login(fake_session)
    fake_session.queue("getDeviceRealTimeData", api_ok({
        "device_point_list": [{"device_point": SAMPLE_POINTS}],
    }))
    fake_session.queue("getDeviceList", api_ok({"pageList": [
        {"device_type": 22, "ps_key": "777_22_247_1"},
        {"device_type": 14, "ps_key": "777_14_1_1"},
    ]}))
    fake_session.queue("getDeviceRealTimeData", api_ok({
        "device_point_list": [{"device_point": {
            "p13149": "0", "p13121": "300", "p13126": "1000", "p13150": "0",
        }}],
    }))

    result = plugin.generate_image({"ps_id": "777"}, FakeDeviceConfig(env=FULL_ENV))

    realtime_calls = [
        c for c in fake_session.calls if c["endpoint"] == "getDeviceRealTimeData"
    ]
    assert len(realtime_calls) == 2
    assert realtime_calls[1]["json"]["ps_key_list"] == ["777_14_1_1"]
    assert realtime_calls[1]["json"]["device_type"] == 14
    assert result is sentinel
    metrics = captured["template_params"]["metrics"]
    assert metrics["grid_power"] == -0.3
    assert metrics["battery_power"] == 1.0


def test_ess_failure_falls_back(plugin, fake_session, monkeypatch):
    captured, sentinel = capture_render(plugin, monkeypatch)
    queue_login(fake_session)
    fake_session.queue("getDeviceRealTimeData", api_ok({
        "device_point_list": [{"device_point": SAMPLE_POINTS}],
    }))
    fake_session.queue("getDeviceList", FakeResponse(200, {
        "result_code": "E00001", "result_msg": "nope",
    }))

    result = plugin.generate_image({"ps_id": "777"}, FakeDeviceConfig(env=FULL_ENV))

    assert result is sentinel
    assert captured["template_params"]["metrics"]["grid_power"] == -0.85
