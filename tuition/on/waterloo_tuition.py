#!/usr/bin/env python3
"""University of Waterloo 2026-2027 first-year tuition scraper.
# MARKER: waterlooTuitionV1

Source: https://uwaterloo.ca/future-students/financing/tuition
Three <details> sections (Ontario residents / outside Ontario or Canada /
International visa students), each with a first-year table:
  Faculty or program | Estimated tuition and incidental fees | Books...

IMPORTANT: Waterloo publishes "Estimated tuition and incidental fees"
(combined). No tuition-only breakdown, so figures include incidental fees --
flagged in every comment (same caveat as Carleton/TMU).

Usage:
    python waterloo_tuition.py scrape      # fetch page -> output/waterloo_raw.json
    python waterloo_tuition.py summarize   # raw -> output/waterloo_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
URL = "https://uwaterloo.ca/future-students/financing/tuition"

SECTIONS = [
    ("domestic-in-province", "living in Ontario"),
    ("domestic-out-of-province", "living outside of Ontario or Canada"),
    ("international", "International (visa) students"),
]


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def money(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{2})?)", cell or "")
    return float(m.group(1).replace(",", "")) if m else None


def clean_name(raw):
    name = re.sub(r"\s+", " ", raw).strip()
    name = re.sub(r"\s*/\s*", "/", name)  # normalize spacing around slashes
    return name


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    doc = fetch()
    data = {}
    for key, marker in SECTIONS:
        i = doc.find(marker)
        assert i > 0, f"section {marker!r} not found"
        m = re.search(r"<table.*?</table>", doc[i:], re.S | re.I)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S | re.I)
        n = 0
        for r in rows[1:]:
            cells = [re.sub(r"<[^>]+>", " ", x).strip()
                     for x in re.split(r"</t[dh][^>]*>", r)]
            cells = [H.unescape(x).replace("\xa0", " ").strip()
                     for x in cells if x.strip()]
            if not cells or len(cells) < 2:
                continue
            name = clean_name(cells[0])
            data.setdefault(name, {})[key] = money(cells[1])
            n += 1
        print(f"{key}: {n} programs")
    p = OUT_DIR / "waterloo_raw.json"
    p.write_text(json.dumps({"url": URL, "programs": data}, indent=1))
    print(f"wrote {p}")


def summarize():
    p = OUT_DIR / "waterloo_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    data = json.loads(p.read_text())["programs"]
    entries = []
    for name in sorted(data):
        fees = data[name]
        tuition = {k: v for k, v in fees.items() if v is not None}
        if not tuition:
            continue
        entries.append({
            "universityId": "waterloo",
            "universityName": "University of Waterloo",
            "programId": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60],
            "programName": name,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                "First-year estimate. NOTE: Waterloo publishes 'Estimated "
                "tuition and incidental fees' (combined); no tuition-only "
                "breakdown, so figures include incidental fees. Books/supplies "
                "excluded. Source: uwaterloo.ca future-students financing tuition.",
        })
    out = OUT_DIR / "waterloo_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")
    for e in entries[:6]:
        print(e["programName"][:45], e["tuition"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: waterloo_tuition.py scrape | summarize")

