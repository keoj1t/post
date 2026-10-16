import os
import osmium

PBF = os.path.join("reference", "kazakhstan-latest.osm.pbf")
OUT = os.path.join("reference", "districts_report.txt")

WANTED = [
    "ауэзов", "бостандык", "алмалин", "медеу", "турксиб", "жетысу", "жетісу",
    "наурызбай", "алатау",                     # Алматы
    "есиль", "есіл", "сарыарка", "сарыарқа", "байконур", "байқоңыр",
    "нура", "нұра", "алматы р",                # Астана
    "аль-фараби", "әл-фараби", "абай р", "енбекши", "еңбекші", "каратау", "қаратау",  # Шымкент
]


class Find(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rels = []
        self.aksai = []

    def relation(self, r):
        if r.tags.get("boundary") != "administrative":
            return
        name = r.tags.get("name", "")
        name_ru = r.tags.get("name:ru", "")
        low = (name + " " + name_ru).lower()
        if any(w in low for w in WANTED):
            self.rels.append((r.tags.get("admin_level", "?"), name, name_ru, r.id))

    def node(self, n):
        name = n.tags.get("name", "")
        if n.tags.get("place") and "аксай" in name.lower():
            self.aksai.append((n.tags.get("place"), name))


def main():
    if not os.path.exists(PBF):
        print("Не найден файл", PBF)
        return
    print("Читаю файл, подожди несколько минут...")
    h = Find()
    h.apply_file(PBF)

    lines = ["=== Найденные границы (admin_level | name | name:ru | id) ==="]
    for lvl, name, ru, rid in sorted(h.rels):
        lines.append(f"{lvl} | {name} | {ru} | {rid}")
    lines.append(f"\nВсего найдено: {len(h.rels)}")
    lines.append("\n=== Места со словом 'Аксай' (place | name) ===")
    for p, name in h.aksai[:30]:
        lines.append(f"{p} | {name}")

    text = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print("\nОтчёт сохранён в", OUT)


if __name__ == "__main__":
    main()
