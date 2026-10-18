
import re
import unicodedata

LOW = 'а-яёәіңғүұқөһ'
UP = 'А-ЯЁӘІҢҒҮҰҚӨҺ'
BN = '\x01'  # «б/н» (без номера) как один символ

_CHUNK = re.compile(
    rf'(?P<num>\d+(?:/\d+)?(?:-\d+)?)'
    rf'|(?P<bn>{BN})'
    rf'|(?P<caps>[{UP}]{{2,}}(?![{LOW}])|[A-Z]{{2,}}(?![a-z]))'
    rf'|(?P<cap>[{UP}][{LOW}]*(?:-[{UP}][{LOW}]*)*|[A-Z][a-z]*(?:-[A-Z][a-z]*)*)'
    rf'|(?P<low>[{LOW}]+|[a-z]+)'
    rf'|(?P<slash>/)'
    rf'|(?P<other>\S)'
)

FIELD = {}
for _name, _words, _suffix in (
    ('house', ('д', 'дом', 'дм', 'house'), False),
    ('house', ('үй', 'үйі', 'уй'), True),
    ('apartment', ('кв', 'квартира', 'кварт', 'офис', 'оф', 'пом', 'помещ', 'помещение', 'flat', 'kv', 'kb', 'apt'), False),
    ('apartment', ('пәтер', 'пэтер', 'pater'), True),
    ('entrance', ('под', 'подъезд', 'подьезд', 'подезд', 'пд'), False),
    ('entrance', ('кіреберіс', 'киреберис'), True),
    ('floor', ('эт', 'этаж', 'floor'), False),
    ('floor', ('қабат', 'кабат'), True),
    ('building', ('корп', 'корпус', 'блок', 'block'), False),
    ('structure', ('стр', 'строение'), False),
):
    for _w in _words:
        FIELD[_w] = (_name, _suffix)

TYPE = {
    'ул': 'ул.', 'улица': 'ул.', 'көше': 'ул.', 'көшесі': 'ул.', 'ul': 'ул.',
    'пр': 'пр.', 'пр-т': 'пр.', 'пр-кт': 'пр.', 'проспект': 'пр.', 'даңғылы': 'пр.', 'даңғыл': 'пр.',
    'мкр': 'мкр.', 'мкрн': 'мкр.', 'микрорайон': 'мкр.', 'mkr': 'мкр.',
    'пер': 'пер.', 'переулок': 'пер.', 'бул': 'бул.', 'бульвар': 'бул.',
}
GEO = {  # суффиксы геообъектов в казахском: «Қарасайауданы»
    'ауданы': 'district', 'аудан': 'district', 'район': 'district',
    'ауылы': 'locality', 'ауыл': 'locality',
    'облысы': 'province', 'обл': 'province', 'область': 'province',
}
CITY_TAIL = {'ш', 'қ', 'қала', 'қаласы', 'г'}
LIVING = {'жк', 'жм'}
LETTER_MARKERS = set('дкспо')  # одиночные строчные буквы, которые чаще маркеры, чем литера дома

_MARKERS_BY_LEN = sorted(set(FIELD) | set(TYPE) | set(GEO), key=len, reverse=True)
_PEEL = sorted([m for m in set(FIELD) | set(GEO) | {'көшесі', 'көше', 'даңғылы', 'даңғыл'} if len(m) >= 2],
               key=len, reverse=True)
_ROMAN = re.compile(r'[IVXLC]+', re.I)


def _segment_lower(word):
    """'дкв' -> ['д','кв']; если разобрать целиком нельзя — [word]."""
    out, pos = [], 0
    while pos < len(word):
        for marker in _MARKERS_BY_LEN:
            if word.startswith(marker, pos):
                out.append(marker)
                pos += len(marker)
                break
        else:
            return [word]
    return out


def _peel_suffixes(word):
    """'Вкв' -> ('В',['кв']), 'Елдаңғылы' -> ('Ел',['даңғылы']), 'Қарасайауданы' -> ('Қарасай',['ауданы'])."""
    tail = []
    while True:
        low = word.lower()
        for marker in _PEEL:
            if low.endswith(marker) and len(word) > len(marker):
                head = word[:-len(marker)]
                # одиночную заглавную букву оставляем (литера корпуса), иначе голова >= 2 букв
                if len(head) >= 2 or head.isupper():
                    word = head
                    tail.insert(0, marker)
                    break
        else:
            return word, tail


