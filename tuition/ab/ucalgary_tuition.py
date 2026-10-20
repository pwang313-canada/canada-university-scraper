#!/usr/bin/env python3
"""University of Calgary undergraduate tuition scraper (2026-2027).

ucalgaryTuitionV1

Source: UCalgary Academic Calendar, section P.1.1 Undergraduate Tuition
(calendar.ucalgary.ca). The chart "Tuition Rates per Course for
Course-based Undergraduate Programs (effective Spring Term 2026)" is the
2026/27 schedule (UCalgary's tuition year runs Spring-Winter; the Board
approved +2% domestic / +4% international for 2026/27).

Model: tuition is charged per 3-unit course at the rate of the faculty
OFFERING the course. Annual figure = per-course rate x 10 courses
(30 units). Program-specific fees (Music, Dance, BDCI) are charged per
term in Fall and Winter on top of course tuition, so those programs get
their own entries: Most-Faculties annual + fee x 2 terms.

Per-term programs: Doctor of Medicine is assessed per term over three
terms a year (Fall/Winter/Spring) -> annual = per-term x 3. Doctor of
Veterinary Medicine is assessed Fall & Winter -> annual = per-term x 2
(Years 1-3 rate; Year 4 is split over three terms at the same annual
total). DVM publishes no international rate.

Skipped: Summer Law Institute, Foreign Trained Lawyers (program and
LWFT courses), PGME (residency), co-op/internship course rows, audit,
and minor-only program fees.

Output: output/ucalgary_tuition.json (entry-list schema, shared with
the other province scrapers; combine with combine_tuition.py).
"""

import json
import os
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

URL = "https://calendar.ucalgary.ca/pages/b15b7e973a234197aded0daf61f34b9a"
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "ucalgary"
UNIVERSITY_NAME = "University of Calgary"
COURSES_PER_YEAR = 10  # 30 units, 3 units per course

BASE_COMMENT = (
    "From the UCalgary Academic Calendar (P.1.1 Undergraduate Tuition), "
    "rates effective Spring Term 2026. Tuition is charged per 3-unit "
    "course at the rate of the faculty offering the course; annual = "
    "per-course rate x 10 courses (30 units). Tuition only; general "
    "fees excluded."
)


def money(text):
    text = text.strip()
    if not text or text.upper() == "N/A":
        return None
    return float(text.replace("$", "").replace(",", ""))


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def tables_after(soup, heading_text):
    """Return the first <table> following the element containing the text."""
    for el in soup.find_all(string=re.compile(re.escape(heading_text))):
        table = el.find_next("table")
        if table:
            return table
    return None


def rows(table):
    out = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if cells:
            out.append(cells)
    return out


