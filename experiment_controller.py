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
        try : 
            self.cap = open_camera(camera_index)

            if self.cap is None or not self.cap.isOpened() :
                raise RuntimeError("Could not open camera")
            
            self.laser = LaserRelay()
            self.laser.open()

            self.last_run_folder = run_experiment(
                cap=self.cap,
                laser=self.laser,
                microorganism_type=microorganism_type,
                run_id=run_id,
                duration_seconds=duration_seconds,
                interval_seconds=interval_seconds,
                output_root=output_root,
                stop_event=self.stop_event
            )

        except RuntimeError as error : 
            self.last_error = str(error)
            print(f"Experiment failed: {error}")

        finally : 
            if self.laser is not None : 
                self.laser.close()
                self.laser = None

            if self.cap is not None : 
                self.cap.release()
                self.cap = None

            self.is_running = False


    def stop_experiment(self) : 
        if not self.is_running : 
            return
        
        self.stop_event.set()


    def thread_is_alive(self) : 
        """
        Function that checks if background thread is still alive
        """

        if self.thread is None : 
            return False # Because no active thread
        
        return self.thread.is_alive() 