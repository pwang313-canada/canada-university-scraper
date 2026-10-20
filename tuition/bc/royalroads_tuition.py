#!/usr/bin/env python3
"""Royal Roads University (RRU) undergraduate tuition scraper.
# MARKER: royalRoadsTuitionV1

Source: https://www.royalroads.ca/student-life/tuition-fees/search-tuition-fees
The search lists every program as a card (paginated, ~10 pages) with
Domestic / International tuition. Only Bachelor programs are kept
(RRU undergraduate degrees are 3rd-year-entry degree completions).

Two pricing shapes:
  - per credit (Environmental Practice): annual = rate x 30 credits.
  - flat figure: the TOTAL tuition for the two-year (60-credit) degree
    completion, so annual = total / 2. Cross-check: the international
    flat total $52,618 ~= $877/credit x 60 credits.
Ancillary fees and the tuition deposit are not tuition -- excluded.

Output: output/royalroads_tuition.json
Requires: beautifulsoup4, curl_cffi
"""
import json
import re
import time
from pathlib import Path

BASE = ("https://www.royalroads.ca/student-life/tuition-fees/"
        "search-tuition-fees")
ACADEMIC_YEAR = "2026-2027"
CREDITS_PER_YEAR = 30
PROGRAM_YEARS = 2


def fetch(url):
    from curl_cffi import requests
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, impersonate="chrome120", timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def amount(seg):
    """(value, is_per_credit) from a card's Domestic/International segment."""
    m = re.search(r"\$([\d,]+(?:\.\d{2})?)\s*(per credit)?", seg)
    return (float(m.group(1).replace(",", "")), bool(m.group(2))) if m else (None, False)


def collect_cards():
    from bs4 import BeautifulSoup
    cards = {}
    for page in range(30):
        soup = BeautifulSoup(fetch(f"{BASE}?page={page}"), "html.parser")
        arts = soup.find_all("article")
        if not arts:
            break
        new = 0
        for a in arts:
            text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            m = re.match(r"^(.*?)\s+Domestic\s+(.*?)\s+International\s+(.*?)\s*$",
                         text)
            if not m:
                continue
            title, dseg, iseg = (g.strip() for g in m.groups())
            if title in cards:
                continue
            dv, dpc = amount(dseg)
            iv, ipc = amount(iseg)
            if dv is None or iv is None:
                continue
            cards[title] = {"dom": dv, "dom_pc": dpc, "intl": iv, "intl_pc": ipc}
            new += 1
        print(f"page {page}: {len(arts)} cards, {new} new")
        if new == 0 and page > 0:
            break
        time.sleep(0.5)
    return cards


def annual(value, per_credit):
    return value * CREDITS_PER_YEAR if per_credit else value / PROGRAM_YEARS


def main():
    cards = collect_cards()
    print(f"total cards: {len(cards)}")

    entries = []
    for title in sorted(cards):
        if not title.startswith("Bachelor"):
            continue
        c = cards[title]
        if c["dom_pc"]:
            comments = (f"Priced per credit: domestic ${c['dom']:,.0f}/credit, "
                        f"international ${c['intl']:,.0f}/credit; annual = "
                        f"x {CREDITS_PER_YEAR} credits. Ancillary fees "
                        f"excluded.")
        else:
            comments = (f"RRU publishes the total tuition for the two-year "
                        f"(60-credit) degree completion: domestic "
                        f"${c['dom']:,.0f}, international ${c['intl']:,.0f}; "
                        f"annual = total / {PROGRAM_YEARS}. Ancillary fees "
                        f"excluded.")
        entries.append({
            "universityId": "royal-roads",
            "universityName": "Royal Roads",
            "programId": slug(title),
            "programName": title,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": round(annual(c["dom"], c["dom_pc"]), 2),
                "international": round(annual(c["intl"], c["intl_pc"]), 2),
            },
            "comments": comments,
        })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "royalroads_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:52]:52s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
