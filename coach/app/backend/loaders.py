#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


# -----------------------------
# Paths (anchored, no CWD reliance)
# -----------------------------
# coach/app/backend/loaders.py -> parents[3] == SailAnalytics/
BASE_DIR = Path(__file__).resolve().parents[3]
TOTALRACES_DIR = BASE_DIR / "data" / "totalraces"

# Roster colors can live in either:
#   - data/roster/RosterColors.csv   (your current tree)
#   - data/RosterColors.csv          (legacy fallback)
ROSTER_COLORS_PATH_PRIMARY = BASE_DIR / "data" / "roster" / "RosterColors.csv"
ROSTER_COLORS_PATH_FALLBACK = BASE_DIR / "data" / "RosterColors.csv"


# -----------------------------
# Roster colors (presentation layer)
# -----------------------------
_ROSTER_CACHE: Optional[Dict[str, str]] = None
_HEX_RX = re.compile(r"^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def roster_colors() -> Dict[str, str]:
    """
    Load stable per-sailor colors from RosterColors.csv.

    Expected columns:
      - name, color
    Example rows:
      yalcin,#ff0000

    Returns: { "yalcin": "#ff0000", ... }
    Caches after first read (restart server to pick up edits).
    """
    global _ROSTER_CACHE
    if _ROSTER_CACHE is not None:
        return _ROSTER_CACHE

    out: Dict[str, str] = {}

    path = None
    if ROSTER_COLORS_PATH_PRIMARY.exists():
        path = ROSTER_COLORS_PATH_PRIMARY
    elif ROSTER_COLORS_PATH_FALLBACK.exists():
        path = ROSTER_COLORS_PATH_FALLBACK

    if path is None:
        _ROSTER_CACHE = out
        return out

    try:
        df = pd.read_csv(path)
    except Exception:
        _ROSTER_CACHE = out
        return out

    cols_lc = {c.lower(): c for c in df.columns}
    name_col = cols_lc.get("name") or cols_lc.get("sailor") or cols_lc.get("sailor_name")
    color_col = cols_lc.get("color") or cols_lc.get("hex") or cols_lc.get("colour")

    if not name_col or not color_col:
        _ROSTER_CACHE = out
        return out

    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip().lower()
        color = str(row.get(color_col, "")).strip()
        if not name or not color:
            continue
        if _HEX_RX.match(color):
            out[name] = color.lower()

    _ROSTER_CACHE = out
    return out


# -----------------------------
# Filename parsing
# -----------------------------
# Expected: <sailor>_<race_date>_R<race_number>_<fleet>.csv
# Example: william_301125_R1_yellow.csv
_RX = re.compile(
    r"^(?P<sailor>[a-z0-9]+)_(?P<date>\d{6})_R(?P<rn>\d+)_(?P<fleet>[a-z0-9]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RaceGroup:
    group_id: str              # 301125_R1_yellow
    race_date: str             # 301125
    race_number: int           # 1
    fleet: str                 # yellow
    files: Tuple[Path, ...]    # per-sailor CSVs


def _parse_stem(stem: str) -> Optional[Tuple[str, str, int, str]]:
    m = _RX.match(stem)
    if not m:
        return None
    sailor = m.group("sailor")
    race_date = m.group("date")
    race_number = int(m.group("rn"))
    fleet = m.group("fleet")
    return sailor, race_date, race_number, fleet


def list_race_groups() -> Dict[str, RaceGroup]:
    """
    Groups per-sailor TotalRaces CSVs into race-groups keyed by:
      <race_date>_R<race_number>_<fleet>
    """
    groups: Dict[str, List[Path]] = {}
    meta: Dict[str, Tuple[str, int, str]] = {}

    if not TOTALRACES_DIR.exists():
        return {}

    for p in TOTALRACES_DIR.glob("*.csv"):
        parsed = _parse_stem(p.stem)
        if not parsed:
            continue
        sailor, race_date, rn, fleet = parsed
        gid = f"{race_date}_R{rn}_{fleet}"
        groups.setdefault(gid, []).append(p)
        meta[gid] = (race_date, rn, fleet)

    out: Dict[str, RaceGroup] = {}
    for gid, files in groups.items():
        race_date, rn, fleet = meta[gid]
        out[gid] = RaceGroup(
            group_id=gid,
            race_date=race_date,
            race_number=rn,
            fleet=fleet,
            files=tuple(sorted(files)),
        )
    return out


def list_race_groups_public() -> List[dict]:
    """
    Returns a list of objects for the frontend Race dropdown.
    """
    groups = list_race_groups()
    items = []
    for gid in sorted(groups.keys()):
        g = groups[gid]
        label = f"{g.race_date} | Race {g.race_number} | Fleet {g.fleet}"
        items.append(
            {
                "id": g.group_id,
                "label": label,
                "date": g.race_date,
                "race_number": g.race_number,
                "fleet": g.fleet,
            }
        )
    return items


def sailors_in_group(group_id: str) -> List[str]:
    g = list_race_groups().get(group_id)
    if not g:
        return []
    sailors = []
    for p in g.files:
        parsed = _parse_stem(p.stem)
        if parsed:
            sailor, _, _, _ = parsed
            sailors.append(sailor)
    return sorted(set(sailors))


def _detect_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None


def load_group_df(group_id: str, sailors: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Loads and concatenates per-sailor CSVs for the selected group.
    Adds/normalizes columns needed by the API:
      - sailor_name
      - leg_instance_id  (normalized from geom_leg_id)
      - t               (time index)
    """
    groups = list_race_groups()
    g = groups.get(group_id)
    if not g:
        return pd.DataFrame()

    # Filter files by sailor selection
    keep_files = []
    for p in g.files:
        parsed = _parse_stem(p.stem)
        if not parsed:
            continue
        sailor, _, _, _ = parsed
        if (not sailors) or (sailor in sailors):
            keep_files.append(p)

    frames = []
    for p in keep_files:
        parsed = _parse_stem(p.stem)
        if not parsed:
            continue
        sailor, _, _, _ = parsed

        df = pd.read_csv(p)

        # ensure sailor_name
        if "sailor_name" not in df.columns:
            df["sailor_name"] = sailor
        else:
            df["sailor_name"] = df["sailor_name"].fillna(sailor)

        frames.append(df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Normalize time index -> t
    t_col = _detect_col(df, ["t", "timestamp_utc", "timestamp", "time_s", "sample_idx"])
    if t_col is None:
        df["t"] = range(len(df))
    else:
        df["t"] = df[t_col]

    # Normalize legs -> leg_instance_id (source column is geom_leg_id in your files)
    leg_col = _detect_col(df, ["geom_leg_id", "leg_instance_id", "leg", "leg_id"])
    if leg_col is None:
        df["leg_instance_id"] = None
    else:
        df["leg_instance_id"] = df[leg_col]

    return df


def legs_in_df(df: pd.DataFrame) -> List[int]:
    if df is None or df.empty or "leg_instance_id" not in df.columns:
        return []
    vals = pd.to_numeric(df["leg_instance_id"], errors="coerce").dropna().astype(int).unique().tolist()
    return sorted(vals)