def _chunks(text):
    items = []
    for m in _CHUNK.finditer(text):
        kind, value = m.lastgroup, m.group()
        if kind == 'other':
            continue
        items.append([kind, value])
    return items


def _find_city(word, is_city):
    """Самый длинный префикс-город + допустимый «хвост» (маркер типа улицы, ш/қ, обл...)."""
    low_tails = set(TYPE) | set(GEO) | CITY_TAIL | LIVING

    def tail_ok(rest):
        rest = rest.lower()
        if rest == '' or rest in low_tails:
            return True
        # опечатка вида «Атыраулмкр»: один лишний символ перед известным маркером
        return any(rest.endswith(t) and len(rest) - len(t) == 1 for t in low_tails if len(t) >= 2)

    for k in range(len(word), 2, -1):
        if is_city(word[:k]) and tail_ok(word[k:]):
            return word[:k], word[k:].lower()
    return None, None


def explode(raw, is_city):
    """Возвращает каноническую строку «г. Город, ул. Улица, д. 1, кв. 2» либо None."""
    s = unicodedata.normalize('NFKC', raw or '')
    s = re.sub(r'[\u200b-\u200f\u2060\ufeff\u00ad]', '', s).strip()
    if len(s) < 12 or re.search(r'[\s,;]', s) or not re.search(r'\d|б\s*/\s*н', s, re.I):
        return None  # обычная строка — её разберёт основной конвейер

    s = re.sub(r'б\s*/\s*н', BN, s, flags=re.I)
    s = re.sub(r'№|No\.?', '', s)
    raw_items = _chunks(s)

    # 1) раскладываем куски: отщепляем маркеры, режем строчные цепочки
    items = []
    for kind, value in raw_items:
        if kind == 'cap':
            head, tail = _peel_suffixes(value)
            items.append(['cap', head])
            items.extend(['low', t] for t in tail)
        elif kind == 'low':
            parts = _segment_lower(value)
            if len(value) == 1 and value not in FIELD and value not in TYPE:
                items.append(['letter', value])
            else:
                items.extend(['low', p] for p in parts)
        else:
            items.append([kind, value])

    # 1б) «Байганинад3/2» -> Байганина + д; «Авангард3д22» (д дальше есть) не трогаем
    for k in range(len(items) - 1):
        kind, value = items[k]
        if (kind == 'cap' and items[k + 1][0] == 'num' and value[-1:] in 'дД' and len(value) >= 5
                and value[-2].lower() not in 'рнлзг'
                and not any(it[0] == 'low' and it[1] in ('д', 'дом') for it in items[k + 2:])):
            items[k][1] = value[:-1]
            items.insert(k + 1, ['low', 'д'])
            break

    # 2) приставка «г»/«г.» перед городом
    if items and items[0][0] == 'low' and items[0][1] in ('г', 'гор', 'город'):
        items.pop(0)
    elif items and items[0][0] == 'letter' and items[0][1] == 'г':
        items.pop(0)
    if not items or items[0][0] != 'cap':
        return None

    # 3) город (+ слитный маркер после него). Город мог быть отщеплён «по хвосту» — склеим заново.
    first = items[0][1]
    consumed = 1
    while True:
        city, rest = _find_city(first, is_city)
        if city:
            break
        # «Усть-Каменогорск»/двухсловные города: пробуем присоединить следующий cap
        if consumed < len(items) and items[consumed][0] == 'cap' and consumed < 3:
            first += items[consumed][1]
            consumed += 1
            continue
        return None
    items = items[consumed:]
    # опечатка «Атыраулмкр»: хвост = лишняя буква + маркер -> берём сам маркер
    if rest not in TYPE and rest not in GEO and rest not in CITY_TAIL:
        rest = next((t for t in sorted(TYPE, key=len, reverse=True) if rest.endswith(t)), rest)
    province = None
    if rest == '' and items and items[0][0] == 'low' and GEO.get(items[0][1]) == 'province':
        rest = items.pop(0)[1]
    if rest in GEO and GEO[rest] == 'province':
        province, city = city, None
    elif rest in TYPE:
        items.insert(0, ['low', rest])
    # остальные хвосты (ш, қ, ...) — просто признак города

    # 4) автомат полей
    out = {'house': None, 'apartment': None, 'entrance': None, 'floor': None,
           'building': None, 'structure': None}
    street_type, names, living, district, locality = None, [], None, None, None
    n = len(items)
    i = 0

    def take_value(j):
        """Значение поля после маркера: число(+литера), римская цифра, литера(+число). -> (value, next_j)."""
        if j >= n:
            return None, j
        kind, value = items[j]
        if kind == 'num':
            j += 1
            if j + 1 < n and items[j][0] == 'slash' and items[j + 1][0] in ('letter', 'cap') and len(items[j + 1][1]) == 1:
                value += '/' + items[j + 1][1]
                j += 2
                return value, j
            if j < n and items[j][0] in ('letter', 'cap') and len(items[j][1]) == 1 and items[j][1].lower() not in LETTER_MARKERS:
                value += items[j][1]
                j += 1
            return value, j
        if kind == 'caps' and _ROMAN.fullmatch(value):
            return value, j + 1
        if kind in ('cap', 'letter') and len(value) == 1:
            letter = value
            j += 1
            if j < n and items[j][0] == 'num':
                letter += items[j][1]
                j += 1
            return letter, j
        if kind == 'bn':
            return 'б/н', j + 1
        return None, j

    while i < n:
        kind, value = items[i]
        low = value.lower()

        if kind == 'num':
            nxt = items[i + 1] if i + 1 < n else None
            nxt2 = items[i + 2] if i + 2 < n else None
            # «144үй», «34пәтер» — число перед казахским маркером
            if nxt and nxt[0] == 'low' and nxt[1] in FIELD and FIELD[nxt[1]][1]:
                out[FIELD[nxt[1]][0]] = value
                i += 2
                continue
            # «12д» + «кв…»: д — суффикс дома, а не префикс следующего числа
            if nxt and nxt[0] == 'low' and nxt[1] in ('д', 'дом') and (nxt2 is None or nxt2[0] != 'num'):
                out['house'] = value
                i += 2
                continue
            val, j = take_value(i)
            # у микрорайона первое число — часть названия («Аксай 4»), дом идёт после «д»
            if street_type == 'мкр.' and names and not names[-1][-1:].isdigit() and out['house'] is None \
                    and j < n and items[j][0] == 'low' and items[j][1] in ('д', 'дом'):
                names[-1] += ' ' + val
                i = j
                continue
            if out['house'] is None:
                out['house'] = val
            i = j
            continue

        if kind == 'bn':
            out['house'] = 'б/н'
            i += 1
            continue

        if kind == 'low' and low in FIELD:
            field, _ = FIELD[low]
            val, j = take_value(i + 1)
            if val is not None and out[field] is None:
                out[field] = val
                i = j
                continue
            i += 1
            continue

        if kind == 'low' and low in TYPE:
            street_type = TYPE[low]
            i += 1
            continue

        if kind == 'low' and low in GEO:
            target = GEO[low]
            if names:
                value_ = ' '.join(names)
                names = []
                if target == 'district':
                    district = value_
                elif target == 'locality':
                    locality = value_
                elif target == 'province':
                    province = value_
            i += 1
            continue

        if kind == 'caps' and low in LIVING:
            j, area = i + 1, []
            while j < n and items[j][0] in ('cap', 'caps') and items[j][1].lower() not in LIVING:
                area.append(items[j][1])
                j += 1
            living = ' '.join(area) or None
            i = j
            continue

        if kind in ('cap', 'caps'):
            names.append(value)
            i += 1
            continue

        i += 1  # неопознанный мусор и одиночные «/»

    name = ' '.join(names) or None
    if not (name or living) and out['house'] is None:
        return None

    parts = []
    if province:
        parts.append(f'{province} облысы')
    if district:
        parts.append(f'{district} ауданы')
    if city:
        parts.append(f'г. {city}')
    if locality:
        parts.append(f'{locality} ауылы')
    if living:
        parts.append(f'ЖК {living}')
    if name:
        parts.append(f'{street_type} {name}' if street_type else name)
    for field, label in (('house', 'д.'), ('building', 'корп.'), ('structure', 'стр.'),
                         ('entrance', 'под.'), ('floor', 'эт.'), ('apartment', 'кв.')):
        if out[field]:
            parts.append(f'{label} {out[field]}')
    return ', '.join(parts)
