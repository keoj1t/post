import re

FIELD_WORDS = {
    'house': ('дом','дм','д','үй','үйі','уй','ui','uy','house','bld','building'),
    'apartment': ('квартира','кварт','кв','пәтер','пәтері','пэтер','pater','flat','kv','kb','apt','appt','apartment','офис','office','нп','пом','помещ','помещение'),
    'entrance': ('подъезд','подьезд','подьедз','подъедз','подезд','подъ','под','пд','podest','кіреберіс','кіреберісі','киреберис','entrance'),
    'floor': ('этаж','эт','қабат','қабаты','кабат','floor'),
    'building': ('корпус','корп','к','блок','block','корпусы'),
    'structure': ('строение','стр','құрылыс','құрылысы'),
}
STREET_WORDS = {
    'улица': ('улица','улиц','ул','көше','көшесі','көш','к-сі','косеси','кошеси','koshe','koshesi','street','st','str','ul'),
    'проспект': ('проспект','просп','пр-т','пр-кт','пркт','пр','даңғыл','даңғылы','даңғ','д-лы','дангылы','avenue','ave'),
    'переулок': ('переулок','пер','тұйық','тұйығы','туйык','lane'),
    'микрорайон': ('микрорайон','мкрн','мкр','mkr','шағынаудан','шағын-аудан','ықшамаудан','ықшам-аудан'),
    'квартал': ('квартал','кв-л','орам','орамы'),
    'бульвар': ('бульвар','бул','бульвары','boulevard'),
    'шоссе': ('шоссе','тасжол','тасжолы'),
    'проезд': ('проезд','өтпе','өткел'),
    'площадь': ('площадь','пл','алаң','алаңы'),
    'набережная': ('набережная','наб','жағалау','жағалауы'),
    'тупик': ('тупик',),
    'тракт': ('тракт','трасса','трасс','трассасы'),
}
CITY_ALIASES = {
    'ақтөбе':'актобе','ақтау':'актау','атырау':'атырау','қарағанды':'караганда','қостанай':'костанай',
    'қызылорда':'кызылорда','көкшетау':'кокшетау','талдықорған':'талдыкорган','түркістан':'туркестан',
    'теміртау':'темиртау','екібастұз':'экибастуз','орал':'уральск','өскемен':'усть-каменогорск',
    'петропавл':'петропавловск','жезқазған':'жезказган','қонаев':'конаев','балқаш':'балхаш','байқоңыр':'байконур',
    'нур-султан':'астана','нурсултан':'астана','nur-sultan':'астана','алма-ата':'алматы','alma-ata':'алматы',
    'astana':'астана','almaty':'алматы','aktobe':'актобе','aktau':'актау','atyrau':'атырау',
    'karaganda':'караганда','pavlodar':'павлодар','kostanay':'костанай','kyzylorda':'кызылорда',
    'shymkent':'шымкент','taraz':'тараз','semey':'семей','petropavlovsk':'петропавловск',
    'kokshetau':'кокшетау','taldykorgan':'талдыкорган','turkestan':'туркестан','uralsk':'уральск',
    'ekibastuz':'экибастуз','temirtau':'темиртау','rudny':'рудный','zhezkazgan':'жезказган','balkhash':'балхаш',
    'baikonur':'байконур','ust-kamenogorsk':'усть-каменогорск','ust kamenogorsk':'усть-каменогорск',
    'oskemen':'усть-каменогорск','semipalatinsk':'семей','petropavl':'петропавловск','konayev':'конаев','konaev':'конаев',
}
PROVINCE_ALIASES = {
    'ақмола':'акмолинская','ақтөбе':'актюбинская','қарағанды':'карагандинская','қостанай':'костанайская',
    'қызылорда':'кызылординская','маңғыстау':'мангистауская','жамбыл':'жамбылская','жетісу':'жетісу',
    'түркістан':'туркестанская','ұлытау':'ұлытау','абай':'абай','алматы':'алматинская',
    'жетысуская':'жетісу','улытауская':'ұлытау','абайская':'абай',
    'атырау':'атырауская','павлодар':'павлодарская','батыс қазақстан':'западно-казахстанская',
    'шығыс қазақстан':'восточно-казахстанская','солтүстік қазақстан':'северо-казахстанская',
    'pavlodarskaya':'павлодарская','almatinskaya':'алматинская','karagandinskaya':'карагандинская',
    'akmolinskaya':'акмолинская','aktyubinskaya':'актюбинская','kostanayskaya':'костанайская',
    'atyrauskaya':'атырауская','mangistauskaya':'мангистауская','kyzylordinskaya':'кызылординская',
    'turkestanskaya':'туркестанская','zhambylskaya':'жамбылская','severo-kazakhstanskaya':'северо-казахстанская',
    'zapadno-kazakhstanskaya':'западно-казахстанская','vostochno-kazakhstanskaya':'восточно-казахстанская',
}
POSTAL = r'(?:\d{6}|[A-Z]\d{2}[A-Z]\d[A-Z]\d)'
ACCESS_NOTE = re.compile(r'(?<!\w)(?:код|домофон|звонить|оставить|пароль)(?=\s|[:#№-]|\d|$).*$', re.I)
POST_BOX = re.compile(r'(?<!\w)(?:(?:абонентский|почтовый)\s+ящик\s*)?(?:а\s*/\s*я|a\s*/\s*y)\s*[:№#.-]?\s*[\w/-]+|(?<!\w)(?:абонентский|почтовый)\s+ящик\s*[:№#.-]?\s*[\w/-]+', re.I)
PARENTHETICAL_NOTE = re.compile(r'\(([^()]*)\)')
ACCESS_CODE = re.compile(r'(?<!\w)#\s*[A-ZА-Я]?\d+[A-ZА-Я]?(?!\w)', re.I)


