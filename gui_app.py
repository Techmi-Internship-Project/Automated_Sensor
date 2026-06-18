import tkinter as tk
from tkinter import messagebox, simpledialog
import re

from pathlib import Path

from experiment_controller import ExperimentController
from startup_recovery import move_valid_runs_to_training, current_folder_has_contents, wipe_folder_contents, move_run_to_training
from organism_menu import get_organism_options


def format_elapsed(seconds) : 
        """
        Easy to read time format
        """
        seconds = int(seconds)
        if seconds < 60 : 
            return f"{seconds}s"
        elif seconds < 3600 : # Minutes only but not hours 
            minutes, secs = divmod(seconds, 60)
            return f"{minutes}m {secs}s"
        else : 
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            return f"{hours}h {minutes}m {secs}s"
class SensorGUI : 
    """
    Class for the GUI
    """
    def __init__(self, current_folder, training_folder):
        self.root = tk.Tk() # Create main Tkinter window
        self.root.title("Bioreactor Sensor")
        self.root.geometry("600x500")

        self.controller = ExperimentController()

        self.current_folder = current_folder
        self.training_folder = training_folder

        # If path doesn't exist here
        self.current_folder.mkdir(parents=True, exist_ok=True)
        self.training_folder.mkdir(parents=True, exist_ok=True)

        self.organism = tk.StringVar()
        self.camera_index = tk.StringVar(value="0")

        #Both in minutes
        self.duration = tk.StringVar(value="0.5")
        self.interval = tk.StringVar(value="0.1")

        self.status = tk.StringVar(value="Status: Idle")
        self.run_id = tk.StringVar(value="Run ID: None")
        self.error = tk.StringVar(value="Error: None")
        
        self.elapsed = tk.StringVar(value="Elasped: 0s")
        self.capture_count = tk.StringVar(value="Captures: 0")
        self.run_folder = tk.StringVar(value="Run folder: None")
        self.last_saved_image = tk.StringVar(value="Last image: None")
        self.last_message = tk.StringVar(value="Message: Idle")

        self.last_seen_alert_id = 0 # To avoid continuous popups
        self.alert_popup_open = False

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

        self.organism_options = get_organism_options(self.training_folder)
        # Dropdown
        if self.organism_options : 
            self.organism.set(self.organism_options[0])
            self.organism_menu = tk.OptionMenu(organism_frame, self.organism, *self.organism_options)
        else :
            # Set to empty string
            self.organism.set("")
            self.organism_menu = tk.OptionMenu(organism_frame, self.organism, "")


        self.organism_menu.pack(side=tk.LEFT)

        # Create new organism
        self.create_organism_button = tk.Button(organism_frame, text="Create New", command=self.create_new_organism)
        self.create_organism_button.pack(side=tk.LEFT, padx=5)

        # Camera
        camera_frame = tk.Frame(self.root)
        camera_frame.pack(pady=5)

        camera_label = tk.Label(camera_frame, text="Camera Index:")
        camera_label.pack(side=tk.LEFT)
        self.camera_entry = tk.Entry(camera_frame, textvariable=self.camera_index, width=10)
        self.camera_entry.pack(side=tk.LEFT)

        # Duration
        duration_frame = tk.Frame(self.root)
        duration_frame.pack(pady=5)
        duration_label = tk.Label(duration_frame, text="Duration minutes: ")
        duration_label.pack(side=tk.LEFT)
        self.duration_entry = tk.Entry(duration_frame, textvariable=self.duration, width=10)
        self.duration_entry.pack(side=tk.LEFT)

        # Interval
        interval_frame = tk.Frame(self.root)
        interval_frame.pack(pady=5)
        interval_label = tk.Label(interval_frame, text="Interval minutes:")
        interval_label.pack(side=tk.LEFT)
        self.interval_entry = tk.Entry(interval_frame, textvariable=self.interval, width=10)
        self.interval_entry.pack(side=tk.LEFT)

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

        # Elasped time
        elapsed_label = tk.Label(self.root, textvariable=self.elapsed)
        elapsed_label.pack(pady=3)

        # Capture count
        capture_count_label = tk.Label(self.root, textvariable=self.capture_count)
        capture_count_label.pack(pady=3)



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
        
        organism_path = Path(self.training_folder) / organism_name
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
        if not current_folder_has_contents(self.current_folder) : 
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
        moved_count, skipped_count = move_valid_runs_to_training(current_folder=self.current_folder, training_folder=self.training_folder)

        self.refresh_organism_menu()
        self.update_recovery_button_state()
        recovery_window.destroy()
        messagebox.showinfo("Recovery Complete", f"Moved {moved_count} valid run(s).\nSkipped {skipped_count} invalid/incomplete run(s).")
        wipe_folder_contents(self.current_folder)

    def recovery_delete_current(self, recovery_window) : 
        """
        Deletes everything inside current/ from the recovery popup
        """
        confirm = messagebox.askyesno("Confirm Delete", "Delete everything inside current folder?")

        if not confirm : 
            return
        wipe_folder_contents(self.current_folder)

        self.update_status_loop()
        recovery_window.destroy()
        messagebox.showinfo("Deleted", "Everything inside current folder was deleted")


    def update_recovery_button_state(self) : 
        """
        Updates the recovery button enabled/disabled state
        """

        has_contents = current_folder_has_contents(self.current_folder)

        if has_contents and not self.controller.is_running:  # Enabled, only can press when not actively running experiment
            self.recovery_button.config(state=tk.NORMAL) # Allow user to press
        else :  # Disabled
            self.recovery_button.config(state=tk.DISABLED)


    def refresh_organism_menu(self) : 
        organism_options = get_organism_options(self.training_folder)

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
                output_root=self.current_folder
            )

            # Update labels
            self.run_id.set(f"Run ID: {run_id}")
            self.status.set("Status: Running")
            self.error.set("Error: None")
            self.last_seen_alert_id = 0
            self.alert_popup_open = False

            # Update controls immediately after starting experiment
            self.update_control_states()

        except RuntimeError as error : 
            messagebox.showerror("Error", str(error))


        
    def stop_experiment(self) : 
        # Tell controller to stop experiment
        self.controller.stop_experiment()
        self.stop_requested = True
        self.status.set("Status: Stop requested")


    def update_status_loop(self) : 

        status = self.controller.get_status()
        elapsed_seconds = status.get("elapsed_seconds", 0.0)
        capture_count = status.get("capture_count", 0)
        run_folder = status.get("run_folder", None)
        last_saved_image = status.get("last_saved_image", None)
        last_message = status.get("last_message", "Idle")


        capture_error = status.get("last_error", None)
        last_capture_result = status.get("last_capture_result", "None")

        alert_message = status.get("alert_message", None)
        alert_id = status.get("alert_id", 0)

        new_alert_exists = alert_message is not None and alert_id != self.last_seen_alert_id

        # Check if alert popup is open
        popup_is_available = not self.alert_popup_open

        if new_alert_exists and popup_is_available : 
            self.last_seen_alert_id = alert_id
            self.alert_popup_open = True

            try : 
                messagebox.showwarning("Capture Warning", alert_message)

            finally : 
                self.alert_popup_open = False

        # Check for errors
        if self.controller.last_error is not None : 
            # Show last error
            self.error.set(f"Error: {self.controller.last_error}")

        # Check if experiment is done and has a run folder to move
        if not self.controller.is_running and self.controller.last_run_folder is not None : 
            move_run_to_training(self.controller.last_run_folder, training_folder=self.training_folder, current_folder=self.current_folder)
            
            # Clear last_run_folder
            self.controller.last_run_folder = None

            wipe_folder_contents(self.current_folder)

            self.refresh_organism_menu()


        # Update button and input states based on whether experiment is running
        self.update_control_states()

        self.elapsed.set(f"Elapsed: {format_elapsed(elapsed_seconds)}")
        self.capture_count.set(f"Captures: {capture_count}")
        
        if run_folder is not None : 
            self.run_folder.set(f"Run folder: {run_folder}")
        else : 
            self.run_folder.set("Run folder: None")

        if last_saved_image is not None : 
            self.last_saved_image.set(f"Last image: {last_saved_image}")
        else : 
            self.last_saved_image.set("Last image: None")

        self.last_message.set(f"Message: {last_message}")

        # Schedule to run again after 500ms
        self.root.after(500, self.update_status_loop)

    def update_control_states(self) : 
        """
        Enables or disables controls based on experiment status
        """
        if self.controller.is_running and not self.stop_requested : 
            self.status.set("Status: Running")
            self.start_button.config(state=tk.DISABLED) # Dont allow user to press
            self.stop_button.config(state=tk.NORMAL) # Allow user to press
            
            self.organism_menu.config(state=tk.DISABLED)
            self.camera_entry.config(state=tk.DISABLED)
            self.create_organism_button.config(state=tk.DISABLED)
            self.interval_entry.config(state=tk.DISABLED)
            self.recovery_button.config(state=tk.DISABLED)
            self.duration_entry.config(state=tk.DISABLED)

        elif self.controller.is_running and self.stop_requested : 
            self.start_button.config(state=tk.DISABLED) # Dont allow user to press
            self.stop_button.config(state=tk.DISABLED) # Dont user to press
            self.organism_menu.config(state=tk.DISABLED)
            self.camera_entry.config(state=tk.DISABLED)
            self.create_organism_button.config(state=tk.DISABLED)
            self.interval_entry.config(state=tk.DISABLED)
            self.recovery_button.config(state=tk.DISABLED)
            self.duration_entry.config(state=tk.DISABLED)


        else : 
            self.stop_requested = False
            self.status.set("Status: Idle")
            self.start_button.config(state=tk.NORMAL) # Dont allow user to press
            self.stop_button.config(state=tk.DISABLED) # Allow user to press

            self.organism_menu.config(state=tk.NORMAL)
            self.camera_entry.config(state=tk.NORMAL)
            self.create_organism_button.config(state=tk.NORMAL)
            self.interval_entry.config(state=tk.NORMAL)
            self.recovery_button.config(state=tk.NORMAL)
            self.duration_entry.config(state=tk.NORMAL)


            self.update_recovery_button_state()



    def run(self) : 
        self.root.mainloop()

    