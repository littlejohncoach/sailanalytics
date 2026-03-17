#!/usr/bin/env python3
# MakeMoveMarkz.py — User selects a marks CSV file from Downloads and copies it into data/marks/

import os
import shutil
import tkinter as tk
from tkinter import filedialog


def main():
    # Base project directory (folder where this script lives)
    base = os.path.dirname(os.path.abspath(__file__))

    # Destination folder: data/marks/
    dest_dir = os.path.join(base, "data", "marks")
    os.makedirs(dest_dir, exist_ok=True)

    # Default folder: user's Downloads
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")

    # Hidden Tk root for the file dialog
    root = tk.Tk()
    root.withdraw()

    # File picker: ONLY marks CSV files
    filepath = filedialog.askopenfilename(
        initialdir=downloads_dir,
        title="Select Marks CSV",
        filetypes=[
            ("Marks CSV", "marks_*.csv"),
            ("CSV Files", "*.csv")
        ]
    )

    # User cancelled
    if not filepath:
        print("No file selected.")
        return

    fname = os.path.basename(filepath)
    dest = os.path.join(dest_dir, fname)

    try:
        shutil.copy(filepath, dest)
        print(f"SUCCESS: {fname} copied to data/marks/")
    except Exception as e:
        print("ERROR copying file:", e)


if __name__ == "__main__":
    main()
