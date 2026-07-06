import threading
import time

from camera import open_camera
from experiment import run_experiment
from laser_control import LaserRelay

class ExperimentController : 
    """
    Class that controls starting and stopping experiments
    """

    def __init__(self):
        self.thread = None # Background experiment thread
        self.stop_event = threading.Event() # Event used to stop experiment
        self.hardware_error_event = threading.Event() # Event used to stop experiment if hardware error
        self.csv_ready_event = threading.Event()
        self.hardware_error_message = None
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
            "run_completed_successfully": False # False by default until actually completes correctly
        }
        

    def start_experiment(
            self,
            microorganism_type,
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
            handshake_timeout_hours=1.0
    ):
        # Is experiment already running?
        if self.is_running : 
            raise RuntimeError("Experiment is already running")
        
        self.stop_event.clear() # Clear any previous stop request
        self.hardware_error_event.clear() # Clear any previous hardware error events
        self.csv_ready_event.clear()
        self.hardware_error_message = None
        self.last_error = None
        self.last_run_folder = None
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
            run_completed_successfully = False
        )

        self.thread = threading.Thread(
            target=self._experiment_worker,
            args=(
            microorganism_type,
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
                hardware_error_message_getter=lambda: self.hardware_error_message,
                standalone_mode=standalone_mode,
                retrain_model=retrain_model,
                handshake_timeout_hours=handshake_timeout_hours,
                csv_ready_event=csv_ready_event
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

        # Handle fatal experiment errors.
        except RuntimeError as error:

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

        self.update_status(
            state="stopping",
            last_message="Stop requested...",
            run_completed_successfully = False,
            duration_seconds=0, # For progress bar
            capture_count=0,
            alert_id=0, # For popup handling
            elapsed_seconds=0,
        )



    def thread_is_alive(self) : 
        """
        Function that checks if background thread is still alive
        """

        if self.thread is None : 
            return False # Because no active thread
        
        return self.thread.is_alive() 
    

    def update_status(self, **kwargs) : 
        """
        Update the shared dictionary
        """

        # Lock status dictionary so only one thread edits
        with self.status_lock : 
            if "alert_message" in kwargs and kwargs["alert_message"] is not None :
                kwargs["alert_id"] = self.status.get("alert_id", 0) + 1
            
            self.status.update(kwargs)



    def get_status(self) : 
        """
        Read current status safely
        """
        with self.status_lock : 
            return dict(self.status)
        

