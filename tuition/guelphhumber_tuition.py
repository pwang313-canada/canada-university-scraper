#!/usr/bin/env python3
"""Scrape University of Guelph-Humber first-year tuition (domestic Ontario /
out-of-province / international) from the official tuition-fees page.
Tuition only: excludes student/international fees rows.
# guelphHumberV1
"""

import json
import os
import re
import sys

try:
    from curl_cffi import requests  # impersonates Chrome TLS
    _IMPERSONATE = "chrome120"
except ImportError:
    sys.exit("curl_cffi is required: pip install curl_cffi")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("beautifulsoup4 is required: pip install beautifulsoup4")

URL = "https://www.guelphhumber.ca/tuition-support/tuition-fees"
AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")

# <details> accordion summary -> pipeline tuition key
SECTIONS = [
    ("ontario, full-time study", "domestic-in-province"),
    ("out of province, full-time study", "domestic-out-of-province"),
    ("international, full-time study", "international"),
]

PROGRAM_ROWS = ("business programs", "all other programs")


def parse_amount(text):
    m = AMOUNT_RE.search(text or "")
    return float(m.group(1).replace(",", "")) if m else None


def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-CA,en;q=0.9",
    }
    r = requests.get(URL, timeout=30, headers=headers, impersonate="chrome120")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # tuition[program_key][pipeline_key] = amount
    tuition = {}
    for summary_keyword, tuition_key in SECTIONS:
        detail = None
        for d in soup.find_all("details"):
            s = d.find("summary")
            if s and summary_keyword in s.get_text(" ", strip=True).lower():
                detail = d
                break
        if not detail:
            print(f"WARNING: section not found: {summary_keyword}", file=sys.stderr)
            continue
        table = detail.find("table")
        if not table:
            continue
        for tr in table.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            label = cells[0].lower()
            if "student fees" in label or label == "total":
                break  # tuition rows come before the fees rows
            if label in PROGRAM_ROWS and len(cells) > 1:
                amount = parse_amount(cells[1])
                if amount is not None:
                    tuition.setdefault(label, {})[tuition_key] = amount

    entries = []
    for label in PROGRAM_ROWS:
        t = tuition.get(label, {})
        if not t:
            continue
        program_id = label.replace(" ", "-")
        entries.append({
            "universityId": "guelphhumber",
            "universityName": "University of Guelph-Humber",
            "programId": program_id,
            "programName": " ".join(w.capitalize() for w in label.split()),
            "academicYear": "2026-2027",
            "tuition": t,
            "comments": (
                "First-year tuition only; student/international fees excluded. "
                "Domestic figures are 2026-27 estimates; international tuition is "
                "the published 2027-2028 rate (page note). "
                "Source: guelphhumber.ca/tuition-support/tuition-fees"
            ),
        })

    os.makedirs("output", exist_ok=True)
    out = os.path.join("output", "guelphhumber_tuition.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    print(f"wrote {out} ({len(entries)} entries)")


if __name__ == "__main__":
    main()
