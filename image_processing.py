import cv2 as cv
import numpy as np
from datetime import datetime 

def subtract_background(measurement, noise) : 
    noise = noise.astype(np.int16)
    measurement = measurement.astype(np.int16)

    result = measurement - noise
    result = np.clip(result, 0, 255).astype(np.uint8)

    return result

def make_filename(
        microorganism_type,
        run_id,
    ) :
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{microorganism_type}_run_{run_id}_{timestamp}.jpg"
