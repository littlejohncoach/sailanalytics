#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SailAnalytics/Arun/RunFIT.py  (ONE-FILE MODE, AUTO-EXIT)

Use-case:
- You download ONE TrainingPeaks file to ~/Downloads
- Immediately run this script (Dock/command)
- It processes ONLY ONE file (the newest *.FIT.gz):
    - waits until download is stable
    - extracts .FIT
    - detects date from filename (YYYY-MM-DD -> DDMMYY) [locked]
    - dialog (radio buttons):
          sailor
          group (yellow/blue/green/red)
    - renames to: sailor_DDMMYY_group.FIT
    - moves to:   SailAnalytics/data/fit/
    - moves original .FIT.gz to Trash
- Then exits (no spinning wheel).
"""

from __future__ import annotations

import gzip
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Tuple, Optional


# --------------------------------------------------
# PATHS (LOCKED)
# --------------------------------------------------
ARUN_DIR = Path(__file__).resolve().parent              # .../SailAnalytics/Arun
SA_ROOT = ARUN_DIR.parent                               # .../SailAnalytics

DOWNLOADS_DIR = Path.home() / "Downloads"
FIT_DEST_DIR = SA_ROOT / "data" / "fit"
FIT_DEST_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# FIXED OPTIONS (Option A radios)
# --------------------------------------------------
SAILORS = ["berkay", "joao", "william", "lourenco", "edu", "yalcin"]
GROUPS = ["yellow", "blue", "green", "red"]


# --------------------------------------------------
# macOS Trash
# --------------------------------------------------
def move_to_trash(path: Path) -> None:
    """Move a file/folder to macOS Trash using Finder (osascript)."""
    if not path.exists():
        return
    cmd = ["osascript", "-e", f'tell application "Finder" to delete POSIX file "{str(path)}"']
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------------------------------------------
# Date parser from TP filename
# --------------------------------------------------
def extract_date_ddmmyy_from_tp_filename(name: str) -> str:
    """
    Example:
      tp-5422874.2026-02-26-15-00-31-591Z....FIT.gz
    Extract:
      2026-02-26 -> 260226 (DDMMYY)
    """
    m = re.search(r"\.(\d{4})-(\d{2})-(\d{2})-", name)
    if not m:
        raise RuntimeError(f"Cannot detect date from filename: {name}")
    yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
    return f"{dd}{mm}{yyyy[2:]}"


# --------------------------------------------------
# Wait until download finished (size stable)
# --------------------------------------------------
def wait_for_stable_file(path: Path, checks: int = 3, delay_s: float = 0.4) -> None:
    last_size = -1
    stable = 0
    while stable < checks:
        if not path.exists():
            stable = 0
            last_size = -1
            time.sleep(delay_s)
            continue

        size = path.stat().st_size
        if size == last_size and size > 0:
            stable += 1
        else:
            stable = 0
            last_size = size

        time.sleep(delay_s)


# --------------------------------------------------
# Find newest TP file (one-file mode)
# --------------------------------------------------
def newest_fit_gz(downloads_dir: Path) -> Optional[Path]:
    candidates = list(downloads_dir.glob("*.FIT.gz"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


# --------------------------------------------------
# Dialog (radio buttons)
# --------------------------------------------------
def choose_sailor_and_group(date_ddmmyy: str, filename: str) -> Tuple[str, str]:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()

    win = tk.Toplevel(root)
    win.title("RunFIT — Assign file")
    win.geometry("520x560")
    win.resizable(False, False)

    tk.Label(win, text="TrainingPeaks FIT detected", font=("Arial", 14, "bold")).pack(pady=(12, 4))
    tk.Label(win, text=f"File: {filename}", font=("Arial", 10)).pack(pady=(0, 8))
    tk.Label(win, text=f"Date detected (locked): {date_ddmmyy}", font=("Arial", 12)).pack(pady=(0, 10))

    sailor_var = tk.StringVar(value="")
    group_var = tk.StringVar(value="")

    frame_s = tk.LabelFrame(win, text="Select Sailor", padx=10, pady=8)
    frame_s.pack(fill="x", padx=12, pady=10)

    for s in SAILORS:
        tk.Radiobutton(frame_s, text=s, variable=sailor_var, value=s).pack(anchor="w")

    frame_g = tk.LabelFrame(win, text="Select Group", padx=10, pady=8)
    frame_g.pack(fill="x", padx=12, pady=10)

    for g in GROUPS:
        tk.Radiobutton(frame_g, text=g, variable=group_var, value=g).pack(anchor="w")

    result = {"sailor": None, "group": None, "skip": False}

    def on_ok():
        s = sailor_var.get().strip()
        g = group_var.get().strip()
        if not s or not g:
            messagebox.showwarning("Missing selection", "Select BOTH sailor and group.")
            return
        result["sailor"] = s
        result["group"] = g
        win.destroy()

    def on_cancel():
        result["skip"] = True
        win.destroy()

    btns = tk.Frame(win)
    btns.pack(pady=14)
    tk.Button(btns, text="OK", width=12, command=on_ok).pack(side="left", padx=10)
    tk.Button(btns, text="Cancel", width=12, command=on_cancel).pack(side="left", padx=10)

    win.grab_set()
    win.wait_window()

    # IMPORTANT: destroy root so macOS doesn't keep a “spinning app”
    try:
        root.destroy()
    except Exception:
        pass

    if result["skip"]:
        raise RuntimeError("User cancelled.")

    return str(result["sailor"]), str(result["group"])


# --------------------------------------------------
# Process one file
# --------------------------------------------------
def process_one(gz_path: Path) -> Path:
    wait_for_stable_file(gz_path, checks=3, delay_s=0.4)

    date_ddmmyy = extract_date_ddmmyy_from_tp_filename(gz_path.name)

    # Extract .FIT next to .gz (Downloads)
    fit_tmp = gz_path.with_suffix("")  # removes .gz -> .FIT
    if fit_tmp.exists():
        try:
            fit_tmp.unlink()
        except Exception:
            pass

    with gzip.open(gz_path, "rb") as f_in:
        with open(fit_tmp, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    sailor, group = choose_sailor_and_group(date_ddmmyy, gz_path.name)

    new_name = f"{sailor}_{date_ddmmyy}_{group}.FIT"
    dest = FIT_DEST_DIR / new_name

    # Avoid overwriting silently
    if dest.exists():
        base = dest.stem
        ext = dest.suffix
        k = 2
        while True:
            alt = FIT_DEST_DIR / f"{base}_{k}{ext}"
            if not alt.exists():
                dest = alt
                break
            k += 1

    shutil.move(str(fit_tmp), str(dest))
    move_to_trash(gz_path)

    return dest


# --------------------------------------------------
# MAIN (auto-exit)
# --------------------------------------------------
def main() -> None:
    gz = newest_fit_gz(DOWNLOADS_DIR)
    if not gz:
        print("No *.FIT.gz found in ~/Downloads.")
        return

    print(f"Processing newest download: {gz.name}")
    try:
        out = process_one(gz)
        print("Saved:", out)
        print("Done.")
    except Exception as e:
        print("ERROR:", e)
        # Cleanup extracted temp FIT if left behind
        tmp = gz.with_suffix("")
        if tmp.exists():
            try:
                move_to_trash(tmp)
            except Exception:
                pass
        return


if __name__ == "__main__":
    main()