def strip_access_notes(text):
    """Remove delivery/access instructions so their codes cannot become address numbers."""
    text = PARENTHETICAL_NOTE.sub(' ', text or '')
    text = ACCESS_CODE.sub(' ', text)
    return ACCESS_NOTE.sub('', text).rstrip(' ,;')


def strip_post_boxes(text):
    """Remove postal-box identifiers so their numbers are not parsed as address units."""
    return POST_BOX.sub(' ', text or '')


def _typo_aliases():
    words={word for group in (*FIELD_WORDS.values(),*STREET_WORDS.values()) for word in group if len(word)>=5}
    candidates={}
    for word in words:
        variants={word[:i]+word[i+1:] for i in range(len(word))}
        variants|={word[:i]+word[i+1]+word[i]+word[i+2:] for i in range(len(word)-1)}
        variants|={word[:i]+word[i]+word[i:] for i in range(len(word))}
        for variant in variants:candidates.setdefault(variant,set()).add(word)
    return {variant:next(iter(targets)) for variant,targets in candidates.items() if len(targets)==1 and variant not in words}


TYPO_ALIASES=_typo_aliases()


def extract_postal(s):
    label=r'(?:почтовый\s*индекс|пошталық\s*индекс|пошта\s*индексі|индекс[і]?|postal\s*code|postcode|zip\s*code|zipcode|zip)'
    explicit = re.compile(rf'(?<!\w){label}\s*[:№#.-]?\s*((?=[A-Z0-9]*\d)[A-Z0-9]{{4,10}})(?!\w)',re.I)
    matches=list(explicit.finditer(s))
    if not matches:
        matches=list(re.finditer(rf'(?<!\w)({POSTAL})\s*{label}(?!\w)',s,re.I))
    if not matches:
        for match in re.finditer(rf'(?<!\w){POSTAL}(?!\w)',s,re.I):
            before=s[:match.start()]
            if re.search(r'(?:дом|дм|үй|квартира|пәтер|bld|appt)\s*[.№#]?\s*$',before,re.I):
                continue
            matches.append(match)
    if not matches:
        return None,s
    first=matches[0]
    value=first.group(1) if first.lastindex else first.group()
    for match in reversed(matches):s=s[:match.start()]+' '+s[match.end():]
    return value.upper(),s


