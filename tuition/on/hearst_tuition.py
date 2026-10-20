#!/usr/bin/env python3
"""Scrape Universite de Hearst 2026-2027 undergraduate tuition.

Sources (static HTML, French):
  - https://uhearst.ca/droits-de-scolarite/etudiants-canadiens-1er-cycle/
    (Canadian students: per 3-credit course, by year of study)
  - https://uhearst.ca/droits-de-scolarite/etudiants-internationaux-1er-cycle/
    (International students: flat per-course rate + admin fee)

Hearst does NOT price by program - tuition is a flat per-course rate that
depends only on year of study (years 1-3: 601,80 $/course, year 4: 543,00 $/course).
Annual figures assume a full-time load of 10 courses/year (5/semester x 2).

Output: output/hearst_tuition.json in the shared tuition_summary format.

Usage:
    python hearst_tuition.py
Requires: nothing beyond the Python standard library.

Version: hearstTuitionV1
"""

import html
import json
import os
import re
import urllib.request

URL_DOMESTIC = "https://uhearst.ca/droits-de-scolarite/etudiants-canadiens-1er-cycle/"
URL_INTL = "https://uhearst.ca/droits-de-scolarite/etudiants-internationaux-1er-cycle/"
OUT_PATH = os.path.join("output", "hearst_tuition.json")
ACADEMIC_YEAR = "2026-2027"
COURSES_PER_YEAR = 10  # full-time: 5 courses/semester x 2 semesters


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def first_table(page: str) -> str:
    m = re.search(r"<table.*?</table>", page, re.S)
    if not m:
        raise RuntimeError("No table found - page layout may have changed")
    return m.group(0)


def money_fr(cell: str) -> float:
    """Parse French-format amounts like '601,80 $ par cours de 3 crédits'."""
    m = re.search(r"([\d\s\u00a0]+,\d+|\d+)", cell)
    if not m:
        raise ValueError(f"no amount in {cell!r}")
    c = m.group(1).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    return float(c)


def parse_domestic(page: str):
    """Returns [(year_label, per_course_rate)]."""
    rows = re.findall(r"<tr.*?>(.*?)</tr>", first_table(page), re.S)
    out = []
    for r in rows:
        cells = [
            html.unescape(re.sub(r"<.*?>", "", c)).strip()
            for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", r, re.S)
        ]
        if len(cells) < 2:
            continue
        label = re.sub(r"\s+", " ", cells[0])
        # Extract the year number: "1ère année", "2e année", ...
        ym = re.search(r"(\d)\s*(?:ère|e)\s*ann", label)
        if not ym:
            continue
        try:
            rate = money_fr(cells[1])
        except ValueError:
            print(f"  skip (no rate): {label!r} -> {cells[1]!r}")
            continue
        out.append((f"Year {ym.group(1)}", round(rate * COURSES_PER_YEAR, 2)))
    return out


def parse_intl(page: str) -> float:
    """International tuition per course (excludes the separate admin fee row)."""
    rows = re.findall(r"<tr.*?>(.*?)</tr>", first_table(page), re.S)
    for r in rows:
        cells = [
            html.unescape(re.sub(r"<.*?>", "", c)).strip()
            for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", r, re.S)
        ]
        if len(cells) < 2:
            continue
        label = re.sub(r"\s+", " ", cells[0]).lower()
        if "citoyennet" in label and "trang" in label:
            return round(money_fr(cells[1]) * COURSES_PER_YEAR, 2)
    raise RuntimeError("International tuition row not found")


def main() -> None:
    print(f"Fetching {URL_DOMESTIC}")
    domestic = parse_domestic(fetch(URL_DOMESTIC))
    print(f"  domestic years: {len(domestic)}")
    print(f"Fetching {URL_INTL}")
    intl_annual = parse_intl(fetch(URL_INTL))
    print(f"  international annual: {intl_annual}")

    entries = []
    for year_label, annual in domestic:
        slug = year_label.lower().replace(" ", "-")
        entries.append(
            {
                "universityId": "hearst",
                "universityName": "Hearst",
                "programId": f"domestic-{slug}",
                "programName": f"Domestic - {year_label}",
                "academicYear": ACADEMIC_YEAR,
                "tuition": {
                    "domestic-in-province": annual,
                    "international": intl_annual,
                },
                "comments": (
                    "Hearst prices by year of study, not by program "
                    f"({COURSES_PER_YEAR} courses/year at the per-course rate). "
                    "No Ontario/non-Ontario split - one Canadian rate. "
                    "Tuition only; ancillary fees (association, services, "
                    "Greenshield health/dental, tech fee) are per-course / "
                    "per-semester / per-year add-ons listed separately. "
                    "International students also pay 200 $/course admin fee "
                    "on top of tuition (not included in the figure)."
                ),
            }
        )

    print(f"Parsed {len(entries)} year entries")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName']}: domestic={t['domestic-in-province']}, "
              f"intl={t['international']}")


if __name__ == "__main__":
    main()
