import re
import unicodedata
from app import osm
from app.geo import resolve_geo, ROWS, depth_of, LOC, PROV, DIST, top_of, prov_display, norm as geo_norm, strip_markers, pick_ru

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
for w in ("кв", "квартира", "кварт", "flat", "kv", "апт", "ап"):
    KW[w] = "apartment"
for w in ("подъезд", "подьезд", "подъ", "под", "п"):
    KW[w] = "entrance"
for w in ("этаж", "эт", "floor"):
    KW[w] = "floor"
for w in ("дом", "д", "дм", "уй"):
    KW[w] = "house"

NUM_RE = re.compile(r"^\d+[а-яa-z]?(?:/\d+[а-яa-z]?)?$", re.I)


def extract_keyword_fields(s: str):
    """Находит квартиру/подъезд/этаж/дом. Возвращает (поля, оставшаяся строка)."""
    tokens = re.findall(r",|[^\s,]+", s)
    norm = [canonical_marker(t) for t in tokens]
    n = len(tokens)
    is_num = [bool(NUM_RE.match(t)) for t in norm]

    kws = [i for i, t in enumerate(norm) if t in KW
           and not (t == "под" and i + 1 < n and norm[i + 1] in LANDMARK_INFLECTIONS)]

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
    s = re.sub(r"(\d)([^\W\d_]{2,})", r"\1 \2", s, flags=re.I)
    s = re.sub(r"([^\W\d_]{2,})(\d)", r"\1 \2", s, flags=re.I)
    return s



APT_WORDS = r"(?:кв|квартира|flat|kv|апт|ап)"
ENT_WORDS = r"(?:подъезд|подьезд|под|п)"
FLOOR_WORDS = r"(?:этаж|эт|floor)"
HOUSE_WORDS = r"(?:дом|дм|д)"

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


# Исправляем только известные маркеры с одной пропущенной буквой.
# Названия улиц и жилмассивов не нормализуем и не исправляем по сходству.
_MISSING_LETTER_CANDIDATES = {}
for _marker in ("переулок", "проспект", "микрорайон", "бульвар", "квартира", "подъезд"):
    for _position in range(len(_marker)):
        _variant = _marker[:_position] + _marker[_position + 1:]
        _MISSING_LETTER_CANDIDATES.setdefault(_variant, set()).add(_marker)
MARKER_ALIASES = {variant: next(iter(markers))
                  for variant, markers in _MISSING_LETTER_CANDIDATES.items()
                  if len(markers) == 1 and variant not in STREET_TYPES and variant not in KW}
MARKER_ALIASES.update({"подьедз": "подъезд", "подъедз": "подъезд", "подезд": "подъезд"})

LANDMARK_INFLECTIONS = {"магазином", "магазина", "школой", "школы", "банком", "банка", "аптекой", "аптеки"}


def extract_glued_fields(s):
    """Связь в «эт4» сильнее соседства в «подъезд 5 эт 4»."""
    words = set(KW) | {alias for alias, target in MARKER_ALIASES.items() if target in KW}
    alternatives = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
    number = r"\d+[а-яa-z]??(?:/\d+[а-яa-z]??)?"
    patterns = [re.compile(rf"(?<!\w)(?P<marker>{alternatives})\.?(?P<number>{number})(?!\w)", re.I),
                re.compile(rf"(?<!\w)(?P<number>{number})(?P<marker>{alternatives})(?!\w)", re.I)]
    candidates = sorted((match for pattern in patterns for match in pattern.finditer(s)), key=lambda match: match.start())
    fields, used = {}, []
    for match in candidates:
        field = KW[canonical_marker(match['marker'])]
        if field in fields or any(match.start() < end and match.end() > start for start, end in used):
            continue
        fields[field] = match['number']
        used.append(match.span())
    for start, end in sorted(used, reverse=True):
        s = s[:start] + ' ' + s[end:]
    return fields, s


def extract_landmark(s):
    tokens = list(re.finditer(r",|[^\s,]+", s))
    for i, token in enumerate(tokens):
        if canonical_marker(token.group()) in LANDMARK_SET | LANDMARK_INFLECTIONS:
            start = token.start()
            if i and canonical_marker(tokens[i - 1].group()) in {"под", "над", "за", "перед", "у", "около"}:
                start = tokens[i - 1].start()
            return ' '.join(s[start:].replace(',', ' ').split()), s[:start]
    return None, s


