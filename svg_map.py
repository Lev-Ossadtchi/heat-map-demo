#!/usr/bin/env python3
"""Тот же макет в векторе — то, что уходит в печать.

Разница с растром принципиальная для стены 2,5 × 1,5 м: границы регионов,
точки и подписи остаются резкими при любом увеличении, а типография печатает
без пересчёта разрешения. Растром остаётся только тепловая подложка — она по
природе непрерывная, и вектором её изображать незачем; она вшивается внутрь
файла, так что SVG остаётся одним самодостаточным документом.
"""
import base64
import io
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import render as R

ROOT = Path(__file__).parent
W_MM, H_MM = 2500, 1500          # размер листа на стене


def heat_png(width, height, proj, points, alpha=0.55):
    heat = Image.new("L", (width, height), 0)
    hd = ImageDraw.Draw(heat)
    r = max(6, width // 110)
    for f in points["features"]:
        x, y = proj(*f["geometry"]["coordinates"])
        hd.ellipse([x - r, y - r, x + r, y + r], fill=40)
    heat = heat.filter(ImageFilter.GaussianBlur(r * 0.8))
    peak = max(heat.getdata()) or 1
    heat = heat.point(lambda v: min(255, int(v * 255 / peak * alpha)))
    warm = Image.new("RGB", (width, height), R.HEAT)
    rgba = warm.convert("RGBA")
    rgba.putalpha(heat)
    buf = io.BytesIO()
    rgba.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main():
    regions = json.loads((ROOT / "regions.json").read_text())
    points = json.loads((ROOT / "points.json").read_text())

    w = 2000                                  # система координат внутри SVG
    y0, y1 = R.merc(R.LAT1), R.merc(R.LAT0)
    map_h = int(w * abs(y1 - y0) / math.radians(R.LON1 - R.LON0))
    top, bottom = int(map_h * R.HEAD), int(map_h * R.FOOT)
    h = map_h + top + bottom
    base = R.make_proj(w, map_h)

    def proj(lon, lat):
        x, y = base(lon, lat)
        return x, y + top

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W_MM}mm" height="{W_MM * h / w:.0f}mm" '
        f'viewBox="0 0 {w} {h}" font-family="Arial, Helvetica, sans-serif">',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
        f'<rect y="{top}" width="{w}" height="{map_h}" fill="#eef2f5"/>',
    ]

    for f in regions["features"]:
        col = R.color_for(f["properties"]["count"])
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        d = []
        for poly in polys:
            for ring in poly:
                pts = [proj(x, y) for x, y in ring]
                if len(pts) < 3:
                    continue
                d.append("M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z")
        if d:
            parts.append(f'<path d="{" ".join(d)}" fill="{col}" stroke="#8a97a6" '
                         f'stroke-width="0.7" fill-rule="evenodd"/>')

    png = heat_png(w, h, proj, points)
    parts.append(f'<image x="0" y="0" width="{w}" height="{h}" '
                 f'xlink:href="data:image/png;base64,{png}" '
                 f'href="data:image/png;base64,{png}"/>')

    for f in points["features"]:
        x, y = proj(*f["geometry"]["coordinates"])
        if top <= y <= top + map_h and 0 <= x <= w:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#1b2a38" '
                         f'stroke="#ffffff" stroke-width="1"/>')

    best = sorted(regions["features"], key=lambda f: -f["properties"]["count"])[:2]
    line = " · ".join(f"{f['properties']['name']} — {f['properties']['count']}" for f in best)
    pad = w // 45
    parts += [
        f'<text x="{pad}" y="{top * 0.42:.0f}" font-size="{w // 45}" fill="#16202b">'
        f'Объекты теплоснабжения: покрытие и плотность</text>',
        f'<text x="{pad}" y="{top * 0.78:.0f}" font-size="{w // 95}" fill="#3b4856">'
        f'Больше всего объектов:  {line}</text>',
        f'<text x="{pad}" y="{top + map_h + bottom * 0.55:.0f}" font-size="{w // 95}" fill="#5d6b7a">'
        f'Объектов на карте: {len(points["features"])}. Данные: Wikidata (объекты), '
        f'Natural Earth (границы регионов). Демонстрация подхода: на данных заказчика '
        f'карта строится так же.</text>',
    ]

    step = w // 26
    x = w - pad - step * len(R.STEPS)
    y = top + map_h + bottom * 0.35
    for i, (lim, col) in enumerate(R.STEPS):
        parts.append(f'<rect x="{x + i * step}" y="{y:.0f}" width="{step}" height="{w // 190}" '
                     f'fill="{col}" stroke="#c8d0d8" stroke-width="0.5"/>')
    parts.append(f'<text x="{x}" y="{y - w // 150:.0f}" font-size="{w // 95}" fill="#5d6b7a">'
                 f'Объектов в регионе</text>')
    parts.append('</svg>')

    out = ROOT / "map-печать.svg"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"  {out.name}: {W_MM} × {W_MM * h / w:.0f} мм, {out.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
