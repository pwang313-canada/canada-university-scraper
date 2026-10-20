#!/usr/bin/env python3
"""OCAD University 2026-2027 undergraduate tuition scraper.
# MARKER: ocadTuitionV1

Downloads the three official Fall/Winter fee-schedule PDFs, extracts the
"Course Tuition Fees" rows, and writes output/ocad_tuition.json in the
shared tuition schema (same shape as hearst_tuition_output.json).

OCAD prices by per-term credit load, not by flat annual rate. The reported
annual figure = 2.50-credit column x 2 terms (5.0 credits = standard
full-time Fall/Winter year). The assumption is stated in every comment.

Usage:
    python ocad_tuition.py            # one run: download PDFs + extract + summarize
    python ocad_tuition.py all        # same as above
    python ocad_tuition.py scrape     # download PDFs + extract raw tables only
    python ocad_tuition.py summarize  # raw tables -> output/ocad_tuition.json

Requires: pypdf  (pip install pypdf)
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
PDF_DIR = BASE / "pdfs"
OUT_DIR = BASE / "output"
RAW_JSON = OUT_DIR / "ocad_tuition_raw.json"
FINAL_JSON = OUT_DIR / "ocad_tuition.json"

PDFS = {
    "dom_bfa_ba": "https://www.ocadu.ca/sites/default/files/2026-06/"
                  "2026%2027%20FW%20UG%20DOM%20BFA%20BA%20Tuition%20Fee%20Schedule.pdf",
    "dom_bdes": "https://www.ocadu.ca/sites/default/files/2026-06/"
                "2026%2027%20FW%20UG%20DOM%20BDES%20Tuition%20Fee%20Schedule.pdf",
    "intl": "https://www.ocadu.ca/sites/default/files/2026-06/"
            "2026%2027%20FW%20UG%20INTL%20Tuition%20Fee%20Schedule.pdf",
}

CREDIT_COLS = ["0.25", "0.50", "0.75", "1.00", "1.50", "2.00", "2.50", "3.00"]
FULLTIME_COL = "2.50"  # standard full-time term load; annual = 2 terms

# Spot-check values straight from the PDFs (2.50-credit column).
EXPECTED_250 = {
    ("dom_bfa_ba", "new+returning"): 3085.00,
    ("dom_bdes", "2023+"): 4041.10,
    ("dom_bdes", "2022prior"): 3085.00,
    ("intl", "new+returning"): 15124.10,
}
EXPECTED_ISR_250 = 375.00  # international ISR levy at 2.50 credits


def download_pdfs() -> dict:
    PDF_DIR.mkdir(exist_ok=True)
    paths = {}
    for key, url in PDFS.items():
        dest = PDF_DIR / f"{key}.pdf"
        if not dest.exists():
            print(f"downloading {key} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                f.write(r.read())
        paths[key] = dest
        print(f"  {key}: {dest.stat().st_size} bytes")
    return paths


def pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is required: pip install pypdf")
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def parse_money_row(text: str, label: str) -> list:
    """Return list of (position, [values]) for every '<label> n n n...' row."""
    rows = []
    for m in re.finditer(re.escape(label) + r"((?:\s+[\d,]+\.\d{2})+)", text):
        vals = [float(v.replace(",", "")) for v in re.findall(r"[\d,]+\.\d{2}", m.group(1))]
        rows.append((m.start(), vals))
    return rows


def extract() -> dict:
    paths = download_pdfs()
    raw = {"credit_columns": CREDIT_COLS, "fulltime_column": FULLTIME_COL, "tables": {}}

    # --- Domestic BFA/BA + International: single table each ---
    for key in ("dom_bfa_ba", "intl"):
        text = pdf_text(paths[key])
        rows = parse_money_row(text, "Course Tuition Fees")
        assert rows, f"{key}: no tuition row found"
        assert all(r[1] == rows[0][1] for r in rows), f"{key}: inconsistent repeats"
        assert len(rows[0][1]) == 8, f"{key}: expected 8 columns"
        table = {"new+returning": dict(zip(CREDIT_COLS, rows[0][1]))}
        if key == "intl":
            isr = parse_money_row(text, "ISR Levy")
            assert isr, "intl ISR row missing"
            assert all(r[1] == isr[0][1] for r in isr), "intl ISR inconsistent repeats"
            assert len(isr[0][1]) == 8, "intl ISR column count"
            table["isr_levy"] = dict(zip(CREDIT_COLS, isr[0][1]))
        raw["tables"][key] = table

    # --- Domestic BDes: two cohorts (2023+ admits p.1, 2022/prior p.2) ---
    text = pdf_text(paths["dom_bdes"])
    h_new = text.find("2023 + NEW ADMIT")
    h_old = text.find("ADMIT YEAR 2022 + PRIOR")
    assert h_new != -1 and h_old != -1, "BDes cohort headers not found"
    rows = parse_money_row(text, "Course Tuition Fees")
    cohorts = {"2023+": [], "2022prior": []}
    for pos, vals in rows:
        assert len(vals) == 8, "BDes row column count"
        cohorts["2022prior" if pos > h_old else "2023+"].append(vals)
    assert cohorts["2023+"] and cohorts["2022prior"], "BDes missing cohort rows"
    for name, rs in cohorts.items():  # repeated tables on p.2 must agree
        assert all(r == rs[0] for r in rs), f"BDes {name}: inconsistent repeats"
    raw["tables"]["dom_bdes"] = {
        name: dict(zip(CREDIT_COLS, rs[0])) for name, rs in cohorts.items()
    }

    # --- spot checks against hand-read PDF values ---
    for (tkey, cohort), want in EXPECTED_250.items():
        got = raw["tables"][tkey][cohort][FULLTIME_COL]
        assert abs(got - want) < 0.01, f"spot check {tkey}/{cohort}: {got} != {want}"
    got_isr = raw["tables"]["intl"]["isr_levy"][FULLTIME_COL]
    assert abs(got_isr - EXPECTED_ISR_250) < 0.01, f"ISR spot check: {got_isr}"
    # linearity sanity: 0.50 col == 2x 0.25 col
    for tkey, table in raw["tables"].items():
        for cohort, cols in table.items():
            if cohort == "isr_levy":
                continue
            assert abs(cols["0.50"] - 2 * cols["0.25"]) < 0.01, f"{tkey}/{cohort} not linear"

    OUT_DIR.mkdir(exist_ok=True)
    RAW_JSON.write_text(json.dumps(raw, indent=1))
    print(f"wrote {RAW_JSON}")
    return raw


ENTRY_DEFS = [
    dict(programId="domestic-bfa-ba",
         programName="BFA/BA (new + returning students)",
         table="dom_bfa_ba", cohort="new+returning",
         note="Covers Bachelor of Fine Arts and Bachelor of Arts."),
    dict(programId="domestic-bdes-2023plus",
         programName="BDes (admitted 2023 or later)",
         table="dom_bdes", cohort="2023+",
         note="Bachelor of Design, 2023+ admits pay the higher BDes rate."),
    dict(programId="domestic-bdes-2022prior",
         programName="BDes (admitted 2022 or prior)",
         table="dom_bdes", cohort="2022prior",
         note="Bachelor of Design, 2022/prior admits grandfathered at the BFA/BA rate."),
]


def summarize() -> list:
    raw = json.loads(RAW_JSON.read_text()) if RAW_JSON.exists() else extract()
    # One international rate for every program (BFA/BA/BDes, new + returning).
    intl_per_term = raw["tables"]["intl"]["new+returning"][raw["fulltime_column"]]
    intl_annual = round(intl_per_term * 2, 2)
    entries = []
    for d in ENTRY_DEFS:
        cols = raw["tables"][d["table"]][d["cohort"]]
        per_term = cols[raw["fulltime_column"]]
        annual = round(per_term * 2, 2)
        comments = (
            f"{d['note']} Figure = 2.50-credit column (${per_term:,.2f}) x 2 terms "
            f"(5.0 credits = standard full-time Fall/Winter year). No Ontario / "
            f"out-of-province split - one Canadian domestic rate. International "
            f"students pay one rate across all programs (${intl_annual:,.2f}); ISR "
            f"levy ($750/year at full-time load) not included. Tuition ONLY; "
            f"ancillary fees (Access Copyright, Student Buildings, Wellness Centre, "
            f"etc.) and mandatory fees (Student Union, Xpace, health/dental) are "
            f"listed separately in the schedule and not included. Source: OCAD "
            f"2026/2027 Fall Winter fee schedule PDF ({d['table']})."
        )
        entries.append({
            "universityId": "ocad",
            "universityName": "OCAD University",
            "programId": d["programId"],
            "programName": d["programName"],
            "academicYear": "2026-2027",
            "tuition": {"domestic-in-province": annual, "international": intl_annual},
            "comments": comments,
        })
    FINAL_JSON.write_text(json.dumps(entries, indent=1))
    print(f"wrote {FINAL_JSON} ({len(entries)} entries)\n")
    for e in entries:
        t = e["tuition"]
        print(f'{e["programId"]:28s} dom ${t["domestic-in-province"]:>10,.2f}  intl ${t["international"]:>10,.2f}')
    return entries


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "scrape":
        extract()
    elif cmd == "summarize":
        summarize()
    elif cmd == "all":
        extract()
        summarize()
    else:
        sys.exit("usage: ocad_tuition.py [all|scrape|summarize]")
