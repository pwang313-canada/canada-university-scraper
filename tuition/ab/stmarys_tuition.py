#!/usr/bin/env python3
"""St. Mary's University (Calgary) tuition scraper (2026-2027).

stmarysTuitionV1 -- NOTE: this is St. Mary's University in CALGARY,
not Saint Mary's University in Halifax.

Source: St. Mary's University -- Tuition and Fees page
(stmu.ca/admission/tuition-and-fees/), "Undergraduate Programs:
Domestic Students 2026-2027" and "...International Students
2026-2027" tables. The page publishes the annual tuition directly
(10 courses / 30 credits per year):

  Domestic      $936 per course  -> $9,360/year
  International $2,808 per course -> $28,080/year (exactly 3x)

One rate covers all undergraduate programs. The Education
After-Degree tables on the same page ($11,940 / $35,820) are a
post-degree program and are out of scope, as are the Master of
Education and certificate tables. General fees (athletics, student
services, Students' Association, U-Pass, health & dental) are listed
separately and excluded.

Output: output/stmarys_tuition.json (entry-list schema, shared with
the other province scrapers; combine with combine_tuition.py).
"""

import json
import os
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

URL = "https://stmu.ca/admission/tuition-and-fees/"
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "stmarys"
UNIVERSITY_NAME = "St. Mary's University"

BASE_COMMENT = (
    "From St. Mary's University (Calgary) Tuition and Fees page, "
    "2026-2027 undergraduate tables, which publish the annual tuition "
    "directly (10 courses / 30 credits per year): $936 per course "
    "domestic, $2,808 international. One rate covers all "
    "undergraduate programs. General fees are listed separately and "
    "excluded. The Education After-Degree is a post-degree program "
    "and is not included."
)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money(text):
    return float(text.replace("$", "").replace(",", "").strip())


def annual_tuition(soup, section_keyword):
    """Tuition row's Annual Cost in the first table after the heading
    containing section_keyword (headings carry an 'expand_less'
    suffix from the accordion markup)."""
    seen_section = False
    for el in soup.find_all(["h2", "h3", "table"]):
        if el.name in ("h2", "h3"):
            seen_section = section_keyword in el.get_text(" ", strip=True)
        elif seen_section:
            rows = [[c.get_text(" ", strip=True)
                     for c in tr.find_all(["td", "th"])]
                    for tr in el.find_all("tr")]
            annual_col = rows[0].index("Annual Cost")
            for row in rows:
                if row and row[0] == "Tuition":
                    return money(row[annual_col])
    raise RuntimeError(f"section not found: {section_keyword}")


def main():
    r = requests.get(URL, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    entry = {
        "universityId": UNIVERSITY_ID,
        "universityName": UNIVERSITY_NAME,
        "programId": slugify("All Undergraduate Programs"),
        "programName": "All Undergraduate Programs",
        "academicYear": ACADEMIC_YEAR,
        "tuition": {
            "domestic-in-province": annual_tuition(
                soup, "Undergraduate Programs: Domestic"),
            "international": annual_tuition(
                soup, "Undergraduate Programs: International"),
        },
        "comments": BASE_COMMENT,
    }

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "stmarys_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([entry], f, indent=1, ensure_ascii=False)
    print(f"Wrote 1 entry to {path}: {entry['tuition']}")


if __name__ == "__main__":
    main()
