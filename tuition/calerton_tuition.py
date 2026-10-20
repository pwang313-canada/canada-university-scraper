#!/usr/bin/env python3
"""Scrape Carleton Fall 2026 / Winter 2027 UNDERGRADUATE tuition, 3 categories.

Sources (each page's "Full-fee ... Undergraduate Status" table, First Year):
  f26w27-ug-ontario/       -> domestic-in-province
  f26w27-ug-other/          -> domestic-out-of-province
  f26w27-ug-international/  -> international
  (base: https://carleton.ca/studentaccounts/tuition-fees/fw-ug/)

The three pages are merged into one entry per program (Bachelor-level only;
no masters/PhD on these pages). Figures are already Fall + Winter combined
(full year), so no doubling.

Output: output/carleton_tuition.json in the shared tuition_summary format.

Usage:
    python calerton_tuition.py
Requires: nothing beyond the Python standard library.
"""

import html
import json
import os
import re
import urllib.request

BASE = "https://carleton.ca/studentaccounts/tuition-fees/fw-ug/"
URLS = {
    "domestic-in-province": BASE + "f26w27-ug-ontario/",
    "domestic-out-of-province": BASE + "f26w27-ug-other/",
    "international": BASE + "f26w27-ug-international/",
}
OUT_PATH = os.path.join("output", "carleton_tuition.json")
ACADEMIC_YEAR = "2026-2027"


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


def parse_table(page: str):
    """Return {program name: First Year figure} from the Full-fee table."""
    tables = re.findall(r"<table.*?</table>", page, re.S)
    target = None
    for t in tables:
        if "Full-fee" in t and "Undergraduate Status" in t:
            target = t
            break
    if target is None:
        raise RuntimeError("Could not find the Full-fee Undergraduate table")

    rows = re.findall(r"<tr.*?>(.*?)</tr>", target, re.S)
    entries = {}
    for r in rows:
        cells = [
            html.unescape(re.sub(r"<.*?>", "", c)).strip()
            for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", r, re.S)
        ]
        if len(cells) < 2 or not cells[0]:
            continue
        name, first_year = cells[0], cells[1]
        # Skip the header row and note rows (no figure).
        if "first year" in first_year.lower():
            continue
        amount = first_year.replace(",", "").replace("$", "").strip()
        try:
            entries[name] = float(amount)
        except ValueError:
            print(f"  skip (no First Year figure): {name!r} -> {first_year!r}")
    return entries


def make_entry(name, in_prov, out_prov, intl_fee):
    # Remove any 'Domestic -' style prefix up to the first letter of the
    # real program name: "Domestic -Bachelor of Health Sciences"
    # -> "Bachelor of Health Sciences".
    name = re.sub(r"^Domestic(?:\s*-\s*|\s+)", "", name).strip()
    tuition = {}
    if in_prov is not None:
        tuition["domestic-in-province"] = in_prov
    if out_prov is not None:
        tuition["domestic-out-of-province"] = out_prov
    if intl_fee is not None:
        tuition["international"] = intl_fee
    return {
        "universityId": "carleton",
        "universityName": "Carleton",
        "programId": f"domestic-{slug(name)}",
        "programName": name,
        "academicYear": ACADEMIC_YEAR,
        "tuition": tuition,
        "comments": (
            "Undergraduate (Bachelor-level), Fall + Winter combined "
            "(full year), full-fee (2.0+ billing hours/term), First Year. "
            "Carleton quotes include compulsory miscellaneous fees + UPASS "
            "(not tuition-only like the Brock fees estimator)."
        ),
    }


def main() -> None:
    tables = {}
    for category, url in URLS.items():
        print(f"Fetching [{category}] {url}")
        tables[category] = parse_table(fetch(url))
        print(f"  parsed {len(tables[category])} programs")

    ont = tables["domestic-in-province"]
    oth = tables["domestic-out-of-province"]
    intl = tables["international"]

    entries = []
    for name, in_prov in ont.items():
        # Bachelor-level only: skip post-bac diplomas, certificates,
        # and special (non-degree) rows.
        if not name.startswith("Bachelor"):
            print(f"  skip (not a Bachelor program): {name}")
            continue
        out_prov = oth.get(name)
        if out_prov is None:
            print(f"  warn: no out-of-province figure for {name!r}")
        intl_fee = intl.get(name)
        if intl_fee is None:
            print(f"  warn: no international figure for {name!r}")
        entries.append(make_entry(name, in_prov, out_prov, intl_fee))

    print(f"Merged {len(entries)} program entries")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")
    # Spot-check a few well-known programs.
    for e in entries:
        if e["programId"] in (
            "domestic-bachelor-of-computer-science",
            "domestic-bachelor-of-engineering",
            "domestic-bachelor-of-arts",
        ):
            t = e["tuition"]
            print(f"  {e['programName']}: "
                  f"{t.get('domestic-in-province')}/"
                  f"{t.get('domestic-out-of-province')}/"
                  f"{t.get('international')}")


if __name__ == "__main__":
    main()
