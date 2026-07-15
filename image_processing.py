import cv2 as cv
import numpy as np
from datetime import datetime 

# Image file is formatted as: <microorganism_type>_run_<run_id>_<timestamp>_<index>.jpg
# with the timestamp in the format YYYYMMDD_HHMMSS and a zero-padded capture
# index. The index guarantees a unique filename even when two captures land in
# the same wall-clock second, so images are never silently overwritten. The
# partner ML parser reads run_id/date/time by fixed position and ignores the
# trailing numeric index (it is not a phase-stage suffix).

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
        capture_index=0,
    ) :
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{microorganism_type}_run_{run_id}_{timestamp}_{capture_index:04d}.jpg"
