#!/usr/bin/env python3
"""Conservative Ontario university tuition source discovery and extraction."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process

try:
    import pandas as pd
except Exception:
    pd = None

try:
    import pdfplumber
except Exception:
    pdfplumber = None

YEAR_DEFAULT = "2026-2027"
USER_AGENT = "OntarioUniversityPlannerTuitionResearch/1.0 (educational research; contact: configure in script)"
TIMEOUT = 25
DELAY_SECONDS = 0.6
MAX_PAGES_PER_UNIVERSITY = 80
MAX_LINKS_PER_PAGE = 100
AMOUNT_RE = re.compile(
    r"(?<!\w)(?:CAD\s*)?(?:C\$|\$)\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|(?<!\w)\d{1,3}(?:,\d{3})*\.\d{2}\s*(?:CAD|Canadian dollars)",
    re.I,
)
YEAR_RE = re.compile(r"(?:2026\s*[-–/]\s*2027|2026\s*[-–/]\s*27|2026-27)", re.I)
TUITION_HINTS = (
    "tuition",
    "fee",
    "fees",
    "registrar",
    "cost of attendance",
    "costs",
    "international student",
    "domestic student",
    "undergraduate",
    "graduate",
    "finance",
    "financial services",
)
NEGATIVE_HINTS = (
    "news",
    "event",
    "calendar",
    "athletics",
    "giving",
    "donate",
    "employment",
    "job",
    "privacy",
    "accessibility",
    "alumni",
    "research news",
)
CATEGORIES = {
    "domestic_ontario": (
        "ontario resident",
        "ontario domestic",
        "domestic ontario",
        "ontario student",
    ),
    "domestic_out_of_province": (
        "out-of-province",
        "out of province",
        "non-ontario resident",
        "outside ontario",
        "domestic non-ontario",
    ),
    "international": ("international", "visa student", "international student"),
    "domestic_unspecified": ("domestic", "canadian student", "canadian citizen"),
}

# Maps scraper studentCategory -> tuition_summary.json tuition keys.
SUMMARY_CATEGORY_KEYS = {
    "domestic_ontario": "domestic-in-province",
    "domestic_out_of_province": "domestic-out-province",
    "international": "international",
    "domestic_unspecified": "domestic-in-province",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, dict):
        # Common wrapper shapes
        for key in ("universities", "programs", "data", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list (or an object wrapping one)")
    return data


def first_value(obj, keys, default=None):
    if not isinstance(obj, dict):
        return default
    low = {str(k).lower(): v for k, v in obj.items()}
    for key in keys:
        val = low.get(key.lower())
        if val not in (None, ""):
            return val
    return default


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", norm(s).lower()).strip("-")


def university_name(u):
    return norm(
        first_value(
            u,
            ["name", "universityName", "title", "institution", "displayName"],
            "Unknown University",
        )
    )


def university_id(u):
    return norm(
        first_value(u, ["id", "universityId", "slug", "code"], slug(university_name(u)))
    )


def university_url(u):
    url = first_value(
        u, ["website", "websiteUrl", "url", "officialWebsite", "domain", "homepage"]
    )
    if not url:
        # Some datasets use nested website fields.
        nested = first_value(u, ["links", "contact", "web"])
        if isinstance(nested, dict):
            url = first_value(nested, ["website", "url", "homepage"])
    url = norm(url)
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url or ""


def university_tuition_url(u):
    """Direct tuition page URL from universities.json ("tuitionUrl" field).

    When present, discovery skips homepage crawling and uses this URL directly.
    """
    url = norm(
        first_value(u, ["tuitionUrl", "tuitionURL", "tuitionPage", "tuition_url"], "")
    )
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url or ""


def program_name(p):
    return norm(
        first_value(p, ["name", "programName", "title", "displayName", "program"], "")
    )


def program_id(p):
    return norm(
        first_value(
            p, ["id", "programId", "program_id", "code", "slug"], slug(program_name(p))
        )
    )


def program_university_hint(p):
    return norm(
        first_value(
            p,
            [
                "universityId",
                "university_id",
                "university",
                "universityName",
                "institutionId",
                "institution",
            ],
            "",
        )
    )


def same_domain(url_a, url_b):
    try:
        a, b = urlparse(url_a).hostname, urlparse(url_b).hostname
        return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))
    except Exception:
        return False


def allowed_candidate(text, url):
    blob = (text + " " + url).lower()
    if any(x in blob for x in NEGATIVE_HINTS):
        return False
    return any(x in blob for x in TUITION_HINTS)


def canonical_url(url):
    url, _ = urldefrag(url)
    p = urlparse(url)
    return p._replace(fragment="", query="").geturl().rstrip("/")


def fetch(url):
    try:
        r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code >= 400:
            return None, f"HTTP {r.status_code}"
        ctype = r.headers.get("content-type", "").lower()
        return (r, None)
    except Exception as e:
        return None, str(e)


def parse_university_home(u):
    home = university_url(u)
    if not home:
        return [], {"status": "missing_official_website_url", "url": ""}
    queue = deque([(home, 0)])
    visited, found = set(), []
    pages = 0
    errors = []
    base_host = urlparse(home).hostname
    while queue and pages < MAX_PAGES_PER_UNIVERSITY:
        url, depth = queue.popleft()
        url = canonical_url(url)
        if url in visited or not same_domain(url, home):
            continue
        visited.add(url)
        r, err = fetch(url)
        pages += 1
        if err:
            errors.append({"url": url, "error": err})
            continue
        ctype = r.headers.get("content-type", "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            if allowed_candidate(url, url):
                found.append(
                    {
                        "url": r.url,
                        "title": url.rsplit("/", 1)[-1],
                        "kind": "pdf",
                        "discoveredFrom": home,
                    }
                )
            continue
        if "html" not in ctype and not r.text.lstrip().startswith("<"):
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        title = norm(soup.title.get_text(" ", strip=True) if soup.title else "")
        page_text = norm(soup.get_text(" ", strip=True))[:20000]
        if allowed_candidate(title + " " + page_text[:3000], r.url):
            found.append(
                {"url": r.url, "title": title, "kind": "html", "discoveredFrom": home}
            )
        if depth >= 2:
            continue
        links = 0
        for a in soup.find_all("a", href=True):
            href = urljoin(r.url, a["href"])
            label = norm(a.get_text(" ", strip=True))
            if not href.startswith(("http://", "https://")):
                continue
            if not same_domain(href, home):
                continue
            link_text = (label + " " + href).lower()
            is_pdf = ".pdf" in urlparse(href).path.lower()
            if is_pdf and allowed_candidate(link_text, href):
                found.append(
                    {
                        "url": href,
                        "title": label or href.rsplit("/", 1)[-1],
                        "kind": "pdf",
                        "discoveredFrom": r.url,
                    }
                )
            elif allowed_candidate(link_text, href):
                queue.append((href, depth + 1))
            links += 1
            if links >= MAX_LINKS_PER_PAGE:
                break
        time.sleep(DELAY_SECONDS)
    dedup, unique = set(), []
    for item in found:
        uurl = canonical_url(item["url"])
        if uurl not in dedup:
            dedup.add(uurl)
            item["url"] = uurl
            unique.append(item)
    return unique, {
        "status": "discovered" if unique else "no_candidate_sources_found",
        "url": home,
        "pagesVisited": pages,
        "errors": errors,
    }


def source_registry_path(output_dir):
    return output_dir / "tuition_sources.json"


def discover(args):
    data_dir, out = Path(args.data_dir), Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    universities = read_json(data_dir / "universities.json")
    registry = []
    for idx, u in enumerate(universities, 1):
        name, uid = university_name(u), university_id(u)
        tuition_url = university_tuition_url(u)
        if tuition_url:
            # Direct tuitionUrl from universities.json — skip homepage crawling.
            logging.info(
                "[%s/%s] Using tuitionUrl for %s", idx, len(universities), name
            )
            curl = canonical_url(tuition_url)
            kind = "pdf" if curl.lower().endswith(".pdf") else "html"
            sources = [
                {
                    "url": curl,
                    "title": "Official tuition page (from universities.json)",
                    "kind": kind,
                    "discoveredFrom": "tuitionUrl",
                }
            ]
            status = {
                "status": "direct_tuition_url",
                "url": curl,
                "pagesVisited": 0,
                "errors": [],
            }
            home = university_url(u)
        else:
            home = university_url(u)
            logging.info("[%s/%s] Discovering %s", idx, len(universities), name)
            sources, status = parse_university_home(u)
        registry.append(
            {
                "universityId": uid,
                "universityName": name,
                "officialWebsite": home,
                "tuitionUrl": tuition_url or None,
                "academicYearTarget": args.academic_year,
                "sources": sources,
                "discovery": status,
                "manuallyAddedSources": [],
            }
        )
    source_registry_path(out).write_text(
        json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logging.info("Wrote %s", source_registry_path(out))
    return registry


def page_html(url, use_playwright=False):
    if use_playwright:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1200)
                html = page.content()
                title = page.title()
                final_url = page.url
                browser.close()
                return html, title, final_url, None
        except Exception as e:
            logging.warning(
                "Playwright failed for %s: %s; falling back to requests", url, e
            )
    r, err = fetch(url)
    if err:
        return None, "", url, err
    soup = BeautifulSoup(r.text, "html.parser")
    return (
        r.text,
        norm(soup.title.get_text(" ", strip=True) if soup.title else ""),
        r.url,
        None,
    )


def category_from_context(text):
    t = text.lower()
    for category, hints in CATEGORIES.items():
        if any(h in t for h in hints):
            return category
    return "unspecified"


def fee_period_from_context(text):
    t = text.lower()
    # "Per Term" wins over "per credit": pages often show both a per-term summary
    # row and a per-credit breakdown table; the row-level label is the authority.
    if any(x in t for x in ("per term", "per semester", "fall term", "winter term")):
        return "term"
    if any(x in t for x in ("per course", "per credit", "per credit hour", "per unit")):
        return "per_course_or_credit"
    if any(
        x in t
        for x in (
            "annual",
            "per year",
            "academic year",
            "10 courses",
            "30 credit hours",
        )
    ):
        return "academic_year"
    return "unspecified"


def extract_amounts(text):
    vals = []
    for m in AMOUNT_RE.finditer(text or ""):
        raw = norm(m.group(0))
        cleaned = (
            re.sub(r"(?i)CAD|Canadian dollars|C\$|\$", "", raw).replace(",", "").strip()
        )
        try:
            amount = float(cleaned)
        except ValueError:
            continue
        if 100 <= amount <= 200000:
            vals.append((raw, amount))
    return vals


def find_section_label(table):
    """Walk backwards from a table to find the nearest short heading mentioning
    Domestic or International (e.g. Algoma's "Domestic Fees" / "International Fees")."""
    for prev in table.previous_elements:
        name = getattr(prev, "name", None)
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = norm(prev.get_text(" ", strip=True))
            low = text.lower()
            if "international" in low:
                return "international"
            if "domestic" in low:
                return "domestic_ontario"
        # Stop after scanning a reasonable distance (avoid matching page header)
        if name == "table":
            break
    return None


def find_tuition_column(headers):
    """Return the index of the TUITION column (not TOTAL, not FEES)."""
    for i, h in enumerate(headers):
        low = h.lower()
        if "tuition" in low and "total" not in low:
            return i
    return None


def extract_html_observations(html, url, title, university, academic_year, programs):
    soup = BeautifulSoup(html, "html.parser")
    observations, reviews = [], []
    visible_text = norm(soup.get_text(" ", strip=True))
    page_year_match = bool(
        YEAR_RE.search(visible_text) or YEAR_RE.search(title) or YEAR_RE.search(url)
    )
    # Tables: use the section heading (Domestic/International) and extract ONLY the
    # TUITION column amount (ignore ancillary fees and TOTAL columns).
    for table_index, table in enumerate(soup.find_all("table")):
        headers = []
        first_row = table.find("tr")
        if first_row:
            headers = [
                norm(c.get_text(" ", strip=True))
                for c in first_row.find_all(["th", "td"])
            ]
        section = find_section_label(table)
        tuition_col = find_tuition_column(headers)
        for row_index, tr in enumerate(table.find_all("tr")):
            cells = [
                norm(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])
            ]
            if not cells:
                continue
            row_text = " | ".join(cells)
            # If we found a TUITION column, extract only that cell; else fall back to whole row.
            if tuition_col is not None and tuition_col < len(cells):
                target_text = cells[tuition_col]
                target_label = f"tuition column '{headers[tuition_col]}'"
            else:
                target_text = row_text
                target_label = "whole row (no tuition column found)"
            if not extract_amounts(target_text):
                continue
            context = norm(
                title
                + " | "
                + " | ".join(headers)
                + " | "
                + row_text
                + f" | section={section or 'unknown'} | extracted from {target_label}"
            )
            obs = make_observations(
                context,
                url,
                title,
                university,
                academic_year,
                programs,
                "html_table",
                table_index,
                row_index,
                page_year_match,
            )
            # Override category with the section heading when found.
            if section:
                for o in obs:
                    o["studentCategory"] = section
                    o["sourceContext"] = (
                        o["sourceContext"][:1500] + f" | sectionOverride={section}"
                    )
            observations.extend(obs)
    # Some tuition pages are cards/list text, not tables; preserve them as page-level candidates.
    if not observations:
        for line in re.split(r"(?<=[.;])\s+|(?<=\|)\s*", visible_text):
            if extract_amounts(line):
                observations.extend(
                    make_observations(
                        line,
                        url,
                        title,
                        university,
                        academic_year,
                        programs,
                        "html_text",
                        None,
                        None,
                        page_year_match,
                    )
                )
    if not observations:
        reviews.append(
            review_row(
                university,
                url,
                title,
                "no_currency_amounts_extracted",
                "Page may use a calculator, image/PDF, script-rendered content, or a nonstandard format.",
            )
        )
    return observations, reviews


