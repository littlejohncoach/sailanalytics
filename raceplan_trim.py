#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
raceplan_trim.py  (PROJECT ROOT)
--------------------------------
Script-only RacePlan + batch trim engine (no backend/frontend).

This version is aligned to YOUR current READY schema:
- It slices by unix_s (not timestamp_utc), because Workflow.py enforces unix_s.

READY day files (no race numbers):
  data/ready/<sailor>_<DDMMYY>_<fleet>_ready.csv
Example:
  data/ready/william_300126_yellow_ready.csv

RacePlan storage:
  data/racetimes/raceplan_<DDMMYY>_<fleet>.csv

RacePlan columns:
  race_number,start_time_hhmm,finish_time_hhmm

Times:
- start_time_hhmm / finish_time_hhmm are interpreted as UTC on that date.

Outputs:
  data/trimmed/<sailor>_<DDMMYY>_R<race_number>_<fleet>_trimmed.csv

Deterministic rules:
- Slice includes rows with unix_s >= gun_unix and <= finish_unix
- elapsed_race_time_s reset to 0 at start of slice
- finished_flag = 1 on the last row of the slice only
- finish_time_utc set to the race finish timestamp (ISO Z) for all rows
- If a sailor has zero rows in a race window => warning, no output file
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import pandas as pd
from datetime import datetime, timezone


# Resolve project root robustly (this file must live in project root)
ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
READY_DIR = DATA_DIR / "ready"
TRIMMED_DIR = DATA_DIR / "trimmed"
RACETIMES_DIR = DATA_DIR / "racetimes"

TRIMMED_DIR.mkdir(parents=True, exist_ok=True)
RACETIMES_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class RaceWindow:
    race_number: int
    gun_unix: int
    finish_unix: int
    finish_iso_z: str


def _require_ddmmyy(ddmmyy: str) -> None:
    if not re.fullmatch(r"\d{6}", ddmmyy):
        raise ValueError("race_date must be DDMMYY (6 digits), e.g. 300126")


def _require_hhmm(hhmm: str) -> None:
    if not re.fullmatch(r"\d{2}:\d{2}", hhmm):
        raise ValueError("time must be HH:MM, e.g. 13:05")