def join_spaced_numbers(s):
    """После явного маркера одиночные цифры образуют один номер; запятая — граница."""
    words = {word for group in FIELD_WORDS.values() for word in group}
    words |= {alias for alias, target in TYPO_ALIASES.items() if target in words}
    markers = '|'.join(re.escape(word) for word in sorted(words, key=len, reverse=True))
    pattern = rf'(?<!\w)({markers})(\.?\s*)(\d(?:[ \t]+\d){{1,5}})(?!\w|[ \t]+\d)'
    return re.sub(pattern, lambda m: m[1]+m[2]+re.sub(r'\s+', '', m[3]), s, flags=re.I)


def normalize_compact(s):
    """Разделяет маркеры на границах чисел и в начале слова, не режет произвольные названия."""
    s=re.sub(r'(?<!\w)((?i:ул|ul|мкрн|мкр|mkr|пр-т|пр))(?=[А-ЯӘІҢҒҮҰҚӨҺ])',r'\1 ',s)
    s=re.sub(
        r'(?P<prefix>[^\W\d_]*?)(?P<number>\d+[а-яa-z]?)(?P<marker>дом|дм|үйі?|уй)(?P<tail>/\d+[а-яa-z]?)',
        lambda m: (m['prefix'] + ' ' if m['prefix'] else '') + m['marker'] + ' ' + m['number'] + m['tail'],
        s, flags=re.I,
    )
    field_words={word for words in FIELD_WORDS.values() for word in words if len(word)>=2}
    street_words={word for words in STREET_WORDS.values() for word in words if len(word)>=3}
    street_suffixes='|'.join(re.escape(word) for word in sorted(street_words,key=len,reverse=True))
    s=re.sub(rf'(?<!\w)({street_suffixes})(?=\d)',r'\1 ',s,flags=re.I)
    s=re.sub(rf'(?<=[^\W\d_])({street_suffixes})(?=\d)',r' \1 ',s,flags=re.I)
    markers='|'.join(re.escape(word) for word in sorted(field_words|street_words,key=len,reverse=True))
    fields='|'.join(re.escape(word) for word in sorted(field_words,key=len,reverse=True))
    glued_following = field_words | street_words | {'магазин','паркинг','парковка','тц','трц','банк','школа','аптека','qazpost','жанында','рядом','возле'}
    following='|'.join(re.escape(word) for word in sorted(glued_following,key=len,reverse=True))
    s=re.sub(rf'(?<!\w)({fields})(?=(?:{following}))',r'\1 ',s,flags=re.I)
    s=re.sub(rf'(?<!\w)({fields})\s*[№#:=]\s*(?=\d)',r'\1 ',s,flags=re.I)
    s=re.sub(rf'(?<!\w)({fields})\s*no\.?\s*(?=\d)',r'\1 ',s,flags=re.I)
    s=re.sub(rf'(?<!\w)({fields})(?=[a-zа-я]\d)',r'\1 ',s,flags=re.I)
    house_markers='|'.join(re.escape(word) for word in sorted(FIELD_WORDS['house'],key=len,reverse=True))
    apartment_markers='|'.join(re.escape(word) for word in sorted(FIELD_WORDS['apartment'],key=len,reverse=True))
    s=re.sub(rf'(?<!\w)({house_markers})({apartment_markers})(?=\d)',r'\1 \2 ',s,flags=re.I)
    s=re.sub(rf'(?<=\d)({house_markers})\s*({apartment_markers})(?=\s*\d)',r' \1 \2 ',s,flags=re.I)
    s=re.sub(rf'(?<!\w)({fields})\?\s*',r'\1 ',s,flags=re.I)
    s=re.sub(rf'(?<!\w)({fields})\s*[—–]\s*(?=\d)',r'\1 ',s,flags=re.I)
    s=re.sub(r'(?<!\w)(ул|ul|st)\s*\.(?=\s|$)',r'\1 ',s,flags=re.I)
    s=re.sub(r'(?<!по)(?<![Пп][Оо])(?<=[^\W\d_])д\.\s*(?=\d)',' д',s)   # не рвём «под. 2» на «по д2»
    s=re.sub(rf'(?<=\d)-(?=(?:{markers}))',' ',s,flags=re.I)
    s=re.sub(rf'(?<=\d)(?=(?:{markers}))',' ',s,flags=re.I)
    s=re.sub(r'(?<=\d)(?=[^\W\d_]{2,})',' ',s,flags=re.U)
    full_markers=sorted(set(STREET_WORDS)|{'мкр','мкрн','көшесі','көше','даңғылы','даңғыл','тұйық','тұйығы','шағынаудан','ықшамаудан'},key=len,reverse=True)
    full_markers+=sorted({alias for alias,target in TYPO_ALIASES.items() if target in street_words and len(target)>=5},key=len,reverse=True)
    known=field_words|street_words
    def separate_name(match):
        token=match.group()
        if token.lower() in known or token.lower() in TYPO_ALIASES:return token
        for marker in full_markers:
            if token.lower().startswith(marker) and len(token)>len(marker)+1:
                tail=token[len(marker):].lower()
                if re.match(r'[ьъыйэ]',tail) or tail in {'ная','ный','ное','ной','ные','овая','овый','ская','ский','ых','ого'}:
                    return token
                return token[:len(marker)]+' '+token[len(marker):]
        return token
    s=re.sub(r'(?<!\w)[^\W\d_]+',separate_name,s)
    s=re.sub(r'(?<!\w)(ул|ul|st)\.(?=\w)',r'\1 ',s,flags=re.I)
    s=re.sub(r'(?<!\w)(город|қала(?!сы)|область|облыс(?!ы)|район)\s*(?=[^\W\d_])',r'\1 ',s,flags=re.I)
    s=re.sub(r'(?<=\w)(?=қаласы\b|облысы\b|ауданы\b)',' ',s,flags=re.I)
    return s


