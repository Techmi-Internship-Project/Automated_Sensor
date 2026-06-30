import tkinter as tk
from tkinter import messagebox
import cv2 as cv
from PIL import Image, ImageTk # So OpenCV frames can be shown inside Tkinter
import time

from camera import open_camera, set_normal_exposure, set_low_exposure
from aruco import detect_aruco_markers, get_roi_corners
from laser_control import LaserRelay
from camera_settings import AUTO_CONTROL_WARNING, get_camera_profile, save_camera_profile, apply_camera_profile

class CameraSetupWindow :
    """
    Class for the camera setup, complete with live feed and laser testing
    """

    def __init__(self, parent, camera_index, on_close=None) :
        
        # Parent Tkinter window
        self.parent = parent
        self.camera_index = camera_index

        # Function to run when this window closes
        self.on_close = on_close

        
        # Create the popup window
        self.window = tk.Toplevel(self.parent)
        self.window.title("Camera Setup")
        self.window.geometry("850x600")

        # Actively running?
        self.running = True

        # Store latest Tkinter image so it does not get garbage collected
        self.current_tk_image = None
        self.cap = None
        self.laser = None
        self.laser_is_on = False # For toggling

        # Camera settings
        self.current_profile = tk.StringVar(value="normal")
        self.exposure_value = tk.IntVar(value=0)
        self.gain_value = tk.IntVar(value=0)
        # Sliders are currently being loaded in from file
        self.loading_sliders = False
        self.settings_status = tk.StringVar(value="Settings: Loaded normal profile")

        # Default testing labels
        self.marker_status = tk.StringVar(value="Markers: Not checked yet")
        self.roi_status = tk.StringVar(value="ROI: Not checked yet")
        self.laser_status = tk.StringVar(value="Idle")

        
        # Tell Tkinter what to do when the window is closed
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.build_widgets()

        camera_opened = self.open_selected_camera()
        
        if not camera_opened : 
            # Camera error, leave safely
            self.abort_setup_window() 
            return # Stop __init__ 

        self.current_profile.set("normal")
        # Load json file into sliders
        self.load_profile_into_sliders("normal")
        self.apply_slider_settings_to_camera()

        self.open_laser_relay()
        
        
        # Start updating live feed
        self.update_video_loop()

    def build_widgets(self) :
        title_label = tk.Label(self.window, text="Camera Setup", font=("Arial", 16))
        title_label.pack(pady=10)

        main_frame = tk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        left_frame = tk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,10))

        right_frame = tk.Frame(main_frame, width=340)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        right_frame.pack_propagate(False) # So right frame does not shrink around children
        
        # Warning
        warning_label = tk.Label(right_frame, text=AUTO_CONTROL_WARNING, wraplength=320, justify=tk.LEFT, fg="RED")
        warning_label.pack(fill=tk.X, pady=(0,8))
        
        # Camera profile
        profile_frame = tk.Frame(right_frame)
        profile_frame.pack(fill=tk.X, pady=5)
        normal_button = tk.Radiobutton(profile_frame, text="Normal Exposure", variable=self.current_profile, value="normal", command=self.switch_camera_profile)
        normal_button.pack(side=tk.LEFT, padx=5)
        low_button = tk.Radiobutton(profile_frame, text="Low Exposure", variable=self.current_profile, value="low", command=self.switch_camera_profile)
        low_button.pack(side=tk.RIGHT, padx=5)

        # Live feed
        self.video_label = tk.Label(left_frame)
        self.video_label.pack(pady=10)

        # Marker Status
        marker_label = tk.Label(left_frame, textvariable=self.marker_status)
        marker_label.pack(pady=3)

        # ROI Status
        roi_label = tk.Label(left_frame, textvariable=self.roi_status)
        roi_label.pack(pady=3)

        # Settings Sliders
        settings_frame = tk.Frame(right_frame)
        settings_frame.pack(fill=tk.X, pady=8)

        self.exposure_slider = tk.Scale (
            settings_frame,
            from_=-13,
            to=0,
            resolution=1,
            orient=tk.HORIZONTAL,
            label="Exposure",
            variable=self.exposure_value,
            command=self.on_slider_change,
            length=240
        )
        self.exposure_slider.pack(fill=tk.X, pady=3)
        
        self.gain_slider = tk.Scale (
            settings_frame,
            from_=-0,
            to=255,
            resolution=1,
            orient=tk.HORIZONTAL,
            label="Gain",
            variable=self.gain_value,
            command=self.on_slider_change,
            length=240
        )
        self.gain_slider.pack(fill=tk.X, pady=3)
        
        settings_status_label = tk.Label(right_frame, textvariable=self.settings_status, wraplength=310, justify=tk.LEFT)
        settings_status_label.pack(fill=tk.X, pady=5)

        # Laser Status
        laser_label = tk.Label(right_frame, textvariable=self.laser_status)
        laser_label.pack(fill=tk.X, pady=5)

        # Setup buttons frame
        button_frame = tk.Frame(right_frame)
        button_frame.pack(fill=tk.X, pady=8)

        # Small save/reset frame
        save_reset_frame = tk.Frame(button_frame)
        save_reset_frame.pack(fill=tk.X, pady=3)

        # Save profile button
        save_button = tk.Button(save_reset_frame, text="Save Profile", command=self.save_current_profile)
        save_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        # Reset profile button
        reset_button = tk.Button(save_reset_frame, text="Reset Camera", command=self.reset_current_profile)
        reset_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        # Laser test button
        self.test_laser_button = tk.Button(button_frame, text="Toggle Laser", command=self.toggle_laser)
        self.test_laser_button.pack(fill=tk.X, pady=3)

        # Close button
        close_button = tk.Button(button_frame, text="Close", command=self.close)
        close_button.pack(fill=tk.X, pady=3)


    def open_selected_camera(self) : 

        self.cap = open_camera(self.camera_index)

        if self.cap is None or not self.cap.isOpened() :
            messagebox.showerror("Camera Error", f"Could not open camera index {self.camera_index}.")
            return False

        return True # Opened successfully
        
        set_normal_exposure(self.cap)

    def open_laser_relay(self) : 
        try : 
            if self.laser is None :
                self.laser = LaserRelay()
                self.laser.open()
                self.laser.off()
                self.laser_is_on = False
                self.laser_status.set("Laser: OFF")

        except Exception as error : 
            self.laser = None
            self.laser_is_on = False
            self.laser_status.set("Laser: Not connected")

            messagebox.showerror("Laser Error", str(error))
        
    def update_video_loop(self) : 
        """
        Updates the live video feed
        """
        # Check if setup window has stopped running
        if not self.running : 
            return # Stop updating frames
        
        # Check if camera object does not exist
        if self.cap is None : 
            # Schedule another attempt later
            self.window.after(100, self.update_video_loop)
            return 
        
        # Read a frame
        success, frame = self.cap.read()

        if not success or frame is None : 
            self.marker_status.set("Markers: Camera frame failed")
            self.window.after(100, self.update_video_loop)
            return
        
        display_frame = frame.copy()

        # Analyze frame for markers
        self.update_aruco_overlay(display_frame)

        rgb_frame = cv.cvtColor(display_frame, cv.COLOR_BGR2RGB)
        rgb_frame = self.resize_frame_for_display(rgb_frame, max_width=540, max_height=340)

        # Use pillow to display in Tkinter
        pillow_image = Image.fromarray(rgb_frame)
        self.current_tk_image = ImageTk.PhotoImage(image=pillow_image)

        # Show image in video label
        self.video_label.config(image=self.current_tk_image)

        self.window.after(30, self.update_video_loop)

    def update_aruco_overlay(self, display_frame) : 
        """
        Draws ArUco and ROI debugging info on the feed
        """
        corners, ids = detect_aruco_markers(display_frame)

        if ids is None :
            marker_count = 0
        else : 
            marker_count = len(ids)

        # Update marker label
        self.marker_status.set(f"Markers: {marker_count} detected")

        # Check if marker corners exist and at least one marker detected
        if corners is not None and ids is not None : 
            # Draw outlines of markers
            cv.aruco.drawDetectedMarkers(display_frame, corners, ids)

        roi_corners = get_roi_corners(corners, ids)

        if roi_corners is not None : 
            # Convert corners to pixel coordinates
            roi_points = roi_corners.astype(int)

            # Draw ROI outline on display frame
            cv.polylines(display_frame, [roi_points], isClosed=True, color=(0, 255, 0), thickness=3)

            self.roi_status.set("ROI: Found")

        else : 
            # ROI not able to be found 
            self.roi_status.set("ROI: Not found")


    def resize_frame_for_display(self, frame, max_width, max_height) : 
        """
        Resizes frame while preserving aspect ratio
        """

        height, width = frame.shape[:2]
        width_scale = max_width / width
        height_scale = max_height /  height

        # Use the smaller scale so frame fits inside both limits
        scale = min(width_scale, height_scale)

        # Calculate resized dimensions
        resized_width = int(width * scale)
        resized_height = int(height * scale)

        resized_frame = cv.resize(frame, (resized_width, resized_height))

        return resized_frame
    

    def load_profile_into_sliders(self, profile_name) : 
        """
        Loads a saved profile into the adjustable sliders
        """

        # Sliders are being loaded
        self.loading_sliders = True

        profile = get_camera_profile(profile_name)

        self.exposure_value.set(profile["exposure"])
        self.gain_value.set(profile["gain"])

        # Complete
        self.loading_sliders = False

    def get_profile_from_sliders(self) : 
        """
        Reads current slider values into a profile dictionary 
        """

        return {
            "exposure": int(self.exposure_value.get()),
            "gain": int(self.gain_value.get()),
        }
    
    def apply_slider_settings_to_camera(self) : 
        """
        Applies current slider values directly to opened camera
        """

        # Check if camera is available
        if self.cap is None :
            return 
        
        profile = self.get_profile_from_sliders()

        # Apply
        self.cap.set(cv.CAP_PROP_EXPOSURE, profile["exposure"])
        self.cap.set(cv.CAP_PROP_GAIN, profile["gain"])
    

    def on_slider_change(self, value) : 
        """
        Runs whenever a slider changes
        """
        if self.loading_sliders : 
            return # So file does not apply partial values
        
        self.apply_slider_settings_to_camera()
    
    def switch_camera_profile(self) : 
        """
        Switches between normal and low profiles
        """

        profile_name = self.current_profile.get()
        self.load_profile_into_sliders(profile_name)

        self.apply_slider_settings_to_camera()

    def save_current_profile(self) : 
        """
        Saves current slider values to selected profile
        """

        profile_name = self.current_profile.get()
        profile = self.get_profile_from_sliders()

        save_camera_profile(profile_name, profile)
        self.settings_status.set(f"Settings: Saved {profile_name} profile")


    def reset_current_profile(self) : 
        """
        Resets the current camera settings and sliders to what is in camera_settings.json
        """
        
        profile_name = self.current_profile.get()

        self.load_profile_into_sliders(profile_name)
        self.apply_slider_settings_to_camera()

        self.settings_status.set(f"Settings: Reloaded {profile_name} profile")

    def toggle_laser(self) : 
        """
        Toggles the USB relay on or off
        """

        try :
            # If laser hasn't been opened yet
            if self.laser is None : 
                self.open_laser_relay()

            if self.laser is None : # Failed despite guardrails 
                return

            # Check if laser is currently off
            if not self.laser_is_on : 
                self.laser.on()
                self.laser_is_on = True
                self.laser_status.set("Laser: ON")
            else :  # Laser is currently on
                self.laser.off()
                self.laser_is_on = False
                self.laser_status.set("Laser: OFF")

        except RuntimeError as error :
            # Should be treated as off after an error 
            self.laser_is_on = False
            self.laser_status.set("Laser: Error")
            messagebox.showerror("Laser Error", str(error))


    def shutdown_laser(self) : 
        """
        Safely turns laser off for safer close() function
        """
        if self.laser is not None : 
            try : 
                self.laser.off()
                time.sleep(0.2)
                self.laser.close()

            except Exception: 
                pass # Ignore cleanup errors while closing

            self.laser = None
        
        self.laser_is_on = False
        self.laser_status.set("Laser: OFF")

    def abort_setup_window(self) : 
        """
        Safely aborts setup window creation when startup fails
        """
        self.running = False

        # If somehow the laser is on
        if self.laser is not None : 
            try : 
                self.laser.off()
                self.laser.close()

            except Exception : 
                pass # Continue even if fail
            
            self.laser = None

        # If camera exists
        if self.cap is not None : 
            self.cap.release()
            self.cap = None

        # Tell main GUI that setup is not open
        if self.on_close is not None : 
            # Run close callback
            self.on_close()

        # Check if window still exists
        if self.window.winfo_exists() : 
            self.window.destroy()
        

    def close(self) : 
        """
        Safely closes the camera setup window
        """

        # Check if already stopping
        if not self.running :
            return
        
        self.running = False
        self.shutdown_laser()

        if self.cap is not None : 
            self.cap.release()
            self.cap = None

        # If on-close callback provided, do so
        if self.on_close is not None: 
            self.on_close()

        self.window.destroy()