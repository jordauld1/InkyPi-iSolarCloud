from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
from datetime import datetime, timedelta
import logging
import json
import os
import pytz
import re
import requests

logger = logging.getLogger(__name__)

# Regional gateway URLs for the iSolarCloud Developer (Open) API
API_GATEWAYS = {
    "global": "https://gateway.isolarcloud.com/openapi",
    "europe": "https://gateway.isolarcloud.eu/openapi",
    "australia": "https://augateway.isolarcloud.com/openapi",
    "international": "https://gateway.isolarcloud.com.hk/openapi",
}

# Plant-level measuring point IDs (device_type = 11)
POINT_IDS = [
    "83022",  # Daily Yield of Plant (Wh)
    "83024",  # Plant Total Yield (Wh)
    "83033",  # Plant Power (W)
    "83072",  # Feed-in Energy Today (Wh)
    "83102",  # Energy Purchased Today (Wh)
    "83106",  # Load Power (W)
    "83252",  # Battery Level (SOC) (%)
    "83118",  # Daily Load Consumption (Wh)
]

# Hybrid inverter (device_type 14) power points, all W and >= 0
ESS_DEVICE_TYPE = 14
ESS_IMPORT_POINT = "13149"     # Purchased power (from grid)
ESS_EXPORT_POINT = "13121"     # Export power (to grid)
ESS_CHARGE_POINT = "13126"     # Battery charging power
ESS_DISCHARGE_POINT = "13150"  # Battery discharging power
ESS_POINT_IDS = [ESS_IMPORT_POINT, ESS_EXPORT_POINT, ESS_CHARGE_POINT, ESS_DISCHARGE_POINT]