def make_observations(
    context,
    url,
    title,
    university,
    academic_year,
    programs,
    extraction_method,
    table_index,
    row_index,
    page_year_match,
):
    amounts = extract_amounts(context)
    if not amounts:
        return []
    text_low = context.lower()
    # Use fuzzy program matching only to suggest candidates; never auto-certify.
    names = [(program_name(p), p) for p in programs if program_name(p)]
    best_name, best_score, best_program = "", 0, None
    if names:
        match = process.extractOne(
            context[:500], [x[0] for x in names], scorer=fuzz.partial_ratio
        )
        if match:
            best_name, best_score, _ = match
            if best_score >= 82:
                best_program = next((p for n, p in names if n == best_name), None)
    out = []
    for raw, amount in amounts:
        out.append(
            {
                "universityId": university["universityId"],
                "universityName": university["universityName"],
                "programId": program_id(best_program) if best_program else None,
                "programName": program_name(best_program) if best_program else None,
                "programMatchScore": best_score if best_program else None,
                "programMatchMethod": "fuzzy_suggestion_only"
                if best_program
                else "unmatched",
                "academicYear": academic_year,
                "sourcePageTitle": title,
                "sourceUrl": url,
                "sourceContext": context[:1800],
                "studentCategory": category_from_context(context),
                "tuitionAmount": amount,
                "amountAsPublished": raw,
                "currency": "CAD",
                "feePeriod": fee_period_from_context(context),
                "academicYearExplicitlyFound": bool(page_year_match),
                "extractionMethod": extraction_method,
                "tableIndex": table_index,
                "rowIndex": row_index,
                "retrievedAt": datetime.now(timezone.utc).isoformat(),
                "verificationStatus": "needs_review",
                "reviewNotes": "Confirm this is tuition (not ancillary fees), correct program/campus/student category, and the 2026-2027 academic year.",
            }
        )
    return out


