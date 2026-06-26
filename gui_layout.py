import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import re
import time
import math
from pathlib import Path
from PIL import Image, ImageTk

from gui_theme import (
    NAVY,
    NAVY_2,
    OFF_WHITE,
    TECHMI_BLUE,
    FONT_BRAND,
    _btn,
)


class LayoutMixin:
    """
    GUI section mixin split out of the original SensorGUI class.
    """

    def _build_ui(self):
            self.root.grid_rowconfigure(0, weight=0)
            self.root.grid_rowconfigure(1, weight=1)
            self.root.grid_columnconfigure(0, weight=1)

            self._build_topbar()
            self._build_main_area()

    def _build_topbar(self):
            bar = tk.Frame(self.root, bg=NAVY, height=56)
            bar.grid(row=0, column=0, sticky="ew")
            bar.grid_propagate(False)
            bar.grid_columnconfigure(1, weight=1)

            # Logo
            logo_fr = tk.Frame(bar, bg=TECHMI_BLUE, padx=20, pady=8)
            logo_fr.grid(row=0, column=0, sticky="ns")
            tk.Label(logo_fr, text="TECHMI", fg="white", bg=TECHMI_BLUE,
                     font=(FONT_BRAND, 20, "bold")).pack()

            # Title
            tk.Label(bar, text="Bioreactor Sensor Control Panel",
                     fg="white", bg=NAVY,
                     font=(FONT_BRAND, 16, "bold")).grid(row=0, column=1,
                                                         padx=20, sticky="w")

            # Right side: system ready + settings
            right = tk.Frame(bar, bg=NAVY)
            right.grid(row=0, column=2, padx=16, sticky="e")

            # System ready pill
            self.system_ready_lbl = tk.Label(
                right, text="⬤  System Ready",
                fg="#d1fae5", bg="#0d2e1a",
                font=(FONT_BRAND, 11, "bold"),
                padx=12, pady=5, relief="flat"
            )
            self.system_ready_lbl.pack(side=tk.LEFT, padx=(0, 12))

            _btn(right, "⚙  Settings", self._open_settings_window,
                 kind="dark").pack(side=tk.LEFT)

    def _build_main_area(self):
            main = tk.Frame(self.root, bg=OFF_WHITE)
            main.grid(row=1, column=0, sticky="nsew")
            main.grid_rowconfigure(0, weight=1)
            main.grid_columnconfigure(0, weight=0)   # sidebar
            main.grid_columnconfigure(1, weight=1)   # content

            self._build_sidebar(main)
            self._build_content(main)

    def _build_sidebar(self, parent):
            sb = tk.Frame(parent, bg=NAVY, width=170)
            sb.grid(row=0, column=0, sticky="ns")
            sb.grid_propagate(False)
            sb.grid_rowconfigure(3, weight=1)

            # Dashboard nav (active)
            active = tk.Frame(sb, bg=TECHMI_BLUE, padx=0, pady=0)
            active.grid(row=0, column=0, sticky="ew", padx=10, pady=(20, 4))
            tk.Label(active, text="⌂  Dashboard", fg="white", bg=TECHMI_BLUE,
                     font=(FONT_BRAND, 12, "bold"), padx=14, pady=10,
                     anchor="w").pack(fill=tk.X)

            # Settings nav
            settings_nav = tk.Label(sb, text="⚙  Settings", fg="#9db5d4", bg=NAVY,
                                    font=(FONT_BRAND, 11), padx=22, pady=12,
                                    anchor="w", cursor="hand2")
            settings_nav.grid(row=1, column=0, sticky="ew")
            settings_nav.bind("<Button-1>", lambda e: self._open_settings_window())

            # Version
            tk.Label(sb, text="v1.0.0", fg="#3d5a80", bg=NAVY,
                     font=(FONT_BRAND, 9)).grid(row=4, column=0, pady=12)

            # All systems nominal
            nom = tk.Frame(sb, bg=NAVY_2, padx=10, pady=10)
            nom.grid(row=3, column=0, sticky="sew", padx=10, pady=12)
            tk.Label(nom, text="⬤  All Systems", fg="#bbf7d0", bg=NAVY_2,
                     font=(FONT_BRAND, 10, "bold"), anchor="w").pack(fill=tk.X)
            tk.Label(nom, text="   Nominal", fg="#6ee7b7", bg=NAVY_2,
                     font=(FONT_BRAND, 10), anchor="w").pack(fill=tk.X)

    def _build_content(self, parent):
            # Scrollable canvas
            outer = tk.Frame(parent, bg=OFF_WHITE)
            outer.grid(row=0, column=1, sticky="nsew")
            outer.grid_rowconfigure(0, weight=1)
            outer.grid_columnconfigure(0, weight=1)

            canvas = tk.Canvas(outer, bg=OFF_WHITE, highlightthickness=0, bd=0)
            scrollbar = ttk.Scrollbar(outer, orient="vertical",
                                      command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)

            scrollbar.grid(row=0, column=1, sticky="ns")
            canvas.grid(row=0, column=0, sticky="nsew")

            content_frame = tk.Frame(canvas, bg=OFF_WHITE)
            canvas_window = canvas.create_window((0, 0), window=content_frame,
                                                  anchor="nw")

            def _on_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.itemconfig(canvas_window, width=canvas.winfo_width())

            content_frame.bind("<Configure>", _on_configure)
            canvas.bind("<Configure>",
                        lambda e: canvas.itemconfig(canvas_window,
                                                    width=e.width))

            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

            # Two-column layout inside content_frame
            content_frame.grid_columnconfigure(0, weight=1, minsize=520)
            content_frame.grid_columnconfigure(1, weight=1, minsize=620)

            left  = tk.Frame(content_frame, bg=OFF_WHITE)
            left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
            left.grid_columnconfigure(0, weight=1)

            right = tk.Frame(content_frame, bg=OFF_WHITE)
            right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
            right.grid_columnconfigure(0, weight=1)

            # Left column panels
            self._build_setup_panel(left)
            self._build_timing_panel(left)
            self._build_run_control_panel(left)
            self._build_live_status_panel(left)
            self._build_log_panel(left)

            # Right column panels
            self._build_camera_preview_panel(right)
            self._build_camera_settings_panel(right)
            self._build_recovery_panel(right)