class ISolarCloud(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["style_settings"] = True
        return template_params

    def generate_image(self, settings, device_config):
        # Load credentials from .env
        username = device_config.load_env_key("ISOLARCLOUD_USERNAME")
        password = device_config.load_env_key("ISOLARCLOUD_PASSWORD")
        appkey = device_config.load_env_key("ISOLARCLOUD_APPKEY")
        secret_key = device_config.load_env_key("ISOLARCLOUD_SECRET")

        if not all([username, password, appkey, secret_key]):
            raise RuntimeError(
                "iSolarCloud credentials not configured. "
                "Add ISOLARCLOUD_USERNAME, ISOLARCLOUD_PASSWORD, ISOLARCLOUD_APPKEY, "
                "and ISOLARCLOUD_SECRET to your .env file."
            )

        api_region = settings.get("api_region", "global")
        api_base = API_GATEWAYS.get(api_region, API_GATEWAYS["global"])
        ps_id = settings.get("ps_id", "").strip()

        api = _SungrowAPI(api_base, appkey, secret_key)

        # Authenticate
        token = api.login(username, password)

        # Auto-detect ps_id if not provided
        if not ps_id:
            plants = api.get_plant_list(token)
            if not plants:
                raise RuntimeError(
                    "No power stations found on this iSolarCloud account."
                )
            listing = ", ".join(f"{p.get('ps_id')} ({p.get('ps_name', '')})" for p in plants)
            logger.info("iSolarCloud power stations on this account: %s", listing)
            if len(plants) > 1:
                logger.warning(
                    "Multiple power stations found; using the first. "
                    "Set Power Station ID in the plugin settings to choose another."
                )
            ps_id = str(plants[0]["ps_id"])
            logger.info("Auto-detected Power Station ID: %s (%s)", ps_id, plants[0].get("ps_name", ""))

        # Fetch real-time data
        device_points = api.get_device_realtime_data(token, ps_id, POINT_IDS)
        if not device_points:
            raise RuntimeError(
                f"No data for Power Station ID {ps_id}. "
                "Check the ID, or leave it blank to auto-detect."
            )
        ess_key, ess_points = self._fetch_ess(api, token, ps_id)

        # Parse metrics
        plant_name = device_points.get("device_name", f"Plant {ps_id}")
        metrics = self._parse_metrics(device_points, plant_name, ess_points)

        # Build template params
        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)

        if time_format == "24h":
            last_refresh = now.strftime("%H:%M")
        else:
            last_refresh = now.strftime("%I:%M %p").lstrip("0")
        current_date = f"{now:%A, %B} {now.day}"
        history = self._record_and_load_history(metrics, now, ps_id)
        history = self._backfill_history(api, token, ps_id, ess_key, now, tz, history)

        template_params = {
            "metrics": metrics,
            "current_date": current_date,
            "last_refresh": last_refresh,
            "plugin_settings": settings,
            "plant_name": metrics.get("plant_name", "iSolarCloud"),
            "history": history,
            "chart": self._chart_series(history),
        }

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        image = self.render_image(dimensions, "isolarcloud.html", "isolarcloud.css", template_params)
        if not image:
            raise RuntimeError("Failed to render solar dashboard, please check logs.")
        return image

    @staticmethod
    def _chart_series(history):
        return {
            "labels": [h.get("time", "") for h in history],
            "battery_soc": [h.get("battery_soc", 0) for h in history],
            "solar_kw": [h.get("solar_kw", 0) for h in history],
            "grid_import_kw": [h.get("grid_import_kw", 0) for h in history],
            "grid_export_kw": [h.get("grid_export_kw", 0) for h in history],
        }

    def _fetch_ess(self, api, token, ps_id):
        try:
            devices = api.get_device_list(token, ps_id)
            for device in devices:
                key = device.get("ps_key")
                if str(device.get("device_type")) == str(ESS_DEVICE_TYPE) and key:
                    return key, api.get_device_realtime_data(
                        token, ps_id, ESS_POINT_IDS, device_type=ESS_DEVICE_TYPE, ps_key=key,
                    )
            return None, {}
        except RuntimeError as e:
            logger.warning("iSolarCloud battery/grid points unavailable, using estimates: %s", e)
            return None, {}

    # ── Metrics parsing ──────────────────────────────────────────────────

    def _parse_metrics(self, device_points, plant_name, ess_points=None):
        """Extract display metrics from the device real-time data point map."""

        def pf(key, default=0.0):
            """Parse a point value to float."""
            try:
                return float(device_points.get(key, default))
            except (TypeError, ValueError):
                return default

        def pf_opt(points, key):
            """Parse a point value to float, or None when unavailable."""
            try:
                return float(points[key])
            except (KeyError, TypeError, ValueError):
                return None

        ess = ess_points or {}

        # Values from the API are in Wh for energy, W for power
        today_energy_wh = pf("p83022")
        total_energy_wh = pf("p83024")
        pv_power_w = pf("p83033")
        feed_in_wh = pf("p83072")
        energy_purchased_wh = pf("p83102")
        load_power_w = pf("p83106")
        battery_soc = pf("p83252") * 100  # API returns as decimal fraction

        # Convert Wh to kWh for display
        today_energy = round(today_energy_wh / 1000, 1) if today_energy_wh else 0.0
        total_energy = round(total_energy_wh / 1000, 1) if total_energy_wh else 0.0
        today_grid_feed = round(feed_in_wh / 1000, 1) if feed_in_wh else 0.0
        today_grid_import = round(energy_purchased_wh / 1000, 1) if energy_purchased_wh else 0.0
        curr_power = round(pv_power_w / 1000, 2) if pv_power_w else 0.0

        # Net power: positive = importing, negative = exporting
        imp = pf_opt(ess, f"p{ESS_IMPORT_POINT}")
        exp = pf_opt(ess, f"p{ESS_EXPORT_POINT}")
        if imp is not None and exp is not None:
            net_power_w = imp - exp
        else:
            # Fallback: ignores battery flow
            net_power_w = load_power_w - pv_power_w

        chg = pf_opt(ess, f"p{ESS_CHARGE_POINT}")
        dis = pf_opt(ess, f"p{ESS_DISCHARGE_POINT}")
        if chg is not None or dis is not None:
            battery_power = round(((chg or 0.0) - (dis or 0.0)) / 1000, 2)
        else:
            battery_power = None

        load_wh = pf_opt(device_points, "p83118")
        if load_wh is not None:
            today_load = round(max(load_wh / 1000, 0.0), 1)
        else:
            # Fallback: includes battery charge
            today_load = round(today_energy - today_grid_feed + today_grid_import, 1)
            if today_load < 0:
                today_load = 0.0

        # Self-sufficiency: share of household use not drawn from the grid
        self_sufficiency = 0.0
        if today_load > 0:
            self_sufficiency = round(min(max((today_load - today_grid_import) / today_load * 100, 0.0), 100.0), 1)

        return {
            "plant_name": plant_name,
            "curr_power": curr_power,
            "battery_power": battery_power,
            "grid_power": round(net_power_w / 1000, 2),
            "battery_soc": int(round(min(max(battery_soc, 0.0), 100.0))),
            "today_energy": today_energy,
            "today_grid_feed": today_grid_feed,
            "today_grid_import": today_grid_import,
            "today_load": today_load,
            "self_sufficiency": self_sufficiency,
            "total_energy": total_energy,
        }

    # ── History recording ────────────────────────────────────────────────

    HISTORY_MAX_ENTRIES = 1440  # one day at 1-minute refreshes
    HISTORY_CHUNK = timedelta(hours=3)
    HISTORY_MAX_CHUNKS = 8
    HISTORY_PLANT_POINTS = ["83033", "83252", "83106"]
    HISTORY_ESS_POINTS = [ESS_IMPORT_POINT, ESS_EXPORT_POINT]

    def _history_path(self, ps_id):
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(ps_id)) or "default"
        return self.get_plugin_dir(f"history_{safe_id}.json")

    def _record_and_load_history(self, metrics, now, ps_id):
        """Append current reading to this plant's history file and return today's entries."""
        path = self._history_path(ps_id)

        # Load existing history
        history = []
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    history = json.load(f)
            except (json.JSONDecodeError, OSError):
                history = []
        if not isinstance(history, list):
            history = []

        # Filter to today before applying the entry cap
        today_str = now.strftime("%Y-%m-%d")
        history = [
            h for h in history
            if isinstance(h, dict) and str(h.get("ts", "")).startswith(today_str)
        ]

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
        history = history[-self.HISTORY_MAX_ENTRIES:]

        self._save_history(path, history)

        # Remove the old shared history file
        legacy = self.get_plugin_dir("history.json")
        if os.path.exists(legacy):
            try:
                os.remove(legacy)
            except OSError:
                pass

        return history

    @staticmethod
    def _save_history(path, history):
        """Save a history list atomically."""
        try:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(history, f)
            os.replace(tmp, path)
        except OSError as e:
            logger.warning("Failed to save history: %s", e)

    def _backfill_history(self, api, token, ps_id, ess_key, now, tz, history):
        """Merge today's minute samples with later local readings and cache them."""
        existing_api = {
            h["ts"]: h for h in history if h.get("src") == "api"
        }
        if existing_api:
            start = max(datetime.fromisoformat(ts) for ts in existing_api)
        else:
            start = tz.localize(datetime(now.year, now.month, now.day))

        def fetch(key, points):
            rows = []
            window_start = start
            for _ in range(self.HISTORY_MAX_CHUNKS):
                if window_start >= now:
                    break
                window_end = min(window_start + self.HISTORY_CHUNK, now)
                rows.extend(api.get_minute_data(
                    token, key, points,
                    window_start.astimezone(tz).strftime("%Y%m%d%H%M%S"),
                    window_end.astimezone(tz).strftime("%Y%m%d%H%M%S"),
                ))
                window_start = window_end
            return rows

        try:
            plant_rows = fetch(f"{ps_id}_11_0_0", self.HISTORY_PLANT_POINTS)
            ess_rows = fetch(ess_key, self.HISTORY_ESS_POINTS) if ess_key else []
        except RuntimeError as e:
            logger.warning("iSolarCloud history unavailable, using local readings: %s", e)
            return history

        ess_by_stamp = {row["time_stamp"]: row for row in ess_rows}

        def number(row, key):
            try:
                return float(row.get(key, 0))
            except (TypeError, ValueError):
                return 0.0

        for row in plant_rows:
            stamp = row["time_stamp"]
            local_time = tz.localize(datetime.strptime(stamp, "%Y%m%d%H%M%S"))
            pv = number(row, "p83033")
            soc = number(row, "p83252")
            load = number(row, "p83106")
            inverter = ess_by_stamp.get(stamp)
            if inverter is not None:
                imp = number(inverter, f"p{ESS_IMPORT_POINT}")
                exp = number(inverter, f"p{ESS_EXPORT_POINT}")
            else:
                net = load - pv
                imp = max(net, 0)
                exp = max(-net, 0)
            entry = {
                "ts": local_time.isoformat(),
                "time": local_time.strftime("%H:%M"),
                "battery_soc": int(round(min(max(soc * 100, 0), 100))),
                "solar_kw": round(pv / 1000, 2),
                "grid_import_kw": round(imp / 1000, 2),
                "grid_export_kw": round(exp / 1000, 2),
                "src": "api",
            }
            existing_api[entry["ts"]] = entry

        latest_api = max((datetime.fromisoformat(ts) for ts in existing_api), default=None)
        merged = list(existing_api.values())
        merged.extend(
            h for h in history
            if h.get("src") != "api"
            and (latest_api is None or datetime.fromisoformat(h["ts"]) > latest_api)
        )
        merged.sort(key=lambda h: datetime.fromisoformat(h["ts"]))
        merged = merged[-self.HISTORY_MAX_ENTRIES:]
        self._save_history(self._history_path(ps_id), merged)
        return merged


