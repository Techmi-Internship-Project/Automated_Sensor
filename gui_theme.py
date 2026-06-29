"""
Shared styling and small widget helpers for the TECHMI GUI.

This file has no experiment logic.  It only contains colors, fonts,
formatting helpers, and widget factory functions used by the panel files.
"""

import ctypes
import tkinter as tk

# ── Brand palette ──────────────────────────────────────────────────────────────
NAVY        = "#081225"
NAVY_2      = "#101b33"
NAVY_3      = "#0d1a30"
TECHMI_BLUE = "#233dff"
TECHMI_CYAN = "#08d3dd"
OFF_WHITE   = "#f6f8fc"
CARD_BG     = "#ffffff"
CARD_BORDER = "#dce3ee"
TEXT_DARK   = "#111827"
TEXT_MUTED  = "#667085"
SUCCESS     = "#16a34a"
DANGER      = "#dc2626"
WARNING     = "#f97316"
DISABLED_BG = "#eef2f7"

# Font stack used across the whole GUI.
FONT_BRAND = "Segoe UI"
FONT_MONO  = "Consolas"
# Public names that other GUI files are allowed to import explicitly.
__all__ = [
    "NAVY",
    "NAVY_2",
    "NAVY_3",
    "TECHMI_BLUE",
    "TECHMI_CYAN",
    "OFF_WHITE",
    "CARD_BG",
    "CARD_BORDER",
    "TEXT_DARK",
    "TEXT_MUTED",
    "SUCCESS",
    "DANGER",
    "WARNING",
    "DISABLED_BG",
    "FONT_BRAND",
    "FONT_MONO",
    "enable_windows_dpi_awareness",
    "format_elapsed",
    "_round_rect",
    "_label",
    "_btn",
    "_entry",
    "_section_label",
    "_card",
]

def enable_windows_dpi_awareness():
    """
    Makes the Tkinter window sharper on high-DPI Windows displays.

    This must be called before tk.Tk() is created.  If the DPI call fails,
    the app still runs normally.
    """

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def format_elapsed(seconds: float) -> str:
    """
    Formats seconds into a compact time string for the dashboard.
    """

    seconds = int(seconds)

    if seconds < 60:
        return f"{seconds}s"

    if seconds < 3600:
        minutes, secs = divmod(seconds, 60)
        return f"{minutes:02d}:{secs:02d}"

    if seconds < 86400:
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{days}d {hours:02d}:{minutes:02d}"


def _round_rect(canvas, x1, y1, x2, y2, r=14, **kw):
    """
    Draws a rounded rectangle on a canvas.
    """

    pts = [
        x1+r, y1,   x2-r, y1,
        x2,   y1,   x2,   y1+r,
        x2,   y2-r, x2,   y2,
        x2-r, y2,   x1+r, y2,
        x1,   y2,   x1,   y2-r,
        x1,   y1+r, x1,   y1,
        x1+r, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _label(parent, text, fg=TEXT_DARK, size=11, bold=False, bg=CARD_BG, **kw):
    """
    Creates a standard label using the dashboard font and colors.
    """

    weight = "bold" if bold else "normal"
    return tk.Label(
        parent,
        text=text,
        fg=fg,
        bg=bg,
        font=(FONT_BRAND, size, weight),
        **kw
    )


def _btn(parent, text, cmd, kind="secondary", h=32, w=None, **kw):
    """
    Creates a styled button used throughout the dashboard.
    """

    styles = {
        "primary":   dict(bg=TECHMI_BLUE, fg="white", activebackground="#1a2fd0", activeforeground="white"),
        "danger":    dict(bg="white", fg=DANGER, activebackground="#fff1f2", activeforeground=DANGER),
        "cyan":      dict(bg=TECHMI_CYAN, fg=NAVY, activebackground="#07bbc4", activeforeground=NAVY),
        "secondary": dict(bg="white", fg=NAVY, activebackground="#eef2ff", activeforeground=NAVY),
        "dark":      dict(bg=NAVY_2, fg="white", activebackground=NAVY, activeforeground="white"),
        "ghost":     dict(bg=CARD_BG, fg=TEXT_MUTED, activebackground=OFF_WHITE, activeforeground=TEXT_DARK),
    }

    style = styles.get(kind, styles["secondary"])
    config = dict(
        relief="flat",
        bd=0,
        cursor="hand2",
        font=(FONT_BRAND, 10, "bold" if kind == "primary" else "normal"),
        padx=8,
        pady=3,
        **style
    )
    config.update(kw)

    button = tk.Button(parent, text=text, command=cmd, **config)

    if w:
        button.configure(width=w)

    return button


def _entry(parent, var, w=6):
    """
    Creates a clean centered entry field for timing inputs.
    """

    return tk.Entry(
        parent,
        textvariable=var,
        width=w,
        font=(FONT_BRAND, 11),
        justify="center",
        relief="flat",
        bd=1,
        bg="white",
        fg=TEXT_DARK,
        highlightthickness=1,
        highlightcolor=TECHMI_BLUE,
        highlightbackground=CARD_BORDER
    )


def _section_label(parent, text, bg=CARD_BG):
    """
    Creates the small uppercase labels inside cards.
    """

    return tk.Label(
        parent,
        text=text.upper(),
        fg=TEXT_MUTED,
        bg=bg,
        font=(FONT_BRAND, 8, "bold")
    )


def _card(parent, title="", icon="", bg=CARD_BG):
    """
    Creates a white card with a thin border and optional title row.
    """

    outer = tk.Frame(parent, bg=CARD_BORDER, padx=1, pady=1)
    inner = tk.Frame(outer, bg=bg, padx=0, pady=0)
    inner.pack(fill=tk.BOTH, expand=True)

    if title:
        header = tk.Frame(inner, bg=bg)
        header.pack(fill=tk.X, padx=8, pady=(5, 1))

        title_text = f"{icon}  {title}" if icon else title
        tk.Label(
            header,
            text=title_text,
            fg=NAVY,
            bg=bg,
            font=(FONT_BRAND, 11, "bold")
        ).pack(side=tk.LEFT)

    content = tk.Frame(inner, bg=bg)
    content.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

    return outer, content
