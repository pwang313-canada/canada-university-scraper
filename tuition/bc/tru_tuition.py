#!/usr/bin/env python3
"""TRU (Thompson Rivers University) tuition scraper.
# MARKER: truTuitionV1

Source: https://www.tru.ca/current/enrolment-services/tuition.html
Section "Tuition and fee amounts 2026-2027" -> academicYear 2026-2027.

TRU charges per credit. TUITION ONLY -- the page's ancillary, student
union and administrative fee tables are not read.
  Domestic:  Undergraduate $165.10/cr, Career Technical $154.47/cr,
             ABE and ESAL tuition-free, Law $628.03/cr (Year 1) and
             $753.64/cr (Years 2/3).
  International: Undergraduate $875/cr, ESAL $717/cr,
             Law $1,477/cr (Year 1) and $1,772/cr (Years 2/3).
Vocational (per month) and apprenticeship (per week) rates are skipped --
they are not credit-based degree programs. Graduate table skipped.

Annual figure = per-credit rate x 30 credits.
BC has one domestic rate (no in/out-of-province split).

Output: output/tru_tuition.json
Requires: beautifulsoup4, curl_cffi
"""
import json
import re
from pathlib import Path

URL = "https://www.tru.ca/current/enrolment-services/tuition.html"
ACADEMIC_YEAR = "2026-2027"
CREDITS_PER_YEAR = 30


def fetch(url):
    # tru.ca drops chunked urllib reads (IncompleteRead) and occasionally
    # closes curl_cffi connections under repeated hits; retry a few times.
    from curl_cffi import requests
    import time
    last = None
    for attempt in range(4):
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


def table_after_label(soup, label):
    """First <table> after the element whose whole text is `label`."""
    for el in soup.find_all(True):
        if el.get_text(" ", strip=True) == label and not el.find("table"):
            return el.find_next("table")
    raise RuntimeError(f"section label not found: {label!r}")


def rows_of(table):
    out = {}
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))
                 for c in tr.find_all(["td", "th"])]
        if len(cells) >= 2:
            out[cells[0]] = cells[1]
    return out


def per_credit(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{2})?)/credit", cell)
    return float(m.group(1).replace(",", "")) if m else None


def main():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fetch(URL), "html.parser")
    dom = rows_of(table_after_label(soup, "Undergraduate Campus Tuition"))
    intl = rows_of(table_after_label(soup, "International Undergraduate Campus Tuition"))
    print(f"domestic rows: {len(dom)}, international rows: {len(intl)}")

    ug_dom = per_credit(dom["Undergraduate tuition"])
    ug_intl = per_credit(intl["Undergraduate/ABE"])
    law_dom = [float(v) for v in re.findall(
        r"\$([\d,]+(?:\.\d{2})?)/credit", dom["Law"])]
    law_intl = [float(v) for v in re.findall(
        r"\$([\d,]+(?:\.\d{2})?)/credit", intl["Law"])]

    # (programName, domestic per-credit or 0/'free', international per-credit, note)
    specs = [
        ("Undergraduate Programs", ug_dom, ug_intl, ""),
        ("Career Technical Courses", per_credit(dom["Career technical courses"]),
         ug_intl,
         " International uses TRU's standard undergraduate rate; no separate "
         "career-technical international rate is published."),
        ("University Preparation (ABE)", 0.0, ug_intl,
         " Tuition-free for domestic students (applicable fees still apply)."),
        ("English as a Second or Additional Language (ESAL)", 0.0,
         per_credit(intl["ESAL"]),
         " Tuition-free for domestic students (applicable fees still apply)."),
        ("Law (Year 1)", law_dom[0], law_intl[0], ""),
        ("Law (Years 2 and 3)", law_dom[1], law_intl[1], ""),
    ]

    entries = []
    for name, d_rate, i_rate, note in specs:
        entries.append({
            "universityId": "tru",
            "universityName": "TRU",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": round(d_rate * CREDITS_PER_YEAR, 2),
                "international": round(i_rate * CREDITS_PER_YEAR, 2),
            },
            "comments": (
                f"Per-credit tuition x {CREDITS_PER_YEAR} credits: domestic "
                f"${d_rate}/cr, international ${i_rate}/cr. Tuition only; "
                f"ancillary and student-union fees excluded.{note}"
            ),
        })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "tru_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:48]:48s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
