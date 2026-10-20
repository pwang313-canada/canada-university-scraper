#!/usr/bin/env python3
"""Burman University (Lacombe, Alberta) tuition scraper (2026-2027).

burmanTuitionV1

Source: Burman University, Student Financial Services cost summaries
(burmanu.ca/studentfinancialservices/costsummarycad for Canadian
citizens/permanent residents, .../costsummaryworld for international
students), May 2026 - April 2027. Burman publishes no per-program fee
schedule; both summaries quote one rate for all programs, and the
domestic figure matches the tuition Burman reports to Alberta Student
Aid (ALIS) for every bachelor's program.

  Domestic      Tuition, 30 credits/year ($577/credit) -> $17,310
  International Tuition, 30 credits/year ($696/credit) -> $20,880

Excluded (listed separately on the same pages): mandatory fees
($1,000), health plan ($360), application and attendance-confirmation
fees, dorm/cafe charges.

Output: output/burman_tuition.json (entry-list schema, shared with
the other province scrapers; combine with combine_tuition.py).
"""

import json
import os
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

BASE = "https://www.burmanu.ca/studentfinancialservices/"
DOMESTIC_URL = BASE + "costsummarycad"
INTERNATIONAL_URL = BASE + "costsummaryworld"
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "burman"
UNIVERSITY_NAME = "Burman University"

BASE_COMMENT = (
    "From Burman University's Student Financial Services cost "
    "summaries for May 2026 - April 2027 (Burman's academic year). "
    "One tuition rate applies to all programs, quoted per 30-credit "
    "year: $577/credit domestic, $696/credit international. The "
    "domestic figure matches the tuition reported to Alberta Student "
    "Aid (ALIS). Mandatory fees ($1,000) and health plan ($360) are "
    "listed separately and excluded."
)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def annual_tuition(url):
    r = requests.get(url, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.find("article").get_text(" ", strip=True)
    m = re.search(r"Tuition and Fees\s*\$\s*([\d,]+)\s*Tuition 30 credits/year",
                  text)
    if not m:
        raise RuntimeError(f"tuition block not found at {url}")
    return float(m.group(1).replace(",", ""))


def main():
    entry = {
        "universityId": UNIVERSITY_ID,
        "universityName": UNIVERSITY_NAME,
        "programId": slugify("All Undergraduate Programs"),
        "programName": "All Undergraduate Programs",
        "academicYear": ACADEMIC_YEAR,
        "tuition": {
            "domestic-in-province": annual_tuition(DOMESTIC_URL),
            "international": annual_tuition(INTERNATIONAL_URL),
        },
        "comments": BASE_COMMENT,
    }

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "burman_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([entry], f, indent=1, ensure_ascii=False)
    print(f"Wrote 1 entry to {path}: {entry['tuition']}")


if __name__ == "__main__":
    main()
