#!/usr/bin/env python3
# StageOnePanel.py — Stage One GUI logic

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import os
import pandas as pd
import webbrowser
import urllib.parse
from datetime import datetime, timedelta
import shutil
import subprocess
import sys

from Workflow import (
    run_trimming_pipeline,
    run_trim_all_races_for_day,
)

FIT_DIR = "data/fit/"
RACETIMES_PATH = "data/racetimes/RaceTimes.csv"
MARKS_DEST_DIR = "data/marks/"


# --------------------------------------------------------------
# TIME HELPERS (EXPLICIT OFFSET, NO SYSTEM TIMEZONE)
# --------------------------------------------------------------
def _dt_from_local(date_ddmmyy, hms):
    d = datetime.strptime(date_ddmmyy, "%d%m%y")
    t = datetime.strptime(hms, "%H:%M:%S")
    return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second)


def local_to_utc_hms(date_ddmmyy, hms, offset_hours):
    return (
        _dt_from_local(date_ddmmyy, hms)
        - timedelta(hours=offset_hours)
    ).strftime("%H:%M:%S")


def utc_to_local_hms(date_ddmmyy, hms, offset_hours):
    return (
        _dt_from_local(date_ddmmyy, hms)
        + timedelta(hours=offset_hours)
    ).strftime("%H:%M:%S")


def _require_ddmmyy(date_str: str) -> bool:
    return len(date_str) == 6 and date_str.isdigit()


def _open_file_in_os(path: str):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


