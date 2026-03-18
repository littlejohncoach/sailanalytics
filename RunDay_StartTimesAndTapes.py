#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RunDay_StartTimesAndTapes.py
----------------------------------------------------------
One-button "day runner" for Stage-2 pipeline:

UPDATED BEHAVIOUR:
- If trimmed data exists → run StartTimeVerifier (normal)
- If trimmed missing BUT totalraces exists → SKIP safely
- If neither exists → HARD FAIL

This allows re-running after archive without breaking.
----------------------------------------------------------
"""

import argparse
import csv
import sys
import subprocess
from pathlib import Path


# ---------------------------------------------------------
# Finder "Open With Terminal" support
# ---------------------------------------------------------
def _prompt_args_if_missing():
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

    mode = simpledialog.askstring(
        "Run Day (optional)",
        "Optional:\n"
        "- Single race (e.g. 2)\n"
        "- Range (e.g. 1-6)\n"
        "- Blank = all races",
        parent=root
    )

    if mode:
        mode = mode.strip()
        if "-" in mode:
            a, b = mode.split("-", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                sys.argv += ["--from_race", a.strip(), "--to_race", b.strip()]
            else:
                messagebox.showerror("Invalid", "Range must be like 1-6")
                raise SystemExit(1)
        else:
            if mode.isdigit():
                sys.argv += ["--race", mode]
            else:
                messagebox.showerror("Invalid", "Race must be an integer")
                raise SystemExit(1)

    sys.argv += ["--date", date, "--group", group]


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

RACETIMES_PATH = BASE_DIR / "data" / "racetimes" / "RaceTimes.csv"
STARTTIMEVERIFIER_PATH = BASE_DIR / "StartTimeVerifier.py"

TRIMMED_DIR = BASE_DIR / "data" / "trimmed"
TOTAL_DIR = BASE_DIR / "data" / "totalraces"


# ---------------------------------------------------------
# READ RACES
# ---------------------------------------------------------
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

    return sorted(set(races))


# ---------------------------------------------------------
# CORE EXECUTION (UPDATED)
# ---------------------------------------------------------
def _run_one(date_ddmmyy: str, race_number: int, group: str):

    trimmed_pattern = f"*_{date_ddmmyy}_R{race_number}_{group}_trimmed.csv"
    total_pattern = f"*_{date_ddmmyy}_R{race_number}_{group}.csv"

    trimmed_files = list(TRIMMED_DIR.glob(trimmed_pattern))
    total_files = list(TOTAL_DIR.glob(total_pattern))

    # --------------------------------------------------
    # FALLBACK LOGIC
    # --------------------------------------------------
    if not trimmed_files:
        print("\n" + "=" * 72)
        print(f"SKIP StartTimes: {date_ddmmyy}  R{race_number}  {group}")
        print("Reason: no trimmed data")

        if total_files:
            print(f"→ Using existing totalraces ({len(total_files)} files)")
            print("=" * 72)
            return
        else:
            raise RuntimeError(
                f"No data available for {date_ddmmyy} R{race_number} {group} "
                f"(no trimmed + no totalraces)"
            )

    # --------------------------------------------------
    # NORMAL EXECUTION
    # --------------------------------------------------
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
        raise RuntimeError(
            f"FAILED: {date_ddmmyy} R{race_number} {group} (exit={res.returncode})"
        )

    print(f"OK: {date_ddmmyy} R{race_number} {group}")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    _prompt_args_if_missing()

    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--group", required=True)
    ap.add_argument("--race", default="")
    ap.add_argument("--from_race", type=int, default=None)
    ap.add_argument("--to_race", type=int, default=None)
    args = ap.parse_args()

    date_ddmmyy = args.date.strip()
    group = args.group.strip().lower()

    if not STARTTIMEVERIFIER_PATH.exists():
        raise RuntimeError(f"StartTimeVerifier not found: {STARTTIMEVERIFIER_PATH}")

    # Single race
    if args.race:
        if not args.race.isdigit():
            raise RuntimeError("--race must be integer")
        _run_one(date_ddmmyy, int(args.race), group)
        print("\nDONE (single race).")
        return

    races = _read_races_for_day(date_ddmmyy, group)
    if not races:
        raise RuntimeError(f"No races found for {date_ddmmyy} {group}")

    if args.from_race is not None:
        races = [r for r in races if r >= args.from_race]
    if args.to_race is not None:
        races = [r for r in races if r <= args.to_race]

    if not races:
        raise RuntimeError("No races remain after filtering.")

    print(f"Found races: {', '.join('R'+str(r) for r in races)}")

    for r in races:
        _run_one(date_ddmmyy, r, group)

    print("\nDONE (all races).")


if __name__ == "__main__":
    main()