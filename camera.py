import cv2 as cv
from camera_settings import apply_camera_profile
from config import SETTLE_FRAMES

def open_camera(index):
    cap = cv.VideoCapture(index, cv.CAP_MSMF)
    cap.set(cv.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, 1080)

    return cap


def reopen_camera(cap, index):
    """
    Release a (possibly dead) capture handle and open a fresh one on the same
    index. Used to recover from the Windows MSMF driver silently closing the
    camera on long runs. Exposure is re-applied per capture, so only the
    VideoCapture object needs to be rebuilt here.

    Returns the new capture object (never releases without reopening).
    """
    try:
        if cap is not None:
            cap.release()
    except Exception:
        pass

    return open_camera(index)
    



def set_normal_exposure(cap):
    apply_camera_profile(cap, "normal")

def set_low_exposure(cap):
    apply_camera_profile(cap, "low")

def grab_frame(cap, settle_frames = SETTLE_FRAMES):   # Settle time for camera
    for _ in range(settle_frames):
        cap.read()

    success,frame = cap.read()
    if not success:
        return None
    
    return frame