#!/usr/bin/env python3
"""The King's University (Edmonton) tuition scraper (2026-2027).

kingsTuitionV1

Source: The King's University -- Tuition & Fees page
(kingsu.ca/services/financial-aid/tuition-and-fees), 2026-2027 tables
for Domestic and International students.

Model: one per-credit rate for ALL programs. The page quotes a full
course load as 15.5 credits per term (King's normal load is 31
credits/year); the annual figures here use the standard 30-credit
year used across the planner for comparability.

  Domestic      $516/credit -> $15,480/year (31-credit load: $15,996)
  International $774/credit -> $23,220/year (exactly 1.5x domestic;
                King's no longer uses the old per-term international
                cohort fee)

Excluded: student fees, orientation fee, healthcare plan, deposits
(international admissions/tuition deposits), textbooks.

Output: output/kings_tuition.json (entry-list schema, shared with
the other province scrapers; combine with combine_tuition.py).
"""

import json
import os
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

URL = "https://www.kingsu.ca/services/financial-aid/tuition-and-fees"
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "kings"
UNIVERSITY_NAME = "The King's University"
CREDITS_PER_YEAR = 30

BASE_COMMENT = (
    "From The King's University Tuition & Fees page (2026-2027). One "
    "per-credit rate applies to all programs; annual = per-credit x "
    "30 credits (King's quotes a full load as 15.5 credits/term, i.e. "
    "31 credits/year, which would be $15,996 domestic / $23,994 "
    "international). Student fees, orientation, healthcare plan and "
    "deposits excluded."
)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def per_credit_rate(soup, table_index):
    """Per-credit rate from the Tuition row of the given table."""
    table = soup.find_all("table")[table_index]
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if cells and cells[0].startswith("Tuition ("):
            m = re.search(r"\$([\d,]+(?:\.\d{2})?)/credit", cells[0])
            if m:
                return float(m.group(1).replace(",", ""))
    raise RuntimeError(f"tuition row not found in table {table_index}")


def main():
    r = requests.get(URL, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Table 0 = Domestic Students, Table 1 = International Students
    # (both headed 'Tuition & Fees (per term)', 2026-2027).
    domestic = per_credit_rate(soup, 0)
    intl = per_credit_rate(soup, 1)

    entry = {
        "universityId": UNIVERSITY_ID,
        "universityName": UNIVERSITY_NAME,
        "programId": slugify("All Undergraduate Programs"),
        "programName": "All Undergraduate Programs",
        "academicYear": ACADEMIC_YEAR,
        "tuition": {
            "domestic-in-province": round(domestic * CREDITS_PER_YEAR, 2),
            "international": round(intl * CREDITS_PER_YEAR, 2),
        },
        "comments": BASE_COMMENT
                    + f" Per-credit: ${domestic:,.2f} domestic / "
                      f"${intl:,.2f} international.",
    }

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "kings_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([entry], f, indent=1, ensure_ascii=False)
    print(f"Wrote 1 entry to {path}: {entry['tuition']}")


if __name__ == "__main__":
    main()
