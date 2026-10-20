#!/usr/bin/env python3
"""Scrape Laurentian University 2026-2027 full-time undergraduate tuition.

Source: https://laurentian.ca/academics/fees-financing/undergraduate-tuition
Page is static HTML but sits behind Incapsula - requires full browser headers
(a bare urllib User-Agent gets HTTP 403).

Takes the "Full-Time Undergraduate" section: for each program group, the
"Tuition and Fees for Ontario Residents" table -> domestic-in-province and the
"Tuition and Fees for Students from Out of Province" table -> domestic-out-province.
Uses the Tuition column only (not the incidental/association fee totals).

International tuition comes from the separate International Fees page
(/academics/fees-financing/international), same 5 program groups, "Total Tuition"
column (annual).

Output: output/laurentian_tuition.json in the shared tuition_summary format.

Usage:
    python laurentian_tuition.py
Requires: nothing beyond the Python standard library.

Version: laurentianTuitionV2 (adds international from /international page)
"""

import html
import json
import os
import re
import time
import urllib.request

URL = "https://laurentian.ca/academics/fees-financing/undergraduate-tuition"
URL_INTL = "https://laurentian.ca/academics/fees-financing/international"
OUT_PATH = os.path.join("output", "laurentian_tuition.json")
ACADEMIC_YEAR = "2026-2027"

# Full browser header set - Incapsula returns 403 for bare clients.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


def slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def clean(t: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t)).strip())


def money(cell: str) -> float:
    return float(cell.replace(",", "").replace("$", "").strip())


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        enc = resp.headers.get_content_charset() or "utf-8"
        # urllib handles gzip/deflate via Accept-Encoding automatically? No -
        # it does not decode. Handle it manually.
        import gzip

        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        elif resp.headers.get("Content-Encoding") == "deflate":
            import zlib

            raw = zlib.decompress(raw)
        return raw.decode(enc, errors="replace")


def parse_fulltime(page: str):
    # Scope to the Full-Time Undergraduate section (before Part-Time).
    ft = page.find("Full-Time Undergraduate")
    pt = page.find("Part-Time Undergraduate")
    if ft == -1:
        raise RuntimeError("Full-Time Undergraduate section not found")
    section = page[ft : pt if pt != -1 else len(page)]

    entries = []
    for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", section, re.S):
        group = clean(m.group(1))
        seg = section[m.end() : m.end() + 9000]
        tables = re.findall(r"<table.*?</table>", seg, re.S)[:2]
        if len(tables) < 2:
            print(f"  skip (expected 2 tables): {group}")
            continue
        tuitions = []
        for tb in tables:
            rows = re.findall(r"<tr.*?>(.*?)</tr>", tb, re.S)
            if len(rows) < 2:
                continue
            cells = [clean(c) for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", rows[1], re.S)]
            # Tuition is the 2nd column.
            try:
                tuitions.append(money(cells[1]))
            except (ValueError, IndexError):
                tuitions.append(None)
        ontario, out_prov = tuitions[0], tuitions[1]
        if ontario is None:
            print(f"  skip (no Ontario tuition): {group}")
            continue
        entries.append((group, ontario, out_prov))
    return entries


def parse_international(page: str):
    """Returns {group_name: annual_tuition} from the International Fees page."""
    out = {}
    for m in re.finditer(r"<h[234][^>]*>(.*?)</h[234]>", page, re.S):
        heading = clean(m.group(1))
        key = heading.lower()
        seg = page[m.end() : m.end() + 4000]
        tm = re.search(r"<table.*?</table>", seg, re.S)
        if not tm:
            continue
        rows = re.findall(r"<tr.*?>(.*?)</tr>", tm.group(0), re.S)
        if not rows:
            continue
        header = [clean(c) for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", rows[0], re.S)]
        # Undergrad tables have "Total Tuition" column; skip Masters/Doctoral/UHIP.
        if "Total Tuition" not in header:
            continue
        idx = header.index("Total Tuition")
        for r in rows[1:]:
            cells = [clean(c) for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", r, re.S)]
            if len(cells) <= idx:
                continue
            try:
                out[key] = (heading, money(cells[idx]))
                break  # one data row per undergrad table
            except ValueError:
                continue
    return out


def main() -> None:
    print(f"Fetching {URL}")
    page = fetch(URL)
    groups = parse_fulltime(page)
    print(f"Parsed {len(groups)} program groups")

    print(f"Fetching {URL_INTL}")
    time.sleep(5)  # Incapsula rate-limits rapid sequential requests
    intl = parse_international(fetch(URL_INTL))
    print(f"Parsed {len(intl)} international groups")

    entries = []
    for group, ontario, out_prov in groups:
        tuition = {"domestic-in-province": ontario}
        if out_prov is not None:
            tuition["domestic-out-province"] = out_prov
        gkey = group.lower()
        if gkey in intl:
            tuition["international"] = intl[gkey][1]
        else:
            print(f"  note: no international match for {group!r}")
        entries.append(
            {
                "universityId": "laurentian",
                "universityName": "Laurentian",
                "programId": f"domestic-{slug(group)}",
                "programName": group,
                "academicYear": ACADEMIC_YEAR,
                "tuition": tuition,
                "comments": (
                    "Full-time undergraduate annual tuition (Tuition column only; "
                    "incidental + association fees excluded). Engineering is "
                    "priced on 36 credits, others on 30. International from the "
                    "separate International Fees page (Total Tuition column)."
                ),
            }
        )

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:50]:50s} ON={t['domestic-in-province']}, "
              f"OOP={t.get('domestic-out-province')}")


if __name__ == "__main__":
    main()
