#!/usr/bin/env python3

import json
import re
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "js" / "data.js"
RAW = PATH.read_text(encoding="utf-8")
CATALOG = json.loads(RAW[RAW.index("[") : RAW.rindex("]") + 1])

# Номера строк, на которых объявлен "type" каждой записи (порядок = порядку массива)
type_lines = [RAW.count("\n", 0, m.start()) + 1 for m in re.finditer(r'"type":\s*"\w+"', RAW)]
if len(type_lines) != len(CATALOG):
    raise SystemExit(f"Строк с типом {len(type_lines)}, а записей {len(CATALOG)}")

records = [(ln, item["titleEn"], item["type"]) for ln, item in zip(type_lines, CATALOG)]

width = max(len(t) for _, t, _ in records)
for line, title, kind in records:
    print(f"{line}: {title.ljust(width)}  [{kind}]")
