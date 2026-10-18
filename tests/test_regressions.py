"""Регрессионные тесты разбора. Запуск: python tests/test_regressions.py  (или pytest tests)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.parser import parse_address  # noqa: E402

# raw -> ожидаемые поля (проверяем только перечисленные)
CASES = [
    # --- слитные строки из ТЗ и train ---
    ('гУральскпрТулбаева12кв44', dict(city='Уральск', street_type='проспект', street_name='Тулбаева', house='12', apartment='44')),
    ('г.Астанаул.Кабанбайбатыра58/1корп.Вкв.102', dict(city='Астана', street_type='улица', street_name='Кабанбайбатыра', house='58/1', building='В', apartment='102')),
    ('АлматымкрАксай4д78кв12', dict(city='Алматы', street_type='микрорайон', street_name='Аксай 4', house='78', apartment='12')),
    ('гШымкентпрБауыржанМомышулы21/Апомещ3', dict(city='Шымкент', street_name='Бауыржан Момышулы', house='21/А', apartment='3')),
    ('КарагандаулЛенина12АпомещениеIV', dict(city='Караганда', street_name='Ленина', house='12А', apartment='IV')),
    ('гПавлодарпрШакаримаб/нкв5', dict(city='Павлодар', street_name='Шакарима', house='б/н', apartment='5')),
    ('АстанақМәңгілікЕлдаңғылы55/2үй34пәтер', dict(city='Астана', street_type='проспект', street_name='Мәңгілік Ел', house='55/2', apartment='34')),
    ('гАктобеулБайганинад3/2кв10', dict(city='Актобе', street_name='Байганина', house='3/2', apartment='10')),
    ('гАтыраулмкрАвангард3д22кв105', dict(city='Атырау', street_type='микрорайон', street_name='Авангард 3', house='22', apartment='105')),
    ('СемейшШакаримкөшесі144үй', dict(city='Семей', street_type='улица', street_name='Шакарим', house='144')),
    ('гТуркестанулКожановад45а', dict(city='Туркестан', street_name='Кожанова', house='45а')),
    ('гКызылордаулАйтекеби12дкв3', dict(city='Кызылорда', street_name='Айтекеби', house='12', apartment='3')),
    ('гТалдыкорганмкрЖетысу15дкв2', dict(city='Талдыкорган', street_type='микрорайон', street_name='Жетысу', house='15', apartment='2')),
    ('гАстанаЖКHighvillAstanaблокС2кв302', dict(city='Астана', living_area='Highvill Astana', building='С2', apartment='302')),
    ('гШымкентмкрНурсатд101кв55', dict(city='Шымкент', street_type='микрорайон', street_name='Нурсат', house='101', apartment='55')),
    ('гАстанапрТуран48/2пом12', dict(city='Астана', street_name='Туран', house='48/2', apartment='12')),
    ('гСемейулМомышұлы22Аофис1', dict(city='Семей', street_name='Момышұлы', house='22А', apartment='1')),
    ('гУсть-КаменогорскпрАуэзова20/1кв8', dict(city='Усть-Каменогорск', street_name='Ауэзова', house='20/1', apartment='8')),
    # --- префиксы «пр/ул/мкр» не должны отъедать буквы названия ---
    ('г. Уральск, проспект Абулхаир хана, д. 153/1', dict(street_name='Абулхаир хана')),
    ('г. Усть-Каменогорск, СНТ "Светоч", улица 3-я, дача 88', dict(street_name='3я')),
    # --- номера, «№», «!!!», кавычки, под./д. ---
    ('г. Шымкент, ул. Байтурсынова, д. 5 «б», кв. 10, под. 2', dict(house='5б', apartment='10', entrance='2')),
    ('Республика Казахстан, г. Шымкент, ул. Г. Иляева, д. 25, кв. 14!!!', dict(city='Шымкент', street_name='Г. Иляева', house='25', apartment='14')),
    ('г. Караганда, пр-кт Бухар-Жырау, дом № 51/2, кв. № 18', dict(street_type='проспект', street_name='Бухар-Жырау', house='51/2', apartment='18')),
    ('г. Атырау, мкр.-н Алмагуль, д.-№ 14, кв.-№ 88', dict(street_type='микрорайон', street_name='Алмагуль', house='14', apartment='88')),
    ('г. Актобе... мкр. 11... д. 25... кв. 8', dict(city='Актобе', house='25', apartment='8')),
    ('г. Павлодар, ул. М. Жусупа, д. 280, офис 3 (2-й этаж)', dict(apartment='3', floor='2')),
    ('г.Астана,ул.М.Габдуллина,д.12,кв.45 (ориентир: за ТД «Арт»)', dict(landmark='за ТД «Арт»')),
    # --- казахские строки ---
    ('Ақмола облысы, Целиноград ауданы, Қосшы қ., Республика көшесі, 12-үй', dict(city='Қосшы', street_name='Республика', house='12')),
    ('Атырау облысы, Құлсары қ., Махамбет көшесі, 33-үй', dict(city='Құлсары', street_name='Махамбет', house='33')),
    ('Алматы ш., Медеу ауданы, Абай даңғылы, 150/2 үй, 12 пәтер', dict(province='Алматы', city='Алматы', district='Медеу', street_name='Абай', house='150/2', apartment='12')),
    ('Алматы облысы, Еңбекшіқазақ ауданы, Есік қ., Абай көшесі, 45 үй', dict(province='Алматинская область', city='Есік', street_name='Абай', house='45')),
    ('Астана қ., Нұра ауданы, Тұран даңғылы, 37/9 үй, 3-блок', dict(province='Астана', city='Астана', street_name='Тұран', house='37/9', building='3')),
    ('Алматы ш., Наурызбай ауданы, Абай даңғылының жалғасы, 10-үй', dict(city='Алматы', street_name='Абай', house='10')),
    ('Петропавл ш., Қазақстан Конституциясы көшесі, 40 үй', dict(street_name='Қазақстан Конституциясы', house='40')),
    ('Қарағанды ш., Бұқар жырау даңғылы, 42-үй, 8-пәтер', dict(city='Караганда', street_name='Бұқар жырау', house='42', apartment='8')),
    # --- обычные строки не должны ломаться ---
    ('город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70', dict(city='Алматы', street_type='микрорайон', street_name='Аксай 3а', house='59', apartment='70')),
    ('Ул .Курильская 9 кв 1', dict(street_type='улица', street_name='Курильская', house='9', apartment='1')),
]


def run():
    failed = 0
    for raw, expected in CASES:
        got = parse_address(raw)
        bad = {k: (v, got.get(k)) for k, v in expected.items() if got.get(k) != v}
        if bad:
            failed += 1
            print('FAIL', raw, bad)
    print(f'{len(CASES) - failed}/{len(CASES)} passed')
    return failed


def test_regressions():
    assert run() == 0


if __name__ == '__main__':
    sys.exit(1 if run() else 0)
