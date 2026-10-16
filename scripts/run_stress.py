"""Прогон адресов через парсер.
  python scripts/run_stress.py data/stress.txt
Результат печатается и сохраняется в data/stress_out.txt (его можно прислать целиком).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.parser import parse_address
FIELDS = ["province", "city", "district", "living_area", "street_type", "street_name",
          "house", "apartment", "entrance", "floor", "landmark"]
src = sys.argv[1] if len(sys.argv) > 1 else "data/stress.txt"
lines = [l.strip() for l in open(src, encoding="utf-8") if l.strip()]
out = []
for i, raw in enumerate(lines, 1):
    try:
        r = parse_address(raw)
        got = " | ".join(f"{f}={r[f]}" for f in FIELDS if r.get(f))
        out.append(f"{i}. {raw}\n   -> {got}   [conf {r['confidence']}]")
    except Exception as e:
        out.append(f"{i}. {raw}\n   -> ОШИБКА: {type(e).__name__}: {e}")
text = "\n".join(out)
print(text)
open(os.path.join(os.path.dirname(src) or ".", "stress_out.txt"), "w", encoding="utf-8").write(text)