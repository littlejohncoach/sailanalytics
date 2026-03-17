#!/usr/bin/env python3
# TruthMotionRaw.py — add raw SOG (m/min) and raw COG (deg) to each tape CSV
# Canonical source: data/tapes/ only. Append-only (hard error if columns already exist).
#
# IMPORTANT:
# - Must remain callable as: process_one_csv(path: str)
# - Extra args exist only for backward/forward compatibility with any callers;
#   they are ignored here (HR is handled elsewhere in the pipeline).

import os
import glob
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone


def parse_ts_utc(s: str) -> datetime:
    # Accept "Z" or "+00:00"
    s = str(s).strip()
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # Force UTC if somehow naive (shouldn't happen in tapes)
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def initial_bearing_deg(lat1_deg, lon1_deg, lat2_deg, lon2_deg):
    """
    Vectorized initial bearing (forward azimuth) from point 1 to point 2.
    Returns degrees in [0, 360).
    """
    lat1 = np.radians(lat1_deg)
    lon1 = np.radians(lon1_deg)
    lat2 = np.radians(lat2_deg)
    lon2 = np.radians(lon2_deg)

    dlon = lon2 - lon1

    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)

    theta = np.degrees(np.arctan2(x, y))
    return (theta + 360.0) % 360.0


def find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def process_one_csv(
    path: str,
    add_hr: bool = False,                 # ignored (HR handled elsewhere)
    trimmed_dir: str = "data/trimmed",     # ignored
    trimmed_pattern: str = "*trimmed*.csv",# ignored
    require_hr: bool = False,             # ignored
) -> None:
    df = pd.read_csv(path)

    # Deterministic ordering
    if "sample_idx" in df.columns:
        df = df.sort_values("sample_idx", kind="mergesort").reset_index(drop=True)

    # Append-only law (hard error if present)
    for c in ("SOG_raw_mpm", "COG_raw_deg"):
        if c in df.columns:
            raise RuntimeError(f"{os.path.basename(path)}: column exists (sacrosanct): {c}")

    # Required columns
    if "timestamp_utc" not in df.columns:
        raise RuntimeError(f"{os.path.basename(path)}: missing timestamp_utc")

    if "seg_dist_m" not in df.columns:
        raise RuntimeError(f"{os.path.basename(path)}: missing seg_dist_m (run TruthDistance first)")

    lat_col = find_col(df, ["latitude_deg", "lat_deg", "latitude", "lat"])
    lon_col = find_col(df, ["longitude_deg", "lon_deg", "longitude", "lon"])
    if lat_col is None or lon_col is None:
        raise RuntimeError(f"{os.path.basename(path)}: missing latitude/longitude columns")

    # Parse timestamps
    ts = [parse_ts_utc(x) for x in df["timestamp_utc"].tolist()]
    n = len(ts)

    # dt seconds (first row dt = 0)
    dt_s = np.zeros(n, dtype=float)
    for i in range(1, n):
        dt_s[i] = (ts[i] - ts[i - 1]).total_seconds()

    # Raw SOG in m/min from seg_dist_m and dt
    seg = df["seg_dist_m"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        sog_raw_mpm = np.where(dt_s > 0.0, (seg / dt_s) * 60.0, 0.0)
    sog_raw_mpm = np.nan_to_num(sog_raw_mpm, nan=0.0, posinf=0.0, neginf=0.0)

    # Raw COG (bearing) between consecutive points (first row = 0)
    lat = df[lat_col].to_numpy(dtype=float)
    lon = df[lon_col].to_numpy(dtype=float)

    cog_raw_deg = np.zeros(n, dtype=float)
    if n >= 2:
        b = initial_bearing_deg(lat[:-1], lon[:-1], lat[1:], lon[1:])
        b = np.nan_to_num(b, nan=0.0, posinf=0.0, neginf=0.0)
        cog_raw_deg[1:] = b

    # Write new columns (raw only; no smoothing)
    df["SOG_raw_mpm"] = np.round(sog_raw_mpm, 3)
    df["COG_raw_deg"] = np.round(cog_raw_deg, 3)

    # Atomic in-place replace
    tmp_path = path + ".tmp"
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, path)

    print(f"OK  {os.path.basename(path)}  rows={n}")


def main():
    ap = argparse.ArgumentParser(description="Append raw SOG_raw_mpm and COG_raw_deg to tapes in data/tapes/")
    ap.add_argument("--tapes_dir", default="data/tapes", help="Directory containing Tape_*.csv (default: data/tapes)")
    ap.add_argument("--pattern", default="Tape_*.csv", help="Glob pattern (default: Tape_*.csv)")
    args = ap.parse_args()

    tapes_dir = args.tapes_dir
    if not os.path.isdir(tapes_dir):
        raise SystemExit(f"ERROR: canonical tapes_dir not found: {tapes_dir}")

    paths = sorted(glob.glob(os.path.join(tapes_dir, args.pattern)))
    if not paths:
        raise SystemExit(f"ERROR: no files matched {os.path.join(tapes_dir, args.pattern)}")

    for p in paths:
        process_one_csv(p)

    print("DONE: TruthMotionRaw applied to all matching tapes.")


if __name__ == "__main__":
    main()
