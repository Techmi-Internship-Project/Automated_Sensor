"""
gui_recovery_settings.py

Handles the Recovery/Summary panel, the Settings popup window,
and the open-recovery-window logic (move / delete old runs).

All methods in this mixin expect self to be a SensorGUI instance.
"""

import tkinter as tk
from tkinter import messagebox
import time
import shutil
import threading
from datetime import datetime
from pathlib import Path

from gui_theme import (
    CARD_BG,
    CARD_BORDER,
    FONT_BRAND,
    NAVY,
    OFF_WHITE,
    SUCCESS,
    DANGER,
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
    find_last_run_info,
)
from camera_tools import camera_can_capture
from laser_control import LaserRelay

# How often the background health check runs (camera/laser/storage).
HEALTH_CHECK_INTERVAL_MS = 5000
# Below this much free space on the data drive, storage is flagged unhealthy.
MIN_FREE_STORAGE_GB = 5.0
# Order matters for the "all systems" pill: items checked here decide overall health.
HEALTH_ITEMS = ["Camera", "Laser Module", "Storage"]


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

        # StringVars set by update_recovery_panel
        self._last_capture_var = tk.StringVar(value="—")
        self._last_run_var     = tk.StringVar(value="—")
        self._total_caps_var   = tk.StringVar(value="—")

        for i, (label, var) in enumerate([
            ("Last Successful Capture", self._last_capture_var),
            ("Last Run",                self._last_run_var),
            ("Total Captures (Last Run)", self._total_caps_var),
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
        # Stored on self so the health-check loop can recolor the whole box.
        self._health_box = tk.Frame(c, bg="#eef2ff")
        self._health_box.grid(row=0, column=1, sticky="nsew")
        self._health_box.grid_columnconfigure(0, weight=1)

        self._health_title_lbl = tk.Label(
            self._health_box,
            text="System Health",
            fg=NAVY,
            bg="#eef2ff",
            font=(FONT_BRAND, 10, "bold")
        )
        self._health_title_lbl.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        # Each health item gets a StringVar (text) and a Label ref (color),
        # both updated live by the health-check loop.
        self._health_vars = {}
        self._health_value_labels = {}
        self._health_row_frames = {}
        for i, item in enumerate(HEALTH_ITEMS):
            row_frame = tk.Frame(self._health_box, bg="#eef2ff")
            row_frame.grid(row=i + 1, column=0, sticky="ew",
                           padx=12, pady=(0, 4 if i < len(HEALTH_ITEMS) - 1 else 10))
            self._health_row_frames[item] = row_frame

            v = tk.StringVar(value="…  Checking")
            self._health_vars[item] = v

            tk.Label(row_frame,
                     text=f"{item}:",
                     fg=TEXT_MUTED,
                     bg="#eef2ff",
                     font=(FONT_BRAND, 10),
                     width=14,
                     anchor="w").pack(side=tk.LEFT)

            value_lbl = tk.Label(row_frame,
                                 textvariable=v,
                                 fg=TEXT_MUTED,
                                 bg="#eef2ff",
                                 font=(FONT_BRAND, 10, "bold"))
            value_lbl.pack(side=tk.LEFT)
            self._health_value_labels[item] = value_lbl

        # Health-state cache: None = unknown/checking, True/False once known.
        self._health_state = {item: None for item in HEALTH_ITEMS}

    # ── System health checks ──────────────────────────────────────────────────
    def _init_health_system(self):
        """
        Call once after the UI is built. Starts the recurring background
        health check (camera / laser / storage) and the recovery panel's
        first disk scan.
        """
        self._recovery_dirty = True
        self._prev_is_running = False
        self._run_health_check()
        self.update_recovery_panel()

    def _run_health_check(self):
        """
        Checks laser presence and free storage synchronously (cheap, no
        device I/O beyond listing serial ports / statvfs). Camera presence
        is checked in a background thread since opening a capture device
        can briefly block.

        Skips actually opening the camera if the preview or an experiment
        is already using it — in that case frames are clearly flowing, so
        the camera is healthy by definition and we avoid grabbing a second
        handle on the same device.
        """

        # ── Storage ──────────────────────────────────────────────────────────
        try:
            free_gb = shutil.disk_usage(self.current_folder).free / (1024 ** 3)
            storage_ok = free_gb >= MIN_FREE_STORAGE_GB
        except Exception:
            storage_ok = False
        self._apply_health_result("Storage", storage_ok)

        # ── Laser ────────────────────────────────────────────────────────────
        try:
            laser_ok = LaserRelay().find_port() is not None
        except Exception:
            laser_ok = False
        self._apply_health_result("Laser Module", laser_ok)

        # ── Camera ───────────────────────────────────────────────────────────
        if self._preview_running or self.controller.is_running:
            self._apply_health_result("Camera", True)
        else:
            try:
                cam_idx = self.get_selected_camera_index()
            except RuntimeError:
                self._apply_health_result("Camera", False)
            else:
                threading.Thread(
                    target=self._camera_health_worker,
                    args=(cam_idx,),
                    daemon=True
                ).start()

        # Reschedule.
        self.root.after(HEALTH_CHECK_INTERVAL_MS, self._run_health_check)

    def _camera_health_worker(self, cam_idx):
        """
        Runs on a background thread: briefly opens the camera to confirm
        it produces a frame, then hands the result back to the GUI thread.
        """
        try:
            ok = camera_can_capture(cam_idx)
        except Exception:
            ok = False
        self.root.after(0, lambda: self._apply_health_result("Camera", ok))

    def _apply_health_result(self, item, ok: bool):
        """
        Updates one health-checklist row and refreshes the overall
        system-ready indicators (topbar pill + sidebar card).
        """
        self._health_state[item] = ok
        var = self._health_vars.get(item)
        lbl = self._health_value_labels.get(item)
        if var is None or lbl is None:
            return

        if ok:
            var.set("✓  Nominal")
            lbl.configure(fg=SUCCESS)
        else:
            var.set("✕  Unavailable")
            lbl.configure(fg=DANGER)

        self._refresh_overall_health_indicator()

    def _refresh_overall_health_indicator(self):
        """
        Updates the topbar pill and the sidebar "All Systems" card based
        on the combined health-check state. Only shows green if every
        checked item is confirmed healthy.
        """
        states = list(self._health_state.values())
        all_ok = all(states) and None not in states

        if all_ok:
            pill_text, pill_fg, pill_bg = "⬤  System Ready", "#d1fae5", "#0d2e1a"
            title_fg, status_fg, status_text = "#bbf7d0", "#6ee7b7", "   Nominal"
        else:
            pill_text, pill_fg, pill_bg = "⬤  Attention Needed", "#fee2e2", "#3a0d0d"
            title_fg, status_fg, status_text = "#fecaca", "#fca5a5", "   Issue Detected"

        try:
            self.system_ready_lbl.configure(text=pill_text, fg=pill_fg, bg=pill_bg)
        except Exception:
            pass

        try:
            self._sidebar_health_title_lbl.configure(fg=title_fg)
            self._sidebar_health_status_lbl.configure(fg=status_fg, text=status_text)
        except Exception:
            pass

    # ── Recovery / Summary live updates ───────────────────────────────────────
    def _format_capture_timestamp(self, ts: float) -> str:
        """
        Formats a unix timestamp as 'Today, HH:MM' or 'Mon DD, HH:MM'.
        """
        dt = datetime.fromtimestamp(ts)
        now = datetime.now()
        if dt.date() == now.date():
            return f"Today, {dt.strftime('%H:%M')}"
        return dt.strftime("%b %d, %H:%M")

    def update_recovery_panel(self):
        """
        Keeps the Recovery / Summary stats current.

        While a run is active, this reads live numbers straight out of the
        controller's status dict (cheap, no disk access) so the panel
        updates every poll tick. While idle, it only rescans disk when
        something has actually changed (self._recovery_dirty), since
        walking run folders is comparatively expensive.
        """

        if self.controller.is_running:
            self._prev_is_running = True
            st = self.controller.get_status()
            run_folder = st.get("run_folder")
            captures = st.get("capture_count", 0)
            last_img = st.get("last_saved_image")

            if run_folder:
                self._last_run_var.set(f"{self.organism.get()} / {Path(run_folder).name}")
            self._total_caps_var.set(str(captures))
            if last_img:
                self._last_capture_var.set(self._format_capture_timestamp(time.time()))
            return

        # Just transitioned from running -> idle: the run that finished
        # (whether completed, stopped, or errored) is now "the last run".
        if self._prev_is_running:
            self._recovery_dirty = True
            self._prev_is_running = False

        if not self._recovery_dirty:
            return
        self._recovery_dirty = False

        info = find_last_run_info(
            current_folder=self.current_folder,
            training_folder=self.training_folder
        )

        if info is None:
            self._last_run_var.set("—")
            self._total_caps_var.set("—")
            self._last_capture_var.set("—")
            return

        self._last_run_var.set(info["run_name"])
        self._total_caps_var.set(str(info["capture_count"]))
        self._last_capture_var.set(self._format_capture_timestamp(info["last_capture_ts"]))

    # ── Settings popup ────────────────────────────────────────────────────────
    def _open_settings_window(self):
        """
        Opens the Settings Toplevel with laser COM port and other config.
        """

        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("600x600")
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
        

        # ── ArUco Error Handling ──────────────────────────────────────────────
                # ── ArUco Error Handling ──────────────────────────────────────────────
        tk.Frame(win, bg=CARD_BORDER, height=1).pack(fill=tk.X, padx=28, pady=(12, 8))

        tk.Label(win,
                 text="ArUco Error Handling",
                 fg=NAVY,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 11, "bold")).pack(anchor="w", padx=28)

        # Initialize vars the first time the window is opened.
        if not hasattr(self, "_continue_with_prev_roi_var"):
            self._continue_with_prev_roi_var = tk.BooleanVar(value=True)
        if not hasattr(self, "_max_aruco_failures_var"):
            self._max_aruco_failures_var = tk.StringVar(value="3")

        # Checkbox: continue using previous ROI (on by default).
        chk_frame = tk.Frame(win, bg=OFF_WHITE)
        chk_frame.pack(fill=tk.X, padx=28, pady=(6, 2))

        chk = tk.Checkbutton(
            chk_frame,
            text="Continue using previous ROI when markers disappear",
            variable=self._continue_with_prev_roi_var,
            bg=OFF_WHITE,
            fg=TEXT_DARK,
            font=(FONT_BRAND, 11),
            activebackground=OFF_WHITE,
            command=lambda: _toggle_aruco_dropdown()
        )
        chk.pack(side=tk.LEFT)

        # Indented row for the consecutive-failures dropdown.
        fail_frame = tk.Frame(win, bg=OFF_WHITE)
        fail_frame.pack(fill=tk.X, padx=52, pady=(0, 4))  # extra left indent

        tk.Label(fail_frame,
                 text="Stop after consecutive capture failures:",
                 fg=TEXT_MUTED,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 10)).pack(side=tk.LEFT, padx=(0, 8))

        failure_dropdown = tk.OptionMenu(
            fail_frame,
            self._max_aruco_failures_var,
            "1", "2", "3", "5", "10"
        )
        failure_dropdown.configure(
            font=(FONT_BRAND, 10),
            bg="white",
            fg=TEXT_DARK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=CARD_BORDER
        )
        failure_dropdown.pack(side=tk.LEFT)

        def _toggle_aruco_dropdown():
            # Dropdown is only usable when the checkbox is OFF.
            state = "disabled" if self._continue_with_prev_roi_var.get() else "normal"
            failure_dropdown.configure(state=state)
            for child in fail_frame.winfo_children():
                try:
                    child.configure(state=state)
                except tk.TclError:
                    pass

        # Set initial dropdown state to match the checkbox default.
        _toggle_aruco_dropdown()



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