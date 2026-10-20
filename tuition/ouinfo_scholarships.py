#!/usr/bin/env python3
"""Retrieve OUInfo scholarships via the site's own JSON feed.

The https://ouinfo.ca/scholarships/ page is a JS-rendered shell; the real
data lives in the feed the page itself loads:
    https://ouinfo.ca/res/scholarships-en-ed<EDITION>.json
The edition number is read live from the page HTML, so this keeps working
when OUInfo rolls to a new edition.

Output: output/scholarships.json (raw feed, one JSON array).

Feed fields per scholarship:
    id, url, title, university_id, university, university_url,
    apply_needed ("1"/"0"), renewable, indigenous, equity_seeking,
    grade_range (coded 1-7), dollar_range (coded), quantity,
    value (e.g. "Variable", "$1,000"), deadline, html (tile markup)

Usage:
    python ouinfo_scholarships.py
Requires: nothing beyond the Python standard library.
"""

import json
import os
import re
import urllib.request

PAGE_URL = "https://ouinfo.ca/scholarships/"
FEED_URL = "https://ouinfo.ca/res/scholarships-en-ed{edition}.json"
OUT_PATH = os.path.join("output", "scholarships.json")


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def detect_edition(page_html: str) -> str:
    m = re.search(r'edition[":\\ ]+\"?(\d+)', page_html)
    if not m:
        raise RuntimeError("Could not detect feed edition from scholarships page")
    return m.group(1)


def main() -> None:
    print(f"Fetching {PAGE_URL}")
    page = fetch(PAGE_URL)
    edition = detect_edition(page)
    print(f"Detected edition: {edition}")

    feed_url = FEED_URL.format(edition=edition)
    print(f"Fetching {feed_url}")
    raw = fetch(feed_url)
    data = json.loads(raw)
    print(f"Retrieved {len(data)} scholarships")

    # Summary per university.
    counts: dict[str, int] = {}
    for s in data:
        counts[s.get("university", "?")] = counts.get(s.get("university", "?"), 0) + 1
    print("Top universities:")
    for uni, n in sorted(counts.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {uni}: {n}")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

