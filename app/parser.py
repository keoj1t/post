import re
import unicodedata
from functools import lru_cache
from app import osm
from app.normalization import FIELD_WORDS, STREET_WORDS, PROVINCE_ALIASES, TYPO_ALIASES, PARENTHETICAL_NOTE, extract_postal, normalize_compact, split_compact_chains, strip_access_notes, strip_post_boxes
from app.geo import resolve_geo, ROWS, depth_of, LOC, PROV, DIST, top_of, prov_display, norm as geo_norm, strip_markers, pick_ru


def clean(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\r\n]+", ", ", s)
    s = re.sub(r"[\u200b-\u200f\u2060\ufeff\u00ad]", "", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"(?<!\w)н\s*\.\s*п\s*\.?(?!\w)", "нп", s, flags=re.I)
    s = re.sub(r"(?<!\w)к-сі(?!\w)", "көшесі", s, flags=re.I)
    s = re.sub(r"[;|]+", ",", s)
    s = re.sub(r"\s*/{2,}\s*", ", ", s)
    s = re.sub(r"\s+/\s+", ", ", s)
    s = re.sub(r"[()\[\]]", ", ", s)
    s = re.sub(r"\s+\.", ".", s)
    s = re.sub(r"\.(?=\S)", ". ", s)
    s = re.sub(r"(?:\s*,){2,}", ",", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
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

NUM_RE = re.compile(r"^(?:\d+[а-яa-z]?(?:/(?:\d+[а-яa-z]?|[а-яa-z]))?(?:-\d+[а-яa-z]?)?|[ivxlcdm]+(?:-(?:\d+|[а-яa-z]+))?)$", re.I)
for _field, _words in FIELD_WORDS.items():
    for _word in _words:
        KW[_word] = _field


def extract_keyword_fields(s: str):
    tokens = re.findall(r",|[^\s,]+", s)
    norm = [canonical_marker(t) for t in tokens]
    n = len(tokens)
    is_num = [bool(NUM_RE.match(t)) for t in norm]

    kws = [i for i, t in enumerate(norm) if t in KW
           and not (t == "под" and i + 1 < n and norm[i + 1] in LANDMARK_INFLECTIONS)]

    def free_nums(i, used):
        cand = []
        field = KW[norm[i]]
        def usable(j):
            return is_num[j] or (field == "building" and bool(re.fullmatch(r"[a-zа-я](?:\d+[a-zа-я]?)?(?:-\d+)?", tokens[j], re.I)))
        if i > 0 and usable(i - 1) and (i - 1) not in used:
            cand.append(i - 1)
        if i + 1 < n and usable(i + 1) and (i + 1) not in used:
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
                used.update({i, j})
                done.add(i)
                changed = True
        if changed:
            continue
        for i in kws:
            if i in done or KW[norm[i]] in fields:
                continue
            cand = free_nums(i, used)
            if len(cand) == 2:
                if KW[norm[i]] == "apartment":
                    j = cand[1]
                else:
                    j = cand[0] if suffix_style else cand[1]
                fields[KW[norm[i]]] = tokens[j].strip(".")
                used.update({i, j})
                done.add(i)
                changed = True
                break

    rest = [t for k, t in enumerate(tokens) if k not in used]
    return fields, " ".join(rest)


def split_glued(s: str) -> str:
    s = re.sub(r"(\d)([^\W\d_]{2,})", r"\1 \2", s, flags=re.I)
    s = re.sub(r"([^\W\d_]{2,})(\d)", r"\1 \2", s, flags=re.I)
    return s


_NO_JOIN = set("пдксвиуо")


def join_house_letter(s):
    def space_fix(m):
        return m.group(0) if m.group(2).lower() in _NO_JOIN else m.group(1) + m.group(2)

    def dash_fix(m):
        return m.group(0) if m.group(2).lower() in "йм" else m.group(1) + m.group(2)

    s = re.sub(r"(?<![\w/])(\d+)\s+([^\W\d_])(?![^\W\d_])", space_fix, s)
    s = re.sub(r"(?<![\w/])(\d+)-([^\W\d_])(?![^\W\d_])", dash_fix, s)
    return s


def join_digit_runs(s):
    def fix(m):
        digits = m.group(0).split()
        if len(digits) >= 3 or "0" in digits:
            return "".join(digits)
        return m.group(0)

    return re.sub(r"(?<![\w/.,-])\d(?:[ \t]+\d)+(?![\w/-])", fix, s)


def russian_city(city):
    if not city:
        return city
    from app.normalization import CITY_ALIASES
    target = CITY_ALIASES.get(geo_norm(city))
    if not target and city.isascii():
        target = CITY_ALIASES.get(city.strip().lower())
    if target:
        return target.title()
    if geo_norm(city) in CITY_KEYS:
        return city.title()
    return city


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

LANDMARK_WORDS = r"(?:магазин|тц|трц|банк|школа|аптека|паркинг|парковка|qazpost|рядом|возле|напротив)"
for _type, _words in STREET_WORDS.items():
    for _word in _words:
        STREET_TYPES[_word] = _type

LANDMARK_SET = {"магазин", "тц", "трц", "банк", "школа", "аптека", "паркинг", "паркингтің", "паркингтин", "паркингтың", "парковка",
                "qazpost", "рядом", "возле", "напротив", "ориентир", "около", "за", "дүкен", "мектеп", "дәріхана", "жанында", "қарсысында"}
GEO_MARKERS = {"город", "г", "область", "обл", "район", "р-н",
               "қаласы", "қала", "облысы", "облыс", "ауданы", "аудан", "пос", "посёлок", "поселок", "ауыл", "ауылы", "oblast"}
NUMBER_BEFORE_TYPE = {"микрорайон", "квартал"}


_MISSING_LETTER_CANDIDATES = {}
for _marker in ("переулок", "проспект", "микрорайон", "бульвар", "квартира", "подъезд"):
    for _position in range(len(_marker)):
        _variant = _marker[:_position] + _marker[_position + 1:]
        _MISSING_LETTER_CANDIDATES.setdefault(_variant, set()).add(_marker)
MARKER_ALIASES = {variant: next(iter(markers))
                  for variant, markers in _MISSING_LETTER_CANDIDATES.items()
                  if len(markers) == 1 and variant not in STREET_TYPES and variant not in KW}
MARKER_ALIASES.update({"подьедз": "подъезд", "подъедз": "подъезд", "подезд": "подъезд"})
MARKER_ALIASES["ауд"] = "ауданы"
MARKER_ALIASES.update({
    "qalasy": "қаласы", "qala": "қала", "каласы": "қаласы",
    "ui": "үй", "uy": "үй", "pater": "пәтер", "pәтер": "пәтер",
    "koshe": "көше", "koshesi": "көшесі", "кошеси": "көшесі",
})
MARKER_ALIASES.update({alias: target for alias, target in TYPO_ALIASES.items() if alias not in KW and alias not in STREET_TYPES})
MARKER_ALIASES.update({"падъезд": "подъезд", "падьезд": "подъезд", "подъезт": "подъезд", "подьезт": "подъезд"})

LANDMARK_INFLECTIONS = {"магазином", "магазина", "школой", "школы", "банком", "банка", "аптекой", "аптеки"}


def extract_glued_fields(s):
    words = set(KW) | {alias for alias, target in MARKER_ALIASES.items() if target in KW}
    alternatives = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
    number = r"\d+[а-яa-z]??(?:/\d+[а-яa-z]??)?"
    separator = r"[-.]?"
    next_explicit_field = rf"(?=\d+[а-яa-z]?(?:/\d+[а-яa-z]?)?{separator}\s*(?:{alternatives})(?!\w))"
    patterns = [re.compile(rf"(?<!\w)(?P<marker>{alternatives}){separator}(?P<number>{number})(?!\w)", re.I),
                re.compile(rf"(?<!\w)(?P<number>{number}){separator}\s*(?P<marker>{alternatives})(?:(?!\w)|{next_explicit_field})", re.I)]
    candidates = sorted((match for pattern in patterns for match in pattern.finditer(s)), key=lambda match: match.start())
    fields, used = {}, []
    for match in candidates:
        field = KW[canonical_marker(match['marker'])]
        if field in fields or any(match.start() < end and match.end() > start for start, end in used):
            continue
        if match.re is patterns[1] and re.match(r'\s*[.№:#-]?\s*(?:\d|[^\W\d_](?![^\W\d_]))', s[match.end():], re.UNICODE):
            continue
        fields[field] = match['number']
        used.append(match.span())
    for start, end in sorted(used, reverse=True):
        s = s[:start] + ' ' + s[end:]
    return fields, s


def extract_landmark(s):
    tokens = list(re.finditer(r",|[^\s,]+", s))
    for token in tokens:
        if canonical_marker(token.group()) in {"рынок", "базар"}:
            start = token.start()
            landmark = " ".join(s[start:].replace(",", " ").split()).strip()
            return landmark, s[:start].rstrip(" ,")
    descriptive_entrance = re.compile(
        r"^(?:со\s+двора|с\s+двора|со\s+стороны|с\s+улицы|возле\b|рядом\b|"
        r"жанында\b|сол\b|оң\b|паркинг\w*\b)", re.I
    )
    for i, token in enumerate(tokens):
        token_marker = canonical_marker(token.group())
        is_entrance_marker = token_marker in {word for word, field in KW.items() if field == "entrance"}
        if not is_entrance_marker and token_marker not in {"вход", "въезд"}:
            continue
        remainder = s[token.end():].lstrip(" ,")
        if not descriptive_entrance.search(remainder):
            continue
        comma = s.find(",", token.end())
        end = comma if comma >= 0 else len(s)
        landmark = " ".join(s[token.end():end].split()).strip(" ,")
        rest = s[:token.start()] + (s[comma + 1:] if comma >= 0 else "")
        return landmark, rest
    for i, token in enumerate(tokens):
        if canonical_marker(token.group()) in LANDMARK_SET | LANDMARK_INFLECTIONS:
            start = token.start()
            if canonical_marker(token.group()) == "ориентир":
                following = next((item for item in tokens[i + 1:] if item.group() != ","), None)
                if following is None:
                    continue
                start = following.start()
            if i and canonical_marker(tokens[i - 1].group()) in {"под", "над", "за", "перед", "у", "около"}:
                if canonical_marker(token.group()) != "ориентир":
                    start = tokens[i - 1].start()
            if not s[:start].strip(" ,"):
                comma = s.find(",", start)
                if comma != -1:
                    return ' '.join(s[start:comma].split()), s[comma + 1:]
            return ' '.join(s[start:].replace(',', ' ').split()), s[:start]
    return None, s


def extract_intersection(s):
    """Move a secondary crossing street into landmark, preserving the primary street."""
    marker = re.compile(r"(?<!\w)(?:уг\.?|угол|пересечение(?:\s+улиц(?:ы)?)?)(?!\w)", re.I)
    match = marker.search(s)
    if not match:
        return None, s
    tail = s[match.start():]
    end = len(tail)
    comma = tail.find(',')
    if comma >= 0:
        end = min(end, comma)
    boundary = re.search(r"(?<!\w)(?:дом|дм|д|үй|квартира|кв|пәтер|корпус|корп|подъезд|подьезд|этаж|эт)\.?\s*(?:\d|б/н)", tail, re.I)
    if boundary:
        end = min(end, boundary.start())
    landmark = " ".join(tail[:end].split()).strip(" ,")
    rest = (s[:match.start()] + " " + tail[end:]).strip(" ,")
    return landmark or None, rest


def extract_highway_route(s):
    """Protect a hyphenated route name and its kilometre point from generic parsing."""
    route = r"[^\s,]+(?:-[^\s,]+)+"
    kilometer = r"(?:\d+\s*(?:км|километр(?:а|ов)?)|\d+\s*-\s*й\s+километр)"
    road_type = r"трассасы|трасса|тракт|шоссе"
    patterns = (
        re.compile(rf"(?<!\w)(?P<km_before>{kilometer})\s+(?P<type>{road_type})\s+(?P<route>{route})(?:\s*,?\s*(?P<km_after>{kilometer}))?", re.I),
        re.compile(rf"(?<!\w)(?P<type>{road_type})\s+(?P<route>{route})(?:\s*,?\s*(?P<km_after>{kilometer}))?", re.I),
        re.compile(rf"(?<!\w)(?P<route>{route})\s+(?P<type>{road_type})(?:\s*,?\s*(?P<km_after>{kilometer}))?", re.I),
    )
    for pattern in patterns:
        match = pattern.search(s)
        if not match:
            continue
        marker = match.group('type').lower()
        normalized_type = 'шоссе' if marker == 'шоссе' else ('тракт' if marker.startswith('трасс') else 'тракт')
        kilometer_value = match.groupdict().get('km_before') or match.groupdict().get('km_after')
        name = match.group('route')
        if kilometer_value:
            name = f"{name} {kilometer_value.strip()}"
        rest = (s[:match.start()] + ' ' + s[match.end():]).strip(' ,')
        return {'street_type': normalized_type, 'street_name': name}, rest
    return None, s


def split_compact_geography(s):
    compact = lambda value: re.sub(r'[\s.-]+', '', value.lower())
    regions = {}
    for key, ids in PROV.items():
        if any('област' in ROWS[item][1].lower() for item in ids):
            regions[compact(key)] = prov_display(ids[0])
    for alias, canonical in PROVINCE_ALIASES.items():
        if compact(canonical) in regions:
            regions[compact(alias)] = regions[compact(canonical)]
    prefixes = {}
    for name, display in regions.items():
        for size in range(5, len(name)):
            prefixes.setdefault(name[:size], set()).add(display)
    for prefix, displays in prefixes.items():
        if len(displays) == 1:
            regions.setdefault(prefix, next(iter(displays)))
    cities = {compact(key): key for key in CITY_KEYS}
    from app.normalization import CITY_ALIASES
    cities.update({compact(alias): alias for alias in CITY_ALIASES})

    def separate(match):
        original = match.group()
        word = compact(original)
        if '-' in original:
            route_parts = [compact(part) for part in original.split('-')]
            if (all(part in cities for part in route_parts)
                    or (original[:1].isupper() and len(route_parts) >= 2
                        and all(part[:1].isupper() for part in original.split('-'))
                        and route_parts[0] in cities)):
                return original
        city_markers = sorted({compact(word) for words in STREET_WORDS.values() for word in words}, key=len, reverse=True)
        for prefix in ("г", "g"):
            for city in sorted(cities, key=len, reverse=True):
                if not word.startswith(prefix + city):
                    continue
                tail = word[len(prefix) + len(city):]
                marker = next((value for value in city_markers
                               if len(value) >= 2 and tail.startswith(value) and len(tail) > len(value) + 1), None)
                if marker:
                    city_end = len(prefix) + len(city)
                    marker_end = city_end + len(marker)
                    return (' ' + CITY_ALIASES.get(city, cities[city]) + ' '
                            + original[city_end:marker_end] + ' ' + original[marker_end:] + ' ')
        marker = re.search(r'(область|обл|облысы|облыс|oblast)$', word)
        if marker:
            stem = word[:marker.start()]
            if stem in regions:
                return ' ' + regions[stem] + ' '
            for city in sorted(cities, key=len, reverse=True):
                if stem.startswith(city) and stem[len(city):] in regions:
                    return ' ' + cities[city] + ' , ' + regions[stem[len(city):]] + ' '
        for city in sorted(cities, key=len, reverse=True):
            tail = word[len(city):] if word.startswith(city) else ""
            suffixes = ("қаласы", "қала", "qalasy", "qala", "каласы", "қ", "q")
            suffix = next((value for value in suffixes if tail.startswith(value)), None)
            if suffix and len(tail) == len(suffix):
                return ' ' + CITY_ALIASES.get(city, cities[city]) + ' ' + original[len(city):] + ' '
            if suffix and len(tail) > len(suffix):
                end = len(city) + len(suffix)
                return (' ' + CITY_ALIASES.get(city, cities[city]) + ' '
                        + original[len(city):end] + ' ' + original[end:] + ' ')
            street_abbreviations = {word for group in STREET_WORDS.values() for word in group}
            if tail in street_abbreviations:
                return ' ' + CITY_ALIASES.get(city, cities[city]) + ' ' + original[len(city):] + ' '
            if len(tail) >= 4:
                return ' ' + CITY_ALIASES.get(city, cities[city]) + ' ' + original[len(city):] + ' '
        return original
    s = re.sub(r'(область|облысы|oblast)(?=(?:дом|дм|кв|үй|пәтер)\d)', r'\1 ', s, flags=re.I)
    return re.sub(r'[^\W\d_]+(?:[-.][^\W\d_]+)*', separate, s)


@lru_cache(maxsize=1)
def district_catalog():
    catalog = {key: list(ids) for key, ids in DIST.items()}
    for key, ids in DIST.items():
        if ' ' in key or key.endswith(('ский', 'ской', 'цкий')):
            continue
        stem = key[:-1] if key.endswith(('а', 'ы')) else key
        for alias in (stem + 'ский', stem + 'инский'):
            catalog.setdefault(alias, [])
            catalog[alias].extend(item for item in ids if item not in catalog[alias])
    return catalog


def extract_inline_geo(s):
    tokens = list(re.finditer(r",|[^\s,]+", s))
    taken, out = set(), {}
    for i, token in enumerate(tokens):
        if token.group().lower() in {'казахстан', 'қазақстан', 'kazakhstan', 'kazakstan', 'kz', 'рк', 'қр'} and (i == 0 or tokens[i - 1].group() == ','):
            taken.add(i)

    def claim(start, end, key, value):
        taken.update(range(start, end))
        out[key] = value

    def phrase(start, end):
        return ' '.join(token.group() for token in tokens[start:end])
    for i, token in enumerate(tokens):
        marker = canonical_marker(token.group())
        if marker == "қ" and i > 0 and geo_norm(tokens[i - 1].group()) in CITY_KEYS:
            taken.add(i)
            continue
        if i in taken or marker not in {"область", "обл", "облысы", "облыс", "oblast", "район", "р-н", "ауданы", "аудан"}:
            continue
        province = marker in {"область", "обл", "облысы", "облыс", "oblast"}
        catalog = PROV if province else district_catalog()
        match = None
        previous = tokens[i - 1].group() if i else ","
        suffix_district = marker in {"ауданы", "аудан", "район", "р-н"} and (
            previous != ","
            and geo_norm(previous) not in CITY_KEYS
            and canonical_marker(previous) not in set(STREET_TYPES) | set(KW)
        )
        directions = (-1, 1) if province else ((-1,) if suffix_district else (1, -1))
        for direction in directions:
            for count in (3, 2, 1):
                start, end = (i - count, i) if direction == -1 else (i + 1, i + 1 + count)
                if start < 0 or end > len(tokens) or any(j in taken or tokens[j].group() == ',' for j in range(start, end)):
                    continue
                value = phrase(start, end)
                key = geo_norm(strip_markers(value))
                if province and value.lower() in PROVINCE_ALIASES and geo_norm(PROVINCE_ALIASES[value.lower()]) in catalog:
                    key = geo_norm(PROVINCE_ALIASES[value.lower()])
                if key in catalog:
                    if province and not any(re.search(r'област|обл\.|облыс', ROWS[item][1], re.I) for item in catalog[key]):
                        continue
                    shown = prov_display(catalog[key][0]) if province else strip_markers(value)
                    match = min(start, i), max(end, i + 1), shown
                    break
            if match:
                break
        if not match and not province:
            if suffix_district:
                for count in (2, 1):
                    start = i - count
                    if start < 0 or any(j in taken or tokens[j].group() == ',' for j in range(start, i)):
                        continue
                    if count > 1 and geo_norm(tokens[start].group()) in CITY_KEYS:
                        start += 1
                    value = phrase(start, i)
                    if geo_norm(value) in {"белгісіз", "неизвестный", "неизвестно", "unknown"}:
                        break
                    if all(canonical_marker(tokens[j].group()) not in GEO_MARKERS | set(STREET_TYPES) | set(KW)
                           and not NUM_RE.match(tokens[j].group()) for j in range(start, i)):
                        match = start, i + 1, value
                        break
            else:
                for j in (i + 1, i - 1):
                    if 0 <= j < len(tokens) and j not in taken:
                        value = tokens[j].group()
                        if geo_norm(value) in {"белгісіз", "неизвестный", "неизвестно", "unknown"}:
                            continue
                        if value != ',' and canonical_marker(value) not in GEO_MARKERS | set(STREET_TYPES) | set(KW) and not NUM_RE.match(value):
                            match = min(i, j), max(i, j) + 1, value
                            break
        if not match and province:
            order = (i - 1, i + 1) if marker in {'облысы', 'облыс', 'oblast'} else (i + 1, i - 1)
            for j in order:
                if 0 <= j < len(tokens) and j not in taken:
                    value = tokens[j].group()
                    if value != ',' and canonical_marker(value) not in GEO_MARKERS | set(STREET_TYPES) | set(KW) and not NUM_RE.match(value):
                        match = min(i, j), max(i, j) + 1, value + ' ' + token.group()
                        break
        if match:
            claim(match[0], match[1], 'province' if province else 'district', match[2])
    for i, token in enumerate(tokens):
        marker = canonical_marker(token.group())
        if marker == 'қ' and i > 0 and geo_norm(tokens[i - 1].group()) in CITY_KEYS:
            taken.add(i)
            continue
        if i in taken or marker not in {'город', 'г', 'қала', 'қаласы', 'ауыл', 'ауылы', 'кент', 'село', 'пос', 'поселок', 'посёлок', 'с', 'п', 'ст'}:
            continue
        if marker in {'с', 'п', 'ст'} and not (i == 0 or tokens[i - 1].group() == ','):
            continue
        direction = -1 if marker in {'қаласы', 'ауылы'} else 1
        for count in (2, 1):
            start, end = (i - count, i) if direction < 0 else (i + 1, i + 1 + count)
            if start < 0 or end > len(tokens) or any(j in taken or tokens[j].group() == ',' for j in range(start, end)):
                continue
            value = phrase(start, end)
            if '/' in value:
                continue
            if geo_norm(value) in CITY_KEYS or (count == 1 and canonical_marker(value) not in GEO_MARKERS | set(STREET_TYPES) | set(KW) and not NUM_RE.fullmatch(value)):
                claim(min(i, start), max(i + 1, end), 'city', value)
                if marker in {'ауыл', 'ауылы', 'кент', 'село', 'пос', 'поселок', 'посёлок', 'с', 'п', 'ст'}:
                    out['_locality_kind'] = 'village'
                break
    for i in range(len(tokens)):
        if i in taken:
            continue
        for count in (2, 1):
            end = i + count
            if end > len(tokens) or any(j in taken or tokens[j].group() == ',' for j in range(i, end)):
                continue
            value = phrase(i, end)
            known_city = any(re.search(r'^г\.|город|қаласы', ROWS[item][1], re.I) for item in LOC.get(geo_norm(value), []))
            initial_city = i == 0 and end < len(tokens) and tokens[end].group() == ',' and known_city
            if geo_norm(value) not in CITY_KEYS and not initial_city:
                continue
            before = canonical_marker(tokens[i - 1].group()) if i else ''
            after = canonical_marker(tokens[end].group()) if end < len(tokens) else ''
            if (before in STREET_TYPES and after not in {'қаласы', 'қала'}) or before in LANDMARK_SET | LANDMARK_INFLECTIONS or before in {'область', 'обл', 'облыс', 'облысы', 'аудан', 'район'}:
                continue
            start = i - 1 if before in {'город', 'г', 'қала'} else i
            last = end + 1 if after in {'қаласы', 'қала'} else end
            claim(start, last, 'city', value)
            break
    if not out.get('district'):
        districts = district_catalog()
        city_tops = {top_of(item) for item in LOC.get(geo_norm(out.get('city', '')), [])}
        for i, token in enumerate(tokens):
            if i in taken:
                continue
            key = geo_norm(token.group())
            ids = districts.get(key, [])
            before = canonical_marker(tokens[i - 1].group()) if i else ''
            after = canonical_marker(tokens[i + 1].group()) if i + 1 < len(tokens) else ''
            if before in STREET_TYPES or after in STREET_TYPES or before in LANDMARK_SET | LANDMARK_INFLECTIONS:
                continue
            if city_tops:
                ids = [item for item in ids if top_of(item) in city_tops]
            elif not key.endswith(('ский', 'цкий')):
                continue
            if len(set(ids)) == 1:
                claim(i, i + 1, 'district', strip_markers(ROWS[ids[0]][1]))
                break
    spans = [(tokens[i].start(), tokens[i].end()) for i in taken]
    for start, end in sorted(spans, reverse=True):
        s = s[:start] + ' ' + s[end:]
    return out, s


def has_geo_conflict(res):
    cities = LOC.get(geo_norm(res.get('city') or ''), [])
    kind = r'село|с\.|пос|ауыл|аул|станц|ст\.' if res.get('_locality_kind') == 'village' else r'г\.а\.|^г\.|город|қаласы'
    cities = [i for i in cities if re.search(kind, ROWS[i][1], re.I)]
    provinces = PROV.get(geo_norm(strip_markers(res.get('province') or '')), [])
    return bool(cities and provinces and not ({top_of(i) for i in cities} & set(provinces)))


def canonical_marker(token):
    token = token.strip(".").lower()
    return MARKER_ALIASES.get(token, token)


def extract_living_area(s):
    marker = re.search(r"(?<!\w)(?:ж\s*[./]?\s*[мк]\.?|жк|жилмассив|жилой\s+массив|жилой\s+комплекс|тұрғын\s+алап|тұрғын\s+үй\s+кешені)(?!\w)\s*", s, re.I)
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
    t = text.strip(". ")
    if not t or NUM_RE.match(t.lower()):
        return False
    return geo_norm(t) in CITY_KEYS


def split_leading_city(seg):
    if len(seg) < 2 or nt(seg[0]) in STREET_TYPES or nt(seg[0]) in GEO_MARKERS:
        return None, seg
    for k in (2, 1):
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
        if stype not in NUMBER_BEFORE_TYPE and not out["living_area"]:
            for part in later:
                for area_pos, area_token in enumerate(part):
                    if nt(area_token) not in NUMBER_BEFORE_TYPE:
                        continue
                    area_name = part[:area_pos] + [area_token] + part[area_pos + 1:]
                    out["living_area"] = " ".join(area_name)
                    break
                if out["living_area"]:
                    break

        if stype == "микрорайон" and ti >= 1 and not NUM_RE.match(nt(seg[ti - 1])):
            name = seg[:ti]
            tail = seg[ti + 1:]
            if out["house"] is not None:
                name += tail
                tail = []
        elif stype in NUMBER_BEFORE_TYPE and ti >= 1 and NUM_RE.match(nt(seg[ti - 1])):
            if stype == "микрорайон":
                name = seg[:ti]
                out["living_area"] = None
            else:
                name = [seg[ti - 1]]
                out["living_area"] = " ".join(seg[:ti - 1]) or None
            tail = seg[ti + 1:]
        else:
            name = seg[ti + 1:]
            tail = []
            for offset, token in enumerate(name):
                if nt(token) in STREET_TYPES and STREET_TYPES[nt(token)] not in NUMBER_BEFORE_TYPE:
                    name = name[:offset]
                    break
            suffix_number = (stype not in NUMBER_BEFORE_TYPE and len(name) == 1
                             and NUM_RE.match(nt(name[0])))
            if ti > 0 and (not name or nt(name[0]) in KW or suffix_number):
                if suffix_number and out["house"] is None:
                    out["house"] = name[0].strip(".")
                name = seg[:ti]
            if (len(name) == 1 and NUM_RE.match(nt(name[0])) and ti > 0
                    and stype not in NUMBER_BEFORE_TYPE and out["house"] is None):
                out["house"] = name[0].strip(".")
                name = seg[:ti]
            elif not name and ti > 0:
                name = seg[:ti]
        if out['house'] is not None and stype not in NUMBER_BEFORE_TYPE and len(name) >= 2 and NUM_RE.fullmatch(nt(name[-1])):
            name = name[:-1]

        if out["house"] is None:
            for part in [tail] + later:
                if any(nt(token) in NUMBER_BEFORE_TYPE for token in part):
                    continue
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
        "postal_code": None, "building": None, "structure": None,
        "confidence": 0.0,
    }
    parenthetical_notes = "; ".join(
        " ".join(note.split()) for note in PARENTHETICAL_NOTE.findall(raw or "") if note.strip()
    ) or None
    without_notes = PARENTHETICAL_NOTE.sub(" ", raw or "")
    source_text = strip_post_boxes(strip_access_notes(clean(without_notes)))
    no_house_number = bool(re.search(r"(?<!\w)(?:дом|дм|д|үй)?\s*б\s*/\s*н(?!\w)", source_text, re.I))
    if no_house_number:
        source_text = re.sub(r"(?<!\w)(?:дом|дм|д|үй)?\s*б\s*/\s*н(?!\w)", " ", source_text, flags=re.I)
    highway_route, s = extract_highway_route(source_text)
    from app.normalization import join_spaced_numbers
    s = join_spaced_numbers(s)
    s = join_digit_runs(s)
    postal_code, s = extract_postal(s)
    s = split_compact_geography(s)
    s = split_compact_chains(s)
    s = normalize_compact(s)
    fused_street_suffix = None
    suffix_match = re.search(
        r"(?<!\w)(?:улица|ул|проспект|пр-т|пр|street|st)\s+(.+?)(\d+)\s*(?=(?:дом|дм|д|үй)\s*\d)",
        s, re.I,
    )
    if suffix_match:
        fused_street_suffix = f"{suffix_match.group(1).strip()} {suffix_match.group(2)}"
    glued_fields, s = extract_glued_fields(s)
    s = normalize_compact(s)
    s = split_glued(s)
    s = join_house_letter(s)
    s = split_compact_geography(s)
    living_area, s = extract_living_area(s)
    fields, s = extract_keyword_fields(s)
    fields.update(glued_fields)
    for k, v in fields.items():
        res[k] = v

    explicit_geo, s = extract_inline_geo(s)
    intersection, s = extract_intersection(s)
    landmark, s = extract_landmark(s)

    st = parse_street(s, res["house"])
    if highway_route:
        st['street_type'] = highway_route['street_type']
        st['street_name'] = highway_route['street_name']
    if fused_street_suffix and st.get("street_type") and st.get("street_name"):
        st["street_name"] = fused_street_suffix
    pair = re.fullmatch(r"(.+?)\s+(\d+)-(\d+)", st.get("street_name") or "")
    if (pair and not res.get("house") and not st.get("house") and not res.get("apartment")):
        st["street_name"] = pair.group(1).strip()
        st["house"] = pair.group(2)
        res["apartment"] = pair.group(3)
    house_pair = re.fullmatch(r"(\d+)-(\d+)", str(st.get("house") or res.get("house") or ""))
    if house_pair and not res.get("apartment"):
        st["house"] = house_pair.group(1)
        res["house"] = house_pair.group(1)
        res["apartment"] = house_pair.group(2)
    if (st["house"] is None and st["street_name"] and res.get("entrance")
            and "/" in str(res["entrance"])):
        st["house"] = res["entrance"]
        res["entrance"] = None
    for k in ("street_type", "street_name", "house", "landmark", "living_area"):
        res[k] = st[k]
    if no_house_number:
        res["house"] = "б/н"
    if res["street_name"]:
        street_name = re.sub(r"\s+(?:д|дм|дом)\.?\s*$", "", res["street_name"], flags=re.I)
        street_name = re.sub(r"^[\s.,;:№#]+|[\s.,;:№#]+$", "", street_name)
        street_name = re.sub(r"\s+", " ", street_name).strip()
        numeric_quarter = (res.get("street_type") in NUMBER_BEFORE_TYPE
                           and bool(NUM_RE.fullmatch(street_name)))
        if not re.search(r"[^\W\d_]", street_name, re.UNICODE) and not numeric_quarter:
            street_name = None
        res["street_name"] = street_name or None
    if living_area:
        res["living_area"] = living_area
    if res.get("street_name"):
        name = str(res["street_name"]).strip()
        if res.get("street_type") not in NUMBER_BEFORE_TYPE:
            house_tail = re.fullmatch(r"(.+\D)\s+(\d+[a-zа-я]?(?:/\d+[a-zа-я]?)?)", name, re.I)
            if house_tail and not res.get("house"):
                res["street_name"] = house_tail.group(1).strip()
                res["house"] = house_tail.group(2)
            elif house_tail and res.get("house") == house_tail.group(2):
                res["street_name"] = house_tail.group(1).strip()
        res["street_name"] = re.sub(r"\s+(?:код|дом|дм|д|үй)\s*$", "", str(res["street_name"]), flags=re.I).strip()
        if re.fullmatch(r"(?:kb|kv|flat|дом|дм|подъезд|podest|пд)", res["street_name"], re.I):
            res["street_name"] = None
    if landmark:
        res["landmark"] = landmark
    if intersection:
        res["landmark"] = "; ".join(value for value in (intersection, res.get("landmark")) if value)
    if parenthetical_notes:
        res["landmark"] = "; ".join(value for value in (res.get("landmark"), parenthetical_notes) if value)
    city_segment = explicit_geo.get('city', '') + (' ауылы' if explicit_geo.get('_locality_kind') == 'village' else '')
    geo_segments = ([explicit_geo['province']] if explicit_geo.get('province') else []) + st["_geo"] + ([city_segment] if city_segment else [])
    g = resolve_geo(geo_segments)
    res["province"], res["city"], res["district"] = g["province"], g["city"], g["district"]
    res.update(explicit_geo)
    for geo_field in ("city", "province"):
        geo_value = res.get(geo_field)
        if geo_value and len(re.sub(r"[^\w]", "", str(geo_value))) == 1:
            res[geo_field] = None
    res["city"] = russian_city(res["city"])
    if not res.get("city"):
        locality = re.match(r"^\s*(?:(?:с|пос|п|ст)\.?|село|поселок|посёлок|ауыл(?:ы)?)\s+([^,]+)", source_text, re.I)
        if locality:
            candidate = locality.group(1).strip(" .,")
            if candidate and canonical_marker(candidate) not in GEO_MARKERS | set(STREET_TYPES) | set(KW):
                res["city"] = candidate
                res["_locality_kind"] = "village"

    if res.get("district"):
        from app.geo import DIST, ROWS, strip_markers, top_of
        district_key = geo_norm(strip_markers(res["district"]))
        district_ids = DIST.get(district_key, [])
        city_ids = LOC.get(geo_norm(res.get("city") or ""), [])
        city_tops = {top_of(item) for item in city_ids}
        matching = [item for item in district_ids if not city_tops or top_of(item) in city_tops]
        if len(matching) == 1:
            res["district"] = strip_markers(ROWS[matching[0]][1])
        else:
            district = str(res["district"]).strip()
            res["district"] = district[:1].upper() + district[1:]


    if not res.get("district") and res["city"] and res.get("living_area") and res.get("_locality_kind") != 'village':
        area_district = osm.lookup_place_district(geo_norm(res["city"]), res["living_area"])
        if area_district:
            res["district"] = area_district

    street_match = 'not_checked'
    if res["city"] and res["street_name"] and res.get('_locality_kind') != 'village':
        info = osm.lookup(geo_norm(res["city"]), res["street_name"], res["street_type"])
        street_match = 'matched' if info else 'not_confirmed'
        if info:
            if not res["district"] and info.get("district"):
                res["district"] = info["district"]
            if not res["street_type"] and info.get("street_type"):
                res["street_type"] = info["street_type"]
    elif not res["city"] and res["street_name"] and not res["street_type"]:
        inferred_type = osm.lookup_street_type_global(res["street_name"])
        if inferred_type:
            res["street_type"] = inferred_type
            street_match = 'global_type_inferred'

    res['postal_code'] = postal_code
    from app.review import build_review
    res['review'] = build_review(raw, res, street_match=street_match)
    issue_codes = {issue['code'] for issue in res['review']['issues']}
    route_kilometer = bool(res.get('street_type') in {'тракт','шоссе'} and res.get('street_name')
                           and re.search(r'\b(?:\d+\s*км|\d+\s*-\s*й\s+километр)\b',res['street_name'],re.I))
    if not res.get('house') and not route_kilometer:
        confidence = 0.35
    elif 'unassigned_numbers' in issue_codes or has_geo_conflict(res):
        confidence = 0.55
    elif not (res.get('street_name') or res.get('living_area')):
        confidence = 0.65
    elif street_match == 'not_confirmed':
        confidence = 0.78
    elif street_match == 'matched':
        confidence = 0.95
    else:
        confidence = 0.90
    res['confidence'] = confidence
    return res
