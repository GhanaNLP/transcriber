#!/usr/bin/env python3
"""
Transcriber - tkinter GUI
Run: python transcriber.py
     python transcriber.py --code <volunteer_code>
     python transcriber.py --audio /path/to/audio --output /path/to/transcripts

Audio files are distributed manually (zip archives).
The volunteer code is used to:
  - Verify the volunteer is working with their assigned audio files
  - Authenticate pushes to the HuggingFace output repo
  - Identify the assigned language for transcript validation
"""

import os
import re
import sys
import glob
import platform
import subprocess
import argparse
import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path

# ── Cross-platform helpers ─────────────────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"
IS_MAC     = platform.system() == "Darwin"

# ── Average character threshold ───────────────────────────────────────────────
AVG_CHARS_THRESHOLD = 13500

# ── HF output repo (transcripts are pushed here) ─────────────────────────────
HF_OUTPUT_REPO = "ghananlpcommunity/ghana-asr-transcripts"

# Push a batch to HF every N saved transcriptions
PUSH_EVERY_N = 10

# ── Tiny Lang Detector repo ───────────────────────────────────────────────────
TINY_LANG_DETECTOR_REPO = "https://github.com/GhanaNLP/tiny-lang-detector.git"
TINY_LANG_DETECTOR_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "tiny-lang-detector")

# ── Language detection threshold ─────────────────────────────────────────────
# Warn the volunteer if fewer than this fraction of sentences match the language
LANG_DETECTION_WARN_THRESHOLD = 0.70   # below this → show a warning
LANG_DETECTION_BLOCK_THRESHOLD = 0.70  # below this → block saving

# ── Gemini Prompts ────────────────────────────────────────────────────────────
GEMINI_PROMPT_1 = (
    "give me a full accurate transcription of this ghanaian news media audio which is mainly in {lang} "
    "but also contains some english. plain text transcription with no headings and formatting just as i will "
    "get with a standard ASR like whisper. Write english as english text without trying to adapt them to {lang}."
)
GEMINI_PROMPT_2 = (
    "give me a full accurate transcription of this audio from {lang} speakers "
    "who mix english words when speaking {lang}. plain text transcription."
)


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Transcriber — batch audio transcription helper"
    )
    parser.add_argument("--audio",  "-a", default=None,
                        help="Path to folder containing audio files")
    parser.add_argument("--output", "-o", default=None,
                        help="Path to folder where transcript .txt files will be saved")
    parser.add_argument("--code",   "-c", default=None,
                        help="Volunteer code — used for verification and HF push auth")
    return parser.parse_args()


# ── Dependency bootstrap ──────────────────────────────────────────────────────

def _pip(*args):
    """Run pip as a subprocess, user-install to avoid permission issues."""
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "--user", "--quiet", *args])


def ensure_dependencies():
    """Install huggingface_hub and tiny-lang-detector if not already present."""

    # 1. huggingface_hub
    try:
        import huggingface_hub  # noqa
    except ImportError:
        print("Installing huggingface_hub…")
        _pip("huggingface_hub")

    # 2. tiny-lang-detector — clone repo if not present, then install
    _ensure_tiny_lang_detector()


def _ensure_tiny_lang_detector():
    """Clone and install tiny-lang-detector if not already available."""
    try:
        # Already importable — nothing to do
        import importlib.util
        if importlib.util.find_spec("src.detector") is not None:
            return
        # Try adding the cloned dir to path
        if os.path.isdir(TINY_LANG_DETECTOR_DIR):
            if TINY_LANG_DETECTOR_DIR not in sys.path:
                sys.path.insert(0, TINY_LANG_DETECTOR_DIR)
            import importlib.util
            if importlib.util.find_spec("src.detector") is not None:
                return
    except Exception:
        pass

    # Clone if the directory doesn't exist yet
    if not os.path.isdir(TINY_LANG_DETECTOR_DIR):
        print("Cloning tiny-lang-detector…")
        try:
            subprocess.check_call(
                ["git", "clone", "--depth", "1",
                 TINY_LANG_DETECTOR_REPO, TINY_LANG_DETECTOR_DIR]
            )
        except Exception as e:
            print(f"⚠️  Could not clone tiny-lang-detector: {e}")
            print("   Language detection will be disabled for this session.")
            return

    # Add to path
    if TINY_LANG_DETECTOR_DIR not in sys.path:
        sys.path.insert(0, TINY_LANG_DETECTOR_DIR)

    # Install via setup.py / pyproject to register the package properly
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install",
             "--user", "--quiet", TINY_LANG_DETECTOR_DIR]
        )
    except Exception as e:
        print(f"⚠️  Could not install tiny-lang-detector: {e}")


