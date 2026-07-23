from pathlib import Path
import shutil
import json
import os
import stat

def read_json_file(path) : 
    path = Path(path)

    with open(path, "r", encoding="utf-8") as file : 
        return json.load(file)

def find_existing_runs(current_folder="current") : 
    """
    Find existing run folders inside current.
    """

    current_path = Path(current_folder)

    if not current_path.exists() :  # Should exist at this point, but just for safety
        current_path.mkdir(parents=True, exist_ok=True)
        return [] # Return empty list since there was nothing
    
    run_folders = []

    for organism_folder in current_path.iterdir() : # Each microorganism folder type
        if not organism_folder.is_dir() : # If item is not a folder
            continue
        try:
            for run_folder in organism_folder.iterdir() : # Each run
                if not run_folder.is_dir() : 
                    continue # Skip if not a folder

                if (run_folder / "run.json").exists() : 
                    run_folders.append(run_folder)
        except PermissionError:
            print(f"Skipping {organism_folder}: access denied (Google Drive Sync)")
            continue 

    return run_folders


def classify_run_folder(run_folder) : 
    """
    Determine whether previous run completed or was interrupted.
    """

    done_file = run_folder / "DONE.json"
    run_file = run_folder / "run.json"

    image_files = list(run_folder.glob("*.jpg")) # All image files

    if done_file.exists() : 
        return "completed"
    
    if run_file.exists() and len(image_files) > 0 : 
        return "interrupted"
    
    if run_file.exists() and len(image_files) == 0 : 
        return "empty_started"
    
    return "unknown"

def get_run_metadata(run_folder) : 
    """
    Gets organism type and run ID from run.json
    """

    run_file = run_folder / "run.json"

    if not run_file.exists() : 
        return None
    
    # Try to read run.json
    try :
        data = read_json_file(run_file)

    except (json.JSONDecodeError, OSError) : 
        return None
    
    # Get data from json file
    microorganism_type = data.get("microorganism_type")
    run_id = data.get("run_id")

    if microorganism_type is None or run_id is None : # Couldn't read the data
        return None
    
    return {
        "microorganism_type": str(microorganism_type),
        "run_id": str(run_id) 
    }


def build_training_destination(run_folder, training_folder="training") : 
    """
    Creates a destination folder for training data
    """
    metadata = get_run_metadata(run_folder)

    # Check if it could be read
    if metadata is None : 
        return None
    
    # Get metadata
    microorganism_type = metadata["microorganism_type"]
    run_id = metadata["run_id"]

    training_path = Path(training_folder)

    # Create the organism-specific path
    organism_folder = training_path / microorganism_type

    destination = organism_folder / f"run_{run_id}"
    return destination

def move_run_to_training(run_folder, training_folder="training", current_folder="current") : 
    """
    Moves one run folder into training/organism/run_id
    """

    destination = build_training_destination(run_folder, training_folder)

    # Check if building the destination failed, skip if so
    if destination is None :
        print(f"Skipping {run_folder}: missing or invalid run.json")

        return False
    
    destination.parent.mkdir(parents=True, exist_ok=True)

    # If somehow duplicate IDs occur, skip this run instead of overwriting data
    if destination.exists() : 
        print(f"Skipping {run_folder}: destination already exists at {destination}")
        return False # Move did not happen
    

    # Move entire run folder into training destination
    shutil.move(str(run_folder), str(destination))
    print(f"Moved {run_folder} -> {destination}")

    # The run data has already safely moved at this point — a failure while
    # tidying up the now-empty organism folder (e.g. a Google Drive
    # placeholder/reparse-point file raising OSError mid-walk) must not
    # make this function report the move itself as failed. The caller also
    # runs its own belt-and-suspenders cleanup of current/ afterward.
    try:
        cleanup_empty_organism_folders(current_folder)
    except Exception as error:
        print(f"Warning: could not clean up empty organism folder in {current_folder}: {error}")

    return True # Move succeeded


def current_folder_has_contents(current_folder="current") :
    """
    Checks if current/ contains anything for the GUI
    """

    current_path = Path(current_folder)
    if not current_path.exists() : 
        # Create the current folder if it doesn't exist already
        current_path.mkdir(parents=True, exist_ok=True)

        return False # Because folder was empty
    
    return any(current_path.iterdir()) # Return whether the folder contains at least one item


