#!/usr/bin/env python3
"""MacEwan University undergraduate tuition scraper (2026-2027).

macewanTuitionV1

Source: MacEwan University Academic Calendar 2026-2027 (archived
edition), Office of the University Registrar Information -> Tuition
and Fees -> Tuition (calendar.macewan.ca). The calendar root now
serves the 2027-2028 edition, so the archived 2026-2027 URL is used
deliberately. Rates are Board-approved for 2026/27.

Model: tuition = course credits x the program's per-credit rate.
Annual = per-credit x 30 credits.

Domestic bachelor-degree rates per credit:
  $214 -> $6,420/yr  (BA, Bachelor of Child & Youth Care, BCom, BSW)
  $250 -> $7,500/yr  (BSc, BSc in Nursing, B Psychiatric Nursing,
                      BMus, B Early Childhood Curriculum Studies,
                      B Public Safety and Justice, Applied Human
                      Service Administration)
  $293 -> $8,790/yr  (B Communication Studies, B Design, B Fine Art)

International tuition is a FLAT $941 per credit for all post-secondary
programs (minimum 9 credits billed per Fall/Winter term), so every
entry carries international = $941 x 30 = $28,230.

Scope: bachelor and applied degree programs only (the planner app
lists bachelor's programs). Diplomas, certificates, post-baccalaureate
and preparatory programs (EAL, Academic Upgrading) are in the same
calendar table but are not emitted.

Output: output/macewan_tuition.json (entry-list schema, shared with
the other province scrapers; combine with combine_tuition.py).
"""

import json
import os
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

URL = ("https://calendar.macewan.ca/previous-calendars/2026-2027/"
       "our-info/tuition-fees/tuition/")
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "macewan"
UNIVERSITY_NAME = "MacEwan University"
CREDITS_PER_YEAR = 30

BASE_COMMENT = (
    "From the MacEwan University Academic Calendar 2026-2027 (Board-"
    "approved rates). Tuition is charged per credit at the program's "
    "rate; annual = per-credit rate x 30 credits. International tuition "
    "is a flat $941 per credit for all post-secondary programs "
    "(minimum 9 credits billed per Fall/Winter term). Tuition only; "
    "mandatory non-instructional fees excluded."
)

# Calendar section headings whose tables count as degree programs.
DEGREE_SECTIONS = ("Bachelor Degree Programs", "Applied Degree Programs")


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money(text):
    return float(text.replace("$", "").replace(",", "").strip())


def main():
    r = requests.get(URL, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    content = soup.find("div", id="content") or soup

    # --- domestic per-credit rates for degree programs --------------
    programs = {}  # program name -> per-credit domestic rate
    section = None
    for el in content.find_all(["h2", "h3", "h4", "table"]):
        if el.name != "table":
            text = el.get_text(" ", strip=True)
            if text in DEGREE_SECTIONS or text.startswith(
                ("Post-Baccalaureate", "Post-Diploma", "University Transfer",
                 "Certificate and Diploma", "Certificate of Achievement",
                 "University and College Entrance", "International Tuition")
            ):
                section = text
            continue
        if section not in DEGREE_SECTIONS:
            continue
        for tr in el.find_all("tr"):
            cells = [c.get_text(" ", strip=True)
                     for c in tr.find_all(["td", "th"])]
            if len(cells) == 2 and cells[1].startswith("$"):
                programs[cells[0]] = money(cells[1])

    if not programs:
        raise RuntimeError("no degree programs parsed from the calendar page")

    # --- international flat per-credit rate -------------------------
    text = content.get_text(" ", strip=True)
    intl_section = text.split("International Tuition Fees", 1)[1]
    per_credit = max(
        float(v.replace(",", ""))
        for v in re.findall(r"\$([\d,]+)", intl_section.split("Spring")[0])
        if float(v.replace(",", "")) < 5000
        and float(v.replace(",", "")) > 100
        and "." not in v
    )
    # The table's per-credit column is $941 (totals run into the
    # thousands); sanity-anchor on the 9-credit total instead:
    m = re.search(r"9\s+\$([\d,]+)\s+\$([\d,]+)", intl_section)
    if m:
        per_credit = float(m.group(1).replace(",", ""))

    out = []
    for name, rate in sorted(programs.items()):
        out.append({
            "universityId": UNIVERSITY_ID,
            "universityName": UNIVERSITY_NAME,
            "programId": slugify(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": round(rate * CREDITS_PER_YEAR, 2),
                "international": round(per_credit * CREDITS_PER_YEAR, 2),
            },
            "comments": BASE_COMMENT + f" Domestic rate ${rate:,.0f}/credit.",
        })

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "macewan_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(out)} entries to {path} "
          f"(international per-credit ${per_credit:,.0f})")


if __name__ == "__main__":
    main()
