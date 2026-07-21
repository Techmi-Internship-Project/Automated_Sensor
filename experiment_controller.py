import ctypes
import threading
import time

from camera import open_camera, reopen_camera
from experiment import run_experiment
from laser_control import LaserRelay

# Flags for ctypes.windll.kernel32.SetThreadExecutionState, used to stop
# Windows from sleeping partway through an unattended multi-hour run.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _prevent_system_sleep() :
    """
    Tell Windows not to sleep until told otherwise. No-op (with a printed
    warning) on non-Windows platforms, since ctypes.windll only exists there.
    """
    try :
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except AttributeError :
        print("SetThreadExecutionState unavailable (not running on Windows) — sleep prevention skipped.")


def _allow_system_sleep() :
    """
    Release the sleep-prevention request made in _prevent_system_sleep so
    normal power management resumes once the run ends.
    """
    try :
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except AttributeError :
        pass


class ExperimentController :
    """
    Class that controls starting and stopping experiments
    """

    def __init__(self):
        self.thread = None # Background experiment thread
        self.stop_event = threading.Event() # Event used to stop experiment
        self.hardware_error_event = threading.Event() # Event used to signal a hardware fault
        self.csv_ready_event = threading.Event()
        self.csv_skipped = False
        # Per-item hardware fault tracking (item name -> message). A dict
        # rather than one shared string so independent faults (e.g. Camera
        # AND Storage both down) don't clobber each other, and so a single
        # item recovering can clear just its own entry instead of wiping out
        # a still-active fault on a different item.
        self.hardware_faults = {}
        self._hardware_fault_lock = threading.Lock()
        self.is_running = False
        self.last_error = None # Most recent error message
        self.last_run_folder = None # Folder where most recent run was saved
        self.camera_index = None
        self.cap = None # Camera object
        self.laser = None # Laser relay object

        # Lock for safely changing run duration while experiment is running
        self.duration_lock = threading.Lock()
        # Currently requested experiment duration in seconds
        self.requested_duration_seconds = 0
        # Ending cleanly after event capture
        self.end_after_current_capture_event = threading.Event()


        # Lock so experiment thread and GUI thread do not edit status at same time
        self.status_lock = threading.Lock()
        # Queue of every (message, category) sent via update_status, so the
        # GUI can log all of them in order rather than polling a single
        # overwritable field every 200ms — a fast burst of status changes
        # (e.g. a capture failing, the camera reconnecting, and the next
        # capture starting, all within one poll window) could otherwise
        # silently vanish, since only whichever value happened to be
        # current at the exact moment of a poll tick would ever get logged.
        self._log_queue = []
        self.status = { # Dictionary for live status updates
            "state": "idle",
            "elapsed_seconds": 0,
            "duration_seconds" : 0, # For progress bar
            "capture_count": 0,
            "last_saved_image": None, # Most recently saved image path
            "run_folder": None, # Store current run folder path
            "last_message": "Idle", # Most recent status message
            "last_message_category": "green", # Log color for last_message
            "alert_message": None, # For specific error handling
            "alert_id" : 0, # For popup handling
            "run_completed_successfully": False, # False by default until actually completes correctly
            "partner_confirmed": True, # In collaborative retrain mode, set False until the ML machine confirms ml_done
            "degraded": False, # True while a post-first-capture fault is currently active
            "degraded_message": None, # Human-readable current problem description for the GUI banner
        }
        

    def begin_run(
            self,
            microorganism_type,
            media_type,
            camera_index,
            duration_seconds,
            interval_seconds,
            camera_name=None,
            output_root="current",
            continue_with_prev_roi=True,
            max_consecutive_failures=3,
            laser_port=None,
            standalone_mode=True,
            retrain_model=False,
            handshake_timeout_hours=1.0,
            
    ):
        # Is experiment already running?
        if self.is_running : 
            raise RuntimeError("Experiment is already running")
        
        self.stop_event.clear() # Clear any previous stop request
        self.hardware_error_event.clear() # Clear any previous hardware error events
        self.csv_ready_event.clear()
        with self._hardware_fault_lock :
            self.hardware_faults = {}
        with self.status_lock :
            self._log_queue = []
        self.last_error = None
        self.last_run_folder = None
        self.csv_skipped = False
        self.camera_index = camera_index

        # Lock duration state before setting start duration 
        with self.duration_lock : 
            self.requested_duration_seconds = duration_seconds
        self.end_after_current_capture_event.clear()

        run_id = int(time.time())

        self.update_status(
            state="starting",
            elapsed_seconds=0.0,
            duration_seconds=duration_seconds,
            capture_count=0,
            last_saved_image=None,
            run_folder=None,
            last_message="Starting experiment...",
            alert_message=None,
            alert_id=0,
            run_completed_successfully = False,
            partner_confirmed = True,
            degraded = False,
            degraded_message = None,
        )

        self.thread = threading.Thread(
            target=self._experiment_worker,
            args=(
            microorganism_type,
            media_type,
            camera_index,
            camera_name,
            run_id,
            duration_seconds,
            interval_seconds,
            output_root,
            continue_with_prev_roi,
            max_consecutive_failures,
            laser_port,
            standalone_mode,
            retrain_model,
            handshake_timeout_hours,
            self.csv_ready_event),
            daemon=True  # Thread closes automatically when main program exits
        )

        # Mark experiment as running
        self.is_running = True
        self.thread.start()
        
        return run_id
    

    def _experiment_worker(
        self,
        microorganism_type,
        media_type,
        camera_index,
        camera_name,
        run_id,
        duration_seconds,
        interval_seconds,
        output_root,
        continue_with_prev_roi,
        max_consecutive_failures,
        laser_port=None,
        standalone_mode=True,
        retrain_model=False,
        handshake_timeout_hours=1.0,
        csv_ready_event=None
):
        """
        Runs the experiment in a background thread.
        """

        # Track whether the run finished normally.
        run_completed_successfully = False

        # Stop Windows from sleeping for the duration of the run — an
        # unattended run left overnight has no one there to wake the
        # machine back up if it suspends partway through.
        _prevent_system_sleep()

        # Try to run the full experiment.
        try:

            # Open the selected camera.
            self.cap = open_camera(camera_index)

            # Check if the camera failed to open.
            if self.cap is None or not self.cap.isOpened():

                # Stop the run because the camera is required.
                raise RuntimeError("Could not open camera")

            # Create the laser relay object.
            self.laser = LaserRelay(port=laser_port)

            # Open the laser relay connection.
            self.laser.open()

            # Run the actual experiment and store the completed run folder.
            self.last_run_folder = run_experiment(
                cap=self.cap,
                laser=self.laser,
                microorganism_type=microorganism_type,
                media_type=media_type,
                run_id=run_id,
                duration_seconds=duration_seconds,
                interval_seconds=interval_seconds,
                output_root=output_root,
                stop_event=self.stop_event,
                status_callback=self.update_status,
                duration_callback=self.get_requested_duration_seconds,
                continue_with_prev_roi=continue_with_prev_roi,
                max_consecutive_failures=max_consecutive_failures,
                end_after_next_capture_event=self.end_after_current_capture_event,
                hardware_error_event=self.hardware_error_event,
                hardware_error_message_getter=self.get_hardware_fault_message,
                standalone_mode=standalone_mode,
                retrain_model=retrain_model,
                handshake_timeout_hours=handshake_timeout_hours,
                csv_ready_event=csv_ready_event,
                csv_skipped_getter=lambda: self.csv_skipped,
                camera_index=camera_index,
                camera_reopen=self._reopen_camera,
            )

            # Check if the stop button was not requested.
            if not self.stop_event.is_set():
                # Update the GUI status as finished.
                self.update_status(
                    state="finished",
                    last_message="Experiment finished.",
                    last_error=None,
                    run_completed_successfully=True
                )

            # Handle the case where the user stopped the run.
            else:

                # Mark the run as stopped rather than completed.
                self.update_status(
                    state="stopped",
                    last_message="Experiment stopped by user.",
                    last_error=None,
                    run_completed_successfully=False
                )

        # Handle fatal experiment errors. Catches Exception broadly, not just
        # RuntimeError — anything unexpected escaping run_experiment (e.g. a
        # raw OSError from a metadata write on a dropped drive) must still
        # surface here instead of silently killing this daemon thread with
        # no GUI error and is_running stuck True.
        except Exception as error:

            # Store the error text.
            self.last_error = str(error)

            # Print the error in the terminal for debugging.
            print(f"Experiment failed: {error}")

            # Update the GUI status and trigger one alert popup.
            self.update_status(
                state="error",
                last_error=str(error),
                last_message=f"Experiment stopped because of an error: {error}",
                run_completed_successfully=False,
                alert_message=f"Experiment stopped because of an error:\n\n{error}"
            )

        # Always clean up hardware resources.
        finally:

            # Let Windows sleep normally again now that the run is over.
            _allow_system_sleep()

            # Check if the laser relay exists.
            if self.laser is not None:

                # Try to turn the laser off before closing the relay.
                try:

                    # Turn the laser off for safety.
                    self.laser.off()
                    time.sleep(0.2)


                # Ignore laser-off errors during cleanup.
                except RuntimeError:

                    # Continue cleanup even if laser off failed.
                    pass

                # Try to close the laser relay connection.
                try:

                    # Close the laser relay.
                    self.laser.close()

                # Ignore laser-close errors during cleanup.
                except RuntimeError:

                    # Continue cleanup even if laser close failed.
                    pass

                # Clear the laser object.
                self.laser = None

            # Check if the camera exists.
            if self.cap is not None:

                # Release the camera.
                self.cap.release()

                # Clear the camera object.
                self.cap = None

            # Mark the controller as not running.
            self.is_running = False

    def _reopen_camera(self, current_cap) :
        """
        Release the current camera handle and open a fresh one on the same
        selected index. Keeps self.cap pointed at the live handle so the finally
        cleanup releases the current object rather than a stale one. Returns the
        new capture object.
        """
        self.cap = reopen_camera(current_cap, self.camera_index)
        return self.cap

    def set_hardware_fault(self, item, message) :
        """
        Records that a given health item (Camera / Laser Module / Storage)
        is currently faulted. Safe to call for multiple independent items at
        once — each gets its own entry so one item's fault doesn't clobber
        another's.
        """
        with self._hardware_fault_lock :
            self.hardware_faults[item] = message
            self.hardware_error_event.set()

    def clear_hardware_fault(self, item) :
        """
        Records that a given health item has recovered. Only clears the
        shared hardware_error_event once every faulted item has recovered.
        """
        with self._hardware_fault_lock :
            self.hardware_faults.pop(item, None)
            if not self.hardware_faults :
                self.hardware_error_event.clear()

    def get_hardware_fault_message(self) :
        """
        Returns a combined human-readable message for every currently
        faulted item, or None if nothing is faulted.
        """
        with self._hardware_fault_lock :
            if not self.hardware_faults :
                return None
            return " | ".join(f"{item}: {msg}" for item, msg in self.hardware_faults.items())

    def get_requested_duration_seconds(self) :
        """
        Safely returns experiment duration
        """

        # Lock duration while reading
        with self.duration_lock : 
            return self.requested_duration_seconds
        
    def end_after_next_capture(self):
        """
        Signals the experiment to finish cleanly after the next successful capture.
        """
        if not self.is_running:
            return
        self.end_after_current_capture_event.set()

    def adjust_time(self, seconds_delta, minimum_extra_seconds=600) :
        """
        Changes time to the active experiment duration, and does not let time go below 10 minutes
        """

        if not self.is_running : 
            return # Do nothing
        
        status = self.get_status()
        elapsed_seconds = status.get("elapsed_seconds", 0)

        # Calculate minimum allowed duration so subtracting time doesn't just automatically end run
        minimum_duration = elapsed_seconds + minimum_extra_seconds

        # Lock state while changing
        with self.duration_lock : 
            requested_new_duration = self.requested_duration_seconds + seconds_delta
            self.requested_duration_seconds = max(minimum_duration, requested_new_duration)
            updated_duration = self.requested_duration_seconds

        # Time added
        if seconds_delta > 0 :
            message = f"Added {seconds_delta // 3600}h to experiment"
        
        # Time subtracted
        elif seconds_delta < 0 : 
            message = f"Subtracted {abs(seconds_delta) // 3600}h from experiment"
        
        # Zero adjustment
        else : 
            message = "Experiment duration unchanged"

        # Update GUI
        self.update_status(
            duration_seconds=updated_duration,
            last_message=message
        )




    def stop_experiment(self) : 
        """
        Requests experiment thread to stop"""
        if not self.is_running : 
            return
        
        self.stop_event.set()

        # Only update state/messaging here — do not zero out
        # duration/capture_count/elapsed_seconds. Those drive the GUI's
        # progress donut, progress bar, elapsed/remaining time, and capture
        # ratio (see gui_backend_actions._update_status_loop_body), so
        # zeroing them made every progress indicator snap to 0 the instant
        # Stop was clicked instead of freezing at the run's true final state.
        self.update_status(
            state="stopping",
            last_message="Stop requested...",
            run_completed_successfully = False,
            alert_id=0, # For popup handling
        )

    def update_status(self, **kwargs) :
        """
        Update the shared dictionary
        """

        # Lock status dictionary so only one thread edits
        with self.status_lock :
            if "alert_message" in kwargs and kwargs["alert_message"] is not None :
                kwargs["alert_id"] = self.status.get("alert_id", 0) + 1

            # Queue every distinct log-worthy message (see _log_queue above).
            # Default an unset category to "gray" (neutral) rather than
            # leaving it to inherit whatever category the previous message
            # happened to have — silently inheriting a stale color is what
            # made a real capture failure show up as an innocuous green line.
            if kwargs.get("last_message") :
                category = kwargs.get("last_message_category", "gray")
                self._log_queue.append((kwargs["last_message"], category))

            self.status.update(kwargs)

    def drain_log_queue(self) :
        """
        Returns and clears every (message, category) queued since the last
        drain, in the order they were sent. Used by the GUI's status poll
        to log every distinct message instead of only whichever one happens
        to be current at each 200ms poll tick.
        """
        with self.status_lock :
            messages = self._log_queue
            self._log_queue = []
        return messages

    def get_status(self) :
        """
        Read current status safely
        """
        with self.status_lock :
            return dict(self.status)
        