def move_valid_runs_to_training(current_folder="current", training_folder="training") : 
    """
    Moves current/ runs into training/, valid runs have the status "completed" or "interrupted"
    """
    existing_runs = find_existing_runs(current_folder=current_folder)
    moved_count = 0
    skipped_count = 0

    for run_folder in existing_runs : 
        # Classify run folder
        run_state = classify_run_folder(run_folder)
        image_count = len(list(run_folder.glob("*.jpg")))

        # Check if should be moved
        if run_state in ["completed", "interrupted"] and image_count > 0 : 
            move_success = move_run_to_training(run_folder, training_folder=training_folder)
            if move_success :
                moved_count += 1
            else : 
                skipped_count += 1

        else : 
            # Runs that should not be moved
            skipped_count += 1


    return moved_count, skipped_count


def cleanup_empty_organism_folders(current_folder="current") :
    current_path = Path(current_folder)

    if not current_path.exists() :
        return # Does not exist

    def handle_error(func, path, exc_info) :
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception :
            pass

    try:
        organism_folders = list(current_path.iterdir())
    except OSError as error:
        print(f"Warning: could not list {current_path} for cleanup: {error}")
        return

    for organism_folder in organism_folders :
        try :
            if not organism_folder.is_dir() :
                continue

            try :
                organism_folder.rmdir()
                continue

            # Not truly empty — could be real run data, or could just be a
            # stray leftover file (e.g. a Windows desktop.ini or a Google
            # Drive sync marker) that a bare rmdir() refuses to remove.
            except OSError :
                pass

            # Only escalate to a recursive delete if there's no actual run
            # data in here — never remove a folder that still has a run.json
            # anywhere inside it.
            if any(organism_folder.rglob("run.json")) :
                continue

            shutil.rmtree(organism_folder, onerror=handle_error)

        except Exception as error :
            # A single problematic folder (e.g. a Google Drive placeholder
            # file that isn't fully synced yet) must not stop the other
            # organism folders in current/ from being cleaned up.
            print(f"Warning: could not clean up {organism_folder}: {error}")
            continue


def find_last_run_info(current_folder="current", training_folder="training") :
    """
    Finds the most recently touched run folder across current/ and training/, and
    returns display info for Recovery / Summary panel.
    
    Returns None if no run folders exist 
    """

    all_runs = (find_existing_runs(current_folder=current_folder) + find_existing_runs(current_folder=training_folder))

    if not all_runs : 
        return None # No runs found

    def folder_mtime(folder) : 
        try : 
            return folder.stat().st_mtime
        except OSError :
            return 0

    latest = max(all_runs, key=folder_mtime)

    metadata = get_run_metadata(latest) or {}
    organism_name = metadata.get("microorganism_type", "unknown")
    run_id = metadata.get("run_id", "unknown")

    images = sorted(latest.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
    capture_count = len(images)

    if images : 
        last_capture_ts = images[-1].stat().st_mtime # Get the timestamp of the last image
    else :
        last_capture_ts = None

    return {
        "run_name": f"{organism_name} / run_{run_id}",
        "capture_count" : capture_count,
        "last_capture_ts": last_capture_ts,
    }


def wipe_folder_contents(folder_path) : 
    """
    Helper function to delete everything inside a folder
    """

    folder_path = Path(folder_path)

    # If somehow there is no current folder, create one
    if not folder_path.exists() :  
        folder_path.mkdir(parents=True, exist_ok=True)

        return
    
    def handle_error(func, path, exc_info) :
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    try:
        items = list(folder_path.iterdir())
    except OSError as error:
        print(f"Warning: could not list {folder_path} to wipe: {error}")
        return

    for item in items :
        try:
            if item.is_dir() :
                # Delete the folder. onerror (not onexc, which only exists on
                # Python 3.12+) for compatibility with older Python — onexc
                # raised TypeError immediately on 3.11, silently aborting this
                # whole cleanup every time it ran.
                shutil.rmtree(item, onerror=handle_error)

            else :
                # Delete the individual file
                item.unlink()

        except Exception as error:
            # One problematic item (e.g. a Google Drive placeholder file
            # mid-sync) must not stop the rest of current/ from being wiped.
            print(f"Warning: could not remove {item}: {error}")
            continue


