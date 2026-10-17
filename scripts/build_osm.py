import os
import re
import sqlite3
import sys
from collections import Counter

CITIES = {
    "Алматы":  (43.00, 76.70, 43.50, 77.25),
    "Астана":  (50.90, 71.10, 51.40, 71.85),
    "Шымкент": (42.20, 69.40, 42.50, 69.85),
    "Актобе": (50.18, 57.05, 50.40, 57.40),
    "Караганда": (49.70, 72.95, 49.92, 73.25),
    "Атырау":  (47.03, 51.80, 47.20, 52.05),
    "Актау":   (43.55, 51.05, 43.75, 51.30),
    "Павлодар": (52.20, 76.80, 52.38, 77.15),
    "Семей":   (50.33, 80.10, 50.50, 80.40),
    "Усть-Каменогорск": (49.88, 82.45, 50.05, 82.80),
    "Костанай": (53.12, 63.50, 53.30, 63.80),
    "Петропавловск": (54.80, 69.00, 54.95, 69.30),
    "Тараз":   (42.83, 71.25, 42.97, 71.50),
    "Кызылорда": (44.78, 65.40, 44.92, 65.65),
    "Уральск": (51.15, 51.25, 51.32, 51.50),
    "Талдыкорган": (44.95, 78.28, 45.08, 78.50),
    "Кокшетау": (53.22, 69.28, 53.35, 69.50),
    "Туркестан": (43.25, 68.17, 43.36, 68.35),
    "Конаев":  (43.82, 76.95, 43.92, 77.20),
    "Темиртау": (50.00, 72.85, 50.12, 73.10),
    "Экибастуз": (51.65, 75.20, 51.80, 75.45),
    "Рудный":  (52.93, 63.02, 53.02, 63.25),
    "Жезказган": (47.72, 67.65, 47.85, 67.90),
    "Балхаш":  (46.80, 74.85, 46.92, 75.10),
}
HIGHWAYS = {"residential", "primary", "secondary", "tertiary", "unclassified",
            "living_street", "pedestrian", "trunk", "service", "road"}

TYPE_WORDS = [
    ("улица", r"улица|ул|көшесі|кошесі"),
    ("проспект", r"проспект|пр-т|просп|пр|даңғылы"),
    ("переулок", r"переулок|пер|тұйық көшесі"),
    ("бульвар", r"бульвар|бул|бульвары"),
    ("шоссе", r"шоссе|тас жолы"),
    ("тупик", r"тупик|тұйығы"),
    ("микрорайон", r"микрорайон|мкр|шағын ауданы"),
    ("квартал", r"квартал|кв-л"),
]

DISTRICT_FIX = {"Әулиеата": "Аулиеата", "Жібек жолы": "Жибек Жолы"}
DISTRICT_RE = re.compile(
    r"(?:район|р-н|районы|аудан(?:ы|ы)?|district|район города|қалалық аудан)", re.I
)

NEAR = 0.0012
DEFAULT_MARGIN = 0.10
RELAXED_MARGIN = {"Караганда": 0.5, "Актобе": 0.5}


def norm(t):
    t = t.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def split_type(name):
    n = norm(name)
    for stype, words in TYPE_WORDS:
        m = re.match(rf"^(?:{words})\s+(.+)$", n) or re.match(rf"^(.+?)\s+(?:{words})$", n)
        if m:
            return stype, m.group(1).strip()
    return None, n


def city_of(lat, lon):
    for c, (s, w, n, e) in CITIES.items():
        if s <= lat <= n and w <= lon <= e:
            return c
    return None


def clean_district(name):
    n = DISTRICT_RE.sub(" ", name)
    n = re.sub(r"\s+", " ", n).strip(" .,-")
    return DISTRICT_FIX.get(n, n)


def ru_name(tags):
    return tags.get("name:ru") or tags.get("name")


