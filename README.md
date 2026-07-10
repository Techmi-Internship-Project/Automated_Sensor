# TECHMI Bioreactor Sensor Control Panel

Automated bioreactor monitoring system for measuring microorganism growth via laser illumination imaging for machine learning applications. Built during an embedded systems engineering internship at TECHMI Group, Valencia, Spain.

---

## Overview

The system captures time-series images of a bioreactor culture through a laser imaging pipeline. Four ArUco markers define a region of interest (ROI) around the bioreactor vessel. At each capture interval, the system:

1. Captures a laser-off calibration image at normal exposure to detect the ArUco markers and computes a perspective-corrected ROI
2. Captures a laser-off background image at low exposure
3. Captures a laser-on measurement image at the same exposure
4. Aligns the images and subtracts the background to isolate the laser signal
5. Saves the processed image to the run folder

In collaborative mode, a partner machine running a biomass/current stage prediction model reads the run folder from shared Google Drive, classifies the growth stage, and communicates estimated biomass and growth stage back through a shared `comms.json` file.

---

## System Requirements

- **OS:** Windows 10/11 (required for MSMF camera backend and WMI device enumeration)
- **Python:** 3.12+
- **Camera:** USB camera compatible with Windows MSMF. Auto-exposure, auto-white-balance, and auto-focus must be disabled manually using Webcam Configuration Tool or similar software before running.
- **Laser relay:** Silicon Labs CP210x USB-to-UART relay module (controlled via AT commands at 9600 baud)
- **Storage:** Shared Google Drive folder (recommended) or local path. If computer has enough power, both this control panel and the ML can be ran locally on the same computer for faster communication.

---

## Dependencies

Install with pip:

```
pip install opencv-contrib-python pillow pyserial matplotlib
```

| Package | Purpose |
|---|---|
| `opencv-contrib-python` | Camera capture, ArUco detection, image processing |
| `pillow` | Displaying OpenCV frames in Tkinter |
| `pyserial` | USB relay serial communication |
| `matplotlib` | Live biomass graph in Recovery panel |

---

## Installation & First Run

1. Clone or extract the project folder
2. Install dependencies (see above)
3. Run `main.py`:

```
python main.py
```

On first launch, a setup dialog will prompt you to select a data root folder. This is the top-level directory where all experiment data is stored — typically your shared Google Drive folder. This path is saved to `app_settings.json` and does not need to be set again.

---

## File Structure

```
project/
│
├── main.py                    # Entry point — DPI setup, first-run setup, launch
├── config.py                  # Settings loading/saving, shared constants
│
├── experiment.py              # Core experiment loop (runs in background thread)
├── experiment_controller.py   # Thread management, event signaling, status dict
├── measurement_capture.py     # Single capture sequence (ROI → laser → subtract)
│
├── aruco.py                   # ArUco marker detection and ROI homography
├── camera.py                  # Camera open, exposure profiles, frame grab
├── camera_settings.py         # Load/save camera profiles from camera_settings.json
├── camera_tools.py            # WMI device enumeration, MSMF index scanning
├── image_processing.py        # Background subtraction, filename generation
├── laser_control.py           # LaserRelay class — serial AT commands
│
├── run_metadata.py            # Write run.json, DONE.json, comms.json
├── startup_recovery.py        # Find, classify, move, and wipe run folders
├── organism_menu.py           # Organism folder discovery
│
├── gui_app.py                 # SensorGUI class — owns root window and shared state
├── gui_layout.py              # Top bar, sidebar, content area construction
├── gui_backend_actions.py     # Button handlers, status poll loop, CSV upload
├── gui_camera_panel.py        # Camera preview, exposure sliders, ROI overlay
├── gui_recovery_settings.py   # Recovery panel, health checks, settings window, biomass graph
├── gui_run_status_panel.py    # Live status card, progress bar, log panel
├── gui_setup_panel.py         # Organism and camera selection
├── gui_timing_panel.py        # Duration/interval inputs and presets
├── gui_theme.py               # Colors, fonts, shared widget factories
│
├── app_settings.json          # Persisted user settings (created on first run)
└── camera_settings.json       # Camera exposure profiles (normal / low)
```

---

## Data Folder Structure

All experiment data lives under the configured data root:

```
data_root/
├── current/
│   └── organism_name/
│       └── run_TIMESTAMP/
│           ├── run.json          # Run metadata (organism, duration, interval, camera)
│           ├── comms.json        # Two-machine handshake and live ML data (collaborative mode)
│           ├── DONE.json         # Written on clean finish
│           ├── run.log           # GUI log for this run
│           ├── sensor_data.csv   # Uploaded by user at end of run (collaborative mode)
│           └── *.jpg             # Captured processed images
│
└── training/
    └── organism_name/
        └── run_TIMESTAMP/        # Moved here after successful run completes, same format at current/
```

---

## Settings

Settings are stored in `app_settings.json` in the project directory.

