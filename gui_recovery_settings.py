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
from tkinter import filedialog

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
    TECHMI_BLUE,
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
from config import save_app_settings, load_app_settings, SETTLE_FRAMES
from gui_camera_panel import _info_icon

# How often the background health check runs (camera/laser/storage).
HEALTH_CHECK_INTERVAL_MS = 5000
# Below this much free space on the data drive, storage is flagged unhealthy.
MIN_FREE_STORAGE_GB = 5.0
# Consecutive failed storage checks required before treating the drive as
# actually gone. At the 5s check interval this gives ~10-15s of tolerance
# for a brief Google Drive / network-drive hiccup, mirroring the bounded
# reconnect attempts already used for camera and laser relay failures,
# instead of aborting a multi-hour run on a single missed check.
STORAGE_FAILURE_TOLERANCE = 3
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

        # 3 sub-columns inside the card: stats on left, graph in middle, health on right
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(1, weight=2)
        c.grid_columnconfigure(2, weight=1)

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
                font=(FONT_BRAND, 9),
                wraplength=130,
                anchor="w",
                justify="left"
            ).grid(row=i * 2 + 1, column=0, sticky="w")

        # ── Middle: Biomass graph + stage label ────────────────────────────────────
        graph_col = tk.Frame(c, bg=CARD_BG)
        graph_col.grid(row=0, column=1, sticky="nsew", padx=(0,8))
        graph_col.grid_columnconfigure(0, weight=1)
        graph_col.grid_rowconfigure(0, weight=0)
        graph_col.grid_rowconfigure(1, weight=0)


        # Store biomass/CFU data and stage
        self._biomass_data = [] # List of (elapsed_hours, biomass)
        self._cfu_data = []     # List of (elapsed_hours, cfu_ml)
        self._graph_metric = "biomass"  # Which metric currently drives the trend graph
        self._current_state_var = tk.StringVar(value="-")
        self._current_biomass_var = tk.StringVar(value="Biomass: —")
        self._current_cfu_var = tk.StringVar(value="CFU/mL: —")
        self._run_start_time = None # Set when run starts

        from config import load_app_settings
        import matplotlib
        matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        # Figure
        self._bio_fig, self._bio_ax = plt.subplots(figsize=(2.8, 2.5))

        self._bio_fig.patch.set_facecolor(CARD_BG)
        self._bio_ax.set_facecolor("#f8fafc")
        self._bio_ax.set_xlabel("Elapsed (h)", fontsize=7, color=TEXT_MUTED)
        self._bio_ax.set_ylabel("Biomass", fontsize=7, color=TEXT_MUTED)
        self._bio_ax.tick_params(labelsize=6, colors=TEXT_MUTED)

        for spine in self._bio_ax.spines.values() : 
            spine.set_edgecolor(CARD_BORDER)
        self._bio_fig.tight_layout(pad=0.8) 

        self._bio_canvas = FigureCanvasTkAgg(self._bio_fig, master=graph_col)
        self._bio_canvas_widget = self._bio_canvas.get_tk_widget()
        self._bio_canvas_widget.grid(row=0, column=0)
        self._bio_canvas_widget.configure(width=280, height=150)

        # Toggle row: two clickable "tabs" showing each metric's latest value.
        # Clicking one switches which metric drives the trend graph above —
        # biomass (g/L) and CFU/mL live on very different scales, so plotting
        # both on one shared axis would be unreadable in this small a space.
        toggle_row = tk.Frame(graph_col, bg=CARD_BG)
        toggle_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        toggle_row.grid_columnconfigure((0, 1), weight=1)

        self._biomass_tab = tk.Label(
            toggle_row, textvariable=self._current_biomass_var,
            bg=TECHMI_BLUE, fg="white",
            font=(FONT_BRAND, 8, "bold"),
            padx=6, pady=3, cursor="hand2"
        )
        self._biomass_tab.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self._biomass_tab.bind("<Button-1>", lambda e: self._set_graph_metric("biomass"))

        self._cfu_tab = tk.Label(
            toggle_row, textvariable=self._current_cfu_var,
            bg="#eef2ff", fg=TEXT_MUTED,
            font=(FONT_BRAND, 8, "bold"),
            padx=6, pady=3, cursor="hand2"
        )
        self._cfu_tab.grid(row=0, column=1, sticky="ew", padx=(2, 0))
        self._cfu_tab.bind("<Button-1>", lambda e: self._set_graph_metric("cfu_ml"))

        # ── Right: system health checklist ────────────────────────────────────
        # Stored on self so the health-check loop can recolor the whole box.
        self._health_box = tk.Frame(c, bg="#eef2ff")
        self._health_box.grid(row=0, column=2, sticky="nsew")
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
                        padx=12, pady=(0, 6 if i < len(HEALTH_ITEMS) - 1 else 10))
            self._health_row_frames[item] = row_frame

            tk.Label(row_frame, text=f"{item}:",
                    fg=TEXT_MUTED, bg="#eef2ff",
                    font=(FONT_BRAND, 9), anchor="w").pack(anchor="w")

            v = tk.StringVar(value="…  Checking")
            self._health_vars[item] = v

            value_lbl = tk.Label(row_frame, textvariable=v,
                                fg=TEXT_MUTED, bg="#eef2ff",
                                font=(FONT_BRAND, 9, "bold"), anchor="w")
            value_lbl.pack(anchor="w")
            self._health_value_labels[item] = value_lbl


        # Health-state cache: None = unknown/checking, True/False once known.
        self._health_state = {item: None for item in HEALTH_ITEMS}
        self._camera_health_in_progress = False

    def _start_comms_poll(self) : 
        """
        Starts a 30-second comms.json polling loop.
        Only reads when a run is active and not in standalone mode
        """
        self._biomass_data = []
        self._cfu_data = []
        self._run_start_time = time.monotonic()
        self._end_alert_shown = False  # Latch so the end_alert popup fires once per run

        # Don't poll immediately — run folder doesn't exist yet
    # First poll fires after 30 seconds
        if not getattr(self, "_shutting_down", False):
            self.root.after(30000, self._comms_poll)


    def _comms_poll(self) : 
        """
        Reads comms.json every 30 seconds and updates graph + stage.
        Reschedules itself while experiment is running
        """
        from config import load_app_settings
        from run_metadata import read_comms_file
        s = load_app_settings()
        standalone = s.get("standalone_mode", True)

        
        if not standalone and self.controller.is_running : 
            st = self.controller.get_status()
            run_folder = st.get("run_folder")
            
            # Run folder not created safeguard
            if run_folder is None : 
                if self.controller.is_running : 
                    self.root.after(5000, self._comms_poll)
                return

           
            if run_folder : 
                comms = read_comms_file(run_folder)
                if comms :
                    biomass = comms.get("current_biomass")
                    cfu_ml = comms.get("current_cfu_ml")
                    state = comms.get("current_state")
                    needs_redraw = False


                    if state is not None :
                        self._current_state_var.set(str(state).capitalize())
                        needs_redraw = True
                    else :
                        self._current_state_var.set("-")

                    if biomass is not None :
                        self._current_biomass_var.set(f"Biomass: {biomass:.3g}")
                        last_biomass = self._biomass_data[-1][1] if self._biomass_data else None
                        if biomass != last_biomass: # Only append if value changed
                            elapsed_h = (time.monotonic() - self._run_start_time) / 3600
                            self._biomass_data.append((elapsed_h, biomass))
                            needs_redraw = True
                    else :
                        self._current_biomass_var.set("Biomass: —")

                    if cfu_ml is not None :
                        self._current_cfu_var.set(f"CFU/mL: {cfu_ml:.3g}")
                        last_cfu = self._cfu_data[-1][1] if self._cfu_data else None
                        if cfu_ml != last_cfu: # Only append if value changed
                            elapsed_h = (time.monotonic() - self._run_start_time) / 3600
                            self._cfu_data.append((elapsed_h, cfu_ml))
                            needs_redraw = True
                    else :
                        self._current_cfu_var.set("CFU/mL: —")

                    if needs_redraw:
                        self._update_biomass_graph() # State changed but biomass didn't update anyway

                    # Partner ML sets end_alert once the culture has been in
                    # stationary/death for consecutive reads. Surface it once as a
                    # GUI warning (via the controller alert path, which the status
                    # poll loop turns into a popup) so the operator can act on it.
                    if comms.get("end_alert") and not getattr(self, "_end_alert_shown", False):
                        self._end_alert_shown = True
                        self.controller.update_status(
                            last_message="END ALERT: partner detected sustained stationary/death phase.",
                            last_message_category="red",
                            alert_message=(
                                "END ALERT\n\n"
                                "The analysis machine reports the culture has been in a "
                                "stationary/death phase for consecutive readings.\n\n"
                                "Consider ending the run and turning the bioreactor off."
                            ),
                        )




        # Reschedule if still running
        if self.controller.is_running and not getattr(self, "_shutting_down", False):
            self.root.after(30000, self._comms_poll)



    def _set_graph_metric(self, metric) :
        """
        Switches which metric (biomass or cfu_ml) drives the trend graph and
        highlights the active tab. The two live on very different scales
        (g/L vs. a raw cell count), so only one is ever plotted at a time.
        """
        if metric == self._graph_metric :
            return
        self._graph_metric = metric
        self._biomass_tab.configure(
            bg=TECHMI_BLUE if metric == "biomass" else "#eef2ff",
            fg="white" if metric == "biomass" else TEXT_MUTED,
        )
        self._cfu_tab.configure(
            bg=TECHMI_BLUE if metric == "cfu_ml" else "#eef2ff",
            fg="white" if metric == "cfu_ml" else TEXT_MUTED,
        )
        self._update_biomass_graph()

    def _update_biomass_graph(self) :
        """
        Redraws the matplotlib graph with the currently selected metric's data
        (biomass or CFU/mL — see _set_graph_metric).
        """
        from config import load_app_settings

        s = load_app_settings()
        standalone = s.get("standalone_mode", True)

        metric = getattr(self, "_graph_metric", "biomass")
        data = self._biomass_data if metric == "biomass" else self._cfu_data
        metric_label = "Biomass" if metric == "biomass" else "CFU/mL"

        self._bio_ax.clear()
        self._bio_ax.set_facecolor("#f8fafc")

        # Gate the placeholder purely on whether any data has actually been
        # collected for the run currently being displayed — not on the
        # *current* standalone_mode setting, which can be toggled in
        # Settings after a collaborative run finishes (e.g. planning the
        # next run) and would otherwise hide that run's real data. The
        # standalone check is only used to pick the placeholder wording.
        if not data :
            placeholder_text = "Standalone mode\n(no biomass/CFU data)" if standalone else "Awaiting data..."
            self._bio_ax.text(0.5, 0.5,
                              placeholder_text,
                              ha="center", va="center",
                              transform=self._bio_ax.transAxes,
                              color=TEXT_MUTED, fontsize=7)
            self._bio_ax.set_xticks([])
            self._bio_ax.set_yticks([])
            self._bio_ax.set_title(
                f"Estimated Stage: -",
                fontsize=8, color=TEXT_MUTED, pad=2,  fontweight="bold"
            )


        else :
            xs = [p[0] for p in data]
            ys = [p[1] for p in data]

            self._bio_ax.clear()
            self._bio_ax.set_facecolor("#f8fafc")
            self._bio_ax.plot(xs, ys, color=TECHMI_BLUE, linewidth=1.2,
                            marker="o", markersize=3)
            self._bio_ax.set_xlabel("Elapsed(h)", fontsize=7, color=TEXT_MUTED)
            self._bio_ax.set_ylabel(metric_label, fontsize=7, color=TEXT_MUTED)
            self._bio_ax.tick_params(labelsize=6, colors=TEXT_MUTED)
            self._bio_ax.set_title(
                f"Estimated Stage: {self._current_state_var.get()}",
                fontsize=8, color=TEXT_MUTED, pad=2, fontweight="bold"
            )

        for spine in self._bio_ax.spines.values():
            spine.set_edgecolor(CARD_BORDER)

        from matplotlib.ticker import MaxNLocator
        self._bio_ax.xaxis.set_major_locator(MaxNLocator(nbins=4, prune="both"))

        self._bio_fig.tight_layout(pad=0.8)
        self._bio_canvas.draw()


    # ── System health checks ──────────────────────────────────────────────────
    def _init_health_system(self):
        """
        Call once after the UI is built. Starts the recurring background
        health check (camera / laser / storage) and the recovery panel's
        first disk scan.
        """
        self._recovery_dirty = True
        self._prev_is_running = False
        self._biomass_data = []
        self._cfu_data = []
        self._run_start_time = None
        self._run_health_check()
        self.update_recovery_panel()
        self._update_biomass_graph()

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
            # Drive unmounted, network path dropped, etc. — treat as a failed
            # check rather than crashing the health-check loop.
            storage_ok = False

        streak = getattr(self, "_storage_failure_streak", 0)
        if storage_ok:
            streak = 0
        else:
            streak += 1
        self._storage_failure_streak = streak

        # Don't report the drive as down until it's failed several checks in
        # a row — a single missed check is treated as a transient blip, not
        # a real disconnect, so it doesn't trip the hardware-fault stop below.
        if not storage_ok and 0 < streak < STORAGE_FAILURE_TOLERANCE:
            self._append_log(
                f"Storage check failed ({streak}/{STORAGE_FAILURE_TOLERANCE}) — retrying...",
                "yellow",
            )
        reported_storage_ok = storage_ok or streak < STORAGE_FAILURE_TOLERANCE
        self._apply_health_result("Storage", reported_storage_ok)

        # ── Laser ────────────────────────────────────────────────────────────
        try:
            laser_ok = LaserRelay().find_port() is not None
        except Exception:
            laser_ok = False
        self._apply_health_result("Laser Module", laser_ok)

        # ── Camera ───────────────────────────────────────────────────────────
        if self._preview_running or self.controller.is_running:
            self._apply_health_result("Camera", True)
        elif not self._camera_health_in_progress:
            try:
                cam_idx = self.get_selected_camera_index()
            except RuntimeError:
                self._apply_health_result("Camera", False)
            else:
                self._camera_health_in_progress = True
                threading.Thread(
                    target=self._camera_health_worker,
                    args=(cam_idx,),
                    daemon=True
                ).start()

        
        # Reschedule.
        if not getattr(self, "_shutting_down", False) :
            self._health_check_after_id = self.root.after(HEALTH_CHECK_INTERVAL_MS, self._run_health_check)

    def _camera_health_worker(self, cam_idx):
        """
        Runs on a background thread: briefly opens the camera to confirm
        it produces a frame, then hands the result back to the GUI thread.
        """
        try:
            ok = camera_can_capture(cam_idx)
        except Exception:
            ok = False
        def _done():
            self._camera_health_in_progress = False
            self._apply_health_result("Camera", ok)
        self.root.after(0, _done)

    def _apply_health_result(self, item, ok: bool):
        """
        Updates one health-checklist row and refreshes the overall
        system-ready indicators (topbar pill + sidebar card).

        If system health is critical and an experiment is running, 
        signals are sent to stop experiment as soon as error is detected. 
        """
        prev_state = self._health_state.get(item)
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

        # Signal a running experiment when a critical device's health
        # changes, in either direction — set the fault when it goes down so
        # the run can react (and, once it has captured at least one image,
        # keep running in a degraded state instead of aborting), and clear
        # it on recovery so the degraded banner and log can reflect that the
        # problem is gone. Per-item tracking so an unrelated item's fault
        # isn't accidentally cleared/clobbered by this one.
        if self.controller.is_running :
            if not ok and prev_state is True :
                self.controller.set_hardware_fault(item, f"{item} disconnected during experiment")
            elif ok and prev_state is False :
                self.controller.clear_hardware_fault(item)

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
        if ts is None:
            return "—"
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
        win.geometry("800x700")
        win.configure(bg=OFF_WHITE)
        win.resizable(False, False)
        win.grab_set()

        if not hasattr(self,"_standalone_mode_var") : 
            self._standalone_mode_var = tk.BooleanVar(value=load_app_settings().get("standalone_mode", True))
        if not hasattr(self, "_retrain_model_var") :
            self._retrain_model_var = tk.BooleanVar(value=load_app_settings().get("retrain_model", False))
        if not hasattr(self, "_handshake_timeout_var") :
            self._handshake_timeout_var = tk.StringVar(value=str(load_app_settings().get("handshake_timeout_hours", 1.0)))

        tk.Label(win,
                 text="Settings",
                 fg=NAVY,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 15, "bold")).pack(pady=(18, 14))

        # ── Laser device selector ────────────────────────────────────────────────────
        import serial.tools.list_ports as stlp

        fr = tk.Frame(win, bg=OFF_WHITE)
        fr.pack(fill=tk.X, padx=28, pady=6)
        
        tk.Label(fr,
                 text="Laser Relay Device:",
                 fg=TEXT_DARK,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 11),
                 width=20,
                 anchor="w").pack(side=tk.LEFT)

        if not hasattr(self, "_laser_port_var") : 
            self._laser_port_var = tk.StringVar(value="Auto-detect")

        def _get_port_options() :
            try:  
                ports = stlp.comports()
                options = ["Auto-detect"]
                for p in sorted(ports, key=lambda x: x.device) : 
                    options.append(f"{p.device} - {p.description}")
                if ports == None : 
                    return ["Auto-detect"]
                return options
            except Exception : 
                return ["Auto-detect"]
            
            
            
        port_options = _get_port_options()

        laser_menu = tk.OptionMenu(fr, self._laser_port_var, *port_options)
        laser_menu.configure(
            font=(FONT_BRAND, 10),
            bg="white",
            fg=TEXT_DARK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            width=28
        )
        laser_menu.pack(side=tk.LEFT, padx=(0,0))

        def _refresh_ports() :
            menu = laser_menu["menu"]
            menu.delete(0, "end")
            for opt in _get_port_options() :
                menu.add_command(label=opt, command=lambda value=opt: self._laser_port_var.set(value))

        _btn(fr, "↻", _refresh_ports, "primary").pack(side=tk.LEFT)

        # ── Identify Cameras ──────────────────────────────────────────────────
        fr_id = tk.Frame(win, bg=OFF_WHITE)
        fr_id.pack(fill=tk.X, padx=28, pady=6)

        tk.Label(fr_id,
                 text="Camera Labels:",
                 fg=TEXT_DARK,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 11),
                 width=20,
                 anchor="w").pack(side=tk.LEFT)

        _btn(fr_id, "Identify Cameras…",
             lambda: self._open_identify_cameras_window(win),
             "secondary").pack(side=tk.LEFT)



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

        if not hasattr(self, "_data_root_var") : 
            self._data_root_var = tk.StringVar(value=str(self.current_folder.parent))

        tk.Label(fr3,
                 textvariable=self._data_root_var,
                 fg=TEXT_MUTED,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 10),
                 wraplength=500,
                 anchor="w",
                 justify="left").pack(side=tk.LEFT)
        
        def _browse() : 
            chosen = filedialog.askdirectory(title="Select Data Root Folder", initialdir=self._data_root_var.get())
            if chosen : 
                self._data_root_var.set(chosen)

        browse_btn = _btn(fr3, "Browse", _browse, "primary")
        browse_btn.pack(side=tk.LEFT, padx=(24,0))

        if self.controller.is_running :
            browse_btn.configure(state="disabled")

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

        def _toggle_collab_options()  :
            # Retrain and timeout only make sense in collaborative mode
            state = "disabled" if self._standalone_mode_var.get() else "normal"
            if self._standalone_mode_var.get() :
                self._retrain_model_var.set(False)
            retrain_chk.configure(state=state)
            timeout_entry.configure(state=state)
            timeout_label.configure(state=state)


        # Standalone mode row with info icon
        standalone_row = tk.Frame(win, bg=OFF_WHITE)
        standalone_row.pack(fill=tk.X, padx=28, pady=(6, 2))
        tk.Checkbutton(
            standalone_row,
            text="Standalone mode (no partner machine)",
            variable=self._standalone_mode_var,
            bg=OFF_WHITE, fg=TEXT_DARK, font=(FONT_BRAND, 11),
            activebackground=OFF_WHITE,
            command=_toggle_collab_options
        ).pack(side=tk.LEFT)
        _info_icon(
            standalone_row,
            "When enabled, the experiment runs without communicating with the\n"
            "partner machine. No comms.json is written, no handshake is required,\n"
            "and the run completes immediately. Use this for solo testing.",
            bg=OFF_WHITE
        ).pack(side=tk.LEFT, padx=(6, 0))

        # Retrain model row with info icon
        retrain_row = tk.Frame(win, bg=OFF_WHITE)
        retrain_row.pack(fill=tk.X, padx=28, pady=(0, 2))
        retrain_chk = tk.Checkbutton(
            retrain_row,
            text="Retrain model after each run",
            variable=self._retrain_model_var,
            bg=OFF_WHITE, fg=TEXT_DARK, font=(FONT_BRAND, 11),
            activebackground=OFF_WHITE
        )
        retrain_chk.pack(side=tk.LEFT)
        _info_icon(
            retrain_row,
            "After the run completes, you will be prompted to upload a sensor\n"
            "data CSV. The experiment will then wait for the partner machine to\n"
            "finish retraining before the run is moved to training/.",
            bg=OFF_WHITE
        ).pack(side=tk.LEFT, padx=(6, 0))

        timeout_frame = tk.Frame(win, bg=OFF_WHITE)
        timeout_frame.pack(fill=tk.X, padx=28, pady=(0, 4))
        timeout_label = tk.Label(timeout_frame, text="    Handshake / retrain timeout (hours):",
                 fg=TEXT_MUTED, bg=OFF_WHITE,
                 font=(FONT_BRAND, 10))
        timeout_label.pack(side=tk.LEFT, padx=(0, 8))
        timeout_entry = tk.Entry(timeout_frame, textvariable=self._handshake_timeout_var,
                 width=6, font=(FONT_BRAND, 10), relief="flat",
                 bg="white", fg=TEXT_DARK, highlightthickness=1,
                 highlightbackground=CARD_BORDER)
        timeout_entry.pack(side=tk.LEFT)


        
        _toggle_collab_options()

        # ── Divider + action buttons ──────────────────────────────────────────
        tk.Frame(win, bg=CARD_BORDER, height=1).pack(fill=tk.X, padx=28, pady=16)

        if self.controller.is_running:
            tk.Label(win,
                    text="⚠  Settings locked while experiment is running.",
                    fg=DANGER,
                    bg=OFF_WHITE,
                    font=(FONT_BRAND, 9, "bold")).pack(pady=(0, 8))
            
            def _disable_all(parent) :
                for child in parent.winfo_children() : 
                    try :
                        child.configure(state="disabled")
                    except tk.TclError : 
                        pass
                    _disable_all(child)
            _disable_all(win)

        btn_row = tk.Frame(win, bg=OFF_WHITE)
        btn_row.pack(padx=28)

        _settings_save_btn = _btn(btn_row, "Save",
             lambda: self._save_settings(win),
             "primary")
        _settings_save_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        cancel_btn = _btn(btn_row, "Cancel",
             win.destroy,
             "secondary")
        cancel_btn.pack(side=tk.LEFT)

        if self.controller.is_running : 
            _settings_save_btn.configure(state="disabled")
            cancel_btn.configure(state="normal")

    
    def _get_laser_port_override(self): 
        """
        Returns the raw COM port string from the settings dropdown,
        or None if "Auto-detect" is selected.
        """
        val = getattr(self, "_laser_port_var", None)
        if val is None : 
            return None
        
        raw = val.get()
        if raw == "Auto-detect" or not raw : 
            return None
        # Value is formatted as "COM3 - Description", extract just the port
        return raw.split(" - ")[0].strip()

    def _open_identify_cameras_window(self, parent_win):
        """
        Opens a window showing a captured frame from each camera index
        so the user can identify and rename them.
        """
        import cv2 as cv
        from PIL import Image, ImageTk

        iwin = tk.Toplevel(parent_win)
        iwin.title("Identify Cameras")
        iwin.configure(bg=OFF_WHITE)
        iwin.grab_set()

        tk.Label(iwin,
                 text="Loading camera previews…",
                 fg=TEXT_MUTED,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 10)).pack(pady=20, padx=20)

        iwin.update()

        # Grab one frame from each working camera
        cameras = self.available_cameras
        frames = {}
        for cam in cameras:
            idx = cam["index"]
            cap = cv.VideoCapture(idx, cv.CAP_MSMF)
            if cap.isOpened():
                for _ in range(SETTLE_FRAMES):
                    cap.read()
                ok, frame = cap.read()
                if ok and frame is not None:
                    frames[idx] = frame

            cap.release()

        # Clear loading label
        for w in iwin.winfo_children():
            w.destroy()

        if not frames:
            tk.Label(iwin,
                     text="No cameras could be opened.",
                     fg=DANGER,
                     bg=OFF_WHITE,
                     font=(FONT_BRAND, 10)).pack(pady=20, padx=20)
            _btn(iwin, "Close", iwin.destroy, "secondary").pack(pady=8)
            return

        tk.Label(iwin,
                 text="Identify your cameras by the preview below.",
                 fg=TEXT_MUTED,
                 bg=OFF_WHITE,
                 font=(FONT_BRAND, 9)).pack(pady=(12, 4), padx=20)

        frame_row = tk.Frame(iwin, bg=OFF_WHITE)
        frame_row.pack(padx=20, pady=8)

        THUMB_W, THUMB_H = 320, 200
        self._camera_preview_images = []

        for col, cam in enumerate(cameras):
            idx = cam["index"]
            col_frame = tk.Frame(frame_row, bg=OFF_WHITE)
            col_frame.grid(row=0, column=col, padx=12)

            if idx in frames:
                img = frames[idx]
                h, w = img.shape[:2]
                scale = min(THUMB_W / w, THUMB_H / h)
                nw, nh = int(w * scale), int(h * scale)
                resized = cv.resize(img, (nw, nh))
                rgb = cv.cvtColor(resized, cv.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb)
                tkimg = ImageTk.PhotoImage(pil)
                self._camera_preview_images.append(tkimg)
                tk.Label(col_frame, image=tkimg, bg="#000000").pack()
            else:
                tk.Label(col_frame,
                         text="Could not\ncapture frame",
                         bg="#1a1a2e", fg=TEXT_MUTED,
                         width=30, height=8,
                         font=(FONT_BRAND, 9)).pack()

            tk.Label(col_frame,
                     text=f"Index {idx}",
                     fg=TEXT_MUTED,
                     bg=OFF_WHITE,
                     font=(FONT_BRAND, 8)).pack(pady=(4, 2))

            tk.Label(col_frame,
                     text=cam["name"],
                     font=(FONT_BRAND, 10),
                     bg=OFF_WHITE,
                     fg=TEXT_DARK).pack()

        btn_row = tk.Frame(iwin, bg=OFF_WHITE)
        btn_row.pack(pady=12)
        _btn(btn_row, "Close", iwin.destroy, "secondary").pack()
    

    def _save_settings(self, win):
        """
        Saves settings and closes the Settings window.
        """
        
        if not self.controller.is_running : 
            new_root = getattr(self, "_data_root_var", None)
            if new_root:
                current_root = str(self.current_folder.parent)
                new_root_str = new_root.get()
                if new_root.get() != current_root: 
                    settings = load_app_settings()
                    settings["data_root"] = new_root.get()
                    save_app_settings(settings)
                    
                    # Hot swap live paths, should ONLY be done in idle state
                    from pathlib import Path
                    self.current_folder=  Path(new_root_str) / "current"
                    self.training_folder = Path(new_root_str) / "training"
                    self.current_folder.mkdir(parents=True, exist_ok=True)
                    self.training_folder.mkdir(parents=True, exist_ok=True)

                    # Force recovery panel to rescan against new location
                    self._recovery_dirty = True

                    self._append_log(f"Data root changed to {new_root_str}.", "gray")

        # Settings
        settings = load_app_settings() 
        settings["standalone_mode"] = self._standalone_mode_var.get()
        settings["retrain_model"] = self._retrain_model_var.get()
        try :
            settings["handshake_timeout_hours"] = float(
                getattr(self, "_handshake_timeout_var", tk.StringVar(value="1.0")).get())
            
        except ValueError :
            settings["handshake_timeout_hours"] = 1.0
        
        save_app_settings(settings)
        
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
        win.geometry("420x300")
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
            f"Moved {moved} run(s), skipped {skipped} invalid runs")
        self._append_log(f"Recovery: moved {moved}, skipped {skipped} invalid runs", "gray")

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
        state = "normal" if (has and not self.controller.is_running) else "disabled"

        try:
            self.recovery_button.configure(state=state)
            if state == "normal" : 
                self.recovery_button.configure(bg=TECHMI_BLUE, fg="white", font=(FONT_BRAND, 10, "bold"))
            else : 
                self.recovery_button.configure(bg=CARD_BG, fg=TEXT_MUTED, font=(FONT_BRAND, 10, "normal"))
                
        except Exception:
            pass

    def _show_run_summary(self, run_folder, captures, elapsed, done_data=None):
        """
        Shows a popup summary when a run finishes and moves to training.

        done_data, if provided, is the parsed DONE.json for the run — used
        to flag runs that completed despite hitting capture/hardware faults
        along the way, so a run with data gaps isn't mistaken for a clean one.
        """

        msg = (
            f"Run completed successfully.\n\n"
            f"Captures saved: {captures}\n"
            f"Elapsed time:   {format_elapsed(elapsed)}\n\n"
            f"Folder: {run_folder}"
        )

        done_data = done_data or {}
        if done_data.get("had_errors") :
            reasons = done_data.get("failure_reasons", [])
            msg += (
                f"\n\n⚠ This run was degraded: "
                f"{done_data.get('failed_capture_count', 0)} failed capture attempt(s).\n"
                f"Reasons encountered:\n- " + "\n- ".join(reasons)
            )

        messagebox.showinfo("Run Complete", msg)
