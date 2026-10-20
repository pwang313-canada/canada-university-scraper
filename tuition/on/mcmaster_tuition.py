#!/usr/bin/env python3
"""Scrape McMaster University 2026-2027 undergraduate tuition by program.

Source: https://future.mcmaster.ca/finances/cost-estimator/
The estimator is a WordPress AJAX form. Tuition comes from the
course_cost_func admin-ajax endpoint:
  POST /wp/wp-admin/admin-ajax.php
  action=course_cost_func, course=<id>, citizenship_status=<value>,
  attending=Full-Time, courseload=5

Three categories (citizenship_status values from the page):
  - "Canadian Citizen/Permanent Resident"          -> domestic-in-province
  - "Canadian/Permanent Resident (Non-Ontario)"    -> domestic-out-province
  - "Non-Canadian/International Visa Student"     -> international

Full-Time, 5 courses (full course load). Tuition only - the estimator's
living/residence/meal-plan options affect housing+food estimates, not tuition.

Skips non-degree programs: MELD Diploma (21) and STEP Program (22).

Output: output/mcmaster_tuition.json in the shared tuition_summary format.

Usage:
    python mcmaster_tuition.py
Requires: nothing beyond the Python standard library.

Version: mcmasterTuitionV1
"""

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request

ESTIMATOR = "https://future.mcmaster.ca/finances/cost-estimator/"
AJAX = "https://future.mcmaster.ca/wp/wp-admin/admin-ajax.php"
OUT_PATH = os.path.join("output", "mcmaster_tuition.json")
ACADEMIC_YEAR = "2026-2027"
DELAY = 0.7  # seconds between requests

CITIZENSHIPS = [
    ("Canadian Citizen/Permanent Resident", "domestic-in-province"),
    ("Canadian/Permanent Resident (Non-Ontario)", "domestic-out-province"),
    ("Non-Canadian/International Visa Student", "international"),
]

# Non-degree programs to skip.
SKIP_IDS = {"21", "22"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": ESTIMATOR,
}


def slug(name: str) -> str:
    s = html.unescape(name).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={**HEADERS, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def post_tuition(course_id: str, citizenship: str) -> float | None:
    data = urllib.parse.urlencode(
        {
            "action": "course_cost_func",
            "course": course_id,
            "citizenship_status": citizenship,
            "attending": "Full-Time",
            "courseload": "5",
        }
    ).encode()
    req = urllib.request.Request(
        AJAX,
        data=data,
        headers={
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    m = re.search(r"id='tuition-fee'>([\d,\.]+)<", body)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def get_courses() -> list:
    """(course_id, program_name) from the estimator page."""
    page = fetch(ESTIMATOR)
    m = re.search(r"<select id='course'[^>]*>(.*?)</select>", page, re.S)
    if not m:
        raise RuntimeError("Course select not found")
    opts = re.findall(r"<option value='([^']*)'[^>]*>([^<]*)", m.group(1))
    courses = []
    for cid, name in opts:
        name = html.unescape(name.strip())
        if cid and cid not in SKIP_IDS and name:
            courses.append((cid, name))
    return courses


def main() -> None:
    print("Fetching program list")
    courses = get_courses()
    print(f"  {len(courses)} programs")

    entries = []
    for n, (cid, name) in enumerate(courses):
        tuition = {}
        for citizenship, key in CITIZENSHIPS:
            time.sleep(DELAY)
            try:
                amount = post_tuition(cid, citizenship)
            except Exception as e:
                print(f"  ERROR {name} [{key}]: {e}")
                amount = None
            if amount is not None:
                tuition[key] = amount
            else:
                print(f"  no figure: {name} [{key}]")
        if not tuition:
            print(f"  skip (no figures at all): {name}")
            continue
        entries.append(
            {
                "universityId": "mcmaster",
                "universityName": "McMaster",
                "programId": f"domestic-{slug(name)}",
                "programName": html.unescape(name),
                "academicYear": ACADEMIC_YEAR,
                "tuition": tuition,
                "comments": (
                    "Full-time annual tuition from McMaster's Cost Estimator "
                    "(course_cost_func, 5 courses). Tuition only; living, "
                    "residence and meal plan selections do not affect tuition."
                ),
            }
        )
        if (n + 1) % 5 == 0:
            print(f"  ...{n + 1}/{len(courses)}")

    print(f"Parsed {len(entries)} programs")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")
    for e in entries:
        if "computer" in e["programId"] or "business" in e["programId"]:
            t = e["tuition"]
            print(f"  {e['programName'][:42]:42s} ON={t.get('domestic-in-province')}, "
                  f"OOP={t.get('domestic-out-province')}, intl={t.get('international')}")


if __name__ == "__main__":
    main()
