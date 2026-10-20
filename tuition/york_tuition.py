#!/usr/bin/env python3
"""York University 2026-2027 undergraduate tuition.
# MARKER: yorkTuitionV1

Source: https://students.yorku.ca/sfs/course-and-program-fees and the
per-faculty Fall/Winter 2026-2027 fee pages
(students.yorku.ca/sfs/fees/courses/2026-2027/fall-winter/...).

York blocks automated fetching, so figures were collected from the official
fee pages directly (2026-10-15) and are embedded below. Each faculty page
shows TUITION / supplementary / total; only the TUITION row is used
(supplementary fees excluded).

Most figures are PER CREDIT: annual = per-credit x 30 (full-time load).
Exceptions: Bachelor of Design is a fixed ANNUAL fee; Osgoode JD is a fixed
PER-TERM fee (annual = x 2). Figures are for the 2026 entry cohort
("entering September 9, 2026 or later").

Usage:
    python york_tuition.py scrape      # embed -> output/york_raw.json
    python york_tuition.py summarize   # raw -> output/york_tuition.json
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"

# (programId, programName, ont, oop, intl, basis)
# basis: "credit" = per-credit (annual = x30); "annual" = fixed yearly;
#        "term" = per-term (annual = x2). oop=None -> no out-of-province split.
DATA = [
    ("health", "Faculty of Health", 208.01, 236.08, 1352.45, "credit"),
    ("ampd-general", "AMPD - All Other Programs", 208.01, 236.08, 1352.45, "credit"),
    ("ampd-bdes", "AMPD - Bachelor of Design", 9179.50, 10418.06, 40573.81, "annual"),
    ("education", "Faculty of Education", 208.01, 236.08, 1275.90, "credit"),
    ("euc-general", "Environmental and Urban Change - All Other", 208.01, 236.08, 1352.45, "credit"),
    ("euc-bes", "EUC - Environmental Studies / Global Geography", 208.01, 236.08, 1392.66, "credit"),
    ("glendon-general", "Glendon - All Other Programs", 208.01, 236.08, 1276.98, "credit"),
    ("glendon-science", "Glendon - Biology, Mathematics", 208.01, 236.08, 1391.01, "credit"),
    ("glendon-econ", "Glendon - Economics, Business Economics", 208.01, 236.08, 1338.97, "credit"),
    ("lassonde-cs", "Lassonde - Computer Science / Digital Technologies", 294.00, 333.68, 1260.84, "credit"),
    ("lassonde-beng", "Lassonde - BEng", 325.44, 369.35, 1310.15, "credit"),
    ("laps-general", "LAPS - All Other Programs", 208.01, 236.08, 1314.18, "credit"),
    ("laps-tech", "LAPS - BDEM, BPA, Information Technology", 294.00, 333.68, 1402.69, "credit"),
    ("laps-bhr", "LAPS - Bachelor of Human Resources", 272.35, None, 1332.77, "credit"),
    ("laps-bcom", "LAPS - Bachelor of Commerce", 352.17, 367.24, 1422.54, "credit"),
    ("schulich-bba", "Schulich - BBA / iBBA", 352.17, 367.24, 1466.17, "credit"),
    ("science", "Faculty of Science", 208.01, 236.08, 1391.01, "credit"),
    ("osgoode-jd", "Osgoode Hall - Juris Doctor (JD)", 12649.15, 14355.86, 24437.38, "term"),
]


def annualize(value, basis):
    if value is None:
        return None
    if basis == "credit":
        return round(value * 30, 2)
    if basis == "term":
        return round(value * 2, 2)
    return round(value, 2)


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    p = OUT_DIR / "york_raw.json"
    p.write_text(json.dumps({
        "source": "https://students.yorku.ca/sfs/course-and-program-fees",
        "collected": "2026-10-15",
        "note": ("York blocks automated fetching; figures collected from the "
                 "official per-faculty Fall/Winter 2026-2027 fee pages. "
                 "TUITION row only (supplementary fees excluded). 2026 entry cohort."),
        "programs": [
            {"id": pid, "name": name, "ont": ont, "oop": oop,
             "intl": intl, "basis": basis}
            for pid, name, ont, oop, intl, basis in DATA
        ],
    }, indent=1))
    print(f"wrote {p} ({len(DATA)} programs)")


def summarize():
    p = OUT_DIR / "york_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    programs = json.loads(p.read_text())["programs"]
    entries = []
    for d in programs:
        tuition = {"domestic-in-province": annualize(d["ont"], d["basis"])}
        note = ""
        if d["oop"] is not None:
            tuition["domestic-out-of-province"] = annualize(d["oop"], d["basis"])
        else:
            note = "No out-of-province split; single domestic rate. "
        tuition["international"] = annualize(d["intl"], d["basis"])
        basis_note = {
            "credit": "Per-credit figure x 30 = full-time annual. ",
            "annual": "Fixed annual program fee. ",
            "term": "Per-term figure x 2 = annual. ",
        }[d["basis"]]
        entries.append({
            "universityId": "york",
            "universityName": "York University",
            "programId": d["id"],
            "programName": d["name"],
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                note + basis_note +
                "Tuition only (supplementary fees excluded). 2026 entry cohort "
                "(entering Sept 9, 2026 or later). Figures collected 2026-10-15 "
                "from York's official fee pages (automated fetching blocked). "
                "Source: students.yorku.ca/sfs/course-and-program-fees.",
        })
    out = OUT_DIR / "york_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")
    for e in entries[:5]:
        print(e["programId"], e["tuition"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: york_tuition.py scrape | summarize")

