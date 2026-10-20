#!/usr/bin/env python3
"""Extract Algoma University tuition only (ignore application fees, ancillary fees, totals)."""
# algomaFixV1

import json
import re
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests  # impersonates Chrome TLS; bypasses Cloudflare

    _IMPERSONATE = "chrome120"
except ImportError as e:
    raise SystemExit(
        "curl_cffi is required but could not be imported. "
        f"Run: pip install curl_cffi (error: {e})"
    )

URL = "https://algomau.ca/students/student-accounts/tuition-residence-fees/"
AMOUNT_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2}))")


def get_tuition(soup, section_keyword):
    """Find the section heading (e.g. 'Domestic Fees'), then the first table after it,
    then return the TUITION column's per-term amounts."""
    # Section label may be in a heading, button (accordion), or div — search broadly.
    heading = None
    for el in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "button", "div", "span", "strong"]
    ):
        text = el.get_text(" ", strip=True)
        if text and len(text) < 60 and section_keyword.lower() in text.lower():
            # Avoid matching nested parents: prefer the deepest (shortest) match
            if heading is None or len(text) < len(heading.get_text(" ", strip=True)):
                heading = el
    if not heading:
        return []

    table = heading.find_next("table")
    if not table:
        return []
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [
        c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])
    ]
    # TUITION column: header says "tuition" but not "total"
    tcol = next(
        (i for i, h in enumerate(headers) if "tuition" in h and "total" not in h), None
    )
    if tcol is None:
        return []
    amounts = []
    for tr in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if tcol >= len(cells):
            continue
        # Only per-term rows (skip per-credit breakdown rows)
        if "per term" not in cells[0].lower():
            continue
        m = AMOUNT_RE.search(cells[tcol])
        if m:
            amounts.append(float(m.group(1).replace(",", "")))
    return amounts


def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-CA,en;q=0.9",
    }
    r = requests.get(URL, timeout=25, headers=headers, impersonate="chrome120")

    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    domestic = get_tuition(soup, "domestic")
    international = get_tuition(soup, "international")

    # Annualize: 2 terms = 1 year. Use the Fall/Winter row (last per-term row).
    def annual(amounts):
        return round(amounts[-1] * 2, 2) if amounts else None

    d, i = annual(domestic), annual(international)
    tuition = {}
    if d:
        tuition["domestic-in-province"] = d
        # Algoma publishes a single domestic rate (no OOP differential);
        # both domestic keys carry it, per the RMC convention.
        tuition["domestic-out-of-province"] = d
    if i:
        tuition["international"] = i

    entry = {
        "universityId": "algoma",
        "universityName": "Algoma University",
        "programId": "undergraduate",
        "programName": "Undergraduate (full-time)",
        "academicYear": "2026-2027",
        "tuition": tuition,
        "comments": (
            "Flat undergraduate rate; Algoma publishes no per-program breakdown. "
            "Tuition column only, annualized from per-term Fall 2026 & Winter 2027 x 2; "
            "ancillary fees excluded. No Ontario/out-of-province differential published, "
            "so both domestic keys carry the published domestic figure. "
            "Source: algomau.ca/students/student-accounts/tuition-residence-fees/"
        ),
    }
    import os
    os.makedirs("output", exist_ok=True)
    out = os.path.join("output", "algoma_tuition.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump([entry], f, indent=2)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
