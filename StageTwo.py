#!/usr/bin/env python3
# StageTwo.py — marks → geometry → metadata → viewer

import argparse
import os
import sys
import subprocess
import webbrowser
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import urllib.parse
import csv
from pathlib import Path


def fail(msg):
    print(f"[STAGE 2 ERROR] {msg}")
    sys.exit(1)


# -----------------------------------------------------
# Check if metadata exists
# -----------------------------------------------------
def metadata_exists(metadata_file, race_id):

    if not metadata_file.exists():
        return False

    with open(metadata_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for r in reader:
            if r.get("race_id") == race_id:
                return True

    return False


# -----------------------------------------------------
# Load autocomplete values
# -----------------------------------------------------
def load_existing_values(metadata_file, field):

    values = set()

    if not metadata_file.exists():
        return []

    with open(metadata_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for r in reader:
            v = r.get(field)
            if v:
                values.add(v.strip())

    return sorted(values)


# -----------------------------------------------------
# Autocomplete dialog
# -----------------------------------------------------
def autocomplete_dialog(root, title, prompt, options):

    value = simpledialog.askstring(title, prompt, parent=root)

    if not value:
        return ""

    value = value.strip()

    matches = [o for o in options if o.lower().startswith(value.lower())]

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        messagebox.showinfo("Suggestions", "\n".join(matches))

    return value


# -----------------------------------------------------
# Wind direction from geometry
# -----------------------------------------------------
def read_wind_dir_from_geometry(geometry_file):

    with open(geometry_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        first = next(reader)

        return int(float(first["bearing_deg"]))


# -----------------------------------------------------
# Write metadata safely
# -----------------------------------------------------
def append_metadata(metadata_file, row):

    fields = [
        "race_id",
        "date",
        "race_number",
        "fleet",
        "venue",
        "event",
        "wind_dir_deg",
        "wind_knots",
        "sea_state",
        "wind_type"
    ]

    write_header = not metadata_file.exists()

    with open(metadata_file, "a", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
            lineterminator="\n"
        )

        if write_header:
            writer.writeheader()

        writer.writerow(row)


# -----------------------------------------------------
# MAIN
# -----------------------------------------------------
def main():

    ap = argparse.ArgumentParser()

    ap.add_argument("--date", required=True)
    ap.add_argument("--race", required=True)
    ap.add_argument("--group", required=True)
    ap.add_argument("--port", required=True)

    args = ap.parse_args()

    date  = args.date.strip()
    race  = args.race.strip()
    group = args.group.strip().lower()
    port  = args.port.strip()

    race_id = f"{date}_R{race}_{group}"

    base_dir = Path(__file__).resolve().parent

    marks_dir = base_dir / "data" / "marks"
    geometry_dir = base_dir / "data" / "geometry"
    trimmed_dir = base_dir / "data" / "trimmed"
    metadata_dir = base_dir / "data" / "race_metadata"

    geometry_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    metadata_file = metadata_dir / "race_metadata.csv"

    root = tk.Tk()
    root.withdraw()

    # -------------------------------------------------
    # Select marks file
    # -------------------------------------------------

    marks_path = filedialog.askopenfilename(
        title="Select Marks File",
        initialdir=marks_dir,
        filetypes=[("Marks", "*.csv *.json"), ("All", "*.*")]
    )

    if not marks_path:
        fail("No marks file selected.")

    # -------------------------------------------------
    # Build geometry
    # -------------------------------------------------

    geometry_file = geometry_dir / f"geometry_{race_id}.csv"

    geometry_script = base_dir / "geometry.py"

    subprocess.run(
        [
            sys.executable,
            geometry_script,
            "--marks",
            marks_path,
            "--out",
            geometry_file
        ],
        check=True
    )

    if not geometry_file.exists():
        fail("Geometry file not created.")

    # -------------------------------------------------
    # Wind direction from leg 1
    # -------------------------------------------------

    wind_dir_deg = read_wind_dir_from_geometry(geometry_file)

    # -------------------------------------------------
    # Metadata logic
    # -------------------------------------------------

    if metadata_exists(metadata_file, race_id):

        print(f"[STAGE 2] Metadata already exists for {race_id} — skipping dialog.")

    else:

        venues = load_existing_values(metadata_file, "venue")
        events = load_existing_values(metadata_file, "event")
        sea_states = load_existing_values(metadata_file, "sea_state")
        wind_types = load_existing_values(metadata_file, "wind_type")

        venue = autocomplete_dialog(root, "Race Metadata", "Venue:", venues)

        event = autocomplete_dialog(root, "Race Metadata", "Event:", events)

        wind_knots = simpledialog.askinteger(
            "Race Metadata",
            "Wind strength (knots):"
        )

        sea_state = autocomplete_dialog(
            root,
            "Race Metadata",
            "Sea state:",
            sea_states
        )

        wind_type = autocomplete_dialog(
            root,
            "Race Metadata",
            "Wind type:",
            wind_types
        )

        append_metadata(
            metadata_file,
            {
                "race_id": race_id,
                "date": date,
                "race_number": race,
                "fleet": group,
                "venue": venue,
                "event": event,
                "wind_dir_deg": wind_dir_deg,
                "wind_knots": wind_knots,
                "sea_state": sea_state,
                "wind_type": wind_type
            }
        )

        print(f"[STAGE 2] Metadata saved for {race_id}")

    # -------------------------------------------------
    # Find trimmed tracks
    # -------------------------------------------------

    trimmed_files = []

    for f in os.listdir(trimmed_dir):

        if not f.endswith("_trimmed.csv"):
            continue

        if f"_{date}_R{race}_" not in f:
            continue

        if f"_{group}_trimmed.csv" not in f:
            continue

        trimmed_files.append(f)

    trimmed_files = sorted(trimmed_files)

    if not trimmed_files:
        fail("No trimmed tracks found.")

    # -------------------------------------------------
    # Confirm tracks
    # -------------------------------------------------

    ok = messagebox.askokcancel(
        "Confirm Tracks",
        "\n".join(trimmed_files)
    )

    if not ok:
        fail("Viewer cancelled.")

    # -------------------------------------------------
    # Launch viewer
    # -------------------------------------------------

    geometry_url = f"../data/geometry/{geometry_file.name}"

    query = urllib.parse.urlencode({"geometry": geometry_url})

    for t in trimmed_files:
        query += "&" + urllib.parse.urlencode({"trimmed": t})

    viewer_url = f"http://localhost:{port}/viewer/index_course.html?{query}"

    print("[STAGE 2]")
    print("Geometry:", geometry_file)
    print("Viewer:", viewer_url)

    webbrowser.open(viewer_url)


if __name__ == "__main__":
    main()