def extract_inline_geo(s):
    """Извлекает явные область/район и известный город без запятых."""
    tokens = list(re.finditer(r",|[^\s,]+", s))
    taken, out = set(), {}
    def claim(start, end, key, value):
        taken.update(range(start, end))
        out[key] = value
    def phrase(start, end):
        return ' '.join(token.group() for token in tokens[start:end])
    for i, token in enumerate(tokens):
        marker = canonical_marker(token.group())
        if i in taken or marker not in {"область", "обл", "облысы", "район", "р-н", "ауданы"}:
            continue
        province = marker in {"область", "обл", "облысы"}
        catalog = PROV if province else DIST
        match = None
        for direction in (-1, 1):
            for count in (3, 2, 1):
                start, end = (i-count, i) if direction == -1 else (i+1, i+1+count)
                if start < 0 or end > len(tokens) or any(j in taken or tokens[j].group() == ',' for j in range(start, end)):
                    continue
                value = phrase(start, end)
                key = geo_norm(strip_markers(value))
                if key in catalog:
                    shown = prov_display(catalog[key][0]) if province else strip_markers(value)
                    match = min(start, i), max(end, i+1), shown
                    break
            if match:
                break
        # Явный неизвестный район сохраняем, но не придумываем географию по нему.
        if not match and not province:
            for j in (i+1, i-1):
                if 0 <= j < len(tokens) and j not in taken:
                    value = tokens[j].group()
                    if value != ',' and canonical_marker(value) not in GEO_MARKERS | set(STREET_TYPES) | set(KW) and not NUM_RE.match(value):
                        match = min(i,j), max(i,j)+1, value
                        break
        if match:
            claim(match[0], match[1], 'province' if province else 'district', match[2])
    for i in range(len(tokens)):
        if i in taken:
            continue
        for count in (2, 1):
            end = i + count
            if end > len(tokens) or any(j in taken or tokens[j].group() == ',' for j in range(i,end)):
                continue
            value = phrase(i,end)
            if geo_norm(value) not in CITY_KEYS:
                continue
            before = canonical_marker(tokens[i-1].group()) if i else ''
            after = canonical_marker(tokens[end].group()) if end < len(tokens) else ''
            if before in STREET_TYPES or before in GEO_MARKERS or after in {'қаласы', 'город', 'г'}:
                continue
            claim(i,end,'city',value)
            break
    spans = [(tokens[i].start(), tokens[i].end()) for i in taken]
    for start, end in sorted(spans, reverse=True):
        s = s[:start] + ' ' + s[end:]
    return out, s


def has_geo_conflict(res):
    cities = LOC.get(geo_norm(res.get('city') or ''), [])
    cities = [i for i in cities if re.search(r"г\.а\.|^г\.|город|қаласы", ROWS[i][1], re.I)]
    provinces = PROV.get(geo_norm(strip_markers(res.get('province') or '')), [])
    return bool(cities and provinces and not ({top_of(i) for i in cities} & set(provinces)))


def canonical_marker(token):
    token = token.strip(".").lower()
    return MARKER_ALIASES.get(token, token)


def extract_living_area(s):
    """Отделяет явный жилмассив до разбора дома, сохраняя его номер."""
    marker = re.search(r"(?<!\w)(?:ж\s*[./]?\s*м\.?|жилмассив|жилой\s+массив|тұрғын\s+алап)(?!\w)\s*", s, re.I)
    if not marker:
        return None, s
    tokens = list(re.finditer(r",|[^\s,]+", s[marker.end():]))
    name_tokens = []
    end = marker.end()
    for token in tokens:
        value = token.group()
        key = canonical_marker(value)
        if value == "," or key in STREET_TYPES or key in KW or key in GEO_MARKERS or key in LANDMARK_SET:
            break
        name_tokens.append(value)
        end = marker.end() + token.end()
    if not name_tokens:
        return None, s
    return " ".join(name_tokens), s[:marker.start()] + " " + s[end:]


def nt(t):
    return canonical_marker(t)


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
    glued_fields, s = extract_glued_fields(s)
    s = split_glued(s)
    living_area, s = extract_living_area(s)
    fields, s = extract_keyword_fields(s)
    fields.update(glued_fields)
    for k, v in fields.items():
        res[k] = v

    landmark, s = extract_landmark(s)
    explicit_geo, s = extract_inline_geo(s)

    st = parse_street(s, res["house"])
    for k in ("street_type", "street_name", "house", "landmark", "living_area"):
        res[k] = st[k]
    if living_area:
        res["living_area"] = living_area
    if landmark:
        res["landmark"] = landmark
    geo_segments = st["_geo"] + ([explicit_geo['city']] if explicit_geo.get('city') else [])
    g = resolve_geo(geo_segments)
    res["province"], res["city"], res["district"] = g["province"], g["city"], g["district"]
    res.update(explicit_geo)

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
    if has_geo_conflict(res):
        res["confidence"] = min(res["confidence"], 0.55)
    return res
