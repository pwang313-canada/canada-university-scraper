#!/usr/bin/env python3
"""University of Toronto St. George 2026-2027 undergrad tuition scraper.
# MARKER: uoftTuitionV1

Source: https://tuitionexplorer.registrar.utoronto.ca/index.php
A JS app backed by requests/getSearchFilters.php (filter metadata) and
server-rendered result pages. We query index.php directly:
  ?academicYear=2026-27&sessionType=1&studyLevel=UG&residency=DOM|NOR|INT
   &campus=UTSG&program=<id>
and read the "Program Fee" (tuition only; incidental/system-access/UHIP
columns excluded).

Residencies: DOM = Domestic (Ontario), NOR = Domestic (Non-Ontario),
INT = International.

We report FIRST-YEAR/entry rates per program. Arts & Science Year-2+
premiums (Commerce, Computer Science, Data Science) are separate entries
since they are materially different and stream-dependent.

Usage:
    python uoft_tuition.py scrape      # fetch all -> output/uoft_raw.json
    python uoft_tuition.py summarize   # raw -> output/uoft_tuition.json
"""
import html as H
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
URL = "https://tuitionexplorer.registrar.utoronto.ca/index.php"

# (programId, programName, faculty, uoft_program_id)
PROGRAMS = [
    ("engineering", "Engineering (BASc)", "Faculty of Applied Science & Engineering", 53),
    ("architecture", "Architectural Studies", "Daniels Faculty of Architecture", 18),
    ("arts-science", "Arts & Science (Year 1 admission)",
     "Faculty of Arts & Science", 207),
    ("commerce", "Commerce (Year 2+ specialist)",
     "Faculty of Arts & Science", 1),
    ("computer-science", "Computer Science (Year 2+ major/specialist)",
     "Faculty of Arts & Science", 169),
    ("data-science", "Data Science (Year 2+ specialist)",
     "Faculty of Arts & Science", 170),
    ("dentistry", "Dentistry (DDS)", "Faculty of Dentistry", 20),
    ("information", "Information (BI)", "Faculty of Information", 40),
    ("kinesiology", "Kinesiology (BKin)",
     "Faculty of Kinesiology and Physical Education", 39),
    ("law", "Law (JD)", "Faculty of Law", 21),
    ("medicine", "Medicine (MD)", "Temerty Faculty of Medicine", 22),
    ("music", "Music (BMus)", "Faculty of Music", 27),
    ("nursing", "Nursing (BScN)", "Lawrence Bloomberg Faculty of Nursing", 32),
    ("pharmacy", "Pharmacy (PharmD)", "Leslie Dan Faculty of Pharmacy", 33),
]

RESIDENCIES = [("DOM", "domestic-in-province"),
               ("NOR", "domestic-out-of-province"),
               ("INT", "international")]


def fetch_fee(pid, res):
    q = urllib.parse.urlencode({
        "academicYear": "2026-27", "sessionType": "1", "studyLevel": "UG",
        "residency": res, "campus": "UTSG", "program": pid})
    req = urllib.request.Request(URL + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        doc = r.read().decode("utf-8", "replace")
    for t in re.findall(r"<table.*?</table>", doc, re.S | re.I):
        if "Program Fee" in t and "Course Load" not in t:
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I)
            for r in rows[1:]:
                cells = [H.unescape(re.sub(r"<[^>]+>", " ", x)).strip()
                         for x in re.split(r"</t[dh][^>]*>", r)]
                cells = [c.replace("\xa0", " ").strip() for c in cells if c.strip()]
                if len(cells) >= 2:
                    m = re.search(r"\$([\d,]+\.\d{2})", cells[1])
                    if m:
                        return cells[0], float(m.group(1).replace(",", ""))
    raise ValueError(f"no program fee found for program={pid} residency={res}")


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    data = {}
    for pid, pname, faculty, upid in PROGRAMS:
        entry = {"programId": pid, "programName": pname, "faculty": faculty,
                 "uoftId": upid, "fees": {}}
        for res, key in RESIDENCIES:
            label, amount = fetch_fee(upid, res)
            entry["fees"][key] = {"label": label, "amount": amount}
            print(f"  {pid:18s} {key:24s} {amount:>10,.2f}  ({label[:45]})")
            time.sleep(0.4)
        data[pid] = entry
    p = OUT_DIR / "uoft_raw.json"
    p.write_text(json.dumps(data, indent=1))
    print(f"wrote {p}")


def summarize():
    p = OUT_DIR / "uoft_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    data = json.loads(p.read_text())
    entries = []
    for pid, pname, faculty, upid in PROGRAMS:
        e = data[pid]
        entries.append({
            "universityId": "uoft",
            "universityName": "University of Toronto (St. George)",
            "programId": pid,
            "programName": f"{pname} ({faculty})",
            "academicYear": "2026-2027",
            "tuition": {k: v["amount"] for k, v in e["fees"].items()},
            "comments":
                "Program Fee (tuition only) for 2026-27 Fall/Winter; incidental + "
                "system access fees and (intl) UHIP excluded. "
                "Source: tuitionexplorer.registrar.utoronto.ca.",
        })
    out = OUT_DIR / "uoft_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: uoft_tuition.py scrape | summarize")

