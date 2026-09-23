#!/usr/bin/env python3
"""Печатный макет карты: точки, зоны покрытия и тепловая подложка.

Рисуется без браузера и без карты-подложки — только из данных. Так макет можно
пересобрать в любом размере: для стены 2,5 × 1,5 м и для просмотра на экране
берётся один и тот же код, меняется лишь число точек на метр.

Тепловая подложка считается честной плотностью: каждая точка добавляет
гауссово пятно, пятна складываются, и шкала растягивается по итоговому
максимуму. Это не размытая картинка поверх точек, а именно плотность объектов.
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
# Рамка карты: европейская часть и Урал, где стоит большинство объектов.
# Рамка подобрана под лист 2,5 × 1,5 м: при этой проекции отношение сторон
# карты вместе с заголовком и подписью совпадает с отношением сторон листа,
# и печатнику не придётся ничего обрезать или добавлять поля.
LON0, LON1 = 19.0, 130.0
LAT0, LAT1 = 41.5, 70.0
HEAD = 0.155          # доля высоты под заголовок
FOOT = 0.075          # и под подпись с источниками и шкалой

SCALE = {"экран": 1600, "печать": 7000}        # ширина в точках
# Две шкалы на одной карте должны быть из разных семейств, иначе читатель не
# понимает, что перед ним: заливка региона или пятно плотности. Зоны —
# холодные и приглушённые, плотность — тёплая. Точки не участвуют ни в одной
# шкале и потому графитовые: они одинаково видны и на синем, и на оранжевом.
# Холодная шкала намеренно остаётся светлой: тёмно-синяя заливка под тёплым
# пятном плотности даёт грязный оливковый, и обе величины перестают читаться.
STEPS = [(0, "#f7f9fa"), (1, "#e4edf3"), (6, "#cddfea"),
         (12, "#b2cde0"), (20, "#96b9d3"), (30, "#7aa5c6")]
HEAT = "#e8642a"          # тёплая подложка плотности
DOT = "#1b2a38"           # графит для точек


def merc(lat):
    """Проекция Меркатора по широте — та же, что у веб-карт."""
    lat = max(min(lat, 85.0), -85.0)
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def make_proj(w, h):
    y0, y1 = merc(LAT1), merc(LAT0)
    def proj(lon, lat):
        x = (lon - LON0) / (LON1 - LON0) * w
        y = (merc(lat) - y0) / (y1 - y0) * h
        return x, y
    return proj


def color_for(count):
    out = STEPS[0][1]
    for lim, col in STEPS:
        if count >= lim:
            out = col
    return out


def draw(width, name):
    # Высота — из самой проекции, иначе карта растянется: в Меркаторе градус
    # широты на севере «длиннее» градуса долготы, и отношение сторон считается
    # не по градусам, а по спроецированным величинам.
    y0, y1 = merc(LAT1), merc(LAT0)
    map_h = int(width * abs(y1 - y0) / math.radians(LON1 - LON0))
    top = int(map_h * HEAD)
    bottom = int(map_h * FOOT)
    h = map_h + top + bottom
    base = make_proj(width, map_h)

    def proj(lon, lat):
        x, y = base(lon, lat)
        return x, y + top

    regions = json.loads((ROOT / "regions.json").read_text())
    points = json.loads((ROOT / "points.json").read_text())

    img = Image.new("RGB", (width, h), "#ffffff")
    dr = ImageDraw.Draw(img)
    dr.rectangle([0, top, width, top + map_h], fill="#eef2f5")
    dr.line([0, top, width, top], fill="#d8dee6", width=max(1, width // 900))

    # ---- зоны покрытия: заливка по числу объектов
    for f in regions["features"]:
        col = color_for(f["properties"]["count"])
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            ring = [proj(x, y) for x, y in poly[0]]
            if len(ring) > 2:
                dr.polygon(ring, fill=col, outline="#8a97a6")

    # ---- тепловая подложка: плотность объектов
    heat = Image.new("L", (width, h), 0)
    hd = ImageDraw.Draw(heat)
    r = max(6, width // 110)
    for f in points["features"]:
        x, y = proj(*f["geometry"]["coordinates"])
        if -r < x < width + r and -r < y < h + r:
            hd.ellipse([x - r, y - r, x + r, y + r], fill=40)
    heat = heat.filter(ImageFilter.GaussianBlur(r * 0.8))
    peak = max(heat.getdata()) or 1
    heat = heat.point(lambda v: min(255, int(v * 255 / peak)))

    warm = Image.new("RGB", (width, h), HEAT)
    img = Image.composite(warm, img, heat.point(lambda v: int(v * 0.5)))

    # ---- объекты
    dot = max(2, width // 500)
    d2 = ImageDraw.Draw(img)
    for f in points["features"]:
        x, y = proj(*f["geometry"]["coordinates"])
        if 0 <= x <= width and 0 <= y <= h:
            d2.ellipse([x - dot, y - dot, x + dot, y + dot],
                       fill=DOT, outline="#ffffff", width=max(1, dot // 3))

    # ---- подписи
    try:
        big = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", width // 45)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", width // 95)
    except OSError:
        big = small = ImageFont.load_default()
    pad = width // 45
    d2.text((pad, int(top * 0.18)), "Объекты теплоснабжения: покрытие и плотность",
            fill="#16202b", font=big)
    best = sorted(regions["features"], key=lambda f: -f["properties"]["count"])[:2]
    lines = [f"{f['properties']['name']} — {f['properties']['count']}" for f in best]
    d2.text((pad, int(top * 0.66)), "Больше всего объектов:  " + " · ".join(lines),
            fill="#3b4856", font=small)
    d2.text((pad, top + map_h + bottom // 3),
            f"Объектов на карте: {len(points['features'])}. "
            "Данные: Wikidata (объекты), Natural Earth (границы регионов). "
            "Демонстрация подхода: на данных заказчика карта строится так же.",
            fill="#5d6b7a", font=small)

    # Шкала заливки — внизу справа, чтобы цвет региона читался в число и не
    # спорил с заголовком за место.
    step_w = width // 26
    sh = max(6, width // 190)
    x = width - pad - step_w * len(STEPS)
    y = top + map_h + bottom // 3
    for i, (lim, col) in enumerate(STEPS):
        d2.rectangle([x + i * step_w, y, x + (i + 1) * step_w, y + sh], fill=col,
                     outline="#c8d0d8")
    d2.text((x, y - sh * 3), "Объектов в регионе", fill="#5d6b7a", font=small)
    d2.text((x, y + sh * 2), "0", fill="#5d6b7a", font=small)
    d2.text((x + step_w * len(STEPS) - step_w // 2, y + sh * 2), "30+",
            fill="#5d6b7a", font=small)

    out = ROOT / f"map-{name}.png"
    img.save(out, "PNG")
    print(f"  {out.name}: {width}×{h} точек, {out.stat().st_size // 1024} КБ")
    return out


if __name__ == "__main__":
    which = sys.argv[1:] or ["экран", "печать"]
    for k in which:
        draw(SCALE[k], k)
