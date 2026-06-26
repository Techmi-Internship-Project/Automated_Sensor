"""
camera_preview_panel.py

Embeddable camera preview panel for the TECHMI Bioreactor Sensor GUI.
Handles live feed, ArUco overlay toggle, and laser toggle directly
inside the main window without opening a separate Toplevel.
"""

import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
from pathlib import Path
import cv2 as cv

from camera import open_camera, set_normal_exposure
from aruco import detect_aruco_markers, get_roi_corners
from laser_control import LaserRelay

# ── Brand colours (shared constants) ──────────────────────────────────────────
NAVY       = "#081225"
NAVY_2     = "#101b33"
TECHMI_BLUE= "#233dff"
TECHMI_CYAN= "#08d3dd"
CARD_BG    = "#ffffff"
CARD_BORDER= "#dce3ee"
TEXT_DARK  = "#111827"
TEXT_MUTED = "#667085"
SUCCESS    = "#16a34a"
DANGER     = "#dc2626"
WARNING    = "#f97316"
OFF_WHITE  = "#f6f8fc"

PREVIEW_W  = 640   # px inside the card
PREVIEW_H  = 360


class CameraPreviewPanel:
    """
    Drop-in panel that can be embedded inside any Tkinter parent frame.

    Public API
    ----------
    start_preview(camera_index)   – open camera and begin frame loop
    stop_preview()                – release camera, show logo placeholder
    set_laser(relay: LaserRelay)  – attach an already-opened LaserRelay
    get_laser_state() -> bool
    log_callback                  – assign a callable(message, category) to
                                    route panel messages to the main log
    """

    # ── Init ──────────────────────────────────────────────────────────────────
    def __init__(self, parent, log_callback=None):
        self.parent       = parent
        self.log_callback = log_callback   # callable(msg, category)

        self.cap              = None
        self.running          = False
        self.show_overlay     = False
        self.laser: LaserRelay | None = None
        self.laser_is_on      = False
        self.current_tk_image = None

        # Stats surfaced by the overlay bar
        self.marker_count_var = tk.StringVar(value="Markers: —")
        self.roi_var          = tk.StringVar(value="ROI: —")

        self._logo_photo  = None     # placeholder image reference
        self._after_id    = None     # .after() handle so we can cancel

        self._build_ui()
        self._show_placeholder()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        """Build the camera preview panel widgets."""
        self.frame = tk.Frame(self.parent, bg=CARD_BG)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # ── Top control bar ──────────────────────────────────────────────────
        ctrl_bar = tk.Frame(self.frame, bg=CARD_BG)
        ctrl_bar.pack(fill=tk.X, padx=14, pady=(6, 4))

        # Preview ON/OFF toggle
        self.preview_var = tk.BooleanVar(value=False)
        self.preview_btn = tk.Button(
            ctrl_bar,
            text="▶  Preview OFF",
            command=self._toggle_preview,
            bg="#eef2ff", fg=TECHMI_BLUE,
            activebackground=TECHMI_BLUE, activeforeground="white",
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=10, pady=4, cursor="hand2"
        )
        self.preview_btn.pack(side=tk.LEFT)

        # ArUco overlay toggle
        self.overlay_btn = tk.Button(
            ctrl_bar,
            text="◎  ROI Overlay: OFF",
            command=self._toggle_overlay,
            bg=CARD_BG, fg=TEXT_MUTED,
            relief="flat", bd=0,
            font=("Segoe UI", 10),
            padx=10, pady=4, cursor="hand2"
        )
        self.overlay_btn.pack(side=tk.LEFT, padx=(6, 0))

        # Laser toggle (right-aligned)
        self.laser_btn = tk.Button(
            ctrl_bar,
            text="⬤  Laser: OFF",
            command=self._toggle_laser,
            bg=NAVY_2, fg="#9ca3af",
            activebackground=NAVY, activeforeground="white",
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=12, pady=4, cursor="hand2"
        )
        self.laser_btn.pack(side=tk.RIGHT)

        # ── Video canvas ─────────────────────────────────────────────────────
        self.canvas = tk.Canvas(
            self.frame,
            width=PREVIEW_W, height=PREVIEW_H,
            bg="#0a0f1e", highlightthickness=0, bd=0
        )
        self.canvas.pack(padx=14, pady=(0, 4))

        # ── Status bar below canvas ──────────────────────────────────────────
        status_bar = tk.Frame(self.frame, bg=CARD_BG)
        status_bar.pack(fill=tk.X, padx=14, pady=(0, 10))

        tk.Label(
            status_bar, textvariable=self.roi_var,
            bg=CARD_BG, fg=TEXT_MUTED, font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)

        tk.Label(
            status_bar, textvariable=self.marker_count_var,
            bg=CARD_BG, fg=TEXT_MUTED, font=("Segoe UI", 9)
        ).pack(side=tk.RIGHT)

    # ── Placeholder (logo) ────────────────────────────────────────────────────
    def _show_placeholder(self):
        """Draw transparent TECHMI logo on canvas when preview is off."""
        self.canvas.delete("all")
        self.canvas.configure(bg="#0a0f1e")

        if self._logo_photo is None:
            try:
                logo_path = Path("logo_azul.png")
                img = Image.open(logo_path).convert("RGBA")
                # Scale to ~40 % of canvas width
                scale  = (PREVIEW_W * 0.4) / img.width
                new_w  = max(1, int(img.width  * scale))
                new_h  = max(1, int(img.height * scale))
                img    = img.resize((new_w, new_h), Image.LANCZOS)
                # Lower opacity
                alpha  = img.getchannel("A").point(lambda p: int(p * 0.18))
                img.putalpha(alpha)
                self._logo_photo = ImageTk.PhotoImage(img)
            except Exception:
                self._logo_photo = None

        cx, cy = PREVIEW_W // 2, PREVIEW_H // 2
        if self._logo_photo:
            self.canvas.create_image(cx, cy, image=self._logo_photo,
                                     anchor="center")
        else:
            self.canvas.create_text(
                cx, cy, text="TECHMI",
                fill="#1a2a4a", font=("Segoe UI", 36, "bold")
            )

        self.canvas.create_text(
            cx, cy + 60,
            text="Camera preview is off — press ▶ Preview to start",
            fill="#2d3f5e", font=("Segoe UI", 11)
        )
        self.marker_count_var.set("Markers: —")
        self.roi_var.set("ROI: —")

    # ── Preview toggle ────────────────────────────────────────────────────────
    def _toggle_preview(self):
        if not self.running:
            self.start_preview_with_current_camera()
        else:
            self.stop_preview()

    def start_preview_with_current_camera(self):
        """Called internally; uses camera_index set via start_preview()."""
        idx = getattr(self, "_camera_index", 0)
        self.start_preview(idx)

    def start_preview(self, camera_index: int):
        """Open camera and begin frame loop."""
        if self.running:
            return

        self._camera_index = camera_index
        self.cap = open_camera(camera_index)

        if self.cap is None or not self.cap.isOpened():
            messagebox.showerror("Camera Error",
                                 f"Could not open camera {camera_index}.")
            self._show_placeholder()
            return

        set_normal_exposure(self.cap)
        self.running = True
        self.preview_btn.configure(
            text="⏹  Preview ON",
            bg=TECHMI_BLUE, fg="white"
        )
        self._log("Camera preview started.", "blue")
        self._frame_loop()

    def stop_preview(self):
        """Release camera and show placeholder."""
        self.running = False
        if self._after_id is not None:
            try:
                self.canvas.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self.preview_btn.configure(
            text="▶  Preview OFF",
            bg="#eef2ff", fg=TECHMI_BLUE
        )
        self._show_placeholder()
        self._log("Camera preview stopped.", "blue")

    # ── Frame loop ────────────────────────────────────────────────────────────
    def _frame_loop(self):
        if not self.running:
            return

        if self.cap is None or not self.cap.isOpened():
            self.marker_count_var.set("Markers: camera lost")
            self._after_id = self.canvas.after(200, self._frame_loop)
            return

        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.marker_count_var.set("Markers: frame failed")
            self._after_id = self.canvas.after(100, self._frame_loop)
            return

        display = frame.copy()

        # ArUco detection (always run for status, draw only if overlay on)
        corners, ids = detect_aruco_markers(display)
        marker_count = 0 if ids is None else len(ids)
        self.marker_count_var.set(f"Markers: {marker_count} detected")

        if self.show_overlay:
            if corners is not None and ids is not None:
                cv.aruco.drawDetectedMarkers(display, corners, ids)
            roi_pts = get_roi_corners(corners, ids)
            if roi_pts is not None:
                cv.polylines(
                    display,
                    [roi_pts.astype(int)],
                    isClosed=True,
                    color=(0, 255, 0),
                    thickness=2
                )
                self.roi_var.set("ROI: Found")
            else:
                self.roi_var.set("ROI: Not found")
        else:
            self.roi_var.set("ROI: overlay off")

        # Resize to fit canvas
        h, w = display.shape[:2]
        scale    = min(PREVIEW_W / w, PREVIEW_H / h)
        new_w    = int(w * scale)
        new_h    = int(h * scale)
        resized  = cv.resize(display, (new_w, new_h))
        rgb      = cv.cvtColor(resized, cv.COLOR_BGR2RGB)
        pil_img  = Image.fromarray(rgb)
        tk_img   = ImageTk.PhotoImage(pil_img)

        # Centre on canvas
        x_off = (PREVIEW_W - new_w) // 2
        y_off = (PREVIEW_H - new_h) // 2

        self.canvas.delete("all")
        self.canvas.configure(bg="#000000")
        self.canvas.create_image(x_off, y_off, image=tk_img, anchor="nw")
        self.current_tk_image = tk_img   # keep reference

        self._after_id = self.canvas.after(33, self._frame_loop)   # ~30 fps

    # ── Overlay toggle ────────────────────────────────────────────────────────
    def _toggle_overlay(self):
        self.show_overlay = not self.show_overlay
        if self.show_overlay:
            self.overlay_btn.configure(
                text="◎  ROI Overlay: ON",
                fg=SUCCESS
            )
        else:
            self.overlay_btn.configure(
                text="◎  ROI Overlay: OFF",
                fg=TEXT_MUTED
            )

    # ── Laser ─────────────────────────────────────────────────────────────────
    def set_laser(self, relay: "LaserRelay"):
        """Attach an already-opened LaserRelay instance."""
        self.laser = relay

    def _toggle_laser(self):
        if self.laser is None:
            # Try to open
            try:
                self.laser = LaserRelay()
                self.laser.open()
                self.laser.off()
                self.laser_is_on = False
                self._log("Laser relay connected.", "blue")
            except Exception as e:
                messagebox.showerror("Laser Error", str(e))
                self.laser = None
                return

        try:
            if self.laser_is_on:
                self.laser.off()
                self.laser_is_on = False
                self.laser_btn.configure(
                    text="⬤  Laser: OFF",
                    bg=NAVY_2, fg="#9ca3af"
                )
                self._log("Laser OFF.", "blue")
            else:
                self.laser.on()
                self.laser_is_on = True
                self.laser_btn.configure(
                    text="⬤  Laser: ON",
                    bg="#16a34a", fg="white"
                )
                self._log("Laser ON.", "blue")
        except Exception as e:
            self.laser_is_on = False
            messagebox.showerror("Laser Error", str(e))

    def get_laser_state(self) -> bool:
        return self.laser_is_on

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def destroy(self):
        """Release resources. Call before closing the main window."""
        self.running = False
        if self._after_id is not None:
            try:
                self.canvas.after_cancel(self._after_id)
            except Exception:
                pass
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self.laser is not None:
            try:
                self.laser.off()
                self.laser.close()
            except Exception:
                pass
            self.laser = None

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _log(self, message: str, category: str = "gray"):
        if self.log_callback:
            self.log_callback(message, category)