import cv2 as cv
import time
from pathlib import Path


from measurement_capture import capture_measurement
from image_processing import make_filename
from run_metadata import write_run_metadata, write_done_file, write_comms_file, read_comms_file


def run_experiment(
        cap,
        laser,
        microorganism_type,
        media_type,
        run_id,
        duration_seconds,
        interval_seconds,
        output_root="current",
        stop_event=None,
        status_callback=None,
        duration_callback=None,
        continue_with_prev_roi=True,
        max_consecutive_failures=3,
        end_after_next_capture_event=None,
        hardware_error_event=None,
        hardware_error_message_getter=None,
        standalone_mode=True,
        retrain_model=False,
        handshake_timeout_hours = 1.0,
        csv_ready_event=None,
        csv_skipped_getter=None,
        camera_index=0,
        camera_reopen=None,
        max_reconnect_attempts=3,
        reconnect_backoff_seconds=2.0,
        heartbeat_interval_seconds=120,
        max_first_capture_roi_attempts=3,
        first_roi_retry_delay_seconds=5.0,
):
    """
    Run repeated measurements for specified amount of time
    Parameters: 
        cap: OpenCV VideoCapture object
        microorganism_type:
            Name of the microorganism being measured.

        media_type:
            Name of the growth media used for this run. Written to run.json
            for the partner ML machine, which reads it as a categorical
            feature (falling back to 'unknown' if absent).

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
    first_capture_roi_attempts = 0     # How many times the very first capture's ROI search has been tried

    def send_status(**kwargs) :
        """
        Send live status updates. Never lets a problem in the status
        callback itself (e.g. a bug in the GUI's update handler) become a
        way to abort an otherwise-healthy run.
        """

        if status_callback is not None :
            try :
                status_callback(**kwargs)
            except Exception as callback_error :
                print(f"send_status callback failed: {callback_error}")

    def attempt_camera_reopen(current_cap) :
        """
        Try to recover a dead camera (e.g. Windows MSMF closing the device on a
        long run) by releasing and reopening it. Returns a working capture object
        on success, or None if every attempt failed.
        """
        if camera_reopen is None :
            return None

        for attempt in range(1, max_reconnect_attempts + 1) :
            send_status(
                state="warning",
                last_message=f"Camera lost — reopening (attempt {attempt}/{max_reconnect_attempts})...",
                last_message_category="yellow",
            )
            try :
                new_cap = camera_reopen(current_cap)
                current_cap = new_cap
                if new_cap is not None and new_cap.isOpened() :
                    send_status(last_message="Camera reopened.", last_message_category="green")
                    return new_cap
            except Exception as cam_error :
                print(f"Camera reopen attempt {attempt} failed: {cam_error}")
            time.sleep(reconnect_backoff_seconds * attempt)

        return None

    def attempt_laser_reconnect() :
        """
        Try to recover a transient laser relay serial fault by reconnecting.
        Returns True on success, False if every attempt failed.
        """
        if laser is None :
            return False

        for attempt in range(1, max_reconnect_attempts + 1) :
            send_status(
                state="warning",
                last_message=f"Laser relay error — reconnecting (attempt {attempt}/{max_reconnect_attempts})...",
                last_message_category="yellow",
            )
            try :
                laser.reconnect()
                send_status(last_message="Laser relay reconnected.", last_message_category="green")
                return True
            except Exception as relay_error :
                print(f"Laser reconnect attempt {attempt} failed: {relay_error}")
            time.sleep(reconnect_backoff_seconds * attempt)

        return False

    # Tracks faults that occur after at least one image has already been
    # captured. Once capture_number >= 1, a run is never aborted by a
    # hardware/capture fault — instead it logs clearly and keeps retrying
    # every scheduled interval until the requested duration elapses, so an
    # unattended run always completes and saves whatever it managed to
    # capture. Before the first successful capture, existing fail-fast
    # behavior is unchanged (see each raise site below).
    active_problems = {}        # "hardware"/"capture" -> current problem message
    failure_reasons_seen = []   # distinct messages seen this run, first-seen order
    total_capture_failures = 0  # lifetime count, unlike consecutive_capture_failures

    def _sync_degraded_status() :
        send_status(
            degraded=bool(active_problems),
            degraded_message=" | ".join(active_problems.values()) or None,
        )

    def _record_failure_reason(msg) :
        if msg not in failure_reasons_seen :
            failure_reasons_seen.append(msg)

    def _enter_hardware_degraded(msg) :
        if active_problems.get("hardware") != msg :
            active_problems["hardware"] = msg
            _record_failure_reason(msg)
            print(f"DEGRADED (hardware): {msg}")
            send_status(
                state="warning",
                last_message=f"DEGRADED: {msg} — run will continue to duration_reached.",
                last_message_category="red",
            )
        _sync_degraded_status()

    def _clear_hardware_degraded() :
        if "hardware" in active_problems :
            del active_problems["hardware"]
            print("Hardware fault cleared.")
            send_status(last_message="Hardware recovered.", last_message_category="green")
        _sync_degraded_status()

    def _enter_capture_degraded(msg) :
        if active_problems.get("capture") != msg :
            active_problems["capture"] = msg
            _record_failure_reason(msg)
            print(f"DEGRADED (capture): {msg}")
        _sync_degraded_status()

    def _clear_capture_degraded() :
        if "capture" in active_problems :
            del active_problems["capture"]
            print("Capture failures recovered.")
            send_status(last_message="Capture recovered — resuming normal captures.", last_message_category="green")
        _sync_degraded_status()


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

    capture_number = 0

    write_run_metadata(
        run_folder=run_folder,
        microorganism_type=microorganism_type,
        media_type=media_type,
        run_id=run_id,
        duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        camera_index=camera_index,
    )



    # Write comms file
    if not standalone_mode :
        write_comms_file(run_folder, retrain_model=retrain_model)
        send_status(last_message="Waiting for partner handshake...")
        ack_deadline = time.monotonic() + handshake_timeout_hours * 3600
        wait_start = time.monotonic()

        while True : 
            comms = read_comms_file(run_folder)
            if comms and comms.get("start_handshake") == "ack": 
                send_status(last_message="Handshake acknowledged. Starting run")
                break
            if time.monotonic() > ack_deadline :
                raise RuntimeError("Handshake timeout: partner machine did not respond")
            if stop_event is not None and stop_event.is_set() : 
                raise RuntimeError("Stopped during handshake wait")
            time.sleep(5)

    start_time = time.monotonic()
    next_capture_time = start_time
    experiment_end_time = start_time + duration_seconds
    last_heartbeat_time = start_time


    finish_reason = "unknown"
    fatal_error_text = None

    clean_finish_reasons = ["duration_reached", "user_stopped", "end_after_capture"]

    try:
        while True:

            if stop_event is not None and stop_event.is_set() : # User pressed stop button
                finish_reason = "user_stopped"
                send_status(state="stopping", last_message="Stop requested.")
                break

            if hardware_error_event is not None and hardware_error_event.is_set() :
                msg = hardware_error_message_getter() if hardware_error_message_getter else "Hardware disconnected"
                if capture_number == 0 :
                    raise RuntimeError(f"HARDWARE_FAULT: {msg}")
                _enter_hardware_degraded(msg)
            elif "hardware" in active_problems :
                # The event was cleared (health check saw the item recover) —
                # let the banner and log reflect that.
                _clear_hardware_degraded()

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
                    if "capture" in active_problems :
                        _clear_capture_degraded()

                    filename = make_filename(
                        microorganism_type,
                        run_id,
                        capture_index=capture_number,
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

                except Exception as error:
                    # Catches RuntimeError from capture_measurement's known
                    # failure modes, but also anything unexpected (e.g. a
                    # raw cv2/OpenCV error) — a single bad capture should
                    # never be able to silently kill an otherwise-healthy
                    # multi-hour run.
                    error_text = str(error)
                    print(f"Capture failed: {error}")

                    # ArUco not found on the very first capture — no fallback
                    # is available yet. Retry a few times with a real delay
                    # between attempts before giving up — a run that hasn't
                    # captured anything yet is worth a bit of patience for
                    # something transient (camera still settling, brief
                    # vibration, condensation) to clear up, rather than
                    # failing on the very first try.
                    if "ARUCO_NOT_FOUND" in error_text and last_known_roi is None:
                        first_capture_roi_attempts += 1

                        if first_capture_roi_attempts < max_first_capture_roi_attempts :
                            send_status(
                                last_message=(
                                    f"ArUco markers not found on first capture — retrying in "
                                    f"{first_roi_retry_delay_seconds:.0f}s "
                                    f"({first_capture_roi_attempts}/{max_first_capture_roi_attempts})..."
                                ),
                                last_message_category="yellow",
                            )
                            time.sleep(first_roi_retry_delay_seconds)
                            continue

                        raise RuntimeError(
                            "ARUCO_NOT_FOUND: Could not detect ArUco markers on the "
                            f"first capture after {max_first_capture_roi_attempts} attempts. "
                            "Please use the Camera Setup widget in the main window to "
                            "verify your camera and marker placement before starting "
                            "the experiment."
                        )

                    consecutive_capture_failures += 1
                    total_capture_failures += 1

                    # Markers disappeared mid-run and continue_with_prev_roi is
                    # off. This is a normal missed-image case (bad lighting,
                    # vibration, momentary obstruction) — log it and count it
                    # toward max_consecutive_failures like any other capture
                    # failure, rather than aborting the whole run on one miss.
                    if "ARUCO_NOT_FOUND" in error_text:
                        send_status(
                            state="warning",
                            last_capture_result="ArUco markers missing",
                            last_error=error_text,
                            last_message=f"Capture failed {consecutive_capture_failures}/{max_consecutive_failures}: markers not found",
                            last_message_category="yellow",
                        )
                        if capture_number >= 1 :
                            _enter_capture_degraded(f"ArUco markers not found: {error_text}")

                    # Transient laser relay serial fault — try a bounded reconnect
                    # before treating it as fatal so one USB/serial glitch on a
                    # multi-day run doesn't abort the whole experiment.
                    elif "RELAY_FAILURE" in error_text:
                        if not attempt_laser_reconnect():
                            if capture_number == 0 :
                                send_status(state="error", last_error=error_text, last_message=f"Fatal relay failure: {error_text}")
                                raise RuntimeError(error_text)
                            _enter_capture_degraded(f"Relay failure (reconnect exhausted): {error_text}")
                            send_status(
                                state="warning",
                                last_capture_result="Relay failure — degraded",
                                last_error=error_text,
                                last_message=f"Capture failed {consecutive_capture_failures}/{max_consecutive_failures}: relay failure persists, will keep retrying",
                                last_message_category="red",
                            )
                        else :
                            send_status(
                                state="warning",
                                last_capture_result="Relay recovered",
                                last_error=error_text,
                                last_message=f"Capture failed {consecutive_capture_failures}/{max_consecutive_failures}: relay reconnected",
                            )

                    # Camera failure (e.g. Windows MSMF closing the device on a
                    # long run) — try a bounded reopen before counting it fatal.
                    else:
                        if "Camera failed to capture" in error_text:
                            recovered_cap = attempt_camera_reopen(cap)
                            if recovered_cap is not None:
                                cap = recovered_cap
                        send_status(
                            state="warning",
                            last_capture_result="Failed",
                            last_error=error_text,
                            last_message=f"Capture failed {consecutive_capture_failures}/{max_consecutive_failures}: {error_text}",
                            last_message_category="yellow",
                        )
                        if capture_number >= 1 :
                            _enter_capture_degraded(f"Capture failure: {error_text}")

                    # Before the first successful capture, a run that can't
                    # get going at all still fails fast (nothing worth
                    # waiting hours/days for). Once at least one image has
                    # been captured, every failure above has already been
                    # logged and marked degraded immediately (not gated on
                    # this threshold — a save-only failure can otherwise keep
                    # resetting consecutive_capture_failures to 0 every time
                    # capture_measurement itself still succeeds, so waiting
                    # for this count to reach the threshold isn't reliable).
                    if consecutive_capture_failures >= max_consecutive_failures and capture_number == 0 :
                        abort_msg = f"Capture failed for {consecutive_capture_failures} consecutive attempts.\nExperiment aborted."
                        print(abort_msg)
                        send_status(last_message=abort_msg, last_message_category="red")
                        raise RuntimeError(f"Fatal camera/capture failure: {error}")
                # Schedule next capture from original timeline. Clamp to "now" so a
                # slow capture (retries, reconnect) can't leave next_capture_time in
                # the past and fire a burst of back-to-back captures to catch up.
                next_capture_time += interval_seconds
                next_capture_time = max(next_capture_time, time.monotonic())
                last_heartbeat_time = time.monotonic()
                send_status(last_message="Waiting for next capture...")


            # Stop once duration reached
            if elapsed_time >= current_duration:
                print("Experiment duration reached.")
                finish_reason = "duration_reached"
                send_status(state="finished", last_message="Experiment duration reached")
                break

            # Periodic heartbeat so the log shows proof of life during long
            # waits between captures. Without this, a crash mid-wait leaves
            # no trace between one capture and the next scheduled one, which
            # can be a gap of many minutes.
            if current_time - last_heartbeat_time >= heartbeat_interval_seconds:
                remaining_wait = max(0, int(next_capture_time - current_time))
                send_status(
                    last_message=f"Still running — next capture in {remaining_wait}s...",
                    last_message_category="gray",
                )
                last_heartbeat_time = current_time

            time.sleep(0.1)

        # Only write DONE.json if experiment if experiment finished successfully
        if finish_reason in clean_finish_reasons :
            write_done_file(
                run_folder=run_folder,
                run_id=run_id,
                capture_count=capture_number,
                reason=finish_reason,
                had_errors=bool(failure_reasons_seen),
                failed_capture_count=total_capture_failures,
                failure_reasons=failure_reasons_seen,
                degraded_at_finish=bool(active_problems),
            )


        if not standalone_mode and retrain_model and finish_reason in clean_finish_reasons :
            # Not yet confirmed by the partner ML machine. The GUI uses this to
            # decide whether it is safe to move the run out of current/ — while
            # it is False the run folder (and its sensor_data.csv) must stay put
            # so the ML can still read it.
            send_status(partner_confirmed=False)
            send_status(last_message="Experiment complete. Waiting for sensor CSV", state="awaiting_csv")

            # Bounded wait for the user to upload/skip the CSV so the worker can't
            # block forever if nobody responds.
            csv_wait_seconds = handshake_timeout_hours * 3600
            csv_ready = True
            if csv_ready_event is not None :
                csv_ready = csv_ready_event.wait(timeout=csv_wait_seconds)

            if not csv_ready :
                # Nobody uploaded or skipped in time. Leave the run in current/
                # (partner_confirmed stays False) rather than moving it while the
                # ML might still act on it.
                send_status(
                    last_message="Timed out waiting for sensor CSV. Run left in current/ for the partner machine.",
                    last_message_category="yellow",
                )
            else :
                # Check if user skipped CSV upload
                if csv_skipped_getter is not None and csv_skipped_getter() :
                    send_status(last_message="CSV upload skipped. Notifying partner machine...")
                else :
                    send_status(last_message="Waiting for model retraining...", state="waiting_retrain")

                # Both outcomes wait for partner status
                ml_deadline = time.monotonic() + handshake_timeout_hours * 3600
                while True :
                    comms = read_comms_file(run_folder)
                    if comms and comms.get("ml_done") is True :
                        # Partner finished cleanly — safe for the GUI to move the run.
                        send_status(last_message="Retraining complete", partner_confirmed=True)
                        break
                    if time.monotonic() > ml_deadline :
                        # Partner never confirmed. Leave partner_confirmed False so the
                        # GUI does not move the folder out from under the ML mid-retrain.
                        send_status(
                            last_message="Retraining wait timed out. Run left in current/ for the partner machine.",
                            last_message_category="yellow",
                        )
                        break
                    if stop_event is not None and stop_event.is_set() :
                        break
                    time.sleep(10)

    # Fatal capture, saving, camera, relay failure, or anything unexpected
    # (e.g. an OSError writing DONE.json) — catches everything so the run
    # always reports a clear reason instead of the thread dying silently.
    except Exception as error:
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
        # Always clear the live banner on any exit path (clean finish,
        # pre-capture fatal error, user stop) — this only affects the live
        # GUI state, not the permanent DONE.json degradation record below.
        send_status(degraded=False, degraded_message=None)

        if laser is not None :  # Just in case failure occurs
            try :
                laser.off()

            except Exception :
                pass # Continue if laser cleanup fails — never let cleanup itself crash

        
    print(f"Experiment finished with {capture_number} saved images.")
    return run_folder

