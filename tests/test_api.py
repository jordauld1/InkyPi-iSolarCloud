import pytest

from conftest import FakeResponse, api_ok


@pytest.fixture
def api(plugin_mod):
    return plugin_mod._SungrowAPI(
        "https://example.test/openapi", "test-appkey", "test-secret",
    )


def test_login_success(api, fake_session):
    fake_session.queue("login", api_ok({"token": "tok", "login_state": "1"}))
    assert api.login("test-user", "test-pass") == "tok"
    call = fake_session.calls[0]
    assert call["url"] == "https://example.test/openapi/login"
    assert call["headers"]["x-access-key"] == "test-secret"
    assert call["headers"]["sys_code"] == "901"
    assert "token" not in call["headers"]


def test_login_rejected(api, fake_session):
    fake_session.queue("login", api_ok({"token": "tok", "login_state": "0"}))
    with pytest.raises(RuntimeError, match="login failed"):
        api.login("test-user", "test-pass")


def test_http_failure(api, fake_session):
    fake_session.queue("login", FakeResponse(500, None, "boom"))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        api.login("test-user", "test-pass")


def test_api_error(api, fake_session):
    fake_session.queue("login", FakeResponse(200, {
        "result_code": "E00003", "result_msg": "bad appkey",
    }))
    with pytest.raises(RuntimeError, match="bad appkey"):
        api.login("test-user", "test-pass")


def test_realtime_data(api, fake_session):
    fake_session.queue("getDeviceRealTimeData", api_ok({
        "device_point_list": [{"device_point": {"p83022": "1"}}],
    }))
    points = api.get_device_realtime_data("tok", "123", ["83022"])
    call = fake_session.calls[0]
    assert call["json"]["ps_key_list"] == ["123_11_0_0"]
    assert call["json"]["device_type"] == 11
    assert call["headers"]["token"] == "tok"
    assert points["p83022"] == "1"


def test_empty_realtime_data(api, fake_session):
    fake_session.queue("getDeviceRealTimeData", api_ok({"device_point_list": []}))
    assert len(api.get_device_realtime_data("tok", "123", ["83022"])) == 0


def test_plant_list(api, fake_session):
    fake_session.queue("getPowerStationList", api_ok({"pageList": [{"ps_id": 1}]}))
    plants = api.get_plant_list("tok")
    assert len(plants) == 1
    assert plants[0]["ps_id"] == 1


def test_device_list(api, fake_session):
    devices = [{"device_type": 14, "ps_key": "1_14_1_1"}]
    fake_session.queue("getDeviceList", api_ok({"pageList": devices}))

    assert api.get_device_list("tok", "1") == devices
    call = fake_session.calls[0]
    assert call["json"]["ps_id"] == "1"
    assert call["json"]["curPage"] == 1
    assert call["json"]["size"] == 100


def test_realtime_data_for_device(api, fake_session):
    fake_session.queue("getDeviceRealTimeData", api_ok({
        "device_point_list": [{"device_point": {"p13149": "1693"}}],
    }))

    points = api.get_device_realtime_data(
        "tok", "1", ["13149"], device_type=14, ps_key="1_14_1_1",
    )

    call = fake_session.calls[0]
    assert call["json"]["device_type"] == 14
    assert call["json"]["ps_key_list"] == ["1_14_1_1"]
    assert points == {"p13149": "1693"}
