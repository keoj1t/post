import csv
import os
import re
from app.normalization import CITY_ALIASES, PROVINCE_ALIASES

PATH = os.path.join(os.path.dirname(__file__), "..", "reference", "kato_ru.csv")

KZ_LETTERS = re.compile(r"[әіңғүұқөһӘІҢҒҮҰҚӨҺ]")
DOTTED = re.compile(
    r"(?<!\w)(?:г\.а\.|г\.|гор\.|с\.о\.|с\.|п\.|пос\.|а\.о\.|а\.|ст\.|обл\.)\s*", re.I)
WORDS = re.compile(
    r"\b(?:город|область|район|поселок|посёлок|село|р-н|қаласы|қала|облысы|облыс|ауданы|аудан|ауыл|ауылы|кент)\b", re.I)


def strip_markers(t: str) -> str:
    t = DOTTED.sub(" ", t)
    t = WORDS.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip(" .,-")


def norm(t: str) -> str:
    t = t.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return CITY_ALIASES.get(t, t)


def pick_ru(seg: str) -> str:
    """'город Алматы/Алматы қаласы' -> 'город Алматы' (русская половина)."""
    parts = [p.strip() for p in seg.split("/")]
    for p in parts:
        if p and not KZ_LETTERS.search(p):
            return p
    return parts[0]


ROWS = {}
with open(PATH, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f, delimiter=";"):
        ROWS[int(r["id"])] = (int(r["parent_id"]), r["name"].strip())


def top_of(i):
    while ROWS[i][0] in ROWS:
        i = ROWS[i][0]
    return i


def depth_of(i):
    d = 0
    while ROWS[i][0] in ROWS:
        i = ROWS[i][0]
        d += 1
    return d


PROV, DIST, LOC = {}, {}, {}
for i, (parent, name) in ROWS.items():
    key = norm(strip_markers(name))
    if not key:
        continue
    d = depth_of(i)
    if d == 0:
        PROV.setdefault(key, []).append(i)
        if not re.search(r"област", name, re.I):    
            LOC.setdefault(key, []).append(i)
    elif re.search(r"с\.о|а\.о", name, re.I):
        continue                                    
    elif re.search(r"район|р\.а\.", name, re.I):
        DIST.setdefault(key, []).append(i)
    else:
        LOC.setdefault(key, []).append(i)


for _alias, _canonical in PROVINCE_ALIASES.items():
    if norm(_canonical) in PROV and norm(_alias) not in PROV:
        PROV[norm(_alias)] = PROV[norm(_canonical)]


def prov_display(i):
    name = ROWS[i][1]
    m = re.match(r"\s*область\s+(.+)", name, re.I)
    if m:
        return m.group(1).strip() + " область"       
    if re.search(r"област", name, re.I):
        return name.strip()
    return strip_markers(name)                      

def resolve_geo(segments):
    out = {"province": None, "city": None, "district": None, "geo_conf": 0.0}
    prov_id, city_text, ambiguous = None, None, False

    for seg in segments:
        text = pick_ru(seg)
        shown = strip_markers(text)
        key = norm(shown)
        if not key:
            continue
        is_dist = re.search(r"\b(район|р-н|ауданы)\b", text, re.I)
        is_prov = re.search(r"\b(область|облысы)\b|обл\.", text, re.I)

        if is_dist:
            out["district"] = shown
            if prov_id is None and key in DIST:
                tops = {top_of(i) for i in DIST[key]}
                if len(tops) == 1:
                    prov_id = tops.pop()
        elif is_prov and key in PROV:
            prov_id = PROV[key][0]
        elif key in LOC:
            city_text = shown                        
        elif key in PROV:
            prov_id = PROV[key][0]
        elif key in DIST:
            out["district"] = shown
        else:
            city_text = city_text or shown           

    if city_text:
        out["city"] = city_text
        ids = LOC.get(norm(city_text), [])
        if prov_id:
            narrowed = [i for i in ids if top_of(i) == prov_id]
            ids = narrowed or ids
        # Одноимённые сёла и участки не должны делать город «неоднозначным»:
        # если среди совпадений есть настоящие города, берём только их.
        city_ids = [i for i in ids if re.search(r"г\.а\.|^г\.|город|қаласы", ROWS[i][1], re.I)]
        village = any(re.search(r"\bсело\b|(?<!\w)с\.|посел|посёл|пос\.|ауылы", pick_ru(sg), re.I)
                      for sg in segments if norm(strip_markers(pick_ru(sg))) == norm(city_text))
        if not village:
            ids = city_ids or ids
        tops = {top_of(i) for i in ids}
        if len(tops) > 1:
            ambiguous = True
        if ids:
            # Район берём только из общей родительской цепочки всех совпадений.
            # Районы внутри большого города по одному имени города не определяются.
            district_ids = set()
            for item in ids:
                district = None
                parent = ROWS[item][0]
                while parent in ROWS:
                    if re.search(r'район|р\.а\.|ауданы', ROWS[parent][1], re.I):
                        district = parent
                        break
                    parent = ROWS[parent][0]
                district_ids.add(district)
            if not out['district'] and len(district_ids) == 1 and None not in district_ids:
                out['district'] = strip_markers(ROWS[next(iter(district_ids))][1])
            best = min(ids, key=depth_of)
            if depth_of(best) == 0:                  
                prov_id = best
            elif prov_id is None and not ambiguous:
                prov_id = top_of(best)

    if prov_id:
        out["province"] = prov_display(prov_id)

    score = 0.0
    score += 0.5 if out["province"] else 0
    score += 0.5 if out["city"] else 0
    out["geo_conf"] = score - (0.3 if ambiguous else 0)
    
    return out
