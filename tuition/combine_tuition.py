#!/usr/bin/env python3
"""Combine per-university scraper outputs into one app-ready tuition file.

Reads every <name>_tuition*.json (shared entry-list schema) in the input dir
-- raw/debug files (*raw*.json) are skipped -- and writes a single JSON:

  {
    "<universityId>": {
      "universityId": "...",
      "universityName": "...",
      "tuitionByMajor": {
        "<programName>": {
          "tuition": ...,       # domestic in-province (omit if absent)
          "tuitionOop": ...,    # domestic out-of-province (omit if absent)
          "tuitionIntl": ...,   # international (omit if absent)
          "tuitionYear": "2026-2027",
          "tuitionNote": "..."
        }
      }
    }
  }

Usage:
    python combine_tuition.py [input_dir] [output_file]
Defaults: input_dir="output", output_file="<input_dir>/all-tuition.json".
Requires: nothing beyond the Python standard library.
"""

import glob
import json
import os
import re
import sys

# Scraper tuition key -> app tuitionByMajor key.
KEY_MAP = {
    "domestic-in-province": "tuition",
    "domestic-out-of-province": "tuitionOop",
    "domestic-out-province": "tuitionOop",  # older spelling, same meaning
    "international": "tuitionIntl",
}


def clean_program_name(name: str) -> str:
    """Strip the 'Domestic -'/'Domestic ' prefix; it is not the program name."""
    return re.sub(r"^Domestic(?:\s*-\s*|\s+)", "", name).strip()


def convert_entry(entry):
    """Convert one scraper entry to a tuitionByMajor value dict."""
    major = {}
    for k, v in (entry.get("tuition") or {}).items():
        if k not in KEY_MAP:
            print(f"  warn: unknown tuition key {k!r} "
                  f"in {entry.get('universityId')}/{entry.get('programName')}")
            continue
        major[KEY_MAP[k]] = v
    major["tuitionYear"] = entry.get("academicYear")
    major["tuitionNote"] = entry.get("comments")
    return major


def main() -> None:
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "output"
    out_path = (sys.argv[2] if len(sys.argv) > 2
                else os.path.join(input_dir, "all-tuition.json"))

    files = sorted(glob.glob(os.path.join(input_dir, "*_tuition*.json")))
    files = [f for f in files if "raw" not in os.path.basename(f).lower()]
    if not files:
        raise SystemExit(f"No *_tuition*.json files found in {input_dir!r}")

    combined = {}
    total_programs = 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            print(f"  skip (not an entry list): {path}")
            continue
        print(f"  {os.path.basename(path)}: {len(entries)} entries")
        for e in entries:
            uid = e.get("universityId")
            if not uid:
                print(f"  warn: entry without universityId in {path}")
                continue
            uni = combined.setdefault(uid, {
                "universityId": uid,
                "universityName": e.get("universityName"),
                "tuitionByMajor": {},
            })
            if uni["universityName"] != e.get("universityName"):
                print(f"  warn: name mismatch for {uid}: "
                      f"{uni['universityName']!r} vs {e.get('universityName')!r}")
            name = e.get("programName") or e.get("programId") or "?"
            if e.get("programName"):
                name = clean_program_name(name)
            majors = uni["tuitionByMajor"]
            if name in majors:
                print(f"  warn: duplicate program {uid}/{name} -- merging keys")
                majors[name].update(convert_entry(e))
            else:
                majors[name] = convert_entry(e)
            total_programs += 1

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"Combined {len(combined)} universities, "
          f"{total_programs} programs -> {out_path}")


if __name__ == "__main__":
    main()
