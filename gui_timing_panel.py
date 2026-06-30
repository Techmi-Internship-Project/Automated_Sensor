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
    format_elapsed,
    _card,
    _entry,
    _section_label,
)

class TimingPanelMixin:
    """
    GUI section mixin split out of the original SensorGUI class.
    """

    def _build_timing_panel(self, parent, row=0):
            card, c = _card(parent, "EXPERIMENT TIMING", "◷")
            parent.grid_rowconfigure(0, weight=1)
            parent.grid_columnconfigure(0, weight=1)
            # Row 1 of the left dashboard column
            card.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
            c.grid_columnconfigure((0, 1, 2), weight=1)

            # Duration
            _section_label(c, "Total Duration").grid(
                row=0, column=0, columnspan=3, sticky="w", pady=(0, 2))

            self.dur_days_e = _entry(c, self.duration_days)
            self.dur_days_e.grid(row=1, column=0, sticky="ew", padx=(0, 4))
            self.dur_hrs_e  = _entry(c, self.duration_hours)
            self.dur_hrs_e.grid(row=1, column=1, sticky="ew", padx=4)
            self.dur_min_e  = _entry(c, self.duration_minutes)
            self.dur_min_e.grid(row=1, column=2, sticky="ew", padx=(4, 0))

            for lbl, col in [("Days", 0), ("Hours", 1), ("Minutes", 2)]:
                tk.Label(c, text=lbl, fg=TEXT_MUTED, bg=CARD_BG,
                         font=(FONT_BRAND, 7)).grid(
                    row=2, column=col, pady=(0, 2))

            self._idle_only_widgets += [self.dur_days_e, self.dur_hrs_e,
                                        self.dur_min_e]

            # Interval
            _section_label(c, "Capture Interval").grid(
                row=3, column=0, columnspan=3, sticky="w", pady=(0, 2))

            self.int_hrs_e = _entry(c, self.interval_hours)
            self.int_hrs_e.grid(row=4, column=0, sticky="ew", padx=(0, 4))
            self.int_min_e = _entry(c, self.interval_minutes)
            self.int_min_e.grid(row=4, column=1, sticky="ew", padx=4)

            for lbl, col in [("Hours", 0), ("Minutes", 1)]:
                tk.Label(c, text=lbl, fg=TEXT_MUTED, bg=CARD_BG,
                         font=(FONT_BRAND, 7)).grid(
                    row=5, column=col, pady=(0, 2))

            self._idle_only_widgets += [self.int_hrs_e, self.int_min_e]

            # Quick presets
            _section_label(c, "Quick Presets").grid(
                row=6, column=0, columnspan=3, sticky="w", pady=(0, 0))

            pf = tk.Frame(c, bg=CARD_BG,)
            pf.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(0, 2))
            pf.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

            self._preset_btns = []
            presets = [("6h",  dict(hours=6)),
                       ("12h", dict(hours=12)),
                       ("24h", dict(days=1)),
                       ("48h", dict(days=2)),
                       ("72h", dict(days=3))]
            for i, (label, kwargs) in enumerate(presets):
                # Border frame creates the gray outline around each preset button.
                btn_border = tk.Frame(
                    pf,
                    bg=CARD_BORDER,
                    padx=1,
                    pady=1
                )

                # Place each bordered button frame in the preset row.
                btn_border.grid(
                    row=0,
                    column=i,
                    sticky="ew",
                    padx=2,
                    pady=1
                )

                # Actual preset button sits inside the border frame.
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
                    command=lambda kw=kwargs: self.set_duration_preset(**kw)
                )

                # Fill the border frame so the gray outline is visible around the button.
                b.pack(fill=tk.BOTH, expand=True)

                self._preset_btns.append(b)
                self._idle_only_widgets.append(b)

            
    def _highlight_preset(self, btn):
            for b in self._preset_btns:
                b.configure(bg=CARD_BG, fg=TEXT_MUTED)
            btn.configure(bg=TECHMI_BLUE, fg="white")
            self._active_preset_btn = btn

    def set_duration_preset(self, days=0, hours=0, mins=0):
            self.duration_days.set(str(days))
            self.duration_hours.set(str(hours))
            self.duration_minutes.set(str(mins))
            # Highlight matching button
            mapping = {(0,6,0):0, (0,12,0):1, (1,0,0):2, (2,0,0):3, (3,0,0):4}
            idx = mapping.get((days, hours, mins))
            if idx is not None:
                self._highlight_preset(self._preset_btns[idx])
            self.update_timing_estimates()

    def update_timing_estimates(self):
            try:
                d = self.get_duration_seconds_from_inputs()
                i = self.get_interval_seconds_from_inputs()
            except ValueError:
                self.estimated_duration_text.set("Total run time: Invalid input")
                self.estimated_capture_count = 0
                self.estimated_finish_text.set("Est. finish: —")
                return

            if i <= 0:
                self.estimated_capture_count =0
                return

            dur_text  = format_elapsed(d)
            est_caps  = int(d // i) + 1 # +1 because capture at time = 0
            finish_ts = time.time() + d
            finish    = time.strftime("%a %H:%M", time.localtime(finish_ts))

            self.estimated_duration_text.set(f"Total run time: {dur_text}")
            self.estimated_capture_count = est_caps
            self.estimated_finish_text.set(f"Est. finish: {finish}")

    def get_duration_seconds_from_inputs(self):
            days = int(self.duration_days.get())
            hours = int(self.duration_hours.get())
            mins  = int(self.duration_minutes.get())
            if days < 0 or hours < 0 or mins < 0:
                raise ValueError("Duration values cannot be negative.")
            total = days * 86400 + hours * 3600 + mins * 60
            if total <= 0:
                raise ValueError("Duration must be greater than 0.")
            return total

    def get_interval_seconds_from_inputs(self):
            hours = int(self.interval_hours.get())
            mins  = int(self.interval_minutes.get())
            if hours < 0 or mins < 0:
                raise ValueError("Interval values cannot be negative.")
            total = hours * 3600 + mins * 60
            if total <= 0:
                raise ValueError("Interval must be greater than zero.")
            return total

