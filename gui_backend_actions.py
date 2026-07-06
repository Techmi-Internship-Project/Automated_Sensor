import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import re
import time
import math
from pathlib import Path
from PIL import Image, ImageTk

from gui_theme import format_elapsed, WARNING
from organism_menu import get_organism_options
from camera_tools import scan_available_cameras
from startup_recovery import (
    current_folder_has_contents,
    wipe_folder_contents,
    move_run_to_training,
    build_training_destination
)
from gui_camera_panel import FilledSliderInput
from config import load_app_settings


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
        """
        Loads available cameras and names
        """
        from config import load_app_settings
        settings = load_app_settings()
        self.available_cameras = scan_available_cameras()
        self.camera_label_to_index = {}
        self.camera_label_to_name  = {}
        for cam in self.available_cameras:
            self.camera_label_to_index[cam["label"]] = cam["index"]
            self.camera_label_to_name[cam["label"]]  = cam.get("name")
    
    
    def refresh_camera_menu(self):
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

    def get_selected_camera_name(self):
            label = self.selected_camera.get()
            return self.camera_label_to_name.get(label)

    def start_experiment(self):
            organism = self.organism.get().strip()
            if not organism:
                messagebox.showerror("Error", "No organism selected.")
                return

            try:
                # Clear any error from previous experiment 
                self.controller.last_error = None
                self.error_var.set("-")

                cam_idx  = self.get_selected_camera_index()
                cam_name = self.get_selected_camera_name()
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
                # Release preview camera and laser relay so the experiment can open them
                if self._preview_running or self._laser is not None:
                    self._stop_preview()

                # Read ArUco recovery settings (defaults used if never opened Settings).
                continue_roi = getattr(self, "_continue_with_prev_roi_var",
                                       None)
                max_fails    = getattr(self, "_max_aruco_failures_var", None)

                s = load_app_settings()

                run_id = self.controller.start_experiment(
                    microorganism_type=organism,
                    camera_index=cam_idx,
                    camera_name=cam_name,
                    duration_seconds=duration,
                    interval_seconds=interval,
                    output_root=self.current_folder,
                    continue_with_prev_roi=continue_roi.get() if continue_roi else True,
                    max_consecutive_failures=int(max_fails.get()) if max_fails else 3,
                    laser_port=self._get_laser_port_override(),
                    standalone_mode=s.get("standalone_mode", True),
                    retrain_model=s.get("retrain_model", False),
                    handshake_timeout_hours=s.get("handshake_timeout_hours", 1.0)
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

    def _request_end_after_next(self):
            if not self.controller.is_running:
                return
            self.controller.end_after_next_capture()
            self._end_after_next_requested = True
            self._end_after_next_btn.configure(text="✓ Queued", state="disabled")
            self._append_log("Experiment will end after next capture.", "yellow")

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
                    time.sleep(0.2)
                    self._laser.close()
                    
                except Exception:
                    pass

    def update_status_loop(self):
            # Prevent reentrant calls spawned by Tkinter's modal-dialog nested event
            # loop (e.g. messagebox.showwarning).  Without this guard, every 200 ms
            # tick that fires while a popup is open spawns a new parallel loop, and
            # after a few seconds the canvas is being redrawn hundreds of times per
            # second, flooding the event queue and freezing the display.
            try: 
                if self._status_loop_active:
                    self.root.after(200, self.update_status_loop)
                    return
                self._status_loop_active = True
                try:
                    self._update_status_loop_body()
                finally:
                    self._status_loop_active = False

            except Exception as e: 
                print(f"Update status error: {e}")

            finally:
                self.root.after(200, self.update_status_loop)

    def _update_status_loop_body(self):
            st = self.controller.get_status()
            elapsed   = st.get("elapsed_seconds",         0.0)
            duration  = st.get("duration_seconds",         0.0)
            captures  = st.get("capture_count",            0)
            run_folder= st.get("run_folder",               None)
            last_img  = st.get("last_saved_image",         None)
            last_msg  = st.get("last_message",             "Idle")
            last_msg_category = st.get("last_message_category", "green")
            run_ok    = st.get("run_completed_successfully", False)

            if run_folder and run_folder != "-" :
                 self._active_log_path = Path(run_folder) / "run.log"

            alert_msg = st.get("alert_message", None)
            alert_id  = st.get("alert_id",      0)

            if (alert_msg is not None
                    and alert_id != self.last_seen_alert_id
                    and not self.alert_popup_open):
                self.last_seen_alert_id = alert_id
                self.alert_popup_open   = True
                try:
                    messagebox.showwarning("Capture Warning", alert_msg)
                finally:
                    self.alert_popup_open = False

            if self.controller.last_error:
                err = self.controller.last_error
                self.error_var.set(err)
                self._append_log(f"Error: {err}", "red")
                self.controller.last_error = None

            state = st.get("state")

            if state == "awaiting_csv" and not getattr(self, "_csv_uploaded_prompted", False) :
                self._csv_uploaded_prompted = True
                self._csv_upload_run_folder = run_folder # Because this will get wiped in folder move
                self._prompt_csv_upload(self._csv_upload_run_folder)

            # Move completed run
            if (not self.controller.is_running
                    and self.controller.last_run_folder is not None
                    and run_ok):
                
                s = load_app_settings()
                standalone = s.get("standalone_mode",True)
                retrain = s.get("retrain_model", False)

                

                done_folder = self.controller.last_run_folder
                dest = build_training_destination(done_folder, self.training_folder)
                ok = move_run_to_training(
                    done_folder,
                    training_folder=self.training_folder,
                    current_folder=self.current_folder
                )
                self.controller.last_run_folder = None
                if ok and dest and str(dest) != self.last_summary_dest:
                    self.last_summary_dest = str(dest)
                    self._append_log(
                        f"Run complete. Moved to {dest.name}.", "green")
                    self._show_run_summary(run_folder, captures, elapsed)
                    
                self._active_log_path = None
                wipe_folder_contents(self.current_folder)

                self._csv_uploaded = False  
                self._csv_uploaded_prompted = False  



            self.update_control_states()
            self.update_recovery_panel()

            # Progress
            rem = max(0.0, duration - elapsed) if duration > 0 else 0.0
            time_pct = max(0.0, min(100.0, elapsed / duration * 100)) if duration > 0 else 0.0

            # Update live status panel if live time changes
            if self.controller.is_running and duration > 0:
                try:
                    interval = self.get_interval_seconds_from_inputs()
                    self.estimated_capture_count = int(duration // interval) + 1
                    finish_ts = time.time() + rem
                    finish = time.strftime("%a %H:%M", time.localtime(finish_ts))
                    self.estimated_finish_text.set(f"Est. finish: {finish}")

                except ValueError:
                    pass
            else:
                # Update using values from timing input panel, not live updates
                self.update_timing_estimates()

            capture_pct = max(0.0, min(100.0, captures / self.estimated_capture_count * 100)) if self.estimated_capture_count > 0 else 0.0

            self.progress_pct.set(capture_pct)
            self._draw_donut(time_pct)
            self.elapsed.set(format_elapsed(elapsed))
            self.remaining.set(format_elapsed(rem))

                
            self.capture_ratio.set(f"{captures} / {self.estimated_capture_count}")

            self.run_folder_var.set(str(run_folder) if run_folder else "-")
            self.last_img_var.set(str(last_img) if last_img else "-")

            if last_msg and last_msg != self.last_msg_var.get() : # Only update if changed
                 self.last_msg_var.set(last_msg)
                 if self.controller.is_running:
                    self._append_log(last_msg, last_msg_category)


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
                    if isinstance(w, FilledSliderInput) : 
                        w.set_enabled(not running)

                    else : 
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

            # End-after-next button (managed separately since it self-disables after click)
            try:
                if not running:
                    self._end_after_next_requested = False
                    self._end_after_next_btn.configure(
                        text="End After Next",
                        fg=WARNING,
                        state="disabled"
                    )
                elif running and not stopping and not self._end_after_next_requested:
                    self._end_after_next_btn.configure(state="normal")
                else:
                    self._end_after_next_btn.configure(state="disabled")
            except Exception:
                pass

            self.update_recovery_button_state()

    def _prompt_csv_upload(self, run_folder)  :
        from tkinter import filedialog
        import shutil

        if run_folder is None : 
            self._csv_uploaded_prompted = False
            return 

        csv_path = filedialog.askopenfilename(
            title="Select Sensor Data CSV",
            filetypes=[("CSV files", "*.csv")]
        )

        if not csv_path : 
            self._csv_uploaded_prompted = False
            return
        
        dest = Path(run_folder) / "sensor_data.csv"
        try : 
            shutil.copy2(csv_path, dest)
            self._csv_uploaded = True
            self.controller.csv_ready_event.set()
            self._append_log("Sensor CSV uploaded. Waiting for model retraining...", "blue")
        except Exception as e:
            self._csv_uploaded_prompted = False # Allow retry
            messagebox.showerror("CSV Upload Error", str(e))

