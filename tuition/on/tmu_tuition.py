#!/usr/bin/env python3
"""Toronto Metropolitan University 2026-2027 undergrad tuition scraper.
# MARKER: tmuTuitionV1

Source: https://www.torontomu.ca/current-students/tuition-fees/undergraduate/
Three "Total Fees" tables: Domestic Ontario / Domestic Out-of-Province /
International, each Program x Year 1..5+.

IMPORTANT: TMU publishes "Total Fees" = tuition + ancillary fees (page
states this explicitly). There is no tuition-only breakdown, so figures
are totals including ancillary -- flagged in every comment (same caveat
as the Carleton scraper).

We emit ONE entry per program at the YEAR-1 rate.

Usage:
    python tmu_tuition.py scrape      # fetch page -> output/tmu_raw.json
    python tmu_tuition.py summarize   # raw -> output/tmu_tuition.json
"""
import html as H
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
URL = "https://www.torontomu.ca/current-students/tuition-fees/undergraduate/"

TABLES = [
    ("domestic-in-province", "Domestic Ontario Fee Rates"),
    ("domestic-out-of-province", "Domestic Out-of-Province Fee Rates"),
    ("international", "International Fee Rates"),
]


def urlopen_nossl(req, timeout=60):
    """urlopen that falls back to unverified SSL on certificate errors
    (outdated CA bundle / corporate SSL inspection on Windows)."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (ssl.SSLCertVerificationError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", e)
        if not isinstance(reason, ssl.SSLCertVerificationError):
            raise
        print("WARNING: SSL certificate verification failed; retrying with "
              "verification disabled. (Fix properly with: pip install -U certifi)",
              file=sys.stderr)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read()


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    return urlopen_nossl(req).decode("utf-8", "replace")


def clean_name(raw):
    name = re.sub(r"^\(google sheet\)\s*", "", raw).strip()
    name = re.sub(r"\s*\(external link\)\s*", "", name).strip()
    return re.sub(r"\s+", " ", name)


def money(cell):
    cell = cell.strip()
    if cell.upper() == "N/A" or not cell:
        return None
    m = re.search(r"\$([\d,]+(?:\.\d{2})?)", cell)
    return float(m.group(1).replace(",", "")) if m else None


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    doc = fetch()
    tables = re.findall(r"<table.*?</table>", doc, re.S | re.I)
    # locate the three Total Fees tables by preceding tab label
    data = {}
    for key, label in TABLES:
        idx = doc.find(label)
        assert idx > 0, f"tab {label!r} not found"
        # first <table> after the label
        m = re.search(r"<table.*?</table>", doc[idx:], re.S | re.I)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S | re.I)
        hdr = [H.unescape(re.sub(r"<[^>]+>", " ", x)).strip()
               for x in re.split(r"</t[dh][^>]*>", rows[0])]
        assert "Year 1" in hdr[1], f"unexpected header: {hdr[:3]}"
        n = 0
        for r in rows[1:]:
            cells = [re.sub(r"<[^>]+>", " ", x).strip()
                     for x in re.split(r"</t[dh][^>]*>", r)]
            cells = [H.unescape(x).replace("\xa0", " ").strip()
                     for x in cells if x.strip()]
            if not cells:
                continue
            name = clean_name(cells[0])
            data.setdefault(name, {})[key] = money(cells[1])
            n += 1
        print(f"{key}: {n} programs")
    p = OUT_DIR / "tmu_raw.json"
    p.write_text(json.dumps({"url": URL, "programs": data}, indent=1))
    print(f"wrote {p}")


def summarize():
    p = OUT_DIR / "tmu_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    data = json.loads(p.read_text())["programs"]
    entries = []
    for name in sorted(data):
        fees = data[name]
        if not any(fees.get(k) for k in ("domestic-in-province",
                                        "domestic-out-of-province",
                                        "international")):
            continue  # all N/A (e.g. Direct Entry variants)
        tuition = {k: v for k, v in fees.items() if v is not None}
        entries.append({
            "universityId": "tmu",
            "universityName": "Toronto Metropolitan University",
            "programId": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
            "programName": name,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                "Year-1 rate shown. NOTE: TMU publishes 'Total Fees' = tuition "
                "+ ancillary fees (no tuition-only breakdown); figures include "
                "ancillary. Source: torontomu.ca current-students tuition-fees "
                "undergraduate.",
        })
    out = OUT_DIR / "tmu_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: tmu_tuition.py scrape | summarize")
