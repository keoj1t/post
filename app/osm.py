"""Поиск района и типа улицы по справочнику OSM (reference/osm_streets.sqlite).
Если файла нет, всё работает как раньше: функции возвращают None."""
import os
import re
import sqlite3
from app.normalization import CITY_ALIASES

PATH = os.path.join(os.path.dirname(__file__), "..", "reference", "osm_streets.sqlite")
ALIAS = {"нур-султан": "астана", "өскемен": "усть-каменогорск", "қонаев": "конаев", "капчагай": "конаев"}
TYPE_RE = r"улица|ул|проспект|пр-т|просп|пр|переулок|пер|бульвар|бул|шоссе|тупик|микрорайон|мкр|квартал|кв-л|көшесі|көше|кошеси|даңғылы|дангылы|даңғыл|тұйық көшесі|street|st|avenue|ave|road|rd"

_db = None
_cities = {}
_compact_streets = {}


def _compact_name(value):
    return re.sub(r'[\W_]+', '', _norm(value).translate(str.maketrans('әіңғүұқөһ', 'аингуукох')))


def _street_name_keys(value):
    """Conservative spelling variants for Kazakh street names written in Russian case."""
    key = _compact_name(value)
    keys = {key} if key else set()
    if len(key) >= 4:
        if key.endswith("я"):
            keys.add(key[:-1] + "й")
            keys.add(key[:-1])
        for ending, canonical in (("ова", "ов"), ("ева", "ев"), ("ина", "ин"), ("ына", "ын")):
            if key.endswith(ending) and len(key) > len(ending) + 2:
                keys.add(key[:-len(ending)] + canonical)
    return keys


def _conn():
    global _db
    if _db is None and os.path.exists(PATH):
        _db = sqlite3.connect(PATH, check_same_thread=False)
        _cities.update({r[0].lower(): r[0] for r in _db.execute("SELECT DISTINCT city FROM street")})
    return _db


def _city_record(city):
    """Resolve Russian, Kazakh and common Latin city names to the OSM key."""
    if not city:
        return None
    key = _norm(city).removeprefix("город ").strip()
    key = ALIAS.get(key, CITY_ALIASES.get(key, key))
    return _cities.get(key)


def _norm(t):
    t = t.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(rf"^(?:{TYPE_RE})\s+|\s+(?:{TYPE_RE})$", "", t)


def _place_district(db, c, name):
    """Микрорайон / жилой массив: ищем в таблице мест, отбрасывая номер в конце ('аксай 3а' -> 'аксай')."""
    n = _norm(name)
    cands = [n]
    base = re.sub(r"[\s-]+\d+[а-яa-z]?$", "", n)
    if base != n:
        cands.append(base)
    for cand in cands:
        rows = db.execute("SELECT district FROM place WHERE city=? AND (name=? OR name LIKE ? OR name LIKE ?)",
                          (c, cand, cand + " %", cand + "-%")).fetchall()
        ds = {r[0] for r in rows if r[0]}
        if len(ds) == 1:
            return ds.pop()
    return None


def lookup_place_district(city, name):
    """Return a district only when the local place reference maps the name uniquely."""
    db = _conn()
    if db is None or not city or not name:
        return None
    c = _city_record(city)
    return _place_district(db, c, name) if c else None


def lookup_street_type_global(street_name):
    """Infer a street type without a city only when the national OSM majority is clear."""
    db = _conn()
    if db is None or not street_name:
        return None
    name = _norm(street_name)
    rows = db.execute(
        "SELECT type, SUM(n) FROM street "
        "WHERE name=? OR name LIKE ? GROUP BY type",
        (name, "% " + name),
    ).fetchall()
    totals = {kind: count for kind, count in rows if kind and count}
    total = sum(totals.values())
    if not total:
        return None
    kind, count = max(totals.items(), key=lambda item: item[1])
    return kind if count / total >= 0.5 else None


def lookup(city, street_name, street_type=None):
    """-> {'district': str|None, 'street_type': str|None} или None."""
    db = _conn()
    if db is None or not city or not street_name:
        return None
    c = _city_record(city)
    if not c:
        return None
    out = {"district": None, "street_type": None}
    rows = db.execute("SELECT type, district, n FROM street WHERE city=? AND name=?",
                      (c, _norm(street_name))).fetchall()
    if not rows:
        if c not in _compact_streets:
            names = {}
            for (name,) in db.execute('SELECT DISTINCT name FROM street WHERE city=?', (c,)):
                names.setdefault(_compact_name(name), set()).add(name)
            _compact_streets[c] = names
        matches = set().union(*(_compact_streets[c].get(key, set()) for key in _street_name_keys(street_name)))
        if not matches and street_type not in ('микрорайон', 'квартал'):
            base = re.sub(r'\s+\d+[а-яa-z]?$', '', street_name, flags=re.I)
            if base != street_name:
                matches = _compact_streets[c].get(_compact_name(base), set())
        if len(matches) == 1:
            name = next(iter(matches))
            rows = db.execute('SELECT type, district, n FROM street WHERE city=? AND name=?', (c, name)).fetchall()
            if re.sub(r'\s+', ' ', _norm(street_name).translate(str.maketrans('әіңғүұқөһ', 'аингуукох'))) != name:
                out['street_name'] = name
    for idx, key in ((1, "district"), (0, "street_type")):
        tot = {}
        for r in rows:
            if r[idx]:
                tot[r[idx]] = tot.get(r[idx], 0) + r[2]
        if tot:
            best = max(tot, key=tot.get)
            if tot[best] / sum(tot.values()) >= (0.6 if key == "district" else 0.5):
                out[key] = best
    if out["district"] is None and street_type in ("микрорайон", "квартал", None):
        out["district"] = _place_district(db, c, street_name)
    if not out["district"] and not out["street_type"]:
        return None
    return out
