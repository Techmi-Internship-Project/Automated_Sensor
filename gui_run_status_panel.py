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
    CARD_BORDER,
    FONT_MONO,
    SUCCESS,
    TECHMI_BLUE,
    TEXT_DARK,
    TEXT_MUTED,
    WARNING,
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
                                 self.start_experiment, "primary")
        self.start_button.grid(row=0, column=0, sticky="ew",
                               padx=(0, 6), pady=(2, 5))

        self.stop_button = _btn(c, "■  Stop Experiment",
                                self.stop_experiment, "danger")
        self.stop_button.grid(row=0, column=1, sticky="ew",
                              padx=(6, 0), pady=(0, 5))

        # Live adjustment section label
        _section_label(c, "Live Run Adjustments").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 2))

        # Adjustment buttons: +1h, +6h, -1h, End After Next
        adj_frame = tk.Frame(c, bg=CARD_BG)
        adj_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0,2))
        adj_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        for i, (label, delta) in enumerate([
            ("+1h",  3600),
            ("+6h", 21600),
            ("-1h", -3600),
        ]):
            btn_border = tk.Frame(adj_frame, bg=CARD_BORDER, padx=1, pady=1)

            btn_border.grid(
                row=0,
                column=i,
                sticky="ew",
                padx=2,
                pady=1
            )

            b = tk.Button(
                btn_border,
                text=label,
                relief="flat",
                bd=0,
                cursor="hand2",
                bg=CARD_BG,
                fg=TEXT_MUTED,
                activebackground=TECHMI_BLUE,
                activeforeground="white",
                font=(FONT_BRAND, 9),
                padx=6,
                pady=2,
                command=lambda d=delta: self.controller.adjust_time(d) 
            )

            b.pack(fill=tk.BOTH, expand=True)

            self._run_adjust_btns.append(b)

        # End After Next Capture button (column 3, same row as time adjustments)
        end_border = tk.Frame(adj_frame, bg=CARD_BORDER, padx=1, pady=1)
        end_border.grid(row=0, column=3, sticky="ew", padx=2, pady=1)

        self._end_after_next_btn = tk.Button(
            end_border,
            text="End After Next",
            relief="flat",
            bd=0,
            cursor="hand2",
            bg=CARD_BG,
            fg=WARNING,
            activebackground=WARNING,
            activeforeground="white",
            font=(FONT_BRAND, 9),
            padx=6,
            pady=2,
            command=self._request_end_after_next
        )
        self._end_after_next_btn.pack(fill=tk.BOTH, expand=True)

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
                                       width=90,
                                       height=90,
                                       bg=CARD_BG,
                                       highlightthickness=0)
        self._donut_canvas.grid(row=0, column=0,
                                rowspan=3,
                                padx=(0, 14),
                                pady=(0,0),
                                sticky="nw")
        # Draw initial empty ring
        self._draw_donut(0)

        # ── Metric labels grid (right side) ───────────────────────────────────
        metrics = tk.Frame(c, bg=CARD_BG)
        metrics.grid(row=0, column=1, sticky="ew", padx=(5,0))

        # Metric columns expand.
        metrics.grid_columnconfigure(0, weight=1)
        metrics.grid_columnconfigure(2, weight=1)
        metrics.grid_columnconfigure(4, weight=1)
        metrics.grid_columnconfigure(6, weight=1)

        # Divider columns stay thin.
        metrics.grid_columnconfigure(1, weight=0)
        metrics.grid_columnconfigure(3, weight=0)
        metrics.grid_columnconfigure(5, weight=0)

        metric_items = [
            ("Status", self.status, SUCCESS),
            ("Elapsed", self.elapsed, TEXT_DARK),
            ("Remaining", self.remaining, TEXT_DARK),
            ("Est. Finish", self.estimated_finish_text, TEXT_DARK),
        ]

        # Where text goes
        metric_cols = [0,2,4,6]

        for i, (label_text, string_var, value_color) in enumerate(metric_items):
            col = metric_cols[i]

            # Small muted metric title.
            tk.Label(
                metrics,
                text=label_text,
                fg=TEXT_MUTED,
                bg=CARD_BG,
                font=(FONT_BRAND, 8, "bold"),
                anchor="w"
            ).grid(
                row=0,
                column=col,
                sticky="w",
                padx=(0, 8)
            )

            # Main metric value.
            tk.Label(
                metrics,
                textvariable=string_var,
                fg=value_color,
                bg=CARD_BG,
                font=(FONT_BRAND, 10, "bold"),
                anchor="w"
            ).grid(
                row=1,
                column=col,
                sticky="w",
                padx=(0, 8),
                pady=(1, 0)
            )

        # Thin vertical divider lines between metric groups.
        for divider_col in [1, 3, 5]:
            tk.Frame(
                metrics,
                bg=CARD_BORDER,
                width=1
            ).grid(
                row=0,
                column=divider_col,
                rowspan=2,
                sticky="ns",
                padx=(8, 12),
                pady=(0, 0)
            )
            
        # ── Capture count row ──────────────────────────────────────────────────
        capture_row = tk.Frame(c, bg=CARD_BG)
        capture_row.grid(row=1, column=1, sticky="ew", pady=(8, 2))
        capture_row.grid_columnconfigure(1, weight=1)

        tk.Label(
            capture_row,
            text="Captures",
            fg=TEXT_MUTED,
            bg=CARD_BG,
            font=(FONT_BRAND, 8, "bold")
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        tk.Label(
            capture_row,
            textvariable=self.capture_ratio,
            fg=TEXT_DARK,
            bg=CARD_BG,
            font=(FONT_BRAND, 10, "bold")
        ).grid(row=0, column=1, sticky="w")

        # Progress bar for run completion.
        self.progress_bar = ttk.Progressbar(
            c,
            orient=tk.HORIZONTAL,
            mode="determinate",
            style="T.Horizontal.TProgressbar",
            variable=self.progress_pct,
        )
        self.progress_bar["maximum"] = 100
        self.progress_bar.grid(row=2, column=1, sticky="ew", pady=(2, 0))

        # ── Bottom message row ─────────────────────────────────────────────────
        bottom_msg = tk.Frame(c, bg=CARD_BG)
        bottom_msg.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 0)
        )
        bottom_msg.grid_columnconfigure(0, weight=1)

        # Single status line: shows error in red when one is active,
        # otherwise shows the last controller message in muted text.
        self._status_label = tk.Label(
            bottom_msg,
            textvariable=self.last_msg_var,
            fg=TEXT_MUTED,
            bg=CARD_BG,
            font=(FONT_BRAND, 8),
            anchor="w",
            wraplength=700,
            justify="left"
        )
        self._status_label.grid(row=0, column=0, sticky="ew")

        def _on_error_change(*_):
            err = self.error_var.get()
            if err and err not in ("—", "-"):
                self._status_label.configure(textvariable=self.error_var, fg=DANGER)
            else:
                self._status_label.configure(textvariable=self.last_msg_var, fg=TEXT_MUTED)

        self.error_var.trace_add("write", _on_error_change)
    # ── Donut renderer ────────────────────────────────────────────────────────
    def _draw_donut(self, pct: float):
        """
        Redraws the donut chart to reflect the given completion percentage.
        Called on every status loop tick.
        """

        cv = self._donut_canvas
        cv.delete("all")

        cx, cy = 45, 45
        r = 34   # outer radius of the arc
        arc_width = 10

        # Background ring (full circle in light grey)
        cv.create_arc(cx - r, cy - r, cx + r, cy + r,
                      start=90, extent=360,
                      outline="#e8edf5",
                      width=arc_width,
                      style="arc")

        # Progress arc (clockwise from top, TECHMI blue).
        # Cap at 99.9 % to avoid extent = -360, which Tkinter renders as empty.
        if pct >= 0.25:
            extent = -min(pct, 99.9) * 3.6
        else:
            extent = 0

        if extent != 0:
            cv.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=90, extent=extent,
                        outline=TECHMI_BLUE,
                        width=arc_width,
                        style="arc")

        # Percentage text in the centre
        cv.create_text(cx, cy - 2,
                    text=f"{int(pct)}%",
                    fill=TEXT_DARK,
                    font=(FONT_BRAND, 11, "bold"))


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

        # ── Color tag definitions ────────────────────────────────────────────
        self.log_text.tag_configure("gray",   foreground="#6b7280")
        self.log_text.tag_configure("blue",   foreground="#2563eb")
        self.log_text.tag_configure("green",  foreground=SUCCESS)
        self.log_text.tag_configure("red",    foreground=DANGER)
        self.log_text.tag_configure("yellow", foreground="#cda30b")
        self.log_text.tag_configure("time",   foreground=TEXT_MUTED)

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

        Will incrementally write logs to a file in the current/ folder as experiment runs
        """

        timestamp = time.strftime("%H:%M:%S")

        # Unlock the Text widget, insert, lock again, scroll to bottom
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{timestamp}  ", "time")
        self.log_text.insert("end", "● ", category)
        self.log_text.insert("end", f"{message}\n", category)

        # Cap the log so a multi-day run can't grow the widget unbounded.
        # Trim oldest lines once past the limit.
        max_lines = 2000
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > max_lines:
            self.log_text.delete("1.0", f"{line_count - max_lines}.0")

        self.log_text.configure(state="disabled")
        self.log_text.see("end")

        # Write to run log if experiment is active
        if self._active_log_path is not None : 
            try:
                log_path = self._active_log_path
                with open(log_path, "a", encoding="utf-8") as f: 
                    full_ts = time.strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{full_ts}][{category.upper()}] {message}\n")
            except Exception :
                pass