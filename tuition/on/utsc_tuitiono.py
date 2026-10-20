#!/usr/bin/env python3
"""U of T Scarborough 2026-2027 undergraduate tuition scraper.
# MARKER: utscTuitionV1

Source: https://www.utsc.utoronto.ca/admissions/tuition-and-fees
Three tuition tables (Domestic-Ontario / Domestic-outside-Ontario /
International), each: Program x First Year Fee x Year 2 and up.
Incidental-fee and other-expense tables on the page are not tuition and
are skipped.

We emit ONE entry per program group at the FIRST-YEAR rate (entry-level);
Year 2+ figures are noted in comments.

Usage:
    python utsc_tuition.py scrape      # fetch page -> output/utsc_raw.json
    python utsc_tuition.py summarize   # raw -> output/utsc_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
URL = "https://www.utsc.utoronto.ca/admissions/tuition-and-fees"

TABLES = [
    ("domestic-in-province", "Domestic students - Ontario residents"),
    ("domestic-out-of-province", "Domestic students - outside Ontario"),
    ("international", "International students"),
]

PROGRAMS = [
    ("computer-science", "Computer Science"),
    ("management", "Management"),
    ("arts-science-general", "Arts, Science, all other programs"),
]


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def money(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{2})?)", cell)
    return float(m.group(1).replace(",", "")) if m else None


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    doc = fetch()
    tables = re.findall(r"<table.*?</table>", doc, re.S | re.I)
    data = {}
    for key, title in TABLES:
        found = None
        for t in tables:
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I)
            hdr = [H.unescape(re.sub(r"<[^>]+>", " ", x)).strip()
                   for x in re.split(r"</t[dh][^>]*>", rows[0])]
            hdr = [x for x in hdr if x]
            if hdr and hdr[0] == title:
                found = rows
                break
        assert found, f"table {title!r} not found"
        for r in found[1:]:
            cells = [re.sub(r"<[^>]+>", " ", x).strip()
                     for x in re.split(r"</t[dh][^>]*>", r)]
            cells = [H.unescape(x).replace("\xa0", " ").strip()
                     for x in cells if x.strip()]
            data.setdefault(cells[0], {})[key] = {
                "first_year": money(cells[1]), "year2_up": money(cells[2])}
    p = OUT_DIR / "utsc_raw.json"
    p.write_text(json.dumps({"url": URL, "programs": data}, indent=1))
    print(f"wrote {p} ({len(data)} programs)")


def summarize():
    p = OUT_DIR / "utsc_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    data = json.loads(p.read_text())["programs"]
    entries = []
    for pid, pname in PROGRAMS:
        d = data[pname]
        tuition = {k: v["first_year"] for k, v in d.items()}
        upper = ", ".join(f"{k} ${v['year2_up']:,.2f}" for k, v in d.items())
        entries.append({
            "universityId": "utsc",
            "universityName": "University of Toronto Scarborough",
            "programId": pid,
            "programName": pname,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                "First-year rate shown; Year 2 and up: " + upper + ". "
                "Tuition only; incidental/ancillary fees excluded. "
                "Source: utsc.utoronto.ca admissions tuition-and-fees.",
        })
    out = OUT_DIR / "utsc_tuition.json"
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
        sys.exit("usage: utsc_tuition.py scrape | summarize")

