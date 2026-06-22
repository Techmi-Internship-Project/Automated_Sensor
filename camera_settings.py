import json
from pathlib import Path
import cv2 as cv

SETTINGS_FILE = Path("camera_settings.json")

AUTO_CONTROL_WARNING = ("Warning: auto exposure, auto white balance, and auto focus MUST be disabled manually "
                        "using Webcam Configuration Tool or another similar software before these settings will behave reliably.")

DEFAULT_CAMERA_SETTINGS = {
    "normal": {
        "exposure": -6,
        "gain": 0,
        "wb_temp": 4600
    },
    "low": {
        "exposure": -10,
        "gain": 0,
        "wb_temp": 4600
    }
}


def get_default_camera_settings() : 
    """
    Returns a copy of the default settings
    """
    return json.loads(json.dumps(DEFAULT_CAMERA_SETTINGS))


def load_camera_settings() :
    """
    Loads camera settings from JSON file
    """

    if not SETTINGS_FILE.exists() : 
        # Create fresh copy of default settings
        settings = get_default_camera_settings()
        save_camera_settings(settings)
        
        return settings
    
    # Open settings file for reading
    with open(SETTINGS_FILE, "r", encoding="utf-8") as file : 
        loaded_settings = json.load(file)

    # Create fresh default settings dictionary 
    settings = get_default_camera_settings()

    # Merge loaded settings into defaults so missing fields do not crash program
    for profile_name in settings : 
        if profile_name in loaded_settings : 
            settings[profile_name].update(loaded_settings[profile_name])

    return settings



def save_camera_settings(settings) : 
    """
    Saves camera settings to the JSON file
    """

    with open(SETTINGS_FILE, "w", encoding="utf-8") as file : 
        # Write settings dictionary as readable JSON
        json.dump(settings, file, indent=4)
        



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
    # WB
    cap.set(cv.CAP_PROP_WB_TEMPERATURE, profile["wb_temp"])



def read_camera_values(cap) : 
    """
    Reads back current camera values after applying settings
    """

    return {
        "exposure": cap.get(cv.CAP_PROP_EXPOSURE),
        "gain": cap.get(cv.CAP_PROP_GAIN),
        "wb_temp": cap.get(cv.CAP_PROP_WB_TEMPERATURE),
    }