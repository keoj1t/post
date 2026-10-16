import unittest
import json
from pathlib import Path

from app.main import parse_one
from app.parser import parse_address, split_glued


class AddressVariantsTest(unittest.TestCase):
    def assert_fields(self, raw, **fields):
        parsed = parse_address(raw)
        for key, value in fields.items():
            self.assertEqual(parsed[key], value, (raw, key, parsed))

    def test_residential_markers_and_glued_numbers(self):
        for marker in ('жм', 'ЖМ', 'ж/м', 'ж.м.', 'жилмассив', 'жилой массив', 'тұрғын алап'):
            with self.subTest(marker=marker):
                self.assert_fields(f'{marker} Коктал1 переулок xxx дом1',
                                   living_area='Коктал 1', street_type='переулок',
                                   street_name='xxx', house='1')

    def test_residential_area_with_city_and_commas(self):
        self.assert_fields('Астана, жм Коктал 1, преулок Абая, дм 12/1 кв 5',
                           city='Астана', living_area='Коктал 1', street_type='переулок',
                           street_name='Абая', house='12/1', apartment='5')

    def test_residential_only_is_not_house(self):
        self.assert_fields('жм Коктал1', living_area='Коктал 1', house=None, street_name=None)

    def test_multiword_and_kazakh_name(self):
        self.assert_fields('жилой массив Юго Восток, ул Абая дом 1',
                           living_area='Юго Восток', street_name='Абая', house='1')
        self.assert_fields('тұрғын алап Көктал1, переулок Қараөткел дм1',
                           living_area='Көктал 1', street_name='Қараөткел', house='1')
        self.assertEqual(split_glued('Сәуле1'), 'Сәуле 1')

    def test_missing_letters_in_markers(self):
        for marker in ('преулок', 'переулк', 'переуло', 'ПРЕУЛОК'):
            with self.subTest(marker=marker):
                self.assert_fields(f'{marker} Абая дм1', street_type='переулок',
                                   street_name='Абая', house='1')
        self.assert_fields('проспкт Абая дм 12 квартра 5', street_type='проспект',
                           street_name='Абая', house='12', apartment='5')
        self.assert_fields('Абая дом 4 подъзд 2', street_name='Абая', house='4', entrance='2')

    def test_names_and_raw_are_not_corrected(self):
        self.assert_fields('ул Преулковая дом 4', street_name='Преулковая', house='4')
        self.assert_fields('ул Абаа дом 4', street_name='Абаа', house='4')
        raw = '  ЖМ Коктал1 ПРЕУЛОК xxx дм1\u200b  '
        result = parse_one({'id': 'unchanged', 'raw_address': raw})
        self.assertEqual(result['raw_address'], raw)
        self.assertEqual(result['id'], 'unchanged')
        self.assertEqual(result['living_area'], 'Коктал 1')

    def test_mixed_inline_address_and_conflicting_geography(self):
        raw = 'жм пуси улица гарова астана алматинская область район сарыаркинский 3дом кварт4 подьедз5 эт4 под магазином алена'
        self.assert_fields(raw, living_area='пуси', street_type='улица', street_name='гарова',
                           city='астана', province='Алматинская область', district='сарыаркинский',
                           house='3', apartment='4', entrance='5', floor='4', landmark='под магазином алена')
        result = parse_one({'id': 23, 'raw_address': raw})
        self.assertEqual(result['raw_address'], raw)
        self.assertLess(result['confidence'], 0.6)

    def test_glued_field_bindings_do_not_steal_neighbouring_numbers(self):
        self.assert_fields('ул Абая 3дом кварт4 подьедз5 эт4', house='3', apartment='4', entrance='5', floor='4')
        self.assert_fields('66квартал 12дом 69квартира', street_type='квартал', street_name='66', house='12', apartment='69')
        self.assert_fields('ул Абая дом12а/1 кварт4 подъезд5 эт4', house='12а/1', apartment='4', entrance='5', floor='4')
        self.assert_fields('ул Абая дом 3 кв 4 подъезд 5 этаж 4', house='3', apartment='4', entrance='5', floor='4')

    def test_landmark_preposition_is_not_an_entrance(self):
        self.assert_fields('Абая дом 3 этаж 4 под магазином алена', house='3', floor='4', entrance=None, landmark='под магазином алена')
        self.assert_fields('Абая 3 магазин Береке 4подъезд 9этаж', house='3', entrance='4', floor='9', landmark='магазин Береке')

    def test_inline_geography_does_not_consume_city_named_street(self):
        self.assert_fields('улица Астана дом1', street_name='Астана', house='1', city=None)
        self.assert_fields('Алматинская область, город Конаев, улица Абая дом1',
                           province='Алматинская область', city='Конаев', street_name='Абая', house='1')

    def test_error_page_results_match_the_parser(self):
        fixtures = json.loads((Path(__file__).parent / 'app/static/errors-log.json').read_text(encoding='utf-8-sig'))
        for fixture in fixtures:
            with self.subTest(example=fixture['example']):
                self.assert_fields(fixture['example'], **fixture['expected'])


if __name__ == '__main__':
    unittest.main()
