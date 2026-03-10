#!/usr/bin/env python3
"""
generate_codes.py — Data Curator Only
=======================================
Generates one code per volunteer. Each code encodes:
  - The HF dataset repo
  - The volunteer's assigned language
  - The exact list of file IDs they should download and transcribe

Setup:
    pip install pandas

Run:
    python scripts/generate_codes.py
"""

import base64
import json
import os
import sys
import math

# ════════════════════════════════════════════
#  ✏️  CONFIGURE HERE
# ════════════════════════════════════════════

HF_REPO      = "your-hf-username/ghana-audio-master"   # same repo used in upload_to_hf.py
MANIFEST_CSV = "manifest.csv"                           # produced by upload_to_hf.py

# How many audio files to assign per language across all volunteers for that language.
# Set to None to assign ALL available files for that language.
FILES_PER_LANGUAGE = {
    "twi":     200,   # total files to distribute across twi volunteers
    "ewe":     200,
    "dagbani": 200,
}

# Number of volunteers per language
VOLUNTEERS_PER_LANGUAGE = {
    "twi":     2,
    "ewe":     2,
    "dagbani": 1,
}

# ════════════════════════════════════════════


def check_config():
    errors = []
    if HF_REPO.startswith("your-hf-username"):
        errors.append("  HF_REPO still has a placeholder — update it at the top of this script")
    if not os.path.exists(MANIFEST_CSV):
        errors.append(f"  manifest.csv not found at: {MANIFEST_CSV} — run upload_to_hf.py first")
    if errors:
        sys.exit("❌  Fix these before running:\n" + "\n".join(errors))


def encode_code(hf_repo, language, file_ids):
    payload = json.dumps({
        "repo": hf_repo,
        "lang": language,
        "ids":  file_ids,
    }, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def generate(manifest_path, hf_repo):
    try:
        import pandas as pd
    except ImportError:
        sys.exit("❌  Run: pip install pandas")

    df = pd.read_csv(manifest_path)
    volunteers = []
    vol_number = 1

    for lang in ["twi", "ewe", "dagbani"]:
        n_vols  = VOLUNTEERS_PER_LANGUAGE.get(lang, 0)
        n_files = FILES_PER_LANGUAGE.get(lang)

        if n_vols == 0:
            continue

        lang_df = df[df["language"] == lang].reset_index(drop=True)
        total_available = len(lang_df)

        if total_available == 0:
            print(f"  ⚠️   No files found for language '{lang}' in manifest — skipping.")
            continue

        if n_files is None or n_files > total_available:
            n_files = total_available

        # Take the first n_files rows
        selected = lang_df.iloc[:n_files]
        ids = selected["id"].tolist()

        # Split IDs evenly across volunteers
        slice_size = math.ceil(len(ids) / n_vols)
        for i in range(n_vols):
            chunk = ids[i * slice_size : (i + 1) * slice_size]
            if not chunk:
                break
            code = encode_code(hf_repo, lang, chunk)
            volunteers.append({
                "volunteer":  vol_number,
                "language":   lang,
                "file_count": len(chunk),
                "file_ids":   chunk,
                "code":       code,
            })
            vol_number += 1

    return volunteers


if __name__ == "__main__":
    check_config()

    print("📂  Reading manifest...")
    volunteers = generate(MANIFEST_CSV, HF_REPO)

    if not volunteers:
        sys.exit("❌  No volunteers generated — check your manifest and config.")

    # Print summary table
    print(f"\n{'='*90}")
    print(f"  VOLUNTEER CODES")
    print(f"{'='*90}")
    print(f"  {'#':<4} {'LANGUAGE':<12} {'FILES':<8}  CODE")
    print(f"  {'-'*4} {'-'*12} {'-'*8}  {'-'*55}")
    for v in volunteers:
        print(f"  {v['volunteer']:<4} {v['language']:<12} {v['file_count']:<8}  {v['code']}")
    print(f"{'='*90}\n")

    # Save full details (includes file IDs) — keep private
    out = [{k: v for k, v in vol.items()} for vol in volunteers]
    with open("volunteer_codes.json", "w") as f:
        json.dump(out, f, indent=2)

    print("  ✅  Codes saved to volunteer_codes.json")
    print("  ⚠️   Keep volunteer_codes.json private — share only the individual codes.\n")
