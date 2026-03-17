#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TapeFinishFinder.py
----------------------------------------------------------
Pipeline-activated finish line detection + truth passes.

Inputs:
- Existing <sailor>_<date>_R<race>_<group>.csv in data/tapes/ (or legacy Tape_<date>_R<race>_<sailor>.csv)
- marks_<date>_R<race>_<group>.csv (FinishS / FinishP)
- <sailor>_<date>_R<race>_<group>_trimmed.csv in data/trimmed/ (heart_rate)

Behavior:
1) Finds first TRUE finite segment–segment intersection between
   sailor track segments and the finite FinishS–FinishP segment
2) Interpolates exact crossing timestamp
3) Appends (ADD ONLY):
      finish_time_utc
      elapsed_race_time_s
      finished_flag
4) Pipeline hooks (IN-PROCESS, NO SHELL):
      TruthDistance.py  -> process_one_csv(path)
      TruthMotionRaw.py -> process_one_csv(path)
5) Heart-rate truth (ADD ONLY; no zones; no smoothing here):
      HR_raw_bpm
      HR_filled_bpm
      HR_imputed_flag

HR fill rule:
- Internal gaps: linear interpolation in time between the two bracketing valid HR samples
- Leading gaps: forward-fill from first valid
- Trailing gaps: back-fill from last valid

