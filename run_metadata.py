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
        run_id,
        duration_seconds,
        interval_seconds,
        camera_index
):
    """
    Write information about setup
    """

    data = {
        "run_id": run_id,
        "microorganism_type": microorganism_type,
        "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "camera_index": camera_index,
        "started_at": datetime.now().isoformat()
    }

    atomic_write_json(Path(run_folder) / "run.json", data)


def write_done_file(
        run_folder,
        run_id,
        capture_count,
        reason
):  
    """
    Write DONE.json when experiment finishes properly
    """

    data = {
        "run_id": run_id,
        "capture_count": capture_count,
        "reason": reason,
        "finished_at": datetime.now().isoformat()
    }

    atomic_write_json(Path(run_folder) / "DONE.json", data)