import cv2 as cv
import numpy as np
from datetime import datetime 

# Image file is formatted as: <microorganism_type>_run_<run_id>_<timestamp>.jpg
# with the timestamp in the format YYYYMMDD_HHMMSS

def subtract_background(measurement, noise) : 
    # Cast to int16 to avoid underflow
    noise = noise.astype(np.int16)
    measurement = measurement.astype(np.int16)

    result = measurement - noise
    # Cast to int8 to return usable value
    result = np.clip(result, 0, 255).astype(np.uint8)

    return result

def make_filename(
        microorganism_type,
        run_id,
    ) :
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{microorganism_type}_run_{run_id}_{timestamp}.jpg"
