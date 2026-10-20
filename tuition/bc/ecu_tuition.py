#!/usr/bin/env python3
"""Emily Carr University (ECU) undergraduate tuition scraper.
# MARKER: ecuTuitionV1

Source: https://ecuad.ca/tuition-fees-undergrad/
The page carries per-term tables by credit load for two terms:
"Summer 2026" and "Fall 2026 + Spring 2027". The Fall/Spring group is
the academic year -> academicYear 2026-2027.

ECU charges one rate for all undergraduate programs. The tables'
"Tuition + Related Fees" column is used (ECU publishes tuition bundled
with its related course fees); the separate "Other Mandatory Fees"
column (UPass etc.) is excluded. The legacy international table
(2022/2023 cohort and earlier) is skipped -- new students pay the
current international rate.

Annual figure = the 15-credit row x 2 terms (= 30 credits).

Output: output/ecu_tuition.json
Requires: beautifulsoup4, curl_cffi
"""
import json
import re
import time
from pathlib import Path

URL = "https://ecuad.ca/tuition-fees-undergrad/"
ACADEMIC_YEAR = "2026-2027"
TERM_LABEL = "Fall 2026 + Spring 2027"
FULL_TERM_CREDITS = "15"


def fetch(url):
    from curl_cffi import requests
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, impersonate="chrome120", timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{1,2})?)", cell.replace(" ", ""))
    return float(m.group(1).replace(",", "")) if m else None


def tagged_tables(soup):
    """Yield (term_label, kind, table) walking the page in order."""
    term, kind = None, None
    for el in soup.find_all(True):
        if el.name == "table":
            yield term, kind, el
        elif el.name in ("h2", "h3", "h4", "p", "strong", "summary"):
            text = el.get_text(" ", strip=True)
            if TERM_LABEL in text:
                term = TERM_LABEL
            elif "Summer 2026" in text:
                term = "Summer 2026"
            if el.name == "h3":
                if "Domestic Tuition" in text:
                    kind = "domestic"
                elif "International Tuition" in text:
                    kind = ("legacy" if "Earlier" in text else "international")


def annual_from(table):
    """15-credit per-term 'Tuition + Related Fees' x 2 terms."""
    rows = [[re.sub(r"\s+", " ", c.get_text(" ", strip=True))
             for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
    col = next(i for i, h in enumerate(rows[0])
               if "Tuition + Related Fees" in h)
    for row in rows[1:]:
        if row and row[0] == FULL_TERM_CREDITS:
            return money(row[col]) * 2
    raise RuntimeError("15-credit row not found")


def main():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fetch(URL), "html.parser")
    tables = {}
    for term, kind, table in tagged_tables(soup):
        if term == TERM_LABEL and kind in ("domestic", "international"):
            tables[kind] = table
    dom = annual_from(tables["domestic"])
    intl = annual_from(tables["international"])
    print(f"{TERM_LABEL}: domestic annual={dom}, international annual={intl}")

    entries = [{
        "universityId": "emily-carr",
        "universityName": "Emily Carr (ECU)",
        "programId": slug("All Undergraduate Programs"),
        "programName": "All Undergraduate Programs",
        "academicYear": ACADEMIC_YEAR,
        "tuition": {
            "domestic-in-province": round(dom, 2),
            "international": round(intl, 2),
        },
        "comments": "One rate for all ECU undergraduate programs. "
                    "15 credits/term x 2 terms (30 credits) at the "
                    "'Tuition + Related Fees' column; the separate 'Other "
                    "Mandatory Fees' (UPass etc.) are excluded. "
                    "Fall 2026 + Spring 2027 tables.",
    }]

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "ecu_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:42]:42s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
