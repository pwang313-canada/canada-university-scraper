#!/usr/bin/env python3
"""UVic tuition scraper.
# MARKER: uvicTuitionV1

Source: https://www.uvic.ca/undergraduate/finances/tuition-costs/index.php

That page is an interactive estimator driven by UVic's own API:
  /apis/program/getPrograms?level=UG|LW
  /apis/fee/getGroupedFees?level=UG&residency=D|I&programId=<id>
  /apis/fee/getFees?level=LW&residency=D|I&programId=<id>

The /apis/ endpoints refuse plain HTTP clients (connection dropped), so
the fetches run inside a real browser page via Playwright, the same
approach as brock_tuition.py.

UVic prices by faculty, not by individual program. Fees are published as
two-term totals (= one academic year); the "tuition" group is used and
ancillary fees (student society, bus pass, athletics, ...) are excluded.
Domestic tuition is a single two-term figure. INTERNATIONAL tuition
escalates by year of study -- the API returns separate Year 1/2/3/4 rows
(and its tuition_total is the whole-degree sum) -- so the Year 1 row is
used as the annual figure, with the later years noted in the comments.
Rates effective May 1, 2026 -> academicYear 2026-2027.
BC has one domestic rate (no in/out-of-province split).

Output: output/uvic_tuition.json
Requires: pip install playwright && playwright install chromium
          (or Google Chrome for the channel="chrome" fast path)
"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

PAGE_URL = "https://www.uvic.ca/undergraduate/finances/tuition-costs/index.php"
ACADEMIC_YEAR = "2026-2027"

FETCH_JS = """
async () => {
  const j = async (u) => {
    const r = await fetch(u);
    if (r.status !== 200) throw new Error(u + ' -> HTTP ' + r.status);
    return r.json();
  };
  const out = {UG: [], LW: []};
  for (const level of ['UG', 'LW']) {
    const programs = await j(`/apis/program/getPrograms?level=${level}`);
    for (const p of programs) {
      const fees = {};
      for (const res of ['D', 'I']) {
        fees[res] = level === 'UG'
          ? await j(`/apis/fee/getGroupedFees?level=UG&residency=${res}&programId=${p.id}`)
          : await j(`/apis/fee/getFees?level=LW&residency=${res}&programId=${p.id}`);
      }
      out[level].push({id: p.id, programName: p.programName, fees});
    }
  }
  return out;
}
"""


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def ug_tuition(grouped):
    """(annual tuition, {year: fee} or None) from a getGroupedFees response.

    International rows are split by year of study (Year 1..4); the annual
    figure is the Year 1 row. Domestic has a single row.
    """
    rows = grouped.get("tuition", [])
    years = {}
    for r in rows:
        m = re.search(r"Year (\d)", r["feeDescription"])
        if m:
            years[int(m.group(1))] = float(r["twoTermFee"] or 0)
    if years:
        return years[min(years)], years
    return float(sum(r["twoTermFee"] or 0 for r in rows)), None


def lw_tuition(rows):
    """Annual tuition from a getFees list: only the 'Tuition' rows."""
    return float(sum(
        r["twoTermFee"] or 0 for r in rows
        if r["feeDescription"].strip().lower().startswith("tuition")))


def main():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                channel="chrome", headless=True,
                args=["--disable-blink-features=AutomationControlled"])
            print("Using real Chrome")
        except Exception as e:
            print(f"Real Chrome not found ({e}); falling back to Chromium")
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"])
        page = browser.new_page()
        page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)
        data = page.evaluate(FETCH_JS)
        browser.close()

    entries = []
    for prog in data["UG"]:
        name = re.sub(r"\s+", " ", prog["programName"]).strip()
        dom_annual, _ = ug_tuition(prog["fees"]["D"])
        intl_annual, years = ug_tuition(prog["fees"]["I"])
        comments = ("Two-term (one academic year) tuition from UVic's "
                    "tuition estimator API; ancillary fees excluded. "
                    "Rates effective May 1, 2026.")
        if years:
            later = ", ".join(f"Year {y} ${years[y]:,.0f}"
                              for y in sorted(years) if y != min(years))
            comments += (f" International figure is the Year 1 rate; it "
                         f"rises by year of study ({later}).")
        entries.append({
            "universityId": "uvic",
            "universityName": "UVic",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": dom_annual,
                "international": intl_annual,
            },
            "comments": comments,
        })
    for prog in data["LW"]:
        name = re.sub(r"\s+", " ", prog["programName"]).strip()
        entries.append({
            "universityId": "uvic",
            "universityName": "UVic",
            "programId": slug(name),
            "programName": name,
            "academicYear": ACADEMIC_YEAR,
            "tuition": {
                "domestic-in-province": lw_tuition(prog["fees"]["D"]),
                "international": lw_tuition(prog["fees"]["I"]),
            },
            "comments": "Law (JD): two-term tuition rows only from UVic's "
                        "tuition estimator API; ancillary fees excluded. "
                        "Rates effective May 1, 2026.",
        })

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / "uvic_tuition.json"
    dest.write_text(json.dumps(entries, indent=2))
    print(f"Wrote {len(entries)} entries to {dest}")
    for e in entries:
        t = e["tuition"]
        print(f"  {e['programName'][:40]:40s} dom={t['domestic-in-province']:>9} "
              f"intl={t['international']:>9}")


if __name__ == "__main__":
    main()
