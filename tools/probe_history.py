"""Probe iSolarCloud minute history without changing the plugin.

History endpoint parameters and timestamp semantics are unverified; consult the
Developer Portal and use this script only with an account owner's credentials.
"""

import argparse
from datetime import datetime, timedelta
import json
import os
import sys
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests


API_GATEWAYS = {
    "global": "https://gateway.isolarcloud.com/openapi",
    "europe": "https://gateway.isolarcloud.eu/openapi",
    "australia": "https://augateway.isolarcloud.com/openapi",
    "international": "https://gateway.isolarcloud.com.hk/openapi",
}
CREDENTIAL_KEYS = (
    "ISOLARCLOUD_USERNAME",
    "ISOLARCLOUD_PASSWORD",
    "ISOLARCLOUD_APPKEY",
    "ISOLARCLOUD_SECRET",
)


def api_call(base, endpoint, payload, secret, token=None):
    """Use the plugin's V1 plaintext POST convention, retaining probe metadata."""
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "sys_code": "901",
        "x-access-key": secret,
    }
    if token is not None:
        headers["token"] = token
    started = time.perf_counter()
    response = requests.post(
        f"{base}/{endpoint}", headers=headers, json=payload, timeout=30
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{endpoint}: invalid JSON (HTTP {response.status_code})") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"{endpoint}: expected a JSON object (HTTP {response.status_code})")
    if endpoint != "login" and endpoint != "getPowerStationList":
        return response.status_code, elapsed_ms, len(response.content), result
    if response.status_code != 200:
        raise RuntimeError(f"{endpoint}: HTTP {response.status_code}")
    if str(result.get("result_code")) != "1":
        raise RuntimeError(f"{endpoint}: {result.get('result_msg', 'Unknown error')}")
    return response.status_code, elapsed_ms, len(response.content), result


def redact(value, secrets):
    """Remove known credentials from any output, including a raw API echo."""
    if isinstance(value, dict):
        return {redact(key, secrets): redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
    return value


def samples_for_point(data, point):
    """Find obvious point series or timestamped rows without assuming a schema."""
    names = {point, f"p{point}"}
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in names and isinstance(value, list):
                    found.extend(value)
                elif key in names and any(
                    time_key in node
                    for time_key in ("time", "timestamp", "time_stamp", "collect_time")
                ):
                    found.append(node)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="getDevicePointMinuteDataList")
    parser.add_argument("--points", default="83033,83252")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--hours", type=float, default=6)
    parser.add_argument("--end-offset-hours", type=float, default=0,
                        help="shift the window end into the future for failure-mode probing")
    parser.add_argument("--param-style", choices=("a", "b", "c"), default="a")
    parser.add_argument("--raw", action="store_true")
    args = parser.parse_args()

    missing = [key for key in CREDENTIAL_KEYS if not os.environ.get(key)]
    if missing:
        print("Missing environment keys: " + ", ".join(missing))
        return 2

    secrets = [os.environ[key] for key in CREDENTIAL_KEYS]
    region = os.environ.get("ISOLARCLOUD_REGION", "global")
    if region not in API_GATEWAYS:
        print("Invalid ISOLARCLOUD_REGION; choose: " + ", ".join(API_GATEWAYS))
        return 2
    points = [point.strip().removeprefix("p") for point in args.points.split(",")]
    if not points or any(not point.isdecimal() for point in points):
        print("--points must be a comma-separated list of numeric point IDs")
        return 2
    if args.interval <= 0 or args.hours <= 0:
        print("--interval and --hours must be positive")
        return 2

    try:
        base = API_GATEWAYS[region]
        appkey = os.environ["ISOLARCLOUD_APPKEY"]
        _, _, _, login = api_call(
            base,
            "login",
            {
                "appkey": appkey,
                "user_account": os.environ["ISOLARCLOUD_USERNAME"],
                "user_password": os.environ["ISOLARCLOUD_PASSWORD"],
            },
            os.environ["ISOLARCLOUD_SECRET"],
        )
        login_data = login.get("result_data") or {}
        token = login_data.get("token")
        if not token or login_data.get("login_state") != "1":
            raise RuntimeError("iSolarCloud login failed; check credentials")
        secrets.append(token)

        ps_id = os.environ.get("ISOLARCLOUD_PS_ID")
        if not ps_id:
            _, _, _, plants_response = api_call(
                base,
                "getPowerStationList",
                {"appkey": appkey, "token": token, "curPage": 1, "size": 100},
                os.environ["ISOLARCLOUD_SECRET"],
                token,
            )
            plants = (plants_response.get("result_data") or {}).get("pageList") or []
            if not plants:
                raise RuntimeError("No power stations found on this account")
            ps_id = str(plants[0]["ps_id"])

        timezone_name = os.environ.get("ISOLARCLOUD_TIMEZONE")
        if timezone_name:
            now = datetime.now(ZoneInfo(timezone_name))
            print(f"Window timezone: {timezone_name} (provided by ISOLARCLOUD_TIMEZONE)")
        else:
            now = datetime.now().astimezone()
            print(f"Window timezone: {now.tzinfo} (system local; verify it is plant local)")
        now += timedelta(hours=args.end_offset_hours)
        start = now - timedelta(hours=args.hours)
        ps_key = f"{ps_id}_11_0_0"
        payload = {
            "appkey": appkey,
            "token": token,
            "points": ",".join(points if args.param_style == "c" else [f"p{p}" for p in points]),
            "start_time_stamp": start.strftime("%Y%m%d%H%M%S"),
            "end_time_stamp": now.strftime("%Y%m%d%H%M%S"),
            "minute_interval": args.interval,
        }
        if args.param_style == "b":
            payload["ps_key"] = ps_key
        else:
            payload["ps_key_list"] = [ps_key]
        status, elapsed_ms, size, result = api_call(
            base, args.endpoint, payload, os.environ["ISOLARCLOUD_SECRET"], token
        )
        print(f"HTTP status: {status}")
        print(f"result_code: {redact(result.get('result_code'), secrets)}")
        print(f"result_msg: {redact(result.get('result_msg'), secrets)}")
        print(f"elapsed_ms: {elapsed_ms}")
        print(f"response_bytes: {size}")
        data = result.get("result_data")
        print(f"result_data keys: {redact(list(data), secrets) if isinstance(data, dict) else '(not an object)'}")
        for point in points:
            samples = samples_for_point(data, point)
            if samples:
                print(f"point {point}: {len(samples)} samples")
                print(json.dumps(redact(samples[:3], secrets), ensure_ascii=False))
                print(json.dumps(redact(samples[-3:], secrets), ensure_ascii=False))
        if args.raw:
            print(json.dumps(redact(result, secrets), indent=2, ensure_ascii=False))
        return 0
    except (requests.RequestException, RuntimeError, KeyError, ZoneInfoNotFoundError) as exc:
        print(f"Probe failed: {redact(str(exc), secrets)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
