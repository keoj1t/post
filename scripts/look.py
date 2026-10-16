import json
data = json.load(open("data/train.json", encoding="utf-8"))
print("Записей:", len(data))
print("Ключи первой записи:", list(data[0].keys()))
for r in data[:20]:
    print(r)