def split_compact_chains(s):
    s=re.sub(r'(?<!\w)(?:(?:дом|дм|д)\s*)?(\d+[а-яa-z]?(?:/\d+[а-яa-z]?)?)[- ]?(к|k|с|c)(\d+)(?!\w)',
             lambda match:'дом'+match[1]+(' корпус' if match[2].lower() in {'к','k'} else ' строение')+match[3],s,flags=re.I)
    words={word for words in FIELD_WORDS.values() for word in words if len(word)>=2}
    words|={alias for alias,target in TYPO_ALIASES.items() if target in words}
    markers='|'.join(re.escape(word) for word in sorted(words,key=len,reverse=True))
    number=r'\d+[а-яa-z]??(?:/\d+[а-яa-z]??)?'
    streets='|'.join(re.escape(word) for words in STREET_WORDS.values() for word in sorted(words,key=len,reverse=True) if len(word)>2)
    prefix=re.compile(rf'(?:{markers}){number}(?=(?:{markers})|(?:{streets})|$)',re.I)
    suffix=re.compile(rf'{number}(?:{markers})(?=\d|(?:{markers})|(?:{streets})|$)',re.I)
    def separate(match):
        token=match.group()
        position=0;parts=[]
        while position<len(token):
            pattern=suffix if token[position].isdigit() else prefix
            pair=pattern.match(token,position)
            if not pair:break
            parts.append(pair.group());position=pair.end()
        if not parts:return token
        if position<len(token):parts.append(token[position:])
        return ' '.join(parts)
    return re.sub(r'[^\s,;]+',separate,s)
