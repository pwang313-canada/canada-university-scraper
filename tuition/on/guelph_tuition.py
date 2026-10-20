#!/usr/bin/env python3
"""Scrape University of Guelph Fall 2026 / Winter 2027 undergraduate tuition.

Source: https://www.uoguelph.ca/registrar/finances-fees/tuition-fees/guelph-undergrad
Page is static HTML.

Three categories, all full-time (2.00+ credits), per semester x2 for the
Fall+Winter annual total:
  - "Tuition for Domestic Students (One Semester, All Cohorts)":
    Ontario column -> domestic-in-province, Non-Ontario -> domestic-out-province
  - "Tuition for International Students (One Semester)":
    Cohort 2026 column (new Fall 2026 entrants) -> international

Output: output/guelph_tuition.json in the shared tuition_summary format.

Usage:
    python guelph_tuition.py
Requires: nothing beyond the Python standard library.

Version: guelphTuitionV2 (3 categories: domestic-in-province, domestic-out-province, international).
"""

import html
import json
import os
import re
import urllib.request

URL = "https://www.uoguelph.ca/registrar/finances-fees/tuition-fees/guelph-undergrad"
OUT_PATH = os.path.join("output", "guelph_tuition.json")
ACADEMIC_YEAR = "2026-2027"
SECTION_MARKER = "Fall 2026, Winter 2027"
DOMESTIC_HEADING = "Tuition for Domestic Students (One Semester, All Cohorts)"
INTL_HEADING = "Tuition for International Students (One Semester)"
INTL_COHORT = "Cohort 2026"


def slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def base_name(name: str) -> str:
    """Strip parentheticals for cross-table matching (e.g. the two B.Eng rows)."""
    return re.sub(r"\s*\(.*?\)\s*", "", name).strip().lower()


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def table_after(page: str, heading: str) -> str:
    sec_start = page.find(SECTION_MARKER)
    if sec_start == -1:
        raise RuntimeError(f"Could not find section {SECTION_MARKER!r} - page layout may have changed")
    section = page[sec_start:]
    h = section.find(heading)
    if h == -1:
        raise RuntimeError(f"Could not find table heading {heading!r}")
    ts = section.find("<table", h)
    te = section.find("</table>", ts) + len("</table>")
    return section[ts:te]


def parse_rows(table: str):
    rows = re.findall(r"<tr.*?>(.*?)</tr>", table, re.S)
    out = []
    for r in rows:
        cells = [
            html.unescape(re.sub(r"<.*?>", "", c)).strip()
            for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", r, re.S)
        ]
        cells = [re.sub(r"\s+", " ", c) for c in cells]
        if cells and "program name" not in cells[0].lower():
            out.append(cells)
    return out


def money(cell: str) -> float:
    return float(cell.replace(",", "").replace("$", "").strip())


def main() -> None:
    print(f"Fetching {URL}")
    page = fetch(URL)

    # Domestic table: Program Name | Ontario | Non-Ontario
    # Kept as a list - the two B.Eng rows differ in Non-Ontario rates.
    domestic = []
    for cells in parse_rows(table_after(page, DOMESTIC_HEADING)):
        if len(cells) < 3:
            continue
        name = cells[0]
        try:
            domestic.append({
                "name": name,
                "ontario": round(money(cells[1]) * 2, 2),
                "non_ontario": round(money(cells[2]) * 2, 2),
            })
        except ValueError:
            print(f"  skip (no domestic figures): {name!r}")
    # Filter out graduate/diploma programs (not undergraduate).
    domestic = [
        d for d in domestic
        if not d["name"].startswith(("Doctor of", "Diploma"))
    ]
    print(f"  domestic rows: {len(domestic)}")

    # International table: Program Name | Cohort 2026 | Cohort 2025 | ...
    # Header row is needed to locate the Cohort 2026 column, so parse it raw.
    intl_table = table_after(page, INTL_HEADING)
    intl_header = re.findall(r"<tr.*?>(.*?)</tr>", intl_table, re.S)[0]
    header_cells = [
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<.*?>", "", c)).strip())
        for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", intl_header, re.S)
    ]
    try:
        cohort_idx = next(
            i for i, c in enumerate(header_cells) if INTL_COHORT.lower() in c.lower()
        )
    except StopIteration:
        raise RuntimeError(f"Could not find {INTL_COHORT!r} column")
    intl = {}
    for cells in parse_rows(intl_table):
        name = cells[0]
        try:
            intl[base_name(name)] = round(money(cells[cohort_idx]) * 2, 2)
        except (ValueError, IndexError):
            print(f"  skip (no {INTL_COHORT} figure): {name!r}")
    print(f"  international rows: {len(intl)}")

    entries = []
    for d in domestic:
        key = base_name(d["name"])
        # Strip the 'Bachelor of ' degree prefix; it is not the program name.
        prog_name = re.sub(r"^Bachelor( of)?\s+", "", d["name"]).strip()
        tuition = {
            "domestic-in-province": d["ontario"],
            "domestic-out-province": d["non_ontario"],
        }
        if key in intl:
            tuition["international"] = intl[key]
        else:
            print(f"  note: no international match for {d['name']!r}")
        entries.append(
            {
                "universityId": "guelph",
                "universityName": "Guelph",
                "programId": f"domestic-{slug(d['name'])}",
                "programName": prog_name,
                "academicYear": ACADEMIC_YEAR,
                "tuition": tuition,
                "comments": (
                    "Fall + Winter combined (per-semester full-time 2.00+ credits "
                    "x 2). International uses the Cohort 2026 column (new Fall 2026 "
                    "entrants). Guelph quotes tuition ONLY - compulsory fees are "
                    "listed separately on the same page (unlike Carleton, which "
                    "bundles them)."
                ),
            }
        )

    print(f"Parsed {len(entries)} programs")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")
    for e in entries:
        if "commerce" in e["programId"]:
            t = e["tuition"]
            print(f"  B.Comm: in-province={t['domestic-in-province']}, "
                  f"out-province={t['domestic-out-province']}, "
                  f"intl={t.get('international')}")


if __name__ == "__main__":
    main()