def get_language_detector(lang: str):
    """
    Return a callable  check(text) -> (match: bool, score: float)
    Uses tiny-lang-detector if available; returns a no-op otherwise.
    """
    try:
        if TINY_LANG_DETECTOR_DIR not in sys.path:
            sys.path.insert(0, TINY_LANG_DETECTOR_DIR)
        from src.detector import LanguageDetector  # noqa
        data_dir = os.path.join(TINY_LANG_DETECTOR_DIR, "data")
        if not os.path.isdir(data_dir):
            return None

        detector = LanguageDetector(data_dir=data_dir)
        lang_key = lang.lower().replace(" ", "_")

        # Find best matching key in loaded tables
        available = list(detector.tables.keys())
        matched_key = None
        for key in available:
            if key.lower() == lang_key or key.lower() == lang.lower():
                matched_key = key
                break
        # fuzzy: check if lang is a substring
        if matched_key is None:
            for key in available:
                if lang.lower() in key.lower() or key.lower() in lang.lower():
                    matched_key = key
                    break

        if matched_key is None:
            print(f"⚠️  Language '{lang}' not found in tiny-lang-detector "
                  f"(available: {available}). Language check disabled.")
            return None

        def check(text):
            result = detector.check_language(text, matched_key)
            return result["match"], result["score"]

        return check

    except Exception as e:
        print(f"⚠️  Language detector unavailable: {e}")
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_audio_files(audio_folder):
    files = []
    for pat in ["*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"]:
        files.extend(glob.glob(os.path.join(audio_folder, pat)))
    return sorted(set(files), key=lambda f: os.path.basename(f))

def transcript_path(audio_path, text_folder):
    return os.path.join(text_folder, Path(audio_path).stem + ".txt")

def get_pending(audio_folder, text_folder):
    return [f for f in get_audio_files(audio_folder)
            if not os.path.exists(transcript_path(f, text_folder))]

def get_done_count(audio_folder, text_folder):
    return len([f for f in get_audio_files(audio_folder)
                if os.path.exists(transcript_path(f, text_folder))])

def all_transcripts(audio_folder, text_folder):
    result = set()
    for f in get_audio_files(audio_folder):
        tp = transcript_path(f, text_folder)
        if os.path.exists(tp):
            result.add(open(tp, encoding="utf-8").read().strip())
    return result

SKIP_LOG = "skipped.log"

def skip_log_path(text_folder):
    return os.path.join(text_folder, SKIP_LOG)

def load_skipped(text_folder):
    path = skip_log_path(text_folder)
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_skipped(text_folder, basename):
    with open(skip_log_path(text_folder), "a", encoding="utf-8") as f:
        f.write(basename + "\n")


def remove_consecutive_repetitions(text):
    parts = re.split(r'(\s*[.!?\n]+\s*)', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i].strip()
        delim = parts[i+1] if i+1 < len(parts) else " "
        if s:
            sentences.append((s, delim))
    if parts and parts[-1].strip():
        sentences.append((parts[-1].strip(), ""))

    if not sentences:
        return text, 0

    cleaned = [sentences[0]]
    removed = 0

    i = 1
    while i < len(sentences):
        matched = False
        max_block = (len(sentences) - i) // 2
        for k in range(min(max_block, 10), 0, -1):
            block      = [s for s, _ in sentences[i:i+k]]
            prev_block = [s for s, _ in cleaned[-k:]] if len(cleaned) >= k else None
            if prev_block and [s.lower() for s in block] == [s.lower() for s in prev_block]:
                removed += k
                i += k
                matched = True
                break
        if not matched:
            cleaned.append(sentences[i])
            i += 1

    result = " ".join(s + d for s, d in cleaned).strip()
    return result, removed

def validate_transcript(text):
    cleaned, n_removed = remove_consecutive_repetitions(text)
    warnings = []
    avg   = AVG_CHARS_THRESHOLD
    lower = avg * (2 / 3)
    upper = avg * (4 / 3)
    if len(cleaned) < lower:
        warnings.append(
            f"Transcript too short: {len(cleaned):,} chars "
            f"(expected ≥ {int(lower):,}, target is {avg:,}).\n"
            f"   → Try switching Gemini to Thinking Mode for a more complete transcription."
        )
    elif len(cleaned) > upper:
        warnings.append(
            f"Transcript too long: {len(cleaned):,} chars "
            f"(expected ≤ {int(upper):,}, target is {avg:,}).\n"
            f"   → Try switching Gemini to Thinking Mode for a more focused output."
        )
    return cleaned, warnings


# ── Volunteer code helpers ────────────────────────────────────────────────────

def decode_code(code):
    import json, base64
    padding = 4 - len(code) % 4
    if padding != 4:
        code += "=" * padding
    try:
        payload = base64.urlsafe_b64decode(code.encode()).decode()
        data    = json.loads(payload)
        assert "lang" in data and "ids" in data and "tok" in data
        return data
    except Exception:
        return None

def token_from_code(code):
    data = decode_code(code)
    if data is None:
        raise ValueError("Invalid volunteer code — cannot extract token.")
    return data["tok"]

def lang_from_code(code):
    data = decode_code(code)
    return data["lang"] if data else None

def verify_audio_against_code(audio_folder, code):
    data = decode_code(code)
    if data is None:
        return False, set(), set(), [], []
    assigned_ids = set(data["ids"])
    present_ids  = {Path(f).stem for f in get_audio_files(audio_folder)}
    missing      = sorted(assigned_ids - present_ids)
    extra        = sorted(present_ids  - assigned_ids)
    ok           = len(missing) == 0 and len(extra) == 0
    return ok, assigned_ids, present_ids, missing, extra


