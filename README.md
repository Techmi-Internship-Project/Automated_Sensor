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

In collaborative mode, a partner machine running a biomass/CFU/mL/current stage prediction model reads the run folder from shared Google Drive, classifies the growth stage, and communicates the estimated growth stage, biomass, and CFU/mL back through a shared `comms.json` file.

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
├── media_menu.py              # Media type option discovery/persistence (app_settings.json)
│
├── gui_app.py                 # SensorGUI class — owns root window and shared state
├── gui_layout.py              # Top bar, sidebar, content area construction
├── gui_backend_actions.py     # Button handlers, status poll loop, CSV upload
├── gui_camera_panel.py        # Camera preview, exposure sliders, ROI overlay
├── gui_recovery_settings.py   # Recovery panel, health checks, settings window, biomass graph
├── gui_run_status_panel.py    # Live status card, progress bar, log panel
├── gui_setup_panel.py         # Organism, media type, and camera selection
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
│           ├── run.json          # Run metadata (organism, media type, duration, interval, camera)
│           ├── comms.json        # Two-machine handshake and live ML data (collaborative mode)
│           ├── DONE.json         # Written on clean finish (see fields below)
│           ├── run.log           # GUI log for this run
│           ├── sensor_data.csv   # Uploaded by user at end of run (collaborative mode, required)
│           ├── tcd_data.csv      # Uploaded by user at end of run (collaborative mode, optional — Hamilton TCD export)
│           └── *.jpg             # Captured processed images
│
└── training/
    └── organism_name/
        └── run_TIMESTAMP/        # Moved here after successful run completes, same format at current/
