"""
gui_run_status_panel.py

Builds four dashboard panels:
  • Run Control   (start, stop, live adjustments)
  • Live Status   (donut progress, metrics, progress bar, last message)
  • Log/Messages  (scrollable timestamped log with colour-coded categories)

Row assignments (left column, injected by gui_layout.py):
  row 0 → setup panel     (gui_setup_panel.py)
  row 1 → timing panel    (gui_timing_panel.py)
  row 2 → run control     ← this file
  row 3 → live status     ← this file

Row assignments (right column):
  row 2 → log/messages    ← this file
  row 3 → recovery panel  (gui_recovery_settings.py)
"""

import tkinter as tk
from tkinter import ttk
import time

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

    # ── Run Control panel ─────────────────────────────────────────────────────
    def _build_run_control_panel(self, parent, row=0):
        """
        Creates the Run Control card with Start, Stop, and live-adjustment
        buttons.  Placed at row 2 of the left dashboard column.
        """

        card, c = _card(parent, "RUN CONTROL", "▷")
        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(1, weight=1)

        # Start / Stop buttons side by side
        self.start_button = _btn(c, "▶  Start Experiment",
                                 self.start_experiment, "primary", h=40)
        self.start_button.grid(row=0, column=0, sticky="ew",
                               padx=(0, 6), pady=(0, 10))

        self.stop_button = _btn(c, "■  Stop Experiment",
                                self.stop_experiment, "danger", h=40)
        self.stop_button.grid(row=0, column=1, sticky="ew",
                              padx=(6, 0), pady=(0, 10))

        # Live adjustment section label
        _section_label(c, "Live Run Adjustments").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))

        # Adjustment buttons: +1h, +6h, −1h
        adj_frame = tk.Frame(c, bg=CARD_BG)
        adj_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
        adj_frame.grid_columnconfigure((0, 1, 2), weight=1)

        for i, (label, delta) in enumerate([
            ("+1h",  3600),
            ("+6h", 21600),
            ("−1h", -3600),
        ]):
            b = _btn(adj_frame, label,
                     lambda d=delta: self.controller.adjust_time(d),
                     "secondary")
            b.grid(row=0, column=i, sticky="ew", padx=3)
            # Track for enable/disable during experiments
            self._run_adjust_btns.append(b)

    # ── Live Status panel ─────────────────────────────────────────────────────
    def _build_live_status_panel(self, parent, row=0):
        """
        Creates the Live Status card with a donut progress indicator,
        four metric labels, a linear progress bar, and a last-message line.
        Placed at row 3 of the left dashboard column.
        """

        card, c = _card(parent, "LIVE STATUS", "▣")
        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 6))
        c.grid_columnconfigure(0, weight=0)   # donut column fixed
        c.grid_columnconfigure(1, weight=1)   # metrics column fills

        # ── Donut canvas (left side of card) ──────────────────────────────────
        self._donut_canvas = tk.Canvas(c,
                                       width=110,
                                       height=110,
                                       bg=CARD_BG,
                                       highlightthickness=0)
        self._donut_canvas.grid(row=0, column=0,
                                rowspan=3,
                                padx=(0, 16),
                                pady=4,
                                sticky="n")
        # Draw initial empty ring
        self._draw_donut(0)

        # ── Metric labels grid (right side) ───────────────────────────────────
        metrics = tk.Frame(c, bg=CARD_BG)
        metrics.grid(row=0, column=1, sticky="nsew")
        metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Four columns: Status | Elapsed | Remaining | Est. Finish
        for col, (label_text, string_var) in enumerate([
            ("Status",      self.status),
            ("Elapsed",     self.elapsed),
            ("Remaining",   self.remaining),
            ("Est. Finish", self.estimated_finish_text),
        ]):
            # Small muted header
            tk.Label(metrics,
                     text=label_text,
                     fg=TEXT_MUTED,
                     bg=CARD_BG,
                     font=(FONT_BRAND, 9, "bold")).grid(
                row=0, column=col, sticky="w", padx=6, pady=(0, 2))

            # Value label — Status uses green, others use dark text
            value_fg = SUCCESS if label_text == "Status" else TEXT_DARK
            tk.Label(metrics,
                     textvariable=string_var,
                     fg=value_fg,
                     bg=CARD_BG,
                     font=(FONT_BRAND, 11, "bold")).grid(
                row=1, column=col, sticky="w", padx=6)

        # ── Captures row + linear progress bar ───────────────────────────────
        prog_frame = tk.Frame(c, bg=CARD_BG)
        prog_frame.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        prog_frame.grid_columnconfigure(1, weight=1)

        tk.Label(prog_frame,
                 text="Captures",
                 fg=TEXT_MUTED,
                 bg=CARD_BG,
                 font=(FONT_BRAND, 9, "bold")).grid(row=0, column=0,
                                                    sticky="w", padx=(0, 8))
        tk.Label(prog_frame,
                 textvariable=self.capture_count,
                 fg=TEXT_DARK,
                 bg=CARD_BG,
                 font=(FONT_BRAND, 11, "bold")).grid(row=0, column=1,
                                                     sticky="w")

        # Progress bar (styled via ttk in __init__)
        self.progress_bar = ttk.Progressbar(
            c,
            orient=tk.HORIZONTAL,
            mode="determinate",
            style="T.Horizontal.TProgressbar",
            variable=self.progress_pct,
        )
        self.progress_bar["maximum"] = 100
        self.progress_bar.grid(row=2, column=1, sticky="ew", pady=(6, 0))

        # ── Last message ──────────────────────────────────────────────────────
        tk.Label(c,
                 textvariable=self.last_msg_var,
                 fg=TEXT_MUTED,
                 bg=CARD_BG,
                 font=(FONT_BRAND, 10),
                 anchor="w",
                 wraplength=500).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # ── Error line ────────────────────────────────────────────────────────
        tk.Label(c,
                 textvariable=self.error_var,
                 fg=DANGER,
                 bg=CARD_BG,
                 font=(FONT_BRAND, 10),
                 anchor="w").grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(2, 0))

    # ── Donut renderer ────────────────────────────────────────────────────────
    def _draw_donut(self, pct: float):
        """
        Redraws the donut chart to reflect the given completion percentage.
        Called on every status loop tick.
        """

        cv = self._donut_canvas
        cv.delete("all")

        cx, cy = 55, 55
        r = 46   # outer radius of the arc

        # Background ring (full circle in light grey)
        cv.create_arc(cx - r, cy - r, cx + r, cy + r,
                      start=90, extent=360,
                      outline="#e8edf5",
                      width=14,
                      style="arc")

        # Progress arc (clockwise from top, TECHMI blue)
        extent = -pct * 3.6
        if extent != 0:
            cv.create_arc(cx - r, cy - r, cx + r, cy + r,
                          start=90, extent=extent,
                          outline=TECHMI_BLUE,
                          width=14,
                          style="arc")

        # Percentage text in the centre
        cv.create_text(cx, cy - 6,
                       text=f"{int(pct)}%",
                       fill=TEXT_DARK,
                       font=(FONT_BRAND, 14, "bold"))

        # Small label below the number
        cv.create_text(cx, cy + 14,
                       text="COMPLETE",
                       fill=TEXT_MUTED,
                       font=(FONT_BRAND, 7))

    # ── Log / Messages panel ──────────────────────────────────────────────────
    def _build_log_panel(self, parent, row=0):
        """
        Creates the scrollable log card.

        Colour categories:
          gray  → system / startup messages
          blue  → technical events (laser on/off, camera, profile changes)
          green → capture-related success messages
          red   → warnings and errors

        Placed at row 2 of the right dashboard column.
        """

        card, c = _card(parent, "LOG / MESSAGES", "≡")
        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 6))

        # Scrollbar + Text widget side by side
        scroll = tk.Scrollbar(c)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(
            c,
            height=7,          # roughly 7 lines visible
            width=1,           # let pack fill the width
            bg="#f8fafc",
            fg=TEXT_DARK,
            font=(FONT_MONO, 9),
            relief="flat",
            bd=0,
            yscrollcommand=scroll.set,
            state="disabled",  # read-only; unlocked only during writes
            wrap="word",
            padx=6,
            pady=4,
            cursor="arrow",
            selectbackground=TECHMI_BLUE,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.configure(command=self.log_text.yview)

        # ── Colour tag definitions ────────────────────────────────────────────
        self.log_text.tag_configure("gray",  foreground="#6b7280")
        self.log_text.tag_configure("blue",  foreground="#2563eb")
        self.log_text.tag_configure("green", foreground=SUCCESS)
        self.log_text.tag_configure("red",   foreground=DANGER)
        self.log_text.tag_configure("time",  foreground=TEXT_MUTED)

        # First log entry
        self._append_log("System started.", "gray")

    def _append_log(self, message: str, category: str = "gray"):
        """
        Appends a timestamped, colour-coded line to the log widget.

        Parameters
        ----------
        message  : str   Text to display.
        category : str   One of 'gray', 'blue', 'green', 'red'.
                         Controls both the dot colour and the text colour.
        """

        timestamp = time.strftime("%H:%M:%S")

        # Unlock the Text widget, insert, lock again, scroll to bottom
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{timestamp}  ", "time")
        self.log_text.insert("end", "● ", category)
        self.log_text.insert("end", f"{message}\n", category)
        self.log_text.configure(state="disabled")
        self.log_text.see("end")
