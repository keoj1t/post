import json
import re
import sys
import difflib

GROUPS = {
    "Адрес (область, город, улица, дом)": (
        0.60, ["province", "city", "street_type", "street_name", "house"]),
    "Квартира, подъезд, этаж": (
        0.25, ["apartment", "entrance", "floor"]),
    "Район, жилой массив": (
        0.15, ["district", "living_area"]),
}
EXTRA_FIELDS = ["landmark"]


def norm(v):
    if v is None:
        return None
    s = str(v).lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    return data


def run_parser(gold):
    from app.parser import parse_address
    preds = []
    for r in gold:
        try:
            p = parse_address(r["raw_address"])
        except Exception as e:  
            print("ОШИБКА парсера на:", r["raw_address"], e)
            p = {}
        p = dict(p)
        p["id"] = r.get("id")
        p["raw_address"] = r["raw_address"]
        preds.append(p)
    return preds


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "-v" in sys.argv
    if not args:
        print(__doc__)
        return
    gold = load(args[0])
    if len(args) > 1:
        pred_list = load(args[1])
    else:
        pred_list = run_parser(gold)

    pred_by_id = {p.get("id"): p for p in pred_list}
    pred_by_raw = {p.get("raw_address"): p for p in pred_list}

    stats = {}   
    errors = []

    for g in gold:
        p = pred_by_id.get(g.get("id")) or pred_by_raw.get(g["raw_address"]) or {}
        all_fields = [f for _, (_, fs) in GROUPS.items() for f in fs] + EXTRA_FIELDS
        for f in all_fields:
            want = norm(g.get(f))
            if want is None:
                continue 
            have = norm(p.get(f))
            st = stats.setdefault(f, [0, 0, 0.0])
            st[1] += 1
            if have == want:
                st[0] += 1
                st[2] += 1.0
            else:
                st[2] += difflib.SequenceMatcher(None, have or "", want).ratio()
                errors.append((g["raw_address"], f, g.get(f), p.get(f)))

    print(f"\nЗаписей в эталоне: {len(gold)}\n")
    print(f"{'Поле':<14}{'Точно':>8}{'Всего':>8}{'Точность':>10}{'Похожесть':>11}")
    print("-" * 51)
    field_acc = {}
    for f, (ok, n, sim) in stats.items():
        acc = ok / n
        field_acc[f] = acc
        print(f"{f:<14}{ok:>8}{n:>8}{acc*100:>9.1f}%{sim/n*100:>10.1f}%")

    print("\nГруппы:")
    total, wsum = 0.0, 0.0
    for name, (w, fs) in GROUPS.items():
        accs = [field_acc[f] for f in fs if f in field_acc]
        if not accs:
            continue
        g_acc = sum(accs) / len(accs)
        total += w * g_acc
        wsum += w
        print(f"  {name:<40} вес {int(w*100)}%  -> {g_acc*100:.1f}%")
    if wsum:
        print(f"\nИТОГО (взвешенная точность): {total / wsum * 100:.1f}%")

    if verbose and errors:
        print(f"\nОшибки ({len(errors)}):")
        for raw, f, want, have in errors:
            print(f"- {raw}\n    {f}: ждали {want!r}, получили {have!r}")
    elif errors:
        print(f"\nОшибок: {len(errors)}. Запусти с -v, чтобы увидеть каждую.")


if __name__ == "__main__":
    main()
