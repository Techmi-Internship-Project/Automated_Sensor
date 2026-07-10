from pathlib import Path
import re

def is_valid_name(name) : 
    """
    Returns True only if name uses letters, numbers, underscores, or hyphens
    """
    return re.fullmatch(r"[A-Za-z0-9_-]+", name) is not None

def get_organism_options(training_folder="training") : 
    """
    Finds the names of all different organism folders inside training/
    """

    training_path = Path(training_folder)

    # Create folder if it doesn't already exist
    training_path.mkdir(parents=True, exist_ok=True)

    organism_options = []
    
    for item in training_path.iterdir() : 
        if item.is_dir() :
            # Add to list
            organism_options.append(item.name)

    return sorted(organism_options)


