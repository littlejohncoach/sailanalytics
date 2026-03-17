#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AddGeometryToTape.py
--------------------------------------------------
Stage: Geometry Enrichment (pre-Analytics outputs)

Reads 1 Hz truth tapes and writes a geometry-enriched copy WITHOUT
modifying the original tape.

UI (UPDATED):
- Select ONE OR MORE races from data/racetimes/RaceTimes.csv
- Display: <date>  R<race_number>  <group_color>
- Multi-select: Cmd-click (toggle) / Shift-click (range) on Mac

Inputs (read-only):
- data/tapes/*_<date>_R<race_number>_<group_color>.csv
- data/geometry/geometry_<date>_R<race_number>_<group_color>.csv

OUTPUT (LOCKED BY USER):
- data/totalraces/<same filename>.csv

Adds per-row geometry columns:
- geom_leg_id
- geom_from_mark
- geom_to_mark
- geom_leg_bearing_deg
- target_lat_deg
- target_lon_deg
- dist_to_target_m           (int meters)   [distance to target midpoint/mark]
- bearing_to_target_deg      (int degrees 0–359) [bearing to target midpoint/mark]

Adds motion truth field + ATB outputs (whole numbers):
- COG_deg                    (smoothed, int 0–359)   [KEEPS COG_raw_deg]
- ATB_angle_deg              (int 0–180)
- ATB_offset_deg             (int, upwind only; ATB_angle_deg - 38)

COG smoothing:
- Distance-window smoothing ±10 m along-track using vector average of COG_raw_deg.

ATB:
- Uses COG_deg and bearing_to_target_deg.
- Upwind rows are those where geom_to_mark in {"1","3"}  (legacy rule kept as-is)

Leg transitions (adaptive radius, EARLIEST-ARRIVAL RULE):
- For a target mark, compute the first index within each radius in [1,5,10,15].
- Choose the EARLIEST index among those hits (time-first).
- Record the SMALLEST radius that achieves that earliest index.
- If no hit within 15m, leg ends at last sample (mark miss)

Gate-aware arrival (UPDATED):
- If geometry row has to_is_gate==1 and provides both gate endpoints (S and P),
  then arrival distance is min(dist_to_S, dist_to_P) instead of distance to midpoint.

No PTM / progress calculations.
--------------------------------------------------
"""

from __future__ import annotations

import csv
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import numpy as np
import pandas as pd


# --------------------------------------------------
# PATHS (LOCKED)
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[1]  # .../SailAnalytics
DATA_DIR = BASE_DIR / "data"

TAPES_DIR = DATA_DIR / "tapes"
GEOM_DIR = DATA_DIR / "geometry"
OUT_DIR = DATA_DIR / "totalraces"   # <-- LOCKED OUTPUT DESTINATION
RACETIMES_PATH = DATA_DIR / "racetimes" / "RaceTimes.csv"

ARRIVAL_RADIUS_LADDER_M = [1.0, 5.0, 10.0, 15.0]

COG_SMOOTH_WINDOW_M = 10.0  # ±10 m along track
EARTH_R_M = 6371000.0


# --------------------------------------------------
# ATOMIC WRITE
# --------------------------------------------------
def atomic_write_csv(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(out_path)


# --------------------------------------------------
# GEO (vectorized)
# --------------------------------------------------
def haversine_m_vec(lat1_deg, lon1_deg, lat2_deg, lon2_deg) -> np.ndarray:
    lat1 = np.radians(lat1_deg)
    lon1 = np.radians(lon1_deg)
    lat2 = np.radians(lat2_deg)
    lon2 = np.radians(lon2_deg)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return EARTH_R_M * c


def bearing_deg_vec(lat1_deg, lon1_deg, lat2_deg, lon2_deg) -> np.ndarray:
    lat1 = np.radians(lat1_deg)
    lat2 = np.radians(lat2_deg)
    dlon = np.radians(lon2_deg - lon1_deg)

    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    ang = np.degrees(np.arctan2(y, x))
    ang = np.where(ang < 0, ang + 360.0, ang)
    return ang


def compute_raw_cog_from_latlon(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """
    Raw COG from consecutive GPS points (deg 0–360).
    For last sample: copy previous.
    """
    n = len(lat)
    if n < 2:
        return np.zeros(n, dtype=float)

    lat1 = lat[:-1]
    lon1 = lon[:-1]
    lat2 = lat[1:]
    lon2 = lon[1:]

    cog = bearing_deg_vec(lat1, lon1, lat2, lon2).astype(float)
    cog = np.concatenate([cog, np.array([cog[-1]], dtype=float)])
    return cog


# --------------------------------------------------
# COG SMOOTHING (±10 m DISTANCE WINDOW, VECTOR AVG)
# --------------------------------------------------
def smooth_cog_distance_window(cog_raw_deg: np.ndarray, dist_from_start_m: np.ndarray, window_m: float) -> np.ndarray:
    """
    Distance-window smoothing ±window_m using vector average on unit circle.
    Returns float degrees [0,360).
    """
    n = len(cog_raw_deg)
    if n == 0:
        return cog_raw_deg

    rad = np.radians(cog_raw_deg.astype(float))
    sinv = np.sin(rad)
    cosv = np.cos(rad)

    d = dist_from_start_m.astype(float)
    if np.any(np.diff(d) < -1e-6):
        raise ValueError("dist_from_start_m must be non-decreasing for distance-window smoothing.")

    out = np.zeros(n, dtype=float)

    left = 0
    right = -1
    sum_sin = 0.0
    sum_cos = 0.0

    for i in range(n):
        while (right + 1) < n and (d[right + 1] - d[i]) <= window_m:
            right += 1
            sum_sin += sinv[right]
            sum_cos += cosv[right]

        while left < n and (d[i] - d[left]) > window_m:
            sum_sin -= sinv[left]
            sum_cos -= cosv[left]
            left += 1

        ang = np.degrees(np.arctan2(sum_sin, sum_cos))
        if ang < 0:
            ang += 360.0
        out[i] = ang

    return out


# --------------------------------------------------
# UI: select race(s) (STRICT)
# --------------------------------------------------
def select_races() -> list[dict] | None:
    if not RACETIMES_PATH.exists():
        messagebox.showerror("Error", f"Missing: {RACETIMES_PATH}")
        return None

    with open(RACETIMES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    required = ["date", "race_number", "group_color"]
    missing = [c for c in required if c not in fieldnames]
    if missing:
        messagebox.showerror(
            "Error",
            "RaceTimes.csv missing required columns:\n"
            + ", ".join(missing)
            + "\n\nRequired exactly:\n"
            + ", ".join(required),
        )
        return None

    if not rows:
        messagebox.showerror("Error", "RaceTimes.csv is empty.")
        return None

    display = []
    for r in rows:
        d = str(r["date"]).strip()
        rn = str(r["race_number"]).strip()
        gc = str(r["group_color"]).strip()
        display.append(f"{d}  R{rn}  {gc}")

    win = tk.Toplevel()
    win.title("Add Geometry — Select Race(s)")
    win.geometry("640x420")

    tk.Label(win, text="Select one or more races (Cmd/Shift-click):", font=("Arial", 14)).pack(pady=10)

    frame = tk.Frame(win)
    frame.pack(fill="both", expand=True, padx=12, pady=8)

    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")

    # UPDATED: multi-select listbox
    lb = tk.Listbox(frame, yscrollcommand=scrollbar.set, font=("Menlo", 13), selectmode="extended")
    for item in display:
        lb.insert("end", item)
    lb.pack(side="left", fill="both", expand=True)

    scrollbar.config(command=lb.yview)

    result = {"rows": None}

    def on_ok():
        sel = lb.curselection()
        if not sel:
            messagebox.showwarning("Select race(s)", "Please select one or more races.")
            return
        result["rows"] = [rows[i] for i in sel]
        win.destroy()

    def on_cancel():
        result["rows"] = None
        win.destroy()

    btns = tk.Frame(win)
    btns.pack(pady=10)
    tk.Button(btns, text="OK", width=12, command=on_ok).pack(side="left", padx=8)
    tk.Button(btns, text="Cancel", width=12, command=on_cancel).pack(side="left", padx=8)

    win.grab_set()
    win.wait_window()
    return result["rows"]


# --------------------------------------------------
# LOAD GEOMETRY (STRICT + GATE-OPTIONAL)
# --------------------------------------------------
def load_geometry(date: str, race_number: str, group_color: str) -> pd.DataFrame:
    geom_path = GEOM_DIR / f"geometry_{date}_R{race_number}_{group_color}.csv"
    if not geom_path.exists():
        raise FileNotFoundError(f"Missing geometry file: {geom_path}")

    g = pd.read_csv(geom_path)

    required = ["leg_id", "from_mark", "to_mark", "to_lat_deg", "to_lon_deg", "bearing_deg"]
    missing = [c for c in required if c not in g.columns]
    if missing:
        raise ValueError(f"Geometry CSV missing columns: {', '.join(missing)}")

    # Gate columns optional for backward compatibility
    if "to_is_gate" not in g.columns:
        g["to_is_gate"] = 0
    for c in ("to_gate_s_lat_deg", "to_gate_s_lon_deg", "to_gate_p_lat_deg", "to_gate_p_lon_deg"):
        if c not in g.columns:
            g[c] = np.nan

    g = g.sort_values("leg_id").reset_index(drop=True)
    return g


# --------------------------------------------------
# ARRIVAL SEARCH (EARLIEST INDEX OVERALL)
# --------------------------------------------------
def _earliest_hit_from_distance_series(d: np.ndarray, start_idx: int) -> tuple[int | None, float | None]:
    hits: list[tuple[int, float]] = []
    for r in ARRIVAL_RADIUS_LADDER_M:
        idxs = np.where(d <= r)[0]
        if idxs.size > 0:
            hits.append((start_idx + int(idxs[0]), float(r)))

    if not hits:
        return None, None

    earliest_idx = min(i for i, _ in hits)
    smallest_r = min(r for i, r in hits if i == earliest_idx)
    return earliest_idx, smallest_r


def find_arrival_index_point(
    lat: np.ndarray,
    lon: np.ndarray,
    start_idx: int,
    tlat: float,
    tlon: float,
) -> tuple[int | None, float | None]:
    n = len(lat)
    if start_idx >= n:
        return None, None
    d = haversine_m_vec(lat[start_idx:], lon[start_idx:], tlat, tlon)
    return _earliest_hit_from_distance_series(d, start_idx)


def find_arrival_index_gate_min_sp(
    lat: np.ndarray,
    lon: np.ndarray,
    start_idx: int,
    slat: float,
    slon: float,
    plat: float,
    plon: float,
) -> tuple[int | None, float | None]:
    n = len(lat)
    if start_idx >= n:
        return None, None
    dS = haversine_m_vec(lat[start_idx:], lon[start_idx:], slat, slon)
    dP = haversine_m_vec(lat[start_idx:], lon[start_idx:], plat, plon)
    d = np.minimum(dS, dP)
    return _earliest_hit_from_distance_series(d, start_idx)


# --------------------------------------------------
# ATB
# --------------------------------------------------
def angular_diff_deg(a_deg: np.ndarray, b_deg: np.ndarray) -> np.ndarray:
    """
    Smallest absolute angular difference between headings a and b in degrees.
    Returns [0,180].
    """
    d = (a_deg - b_deg + 180.0) % 360.0 - 180.0
    return np.abs(d)


# --------------------------------------------------
# CORE
# --------------------------------------------------
def enrich_tape_with_geometry(tape_path: Path, geom: pd.DataFrame) -> tuple[Path, list[str]]:
    df = pd.read_csv(tape_path)
    if df.empty:
        raise ValueError(f"{tape_path.name}: tape is empty")

    for c in ("timestamp_utc", "latitude", "longitude"):
        if c not in df.columns:
            raise ValueError(f"{tape_path.name}: missing required column '{c}'")

    if "dist_from_start_m" not in df.columns:
        if "seg_dist_m" not in df.columns:
            raise ValueError(f"{tape_path.name}: missing dist_from_start_m and seg_dist_m (need one to build distance axis)")
        seg = pd.to_numeric(df["seg_dist_m"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        df["dist_from_start_m"] = np.cumsum(seg)

    df["__ts"] = pd.to_datetime(df["timestamp_utc"], errors="raise")
    df = df.sort_values("__ts").reset_index(drop=True)

    lat = pd.to_numeric(df["latitude"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["longitude"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(lat).any() or np.isnan(lon).any():
        raise ValueError(f"{tape_path.name}: latitude/longitude contains NaN")

    dist_axis = pd.to_numeric(df["dist_from_start_m"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(dist_axis).any():
        raise ValueError(f"{tape_path.name}: dist_from_start_m contains NaN")

    n = len(df)

    geom_leg_id = np.zeros(n, dtype=int)
    geom_from_mark = np.array([""] * n, dtype=object)
    geom_to_mark = np.array([""] * n, dtype=object)
    geom_leg_bearing_deg = np.zeros(n, dtype=int)
    target_lat = np.zeros(n, dtype=float)
    target_lon = np.zeros(n, dtype=float)

    notes: list[str] = []
    start_idx = 0

    for _, lg in geom.iterrows():
        if start_idx >= n:
            break

        leg_id = int(lg["leg_id"])
        from_mark = str(lg["from_mark"])
        to_mark = str(lg["to_mark"])
        leg_bearing = int(round(float(lg["bearing_deg"]))) % 360

        # target midpoint/mark
        tlat = float(lg["to_lat_deg"])
        tlon = float(lg["to_lon_deg"])

        # gate-aware arrival
        to_is_gate = int(pd.to_numeric(lg.get("to_is_gate", 0), errors="coerce") or 0)

        used_gate = False
        end_idx = None
        used_r = None

        if to_is_gate == 1:
            slat = pd.to_numeric(lg.get("to_gate_s_lat_deg", np.nan), errors="coerce")
            slon = pd.to_numeric(lg.get("to_gate_s_lon_deg", np.nan), errors="coerce")
            plat = pd.to_numeric(lg.get("to_gate_p_lat_deg", np.nan), errors="coerce")
            plon = pd.to_numeric(lg.get("to_gate_p_lon_deg", np.nan), errors="coerce")

            if not (np.isnan(slat) or np.isnan(slon) or np.isnan(plat) or np.isnan(plon)):
                end_idx, used_r = find_arrival_index_gate_min_sp(
                    lat, lon, start_idx,
                    float(slat), float(slon),
                    float(plat), float(plon),
                )
                used_gate = True

        if end_idx is None:
            end_idx, used_r = find_arrival_index_point(lat, lon, start_idx, tlat, tlon)
            used_gate = False

        if end_idx is None:
            end_idx = n - 1
            notes.append(
                f"{tape_path.name}: leg {leg_id} to '{to_mark}' never within {ARRIVAL_RADIUS_LADDER_M[-1]:.0f} m (mark miss)."
            )
        else:
            src = "GATE(min(S,P))" if used_gate else "POINT"
            notes.append(
                f"{tape_path.name}: leg {leg_id} to '{to_mark}' arrival at idx={end_idx} using radius {used_r:.0f} m ({src})."
            )

        geom_leg_id[start_idx : end_idx + 1] = leg_id
        geom_from_mark[start_idx : end_idx + 1] = from_mark
        geom_to_mark[start_idx : end_idx + 1] = to_mark
        geom_leg_bearing_deg[start_idx : end_idx + 1] = leg_bearing
        target_lat[start_idx : end_idx + 1] = tlat
        target_lon[start_idx : end_idx + 1] = tlon

        start_idx = end_idx + 1

    if (geom_leg_id == 0).any():
        last = int(np.max(geom_leg_id))
        if last == 0:
            raise ValueError(f"{tape_path.name}: geometry could not be applied (no leg assigned).")
        mask = geom_leg_id == 0
        geom_leg_id[mask] = last
        last_idx = np.where(~mask)[0][-1]
        geom_from_mark[mask] = geom_from_mark[last_idx]
        geom_to_mark[mask] = geom_to_mark[last_idx]
        geom_leg_bearing_deg[mask] = geom_leg_bearing_deg[last_idx]
        target_lat[mask] = target_lat[last_idx]
        target_lon[mask] = target_lon[last_idx]
        notes.append(f"{tape_path.name}: trailing rows assigned to last leg {last} (geometry shorter than tape).")

    dist_to_target = haversine_m_vec(lat, lon, target_lat, target_lon)
    bear_to_target = bearing_deg_vec(lat, lon, target_lat, target_lon)

    # ---------------------------
    # COG TruthField (KEEP COG_raw_deg)
    # ---------------------------
    if "COG_raw_deg" in df.columns:
        cog_raw = pd.to_numeric(df["COG_raw_deg"], errors="coerce").to_numpy(dtype=float)
        if np.isnan(cog_raw).any():
            cog_fallback = compute_raw_cog_from_latlon(lat, lon)
            mask = np.isnan(cog_raw)
            cog_raw[mask] = cog_fallback[mask]
    else:
        cog_raw = compute_raw_cog_from_latlon(lat, lon)
        df["COG_raw_deg"] = np.rint(cog_raw).astype(int) % 360

    cog_smooth = smooth_cog_distance_window(
        cog_raw_deg=cog_raw,
        dist_from_start_m=dist_axis,
        window_m=COG_SMOOTH_WINDOW_M
    )
    cog_deg = (np.rint(cog_smooth).astype(int) % 360)

    # ---------------------------
    # ATB outputs (whole numbers)
    # ---------------------------
    bearing_to_target_deg = (np.rint(bear_to_target).astype(int) % 360).astype(int)
    atb_angle = angular_diff_deg(cog_deg.astype(float), bearing_to_target_deg.astype(float))
    atb_angle_deg = np.rint(atb_angle).astype(int)

    # legacy upwind rule retained
    is_upwind = np.isin(geom_to_mark.astype(str), np.array(["1", "3"], dtype=object))
    atb_offset = np.full(n, pd.NA, dtype=object)
    atb_offset_vals = (atb_angle_deg - 38).astype(int)
    atb_offset[is_upwind] = atb_offset_vals[is_upwind]

    # append columns
    df = df.drop(columns="__ts")
    df["geom_leg_id"] = geom_leg_id.astype(int)
    df["geom_from_mark"] = geom_from_mark
    df["geom_to_mark"] = geom_to_mark
    df["geom_leg_bearing_deg"] = geom_leg_bearing_deg.astype(int)
    df["target_lat_deg"] = target_lat.astype(float)
    df["target_lon_deg"] = target_lon.astype(float)
    df["dist_to_target_m"] = np.rint(dist_to_target).astype(int)
    df["bearing_to_target_deg"] = bearing_to_target_deg.astype(int)

    df["COG_deg"] = cog_deg.astype(int)
    df["ATB_angle_deg"] = atb_angle_deg.astype(int)
    df["ATB_offset_deg"] = pd.array(atb_offset, dtype="Int64")

    out_path = OUT_DIR / tape_path.name
    atomic_write_csv(df, out_path)
    return out_path, notes


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main() -> None:
    root = tk.Tk()
    root.withdraw()

    try:
        sels = select_races()
        if not sels:
            return

        all_notes: list[str] = []
        total_outputs = 0
        skipped_patterns = 0

        for sel in sels:
            date = str(sel["date"]).strip()
            race_number = str(sel["race_number"]).strip()
            group_color = str(sel["group_color"]).strip()

            geom = load_geometry(date, race_number, group_color)

            pattern = f"*_{date}_R{race_number}_{group_color}.csv"
            tapes = sorted(TAPES_DIR.glob(pattern))
            if not tapes:
                all_notes.append(f"(skip) No tapes found: data/tapes/{pattern}")
                skipped_patterns += 1
                continue

            for tape_path in tapes:
                _, notes = enrich_tape_with_geometry(tape_path, geom)
                all_notes.extend(notes)
                total_outputs += 1

        msg = f"Geometry + COG_deg + ATB added to {total_outputs} tape(s).\nOutput: data/totalraces/"
        if skipped_patterns:
            msg += f"\nSkipped race selections with no matching tapes: {skipped_patterns}"
        if all_notes:
            print("\n".join(all_notes))
            msg += "\n\nNotes (first 8):\n" + "\n".join(all_notes[:8])

        messagebox.showinfo("Done", msg)

    except Exception as e:
        messagebox.showerror("AddGeometryToTape.py error", str(e))


if __name__ == "__main__":
    main()