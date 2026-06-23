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
        roi_corners:
            The four detected ROI corner coordinates.

        None:
            Returned if the markers could not be detected.
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
        roi_corners = get_roi_corners(corners, ids)

        # If all required markers were found, return the ROI corners.
        if roi_corners is not None:
            return roi_corners

        # Marker detection failed for this frame.
        print(
            f"Marker detection failed, "
            f"attempt {attempt + 1}/{max_attempts}"
        )
    return None


def capture_measurement(cap, laser, status_callback=None):
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

    Returns:
        laser_only:
            The aligned and background-subtracted laser image.

    Raises:
        RuntimeError:
            Raised if marker detection, camera capture, or alignment fails.
    """

    def send_status(**kwargs) : 
        """
        Helper function for sending measurement status updates
        """
        if status_callback is not None : 
            status_callback(**kwargs)

    # Find the target area's current position.
    roi_corners = find_roi(cap)
    send_status(last_message="Finding ROI...")

    # Stop this measurement if all four markers were not detected.
    if roi_corners is None:
        raise RuntimeError("ARUCO_NOT_FOUND: Could not detect all four ArUco markers")

    # Use low exposure for both measurement images.
    set_low_exposure(cap)
    send_status(last_message="Setting low exposure...")


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


    # Return the processed image to main.py.
    return laser_only



