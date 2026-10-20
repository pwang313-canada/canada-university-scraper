#!/usr/bin/env python3
"""Scrape Nipissing University 2026-2027 undergraduate tuition by program.

Source: https://www.nipissingu.ca/student-financial-services/tuition-fees-term
Nipissing uses Drupal Views with exposed filters. Tuition is priced by FEE GROUP
(Arts and Science / BBA-BComm / Computer Science), not by individual program.

Strategy:
  1. Fetch the undergrad view with program=All for Ontario (student=5491,
     "Admitted in or After 2023-2024") and Out-of-Province (student=5501).
     Each returns 3 fee-group rows; take the 30-credit Tuition figure.
  2. For each program id, fetch its individual view page once to learn which
     fee group it belongs to.
  3. International comes from the separate International Tuition page
     (program=1, "All Undergrad programs") - a single flat rate.

Three categories:
  - domestic-in-province  (Ontario, admitted 2023-24+)
  - domestic-out-province (Canadian outside Ontario)
  - international         (flat rate for all undergrad)

Skips Post-Baccalaureate diplomas/certificates (ids 30-39, not bachelor's).

Output: output/nipissing_tuition.json in the shared tuition_summary format.

Usage:
    python nipissing_tuition.py
Requires: nothing beyond the Python standard library.

Version: nipissingTuitionV2 (full browser headers for Cloudflare)
"""

import gzip
import html
import json
import os
import re
import time
import urllib.request

BASE = "https://www.nipissingu.ca"
UG_VIEW = (BASE + "/studentsupports/student-financial-services/"
           "tuition-fees-payments/undergraduate-tuition-and-fees")
INTL_VIEW = (BASE + "/studentsupports/student-financial-services/"
             "tuition-fees-payments/international-tuition-and-fees")
OUT_PATH = os.path.join("output", "nipissing_tuition.json")
ACADEMIC_YEAR = "2026-2027"
DELAY = 0.6

SEMESTER_FW = "5476"          # Fall/Winter
STUDENT_ONTARIO = "5491"      # Admitted in or After 2023-2024
STUDENT_OUTPROV = "5501"      # Canadian Students Outside of Ontario

# Post-Baccalaureate diplomas/certificates - not bachelor's programs.
SKIP_IDS = {str(i) for i in range(30, 40)}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def slug(name: str) -> str:
    s = html.unescape(name).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", errors="replace")


def view_text(page: str) -> str:
    m = re.search(r'<div class="view-content[^"]*">(.*)', page, re.S)
    if not m:
        return ""
    t = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
    return re.sub(r"\s+", " ", t).strip()


def parse_groups(text: str) -> dict:
    """{group_key: 30-credit tuition} from a program=All view page."""
    groups = {}
    # Split into rows on the credit table headers
    for chunk in re.split(r"(Arts and Science|BBA/BCOMM|Computer Science)", text):
        pass
    # Simpler: find each "30 $X $Y" occurrence with its preceding group label
    # The view lists groups in order; match label -> 30-credit tuition.
    pattern = re.compile(
        r"(Arts and Science|BBA/BCOMM/College Partnership|"
        r"Computer Science/Data Science).*?30 \$([\d,\.]+) \$",
        re.S,
    )
    for m in pattern.finditer(text):
        label, amount = m.group(1), m.group(2)
        if "Arts and Science" in label:
            key = "artsci"
        elif "BBA" in label:
            key = "bba"
        else:
            key = "cs"
        groups[key] = float(amount.replace(",", ""))
    return groups


def group_of_program(pid: str) -> str:
    """Fetch a program's view page; return its fee-group key."""
    url = (f"{UG_VIEW}?semester={SEMESTER_FW}"
           f"&student={STUDENT_ONTARIO}&program={pid}")
    text = view_text(fetch(url))
    if "BBA/BCOMM" in text or "BBA/BComm" in text:
        return "bba"
    if "Computer Science/Data Science" in text:
        return "cs"
    if "Arts and Science" in text:
        return "artsci"
    raise RuntimeError(f"Could not determine group for program {pid}")


def get_programs() -> list:
    """(program_id, program_name) from the exposed filter."""
    page = fetch(UG_VIEW)
    m = re.search(r'<select[^>]*name="program"[^>]*>(.*?)</select>', page, re.S)
    if not m:
        raise RuntimeError("Program select not found")
    opts = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)', m.group(1))
    programs = []
    for pid, name in opts:
        name = html.unescape(name.strip())
        if pid and pid != "All" and pid not in SKIP_IDS and name:
            programs.append((pid, name))
    return programs


def main() -> None:
    print("Fetching program list")
    programs = get_programs()
    print(f"  {len(programs)} programs")

    print("Fetching Ontario group rates (program=All)")
    ont_groups = parse_groups(view_text(fetch(
        f"{UG_VIEW}?semester={SEMESTER_FW}"
        f"&student={STUDENT_ONTARIO}&program=All")))
    print(f"  {ont_groups}")
    time.sleep(DELAY)

    print("Fetching out-of-province group rates (program=All)")
    oop_groups = parse_groups(view_text(fetch(
        f"{UG_VIEW}?semester={SEMESTER_FW}"
        f"&student={STUDENT_OUTPROV}&program=All")))
    print(f"  {oop_groups}")
    time.sleep(DELAY)

    print("Fetching international flat rate")
    intl_text = view_text(fetch(f"{INTL_VIEW}?semester={SEMESTER_FW}&program=1"))
    m = re.search(r"30 \$([\d,\.]+) \$", intl_text)
    intl_rate = float(m.group(1).replace(",", "")) if m else None
    print(f"  international 30cr = {intl_rate}")

    entries = []
    for n, (pid, name) in enumerate(programs):
        time.sleep(DELAY)
        try:
            gkey = group_of_program(pid)
        except Exception as e:
            print(f"  ERROR mapping {name}: {e}")
            continue
        tuition = {"domestic-in-province": ont_groups[gkey]}
        if gkey in oop_groups:
            tuition["domestic-out-province"] = oop_groups[gkey]
        if intl_rate is not None:
            tuition["international"] = intl_rate
        entries.append(
            {
                "universityId": "nipissing",
                "universityName": "Nipissing",
                "programId": f"domestic-{slug(name)}",
                "programName": html.unescape(name),
                "academicYear": ACADEMIC_YEAR,
                "tuition": tuition,
                "comments": (
                    "Full-time annual tuition (30 credits, Fall/Winter) from "
                    "Nipissing's tuition-fee Views. Nipissing prices by fee "
                    "group (Arts and Science / BBA-BComm / Computer Science), "
                    "not per program; Tuition column only (ancillary fees, "
                    "insurance, bus pass excluded). Ontario rate is for "
                    "students admitted in/after 2023-2024. International is a "
                    "flat rate for all undergrad programs."
                ),
            }
        )
        if (n + 1) % 10 == 0:
            print(f"  ...{n + 1}/{len(programs)}")

    print(f"Parsed {len(entries)} programs")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")
    for e in entries:
        if "business" in e["programId"] or "computer-science" in e["programId"]:
            t = e["tuition"]
            print(f"  {e['programName'][:42]:42s} ON={t.get('domestic-in-province')}, "
                  f"OOP={t.get('domestic-out-province')}, intl={t.get('international')}")


if __name__ == "__main__":
    main()
