#!/usr/bin/env python3
"""Western University 2026-2027 first-year tuition scraper.
# MARKER: westernTuitionV1

Source: registrar.uwo.ca fee schedules (PDFs). The tuition-fee-estimator page
is a shell; real figures are in:
  2026-27-UGRD-Fee-Schedule---FT-Domestic2.pdf      (Ontario + Out-of-Province)
  2026-27-UGRD-Fee-Schedule---FT-International1.pdf (International)

The domestic PDF has TWO side-by-side schedules: "ONTARIO RESIDENT" (left)
and "OUT-OF-PROVINCE" (right), each with Total Fee + TUITION columns.
The TUITION column is tuition-only (ancillaries are separate columns and
are excluded). All PDFs use full-time Year 1 rows.

Needs pypdf: pip install pypdf

Usage:
    python western_tuition.py scrape      # download PDFs -> output/western_raw.json
    python western_tuition.py summarize   # raw -> output/western_tuition.json
"""
import html as H
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"
PDF_BASE = "https://registrar.uwo.ca/student_finances/fees_refunds/"

PDFS = {
    "dom": "2026-27-UGRD-Fee-Schedule---FT-Domestic2.pdf",
    "intl": "2026-27-UGRD-Fee-Schedule---FT-International1.pdf",
}

# (programId, programName, dom_match, intl_match)
# dom_match/intl_match: substring to find the row in each PDF.
PROGRAMS = [
    ("arts-humanities", "Arts & Humanities, Media & Communication Studies",
     "Arts & Humanities", "Arts & Humanity"),
    ("social-science", "Social Science, Science, Bio/Med Science",
     "Social Science", "Social Science"),
    ("health-science", "Health Science, Kinesiology, Music",
     "Health Science", "Health Science"),
    ("nursing", "Nursing (excluding Compressed)",
     "Nursing (excluding Compressed)", "Nursing (Not Including"),
    ("computer-science", "Computer Science",
     "MOS, Computer Science", "Computer Science Year 1"),
    ("mos", "Management & Organizational Studies",
     "MOS, Computer Science", "MOS Year 1"),
    ("engineering", "Engineering",
     "Engineering Year 1", "Engineering Year 1"),
    ("business", "Business (Ivey)",
     "Business", "Business"),
    ("dentistry", "Dentistry",
     "Dentistry Year 1", "Dentistry Year 1"),
    ("education", "Education (BEd)",
     "Education (BEd)", "Education (BEd)"),
    ("law", "Law",
     "Law All years", "Law All Years"),
    ("medicine", "Medicine (MD)",
     "Medicine (MD) All years", None),  # no intl figure published
]


def fetch_pdf(name):
    url = PDF_BASE + urllib.parse.quote(name)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def pdf_text(data):
    from pypdf import PdfReader
    import io
    r = PdfReader(io.BytesIO(data))
    return "\n".join(p.extract_text() or "" for p in r.pages)


def money(s):
    m = re.search(r"\$?([\d,]+\.\d{2})", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def parse_domestic(text):
    """Return list of (program, ont_tuition, oop_tuition) for Year 1 / All years."""
    out = []
    for line in text.split("\n"):
        m = re.search(
            r"(.+?)\s+(?:Year 1|All years)\s+"
            r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+"
            r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})", line)
        if m:
            prog = re.sub(r"[†‡*]+", "", m.group(1)).strip()
            out.append((prog, money(m.group(3)), money(m.group(5))))
    return out


def parse_intl(text):
    """Return list of (program, intl_tuition) for Year 1 / All Years rows."""
    out = []
    for line in text.split("\n"):
        m = re.search(
            r"(.+?)\s+(?:Year 1[\d,\s&]*|All Years)\s+"
            r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})", line)
        if m:
            prog = re.sub(r"[†‡*]+", "", m.group(1)).strip().rstrip(",")
            out.append((prog, money(m.group(3))))
    return out


def scrape():
    OUT_DIR.mkdir(exist_ok=True)
    pdfs = {k: pdf_text(fetch_pdf(name)) for k, name in PDFS.items()}
    dom = parse_domestic(pdfs["dom"])
    intl = parse_intl(pdfs["intl"])
    print(f"domestic rows: {len(dom)}, intl rows: {len(intl)}")
    p = OUT_DIR / "western_raw.json"
    p.write_text(json.dumps({"dom": dom, "intl": intl}, indent=1))
    print(f"wrote {p}")


def summarize():
    p = OUT_DIR / "western_raw.json"
    if not p.exists():
        sys.exit("run scrape first")
    raw = json.loads(p.read_text())
    dom, intl = raw["dom"], raw["intl"]

    def find(rows, needle):
        nl = needle.lower()
        for prog, *vals in rows:
            pl = prog.lower()
            if nl in pl or pl in nl:
                return prog, vals
        return None, None

    entries = []
    for pid, pname, dom_m, intl_m in PROGRAMS:
        dprog, dvals = find(dom, dom_m)
        assert dprog, f"domestic row not found: {dom_m!r}"
        tuition = {
            "domestic-in-province": dvals[0],
            "domestic-out-of-province": dvals[1],
        }
        note = ""
        if intl_m:
            iprog, ivals = find(intl, intl_m)
            assert iprog, f"intl row not found: {intl_m!r}"
            tuition["international"] = ivals[0]
        else:
            note = "No international figure published. "
        if pid in ("computer-science", "mos"):
            note += ("Domestic figure from Western's combined 'MOS, Computer "
                     "Science' row; international priced separately. ")
        entries.append({
            "universityId": "western",
            "universityName": "Western University",
            "programId": pid,
            "programName": pname,
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                note +
                "First-year full-time tuition (TUITION column only; ancillary "
                "fees excluded). Domestic PDF carries Ontario-resident and "
                "out-of-province schedules side by side. "
                "Source: registrar.uwo.ca fee schedules.",
        })
    out = OUT_DIR / "western_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")
    for e in entries:
        print(e["programId"], e["tuition"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        scrape()
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: western_tuition.py scrape | summarize")

