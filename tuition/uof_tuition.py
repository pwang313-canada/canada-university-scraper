#!/usr/bin/env python3
"""Universite de l'Ontario francais (UOF) tuition scraper.
# MARKER: uofTuitionV1

Fetches https://uontario.ca/english/admissions/fees-and-tuition, parses the
CURRENT (first) tuition table, and writes output/uof_tuition.json in the
shared tuition schema.

The fees page stacks several years of tables; only the first table (3
columns: Ontario / non-Ontario Canadian / International) is scraped. The
page does NOT label that table's academic year, so the year is recorded
with an explicit caveat in comments.

Full-time standard: 16 credits/term x 2 terms = 32 credits (per request).

Usage:
    python uof_tuition.py scrape      # fetch page + extract raw table
    python uof_tuition.py summarize   # raw -> output/uof_tuition.json
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
RAW_JSON = OUT_DIR / "uof_tuition_raw.json"
FINAL_JSON = OUT_DIR / "uof_tuition.json"

URL = "https://uontario.ca/english/admissions/fees-and-tuition"
FULLTIME_CREDITS_PER_TERM = 16  # per request; page's own minimum is 9

# Hand-read from the page's current table (spot checks).
EXPECTED_PER_CREDIT = [246.00, 258.00, 444.00]


def fetch_text() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    text = re.sub(r"<[^>]+>", "|", html)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\|+", "|", text)


def scrape() -> dict:
    text = fetch_text()
    # Current table = first one headed "Canadian students living in Ontario".
    i = text.find("Canadian students living in Ontario")
    assert i != -1, "current tuition table header not found"
    seg = text[i:i + 2000]
    cells = [c.strip() for c in seg.split("|") if c.strip()]

    def row(label: str) -> list:
        j = cells.index(label)
        vals = []
        for c in cells[j + 1:j + 4]:
            m = re.fullmatch(r"\$([\d,]+(?:\.\d{2})?)", c)
            assert m, f"bad money cell {c!r} after {label!r}"
            vals.append(float(m.group(1).replace(",", "")))
        return vals

    per_credit = row("Cost per credit")
    per_course = row("Cost per 3-credit course")
    per_term5 = row("Cost per term of 5 courses")
    annual30 = row("Annual cost (2 terms of 5 courses per term)")

    # spot checks + cross-validation between the table's own rows
    assert per_credit == EXPECTED_PER_CREDIT, f"per-credit changed: {per_credit}"
    for got, want, name in ((per_course, [p * 3 for p in per_credit], "3-credit"),
                            (per_term5, [p * 15 for p in per_credit], "15-credit term"),
                            (annual30, [p * 30 for p in per_credit], "annual")):
        assert all(abs(g - w) < 0.01 for g, w in zip(got, want)), \
            f"{name} row inconsistent: {got} vs {want}"

    raw = {
        "source": URL,
        "columns": ["domestic-in-province", "domestic-out-of-province", "international"],
        "per_credit": per_credit,
        "fulltime_credits_per_term": FULLTIME_CREDITS_PER_TERM,
    }
    OUT_DIR.mkdir(exist_ok=True)
    RAW_JSON.write_text(json.dumps(raw, indent=1))
    print(f"wrote {RAW_JSON}")
    return raw


def summarize() -> list:
    raw = json.loads(RAW_JSON.read_text()) if RAW_JSON.exists() else scrape()
    n = raw["fulltime_credits_per_term"] * 2  # 32 credits/year
    cols = raw["columns"]
    annual = {k: round(v * n, 2) for k, v in zip(cols, raw["per_credit"])}
    comments = (
        "YEAR CAVEAT: the UOF fees page does not label the academic year of its "
        "current tuition table (older tables on the same page are 2021-2022 and "
        "2022-2023); figures are the latest published rates, retrieved 2026-10-14. "
        f"Figure = cost-per-credit x {n} credits "
        f"({FULLTIME_CREDITS_PER_TERM} credits/term x 2 terms, per request; the page's "
        "own full-time minimum is 9 credits/term). One undergraduate rate for all "
        "programs. Tuition ONLY; ancillary fees ($16.67/credit) are billed separately "
        "and not included. International figure excludes mandatory UHIP health "
        "insurance (~$756/year). Source: " + URL
    )
    entries = [{
        "universityId": "uof",
        "universityName": "Universit\u00e9 de l'Ontario fran\u00e7ais",
        "programId": "undergraduate-all",
        "programName": "Undergraduate - all programs",
        "academicYear": "2026-2027",
        "tuition": annual,
        "comments": comments,
    }]
    FINAL_JSON.write_text(json.dumps(entries, indent=1))
    print(f"wrote {FINAL_JSON} ({len(entries)} entries)\n")
    for k, v in annual.items():
        print(f"{k:28s} ${v:>10,.2f}")
    return entries


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: uof_tuition.py [scrape|summarize]")

