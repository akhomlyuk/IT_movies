#!/usr/bin/env python3

import re

from lib import ROOT, load_catalog

RAW = (ROOT / "js" / "data.js").read_text(encoding="utf-8")
CATALOG = load_catalog()

# Line numbers where each record's "type" is declared (order = array order)
type_lines = [RAW.count("\n", 0, m.start()) + 1 for m in re.finditer(r'"type":\s*"\w+"', RAW)]
if len(type_lines) != len(CATALOG):
    raise SystemExit(f"Строк с типом {len(type_lines)}, а записей {len(CATALOG)}")

records = [(ln, item["titleEn"], item["type"]) for ln, item in zip(type_lines, CATALOG)]

width = max(len(t) for _, t, _ in records)
for line, title, kind in records:
    print(f"{line}: {title.ljust(width)}  [{kind}]")