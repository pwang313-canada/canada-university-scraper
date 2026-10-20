#!/usr/bin/env python3
"""UBC undergraduate tuition scraper.
# MARKER: ubcTuitionV1

Source: https://students.ubc.ca/finances/tuition-fees/undergraduate-tuition-fees/

The page publishes, for 2026/27:
  - Domestic per-credit table (by program)
  - International per-credit table (by program)
  - Post-baccalaureate flat program fees (DMD, BEd, Law, MD, PharmD, ...)
  - Vantage College minimum program fees -- SKIPPED (separate pathway
    college, not direct-entry programs).

Annual figure = per-credit rate x 30 credits (the planner's standard year).
Each entry's comments record UBC's own first-year full course load and its
published full-load tuition when the load differs from 30 credits.

Domestic and international program names differ slightly on the page
("Applied Science (Year 1)" vs "Applied Science - Engineering",
"Land & Food Systems" vs "Land and Food Systems"); they are matched by a
normalized stem so each program ends up as ONE entry with both rates.
BC has one domestic rate (no in/out-of-province split).

Output: output/ubc_tuition.json
Requires: beautifulsoup4
"""
import json
import re
import urllib.request
from pathlib import Path

URL = ("https://students.ubc.ca/finances/tuition-fees/"
       "undergraduate-tuition-fees/")
ACADEMIC_YEAR = "2026-2027"
CREDITS_PER_YEAR = 30


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def stem(name):
    """Normalize a program name for domestic<->international matching."""
    s = re.sub(r"\(.*?\)", "", name)          # drop (Year 1), (Sauder ...)
    s = s.split(" – ")[0].split(" - ")[0]      # drop '- Engineering' suffix
    s = s.replace("&", "and")
    return re.sub(r"\s+", " ", s).strip().lower()


def money(cell):
    return float(cell.replace("$", "").replace(",", "").strip())


def table_after(soup, heading_text, tag="h3"):
    for h in soup.find_all(tag):
        if heading_text in h.get_text(" ", strip=True):
            return h.find_next("table")
    return None


def parse_per_credit(table):
    """{display name: (per-credit, first-year load, published full-load)}"""
    out = {}
    for tr in table.find_all("tr")[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        out[cells[0]] = (money(cells[1]), int(cells[2]), money(cells[3]))
    return out


def main():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fetch(URL), "html.parser")
    dom = parse_per_credit(table_after(soup, "Domestic student tuition amounts"))
    intl = parse_per_credit(table_after(soup, "International student tuition amounts"))
    print(f"per-credit rows: domestic={len(dom)}, international={len(intl)}")

    intl_by_stem = {stem(k): v for k, v in intl.items()}
    used_intl = set()

    entries = []
    for name, (per_credit, load, published) in dom.items():
        tuition = {"domestic-in-province": round(per_credit * CREDITS_PER_YEAR, 2)}
        key = stem(name)
        comments = f"Per-credit ${per_credit} x {CREDITS_PER_YEAR} credits. "
        if key in intl_by_stem:
            i_credit, i_load, i_published = intl_by_stem[key]
            used_intl.add(key)
            tuition["international"] = round(i_credit * CREDITS_PER_YEAR, 2)
            comments += f"International per-credit ${i_credit}. "
        if load != CREDITS_PER_YEAR:
            comments += (f"UBC first-year full course load is {load} credits "
                         f"(${published:,.2f} published). ")
        comments += "Tuition only."
        entries.append({
            "universityId": "ubc",
            "universityName": "UBC",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": tuition,
            "comments": comments,
        })

    for key, (per_credit, load, published) in intl_by_stem.items():
        if key not in used_intl:
            print(f"  note: international-only program stem {key!r}")

    # Post-baccalaureate flat program fees.
    pb_table = table_after(soup, "Post-baccalaureate programs", tag="h2")
    for tr in pb_table.find_all("tr")[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        name, dom_fee, intl_fee = cells[0], cells[2], cells[3]
        tuition = {}
        if dom_fee.lower() != "not applicable":
            tuition["domestic-in-province"] = money(dom_fee)
        if intl_fee.lower() != "not applicable":
            tuition["international"] = money(intl_fee)
        entries.append({
            "universityId": "ubc",
            "universityName": "UBC",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": tuition,
            "comments": "Post-baccalaureate program: flat annual program fee "
                        "as published. Tuition only.",
        })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "ubc_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:48]:48s} dom={t.get('domestic-in-province')} "
              f"intl={t.get('international')}")


if __name__ == "__main__":
    main()
