#!/usr/bin/env python3
"""Ambrose University (Calgary) tuition scraper (2026-2027).

ambroseTuitionV1

Source: Ambrose University official "Tuition and Fee Summary
2026-2027" PDF (as of Apr. 30, 2026), linked from
ambrose.edu/admissions/tuition-fees/. The scraper discovers the
current summary PDF on that page (the CDN path changes each year).

Per-credit tuition (page 1 of the summary):
  Undergraduate -- Arts & Sciences and School of Business (combined
    column): $523.49 domestic / $785.24 international (exactly 1.5x)
  Education: $529.98 domestic. The summary's single International
    column belongs to the undergraduate rate; no international
    Education rate is published, so the Education entry is
    domestic-only.
Annual = per-credit x 30 credits.

Excluded per-credit fees: Student Services ($42.72), Registration
($5.95) and Infrastructure & Technology ($40.00) per credit, plus
per-course lab/studio fees listed in the summary.

Output: output/ambrose_tuition.json (entry-list schema, shared with
the other province scrapers; combine with combine_tuition.py).
Requires: pypdf (in requirements.txt).
"""

import io
import json
import os
import re

from bs4 import BeautifulSoup
from curl_cffi import requests
from pypdf import PdfReader

PAGE_URL = "https://ambrose.edu/admissions/tuition-fees/"
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "ambrose"
UNIVERSITY_NAME = "Ambrose University"
CREDITS_PER_YEAR = 30

BASE_COMMENT = (
    "From Ambrose University's official Tuition and Fee Summary "
    "2026-2027. Tuition is per credit; annual = per-credit x 30 "
    "credits. Arts & Sciences and the School of Business share one "
    "rate column. International tuition is 1.5x the domestic rate. "
    "Student Services, registration and infrastructure/technology "
    "fees (per credit) and per-course lab/studio fees are excluded."
)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def find_summary_pdf():
    r = requests.get(PAGE_URL, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if "Tuition-and-Fee-Summary" in a["href"]:
            return a["href"]
    raise RuntimeError("Tuition and Fee Summary PDF not linked on page")


def per_credit_rates(pdf_url):
    """[undergrad domestic, international, education, ...] from the
    summary's first 'Tuition (per credit)' row (page 1)."""
    r = requests.get(pdf_url, impersonate="chrome120", timeout=60)
    r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    text = reader.pages[0].extract_text() or ""
    m = re.search(r"Tuition \(per credit\)\s*((?:[\d,]+\.\d{2}\s*\$?\s*)+)", text)
    if not m:
        raise RuntimeError("Tuition (per credit) row not found in PDF")
    return [float(x.replace(",", "")) for x in re.findall(r"[\d,]+\.\d{2}", m.group(1))]


def entry(name, tuition):
    return {
        "universityId": UNIVERSITY_ID,
        "universityName": UNIVERSITY_NAME,
        "programId": slugify(name),
        "programName": name,
        "academicYear": ACADEMIC_YEAR,
        "tuition": tuition,
        "comments": BASE_COMMENT,
    }


def main():
    rates = per_credit_rates(find_summary_pdf())
    undergrad, intl, education = rates[0], rates[1], rates[2]

    out = [
        entry("Arts & Sciences and Business", {
            "domestic-in-province": round(undergrad * CREDITS_PER_YEAR, 2),
            "international": round(intl * CREDITS_PER_YEAR, 2),
        }),
        entry("Education", {
            "domestic-in-province": round(education * CREDITS_PER_YEAR, 2),
        }),
    ]

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "ambrose_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(out)} entries to {path}")


if __name__ == "__main__":
    main()
