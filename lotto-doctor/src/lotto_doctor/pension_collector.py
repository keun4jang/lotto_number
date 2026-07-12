"""Pension Lottery 720+ data collector.

Since dhlottery.co.kr blocks automated access, data is loaded from CSV.

CSV format (download from https://dhlottery.co.kr):
  회차,추첨일,조,번호
  300,2021-03-06,3,123456
  ...

Alternatively: tab-separated or semicolon-separated formats are auto-detected.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from pathlib import Path
from typing import Optional

from .pension_models import PensionDraw


def parse_pension_csv(text: str) -> list[PensionDraw]:
    """Parse pension lottery CSV text into PensionDraw objects."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return []

    # Auto-detect delimiter
    sample = lines[0]
    delimiter = ","
    for d in [",", "\t", ";"]:
        if d in sample:
            delimiter = d
            break

    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)

    def _norm(k: str) -> str:
        return k.strip().lower().replace(" ", "").replace("_", "")

    draws = []
    for row in reader:
        norm = {_norm(k): v.strip() for k, v in row.items() if v}

        draw_no_key = next((k for k in norm if "회차" in k or "drawno" in k or "no" == k), None)
        if draw_no_key is None:
            draw_no_key = list(norm.keys())[0]
        draw_no = int(re.sub(r"[^\d]", "", norm[draw_no_key]))

        date_key = next((k for k in norm if "날짜" in k or "일" in k or "date" in k), None)
        draw_date = date.today()
        if date_key and date_key in norm:
            raw = norm[date_key]
            m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", raw)
            if m:
                draw_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

        jo_key = next((k for k in norm if "조" in k or "jo" in k or "group" in k), None)
        jo = 1
        if jo_key and jo_key in norm:
            jo = int(re.sub(r"[^\d]", "", norm[jo_key]) or "1")

        num_key = next((k for k in norm if "번호" in k or "number" in k or "num" in k), None)
        number = "000000"
        if num_key and num_key in norm:
            raw = re.sub(r"[^\d]", "", norm[num_key])
            number = raw.zfill(6)[:6]

        draws.append(PensionDraw(draw_no=draw_no, draw_date=draw_date, jo=jo, number=number))

    return sorted(draws, key=lambda d: d.draw_no)


def load_pension_csv(path: str) -> list[PensionDraw]:
    """Load pension lottery data from a CSV file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    text = p.read_text(encoding="utf-8-sig")  # handle BOM
    return parse_pension_csv(text)


def generate_sample_csv(out_path: str = "data/pension_sample.csv") -> None:
    """Create a sample CSV template for the user to fill in."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    content = """회차,추첨일,조,번호
1,2011-07-30,3,123456
2,2011-08-06,1,234567
3,2011-08-13,5,345678
"""
    Path(out_path).write_text(content, encoding="utf-8")
