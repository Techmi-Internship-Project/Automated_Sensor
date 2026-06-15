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


def choose_organism(training_folder="training") : 
    """
    Function to let user choose existing organism or create new type
    """

    organism_options = get_organism_options(training_folder)

    # Menu
    print("\nOrganism Menu")
    print("-------------")
    
    if organism_options : 
        for index, organism in enumerate(organism_options, start=1) : 
            print(f"[{index}] {organism}")

    else :  # No organisms available
        print("No existing organisms found")

    create_new_option = len(organism_options) + 1
    print(f"[{create_new_option}] Create new organism")

    while True : 
        choice = input("Choose organism option: ").strip()

        if not choice.isdigit() :  # Invalid option
            print("Invalid choice. Enter a number.")

            continue # Restart the loop

        choice_number = int(choice)
        if 1 <= choice_number <= len(organism_options) :
            selected_organism = organism_options[choice_number - 1]

            confirm = input(f"Use organism '{selected_organism}'? [y/n]: ").strip().lower()

            if confirm == "y" : 
                return selected_organism
            print("Selection cancelled. Choose again.")

            continue

        if choice_number == create_new_option : 
            new_organism = input("Enter new organism name: ").strip()

            # Check if safe
            if not is_valid_name(new_organism) : 
                print("Invalid name. Use only letters, numbers, underscores, or hyphens")
                continue

            # Create new folder for the new organism
            organism_path = Path(training_folder) / new_organism
            organism_path.mkdir(parents=True, exist_ok=True)

            print(f"Created organism folder: {organism_path}")
            return new_organism
        
        print("Invalid choice. Try again")