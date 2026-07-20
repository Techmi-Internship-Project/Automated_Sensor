from camera import (set_normal_exposure, set_low_exposure, grab_frame)
from aruco import (detect_aruco_markers, get_roi_corners, align_roi)
from image_processing import subtract_background
import time

def find_roi(cap, max_attempts=5):
    """
    Try to detect all four ArUco markers and return the ROI corners.

    Parameters:
        cap:
            OpenCV VideoCapture object.

        max_attempts:
            Maximum number of times to capture a frame and search
            for the ArUco markers.

    Returns:
        (roi_corners, inferred_marker_id):
            roi_corners:
                The four detected/inferred ROI corner coordinates, or None
                if fewer than three required markers were ever detected.

            inferred_marker_id:
                The marker ID that was geometrically inferred from the
                other three (see aruco.get_roi_corners), or None if all
                four were detected directly, or if detection failed.
    """

    # Use normal exposure because the ArUco markers may be difficult
    # to detect at the low exposure used for the laser.
    set_normal_exposure(cap)

    # Try several times in case one frame is blurry or poorly exposed.
    for attempt in range(max_attempts):

        frame = grab_frame(cap)

        # If the camera failed to return a frame, try again.
        if frame is None:
            print(
                f"Camera capture failed, "
                f"attempt {attempt + 1}/{max_attempts}"
            )
            continue

        # Detect all visible ArUco markers in the captured frame.
        corners, ids = detect_aruco_markers(frame)

        # Use the detected markers to determine the four ROI corners.
        roi_corners, inferred_marker_id = get_roi_corners(corners, ids)

        # If enough markers were found, return the ROI corners.
        if roi_corners is not None:
            return roi_corners, inferred_marker_id

        # Marker detection failed for this frame.
        print(
            f"Marker detection failed, "
            f"attempt {attempt + 1}/{max_attempts}"
        )
    return None, None


def capture_measurement(cap, laser, status_callback=None, fallback_roi=None):
    """
    Capture one complete laser measurement.

    The sequence is:

        1. Find the current ROI using ArUco markers.
        2. Set the camera to low exposure.
        3. Capture a laser-OFF background image.
        4. Capture a laser-ON image.
        5. Align both images to the same ROI.
        6. Subtract the background image.
        7. Return the processed laser-only image.

    Parameters:
        cap:
            OpenCV VideoCapture object.

    Parameters:
        fallback_roi:
            ROI corners from the previous successful capture. If provided and
            ArUco detection fails, these corners are used instead of raising.

    Returns:
        (laser_only, roi_corners_used):
            The processed image and the ROI corners that were used, so the
            caller can store them as the new fallback.

    Raises:
        RuntimeError:
            Raised if marker detection fails with no fallback available,
            or if camera capture or alignment fails.
    """

    def send_status(**kwargs) : 
        """
        Helper function for sending measurement status updates
        """
        if status_callback is not None : 
            status_callback(**kwargs)

    # Find the target area's current position.
    send_status(last_message="Finding ROI...")
    roi_corners, inferred_marker_id = find_roi(cap)

    # Use fallback ROI if markers were not detected and one is available.
    if roi_corners is None:
        if fallback_roi is not None:
            send_status(last_message="ArUco markers not found — using previous ROI.")
            roi_corners = fallback_roi
        else:
            raise RuntimeError("ARUCO_NOT_FOUND: Could not detect all four ArUco markers")
    elif inferred_marker_id is not None:
        send_status(
            last_message=f"Marker {inferred_marker_id} not detected — inferred its position from the other three.",
            last_message_category="yellow",
        )

    # Use low exposure for both measurement images.
    send_status(last_message="Setting low exposure...")
    set_low_exposure(cap)


    try : 
        # Turn the laser off before capturing the ambient/background image.
        laser.off()
    except Exception as error : 
        raise RuntimeError(f"RELAY_FAILURE: Could not turn laser off before background capture: {error}")

    # Capture the image containing only ambient light and background noise.
    background = grab_frame(cap)
    send_status(last_message="Capturing laser-off background...")


    # Try to capture the laser on image
    try : 
        try : # Try to turn the laser on
            laser.on()
            send_status(last_message="Turning laser on...")

        except Exception as error : 
            raise RuntimeError(f"RELAY_FAILURE: Could not turn laser on for measurement: {error}")
        
        # Capture the image containing ambient light plus the laser signal.
        laser_image = grab_frame(cap)
        send_status(last_message="Capturing laser image...")

    finally : 
        try : # Try to turn laser off
            laser.off()
            send_status(last_message="Turning laser off...")

        except Exception as error : 
            # More important error overwrites original error
            raise RuntimeError(f"RELAY_FAILURE: Could not turn laser off after measurement: {error}")
        


    # Verify that both camera captures succeeded.
    if background is None or laser_image is None:
        raise RuntimeError(
            "Camera failed to capture measurement images"
        )

    # Perspective-correct and crop the background image
    # using the detected ArUco marker coordinates.
    aligned_background = align_roi(background, roi_corners)
    send_status(last_message="Aligning ROI...")


    # Perspective-correct and crop the laser image
    # using the same ROI coordinates.
    aligned_laser = align_roi(laser_image, roi_corners)

    # Verify that alignment succeeded for both images.
    if aligned_background is None or aligned_laser is None:
        raise RuntimeError(
            "ROI alignment failed"
        )

    # Subtract the background image from the laser image.
    # This should remove most ambient light and leave the laser signal.
    laser_only = subtract_background(aligned_laser, aligned_background)
    send_status(last_message="Subtracting background...")


    # Return the processed image and the ROI corners that were used.
    return laser_only, roi_corners



