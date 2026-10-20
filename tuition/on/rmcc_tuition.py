#!/usr/bin/env python3
"""Royal Military College of Canada (RMC) 2026-2027 tuition scraper.
# MARKER: rmcTuitionV1

Source: https://www.rmc-cmr.ca/en/registrars-office/rmcc-academic-fees
Page states "Effective as of Sept 2025 (no change for AY 26/27)".

RMC is a federal military college: no Ontario vs out-of-province split, so
both domestic keys carry the same "Domestic" figure. Undergraduate tuition
is domestic-only (no international undergrad row; international figures on
the page are all graduate programs).

Undergraduate tables used:
  "Undergraduate Studies - Full-time": per-term Arts & Science $3,310 /
    Engineering $4,545 -> annual = per-term x 2.
  ROTP / UTPNCM cadets are fully subsidized (noted, not priced).
Graduate tables (Master's, Doctoral, MBA, MDS/MPA) are out of scope.

Usage:
    python rmc_tuition.py scrape      # fetch page -> output/rmc_raw.json
    python rmc_tuition.py summarize   # raw -> output/rmc_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
URL = "https://www.rmc-cmr.ca/en/registrars-office/rmcc-academic-fees"


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def money(cell):
    m = re.search(r"\$ ?([\d,]+(?:\.\d{2})?)", cell)
    return float(m.group(1).replace(",", "")) if m else None


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    doc = fetch()
    i = doc.find('id="tui"')
    assert i > 0, "tuition anchor not found"
    seg = doc[i:]
    parts = re.split(r"(<h[1-4][^>]*>.*?</h[34]>|<table.*?</table>)", seg, flags=re.S | re.I)
    cur, tables = None, {}
    for p in parts:
        if re.match(r"<h[1-4]", p, re.I):
            t = H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p))).strip()
            if t and len(t) < 120:
                cur = t
        elif p.strip().startswith("<table"):
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", p, re.S | re.I)
            hdr = [H.unescape(re.sub(r"<[^>]+>", " ", x)).strip()
                   for x in re.split(r"</t[dh][^>]*>", rows[0])]
            hdr = [x for x in hdr if x]
            data = []
            for r in rows[1:]:
                cells = [re.sub(r"<[^>]+>", " ", x).strip()
                         for x in re.split(r"</t[dh][^>]*>", r)]
                cells = [H.unescape(x).replace("\xa0", " ").strip()
                         for x in cells if x.strip()]
                if cells:
                    data.append(cells)
            if cur and data:
                tables[cur] = {"header": hdr, "rows": data}
    ug = {k: v for k, v in tables.items() if k.startswith("Undergraduate Studies")}
    print("undergrad tables:", list(ug))
    p = OUT_DIR / "rmc_raw.json"
    p.write_text(json.dumps({"url": URL, "tables": ug}, indent=1))
    print(f"wrote {p}")


def summarize():
    p = OUT_DIR / "rmc_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    tables = json.loads(p.read_text())["tables"]
    ft = tables["Undergraduate Studies - Full-time"]
    # header: Student Profile | Arts & Science - Per Term | Engineering - Per Term
    # find the Domestic row
    dom = next(r for r in ft["rows"] if r[0].lower().startswith("domestic"))
    arts_term, eng_term = money(dom[1]), money(dom[2])
    assert arts_term and eng_term, f"could not parse domestic row: {dom}"

    def entry(pid, pname, per_term):
        annual = round(per_term * 2, 2)
        return {
            "universityId": "rmc",
            "universityName": "Royal Military College of Canada",
            "programId": pid,
            "programName": pname,
            "academicYear": "2026-2027",
            "tuition": {
                "domestic-in-province": annual,
                "domestic-out-of-province": annual,
            },
            "comments":
                f"Full-time undergraduate {per_term:,.2f}/term x 2 terms. RMC is a "
                "federal military college: no Ontario/out-of-province differential, "
                "so both domestic keys carry the published Domestic figure. "
                "Undergraduate tuition is domestic-only (no international undergrad "
                "row published). ROTP/UTPNCM cadets are fully subsidized. "
                "Tuition only; ancillary/service fees separate. "
                "Source: rmc-cmr.ca registrars-office academic fees "
                "(no change for AY 26/27).",
        }

    entries = [
        entry("arts-science", "Arts & Science (Undergraduate, full-time)", arts_term),
        entry("engineering", "Engineering (Undergraduate, full-time)", eng_term),
    ]
    out = OUT_DIR / "rmc_tuition.json"
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
        sys.exit("usage: rmc_tuition.py scrape | summarize")