def review_row(university, url, title, reason, notes=""):
    return {
        "universityId": university.get("universityId", ""),
        "universityName": university.get("universityName", ""),
        "sourceUrl": url,
        "sourcePageTitle": title,
        "reason": reason,
        "notes": notes,
    }


def parse_pdf(url, university, academic_year, programs):
    observations, reviews = [], []
    if pdfplumber is None:
        return [], [
            review_row(
                university,
                url,
                "",
                "pdfplumber_not_installed",
                "Install requirements.txt to parse PDFs.",
            )
        ]
    r, err = fetch(url)
    if err:
        return [], [review_row(university, url, "", "pdf_download_failed", err)]
    import io

    try:
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            all_text = []
            for page_no, page in enumerate(pdf.pages, 1):
                txt = page.extract_text() or ""
                all_text.append(txt)
                for line_no, line in enumerate(txt.splitlines(), 1):
                    if extract_amounts(line):
                        observations.extend(
                            make_observations(
                                line,
                                url,
                                f"PDF page {page_no}",
                                university,
                                academic_year,
                                programs,
                                "pdf_text",
                                None,
                                line_no,
                                bool(YEAR_RE.search(txt)),
                            )
                        )
            if not observations:
                reviews.append(
                    review_row(
                        university,
                        url,
                        "",
                        "pdf_no_amounts_extracted",
                        "PDF may be scanned or amounts are in a nonstandard format; OCR/manual review may be needed.",
                    )
                )
    except Exception as e:
        reviews.append(review_row(university, url, "", "pdf_parse_error", str(e)))
    return observations, reviews


