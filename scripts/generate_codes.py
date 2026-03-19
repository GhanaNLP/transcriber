#!/usr/bin/env python3
"""
generate_codes.py — Data Curator Only
=======================================
Generates one volunteer code and one highly compressed .zip (LZMA/xz) archive
per volunteer.  Each code encodes ONLY the metadata the volunteer needs to:
  - Know which language they are assigned
  - Verify that the audio files they received are the right ones
  - Push their transcripts to the HF repo

Audio files are distributed manually via the generated archives.
No audio download happens inside the transcriber app.
"""

import base64
import json
import os
import sys
import math
import csv
import glob
import zipfile
from pathlib import Path

# ── Compression: LZMA (xz) is the best available in stdlib ───────────────────
try:
    import lzma  # noqa – just checking availability
    ZIP_COMPRESSION      = zipfile.ZIP_LZMA
    ZIP_COMPRESSION_NAME = "LZMA (xz)"
except ImportError:
    ZIP_COMPRESSION      = zipfile.ZIP_DEFLATED
    ZIP_COMPRESSION_NAME = "DEFLATE (lzma not available)"

# ════════════════════════════════════════════
#  ✏️  CONFIGURE HERE
# ════════════════════════════════════════════

# Per-language audio directories.
# Set each value to the folder containing that language's audio files.
# Paths can be completely independent — no shared parent required.
LANGUAGE_AUDIO_DIRS = {
    "twi":     "/media/owusus/Godstestimo/NLP-Projects/new-Speech-Data/UNICEFSpeech/mp3/mp3_chunks_twi",
    "ewe":     "/media/owusus/Godstestimo/NLP-Projects/new-Speech-Data/UNICEFSpeech/mp3/mp3_chunks_ewe",
    "dagbani": "/media/owusus/Godstestimo/NLP-Projects/new-Speech-Data/UNICEFSpeech/mp3/mp3_chunks_dagbani",
}

# HF write token embedded in each code — gives volunteers push access
HF_TOKEN = "HF_TOKEN_TO_REPO_FOR_PUSHING_UPDATES"

# How many audio files to assign per language across all volunteers.
# Set to None to use ALL available files for that language.
FILES_PER_LANGUAGE = {
    "twi":     None,
    "ewe":     None,
    "dagbani": None,
}

# Number of volunteers per language
VOLUNTEERS_PER_LANGUAGE = {
    "twi":     12,
    "ewe":     2,
    "dagbani": 2,
}

# Output directory for the per-volunteer zip archives
ARCHIVES_DIR = "/media/owusus/Godstestimo/NLP-Projects/new-Speech-Data/UNICEFSpeech/volunteer_audio_zips"

# ════════════════════════════════════════════


def check_config():
    errors = []
    if HF_TOKEN == "hf_YOUR_TOKEN_HERE" or not HF_TOKEN.startswith("hf_"):
        errors.append("  HF_TOKEN still has a placeholder.")
    for lang, path in LANGUAGE_AUDIO_DIRS.items():
        if not path or path.startswith("/path/to/"):
            errors.append(f"  LANGUAGE_AUDIO_DIRS['{lang}'] still has a placeholder path.")
        elif not os.path.exists(path):
            errors.append(f"  LANGUAGE_AUDIO_DIRS['{lang}']: directory not found: {path}")
    if errors:
        sys.exit("❌  Fix these before running:\n" + "\n".join(errors))


