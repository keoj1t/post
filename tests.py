from app.parser import parse_address

CASES = [
    ("город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70",
     {"street_type": "микрорайон", "street_name": "Аксай 3а", "house": "59", "apartment": "70"}),
    ("66квартал 12дом 69квартира",
     {"street_type": "квартал", "street_name": "66", "house": "12", "apartment": "69"}),
    ("Ул .Курильская 9 кв 1",
     {"street_type": "улица", "street_name": "Курильская", "house": "9", "apartment": "1"}),
    ("Туран 55/6 магазин береке 4подьезд 9этаж",
     {"street_name": "Туран", "house": "55/6", "entrance": "4", "floor": "9",
      "landmark": "магазин береке"}),
    ("Нурсити 2 микрорайон 11дом 5 подьезд 239 кв",
     {"street_type": "микрорайон", "street_name": "2", "living_area": "Нурсити",
      "house": "11", "entrance": "5", "apartment": "239"}),
    ("Кулманова 133", {"street_name": "Кулманова", "house": "133"}),
    ("жуалы 19", {"street_name": "жуалы", "house": "19"}),
    ("Назарбаева8 кв 12", {"street_name": "Назарбаева", "house": "8", "apartment": "12"}),
    ("Турксибский район, Рыбинский переулок, дом 4",
     {"street_type": "переулок", "street_name": "Рыбинский", "house": "4"}),
         ("город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70",
     {"province": "Алматы", "city": "Алматы"}),
    ("Актюбинская область, город Актобе/Ақтөбе қаласы, Курильская 9 кв 1",
     {"province": "Актюбинская область", "city": "Актобе", "street_name": "Курильская"}),
    ("Турксибский район, Рыбинский переулок, дом 4",
     {"district": "Турксибский", "street_name": "Рыбинский"}),
]

ok = 0
for raw, expected in CASES:
    got = parse_address(raw)
    bad = {k: (v, got.get(k)) for k, v in expected.items()
           if (got.get(k) or "").lower() != v.lower()}
    if bad:
        print("FAIL:", raw)
        for k, (want, have) in bad.items():
            print(f"   {k}: ждали {want!r}, получили {have!r}")
    else:
        ok += 1
print(f"\nПройдено {ok} из {len(CASES)}")