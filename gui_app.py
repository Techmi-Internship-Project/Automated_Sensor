"""
gui_app.py

Main entry point for the TECHMI Bioreactor Sensor GUI.

The large original GUI file has been split into panel/mixin files so each
section is easier to edit without touching unrelated code.
"""

import tkinter as tk
from tkinter import ttk
from pathlib import Path

from experiment_controller import ExperimentController
from gui_theme import (NAVY, TECHMI_BLUE, enable_windows_dpi_awareness)
from gui_layout import LayoutMixin
from gui_setup_panel import SetupPanelMixin
from gui_timing_panel import TimingPanelMixin
from gui_run_status_panel import RunStatusLogMixin
from gui_camera_panel import CameraPanelMixin
from gui_recovery_settings import RecoverySettingsMixin
from gui_backend_actions import BackendActionsMixin


class SensorGUI(
    LayoutMixin,
    SetupPanelMixin,
    TimingPanelMixin,
    RunStatusLogMixin,
    CameraPanelMixin,
    RecoverySettingsMixin,
    BackendActionsMixin,
):
    """
    TECHMI Bioreactor Sensor Control Panel.

    This class owns the shared state and root window.  The visual sections
    live in separate mixin files to keep the code easier to maintain.
    """

    def __init__(self, current_folder, training_folder):
            enable_windows_dpi_awareness()
            self.root = tk.Tk()
            self.root.title("TECHMI Bioreactor Sensor Control Panel")
            self.root.geometry("1920x1080")
            self.root.minsize(1100, 700)
            self.root.configure(bg=NAVY)

            self.controller    = ExperimentController()
            self.current_folder  = current_folder
            self.training_folder = training_folder
            self.current_folder.mkdir(parents=True, exist_ok=True)
            self.training_folder.mkdir(parents=True, exist_ok=True)
            self._active_log_path = None

            # ── StringVars ────────────────────────────────────────────────────────
            self.organism        = tk.StringVar()
            self.selected_camera = tk.StringVar()
            self.available_cameras       = []
            self.camera_label_to_index   = {}
            self.camera_label_to_name    = {}

            self.duration_days    = tk.StringVar(value="0")
            self.duration_hours   = tk.StringVar(value="0")
            self.duration_minutes = tk.StringVar(value="0")
            self.interval_hours   = tk.StringVar(value="0")
            self.interval_minutes = tk.StringVar(value="0")

            self.estimated_duration_text  = tk.StringVar(value="Total run time: —")
            self.estimated_capture_count  = 0
            self.estimated_finish_text    = tk.StringVar(value="Est. finish: —")
            self.capture_ratio = tk.StringVar(value="0 / 0")

            for v in (self.duration_days, self.duration_hours, self.duration_minutes,
                      self.interval_hours, self.interval_minutes):
                v.trace_add("write", lambda *_: self.update_timing_estimates()) # Tracer that calls function every new write

            self.status        = tk.StringVar(value="Idle")
            self.run_id_var    = tk.StringVar(value="—")
            self.error_var     = tk.StringVar(value="—")
            self.elapsed       = tk.StringVar(value="00:00:00")
            self.remaining     = tk.StringVar(value="—")
            self.progress_pct  = tk.DoubleVar(value=0.0)
            self.run_folder_var= tk.StringVar(value="—")
            self.last_img_var  = tk.StringVar(value="—")
            self.last_msg_var  = tk.StringVar(value="System idle.")

            self.capture_count = 0
            self.last_seen_alert_id = 0
            self.alert_popup_open   = False
            self.stop_requested     = False
            self.camera_setup_open  = False
            self.last_summary_dest  = None
            self._csv_uploaded = False
            self._csv_uploaded_prompted = False
            self._csv_upload_run_folder = None


            # Camera preview state
            self._preview_running   = False
            self._preview_cap       = None
            self._preview_after_id  = None
            self._preview_tk_img    = None
            self._show_overlay      = False
            self._laser             = None
            self._laser_on          = False
            self._logo_photo        = None

            # Camera settings state
            self.exposure_var       = tk.DoubleVar(value=-6)
            self.gain_var           = tk.DoubleVar(value=0)
            self.cam_profile        = tk.StringVar(value="normal")

            # Live adjustment buttons list for enable/disable
            self._run_adjust_btns = []
            self._idle_only_widgets = []
            self._end_after_next_requested = False
            self._status_loop_active = False  # Guard against reentrant update_status_loop

            # ttk style for progress bar
            self._style = ttk.Style()
            self._style.theme_use("clam")
            self._style.configure(
                "T.Horizontal.TProgressbar",
                troughcolor="#dce3ee",
                background=TECHMI_BLUE,
                bordercolor="#dce3ee",
                lightcolor=TECHMI_BLUE,
                darkcolor=TECHMI_BLUE,
                thickness=8
            )

            self._build_ui()
            self.update_timing_estimates()
            self._load_camera_profile_into_ui("normal")
            self._init_health_system()
            self.update_status_loop()
            self.root.protocol("WM_DELETE_WINDOW", self.confirm_exit)

    def run(self):
        """
        Starts the Tkinter event loop.
        """

        self.root.mainloop()
