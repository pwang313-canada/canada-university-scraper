#!/usr/bin/env python3
"""Scrape Lakehead University 2026-2027 undergraduate tuition by program.

Source: https://www.lakeheadu.ca/students/finances/student-fees/cost-estimator
The estimator is a Drupal Views form (GET). Flow:
  1. ?citizenship=domestic&level=undergraduate -> program <select> (62 tids)
  2. ?citizenship=domestic&level=undergraduate&field_uar_programs_tid=<tid>
     -> fee node links (/fees/undergraduate-fees/2026-2027/node/<id>)
  3. Each node has "Fees - Domestic" and "Fees - International" tables with
     Year | Tuition | Ancillary Fees | Total | ... columns (annual figures).

Three categories:
  - domestic-in-province  (Ontario):       "Fees - Domestic" Tuition
  - domestic-out-province (rest of Canada): same as above - Lakehead does NOT
    differentiate Ontario vs non-Ontario domestic rates (verified: the
    estimator returns identical nodes for both citizenship options)
  - international: "Fees - International" Tuition

Year 1 figures are preferred (planner compares first-year costs); if a degree
has no Year 1 row the lowest available year is used and noted.

Output: output/lakehead_tuition.json in the shared tuition_summary format.

Usage:
    python lakehead_tuition.py
Requires: nothing beyond the Python standard library.

Version: lakeheadTuitionV1
"""

import html
import json
import os
import re
import time
import urllib.request

BASE = "https://www.lakeheadu.ca"
ESTIMATOR = BASE + "/students/finances/student-fees/cost-estimator"
OUT_PATH = os.path.join("output", "lakehead_tuition.json")
ACADEMIC_YEAR = "2026-2027"
DELAY = 1.0  # seconds between requests


def slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def money(cell: str) -> float:
    return float(cell.replace(",", "").replace("$", "").strip())


def get_program_tids() -> list:
    """Step 2 of the estimator: (tid, program name) for undergrad programs."""
    page = fetch(f"{ESTIMATOR}?citizenship=domestic&level=undergraduate")
    m = re.search(
        r'<select[^>]*name="field_uar_programs_tid"[^>]*>(.*?)</select>', page, re.S
    )
    if not m:
        raise RuntimeError("Program select not found")
    opts = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', m.group(1))
    tids = []
    for tid, name in opts:
        name = html.unescape(name.strip())
        if tid and tid != "All" and name and name != "- Any -":
            tids.append((tid, name))
    return tids


def get_nodes_for_tid(tid: str) -> list:
    """Step 3: fee node URLs for one program tid. Returns [(node_id, degree)]."""
    page = fetch(
        f"{ESTIMATOR}?citizenship=domestic&level=undergraduate"
        f"&field_uar_programs_tid={tid}"
    )
    links = re.findall(
        r'<a[^>]+href="(/students/finances/student-fees/fees/undergraduate-fees/'
        r'2026-2027/node/(\d+))"[^>]*>(.*?)</a>',
        page,
    )
    out = []
    for href, node_id, txt in links:
        degree = html.unescape(re.sub(r"<[^>]+>", "", txt)).strip()
        if degree and node_id not in [n for n, _ in out]:
            out.append((node_id, degree))
    return out


def parse_node(node_id: str):
    """Returns (degree, [(year, domestic_tuition, intl_tuition)])."""
    page = fetch(
        f"{BASE}/students/finances/student-fees/fees/undergraduate-fees/"
        f"2026-2027/node/{node_id}"
    )
    title_m = re.search(r"<title>(.*?)</title>", page, re.S)
    degree = (
        html.unescape(title_m.group(1)).split("|")[0].strip() if title_m else node_id
    )

    # Split page into the domestic and international fee sections.
    rows_by_section = {}
    for section, label in (("fees-domestic", "dom"), ("fees-international", "intl")):
        i = page.find(section)
        if i == -1:
            continue
        # The table follows the section marker.
        ts = page.find("<table", i)
        te = page.find("</table>", ts) + len("</table>")
        table = page[ts:te]
        for r in re.findall(r"<tr.*?>(.*?)</tr>", table, re.S):
            cells = [
                html.unescape(re.sub(r"<.*?>", "", c)).strip()
                for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", r, re.S)
            ]
            if len(cells) < 2 or cells[0].lower() == "year":
                continue
            try:
                year = int(cells[0])
                tuition = money(cells[1])
            except ValueError:
                continue
            rows_by_section.setdefault(year, {})[label] = tuition

    rows = [
        (y, v.get("dom"), v.get("intl")) for y, v in sorted(rows_by_section.items())
    ]
    return degree, rows


def main() -> None:
    print("Step 1: program list")
    tids = get_program_tids()
    print(f"  {len(tids)} programs")

    print("Step 2: fee nodes per program")
    nodes = {}  # node_id -> degree
    for tid, name in tids:
        time.sleep(DELAY)
        for node_id, degree in get_nodes_for_tid(tid):
            nodes.setdefault(node_id, degree)
    print(f"  {len(nodes)} unique fee nodes")

    print("Step 3: fee tables")
    entries = []
    for n, (node_id, degree) in enumerate(sorted(nodes.items())):
        time.sleep(DELAY)
        deg, rows = parse_node(node_id)
        if not rows:
            print(f"  skip (no fee rows): {degree}")
            continue
        # Prefer Year 1; else lowest available year.
        year, dom, intl = rows[0]
        year_note = "" if year == 1 else f" (Year {year}; no Year 1 row published)"
        tuition = {}
        if dom is not None:
            tuition["domestic-in-province"] = dom
            tuition["domestic-out-province"] = dom
        if intl is not None:
            tuition["international"] = intl
        if not tuition:
            print(f"  skip (no tuition figures): {degree}")
            continue
        entries.append(
            {
                "universityId": "lakehead",
                "universityName": "Lakehead",
                "programId": f"domestic-{slug(degree)}",
                "programName": degree,
                "academicYear": ACADEMIC_YEAR,
                "tuition": tuition,
                "comments": (
                    f"Annual tuition from Lakehead's 2026-2027 fee schedule{year_note}. "
                    "Lakehead does not differentiate Ontario vs non-Ontario "
                    "domestic rates (same nodes for both). Tuition only; "
                    "ancillary fees listed separately on the fee page."
                ),
            }
        )
        if (n + 1) % 20 == 0:
            print(f"  ...{n + 1}/{len(nodes)}")

    print(f"Parsed {len(entries)} programs")
    # Deduplicate: different fee nodes can resolve to the same degree.
    seen = set()
    unique = []
    for e in entries:
        if e["programId"] not in seen:
            seen.add(e["programId"])
            unique.append(e)
    if len(unique) != len(entries):
        print(f"  removed {len(entries) - len(unique)} duplicate(s)")
    entries = unique
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")
    for e in entries[:5]:
        t = e["tuition"]
        print(f"  {e['programName'][:45]:45s} ON={t.get('domestic-in-province')}")


if __name__ == "__main__":
    main()