def encode_code(language, file_ids, hf_token):
    """
    Encode a compact JSON payload into a URL-safe base64 string.
    Carries language, assigned file IDs (for verification), and HF write token.
    """
    payload = json.dumps({
        "lang": language,
        "ids":  file_ids,
        "tok":  hf_token,
    }, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def build_archive(zip_path, file_paths, compression):
    """Create a zip archive with maximum LZMA compression."""
    with zipfile.ZipFile(zip_path, "w", compression=compression,
                         compresslevel=9) as zf:
        for fpath in file_paths:
            zf.write(fpath, arcname=os.path.basename(fpath))
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    return size_mb


def generate():
    os.makedirs(ARCHIVES_DIR, exist_ok=True)
    volunteers = []
    vol_number = 1

    for lang in ["twi", "ewe", "dagbani"]:
        n_vols  = VOLUNTEERS_PER_LANGUAGE.get(lang, 0)
        n_files = FILES_PER_LANGUAGE.get(lang)

        if n_vols == 0:
            continue

        lang_dir = LANGUAGE_AUDIO_DIRS.get(lang, "")
        if not lang_dir or not os.path.exists(lang_dir):
            print(f"  ⚠️   No folder found for '{lang}' at {lang_dir} — skipping.")
            continue

        # Collect all audio files for this language
        all_files = []
        for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"):
            all_files.extend(glob.glob(os.path.join(lang_dir, ext)))
        all_files = sorted(all_files)
        total_available = len(all_files)

        if total_available == 0:
            print(f"  ⚠️   No audio files found for '{lang}' — skipping.")
            continue

        if n_files is None or n_files > total_available:
            n_files = total_available

        selected_files = all_files[:n_files]
        slice_size     = math.ceil(len(selected_files) / n_vols)

        print(f"\n  [{lang.upper()}]  {total_available} files available → "
              f"assigning {n_files} across {n_vols} volunteer(s)  "
              f"(~{slice_size} files each)")

        for i in range(n_vols):
            chunk_paths = selected_files[i * slice_size : (i + 1) * slice_size]
            if not chunk_paths:
                break

            chunk_ids    = [Path(p).stem for p in chunk_paths]
            code         = encode_code(lang, chunk_ids, HF_TOKEN)
            zip_filename = os.path.join(
                ARCHIVES_DIR, f"volunteer_{vol_number:03d}_{lang}.zip"
            )

            print(f"    📦  Vol {vol_number:03d}: {len(chunk_paths)} files → "
                  f"{os.path.basename(zip_filename)} … ", end="", flush=True)
            size_mb = build_archive(zip_filename, chunk_paths, ZIP_COMPRESSION)
            print(f"{size_mb:.1f} MB")

            volunteers.append({
                "volunteer":  vol_number,
                "language":   lang,
                "file_count": len(chunk_ids),
                "file_ids":   chunk_ids,
                "code":       code,
                "archive":    zip_filename,
            })
            vol_number += 1

    return volunteers


if __name__ == "__main__":
    print(f"🗜️   Compression: {ZIP_COMPRESSION_NAME}\n")
    check_config()

    print("📂  Reading local audio files and generating volunteer archives…")
    volunteers = generate()

    if not volunteers:
        sys.exit("❌  No volunteers generated — check your folders and config.")

    # ── Print summary table ───────────────────────────────────────────────────
    col = 110
    print(f"\n{'=' * col}")
    print(f"  VOLUNTEER CODES  (share each code + its archive zip independently)")
    print(f"{'=' * col}")
    print(f"  {'#':<5} {'LANGUAGE':<10} {'FILES':<6} {'ARCHIVE':<35} CODE")
    print(f"  {'-'*5} {'-'*10} {'-'*6} {'-'*35} {'-'*45}")
    for v in volunteers:
        print(f"  {v['volunteer']:<5} {v['language']:<10} {v['file_count']:<6} "
              f"{os.path.basename(v['archive']):<35} {v['code']}")
    print(f"{'=' * col}\n")

    # ── Save CSV ─────────────────────────────────────────────────────────────
    csv_filename = "volunteer_codes.csv"
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as f:
        fieldnames = ["volunteer", "language", "file_count", "file_ids", "code", "archive"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for vol in volunteers:
            row = vol.copy()
            row["file_ids"] = ",".join(str(fid) for fid in row["file_ids"])
            writer.writerow(row)

    print(f"  ✅  Codes saved to {csv_filename}")
    print(f"  📁  Archives saved in  ./{ARCHIVES_DIR}/")
    print()
    print(f"  📬  HOW TO DISTRIBUTE:")
    print(f"       1. Send each volunteer their .zip archive (via Drive, WeTransfer, etc.)")
    print(f"       2. Send them their individual code string separately.")
    print(f"       3. They extract the zip and point the app at those audio files.")
    print()
    print(f"  ⚠️   Keep {csv_filename} private — it contains all tokens.")
    print()
