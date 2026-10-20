#!/usr/bin/env python3
"""Athabasca University undergraduate tuition scraper (2026-2027).

athabascaTuitionV1

Source: Athabasca University Calendar (online, official version),
Fees, refunds, and financial assistance -> Canadian student fees and
Non-Canadian student fees (athabascau.ca). Rates effective for courses
starting Sep. 1, 2026 to Aug. 31, 2027.

AU is an online university: tuition is charged PER CREDIT, and the
rate depends only on the faculty of the course -- Faculty of Business
and Faculty of Health Disciplines courses cost more than Faculty of
Humanities and Social Sciences and Faculty of Science and Technology
courses. Annual = per-credit x 30 credits.

  Domestic (same rate in and outside Alberta):
    Business / Health Disciplines  $227/cr -> $6,810/yr
    Humanities & Soc Sci / Sci & Tech  $211/cr -> $6,330/yr
  Non-Canadian students (living temporarily in Canada) pay exactly
  double: $454 / $422 per credit -> $13,620 / $12,660 per year.
  Students living OUTSIDE Canada pay the domestic tuition rate plus an
  out-of-country fee of $267/credit (noted in comments only).

Excluded per-course fees: Course Administration and Technology Fee
($185 or $169 per course) and Course Materials Fee ($90 per course).

Output: output/athabasca_tuition.json (entry-list schema, shared with
the other province scrapers; combine with combine_tuition.py).
"""

import json
import os
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

BASE = ("https://www.athabascau.ca/calendar/undergraduate/"
        "fees-refunds-and-financial-assistance/")
CANADIAN_URL = BASE + "canadian-student-fees.html"
NON_CANADIAN_URL = BASE + "non-canadian-student-fees.html"
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "athabasca"
UNIVERSITY_NAME = "Athabasca University"
CREDITS_PER_YEAR = 30

BASE_COMMENT = (
    "From the Athabasca University Calendar fee schedules (effective "
    "Sep. 1, 2026 - Aug. 31, 2027). AU charges tuition per credit by "
    "the faculty of the course; annual = per-credit rate x 30 credits. "
    "The domestic rate is the same for Alberta and out-of-province "
    "Canadians. Non-Canadian students living in Canada pay double. "
    "Students living outside Canada pay the domestic tuition rate plus "
    "a $267/credit out-of-country fee. Per-course administration/"
    "technology and materials fees are excluded."
)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money(text):
    return float(text.replace("$", "").replace(",", "").strip())


def one_credit_tuition(url):
    """{faculty short name: per-credit tuition} from the page's first
    1-credit table (regular registrations, in-Alberta section)."""
    r = requests.get(url, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for table in soup.find_all("table"):
        rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                for tr in table.find_all("tr")]
        if not rows or "1-credit course" not in rows[0][0] \
                and "1 credit" not in rows[0][0].lower():
            continue
        header = next((x for x in rows if len(x) == 5 and "Business" in x[1]),
                      None)
        trow = next((x for x in rows if x and x[0] == "Tuition fee"), None)
        if header and trow:
            return {
                header[i].replace("Faculty of ", "").replace(" courses", ""):
                money(trow[i])
                for i in range(1, 5)
            }
    raise RuntimeError(f"1-credit tuition table not found at {url}")


def main():
    domestic = one_credit_tuition(CANADIAN_URL)
    intl = one_credit_tuition(NON_CANADIAN_URL)

    out = []
    for faculty in sorted(domestic):
        tuition = {
            "domestic-in-province":
                round(domestic[faculty] * CREDITS_PER_YEAR, 2),
        }
        if faculty in intl:
            tuition["international"] = round(
                intl[faculty] * CREDITS_PER_YEAR, 2)
        out.append({
            "universityId": UNIVERSITY_ID,
            "universityName": UNIVERSITY_NAME,
            "programId": slugify(faculty),
            "programName": faculty,
            "academicYear": ACADEMIC_YEAR,
            "tuition": tuition,
            "comments": BASE_COMMENT
                        + f" Per-credit tuition ${domestic[faculty]:,.0f} "
                          f"(domestic) / ${intl.get(faculty, 0):,.0f} "
                          "(non-Canadian).",
        })

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "athabasca_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(out)} entries to {path}")


if __name__ == "__main__":
    main()
