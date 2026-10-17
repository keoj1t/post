"""Объяснимая проверка: причины, исходные свидетельства и варианты без автоматической подмены."""
import re
from collections import Counter
from rapidfuzz import process, fuzz
from app.normalization import FIELD_WORDS, STREET_WORDS, POSTAL, normalize_compact, strip_access_notes, strip_post_boxes


def build_review(raw, result, street_match='not_checked'):
    from app.parser import canonical_marker, has_geo_conflict, clean
    from app.geo import LOC, PROV, ROWS, norm, strip_markers, prov_display, depth_of, top_of
    from app.normalization import join_spaced_numbers
    filtered_raw = strip_post_boxes(strip_access_notes(clean(raw or '')))
    numbered = join_spaced_numbers(filtered_raw)
    text=normalize_compact(numbered)
    address_text=re.split(r'(?<!\w)(?:ориентир|рядом|возле|напротив|около|рынок|базар|магазин|тц|трц|кафе|аптека)(?!\w)',text,maxsplit=1,flags=re.I)[0]
    issues=[]
    def add(code,field,ru,kk,hint_ru,hint_kk,severity='warning',candidates=None):
        observed_keys=[field] if field else ['city','province']
        if code=='unassigned_numbers':observed_keys=list(FIELD_WORDS)+['city','province','street_name','living_area','postal_code']
        issues.append({'code':code,'field':field,'severity':severity,'message':{'ru':ru,'kk':kk},
                       'suggestion':{'ru':hint_ru,'kk':hint_kk},'candidates':candidates or [],
                       'observed':{key:result.get(key) for key in observed_keys}})
    def geo_candidates(value,catalog,field):
        matches=process.extract(norm(strip_markers(value)),catalog.keys(),scorer=fuzz.ratio,score_cutoff=86,limit=3)
        choices=[]
        for key,score,_ in matches:
            item=min(catalog[key],key=depth_of)
            shown=prov_display(item) if field=='province' else strip_markers(ROWS[item][1])
            if not any(choice['label']==shown for choice in choices):choices.append({'label':shown,'changes':{field:shown}})
        return choices
    if numbered != filtered_raw:
        add('joined_number_digits',None,'Раздельные цифры после маркера объединены в номер.','Белгіден кейінгі бөлек цифрлар бір нөмірге біріктірілді.',
            'Например, «квартира 9 8» прочитана как «квартира 98». Проверьте номер по исходной строке.',
            'Мысалы, «пәтер 9 8» — «пәтер 98» деп оқылды. Нөмірді бастапқы жолдан тексеріңіз.',severity='info')
    market_destination = bool(result.get('landmark') and re.search(r'рынок|базар',result['landmark'],re.I))
    route_kilometer = bool(result.get('street_type') in {'тракт','шоссе'} and result.get('street_name')
                           and re.search(r'\b(?:\d+\s*км|\d+\s*-\s*й\s+километр)\b',result['street_name'],re.I))
    if not result.get('house') and not route_kilometer:
        add('missing_house','house','Не найден номер дома.','Үй нөмірі табылмады.','Сверьте номер с исходной строкой или уточните его у отправителя.','Нөмірді бастапқы жолдан тексеріңіз немесе жіберушіден нақтылаңыз.')
    if not result.get('street_name') and not result.get('living_area') and not market_destination:
        add('missing_street','street_name','Не найдена улица или жилмассив.','Көше не тұрғын алап табылмады.','Уточните тип и название улицы.','Көше түрі мен атауын нақтылаңыз.')
    if not result.get('city'):
        add('missing_city','city','Не найден город.','Қала табылмады.','Добавьте город: это поможет проверить область и район.','Қаланы қосыңыз: бұл облыс пен ауданды тексеруге көмектеседі.')
    elif norm(result['city']) not in LOC:
        add('unknown_city','city','Населённый пункт не найден в локальном справочнике.','Елді мекен жергілікті анықтамалықта табылмады.','Проверьте написание; варианты ниже — близкие названия, а не автоматическое исправление.','Жазылуын тексеріңіз; төмендегі нұсқалар — ұқсас атаулар, автоматты түзету емес.',candidates=geo_candidates(result['city'],LOC,'city'))
    if result.get('province') and norm(strip_markers(result['province'])) not in PROV:
        add('unknown_province','province','Область не найдена в локальном справочнике.','Облыс жергілікті анықтамалықта табылмады.','Проверьте название области. Близкие варианты требуют подтверждения.','Облыс атауын тексеріңіз. Ұқсас нұсқаларды растау қажет.',candidates=geo_candidates(result['province'],PROV,'province'))
    elif result.get('province') and re.search(r'област|облыс',result['province'],re.I):
        ids=PROV.get(norm(strip_markers(result['province'])),[])
        if ids and not any(re.search(r'област|обл\.|облыс',ROWS[item][1],re.I) for item in ids):
            add('invalid_province_kind','province','После маркера области указано название города.','Облыс белгісінен кейін қала атауы көрсетілген.',
                'Уточните административную область; не превращаем город в область автоматически.','Әкімшілік облысты нақтылаңыз; қаланы автоматты түрде облысқа айналдырмаймыз.')
    if has_geo_conflict(result):
        add('geo_conflict',None,'Город и область противоречат справочнику.','Қала мен облыс анықтамалыққа сәйкес келмейді.','Уточните, какое значение верно. Исходные значения сохранены.','Қай мән дұрыс екенін нақтылаңыз. Бастапқы мәндер сақталды.')
    if result.get('city') and not result.get('province'):
        locations=LOC.get(norm(result['city']),[])
        kind=r'село|с\.|пос|ауыл|аул|станц|ст\.' if result.get('_locality_kind')=='village' else r'г\.а\.|^г\.|город|қаласы'
        preferred=[item for item in locations if re.search(kind,ROWS[item][1],re.I)]
        tops={top_of(item) for item in (preferred or locations)}
        if len(tops)>1:
            choices=[{'label':prov_display(item),'changes':{'province':prov_display(item)}} for item in sorted(tops)[:5]]
            add('ambiguous_geo','city','Есть одноимённые населённые пункты в разных областях.','Әртүрлі облыста аттас елді мекендер бар.',
                'Уточните область или район; одного названия недостаточно.','Облыс не ауданды нақтылаңыз; жалғыз атау жеткіліксіз.',candidates=choices)
    postal=result.get('postal_code')
    if postal and not re.fullmatch(POSTAL,postal,re.I):
        add('invalid_postal','postal_code','Необычный формат почтового индекса.','Пошта индексінің пішімі ерекше.','Проверьте шесть цифр либо семизначный буквенно-цифровой индекс.','Алты санды не жеті таңбалы әріптік-сандық индексті тексеріңіз.')
    if postal:
        add('postal_unverified','postal_code','Индекс извлечён, но его соответствие зданию не проверено.','Индекс алынды, бірақ ғимаратқа сәйкестігі тексерілмеді.','При необходимости проверьте индекс в справочнике Казпочты.','Қажет болса индексті Қазпошта анықтамалығынан тексеріңіз.',severity='info')
    codes=[]
    for match in re.finditer(rf'(?<!\w){POSTAL}(?!\w)',filtered_raw,re.I):
        if re.search(r'(?:дом|дм|үй|квартира|пәтер|bld|appt)\s*[.№#]?\s*$',filtered_raw[:match.start()],re.I):continue
        if match.group().upper() not in codes:codes.append(match.group().upper())
    if len(codes)>1:
        add('conflicting_postal','postal_code','Указано несколько разных индексов.','Бірнеше түрлі индекс көрсетілген.',
            'Выберите индекс нужного здания; не объединяем их в один.','Қажетті ғимарат индексін таңдаңыз; индекстер біріктірілмейді.',candidates=[{'label':code,'changes':{'postal_code':code}} for code in codes])
    if street_match=='not_confirmed':
        add('street_not_confirmed','street_name','Улица не подтверждена локальными данными OSM.','Көше жергілікті OSM деректерімен расталмады.',
            'Возможны другое написание, новое название или неполный справочник. Проверьте название по источнику.','Басқа жазылу, жаңа атау не толық емес анықтамалық болуы мүмкін. Атауды бастапқы дерекпен салыстырыңыз.',severity='info')
    corrections=[]
    for token in re.findall(r'[^\W\d_]+',text):
        canonical=canonical_marker(token)
        if canonical!=token.lower() and (token.lower(),canonical) not in corrections:
            corrections.append((token.lower(),canonical))
    if corrections:
        shown=', '.join(before+' → '+after for before,after in corrections)
        add('normalized_markers',None,'Распознаны опечатки в маркерах: '+shown,'Белгілердегі қателер танылды: '+shown,
            'Проверьте разбор, если исправленный маркер мог быть частью названия. Названия не исправляем по сходству.','Түзетілген белгі атаудың бөлігі болса, нәтижені тексеріңіз. Атаулар ұқсастық бойынша түзетілмейді.',severity='info')
    number=r'(?:\d+[а-яa-z]?(?:/\d+[а-яa-z]?)?|[ivxlcdm]+(?:-[а-яa-z]+)?)'
    for field,words in FIELD_WORDS.items():
        relevant_words = [word for word in words if not (field == 'building' and word == 'к')]
        markers='|'.join(re.escape(word) for word in sorted(relevant_words,key=len,reverse=True))
        values=[]
        for match in re.finditer(rf'(?<!\w)(?:{markers})\.?\s*({number})(?!\w)',text,re.I):
            if match[1] not in values:values.append(match[1])
        if len(values)>1:
            candidates=[{'label':value,'changes':{field:value}} for value in values]
            add('conflicting_'+field,field,'Указано несколько разных номеров: '+', '.join(values),'Бірнеше түрлі нөмір көрсетілген: '+', '.join(values),
                'Выберите нужный номер по исходному адресу.','Бастапқы мекенжай бойынша қажетті нөмірді таңдаңыз.',candidates=candidates)
        unbound_marker = result.get(field) is None and re.search(rf'(?<!\w)(?:{markers})(?!\w)',address_text,re.I)
        negated_building = field == 'building' and re.search(r'(?<!\w)(?:корпус|корп|блок)\s+(?:нет|жоқ|жок|отсутствует)(?!\w)',text,re.I)
        descriptive_entrance = field == 'entrance' and re.search(
            r'(?<!\w)(?:подъезд|подьезд|кіреберіс|кіреберісі)\s+(?:со\s+двора|с\s+двора|со\s+стороны|с\s+улицы|возле\b|рядом\b|сол\b|оң\b|паркинг\w*\b|жанында\b)',
            text,re.I)
        if unbound_marker and not negated_building and not descriptive_entrance:
            add('unbound_'+field,field,'Маркер поля есть, но номер не определён.','Өріс белгісі бар, бірақ нөмір анықталмады.',
                'Восстановите границу: например, «дом 12, квартира 3». Склеенные соседние числа нельзя однозначно разделить.','Шекараны қалпына келтіріңіз: мысалы, «үй 12, пәтер 3». Біріккен көрші сандарды бірмәнді бөлу мүмкін емес.')
    seen=Counter(re.findall(r'\d+(?:/\d+)?',numbered))
    for key,value in result.items():
        if key not in {'confidence','review','raw_address','id'} and value:
            seen.subtract(re.findall(r'\d+(?:/\d+)?',str(value)))
    unused=[number for number,count in seen.items() if count>0]
    if unused:
        add('unassigned_numbers',None,'Не распределены числа: '+', '.join(unused),'Бөлінбеген сандар: '+', '.join(unused),
            'Проверьте, относятся ли они к дому, квартире, корпусу или названию улицы. Не выбираем значение наугад.','Олардың үйге, пәтерге, корпусқа не көше атауына қатысын тексеріңіз. Мәнді кездейсоқ таңдамаймыз.')
    marker_pattern='|'.join(re.escape(word) for words in STREET_WORDS.values() for word in sorted(words,key=len,reverse=True) if len(word)>2)
    streets=list(re.finditer(rf'(?<!\w)({marker_pattern})(?!\w)',address_text,re.I))
    types={word:kind for kind,words in STREET_WORDS.items() for word in words}
    streets=[match for match in streets if types[match[1].lower()] not in {'микрорайон','квартал'}]
    if len(streets)>1:
        candidates=[]
        for i,match in enumerate(streets):
            end=streets[i+1].start() if i+1<len(streets) else len(text)
            name=re.split(r'[,\d]',text[match.end():end],maxsplit=1)[0].strip()
            if name:candidates.append({'label':match[1]+' '+name,'changes':{'street_type':types[match[1].lower()],'street_name':name}})
        add('multiple_streets','street_name','В строке несколько типов или названий улиц.','Жолда бірнеше көше түрі не атауы бар.',
            'Это может быть пересечение или два адреса. Выберите основной адрес.','Бұл қиылыс не екі мекенжай болуы мүмкін. Негізгі мекенжайды таңдаңыз.',candidates=candidates)
    overlaps=list(re.finditer(r'(?<![^\W\d_])(?P<marker>улица|переулок|проспект|көшесі|даңғылы)(?P<name>[^\W\d_]{2,})',filtered_raw,re.I))
    uncertain=[match for match in overlaps if not (match['name'][0].isupper() and not match['marker'].isupper())]
    if uncertain:
        candidates=[]
        for match in uncertain:
            names=[match['name']]
            if match['marker'][-1].lower() in 'аеёиоуыэюяәіөұү':
                names.append(match['marker'][-1]+match['name'])
            candidates.extend({'label':name,'changes':{'street_name':name}} for name in names)
        add('marker_name_overlap','street_name','Граница маркера улицы и названия неоднозначна.','Көше белгісі мен атауының шекарасы екіұшты.',
            'Проверьте, не пропущена ли буква между маркером улицы и названием. Варианты ниже не подтверждены справочником.','Көше белгісі мен атауы арасында әріп түсіп қалмағанын тексеріңіз. Төмендегі нұсқалар анықтамалықпен расталмаған.',candidates=candidates)
    critical_codes = {'missing_house', 'unassigned_numbers', 'geo_conflict', 'unbound_house'}
    needs_review = any(issue['code'] in critical_codes for issue in issues)
    return {'needs_review':needs_review,'issues':issues,'method':'rules-v2','confidence_kind':'heuristic','street_match':street_match,'locality_kind':result.get('_locality_kind','unspecified')}
