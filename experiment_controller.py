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
        self.is_running = False
        self.last_error = None # Most recent error message
        self.last_run_folder = None # Folder where most recent run was saved
        self.camera_index = None
        self.cap = None # Camera object
        self.laser = None # Laser relay object

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
            output_root="current"
    ):
        # Is experiment already running?
        if self.is_running : 
            raise RuntimeError("Experiment is already running")
        
        self.stop_event.clear() # Clear any previous stop request
        self.last_error = None
        self.last_run_folder = None
        self.camera_index = camera_index
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
            run_id,
            duration_seconds,
            interval_seconds,
            output_root),
            daemon = True # Thread closes automatically when main program exits
        )

        # Mark experiment as running
        self.is_running = True
        self.thread.start()
        
        return run_id
    

    def _experiment_worker(
        self,
        microorganism_type,
        camera_index,
        run_id,
        duration_seconds,
        interval_seconds,
        output_root
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
            self.laser = LaserRelay()

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
                status_callback=self.update_status
            )

            # Check if the stop button was not requested.
            if not self.stop_event.is_set():

                # Mark the run as completed successfully.
                run_completed_successfully = True

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

    def stop_experiment(self) : 
        """
        Requests experiment thread to stop"""
        if not self.is_running : 
            return
        
        self.stop_event.set()

        self.update_status(
            state="stopping",
            last_message="Stop requested...",
            run_completed_successfully = False
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
        

