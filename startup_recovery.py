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

    cleanup_empty_organism_folders(current_folder)
    
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


def move_valid_runs_to_training(current_folder="current", training_folder="training"):
    """
    Moves runs with captured images from current/ to training/.
    Only cleans up folders that were successfully moved.
    Never wipes current/ wholesale.
    """
    existing_runs = find_existing_runs(current_folder=current_folder)
    moved_count = 0
    skipped_count = 0

    for run_folder in existing_runs:
        image_count = len(list(run_folder.glob("*.jpg")))

        # Only move runs that actually have captured data
        if image_count > 0:
            move_success = move_run_to_training(
                run_folder,
                training_folder=training_folder,
                current_folder=current_folder
            )
            if move_success:
                moved_count += 1
            else:
                skipped_count += 1
        else:
            skipped_count += 1

    # Only clean up empty organism folders, never wipe current/ entirely
    cleanup_empty_organism_folders(current_folder)

    return moved_count, skipped_count

def cleanup_empty_organism_folders(current_folder="current") : 
    current_path = Path(current_folder)

    if not current_path.exists() :
        return # Does not exist
    
    for organism_folder in current_path.iterdir() : 
        if not organism_folder.is_dir() :
            continue

        try : 
            organism_folder.rmdir()

        # Ignore error if folder is not empty
        except OSError : 
            # Do nothing because non-empty folders stay
            pass 


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

    for item in folder_path.iterdir() : 
        if item.is_dir() : 
            # Delete the folder
            shutil.rmtree(item, onexc=handle_error)

        else : 
            try:
                # Delete the individual file
                item.unlink()
            except Exception :
                pass


