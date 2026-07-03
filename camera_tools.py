import cv2 as cv
import subprocess
import re

MAX_CAMERA_INDEX = 10


def get_camera_devices():
    """
    Gets capturable camera devices from WMI, excluding IR cameras.
    IR cameras appear in WMI but MSMF skips them, so we skip them too
    to keep the two lists in sync.
    """

    try:
        result = subprocess.run(
            ["wmic", "path", "Win32_PnPEntity",
             "where", "PNPClass='Camera'",
             "get", "Name,DeviceID"],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("DeviceID"):
                continue
            parts = re.split(r'\s{2,}', line)
            if len(parts) < 2:
                continue
            device_id = parts[0].strip()
            name = parts[-1].strip()
            if "IR" in name or "infrared" in name.lower():
                continue
            devices.insert(0, {"device_id": device_id, "name": name})
        return devices
    except Exception:
        return []


def camera_can_capture(index):
    cap = cv.VideoCapture(index, cv.CAP_MSMF)
    if not cap.isOpened():
        cap.release()
        return False
    success, frame = cap.read()
    cap.release()
    return success and frame is not None


def scan_available_cameras():
    """
    Matches MSMF indices to WMI devices positionally after filtering
    non-capturable devices (IR cameras) from the WMI list.
    """

    devices = get_camera_devices()

    cv.utils.logging.setLogLevel(cv.utils.logging.LOG_LEVEL_SILENT)

    working_indices = []
    consecutive_failures = 0
    for index in range(MAX_CAMERA_INDEX):
        cap = cv.VideoCapture(index, cv.CAP_MSMF)
        opened = cap.isOpened()
        cap.release()
        if opened:
            working_indices.append(index)
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= 2:
                break

    cv.utils.logging.setLogLevel(cv.utils.logging.LOG_LEVEL_WARNING)

    result = []
    for i, index in enumerate(working_indices):
        if i < len(devices):
            device_id = devices[i]["device_id"]
            device_name = devices[i]["name"]
        else:
            device_id = str(index)
            device_name = f"Camera {index + 1}"

        
        result.append({
            "index": index,
            "name": device_name,
            "device_id": device_id,
            "label": f"[{len(result) + 1}] {device_name}"
        })

    return result