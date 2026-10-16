import os
import osmium

PBF = os.path.join("reference", "kazakhstan-latest.osm.pbf")
OUT = os.path.join("reference", "osm_report.txt")

PLACES = {"suburb", "neighbourhood", "quarter", "city_block"}


class Scan(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.places = {}       
        self.streets = 0
        self.street_examples = []
        self.street_types = {}
        self.admin = {}       

    def node(self, n):
        p = n.tags.get("place")
        name = n.tags.get("name")
        if p in PLACES and name:
            rec = self.places.setdefault(p, [0, []])
            rec[0] += 1
            if len(rec[1]) < 15:
                rec[1].append(name)

    def way(self, w):
        name = w.tags.get("name")
        if w.tags.get("highway") and name:
            self.streets += 1
            if len(self.street_examples) < 15:
                self.street_examples.append(name)
            first = name.split()[0].lower()
            self.street_types[first] = self.street_types.get(first, 0) + 1

    def relation(self, r):
        if r.tags.get("boundary") == "administrative":
            lvl = r.tags.get("admin_level", "?")
            name = r.tags.get("name")
            if name:
                rec = self.admin.setdefault(lvl, [0, []])
                rec[0] += 1
                if len(rec[1]) < 20:
                    rec[1].append(name)


def main():
    if not os.path.exists(PBF):
        print("Не найден файл", PBF)
        return
    print("Читаю файл, подожди несколько минут...")
    h = Scan()
    h.apply_file(PBF)

    lines = []
    lines.append("=== Жилые массивы/районы (place=...) ===")
    for k, (cnt, ex) in h.places.items():
        lines.append(f"{k}: {cnt} шт. Примеры: {ex}")
    lines.append("\n=== Административные границы по уровням ===")
    for lvl in sorted(h.admin):
        cnt, ex = h.admin[lvl]
        lines.append(f"admin_level={lvl}: {cnt} шт. Примеры: {ex}")
    lines.append(f"\n=== Улицы с названием: {h.streets} ===")
    lines.append(f"Примеры: {h.street_examples}")
    top = sorted(h.street_types.items(), key=lambda x: -x[1])[:25]
    lines.append(f"Самые частые первые слова названий: {top}")

    text = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print("\nОтчёт сохранён в", OUT)


if __name__ == "__main__":
    main()
