from conftest import SAMPLE_POINTS, render_dashboard


def dashboard_params(plugin, history_count=2):
    metrics = plugin._parse_metrics(SAMPLE_POINTS, "My Plant")
    history = [
        {
            "ts": f"2026-03-15T06:{i * 30:02d}:00+10:00",
            "time": f"06:{i * 30:02d}",
            "battery_soc": 40,
            "solar_kw": 0.5,
            "grid_import_kw": 0.2,
            "grid_export_kw": 0,
        }
        for i in range(history_count)
    ]
    return {
        "metrics": metrics,
        "current_date": "Sunday, March 15",
        "last_refresh": "12:00 PM",
        "plant_name": "My Plant",
        "history": history,
        "chart": {
            "labels": [h.get("time", "") for h in history],
            "battery_soc": [h.get("battery_soc", 0) for h in history],
            "solar_kw": [h.get("solar_kw", 0) for h in history],
            "grid_import_kw": [h.get("grid_import_kw", 0) for h in history],
            "grid_export_kw": [h.get("grid_export_kw", 0) for h in history],
        },
    }


def test_chart_with_two_entries(plugin):
    html = render_dashboard(dashboard_params(plugin, 2))
    assert 'id="solarChart"' in html
    assert "chart.js" in html


def test_chart_data_is_json(plugin):
    params = dashboard_params(plugin)
    params["history"][0]["time"] = '06:00"</script>'
    params["chart"]["labels"][0] = '06:00"</script>'
    html = render_dashboard(params)
    assert '06:00"</script>' not in html
    assert "</script>" in html


def test_chart_absent_with_one_entry(plugin):
    html = render_dashboard(dashboard_params(plugin, 1))
    assert "solarChart" not in html


def test_energy_values(plugin):
    html = render_dashboard(dashboard_params(plugin))
    assert "18.4" in html
    assert "13.3" in html


def test_battery_bar(plugin):
    html = render_dashboard(dashboard_params(plugin))
    assert "width: 72" in html


def test_battery_soc_renders_without_decimal(plugin):
    html = render_dashboard(dashboard_params(plugin))
    assert '72<span class="metric-unit">%' in html
    assert "72.0" not in html


def test_total_energy_units(plugin):
    params = dashboard_params(plugin)
    params["metrics"]["total_energy"] = 12400.0
    assert "MWh" in render_dashboard(params)
    params["metrics"]["total_energy"] = 500.0
    html = render_dashboard(params)
    assert " kWh" in html
    assert "MWh" not in html
