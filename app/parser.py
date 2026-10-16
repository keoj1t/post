import re
import unicodedata
from app import osm
from app.geo import resolve_geo, ROWS, depth_of, LOC, norm as geo_norm, strip_markers, pick_ru

def clean(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\u200b-\u200f\u2060\ufeff\u00ad]", "", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+\.", ".", s)
    s = re.sub(r"\.(?=\S)", ". ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



KEYWORDS = (
    r"квартал|квартира|кв|подъезд|подьезд|под|этаж|эт|дом|микрорайон|мкр|"
    r"flat|kv|floor"
)
KW = {}
for w in ("кв", "квартира", "flat", "kv", "апт", "ап"):
    KW[w] = "apartment"
for w in ("подъезд", "подьезд", "подъ", "под", "п"):
    KW[w] = "entrance"
for w in ("этаж", "эт", "floor"):
    KW[w] = "floor"
for w in ("дом", "д", "уй"):
    KW[w] = "house"

NUM_RE = re.compile(r"^\d+[а-яa-z]?(?:/\d+[а-яa-z]?)?$", re.I)


def extract_keyword_fields(s: str):
    """Находит квартиру/подъезд/этаж/дом. Возвращает (поля, оставшаяся строка)."""
    tokens = re.findall(r",|[^\s,]+", s)
    norm = [t.strip(".").lower() for t in tokens]
    n = len(tokens)
    is_num = [bool(NUM_RE.match(t)) for t in norm]

    kws = [i for i, t in enumerate(norm) if t in KW]

    def free_nums(i, used):
        """Свободные числа слева и справа от слова i."""
        cand = []
        if i > 0 and is_num[i - 1] and (i - 1) not in used:
            cand.append(i - 1)
        if i + 1 < n and is_num[i + 1] and (i + 1) not in used:
            cand.append(i + 1)
        return cand

    suffix_votes = sum(1 for i in kws
                       if i > 0 and is_num[i - 1] and not (i + 1 < n and is_num[i + 1]))
    prefix_votes = sum(1 for i in kws
                       if i + 1 < n and is_num[i + 1] and not (i > 0 and is_num[i - 1]))
    suffix_style = suffix_votes > prefix_votes

    fields, used, done = {}, set(), set()

    changed = True
    while changed:
        changed = False
        for i in kws:
            if i in done or KW[norm[i]] in fields:
                continue
            cand = free_nums(i, used)
            if len(cand) == 1:
                j = cand[0]
                fields[KW[norm[i]]] = tokens[j].strip(".")
                used.update({i, j}); done.add(i)
                changed = True
        if changed:
            continue
        for i in kws:
            if i in done or KW[norm[i]] in fields:
                continue
            cand = free_nums(i, used)
            if len(cand) == 2:
                if KW[norm[i]] == "apartment":
                    j = cand[1]          # "42 кв 10" -> квартира 10, 42 остаётся домом
                else:
                    j = cand[0] if suffix_style else cand[1]
                fields[KW[norm[i]]] = tokens[j].strip(".")
                used.update({i, j}); done.add(i)
                changed = True
                break  

    rest = [t for k, t in enumerate(tokens) if k not in used]
    return fields, " ".join(rest)

def split_glued(s: str) -> str:
    s = re.sub(r"(\d)([а-яёa-z]{2,})", r"\1 \2", s, flags=re.I)
    s = re.sub(r"([а-яёa-z]{2,})(\d)", r"\1 \2", s, flags=re.I)
    return s



APT_WORDS = r"(?:кв|квартира|flat|kv|апт|ап)"
ENT_WORDS = r"(?:подъезд|подьезд|под|п)"
FLOOR_WORDS = r"(?:этаж|эт|floor)"
HOUSE_WORDS = r"(?:дом|д)"

STREET_TYPES = {
    "улица": "улица", "ул": "улица",
    "проспект": "проспект", "пр": "проспект", "пр-т": "проспект", "просп": "проспект",
    "микрорайон": "микрорайон", "мкр": "микрорайон", "мкрн": "микрорайон",
    "переулок": "переулок", "пер": "переулок",
    "квартал": "квартал", "кв-л": "квартал",
    "бульвар": "бульвар", "бул": "бульвар",
    "шоссе": "шоссе", "тупик": "тупик",
}

LANDMARK_WORDS = r"(?:магазин|тц|трц|банк|школа|аптека|qazpost|рядом|возле|напротив)"

LANDMARK_SET = {"магазин", "тц", "трц", "банк", "школа", "аптека",
                "qazpost", "рядом", "возле", "напротив"}
GEO_MARKERS = {"город", "г", "область", "обл", "район", "р-н",
               "қаласы", "облысы", "ауданы", "пос", "посёлок", "поселок"}
NUMBER_BEFORE_TYPE = {"микрорайон", "квартал"}  


def nt(t):
    return t.strip(".").lower()


def split_segments(tokens):
    segs, cur = [], []
    for t in tokens:
        if t == ",":
            if cur:
                segs.append(cur)
                cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def is_geo_segment(seg):
    text = " ".join(seg)

    if re.search(r"[^\W\d_]/[^\W\d_]", text):
        return True
    return nt(seg[0]) in GEO_MARKERS or nt(seg[-1]) in GEO_MARKERS


# Ключи городов: верхний уровень КАТО (города респ. значения) и первый уровень
# (города обл. значения), кроме сёл, посёлков и районов; плюс крупные города на всякий случай.
_NOT_CITY = re.compile(r"село|посел|посёл|район|област|с\.о|а\.о|\bс\.|\bп\.|\bа\.|\bст\.|ауылы|ауданы|облысы", re.I)
CITY_KEYS = {"алматы", "астана", "нур-султан", "шымкент", "караганда", "актобе", "актау",
             "атырау", "костанай", "павлодар", "семей", "уральск", "тараз", "кызылорда",
             "петропавловск", "усть-каменогорск", "талдыкорган", "кокшетау", "туркестан",
             "темиртау", "экибастуз", "рудный", "жезказган", "балхаш", "конаев", "капчагай"}
for _i, (_parent, _name) in ROWS.items():
    if depth_of(_i) <= 1 and (not _NOT_CITY.search(_name) or re.search(r"город|г\.а\.|қаласы", _name, re.I)):
        _k = geo_norm(strip_markers(pick_ru(_name)))
        if _k:
            CITY_KEYS.add(_k)


def is_city_text(text):
    """Текст целиком совпадает с названием города из КАТО."""
    t = text.strip(". ")
    if not t or NUM_RE.match(t.lower()):
        return False
    return geo_norm(t) in CITY_KEYS


def split_leading_city(seg):
    """Если сегмент начинается с названия города (без слова 'город'),
    отделяет его. Возвращает (город или None, остаток сегмента)."""
    if len(seg) < 2 or nt(seg[0]) in STREET_TYPES or nt(seg[0]) in GEO_MARKERS:
        return None, seg
    for k in (2, 1):                      # сначала два слова, потом одно
        if len(seg) <= k:
            continue
        cand = " ".join(seg[:k])
        if NUM_RE.match(nt(cand)):
            continue
        if is_city_text(cand):
            return cand, seg[k:]
    return None, seg


def parse_street(s, house=None):
    out = {"street_type": None, "street_name": None, "house": house,
           "landmark": None, "living_area": None, "_geo": []}
    tokens = re.findall(r",|[^\s,]+", s)

  
    for i, t in enumerate(tokens):
        if nt(t) in LANDMARK_SET:
            out["landmark"] = " ".join(x for x in tokens[i:] if x != ",")
            tokens = tokens[:i]
            break

    rest = []
    for seg in split_segments(tokens):
        if is_geo_segment(seg):
            out["_geo"].append(" ".join(seg))
        else:
            rest.append(seg)
    if not rest:
        return out

    city_txt, rest[0] = split_leading_city(rest[0])
    if city_txt:
        out["_geo"].append(city_txt)
    rest = [r for r in rest if r]
    if not rest:
        return out

    found = None
    for si, seg in enumerate(rest):
        for ti, t in enumerate(seg):
            if nt(t) in STREET_TYPES:
                found = (si, ti)
                break
        if found:
            break

    if found:
        si, ti = found
        seg = rest[si]
        stype = STREET_TYPES[nt(seg[ti])]
        out["street_type"] = stype
        out["_geo"] += [" ".join(x) for x in rest[:si]]
        later = rest[si + 1:]
        city_after = [x for x in later if is_city_text(" ".join(x))]
        out["_geo"] += [" ".join(x) for x in city_after]
        later = [x for x in later if x not in city_after]

        if stype in NUMBER_BEFORE_TYPE and ti >= 1 and NUM_RE.match(nt(seg[ti - 1])):
            name = [seg[ti - 1]]
            out["living_area"] = " ".join(seg[:ti - 1]) or None
            tail = seg[ti + 1:]
        else:
            name = seg[ti + 1:]
            tail = []
            if not name and ti > 0:        
                name = seg[:ti]

        if out["house"] is None:
            for part in [tail] + later:      
                nums = [t for t in part if NUM_RE.match(nt(t))]
                if nums:
                    out["house"] = nums[0].strip(".")
                    break
            else:                          
                if len(name) >= 2 and NUM_RE.match(nt(name[-1])):
                    out["house"] = name[-1]
                    name = name[:-1]
        out["street_name"] = " ".join(name) or None
    else:
        if (len(rest) >= 2 and out["house"] is None
                and len(rest[-1]) == 1 and NUM_RE.match(nt(rest[-1][0]))):
            out["house"] = rest[-1][0]
            rest = rest[:-1]
        seg = rest[-1]
        out["_geo"] += [" ".join(x) for x in rest[:-1]]
        if out["house"] is None and len(seg) >= 2 and NUM_RE.match(nt(seg[-1])):
            out["house"] = seg[-1]
            seg = seg[:-1]
        elif out["house"] is None and len(seg) == 1 and NUM_RE.match(nt(seg[0])):
            out["house"] = seg[0]
            seg = []
        out["street_name"] = " ".join(seg) or None

    return out


def parse_address(raw: str) -> dict:
    res = {
        "province": None, "city": None, "district": None, "living_area": None,
        "street_type": None, "street_name": None, "house": None,
        "apartment": None, "entrance": None, "floor": None, "landmark": None,
        "confidence": 0.0,
    }
    s = clean(raw)
    s = split_glued(s)
    fields, s = extract_keyword_fields(s)
    for k, v in fields.items():
        res[k] = v

    st = parse_street(s, res["house"])
    for k in ("street_type", "street_name", "house", "landmark", "living_area"):
        res[k] = st[k]
    g = resolve_geo(st["_geo"])
    res["province"], res["city"], res["district"] = g["province"], g["city"], g["district"]

    # Справочник OSM: район и тип улицы, только если их нет в самой строке
    if res["city"] and res["street_name"]:
        info = osm.lookup(res["city"], res["street_name"], res["street_type"])
        if info:
            if not res["district"] and info.get("district"):
                res["district"] = info["district"]
            if not res["street_type"] and info.get("street_type"):
                res["street_type"] = info["street_type"]

    conf = 0.1
    conf += 0.2 * bool(res["province"]) + 0.2 * bool(res["city"])
    conf += 0.25 * bool(res["street_name"]) + 0.25 * bool(res["house"])
    res["confidence"] = round(max(0.05, min(conf - (0.3 - 0.3 * g["geo_conf"]) * 0, 0.95)), 2)
    return res