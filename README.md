# Ontario University Tuition Scraper (2026–2027)

A conservative, source-first collection pipeline for the Ontario University Planner. It reads `universities.json` and `programs.json`, discovers candidate official tuition pages, extracts HTML tables and linked PDFs, optionally renders JavaScript pages with Playwright, and writes:
- `tuition.json` — only tuition amounts that were actually extracted from a source, with source URLs and review status.
- `tuition_sources.json` — discovered/known source URLs per university.
- `manual_review.csv` — items needing human confirmation, including unmatched program names and unsupported pages.
- `scrape_errors.csv` — fetch/parse errors.

**No tuition values are guessed.** Extracted amounts are candidate observations, not guaranteed correct program matches. Check `verificationStatus` before publishing to the app.

## Setup (Windows PowerShell)

Put this folder in your project, or copy its files into `C:\\android\\ontario-university-planner\\tuition-scraper`.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

Copy your existing `universities.json` and `programs.json` into this folder, or run with `--data-dir C:\\android\\ontario-university-planner`.

## Run

1. Discover official pages and linked PDFs:
```powershell
python tuition_scraper.py discover --data-dir C:\android\ontario-university-planner --output-dir output
```

2. Scrape known/discovered sources:
```powershell
python tuition_scraper.py scrape --data-dir C:\android\ontario-university-planner --output-dir output --academic-year 2026-2027
```

3. Render pages with JavaScript (slower; use if normal scraping misses content):
```powershell
python tuition_scraper.py scrape --data-dir C:\android\ontario-university-planner --output-dir output --academic-year 2026-2027 --playwright
```

To run both steps:
```powershell
python tuition_scraper.py all --data-dir C:\android\ontario-university-planner --output-dir output --academic-year 2026-2027 --playwright
```

## Important limitations

- The crawler starts from each university's official website URL in `universities.json`, if present. It only follows same-domain links and pages whose text/URL suggests tuition, fees, registrar, finance, or international/domestic fees.
- Discovery is heuristic. It cannot guarantee every page is found, especially portals, calculators, JavaScript-only apps, or pages requiring choices/login.
- Table extraction is intentionally conservative. It records row context, table headers, page title, and any monetary-looking amount. It does **not** assume a row is the full annual tuition unless the page explicitly supports that interpretation.
- Program matching is fuzzy and is marked `needs_review`; don't automatically publish records solely because a name matched.
- PDFs are parsed with `pdfplumber`; scanned/image-only PDFs require OCR and will be flagged if no text can be extracted.
- Respect each site's terms, robots rules, rate limits, and access restrictions. Do not bypass logins, CAPTCHAs, or technical controls.
