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
        status_callback=None,
        duration_callback=None,
        continue_with_prev_roi=True,
        max_consecutive_failures=3,
        end_after_next_capture_event=None
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
    consecutive_aruco_misses = 0       # How many captures in a row used the fallback ROI
    last_known_roi = None              # Stores ROI from the most recent successful detection

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

    clean_finish_reasons = ["duration_reached", "user_stopped", "end_after_capture"]

    try:
        while True:

            if stop_event is not None and stop_event.is_set() : # User pressed stop button
                finish_reason = "user_stopped"
                send_status(state="stopping", last_message="Stop requested.")
                break

            current_time = time.monotonic()
            elapsed_time = current_time - start_time

            current_duration = duration_callback()
            send_status(elapsed_seconds=elapsed_time, duration_seconds=current_duration)

            

            # Capture when next scheduled time has arrived
            if current_time >= next_capture_time:
                print(f"Taking measurement {capture_number}"
                      f" at {elapsed_time:.1f} seconds"
                    )
                
                try:
                    # Decide whether to pass a fallback ROI for this capture.
                    # On the very first capture, last_known_roi is None, so no
                    # fallback is provided regardless of the setting — missing
                    # markers on the first capture is always fatal.
                    fallback = last_known_roi if continue_with_prev_roi else None

                    # Run complete measurement sequence.
                    laser_only, roi_used = capture_measurement(
                        cap, laser,
                        status_callback=send_status,
                        fallback_roi=fallback
                    )

                    # Detect whether the fallback ROI was used (same object returned).
                    fallback_was_used = (fallback is not None and roi_used is fallback)

                    if fallback_was_used:
                        consecutive_aruco_misses += 1
                        miss_word = "miss" if consecutive_aruco_misses == 1 else "misses"
                        msg = f"Marker not detected. Using previous ROI ({consecutive_aruco_misses} consecutive {miss_word})"
                        print(msg)
                        send_status(last_message=msg, last_message_category="yellow")
                    else:
                        if consecutive_aruco_misses > 0:
                            # Markers were missing before but are detected again now.
                            miss_plural = "s" if consecutive_aruco_misses != 1 else ""
                            msg = f"Marker reacquired after {consecutive_aruco_misses} missed capture{miss_plural}."
                            print(msg)
                            send_status(last_message=msg, last_message_category="green")
                            consecutive_aruco_misses = 0

                    # Update the stored ROI so future captures have a fallback.
                    last_known_roi = roi_used

                    consecutive_capture_failures = 0  # Successful capture

                    filename = make_filename(
                        microorganism_type,
                        run_id,
                    )

                    # Put generated filename inside this run's folder.
                    filepath = run_folder / filename

                    save_successful = cv.imwrite(str(filepath), laser_only)

                    if not save_successful:
                        raise RuntimeError(f"Could not save image: {filepath}")

                    print(f"Saved: {filepath}")

                    send_status(
                        capture_count=capture_number + 1,
                        last_saved_image=str(filepath),
                        last_message="Saved image",
                        last_message_category="green",
                        last_error=None,
                        last_capture_result="Success"
                    )

                    capture_number += 1

                    if (end_after_next_capture_event is not None # TODO
                            and end_after_next_capture_event.is_set()):
                        finish_reason = "end_after_capture"
                        send_status(state="finished",
                                    last_message="Ending after capture as requested.")
                        break

                except RuntimeError as error:
                    error_text = str(error)
                    print(f"Capture failed: {error}")

                    if "RELAY_FAILURE" in error_text:
                        send_status(state="error", last_error=error_text, last_message=f"Fatal relay failure: {error_text}")
                        raise RuntimeError(error_text)

                    # ArUco not found on the very first capture — no fallback
                    # was available, so direct the user to the camera setup widget.
                    if "ARUCO_NOT_FOUND" in error_text and last_known_roi is None:
                        
                        raise RuntimeError(
                            "ARUCO_NOT_FOUND: Could not detect ArUco markers on the "
                            "first capture. Please use the Camera Setup widget in the "
                            "main window to verify your camera and marker placement "
                            "before starting the experiment."
                        )
                    
                        

                    consecutive_capture_failures += 1

                    if "ARUCO_NOT_FOUND" in error_text: # TODO
                        # Markers disappeared mid-run and continue_with_prev_roi
                        # is off, so this counts as a failure.
                        send_status(
                            last_capture_result="ArUco markers missing",
                            last_error=error_text,
                            last_message=f"Capture failed {consecutive_capture_failures}/{max_consecutive_failures}: markers not found",
                            
                        )
                        finish_reason = "fatal_error"
                        break

                    else:
                        send_status(
                            state="warning",
                            last_capture_result="Failed",
                            last_error=error_text,
                            last_message=f"Capture failed {consecutive_capture_failures}/{max_consecutive_failures}: {error_text}"
                        )

                    if consecutive_capture_failures >= max_consecutive_failures:
                        abort_msg = f"Marker not detected for {consecutive_capture_failures} consecutive captures.\nExperiment aborted."
                        print(abort_msg)
                        send_status(last_message=abort_msg, last_message_category="red")
                        raise RuntimeError(f"Fatal camera/capture failure: {error}")
                # Schedule next capture from original timeline
                next_capture_time += interval_seconds
            

            # Stop once duration reached
            if elapsed_time >= current_duration:
                print("Experiment duration reached.")
                finish_reason = "duration_reached"
                send_status(state="finished", last_message="Experiment duration reached")
                break

            send_status(last_message="Waiting for next capture...")
            time.sleep(0.1)

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

