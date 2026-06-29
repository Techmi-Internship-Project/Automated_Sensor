"""
gui_layout.py

Builds the top-level window shell: sidebar, topbar, and the two-column
scrollable dashboard grid.  Panel content is built by the mixin files.

Layout overview
---------------
root (tk.Tk)
  ├── sidebar  (col 0, rows 0-1)  fixed width, full height
  ├── topbar   (row 0, col 1)     fixed height strip
  └── content  (row 1, col 1)     fills remaining space
        └── canvas + scrollbar    vertical scroll
              └── scroll_frame    two equal columns
                    ├── left_col  setup | timing | run-control | live-status
                    └── right_col preview | cam-settings | recovery | log
"""

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from PIL import Image, ImageTk

from gui_theme import (
    NAVY,
    NAVY_2,
    OFF_WHITE,
    TECHMI_BLUE,
    CARD_BG,
    CARD_BORDER,
    FONT_BRAND,
    _btn,
)

# ── Fixed layout constants ────────────────────────────────────────────────────
SIDEBAR_WIDTH  = 190
TOPBAR_HEIGHT  = 60
COL_PAD        = 6   # gap between the two dashboard columns
OUTER_PAD      = 12  # padding around the whole dashboard area


class LayoutMixin:
    """
    Builds the window chrome (sidebar, topbar) and the scrollable
    two-column dashboard grid.  All panel content is injected by
    the other mixin classes.
    """

    # ── Root layout ───────────────────────────────────────────────────────────
    def _build_ui(self):
        """
        Sets up the root window grid and calls each major section builder.
        """

        # Sidebar spans both root rows (row 0 = topbar, row 1 = content)
        self.root.grid_rowconfigure(0, weight=0, minsize=TOPBAR_HEIGHT)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=0, minsize=SIDEBAR_WIDTH)
        self.root.grid_columnconfigure(1, weight=1)

        # Build each section
        self._build_sidebar(self.root)
        self._build_topbar()
        self._build_content(self.root)

    # ── Topbar ────────────────────────────────────────────────────────────────
    def _build_topbar(self):
        """
        Creates the dark header strip with app title, system-ready pill,
        and settings button.  Sits in row 0 col 1 (to the right of sidebar).
        """

        bar = tk.Frame(self.root, bg=NAVY, height=TOPBAR_HEIGHT)
        bar.grid(row=0, column=1, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)  # title fills remaining space
        bar.grid_columnconfigure(1, weight=0)  # right buttons stay right

        # App title
        tk.Label(
            bar,
            text="Bioreactor Sensor Control Panel",
            fg="white",
            bg=NAVY,
            font=(FONT_BRAND, 16, "bold")
        ).grid(row=0, column=0, padx=20, sticky="w")

        # Right-side controls
        right = tk.Frame(bar, bg=NAVY)
        right.grid(row=0, column=1, padx=16, sticky="e")

        # System-ready status pill
        self.system_ready_lbl = tk.Label(
            right,
            text="⬤  System Ready",
            fg="#d1fae5",
            bg="#0d2e1a",
            font=(FONT_BRAND, 11, "bold"),
            padx=12,
            pady=7,
            relief="flat"
        )
        self.system_ready_lbl.pack(side=tk.LEFT, padx=(0, 12))

        # Settings button
        _btn(right, "⚙  Settings", self._open_settings_window,
             kind="dark").pack(side=tk.LEFT)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    def _build_sidebar(self, parent):
        """
        Creates the fixed left sidebar with logo, nav items, and status card.
        Spans both root rows so it runs full window height.
        """

        sb = tk.Frame(parent, bg=NAVY, width=SIDEBAR_WIDTH)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sb.grid_propagate(False)

        # Push the status card to the bottom by weighting an empty row
        sb.grid_rowconfigure(4, weight=1)

        # ── Logo area ─────────────────────────────────────────────────────────
        logo_frame = tk.Frame(sb, bg=NAVY,
                              width=SIDEBAR_WIDTH,
                              height=TOPBAR_HEIGHT)
        logo_frame.grid(row=0, column=0, sticky="ew")
        logo_frame.grid_propagate(False)

        # Try to load logo image; fall back to text if it fails
        try:
            logo_img = Image.open("logo_azul.png").convert("RGBA")
            target_h = TOPBAR_HEIGHT - 14
            scale    = target_h / logo_img.height
            target_w = min(int(logo_img.width * scale), SIDEBAR_WIDTH - 20)
            logo_img = logo_img.resize((target_w, target_h), Image.LANCZOS)

            # Keep a reference so Tkinter does not garbage-collect it
            self._topbar_logo_photo = ImageTk.PhotoImage(logo_img)
            logo_lbl = tk.Label(logo_frame,
                                image=self._topbar_logo_photo,
                                bg=NAVY)
            logo_lbl.place(relx=0.5, rely=0.5, anchor="center")

        except Exception:
            self._topbar_logo_photo = None
            tk.Label(logo_frame,
                     text="TECHMI",
                     fg="white",
                     bg=NAVY,
                     font=(FONT_BRAND, 18, "bold")).place(
                relx=0.5, rely=0.5, anchor="center")

        # ── Dashboard nav (active highlight) ──────────────────────────────────
        active_frame = tk.Frame(sb, bg=TECHMI_BLUE)
        active_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 4))

        tk.Label(
            active_frame,
            text="⌂  Dashboard",
            fg="white",
            bg=TECHMI_BLUE,
            font=(FONT_BRAND, 12, "bold"),
            padx=14,
            pady=10,
            anchor="w"
        ).pack(fill=tk.X)

        # ── Settings nav item ─────────────────────────────────────────────────
        settings_nav = tk.Label(
            sb,
            text="⚙  Settings",
            fg="#9db5d4",
            bg=NAVY,
            font=(FONT_BRAND, 11),
            padx=22,
            pady=12,
            anchor="w",
            cursor="hand2"
        )
        settings_nav.grid(row=2, column=0, sticky="ew")
        settings_nav.bind("<Button-1>",
                          lambda e: self._open_settings_window())

        # ── All Systems Nominal card ───────────────────────────────────────────
        nom = tk.Frame(sb, bg=NAVY_2, padx=10, pady=10)
        nom.grid(row=5, column=0, sticky="sew", padx=10, pady=(0, 4))

        tk.Label(nom,
                 text="⬤  All Systems",
                 fg="#bbf7d0",
                 bg=NAVY_2,
                 font=(FONT_BRAND, 10, "bold"),
                 anchor="w").pack(fill=tk.X)

        tk.Label(nom,
                 text="   Nominal",
                 fg="#6ee7b7",
                 bg=NAVY_2,
                 font=(FONT_BRAND, 10),
                 anchor="w").pack(fill=tk.X)

        # ── Version label ─────────────────────────────────────────────────────
        tk.Label(sb,
                 text="v1.0.0",
                 fg="#3d5a80",
                 bg=NAVY,
                 font=(FONT_BRAND, 9)).grid(row=6, column=0, pady=(2, 10))

    # ── Main content area ─────────────────────────────────────────────────────
    def _build_content(self, parent):
        """
        Builds the main dashboard content area.

        Layout model:

            Left region, columns 1 and 2:
                Setup | Experiment Timing
                Run Control
                Live Status
                Log / Messages

            Right region, column 3:
                Camera Preview
                Camera Settings
                Recovery / Summary

        The left and right regions have independent row systems. This is the key
        difference from trying to force everything into one shared dashboard grid.
        """

        # Main content area sits below the topbar and to the right of the sidebar.
        content = tk.Frame(parent, bg=OFF_WHITE)
        content.grid(row=1, column=1, sticky="nsew")

        # Let content fill all remaining space.
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        # Dashboard is the outer holder for the whole main area.
        dashboard = tk.Frame(content, bg=OFF_WHITE)
        dashboard.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=OUTER_PAD,
            pady=OUTER_PAD
        )

        # Conceptual 3-column layout:
        # columns 0 and 1 = left region
        # column 2       = right camera region
        dashboard.grid_columnconfigure(0, weight=1, uniform="main_cols")
        dashboard.grid_columnconfigure(1, weight=1, uniform="main_cols")
        dashboard.grid_columnconfigure(2, weight=2, uniform="main_cols")

        # Only one outer row. The left and right regions handle their own rows.
        dashboard.grid_rowconfigure(0, weight=1)

        # ── Left region: setup/timing + run/status/log ──────────────────────────
        left_region = tk.Frame(dashboard, bg=OFF_WHITE)
        left_region.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=(0, COL_PAD)
        )

        left_region.grid_columnconfigure(0, weight=1)
        left_region.grid_rowconfigure(0, weight=2)  # setup + timing
        left_region.grid_rowconfigure(1, weight=1)  # run control
        left_region.grid_rowconfigure(2, weight=2)  # live status
        left_region.grid_rowconfigure(3, weight=1)  # log

        # Top row inside left region: setup and timing sit side-by-side.
        top_left_region = tk.Frame(left_region, bg=OFF_WHITE)
        top_left_region.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=(0, COL_PAD)
        )

        top_left_region.grid_columnconfigure(0, weight=1, uniform="left_top")
        top_left_region.grid_columnconfigure(1, weight=1, uniform="left_top")
        top_left_region.grid_rowconfigure(0, weight=1)

        setup_slot = tk.Frame(top_left_region, bg=OFF_WHITE)
        setup_slot.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, COL_PAD)
        )
        setup_slot.grid_columnconfigure(0, weight=1)
        setup_slot.grid_rowconfigure(0, weight=1)

        timing_slot = tk.Frame(top_left_region, bg=OFF_WHITE)
        timing_slot.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(COL_PAD, 0)
        )
        timing_slot.grid_columnconfigure(0, weight=1)
        timing_slot.grid_rowconfigure(0, weight=1)

        # Run control spans the same width as setup + timing.
        run_slot = tk.Frame(left_region, bg=OFF_WHITE)
        run_slot.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(COL_PAD, COL_PAD)
        )
        run_slot.grid_columnconfigure(0, weight=1)
        run_slot.grid_rowconfigure(0, weight=1)

        # Live status spans the same width.
        status_slot = tk.Frame(left_region, bg=OFF_WHITE)
        status_slot.grid(
            row=2,
            column=0,
            sticky="nsew",
            pady=(COL_PAD, COL_PAD)
        )
        status_slot.grid_columnconfigure(0, weight=1)
        status_slot.grid_rowconfigure(0, weight=1)

        # Log spans the same width.
        log_slot = tk.Frame(left_region, bg=OFF_WHITE)
        log_slot.grid(
            row=3,
            column=0,
            sticky="nsew",
            pady=(COL_PAD, 0)
        )
        log_slot.grid_columnconfigure(0, weight=1)
        log_slot.grid_rowconfigure(0, weight=1)

        # ── Right region: camera preview/settings/recovery ──────────────────────
        right_region = tk.Frame(dashboard, bg=OFF_WHITE)
        right_region.grid(
            row=0,
            column=2,
            sticky="nsew",
            padx=(COL_PAD, 0)
        )

        right_region.grid_columnconfigure(0, weight=1)

        # These rows are independent from the left side.
        # Camera preview can be taller without forcing setup/timing to match it.
        right_region.grid_rowconfigure(0, weight=4)  # camera preview
        right_region.grid_rowconfigure(1, weight=2)  # camera settings
        right_region.grid_rowconfigure(2, weight=2)  # recovery summary

        preview_slot = tk.Frame(right_region, bg=OFF_WHITE)
        preview_slot.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=(0, COL_PAD)
        )
        preview_slot.grid_columnconfigure(0, weight=1)
        preview_slot.grid_rowconfigure(0, weight=1)

        camera_settings_slot = tk.Frame(right_region, bg=OFF_WHITE)
        camera_settings_slot.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(COL_PAD, COL_PAD)
        )
        camera_settings_slot.grid_columnconfigure(0, weight=1)
        camera_settings_slot.grid_rowconfigure(0, weight=1)

        recovery_slot = tk.Frame(right_region, bg=OFF_WHITE)
        recovery_slot.grid(
            row=2,
            column=0,
            sticky="nsew",
            pady=(COL_PAD, 0)
        )
        recovery_slot.grid_columnconfigure(0, weight=1)
        recovery_slot.grid_rowconfigure(0, weight=1)

        # ── Build panels into their slots ───────────────────────────────────────
        self._build_setup_panel(setup_slot, row=0)
        self._build_timing_panel(timing_slot, row=0)

        self._build_run_control_panel(run_slot, row=0)
        self._build_live_status_panel(status_slot, row=0)
        self._build_log_panel(log_slot, row=0)

        self._build_camera_preview_panel(preview_slot, row=0)
        self._build_camera_settings_panel(camera_settings_slot, row=0)
        self._build_recovery_panel(recovery_slot, row=0)