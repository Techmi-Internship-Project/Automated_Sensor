import cv2 as cv
from camera_settings import apply_camera_profile
from config import SETTLE_FRAMES

def open_camera(index):
    cap = cv.VideoCapture(index, cv.CAP_MSMF)
    cap.set(cv.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, 1080)
    
    return cap
    



def set_normal_exposure(cap):
    print("Normal settings applied")
    apply_camera_profile(cap, "normal")

def set_low_exposure(cap):
    print("Low exposure settings applied")
    apply_camera_profile(cap, "low")

def grab_frame(cap, settleFrames = SETTLE_FRAMES):   # Settle time for camera
    for i in range(settleFrames):
        cap.read()

    success,frame = cap.read()
    if not success:
        return None
    
    return frame