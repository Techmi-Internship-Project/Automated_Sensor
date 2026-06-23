import cv2 as cv
import time
from pathlib import Path


from measurement_capture import capture_measurement
from image_processing import make_filename
from run_metadata import atomic_write_json, write_run_metadata, write_done_file


def run_experiment(
        cap,
        laser,
        microorganism_type,
        run_id,
        duration_seconds,
        interval_seconds,
        output_root="current",
        stop_event=None,
        status_callback=None
):
    """
    Run repeated measurements for specified amount of time
    Parameters: 
        cap: OpenCV VideoCapture object
        microorganism_type:
            Name of the microorganism being measured.

        run_id:
            Unique identifier for this experiment.

        duration_seconds:
            Total amount of time the experiment should run.

        interval_seconds:
            Time between measurements.

        output_root:
            Main folder where active experiment data is stored
    """
    consecutive_capture_failures = 0
    max_consecutive_capture_failures = 3

    def send_status(**kwargs) : 
        """
        Send live status updates
        """

        if status_callback is not None : 
            status_callback(**kwargs)


    # Create new folder for this experiment
    run_folder = Path(output_root) / microorganism_type / f"run_{run_id}"
    run_folder.mkdir(parents=True, exist_ok=True)

    print(f"Experiment data will be saved in: {run_folder}")

    send_status(
        state="running",
        run_folder=str(run_folder),
        last_message=f"Saving data in {run_folder}"
    )

    # Use monotonic time to see time elapsed
    start_time = time.monotonic()
    next_capture_time = start_time
    experiment_end_time = start_time + duration_seconds

    capture_number = 0

    write_run_metadata(
        run_folder=run_folder,
        microorganism_type=microorganism_type,
        run_id=run_id,
        duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        camera_index=0 # CHANGE LATER
    )

    finish_reason = "unknown"
    fatal_error_text = None

    clean_finish_reasons = ["duration_reached", "user_stopped"]

    try:
        while True:

            if stop_event is not None and stop_event.is_set() : # User pressed stop button
                finish_reason = "user_stopped"
                send_status(state="stopping", last_message="Stop requested.")
                break

            current_time = time.monotonic()
            elapsed_time = current_time - start_time

            send_status(elapsed_seconds=elapsed_time, duration_seconds=duration_seconds)

            # Stop once duration reached
            if elapsed_time >= duration_seconds:
                print("Experiment duration reached.")
                finish_reason = "duration_reached"
                send_status(state="finished", last_message="Experiment duration reached")
                break

            # Capture when next scheduled time has arrived
            if current_time >= next_capture_time:
                print(f"Taking measurement {capture_number}"
                      f" at {elapsed_time:.1f} seconds"
                    )
                
                try:
                    # Run complete measurement sequence
                    laser_only = capture_measurement(cap, laser)

                    consecutive_capture_failures = 0 # Successful capture

                    is_final_capture = (next_capture_time + interval_seconds >= experiment_end_time)


                    filename = make_filename(
                        microorganism_type,
                        run_id,
                    )

                    # Put generated filename inside this run's folder
                    filepath = run_folder / filename

                    save_successful = cv.imwrite(str(filepath), laser_only)

                    if not save_successful:
                        raise RuntimeError(f"Could not save image: {filepath}")
                    
                    print(f"Saved: {filepath}")

                    send_status(
                        capture_count=capture_number + 1,
                        last_saved_image=str(filepath),
                        last_message=f"Saved {filepath.name}",
                        last_error=None,
                        last_capture_result="Success"
                    )

                    capture_number += 1

                except RuntimeError as error:
                    error_text = str(error)
                    print(f"Capture failed: {error}")

                    consecutive_capture_failures += 1

                    if "ARUCO_NOT_FOUND" in error_text : 
                        send_status(
                            last_capture_result="ArUco markers missing",
                            last_error=error_text,
                            alert_message="Could not detect all four ArUco markers.\n\n"
                        )      
                    else : 
                        send_status(
                            state="warning", 
                            last_capture_result="Failed", 
                            last_error=error_text,
                            last_message=f"Capture failed {consecutive_capture_failures}/{max_consecutive_capture_failures} : {error_text} "
                            )


                    if consecutive_capture_failures >= max_consecutive_capture_failures : 
                        raise RuntimeError(f"Fatal camera/capture failure: {error}")
                # Schedule next capture from original timeline
                next_capture_time += interval_seconds
            
            #time.sleep(0.1)

    # Fatal capture, saving, camera, or relay failure
    except RuntimeError as error:
        fatal_error_text = str(error)
        finish_reason = "fatal_error"

        send_status(
            state="error",
            last_error=fatal_error_text,
            last_message=f"Fatal experiment error: {fatal_error_text}"
        )
        # Re-raise error so ExperimentController knows run failed
        raise
    except KeyboardInterrupt:
        print("\nExperiment manually stopped.")
        finish_reason = "user_stopped"

        send_status(
            state="stopped",
            last_message="Experiment manually stopped"
        )

    finally :
        # Only write DONE.json if experiment if experiment finished successfully
        if finish_reason in clean_finish_reasons : 
            write_done_file(
                run_folder=run_folder,
                run_id=run_id,
                capture_count=capture_number,
                reason=finish_reason
            )

        

        if laser is not None :  # Just in case failure occurs
            try :
                laser.off()

            except RuntimeError : 
                pass # Continue if laser cleanup fails

        
    print(f"Experiment finished with {capture_number} saved images.")
    return run_folder