# ── iSolarCloud Developer API V1 plaintext client ───────────────────────

class _SungrowAPI:
    """Plaintext client for the iSolarCloud Developer Portal API (V1)."""

    def __init__(self, api_base, appkey, secret_key):
        self.api_base = api_base
        self.appkey = appkey
        self.secret_key = secret_key

    def login(self, username, password):
        """Authenticate and return a session token (valid 24 h)."""
        payload = {
            "appkey": self.appkey,
            "user_account": username,
            "user_password": password,
        }
        result = self._api_call("login", payload)
        data = result.get("result_data", {})
        token = data.get("token")
        if not token or data.get("login_state") != "1":
            raise RuntimeError("iSolarCloud login failed – check your credentials.")
        return token

    def get_plant_list(self, token):
        """Return a list of power stations for the authenticated user."""
        payload = {
            "appkey": self.appkey,
            "token": token,
            "curPage": 1,
            "size": 100,
        }
        result = self._api_call("getPowerStationList", payload)
        data = result.get("result_data", {})
        return data.get("pageList", [])

    def get_device_list(self, token, ps_id):
        """Return devices belonging to a power station."""
        payload = {
            "appkey": self.appkey,
            "token": token,
            "ps_id": ps_id,
            "curPage": 1,
            "size": 100,
        }
        result = self._api_call("getDeviceList", payload)
        data = result.get("result_data", {})
        return data.get("pageList", [])

    def get_device_realtime_data(self, token, ps_id, point_ids, device_type=11, ps_key=None):
        """Fetch real-time data points for a plant or device."""
        if ps_key is None:
            ps_key = f"{ps_id}_11_0_0"
        payload = {
            "appkey": self.appkey,
            "token": token,
            "device_type": device_type,
            "point_id_list": point_ids,
            "ps_key_list": [ps_key],
        }
        result = self._api_call("getDeviceRealTimeData", payload)
        data = result.get("result_data", {})
        device_list = data.get("device_point_list", [])
        if device_list:
            return device_list[0].get("device_point", {})
        return {}

    def get_minute_data(self, token, ps_key, point_ids, start_ts, end_ts, interval=5):
        """Return 5-minute history rows for one ps_key (window must be <= 3 hours)."""
        payload = {
            "appkey": self.appkey,
            "token": token,
            "ps_key_list": [ps_key],
            "points": ",".join(f"p{point_id}" for point_id in point_ids),
            "start_time_stamp": start_ts,
            "end_time_stamp": end_ts,
            "minute_interval": interval,
        }
        result = self._api_call("getDevicePointMinuteDataList", payload)
        return (result.get("result_data") or {}).get(ps_key) or []

    def _api_call(self, endpoint, payload):
        """Make a plaintext API call to iSolarCloud."""
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "sys_code": "901",
            "x-access-key": self.secret_key,
        }
        if "token" in payload:
            headers["token"] = payload["token"]

        url = f"{self.api_base}/{endpoint}"
        session = get_http_session()
        try:
            resp = session.post(url, headers=headers, json=payload, timeout=30)
        except requests.RequestException as e:
            logger.error("iSolarCloud request to %s failed: %s", endpoint, e)
            raise RuntimeError("iSolarCloud unreachable. Check the Pi's network connection and the selected region.") from e

        if resp.status_code != 200:
            logger.error("iSolarCloud API error [%d]: %s", resp.status_code, resp.text[:200])
            raise RuntimeError(f"iSolarCloud API request failed (HTTP {resp.status_code}).")

        try:
            result = resp.json()
        except ValueError as e:
            logger.error("iSolarCloud returned non-JSON for %s: %s", endpoint, resp.text[:200])
            raise RuntimeError("iSolarCloud returned an unexpected response. Try again later.") from e
        result_code = result.get("result_code")
        if str(result_code) != "1":
            msg = result.get("result_msg", "Unknown error")
            logger.error("iSolarCloud API error: %s (code %s)", msg, result_code)
            raise RuntimeError(f"iSolarCloud: {msg}")

        return result
