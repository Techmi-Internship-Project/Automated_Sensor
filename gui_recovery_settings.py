"""
gui_recovery_settings.py

Handles the Recovery/Summary panel, the Settings popup window,
and the open-recovery-window logic (move / delete old runs).

All methods in this mixin expect self to be a SensorGUI instance.
"""

import tkinter as tk
from tkinter import messagebox
import time
from pathlib import Path

from gui_theme import (
    CARD_BG,
    CARD_BORDER,
    FONT_BRAND,
    NAVY,
    OFF_WHITE,
    SUCCESS,
    TEXT_DARK,
    TEXT_MUTED,
    format_elapsed,
    _btn,
    _card,
    _section_label,
)
from startup_recovery import (
    move_valid_runs_to_training,
    current_folder_has_contents,
    wipe_folder_contents,
    move_run_to_training,
    build_training_destination,
)


class RecoverySettingsMixin:
    """
    GUI section mixin split out of the original SensorGUI class.
    """

    # ── Recovery / Summary panel ──────────────────────────────────────────────
    def _build_recovery_panel(self, parent, row=0):
        """
        Creates the Recovery / Summary card in the right column.
        Shows last capture time, last run name, total captures,
        and a system-health checklist.
        """

        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        card, c = _card(parent, "RECOVERY / SUMMARY", "◇")

        # Place at the bottom of the right column (row 3)
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 8))

        # Two sub-columns inside the card: stats on left, health on right
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(1, weight=1)

        # ── Left: run statistics ──────────────────────────────────────────────
        stats = tk.Frame(c, bg=CARD_BG)
        stats.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        stats.grid_columnconfigure(0, weight=1)

        # StringVars set by update_status_loop
        self._last_capture_var = tk.StringVar(value="—")
        self._last_run_var     = tk.StringVar(value="—")
        self._total_caps_var   = tk.StringVar(value="—")

        for i, (label, var) in enumerate([
            ("Last Successful Capture", self._last_capture_var),
            ("Last Run",                self._last_run_var),
            ("Total Captures (All Runs)", self._total_caps_var),
        ]):
            _section_label(stats, label).grid(
                row=i * 2, column=0,
                sticky="w",
                pady=(8 if i == 0 else 4, 0))

            tk.Label(
                stats,
                textvariable=var,
                fg=SUCCESS if i == 0 else TEXT_DARK,
                bg=CARD_BG,
                font=(FONT_BRAND, 11)
            ).grid(row=i * 2 + 1, column=0, sticky="w")

        # ── Right: system health checklist ────────────────────────────────────
        health = tk.Frame(c, bg="#f0fdf4",
                          highlightthickness=1,
                          highlightbackground="#bbf7d0")
        health.grid(row=0, column=1, sticky="nsew")
        health.grid_columnconfigure(0, weight=1)

        tk.Label(
            health,
            text="System Health",
            fg=NAVY,
            bg="#f0fdf4",
            font=(FONT_BRAND, 10, "bold")
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        # Each health item gets a StringVar so it can be updated at runtime
        self._health_vars = {}
        for i, item in enumerate(["Camera", "Laser Module", "Storage"]):
            row_frame = tk.Frame(health, bg="#f0fdf4")
            row_frame.grid(row=i + 1, column=0, sticky="ew",
                           padx=12, pady=(0, 4 if i < 2 else 10))

            v = tk.StringVar(value="✓  Nominal")
            self._health_vars[item] = v

            tk.Label(row_frame,
                     text=f"{item}:",
                     fg=TEXT_MUTED,
                     bg="#f0fdf4",
                     font=(FONT_BRAND, 10),
                     width=14,
                     anchor="w").pack(side=tk.LEFT)

            tk.Label(row_frame,
                     textvariable=v,
                     fg=SUCCESS,
                     bg="#f0fdf4",
                     font=(FONT_BRAND, 10, "bold")).pack(side=tk.LEFT)

    # ── Settings popup ────────────────────────────────────────────────────────
    def _open_settings_window(self):
        """
        Opens the Settings Toplevel with laser COM port and other config.
        """

        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("440x340")
        win.configure(bg=OFF_WHITE)
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win,
                 text="Settings",
                 fg=NAVY,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 15, "bold")).pack(pady=(18, 14))

        # ── Laser COM port ────────────────────────────────────────────────────
        fr = tk.Frame(win, bg=OFF_WHITE)
        fr.pack(fill=tk.X, padx=28, pady=6)
        tk.Label(fr,
                 text="Laser COM Port:",
                 fg=TEXT_DARK,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 11),
                 width=20,
                 anchor="w").pack(side=tk.LEFT)

        # Keep a StringVar so the value can be read back on save
        if not hasattr(self, "_laser_port_var"):
            self._laser_port_var = tk.StringVar(value="COM5")

        tk.Entry(fr,
                 textvariable=self._laser_port_var,
                 width=10,
                 font=(FONT_BRAND, 11),
                 relief="flat",
                 bd=1,
                 bg="white",
                 fg=TEXT_DARK,
                 highlightthickness=1,
                 highlightbackground=CARD_BORDER).pack(side=tk.LEFT)

        # ── Manual camera index override ──────────────────────────────────────
        fr2 = tk.Frame(win, bg=OFF_WHITE)
        fr2.pack(fill=tk.X, padx=28, pady=6)
        tk.Label(fr2,
                 text="Force Camera Index:",
                 fg=TEXT_DARK,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 11),
                 width=20,
                 anchor="w").pack(side=tk.LEFT)

        if not hasattr(self, "_force_cam_var"):
            self._force_cam_var = tk.StringVar(value="")

        tk.Entry(fr2,
                 textvariable=self._force_cam_var,
                 width=6,
                 font=(FONT_BRAND, 11),
                 relief="flat",
                 bd=1,
                 bg="white",
                 fg=TEXT_DARK,
                 highlightthickness=1,
                 highlightbackground=CARD_BORDER).pack(side=tk.LEFT)

        # ── Data root (read-only display) ─────────────────────────────────────
        fr3 = tk.Frame(win, bg=OFF_WHITE)
        fr3.pack(fill=tk.X, padx=28, pady=6)
        tk.Label(fr3,
                 text="Data Root:",
                 fg=TEXT_DARK,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 11),
                 width=20,
                 anchor="w").pack(side=tk.LEFT)

        tk.Label(fr3,
                 text=str(self.current_folder.parent),
                 fg=TEXT_MUTED,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 10),
                 wraplength=260,
                 anchor="w").pack(side=tk.LEFT)

        # ── Divider + action buttons ──────────────────────────────────────────
        tk.Frame(win, bg=CARD_BORDER, height=1).pack(fill=tk.X, padx=28, pady=16)

        btn_row = tk.Frame(win, bg=OFF_WHITE)
        btn_row.pack(padx=28)

        _btn(btn_row, "Save",
             lambda: self._save_settings(win),
             "primary").pack(side=tk.LEFT, padx=(0, 8))
        _btn(btn_row, "Cancel",
             win.destroy,
             "secondary").pack(side=tk.LEFT)

    def _save_settings(self, win):
        """
        Saves settings and closes the Settings window.
        """
        # LaserRelay will use the COM port on next open call
        win.destroy()
        self._append_log("Settings saved.", "gray")

    # ── Old-runs recovery window ──────────────────────────────────────────────
    def open_recovery_window(self):
        """
        Checks whether the current folder has contents, then opens the
        Handle Old Runs popup if it does.
        """

        if not current_folder_has_contents(self.current_folder):
            messagebox.showinfo("No Old Runs",
                                "The current folder is empty.")
            self.update_recovery_button_state()
            return

        win = tk.Toplevel(self.root)
        win.title("Handle Old Runs")
        win.geometry("420x250")
        win.configure(bg=OFF_WHITE)
        win.grab_set()

        tk.Label(win,
                 text="Old data exists in current/",
                 fg=NAVY,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 13, "bold")).pack(pady=(16, 6))

        tk.Label(win,
                 text="Choose what to do before starting a new run.",
                 fg=TEXT_MUTED,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 10)).pack(pady=(0, 8))

        _btn(win,
             "Move valid runs to training folder",
             lambda: self._recovery_move(win),
             "secondary").pack(fill=tk.X, padx=28, pady=(0, 4))

        _btn(win,
             "Delete everything in current folder",
             lambda: self._recovery_delete(win),
             "danger").pack(fill=tk.X, padx=28, pady=4)

        _btn(win,
             "Keep for now",
             win.destroy,
             "ghost").pack(fill=tk.X, padx=28, pady=4)

    def _recovery_move(self, win):
        """
        Moves valid runs from current/ to training/ then wipes current/.
        """

        moved, skipped = move_valid_runs_to_training(
            current_folder=self.current_folder,
            training_folder=self.training_folder,
        )
        self.update_recovery_button_state()
        win.destroy()
        messagebox.showinfo(
            "Recovery Complete",
            f"Moved {moved} run(s).\nSkipped {skipped} invalid run(s).")
        wipe_folder_contents(self.current_folder)
        self._append_log(f"Recovery: moved {moved}, skipped {skipped}.", "gray")

    def _recovery_delete(self, win):
        """
        Asks for confirmation then wipes everything inside current/.
        """

        if not messagebox.askyesno("Confirm Delete",
                                   "Delete everything in current/?"):
            return
        wipe_folder_contents(self.current_folder)
        self.update_recovery_button_state()
        win.destroy()
        messagebox.showinfo("Deleted", "Everything in current/ was deleted.")
        self._append_log("Current folder wiped.", "gray")

    def update_recovery_button_state(self):
        """
        Enables the Handle Old Runs button only when current/ has contents
        and no experiment is running.
        """

        has = current_folder_has_contents(self.current_folder)
        state = "normal" if (has and not self.controller.is_running) \
            else "disabled"
        try:
            self.recovery_button.configure(state=state)
        except Exception:
            pass

    def _show_run_summary(self, run_folder, captures, elapsed):
        """
        Shows a popup summary when a run finishes and moves to training.
        """

        msg = (
            f"Run completed successfully.\n\n"
            f"Captures saved: {captures}\n"
            f"Elapsed time:   {format_elapsed(elapsed)}\n\n"
            f"Folder: {run_folder}"
        )
        messagebox.showinfo("Run Complete", msg)
