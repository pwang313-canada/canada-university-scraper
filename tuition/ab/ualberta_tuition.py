#!/usr/bin/env python3
"""University of Alberta undergraduate tuition scraper (2026-2027).

ualbertaTuitionV1

Sources (both official, Office of the Registrar):
  1. Fall/Winter Tuition page (domestic model): tuition is charged per
     course by fee index -- index value $121.56, most 3-credit courses are
     fi=6 -> $729.36/course -> $7,293.60 for 30 credits. Some faculties
     charge a higher per-course rate (Engineering, Business, ...) and
     Law (JD) / Medicine (MD) add a program fee.
  2. Undergraduate Cost Calculator
     (costcalculator.registrar.ualberta.ca) -- the university's own
     estimator. Its per-program annual "Tuition" figure already reflects
     the real course mix + program fees, so it is used as the authority
     (it differs from the simple per-course x 10 math for Engineering,
     Business, Law, Medicine, Pharmacy).

International students pay a program-based GUARANTEED annual rate set at
admission (no per-course table exists); the calculator returns the
Fall 2026 cohort's Year 1 guaranteed tuition, used here as the
2026-2027 international figure.

The calculator is a Spring app: GET / sets a JSESSIONID cookie and the
page carries a CSRF token in <meta name="_csrf">, which must be sent as
the X-CSRF-TOKEN header on the POST /getfeesummary call.

Output: ualberta_tuition.json (entry-list schema, shared with the other
province scrapers; combine with combine_tuition.py).
"""

import json
import re
import sys

from bs4 import BeautifulSoup
from curl_cffi import requests

BASE = "https://costcalculator.registrar.ualberta.ca/costcalculator"
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "ualberta"
UNIVERSITY_NAME = "University of Alberta"

# Calculator faculty code -> display name (used to disambiguate program
# names that appear under more than one faculty with different rates).
FACULTY_NAMES = {
    "AH": "Agric, Life & Environ Sciences",
    "AR": "Arts",
    "AU": "Augustana",
    "BC": "Business",
    "PS": "Public Health",
    "ED": "Education",
    "EN": "Engineering",
    "NS": "Native Studies",
    "SA": "Faculté Saint-Jean",
    "PE": "Kinesiology, Sport, & Rec",
    "LA": "Law",
    "MH": "Medicine and Dentistry",
    "NU": "Nursing",
    "PH": "Pharmacy",
    "SC": "Science",
}

BASE_COMMENT = (
    "Annual tuition from UAlberta's official Undergraduate Cost Calculator "
    "(Fall/Winter). Domestic tuition is charged per course by fee index "
    "(2026-2027 index value $121.56; most 3-credit courses $729.36); the "
    "calculator figure reflects the program's actual course mix and any "
    "program fee. International is the Fall 2026 cohort's guaranteed "
    "annual rate (program-based, fixed at admission). Tuition only; "
    "non-instructional fees excluded."
)


def money(text):
    return float(text.replace("$", "").replace(",", "").strip())


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Calculator:
    def __init__(self):
        self.session = requests.Session(impersonate="chrome120")
        html = self.session.get(BASE + "/", timeout=30).text
        m = re.search(r'<meta name="_csrf" content="([^"]*)"', html)
        if not m:
            raise RuntimeError("CSRF token not found on calculator page")
        self.headers = {
            "Referer": BASE + "/",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-TOKEN": m.group(1),
        }

    def get_json(self, path):
        r = self.session.get(f"{BASE}/{path}", timeout=30, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def tuition(self, residency, faculty_code, program_code):
        """Annual tuition for one program, or None if not offered."""
        payload = {
            "startTermStatus": "No",
            "residency": residency,  # ALTA = Canadian, FORGN = international
            "housing": "off-campus",
            "facultyCode": faculty_code,
            "programCode": program_code,
        }
        r = self.session.post(
            f"{BASE}/getfeesummary", json=payload, timeout=30, headers=self.headers
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            # Domestic summary row: ['Tuition', '$ 7,293.60']
            # Intl guaranteed table: ['Tuition Fee', Y1, Y2, Y3, Y4, Total]
            if cells and cells[0] in ("Tuition", "Tuition Fee"):
                return round(money(cells[1]), 2)
        return None


def main():
    calc = Calculator()
    faculties = calc.get_json("getFacultyDomestic")

    # (faculty_code, description) -> {"dom": ..., "intl": ...}
    programs = {}
    for fac in faculties:
        code = fac["code"]
        for residency, path in (
            ("dom", f"getProgramDomestic/{code}"),
            ("intl", f"getProgramInternational/{code}/No"),
        ):
            for prog in calc.get_json(path):
                key = (code, prog["programDescrition"])
                rate = calc.tuition(
                    "ALTA" if residency == "dom" else "FORGN",
                    code,
                    prog["programCode"],
                )
                if rate is not None:
                    programs.setdefault(key, {})[residency] = rate
        print(f"{code} {fac['descrition']}: done", file=sys.stderr)

    # Fill a missing side when the whole faculty shares ONE rate on that
    # side (e.g. Engineering's general program is listed for domestic
    # only, and a few intl-only program labels lack a domestic twin --
    # every Engineering program costs the same, so the rate is known).
    filled = set()
    for (code, desc), rates in programs.items():
        for side in ("dom", "intl"):
            if side not in rates:
                faculty_rates = {
                    r[side]
                    for (c, _), r in programs.items()
                    if c == code and side in r
                }
                if len(faculty_rates) == 1:
                    rates[side] = faculty_rates.pop()
                    filled.add((code, desc, side))

    # Group by description: identical rates across faculties collapse to
    # one plain-named entry; differing rates get a faculty suffix.
    by_desc = {}
    for (code, desc), rates in programs.items():
        by_desc.setdefault(desc, []).append((code, rates))

    entries = []
    for desc, variants in sorted(by_desc.items()):
        rate_sets = {(r.get("dom"), r.get("intl")) for _, r in variants}
        if len(rate_sets) == 1:
            code, rates = variants[0]
            name, note_extra = desc, ""
            if len(variants) > 1:
                note_extra = (
                    " Listed under more than one faculty in the calculator "
                    "at the same rate."
                )
            entries.append((name, code, rates, note_extra))
        else:
            for code, rates in variants:
                name = f"{desc} ({FACULTY_NAMES.get(code, code)})"
                entries.append((name, code, rates, ""))

    out = []
    for name, code, rates, note_extra in sorted(entries, key=lambda e: e[0]):
        tuition = {}
        if rates.get("dom") is not None:
            tuition["domestic-in-province"] = rates["dom"]
        if rates.get("intl") is not None:
            tuition["international"] = rates["intl"]
        comments = BASE_COMMENT + note_extra
        if (code, name.split(" (")[0], "dom") in filled or (
            code,
            name.split(" (")[0],
            "intl",
        ) in filled:
            comments += (
                " One residency side is not listed separately in the "
                "calculator for this program label; the faculty-wide rate "
                "(identical for every program in the faculty) is used."
            )
        if "international" not in tuition:
            comments += (
                " No international rate in the cost calculator "
                "(program does not publish one)."
            )
        out.append(
            {
                "universityId": UNIVERSITY_ID,
                "universityName": UNIVERSITY_NAME,
                "programId": slugify(name),
                "programName": name,
                "academicYear": ACADEMIC_YEAR,
                "tuition": tuition,
                "comments": comments,
            }
        )

    with open("ualberta_tuition.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(out)} entries to ualberta_tuition.json")


if __name__ == "__main__":
    main()
