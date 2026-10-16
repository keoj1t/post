import csv, sys
R = {r['id']: r for r in csv.DictReader(
    open('reference/kato_ru.csv', encoding='utf-8-sig'), delimiter=';')}
i = sys.argv[1]
while i in R:
    print(R[i]['code'], R[i]['name'])
    i = R[i]['parent_id']