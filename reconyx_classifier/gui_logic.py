from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from data_utils import *
import pandas as pd


class Controller(QObject):
    read_signal = pyqtSignal()

    def __init__(self, model):
        super().__init__()
        self.image_dir_model, self.inputDirsModel = model

    def add_input_dir(self):
        # let the user select the target directory
        input_dir = QFileDialog.getExistingDirectory(
            caption="Select input directory.")

        # if no input was selected, skip
        if input_dir == '':
            return

        self.image_dir_model.add_dir(input_dir)

        # don't add duplicate directories
        # (only matches by path name, does not recognize symlinks etc.)
        if len(self.inputDirsModel.findItems(input_dir)) > 0:
            return

        # add path to file list model
        # at this point, the path is still not processed
        item = QStandardItem(input_dir)
        item.setBackground(QColor(255, 250, 205, 50))
        self.inputDirsModel.appendRow(item)

        self.read_signal.emit()

    def remove_input_dir(self, item):
        self.image_dir_model.del_dir(item.text())
        self.inputDirsModel.removeRow(item.row())

    def stop_processing(self):
        self.image_dir_model.pause_reading()

    def start_processing(self):
        self.image_dir_model.continue_reading()
        # re-emit signal to start processing again
        self.read_signal.emit()


class ReadWorker(QObject):
    """Worker responsible for reading images and reporting progress."""

    finished = pyqtSignal()
    progress = pyqtSignal(int)
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)

    def __init__(self, data, parent=None):
        super().__init__(parent)

        self.data = data
        self.running_mutex = QMutex()

    # process signals are ignored if no outstanding directories left
    # the processing function blocks if reading is currently paused
    @pyqtSlot()
    def process_directories(self):
        # get next task, return if no tasks left
        item = self.data.get_next_unread()
        if item is None:
            return

        try:
            if item.read_data(self.report_progress):
                self.result.emit(item)
                self.finished.emit()
        except (FileNotFoundError, InterruptedError) as err:
            self.error.emit((item, err))

    # report the progress and also check if we should interrupt processing
    def report_progress(self, val):
        self.progress.emit(val)

        # check if the data processing was paused
        return not self.data.is_paused()
