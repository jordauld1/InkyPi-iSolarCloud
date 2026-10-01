"""Discover plant-level iSolarCloud measuring points for plan 005."""

import argparse
import os
import re
import sys
import time

import requests


API_GATEWAYS = {
    "global": "https://gateway.isolarcloud.com/openapi",
    "europe": "https://gateway.isolarcloud.eu/openapi",
    "australia": "https://augateway.isolarcloud.com/openapi",
    "international": "https://gateway.isolarcloud.com.hk/openapi",
}

KNOWN_NAMES = {
    "83002": "Inverter AC Power",
    "83006": "Meter Daily Yield",
    "83011": "Meter E-daily Consumption",
    "83022": "Daily Yield of Plant",
    "83024": "Plant Total Yield",
    "83032": "Meter AC Power",
    "83033": "Plant Power",
    "83072": "Daily Feed-in Energy",
    "83097": "Daily Load Energy Consumption from PV",
    "83102": "Daily Purchased Energy",
    "83106": "Load Power",
    "83119": "Daily Feed-in Energy (PV)",
    "83252": "Battery Level (SOC)",
    "83549": "Grid active power",
}


def chunks(start, end, size):
    """Return inclusive ranges of at most size point IDs."""
    return [
        (first, min(first + size - 1, end))
        for first in range(start, end + 1, size)
    ]


def parse_points(device_point):
    """Return sorted (id, value) pairs for populated measuring points."""
    return sorted(
        ((key[1:], value) for key, value in device_point.items()
         if re.fullmatch(r"p\d+", key) and value not in (None, "", "--")),
        key=lambda item: int(item[0]),
    )


def api_call(base, endpoint, payload, secret, token=None):
    """Call the iSolarCloud Open API using the plugin's request format."""
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "sys_code": "901",
        "x-access-key": secret,
    }
    if token is not None:
        headers["token"] = token

    response = requests.post(
        f"{base}/{endpoint}", headers=headers, json=payload, timeout=30
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"iSolarCloud API request failed (HTTP {response.status_code})."
        )

    result = response.json()
    if str(result.get("result_code")) != "1":
        raise RuntimeError(f"iSolarCloud: {result.get('result_msg', 'Unknown error')}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=83001)
    parser.add_argument("--end", type=int, default=83999)
    parser.add_argument("--chunk", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()

    required = (
        "ISOLARCLOUD_USERNAME",
        "ISOLARCLOUD_PASSWORD",
        "ISOLARCLOUD_APPKEY",
        "ISOLARCLOUD_SECRET",
    )
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        print("Missing environment variables: " + ", ".join(missing))
        return 2

    if args.chunk <= 0 or args.delay < 0 or args.start > args.end:
        parser.error("require --chunk > 0, --delay >= 0, and --start <= --end")

    appkey = os.environ["ISOLARCLOUD_APPKEY"]
    secret = os.environ["ISOLARCLOUD_SECRET"]
    region = os.environ.get("ISOLARCLOUD_REGION", "global")
    if region not in API_GATEWAYS:
        parser.error("ISOLARCLOUD_REGION must be global, europe, australia, or international")
    base = API_GATEWAYS[region]

    login = api_call(base, "login", {
        "appkey": appkey,
        "user_account": os.environ["ISOLARCLOUD_USERNAME"],
        "user_password": os.environ["ISOLARCLOUD_PASSWORD"],
    }, secret)
    login_data = login.get("result_data", {})
    token = login_data.get("token")
    if not token or login_data.get("login_state") != "1":
        raise RuntimeError("iSolarCloud login failed – check your credentials.")

    plants_result = api_call(base, "getPowerStationList", {
        "appkey": appkey,
        "token": token,
        "curPage": 1,
        "size": 100,
    }, secret, token)
    plants = plants_result.get("result_data", {}).get("pageList", [])
    print("Plants")
    for plant in plants:
        print(f"{plant['ps_id']}  {plant.get('ps_name', '')}")

    ps_id = os.environ.get("ISOLARCLOUD_PS_ID")
    if not ps_id:
        if not plants:
            raise RuntimeError("No power stations found on this iSolarCloud account.")
        ps_id = str(plants[0]["ps_id"])

    found = {}
    for index, (first, last) in enumerate(chunks(args.start, args.end, args.chunk)):
        if index:
            time.sleep(args.delay)
        try:
            result = api_call(base, "getDeviceRealTimeData", {
                "appkey": appkey,
                "token": token,
                "device_type": 11,
                "point_id_list": [str(point_id) for point_id in range(first, last + 1)],
                "ps_key_list": [f"{ps_id}_11_0_0"],
            }, secret, token)
        except RuntimeError as error:
            print(f"chunk {first}-{last}: {error}")
            continue
        device_list = result.get("result_data", {}).get("device_point_list", [])
        if device_list:
            found.update(parse_points(device_list[0].get("device_point", {})))

    print("Points")
    for point_id, value in sorted(found.items(), key=lambda item: int(item[0])):
        print(f"p{point_id}   {value}   {KNOWN_NAMES.get(point_id, '')}")
    print("Fill in the Discovery results table in plans/005-battery-aware-grid-and-usage.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
