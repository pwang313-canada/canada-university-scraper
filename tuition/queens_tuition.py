#!/usr/bin/env python3
"""Queen's University 2026-2027 undergraduate tuition scraper.
# MARKER: queensTuitionV1

Source: https://www.queensu.ca/registrar/tuition-fees/undergraduate
All three categories (Ontario / Out-of-Province / International) live on the
ONE page in separate sections (#FW-Ontario, #FW-Oop, #FW-International), so a
single fetch gets everything.

Each section has per-faculty tables with a "Tuition" column = Fall/Winter
annual tuition (tuition only; SAL / Ancillary / UHIP columns excluded).

We emit ONE entry per program group at the ENTRY-LEVEL (first-year) rate:
upper-year bands (e.g. Commerce Years 3-4, Computing Year 5, Engineering
Year 6) and per-course Continuing Education (AQ/ABQ/NWT/PQP teacher PD) are
not separate entries; the main ones are noted in comments.

Usage:
    python queens_tuition.py scrape      # fetch page -> output/queens_raw.json
    python queens_tuition.py summarize   # raw -> output/queens_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
URL = "https://www.queensu.ca/registrar/tuition-fees/undergraduate"

SECTIONS = [
    ("ont", "domestic-in-province", 'id="FW-Ontario"'),
    ("oop", "domestic-out-of-province", 'id="FW-Oop"'),
    ("intl", "international", 'id="FW-International"'),
]

# (programId, programName, faculty, ont_row, oop_row, intl_row)
# row values are substrings matched against the table's Program cell.
PROGRAMS = [
    ("arts-science", "Arts & Science (all degrees excl. Computing)",
     "Faculty of Arts and Science",
     "All degrees (excluding Computing)", "All degrees (excluding Computing)",
     "All degrees (excluding Computing)"),
    ("computing", "Computing",
     "Faculty of Arts and Science",
     "Computing - Years 1-4", "Computing - Years 1-4", "Computing - Years 1-6"),
    ("arts-science-certificates", "Certificates in Arts & Science",
     "Faculty of Arts and Science",
     "Certificates in Arts & Science", "Certificates in Arts & Science",
     "Certificates in Arts & Science"),
    ("commerce", "Commerce",
     "Smith School of Business",
     "Commerce - Years 1-2", "Commerce - Years 1-2", "Commerce - Years 1-2"),
    ("business-certificate", "Certificate in Business",
     "Smith School of Business",
     "Certificate in Business", "Certificate in Business", "Certificate in Business"),
    ("education", "Education (Consecutive/Concurrent)",
     "Faculty of Education",
     "Consecutive/ Concurrent", "Consecutive/ Concurrent",
     "Concurrent - Years 1-3"),  # intl Consecutive (Summer Start) is the same $40,299
    ("engineering", "Engineering & Applied Science",
     "Smith Engineering",
     "Engineering & Applied Science", "Engineering & Applied Science",
     "Engineering & Applied Science - Years 1-5"),
    ("mining-btech", "Mining Engineering Technology (BTECH)",
     "Smith Engineering",
     "Mining Engineering Technology (BTECH)", "Mining Engineering Technology (BTECH)",
     "Mining Engineering Tech (BTECH)"),
    ("mining-certificate", "Certificate in Mining Technologies",
     "Smith Engineering",
     "Certificate in Mining Technologies", "Certificate in Mining Technologies",
     "Certificate in Mining Technologies"),
    ("health-sciences", "Health Sciences - On Campus",
     "Faculty of Health Sciences",
     "Health Sciences - On Campus", "Health Sciences - On Campus",
     "Health Sciences - On Campus Year 1"),
    ("health-sciences-distance", "Health Sciences - Distance",
     "Faculty of Health Sciences",
     "Health Sciences - Distance", "Health Sciences - Distance",
     "Health Sciences - Distance"),
    ("law", "Law",
     "Faculty of Law",
     "Law - Years 1-3", "Law - Years 1-3", "Law - Years 1-3"),
    ("law-certificate", "Certificate in Law",
     "Faculty of Law",
     "Certificate in Law", "Certificate in Law", "Certificate in Law"),
    ("medicine", "Medicine",
     "School of Medicine",
     "Medicine", "Medicine", "Medicine"),
    ("nursing", "Nursing",
     "School of Nursing",
     "Nursing", "Nursing", "Nursing - Years 1-5"),
    ("nursing-advanced-standing", "Nursing - Advanced Standing Track",
     "School of Nursing",
     "Nursing - Advanced Standing Track", "Nursing - Advanced Standing Track",
     "Nursing - Advanced Standing Track"),
]


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def parse_section(doc, anchor):
    """Return list of (faculty, program, tuition) for one #FW- section."""
    i = doc.find(anchor)
    assert i > 0, f"section {anchor} not found"
    j = len(doc)
    for _, _, other in SECTIONS:
        if other != anchor:
            k = doc.find(other, i + 1)
            if 0 < k < j:
                j = k
    seg = doc[i:j]
    parts = re.split(r"(<h[34][^>]*>.*?</h[34]>|<table.*?</table>)", seg, flags=re.S | re.I)
    cur, rows = None, []
    for p in parts:
        if re.match(r"<h[34]", p, re.I):
            t = H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p))).strip()
            if "Faculty" in t or "School" in t or "Engineering" in t:
                cur = re.sub(r"Faculty of Health Science$",
                             "Faculty of Health Sciences", t)
        elif p.strip().startswith("<table"):
            trs = re.findall(r"<tr[^>]*>(.*?)</tr>", p, re.S | re.I)
            hdr = [H.unescape(re.sub(r"<[^>]+>", " ", x)).strip()
                   for x in re.split(r"</t[dh][^>]*>", trs[0])]
            try:
                tidx = hdr.index("Tuition")
            except ValueError:
                continue
            for r in trs[1:]:
                cells = [re.sub(r"<[^>]+>", " ", x).strip()
                         for x in re.split(r"</t[dh][^>]*>", r)]
                cells = [H.unescape(x).replace("\xa0", " ").strip()
                         for x in cells if x.strip()]
                if not cells or tidx >= len(cells):
                    continue
                prog = re.sub(r"[\*\^]+$", "", cells[0]).strip()
                m = re.search(r"\$([\d,]+\.\d{2})", cells[tidx])
                if m:
                    rows.append((cur, prog, float(m.group(1).replace(",", ""))))
    return rows


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    doc = fetch()
    data = {}
    for cat, _, anchor in SECTIONS:
        rows = parse_section(doc, anchor)
        print(f"{cat}: {len(rows)} rows")
        data[cat] = [{"faculty": f, "program": p, "tuition": t} for f, p, t in rows]
    p = OUT_DIR / "queens_raw.json"
    p.write_text(json.dumps({"url": URL, "sections": data}, indent=1))
    print(f"wrote {p}")


