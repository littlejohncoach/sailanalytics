#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RunDay_StartTimesAndTapes.py
----------------------------------------------------------
One-button "day runner" for Stage-2 pipeline:
- For a given date + group:
    runs StartTimeVerifier.py for every race found in RaceTimes.csv

This produces:
- verified_start_utc written into RaceTimes.csv (per race)
- truth tapes written into data/tapes/ (per race)
- finish detection appended (via TapeFinishFinder called by TapeBuilder)

Usage (editor Run or terminal):
  python3 RunDay_StartTimesAndTapes.py --date 300126 --group yellow
Optional:
  --race 2           # run only one race
  --from_race 3      # run R3..end
  --to_race 5        # run up to R5
----------------------------------------------------------
"""

import argparse
import csv
import sys
import subprocess
from pathlib import Path


# ---------------------------------------------------------
# Finder "Open With Terminal" support:
# - If script is launched with NO CLI args, prompt via dialogs
# - Injects --date / --group and optional --race or --from_race/--to_race
# ---------------------------------------------------------
def _prompt_args_if_missing():
    # If any args were provided, do nothing (normal CLI/editor run).
    if len(sys.argv) > 1:
        return

    import tkinter as tk
    from tkinter import simpledialog, messagebox

    root = tk.Tk()
    root.withdraw()

    date = simpledialog.askstring("Run Day", "Date (DDMMYY):", parent=root)
    if not date:
        messagebox.showinfo("Cancelled", "No date entered. Exiting.")
        raise SystemExit(0)
    date = date.strip()

    group = simpledialog.askstring("Run Day", "Group / Fleet (e.g. yellow):", parent=root)
    if not group:
        messagebox.showinfo("Cancelled", "No group entered. Exiting.")
        raise SystemExit(0)
    group = group.strip().lower()

    # Optional: single race or range
    mode = simpledialog.askstring(
        "Run Day (optional)",
        "Optional:\n"
        "- Enter SINGLE race number (e.g. 2)\n"
        "- OR range like 1-6\n"
        "- OR leave blank = all races for day",
        parent=root
    )

    if mode:
        mode = mode.strip()
        if "-" in mode:
            a, b = mode.split("-", 1)
            a = a.strip()
            b = b.strip()
            if a.isdigit() and b.isdigit():
                sys.argv += ["--from_race", a, "--to_race", b]
            else:
                messagebox.showerror("Invalid", "Range must be like 1-6")
                raise SystemExit(1)
        else:
            if mode.isdigit():
                sys.argv += ["--race", mode]
            else:
                messagebox.showerror("Invalid", "Race must be an integer like 2")
                raise SystemExit(1)

    # Inject required args
    sys.argv += ["--date", date, "--group", group]


# ---------------------------------------------------------
# PATHS (LOCKED to project root)
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
RACETIMES_PATH = BASE_DIR / "data" / "racetimes" / "RaceTimes.csv"
STARTTIMEVERIFIER_PATH = BASE_DIR / "StartTimeVerifier.py"


def _read_races_for_day(date_ddmmyy: str, group: str):
    if not RACETIMES_PATH.exists():
        raise RuntimeError(f"RaceTimes not found: {RACETIMES_PATH}")

    races = []
    with open(RACETIMES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"date", "race_number", "group_color"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise RuntimeError(f"RaceTimes missing required columns {sorted(required)}")

        for r in reader:
            if (r.get("date") or "").strip() != date_ddmmyy:
                continue
            if (r.get("group_color") or "").strip().lower() != group.lower():
                continue
            rn = (r.get("race_number") or "").strip()
            if rn.isdigit():
                races.append(int(rn))

    races = sorted(set(races))
    return races


def _run_one(date_ddmmyy: str, race_number: int, group: str):
    # IMPORTANT: use the same interpreter that is running THIS script (editor Run uses sys.executable)
    cmd = [
        sys.executable,
        str(STARTTIMEVERIFIER_PATH),
        "--date", date_ddmmyy,
        "--race", str(race_number),
        "--group", group.lower(),
    ]

    print("\n" + "=" * 72)
    print(f"RUN: {date_ddmmyy}  R{race_number}  {group}")
    print("CMD:", " ".join(cmd))
    print("=" * 72)

    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    if res.returncode != 0:
        raise RuntimeError(f"FAILED: {date_ddmmyy} R{race_number} {group} (exit={res.returncode})")

    print(f"OK: {date_ddmmyy} R{race_number} {group}")


def main():
    # Ensure Finder launches (no args) still work.
    _prompt_args_if_missing()

    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="DDMMYY (e.g. 300126)")
    ap.add_argument("--group", required=True, help="fleet/group (e.g. yellow)")
    ap.add_argument("--race", default="", help="optional single race number (e.g. 2)")
    ap.add_argument("--from_race", type=int, default=None, help="optional start race inclusive")
    ap.add_argument("--to_race", type=int, default=None, help="optional end race inclusive")
    args = ap.parse_args()

    date_ddmmyy = str(args.date).strip()
    group = str(args.group).strip().lower()

    if not STARTTIMEVERIFIER_PATH.exists():
        raise RuntimeError(f"StartTimeVerifier not found: {STARTTIMEVERIFIER_PATH}")

    # Single race override
    if str(args.race).strip():
        rn = str(args.race).strip()
        if not rn.isdigit():
            raise RuntimeError("--race must be an integer")
        _run_one(date_ddmmyy, int(rn), group)
        print("\nDONE (single race).")
        return

    races = _read_races_for_day(date_ddmmyy, group)
    if not races:
        raise RuntimeError(f"No races found in RaceTimes for {date_ddmmyy} {group}")

    # Apply range filters
    if args.from_race is not None:
        races = [r for r in races if r >= args.from_race]
    if args.to_race is not None:
        races = [r for r in races if r <= args.to_race]

    if not races:
        raise RuntimeError("After filters, no races remain to run.")

    print(f"Found races for {date_ddmmyy} {group}: {', '.join('R'+str(r) for r in races)}")
    for r in races:
        _run_one(date_ddmmyy, r, group)

    print("\nDONE (all selected races).")


if __name__ == "__main__":
    main()
