#!/usr/bin/env python3
"""Wilfrid Laurier University 2026-2027 undergraduate tuition scraper.
# MARKER: laurierTuitionV1

Source: https://students.wlu.ca/finances/tuition-and-fees/fees-breakdown/tuition-fees.html
Laurier publishes PER-CREDIT fees. Full-time annual = per-0.5-credit x 10
(5.0 credits/year). Domestic tables split Ontario / Non-Ontario; some split
further by entering-year cohort -- we use the 2023/24-to-2026/27 (new student)
column.

Tables used (0-indexed into page tables):
  dom 0: Non-Business            -> per 0.5: ont $693.00 / oop $749.00
  dom 1: Business                -> 2023/24+ col: ont $1,184.00 / oop $1,235.40
  dom 3: CS and Data Science     -> 2023/24+ col: ont $961.00 / oop $961.00
  dom 4: Bachelor of Education   -> per 0.5: ont $821.00 / oop $887.00
  dom 7: Bachelor of Design      -> per 0.5: ont $722.00 / oop $781.00
  intl 16: All Programs (excl Business) -> per 0.5: $3,662.00
  intl 17: All Business Programs -> 2023/24+ col: $4,433.20
  intl 18: BA Economics         -> 2023/24+ col: $3,911.20
  intl 19: Bachelor of Education -> 2020/21+ col: $3,662.00
  intl 22: Bachelor of Computer/Data Science -> 2022/23+ col: $3,947.00

Usage:
    python laurier_tuition.py scrape      # fetch page -> output/laurier_raw.json
    python laurier_tuition.py summarize   # raw -> output/laurier_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
URL = "https://students.wlu.ca/finances/tuition-and-fees/fees-breakdown/tuition-fees.html"

# (programId, programName, dom_table, dom_ont_col, dom_oop_col, intl_table, intl_col)
# Columns are 0-indexed into the data row's cells (after the credit label).
# For cohort-split tables, columns refer to the 2023/24-to-2026/27 entering cohort.
PROGRAMS = [
    ("non-business", "Non-Business (Arts & Science)",
     0, 0, 1, 16, 0),
    ("business", "Business (BBA)",
     1, 1, 3, 17, 4),
    ("cs-data-science", "Computer Science and Data Science",
     3, 1, 3, 22, 3),
    ("economics", "Bachelor of Arts - Economics",
     0, 0, 1, 18, 1),   # domestic = non-business rate
    ("education", "Bachelor of Education",
     4, 0, 1, 19, 1),
    ("design", "Bachelor of Design",
     7, 0, 1, None, None),  # no intl figure published
]


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def money(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{2})?)", cell or "")
    return float(m.group(1).replace(",", "")) if m else None


def get_tables(doc):
    tables = []
    for t in re.findall(r"<table.*?</table>", doc, re.S | re.I):
        rows = []
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I):
            cells = [re.sub(r"<[^>]+>", " ", x).strip()
                     for x in re.split(r"</t[dh][^>]*>", r)]
            cells = [H.unescape(x).replace("\xa0", " ").strip()
                     for x in cells if x.strip()]
            if cells:
                rows.append(cells)
        tables.append(rows)
    return tables


def per_half_credit(rows):
    """Find the per-0.5-credit data row, return its value cells."""
    for r in rows:
        if re.search(r"0\.50|per 0\.5", r[0], re.I):
            return r[1:]
    return None


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    tables = get_tables(fetch())
    print(f"{len(tables)} tables found")
    data = {}
    for pid, pname, dt, doc_ont, doc_oop, it, icol in PROGRAMS:
        entry = {"program": pname}
        drow = per_half_credit(tables[dt])
        assert drow, f"no per-credit row in table {dt}"
        entry["ont_per05"] = money(drow[doc_ont])
        entry["oop_per05"] = money(drow[doc_oop])
        assert entry["ont_per05"] and entry["oop_per05"], f"parse fail table {dt}: {drow}"
        if it is not None:
            irow = per_half_credit(tables[it])
            assert irow, f"no per-credit row in table {it}"
            entry["intl_per05"] = money(irow[icol])
            assert entry["intl_per05"], f"parse fail table {it}: {irow}"
        data[pid] = entry
        print(f"  {pid}: ont={entry['ont_per05']} oop={entry['oop_per05']} "
              f"intl={entry.get('intl_per05')}")
    p = OUT_DIR / "laurier_raw.json"
    p.write_text(json.dumps({"url": URL, "programs": data}, indent=1))
    print(f"wrote {p}")


def summarize():
    p = OUT_DIR / "laurier_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    data = json.loads(p.read_text())["programs"]
    entries = []
    for pid, pname, *_ in PROGRAMS:
        d = data[pid]
        # annual = per-0.5-credit x 10 (5.0 credits = full-time year)
        tuition = {
            "domestic-in-province": round(d["ont_per05"] * 10, 2),
            "domestic-out-of-province": round(d["oop_per05"] * 10, 2),
        }
        note = ""
        if d.get("intl_per05"):
            tuition["international"] = round(d["intl_per05"] * 10, 2)
        else:
            note = "No international figure published. "
        if pid == "economics":
            note += "Domestic rate = Laurier's Non-Business rate. "
        entries.append({
            "universityId": "laurier",
            "universityName": "Wilfrid Laurier University",
            "programId": pid,
            "programName": pname,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                note +
                "Laurier publishes per-credit fees; annual = per-0.5-credit x 10 "
                "(5.0 credits = full-time year). Domestic uses the 2023/24+ "
                "entering cohort column where cohorts are split. "
                "Source: students.wlu.ca tuition-fees.",
        })
    out = OUT_DIR / "laurier_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")
    for e in entries:
        print(e["programId"], e["tuition"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: laurier_tuition.py scrape | summarize")

