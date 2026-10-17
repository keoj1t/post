import itertools
import unittest
import json
from pathlib import Path
from app.main import parse_one
from app.parser import parse_address


class AddressGrammarTest(unittest.TestCase):
    parsed_cases=0
    def check(self,raw,expected):
        type(self).parsed_cases+=1
        row=parse_one({'id':'raw-preserved','raw_address':raw})
        self.assertEqual(row['raw_address'],raw)
        for key,value in expected.items():self.assertEqual(row[key],value,(raw,key,row))
        return row

    def test_permutations_compact_and_spaced_bilingual(self):
        expected={'house':'12','apartment':'3','entrance':'2','floor':'4','building':'7','street_name':'Абай','city':'Алматы'}
        for words in [('дом','квартира','подъезд','этаж','корпус'),('үй','пәтер','кіреберіс','қабат','корпусы')]:
            for permutation in itertools.permutations(zip(words,('12','3','2','4','7'))):
                for suffix in (False,True):
                    for separator in ('',' ',', ','; ','\t','\n'):
                        chunks=[number+word if suffix else word+number for word,number in permutation]
                        raw=separator.join(chunks)+' , Абай көшесі, Алматы қаласы'
                        with self.subTest(raw=raw):self.check(raw,expected)

    def test_mixed_directions_with_explicit_boundaries(self):
        for directions in itertools.product((False,True),repeat=4):
            chunks=[num+word if suffix else word+num for word,num,suffix in zip(('дом','квартира','подъезд','этаж'),('12','3','2','4'),directions)]
            self.check(' '.join(chunks)+', улица Абая, город Алматы',{'house':'12','apartment':'3','entrance':'2','floor':'4'})

    def test_geography_after_landmark(self):
        for tail in ('город Астана Акмолинская область','Акмолинская область город Астана'):
            row=self.check('улица Абая дом12 магазин Алена '+tail,{'city':'Астана','province':'Акмолинская область','landmark':'магазин Алена','house':'12','street_name':'Абая'})
            self.assertIn('geo_conflict',[issue['code'] for issue in row['review']['issues']])
        self.check('Абай көшесі 12 үй дүкен Алена Алматы қаласы',{'city':'Алматы','street_name':'Абай','landmark':'дүкен Алена','house':'12'})

    def test_postal_formats_and_leading_zero(self):
        for postal in ('010000','050000','Z11C9H6'):
            for raw in (f'{postal}, Алматы қаласы, Абай көшесі, үй12',f'ул Абая дом12, Алматы қаласы, индекс {postal}',f'ул Абая дом12, Алматы қаласы, {postal} индекс'):
                self.check(raw,{'postal_code':postal,'house':'12','city':'Алматы'})
        self.check('индекс12345, Алматы, Абая дом1',{'postal_code':'12345','house':'1'})
        self.assertIn('invalid_postal',[i['code'] for i in parse_address('индекс12345, Алматы, Абая дом1')['review']['issues']])
        self.check('Алматы, Абая дом123456',{'postal_code':None,'house':'123456'})
        for label in ('zip code','ZIPCODE','postal code','пошталық индекс'):
            self.check(f'{label} 050000, Алматы қаласы, Абай көшесі, 12 үй',{'postal_code':'050000','house':'12'})

    def test_ambiguous_input_is_not_silently_guessed(self):
        row=self.check('дом1квартира3подьезд2улицабая42переулоклалаа',{'house':'1','apartment':'3','entrance':'2','street_type':'улица'})
        codes={issue['code'] for issue in row['review']['issues']}
        self.assertTrue({'multiple_streets','marker_name_overlap','unassigned_numbers'}<=codes,codes)
        self.assertTrue(row['review']['needs_review'])
        self.assertLess(row['confidence'],.6)
        overlap=next(issue for issue in row['review']['issues'] if issue['code']=='marker_name_overlap')
        self.assertIn('абая',{candidate['changes']['street_name'] for candidate in overlap['candidates']})

    def test_conflicting_numbers_offer_candidates(self):
        row=parse_address('Алматы, ул Абая дом12 дом14 кв3')
        issue=next(i for i in row['review']['issues'] if i['code']=='conflicting_house')
        self.assertEqual({candidate['changes']['house'] for candidate in issue['candidates']},{'12','14'})

    def test_multiword_kazakh_street_and_province(self):
        self.check('015937, Ақтөбе облысы, Ақтау қаласы, Бұқар жырау даңғылы, 776',{'postal_code':'015937','province':'Актюбинская область','city':'Ақтау','street_type':'проспект','street_name':'Бұқар жырау','house':'776'})

    def test_sourced_examples_and_line_permutations(self):
        samples=json.loads((Path(__file__).parent/'data/generated_address_cases.json').read_text(encoding='utf-8'))['samples']
        expected=[{'house':'42','city':'Pavlodar','street_name':'Akademika Satpaeva'},
                  {'house':'2','apartment':'18','city':'Almaty','street_name':'saina'},
                  {'house':'95','apartment':'5','city':'Pavlodar','street_name':'Kataeva'},
                  {'house':'82/1','apartment':'45','city':'Pavlodar','street_name':'Kamzina'},
                  {'house':'776','city':'Ақтау','postal_code':'015937'},
                  {'house':'110','city':'Ақтөбе','province':'Орал облысы','postal_code':'062668'}]
        self.assertEqual(len(samples),26)
        for sample,fields in zip(samples[:6],expected):
            self.check(sample['raw_address'],fields)
            if '\n' in sample['raw_address']:
                for lines in itertools.permutations(sample['raw_address'].splitlines()):
                    self.check(', '.join(lines),fields)
        for sample in samples[6:]:
            postal,province,city,street,house=[part.strip() for part in sample['raw_address'].split(',')]
            name,kind=street.rsplit(' ',1)
            fields={'postal_code':postal,'city':city.removesuffix(' қаласы'),'street_name':name,'house':house,'street_type':'улица' if kind=='көшесі' else 'проспект'}
            row=self.check(sample['raw_address'],fields)
            self.assertTrue(row['review']['needs_review'])
            self.assertTrue(any(issue['code'] in {'geo_conflict','unknown_province','invalid_province_kind'} for issue in row['review']['issues']))
            # Меняем порядок крупных частей синтетического адреса, без привязки к имени.
            for parts in ((street,house,city,province,postal),(postal,street,house,province,city),(city,province,street,house,postal)):
                self.check(', '.join(parts),fields)

    def test_case_spacing_and_service_symbols(self):
        for symbol in ('№','#',':','='):
            for marker in ('дом','үй','bld'):
                self.check(f'Алматы, ул Абая, {marker}{symbol}12, квартира3',{'house':'12','apartment':'3','city':'Алматы'})
        for marker in ('подъзд','подъедз','подъеззд','кіребеіс','кіреберріс'):
            self.check(f'Алматы, Абай көшесі, дом12, {marker}2',{'house':'12','entrance':'2'})
        self.check('Алматы, Абая дом12а/1 кв3\u200b эт4',{'house':'12а/1','apartment':'3','floor':'4'})

    def test_building_structure_and_compound_numbers(self):
        for house in ('12к2','дом12-к2','12k2'):
            self.check('Алматы, ул Абая '+house,{'house':'12','building':'2'})
        self.check('Алматы, ул Абая 12с1',{'house':'12','structure':'1'})
        self.check('Алматы, дом12корпус2строение1 улицаАбая',{'house':'12','building':'2','structure':'1','street_name':'Абая'})

    def test_unknown_geo_offers_dictionary_candidates_without_rewriting(self):
        row=self.check('город Алматыы, ул Абая дом12',{'city':'Алматыы','house':'12'})
        issue=next(issue for issue in row['review']['issues'] if issue['code']=='unknown_city')
        self.assertIn('Алматы',{choice['changes']['city'] for choice in issue['candidates']})
        self.assertTrue(row['review']['needs_review'])

    def test_explicit_village_kind_is_preserved(self):
        row=self.check('Қарасу ауылы, Абай көшесі, 12 үй',{'city':'Қарасу','street_name':'Абай','house':'12'})
        self.assertEqual(row['review']['locality_kind'],'village')

    def test_new_region_names_from_local_kato(self):
        for region,city in [('Абай','Семей'),('Жетісу','Талдықорған'),('Ұлытау','Жезқазған')]:
            for text in (f'{region} облысы, {city} қаласы',f'{city} қаласы, облыс {region}'):
                self.check('Абай көшесі, 12 үй, '+text,{'province':region+' область','city':city,'street_name':'Абай','house':'12'})

    def test_conflicting_postal_codes_are_explained(self):
        row=self.check('индекс 010000 индекс 050000, Алматы, Абая дом12',{'postal_code':'010000','house':'12'})
        issue=next(issue for issue in row['review']['issues'] if issue['code']=='conflicting_postal')
        self.assertEqual({candidate['changes']['postal_code'] for candidate in issue['candidates']},{'010000','050000'})

    def test_compact_city_region_and_dictionary_street(self):
        for region in ('акмолинская', 'акмол'):
            row=self.check(f'мангиликел42астана{region}областьдом2кв43', {
                'province':'Акмолинская область','city':'астана',
                'street_name':'мангилик ел','street_type':'проспект','house':'2','apartment':'43'})
            self.assertIn('unassigned_numbers', [issue['code'] for issue in row['review']['issues']])

    def test_all_compact_regions(self):
        import re
        from app.geo import ROWS, depth_of, strip_markers, prov_display
        for item, (_, name) in ROWS.items():
            if depth_of(item) != 0 or 'область' not in name.lower():
                continue
            stem=re.sub(r'[\s.-]+', '', strip_markers(name).lower())
            for raw in (f'Абая дом2 {stem}область', f'Абая дом2 астана{stem}область'):
                self.check(raw, {'province':prov_display(item),'house':'2'})

    def test_spaced_digits_belong_to_marked_field(self):
        for marker in ('квартира', 'кв', 'пәтер', 'flat'):
            for number in ('9 8', '9\t8', '0 9 8'):
                expected=number.replace(' ', '').replace('\t', '')
                row=self.check(f'Караганда, Абая, дом12 {marker} {number}',
                               {'apartment':expected,'house':'12','province':'Карагандинская область'})
                self.assertNotIn('unassigned_numbers', [issue['code'] for issue in row['review']['issues']])
        self.check('квартира 9 8', {'apartment':'98','house':None})
        self.check('дом 12 квартира 9, 8 этаж', {'house':'12','apartment':'9','floor':'8'})
        self.check('дом 12 квартира 9 80', {'house':'12','apartment':'9'})

    def test_kato_automatically_fills_region_and_parent_district(self):
        for prefix in ('', 'город '):
            self.check(prefix+'Каскелен, улица Абая, дом12',
                       {'city':'Каскелен','province':'Алматинская область','district':'Карасайский'})
        self.check('Караганда, Абая дом12', {'province':'Карагандинская область'})
        self.check('Астана, неизвестнаяулица дом12', {'province':'Астана','district':None})
        self.check('город Каскелен, Акмолинская область, Абая дом12', {'province':'Акмолинская область'})

    def test_bare_district_names_and_adjectives_use_kato_city(self):
        for text in ('сарыаркинский астана мангликел87',
                     'астана мангликел87 сарыаркинский',
                     'сарыарка астана мангликел87'):
            self.check(text, {'district':'Сарыарка','city':'астана','province':'Астана','house':'87','street_name':'мангликел'})
        self.check('Есильский Астана Абая дом12', {'district':'Есиль','city':'Астана'})
        self.check('Астана улица Сарыаркинский дом12', {'street_name':'Сарыаркинский','house':'12'})
        row=self.check('Астана неизвестнаяулица дом12 возле Сарыарка', {'landmark':'возле Сарыарка'})
        self.assertIsNone(row['district'])

    @classmethod
    def tearDownClass(cls):
        print(f'Grammar: {cls.parsed_cases} generated and sourced address variants checked.')

if __name__=='__main__':unittest.main()
