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
)

PREVIEW_WIDTH = 600
PREVIEW_HEIGHT = 300

class HoverTip:
    """
    Small hover tooltip for info icons.
    """

    def __init__(self, widget, text):
        # Store the widget that owns the tooltip.
        self.widget = widget

        # Store the tooltip message.
        self.text = text

        # Toplevel window starts as missing.
        self.tip_window = None

        # Show tooltip when mouse enters widget.
        self.widget.bind("<Enter>", self.show)

        # Hide tooltip when mouse leaves widget.
        self.widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        # Do not open another tooltip if one already exists.
        if self.tip_window is not None:
            return

        # Get widget screen position.
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + 18

        # Create tooltip as a borderless popup.
        self.tip_window = tk.Toplevel(self.widget)

        # Remove normal window border.
        self.tip_window.wm_overrideredirect(True)

        # Position popup near the info icon.
        self.tip_window.wm_geometry(f"+{x}+{y}")

        # Tooltip label.
        tk.Label(
            self.tip_window,
            text=self.text,
            bg="#111827",
            fg="white",
            font=(FONT_BRAND, 8),
            padx=8,
            pady=5,
            justify="left",
            wraplength=230
        ).pack()

    def hide(self, event=None):
        # Destroy tooltip if it exists.
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


def _info_icon(parent, text, bg):
    """
    Creates a small hoverable info icon.
    """

    # Create the small info marker.
    icon = tk.Label(
        parent,
        text="ⓘ",
        bg=bg,
        fg=TEXT_MUTED,
        font=(FONT_BRAND, 9, "bold"),
        cursor="question_arrow"
    )

    # Attach tooltip behavior.
    HoverTip(icon, text)

    # Return icon so caller can grid/pack it.
    return icon


class FilledSliderInput(tk.Frame):
    """
    Custom slider row with:
    - filled blue track
    - draggable knob
    - editable numeric entry box
    - unit label
    """

    def __init__(
        self,
        parent,
        variable,
        from_,
        to,
        unit,
        command=None,
        width=220,
        height=28,
    ):
        # Initialize the parent frame.
        super().__init__(parent, bg=CARD_BG)

        # Store linked Tk variable.
        self.variable = variable

        # Store slider range.
        self.from_ = from_
        self.to = to

        # Store unit text.
        self.unit = unit

        # Store callback function.
        self.command = command

        # Store canvas dimensions.
        self.slider_width = width
        self.slider_height = height

        # Canvas draws track, fill, and knob.
        self.canvas = tk.Canvas(
            self,
            width=self.slider_width,
            height=self.slider_height,
            bg=CARD_BG,
            highlightthickness=0
        )
        self.canvas.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # Entry lets user type exact value.
        self.entry = tk.Entry(
            self,
            width=6,
            justify="center",
            textvariable=self.variable,
            font=(FONT_BRAND, 10),
            relief="flat",
            bg="white",
            fg=TEXT_DARK,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            highlightcolor=TECHMI_BLUE
        )
        self.entry.grid(row=0, column=1, sticky="e", padx=(0, 6))

        # Unit label goes after the input.
        tk.Label(
            self,
            text=self.unit,
            bg=CARD_BG,
            fg=TEXT_DARK,
            font=(FONT_BRAND, 10, "bold")
        ).grid(row=0, column=2, sticky="w")

        # Let canvas column stretch.
        self.grid_columnconfigure(0, weight=1)

        # Redraw when the variable changes.
        self.variable.trace_add("write", lambda *_: self.draw())

        # Update value when user clicks/drags slider.
        self.canvas.bind("<Button-1>", self._on_mouse)

        # Update value while user drags.
        self.canvas.bind("<B1-Motion>", self._on_mouse)

        # Validate typed value when Enter is pressed.
        self.entry.bind("<Return>", self._on_entry_commit)

        # Validate typed value when entry loses focus.
        self.entry.bind("<FocusOut>", self._on_entry_commit)

        # Initial draw.
        self.draw()

    def _value_to_x(self, value):
        # Padding keeps knob from being cut off.
        pad = 10

        # Convert value to 0..1 range.
        ratio = (float(value) - self.from_) / (self.to - self.from_)

        # Clamp ratio.
        ratio = max(0.0, min(1.0, ratio))

        # Convert ratio to x position.
        return pad + ratio * (self.slider_width - 2 * pad)

    def _x_to_value(self, x):
        # Padding keeps knob inside canvas.
        pad = 10

        # Clamp x to usable slider area.
        x = max(pad, min(self.slider_width - pad, x))

        # Convert x to 0..1 ratio.
        ratio = (x - pad) / (self.slider_width - 2 * pad)

        # Convert ratio to actual value.
        value = self.from_ + ratio * (self.to - self.from_)

        # Camera settings use integer values.
        return int(round(value))

    def _on_mouse(self, event):
        # Convert mouse x position to slider value.
        value = self._x_to_value(event.x)

        # Store value in linked variable.
        self.variable.set(value)

        # Run callback if provided.
        if self.command is not None:
            self.command(value)

    def _on_entry_commit(self, event=None):
        try:
            # Read typed value.
            value = int(float(self.variable.get()))
        except Exception:
            # Reset to minimum if input is invalid.
            value = self.from_

        # Clamp typed value.
        value = max(self.from_, min(self.to, value))

        # Store clamped value.
        self.variable.set(value)

        # Run callback if provided.
        if self.command is not None:
            self.command(value)

    def draw(self):
        # Clear old drawing.
        self.canvas.delete("all")

        # Track geometry.
        y = self.slider_height // 2
        pad = 10

        # Try reading current value.
        try:
            value = float(self.variable.get())
        except Exception:
            value = self.from_

        # Clamp value.
        value = max(self.from_, min(self.to, value))

        # Get knob x position.
        x = self._value_to_x(value)

        # Draw gray background track.
        self.canvas.create_line(
            pad,
            y,
            self.slider_width - pad,
            y,
            fill="#d9dee8",
            width=4,
            capstyle=tk.ROUND
        )

        # Draw blue filled track.
        self.canvas.create_line(
            pad,
            y,
            x,
            y,
            fill=TECHMI_BLUE,
            width=4,
            capstyle=tk.ROUND
        )

        # Draw slider knob.
        self.canvas.create_oval(
            x - 7,
            y - 7,
            x + 7,
            y + 7,
            fill=TECHMI_BLUE,
            outline=TECHMI_BLUE
        )

    def set_enabled(self, enabled: bool) : 
        state = tk.NORMAL if enabled else tk.DISABLED
        self.entry.configure(state=state)

        if enabled : 
            self.canvas.bind("<Button-1>", self._on_mouse)
            self.canvas.bind("<B1-Motion>", self._on_mouse)
        else : 
            self.canvas.unbind("<Button-1>")
            self.canvas.unbind("<B1-Motion>")