# ── HF push logic ─────────────────────────────────────────────────────────────

PUSH_OK      =  1
PUSH_FAILED  = -1
PUSH_NOTHING =  0

def push_transcripts_to_hf(audio_folder, text_folder, lang, volunteer_code,
                            status_callback=None):
    ensure_dependencies()
    from huggingface_hub import HfApi, CommitOperationAdd
    import hashlib

    hf_token = token_from_code(volunteer_code)
    vol_hash = hashlib.sha256(volunteer_code.encode()).hexdigest()[:8]
    api      = HfApi(token=hf_token)

    try:
        api.create_repo(
            repo_id   = HF_OUTPUT_REPO,
            repo_type = "dataset",
            exist_ok  = True,
            private   = False,
        )
    except Exception as e:
        print(f"⚠️  Could not verify output repo: {e}")

    operations   = []
    pushed_files = []

    for audio_path in get_audio_files(audio_folder):
        tp = transcript_path(audio_path, text_folder)
        if not os.path.exists(tp):
            continue
        audio_basename = os.path.basename(audio_path)
        repo_name      = f"{audio_basename}__{vol_hash}.txt"
        operations.append(CommitOperationAdd(
            path_in_repo    = f"transcripts/{lang}/{repo_name}",
            path_or_fileobj = tp,
        ))
        pushed_files.append(audio_basename)

    if not operations:
        if status_callback:
            status_callback("Nothing to push yet.")
        return PUSH_NOTHING, 0

    if status_callback:
        status_callback(f"Pushing {len(pushed_files)} transcript(s) to HuggingFace…")

    try:
        api.create_commit(
            repo_id        = HF_OUTPUT_REPO,
            repo_type      = "dataset",
            operations     = operations,
            commit_message = (
                f"Volunteer {vol_hash}: {len(pushed_files)} transcript(s) [lang={lang}]"
            ),
        )
        msg = f"✓ Pushed {len(pushed_files)} transcript(s) to HF"
        print(f"✅  {msg}")
        if status_callback:
            status_callback(msg)
        return PUSH_OK, len(pushed_files)

    except Exception as e:
        err = f"Push failed — will retry later: {e}"
        print(f"❌  {err}")
        if status_callback:
            status_callback(err, error=True)
        return PUSH_FAILED, 0


# ── Clipboard / audio helpers ─────────────────────────────────────────────────

def copy_to_clipboard(root, text=None, filepath=None):
    if text is not None:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        return True, "text"

    if filepath is not None:
        full_path = os.path.abspath(filepath)
        if IS_LINUX:
            uri    = f"file://{full_path}\r\n"
            wayland = os.environ.get("WAYLAND_DISPLAY")
            try:
                if wayland:
                    subprocess.run(["wl-copy", "-t", "text/uri-list"],
                                   input=uri.encode(), check=True)
                else:
                    subprocess.run(["xclip", "-selection", "clipboard",
                                    "-t", "text/uri-list"],
                                   input=uri.encode(), check=True)
                return True, "file"
            except Exception:
                pass
        elif IS_WINDOWS:
            try:
                ps_cmd = (
                    f"$files = New-Object System.Collections.Specialized.StringCollection; "
                    f"$files.Add('{full_path}'); "
                    f"[System.Windows.Forms.Clipboard]::SetFileDropList($files)"
                )
                subprocess.run(
                    ["powershell", "-Command",
                     f"Add-Type -AssemblyName System.Windows.Forms; {ps_cmd}"],
                    check=True, capture_output=True
                )
                return True, "file"
            except Exception:
                pass
        elif IS_MAC:
            try:
                subprocess.run(
                    ["osascript", "-e",
                     f'set the clipboard to (POSIX file "{full_path}")'],
                    check=True
                )
                return True, "file"
            except Exception:
                pass

        root.clipboard_clear()
        root.clipboard_append(full_path)
        root.update()
        return True, "path"

    return False, "none"

def open_audio(filepath):
    full_path = os.path.abspath(filepath)
    if IS_WINDOWS:
        os.startfile(full_path)
    elif IS_MAC:
        subprocess.Popen(["open", full_path])
    else:
        subprocess.Popen(["xdg-open", full_path])


# ── Session config (code + folder paths persisted across launches) ────────────

import json as _json

CONFIG_FILE = ".transcriber_config"

