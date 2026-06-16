import tkinter as tk
from tkinter import messagebox, simpledialog
import re

from pathlib import Path

from experiment_controller import ExperimentController
from startup_recovery import move_valid_runs_to_training, current_folder_has_contents, wipe_folder_contents, move_run_to_training
from organism_menu import get_organism_options

class SensorGUI : 
    """
    Class for the GUI
    """
    def __init__(self):
        self.root = tk.Tk() # Create main Tkinter window
        self.root.title("Bioreactor Sensor")
        self.root.geometry("500x400")

        self.controller = ExperimentController()

        self.organism = tk.StringVar()
        self.camera_index = tk.StringVar(value="0")

        #Both in minutes
        self.duration = tk.StringVar(value="0.5")
        self.interval = tk.StringVar(value="0.1")

        self.status = tk.StringVar(value="Status: Idle")
        self.run_id = tk.StringVar(value="Run ID: None")
        self.error = tk.StringVar(value="Error: None")
        self.stop_requested = False

        self.build_widgets()
        self.update_status_loop() # Start repeated GUI status updater

    
    def build_widgets(self) : 
        """
        Function that builds the GUI layout
        """

        title_label = tk.Label(self.root, text="Bioreactor Sensor Controller", font=("Arial", 16))
        title_label.pack(pady=10) # Place title label in window

        # Store recovery button so we can enable/disable it 
        self.recovery_button = tk.Button(self.root, text="Handle Old Runs", command=self.open_recovery_window)
        self.recovery_button.pack(pady=5)

        organism_frame = tk.Frame(self.root)
        organism_frame.pack(pady=5)

        organism_label = tk.Label(organism_frame, text="Organism")
        organism_label.pack(side=tk.LEFT)

        self.organism_options = get_organism_options("training")
        # Dropdown
        if self.organism_options : 
            self.organism.set(self.organism_options[0])
        else :
            # Set to empty string
            self.organism.set("")

        self.organism_menu = tk.OptionMenu(organism_frame, self.organism, *self.organism_options)
        self.organism_menu.pack(side=tk.LEFT)

        # Create new organism
        create_organism_button = tk.Button(organism_frame, text="Create New", command=self.create_new_organism)
        create_organism_button.pack(side=tk.LEFT, padx=5)

        # Camera
        camera_frame = tk.Frame(self.root)
        camera_frame.pack(pady=5)

        camera_label = tk.Label(camera_frame, text="Camera Index:")
        camera_label.pack(side=tk.LEFT)
        camera_entry = tk.Entry(camera_frame, textvariable=self.camera_index, width=10)
        camera_entry.pack(side=tk.LEFT)

        # Duration
        duration_frame = tk.Frame(self.root)
        duration_frame.pack(pady=5)
        duration_label = tk.Label(duration_frame, text="Duration minutes: ")
        duration_label.pack(side=tk.LEFT)
        duration_entry = tk.Entry(duration_frame, textvariable=self.duration, width=10)
        duration_entry.pack(side=tk.LEFT)

        # Interval
        interval_frame = tk.Frame(self.root)
        interval_frame.pack(pady=5)
        interval_label = tk.Label(interval_frame, text="Interval minutes:")
        interval_label.pack(side=tk.LEFT)
        interval_entry = tk.Entry(interval_frame, textvariable=self.interval, width=10)
        interval_entry.pack(side=tk.LEFT)

        # Create a frame for start and stop buttons.
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=15)

        # Create the start button.
        self.start_button = tk.Button(button_frame, text="Start", command=self.start_experiment)
        self.start_button.pack(side=tk.LEFT, padx=10)
        
        # Create the stop button.
        self.stop_button = tk.Button(button_frame, text="Stop", command=self.stop_experiment)
        self.stop_button.pack(side=tk.LEFT, padx=10)

        # Create a label for status.
        status_label = tk.Label(self.root, textvariable=self.status)
        status_label.pack(pady=5)

        # Create a label for run ID.
        run_id_label = tk.Label(self.root, textvariable=self.run_id)
        run_id_label.pack(pady=5)

        # Create a label for errors.
        error_label = tk.Label(self.root, textvariable=self.error)
        error_label.pack(pady=5)


    def create_new_organism(self) : 
        """
        Creates a new organism folder.
        """
        organism_name = simpledialog.askstring("Create New Organism", "Enter organism name: ")

        # Check if user cancelled the popup
        if organism_name is None : 
            return

        # Clean up the organism name
        organism_name = organism_name.strip().replace(" ", "_").lower()

        # Empty name error
        if organism_name == "" : 
            messagebox.showerror("Error", "Organism name cannot be empty.")
            return
        
        if not re.match(r'^[a-zA-Z0-9_]+$', organism_name) :
            messagebox.showerror("Error", "Organism name can only contain letters, numbers, and underscores.")
            return
        
        organism_path = Path("training") / organism_name
        organism_path.mkdir(parents=True, exist_ok=True)

        # Refresh organism dropdown 
        self.refresh_organism_menu()
        # Select the new organism
        self.organism.set(organism_name)

        messagebox.showinfo("Organism Created", f"Created organism: {organism_name}")

    def open_recovery_window(self) : 
        """
        Opens recovery popup window
        """
        if not current_folder_has_contents("current") : 
            messagebox.showinfo("No Old Runs", "current folder is empty.")

            self.update_recovery_button_state()
            return
        
        # Create popup window
        recovery_window = tk.Toplevel(self.root)
        recovery_window.title("Handle Old Runs")
        recovery_window.geometry("380x220")

        # Prevent interaction with main window until popup closed
        recovery_window.grab_set()
        
        title_label = tk.Label(recovery_window, text="Old data exists in current folder", font=("Arial", 14))
        title_label.pack(pady=10)
        
        info_label = tk.Label(recovery_window, text="Choose what to do before starting a new run.")
        info_label.pack(pady=5)

        move_button = tk.Button(recovery_window, text="Move valid runs to training folder", command=lambda: self.recovery_move_valid_runs(recovery_window))
        move_button.pack(pady=5)

        del_button = tk.Button(recovery_window, text="Delete everything in current folder", command=lambda: self.recovery_delete_current(recovery_window))
        del_button.pack(pady=5)

        keep_button = tk.Button(recovery_window,text="Keep for now", command=recovery_window.destroy)
        keep_button.pack(pady=5)

    
    def recovery_move_valid_runs(self, recovery_window) : 
        """
        Moves all valid current folder runs from the recovery popup
        """
        moved_count, skipped_count = move_valid_runs_to_training()

        self.refresh_organism_menu()
        self.update_recovery_button_state()
        recovery_window.destroy()
        messagebox.showinfo("Recovery Complete", f"Moved {moved_count} valid run(s).\nSkipped {skipped_count} invalid/incomplete run(s).")

    def recovery_delete_current(self, recovery_window) : 
        """
        Deletes everything inside current/ from the recovery popup
        """
        confirm = messagebox.askyesno("Confirm Delete", "Delete everything inside current folder?")

        if not confirm : 
            return
        wipe_folder_contents("current")

        self.update_status_loop()
        recovery_window.destroy()
        messagebox.showinfo("Deleted", "Everything inside current folder was deleted")


    def update_recovery_button_state(self) : 
        """
        Updates the recovery button enabled/disabled state
        """

        has_contents = current_folder_has_contents("current")

        if has_contents and not self.controller.is_running:  # Enabled, only can press when not actively running experiment
            self.recovery_button.config(state=tk.NORMAL) # Allow user to press
        else :  # Disabled
            self.recovery_button.config(state=tk.DISABLED)


    def refresh_organism_menu(self) : 
        organism_options = get_organism_options("training")

        menu = self.organism_menu["menu"]
        # Delete old entries
        menu.delete(0, "end")

        for organism in organism_options : 
            # Add to dropdown
            menu.add_command(label=organism, command=lambda value=organism: self.organism.set(value))

        if organism_options and self.organism.get() == "" : 
            # There are options an none selected
            self.organism.set(organism_options[0])

    
    


    def start_experiment(self) : 
        """
        Starts experiment
        """

        microorganism_type = self.organism.get().strip()
        if microorganism_type == "" : 
            # Error popup
            messagebox.showerror("Error", "No organism selected.")
            return 
        
        # Try to parse numeric input fields
        try : 
            camera_index = int(self.camera_index.get())
            duration_minutes = float(self.duration.get())
            interval_minutes = float(self.interval.get())

        except ValueError:
            messagebox.showerror("Error", "Camera, duration, and interval must be valid numbers.")
            return
        
        duration_seconds = duration_minutes * 60
        interval_seconds = interval_minutes * 60

        # Try to start experiment
        try: 
            run_id = self.controller.start_experiment(
                microorganism_type=microorganism_type,
                camera_index=camera_index,
                duration_seconds=duration_seconds,
                interval_seconds=interval_seconds,
                output_root="current"
            )

            # Update labels
            self.run_id.set(f"Run ID: {run_id}")
            self.status.set("Status: Running")
            self.error.set("Error: None")

        except RuntimeError as error : 
            messagebox.showerror("Error", str(error))


        
    def stop_experiment(self) : 
        # Tell controller to stop experiment
        self.controller.stop_experiment()
        self.stop_requested = True
        self.status.set("Status: Stop requested")


    def update_status_loop(self) : 
        if self.controller.is_running and not self.stop_requested : 
            self.status.set("Status: Running")
            self.start_button.config(state=tk.DISABLED) # Dont allow user to press
            self.stop_button.config(state=tk.NORMAL) # Allow user to press

        elif self.controller.is_running and self.stop_requested : 
            self.start_button.config(state=tk.DISABLED) # Dont allow user to press
            self.stop_button.config(state=tk.DISABLED) # Dont user to press
        
        else : 
            self.status.set("Status: Idle")
            self.start_button.config(state=tk.NORMAL) # Dont allow user to press
            self.stop_button.config(state=tk.DISABLED) # Allow user to press

        # Check for errors
        if self.controller.last_error is not None : 
            # Show last error
            self.error.set(f"Error: {self.controller.last_error}")

        # Check if experiment is done and has a run folder to move
        if not self.controller.is_running and self.controller.last_run_folder is not None : 
            move_run_to_training(self.controller.last_run_folder, training_folder="training")
            
            # Clear last_run_folder
            self.controller.last_run_folder = None

            self.refresh_organism_menu()

        self.update_recovery_button_state()

        # Schedule to run again after 500ms
        self.root.after(500, self.update_status_loop)


    def run(self) : 
        self.root.mainloop()