"""Render synthetic iSolarCloud dashboards with assets from a local InkyPi checkout."""
import argparse
import math
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tests")]
import inkypi_stubs

inkypi_stubs.install()
from isolarcloud import isolarcloud


SAMPLE = {
    "p83022": "18400",
    "p83024": "12400000",
    "p83033": "3450",
    "p83072": "6200",
    "p83102": "1100",
    "p83106": "2600",
    "p83252": "0.72",
}


def synthetic_history():
    start = datetime(2026, 3, 15, 6, 0, tzinfo=timezone(timedelta(hours=10)))
    history = []
    for step in range(25):
        timestamp = start + timedelta(minutes=30 * step)
        hour = 6 + step / 2
        daylight = math.sin(math.pi * step / 24)
        battery = 20 + 75 * step / 12 if step <= 12 else 95 - 30 * (step - 12) / 12
        grid_import = 0.6 if hour < 8.5 or hour > 16.5 else 0.0
        history.append({
            "ts": timestamp.isoformat(),
            "time": timestamp.strftime("%H:%M"),
            "battery_soc": round(battery),
            "solar_kw": round(5 * daylight, 2),
            "grid_import_kw": grid_import,
            "grid_export_kw": round(2.5 * daylight, 2) if grid_import == 0 else 0.0,
        })
    return history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inkypi", default="../InkyPi", type=Path)
    parser.add_argument("--out", default="preview", type=Path)
    args = parser.parse_args()

    inkypi = args.inkypi.resolve()
    base_render = inkypi / "src" / "plugins" / "base_plugin" / "render"
    if not (base_render / "plugin.html").exists():
        print(f"InkyPi checkout not found at {args.inkypi}")
        return 2

    static = inkypi / "src" / "static"
    fonts = static / "fonts"
    font_faces = [
        {
            "font_family": family,
            "font_weight": weight,
            "font_style": "normal",
            "url": (fonts / filename).as_uri(),
        }
        for family, weight, filename in (
            ("Jost", "normal", "Jost.ttf"),
            ("Jost", "bold", "Jost-SemiBold.ttf"),
            ("Dogica", "normal", "dogicapixel.ttf"),
            ("Dogica", "bold", "dogicapixelbold.ttf"),
        )
    ]
    env = Environment(
        loader=FileSystemLoader([str(REPO / "isolarcloud" / "render"), str(base_render)]),
        autoescape=select_autoescape(["html", "xml"]),
    )
    metrics = isolarcloud.ISolarCloud({"id": "isolarcloud"})._parse_metrics(
        SAMPLE, "My Solar Plant",
    )
    params = {
        "metrics": metrics,
        "history": synthetic_history(),
        "plant_name": "My Solar Plant",
        "current_date": "Sunday, March 15",
        "last_refresh": "10:45 PM",
        "plugin_settings": {},
        "style_sheets": [
            (base_render / "plugin.css").as_uri(),
            (REPO / "isolarcloud" / "render" / "isolarcloud.css").as_uri(),
        ],
        "static_dir": static.as_uri(),
        "font_faces": font_faces,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    cards = []
    template = env.get_template("isolarcloud.html")
    for width, height in [(800, 480), (640, 400), (600, 448), (400, 300)]:
        for orientation, frame_width, frame_height in (
            ("horizontal", width, height),
            ("vertical", height, width),
        ):
            filename = f"{frame_width}x{frame_height}_{orientation}.html"
            path = args.out / filename
            path.write_text(template.render(params), encoding="utf-8")
            print(path)
            cards.append(
                f'<div><div>{frame_width}×{frame_height} {escape(orientation)}</div>'
                f'<iframe src="{escape(filename)}" width="{frame_width}" '
                f'height="{frame_height}" style="border:1px solid #888"></iframe></div>'
            )

    index = (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>iSolarCloud preview</title>"
        "</head><body><div style=\"display:flex; flex-wrap:wrap; gap:16px\">"
        + "".join(cards)
        + "</div></body></html>\n"
    )
    index_path = args.out / "index.html"
    index_path.write_text(index, encoding="utf-8")
    print(index_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
