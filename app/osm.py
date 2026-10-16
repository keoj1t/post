"""Поиск района и типа улицы по справочнику OSM (reference/osm_streets.sqlite).
Если файла нет, всё работает как раньше: функции возвращают None."""
import os
import re
import sqlite3

PATH = os.path.join(os.path.dirname(__file__), "..", "reference", "osm_streets.sqlite")
ALIAS = {"нур-султан": "астана", "өскемен": "усть-каменогорск", "қонаев": "конаев", "капчагай": "конаев"}
TYPE_RE = r"улица|ул|проспект|пр-т|просп|пр|переулок|пер|бульвар|бул|шоссе|тупик|микрорайон|мкр|квартал|кв-л"

_db = None
_cities = {}   # 'усть-каменогорск' -> 'Усть-Каменогорск' (названия берём из самой базы)


def _conn():
    global _db
    if _db is None and os.path.exists(PATH):
        _db = sqlite3.connect(PATH, check_same_thread=False)
        _cities.update({r[0].lower(): r[0] for r in _db.execute("SELECT DISTINCT city FROM street")})
    return _db


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


def lookup(city, street_name, street_type=None):
    """-> {'district': str|None, 'street_type': str|None} или None."""
    db = _conn()
    if db is None or not city or not street_name:
        return None
    key = city.lower().replace("город", "").replace("ё", "е").strip()
    c = _cities.get(ALIAS.get(key, key))
    if not c:
        return None
    out = {"district": None, "street_type": None}
    rows = db.execute("SELECT type, district, n FROM street WHERE city=? AND name=?",
                      (c, _norm(street_name))).fetchall()
    for idx, key in ((1, "district"), (0, "street_type")):
        tot = {}
        for r in rows:
            if r[idx]:
                tot[r[idx]] = tot.get(r[idx], 0) + r[2]
        if tot:
            best = max(tot, key=tot.get)
            if tot[best] / sum(tot.values()) >= 0.6:   # иначе улица тянется через несколько районов
                out[key] = best
    if out["district"] is None and street_type in ("микрорайон", "квартал", None):
        out["district"] = _place_district(db, c, street_name)
    if not out["district"] and not out["street_type"]:
        return None
    return out