| Key | Type | Default | Description |
|---|---|---|---|
| `data_root` | string | (set on first run) | Absolute path to the experiment data root folder |
| `standalone_mode` | bool | `true` | When true, skips all collaborative handshake logic |
| `retrain_model` | bool | `false` | When true, prompts for CSV upload and waits for ML retraining after each run |
| `handshake_timeout_hours` | float | `1.0` | How long to wait for partner machine responses before timing out. Supports decimals (e.g. `0.1` = 6 minutes) |

Camera settings are stored separately in `camera_settings.json`:

| Profile | Purpose |
|---|---|
| `normal` | Higher exposure for ArUco marker detection |
| `low` | Low exposure for laser measurement captures |

Each profile has both exposure and gain settings saved. 

NOTE: As it says in the GUI, automatic camera settings need to be disabled manually, as OpenCV was unable to edit these settings through software. A software such as Webcam Configuration Tool is useful for this. For best results, disable auto-focus, auto-whitebalance, and auto-exposure.
---

## Threading Architecture

The app runs two threads simultaneously:

Main thread: runs the GUI. Tkinter requires that only this thread touches the UI, so it never does any hardware work. It polls for updates every 200ms.

Background thread: Daemon thread that runs the experiment, if window closes automatically dies. Camera captures, laser commands, and file writes all happen here. Managed by `ExperimentController`

Since two threads can't safely read and write the same data at the same time, they communicate through shared structures protected by locks:

- (`status_lock`): Locked status dict where the experiment thread writes its current state (elapsed time, capture count, last message). All GUI updates from the background thread go through `status_callback` -> `update_status()` -> status dict -> 200ms poll loop.

- (`threading.Event`):  one-way signals from the GUI to the experiment thread. (`stop_event`, `hardware_error_event`, `csv_ready_event`, `end_after_current_capture_event`)
Duration lock — lets the user adjust run time mid-experiment without the two threads reading a half-written value.

---

## Collaborative Mode (Two-Machine Protocol)

When `standalone_mode` is false and `retrain_model` is true, the sensor machine and a partner ML machine communicate through `comms.json` in the shared Google Drive run folder.

### Handshake Flow

```
Sensor machine                          ML machine
──────────────────────────────────────────────────────
write comms.json (start_handshake: "sw")
                                        read comms.json
                                        write start_handshake: "ack"
read ack → begin capture loop
...captures run...
write DONE.json
send "awaiting_csv" status to GUI
GUI prompts user for sensor data CSV
user uploads CSV → copied to run folder
                                        read sensor_data.csv
                                        retrain model (or skip if retrain_model: false)
                                        write ml_done: true
read ml_done: true
move run folder to training/
```

### `comms.json` Fields

| Field | Writer | Description |
|---|---|---|
| `start_handshake` | Sensor (`"sw"`) → ML (`"ack"`) | Handshake sequence at run start |
| `ml_done` | ML machine | Set to `true` when ML is finished (retrain or skip ack) |
| `retrain_model` | Sensor machine | Whether the ML machine should retrain after this run |
| `current_state` | ML machine | Current growth stage (e.g. `"lag"`, `"exponential"`) |
| `current_biomass` | ML machine | Estimated biomass value for live graph |
| `end_alert` | ML machine | True if organism has been in stationary/death stage for consecutive reads |

---

## Camera Setup

Before running an experiment:

1. Open **Settings → Identify Cameras** to confirm which camera index maps to your bioreactor camera
2. Open the **Camera Preview** in the main window and verify ArUco markers are detected (green ROI overlay should appear)
3. Verify the laser fires correctly using the **Laser: OFF** toggle in the preview bar
4. Check **System Health** — Camera, Laser Module, and Storage should all show Nominal

**Important:** Auto-exposure, auto-white-balance, and auto-focus must be disabled on the camera before running. Use Webcam Configuration Tool or a similar utility. If these are left on, the exposure profiles will not behave reliably.

---

## ArUco Marker Layout

Four DICT_4X4_50 markers define the ROI. The inside corner of each marker is used as the ROI boundary point:

```
ID 0 ──────────────── ID 1
 │                      │
 │         ROI          │
 │                      │
ID 3 ──────────────── ID 2
```

The markers must be printed and placed flat around the bioreactor vessel before starting a run. Marker IDs must be exactly 0, 1, 2, 3 in the positions shown above.

---

## Known Issues / TODOs

- `camera_index=0` is hardcoded in `write_run_metadata` — the selected camera index is not written to `run.json`
- Camera preview runs on the main GUI thread rather than a dedicated thread. This causes performance issues especially with slower USB cameras. Should be moved to a daemon thread
- `create_debug_image` in `aruco.py` is not called in production — kept for development use only
- Different computers have differing camera enumeration that does not behave nicely with OpenCV. Development computer had correct behavior, while other computers may show a reversed order. As of now this is fixed by using the identify cameras button. The main issue was OpenCV only returning an index with no hardware identifier when it finds cameras.
- On long runs (Exceeding 9 hours) Windows MSMF will close the opened camera causing the experiment to fail. Haven't found a cause, it happens at random times or not at all. 


---

## Author

Cade Medearis — Embedded Systems & Computer Vision Engineering Intern  
TECHMI Group, Valencia, Spain