```

The `current/organism_name/` folder itself is also removed once its run folder is
moved out, so `current/` is left empty again after each run finishes.

`DONE.json` fields:

| Field | Description |
|---|---|
| `run_id`, `capture_count`, `reason`, `finished_at` | Standard completion metadata |
| `had_errors` | `true` if any capture or hardware fault occurred during the run |
| `failed_capture_count` | Total number of failed capture attempts (lifetime, not just consecutive) |
| `failure_reasons` | List of distinct failure messages seen during the run |
| `degraded_at_finish` | `true` if the run was still in a degraded (faulted) state at the moment it completed |

A run with `had_errors: true` still finishes and moves to `training/` normally —
see [Resilience & Never-Abort Behavior](#resilience--never-abort-behavior) below.

---

## Settings

Settings are stored in `app_settings.json` in the project directory.

| Key | Type | Default | Description |
|---|---|---|---|
| `data_root` | string | (set on first run) | Absolute path to the experiment data root folder |
| `standalone_mode` | bool | `true` | When true, skips all collaborative handshake logic |
| `retrain_model` | bool | `false` | When true, prompts for CSV upload and waits for ML retraining after each run |
| `handshake_timeout_hours` | float | `1.0` | How long to wait for partner machine responses before timing out. Supports decimals (e.g. `0.1` = 6 minutes) |
| `known_media_types` | list of strings | `[]` | Media types previously entered via "Create New Media Type", offered again in the Setup panel dropdown. Unlike organisms, media types have no folder of their own — this list is their only persistence |

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

- (`status_lock`): Locked status dict where the experiment thread writes its current state (elapsed time, capture count, last message, degraded state). All GUI updates from the background thread go through `status_callback` -> `update_status()` -> status dict -> 200ms poll loop.

- Status messages are also pushed onto an internal queue (`drain_log_queue()`) rather than a single overwritable field, so a fast burst of distinct log lines can't silently drop intermediate messages between poll ticks.

- (`threading.Event`):  one-way signals from the GUI to the experiment thread. (`stop_event`, `hardware_error_event`, `csv_ready_event`, `end_after_current_capture_event`)
Duration lock — lets the user adjust run time mid-experiment without the two threads reading a half-written value.

- Camera preview open (`gui_camera_panel.py`) also runs on a background daemon thread rather than the main GUI thread — a hung/slow camera driver no longer freezes the whole application window. The main thread is notified via `root.after(0, ...)` once the open completes (or fails).

- Windows sleep is suppressed for the duration of a run via `SetThreadExecutionState` (ctypes call to the Windows API), so the OS won't sleep the machine mid-experiment.

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
GUI prompts user for Sensor Data CSV (required) and TCD Data CSV (optional)
user uploads CSV(s) → copied to run folder as sensor_data.csv / tcd_data.csv
                                        read sensor_data.csv (+ tcd_data.csv if present)
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
| `current_cfu_ml` | ML machine | Estimated CFU/mL value for live graph. Shown alongside biomass in the Recovery panel; a toggle switches which of the two drives the trend graph, since the two live on very different scales |
| `end_alert` | ML machine | True if organism has been in stationary/death stage for consecutive reads. When it flips true, the Recovery panel raises a one-time GUI warning to consider ending the run. |
| `first_run` | ML machine | ML-internal flag: set true when the ML has no usable training data yet. Written by the sensor as `false` and not otherwise read on the sensor side. |

> Note: `automated_run` is read by the ML machine (defaulting to automated when absent) but is **not** currently written by the sensor — automated mode is the only supported mode until the sensor-side setting is implemented.

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

**Missing-marker inference:** if exactly one of the four markers can't be detected in a given frame (e.g. blocked by condensation or a cable), its corner is inferred geometrically from the other three using the parallelogram relationship of the ROI rectangle (`top_left + bottom_right == top_right + bottom_left`). The status/log line notes when a corner was inferred rather than directly detected. If two or more markers are missing, ROI detection fails as before.

**Startup ROI retry:** at the start of a run, if the ROI can't be found on the first attempt, the system retries up to 3 times with a 5 second delay between attempts before treating it as a fatal setup error.

---

## Resilience & Never-Abort Behavior

Once a run has captured at least one image, it will not abort due to a hardware
or storage fault — it keeps retrying captures at the scheduled interval for the
remaining duration and always finishes and saves normally, even with gaps.
(Before the first successful capture, a bad camera/relay connection or ROI
failure still fails fast, since there's no data yet to preserve and it's more
likely a setup problem.)

- **Persistent degraded banner:** when a fault occurs mid-run (camera lost,
  laser relay disconnected, storage unreachable, repeated capture/save
  failures), a red banner appears in the Live Status card describing the
  problem and stays visible until it clears or the run ends — unlike the
  regular one-line status message, which gets overwritten by the next routine
  update.
- **Self-healing:** if the underlying fault clears (e.g. the drive
  reconnects, the camera reopens successfully), the next successful capture
  automatically clears the banner and resumes normal logging.
- **Missed images are logged, not silent:** a failed capture (unreadable ROI,
  camera error, failed save, etc.) writes a clear fail message to `run.log`
  and the GUI status, then moves on to the next scheduled capture instead of
  stopping.
- **Recorded in `DONE.json`:** `had_errors`, `failed_capture_count`,
  `failure_reasons`, and `degraded_at_finish` let you tell a run with gaps
  apart from a clean one after the fact without digging through `run.log`
  (see [Data Folder Structure](#data-folder-structure)).
- **Bounded storage retry:** transient storage-health-check failures (e.g. a
  momentary drive hiccup) tolerate up to 3 consecutive failures before being
  treated as a real disconnect, rather than flagging on the very first miss.

---

## Known Issues / TODOs

- `camera_index=0` is hardcoded in `write_run_metadata` — the selected camera index is not written to `run.json`
- `create_debug_image` in `aruco.py` is not called in production — kept for development use only
- Different computers have differing camera enumeration that does not behave nicely with OpenCV. Development computer had correct behavior, while other computers may show a reversed order. As of now this is fixed by using the identify cameras button. The main issue was OpenCV only returning an index with no hardware identifier when it finds cameras.
- On long runs (exceeding 9 hours) Windows MSMF can still close the opened camera unexpectedly (cause not identified — happens at random times or not at all). This no longer fails the run: the camera is reopened automatically, and if reopening also fails the run enters a degraded state and keeps retrying rather than aborting — see [Resilience & Never-Abort Behavior](#resilience--never-abort-behavior).

**Fixed this session** (kept here briefly for reference, remove once stable in the field):
- Camera preview used to run synchronously on the main GUI thread — a hung camera driver froze the whole window. Preview open now runs on a background thread.
- A `shutil.rmtree(..., onexc=...)` call only worked on Python 3.12+; on other Python versions it raised immediately and left the microorganism folder behind in `current/` after a run finished. Switched to the universally-compatible `onerror` parameter.
- The GUI status log polled a single overwritable "last message" field every 200ms, which could silently drop fast-succession messages and occasionally show a stale message color. Replaced with a proper message queue.
- Clicking "Stop" zeroed out the progress bar/elapsed time/capture ratio instantly regardless of actual progress. Fixed to preserve true progress on stop.

---

## Author

Cade Medearis — Embedded Systems & Computer Vision Engineering Intern  
TECHMI Group, Valencia, Spain
