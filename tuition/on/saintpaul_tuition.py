#!/usr/bin/env python3
"""Saint Paul University (Ottawa) 2026-2027 tuition.
# saintPaulV1

Source: https://ustpaul.ca/en/financial-services/tuition-and-incidental-fees-2/

The fee table is headed "Fall 2026 - Winter 2027 - Spring/Summer 2027
(Tuition fees per term)": figures are PER TERM, annual = x 2 (Fall + Winter).
Full-time columns only (part-time/auditor per-3-unit figures skipped).
Ancillary + incidental fee rows excluded (tuition only).

Usage:
    python saintpaul_tuition.py        # -> output/saintpaul_tuition.json
"""
import json
import os
import re
import sys

try:
    from curl_cffi import requests
except ImportError:
    sys.exit("curl_cffi is required: pip install curl_cffi")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("beautifulsoup4 is required: pip install beautifulsoup4")

URL = "https://ustpaul.ca/en/financial-services/tuition-and-incidental-fees-2/"
AMOUNT_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")

GROUP_HEADERS = {"tuition fees", "ancillary fees", "incidental fees"}


def parse_amount(text):
    m = AMOUNT_RE.search((text or "").replace("\xa0", " "))
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

    table = soup.find_all("table")[0]
    in_tuition = False
    rows = []  # (program_label, can_ft_ont, can_ft_nonont, intl_ft) per term
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True).replace("\xa0", " ")
                 for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        first = cells[0].strip().lower()
        if first in GROUP_HEADERS:
            in_tuition = (first == "tuition fees")
            label, values = cells[1], cells[2:]
        elif not in_tuition:
            continue
        else:
            label, values = cells[0], cells[1:]
        amounts = [parse_amount(v) for v in values]
        if len([a for a in amounts if a is not None]) < 7:
            continue
        # value columns: can-ft-ont, can-ft-nonont, can-pt-ont, can-pt-nonont,
        #                can-aud-ont, can-aud-nonont, intl-ft, intl-pt, intl-aud
        rows.append((label, amounts[0], amounts[1], amounts[6]))

    legacy_note = ""
    entries = []
    for label, ont, nonont, intl in rows:
        low = label.lower()
        if "undergraduate" in low and "before the fall" in low:
            if ont:
                legacy_note = (f"Legacy rate for students admitted before Fall 2023: "
                               f"${ont * 2:,.2f}/yr domestic. ")
            continue  # legacy cohort: noted in comments, not a separate entry
        pid = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
        tuition = {}
        if ont is not None:
            tuition["domestic-in-province"] = round(ont * 2, 2)
        if nonont is not None:
            tuition["domestic-out-of-province"] = round(nonont * 2, 2)
        if intl is not None:
            tuition["international"] = round(intl * 2, 2)
        if not tuition:
            continue
        entries.append({
            "universityId": "saintpaul",
            "universityName": "Saint Paul University",
            "programId": pid,
            "programName": label,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments": (
                legacy_note +
                "Per-term figures x 2 = annual (Fall + Winter). Full-time rates; "
                "tuition only (ancillary/incidental fees excluded). "
                "Source: ustpaul.ca tuition-and-incidental-fees-2 (Fall 2026 - Winter 2027)."
            ),
        })

    os.makedirs("output", exist_ok=True)
    out = os.path.join("output", "saintpaul_tuition.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    print(f"wrote {out} ({len(entries)} entries)")


if __name__ == "__main__":
    main()
