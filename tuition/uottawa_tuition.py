#!/usr/bin/env python3
"""University of Ottawa 2026-2027 undergraduate tuition scraper.
# MARKER: uottawaTuitionV1

uOttawa publishes tuition through an ASP.NET WebForms cascade
(dnn.uottawa.ca): academic year -> level -> faculty -> discipline ->
classification (full/part time) -> Submit -> fee table.

We walk the whole undergraduate cascade for three categories and take the
FIRST progress bracket's rate (new-student rate). Full-time disciplines:
annual = per-term x 2. Part-time-only disciplines (e.g. Virtual programs):
annual = per-unit x 30, flagged in comments. Upper brackets are
grandfathered rates for continuing students (kept in the raw file).

Categories:
  ont : Canadian citizen residing in Ontario (.../Tuition-Fees-CDN-ONT)
  oop : Canadian citizen outside Ontario (.../Tuition-Fees-CDN)
  intl: International (.../Tuition-Fees-INTL)

Usage:
    python uottawa_tuition.py scrape [ont|oop|intl|all]  # default all
    python uottawa_tuition.py summarize                  # raw -> output JSON

Notes: the cascade needs cookie persistence (ASP.NET session); posting an
invalid classification kills the server session, so we read the available
classifications per discipline and use a fresh session per faculty.
Results save incrementally, so a run can be resumed.
"""
import html as H
import json
import re
import sys
import time
import urllib.request
import urllib.parse
import http.cookiejar
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "output"


def detect_ids(doc):
    """Each DNN page hosts its own module instance (ctr896, ctr901, ...)."""
    m = re.search(r'(dnn\$ctr\d+\$Default\$TuitionFeesViews)\$ddlAcademicYear', doc)
    assert m, "tuition form not found on page"
    base = m.group(1)
    return base + "$ddl", base + "$btnSearch"


P, B = None, None  # set per page by detect_ids

CATEGORY_URLS = {
    "ont": "https://dnn.uottawa.ca/en/Utilities/University-Fees/Tuition-Fees-CDN-ONT",
    "oop": "https://dnn.uottawa.ca/en/Utilities/University-Fees/Tuition-Fees-CDN",
    "intl": "https://dnn.uottawa.ca/en/Utilities/University-Fees/Tuition-Fees-INTL",
}
CATEGORY_KEYS = {
    "ont": "domestic-in-province",
    "oop": "domestic-out-of-province",
    "intl": "international",
}

YEAR_VALUE = "101"          # 2026-2027
LEVEL_VALUE = "123"         # Undergraduate (bachelor's, certificate)
FULLTIME_VALUE = "141"      # Full time (flat rate)


class Scraper:
    def __init__(self, url):
        self.url = url
        cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def _req(self, data=None):
        headers = {"User-Agent": "Mozilla/5.0"}
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(self.url, data=data, headers=headers)
        with self.opener.open(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")

    def get(self):
        global P, B
        doc = self._req()
        P, B = detect_ids(doc)
        return doc

    def post(self, fields, target=None, submit=False):
        fields = dict(fields)
        if submit:
            fields[B] = "Submit"
        else:
            fields["__EVENTTARGET"] = target
            fields["__EVENTARGUMENT"] = ""
        data = urllib.parse.urlencode(fields).encode()
        return self._req(data)

    @staticmethod
    def form_fields(doc):
        fields = {}
        for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*>', doc, re.I):
            tag, name = m.group(0), m.group(1)
            if re.search(r'type="(submit|button|image)"', tag, re.I):
                continue
            vm = re.search(r'value="([^"]*)"', tag)
            fields[name] = H.unescape(vm.group(1)) if vm else ""
        for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', doc, re.S | re.I):
            name, opts = m.group(1), m.group(2)
            sel = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', opts, re.I) \
                or re.search(r'<option[^>]*value="([^"]*)"', opts, re.I)
            fields[name] = H.unescape(sel.group(1)) if sel else ""
        return fields

    @classmethod
    def options(cls, doc, key):
        m = re.search(r'name="%s".*?</select>' % re.escape(P + key), doc, re.S)
        if not m:
            return []
        return [(H.unescape(v), H.unescape(re.sub("<[^>]+>", "", t)).strip())
                for v, t in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>',
                                       m.group(0), re.S | re.I)]

    def with_retries(self, fn, *args, tries=3):
        for i in range(tries):
            try:
                return fn(*args)
            except Exception:
                if i == tries - 1:
                    raise
                time.sleep(2 * (i + 1))


def new_session(cat):
    """Fresh session walked to year+level."""
    s = Scraper(CATEGORY_URLS[cat])
    doc = s.with_retries(s.get)
    f = s.form_fields(doc)
    for key, val in (("AcademicYear", YEAR_VALUE), ("Level", LEVEL_VALUE)):
        f[P + key] = val
        doc = s.with_retries(s.post, f, P + key)
        f = s.form_fields(doc)
    return s, f, doc


