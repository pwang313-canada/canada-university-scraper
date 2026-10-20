#!/usr/bin/env python3
"""U of T Mississauga 2026-2027 undergraduate tuition scraper.
# MARKER: utmTuitionV1

Source: https://www.utm.utoronto.ca/future-students/finances/tuition-fees
One table: Program (rowspan groups) x Category (Ontario Resident /
Non-Ontario Resident / International) x Fees ("$X (Year 1) $Y (Upper Year)").

We emit ONE entry per program group at the YEAR-1 rate (entry-level,
consistent with the St. George scraper); Upper Year figures are noted in
comments. Tuition only; incidental/residence/books excluded (separate
expense table on the page, not scraped).

Usage:
    python utm_tuition.py scrape      # fetch page -> output/utm_raw.json
    python utm_tuition.py summarize   # raw -> output/utm_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
URL = "https://www.utm.utoronto.ca/future-students/finances/tuition-fees"

CATEGORIES = {
    "Ontario Resident": "domestic-in-province",
    "Non-Ontario Resident": "domestic-out-of-province",
    "International": "international",
}

# (programId, short programName, full program list for comments)
GROUPS = [
    ("tech-specialists",
     "Computing & Technology specialists",
     "Bioinformatics (Specialist), Communication, Culture & Information "
     "Technology (Major), Computer Science (Major or Specialist), Digital "
     "Enterprise Management (Specialist), Health Sciences Communication, "
     "Information Security (Specialist), Technology, Coding & Society (Major), "
     "Visual Culture & Communication (Specialist)"),
    ("commerce-specialists",
     "Commerce & Management specialists",
     "Commerce (Major or Specialist), HR Management and Industrial Relations "
     "(Specialist), Management (Specialist)"),
    ("management-major",
     "Management (Major)",
     "Management (Major)"),
    ("arts-science-general",
     "All other Arts & Science programs",
     "All Remaining Arts Programs, All Remaining Science Programs"),
]


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def parse_fees(cell):
    """'$6,100 (Year 1) $11,420 (Upper Year)' -> {'Year 1': 6100.0, 'Upper Year': 11420.0}."""
    out = {}
    for m in re.finditer(r"\$([\d,]+(?:\.\d{2})?)\s*\(([^)]+)\)", cell):
        out[m.group(2).strip()] = float(m.group(1).replace(",", ""))
    return out


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    doc = fetch()
    t = re.findall(r"<table.*?</table>", doc, re.S | re.I)[0]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I)
    groups, cur = [], None
    for r in rows[1:]:
        cells = re.findall(r"<t[dh]([^>]*)>(.*?)</t[dh]>", r, re.S | re.I)
        texts = [H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b))).strip()
                 for _, b in cells]
        if "rowspan" in cells[0][0]:
            cur = {"programs": texts[0], "fees": {}}
            groups.append(cur)
            cat, fee = texts[1], texts[2]
        else:
            cat, fee = texts[0], texts[1]
        cur["fees"][cat] = parse_fees(fee)
    assert len(groups) == 4, f"expected 4 program groups, got {len(groups)}"
    p = OUT_DIR / "utm_raw.json"
    p.write_text(json.dumps({"url": URL, "groups": groups}, indent=1))
    print(f"wrote {p} ({len(groups)} groups)")


def summarize():
    p = OUT_DIR / "utm_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    groups = json.loads(p.read_text())["groups"]
    assert len(groups) == len(GROUPS)
    entries = []
    for (pid, pname, plist), g in zip(GROUPS, groups):
        tuition, upper = {}, {}
        for cat, key in CATEGORIES.items():
            fees = g["fees"][cat]
            tuition[key] = fees["Year 1"]
            if "Upper Year" in fees:
                upper[key] = fees["Upper Year"]
        comments = (
            f"Covers: {plist}. "
            "Year-1 rate shown; "
        )
        if upper:
            comments += ("upper-year rates: " + ", ".join(
                f"{k} ${v:,.2f}" for k, v in upper.items()) + ". ")
        comments += ("Tuition only; incidental fees, residence, books excluded. "
                     "Source: utm.utoronto.ca future-students finances tuition-fees.")
        entries.append({
            "universityId": "utm",
            "universityName": "University of Toronto Mississauga",
            "programId": pid,
            "programName": pname,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments": comments,
        })
    out = OUT_DIR / "utm_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")
    for e in entries:
        print(e["programId"], e["tuition"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: utm_tuition.py scrape | summarize")

