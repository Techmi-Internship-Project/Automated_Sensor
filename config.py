from pathlib import Path
import json

from run_metadata import atomic_write_json

SETTLE_FRAMES = 10

_SETTINGS_FILE = Path(__file__).parent / "app_settings.json"

_SETTINGS_DEFAULTS = {
    "standalone_mode": True,
    "retrain_model": False,
    "handshake_timeout_hours": 1.0,
    "known_media_types": [],
}

def load_app_settings() : 
    """
    Loads application settings from JSON file
    """
    if not _SETTINGS_FILE.exists() :
        return {**_SETTINGS_DEFAULTS} # No default data root, need to get on cold install
    try :
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as file : 
            loaded = json.load(file)

        # Merge defaults so new keys are always present
        merged = dict(_SETTINGS_DEFAULTS)
        merged.update(loaded)
        return merged
        
    except Exception as e: 
        print(f"Warning: could not load app_settings.json ({e}). Using defaults.")
        return {**_SETTINGS_DEFAULTS}
    
def save_app_settings(settings) :
    """
    Saves application settings to JSON file. Writes to a temp file and
    renames into place so a crash or dropped drive mid-write can't leave
    behind a truncated/corrupt settings file (e.g. wiping data_root).
    """
    atomic_write_json(_SETTINGS_FILE, settings)