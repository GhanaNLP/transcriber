# Transcriber

A desktop app for transcribing Ghanaian audio files using Gemini AI.

---

## Requirements

- Python 3.8 or newer
- Git (for automatic setup)
- An internet connection

**Linux — install these once:**
```bash
sudo apt install python3-tk xclip wl-clipboard git
```

**Windows / Mac** — Python and Git are all you need.

---

## Setup

### 1. Get the app
```bash
git clone https://github.com/GhanaNLP/transcriber.git
cd transcriber
```

### 2. Run it
```bash
python transcriber.py
```

On first launch the app automatically installs everything it needs (`huggingface_hub` and the language validator). This takes about 30 seconds and only happens once.

A setup screen will appear asking for three things:

- **Volunteer code** — paste the code you were sent
- **Audio folder** — browse to the folder where you extracted your zip
- **Output folder** — choose where your transcript files will be saved

Click **Start →**. Your code is remembered for future sessions — you won't need to paste it again.

---

## How to transcribe

1. The app shows one audio file at a time
2. Click **⎘ Copy audio file** → open [gemini.google.com](https://gemini.google.com) → start a new chat → upload the file
3. Click **✦ Prompt 1 (News)** or **✦ Prompt 2 (Conversational)** to copy the right prompt → paste it into Gemini and send
4. Copy Gemini's response → click back on the app → paste into the text box
5. The app checks and saves automatically:
   - Repeated sentences are removed
   - Transcripts that are too short or too long are flagged
   - **Transcripts that don't match your assigned language are flagged** — this helps catch paste errors
6. Every 10 transcriptions your work is uploaded automatically

> **Which prompt?**
> - **Prompt 1 (News)** — formal news broadcast audio
> - **Prompt 2 (Conversational)** — informal or mixed speech
>
> If one gives a short or poor result, try the other. Still poor → click **Skip ⇥**.

---

## Language checking

The app automatically checks that each transcript matches the language you were assigned. If it doesn't:

- **Yellow warning** — the match is low but could be fine (e.g. heavy English mixing). You can still save.
- **Red block** — the transcript looks completely wrong. Re-paste from Gemini or skip the file.

This catches accidental wrong pastes, not genuine mixed-language speech.

---

## Skipping files

Click **Skip ⇥** if you can't get a valid transcript after a few attempts. The file won't appear again. To undo a skip, remove its line from `skipped.log` in your transcripts folder.

---

## Submitting

Your results upload automatically every 10 transcriptions. To upload immediately, click **⬆ Push Now**. When you finish all your files the app pushes anything remaining automatically.

---

## Troubleshooting

**App won't open on Linux**
```bash
sudo apt install python3-tk
```

**"Assignment mismatch" on startup**
Make sure you selected the folder where you extracted *your* zip file, not a different one.

**Push failed**
The app retries automatically next time you save. You can also click **⬆ Push Now** once your connection is back.

**Lost your code**
Contact the project coordinator to get it resent. Once entered it will be saved for future sessions.