# --------------------------------------------------------------
# MAIN PANEL
# --------------------------------------------------------------
class StageOnePanel:

    def __init__(self, root, server_port):
        self.root = root
        self.root.title("SailAnalytics — Stage One")
        self.server_port = server_port

        # ---------------- FIT FILES ----------------
        fit_frame = ttk.LabelFrame(root, text="FIT Files")
        fit_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nw")

        self.fit_listbox = tk.Listbox(
            fit_frame, width=55, height=12, selectmode=tk.EXTENDED
        )
        self.fit_listbox.pack(side="left", padx=5, pady=5)
        self.refresh_fit_files()

        # ---------------- RACE SELECTION ----------------
        race_frame = ttk.LabelFrame(root, text="Race Selection")
        race_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nw")

        ttk.Label(race_frame, text="Date (DDMMYY):").grid(row=0, column=0, sticky="w")
        ttk.Label(race_frame, text="Race #:").grid(row=1, column=0, sticky="w")
        ttk.Label(race_frame, text="Group Color:").grid(row=2, column=0, sticky="w")

        self.entry_date = ttk.Entry(race_frame, width=12)
        self.entry_race = ttk.Entry(race_frame, width=12)   # optional: blank = day mode (trim/view pick race)
        self.entry_group = ttk.Entry(race_frame, width=12)

        self.entry_date.grid(row=0, column=1)
        self.entry_race.grid(row=1, column=1)
        self.entry_group.grid(row=2, column=1)

        # ---------------- SINGLE RACE TIMES ----------------
        time_frame = ttk.LabelFrame(root, text="Race Times (Single Race Trim Only)")
        time_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nw")

        ttk.Label(time_frame, text="Gun Time:").grid(row=0, column=0, sticky="w")
        ttk.Label(time_frame, text="Finish Time:").grid(row=1, column=0, sticky="w")

        self.entry_gun = ttk.Entry(time_frame, width=12)
        self.entry_finish = ttk.Entry(time_frame, width=12)

        self.entry_gun.grid(row=0, column=1)
        self.entry_finish.grid(row=1, column=1)

        # ---------------- RaceTimes tools ----------------
        tools_frame = ttk.LabelFrame(root, text="RaceTimes (data/racetimes/RaceTimes.csv)")
        tools_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nw")

        ttk.Button(tools_frame, text="Open RaceTimes CSV", command=self.open_racetimes_csv).grid(row=0, column=0, padx=5)
        ttk.Button(tools_frame, text="Enter Day RaceTimes (N races)", command=self.enter_day_racetimes).grid(row=0, column=1, padx=5)

        # ---------------- BUTTONS ----------------
        btn_frame = ttk.Frame(root)
        btn_frame.grid(row=4, column=0, padx=10, pady=10, sticky="nw")

        ttk.Button(btn_frame, text="Load Race Times", command=self.load_race_times).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Trim Races", command=self.trim_races).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text="GO TO VIEWER", command=self.go_to_viewer).grid(row=0, column=2, padx=5)
        ttk.Button(btn_frame, text="MOVE MARKS FILE", command=self.move_marks_file).grid(row=0, column=3, padx=5)
        ttk.Button(btn_frame, text="VIEW COURSE", command=self.view_course).grid(row=0, column=4, padx=5)

    # ----------------------------------------------------------
    # OPEN RACETIMES CSV
    # ----------------------------------------------------------
    def open_racetimes_csv(self):
        if not os.path.isfile(RACETIMES_PATH):
            messagebox.showerror("Not Found", f"RaceTimes.csv not found:\n{RACETIMES_PATH}")
            return
        _open_file_in_os(RACETIMES_PATH)

    # ----------------------------------------------------------
    # ENTER DAY RACETIMES (N races) -> writes to RaceTimes.csv
    # ----------------------------------------------------------
    def enter_day_racetimes(self):
        date = self.entry_date.get().strip()
        group = self.entry_group.get().strip().lower()

        if not (_require_ddmmyy(date) and group):
            messagebox.showerror("Missing Fields", "Enter Date (DDMMYY) and Group Color.")
            return

        n_str = simpledialog.askstring("How many races today?", "Enter number of races (e.g. 6)")
        if not n_str:
            return
        try:
            n_races = int(n_str)
            if n_races < 1 or n_races > 20:
                raise ValueError()
        except Exception:
            messagebox.showerror("Invalid", "Number of races must be an integer 1..20.")
            return

        offset_str = simpledialog.askstring("UTC Offset", "Enter UTC offset hours for LOCAL times you will enter (e.g. 0, 1)")
        if offset_str is None:
            return
        try:
            offset = int(offset_str)
        except Exception:
            messagebox.showerror("Invalid", "UTC offset must be an integer.")
            return

        # Load existing RaceTimes.csv if present
        rows = []
        if os.path.isfile(RACETIMES_PATH):
            rows = pd.read_csv(RACETIMES_PATH, dtype=str).to_dict("records")

        # Remove existing rows for this date+group+race_number 1..N (overwrite cleanly)
        kept = []
        for r in rows:
            if r.get("date") == date and str(r.get("group_color", "")).lower() == group:
                try:
                    rn = int(r.get("race_number", "0"))
                except Exception:
                    rn = 0
                if 1 <= rn <= n_races:
                    continue
            kept.append(r)

        new_rows = []
        for race_no in range(1, n_races + 1):
            gun_local = simpledialog.askstring(
                f"Race {race_no}",
                f"Enter GUN time local (HH:MM:SS) for Race {race_no}"
            )
            if not gun_local:
                return

            fin_local = simpledialog.askstring(
                f"Race {race_no}",
                f"Enter FINISH time local (HH:MM:SS) for Race {race_no}"
            )
            if not fin_local:
                return

            gun_utc = local_to_utc_hms(date, gun_local, offset)
            fin_utc = local_to_utc_hms(date, fin_local, offset)

            new_rows.append({
                "date": date,
                "race_number": str(race_no),
                "group_color": group,
                "gun_time": gun_utc,
                "finish_time": fin_utc,
                "utc_offset": str(offset),
            })

        out_rows = kept + new_rows
        os.makedirs(os.path.dirname(RACETIMES_PATH), exist_ok=True)
        pd.DataFrame(out_rows).to_csv(RACETIMES_PATH, index=False)

        messagebox.showinfo("Saved", f"RaceTimes saved for {date} {group} (R1..R{n_races}).")

    # ----------------------------------------------------------
    # MOVE MARKS FILE
    # ----------------------------------------------------------
    def move_marks_file(self):
        src_path = filedialog.askopenfilename(
            title="Select Marks File",
            initialdir=os.path.expanduser("~/Downloads"),
            filetypes=[("CSV files", "*.csv")]
        )

        if not src_path:
            return

        os.makedirs(MARKS_DEST_DIR, exist_ok=True)

        dest_path = os.path.join(
            MARKS_DEST_DIR,
            os.path.basename(src_path)
        )

        try:
            shutil.move(src_path, dest_path)
        except Exception as e:
            messagebox.showerror("Move Failed", str(e))
            return

        messagebox.showinfo("Marks File Moved", dest_path)

    # ----------------------------------------------------------
    # VIEW COURSE (WIRED TO STAGE TWO)
    # Minimal fix: Race # can be blank -> prompt for it
    # ----------------------------------------------------------
    def view_course(self):
        date = self.entry_date.get().strip()
        race = self.entry_race.get().strip()   # may be blank
        group = self.entry_group.get().strip().lower()

        if not (date and group):
            messagebox.showerror(
                "Missing Fields",
                "Date and Group are required."
            )
            return

        # If race blank, ask (multi-race day workflow)
        if race == "":
            # Prefer offering available races if you already trimmed
            races = self._list_available_races(date, group)
            if races:
                race = simpledialog.askstring(
                    "Which race to view course?",
                    f"Available races: {', '.join(races)}\n\nEnter race number:"
                )
            else:
                race = simpledialog.askstring(
                    "Which race to view course?",
                    "Enter race number (e.g. 1):"
                )

            if not race:
                return

            race = race.strip()

            # If we had a list, enforce it
            if races and (not race.isdigit() or race not in races):
                messagebox.showerror("Invalid Race", "Enter a valid race number from the list.")
                return

            # Otherwise just validate numeric
            if not races and (not race.isdigit() or int(race) < 1 or int(race) > 50):
                messagebox.showerror("Invalid Race", "Race number must be an integer (1..50).")
                return

            # write back into box so user can see what was chosen
            self.entry_race.delete(0, tk.END)
            self.entry_race.insert(0, race)

        stage_two_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "StageTwo.py"
        )

        if not os.path.isfile(stage_two_path):
            messagebox.showerror("Error", "StageTwo.py not found.")
            return

        subprocess.Popen(
            [
                sys.executable,
                stage_two_path,
                "--date", date,
                "--race", str(race),
                "--group", group,
                "--port", str(self.server_port),
            ]
        )

    # ----------------------------------------------------------
    # FIT FILE LIST
    # ----------------------------------------------------------
    def refresh_fit_files(self):
        self.fit_listbox.delete(0, tk.END)
        if not os.path.isdir(FIT_DIR):
            return
        for f in sorted(os.listdir(FIT_DIR)):
            if f.lower().endswith(".fit"):
                self.fit_listbox.insert(tk.END, f)

    # ----------------------------------------------------------
    # LOAD RACE TIMES (single race)
    # ----------------------------------------------------------
    def load_race_times(self):
        date = self.entry_date.get().strip()
        race = self.entry_race.get().strip()
        group = self.entry_group.get().strip()

        if not (date and race and group):
            messagebox.showerror("Missing Fields", "Date, Race, and Group required.")
            return

        rows = []
        if os.path.isfile(RACETIMES_PATH):
            rows = pd.read_csv(RACETIMES_PATH, dtype=str).to_dict("records")

        match = next(
            (r for r in rows if r["date"] == date and r["race_number"] == race and r["group_color"] == group),
            None
        )

        if match:
            offset = int(match.get("utc_offset", "0"))
            self.entry_gun.delete(0, tk.END)
            self.entry_finish.delete(0, tk.END)
            self.entry_gun.insert(0, utc_to_local_hms(date, match["gun_time"], offset))
            self.entry_finish.insert(0, utc_to_local_hms(date, match["finish_time"], offset))
            return

        gun_local = simpledialog.askstring("Race Time Entry", "Enter Gun Time (HH:MM:SS)")
        if not gun_local:
            return

        finish_local = simpledialog.askstring("Race Time Entry", "Enter Finish Time (HH:MM:SS)")
        if not finish_local:
            return

        offset_str = simpledialog.askstring("UTC Offset", "Enter UTC Offset (hours)")
        if offset_str is None:
            return
        offset = int(offset_str)

        rows.append({
            "date": date,
            "race_number": race,
            "group_color": group,
            "gun_time": local_to_utc_hms(date, gun_local, offset),
            "finish_time": local_to_utc_hms(date, finish_local, offset),
            "utc_offset": str(offset)
        })

        os.makedirs(os.path.dirname(RACETIMES_PATH), exist_ok=True)
        pd.DataFrame(rows).to_csv(RACETIMES_PATH, index=False)

        self.entry_gun.delete(0, tk.END)
        self.entry_finish.delete(0, tk.END)
        self.entry_gun.insert(0, gun_local)
        self.entry_finish.insert(0, finish_local)

    # ----------------------------------------------------------
    # TRIM RACES
    # - Race blank -> trim ALL races for day from RaceTimes.csv
    # - Race filled -> single race trim (uses gun/finish fields)
    # ----------------------------------------------------------
    def trim_races(self):
        selected = self.fit_listbox.curselection()
        if not selected:
            messagebox.showerror("No FIT Files", "Select at least one FIT file.")
            return

        date = self.entry_date.get().strip()
        race = self.entry_race.get().strip()  # may be blank
        group = self.entry_group.get().strip().lower()

        if not (date and group):
            messagebox.showerror("Missing Fields", "Date and Group Color are required.")
            return

        selected_fits = [self.fit_listbox.get(i) for i in selected]

        # Multi-race day trim
        if race == "":
            try:
                outputs = run_trim_all_races_for_day(selected_fits, date, group)
            except Exception as e:
                messagebox.showerror("Trim Failed", str(e))
                return

            messagebox.showinfo("Trim Complete", f"Trimmed ALL races for {date} {group}.\nFiles written: {len(outputs)}")
            return

        # Single race trim
        gun = self.entry_gun.get().strip()
        fin = self.entry_finish.get().strip()

        if not os.path.isfile(RACETIMES_PATH):
            messagebox.showerror("Missing RaceTimes.csv", "RaceTimes.csv not found.")
            return

        rows = pd.read_csv(RACETIMES_PATH, dtype=str)
        row = rows[
            (rows["date"] == date) &
            (rows["race_number"] == race) &
            (rows["group_color"].str.lower() == group)
        ]

        if row.empty:
            messagebox.showerror("Missing Race", "Race times not loaded.")
            return

        offset = int(row.iloc[0].get("utc_offset", "0"))

        for fit_filename in selected_fits:
            run_trimming_pipeline(
                fit_filename,
                date,
                race,
                local_to_utc_hms(date, gun, offset),
                local_to_utc_hms(date, fin, offset)
            )

        messagebox.showinfo("Trim Complete", "Trim completed.")

    # ----------------------------------------------------------
    # NEW: list available races on disk for date+group
    # ----------------------------------------------------------
    def _list_available_races(self, date, group):
        races = set()
        if not os.path.isdir("data/trimmed/"):
            return []

        for f in os.listdir("data/trimmed/"):
            if not f.endswith("_trimmed.csv"):
                continue
            if f"_{date}_" not in f:
                continue
            if f"_{group}_" not in f:
                continue

            parts = f.split("_")
            r_token = next((p for p in parts if p.startswith("R") and p[1:].isdigit()), None)
            if r_token:
                races.add(r_token[1:])

        return sorted(races, key=lambda x: int(x))

    # ----------------------------------------------------------
    # VIEWER
    # - If Race filled: open that race
    # - If Race blank: ask which race to view (based on trimmed outputs)
    # ----------------------------------------------------------
    def go_to_viewer(self):
        date = self.entry_date.get().strip()
        group = self.entry_group.get().strip().lower()
        race = self.entry_race.get().strip()

        if not (date and group):
            messagebox.showerror("Missing Fields", "Date and Group Color are required.")
            return

        if race == "":
            races = self._list_available_races(date, group)
            if not races:
                messagebox.showerror("No Trimmed Races", f"No trimmed races found for {date} {group}.")
                return

            race = simpledialog.askstring(
                "Which race to view?",
                f"Available races: {', '.join(races)}\n\nEnter race number:"
            )
            if not race:
                return
            race = race.strip()
            if not race.isdigit() or race not in races:
                messagebox.showerror("Invalid Race", "Enter a valid race number from the list.")
                return

            self.entry_race.delete(0, tk.END)
            self.entry_race.insert(0, race)

        trimmed_files = []
        if not os.path.isdir("data/trimmed/"):
            messagebox.showerror("Missing Folder", "data/trimmed/ not found.")
            return

        for f in os.listdir("data/trimmed/"):
            if not f.endswith("_trimmed.csv"):
                continue
            if f"_{date}_R{race}_" not in f:
                continue
            if f"_{group}_trimmed.csv" not in f:
                continue
            trimmed_files.append(f"../data/trimmed/{f}")

        if not trimmed_files:
            messagebox.showerror("No Files", f"No trimmed files found for {date} R{race} {group}.")
            return

        params = {
            "date": date,
            "race_number": str(race),
            "group_color": group
        }

        query = urllib.parse.urlencode(params)
        for t in sorted(trimmed_files):
            query += "&" + urllib.parse.urlencode({"trimmed": t})

        webbrowser.open(
            f"http://localhost:{self.server_port}/viewer/index.html?{query}"
        )
