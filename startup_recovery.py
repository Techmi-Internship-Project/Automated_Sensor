from pathlib import Path
import shutil
import json

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
        for run_folder in organism_folder.iterdir() : # Each run
            if not run_folder.is_dir() : 
                continue # Skip if not a folder

            if (run_folder / "run.json").exists() : 
                run_folders.append(run_folder)

    return run_folders


def classify_run_folder(run_folder) : 
    """
    Determine whether previous run completed or was interrupted.
    """

    done_file = run_folder / "DONE.json"
    run_file = run_folder / "run.json"

    image_files = list(run_folder.glob("*.png")) # All image files

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


def handle_existing_runs(current_folder="current", training_folder="training") : 
    """
    Check for old runs in current/ and ask the user what to do with them.
    """

    existing_runs = find_existing_runs(current_folder)
    

    if not existing_runs : 
        return 
    
    print("\nExisting run folders found:\n")

    for index, run_folder in enumerate(existing_runs) : 
        state = classify_run_folder(run_folder)
        image_count = len(list(run_folder.glob("*.jpg")))

        metadata = get_run_metadata(run_folder)
        organism_name = metadata["microorganism_type"] if metadata else "unknown"

        run_id = metadata["run_id"] if metadata else "unknown"

        print(
            f"[{index}] {run_folder.name} | "
            f"organism={organism_name} | "
            f"run_id={run_id} | "
            f"state={state} | "
            f"images={image_count}"
        )

    # Menu
    print("\nChoose what to do: ")
    print("[1] Keep them")
    print("[2] Delete them")
    print("[3] Move completed/interrupted runs to training folder")

    choice = input("Enter choice: ").strip()

    if choice == "1" : 
        print("Keep existing runs.")
        return
    
    if choice == "2" : 
        confirm = input("Confirm deletion? [y/n] :").strip()
        
        if confirm != "y" : 
            print("Deletion cancelled")
            return

        for run_folder in existing_runs : 
            shutil.rmtree(run_folder)
            print(f"Deleted: {run_folder}")

        
        wipe_folder_contents(current_folder)

        return
    
    if choice == "3" : 
        
        for run_folder in existing_runs : 
            state = classify_run_folder(run_folder)
            image_count = len(list(run_folder.glob("*.jpg")))
            
            if state in ["completed", "interrupted"] and image_count > 0 :
                move_run_to_training(run_folder, training_folder, current_folder)

                continue
            print(f"Skipping {run_folder}: state={state}, images={image_count}")
        
        cleanup_empty_organism_folders(current_folder)

        return
    
    print("Invalid choice. Keeping existing runs.")


    

def wipe_folder_contents(folder_path) : 
    """
    Helper function to delete everything inside a folder
    """

    folder_path = Path(folder_path)

    # If somehow there is no current folder, create one
    if not folder_path.exists() :  
        folder_path.mkdir(parents=True, exist_ok=True)

        return
    
    for item in folder_path.iterdir() : 
        if item.is_dir() : 
            # Delete the folder
            shutil.rmtree(item)

        else : 
            # Delete the individual file
            item.unlink()