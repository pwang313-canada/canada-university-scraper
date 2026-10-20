#!/usr/bin/env python3
"""VIU (Vancouver Island University) tuition scraper.
# MARKER: viuTuitionV1

Source: https://www.viu.ca/admissions/tuition-fee-schedule

VIU charges per credit. TUITION ONLY -- lab fees, supply fees, co-op
semester fees and students' union fees on the page are not read.
  Base rates: domestic credit-based undergraduate $173.12/credit;
  international Undergraduate Degree/Diploma/Certificate $832.09/credit.
  Differential domestic per-credit rates (page's differential table):
  Bachelor of Social Work $471.06, Dental Hygiene $260.02, Practical
  Nursing $230.90, Advanced Diploma in GIS $376.24 (its international
  rate, $655.45, is published; the other differentials use the general
  international rate).
  Adult Basic Education / Literacy / English Language Learning:
  domestic tuition eliminated by government directive; international
  ELL is priced per semester ($5,853.25 x 2).
Graduate table skipped.

Annual figure = per-credit rate x 30 credits (semester-priced ELL x 2).
BC has one domestic rate (no in/out-of-province split).

Output: output/viu_tuition.json
Requires: beautifulsoup4, curl_cffi
"""
import json
import re
import time
from pathlib import Path

URL = "https://www.viu.ca/admissions/tuition-fee-schedule"
ACADEMIC_YEAR = "2026-2027"
CREDITS_PER_YEAR = 30


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


def table_after(soup, heading_part):
    for h in soup.find_all(["h2", "h3", "h4"]):
        if heading_part in h.get_text(" ", strip=True):
            t = h.find_next("table")
            if t is not None:
                return t
    raise RuntimeError(f"no table after heading containing {heading_part!r}")


def rows_of(table):
    out = {}
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))
                 for c in tr.find_all(["td", "th"])]
        if len(cells) >= 2:
            out[cells[0]] = cells[1]
    return out


def per_credit(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{1,2})?)\s*per credit", cell)
    return float(m.group(1).replace(",", "")) if m else None


def main():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fetch(URL), "html.parser")
    dom = rows_of(table_after(soup, "Domestic (Canadian) students"))
    diff = rows_of(table_after(soup, "differential tuition"))
    intl = rows_of(table_after(soup, "International students tuition"))

    base_dom = per_credit(next(v for k, v in dom.items()
                               if "Credit-based undergraduate" in k))
    base_intl = per_credit(next(v for k, v in intl.items()
                                if k.startswith("Undergraduate Degree")))
    gis_intl = per_credit(intl["Advanced Diploma in GIS Applications"])
    ell_sem = float(re.search(
        r"\$([\d,]+\.\d{2})\s*Full Semester",
        intl["English Language Learning"]).group(1).replace(",", ""))
    print(f"base dom={base_dom}, base intl={base_intl}, "
          f"GIS intl={gis_intl}, ELL intl/semester={ell_sem}")

    def diff_rate(name_part):
        return per_credit(next(v for k, v in diff.items() if name_part in k))

    std = (f"Per-credit tuition x {CREDITS_PER_YEAR} credits; tuition "
           f"only, lab/supply/co-op and students' union fees excluded.")
    entries = []

    def add(name, d_annual, i_annual, note=""):
        entries.append({
            "universityId": "viu",
            "universityName": "VIU",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": round(d_annual, 2),
                "international": round(i_annual, 2),
            },
            "comments": f"{std}{note}",
        })

    add("Credit-Based Undergraduate Programs",
        base_dom * CREDITS_PER_YEAR, base_intl * CREDITS_PER_YEAR)
    add("Bachelor of Social Work",
        diff_rate("Bachelor of Social Work") * CREDITS_PER_YEAR,
        base_intl * CREDITS_PER_YEAR,
        " Differential domestic rate; the program is 60 credits total. "
        "No international differential is published, so the general "
        "international rate is shown.")
    add("Dental Hygiene Diploma",
        diff_rate("Dental Hygiene") * CREDITS_PER_YEAR,
        base_intl * CREDITS_PER_YEAR,
        " Differential domestic rate. Actual load is heavier than 30 "
        "credits/year (Year 1: 39 credits, Year 2: 37.5).")
    add("Practical Nursing Diploma",
        diff_rate("Practical Nursing") * CREDITS_PER_YEAR,
        base_intl * CREDITS_PER_YEAR,
        " Differential domestic rate.")
    add("Advanced Diploma in Geographic Information Systems (GIS)",
        diff_rate("Advanced Diploma in Geographic") * CREDITS_PER_YEAR,
        gis_intl * CREDITS_PER_YEAR)
    add("Adult Basic Education and Literacy", 0.0,
        base_intl * CREDITS_PER_YEAR,
        " Domestic tuition eliminated Sept. 1, 2017 by government "
        "directive.")
    entries.append({
        "universityId": "viu",
        "universityName": "VIU",
        "programId": slug("English Language Learning"),
        "programName": "English Language Learning",
        "academicYear": ACADEMIC_YEAR,
        "tuition": {
            "domestic-in-province": 0.0,
            "international": round(ell_sem * 2, 2),
        },
        "comments": "Domestic tuition eliminated Sept. 1, 2017 by "
                    "government directive. International is priced per "
                    "14-week semester; annual = 2 semesters.",
    })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "viu_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:46]:46s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
