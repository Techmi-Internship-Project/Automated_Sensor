import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import re
import time
import math
from pathlib import Path
from PIL import Image, ImageTk

from gui_theme import (
    CARD_BG,
    CARD_BORDER,
    FONT_BRAND,
    TECHMI_BLUE,
    TEXT_DARK,
    TEXT_MUTED,
    _btn,
    _card,
    _section_label,
)
from organism_menu import get_organism_options


class SetupPanelMixin:
    """
    GUI section mixin split out of the original SensorGUI class.
    """

    def _build_setup_panel(self, parent):
            card, c = _card(parent, "SETUP", "⚙")
            card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
            c.grid_columnconfigure(0, weight=1)
            c.grid_columnconfigure(1, weight=0)

            # Organism
            _section_label(c, "Organism").grid(row=0, column=0, columnspan=2,
                                               sticky="w", pady=(0, 4))

            self._organism_options = get_organism_options(self.training_folder)
            if self._organism_options:
                self.organism.set(self._organism_options[0])
            else:
                self.organism.set("")

            self.organism_var_frame = tk.Frame(c, bg=CARD_BG,
                                               highlightthickness=1,
                                               highlightbackground=CARD_BORDER)
            self.organism_var_frame.grid(row=1, column=0, columnspan=2,
                                         sticky="ew", pady=(0, 6))
            self.organism_var_frame.grid_columnconfigure(0, weight=1)

            self._org_display = tk.Label(
                self.organism_var_frame,
                textvariable=self.organism,
                bg="white", fg=TEXT_DARK,
                font=(FONT_BRAND, 11),
                anchor="w", padx=10, pady=6
            )
            self._org_display.grid(row=0, column=0, sticky="ew")

            self._org_arrow = tk.Label(
                self.organism_var_frame, text="▾",
                bg="white", fg=TEXT_MUTED,
                font=(FONT_BRAND, 13), padx=8
            )
            self._org_arrow.grid(row=0, column=1)

            # Bind click to show menu
            for w in (self._org_display, self._org_arrow, self.organism_var_frame):
                w.bind("<Button-1>", self._show_organism_menu)

            self.create_organism_btn = _btn(c, "+  Create New Organism",
                                            self.create_new_organism)
            self.create_organism_btn.grid(row=2, column=0, columnspan=2,
                                          sticky="ew", pady=(0, 12))
            self._idle_only_widgets.append(self.create_organism_btn)

            # Camera
            _section_label(c, "Camera").grid(row=3, column=0, columnspan=2,
                                             sticky="w", pady=(0, 4))

            self.load_available_cameras()
            cam_opts = list(self.camera_label_to_index.keys())
            if cam_opts:
                self.selected_camera.set(cam_opts[0])
            else:
                cam_opts = ["No cameras found"]
                self.selected_camera.set(cam_opts[0])

            cam_fr = tk.Frame(c, bg=CARD_BG, highlightthickness=1,
                              highlightbackground=CARD_BORDER)
            cam_fr.grid(row=4, column=0, sticky="ew", pady=(0, 6), padx=(0, 6))
            cam_fr.grid_columnconfigure(0, weight=1)
            self._cam_display = tk.Label(cam_fr, textvariable=self.selected_camera,
                                         bg="white", fg=TEXT_DARK,
                                         font=(FONT_BRAND, 11),
                                         anchor="w", padx=10, pady=6)
            self._cam_display.grid(row=0, column=0, sticky="ew")
            tk.Label(cam_fr, text="▾", bg="white", fg=TEXT_MUTED,
                     font=(FONT_BRAND, 13), padx=8).grid(row=0, column=1)
            for w in (self._cam_display, cam_fr):
                w.bind("<Button-1>", self._show_camera_menu)

            self._refresh_cam_btn = _btn(c, "↻", self.refresh_camera_menu_on_open,
                                         kind="ghost")
            self._refresh_cam_btn.grid(row=4, column=1, sticky="ew", pady=(0, 6))
            self._idle_only_widgets.append(self._refresh_cam_btn)

            # Handle Old Runs
            self.recovery_button = _btn(c, "▭  Handle Old Runs",
                                        self.open_recovery_window)
            self.recovery_button.grid(row=5, column=0, columnspan=2,
                                      sticky="ew", pady=(4, 0))
            self._idle_only_widgets.append(self.recovery_button)

    def _show_organism_menu(self, event=None):
            if self.controller.is_running:
                return
            menu = tk.Menu(self.root, tearoff=0,
                           font=(FONT_BRAND, 11),
                           bg="white", fg=TEXT_DARK,
                           activebackground=TECHMI_BLUE,
                           activeforeground="white",
                           relief="flat", bd=1)
            opts = get_organism_options(self.training_folder)
            if not opts:
                menu.add_command(label="(no organisms)", state="disabled")
            for o in opts:
                menu.add_command(label=o,
                                 command=lambda v=o: self.organism.set(v))
            try:
                menu.tk_popup(self._org_display.winfo_rootx(),
                              self._org_display.winfo_rooty() +
                              self._org_display.winfo_height())
            finally:
                menu.grab_release()

    def _show_camera_menu(self, event=None):
            if self.controller.is_running:
                return
            self.refresh_camera_menu_on_open()
            opts = list(self.camera_label_to_index.keys())
            if not opts:
                return
            menu = tk.Menu(self.root, tearoff=0,
                           font=(FONT_BRAND, 11), bg="white", fg=TEXT_DARK,
                           activebackground=TECHMI_BLUE,
                           activeforeground="white",
                           relief="flat", bd=1)
            for o in opts:
                menu.add_command(label=o,
                                 command=lambda v=o: self.selected_camera.set(v))
            try:
                menu.tk_popup(self._cam_display.winfo_rootx(),
                              self._cam_display.winfo_rooty() +
                              self._cam_display.winfo_height())
            finally:
                menu.grab_release()

