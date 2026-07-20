import json
import os
from pathlib import Path
from datetime import datetime

def atomic_write_json(path, data):
    """
    Atomically write the files so that they are safely 
    transferred when uploaded to the shared drive.

    Writes to a temp file, then once done it renames it 
    so that Google Drive doesn't read a half-written file

    """

    path = Path(path)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(temp_path,path)



def write_run_metadata(
        run_folder,
        microorganism_type,
        media_type,
        run_id,
        duration_seconds,
        interval_seconds,
        camera_index,
):
    """
    Write information about setup

    media_type is read by the partner ML machine as a categorical feature
    alongside microorganism_type (falls back to 'unknown' there if absent).
    """

    data = {
        "run_id": run_id,
        "microorganism_type": microorganism_type,
        "media_type": media_type,
        "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "camera_index": camera_index,
        "started_at": datetime.now().isoformat(),
    }

    atomic_write_json(Path(run_folder) / "run.json", data)


def write_done_file(
        run_folder,
        run_id,
        capture_count,
        reason,
        had_errors=False,
        failed_capture_count=0,
        failure_reasons=None,
        degraded_at_finish=False,
):
    """
    Write DONE.json when experiment finishes properly.

    had_errors / failed_capture_count / failure_reasons / degraded_at_finish
    record whether the run hit any capture/hardware failures along the way
    (the run still completes and saves normally even so — see experiment.py),
    so a run with data gaps is distinguishable later from a clean one.
    """

    data = {
        "run_id": run_id,
        "capture_count": capture_count,
        "reason": reason,
        "finished_at": datetime.now().isoformat(),
        "had_errors": had_errors,
        "failed_capture_count": failed_capture_count,
        "failure_reasons": failure_reasons or [],
        "degraded_at_finish": degraded_at_finish,
    }

    atomic_write_json(Path(run_folder) / "DONE.json", data)


def read_done_file(run_folder) :
    """
    Reads DONE.json safely. Returns None if missing or corrupt
    """

    path = Path(run_folder) / "DONE.json"
    if not path.exists() :
        return None

    try :
        with open(path, "r", encoding="utf-8") as f :
            return json.load(f)

    except Exception :
        return None


def write_comms_file(run_folder, retrain_model=False) :
    """
    Writes initial comms.json - This machine writes once at start
    Partner machine reads to know run has started, then takes over write
    """

    data = {
        "start_handshake": "sw", # Sensor write
        "ml_done": False,
        "current_state": None,
        "end_alert": False, # If has consecutively been in stationary or death stage
        "current_biomass": None,
        "current_cfu_ml": None,
        "first_run": False, # Assume this is not the first run until proven otherwise. Used by partner ML machine
        "retrain_model": retrain_model,
    }

    atomic_write_json(Path(run_folder) / "comms.json", data)



def read_comms_file(run_folder) : 
    """
    Reads comms.json safely. Returns None if missing or corrupt
    """

    path = Path(run_folder) / "comms.json"
    if not path.exists() : 
        return None
    
    try : 
        with open(path, "r", encoding="utf-8") as f : 
            return json.load(f)
        
    except Exception : 
        return None


