#!/usr/bin/env python3
"""Refresh OUInfo scholarship data.
# scholarshipsV1

OUInfo's scholarship search (ouinfo.ca/scholarships/) is a gated
Gravity-Forms search with no public listing API, sitemap, or index page,
so fresh discovery is not possible. This script refreshes a known URL list:
it re-scrapes each scholarship detail page and updates the mutable fields,
keeping stable ids/codes intact.

Usage:
    python scholarships_refresh.py [input.json]
        input defaults to ./scholarships.json (array with a "url" field,
        e.g. "/scholarships/toronto-mississauga/some-award")
        -> output/scholarships.json (same schema, refreshed fields)

Fields refreshed per page: title, quantity, grade_range (text), value,
apply_needed ("1"/"0"), renewable ("1"/"0"), description.
Pages that fail keep their old row; failed URLs are reported at the end.
"""
import json
import os
import re
import sys
import time

try:
    from curl_cffi import requests
except ImportError:
    sys.exit("curl_cffi is required: pip install curl_cffi")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("beautifulsoup4 is required: pip install beautifulsoup4")

BASE = "https://ouinfo.ca"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-CA,en;q=0.9",
}

FIELD_RES = [
    ("quantity", r"Quantity\s+(.+?)\s+Grade Range"),
    ("grade_range", r"Grade Range\s+(.+?)\s+Value"),
    ("value", r"Value\s+(.+?)\s+Application Required"),
    ("apply_needed", r"Application Required\s+(Yes|No)"),
    ("renewable", r"Renewable\s+(Yes|No)"),
]


def fetch(url, session):
    for attempt in range(2):
        try:
            r = session.get(url, timeout=25, headers=HEADERS)
            if r.status_code == 200 and len(r.text) > 5000:
                return r.text
        except Exception:
            pass
        time.sleep(1.5)
    return None


def parse_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    text = main.get_text(" ", strip=True) if main else soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    out = {}
    for key, pat in FIELD_RES:
        m = re.search(pat, text)
        if m:
            out[key] = m.group(1).strip()
    # description = text after "Renewable Yes/No", minus trailing "More Information"
    m = re.search(r"Renewable\s+(?:Yes|No)\s+(.*)$", text)
    if m:
        desc = re.sub(r"\s*More Information\s*$", "", m.group(1)).strip()
        if desc:
            out["description"] = desc
    h1 = soup.find("h1")
    if h1:
        out["title"] = h1.get_text(" ", strip=True)
    more = soup.find("a", string=re.compile(r"More Information", re.I))
    if more and more.get("href"):
        out["source_url"] = more["href"]
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "scholarships.json"
    rows = json.load(open(src, encoding="utf-8"))
    print(f"loaded {len(rows)} scholarships from {src}")

    session = requests.Session()
    try:
        session.impersonate = "chrome120"
    except Exception:
        pass

    failed, updated = [], 0
    for i, row in enumerate(rows):
        url = row.get("url", "")
        full = url if url.startswith("http") else BASE + url
        html = fetch(full, session)
        if not html:
            failed.append(full)
            continue
        d = parse_detail(html)
        if not (d.get("quantity") or d.get("grade_range") or d.get("value")):
            failed.append(full + " (no fields parsed)")
            continue
        if d.get("title"):
            row["title"] = d["title"]
        if d.get("quantity"):
            row["quantity"] = d["quantity"]
        row["grade_range"] = d.get("grade_range", row.get("grade_range"))
        row["value"] = d.get("value", row.get("value"))
        if d.get("apply_needed"):
            row["apply_needed"] = "1" if d["apply_needed"] == "Yes" else "0"
        if d.get("renewable"):
            row["renewable"] = "1" if d["renewable"] == "Yes" else "0"
        if d.get("description"):
            row["description"] = d["description"]
        if d.get("source_url"):
            row["source_url"] = d["source_url"]
        updated += 1
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(rows)}...")
        time.sleep(0.4)

    os.makedirs("output", exist_ok=True)
    out = os.path.join("output", "scholarships.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print(f"wrote {out}: {updated} updated, {len(failed)} failed")
    for u in failed[:20]:
        print("  FAILED:", u)


if __name__ == "__main__":
    main()
