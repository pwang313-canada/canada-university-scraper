#!/usr/bin/env python3
"""Trent University 2026-2027 undergraduate tuition scraper.
# MARKER: trentTuitionV1

Source: trentu.ca/studentfinances/tuition-fees
Fees live on per-category pages (not the index):
  ont : .../peterborough-fall-2026-winter-2027-tuition-fees-ontario-students
  oop : .../peterborough-fall-2026-winter-2027-tuition-fees-out-province-students
  intl: .../peterborough-international-full-time-fall-2026-winter-2027-fees

Each page has per-program tables with a dedicated "Tuition" column
(tuition-only; Ancillary & Levy shown separately and excluded). We take the
"New - Fall 2026" row = new-student annual tuition.

Program mapping: ont splits CS/BBA/Data Science by cohort (2022 & Prior vs
2023+); new students use the 2023+ cohort. intl lists only programs priced
differently from the base (Nursing, BEd, Certificate); everything else falls
under "All Other Undergraduate Programs" -- applied explicitly and noted.

Post Graduate Certificates / Certificate Program are not undergrad degrees
and are skipped.

Usage:
    python trent_tuition.py scrape      # fetch pages -> output/trent_raw.json
    python trent_tuition.py summarize   # raw -> output/trent_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"

URLS = {
    "ont": "https://www.trentu.ca/studentfinances/peterborough-fall-2026-winter-2027-tuition-fees-ontario-students",
    "oop": "https://www.trentu.ca/studentfinances/peterborough-fall-2026-winter-2027-tuition-fees-out-province-students",
    "intl": "https://www.trentu.ca/studentfinances/peterborough-international-full-time-fall-2026-winter-2027-fees",
}

# (programId, programName, ont_label, oop_label, intl_label)
PROGRAMS = [
    ("software-engineering", "Software Engineering",
     "Software Engineering", "Software Engineering",
     "All Other Undergraduate Programs"),
    ("cs-bba-data-science",
     "Computer Science, Business Administration & Data Science",
     "Computer Science, Bachelor of Business Administration & Data Science (2023 + Cohort)",
     "Computer Science, Bachelor of Business Administration & Data Science",
     "All Other Undergraduate Programs"),
    ("education", "Bachelor of Education",
     "Bachelor of Education", "Bachelor of Education",
     "Bachelor of Education"),
    ("nursing", "Nursing (Collaborative & Compressed)",
     "Nursing Collaborative & Compressed", "Nursing Collaborative & Compressed",
     "Nursing Collaborative & Compressed"),
    ("accounting-economics", "BA Honours in Accounting / Economics",
     "BA Honours in Accounting Economics", "BA Honours in Accounting Economics",
     "All Other Undergraduate Programs"),
    ("all-other", "All Other Undergraduate Programs",
     "All Other Undergraduate Programs", "All Other Undergraduate Programs",
     "All Other Undergraduate Programs"),
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def money(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{2})?)", cell or "")
    return float(m.group(1).replace(",", "")) if m else None


def parse_page(doc):
    """Return {program_label: new-student tuition}."""
    parts = re.split(r"(<table.*?</table>)", doc, flags=re.S | re.I)
    out = {}
    for i, p in enumerate(parts):
        if not p.startswith("<table"):
            continue
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", p, re.S | re.I)
        hdr = [H.unescape(re.sub(r"<[^>]+>", " ", x)).strip()
               for x in re.split(r"</t[dh][^>]*>", rows[0])]
        if "Tuition" not in " ".join(hdr):
            continue
        tidx = hdr.index("Tuition")
        # label = nearest preceding <summary> accordion title
        prev = parts[i - 1]
        summaries = re.findall(r"<summary>(.*?)</summary>", prev, re.S | re.I)
        label = H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", summaries[-1]))).strip() \
            if summaries else "?"
        # strip "Peterborough Undergraduate Programs: " / "Programs: " prefixes
        label = re.sub(r"^(Peterborough Undergraduate Programs|Programs):\s*", "", label)
        for r in rows[1:]:
            cells = [H.unescape(re.sub(r"<[^>]+>", " ", x)).strip()
                     for x in re.split(r"</t[dh][^>]*>", r)]
            cells = [c.replace("\xa0", " ").strip() for c in cells if c.strip()]
            if cells and "New" in cells[0] and "Fall 2026" in cells[0]:
                out[label] = money(cells[tidx] if tidx < len(cells) else "")
                break
    return out


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    data = {}
    for cat, url in URLS.items():
        doc = fetch(url)
        parsed = parse_page(doc)
        print(f"{cat}: {len(parsed)} programs")
        for lbl in parsed:
            print(f"    {lbl[:58]:58s} {parsed[lbl]}")
        data[cat] = parsed
    p = OUT_DIR / "trent_raw.json"
    p.write_text(json.dumps({"urls": URLS, "fees": data}, indent=1))
    print(f"wrote {p}")


def summarize():
    p = OUT_DIR / "trent_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    fees = json.loads(p.read_text())["fees"]
    entries = []
    for pid, pname, ont_l, oop_l, intl_l in PROGRAMS:
        tuition = {}
        for cat, lbl in (("ont", ont_l), ("oop", oop_l), ("intl", intl_l)):
            v = fees[cat].get(lbl)
            assert v is not None, f"missing {cat} / {lbl!r}"
            tuition[{"ont": "domestic-in-province",
                     "oop": "domestic-out-of-province",
                     "intl": "international"}[cat]] = v
        note = ""
        if intl_l == "All Other Undergraduate Programs" and pid != "all-other":
            note = ("International figure from Trent's 'All Other Undergraduate "
                    "Programs' category (program not listed separately). ")
        entries.append({
            "universityId": "trent",
            "universityName": "Trent University",
            "programId": pid,
            "programName": pname,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                note +
                "New-student Fall 2026 annual tuition (Tuition column only; "
                "Ancillary & Levy fees excluded). CS/BBA/Data Science uses the "
                "2023+ cohort rate for new students. "
                "Source: trentu.ca studentfinances tuition-fees.",
        })
    out = OUT_DIR / "trent_tuition.json"
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
        sys.exit("usage: trent_tuition.py scrape | summarize")

