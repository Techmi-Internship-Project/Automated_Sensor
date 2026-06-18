import cv2 as cv
import matplotlib.pyplot as plt
from datetime import datetime
import time


from organism_menu import choose_organism
from experiment_controller import ExperimentController
from gui_app import SensorGUI
from config import CURRENT_FOLDER, TRAINING_FOLDER

def main():
    app = SensorGUI(current_folder=CURRENT_FOLDER, training_folder=TRAINING_FOLDER)
    app.run()
if __name__ == "__main__": main()
