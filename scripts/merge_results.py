#!/usr/bin/env python3
"""
merge_results.py — Data Curator Only
======================================
Fetches all GitHub issues labelled 'results', downloads the attached zip files,
extracts transcripts, and merges them into a single folder organised by language.

Setup:
    pip install requests

Run:
    python scripts/merge_results.py
"""

import os
import sys
import json
import zipfile
import tempfile
import shutil

# ════════════════════════════════════════════
#  ✏️  CONFIGURE HERE
# ════════════════════════════════════════════

GITHUB_REPO  = "your-username/ghana-transcriber"   # e.g. "owusus/ghana-transcriber"
OUTPUT_DIR   = "merged_transcripts"                 # local folder to write merged results into

# ════════════════════════════════════════════

TOKEN_FILE = ".github_token"


def check_config():
    if GITHUB_REPO.startswith("your-username"):
        sys.exit("❌  Set GITHUB_REPO at the top of this script.")


def get_token():
    """Load saved token or prompt once and save it."""
    if os.path.exists(TOKEN_FILE):
        return open(TOKEN_FILE).read().strip()
    # Try public first — no token needed
    return None


def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        f.write(token.strip())
    print(f"  ✅  Token saved to {TOKEN_FILE} (gitignored).\n")


def api_get(url, token=None):
    try:
        import requests
    except ImportError:
        sys.exit("❌  Run: pip install requests")

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(url, headers=headers)
    if r.status_code == 401:
        return None, "auth"
    if r.status_code == 403:
        return None, "auth"
    r.raise_for_status()
    return r, None


def fetch_issues(repo, token):
    """Return all issues labelled 'results'."""
    try:
        import requests
    except ImportError:
        sys.exit("❌  Run: pip install requests")

    issues = []
    page   = 1
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    while True:
        url = f"https://api.github.com/repos/{repo}/issues?labels=results&state=all&per_page=100&page={page}"
        r   = requests.get(url, headers=headers)
        if r.status_code in (401, 403):
            return None, "auth"
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        issues.extend(batch)
        page += 1

    return issues, None


def download_zip_attachments(issue, token, dest_dir):
    """
    GitHub issues don't have formal attachments — volunteers paste a link or
    attach via the issue body/comments. This function scans the body and all
    comments for direct .zip URLs and downloads them.
    """
    try:
        import requests
    except ImportError:
        sys.exit("❌  Run: pip install requests")

    import re
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Collect all text to search (body + comments)
    texts = [issue.get("body") or ""]
    comments_url = issue.get("comments_url", "")
    if comments_url:
        r = requests.get(comments_url, headers=headers)
        if r.ok:
            for c in r.json():
                texts.append(c.get("body") or "")

    full_text = "\n".join(texts)

    # Find .zip links — GitHub user-uploaded files follow this pattern
    zip_urls = re.findall(
        r'https://github\.com/[^\s\)\"]+\.zip|'
        r'https://user-images\.githubusercontent\.com/[^\s\)\"]+\.zip',
        full_text
    )
    # Also match generic direct zip links
    zip_urls += re.findall(r'https?://[^\s\)\"]+\.zip', full_text)
    zip_urls = list(dict.fromkeys(zip_urls))  # deduplicate, preserve order

    downloaded = []
    for url in zip_urls:
        filename = os.path.basename(url.split("?")[0])
        dest     = os.path.join(dest_dir, filename)
        if os.path.exists(dest):
            print(f"    ↩  Already downloaded: {filename}")
            downloaded.append(dest)
            continue
        print(f"    ⬇  Downloading: {filename}")
        r = requests.get(url, headers=headers, stream=True)
        if r.ok:
            with open(dest, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
            downloaded.append(dest)
        else:
            print(f"    ✗  Failed ({r.status_code}): {url}")

    return downloaded


def extract_and_merge(zip_path, output_dir):
    """Extract a zip of transcripts and copy .txt files into output_dir/<lang>/."""
    merged = 0
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp)
        except zipfile.BadZipFile:
            print(f"    ✗  Bad zip file: {zip_path}")
            return 0

        for root, _, files in os.walk(tmp):
            for fname in files:
                if not fname.endswith(".txt") or fname == "skipped.log":
                    continue
                src      = os.path.join(root, fname)
                # Try to infer language from folder structure
                rel      = os.path.relpath(root, tmp)
                parts    = rel.replace("\\", "/").split("/")
                lang     = next(
                    (p for p in parts if p.lower() in ("twi", "ewe", "dagbani")),
                    "unknown"
                )
                lang_dir = os.path.join(output_dir, lang)
                os.makedirs(lang_dir, exist_ok=True)
                dest = os.path.join(lang_dir, fname)
                if not os.path.exists(dest):
                    shutil.copy2(src, dest)
                    merged += 1
                else:
                    # Avoid overwriting — rename with suffix
                    base, ext = os.path.splitext(fname)
                    counter   = 1
                    while os.path.exists(dest):
                        dest = os.path.join(lang_dir, f"{base}_{counter}{ext}")
                        counter += 1
                    shutil.copy2(src, dest)
                    merged += 1
    return merged


if __name__ == "__main__":
    check_config()

    token = get_token()

    print(f"🔍  Fetching issues from {GITHUB_REPO}...")
    issues, err = fetch_issues(GITHUB_REPO, token)

    if err == "auth":
        print("  Private repo or rate limit — a GitHub token is needed.")
        token = input("  Paste your GitHub token (repo scope): ").strip()
        save_token(token)
        issues, err = fetch_issues(GITHUB_REPO, token)
        if err:
            sys.exit("❌  Auth still failed. Check your token has 'repo' scope.")

    if not issues:
        print("  No issues labelled 'results' found.")
        sys.exit(0)

    print(f"  Found {len(issues)} submission(s).\n")

    zips_dir = "downloaded_zips"
    os.makedirs(zips_dir, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_merged = 0

    for issue in issues:
        title  = issue.get("title", "(no title)")
        number = issue.get("number")
        print(f"  📋  #{number}: {title}")
        zips = download_zip_attachments(issue, token, zips_dir)
        for zp in zips:
            n = extract_and_merge(zp, OUTPUT_DIR)
            print(f"       ✅  {n} transcript(s) merged from {os.path.basename(zp)}")
            total_merged += n
        if not zips:
            print(f"       ⚠️   No .zip attachments found in this issue.")

    print(f"\n{'='*60}")
    print(f"  Total transcripts merged : {total_merged}")
    print(f"  Output folder            : {OUTPUT_DIR}/")
    print(f"{'='*60}\n")

    # Print per-language summary
    for lang in sorted(os.listdir(OUTPUT_DIR)):
        lang_path = os.path.join(OUTPUT_DIR, lang)
        if os.path.isdir(lang_path):
            count = len([f for f in os.listdir(lang_path) if f.endswith(".txt")])
            print(f"    {lang:<12}  {count:,} transcripts")
    print()
