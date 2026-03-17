#!/usr/bin/env python3
# Workflow.py
# READY → TRIMMED trimming pipeline
#
# Supported FIT filename formats:
# 1) legacy per-race:
#    <sailor>_<DDMMYY>_R<race>_<group>.FIT
#    e.g. berkay_271125_R1_yellow.FIT
#
# 2) day log (no race):
#    <sailor>_<DDMMYY>_<group>.FIT
#    e.g. william_300126_yellow.FIT
#
# In day-log mode, the GUI race number is canonical.

import os
import subprocess
import sys
import json
import pandas as pd
from datetime import datetime, timezone

FIT_DIR     = "data/fit"
READY_DIR   = "data/ready"
TRIMMED_DIR = "data/trimmed"
RACETIMES_PATH = "data/racetimes/RaceTimes.csv"


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def parse_fit_filename(fit_filename):
    """
    Supports two formats:

    A) berkay_271125_R1_yellow.FIT
       -> sailor=berkay, date=271125, race=1, group=yellow

    B) william_300126_yellow.FIT
       -> sailor=william, date=300126, race=None, group=yellow
    """
    stem = os.path.splitext(fit_filename)[0]
    parts = stem.split("_")

    # Day-log format: <sailor>_<DDMMYY>_<group>
    if len(parts) == 3:
        sailor = parts[0].lower()
        date   = parts[1]
        group  = parts[2].lower()
        return sailor, date, None, group

    # Legacy per-race format: <sailor>_<DDMMYY>_R<race>_<group>
    if len(parts) == 4:
        sailor = parts[0].lower()
        date   = parts[1]

        if not parts[2].startswith("R"):
            raise RuntimeError(f"Invalid race token in FIT filename: {fit_filename}")

        race  = parts[2][1:]
        group = parts[3].lower()
        return sailor, date, race, group

    raise RuntimeError(f"Invalid FIT filename format: {fit_filename}")


def parse_hms_to_unix(date_ddmmyy, hms):
    dt = datetime.strptime(
        f"{date_ddmmyy} {hms}",
        "%d%m%y %H:%M:%S"
    ).replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def ensure_ready_csv(fit_filename):
    """
    READY naming follows FIT stem:
      data/ready/<stem>_ready.csv
    Examples:
      william_300126_yellow_ready.csv
      berkay_271125_R1_yellow_ready.csv
    """
    stem = os.path.splitext(fit_filename)[0]
    ready_csv = os.path.join(READY_DIR, f"{stem}_ready.csv")

    if os.path.isfile(ready_csv):
        return ready_csv

    os.makedirs(READY_DIR, exist_ok=True)

    script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "FitToReady.py"
    )

    if not os.path.isfile(script):
        raise RuntimeError("FitToReady.py not found")

    subprocess.run(
        [
            sys.executable,
            script,
            "--in",  FIT_DIR,
            "--out", READY_DIR
        ],
        check=True
    )

    if not os.path.isfile(ready_csv):
        raise RuntimeError(f"READY file not created: {ready_csv}")

    return ready_csv


