#!/usr/bin/env python3
"""
upload_to_hf.py — Data Curator Only
=====================================
Scans your local twi/, ewe/, dagbani/ folders, assigns each file a unique ID,
and uploads everything to a Hugging Face dataset repo as the master dataset.

Setup:
    pip install huggingface_hub pandas

Run:
    python upload_to_hf.py
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path

# ════════════════════════════════════════════
#  ✏️  CONFIGURE HERE
# ════════════════════════════════════════════

HF_REPO        = "your-hf-username/ghana-audio-master"   # HF dataset repo to create/push to
HF_TOKEN       = ""                                        # Your HF write token (or set HF_TOKEN env var)

LANGUAGE_FOLDERS = {
    "twi":     "/path/to/twi",
    "ewe":     "/path/to/ewe",
    "dagbani": "/path/to/dagbani",
}

# ════════════════════════════════════════════


def check_config():
    errors = []
    if HF_REPO.startswith("your-hf-username"):
        errors.append("  HF_REPO still has a placeholder — update it at the top of this script")
    for lang, path in LANGUAGE_FOLDERS.items():
        if path.startswith("/path/to/"):
            errors.append(f"  LANGUAGE_FOLDERS['{lang}'] still has a placeholder")
        elif not os.path.isdir(path):
            errors.append(f"  Folder not found for '{lang}': {path}")
    if errors:
        sys.exit("❌  Fix these before running:\n" + "\n".join(errors))


def collect_files(language_folders):
    """Walk each language folder and return a list of dicts with id, lang, filename, local_path."""
    audio_exts = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    records = []
    uid = 1
    for lang, folder in language_folders.items():
        files = sorted(
            p for p in Path(folder).iterdir()
            if p.suffix.lower() in audio_exts
        )
        for p in files:
            records.append({
                "id":         f"{lang}_{uid:05d}",
                "language":   lang,
                "filename":   p.name,
                "local_path": str(p),
            })
            uid += 1
    return records


def upload(records, hf_repo, token):
    try:
        from huggingface_hub import HfApi, CommitOperationAdd
    except ImportError:
        sys.exit("❌  Run: pip install huggingface_hub")

    api = HfApi(token=token)

    # Create the repo if it doesn't exist
    api.create_repo(repo_id=hf_repo, repo_type="dataset", exist_ok=True, private=False)
    print(f"✅  Repo ready: https://huggingface.co/datasets/{hf_repo}\n")

    # Upload manifest CSV
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "local_path"} for r in records])
    manifest_path = "/tmp/manifest.csv"
    df.to_csv(manifest_path, index=False)

    operations = [CommitOperationAdd(path_in_repo="manifest.csv", path_or_fileobj=manifest_path)]

    # Upload audio files into per-language subfolders
    total = len(records)
    for i, rec in enumerate(records, 1):
        dest = f"audio/{rec['language']}/{rec['id']}{Path(rec['local_path']).suffix}"
        print(f"  [{i}/{total}]  {rec['id']}  →  {dest}")
        operations.append(CommitOperationAdd(
            path_in_repo=dest,
            path_or_fileobj=rec["local_path"],
        ))

    print("\n📤  Committing to HuggingFace (this may take a while)...")
    api.create_commit(
        repo_id=hf_repo,
        repo_type="dataset",
        operations=operations,
        commit_message="Upload master audio dataset",
    )

    print(f"\n✅  Done! {total} files uploaded.")
    print(f"    Dataset: https://huggingface.co/datasets/{hf_repo}")
    print(f"    Manifest saved locally to: manifest.csv\n")

    # Save manifest locally too
    df.to_csv("manifest.csv", index=False)
    print("  manifest.csv written locally — commit this to your curator repo.")


if __name__ == "__main__":
    check_config()

    token = HF_TOKEN or os.environ.get("HF_TOKEN", "")
    if not token:
        sys.exit("❌  Set HF_TOKEN in the script or as an environment variable.")

    print("📂  Scanning language folders...")
    records = collect_files(LANGUAGE_FOLDERS)

    lang_counts = {}
    for r in records:
        lang_counts[r["language"]] = lang_counts.get(r["language"], 0) + 1
    for lang, count in lang_counts.items():
        print(f"    {lang:<10} {count:,} files")
    print(f"    {'TOTAL':<10} {len(records):,} files\n")

    upload(records, HF_REPO, token)
