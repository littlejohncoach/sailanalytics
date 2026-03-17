#!/usr/bin/env python3
# TruthDistance.py — add seg_dist_m and dist_from_start_m to each tape CSV (per-sample truth)
# Canonical truth source: TAPES/ only (hard error if missing)
# Pipeline: after distance truth, run TruthMotionRaw.py on the same tapes.

import os
import glob
import argparse
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6371000.0  # meters
BASE_DIR = Path(__file__).resolve().parent


def haversine_m(lat1, lon1, lat2, lon2):
    """
    Vectorized haversine distance in meters.
    Inputs are numpy arrays in degrees.
    """
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * (np.sin(dlon / 2.0) ** 2)
    c = 2.0 * np.arcsin(np.sqrt(a))
    return EARTH_RADIUS_M * c


def find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def process_one_csv(path: str) -> None:
    df = pd.read_csv(path)

    # Deterministic ordering
    if "sample_idx" in df.columns:
        df = df.sort_values("sample_idx", kind="mergesort").reset_index(drop=True)

    lat_col = find_col(df, ["latitude_deg", "lat_deg", "latitude", "lat"])
    lon_col = find_col(df, ["longitude_deg", "lon_deg", "longitude", "lon"])

    if lat_col is None or lon_col is None:
        raise ValueError(
            f"{os.path.basename(path)}: could not find lat/lon columns. "
            f"Expected one of latitude_deg/lat_deg/latitude/lat and longitude_deg/lon_deg/longitude/lon."
        )

    lat = df[lat_col].to_numpy(dtype=float)
    lon = df[lon_col].to_numpy(dtype=float)

    n = len(df)
    seg = np.zeros(n, dtype=float)

    if n >= 2:
        d = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
        # Deterministic handling of missing/invalid points: segments become 0
        d = np.nan_to_num(d, nan=0.0, posinf=0.0, neginf=0.0)
        seg[1:] = d

    dist_from_start = np.cumsum(seg)

    # Store with compact rounding
    df["seg_dist_m"] = np.round(seg, 3)
    df["dist_from_start_m"] = np.round(dist_from_start, 3)

    # In-place write (atomic replace)
    tmp_path = path + ".tmp"
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, path)

    total = float(df["dist_from_start_m"].iloc[-1]) if n else 0.0
    print(f"OK  {os.path.basename(path)}  rows={n}  total_dist_m={total:.3f}")


# ---------------------------------------------------------
# PIPELINE HOOK: RUN TruthMotionRaw.py (IN-PROCESS, NO SHELL)
# ---------------------------------------------------------
def run_truth_motion_raw(paths):
    truthmotion_path = BASE_DIR / "TruthMotionRaw.py"
    if not truthmotion_path.exists():
        raise RuntimeError(f"TruthMotionRaw.py not found next to TruthDistance.py: {truthmotion_path}")

    spec = importlib.util.spec_from_file_location("TruthMotionRaw", str(truthmotion_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load TruthMotionRaw.py module spec")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore

    if not hasattr(mod, "process_one_csv"):
        raise RuntimeError("TruthMotionRaw.py must expose process_one_csv(path: str)")

    for p in paths:
        mod.process_one_csv(str(p))


def main():
    ap = argparse.ArgumentParser(description="Add seg_dist_m and dist_from_start_m to tape CSVs in TAPES/")
    ap.add_argument("--tapes_dir", default="TAPES", help="Directory containing Tape_*.csv (default: TAPES)")
    ap.add_argument("--pattern", default="Tape_*.csv", help="Glob pattern (default: Tape_*.csv)")
    args = ap.parse_args()

    tapes_dir = args.tapes_dir
    if not os.path.isdir(tapes_dir):
        raise SystemExit(f"ERROR: canonical TAPES dir not found: {tapes_dir}")

    paths = sorted(glob.glob(os.path.join(tapes_dir, args.pattern)))
    if not paths:
        raise SystemExit(f"ERROR: no files matched {os.path.join(tapes_dir, args.pattern)}")

    print(f"Using TAPES dir: {tapes_dir}")

    # Step 1: Distance truth
    for p in paths:
        process_one_csv(p)

    # Step 2: Motion truth (raw) on the same tapes
    run_truth_motion_raw(paths)

    print("DONE: TruthDistance + TruthMotionRaw applied to all matching tapes.")


if __name__ == "__main__":
    main()
