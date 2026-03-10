# Transcriber

A lightweight desktop app to assist manual transcribing audio files using Gemini.

## Setup — Linux

```bash
sudo apt install python3-tk xclip wl-clipboard
git clone https://github.com/your-org/transcriber.git
cd transcriber
python transcribe.py
```

## Setup — Windows

```bash
git clone https://github.com/your-org/transcriber.git
cd transcriber
python transcribe.py
```

No extra dependencies needed. Python on Windows includes everything out of the box.

## Running

### With a folder picker dialog (no arguments)

```bash
python transcribe.py
```

A setup window will appear asking you to select your audio and output folders.

### With command-line arguments

```bash
python transcribe.py --audio /path/to/audio --output /path/to/transcripts
```

## How it works

1. Click **"⎘ Copy audio file"** → paste the file into Gemini
2. Click **"✦ Gemini prompt 1"** (or 2) → paste the prompt into Gemini
3. Copy Gemini's response → paste into the textarea
4. The app validates and auto-saves:
   - Consecutive repeated sentences are removed automatically
   - Transcripts outside the 18,000–36,000 character range are blocked — re-paste a better version or click **"Skip ⇥"** to move on
   - Duplicate transcripts (identical to one already saved for another file) are blocked

## Skipping files

Click **"Skip ⇥"** if you can't get a valid transcript after several attempts. The filename is written to `skipped.log` in your output folder so it won't appear again in future sessions. To un-skip a file, remove its entry from `skipped.log`.
