#!/usr/bin/env python3
"""UNBC undergraduate tuition scraper.
# MARKER: unbcTuitionV1

Source: https://www.unbc.ca/programs-and-admissions/undergraduate/tuition-and-fees
UNBC publishes no rate table -- tuition comes from the page's own
calculator (a Drupal AJAX form). This script replays that form exactly
as a browser does: load the page, wait out the honeypot timer, then
submit every combination of the calculator's
  4 programs x 5 campuses x 2 student types
with a full-time load (5 courses fall + 5 winter + 0 summer
= 10 courses = 30 credits) and reads the "Tuition" row of each result.

Result (2026-2027): tuition is FLAT -- $6,240 domestic / $31,210
international for every program and campus. Only student fees vary by
campus (Prince George highest); fees are not tuition and are excluded,
with the per-program fee range noted in the comments. If a future run
finds tuition differing by campus, the script emits program-campus
entries instead of collapsing them.

Output: output/unbc_tuition.json
Requires: beautifulsoup4, curl_cffi
"""
import json
import re
import time
from pathlib import Path

URL = ("https://www.unbc.ca/programs-and-admissions/undergraduate/"
       "tuition-and-fees")
ACADEMIC_YEAR = "2026-2027"
HONEYPOT_WAIT = 8  # the form rejects submissions made < ~6s after load


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money(cell):
    m = re.search(r"\$([\d,]+(?:\.\d{1,2})?)", cell)
    return float(m.group(1).replace(",", "")) if m else None


class Calculator:
    def __init__(self):
        from curl_cffi import requests
        self.s = requests.Session(impersonate="chrome120")
        self.build_id = None
        self.honeypot = None
        self.options = {}  # field name -> [(value, label)]

    def load(self):
        from bs4 import BeautifulSoup
        page = self.s.get(URL, timeout=30).text
        soup = BeautifulSoup(page, "html.parser")
        form = soup.find("form", id="tuition-calculator-form-ug")
        self.build_id = form.find("input", {"name": "form_build_id"})["value"]
        self.honeypot = form.find("input", {"name": "honeypot_time"})["value"]
        labels = {l.get("for"): l.get_text(" ", strip=True)
                  for l in form.find_all("label")}
        for field in ("student_type_res", "program", "campus",
                      "housing", "meal", "transportation"):
            self.options[field] = [
                (i["value"], labels.get(i.get("id"), i["value"]))
                for i in form.find_all("input", {"name": field})
            ]
        print("waiting out the form honeypot...")
        time.sleep(HONEYPOT_WAIT)

    def submit(self, student, program, campus):
        import json as _json
        from bs4 import BeautifulSoup
        data = {
            "student_type_res": student, "program": program, "campus": campus,
            "num_courses_fall": "5", "num_courses_winter": "5",
            "num_courses_summer": "0",
            "housing": self._first("housing"), "meal": self._first("meal"),
            "transportation": self._first("transportation"),
            "url": "",
            "form_build_id": self.build_id,
            "form_id": "tuition_calculator_form_ug",
            "honeypot_time": self.honeypot,
            "_triggering_element_name": "op",
            "_triggering_element_value": "Calculate",
            "op": "Calculate",
        }
        r = self.s.post(URL + "?ajax_form=1&_wrapper_format=drupal_ajax",
                        data=data, timeout=30,
                        headers={"X-Requested-With": "XMLHttpRequest",
                                 "Referer": URL})
        txt = r.text
        if txt.startswith("<textarea>"):
            txt = txt[len("<textarea>"):].rsplit("</textarea>", 1)[0]
        tuition = fees = None
        for cmd in _json.loads(txt):
            if cmd.get("command") == "update_build_id":
                self.build_id = cmd["new"]
            body = cmd.get("data") or ""
            if "Tuition" in body:
                for tr in BeautifulSoup(body, "html.parser").find_all("tr"):
                    cells = [c.get_text(" ", strip=True)
                             for c in tr.find_all(["td", "th"])]
                    if cells and cells[0] == "Tuition":
                        tuition = money(cells[1])
                    if cells and cells[0] == "Student fees":
                        fees = money(cells[1])
        if tuition is None:
            raise RuntimeError(f"no tuition in response for "
                               f"{student}/{program}/{campus}")
        return tuition, fees

    def _first(self, field):
        # housing/meal/transportation don't affect the tuition row;
        # pick each group's lowest-cost option (listed first in the form)
        return self.options[field][0][0]


def main():
    calc = Calculator()
    calc.load()
    students = calc.options["student_type_res"]
    programs = calc.options["program"]
    campuses = calc.options["campus"]
    print(f"students={students}\nprograms={programs}\ncampuses={campuses}")

    # matrix[student_label][program_label][campus_label] = (tuition, fees)
    matrix = {}
    for s_val, s_label in students:
        matrix[s_label] = {}
        for p_val, p_label in programs:
            matrix[s_label][p_label] = {}
            for c_val, c_label in campuses:
                t, f = calc.submit(s_val, p_val, c_val)
                matrix[s_label][p_label][c_label] = (t, f)
                print(f"  {s_label:13s} {p_label[:34]:34s} {c_label[:24]:24s} "
                      f"tuition={t} fees={f}")
                time.sleep(0.7)

    dom_label = next(l for _, l in students if "Domestic" in l)
    intl_label = next(l for _, l in students if "International" in l)
    entries = []
    for _, p_label in programs:
        name = (p_label if p_label != "Other undergraduate program"
                else "Other Undergraduate Programs")
        dom_by_campus = matrix[dom_label][p_label]
        intl_by_campus = matrix[intl_label][p_label]
        dom_rates = {t for t, _ in dom_by_campus.values()}
        intl_rates = {t for t, _ in intl_by_campus.values()}
        dom_fees = [f for _, f in dom_by_campus.values()]
        fee_note = (f" Student fees (excluded) vary by campus: "
                    f"${min(dom_fees):,.0f}-${max(dom_fees):,.0f} domestic.")
        if len(dom_rates) == 1 and len(intl_rates) == 1:
            entries.append({
                "universityId": "unbc",
                "universityName": "UNBC",
                "programId": slug(name),
                "programName": name,
                "academicYear": ACADEMIC_YEAR,
                "tuition": {
                    "domestic-in-province": dom_rates.pop(),
                    "international": intl_rates.pop(),
                },
                "comments": "From UNBC's tuition calculator (5 courses fall "
                            "+ 5 winter = 30 credits). Tuition is the same "
                            "at all 5 campuses (Prince George, Fort St. John, "
                            "Quesnel, Terrace/Prince Rupert, Online)." + fee_note,
            })
        else:  # tuition started differing by campus: keep them separate
            for c_label in dom_by_campus:
                entries.append({
                    "universityId": "unbc",
                    "universityName": "UNBC",
                    "programId": slug(f"{name} {c_label}"),
                    "programName": f"{name} — {c_label}",
                    "academicYear": ACADEMIC_YEAR,
                    "tuition": {
                        "domestic-in-province": dom_by_campus[c_label][0],
                        "international": intl_by_campus[c_label][0],
                    },
                    "comments": "From UNBC's tuition calculator (5 courses "
                                "fall + 5 winter = 30 credits).",
                })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "unbc_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:46]:46s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
