#!/usr/bin/env python3
"""Kwantlen (KPU) tuition scraper.
# MARKER: kwantlenTuitionV1

Source: https://www.kpu.ca/tuition-estimator
The estimator is powered by a public Google Sheet (its id is embedded
in the page). This script reads the sheet's "Tuition" tab through the
keyless gviz endpoint -- the same numbers the estimator itself uses.

KPU charges per credit, by rate category (sheet column 1 is tuition;
the ~7% per-credit student fee column is excluded -- tuition only):
  2.a.1 default (most programs) $166.10/cr
  premium categories 2.a.2-2.a.9 for specific programs (nursing,
  product design, brewing/mechatronics, technical apparel, ...)
  vocational $144.70/cr, arborist apprenticeships $296.79/cr
  adult upgrading / qualifying studies / English Language Studies: $0
International is a FLAT $755.77/cr regardless of field of study,
except ENGQ/ELST courses at $418.28/cr.

Annual figure = per-credit rate x 30 credits.
BC has one domestic rate (no in/out-of-province split).

Output: output/kwantlen_tuition.json
Requires: curl_cffi
"""
import json
import re
import time
from pathlib import Path

PAGE_URL = "https://www.kpu.ca/tuition-estimator"
FALLBACK_SHEET_ID = "15Es9Pxoxac2OqXnU0pIuRdxZ0zw6OgXoMEiqGPugZzE"
ACADEMIC_YEAR = "2026-2027"
CREDITS_PER_YEAR = 30

# (display name, description keyword in the sheet, note) -- domestic rows
CATEGORIES = [
    ("Most Programs (default rate)", "Default.",
     ""),
    ("Education Assistant", "Eduation Assistant",
     ""),
    ("Product Design (Bachelor of Design)", "Product Design",
     " Rate also covers the Post-Baccalaureate Diploma in Human Resources "
     "Management."),
    ("Nursing and Health Unit Coordinator", "Health Unit Coordinator",
     " Covers Health Unit Coordinator, Bachelor of Science in Nursing "
     "and Advanced Entry nursing."),
    ("Brewing and Mechatronics", "Brewing and Brewery Operations",
     " Covers Brewing and Brewery Operations, Mechatronics & Advanced "
     "Manufacturing Technology and industry-specific technical programs."),
    ("Technical Apparel Design", "Technical Apparel Design",
     ""),
    ("Accounting (Post-Baccalaureate Diploma)", "Accounting: Post-Baccalaureate",
     ""),
    ("Traditional Chinese Medicine - Acupuncture",
     "Traditional Chinese Medicine", ""),
    ("Business Post-Baccalaureate and Graduate Diplomas",
     "Operations & Supply Chain",
     " Covers post-baccalaureate diplomas in Operations & Supply Chain "
     "Management and Technical Management & Services, and graduate "
     "diplomas in Business Administration."),
    ("Vocational Courses", "vocational courses",
     ""),
    ("Arborist Apprenticeships", "Arborist Technician",
     ""),
    ("Adult Upgrading and University Qualifying Studies",
     "University Qualifying Studies",
     " Tuition-free for domestic students (adult upgrading is also "
     "tuition-free)."),
    ("English Language Studies", "English Language Studies",
     " Tuition-free for domestic students; international students pay "
     "the ENGQ/ELST rate."),
]
INTL_FLAT_KEY = "International per credit regardless"
INTL_ELST_KEY = "international- Courses in ENGQ and ELST"


def fetch(url):
    from curl_cffi import requests
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, impersonate="chrome120", timeout=45)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def sheet_rows(sheet_id, tab):
    txt = fetch(f"https://docs.google.com/spreadsheets/d/{sheet_id}"
                f"/gviz/tq?tqx=out:json&sheet={tab}")
    data = json.loads(re.search(r"setResponse\((.*)\);?\s*$", txt, re.S).group(1))
    return [[(c.get("v") if c else None) for c in row["c"]]
            for row in data["table"]["rows"]]


def rate_for(rows, keyword):
    for row in rows:
        desc = str(row[3] or "")
        if keyword.lower() in desc.lower():
            return float(row[1])
    raise RuntimeError(f"category not found in sheet: {keyword!r}")


def main():
    page = fetch(PAGE_URL)
    m = re.search(r"spreadsheets/([A-Za-z0-9_-]+)/", page)
    sheet_id = m.group(1) if m else FALLBACK_SHEET_ID
    print(f"sheet: {sheet_id}")
    rows = sheet_rows(sheet_id, "Tuition")
    print(f"Tuition tab: {len(rows)} rows")

    intl_flat = rate_for(rows, INTL_FLAT_KEY)
    intl_elst = rate_for(rows, INTL_ELST_KEY)
    print(f"international flat={intl_flat}, ENGQ/ELST={intl_elst}")

    entries = []
    for name, keyword, note in CATEGORIES:
        d_rate = rate_for(rows, keyword)
        i_rate = intl_elst if name == "English Language Studies" else intl_flat
        entries.append({
            "universityId": "kwantlen",
            "universityName": "Kwantlen (KPU)",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": round(d_rate * CREDITS_PER_YEAR, 2),
                "international": round(i_rate * CREDITS_PER_YEAR, 2),
            },
            "comments": (
                f"Per-credit tuition x {CREDITS_PER_YEAR} credits from KPU's "
                f"tuition estimator data: domestic ${d_rate}/cr, "
                f"international ${i_rate}/cr (flat rate regardless of field "
                f"of study). Tuition only; per-credit student fees "
                f"excluded.{note}"
            ),
        })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "kwantlen_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:46]:46s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
