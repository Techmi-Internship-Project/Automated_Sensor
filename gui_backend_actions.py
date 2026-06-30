import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import re
import time
import math
from pathlib import Path
from PIL import Image, ImageTk

from gui_theme import format_elapsed
from organism_menu import get_organism_options
from camera_tools import scan_available_cameras
from startup_recovery import (
    current_folder_has_contents,
    wipe_folder_contents,
    move_run_to_training,
    build_training_destination
)


class BackendActionsMixin:
    """
    GUI section mixin split out of the original SensorGUI class.
    """

    def create_new_organism(self):
            name = simpledialog.askstring("Create New Organism",
                                          "Enter organism name:")
            if name is None:
                return
            name = name.strip().replace(" ", "_").lower()
            if not name:
                messagebox.showerror("Error", "Organism name cannot be empty.")
                return
            if not re.match(r'^[a-zA-Z0-9_]+$', name):
                messagebox.showerror(
                    "Error",
                    "Name can only contain letters, numbers, and underscores.")
                return
            (Path(self.training_folder) / name).mkdir(parents=True, exist_ok=True)
            self.refresh_organism_menu()
            self.organism.set(name)
            messagebox.showinfo("Organism Created", f"Created: {name}")
            self._append_log(f"New organism created: {name}.", "gray")

    def refresh_organism_menu(self):
            # Options are re-read when the dropdown is opened
            pass

    def load_available_cameras(self):
            self.available_cameras    = scan_available_cameras()
            self.camera_label_to_index = {}
            for cam in self.available_cameras:
                self.camera_label_to_index[cam["label"]] = cam["index"]

    def refresh_camera_menu_on_open(self):
            if self.controller.is_running:
                return
            prev = self.selected_camera.get()
            self.load_available_cameras()
            opts = list(self.camera_label_to_index.keys())
            if opts:
                if prev not in opts:
                    self.selected_camera.set(opts[0])
            else:
                self.selected_camera.set("No cameras found")

    def get_selected_camera_index(self):
            label = self.selected_camera.get()
            if label not in self.camera_label_to_index:
                raise RuntimeError("No valid camera selected.")
            return self.camera_label_to_index[label]

    def start_experiment(self):
            organism = self.organism.get().strip()
            if not organism:
                messagebox.showerror("Error", "No organism selected.")
                return

            try:
                cam_idx  = self.get_selected_camera_index()
                duration = self.get_duration_seconds_from_inputs()
                interval = self.get_interval_seconds_from_inputs()
                if interval > duration:
                    messagebox.showerror("Error",
                                         "Interval cannot be longer than duration.")
                    return
            except (ValueError, RuntimeError) as e:
                messagebox.showerror("Error", str(e))
                return

            try:
                run_id = self.controller.start_experiment(
                    microorganism_type=organism,
                    camera_index=cam_idx,
                    duration_seconds=duration,
                    interval_seconds=interval,
                    output_root=self.current_folder
                )
                self.run_id_var.set(str(run_id))
                self.status.set("Running")
                self.error_var.set("—")
                self.last_seen_alert_id = 0
                self.alert_popup_open   = False
                self.update_control_states()
                self._append_log(
                    f"Experiment started. Run ID: {run_id}.", "gray")
            except RuntimeError as e:
                messagebox.showerror("Error", str(e))

    def stop_experiment(self):
            if not self.controller.is_running:
                return
            if not messagebox.askyesno("Confirm Stop",
                                       "Stop the current experiment?\n"
                                       "This run will be interrupted."):
                return
            self.controller.stop_experiment()
            self.stop_requested = True
            self.status.set("Stop requested…")
            self._append_log("Stop requested by user.", "gray")

    def confirm_exit(self):
            if not self.controller.is_running:
                self._cleanup()
                self.root.destroy()
                return
            if not messagebox.askyesno(
                    "Experiment Running",
                    "An experiment is running.\nStop it and exit?"):
                return
            self.controller.stop_experiment()
            self._cleanup()
            self.root.after(600, self.root.destroy)

    def _cleanup(self):
            self._stop_preview()
            if self._laser:
                try:
                    self._laser.off()
                    self._laser.close()
                except Exception:
                    pass

    def update_status_loop(self):
            st = self.controller.get_status()
            elapsed   = st.get("elapsed_seconds",         0.0)
            duration  = st.get("duration_seconds",         0.0)
            captures  = st.get("capture_count",            0)
            run_folder= st.get("run_folder",               None)
            last_img  = st.get("last_saved_image",         None)
            last_msg  = st.get("last_message",             "Idle")
            run_ok    = st.get("run_completed_successfully", False)

            alert_msg = st.get("alert_message", None)
            alert_id  = st.get("alert_id",      0)

            if (alert_msg is not None
                    and alert_id != self.last_seen_alert_id
                    and not self.alert_popup_open):
                self.last_seen_alert_id = alert_id
                self.alert_popup_open   = True
                try:
                    messagebox.showwarning("Capture Warning", alert_msg)
                    self._append_log(f"Warning: {alert_msg}", "red")
                finally:
                    self.alert_popup_open = False

            if self.controller.last_error:
                self.error_var.set(self.controller.last_error)
                self._append_log(f"Error: {self.controller.last_error}", "red")

            # Move completed run
            if (not self.controller.is_running
                    and self.controller.last_run_folder is not None
                    and run_ok):
                done_folder = self.controller.last_run_folder
                dest = build_training_destination(done_folder, self.training_folder)
                ok = move_run_to_training(
                    done_folder,
                    training_folder=self.training_folder,
                    current_folder=self.current_folder
                )
                self.controller.last_run_folder = None
                wipe_folder_contents(self.current_folder)

                if ok and dest and str(dest) != self.last_summary_dest:
                    self.last_summary_dest = str(dest)
                    self._append_log(
                        f"Run complete. Moved to {dest.name}.", "green")
                    self._show_run_summary(run_folder, captures, elapsed)
                    self._last_run_var.set(
                        dest.name if dest else "—")
                    self._last_capture_var.set(
                        time.strftime("%H:%M:%S"))

            self.update_control_states()

            # Progress
            if duration > 0:
                pct = max(0.0, min(100.0, elapsed / duration * 100))
                rem = max(0.0, duration - elapsed)
            else:
                pct, rem = 0.0, 0.0

            self.progress_pct.set(pct)
            self._draw_donut(pct)
            self.elapsed.set(format_elapsed(elapsed))
            self.remaining.set(format_elapsed(rem))

            total_est = (int(duration // (st.get("interval_seconds", 1) or 1))
                         if duration > 0 else 0)
            self.capture_ratio.set(f"{captures} / {self.estimated_capture_count}")

            self.run_folder_var.set(str(run_folder) if run_folder else "—")
            self.last_img_var.set(str(last_img) if last_img else "—")

            if last_msg and last_msg != self.last_msg_var.get():
                self.last_msg_var.set(last_msg)
                if self.controller.is_running:
                    self._append_log(last_msg, "green")

            # System ready indicator
            ready_text = "⬤  System Ready" if not self.controller.is_running \
                else "⬤  Running"
            ready_bg = "#0d2e1a" if not self.controller.is_running else "#1a2e0d"
            try:
                self.system_ready_lbl.configure(text=ready_text, bg=ready_bg)
            except Exception:
                pass

            self.root.after(200, self.update_status_loop)

    def update_control_states(self):
            running  = self.controller.is_running
            stopping = self.stop_requested

            # Start / stop
            start_state = "disabled" if running else "normal"
            stop_state  = "normal" if (running and not stopping) else "disabled"
            self.start_button.configure(state=start_state)
            self.stop_button.configure(state=stop_state)

            if running and not stopping:
                self.status.set("Running")
            elif running and stopping:
                self.status.set("Stopping…")
            else:
                self.stop_requested = False
                self.status.set("Idle")

            # Idle-only widgets
            idle_state = "disabled" if running else "normal"
            for w in self._idle_only_widgets:
                try:
                    w.configure(state=idle_state)
                except Exception:
                    pass

            # Live adjustment buttons
            adj_state = "normal" if (running and not stopping) else "disabled"
            for w in self._run_adjust_btns:
                try:
                    w.configure(state=adj_state)
                except Exception:
                    pass

            self.update_recovery_button_state()

