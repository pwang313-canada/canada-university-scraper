#!/usr/bin/env python3
"""UFV (University of the Fraser Valley) tuition scraper.
# MARKER: ufvTuitionV1

Source: https://www.ufv.ca/fees-and-payments/tuition-and-fees/
The page publishes 2025-2026 and 2026-2027 columns side by side;
the 2026-2027 column is used -> academicYear 2026-2027.

UFV charges per credit. TUITION ONLY -- the "Tuition/credit" row is read;
ancillary, experiential-learning and student-union fees are excluded.
  Domestic undergraduate: $169.94/credit.
  Domestic ABE and ESL: tuition-free ($0.00).
  International: cohort-guaranteed rates; a new student ("began studies
  Sept 2026 or after") pays $797/credit. Post-baccalaureate international
  is also $797/credit; domestic post-baccalaureate pays the standard
  domestic credit rate. No separate international ABE/ESL rate is
  published, so the standard international rate is used there too.
Graduate tables (domestic 700-level, master's) and the co-op work-term
flat fee are skipped.

Annual figure = per-credit rate x 30 credits.
BC has one domestic rate (no in/out-of-province split).

Output: output/ufv_tuition.json
Requires: beautifulsoup4, curl_cffi
"""
import json
import re
import time
from pathlib import Path

URL = "https://www.ufv.ca/fees-and-payments/tuition-and-fees/"
ACADEMIC_YEAR = "2026-2027"
CREDITS_PER_YEAR = 30
YEAR_COL = "2026-2027"
NEW_COHORT = "Sept 2026 or after"


def fetch(url):
    from curl_cffi import requests
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, impersonate="chrome120", timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{1,2})?)", cell)
    return float(m.group(1).replace(",", "")) if m else None


def table_after(soup, heading_part):
    for h in soup.find_all(["h2", "h3"]):
        if heading_part in h.get_text(" ", strip=True):
            t = h.find_next("table")
            if t is not None:
                return t
    raise RuntimeError(f"no table after heading containing {heading_part!r}")


def tuition_per_credit(table, col_part):
    """'Tuition/credit' row value under the column whose header matches."""
    rows = [[re.sub(r"\s+", " ", c.get_text(" ", strip=True))
             for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
    col = next(i for i, h in enumerate(rows[0]) if col_part in h)
    for row in rows[1:]:
        if row and row[0].startswith("Tuition/credit"):
            return money(row[col])
    raise RuntimeError(f"Tuition/credit row not found (col {col_part!r})")


def main():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fetch(URL), "html.parser")
    dom_ug = tuition_per_credit(
        table_after(soup, "credit courses (100-400 level)"), YEAR_COL)
    dom_abe = tuition_per_credit(
        table_after(soup, "Adult Basic Education (ABE)"), YEAR_COL)
    dom_esl = tuition_per_credit(
        table_after(soup, "English Language Studies (ESL)"), YEAR_COL)
    intl_new = tuition_per_credit(
        table_after(soup, "International students"), NEW_COHORT)
    print(f"domestic UG={dom_ug}, ABE={dom_abe}, ESL={dom_esl}, "
          f"international (new cohort)={intl_new}")

    std_note = (f"Per-credit tuition x {CREDITS_PER_YEAR} credits; tuition "
                f"only, ancillary and student-union fees excluded.")
    specs = [
        ("Undergraduate Programs", dom_ug, intl_new, ""),
        ("Adult Basic Education (ABE)", dom_abe, intl_new,
         " Tuition-free for domestic students. No separate international "
         "ABE rate is published; the standard international rate is shown."),
        ("English Language Studies (ESL)", dom_esl, intl_new,
         " Tuition-free for domestic students. No separate international "
         "ESL rate is published; the standard international rate is shown."),
        ("Post-Baccalaureate Programs", dom_ug, intl_new,
         " Domestic post-baccalaureate pays the standard domestic credit "
         "rate; international post-baccalaureate is $797/credit."),
    ]

    entries = []
    for name, d_rate, i_rate, note in specs:
        entries.append({
            "universityId": "ufv",
            "universityName": "UFV",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": round(d_rate * CREDITS_PER_YEAR, 2),
                "international": round(i_rate * CREDITS_PER_YEAR, 2),
            },
            "comments": f"{std_note}{note}",
        })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "ufv_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:42]:42s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
