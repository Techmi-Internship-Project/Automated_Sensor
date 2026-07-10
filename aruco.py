import cv2 as cv
import numpy as np

ARUCO_DICTIONARY = cv.aruco.DICT_4X4_50
REQUIRED_MARKER_IDS = {0, 1, 2, 3}

""" Marker layout expected by this program:

        ID 0 ---------------- ID 1
        |                      |
        |         ROI          |
        |                      |
        ID 3 ---------------- ID 2

 The program uses the inside corner of each marker to define the ROI.
"""


def detect_aruco_markers(image):
    """
    Detect ArUco markers in the image.

    Returns:
        corners:
            List containing the four detected corners of each marker.

            OpenCV stores marker corners in this order:
                0 = top-left
                1 = top-right
                2 = bottom-right
                3 = bottom-left

        ids:
            ID number for each detected marker.

            ids is None when no markers are detected.
    """
    dictionary = cv.aruco.getPredefinedDictionary(ARUCO_DICTIONARY)
    parameters = cv.aruco.DetectorParameters()
    detector = cv.aruco.ArucoDetector(dictionary, parameters)
    corners, ids, _ = detector.detectMarkers(image)
    return corners, ids



def get_roi_corners(corners, ids):
    
    """
    Get the four image points that define the ROI.

    Expected marker positions:

        ID 0 = top-left
        ID 1 = top-right
        ID 2 = bottom-right
        ID 3 = bottom-left

    The inside corner of each marker is used so the markers themselves are
    excluded from the final ROI.

    Returns:
        float32 array in this order:
            top-left
            top-right
            bottom-right
            bottom-left

        Returns None if any required marker is missing.
    """


    if ids is None:
        return None

    detected_markers = {}

    for marker_corners, marker_id in zip(corners, ids.flatten()):
        marker_id = int(marker_id)
        if marker_id not in REQUIRED_MARKER_IDS:
            continue
        detected_markers[marker_id] = marker_corners.reshape(4, 2)

    if not REQUIRED_MARKER_IDS.issubset(detected_markers):
        return None

    top_left = detected_markers[0][2]
    top_right = detected_markers[1][3]
    bottom_right = detected_markers[2][0]
    bottom_left = detected_markers[3][1]

    return np.float32([
        top_left,
        top_right,
        bottom_right,
        bottom_left
    ])


def align_roi(image, roi_corners):
    """
    Warp the detected ROI into a rectangular image.

    The output size is calculated from the ROI's detected pixel dimensions.
    This preserves as much real camera detail as possible.

    The function corrects normal movement, rotation, and perspective.
    It does not perform a true cylindrical unwrap.

    Returns:
        aligned ROI image

        Returns None if the detected ROI dimensions are invalid.
    """
    top_left = roi_corners[0]
    top_right = roi_corners[1]
    bottom_right = roi_corners[2]
    bottom_left = roi_corners[3]

    top_width = np.linalg.norm(top_right - top_left)
    bottom_width = np.linalg.norm(bottom_right - bottom_left)
    output_width = int(round(max(top_width, bottom_width)))

    left_height = np.linalg.norm(bottom_left - top_left)
    right_height = np.linalg.norm(bottom_right - top_right)
    output_height = int(round(max(left_height, right_height)))

    if output_width < 2 or output_height < 2:
        return None

    destination_corners = np.float32([
        [0, 0],
        [output_width - 1, 0],
        [output_width - 1, output_height - 1],
        [0, output_height - 1]
    ])

    transform = cv.getPerspectiveTransform(roi_corners, destination_corners)

    aligned_roi = cv.warpPerspective(
        image,
        transform,
        (output_width, output_height),
        flags=cv.INTER_LINEAR
    )

    return aligned_roi



# ==============================================================================
# DEBUG IMAGE
# ==============================================================================

def create_debug_image(image, corners, ids, roi_corners):
    """
    Draw the detected markers and ROI outline on a copy of the original image.

    This image is only used to verify that marker detection and ROI placement
    are working correctly.

    Used during development to visually verify marker detection
    """

    debug = image.copy()

    # Draw detected marker borders and IDs.
    if ids is not None:
        cv.aruco.drawDetectedMarkers(debug, corners, ids)

    # Draw the selected ROI as a green outline.
    if roi_corners is not None:
        polygon = roi_corners.astype(np.int32).reshape(-1, 1, 2)

        cv.polylines(
            debug,
            [polygon],
            True,
            (0, 255, 0),
            3
        )

    return debug