def find_tuition(rows, faculty, needle):
    for r in rows:
        if r["faculty"] == faculty and needle in r["program"]:
            return r["tuition"]
    raise KeyError(f"no row for {faculty} / {needle!r}")


def summarize():
    p = OUT_DIR / "queens_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    data = json.loads(p.read_text())["sections"]
    entries = []
    for pid, pname, faculty, ont_n, oop_n, intl_n in PROGRAMS:
        tuition = {
            "domestic-in-province": find_tuition(data["ont"], faculty, ont_n),
            "domestic-out-of-province": find_tuition(data["oop"], faculty, oop_n),
            "international": find_tuition(data["intl"], faculty, intl_n),
        }
        entries.append({
            "universityId": "queens",
            "universityName": "Queen's University",
            "programId": pid,
            "programName": f"{pname} ({faculty})",
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                "Entry-level (first-year) Fall/Winter tuition for 2026-2027. "
                "Tuition only; SAL, ancillary fees and (intl) UHIP excluded. "
                "Upper-year bands are priced differently (see raw file). "
                "Source: queensu.ca/registrar/tuition-fees/undergraduate.",
        })
    # program-specific notes
    notes = {
        "computing": "Computing Year 5 is priced lower "
                     "(dom $6,396.00 / oop $7,774.20; intl single Years 1-6 rate).",
        "commerce": "Commerce Years 3-4 priced lower "
                    "(dom $15,102.90 / oop $18,896.70; intl Years 3-6 $55,308.60).",
        "engineering": "Intl Engineering Year 6 priced slightly lower ($57,637.02).",
        "health-sciences": "Intl On-Campus Years 2-5 priced lower ($33,774.90).",
        "education": "Intl Consecutive (Summer Start) is the same $40,299.00; "
                     "intl Concurrent Years 4/5 priced lower.",
    }
    for e in entries:
        if e["programId"] in notes:
            e["comments"] += " " + notes[e["programId"]]
    out = OUT_DIR / "queens_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: queens_tuition.py scrape | summarize")