class CameraPanelMixin:
    """
    GUI section mixin split out of the original SensorGUI class.
    """

    def _build_camera_preview_panel(self, parent, row=0):
            card, c = _card(parent, "CAMERA PREVIEW", "▣")
            parent.grid_rowconfigure(row, weight=1)
            parent.grid_columnconfigure(0, weight=1)
            card.grid(row=row, column=0, sticky="nsew", pady=(0, 6))
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
                font=(FONT_BRAND, 8, "bold")
            )
            self._preview_toggle_btn.pack(side=tk.LEFT)

            self._overlay_btn = _btn(
                ctrl, "◎  ROI Overlay: OFF",
                self._toggle_overlay, kind="ghost"
            )
            self._overlay_btn.pack(side=tk.LEFT, padx=(6, 0))
            self._overlay_btn.configure(state=tk.DISABLED) # Disabled by default

            # Laser toggle (right)
            self._laser_btn = tk.Button(
                ctrl, text="⬤  Laser: OFF",
                command=self._toggle_laser,
                bg=NAVY_2, fg="#9ca3af",
                activebackground=NAVY, activeforeground="white",
                relief="flat", bd=0,
                font=(FONT_BRAND, 8, "bold"),
                padx=12, pady=4, cursor="hand2"
            )
            self._laser_btn.pack(side=tk.RIGHT)
            self._laser_btn.configure(state=tk.DISABLED)

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
                     font=(FONT_BRAND, 8)).pack(side=tk.LEFT)
            tk.Label(sb, textvariable=self._marker_var,
                     bg=CARD_BG, fg=TEXT_MUTED,
                     font=(FONT_BRAND, 8)).pack(side=tk.RIGHT)

    
    
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
                self._refresh_cam_btn.configure(state=tk.DISABLED)

            else:
                self._stop_preview()
                self._refresh_cam_btn.configure(state=tk.NORMAL)


    def _start_preview(self):
            """
            Opens selected camera and starts live preview loop
            """
            try:
                cam_idx  = self.get_selected_camera_index()
                cam_name = self.get_selected_camera_name()
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
            self._cam_display.configure(fg=TEXT_MUTED)
            self._cam_arrow.configure(fg=TEXT_MUTED)
            self._cam_fr.configure(highlightbackground=CARD_BORDER)
            self._laser_btn.configure(state=tk.NORMAL)
            self._overlay_btn.configure(state=tk.NORMAL)
            self._preview_toggle_btn.configure(
                text="⏹  Preview ON",
                bg=TECHMI_BLUE, fg="white"
            )
            self._append_log("Camera preview started.", "blue")
            self._preview_frame_loop()

    def _stop_preview(self):
            self._preview_running = False
            self._cam_display.configure(fg=TEXT_DARK)
            self._cam_arrow.configure(fg=TEXT_MUTED)
            if self._preview_after_id:
                try:
                    self._preview_canvas.after_cancel(self._preview_after_id)
                except Exception:
                    pass
                self._preview_after_id = None
            if self._preview_cap:
                self._preview_cap.release()
                self._preview_cap = None

            if self._laser is not None:
                try:
                    self._laser.off()
                    time.sleep(0.3)
                except Exception:
                    pass
                try:
                    self._laser.close()
                except Exception:
                    pass
                self._laser = None

            self._laser_on = False

            self._laser_btn.configure(text="⬤  Laser: OFF", bg=NAVY_2, fg="#9ca3af",
            state=tk.DISABLED)
            self._set_overlay(False)
            self._overlay_btn.configure(state=tk.DISABLED)
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

    def _set_overlay(self, enabled: bool) : 
        self._show_overlay = enabled
        if enabled : 
            self._overlay_btn.configure(text="◎  ROI Overlay: ON", fg=SUCCESS)
        else :
            self._overlay_btn.configure(text="◎  ROI Overlay: OFF", fg=TEXT_MUTED)


    def _toggle_laser(self):
            if self._laser is None:
                try:
                    from laser_control import LaserRelay
                    self._laser = LaserRelay(port=self._get_laser_port_override())
                    self._laser.open()
                    time.sleep(0.3)
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

    def _build_camera_settings_panel(self, parent, row=0):
        """
        Builds the Camera Settings panel using a 3-column layout.

        Left column:
            Exposure profile selector.

        Middle column:
            Exposure and gain sliders with text inputs.

        Right column:
            Warning message and save/reset buttons.
        """

        # Let this panel fill its slot.
        parent.grid_rowconfigure(row, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Create card.
        card, c = _card(parent, "CAMERA SETTINGS", "☷")
        card.grid(row=row, column=0, sticky="nsew")

        # Five-column grid:
        # 0 = profile column
        # 1 = divider
        # 2 = slider column
        # 3 = divider
        # 4 = actions/warning column
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(1, weight=0)
        c.grid_columnconfigure(2, weight=2)
        c.grid_columnconfigure(3, weight=0)
        c.grid_columnconfigure(4, weight=1)

        # Let content rows stay compact.
        c.grid_rowconfigure(0, weight=1)

        # ── Left column: exposure profile ─────────────────────────────────
        profile_col = tk.Frame(c, bg=CARD_BG)
        profile_col.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        profile_col.grid_columnconfigure(0, weight=1)

        # Label row with info icon.
        profile_label_row = tk.Frame(profile_col, bg=CARD_BG)
        profile_label_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        profile_label_row.grid_columnconfigure(0, weight=1)

        _section_label(profile_label_row, "Exposure Profile").grid(
            row=0,
            column=0,
            sticky="w"
        )

        _info_icon(
            profile_label_row,
            "Choose which saved camera profile is active. Normal is used for setup/preview. Low is used for laser capture.",
            bg=CARD_BG
        ).grid(row=0, column=1, sticky="e")

        # Profile buttons row.
        profile_buttons = tk.Frame(profile_col, bg=CARD_BG)
        profile_buttons.grid(row=1, column=0, sticky="ew")
        profile_buttons.grid_columnconfigure(0, weight=1)
        profile_buttons.grid_columnconfigure(1, weight=1)

        # Normal profile button.
        self._norm_btn = tk.Button(
            profile_buttons,
            text="Normal",
            relief="flat",
            bd=0,
            bg=TECHMI_BLUE,
            fg="white",
            activebackground=TECHMI_BLUE,
            activeforeground="white",
            font=(FONT_BRAND, 9, "bold"),
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self._switch_cam_profile("normal")
        )
        self._norm_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        # Low profile button.
        self._low_btn = tk.Button(
            profile_buttons,
            text="Low",
            relief="flat",
            bd=0,
            bg=CARD_BG,
            fg=TEXT_MUTED,
            activebackground=TECHMI_BLUE,
            activeforeground="white",
            font=(FONT_BRAND, 9),
            padx=10,
            pady=5,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            command=lambda: self._switch_cam_profile("low")
        )
        self._low_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

       
        # ── Divider 1 ─────────────────────────────────────────────────────
        tk.Frame(
            c,
            bg=CARD_BORDER,
            width=1
        ).grid(row=0, column=1, sticky="ns", padx=(0, 12))

        # ── Middle column: sliders ────────────────────────────────────────
        slider_col = tk.Frame(c, bg=CARD_BG)
        slider_col.grid(row=0, column=2, sticky="nsew", padx=(0, 12))
        slider_col.grid_columnconfigure(0, weight=1)

        # Exposure label row.
        exposure_label_row = tk.Frame(slider_col, bg=CARD_BG)
        exposure_label_row.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        exposure_label_row.grid_columnconfigure(0, weight=1)

        _section_label(exposure_label_row, "Exposure").grid(
            row=0,
            column=0,
            sticky="w"
        )

        _info_icon(
            exposure_label_row,
            "Camera exposure controls how long the sensor collects light. Lower values usually reduce brightness and motion blur.",
            bg=CARD_BG
        ).grid(row=0, column=1, sticky="e")

        # Exposure slider with numeric input.
        self._exposure_slider = FilledSliderInput(
            slider_col,
            variable=self.exposure_var,
            from_=-13,
            to=0,
            unit="EV",
            command=self._on_cam_slider_change,
            width=240
        )
        self._exposure_slider.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # Gain label row.
        gain_label_row = tk.Frame(slider_col, bg=CARD_BG)
        gain_label_row.grid(row=2, column=0, sticky="ew", pady=(0, 3))
        gain_label_row.grid_columnconfigure(0, weight=1)

        _section_label(gain_label_row, "Gain").grid(
            row=0,
            column=0,
            sticky="w"
        )

        _info_icon(
            gain_label_row,
            "Camera gain digitally boosts brightness. Higher gain can make the image brighter but usually adds noise.",
            bg=CARD_BG
        ).grid(row=0, column=1, sticky="e")

        # Gain slider with numeric input.
        self._gain_slider = FilledSliderInput(
            slider_col,
            variable=self.gain_var,
            from_=0,
            to=255,
            unit="dB",
            command=self._on_cam_slider_change,
            width=240
        )
        self._gain_slider.grid(row=3, column=0, sticky="ew")

        # ── Divider 2 ─────────────────────────────────────────────────────
        tk.Frame(
            c,
            bg=CARD_BORDER,
            width=1
        ).grid(row=0, column=3, sticky="ns", padx=(0, 12))

        # ── Right column: warning and buttons ─────────────────────────────
        action_col = tk.Frame(c, bg=CARD_BG)
        action_col.grid(row=0, column=4, sticky="nsew")
        action_col.grid_columnconfigure(0, weight=1)

        # Warning label.
        tk.Label(
            action_col,
            text="⚠  Disable camera auto settings manually before running.",
            fg=WARNING,
            bg=CARD_BG,
            font=(FONT_BRAND, 8, "bold"),
            anchor="w",
            justify="left",
            wraplength=180
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # Save profile button.
        self._save_btn = _btn(
            action_col,
            "💾  Save Profile",
            self._save_cam_profile,
            "primary"
        )
        self._save_btn.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        # Reset button.
        self._reset_btn = _btn(
            action_col,
            "↺  Reset to Default",
            self._reset_cam_profile,
            "secondary"
        )
        self._reset_btn.grid(row=2, column=0, sticky="ew")

        self._idle_only_widgets += [
            self._norm_btn,
            self._low_btn,
            self._exposure_slider,
            self._gain_slider,
            self._save_btn,
            self._reset_btn,
            self._preview_toggle_btn
        ]

        
    def _switch_cam_profile(self, name: str):
            self.cam_profile.set(name)
            self._norm_btn.configure(
                bg=TECHMI_BLUE if name == "normal" else CARD_BG,
                fg="white" if name == "normal" else TEXT_MUTED,
                font=(FONT_BRAND, 9, "bold" if name == "normal" else "normal")
            )
            self._low_btn.configure(
                bg=TECHMI_BLUE if name == "low" else CARD_BG,
                fg="white" if name == "low" else TEXT_MUTED,
                font=(FONT_BRAND, 9, "bold" if name == "low" else "normal")
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
                "exposure": int(self.exposure_var.get()),
                "gain":     int(self.gain_var.get()),
            }
            save_camera_profile(profile_name, profile)
            self._append_log(f"Camera profile '{profile_name}' saved.", "blue")

    def _reset_cam_profile(self):
            profile_name = self.cam_profile.get()
            self._load_camera_profile_into_ui(profile_name)
            self._apply_cam_settings_to_preview()
            self._append_log(
                f"Camera profile '{profile_name}' reset to saved settings.", "blue")

