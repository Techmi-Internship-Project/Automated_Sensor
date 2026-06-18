import tkinter as tk
from tkinter import messagebox
import cv2 as cv
from PIL import Image, ImageTk # So OpenCV frames can be shown inside Tkinter
import time

from camera import open_camera, set_normal_exposure
from aruco import detect_aruco_markers, get_roi_corners
from laser_control import LaserRelay

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
        self.window.geometry("800x600")

        # Actively running?
        self.running = True

        # Store latest Tkinter image so it does not get garbage collected
        self.current_tk_image = None
        self.cap = None
        self.laser = None
        self.laser_is_on = False # For toggling

        # Default testing labels
        self.marker_status = tk.StringVar(value="Markers: Not checked yet")
        self.roi_status = tk.StringVar(value="ROI: Not checked yet")
        self.laser_status = tk.StringVar(value="Idle")

        self.build_widgets()
        self.open_selected_camera()

        self.open_laser_relay()
        
        # Tell Tkinter what to do when the window is closed
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        # Start updating live feed
        self.update_video_loop()

    def build_widgets(self) :
        title_label = tk.Label(self.window, text="Camera Setup", font=("Arial", 16))
        title_label.pack(pady=10)

        # Live feed
        self.video_label = tk.Label(self.window)
        self.video_label.pack(pady=10)

        # Marker Status
        marker_label = tk.Label(self.window, textvariable=self.marker_status)
        marker_label.pack(pady=3)

        # ROI Status
        roi_label = tk.Label(self.window, textvariable=self.roi_status)
        roi_label.pack(pady=3)

        # Laser Status
        laser_label = tk.Label(self.window, textvariable=self.laser_status)
        laser_label.pack(pady=3)

        # Setup buttons frame
        button_frame = tk.Frame(self.window)
        button_frame.pack(pady=10)

        # Laser test button
        self.test_laser_button = tk.Button(button_frame, text="Toggle Laser", command=self.toggle_laser)
        self.test_laser_button.pack(side=tk.LEFT, padx=10)

        # Close button
        close_button = tk.Button(button_frame, text="Close", command=self.close)
        close_button.pack(side=tk.LEFT, padx=10)


    def open_selected_camera(self) : 
        self.cap = open_camera(self.camera_index)

        if self.cap is None or not self.cap.isOpened() :
            messagebox.showerror("Camera Error", f"Could not open camera index {self.camera_index}.")
            self.close()

            return
        
        set_normal_exposure(self.cap)

    def open_laser_relay(self) : 
        try : 
            if self.laser is None :
                self.laser = LaserRelay()
                self.laser.open()
                self.laser.off()
                self.laser_is_on = False
                self.laser_status.set("Laser: OFF")

        except RuntimeError as error : 
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
        rgb_frame = self.resize_frame_for_display(rgb_frame, max_width=600, max_height=375)

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

            except RuntimeError: 
                pass # Ignore cleanup errors while closing

            self.laser = None
        
        self.laser_is_on = False
        self.laser_status.set("Laser: OFF")



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