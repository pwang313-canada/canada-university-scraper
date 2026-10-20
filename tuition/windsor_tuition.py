#!/usr/bin/env python3
"""University of Windsor 2026-2027 first-year tuition.
# MARKER: windsorTuitionV1

Source: https://www.uwindsor.ca/finance/fee-estimator (official Tuition Fee
Estimator). Windsor publishes NO static tuition table -- the estimator is a
Drupal AJAX form, so these figures were collected from it directly
(2026-10-15) and are embedded below. Queries: Program=Undergraduate,
Load=Full Time, Term=Fall. Figures are the estimator's "Base Tuition" line
(tuition only; ancillaries excluded). The estimator states fees are per term,
so annual = per-term x 2.

If Windsor publishes a static schedule later, replace DATA with a live fetch.

Usage:
    python windsor_tuition.py scrape      # embed -> output/windsor_raw.json
    python windsor_tuition.py summarize   # raw -> output/windsor_tuition.json
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"

# per-TERM base tuition, collected 2026-10-15 from the official estimator
DATA = {
    # programId: (programName, ont_per_term, oop_per_term, intl_per_term)
    "arts-humanities": ("Arts, Humanities, Social Science",
                        2957.85, 3612.80, 16500.00),
    "business": ("Business",
                 5282.55, 5592.30, 19310.00),
    "computer-science": ("Computer Science",
                         4602.35, 5758.65, 18750.00),
    "economics": ("Economics",
                  3045.65, 3810.75, 18025.00),
    "engineering": ("Engineering",
                    5721.65, 6068.25, 22050.00),
    "science": ("Science",
                3045.65, 3810.75, 18025.00),
    "nursing": ("Nursing",
                2957.85, 3612.80, 21675.00),
}


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    p = OUT_DIR / "windsor_raw.json"
    p.write_text(json.dumps({
        "source": "https://www.uwindsor.ca/finance/fee-estimator",
        "collected": "2026-10-15",
        "note": ("Windsor has no static tuition table; figures collected from "
                 "the official interactive estimator (Program=Undergraduate, "
                 "Full Time, Fall). Per-term Base Tuition."),
        "per_term": {k: {"program": v[0], "ont": v[1], "oop": v[2], "intl": v[3]}
                     for k, v in DATA.items()},
    }, indent=1))
    print(f"wrote {p} ({len(DATA)} programs)")


def summarize():
    p = OUT_DIR / "windsor_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    per_term = json.loads(p.read_text())["per_term"]
    entries = []
    for pid, d in per_term.items():
        entries.append({
            "universityId": "windsor",
            "universityName": "University of Windsor",
            "programId": pid,
            "programName": d["program"],
            "academicYear": "2026-2027",
            "tuition": {
                "domestic-in-province": round(d["ont"] * 2, 2),
                "domestic-out-of-province": round(d["oop"] * 2, 2),
                "international": round(d["intl"] * 2, 2),
            },
            "comments":
                "First-year Base Tuition (tuition only; ancillaries excluded). "
                "Estimator quotes per term; annual = per-term x 2. Windsor "
                "publishes no static table -- figures collected 2026-10-15 "
                "from the official fee estimator. "
                "Source: uwindsor.ca finance fee-estimator.",
        })
    out = OUT_DIR / "windsor_tuition.json"
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
        sys.exit("usage: windsor_tuition.py scrape | summarize")