def _hhmm_to_unix(date_ddmmyy: str, hhmm: str) -> int:
    """
    Interpret HH:MM as UTC time on date_ddmmyy.
    """
    _require_ddmmyy(date_ddmmyy)
    _require_hhmm(hhmm)
    dt = datetime.strptime(f"{date_ddmmyy} {hhmm}:00", "%d%m%y %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _unix_to_iso_z(unix_s: int) -> str:
    return datetime.fromtimestamp(int(unix_s), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def raceplan_path(race_date: str, fleet: str) -> Path:
    return RACETIMES_DIR / f"raceplan_{race_date}_{fleet}.csv"


def save_raceplan_template(race_date: str, fleet: str, n_races: int) -> Path:
    """
    Creates a blank raceplan file with N races (00:00 placeholders).
    You fill times later (GUI or manual edit).
    """
    _require_ddmmyy(race_date)
    fleet = fleet.lower().strip()
    if n_races < 1 or n_races > 20:
        raise ValueError("n_races must be 1..20")

    p = raceplan_path(race_date, fleet)
    df = pd.DataFrame({
        "race_number": list(range(1, n_races + 1)),
        "start_time_hhmm": ["00:00"] * n_races,
        "finish_time_hhmm": ["00:00"] * n_races,
    })
    df.to_csv(p, index=False)
    return p


def load_raceplan(race_date: str, fleet: str) -> list[RaceWindow]:
    _require_ddmmyy(race_date)
    fleet = fleet.lower().strip()

    p = raceplan_path(race_date, fleet)
    if not p.exists():
        raise FileNotFoundError(f"Raceplan missing: {p}")

    df = pd.read_csv(p)
    required = {"race_number", "start_time_hhmm", "finish_time_hhmm"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Raceplan {p.name} missing columns: {sorted(missing)}")

    windows: list[RaceWindow] = []

    for _, r in df.iterrows():
        n = int(r["race_number"])
        start_hhmm = str(r["start_time_hhmm"]).strip()
        finish_hhmm = str(r["finish_time_hhmm"]).strip()

        gun_unix = _hhmm_to_unix(race_date, start_hhmm)
        finish_unix = _hhmm_to_unix(race_date, finish_hhmm)

        if finish_unix <= gun_unix:
            raise ValueError(f"Race {n}: finish must be after start")

        windows.append(RaceWindow(
            race_number=n,
            gun_unix=gun_unix,
            finish_unix=finish_unix,
            finish_iso_z=_unix_to_iso_z(finish_unix),
        ))

    windows.sort(key=lambda w: w.race_number)
    return windows


def find_ready_files_for_day(race_date: str, fleet: str) -> list[Path]:
    """
    Expected pattern:
      data/ready/<sailor>_<DDMMYY>_<fleet>_ready.csv
    """
    _require_ddmmyy(race_date)
    fleet = fleet.lower().strip()
    pat = f"*_{race_date}_{fleet}_ready.csv"
    return sorted(READY_DIR.glob(pat))


def _extract_sailor_from_ready_filename(path: Path) -> str:
    # expected: <sailor>_<DDMMYY>_<fleet>_ready.csv
    name = path.name.lower()
    m = re.match(r"^(?P<sailor>.+?)_\d{6}_[a-z]+_ready\.csv$", name)
    return m.group("sailor") if m else name.split("_")[0]


def trim_all(race_date: str, fleet: str) -> dict:
    """
    Batch trim all sailors for a day+fleet using raceplan windows.
    """
    windows = load_raceplan(race_date, fleet)
    ready_files = find_ready_files_for_day(race_date, fleet)

    if not ready_files:
        raise FileNotFoundError(
            f"No READY files found for {race_date} {fleet} in {READY_DIR}\n"
            f"Expected pattern: *_{race_date}_{fleet}_ready.csv"
        )

    outputs: list[str] = []
    warnings: list[str] = []

    for rf in ready_files:
        sailor = _extract_sailor_from_ready_filename(rf)

        df = pd.read_csv(rf)
        if "unix_s" not in df.columns:
            raise ValueError(f"{rf.name} missing required column: unix_s")

        # Ensure unix_s is numeric int
        df["unix_s"] = pd.to_numeric(df["unix_s"], errors="coerce")
        if df["unix_s"].isna().all():
            raise ValueError(f"{rf.name} has invalid unix_s values (all NaN)")
        df["unix_s"] = df["unix_s"].astype("int64")

        for w in windows:
            race_id = f"{race_date}_R{w.race_number}_{fleet}"
            out = TRIMMED_DIR / f"{sailor}_{race_id}_trimmed.csv"

            dfr = df[(df["unix_s"] >= w.gun_unix) & (df["unix_s"] <= w.finish_unix)].copy()
            if len(dfr) == 0:
                warnings.append(f"{rf.name} -> {race_id}: no samples in window")
                continue

            dfr = dfr.sort_values("unix_s").reset_index(drop=True)

            # Deterministic truth fields
            dfr["elapsed_race_time_s"] = (dfr["unix_s"] - w.gun_unix).astype("int64")
            dfr["finish_time_utc"] = w.finish_iso_z

            # finished_flag: ensure exists and is correct
            dfr["finished_flag"] = 0
            dfr.loc[len(dfr) - 1, "finished_flag"] = 1

            dfr.to_csv(out, index=False)
            outputs.append(str(out))

    return {
        "race_date": race_date,
        "fleet": fleet,
        "raceplan": str(raceplan_path(race_date, fleet)),
        "ready_files": [str(p) for p in ready_files],
        "outputs_written": outputs,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python3 raceplan_trim.py <DDMMYY> <fleet> [--init N]")
        raise SystemExit(2)

    race_date = sys.argv[1].strip()
    fleet = sys.argv[2].strip().lower()

    if len(sys.argv) == 5 and sys.argv[3] == "--init":
        n = int(sys.argv[4])
        p = save_raceplan_template(race_date, fleet, n)
        print(f"Created: {p}")
        raise SystemExit(0)

    res = trim_all(race_date, fleet)
    print("OK")
    print("Raceplan:", res["raceplan"])
    print("READY files:", len(res["ready_files"]))
    print("Outputs written:", len(res["outputs_written"]))
    if res["warnings"]:
        print("WARNINGS:")
        for w in res["warnings"]:
            print(" -", w)
