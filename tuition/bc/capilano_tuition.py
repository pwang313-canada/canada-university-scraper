#!/usr/bin/env python3
"""Capilano University tuition scraper.
# MARKER: capilanoTuitionV1

Source: https://www.capilanou.ca/admissions/fees--finances/tuition--fees/tuition--other-fees/

The page publishes a standard per-credit rate plus per-program surcharges
("Tuition Surcharges and Other Fees" section, 2026/27 academic year).
Annual figure = 30 credits x (standard rate + program-wide surcharge)
+ program-wide flat fees.

  standard rate:  domestic $152.62/cr, international $724.24/cr
  surcharge:      the "All ... courses" per-credit surcharge for the program
                  (max if lower/upper levels differ); if a program has no
                  "All" line, the max per-credit surcharge in its section.
  flat fees:      "additional fees of $X" on program-wide lines only.

Course-specific additional fees and "Approximate other costs"
(books/supplies, lockers, deposits) are NOT counted.
BC has one domestic rate (no in/out-of-province split).

Output: output/capilano_tuition.json
Requires: beautifulsoup4
"""
import json
import re
import urllib.request
from pathlib import Path

URL = ("https://www.capilanou.ca/admissions/fees--finances/"
       "tuition--fees/tuition--other-fees/")
ACADEMIC_YEAR = "2026-2027"
CREDITS_PER_YEAR = 30
EAP_INTL_PER_CREDIT = 586.75  # reduced international rate for EAP courses

MONEY = r"\$?([\d,]+\.\d{2})"
SURCHARGE_RE = re.compile(r"\+\s*" + MONEY + r"\s*per credit")
FLAT_FEE_RE = re.compile(r"additional fees of\s*" + MONEY)


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def clean_name(name):
    return re.sub(r"\s+", " ", name.replace("​", "").replace("\xa0", " ")).strip()


# Bold standalone paragraphs that are section titles, not programs.
NON_PROGRAM_HEADINGS = {"Standard Tuition Fee", "Tuition Surcharges and Other Fees"}


def main():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fetch(URL), "html.parser")
    content = soup.find(id="d.en.51139").find_parent("div")
    text = content.get_text(" ", strip=True)

    dom_rate = float(re.search(
        r"Canadian Citizens / Permanent Residents:\s*\$([\d.]+) per credit",
        text).group(1))
    intl_rate = float(re.search(
        r"International Students:\s*\$([\d.]+) per credit", text).group(1))
    print(f"standard per-credit: domestic={dom_rate}, international={intl_rate}")

    # Walk the content in order; a program heading starts a new section.
    # Headings are standalone bold paragraphs: most link to the program
    # profile, a few are plain bold text.
    programs = []  # (name, [fee line texts], full section text)
    current, mode = None, "fees"
    for el in content.find_all(["p", "ul"]):
        if el.name == "p":
            txt = el.get_text(" ", strip=True)
            if txt.lower().startswith("approximate other costs"):
                mode = "other"
            elif re.fullmatch(r"[A-Z]", txt):
                current, mode = None, "fees"
            else:
                strong = el.find("strong")
                if strong and txt == strong.get_text(" ", strip=True):
                    name = clean_name(txt)
                    a = strong.find("a", href=True)
                    is_heading = (
                        (a is not None and "programs--courses" in a["href"])
                        or (strong.find("a") is None
                            and name not in NON_PROGRAM_HEADINGS and len(name) > 1)
                    )
                    if is_heading:
                        current = (name, [], [])
                        programs.append(current)
                        mode = "fees"
            if current is not None:
                current[2].append(txt)
        elif el.name == "ul" and current is not None:
            lines = [li.get_text(" ", strip=True) for li in el.find_all("li")]
            current[2].extend(lines)
            if mode == "fees":
                current[1].extend(lines)
    print(f"program sections: {len(programs)}")

    entries = []
    for name, fee_lines, section_lines in programs:
        section_text = " ".join(section_lines).lower()
        tuition_free = "tuition-free" in section_text or "tuition free" in section_text

        all_surcharges, all_flat, any_surcharges = [], [], []
        for line in fee_lines:
            sur = [float(v.replace(",", "")) for v in SURCHARGE_RE.findall(line)]
            flat = [float(v.replace(",", "")) for v in FLAT_FEE_RE.findall(line)]
            any_surcharges.extend(sur)
            if line.lower().startswith("all "):
                all_surcharges.extend(sur)
                all_flat.extend(flat)
        surcharge = max(all_surcharges) if all_surcharges else (
            max(any_surcharges) if any_surcharges else 0.0)
        flat_fees = round(sum(all_flat), 2)

        is_eap = "eap" in name.lower() or "english for academic" in name.lower()
        intl_base = EAP_INTL_PER_CREDIT if is_eap else intl_rate

        if tuition_free:
            domestic = flat_fees
        else:
            domestic = round(CREDITS_PER_YEAR * (dom_rate + surcharge) + flat_fees, 2)
        international = round(
            CREDITS_PER_YEAR * (intl_base + surcharge) + flat_fees, 2)

        comments = (
            f"{CREDITS_PER_YEAR} credits/year: base ${dom_rate}/cr domestic, "
            f"${intl_base}/cr international"
            + (f" + program surcharge ${surcharge}/cr" if surcharge else "")
            + (f" + flat fees ${flat_fees}" if flat_fees else "")
            + ". Course-specific additional fees and approximate other costs "
              "(books/supplies) not included."
        )
        if tuition_free:
            comments = ("Tuition-free for domestic students (mandatory ancillary "
                        "fees still apply). " + comments)
        if is_eap:
            comments += (" International rate is the reduced EAP rate "
                         "($586.75/cr, excl. EAP 100/101).")

        entries.append({
            "universityId": "capilano",
            "universityName": "Capilano",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": domestic,
                "international": international,
            },
            "comments": comments,
        })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "capilano_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:48]:48s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
