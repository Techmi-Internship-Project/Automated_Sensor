from pathlib import Path
import json

SETTLE_FRAMES = 10

_SETTINGS_FILE = Path(__file__).parent / "app_settings.json"

_SETTINGS_DEFAULTS = {
    "standalone_mode": True,
    "retrain_model": False,
    "handshake_timeout_hours": 1.0
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
        
    except Exception: 
        print(f"Warning: could not load app_settings.json ({e}). Using defaults.")
        return {**_SETTINGS_DEFAULTS}
    
def save_app_settings(settings) : 
    """
    Saves application settings to JSON file
    """
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as file :
        json.dump(settings, file, indent=4)