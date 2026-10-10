#!/usr/bin/env python3
"""Brock University tuition via the undergraduate fees estimator.
Fills: <Category> - Arts and Sciences, 5.0 credits, No co-op,
No Entrance Award, No Residence Required. Reads the tuition row only
(ignores ancillary fees, awards, residence). Saves output/brock_tuition.json.

Requires: pip install playwright && playwright install chromium
"""

import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://brocku.ca/safa/undergraduate-fees-estimator/"
AMOUNT_RE = re.compile(r"\$([\d,]+\.\d{2})")

# Set to a list of exact "Tuition Category" labels to run only those.
# Leave as None to auto-discover ALL categories from the dropdown.
# 5.0 credits, no co-op, no entrance award, no residence for every run.
PROGRAMS = None
# Example: PROGRAMS = ["Domestic - Arts and Sciences", "International - Engineering"]


def find_select(page, label_text):
    """Find a <select> near a label containing the given text (Gravity Forms markup varies)."""
    # Try: label element -> following select
    label = page.locator(f"text={label_text}").first
    # Look for a select inside the same field container
    container = label.locator("xpath=ancestor::*[contains(@class, 'gfield')][1]")
    sel = container.locator("select").first
    if sel.count() > 0:
        return sel
    # Fallback: next select after the label in DOM order
    sel = label.locator("xpath=following::select[1]")
    if sel.count() > 0:
        return sel
    raise RuntimeError(f"Could not find select for label: {label_text}")


def run_estimator(page, category):
    print(f"Navigating to {URL} ...")
    try:
        resp = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        print(f"  HTTP status: {resp.status if resp else 'no response'}")
    except Exception as e:
        print(f"  GOTO FAILED: {e}")
        raise
    page.wait_for_timeout(3000)
    print(f"  Current URL: {page.url}")
    print(f"  Title: {page.title()}")
    if "brocku.ca" not in page.url:
        raise RuntimeError(f"Navigation did not reach Brock site (at {page.url})")
    # Wait for Cloudflare "Just a moment..." challenge to clear (up to 30s)
    for i in range(30):
        title = page.title()
        if "just a moment" not in title.lower():
            break
        print(f"  Waiting for Cloudflare challenge... ({i + 1}s)")
        page.wait_for_timeout(1000)
    else:
        raise RuntimeError("Cloudflare challenge did not clear after 30s")
    print(f"  Page ready: {page.title()}")
    page.wait_for_timeout(2000)

    # Step 1: Tuition Category (wait for options to populate)
    cat_select = find_select(page, "Tuition Category")
    try:
        cat_select.wait_for(timeout=15000)
        # Wait until our option appears in the dropdown
        page.wait_for_function(
            """(label) => {
                const sel = document.querySelector('select[name="input_7"]');
                if (!sel) return false;
                return Array.from(sel.options).some(o => o.text.trim() === label);
            }""",
            arg=category,
            timeout=15000,
        )
    except Exception as e:
        available = cat_select.locator("option").all_inner_texts()
        raise RuntimeError(
            f"Option '{category}' not in Tuition Category dropdown. "
            f"Available: {available}"
        ) from e
    cat_select.select_option(label=category)
    page.wait_for_timeout(1200)

    # Step 1: Number of credits -> 5.0 (combobox needs keyboard nav)
    credits = find_select(page, "Number of credits:")
    credits.click()
    # Move from 0.0 to 5.0 = 10 steps of 0.5
    for _ in range(10):
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(150)
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)

    # Step 1: co-op -> No (first "No" radio on the page)
    page.locator("text=Are you entering into a co-op program?").first.locator(
        "xpath=ancestor::*[contains(@class, 'gfield')][1]"
    ).locator("input[type=radio][value*=No], label:has-text('No')").first.click()
    page.wait_for_timeout(500)

    # Next -> Step 2
    page.get_by_role("button", name="Next").click()
    page.wait_for_timeout(2000)

    # Step 2: No Entrance Award
    find_select(page, "Estimated Admission Average").select_option(
        label="No Entrance Award"
    )
    page.wait_for_timeout(800)
    page.get_by_role("button", name="Next").click()
    page.wait_for_timeout(2000)

    # Step 3: No Residence Required (default) -> Next
    page.get_by_role("button", name="Next").click()
    page.wait_for_timeout(2000)

    # Step 4: Submit to reveal breakdown
    page.get_by_role("button", name="Submit").click()
    page.wait_for_timeout(3000)

    # Results table: find the tuition row (labelled with the category name)
    tuition = None
    for row in page.locator("table tr").all():
        cells = [c.inner_text().strip() for c in row.locator("td, th").all()]
        if len(cells) >= 4 and category.lower() in cells[0].lower():
            m = AMOUNT_RE.search(cells[3])  # Price column
            if m:
                tuition = float(m.group(1).replace(",", ""))
                break
    return tuition


def slugify(label):
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return s or "program"


def discover_categories(page):
    """Read every option from the Tuition Category dropdown (skips placeholder)."""
    sel = find_select(page, "Tuition Category")
    sel.wait_for(timeout=15000)
    options = sel.locator("option").all_inner_texts()
    cats = []
    for o in options:
        t = o.strip()
        if not t or "select" in t.lower() and len(t) < 30:
            continue
        cats.append(t)
    return cats


def tuition_key(category_label):
    low = category_label.lower()
    if "out of province" in low or "out-of-province" in low:
        return "domestic-out-province"
    if low.startswith("international"):
        return "international"
    return "domestic-in-province"


def main():
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        # Use real Chrome (not bundled Chromium) to pass Cloudflare checks.
        # Requires Google Chrome installed. Falls back to Chromium if unavailable.
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            print("Using real Chrome")
        except Exception as e:
            print(f"Real Chrome not found ({e}); falling back to Chromium")
            browser = p.chromium.launch(
                headless=True, args=["--disable-blink-features=AutomationControlled"]
            )
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Discover categories on first load if not specified
        if PROGRAMS is None:
            page.goto(URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            categories = discover_categories(page)
            print(f"Discovered {len(categories)} tuition categories:")
            for c in categories:
                print(f"  - {c}")
        else:
            categories = list(PROGRAMS)

        summaries = []
        for category in categories:
            program_id = slugify(category)
            print(f"\n=== {program_id} ({category}) ===")
            try:
                tuition = run_estimator(page, category)
            except Exception as e:
                print(f"FAILED: {e}")
                tuition = None
            print(f"Tuition: {tuition}")
            key = tuition_key(category)
            entry = {
                "universityId": "brock",
                "universityName": "Brock",
                "programId": program_id,
                "programName": category,
                "academicYear": "2026-2027",
                "tuition": {key: tuition} if tuition else {},
                "comments": "tuition only (from fees estimator: 5.0 credits, no co-op, no award, no residence)",
            }
            summaries.append(entry)

        browser.close()

    dest = out_dir / "brock_tuition.json"
    dest.write_text(json.dumps(summaries, indent=2))
    print(f"\nWrote {len(summaries)} summaries to {dest}")


if __name__ == "__main__":
    main()
