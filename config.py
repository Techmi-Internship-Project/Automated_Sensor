from pathlib import Path
ARUCO_DICTIONARY = 0  # replace with cv.aruco.DICT_4X4_50 in code
REQUIRED_MARKER_IDS = {0, 1, 2, 3}
SETTLE_FRAMES = 10
DATA_ROOT = Path(r"G:\My Drive\Bioreactor_Data")
CURRENT_FOLDER = DATA_ROOT / "current"
TRAINING_FOLDER = DATA_ROOT / "training"
