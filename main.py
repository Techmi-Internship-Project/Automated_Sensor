import cv2 as cv
import matplotlib.pyplot as plt
from datetime import datetime
import time

from startup_recovery import handle_existing_runs, move_run_to_training
from organism_menu import choose_organism
from experiment_controller import ExperimentController

def main():
    #=================
    #   Startup
    #=================

    handle_existing_runs(current_folder="current", training_folder="training")

    microorganism_type = choose_organism(training_folder="training")
    
    run_id = int(time.time())
    camera_index = 0
    duration_minutes = 0.5
    interval_minutes = 0.1
    duration_seconds = duration_minutes * 60
    interval_seconds = interval_minutes * 60

    controller = ExperimentController()


    #=================
    # Begin Execution
    #=================


    try:

        # Start experiment in background thread
        run_id = controller.start_experiment(
            microorganism_type=microorganism_type,
            camera_index=camera_index,
            duration_seconds=duration_seconds,
            interval_seconds=interval_seconds,
            output_root="current"
        )

        print(f"Started run: {run_id}")
        
        while controller.thread_is_alive() : 
            print("Experiment running...")
            time.sleep(1)

    except KeyboardInterrupt : 
        print("\nStop requested by user.")

        controller.stop_experiment()

        # Wait for thread to shut down safely
        while controller.thread_is_alive()  :
            print("Waiting for experiment to stop...")
            time.sleep(1)

    finally:
        if controller.last_error is not None : 
            print(f"Experiment error: {controller.last_error}")

        if controller.last_run_folder is not None : 
            print(f"Run saved in current/: {controller.last_run_folder}")

            # Move run folder to training
            move_run_to_training(controller.last_run_folder, training_folder="training")

        else: 
            print("No run folder created, so nothing moved to training")
    print("Program finished.")

if __name__ == "__main__": main()
