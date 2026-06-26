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
    NAVY,
    NAVY_2,
    SUCCESS,
    TECHMI_BLUE,
    TEXT_DARK,
    TEXT_MUTED,
    WARNING,
    _btn,
    _card,
    _section_label,
)

from camera_settings import (
    get_camera_profile,
    save_camera_profile,
    get_default_camera_settings,
    save_camera_settings
)

PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 360
class CameraPanelMixin:
    """
    GUI section mixin split out of the original SensorGUI class.
    """

    def _build_camera_preview_panel(self, parent):
            card, c = _card(parent, "CAMERA PREVIEW", "▣")
            card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
            c.grid_columnconfigure(0, weight=1)

            # Control bar
            ctrl = tk.Frame(c, bg=CARD_BG)
            ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 6))

            self._preview_toggle_btn = _btn(
                ctrl, "▶  Preview OFF",
                self._toggle_preview, kind="ghost"
            )
            self._preview_toggle_btn.configure(
                bg="#eef2ff", fg=TECHMI_BLUE,
                font=(FONT_BRAND, 10, "bold")
            )
            self._preview_toggle_btn.pack(side=tk.LEFT)

            self._overlay_btn = _btn(
                ctrl, "◎  ROI Overlay: OFF",
                self._toggle_overlay, kind="ghost"
            )
            self._overlay_btn.pack(side=tk.LEFT, padx=(6, 0))

            # Laser toggle (right)
            self._laser_btn = tk.Button(
                ctrl, text="⬤  Laser: OFF",
                command=self._toggle_laser,
                bg=NAVY_2, fg="#9ca3af",
                activebackground=NAVY, activeforeground="white",
                relief="flat", bd=0,
                font=(FONT_BRAND, 10, "bold"),
                padx=12, pady=4, cursor="hand2"
            )
            self._laser_btn.pack(side=tk.RIGHT)

            # Canvas
            self._PREV_W, self._PREV_H = PREVIEW_WIDTH, PREVIEW_HEIGHT

            preview_holder = tk.Frame(c, bg=CARD_BG)
            preview_holder.grid(row=1, column=0, pady=(0,4))

            # Preview canvas
            self._preview_canvas = tk.Canvas(
                preview_holder, 
                width=self._PREV_W,
                height=self._PREV_H,
                bg="#0a0f1e",
                highlightthickness=0,
                bd=0
            )

            self._preview_canvas.pack(side=tk.LEFT)
            self._draw_preview_placeholder()
            
            # Status bar
            sb = tk.Frame(c, bg=CARD_BG)
            sb.grid(row=2, column=0, sticky="ew", pady=(4, 0))
            self._roi_var     = tk.StringVar(value="ROI: —")
            self._marker_var  = tk.StringVar(value="Markers: —")
            tk.Label(sb, textvariable=self._roi_var,
                     bg=CARD_BG, fg=TEXT_MUTED,
                     font=(FONT_BRAND, 9)).pack(side=tk.LEFT)
            tk.Label(sb, textvariable=self._marker_var,
                     bg=CARD_BG, fg=TEXT_MUTED,
                     font=(FONT_BRAND, 9)).pack(side=tk.RIGHT)

    
    def _draw_preview_placeholder(self):
            """
            Draws TECHMI logo placeholder when camera preview is off
            """
            cv = self._preview_canvas
            cv.delete("all")
            cv.configure(bg="#0a0f1e")

            if self._logo_photo is None:
                try:
                    img = Image.open("logo_azul.png").convert("RGBA")
                    # Scale logo 
                    target_width = int(self._PREV_W * 0.6)
                    scale = target_width / img.width
                    target_height = max(1, int(img.height * scale))

                    # Resize smoothly
                    logo_image = img.resize((target_width, target_height), Image.LANCZOS)
                
                    # Make subtle
                    alpha = logo_image.getchannel("A").point(lambda p: int(p * 0.24))
                    logo_image.putalpha(alpha)

                    # Store reference so Tkinter does not garbage collect it
                    self._logo_photo = ImageTk.PhotoImage(logo_image)

                except Exception:
                    self._logo_photo = None

            cx, cy = self._PREV_W // 2, self._PREV_H // 2

            # Draw if available
            if self._logo_photo:
                cv.create_image(cx, cy - 20,
                                image=self._logo_photo, anchor="center")
            else:
                cv.create_text(cx, cy - 20, text="TECHMI",
                               fill="#1a2a4a", font=(FONT_BRAND, 36, "bold"))

            cv.create_text(cx, cy + 60,
                           text="Press ▶ Preview to start camera feed",
                           fill="#95A5C1", font=(FONT_BRAND, 11))


    def _toggle_preview(self):
            if not self._preview_running:
                self._start_preview()
            else:
                self._stop_preview()

    def _start_preview(self):
            """
            Opens selected camera and starts live preview loop
            """
            try:
                cam_idx = self.get_selected_camera_index()
            except RuntimeError as e:
                messagebox.showerror("Camera Error", str(e))
                return

            from camera import open_camera, set_normal_exposure
            import cv2 as cv

            self._preview_cap = open_camera(cam_idx)

            # Check if failed to open
            if self._preview_cap is None or not self._preview_cap.isOpened():
                messagebox.showerror("Camera Error",
                                     f"Could not open camera {cam_idx}.")
                return

            set_normal_exposure(self._preview_cap)
            self._preview_running = True
            self._preview_toggle_btn.configure(
                text="⏹  Preview ON",
                bg=TECHMI_BLUE, fg="white"
            )
            self._append_log("Camera preview started.", "blue")
            self._preview_frame_loop()

    def _stop_preview(self):
            self._preview_running = False
            if self._preview_after_id:
                try:
                    self._preview_canvas.after_cancel(self._preview_after_id)
                except Exception:
                    pass
                self._preview_after_id = None
            if self._preview_cap:
                self._preview_cap.release()
                self._preview_cap = None

            self._preview_toggle_btn.configure(
                text="▶  Preview OFF",
                bg="#eef2ff", fg=TECHMI_BLUE
            )
            self._draw_preview_placeholder()
            self._append_log("Camera preview stopped.", "blue")

    def _preview_frame_loop(self):
            if not self._preview_running:
                return

            import cv2 as cv
            from aruco import detect_aruco_markers, get_roi_corners

            if self._preview_cap is None or not self._preview_cap.isOpened():
                self._preview_after_id = self._preview_canvas.after(
                    200, self._preview_frame_loop)
                return

            ok, frame = self._preview_cap.read()
            if not ok or frame is None:
                self._marker_var.set("Markers: frame failed")
                self._preview_after_id = self._preview_canvas.after(
                    100, self._preview_frame_loop)
                return

            display = frame.copy()
            corners, ids = detect_aruco_markers(display)
            cnt = 0 if ids is None else len(ids)
            self._marker_var.set(f"Markers: {cnt} detected")

            if self._show_overlay:
                if corners is not None and ids is not None:
                    cv.aruco.drawDetectedMarkers(display, corners, ids)
                roi = get_roi_corners(corners, ids)
                if roi is not None:
                    cv.polylines(display, [roi.astype(int)],
                                 isClosed=True, color=(0, 255, 0), thickness=2)
                    self._roi_var.set("ROI: Found")
                else:
                    self._roi_var.set("ROI: Not found")
            else:
                self._roi_var.set("ROI: overlay off")

            # Read camera frame size.
            h, w = display.shape[:2]

            # Use fixed preview canvas size.
            canvas_w = self._PREV_W
            canvas_h = self._PREV_H

            # Scale image to cover the entire canvas.
            # This avoids black bars by cropping excess image instead of letterboxing.
            scale = max(canvas_w / w, canvas_h / h)

            # Calculate resized dimensions.
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))

            # Use good interpolation depending on whether the image is shrinking or growing.
            interpolation = cv.INTER_AREA if scale < 1.0 else cv.INTER_LINEAR

            # Resize camera image.
            resized = cv.resize(
                display,
                (nw, nh),
                interpolation=interpolation
            )

            # Center-crop resized image to exactly match canvas size.
            x_start = max(0, (nw - canvas_w) // 2)
            y_start = max(0, (nh - canvas_h) // 2)
            cropped = resized[
                y_start:y_start + canvas_h,
                x_start:x_start + canvas_w
            ]

            # Convert OpenCV BGR image to RGB for Tkinter.
            rgb = cv.cvtColor(cropped, cv.COLOR_BGR2RGB)

            # Convert NumPy image to Pillow image.
            pil = Image.fromarray(rgb)

            # Convert Pillow image to Tkinter image.
            tkimg = ImageTk.PhotoImage(pil)

            # Clear old frame.
            self._preview_canvas.delete("all")

            # Draw image at top-left because it already matches the canvas size.
            self._preview_canvas.create_image(
                0,
                0,
                image=tkimg,
                anchor="nw"
            )

            # Store reference so Tkinter does not garbage collect the frame.
            self._preview_tk_img = tkimg
            

            self._preview_after_id = self._preview_canvas.after(33, self._preview_frame_loop)

    def _toggle_overlay(self):
            self._show_overlay = not self._show_overlay
            if self._show_overlay:
                self._overlay_btn.configure(text="◎  ROI Overlay: ON",
                                            fg=SUCCESS)
            else:
                self._overlay_btn.configure(text="◎  ROI Overlay: OFF",
                                            fg=TEXT_MUTED)

    def _toggle_laser(self):
            if self._laser is None:
                try:
                    from laser_control import LaserRelay
                    self._laser = LaserRelay()
                    self._laser.open()
                    self._laser.off()
                    self._laser_on = False
                    self._append_log("Laser relay connected.", "blue")
                except Exception as e:
                    messagebox.showerror("Laser Error", str(e))
                    self._laser = None
                    return

            try:
                if self._laser_on:
                    self._laser.off()
                    self._laser_on = False
                    self._laser_btn.configure(
                        text="⬤  Laser: OFF", bg=NAVY_2, fg="#9ca3af")
                    self._append_log("Laser OFF.", "blue")
                else:
                    self._laser.on()
                    self._laser_on = True
                    self._laser_btn.configure(
                        text="⬤  Laser: ON", bg="#16a34a", fg="white")
                    self._append_log("Laser ON.", "blue")
            except Exception as e:
                self._laser_on = False
                messagebox.showerror("Laser Error", str(e))

    def _build_camera_settings_panel(self, parent):
            card, c = _card(parent, "CAMERA SETTINGS", "☷")
            card.grid(row=1, column=0, sticky="ew", pady=(0, 8))
            c.grid_columnconfigure(0, weight=1)
            c.grid_columnconfigure(1, weight=0)

            # Warning
            tk.Label(
                c,
                text="⚠  Autofocus, Auto Exposure & Auto White Balance must "
                     "be disabled manually on the camera.",
                fg=WARNING, bg=CARD_BG,
                font=(FONT_BRAND, 9, "bold"),
                wraplength=520, anchor="w", justify="left"
            ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

            # Exposure profile buttons
            _section_label(c, "Exposure Profile").grid(
                row=1, column=0, sticky="w", pady=(0, 4))

            pf = tk.Frame(c, bg=CARD_BG)
            pf.grid(row=2, column=0, sticky="w", pady=(0, 12))

            self._norm_btn = tk.Button(
                pf, text="Normal", relief="flat", bd=0,
                bg=TECHMI_BLUE, fg="white",
                activebackground=TECHMI_BLUE, activeforeground="white",
                font=(FONT_BRAND, 11, "bold"),
                padx=14, pady=5, cursor="hand2",
                command=lambda: self._switch_cam_profile("normal")
            )
            self._norm_btn.pack(side=tk.LEFT, padx=(0, 4))

            self._low_btn = tk.Button(
                pf, text="Low", relief="flat", bd=0,
                bg=CARD_BG, fg=TEXT_MUTED,
                activebackground=TECHMI_BLUE, activeforeground="white",
                font=(FONT_BRAND, 11),
                padx=14, pady=5, cursor="hand2",
                highlightthickness=1, highlightbackground=CARD_BORDER,
                command=lambda: self._switch_cam_profile("low")
            )
            self._low_btn.pack(side=tk.LEFT)

            # Exposure slider
            _section_label(c, "Exposure").grid(
                row=3, column=0, sticky="w", pady=(0, 2))

            self._exposure_slider = tk.Scale(
                c, from_=-13, to=0, resolution=1,
                orient=tk.HORIZONTAL,
                variable=self.exposure_var,
                command=self._on_cam_slider_change,
                bg=CARD_BG, fg=TEXT_DARK,
                troughcolor="#e8edf5",
                activebackground=TECHMI_BLUE,
                highlightthickness=0,
                sliderrelief="flat",
                length=300, showvalue=True
            )
            self._exposure_slider.grid(row=4, column=0, sticky="ew",
                                       pady=(0, 8))

            # Gain slider
            _section_label(c, "Gain").grid(
                row=5, column=0, sticky="w", pady=(0, 2))

            self._gain_slider = tk.Scale(
                c, from_=0, to=255, resolution=1,
                orient=tk.HORIZONTAL,
                variable=self.gain_var,
                command=self._on_cam_slider_change,
                bg=CARD_BG, fg=TEXT_DARK,
                troughcolor="#e8edf5",
                activebackground=TECHMI_BLUE,
                highlightthickness=0,
                sliderrelief="flat",
                length=300, showvalue=True
            )
            self._gain_slider.grid(row=6, column=0, sticky="ew", pady=(0, 10))

            # Save / Reset buttons
            btn_row = tk.Frame(c, bg=CARD_BG)
            btn_row.grid(row=7, column=0, columnspan=2, sticky="ew")

            _btn(btn_row, "💾  Save Profile",
                 self._save_cam_profile, "primary").pack(
                side=tk.LEFT, padx=(0, 6))
            _btn(btn_row, "↺  Reset to Default",
                 self._reset_cam_profile, "secondary").pack(side=tk.LEFT)

            self._cam_status_var = tk.StringVar(value="")
            tk.Label(c, textvariable=self._cam_status_var,
                     fg=SUCCESS, bg=CARD_BG,
                     font=(FONT_BRAND, 9)).grid(
                row=8, column=0, sticky="w", pady=(4, 0))

    def _switch_cam_profile(self, name: str):
            self.cam_profile.set(name)
            self._norm_btn.configure(
                bg=TECHMI_BLUE if name == "normal" else CARD_BG,
                fg="white" if name == "normal" else TEXT_MUTED,
                font=(FONT_BRAND, 11, "bold" if name == "normal" else "normal")
            )
            self._low_btn.configure(
                bg=TECHMI_BLUE if name == "low" else CARD_BG,
                fg="white" if name == "low" else TEXT_MUTED,
                font=(FONT_BRAND, 11, "bold" if name == "low" else "normal")
            )
            self._load_camera_profile_into_ui(name)
            self._apply_cam_settings_to_preview()
            self._append_log(f"Exposure profile: {name}.", "blue")

    def _load_camera_profile_into_ui(self, profile_name: str):
            try:
                profile = get_camera_profile(profile_name)
                self.exposure_var.set(profile.get("exposure", -6))
                self.gain_var.set(profile.get("gain", 0))
            except Exception:
                pass

    def _on_cam_slider_change(self, _=None):
            self._apply_cam_settings_to_preview()

    def _apply_cam_settings_to_preview(self):
            import cv2 as cv
            if self._preview_cap and self._preview_cap.isOpened():
                self._preview_cap.set(cv.CAP_PROP_EXPOSURE,
                                      self.exposure_var.get())
                self._preview_cap.set(cv.CAP_PROP_GAIN, self.gain_var.get())

    def _save_cam_profile(self):
            profile_name = self.cam_profile.get()
            profile = {
                "exposure": self.exposure_var.get(),
                "gain":     self.gain_var.get(),
            }
            save_camera_profile(profile_name, profile)
            self._cam_status_var.set(f"Saved {profile_name} profile.")
            self._append_log(f"Camera profile '{profile_name}' saved.", "blue")

    def _reset_cam_profile(self):
            profile_name = self.cam_profile.get()
            defaults = get_default_camera_settings()
            if profile_name in defaults:
                save_camera_settings(defaults)
                self._load_camera_profile_into_ui(profile_name)
                self._apply_cam_settings_to_preview()
                self._cam_status_var.set(f"Reset {profile_name} to defaults.")
                self._append_log(
                    f"Camera profile '{profile_name}' reset to defaults.", "blue")