def sample_points(nodes):
    total = len(nodes)
    if total == 0:
        return []
    idxs = sorted({0, total // 4, total // 2, (3 * total) // 4, total - 1})
    pts = []
    for i in idxs:
        try:
            nd = nodes[i]
            pts.append((nd.lat, nd.lon))
        except Exception:
            continue
    return pts


def main(pbf, out):
    import osmium
    import shapely.wkb as wkb
    from shapely.geometry import Point
    from shapely.prepared import prep

    streets = []
    places = []
    districts = []
    rejected = []
    wkbf = osmium.geom.WKBFactory()

    fp = (osmium.FileProcessor(pbf)
          .with_locations()
          .with_areas(osmium.filter.KeyFilter("boundary")))
    cnt = 0
    for o in fp:
        cnt += 1
        if cnt % 2_000_000 == 0:
            print(f"  ...обработано {cnt:,} объектов", flush=True)
        tags = o.tags
        if o.is_way() and "highway" in tags and tags["highway"] in HIGHWAYS:
            nm = ru_name(tags)
            if not nm:
                continue
            pts = sample_points(o.nodes)
            if not pts:
                continue
            city = city_of(*pts[len(pts) // 2])
            if not city:
                continue
            stype, nn = split_type(nm)
            if nn:
                streets.append((city, stype, nn, pts))
        elif o.is_node() and tags.get("place") in ("suburb", "neighbourhood", "quarter"):
            nm = ru_name(tags)
            if nm:
                city = city_of(o.location.lat, o.location.lon)
                if city:
                    places.append((city, o.location.lat, o.location.lon, nm))
        elif o.is_area() and tags.get("boundary") == "administrative":
            nm = ru_name(tags) or ""
            if not DISTRICT_RE.search(nm):
                continue
            try:
                poly = wkb.loads(wkbf.create_multipolygon(o), hex=True)
                rp = poly.representative_point()
            except Exception:
                continue
            city = city_of(rp.y, rp.x)
            if not city:
                continue
            s_, w_, n_, e_ = CITIES[city]
            minx, miny, maxx, maxy = poly.bounds
            m = RELAXED_MARGIN.get(city, DEFAULT_MARGIN)
            if miny < s_ - m or minx < w_ - m or maxy > n_ + m or maxx > e_ + m:
                rejected.append((city, nm, tags.get("admin_level", "?"),
                                 round(miny, 3), round(minx, 3), round(maxy, 3), round(maxx, 3)))
                continue
            districts.append((city, clean_district(nm), prep(poly), poly))

    print(f"Улиц (участков): {len(streets):,}; мест: {len(places):,}; районов: {len(districts)}")
    by_city = Counter(c for c, *_ in districts)
    print("Районов по городам:", dict(by_city))
    print("Улиц по городам:", dict(Counter(c for c, *_ in streets)))
    print("Города без районов:", [c for c in CITIES if c not in by_city])
    if rejected:
        print("\nОТКЛОНЁННЫЕ районы (город | название | admin_level | юг запад север восток):")
        for r in rejected[:60]:
            print("  ", r)
        print("Если среди них есть настоящие районы города, пришли этот список целиком.")
    if not districts:
        print("ВНИМАНИЕ: районы не найдены. Пришлите мне этот вывод целиком.")

    def district_at(city, lat, lon):
        p = Point(lon, lat)
        own = [(name, pp, poly) for c, name, pp, poly in districts if c == city]
        for name, pp, poly in own:
            if pp.contains(p):
                return name
        best, best_d = None, NEAR
        for name, pp, poly in own:
            d = poly.distance(p)
            if d < best_d:
                best, best_d = name, d
        return best

    agg = Counter()
    for city, stype, nn, pts in streets:
        for lat, lon in pts:
            agg[(city, nn, stype, district_at(city, lat, lon))] += 1

    if os.path.exists(out):
        os.remove(out)
    db = sqlite3.connect(out)
    db.execute("CREATE TABLE street(city TEXT, name TEXT, type TEXT, district TEXT, n INT)")
    db.executemany("INSERT INTO street VALUES (?,?,?,?,?)",
                   [(c, nn, st, d, k) for (c, nn, st, d), k in agg.items()])
    db.execute("CREATE INDEX ix_street ON street(city, name)")
    db.execute("CREATE TABLE place(city TEXT, name TEXT, district TEXT)")
    db.executemany("INSERT INTO place VALUES (?,?,?)",
                   [(c, norm(nm), district_at(c, la, lo)) for c, la, lo, nm in places])
    db.commit()

    print("\nДоля точек улиц с районом по городам с районами:")
    for city in by_city:
        total, with_d = db.execute(
            "SELECT SUM(n), SUM(CASE WHEN district IS NOT NULL THEN n ELSE 0 END) FROM street WHERE city=?",
            (city,)).fetchone()
        print(f"  {city}: {with_d}/{total} = {round(100 * with_d / total)}%")
    db.close()
    print("Готово:", out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Использование: python scripts/build_osm.py путь/к/kazakhstan-latest.osm.pbf")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference", "osm_streets.sqlite")
    main(sys.argv[1], out)
