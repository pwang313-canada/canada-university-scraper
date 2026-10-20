#!/usr/bin/env python3
"""University of Lethbridge undergraduate tuition scraper (2026-2027).

ulethbridgeTuitionV1

Sources (official, ulethbridge.ca):
  * Undergraduate Tuition & Fees Estimate page -- publishes the annual
    tuition directly: domestic $6,822.00, international $24,662.20
    (2026/2027). Used as a cross-check.
  * Financial Services fee-schedule PDFs for Fall 2026/Winter 2027
    (Lethbridge/main campus; Calgary campus tuition is identical --
    only Students' Union fees differ). Links are discovered from the
    fee-schedules page, not hard-coded.

Model: tuition is per 3.0-credit course; annual = per-course x 10
(30 credits). Domestic $682.20/course, international $2,466.22/course
-- both annualize exactly to the published estimates.

A Differential Fee of $19.10 per 3-credit course (both domestic and
international) applies to Health Science, Education and Science
courses; those areas get their own entries at base + $191/year.

Not annualized: Music Studio course fees ($663.97 per 3-credit studio
course) and the Dhillon School of Business Experiential Learning Fee
($20.40/semester) -- course/program fees, not tuition rates.

Output: output/ulethbridge_tuition.json (entry-list schema, shared
with the other province scrapers; combine with combine_tuition.py).
Requires: pypdf (in requirements.txt).
"""

import io
import json
import os
import re
import sys

from bs4 import BeautifulSoup
from curl_cffi import requests
from pypdf import PdfReader

FEE_SCHEDULES_PAGE = "https://www.ulethbridge.ca/financial-services/fee-schedules"
ESTIMATE_PAGE = "https://www.ulethbridge.ca/future-student/undergraduate-tuition-fees"
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "ulethbridge"
UNIVERSITY_NAME = "University of Lethbridge"
COURSES_PER_YEAR = 10  # 30 credits, 3.0 credits per course

BASE_COMMENT = (
    "From the University of Lethbridge 2026/2027 fee schedules "
    "(Fall/Winter, Lethbridge campus; Calgary campus tuition is the "
    "same). Tuition is charged per 3.0-credit course; annual = "
    "per-course rate x 10 courses (30 credits), which matches the "
    "university's published annual tuition estimates ($6,822 domestic / "
    "$24,662.20 international). Tuition only; administrative, Students' "
    "Union and other fees excluded."
)
DIFF_COMMENT = (
    " Includes the $19.10 per-course Differential Fee charged on Health "
    "Science, Education and Science courses (x 10 courses = $191/year)."
)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def find_pdf(session, label):
    """First link on the fee-schedules page with this text (main campus
    section comes before the Calgary section)."""
    soup = BeautifulSoup(session.get(FEE_SCHEDULES_PAGE, timeout=30).text,
                         "html.parser")
    for a in soup.find_all("a", href=True):
        if a.get_text(" ", strip=True) == label:
            return a["href"]
    raise RuntimeError(f"fee schedule link not found: {label}")


def pdf_text(session, url):
    r = session.get(url, timeout=60)
    r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def per_course_tuition(text):
    """Tuition column of the 'One Course (3.0 Credit Hours)' row."""
    m = re.search(r"One Course \(3\.0 Credit Hours\)\s+([\d,]+\.\d{2})", text)
    if not m:
        raise RuntimeError("per-course tuition row not found")
    return float(m.group(1).replace(",", ""))


def differential_fee(text):
    m = re.search(r"Differential Fee.*?([\d,]+\.\d{2})\s*\(3 credit rate\)",
                  text, re.S)
    if not m:
        raise RuntimeError("differential fee not found")
    return float(m.group(1).replace(",", ""))


def main():
    session = requests.Session(impersonate="chrome120")

    dom_text = pdf_text(session, find_pdf(
        session, "Fall 2026/Winter 2027 - Domestic Students"))
    intl_text = pdf_text(session, find_pdf(
        session, "Fall 2026/Winter 2027 - International Students"))

    dom_course, intl_course = per_course_tuition(dom_text), per_course_tuition(intl_text)
    dom_diff, intl_diff = differential_fee(dom_text), differential_fee(intl_text)

    base = {
        "domestic-in-province": round(dom_course * COURSES_PER_YEAR, 2),
        "international": round(intl_course * COURSES_PER_YEAR, 2),
    }
    print(f"per-course: dom ${dom_course}, intl ${intl_course}; "
          f"differential: dom ${dom_diff}, intl ${intl_diff}", file=sys.stderr)
    print(f"annual base: {base}", file=sys.stderr)

    diff = {
        "domestic-in-province": round((dom_course + dom_diff) * COURSES_PER_YEAR, 2),
        "international": round((intl_course + intl_diff) * COURSES_PER_YEAR, 2),
    }

    entries = [
        ("All Other Undergraduate Programs", base, ""),
        ("Health Sciences", diff, DIFF_COMMENT),
        ("Education", diff, DIFF_COMMENT),
        ("Science", diff, DIFF_COMMENT),
    ]
    out = [
        {
            "universityId": UNIVERSITY_ID,
            "universityName": UNIVERSITY_NAME,
            "programId": slugify(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": tuition,
            "comments": BASE_COMMENT + extra,
        }
        for name, tuition, extra in sorted(entries, key=lambda e: e[0])
    ]

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "ulethbridge_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(out)} entries to {path}")


if __name__ == "__main__":
    main()
