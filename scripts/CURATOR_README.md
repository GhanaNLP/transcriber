# Data Curator Reference — Ghana Audio Transcription

Everything you need to run this project from start to finish.

---

## Repo Structure

```
ghana-transcriber/
├── transcribe.py                        ← volunteers run this
├── README.md                            ← volunteer-facing instructions
├── .gitignore
├── .github/
│   └── ISSUE_TEMPLATE/
│       └── result_submission.md         ← pre-fills the GitHub submission form
└── scripts/
    ├── DATA_CURATOR_README.md           ← you are here
    ├── upload_to_hf.py                  ← run once to upload audio to HuggingFace
    ├── generate_codes.py                ← generate one code per volunteer
    └── merge_results.py                 ← fetch submissions and merge transcripts
```

Private files (never commit these):
```
manifest.csv             ← produced by upload_to_hf.py, keep locally
volunteer_codes.json     ← all codes + file ID lists
.github_token            ← saved GitHub token for private repo access
```

---

## One-Time Setup

### 1. Upload audio to HuggingFace

Open `scripts/upload_to_hf.py` and set:

```python
HF_REPO          = "your-hf-username/ghana-audio-master"
HF_TOKEN         = "hf_..."          # or export HF_TOKEN=hf_...
LANGUAGE_FOLDERS = {
    "twi":     "/path/to/twi",
    "ewe":     "/path/to/ewe",
    "dagbani": "/path/to/dagbani",
}
```

Then run:

```bash
pip install huggingface_hub pandas
python scripts/upload_to_hf.py
```

This uploads all audio files and writes `manifest.csv` locally. Commit `manifest.csv` to the repo.

---

### 2. Configure generate_codes.py

Open `scripts/generate_codes.py` and set:

```python
HF_REPO      = "your-hf-username/ghana-audio-master"   # same as above
MANIFEST_CSV = "manifest.csv"

FILES_PER_LANGUAGE = {
    "twi":     200,    # total files to share across twi volunteers
    "ewe":     200,
    "dagbani": 200,
}

VOLUNTEERS_PER_LANGUAGE = {
    "twi":     2,
    "ewe":     2,
    "dagbani": 1,
}
```

Then run:

```bash
pip install pandas
python scripts/generate_codes.py
```

This prints a table of codes and saves `volunteer_codes.json`. Send **one code per volunteer** — keep `volunteer_codes.json` private.

---

### 3. Configure merge_results.py

Open `scripts/merge_results.py` and set:

```python
GITHUB_REPO = "your-username/ghana-transcriber"
```

---

### 4. Commit and push

```bash
git add transcribe.py manifest.csv README.md scripts/ .github/ .gitignore
git commit -m "Initial setup"
git push
```

Make sure `.gitignore` contains:
```
.env
volunteer_codes.json
.github_token
```

---

## Tracking Submissions

Submissions arrive as GitHub Issues labelled **results**. View them at:

```
https://github.com/YOUR_USERNAME/ghana-transcriber/issues?q=label%3Aresults
```

Each issue should have a `.zip` file attached containing the volunteer's transcripts folder.

---

## Merging Results

```bash
pip install requests
python scripts/merge_results.py
```

The script:
1. Fetches all issues labelled `results` from your GitHub repo
2. Downloads every `.zip` attachment
3. Extracts `.txt` transcripts and organises them into `merged_transcripts/<lang>/`
4. Skips files already downloaded — safe to re-run as more submissions arrive
5. Prints a per-language summary

For a **private repo**, the script will prompt for a GitHub token once, then save it to `.github_token`.  
Create one at: https://github.com/settings/tokens/new (tick **repo** scope).

---

## If a Volunteer Has Problems

**Download fails / slow connection:**  
Their partially downloaded files are kept — re-running `python transcribe.py --code <code>` resumes from where it left off (already-downloaded files are skipped).

**They need to restart from scratch:**  
They delete their local `audio/` folder and re-run with the same code.

**You need more volunteers mid-run:**  
Increase `VOLUNTEERS_PER_LANGUAGE` or `FILES_PER_LANGUAGE` in `generate_codes.py` and regenerate. New codes will cover only the files not yet assigned.
