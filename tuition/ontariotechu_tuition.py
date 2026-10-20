#!/usr/bin/env python3
"""Ontario Tech University 2026-2027 undergraduate tuition scraper.
# MARKER: ontarioTechTuitionV1

Scrapes three registrar pages (all 2026-2027):
  domestic (Ontario resident): .../domestic-student-tuition/undergraduate-domestic-tuition-2026-2027.php
  out-of-province domestic:    .../out-of-province-fees/index.php  (tables embedded)
  international:               .../international-student-tuition/undergraduate-international-tuition-2026-2027.php

Each page prices by program group x year of study. We take the FIRST-YEAR
row (rate for 2026-2027 new admits); upper years are grandfathered lower
rates for continuing students. Pre-Engineering is priced per 3-credit
course (not annual) and has no published out-of-province figure.

Usage:
    python ontariotechu_tuition.py scrape      # fetch pages + extract raw tables
    python ontariotechu_tuition.py summarize   # raw -> output/ontariotechu_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
RAW_JSON = OUT_DIR / "ontariotechu_tuition_raw.json"
FINAL_JSON = OUT_DIR / "ontariotechu_tuition.json"

URLS = {
    "domestic-in-province": "https://registrar.ontariotechu.ca/fees-and-payment/"
        "domestic-student-tuition/undergraduate-domestic-tuition-2026-2027.php",
    "domestic-out-of-province": "https://registrar.ontariotechu.ca/fees-and-payment/"
        "out-of-province-fees/index.php",
    "international": "https://registrar.ontariotechu.ca/fees-and-payment/"
        "international-student-tuition/undergraduate-international-tuition-2026-2027.php",
}

# (group id, keyword to match the program label, short program name)
GROUPS = [
    ("allied-health-arts-science", "allied health", "Allied Health / Arts / Science group"),
    ("computer-science", "computer science", "Computer Science group"),
    ("nursing-health-admin", "nursing", "Nursing / Health Administration group"),
    ("commerce", "commerce", "Commerce"),
    ("information-technology", "information technology", "Information Technology"),
    ("engineering", "engineering", "Engineering / Technology group"),
    ("pre-engineering", "pre-engineering", "Pre-Engineering"),
]

# Hand-read spot checks: (group, category) -> first-year figure.
EXPECTED = {
    ("allied-health-arts-science", "domestic-in-province"): 6102.46,
    ("allied-health-arts-science", "domestic-out-of-province"): 7272.11,
    ("allied-health-arts-science", "international"): 34148.27,
    ("computer-science", "domestic-in-province"): 8466.71,
    ("computer-science", "domestic-out-of-province"): 8466.72,
    ("computer-science", "international"): 37831.43,
    ("nursing-health-admin", "domestic-in-province"): 6222.69,
    ("nursing-health-admin", "domestic-out-of-province"): 7415.37,
    ("nursing-health-admin", "international"): 34821.14,
    ("commerce", "domestic-in-province"): 10358.00,
    ("commerce", "domestic-out-of-province"): 10550.42,
    ("commerce", "international"): 37877.47,
    ("information-technology", "domestic-in-province"): 9211.80,
    ("information-technology", "domestic-out-of-province"): 10977.41,
    ("information-technology", "international"): 42143.13,
    ("engineering", "domestic-in-province"): 11443.38,
    ("engineering", "domestic-out-of-province"): 11779.95,
    ("engineering", "international"): 46561.31,
    ("pre-engineering", "domestic-in-province"): 1144.34,
    ("pre-engineering", "international"): 4656.13,
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def parse_tables(doc: str) -> list:
    """Return [(program_label, first_year_cost, per_course)] per table."""
    tables = list(re.finditer(r"<table.*?</table>", doc, re.S | re.I))
    out, prev_end = [], 0
    for t in tables:
        gap = doc[prev_end:t.start()]
        txt = H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", gap))).strip()
        label = re.split(r"ancillary fees\s*\.?", txt, flags=re.I)[-1].strip(" .")
        cells = [H.unescape(c).replace("\xa0", " ").strip()
                 for c in re.sub(r"\|+", "|", re.sub(r"<[^>]+>", "|", t.group(0))).split("|")
                 if c.strip()]
        per_course = any("per 3-credit course" in c.lower() for c in cells)
        first = None
        for j, c in enumerate(cells):
            if c.lower().startswith("first") or c.lower().startswith("pre-engineering"):
                m = re.fullmatch(r"\$([\d,]+\.\d{2})", cells[j + 1])
                first = float(m.group(1).replace(",", ""))
                break
        assert first is not None, f"no first-year cost in table after {label[:60]!r}"
        out.append((label, first, per_course))
        prev_end = t.end()
    return out


def scrape() -> dict:
    raw = {"sources": URLS, "groups": {}}
    for cat, url in URLS.items():
        print(f"fetching {cat} ...")
        tables = parse_tables(fetch(url))
        print(f"  {len(tables)} tables")
        for gid, kw, _ in GROUPS:
            hits = [(lab, cost, pc) for lab, cost, pc in tables
                    if kw in lab.lower() and not (gid == "engineering" and "pre-engineering" in lab.lower())]
            if not hits:
                continue  # e.g. no out-of-province Pre-Engineering table
            costs = {c for _, c, _ in hits}
            assert len(costs) == 1, f"{cat}/{gid}: conflicting tables {costs}"
            lab, cost, per_course = hits[0]
            g = raw["groups"].setdefault(gid, {"label": lab, "per_course": per_course})
            assert g["per_course"] == per_course, f"{gid}: per-course mismatch"
            g[cat] = cost
    # spot checks against hand-read figures
    for (gid, cat), want in EXPECTED.items():
        got = raw["groups"][gid][cat]
        assert abs(got - want) < 0.01, f"spot check {gid}/{cat}: {got} != {want}"
    assert "domestic-out-of-province" not in raw["groups"]["pre-engineering"], \
        "unexpected out-of-province Pre-Engineering table"
    OUT_DIR.mkdir(exist_ok=True)
    RAW_JSON.write_text(json.dumps(raw, indent=1))
    print(f"wrote {RAW_JSON}")
    return raw


def summarize() -> list:
    raw = json.loads(RAW_JSON.read_text()) if RAW_JSON.exists() else scrape()
    entries = []
    for gid, _, pname in GROUPS:
        g = raw["groups"][gid]
        tuition = {k: v for k, v in g.items() if k in URLS}
        if gid == "pre-engineering":
            comments = (
                "Pre-Engineering is priced PER 3-CREDIT COURSE, not per year: "
                f"${tuition['domestic-in-province']:,.2f}/course domestic (Ontario), "
                f"${tuition['international']:,.2f}/course international. "
                "No out-of-province figure is published. Tuition only; ancillary fees separate."
            )
        else:
            notes = []
            if gid == "computer-science":
                notes.append("Note: the university publishes out-of-province CS at "
                             "$8,466.72 vs domestic $8,466.71 (1 cent difference, as published).")
            comments = (
                f"First-year rate for 2026-2027 new admits (based on 10 courses / "
                f"30 credit hours per year). Continuing students pay lower "
                f"grandfathered rates by year of entry (Second/Third/Fourth rows on "
                f"the source page). {' '.join(notes)}"
                f"Tuition ONLY; ancillary fees are separate and not included. "
                f"Sources: Ontario Tech registrar 2026-2027 domestic / out-of-province / "
                f"international undergraduate tuition pages."
            )
        entries.append({
            "universityId": "ontariotechu",
            "universityName": "Ontario Tech University",
            "programId": gid,
            "programName": pname,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments": comments.strip(),
        })
    FINAL_JSON.write_text(json.dumps(entries, indent=1))
    print(f"wrote {FINAL_JSON} ({len(entries)} entries)\n")
    for e in entries:
        t = e["tuition"]
        print(f'{e["programId"]:30s} ' + "  ".join(f"{k.split('-')[-1][:4]} ${v:>10,.2f}" for k, v in t.items()))
    return entries


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: ontariotechu_tuition.py [scrape|summarize]")

