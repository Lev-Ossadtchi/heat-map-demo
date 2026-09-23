#!/usr/bin/env python3
"""Сборка данных для карты: точки, привязка к регионам, плотность.

Источники открытые и названы прямо в карте: объекты энергетики России из
Wikidata (координаты и названия) и границы регионов из Natural Earth. Любой
может повторить выгрузку и получить то же самое — в этом и смысл демонстрации.

Привязка точки к региону — не поиск ближайшей границы, а проверка попадания
внутрь многоугольника. Разница видна на вытянутых областях: ближайшая граница
часто принадлежит соседу, и объект уезжает не в тот регион.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
POINT = re.compile(r"Point\(([-\d.]+) ([-\d.]+)\)")


def points():
    raw = json.loads((ROOT / "wd.json").read_text())
    out = []
    for b in raw["results"]["bindings"]:
        m = POINT.match(b["coord"]["value"])
        if not m:
            continue
        lon, lat = float(m.group(1)), float(m.group(2))
        name = b["itemLabel"]["value"]
        if name.startswith("Q") and name[1:].isdigit():   # без русского имени
            continue
        out.append({"name": name, "lon": lon, "lat": lat})
    return out


def regions():
    d = json.loads((ROOT / "ne_states.geojson").read_text())
    feats = []
    for f in d["features"]:
        p = f["properties"]
        if p.get("admin") != "Russia":
            continue
        feats.append({
            "type": "Feature",
            "properties": {"name": p.get("name_ru") or p.get("name"), "count": 0},
            "geometry": f["geometry"],
        })
    return {"type": "FeatureCollection", "features": feats}


def inside(lon, lat, ring):
    """Точка внутри кольца — по числу пересечений луча (алгоритм чёт-нечет)."""
    hit = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            xx = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if xx > lon:
                hit = not hit
    return hit


def in_feature(lon, lat, geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        if not poly:
            continue
        if inside(lon, lat, poly[0]) and not any(inside(lon, lat, h) for h in poly[1:]):
            return True
    return False


def main():
    pts = points()
    reg = regions()
    # Грубый отсев по рамке региона до точной проверки: она в сотни раз дешевле,
    # а полигоны здесь подробные — без него сборка идёт минутами.
    boxes = []
    for f in reg["features"]:
        xs, ys = [], []
        polys = (f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon"
                 else [f["geometry"]["coordinates"]])
        for poly in polys:
            for x, y in poly[0]:
                xs.append(x); ys.append(y)
        boxes.append((min(xs), min(ys), max(xs), max(ys)))

    unmatched = 0
    for p in pts:
        p["region"] = ""
        for f, (x0, y0, x1, y1) in zip(reg["features"], boxes):
            if not (x0 <= p["lon"] <= x1 and y0 <= p["lat"] <= y1):
                continue
            if in_feature(p["lon"], p["lat"], f["geometry"]):
                p["region"] = f["properties"]["name"]
                f["properties"]["count"] += 1
                break
        if not p["region"]:
            unmatched += 1

    (ROOT / "points.json").write_text(json.dumps(
        {"type": "FeatureCollection", "features": [
            {"type": "Feature",
             "properties": {"name": p["name"], "region": p["region"]},
             "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]}}
            for p in pts]}, ensure_ascii=False), encoding="utf-8")
    (ROOT / "regions.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")

    top = sorted(reg["features"], key=lambda f: -f["properties"]["count"])[:5]
    print(f"точек: {len(pts)}, без региона: {unmatched}")
    print("больше всего объектов:",
          ", ".join(f"{f['properties']['name']} — {f['properties']['count']}" for f in top))


if __name__ == "__main__":
    main()
