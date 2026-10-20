#!/usr/bin/env python3
"""SFU undergraduate tuition scraper.
# MARKER: sfuTuitionV1

The admission page he provided (students/admission/fees-scholarships.html)
only publishes a bundled "tuition and fees" estimate, so the rates come
from the source it links to -- the Academic Calendar fee schedule:
  https://www.sfu.ca/students/calendar/fees-and-regulations/tuition-fees/undergraduate.html
(Fall 2026 calendar -> 2026/27 rates.)

SFU charges per unit. TUITION ONLY: supplementary fees (student services,
activity fee, transit pass, co-op fees) are excluded.
  - Basic rate: most programs.
  - Premium rates (200/300/400-division courses only): Beedie School of
    Business; Engineering Science / Mechatronic Systems / Sustainable
    Energy Engineering; Computing Science. 100-division courses are
    billed at the basic rate.
  - International rates depend on entry cohort; the newest cohort
    ("entered in 2024/2025 or later") is used -- the rate a new student pays.

Annual figure = per-unit rate x 30 units.
BC has one domestic rate (no in/out-of-province split).

Output: output/sfu_tuition.json
Requires: beautifulsoup4
"""
import json
import re
import urllib.request
from pathlib import Path

URL = ("https://www.sfu.ca/students/calendar/fees-and-regulations/"
       "tuition-fees/undergraduate.html")
ACADEMIC_YEAR = "2026-2027"
UNITS_PER_YEAR = 30
NEWEST_COHORT = "2024/2025 or later"

GROUPS = [
    ("basic", "Normal and Course Challenge",
     "All Other Undergraduate Programs"),
    ("business", "Beedie School of Business",
     "Business (Beedie School of Business)"),
    ("engineering", "School of Engineering Science",
     "Engineering (Engineering Science, Mechatronic Systems, Sustainable Energy)"),
    ("computing", "School of Computing Science",
     "Computing Science"),
]


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def group_key(label):
    for key, marker, _ in GROUPS:
        if marker in label:
            return key
    return None


def per_unit(cell):
    m = re.search(r"\$([\d,]+\.\d{2})", cell)
    return float(m.group(1).replace(",", "")) if m else None


def parse_rates(table, cohort_filter):
    """{group_key: per-unit rate} from one fee table.

    Domestic rows are direct (label, fee) pairs. International rows have a
    group header row followed by one row per entry cohort; cohort_filter
    (substring of the cohort label) selects the row, None takes every row.
    """
    rates = {}
    current = None
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if not cells:
            continue
        if len(cells) == 1:
            current = group_key(cells[0])
            continue
        label, fee_cell = cells[0], cells[1]
        if "per unit" not in fee_cell:
            continue  # per-term fees (co-op, law, MD) are not unit tuition
        if label.lower().startswith("for students who entered"):
            if cohort_filter and cohort_filter in label:
                rates[current] = per_unit(fee_cell)
            continue
        key = group_key(label)
        if key:
            current = key
            if cohort_filter is None:
                rates[key] = per_unit(fee_cell)
    return rates


def main():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fetch(URL), "html.parser")
    tables = soup.find_all("table")
    dom = parse_rates(tables[0], cohort_filter=None)
    intl = parse_rates(tables[1], cohort_filter=NEWEST_COHORT)
    print(f"domestic rates: {dom}")
    print(f"international rates (cohort {NEWEST_COHORT}): {intl}")

    entries = []
    for key, _, display in GROUPS:
        d_rate, i_rate = dom[key], intl[key]
        comments = (
            f"Per-unit tuition x {UNITS_PER_YEAR} units: domestic ${d_rate}, "
            f"international ${i_rate} (entry cohort {NEWEST_COHORT}). "
            "Tuition only; supplementary fees excluded."
        )
        if key != "basic":
            comments += (" Premium rate applies to 200/300/400-division "
                         "courses; 100-division courses are billed at the "
                         "basic rate.")
        entries.append({
            "universityId": "sfu",
            "universityName": "SFU",
            "programId": slug(display),
            "programName": display,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": round(d_rate * UNITS_PER_YEAR, 2),
                "international": round(i_rate * UNITS_PER_YEAR, 2),
            },
            "comments": comments,
        })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "sfu_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:48]:48s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
