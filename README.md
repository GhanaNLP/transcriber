# Transcriber

A desktop app to help you transcribe Ghanaian audio files using Gemini.

## Setup — Linux

```bash
sudo apt install python3-tk xclip wl-clipboard
git clone https://github.com/GhanaNLP/transcriber.git
cd transcriber
python transcriber.py --code YOUR_CODE
```

## Setup — Windows

```bash
git clone https://github.com/GhanaNLP/transcriber.git
cd transcriber
python transcriber.py --code YOUR_CODE
```

No extra dependencies needed. Python on Windows includes everything out of the box.

Replace `YOUR_CODE` with the code you were sent. The app will automatically download your assigned audio files and open ready to transcribe.

## How it works

1. On first run, your assigned audio files are downloaded automatically
2. Click **"⎘ Copy audio file"** → paste the file into Gemini
3. Click **"✦ Gemini prompt 1"** (or 2) → paste the prompt into Gemini
4. Copy Gemini's response → paste into the textarea
5. The app validates and auto-saves:
   - Consecutive repeated sentences are removed automatically
   - Transcripts outside the 18,000–36,000 character range are blocked — re-paste a better version or click **"Skip ⇥"** to move on
   - Duplicate transcripts (identical to one already saved for another file) are blocked

## Skipping files

Click **"Skip ⇥"** if you can't get a valid transcript after several attempts. The filename is written to `skipped.log` in your transcripts folder so it won't appear again in future sessions. To un-skip a file, remove its entry from `skipped.log`.

## Submitting your results

When you are done (or want to submit progress):

1. Find your transcripts folder — it is at `transcripts/<language>/` inside the folder where you ran the app
2. Zip the entire `transcripts/<language>/` folder
3. Go to the GitHub repo → **Issues** → **New Issue** → select **"Submit Transcription Results"**
4. Fill in the form and attach your zip file
