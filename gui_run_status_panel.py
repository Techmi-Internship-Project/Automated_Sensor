import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import re
import time
import math
from pathlib import Path
from PIL import Image, ImageTk

from gui_theme import (
    CARD_BG,
    DANGER,
    FONT_BRAND,
    FONT_MONO,
    SUCCESS,
    TECHMI_BLUE,
    TEXT_DARK,
    TEXT_MUTED,
    _btn,
    _card,
    _section_label,
)

class RunStatusLogMixin:
    """
    GUI section mixin split out of the original SensorGUI class.
    """

    def _build_run_control_panel(self, parent):
            card, c = _card(parent, "RUN CONTROL", "▷")
            card.grid(row=2, column=0, sticky="ew", pady=(0, 8))
            c.grid_columnconfigure(0, weight=1)
            c.grid_columnconfigure(1, weight=1)

            self.start_button = _btn(c, "▶  Start Experiment",
                                     self.start_experiment, "primary", h=40)
            self.start_button.grid(row=0, column=0, sticky="ew",
                                   padx=(0, 6), pady=(0, 10))

            self.stop_button = _btn(c, "■  Stop Experiment",
                                    self.stop_experiment, "danger", h=40)
            self.stop_button.grid(row=0, column=1, sticky="ew",
                                  padx=(6, 0), pady=(0, 10))

            _section_label(c, "Live Run Adjustments").grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))

            af = tk.Frame(c, bg=CARD_BG)
            af.grid(row=2, column=0, columnspan=2, sticky="ew")
            af.grid_columnconfigure((0, 1, 2), weight=1)

            for i, (lbl, delta) in enumerate([("+1h", 3600),
                                               ("+6h", 21600),
                                               ("−1h", -3600)]):
                b = _btn(af, lbl,
                         lambda d=delta: self.controller.adjust_time(d),
                         "secondary")
                b.grid(row=0, column=i, sticky="ew", padx=3)
                self._run_adjust_btns.append(b)

    def _build_live_status_panel(self, parent):
            card, c = _card(parent, "LIVE STATUS", "▣")
            card.grid(row=3, column=0, sticky="ew", pady=(0, 8))
            c.grid_columnconfigure(0, weight=0)
            c.grid_columnconfigure(1, weight=1)

            # Donut canvas (left)
            self._donut_canvas = tk.Canvas(c, width=110, height=110,
                                           bg=CARD_BG, highlightthickness=0)
            self._donut_canvas.grid(row=0, column=0, rowspan=3,
                                    padx=(0, 16), pady=4, sticky="n")
            self._draw_donut(0)

            # Metrics grid (right)
            metrics = tk.Frame(c, bg=CARD_BG)
            metrics.grid(row=0, column=1, sticky="nsew")
            metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)

            for col, (label, var) in enumerate([
                ("Status",         self.status),
                ("Elapsed",        self.elapsed),
                ("Remaining",      self.remaining),
                ("Est. Finish",    self.estimated_finish_text),
            ]):
                tk.Label(metrics, text=label, fg=TEXT_MUTED, bg=CARD_BG,
                         font=(FONT_BRAND, 9, "bold")).grid(
                    row=0, column=col, sticky="w", padx=6, pady=(0, 2))
                fg = SUCCESS if label == "Status" else TEXT_DARK
                tk.Label(metrics, textvariable=var, fg=fg, bg=CARD_BG,
                         font=(FONT_BRAND, 11, "bold")).grid(
                    row=1, column=col, sticky="w", padx=6)

            # Captures + progress bar
            prog_fr = tk.Frame(c, bg=CARD_BG)
            prog_fr.grid(row=1, column=1, sticky="ew", pady=(10, 0))
            prog_fr.grid_columnconfigure(1, weight=1)

            tk.Label(prog_fr, text="Captures", fg=TEXT_MUTED, bg=CARD_BG,
                     font=(FONT_BRAND, 9, "bold")).grid(row=0, column=0,
                                                        sticky="w", padx=(0, 8))
            tk.Label(prog_fr, textvariable=self.capture_count,
                     fg=TEXT_DARK, bg=CARD_BG,
                     font=(FONT_BRAND, 11, "bold")).grid(row=0, column=1,
                                                         sticky="w")

            self.progress_bar = ttk.Progressbar(
                c, orient=tk.HORIZONTAL, mode="determinate",
                style="T.Horizontal.TProgressbar", variable=self.progress_pct
            )
            self.progress_bar["maximum"] = 100
            self.progress_bar.grid(row=2, column=1, sticky="ew", pady=(6, 0))

            # Last message
            tk.Label(c, textvariable=self.last_msg_var,
                     fg=TEXT_MUTED, bg=CARD_BG,
                     font=(FONT_BRAND, 10), anchor="w",
                     wraplength=500).grid(
                row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

            # Error
            tk.Label(c, textvariable=self.error_var,
                     fg=DANGER, bg=CARD_BG,
                     font=(FONT_BRAND, 10), anchor="w").grid(
                row=4, column=0, columnspan=2, sticky="ew", pady=(2, 0))

    def _draw_donut(self, pct: float):
            cv = self._donut_canvas
            cv.delete("all")
            cx, cy, r_outer, r_inner = 55, 55, 48, 32
            # Background ring
            cv.create_arc(cx-r_outer, cy-r_outer, cx+r_outer, cy+r_outer,
                          start=90, extent=360,
                          outline="#e8edf5", width=16, style="arc")
            # Progress arc
            extent = -pct * 3.6
            if extent != 0:
                cv.create_arc(cx-r_outer, cy-r_outer, cx+r_outer, cy+r_outer,
                              start=90, extent=extent,
                              outline=TECHMI_BLUE, width=16, style="arc")
            # Centre text
            cv.create_text(cx, cy, text=f"{int(pct)}%",
                           fill=TEXT_DARK, font=(FONT_BRAND, 14, "bold"))
            cv.create_text(cx, cy+18, text="COMPLETE",
                           fill=TEXT_MUTED, font=(FONT_BRAND, 7))

    def _build_log_panel(self, parent):
            card, c = _card(parent, "LOG / MESSAGES", "≡")
            card.grid(row=4, column=0, sticky="ew", pady=(0, 8))

            # Text widget with scrollbar
            scroll = tk.Scrollbar(c)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)

            self.log_text = tk.Text(
                c, height=8, width=1,
                bg="#f8fafc", fg=TEXT_DARK,
                font=(FONT_MONO, 10),
                relief="flat", bd=0,
                yscrollcommand=scroll.set,
                state="disabled",
                wrap="word",
                padx=8, pady=6,
                cursor="arrow",
                selectbackground=TECHMI_BLUE
            )
            self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scroll.configure(command=self.log_text.yview)

            # Colour tags
            self.log_text.tag_configure("gray",  foreground="#6b7280")
            self.log_text.tag_configure("blue",  foreground="#2563eb")
            self.log_text.tag_configure("green", foreground=SUCCESS)
            self.log_text.tag_configure("red",   foreground=DANGER)
            self.log_text.tag_configure("time",  foreground=TEXT_MUTED)

            self._append_log("System started.", "gray")

    def _append_log(self, message: str, category: str = "gray"):
            """Append a timestamped entry to the log widget."""
            timestamp = time.strftime("%H:%M:%S")
            dot_colors = {"gray": "●", "blue": "●", "green": "●", "red": "●"}
            dot = dot_colors.get(category, "●")

            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"{timestamp}  ", "time")
            self.log_text.insert("end", f"{dot} ", category)
            self.log_text.insert("end", f"{message}\n", category)
            self.log_text.configure(state="disabled")
            self.log_text.see("end")