Append-only law everywhere: hard error if any target column already exists.
----------------------------------------------------------
"""

import csv
import math
import re
import argparse
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------
# PATHS (LOCKED)
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MARKS_DIR = DATA_DIR / "marks"
TAPES_DIR = DATA_DIR / "tapes"
TRIMMED_DIR_DEFAULT = DATA_DIR / "trimmed"


# ---------------------------------------------------------
# GEOMETRY (mirrors StartTimeVerifier)
# ---------------------------------------------------------
def project(lat, lon, lat0, lon0):
    R = 6371000.0
    x = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * R
    return x, y


def segment_intersection(A, B, P, Q):
    """
    Finite segment–segment intersection.

    A->B : finish line segment
    P->Q : boat track segment

    Returns:
        u in [0,1] along boat segment (P->Q) if intersection exists,
        else None.
    """
    ax, ay = A
    bx, by = B
    px, py = P
    qx, qy = Q

    rx, ry = bx - ax, by - ay      # finish line vector
    sx, sy = qx - px, qy - py      # boat segment vector

    denom = rx * sy - ry * sx
    if abs(denom) < 1e-12:
        return None  # parallel / collinear

    qpx, qpy = px - ax, py - ay

    # t = parameter on finish line (A->B)
    t = (qpx * sy - qpy * sx) / denom

    # u = parameter on boat segment (P->Q)
    u = (qpx * ry - qpy * rx) / denom

    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return u

    return None


# ---------------------------------------------------------
# LOAD FINISH LINE (obeys skipped == 0)
# ---------------------------------------------------------
def load_finish_line(marks_path: Path):
    finishS = finishP = None

    with open(marks_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if str(r.get("skipped", "")).strip() not in ("", "0"):
                continue

            name = (r.get("name") or "").strip()
            if name == "FinishS":
                finishS = (float(r["lat"]), float(r["lon"]))
            elif name == "FinishP":
                finishP = (float(r["lat"]), float(r["lon"]))

    if finishS is None or finishP is None:
        raise RuntimeError("FinishS / FinishP not found (skipped must be 0)")

    return finishS, finishP


# ---------------------------------------------------------
# FIND FIRST CROSSING (finite segments only)
# ---------------------------------------------------------
def first_crossing_time(ts, la, lo, S, P):
    lat0 = (S[0] + P[0]) / 2.0
    lon0 = (S[1] + P[1]) / 2.0

    A = project(S[0], S[1], lat0, lon0)
    B = project(P[0], P[1], lat0, lon0)

    pts = []
    for t, lat, lon in zip(ts, la, lo):
        x, y = project(lat, lon, lat0, lon0)
        pts.append((t, x, y))

    for i in range(len(pts) - 1):
        t0, x0, y0 = pts[i]
        t1, x1, y1 = pts[i + 1]

        u = segment_intersection(A, B, (x0, y0), (x1, y1))
        if u is not None:
            dt = (t1 - t0).total_seconds()
            return t0 + timedelta(seconds=dt * u)

    return None


# ---------------------------------------------------------
# APPEND-ONLY UPDATE (FINISH COLS)
# ---------------------------------------------------------
def append_finish_cols(tape_path: Path, finish_iso: str, elapsed_s: int, finished_flag: int):
    with open(tape_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    # Sacrosanct Tape Law: never overwrite existing columns
    for c in ("finish_time_utc", "elapsed_race_time_s", "finished_flag"):
        if c in fieldnames:
            raise RuntimeError(f"{tape_path.name}: column exists (sacrosanct): {c}")

    if "timestamp_utc" not in fieldnames:
        raise RuntimeError(f"{tape_path.name}: missing timestamp_utc")

    if ("latitude_deg" in fieldnames) != ("longitude_deg" in fieldnames):
        raise RuntimeError(f"{tape_path.name}: inconsistent *_deg columns")

    if "latitude_deg" in fieldnames and "longitude_deg" in fieldnames:
        lat_col, lon_col = "latitude_deg", "longitude_deg"
    elif "latitude" in fieldnames and "longitude" in fieldnames:
        lat_col, lon_col = "latitude", "longitude"
    else:
        raise RuntimeError(f"{tape_path.name}: missing latitude/longitude columns")

    # Append new columns
    fieldnames = fieldnames + ["finish_time_utc", "elapsed_race_time_s", "finished_flag"]

    for r in rows:
        r["finish_time_utc"] = finish_iso
        r["elapsed_race_time_s"] = str(elapsed_s)
        r["finished_flag"] = str(finished_flag)

        # keep existing columns untouched
        _ = r.get(lat_col)
        _ = r.get(lon_col)

    with open(tape_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------
# HR: trimmed file matching + deterministic fill + append-only
# ---------------------------------------------------------
def _parse_ts_utc(s: str) -> datetime:
    s = str(s).strip()
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _tape_sailor_token(tape_name: str) -> str:
    # New canonical: <sailor>_<ddmmyy>_R<n>_<group>.csv
    m = re.match(r"^([a-zA-Z0-9]+)_(\d{6})_R(\d+)_([a-zA-Z0-9]+)\.csv$", tape_name)
    if m:
        return m.group(1).lower()

    # Legacy canonical: Tape_<ddmmyy>_R<n>_<sailor>.csv
    m = re.match(r"^Tape_(\d{6})_R(\d+)_([a-zA-Z0-9]+)\.csv$", tape_name)
    if m:
        return m.group(3).lower()

    raise RuntimeError(
        f"{tape_name}: filename not canonical (expected <sailor>_<ddmmyy>_R<n>_<group>.csv or Tape_<ddmmyy>_R<n>_<sailor>.csv)"
    )


def _resolve_trimmed_path(trimmed_dir: Path, date: str, race_number: str, group: str, sailor: str) -> Path:
    """
    Deterministic expectation:
      <sailor>_<date>_R<race_number>_<group>_trimmed.csv

    If not found, allow wildcard variants but must be unique.
    """
    expected = trimmed_dir / f"{sailor}_{date}_R{race_number}_{group}_trimmed.csv"
    if expected.exists():
        return expected

    hits = sorted(trimmed_dir.glob(f"{sailor}_{date}_R{race_number}_{group}*trimmed*.csv"))
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise RuntimeError(f"Multiple trimmed candidates for {sailor}: {hits}")

    raise RuntimeError(f"Trimmed HR file not found for {sailor}. Expected: {expected}")


def _load_trimmed_hr(trimmed_path: Path):
    """
    Returns:
      hr_by_unix_s: dict[int -> float]
    Accepts either:
      - unix_s + heart_rate
      - timestamp_iso (or timestamp_utc) + heart_rate
    """
    with open(trimmed_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []

        if "heart_rate" not in cols:
            raise RuntimeError(f"{trimmed_path.name}: missing heart_rate column")

        has_unix = "unix_s" in cols
        ts_col = None
        if not has_unix:
            for cand in ("timestamp_iso", "timestamp_utc", "timestamp"):
                if cand in cols:
                    ts_col = cand
                    break
            if ts_col is None:
                raise RuntimeError(f"{trimmed_path.name}: needs unix_s or a timestamp column")

        hr_by_unix = {}
        for r in reader:
            if has_unix:
                us = int(round(float(r["unix_s"])))
            else:
                dt = _parse_ts_utc(r[ts_col])
                us = int(dt.timestamp())

            hr = r.get("heart_rate", "")
            if hr is None or str(hr).strip() == "":
                # allow missing HR in trimmed (will become None in tape mapping)
                continue

            v = float(hr)

            # Deterministic de-dup: average if same second appears twice
            if us in hr_by_unix:
                hr_by_unix[us] = (hr_by_unix[us] + v) / 2.0
            else:
                hr_by_unix[us] = v

    return hr_by_unix


def _fill_hr(unix_s_list, hr_raw_list):
    """
    Deterministic fill:
      - Internal gaps: linear interpolation in time (unix seconds)
      - Start gap: forward-fill
      - End gap: back-fill
    """
    n = len(hr_raw_list)
    hr_filled = [None] * n

    # locate valid indices
    valid = [i for i, v in enumerate(hr_raw_list) if v is not None]
    if not valid:
        raise RuntimeError("No valid HR samples found to fill from (all missing).")

    first = valid[0]
    last = valid[-1]

    # forward-fill start
    for i in range(0, first):
        hr_filled[i] = float(hr_raw_list[first])

    # back-fill end
    for i in range(last + 1, n):
        hr_filled[i] = float(hr_raw_list[last])

    # copy known points
    for i in valid:
        hr_filled[i] = float(hr_raw_list[i])

    # interpolate internal gaps between consecutive valid points
    for a, b in zip(valid[:-1], valid[1:]):
        # if adjacent, nothing to fill
        if b == a + 1:
            continue

        t0 = unix_s_list[a]
        t1 = unix_s_list[b]
        v0 = float(hr_raw_list[a])
        v1 = float(hr_raw_list[b])

        dt = (t1 - t0)
        for i in range(a + 1, b):
            ti = unix_s_list[i]
            if dt <= 0:
                hr_filled[i] = v0
            else:
                frac = (ti - t0) / dt
                hr_filled[i] = v0 + (v1 - v0) * frac

    # any remaining None should not exist
    for i, v in enumerate(hr_filled):
        if v is None:
            hr_filled[i] = float(hr_raw_list[first])

    return hr_filled


def append_hr_cols_from_trimmed(tape_path: Path, trimmed_dir: Path, date: str, race_number: str, group: str):
    with open(tape_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    # Append-only law
    for c in ("HR_raw_bpm", "HR_filled_bpm", "HR_imputed_flag"):
        if c in fieldnames:
            raise RuntimeError(f"{tape_path.name}: column exists (sacrosanct): {c}")

    if "timestamp_utc" not in fieldnames:
        raise RuntimeError(f"{tape_path.name}: missing timestamp_utc")

    sailor = _tape_sailor_token(tape_path.name)
    trimmed_path = _resolve_trimmed_path(trimmed_dir, date, race_number, group, sailor)

    hr_by_unix = _load_trimmed_hr(trimmed_path)

    unix_s = []
    hr_raw = []

    for r in rows:
        dt = _parse_ts_utc(r["timestamp_utc"])
        us = int(dt.timestamp())
        unix_s.append(us)

        v = hr_by_unix.get(us, None)
        hr_raw.append(v if v is None else float(v))

    hr_filled = _fill_hr(unix_s, hr_raw)

    # Flags + stringify (keep numbers stable)
    hr_imputed_flag = []
    hr_raw_str = []
    hr_filled_str = []

    for raw_v, fill_v in zip(hr_raw, hr_filled):
        if raw_v is None:
            hr_raw_str.append("")
            hr_imputed_flag.append("1")
        else:
            hr_raw_str.append(f"{float(raw_v):.1f}")
            hr_imputed_flag.append("0")

        hr_filled_str.append(f"{float(fill_v):.1f}")

    # Append new columns at end
    fieldnames = fieldnames + ["HR_raw_bpm", "HR_filled_bpm", "HR_imputed_flag"]
    for i, r in enumerate(rows):
        r["HR_raw_bpm"] = hr_raw_str[i]
        r["HR_filled_bpm"] = hr_filled_str[i]
        r["HR_imputed_flag"] = hr_imputed_flag[i]

    with open(tape_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    missing_raw = sum(1 for v in hr_raw if v is None)
    print(f"HR  {tape_path.name}  src={trimmed_path.name}  missing_raw={missing_raw}")


# ---------------------------------------------------------
# PIPELINE HOOK: RUN TruthDistance.py + TruthMotionRaw.py (IN-PROCESS, NO SHELL)
# ---------------------------------------------------------
def run_truth_distance_and_motion_raw_on_files(tape_files):
    truthdistance_path = BASE_DIR / "TruthDistance.py"
    if not truthdistance_path.exists():
        raise RuntimeError(f"TruthDistance.py not found next to TapeFinishFinder.py: {truthdistance_path}")

    spec_d = importlib.util.spec_from_file_location("TruthDistance", str(truthdistance_path))
    if spec_d is None or spec_d.loader is None:
        raise RuntimeError("Failed to load TruthDistance.py module spec")

    mod_d = importlib.util.module_from_spec(spec_d)
    spec_d.loader.exec_module(mod_d)  # type: ignore

    if not hasattr(mod_d, "process_one_csv"):
        raise RuntimeError("TruthDistance.py must expose process_one_csv(path: str)")

    truthmotion_path = BASE_DIR / "TruthMotionRaw.py"
    if not truthmotion_path.exists():
        raise RuntimeError(f"TruthMotionRaw.py not found next to TapeFinishFinder.py: {truthmotion_path}")

    spec_m = importlib.util.spec_from_file_location("TruthMotionRaw", str(truthmotion_path))
    if spec_m is None or spec_m.loader is None:
        raise RuntimeError("Failed to load TruthMotionRaw.py module spec")

    mod_m = importlib.util.module_from_spec(spec_m)
    spec_m.loader.exec_module(mod_m)  # type: ignore

    if not hasattr(mod_m, "process_one_csv"):
        raise RuntimeError("TruthMotionRaw.py must expose process_one_csv(path: str)")

    for tp in tape_files:
        mod_d.process_one_csv(str(tp))
        mod_m.process_one_csv(str(tp))


# ---------------------------------------------------------
# MAIN (PIPELINE-ACTIVATED)
# ---------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--race_id", required=True)  # e.g. 301125_R1_yellow
    ap.add_argument("--trimmed_dir", default=str(TRIMMED_DIR_DEFAULT), help="Directory containing *_trimmed.csv (default: data/trimmed)")
    ap.add_argument("--skip_hr", action="store_true", help="Skip HR append step (default: HR ON)")
    args = ap.parse_args()

    race_id = args.race_id
    date, rpart, group = race_id.split("_")
    race_number = rpart.replace("R", "")

    trimmed_dir = Path(args.trimmed_dir)

    marks_path = MARKS_DIR / f"marks_{date}_R{race_number}_{group}.csv"
    if not marks_path.exists():
        raise RuntimeError(f"Marks not found: {marks_path}")

    finishS, finishP = load_finish_line(marks_path)

        # New canonical tapes: <sailor>_<date>_R<race_number>_<group>.csv
    # race_id already encodes: <date>_R<race_number>_<group>
    tape_files = sorted(TAPES_DIR.glob(f"*_{race_id}.csv"))

    # Backward-compatible support (legacy): Tape_<date>_R<race_number>_<sailor>.csv
    if not tape_files:
        tape_files = sorted(TAPES_DIR.glob(f"Tape_{date}_R{race_number}_*.csv"))

    if not tape_files:
        raise RuntimeError("No tapes found for race")

    # --- finish detection + append-only finish cols
    for tp in tape_files:
        with open(tp, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []

            ts, la, lo = [], [], []
            for r in reader:
                ts.append(
                    datetime.fromisoformat(r["timestamp_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)
                )
                if "latitude_deg" in cols:
                    la.append(float(r["latitude_deg"]))
                    lo.append(float(r["longitude_deg"]))
                else:
                    la.append(float(r["latitude"]))
                    lo.append(float(r["longitude"]))

        ft = first_crossing_time(ts, la, lo, finishS, finishP)

        if ft is None:
            append_finish_cols(tp, "", -1, 0)
        else:
            start_utc = ts[0]
            elapsed_s = int(round((ft - start_utc).total_seconds()))
            append_finish_cols(tp, ft.isoformat(), elapsed_s, 1)

    # --- pipeline step: distance truth then motion truth (raw) appended to the same tapes
    run_truth_distance_and_motion_raw_on_files(tape_files)

    # --- pipeline step: HR truth append (raw + filled + flag)
    if not args.skip_hr:
        if not trimmed_dir.is_dir():
            raise RuntimeError(f"trimmed_dir not found: {trimmed_dir}")
        for tp in tape_files:
            append_hr_cols_from_trimmed(tp, trimmed_dir, date, race_number, group)

    print("TapeFinishFinder completed")


if __name__ == "__main__":
    main()