def load_session(base_dir):
    """Return saved (code, audio_folder, text_folder) or (None, None, None)."""
    path = os.path.join(base_dir, CONFIG_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return (
            data.get("code")         or None,
            data.get("audio_folder") or None,
            data.get("text_folder")  or None,
        )
    except Exception:
        return None, None, None

def save_session(base_dir, code=None, audio_folder=None, text_folder=None):
    path = os.path.join(base_dir, CONFIG_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception:
        data = {}
    if code         is not None: data["code"]         = code.strip()
    if audio_folder is not None: data["audio_folder"] = audio_folder
    if text_folder  is not None: data["text_folder"]  = text_folder
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(data, f)

def clear_session(base_dir):
    path = os.path.join(base_dir, CONFIG_FILE)
    if os.path.exists(path):
        os.remove(path)
    # Also remove old single-value code file if present
    old = os.path.join(base_dir, ".volunteer_code")
    if os.path.exists(old):
        os.remove(old)


# ── Startup Dialog ────────────────────────────────────────────────────────────

class StartupDialog:
    def __init__(self, root, prefill_code=None, prefill_audio=None, prefill_output=None):
        BG     = "#f5f6fa"
        FG     = "#2c3e50"
        MUTED  = "#7f8c8d"
        ACCENT = "#3498db"

        self.root = root
        self.result_code         = None
        self.result_audio_folder = None
        self.result_text_folder  = None

        self.win = tk.Toplevel(root)
        self.win.title("Transcriber — Setup")
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self._cancel)

        frame = tk.Frame(self.win, bg=BG, padx=40, pady=28)
        frame.pack(expand=True, fill="both")

        tk.Label(frame, text="Transcriber Setup", bg=BG, fg=FG,
                 font=("Arial", 18, "bold")).pack(pady=(0, 22))

        tk.Label(frame, text="Volunteer code  (paste yours below):",
                 bg=BG, fg=FG, font=("Arial", 11)).pack(anchor="w")

        self.code_entry = tk.Entry(frame, font=("Arial", 11), width=56,
                                   relief="solid", bd=1)
        self.code_entry.pack(ipady=6, pady=(4, 2), fill="x")
        if prefill_code:
            self.code_entry.insert(0, prefill_code)

        # If we have a saved code, show a small note so the volunteer knows
        if prefill_code:
            tk.Label(frame, text="✓ Code loaded from last session",
                     bg=BG, fg="#27ae60", font=("Arial", 8)).pack(anchor="w", pady=(0, 2))

        self.code_hint = tk.Label(
            frame,
            text="ℹ  Your code verifies your assigned files and lets you push to HuggingFace.",
            bg=BG, fg=MUTED, font=("Arial", 8), wraplength=420, justify="left"
        )
        self.code_hint.pack(anchor="w", pady=(0, 14))

        tk.Label(frame, text="Audio folder  (where you extracted your zip):",
                 bg=BG, fg=FG, font=("Arial", 11)).pack(anchor="w")

        audio_row = tk.Frame(frame, bg=BG)
        audio_row.pack(fill="x", pady=(4, 12))

        self.audio_var = tk.StringVar(value=prefill_audio or "")
        tk.Entry(audio_row, textvariable=self.audio_var, font=("Arial", 10),
                 relief="solid", bd=1, state="readonly").pack(
                     side="left", fill="x", expand=True, ipady=5)
        tk.Button(audio_row, text="Browse…", font=("Arial", 10),
                  bg=ACCENT, fg="white", activebackground="#2980b9",
                  activeforeground="white", relief="flat", padx=10, pady=5,
                  cursor="hand2",
                  command=self._browse_audio).pack(side="left", padx=(8, 0))

        tk.Label(frame, text="Output folder  (where transcripts will be saved):",
                 bg=BG, fg=FG, font=("Arial", 11)).pack(anchor="w")

        output_row = tk.Frame(frame, bg=BG)
        output_row.pack(fill="x", pady=(4, 16))

        self.output_var = tk.StringVar(value=prefill_output or "")
        tk.Entry(output_row, textvariable=self.output_var, font=("Arial", 10),
                 relief="solid", bd=1, state="readonly").pack(
                     side="left", fill="x", expand=True, ipady=5)
        tk.Button(output_row, text="Browse…", font=("Arial", 10),
                  bg=ACCENT, fg="white", activebackground="#2980b9",
                  activeforeground="white", relief="flat", padx=10, pady=5,
                  cursor="hand2",
                  command=self._browse_output).pack(side="left", padx=(8, 0))

        self.error_var = tk.StringVar(value="")
        tk.Label(frame, textvariable=self.error_var, bg=BG,
                 fg="#e74c3c", font=("Arial", 9),
                 wraplength=440, justify="left").pack(anchor="w")

        tk.Button(frame, text="Start →", font=("Arial", 12, "bold"),
                  bg="#27ae60", fg="white", activebackground="#219a52",
                  activeforeground="white", relief="flat", padx=20, pady=10,
                  cursor="hand2", command=self._confirm).pack(pady=(12, 0))

        self.win.geometry("540x460")

    def _browse_audio(self):
        d = filedialog.askdirectory(title="Select audio folder")
        if d:
            self.audio_var.set(d)

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select output / transcripts folder")
        if d:
            self.output_var.set(d)

    def _confirm(self):
        code          = self.code_entry.get().strip()
        audio_folder  = self.audio_var.get().strip()
        output_folder = self.output_var.get().strip()

        if not audio_folder:
            self.error_var.set("Please select your audio folder.")
            return
        if not os.path.isdir(audio_folder):
            self.error_var.set("Audio folder not found — please browse again.")
            return
        if not output_folder:
            self.error_var.set("Please select an output folder for your transcripts.")
            return

        if code:
            data = decode_code(code)
            if data is None:
                self.error_var.set("Invalid volunteer code — please check and try again.")
                return

            ok, assigned, found, missing, extra = verify_audio_against_code(
                audio_folder, code
            )
            if not ok:
                lines = []
                if missing:
                    lines.append(
                        f"Missing {len(missing)} assigned file(s) in your audio folder:\n"
                        + ", ".join(missing[:8])
                        + (" …" if len(missing) > 8 else "")
                    )
                if extra:
                    lines.append(
                        f"{len(extra)} file(s) in the folder are NOT in your assignment "
                        f"(they will be ignored):\n"
                        + ", ".join(extra[:8])
                        + (" …" if len(extra) > 8 else "")
                    )
                self.error_var.set(
                    "⚠  Assignment mismatch:\n" + "\n".join(lines) +
                    "\n\nMake sure you extracted the correct zip file."
                )
                return

        self.result_code         = code if code else None
        self.result_audio_folder = audio_folder
        self.result_text_folder  = output_folder
        self.win.destroy()

    def _cancel(self):
        self.root.destroy()
        sys.exit(0)


# ── Main Transcriber App ──────────────────────────────────────────────────────

class TranscriberApp:
    def __init__(self, root, audio_folder, text_folder, volunteer_code=None):
        self.root           = root
        self.audio_folder   = audio_folder
        self.text_folder    = text_folder
        self.volunteer_code = volunteer_code

        self._last_push_count = self._load_last_push_count()

        # ── Language detection setup ──────────────────────────────────────────
        self._lang           = lang_from_code(volunteer_code) if volunteer_code else None
        self._lang_checker   = None
        self._lang_check_enabled = False
        if self._lang:
            self._lang_checker = get_language_detector(self._lang)
            self._lang_check_enabled = self._lang_checker is not None

        # ── Prompts personalised to the assigned language ─────────────────────
        lang_display = self._lang.capitalize() if self._lang else "the target language"
        self._prompt1 = GEMINI_PROMPT_1.replace("{lang}", lang_display)
        self._prompt2 = GEMINI_PROMPT_2.replace("{lang}", lang_display)

        self.root.title("Transcriber")
        self.root.resizable(True, True)

        self.current_file          = None
        self._has_pending_warnings = False
        self._bad_transcript       = ""
        self._skipped              = load_skipped(text_folder)

        self._build_ui()
        self._load_next()

    def _build_ui(self):
        BG      = "#f5f6fa"
        SURFACE = "#ffffff"
        FG      = "#2c3e50"
        MUTED   = "#7f8c8d"
        TOOLBAR = "#2c3e50"

        self.root.configure(bg=BG)

        # TOP BAR
        top = tk.Frame(self.root, bg=TOOLBAR, height=50)
        top.pack(fill="x")

        # Language badge in toolbar
        lang_label = f"▶ TRANSCRIBER"
        if self._lang:
            lang_label += f"  ·  {self._lang.upper()}"
        tk.Label(top, text=lang_label, bg=TOOLBAR, fg="white",
                 font=("Arial", 12, "bold")).pack(side="left", padx=16, pady=12)

        if self.volunteer_code:
            self.logout_btn = tk.Button(
                top, text="Logout", bg=TOOLBAR, fg="#e74c3c",
                activebackground=TOOLBAR, activeforeground="#ff7979",
                relief="flat", bd=0, cursor="hand2",
                font=("Arial", 10, "bold"), command=self._logout
            )
            self.logout_btn.pack(side="right", padx=(12, 16), pady=12)

        self.progress_var = tk.StringVar(value="...")
        tk.Label(top, textvariable=self.progress_var, bg=TOOLBAR, fg="white",
                 font=("Arial", 10)).pack(side="right", pady=12)

        # FILE INFO & ACTIONS
        info = tk.Frame(self.root, bg=SURFACE, padx=20, pady=20,
                        relief="solid", bd=1)
        info.pack(fill="x", padx=20, pady=20)

        tk.Label(info, text="NOW TRANSCRIBING", bg=SURFACE, fg=MUTED,
                 font=("Arial", 9, "bold")).pack(anchor="w")

        self.filename_var = tk.StringVar(value="loading…")
        tk.Label(info, textvariable=self.filename_var, bg=SURFACE, fg=FG,
                 font=("Arial", 16, "bold"), wraplength=600,
                 justify="left").pack(anchor="w", pady=(5, 15))

        btn_row = tk.Frame(info, bg=SURFACE)
        btn_row.pack(anchor="w")

        btn_style = dict(font=("Arial", 10, "bold"), relief="flat", bd=0,
                         padx=15, pady=8, cursor="hand2")

        self.copy_audio_btn = tk.Button(
            btn_row, text="⎘ Copy audio file",
            bg="#34495e", fg="white",
            activebackground="#2c3e50", activeforeground="white",
            command=self._copy_audio, **btn_style
        )
        self.copy_audio_btn.pack(side="left", padx=(0, 10))

        self.prompt1_btn = tk.Button(
            btn_row, text="✦ Prompt 1 (News)",
            bg="#9b59b6", fg="white",
            activebackground="#8e44ad", activeforeground="white",
            command=self._copy_prompt1, **btn_style
        )
        self.prompt1_btn.pack(side="left", padx=(0, 10))

        self.prompt2_btn = tk.Button(
            btn_row, text="✦ Prompt 2 (Conversational)",
            bg="#8e44ad", fg="white",
            activebackground="#7d3c98", activeforeground="white",
            command=self._copy_prompt2, **btn_style
        )
        self.prompt2_btn.pack(side="left", padx=(0, 10))

        self.play_btn = tk.Button(
            btn_row, text="▶ Play audio",
            bg="#2980b9", fg="white",
            activebackground="#2471a3", activeforeground="white",
            command=self._play_audio, **btn_style
        )
        self.play_btn.pack(side="left", padx=(0, 10))

        if self.volunteer_code:
            self.push_btn = tk.Button(
                btn_row, text="⬆ Push Now",
                bg="#3498db", fg="white",
                activebackground="#2980b9", activeforeground="white",
                command=self._manual_push, **btn_style
            )
            self.push_btn.pack(side="left")

        # WARNING & TEXT AREA
        self.warn_frame = tk.Frame(self.root, bg="#fdf0ed", padx=14, pady=10,
                                   relief="solid", bd=1)
        self.warn_var = tk.StringVar(value="")
        tk.Label(self.warn_frame, textvariable=self.warn_var,
                 bg="#fdf0ed", fg="#e74c3c", font=("Arial", 10),
                 wraplength=660, justify="left").pack(anchor="w")

        self.textarea_frame = tk.Frame(self.root, bg=BG, padx=20)
        self.textarea_frame.pack(fill="both", expand=True)

        tk.Label(self.textarea_frame,
                 text="Paste transcript below (auto-saves on paste):",
                 bg=BG, fg=FG, font=("Arial", 10, "bold")).pack(
                     anchor="w", pady=(0, 5))

        self.text = tk.Text(
            self.textarea_frame, font=("Arial", 11),
            bg=SURFACE, fg=FG, insertbackground=FG,
            relief="solid", bd=1, padx=12, pady=12,
            wrap="word", height=14, undo=True
        )
        self.text.pack(fill="both", expand=True)
        self.text.bind("<KeyRelease>", self._on_paste)
        self.text.bind("<<Paste>>",    self._on_paste)

        # BOTTOM BAR
        bottom = tk.Frame(self.root, bg=BG, padx=20, pady=15)
        bottom.pack(fill="x")

        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(
            bottom, textvariable=self.status_var,
            bg=BG, fg="#27ae60", font=("Arial", 10)
        )
        self.status_label.pack(side="left")

        self.skip_btn = tk.Button(
            bottom, text="Skip ⇥", font=("Arial", 10),
            bg="#95a5a6", fg="white",
            activebackground="#7f8c8d", activeforeground="white",
            relief="flat", bd=0, padx=15, pady=8, cursor="hand2",
            command=self._skip
        )
        self.skip_btn.pack(side="right", padx=(10, 0))

        self.save_btn = tk.Button(
            bottom, text="Save & Next →", font=("Arial", 10, "bold"),
            bg="#27ae60", fg="white",
            activebackground="#219a52", activeforeground="white",
            relief="flat", bd=0, padx=20, pady=8, cursor="hand2",
            command=self._save
        )
        self.save_btn.pack(side="right")

        queue_frame = tk.Frame(self.root, bg=BG, padx=20)
        queue_frame.pack(fill="x", pady=(0, 15))

        tk.Label(queue_frame, text="UP NEXT:", bg=BG, fg=MUTED,
                 font=("Arial", 9, "bold")).pack(side="left", padx=(0, 8))
        self.queue_var = tk.StringVar(value="")
        tk.Label(queue_frame, textvariable=self.queue_var, bg=BG, fg=MUTED,
                 font=("Arial", 9)).pack(side="left")

        self.root.geometry("800x650")

    def _logout(self):
        if messagebox.askyesno(
            "Logout",
            "Are you sure you want to log out?\n\n"
            "This will clear your saved settings and close the app.",
            parent=self.root
        ):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            clear_session(base_dir)
            self.root.destroy()
            sys.exit(0)

    # ── Warning banner ──

    def _show_warning_banner(self, warnings, bad_transcript):
        lines = "\n".join(f"⚠ {w}" for w in warnings)
        self.warn_var.set(
            lines +
            "\n\nRe-paste a corrected version to try again, "
            "or click 'Skip ⇥' to move to the next file."
        )
        self.warn_frame.pack(fill="x", padx=20, pady=(0, 10),
                             before=self.textarea_frame)
        self._has_pending_warnings = True
        self._bad_transcript       = bad_transcript
        self.text.delete("1.0", "end")
        self.save_btn.config(state="disabled", bg="#bdc3c7")

    def _hide_warning_banner(self):
        self.warn_frame.pack_forget()
        self._has_pending_warnings = False
        self.save_btn.config(state="normal", bg="#27ae60")

    # ── Load ──

    def _load_next(self):
        all_pending = get_pending(self.audio_folder, self.text_folder)
        pending     = [f for f in all_pending
                       if os.path.basename(f) not in self._skipped]

        total         = len(get_audio_files(self.audio_folder))
        done          = get_done_count(self.audio_folder, self.text_folder)
        skipped_count = len(self._skipped)

        progress = f"{done} / {total} done"
        if skipped_count:
            progress += f" ({skipped_count} skipped)"
        self.progress_var.set(progress)
        self._hide_warning_banner()

        if not pending:
            label = "🎉 All done!"
            if self._skipped:
                label = f"🎉 Done! ({skipped_count} file(s) skipped)"
            self.filename_var.set(label)
            self.text.config(state="disabled")
            self.save_btn.config(state="disabled", bg="#bdc3c7")
            self.skip_btn.config(state="disabled", bg="#bdc3c7")
            self.queue_var.set("")
            self.current_file = None

            if self.volunteer_code:
                self._do_push()
            return

        self.current_file = pending[0]
        self.filename_var.set(os.path.basename(self.current_file))
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.status_var.set("")
        self.save_btn.config(state="normal", bg="#27ae60")
        self.skip_btn.config(state="normal", bg="#95a5a6")

        upcoming = [os.path.basename(f) for f in pending[1:5]]
        self.queue_var.set(" → ".join(upcoming) if upcoming else "—")

    # ── Language check ──

    def _check_language(self, text):
        """
        Run language detection on the transcript.
        Returns (ok: bool, warning_msg: str | None, block: bool)
          ok=True   → language matches, proceed
          ok=False  → mismatch; warning_msg explains; block=True means refuse to save
        """
        if not self._lang_check_enabled or self._lang_checker is None:
            return True, None, False

        try:
            match, score = self._lang_checker(text)
        except Exception:
            return True, None, False   # detector error → don't penalise volunteer

        if score >= LANG_DETECTION_WARN_THRESHOLD:
            return True, None, False

        lang_name = self._lang.capitalize()

        if score < LANG_DETECTION_BLOCK_THRESHOLD:
            msg = (
                f"⛔  This transcript doesn't look like {lang_name} "
                f"(language match: {score:.0%}).\n\n"
                f"Please make sure you pasted the correct Gemini response "
                f"for a {lang_name} audio file. If the audio really is in another "
                f"language, click Skip ⇥."
            )
            return False, msg, True   # block save

        msg = (
            f"⚠  Low {lang_name} language match: {score:.0%}.\n\n"
            f"This may be fine if the audio contains a lot of English mixing. "
            f"If you're sure it's correct, use Save & Next → to proceed. "
            f"Otherwise re-paste from Gemini."
        )
        return False, msg, False   # warn but allow save

    # ── Paste / Save ──

    def _on_paste(self, event=None):
        self.root.after(80, self._auto_save)

    def _auto_save(self):
        if not self.current_file:
            return
        raw = self.text.get("1.0", "end").strip()
        if not raw:
            return
        cleaned, warnings = validate_transcript(raw)
        if cleaned != raw:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", cleaned)
        if self._check_duplicate(cleaned):
            return
        if warnings:
            self._show_warning_banner(warnings, cleaned)
            note = "Repetitions removed. " if cleaned != raw else ""
            self._flash_status(
                f"{note}Length issue — check warning banner above.", error=True
            )
            return

        # ── Language check ────────────────────────────────────────────────────
        lang_ok, lang_msg, lang_block = self._check_language(cleaned)
        if not lang_ok:
            if lang_block:
                self._show_warning_banner([lang_msg], cleaned)
                self._flash_status("Language mismatch — see warning above.", error=True)
                return
            else:
                # Warn but don't block — volunteer can still paste again or save manually
                self._show_warning_banner([lang_msg], cleaned)
                self._flash_status("Language warning — check above, or Save & Next to proceed.", error=True)
                # Re-enable save so they can override
                self.save_btn.config(state="normal", bg="#e67e22")
                return

        if cleaned != raw:
            self._flash_status("Repetitions auto-removed ✓")
        self._do_save(cleaned)

    def _save(self):
        if not self.current_file:
            return
        transcript = self.text.get("1.0", "end").strip()
        if not transcript:
            self._flash_status("Nothing to save.", error=True)
            return
        if self._check_duplicate(transcript):
            return
        self._do_save(transcript)

    def _skip(self):
        if not self.current_file:
            return
        basename = os.path.basename(self.current_file)
        self._skipped.add(basename)
        save_skipped(self.text_folder, basename)
        self._flash_status(f"Skipped ⇥ {basename}", error=True)
        self._load_next()

    def _check_duplicate(self, transcript):
        if transcript in all_transcripts(self.audio_folder, self.text_folder):
            messagebox.showwarning(
                "Duplicate",
                "This transcript already exists for another file.\nNot saved."
            )
            return True
        return False

    def _load_last_push_count(self):
        p = os.path.join(self.text_folder, ".last_push_count")
        try:
            with open(p, "r") as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def _save_last_push_count(self, count):
        os.makedirs(self.text_folder, exist_ok=True)
        p = os.path.join(self.text_folder, ".last_push_count")
        with open(p, "w") as f:
            f.write(str(count))

    def _do_save(self, transcript):
        os.makedirs(self.text_folder, exist_ok=True)
        tp = transcript_path(self.current_file, self.text_folder)
        with open(tp, "w", encoding="utf-8") as f:
            f.write(transcript)
        self._flash_status(f"✓ Saved {os.path.basename(tp)}")

        if self.volunteer_code:
            current_count = get_done_count(self.audio_folder, self.text_folder)
            if current_count - self._last_push_count >= PUSH_EVERY_N:
                self._do_push()

        self._load_next()

    # ── HF push helpers ──

    def _do_push(self):
        if not self.volunteer_code:
            return
        lang = decode_code(self.volunteer_code)["lang"]

        def status_cb(msg, error=False):
            self._flash_status(msg, error=error)

        result, n = push_transcripts_to_hf(
            audio_folder    = self.audio_folder,
            text_folder     = self.text_folder,
            lang            = lang,
            volunteer_code  = self.volunteer_code,
            status_callback = status_cb,
        )
        if result == PUSH_OK:
            new_count = get_done_count(self.audio_folder, self.text_folder)
            self._last_push_count = new_count
            self._save_last_push_count(new_count)

    def _manual_push(self):
        self._flash_status("Pushing to HuggingFace…")
        self.root.update()
        self._do_push()

    # ── Button actions ──

    def _copy_audio(self):
        if not self.current_file:
            return
        ok, mode = copy_to_clipboard(self.root, filepath=self.current_file)
        if ok:
            label    = "✓ Audio file copied" if mode == "file" else "✓ Path copied"
            self._flash_status(label)
            self.copy_audio_btn.config(text="✓ Copied!")
        else:
            self._flash_status("Could not copy to clipboard.", error=True)
        self.root.after(2000,
                        lambda: self.copy_audio_btn.config(text="⎘ Copy audio file"))

    def _copy_prompt1(self):
        copy_to_clipboard(self.root, text=self._prompt1)
        self._flash_status("✓ Prompt 1 (News) copied")
        self.prompt1_btn.config(text="✓ Copied!")
        self.root.after(2000,
                        lambda: self.prompt1_btn.config(text="✦ Prompt 1 (News)"))

    def _copy_prompt2(self):
        copy_to_clipboard(self.root, text=self._prompt2)
        self._flash_status("✓ Prompt 2 (Conversational) copied")
        self.prompt2_btn.config(text="✓ Copied!")
        self.root.after(2000,
                        lambda: self.prompt2_btn.config(text="✦ Prompt 2 (Conversational)"))

    def _play_audio(self):
        if not self.current_file:
            return
        try:
            open_audio(self.current_file)
            self._flash_status("▶ Playing audio…")
            self.play_btn.config(text="▶ Playing…")
            self.root.after(2000, lambda: self.play_btn.config(text="▶ Play audio"))
        except Exception as e:
            self._flash_status(f"Could not play: {e}", error=True)

    def _flash_status(self, msg, error=False):
        self.status_var.set(msg)
        self.status_label.config(fg="#e74c3c" if error else "#27ae60")
        self.root.after(4000, lambda: self.status_var.set(""))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Install dependencies before the GUI starts
    ensure_dependencies()

    args     = parse_args()
    base_dir = os.path.dirname(os.path.abspath(__file__))

    root = tk.Tk()
    root.withdraw()

    audio_folder   = args.audio
    text_folder    = args.output
    volunteer_code = args.code

    # Load saved session (code + both folder paths)
    saved_code, saved_audio, saved_output = load_session(base_dir)

    if not volunteer_code and saved_code and decode_code(saved_code) is not None:
        volunteer_code = saved_code
    if not audio_folder  and saved_audio and os.path.isdir(saved_audio):
        audio_folder = saved_audio
    if not text_folder   and saved_output:
        text_folder = saved_output

    # If all three are known and audio folder still exists, skip the setup dialog
    all_provided = (audio_folder and os.path.isdir(audio_folder) and text_folder and volunteer_code)

    if all_provided:
        ok, _, _, missing, extra = verify_audio_against_code(audio_folder, volunteer_code)
        if not ok and missing:
            # Saved audio path may have moved — fall through to dialog
            all_provided = False

    if all_provided:
        pass  # go straight to the app
    else:
        dialog = StartupDialog(
            root,
            prefill_code   = volunteer_code,
            prefill_audio  = audio_folder,
            prefill_output = text_folder,
        )
        root.wait_window(dialog.win)

        if dialog.result_audio_folder and dialog.result_text_folder:
            audio_folder   = dialog.result_audio_folder
            text_folder    = dialog.result_text_folder
            volunteer_code = dialog.result_code
        else:
            sys.exit(0)

    if not audio_folder or not text_folder:
        sys.exit(0)

    # Persist everything for next launch
    save_session(base_dir,
                 code=volunteer_code,
                 audio_folder=audio_folder,
                 text_folder=text_folder)

    os.makedirs(text_folder, exist_ok=True)

    root.deiconify()
    app = TranscriberApp(root, audio_folder, text_folder,
                         volunteer_code=volunteer_code)
    root.mainloop()
