"""地圖資料組裝：校界＋建築量體 → site/data/map/*.geojson。

來源（快取在 data/sources/map/，不重打 API）：
- nthu_rel.json           清大校本部界線（OSM relation 3605515，六段 outer way 需拼環）
- guangfu/boai_boundary   交大官方校界（nycu-life/nycu-maps repo）
- nthu/boai_bldg_geom     OSM 建築 footprint（way geometry）
- nycu_buildings.geojson  光復官方建築（maps.nymu.com.tw，含 NLSC 樓高）
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "sources" / "map"
OUT = ROOT / "site" / "data" / "map"


def rnd(pt):
    return [round(pt[0], 6), round(pt[1], 6)]


def assemble_rings(segments):
    """把 OSM relation 的 outer way 段落拼成閉合環。"""
    segs = [[(p["lon"], p["lat"]) for p in s] for s in segments]
    rings = []
    while segs:
        ring = list(segs.pop(0))
        changed = True
        while changed and ring[0] != ring[-1]:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += list(reversed(s))[1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = list(reversed(s))[:-1] + ring
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        rings.append([rnd(list(p)) for p in ring])
    return rings


def boundary_feature(campus, rings):
    return {"type": "Feature", "properties": {"campus": campus},
            "geometry": {"type": "Polygon", "coordinates": rings}}


def load_boundary_geojson(path, campus):
    d = json.loads(path.read_text())
    g = d["features"][0]["geometry"] if "features" in d else d.get("geometry", d)
    coords = g["coordinates"] if g["type"] == "Polygon" else g["coordinates"][0]
    return boundary_feature(campus, [[rnd(p) for p in ring] for ring in coords])


def osm_ways_to_buildings(path):
    feats = []
    for e in json.loads(path.read_text()).get("elements", []):
        geom = e.get("geometry")
        if not geom or len(geom) < 4:
            continue
        t = e.get("tags", {})
        levels = t.get("building:levels")
        try:
            height = float(t.get("height") or 0) or (float(levels) * 3.5 if levels else None)
        except ValueError:
            height = None
        ring = [rnd([p["lon"], p["lat"]]) for p in geom]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        feats.append({"type": "Feature",
                      "properties": {"name": t.get("name"), "height": height},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return feats


def official_guangfu_buildings(path):
    feats = []
    for f in json.loads(path.read_text()).get("features", []):
        p = f["properties"]
        name = p.get("name:zh") or p.get("name_zh") or p.get("name")
        try:
            height = float(p.get("nlsc_BUILD_H") or 0) or None
        except ValueError:
            height = None
        g = f["geometry"]
        if g["type"] == "Polygon":
            coords = [[rnd(pt) for pt in ring] for ring in g["coordinates"]]
        elif g["type"] == "MultiPolygon":
            coords = [[rnd(pt) for pt in ring] for ring in g["coordinates"][0]]
        else:
            continue
        feats.append({"type": "Feature", "properties": {"name": name, "height": height},
                      "geometry": {"type": "Polygon", "coordinates": coords}})
    return feats


def inside(pt, ring):
    x, y = pt
    c, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            c = not c
        j = i
    return c


def main():
    # 校界
    rel = json.loads((SRC / "nthu_rel.json").read_text())["elements"][0]
    outers = [m["geometry"] for m in rel["members"] if m.get("role") == "outer" and m.get("geometry")]
    nthu_rings = assemble_rings(outers)
    campuses = [
        boundary_feature("nthu-main", [max(nthu_rings, key=len)]),
        load_boundary_geojson(SRC / "guangfu_boundary.geojson", "nycu-guangfu"),
        load_boundary_geojson(SRC / "boai_boundary.geojson", "nycu-boai"),
    ]

    # 建築
    guangfu_ring = campuses[1]["geometry"]["coordinates"][0]
    guangfu = [f for f in official_guangfu_buildings(SRC / "nycu_buildings.geojson")
               if inside(f["geometry"]["coordinates"][0][0], guangfu_ring)]
    buildings = (osm_ways_to_buildings(SRC / "nthu_bldg_geom.json")
                 + guangfu
                 + osm_ways_to_buildings(SRC / "boai_bldg_geom.json"))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "campuses.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": campuses}, ensure_ascii=False))
    (OUT / "buildings.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": buildings}, ensure_ascii=False))
    named = sum(1 for f in buildings if f["properties"]["name"])
    print(f"map data: {len(campuses)} campuses, {len(buildings)} buildings ({named} named), "
          f"{(OUT / 'buildings.geojson').stat().st_size // 1024}KB")


if __name__ == "__main__":
    sys.exit(main())
