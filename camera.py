import cv2 as cv
from camera_settings import apply_camera_profile

def open_camera(index): # Fixed settings to avoid changing variables
    cap = cv.VideoCapture(index) # Open camera
    #cap.set(cv.CAP_PROP_FPS, 30)
    # All manual settings, no automated camera 
    #cap.set(cv.CAP_PROP_AUTO_EXPOSURE, 0.25)  # often manual on Windows DirectShow
    #cap.set(cv.CAP_PROP_EXPOSURE, -10)
    #cap.set(cv.CAP_PROP_GAIN, 0)
    #cap.set(cv.CAP_PROP_AUTO_WB, 0)
    #cap.set(cv.CAP_PROP_WB_TEMPERATURE, 4600)
    #cap.set(cv.CAP_PROP_AUTOFOCUS, 0)
    #cap.set(cv.CAP_PROP_FOCUS, 1)
    return cap


def set_normal_exposure(cap):
    print("Normal settings applied")
    apply_camera_profile(cap, "normal")

def set_low_exposure(cap):
    print("Low exposure settings applied")
    apply_camera_profile(cap, "low")

def grab_frame(cap, settleFrames = 10):   # Settle time for camera
    for i in range(settleFrames):
        cap.read()

    success,frame = cap.read()
    if not success:
        return None
    
    return frame