#!/usr/bin/env python3
"""Котельные и границы районов из OpenStreetMap через Overpass.

Данные открытые и берутся напрямую, без ключей и выгрузок: демонстрацию можно
повторить у себя, а не поверить на слово. Котельные в OSM размечены по-разному —
`man_made=works` с профилем отопления, `building=boiler_house`, `power=plant`
с источником тепла, — поэтому запрос собирает все распространённые написания.
"""
import json, sys, time, urllib.request, urllib.parse

OVERPASS = "https://overpass-api.de/api/interpreter"
CITY = sys.argv[1] if len(sys.argv) > 1 else "Нижний Новгород"

Q = f"""
[out:json][timeout:120];
area["name"="{CITY}"]["boundary"="administrative"]->.city;
(
  nwr(area.city)["building"="boiler_house"];
  nwr(area.city)["man_made"="works"]["works"="heating"];
  nwr(area.city)["power"="plant"]["plant:source"~"gas|coal|combined"];
  nwr(area.city)["man_made"="heat_plant"];
  nwr(area.city)["amenity"="boiler_house"];
);
out center tags;
"""

QD = f"""
[out:json][timeout:120];
area["name"="{CITY}"]["boundary"="administrative"]->.city;
rel(area.city)["boundary"="administrative"]["admin_level"="9"];
out geom;
"""


def ask(query, tries=3):
    for i in range(tries):
        try:
            data = urllib.parse.urlencode({"data": query}).encode()
            with urllib.request.urlopen(OVERPASS, data, timeout=180) as r:
                return json.load(r)
        except Exception as e:                      # noqa: BLE001
            print(f"  попытка {i+1}: {e}", file=sys.stderr)
            time.sleep(5)
    return {"elements": []}


if __name__ == "__main__":
    pts = ask(Q)
    json.dump(pts, open("raw_boilers.json", "w"), ensure_ascii=False)
    print(f"котельных: {len(pts.get('elements', []))}")
    dis = ask(QD)
    json.dump(dis, open("raw_districts.json", "w"), ensure_ascii=False)
    print(f"районов: {len(dis.get('elements', []))}")
