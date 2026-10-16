import json, random
data = json.load(open("data/train.json", encoding="utf-8"))
random.seed(1)
for r in random.sample(data, 80):
    print(r)