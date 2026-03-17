#!/usr/bin/env python3
# FitToReady.py
#
# PURPOSE
# -------
# Convert FIT / GPX tracks into READY CSVs with:
# - integer-second timestamps (LOCAL race clock)
# - deterministic ordering
# - gap filling to 1 Hz for gaps <= maxGap seconds
#
# NO analytics
# NO speed
# NO geometry
#
# Output columns:
#   timestamp_iso, unix_s, latitude_raw, longitude_raw, heart_rate

import os, sys, glob, argparse
import pandas as pd

# ---------------------------------------------------------------------
# Decoder capability checks
# ---------------------------------------------------------------------

def have_fitdecode():
    try:
        import fitdecode  # type: ignore
        return True
    except Exception:
        return False

def have_fitparse():
    try:
        import fitparse  # type: ignore
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------

def decode_fit(path):
    rows = []

    if have_fitdecode():
        try:
            import fitdecode  # type: ignore
            with fitdecode.FitReader(path) as fr:
                for frame in fr:
                    if frame.__class__.__name__ != "FitDataMessage":
                        continue
                    if frame.name != "record":
                        continue

                    data = {f.name: f.value for f in frame.fields}
                    ts = data.get("timestamp")
                    lat = data.get("position_lat")
                    lon = data.get("position_long")
                    hr  = data.get("heart_rate")

                    if ts is None or lat is None or lon is None:
                        continue

                    # Treat naive timestamps as LOCAL clock time
                    epoch = ts.timestamp()

                    def to_deg(v):
                        v = float(v)
                        return v * (180.0 / (2**31)) if abs(v) > 180 else v

                    rows.append({
                        "unix_s": epoch,
                        "latitude_raw": to_deg(lat),
                        "longitude_raw": to_deg(lon),
                        "heart_rate": float(hr) if hr is not None else None,
                    })
            return pd.DataFrame(rows)
        except Exception:
            pass

    if have_fitparse():
        try:
            from fitparse import FitFile  # type: ignore
            fit = FitFile(path, check_crc=False)
            fit.parse()
            for rec in fit.get_messages("record"):
                data = {d.name: d.value for d in rec}
                ts = data.get("timestamp")
                lat = data.get("position_lat")
                lon = data.get("position_long")
                hr  = data.get("heart_rate")

                if ts is None or lat is None or lon is None:
                    continue

                # Treat naive timestamps as LOCAL clock time
                epoch = ts.timestamp()

                def to_deg(v):
                    v = float(v)
                    return v * (180.0 / (2**31)) if abs(v) > 180 else v

                rows.append({
                    "unix_s": epoch,
                    "latitude_raw": to_deg(lat),
                    "longitude_raw": to_deg(lon),
                    "heart_rate": float(hr) if hr is not None else None,
                })
            return pd.DataFrame(rows)
        except Exception:
            pass

    return pd.DataFrame()

def decode_gpx(path):
    import xml.etree.ElementTree as ET
    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    tree = ET.parse(path)
    root = tree.getroot()

    rows = []
    for trkpt in root.findall(".//gpx:trkpt", ns):
        lat = float(trkpt.attrib.get("lat"))
        lon = float(trkpt.attrib.get("lon"))
        t_el = trkpt.find("gpx:time", ns)
        hr_el = trkpt.find(".//gpx:hr", ns) or trkpt.find(".//hr")

        if t_el is None:
            continue

        # GPX timestamps are already absolute; keep as-is
        ts = pd.to_datetime(t_el.text).timestamp()

        rows.append({
            "unix_s": ts,
            "latitude_raw": lat,
            "longitude_raw": lon,
            "heart_rate": float(hr_el.text) if hr_el is not None else None,
        })

    return pd.DataFrame(rows)

# ---------------------------------------------------------------------
# Time normalization + gap filling
# ---------------------------------------------------------------------

def normalize_seconds(df):
    df = df.dropna(subset=["unix_s", "latitude_raw", "longitude_raw"]).copy()
    if df.empty:
        return df

    df["unix_s"] = df["unix_s"].round().astype("int64")
    df = df.sort_values("unix_s").drop_duplicates("unix_s", keep="last")
    return df.reset_index(drop=True)

def expected_insertions(unix_s, max_gap):
    add = 0
    for dt in unix_s.diff().iloc[1:]:
        if 2 <= dt <= max_gap:
            add += dt - 1
    return int(add)

def fill_gaps(df, max_gap):
    rows = []

    for i in range(len(df) - 1):
        a = df.iloc[i]
        b = df.iloc[i + 1]

        ta, tb = int(a.unix_s), int(b.unix_s)
        dt = tb - ta

        rows.append(a.to_dict())

        if 2 <= dt <= max_gap:
            for t in range(ta + 1, tb):
                f = (t - ta) / dt
                rows.append({
                    "unix_s": t,
                    "latitude_raw": a.latitude_raw + f * (b.latitude_raw - a.latitude_raw),
                    "longitude_raw": a.longitude_raw + f * (b.longitude_raw - a.longitude_raw),
                    "heart_rate": (
                        int(round(a.heart_rate + f * (b.heart_rate - a.heart_rate)))
                        if pd.notna(a.heart_rate) and pd.notna(b.heart_rate)
                        else None
                    ),
                })

    rows.append(df.iloc[-1].to_dict())
    return pd.DataFrame(rows).sort_values("unix_s").reset_index(drop=True)

# ---------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------

def write_ready(df, out_path):
    # Write LOCAL race clock time (no UTC claim, no Z)
    df["timestamp_iso"] = pd.to_datetime(
        df["unix_s"], unit="s"
    ).dt.strftime("%Y-%m-%dT%H:%M:%S")

    df[[
        "timestamp_iso",
        "unix_s",
        "latitude_raw",
        "longitude_raw",
        "heart_rate"
    ]].to_csv(out_path, index=False)

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", required=True, dest="in_dir")
    ap.add_argument("--out", required=True, dest="out_dir")
    ap.add_argument("--maxgap", type=int, default=12)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    inputs = (
        glob.glob(os.path.join(args.in_dir, "*.FIT")) +
        glob.glob(os.path.join(args.in_dir, "*.fit")) +
        glob.glob(os.path.join(args.in_dir, "*.gpx"))
    )

    for path in sorted(inputs):
        name = os.path.splitext(os.path.basename(path))[0]
        out_csv = os.path.join(args.out_dir, f"{name}_ready.csv")

        if path.lower().endswith(".gpx"):
            df = decode_gpx(path)
        else:
            df = decode_fit(path)

        df = normalize_seconds(df)
        must_add = expected_insertions(df.unix_s, args.maxgap)
        df2 = fill_gaps(df, args.maxgap)

        if len(df2) != len(df) + must_add:
            raise RuntimeError(
                f"[ASSERT FAIL] {name}: expected {len(df) + must_add} rows, got {len(df2)}"
            )

        write_ready(df2, out_csv)
        print(f"[OK] {name}: rows {len(df)} → {len(df2)} (filled {must_add})")

if __name__ == "__main__":
    main()
