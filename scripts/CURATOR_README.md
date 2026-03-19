# Data Curator Reference — Ghana Audio Transcription

---

## Repo structure

```
transcriber/
├── transcriber.py          ← volunteers run this
├── README.md               ← volunteer instructions
├── CURATOR_README.md       ← you are here
└── scripts/
    └── generate_codes.py   ← generate codes + zip archives
```

Private files (never commit):
```
scripts/volunteer_codes.csv       ← all codes and assignments
scripts/volunteer_archives/       ← per-volunteer zip archives
```

HuggingFace output repo:
```
ghananlpcommunity/ghana-asr-transcripts
```

---

## Step 1 — Prepare your audio

Organise audio files into per-language folders (paths can be anywhere):

```
/your/path/twi/        ← all Twi .mp3 / .wav files
/your/path/ewe/
/your/path/dagbani/
```

---

## Step 2 — Generate codes and archives

Open `scripts/generate_codes.py` and set the config block at the top:

```python
LANGUAGE_AUDIO_DIRS = {
    "twi":     "/path/to/twi/audio",
    "ewe":     "/path/to/ewe/audio",
    "dagbani": "/path/to/dagbani/audio",
}
HF_TOKEN = "hf_..."          # write token for the output HF repo
VOLUNTEERS_PER_LANGUAGE = {
    "twi": 12, "ewe": 2, "dagbani": 2,
}
ARCHIVES_DIR = "scripts/volunteer_archives"
```

Then run:

```bash
python scripts/generate_codes.py
```

**Re-running is safe** — if a volunteer's `.zip` already exists it is skipped. Only new volunteers get new archives. Codes are always regenerated and saved to `volunteer_codes.csv`.

The code for each volunteer encodes their language, assigned file IDs, and HF token — the transcriber app uses all three automatically.

---

## Step 3 — Distribute

Each volunteer needs **two things**, sent separately:

1. **Their `.zip` archive** — via Drive, WeTransfer, WhatsApp, etc.
2. **Their code string** — via message or email

They extract the zip, run `python transcriber.py`, paste their code, and point the app at the folder. The app handles everything else.

> Keep `volunteer_codes.csv` private — it contains the HF token for every volunteer.

---

## Step 4 — Share the app

Send volunteers to the repo and ask them to follow README.md:

```
https://github.com/GhanaNLP/transcriber
```

What volunteers need:
- Python 3.8+
- Git
- Their zip archive (extracted)
- Their code string

On Linux they also need: `sudo apt install python3-tk xclip wl-clipboard git`

---

## How language checking works

Each volunteer's code contains their assigned language. When a transcript is pasted, the app uses [tiny-lang-detector](https://github.com/GhanaNLP/tiny-lang-detector) to check that it matches. This catches accidental wrong pastes without bothering volunteers whose audio genuinely contains heavy English mixing.

The detector is cloned and installed automatically when the app first runs — volunteers don't do anything.

Thresholds (in `transcriber.py`):
- `LANG_DETECTION_WARN_THRESHOLD = 0.40` — below this, show a warning (saveable)
- `LANG_DETECTION_BLOCK_THRESHOLD = 0.15` — below this, block saving

---

## Monitoring progress

Transcripts are pushed to:
```
https://huggingface.co/datasets/ghananlpcommunity/ghana-asr-transcripts
```

Each commit is labelled:
```
Volunteer a3f8c912: 10 transcript(s) [lang=twi]
```

Files are stored as:
```
transcripts/twi/<filename>__<vol_hash>.txt
```

The `__vol_hash` suffix means multiple volunteers never overwrite each other.

---

## Troubleshooting

**"Assignment mismatch"**
Volunteer selected the wrong folder. Ask them to re-extract their specific zip.

**Push keeps failing**
Check that the HF token in `generate_codes.py` still has write access. Re-generate codes and redistribute if needed.

**Adding more volunteers mid-run**
Increase `VOLUNTEERS_PER_LANGUAGE` and re-run `generate_codes.py`. Existing archives are untouched.

**Volunteer needs to restart**
They delete their transcripts output folder and reopen the app with the same audio folder and code.

**Volunteer lost their code**
Re-send it from `volunteer_codes.csv`. It will be saved again once they enter it.
