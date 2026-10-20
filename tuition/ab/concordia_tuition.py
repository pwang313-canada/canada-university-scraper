#!/usr/bin/env python3
"""Concordia University of Edmonton tuition scraper (2026-2027).

concordiaTuitionV1

Source: Concordia University of Edmonton (CUE) tuition-estimate PDFs
(concordia.ab.ca, revised Mar/Apr 2026):
  * 2026-27-Domestic-Undergrad-Programs.pdf
  * 2026-27-New-International-Undergrad-Programs-Students.pdf
The PDFs are pinned deliberately -- CUE posts each year's files under
a new wp-content/uploads/<year>/<month>/ folder.

Model: CUE charges a flat EDUCATION FEE per term at a full 15-credit
load, the same for all Arts, Science and Management bachelor's
programs (its only direct-entry bachelor's group; Education and
Environmental Health are after-degree programs). Annual = per-term
x 2 terms.

  Domestic tuition = Education Fee $4,980/term -> $9,960/year
  (matches the Alberta Student Aid figure on ALIS).
  International tuition = Education Fee + International Fee +
  International Supplementary Fee = 4,980 + 5,730 + 2,658
  = $13,368/term -> $26,736/year (new-student rates, Fall 2022+
  cohort structure).

Excluded: Mandatory Fees ($596.30/term), CSA Benefit Plan, lab/seminar
fees ($63/credit hour on lab courses), repatriation and convocation
fees.

Output: output/concordia_tuition.json (entry-list schema, shared with
the other province scrapers; combine with combine_tuition.py).
Requires: pypdf (in requirements.txt).
"""

import io
import json
import os
import re

from curl_cffi import requests
from pypdf import PdfReader

UPLOADS = "https://concordia.ab.ca/wp-content/uploads/2026/04/"
DOMESTIC_PDF = UPLOADS + "2026-27-Domestic-Undergrad-Programs.pdf"
INTERNATIONAL_PDF = (UPLOADS +
                     "2026-27-New-International-Undergrad-Programs-Students.pdf")
ACADEMIC_YEAR = "2026-2027"
UNIVERSITY_ID = "concordia"
UNIVERSITY_NAME = "Concordia University of Edmonton"
TERMS_PER_YEAR = 2

BASE_COMMENT = (
    "From Concordia University of Edmonton's 2026/2027 tuition "
    "estimate sheets. CUE charges a flat Education Fee per term at a "
    "full 15-credit load, the same for all Arts, Science and "
    "Management bachelor's programs; annual = per-term x 2. "
    "International tuition adds the International Fee and the "
    "International Supplementary Fee to the Education Fee. Mandatory "
    "fees, lab/seminar fees ($63/credit hour on lab courses), CSA "
    "benefits and repatriation/convocation fees are excluded."
)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def pdf_text(url):
    r = requests.get(url, impersonate="chrome120", timeout=60)
    r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fee(text, label):
    m = re.search(re.escape(label) + r":?\s*\$([\d,]+\.\d{2})", text)
    if not m:
        raise RuntimeError(f"fee not found: {label}")
    return float(m.group(1).replace(",", ""))


def main():
    dom_text = pdf_text(DOMESTIC_PDF)
    intl_text = pdf_text(INTERNATIONAL_PDF)

    education_fee = fee(dom_text, "Education Fee")
    if fee(intl_text, "Education Fee") != education_fee:
        raise RuntimeError("Education Fee differs between the two PDFs")

    intl_per_term = (
        education_fee
        + fee(intl_text, "International Fee")
        + fee(intl_text, "International Supplementary Fee")
    )

    entry = {
        "universityId": UNIVERSITY_ID,
        "universityName": UNIVERSITY_NAME,
        "programId": slugify("Arts, Science, Management"),
        "programName": "Arts, Science, Management",
        "academicYear": ACADEMIC_YEAR,
        "tuition": {
            "domestic-in-province": round(education_fee * TERMS_PER_YEAR, 2),
            "international": round(intl_per_term * TERMS_PER_YEAR, 2),
        },
        "comments": BASE_COMMENT,
    }

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", "concordia_tuition.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([entry], f, indent=1, ensure_ascii=False)
    print(f"Wrote 1 entry to {path}: {entry['tuition']}")


if __name__ == "__main__":
    main()