def write_trimmed_index():
    """
    Deterministically regenerate trimmed_tracks_index.json
    from actual *_trimmed.csv files on disk.
    """
    os.makedirs(TRIMMED_DIR, exist_ok=True)

    files = sorted(
        f for f in os.listdir(TRIMMED_DIR)
        if f.endswith("_trimmed.csv")
    )

    index_path = os.path.join(TRIMMED_DIR, "trimmed_tracks_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(files, f, indent=2)


# ---------------------------------------------------------
# ensure X times exist in RaceTimes.csv
# ---------------------------------------------------------

def ensure_race_x_times(date, race, group, gun_unix):
    if not os.path.isfile(RACETIMES_PATH):
        return

    df = pd.read_csv(RACETIMES_PATH, dtype=str)

    mask = (
        (df["date"] == date) &
        (df["race_number"] == str(race)) &
        (df["group_color"].str.lower() == str(group).lower())
    )

    if not mask.any():
        return

    idx = df.index[mask][0]

    # Only write once
    if "x_10_unix" in df.columns and pd.notna(df.at[idx, "x_10_unix"]):
        return

    df.loc[idx, "x_10_unix"] = int(gun_unix) + 10
    df.loc[idx, "x_20_unix"] = int(gun_unix) + 20
    df.loc[idx, "x_30_unix"] = int(gun_unix) + 30

    df.to_csv(RACETIMES_PATH, index=False)


# ---------------------------------------------------------
# MAIN PIPELINE (called by GUI) — single race trim
# ---------------------------------------------------------

def run_trimming_pipeline(fit_filename, date_gui, race_gui, gun_time_utc, finish_time_utc):
    """
    Single-race trim.

    - If FIT is legacy (has race in filename): race from filename wins.
    - If FIT is day-log (no race): GUI race number is required.

    Times passed in are UTC HMS strings (HH:MM:SS).
    """

    os.makedirs(TRIMMED_DIR, exist_ok=True)

    sailor, date_fit, race_fit, group_fit = parse_fit_filename(fit_filename)

    # Validate date
    if date_gui and date_fit != date_gui:
        raise RuntimeError(f"Date mismatch: FIT has {date_fit}, GUI has {date_gui}")

    date = date_fit

    # Resolve race
    if race_fit is not None:
        race = race_fit
    else:
        if not race_gui:
            raise RuntimeError("Race # is required in GUI for day-log FITs (no R token in filename).")
        race = str(race_gui).strip()

    # Ensure READY exists
    ready_csv = ensure_ready_csv(fit_filename)
    df = pd.read_csv(ready_csv)

    if "unix_s" not in df.columns:
        raise RuntimeError("READY CSV missing unix_s column")

    gun_unix    = parse_hms_to_unix(date, gun_time_utc)
    finish_unix = parse_hms_to_unix(date, finish_time_utc)

    if finish_unix <= gun_unix:
        raise RuntimeError("Finish time must be after gun time")

    # Write X times to RaceTimes.csv (if row exists)
    ensure_race_x_times(date, race, group_fit, gun_unix)

    trimmed = df[
        (df["unix_s"] >= gun_unix) &
        (df["unix_s"] <= finish_unix)
    ].copy()

    if trimmed.empty:
        raise RuntimeError("Trim resulted in empty dataset")

    trimmed = trimmed.sort_values("unix_s").reset_index(drop=True)

    out_name = f"{sailor}_{date}_R{race}_{group_fit}_trimmed.csv"
    out_csv  = os.path.join(TRIMMED_DIR, out_name)

    trimmed.to_csv(out_csv, index=False)

    write_trimmed_index()

    return out_csv


# ---------------------------------------------------------
# NEW: Trim ALL races for a day+group for selected FIT tracks
# ---------------------------------------------------------

def run_trim_all_races_for_day(selected_fit_filenames, date, group):
    """
    Trim ALL races for a given day+group for the selected FIT tracks.

    selected_fit_filenames: list of FIT filenames (strings) from GUI listbox
      e.g. ["william_300126_yellow.FIT", "yalcin_300126_yellow.FIT"]

    Requires RaceTimes.csv rows for (date, group_color) with:
      gun_time (UTC HH:MM:SS), finish_time (UTC HH:MM:SS)

    Writes:
      data/trimmed/<sailor>_<date>_R<race>_<group>_trimmed.csv
    """
    if not os.path.isfile(RACETIMES_PATH):
        raise RuntimeError("RaceTimes.csv not found")

    rows = pd.read_csv(RACETIMES_PATH, dtype=str)

    day_rows = rows[
        (rows["date"] == str(date)) &
        (rows["group_color"].str.lower() == str(group).lower())
    ].copy()

    if day_rows.empty:
        raise RuntimeError(f"No race times found in RaceTimes.csv for {date} {group}")

    # Sort by numeric race_number
    day_rows["race_number_int"] = day_rows["race_number"].astype(int)
    day_rows = day_rows.sort_values("race_number_int").reset_index(drop=True)

    os.makedirs(TRIMMED_DIR, exist_ok=True)

    outputs = []

    for fit_filename in selected_fit_filenames:
        # Ensure READY exists for THIS FIT (day-log or legacy)
        ready_csv = ensure_ready_csv(fit_filename)
        df = pd.read_csv(ready_csv)

        if "unix_s" not in df.columns:
            raise RuntimeError(f"READY CSV missing unix_s column: {ready_csv}")

        sailor, date_fit, _, group_fit = parse_fit_filename(fit_filename)

        if date_fit != str(date):
            raise RuntimeError(f"Date mismatch: FIT has {date_fit}, requested {date}")

        if group_fit.lower() != str(group).lower():
            raise RuntimeError(f"Group mismatch: FIT has {group_fit}, requested {group}")

        for _, r in day_rows.iterrows():
            race = str(r["race_number"]).strip()
            gun_hms = str(r["gun_time"]).strip()       # already UTC
            fin_hms = str(r["finish_time"]).strip()    # already UTC

            gun_unix = parse_hms_to_unix(date, gun_hms)
            fin_unix = parse_hms_to_unix(date, fin_hms)

            if fin_unix <= gun_unix:
                raise RuntimeError(f"Finish <= gun for {date} R{race} {group}")

            # X-time enrichment (if row exists)
            ensure_race_x_times(date, race, group_fit, gun_unix)

            trimmed = df[(df["unix_s"] >= gun_unix) & (df["unix_s"] <= fin_unix)].copy()
            if trimmed.empty:
                continue

            trimmed = trimmed.sort_values("unix_s").reset_index(drop=True)

            out_name = f"{sailor}_{date}_R{race}_{group_fit}_trimmed.csv"
            out_csv = os.path.join(TRIMMED_DIR, out_name)

            trimmed.to_csv(out_csv, index=False)
            outputs.append(out_csv)

    write_trimmed_index()
    return outputs
