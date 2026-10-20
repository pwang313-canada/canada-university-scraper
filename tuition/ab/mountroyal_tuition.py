#!/usr/bin/env python3
"""Mount Royal University undergraduate tuition scraper (2026-2027).

mountroyalTuitionV1

Source: Mount Royal University 2026-27 Tuition Fee Schedules
(Fall/Winter), mtroyal.ca/academics/fees/pages/2026-27/ --
domestic-fall-winter.php and international-fall-winter.php.

Model: tuition is charged per "full course" (a course worth 2 to 5
credits; a standard course is 3 credits). Annual = full-course fee
x 10 courses (30 credits). Tuition includes instructional equipment
and lab fees.

Domestic per-course rates: base $704.37, with program-specific rates
for Interior Design ($925.18), Broadcast Media ($925.18), BBA
($757.19), BCIS ($728.75), BSc ($728.75), Nursing ($731.86) and
Social Work ($704.10). International tuition is a FLAT $2,427.78 per
course for all programs (no program-specific add-ons in 2026-27),
so every entry carries international = $24,277.80/year.

Output: output/mountroyal_tuition.json (entry-list schema, shared
with the other province scrapers; combine with combine_tuition.py).
"""

import json
import os
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

DOMESTIC_URL = ("https://www.mtroyal.ca/academics/fees/pages/2026-27/"
                "domestic-fall-winter.php")
INTERNATIONAL_URL = ("https://www.mtroyal.ca/academics/fees/pages/2026-27/"
                     "international-fall-winter.php")
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "mountroyal"
UNIVERSITY_NAME = "Mount Royal University"
COURSES_PER_YEAR = 10  # 30 credits, one full course = a 3-credit course

BASE_COMMENT = (
    "From Mount Royal University's 2026-27 Tuition Fee Schedule "
    "(Fall/Winter). Tuition is charged per full course (a standard "
    "3-credit course); annual = full-course fee x 10 courses "
    "(30 credits). Tuition includes instructional equipment and lab "
    "fees. International tuition is a flat per-course rate for all "
    "programs. General and Students' Association fees excluded."
)

# Schedule label -> (entry name, extra comment)
LABEL_MAP = {
    "Bachelor of Interior Design": ("Bachelor of Interior Design", ""),
    "Bachelor of Communication (Broadcast Media)":
        ("Bachelor of Communication (Broadcast Media)", ""),
    "Bachelor of Business Administration (all majors)":
        ("Bachelor of Business Administration",
         " Rate applies to all BBA majors."),
    "Bachelor of Computer Information Systems":
        ("Bachelor of Computer Information Systems", ""),
    "Bachelor of Science (all majors and Spatial Data Science certificate)":
        ("Bachelor of Science",
         " Rate applies to all BSc majors (and the Spatial Data Science "
         "certificate)."),
    "Bachelor of Nursing": ("Bachelor of Nursing", ""),
    "Bachelor of Social Work": ("Bachelor of Social Work", ""),
}


def strip_bachelor(name):
    """Drop the leading 'Bachelor of '/'Bachelor ' -- the app matches
    on the field name (e.g. 'Nursing', 'Business Administration')."""
    return re.sub(r"^Bachelor\s+(of\s+)?", "", name)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money(text):
    return float(text.replace("$", "").replace(",", "").strip())


def tuition_table(soup, caption):
    """Rows of the table whose first row is the given caption."""
    for table in soup.find_all("table"):
        rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                for tr in table.find_all("tr")]
        rows = [r for r in rows if any(r)]
        if rows and rows[0] and rows[0][0] == caption:
            return rows
    raise RuntimeError(f"table not found: {caption}")


def full_course_fee(rows):
    """(label -> full course fee) from a Student Tuition table."""
    out = {}
    for row in rows:
        if len(row) >= 2 and row[1].startswith("$"):
            label = re.sub(r"\s+\d+$", "", row[0])  # drop footnote number
            out[label] = money(row[1])
    return out


def main():
    dom = BeautifulSoup(
        requests.get(DOMESTIC_URL, impersonate="chrome120", timeout=30).text,
        "html.parser")
    intl = BeautifulSoup(
        requests.get(INTERNATIONAL_URL, impersonate="chrome120", timeout=30).text,
        "html.parser")

    base_dom = full_course_fee(tuition_table(dom, "Student Tuition"))
    base_fee = base_dom["Tuition total"]
    specific = full_course_fee(
        tuition_table(dom, "Student Tuition - Program Specific"))
    intl_fee = full_course_fee(tuition_table(intl, "Student Tuition"))[
        "Tuition total"]
    intl_annual = round(intl_fee * COURSES_PER_YEAR, 2)

    entries = [(
        "All Other Undergraduate Programs",
        round(base_fee * COURSES_PER_YEAR, 2),
        " Standard per-course rate; the programs below have "
        "program-specific rates.",
    )]
    for label, fee in specific.items():
        name, extra = LABEL_MAP.get(label, (label, ""))
        entries.append((strip_bachelor(name),
                        round(fee * COURSES_PER_YEAR, 2), extra))

    out = [
        {
            "universityId": UNIVERSITY_ID,
            "universityName": UNIVERSITY_NAME,
            "programId": slugify(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": annual,
                "international": intl_annual,
            },
            "comments": BASE_COMMENT + extra,
        }
        for name, annual, extra in sorted(entries, key=lambda e: e[0])
    ]

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "mountroyal_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(out)} entries to {path}")


if __name__ == "__main__":
    main()