def main():
    r = requests.get(URL, impersonate="chrome120", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # --- per-course rate groups -------------------------------------
    course_table = tables_after(soup, "Tuition Rates per Course")
    per_course = {}  # label -> (domestic, international) per 3-unit course
    for cells in rows(course_table):
        label = cells[0]
        if label.startswith("Home Faculty") or not cells[1].startswith("$"):
            continue  # header row, Audit row ('50% of course fee'), etc.
        dom, intl = money(cells[1]), money(cells[3]) if len(cells) > 3 else None
        if dom is not None:
            per_course[label] = (dom, intl)

    def annual(label):
        dom, intl = per_course[label]
        out = {"domestic-in-province": round(dom * COURSES_PER_YEAR, 2)}
        if intl is not None:
            out["international"] = round(intl * COURSES_PER_YEAR, 2)
        return out

    most = next(k for k in per_course if k.startswith("Most Faculties"))
    entries = []  # (programName, tuition dict, extra comment)

    entries.append((
        "All Other Undergraduate Programs",
        annual(most),
        " Most Faculties rate group: Arts, Science, Kinesiology, Social "
        "Work, School of Architecture, Planning and Landscape, and "
        "Cumming School of Medicine (BHSc and BCR only).",
    ))
    entries.append((
        "Business",
        annual("Haskayne School of Business"),
        " Haskayne School of Business course rate.",
    ))
    entries.append((
        "Engineering",
        annual("Schulich School of Engineering"),
        " Schulich School of Engineering course rate.",
    ))
    entries.append((
        "Nursing",
        annual("Nursing"),
        " Nursing course rate (international pays the Most Faculties rate).",
    ))
    entries.append((
        "Education",
        annual("Werklund School of Education"),
        " Werklund School of Education course rate (international pays "
        "the Most Faculties rate).",
    ))
    entries.append((
        "Law (Juris Doctor)",
        annual("Faculty of Law - Juris Doctor"),
        " Faculty of Law Juris Doctor course rate.",
    ))

    # --- per-term programs ------------------------------------------
    term_table = tables_after(soup, "Tuition Rates per Term")
    term_rates = {}
    for cells in rows(term_table):
        if cells[0] == "Program":
            continue
        dom = money(cells[2])
        intl = money(cells[3]) if len(cells) > 3 else None
        term_rates.setdefault(cells[0], (dom, intl))

    md_dom, md_intl = term_rates["Doctor of Medicine"]
    md = {"domestic-in-province": round(md_dom * 3, 2)}
    if md_intl is not None:
        md["international"] = round(md_intl * 3, 2)
    entries.append((
        "Doctor of Medicine",
        md,
        " MD is assessed per term over three terms a year (Fall, Winter "
        "and Spring); annual = per-term rate x 3.",
    ))

    dvm_dom, dvm_intl = term_rates["Doctor of Veterinary Medicine"]
    dvm = {"domestic-in-province": round(dvm_dom * 2, 2)}
    if dvm_intl is not None:
        dvm["international"] = round(dvm_intl * 2, 2)
    entries.append((
        "Doctor of Veterinary Medicine",
        dvm,
        " DVM is assessed per term in Fall and Winter (Years 1-3 rate; "
        "Year 4 is split over three terms at the same annual total). No "
        "international rate is published.",
    ))

    # --- program-specific fees (per term, Fall + Winter) ------------
    fee_table = tables_after(soup, "Additional Undergraduate Program-Specific Fees")
    base = annual(most)
    fee_programs = {
        "Bachelor of Music": "Bachelor of Music",
        "BA Music, Music minor": "BA Music",
        "BMUS/BEd concurrent program": "BMus/BEd Concurrent",
        "BFA Dance": "BFA Dance",
        "BA Dance": "BA Dance",
        "BA Dance/BKIN": "BA Dance/BKin",
        "BA Dance/BEd Concurrent Programs": "BA Dance/BEd Concurrent",
        "Bachelor of Design in City Innovation":
            "Bachelor of Design in City Innovation",
    }
    for cells in rows(fee_table):
        # Faculty name sits in a rowspan cell: the first row of a group
        # has 3 cells, continuation rows have only (program, fee).
        if len(cells) == 3 and cells[2].startswith("$"):
            label, fee = cells[1], money(cells[2])
        elif len(cells) == 2 and cells[1].startswith("$"):
            label, fee = cells[0], money(cells[1])
        else:
            continue
        if label not in fee_programs or fee is None:
            continue
        tuition = {
            k: round(v + fee * 2, 2) for k, v in base.items()
        }
        entries.append((
            fee_programs[label],
            tuition,
            f" Most Faculties rate plus the program fee of ${fee:,.2f} "
            "per term (Fall and Winter).",
        ))

    out = [
        {
            "universityId": UNIVERSITY_ID,
            "universityName": UNIVERSITY_NAME,
            "programId": slugify(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": tuition,
            "comments": BASE_COMMENT + extra,
        }
        for name, tuition, extra in sorted(entries, key=lambda e: e[0])
    ]

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "ucalgary_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(out)} entries to {path}")


if __name__ == "__main__":
    main()
