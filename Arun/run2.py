#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SailAnalytics/Arun/run2.py

RUN2 = Full automatic pipeline:

1) RunDay_StartTimesAndTapes.py   (build truth tapes)
2) coach/AddGeometryToTape.py     (headless: enrich tapes -> totalraces)
3) Housekeeping BEFORE dashboard launch:
   - Archive sovereign files into: data/archive/<date>_R<race>_<group>/
       tapes/*_<date>_R<race>_<group>.csv
       geometry/geometry_<date>_R<race>_<group>.csv
       marks/marks_<date>_R<race>_<group>.csv
   - COPY sovereign files to archive, but LEAVE originals in place
     so the dashboard can still read live folders
   - Move non-sovereign working files to Trash:
       data/ready/*    (contents)
       data/trimmed/*  (contents)
   - Leaves data/totalraces/ untouched
4) Launch dashboard (detached, so this runner exits)
"""

from __future__ import annotations

import csv
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


# --------------------------------------------------
# PATH RESOLUTION
# --------------------------------------------------
ARUN_DIR = Path(__file__).resolve().parent
SA_ROOT = ARUN_DIR.parent
COACH_DIR = SA_ROOT / "coach"

RUN_DAY_PATH = SA_ROOT / "RunDay_StartTimesAndTapes.py"
ADD_GEOM_PATH = COACH_DIR / "AddGeometryToTape.py"
DASHBOARD_PATH = COACH_DIR / "run_dashboard.py"
RACETIMES_PATH = SA_ROOT / "data" / "racetimes" / "RaceTimes.csv"

DATA_DIR = SA_ROOT / "data"
READY_DIR = DATA_DIR / "ready"
TRIMMED_DIR = DATA_DIR / "trimmed"
TAPES_DIR = DATA_DIR / "tapes"
GEOM_DIR = DATA_DIR / "geometry"
MARKS_DIR = DATA_DIR / "marks"
ARCHIVE_ROOT = DATA_DIR / "archive"


# --------------------------------------------------
# INPUT DIALOG
# --------------------------------------------------
def prompt_inputs():
    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()

    try:
        date = simpledialog.askstring("RUN2", "Date (DDMMYY):", parent=root)
        if not date:
            raise SystemExit(0)
        date = date.strip()

        group = simpledialog.askstring("RUN2", "Group (e.g. yellow):", parent=root)
        if not group:
            raise SystemExit(0)
        group = group.strip().lower()

        mode = simpledialog.askstring(
            "RUN2 (optional)",
            "Optional race filter:\n"
            "- Single race (e.g. 2)\n"
            "- Range (e.g. 1-6)\n"
            "- Blank = all races",
            parent=root
        )

        race_single: Optional[int] = None
        from_race: Optional[int] = None
        to_race: Optional[int] = None

        if mode:
            mode = mode.strip()
            if "-" in mode:
                a, b = mode.split("-", 1)
                a = a.strip()
                b = b.strip()
                if not (a.isdigit() and b.isdigit()):
                    raise SystemExit("Invalid range. Use like 1-6.")
                from_race = int(a)
                to_race = int(b)
            else:
                m = mode.strip()
                if not m.isdigit():
                    raise SystemExit("Invalid race. Use an integer like 2.")
                race_single = int(m)

        return date, group, race_single, from_race, to_race

    finally:
        try:
            root.destroy()
        except Exception:
            pass


# --------------------------------------------------
# READ RACES
# --------------------------------------------------
def read_races(date: str, group: str) -> List[int]:
    if not RACETIMES_PATH.exists():
        raise FileNotFoundError(f"Missing: {RACETIMES_PATH}")

    races: List[int] = []
    with open(RACETIMES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"date", "race_number", "group_color"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise RuntimeError(f"RaceTimes.csv missing required columns: {sorted(required)}")

        for r in reader:
            if (r.get("date") or "").strip() != date:
                continue
            if (r.get("group_color") or "").strip().lower() != group:
                continue
            rn = (r.get("race_number") or "").strip()
            if rn.isdigit():
                races.append(int(rn))

    return sorted(set(races))


# --------------------------------------------------
# STEP 1 — START TIMES + TAPES
# --------------------------------------------------
def run_starttimes(date: str, group: str, races: List[int]) -> None:
    if not RUN_DAY_PATH.exists():
        raise FileNotFoundError(f"Missing: {RUN_DAY_PATH}")

    for r in races:
        cmd = [
            sys.executable,
            str(RUN_DAY_PATH),
            "--date", date,
            "--group", group,
            "--race", str(r),
        ]

        print(f"\n[1/4] StartTimes + Tapes: {date} R{r} {group}")
        res = subprocess.run(cmd, cwd=str(SA_ROOT))
        if res.returncode != 0:
            raise RuntimeError(f"FAILED StartTimes+Tapes: {date} R{r} {group} (exit={res.returncode})")


# --------------------------------------------------
# STEP 2 — ADD GEOMETRY
# --------------------------------------------------
def import_addgeom():
    if not ADD_GEOM_PATH.exists():
        raise FileNotFoundError(f"Missing: {ADD_GEOM_PATH}")

    spec = importlib.util.spec_from_file_location("addgeom", str(ADD_GEOM_PATH))
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import AddGeometryToTape from {ADD_GEOM_PATH}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def run_addgeometry(date: str, group: str, races: List[int]) -> None:
    addgeom = import_addgeom()

    for r in races:
        geom = addgeom.load_geometry(date, str(r), group)

        pattern = f"*_{date}_R{r}_{group}.csv"
        tapes = sorted(addgeom.TAPES_DIR.glob(pattern))

        if not tapes:
            print(f"(skip) No tapes found for {date} R{r} {group}: {pattern}")
            continue

        print(f"[2/4] AddGeometry: {date} R{r} {group}  ({len(tapes)} tapes)")
        for tp in tapes:
            addgeom.enrich_tape_with_geometry(tp, geom)


# --------------------------------------------------
# TRASH HELPERS
# --------------------------------------------------
def move_to_trash(path: Path) -> None:
    if not path.exists():
        return
    cmd = [
        "osascript",
        "-e",
        f'tell application "Finder" to delete POSIX file "{str(path)}"'
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def trash_folder_contents(folder: Path, label: str) -> None:
    if not folder.exists():
        print(f"[3/4] Trash {label}: (folder missing) {folder}")
        return

    items = [p for p in folder.iterdir() if p.name != ".DS_Store"]
    if not items:
        print(f"[3/4] Trash {label}: (nothing to trash) {folder}")
        return

    for p in items:
        move_to_trash(p)

    print(f"[3/4] Trashed contents of {label}: {folder}")


# --------------------------------------------------
# STEP 3 — ARCHIVE + CLEAN
# --------------------------------------------------
def archive_sovereign_and_trash_working(date: str, group: str, races: List[int]) -> None:
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)

    for r in races:
        race_id = f"{date}_R{r}_{group}"
        race_archive = ARCHIVE_ROOT / race_id
        race_archive.mkdir(parents=True, exist_ok=True)

        tapes_dst = race_archive / "tapes"
        geom_dst = race_archive / "geometry"
        marks_dst = race_archive / "marks"
        tapes_dst.mkdir(parents=True, exist_ok=True)
        geom_dst.mkdir(parents=True, exist_ok=True)
        marks_dst.mkdir(parents=True, exist_ok=True)

        # tapes: COPY, do not move
        tape_pattern = f"*_{date}_R{r}_{group}.csv"
        copied_tapes = 0
        for tp in sorted(TAPES_DIR.glob(tape_pattern)):
            dest = tapes_dst / tp.name
            if dest.exists():
                continue
            shutil.copy2(str(tp), str(dest))
            copied_tapes += 1

        # geometry: COPY, do not move
        geom_file = GEOM_DIR / f"geometry_{date}_R{r}_{group}.csv"
        copied_geom = 0
        if geom_file.exists():
            dest = geom_dst / geom_file.name
            if not dest.exists():
                shutil.copy2(str(geom_file), str(dest))
                copied_geom = 1

        # marks: COPY, do not move
        marks_file = MARKS_DIR / f"marks_{date}_R{r}_{group}.csv"
        copied_marks = 0
        if marks_file.exists():
            dest = marks_dst / marks_file.name
            if not dest.exists():
                shutil.copy2(str(marks_file), str(dest))
                copied_marks = 1

        print(f"[3/4] Archived {race_id}: tapes={copied_tapes}, geometry={copied_geom}, marks={copied_marks}")

    # trash only working folders
    trash_folder_contents(READY_DIR, "data/ready")
    trash_folder_contents(TRIMMED_DIR, "data/trimmed")


# --------------------------------------------------
# STEP 4 — DASHBOARD
# --------------------------------------------------
def launch_dashboard_detached() -> None:
    if not DASHBOARD_PATH.exists():
        raise FileNotFoundError(f"Missing: {DASHBOARD_PATH}")

    print("\n[4/4] Launching Dashboard (detached)...")

    p = subprocess.Popen(
        [sys.executable, str(DASHBOARD_PATH)],
        cwd=str(COACH_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    print(f"Dashboard PID: {p.pid}")
    print("Dashboard should open at http://127.0.0.1:8000/")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main() -> None:
    date, group, race_single, from_race, to_race = prompt_inputs()

    races = read_races(date, group)
    if not races:
        raise RuntimeError(f"No races found for {date} {group} in RaceTimes.csv")

    if race_single is not None:
        races = [race_single]
    else:
        if from_race is not None:
            races = [r for r in races if r >= from_race]
        if to_race is not None:
            races = [r for r in races if r <= to_race]

    if not races:
        raise RuntimeError("No races remain after filter.")

    print(f"\nRaces to process: {races}")

    run_starttimes(date, group, races)
    run_addgeometry(date, group, races)
    archive_sovereign_and_trash_working(date, group, races)
    launch_dashboard_detached()

    raise SystemExit(0)


if __name__ == "__main__":
    main()