def program_candidates_for_university(programs, uid, uname):
    selected = []
    for p in programs:
        hint = program_university_hint(p).lower()
        if (
            not hint
            or uid.lower() in hint
            or slug(uname) in slug(hint)
            or slug(hint) in slug(uname)
        ):
            selected.append(p)
    # If the schema doesn't contain university association fields, keep all as match candidates,
    # but the matching result remains only a suggestion.
    return selected or programs


def scrape(args):
    data_dir, out = Path(args.data_dir), Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    universities = read_json(data_dir / "universities.json")
    programs = read_json(data_dir / "programs.json")
    reg_path = source_registry_path(out)
    if not reg_path.exists():
        logging.info("Source registry not found; running discovery first.")
        discover(args)
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    all_observations, all_reviews, errors = [], [], []
    for idx, entry in enumerate(registry, 1):
        university = {
            k: entry.get(k)
            for k in ("universityId", "universityName", "officialWebsite")
        }
        prog_subset = program_candidates_for_university(
            programs, entry["universityId"], entry["universityName"]
        )
        sources = entry.get("sources", []) + entry.get("manuallyAddedSources", [])
        logging.info(
            "[%s/%s] Scraping %s (%s sources)",
            idx,
            len(registry),
            entry["universityName"],
            len(sources),
        )
        if not sources:
            all_reviews.append(
                review_row(
                    university,
                    entry.get("officialWebsite", ""),
                    "",
                    "no_sources_discovered",
                    "Add the official tuition URL to output/tuition_sources.json under manuallyAddedSources.",
                )
            )
        for source in sources:
            url = source.get("url", "")
            if not url:
                continue
            kind = source.get("kind", "")
            if kind == "pdf" or url.lower().endswith(".pdf"):
                obs, rev = parse_pdf(url, university, args.academic_year, prog_subset)
            else:
                html, title, final_url, err = page_html(url, args.playwright)
                if err or html is None:
                    errors.append(
                        {
                            "universityName": entry["universityName"],
                            "url": url,
                            "error": err or "empty response",
                        }
                    )
                    all_reviews.append(
                        review_row(
                            university,
                            url,
                            "",
                            "page_fetch_failed",
                            err or "empty response",
                        )
                    )
                    continue
                obs, rev = extract_html_observations(
                    html,
                    final_url,
                    title or source.get("title", ""),
                    university,
                    args.academic_year,
                    prog_subset,
                )
            all_observations.extend(obs)
            all_reviews.extend(rev)
            time.sleep(DELAY_SECONDS)
    # Add review flags for unverified academic year and fuzzy program match.
    for o in all_observations:
        if not o["academicYearExplicitlyFound"]:
            o["reviewNotes"] += (
                " Page text did not clearly identify 2026-2027; verify the year."
            )
        if not o["programId"]:
            all_reviews.append(
                review_row(
                    {
                        "universityId": o["universityId"],
                        "universityName": o["universityName"],
                    },
                    o["sourceUrl"],
                    o["sourcePageTitle"],
                    "unmatched_program",
                    "Amount extracted but no sufficiently strong program-name suggestion. Context: "
                    + o["sourceContext"][:350],
                )
            )
        elif o["programMatchScore"] is not None:
            all_reviews.append(
                review_row(
                    {
                        "universityId": o["universityId"],
                        "universityName": o["universityName"],
                    },
                    o["sourceUrl"],
                    o["sourcePageTitle"],
                    "verify_program_match",
                    f"Suggested {o['programName']} (score {o['programMatchScore']}); match is not confirmed.",
                )
            )
    # De-duplicate observations while retaining source context.
    seen, unique = set(), []
    for o in all_observations:
        key = (
            o["universityId"],
            o["sourceUrl"],
            o["sourceContext"],
            o["tuitionAmount"],
            o["studentCategory"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(o)
    (out / "tuition.json").write_text(
        json.dumps(unique, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    summaries = build_tuition_summary(unique, args.academic_year)
    (out / "tuition_summary.json").write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(out / "manual_review.csv", all_reviews)
    write_csv(out / "scrape_errors.csv", errors)
    summary = {
        "academicYear": args.academic_year,
        "universitiesInRegistry": len(registry),
        "tuitionObservationsExtracted": len(unique),
        "manualReviewItems": len(all_reviews),
        "scrapeErrors": len(errors),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "warning": "Extraction does not establish that a value is correct tuition for a matched program. Verify every record before production use.",
    }
    (out / "scrape_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    logging.info(
        "Extracted %s candidate observations; %s summaries; %s review items; %s errors.",
        len(unique),
        len(summaries),
        len(all_reviews),
        len(errors),
    )
    logging.info("Outputs: %s", out.resolve())


def build_tuition_summary(observations, academic_year):
    """Aggregate scraped observations into per-university/program tuition summaries.

    Only per-term tuition figures are used ("Credits Per Term"); one academic year
    is annualised as 2 terms. Groups by (university, program); for each of the
    three tuition categories picks the median amount, preferring observations
    where the academic year was explicit.
    """
    from statistics import median

    # Strict: per-term tuition only. Annualise as 2 terms = 1 year.
    observations = [o for o in observations if o.get("feePeriod") == "term"]

    groups = {}
    for o in observations:
        key = (
            o["universityId"],
            o["universityName"],
            o.get("programId"),
            o.get("programName"),
        )
        groups.setdefault(key, []).append(o)

    summaries = []
    for (uid, uname, pid, pname), obs in sorted(
        groups.items(), key=lambda kv: (kv[0][1], kv[0][3] or "")
    ):
        tuition = {}
        year_verified = True
        for o in obs:
            skey = SUMMARY_CATEGORY_KEYS.get(o.get("studentCategory", ""))
            if not skey:
                continue
            tuition.setdefault(skey, []).append(
                (o["tuitionAmount"], bool(o.get("academicYearExplicitlyFound")))
            )
            if not o.get("academicYearExplicitlyFound"):
                year_verified = False
        tuition_out = {}
        for skey, vals in tuition.items():
            # Prefer amounts from pages where the year was explicit; else use all.
            explicit = [v for v, y in vals if y]
            pool = explicit or [v for v, _ in vals]
            # Annualise: per-term figure x 2 terms.
            tuition_out[skey] = round(median(pool) * 2, 2)
        comments = "tuition only (annualised from per-term figures)"
        if not tuition_out:
            comments += "; no per-term tuition figures found on source page"
        if not year_verified:
            comments += "; academic year not explicitly confirmed on source page"
        summaries.append(
            {
                "universityId": uid,
                "universityName": uname,
                "programId": pid,
                "programName": pname,
                "academicYear": academic_year,
                "tuition": tuition_out,
                "comments": comments,
            }
        )
    return summaries


def summarize(args):
    """Build tuition_summary.json from an existing output/tuition.json (no scraping)."""
    out = Path(args.output_dir)
    src = out / "tuition.json"
    if not src.exists():
        sys.exit(
            f"No {src} found. Run 'scrape' first, or point --output-dir at a folder containing tuition.json."
        )
    observations = json.loads(src.read_text(encoding="utf-8"))
    summaries = build_tuition_summary(observations, args.academic_year)
    dest = out / "tuition_summary.json"
    dest.write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logging.info("Wrote %s summaries to %s", len(summaries), dest)


def write_csv(path, rows):
    rows = list(rows)
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Discover and scrape official Ontario university tuition sources."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("discover", "scrape", "all", "summarize"):
        p = sub.add_parser(name)
        p.add_argument(
            "--data-dir",
            default=".",
            help="Folder containing universities.json and programs.json",
        )
        p.add_argument("--output-dir", default="output", help="Output directory")
        p.add_argument("--academic-year", default=YEAR_DEFAULT)
        p.add_argument(
            "--playwright",
            action="store_true",
            help="Render HTML pages in Chromium for JS content (slower)",
        )
    args = parser.parse_args()
    if args.command in ("discover", "all"):
        discover(args)
    if args.command in ("scrape", "all"):
        scrape(args)
    if args.command == "summarize":
        summarize(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Cancelled.")
    except Exception as exc:
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
