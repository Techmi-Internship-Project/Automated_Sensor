from config import load_app_settings, save_app_settings


def prompt_data_root_if_needed(root):
    settings = load_app_settings()
    if settings.get("data_root"):
        return True

    from tkinter import filedialog, messagebox

    messagebox.showinfo(
        "First Time Setup",
        "Welcome to the TECHMI Bioreactor Sensor Control Panel.\n\n"
        "Please select a folder to store your experiment data.\n"
        "This is typically your shared Google Drive folder.",
        parent=root
    )

    chosen = filedialog.askdirectory(
        title="Select Data Root Folder",
        parent=root
    )

    if not chosen:
        root.destroy()
        return False

    settings["data_root"] = chosen
    save_app_settings(settings)
    return True


def main():
    import tkinter as tk
    import ctypes

    # Make app DPI aware so it is adaptive to different monitors
    try :
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # Per monitor DPI aware
    except Exception :
        try :
            ctypes.windll.user32.SetProcessDPIAware() # Fallback
        except Exception:
            pass

    root = tk.Tk()
    root.withdraw()  # hide until setup is done

    if not prompt_data_root_if_needed(root):
        return

    from pathlib import Path
    from gui_app import SensorGUI

    s = load_app_settings()
    data_root = Path(s["data_root"])
    current_folder = data_root / "current"
    training_folder = data_root / "training"
    current_folder.mkdir(parents=True, exist_ok=True)
    training_folder.mkdir(parents=True, exist_ok=True)

    app = SensorGUI(
        root=root,
        current_folder=current_folder,
        training_folder=training_folder
    )
    root.deiconify()  # show window after setup
    root.mainloop()


if __name__ == "__main__":
    main()