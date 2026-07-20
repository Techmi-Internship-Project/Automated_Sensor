import json
from pathlib import Path
import cv2 as cv

from run_metadata import atomic_write_json

SETTINGS_FILE = Path("camera_settings.json")

AUTO_CONTROL_WARNING = ("Warning: auto exposure, auto white balance, and auto focus MUST be disabled manually "
                        "using Webcam Configuration Tool or another similar software before these settings will behave reliably.")

DEFAULT_CAMERA_SETTINGS = {
    "normal": {
        "exposure": -6,
        "gain": 0,
    },
    "low": {
        "exposure": -10,
        "gain": 0,
    }
}


def get_default_camera_settings() : 
    """
    Returns a copy of the default settings
    """
    return json.loads(json.dumps(DEFAULT_CAMERA_SETTINGS))


def load_camera_settings() :
    """
    Loads camera settings from JSON file. Falls back to defaults if the
    file is missing, corrupted (e.g. left half-written by a crash), or
    doesn't contain the expected structure — a bad settings file should
    never stop the app from starting.
    """

    if not SETTINGS_FILE.exists() :
        # Create fresh copy of default settings
        settings = get_default_camera_settings()
        save_camera_settings(settings)

        return settings

    try :
        # Open settings file for reading
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file :
            loaded_settings = json.load(file)
    except (OSError, json.JSONDecodeError) as error :
        print(f"Warning: could not load {SETTINGS_FILE} ({error}). Using defaults.")
        return get_default_camera_settings()

    # Create fresh default settings dictionary
    settings = get_default_camera_settings()

    if not isinstance(loaded_settings, dict) :
        print(f"Warning: {SETTINGS_FILE} has an unexpected format. Using defaults.")
        return settings

    # Merge loaded settings into defaults so missing fields do not crash program
    for profile_name in settings :
        profile_data = loaded_settings.get(profile_name)
        if isinstance(profile_data, dict) :
            settings[profile_name].update(profile_data)

    return settings



def save_camera_settings(settings) :
    """
    Saves camera settings to the JSON file. Writes to a temp file and
    renames into place so a crash or dropped drive mid-write can't leave
    behind a truncated/corrupt settings file.
    """

    atomic_write_json(SETTINGS_FILE, settings)
        



def save_camera_profile(profile_name, profile_settings) : 
    """
    Saves a camera profile
    """

    # Load current settings from disk
    settings = load_camera_settings()

    # Check if profile name is invalid
    if profile_name not in settings : 
        raise ValueError(f"Unknown camera profile: {profile_name}")
    
    settings[profile_name].update(profile_settings)

    # Save all settings back to disk
    save_camera_settings(settings)


def get_camera_profile(profile_name) : 
    """
    Returns one camera profile
    """

    settings = load_camera_settings()
     # Check if profile name is invalid
    if profile_name not in settings : 
        raise ValueError(f"Unknown camera profile: {profile_name}")
    
    return settings[profile_name]



def apply_camera_profile(cap, profile_name) : 
    """
    Applies a camera profile to an opened camera
    """

    profile = get_camera_profile(profile_name)

    # Apply exposure
    cap.set(cv.CAP_PROP_EXPOSURE, profile["exposure"])
    # Gain
    cap.set(cv.CAP_PROP_GAIN, profile["gain"])
    



def read_camera_values(cap) : 
    """
    Reads back current camera values after applying settings
    """

    return {
        "exposure": cap.get(cv.CAP_PROP_EXPOSURE),
        "gain": cap.get(cv.CAP_PROP_GAIN),
    }