def walk_discipline(s, f, dval):
    """Select discipline -> classification -> submit; return (amounts, class_value, f)."""
    f[P + "Discipline"] = dval
    doc = s.with_retries(s.post, f, P + "Discipline")
    f = s.form_fields(doc)
    classes = [v for v, t in s.options(doc, "Classification") if v != "- Select -"]
    assert classes, "no classifications offered"
    cval = FULLTIME_VALUE if FULLTIME_VALUE in classes else classes[0]
    f[P + "Discipline"] = dval
    f[P + "Classification"] = cval
    doc = s.with_retries(s.post, f, P + "Classification")
    f = s.form_fields(doc)
    f[P + "Classification"] = cval
    doc = s.with_retries(s.post, f, None, True)
    f = s.form_fields(doc)
    amounts = [float(x.replace(",", ""))
               for x in re.findall(r"CA\$([\d,]+\.\d{2})", doc)]
    assert amounts, "no fee table returned"
    return amounts, cval, f


def scrape_category(cat):
    raw_path = OUT_DIR / f"uottawa_raw_{cat}.json"
    OUT_DIR.mkdir(exist_ok=True)
    done = {}
    if raw_path.exists():
        done = json.loads(raw_path.read_text()).get("disciplines", {})
        print(f"resuming {cat}: {len(done)} disciplines already done")

    s, f, doc = new_session(cat)
    faculties = [(v, t) for v, t in s.options(doc, "Faculty") if v != "- Select -"]
    print(f"{cat}: {len(faculties)} faculties")

    for fval, fname in faculties:
        s, f, doc = new_session(cat)  # fresh session per faculty: limits blast radius
        f[P + "Faculty"] = fval
        doc = s.with_retries(s.post, f, P + "Faculty")
        f = s.form_fields(doc)
        disciplines = [(v, t) for v, t in s.options(doc, "Discipline") if v != "- Select -"]
        print(f"  {fname} ({len(disciplines)} disciplines)", flush=True)
        for dval, dname in disciplines:
            key = f"{fname} || {dname}"
            if key in done:
                continue
            try:
                amounts, cval, f = walk_discipline(s, f, dval)
            except Exception as e:
                print(f"    retry {dname} with fresh session ({e})", flush=True)
                try:
                    s, f, doc = new_session(cat)
                    f[P + "Faculty"] = fval
                    doc = s.with_retries(s.post, f, P + "Faculty")
                    f = s.form_fields(doc)
                    amounts, cval, f = walk_discipline(s, f, dval)
                except Exception as e2:
                    print(f"    FAILED {dname}: {e2}", flush=True)
                    continue
            done[key] = {"faculty": fname, "discipline": dname,
                         "classification": cval, "amounts": amounts}
            if len(done) % 10 == 0:
                raw_path.write_text(json.dumps(
                    {"category": cat, "disciplines": done}, indent=1))
        raw_path.write_text(json.dumps({"category": cat, "disciplines": done}, indent=1))
    print(f"{cat}: done, {len(done)} disciplines -> {raw_path}")


def slug(text):
    text = H.unescape(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def summarize():
    raws = {}
    for cat in CATEGORY_URLS:
        p = OUT_DIR / f"uottawa_raw_{cat}.json"
        if not p.exists():
            sys.exit(f"missing {p}; run scrape {cat} first")
        raws[cat] = json.loads(p.read_text())["disciplines"]

    keys = list(raws["ont"].keys())
    entries = []
    for key in keys:
        faculty = raws["ont"][key]["faculty"]
        discipline = raws["ont"][key]["discipline"]
        tuition, notes = {}, []
        for cat, tkey in CATEGORY_KEYS.items():
            d = raws[cat].get(key)
            if not d:
                continue
            first = d["amounts"][0]  # new-student bracket
            if d["classification"] == FULLTIME_VALUE:
                tuition[tkey] = round(first * 2, 2)  # per-term -> annual
            else:
                tuition[tkey] = round(first * 30, 2)  # per-unit x 30 units
                notes.append(f"{tkey} is part-time-only (per-unit x 30 units)")
        comment = (
            "Full-time flat rate for 2026-2027 new admits "
            "(annual = per-term x 2). " if not notes else
            "Part-time-only program: annual = per-unit x 30 units. "
        )
        entries.append({
            "universityId": "uottawa",
            "universityName": "University of Ottawa",
            "programId": slug(faculty) + "-" + slug(discipline),
            "programName": f"{discipline} ({faculty})",
            "academicYear": "2026-2027",
            "tuition": tuition,
            "comments":
                comment +
                "First progress bracket (new-student rate); upper brackets are "
                "grandfathered rates for continuing students (see raw file). "
                "Tuition only; ancillary fees separate. Source: uOttawa "
                "tuition fee calculator (dnn.uottawa.ca).",
        })
    entries.sort(key=lambda e: e["programId"])
    out = OUT_DIR / "uottawa_tuition.json"
    out.write_text(json.dumps(entries, indent=1))
    print(f"wrote {out} ({len(entries)} entries)")
    return entries


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summarize"
    if cmd == "scrape":
        cats = sys.argv[2:] or ["all"]
        if cats == ["all"]:
            cats = list(CATEGORY_URLS)
        for c in cats:
            scrape_category(c)
    elif cmd == "summarize":
        summarize()
    else:
        sys.exit("usage: uottawa_tuition.py scrape [ont|oop|intl|all] | summarize")

