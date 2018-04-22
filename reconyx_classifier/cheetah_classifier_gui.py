from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

import design
import sys

from queue import PriorityQueue
from collections import OrderedDict

# classification imports
from data_utils import *
import pandas as pd

import logging

log = logging.getLogger(__name__)

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(levelname)-7s - %(name)-10s - %(message)s")


class ImageData:
    # TODO: make class into a model for the QListView

    def __init__(self):
        self.data = OrderedDict()

        self.paused = False
        self.active_item = None

    def add_dir(self, dir_path):
        if dir_path in self.data:
            return

        data_info = DataInformation(dir_path)
        self.data[data_info.data_path] = data_info

    def del_dir(self, dir_path):
        if dir_path in self.data:
            item = self.data[dir_path]

            # interrupt processing first if item is being processed
            if not item.process_lock.tryLock():
                # signal end and wait for the lock
                self.active_item = None
                item.process_lock.lock()

            # item is not being processed, delete it
            del self.data[dir_path]

    def get_next_unread(self):
        # naively iterate through the dictionary to get next task
        # (can't easily use a generator since inserts invalidate iterator)
        for val in self.data.values():
            if val.metadata is None:
                self.active_item = val
                return val

        return None

    def pause_reading(self):
        self.paused = True
        self.active_item = None

    def continue_reading(self):
        self.paused = False


class DataInformation:
    def __init__(self, data_path):
        self.data_path = data_path
        self.metadata = None

        self.process_lock = QMutex()

    def read_data(self, progress_callback):
        """Read the images in the directory specified by this data."""

        # only process if the main thread isn't trying to delete it
        if not self.process_lock.tryLock():
            return False

        try:
            self.metadata = read_dir_metadata(
                                    self.data_path,
                                    progress_callback=progress_callback)
        except FileNotFoundError as err:
            self.metadata = pd.DataFrame()
            raise err
        finally:
            self.process_lock.unlock()

        return True

    def classify_data(self):
        pass


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

    # TODO: if a directory is added/removed multiple times, this slot
    # TODO: queues the add-events and starts processing after stops
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

        # self.active_item should never be None at this stage
        # (report_progress is only ever called from within process_directories)
        return self.data.active_item is not None


class ExampleApp(QMainWindow, design.Ui_MainWindow):
    read_signal = pyqtSignal()

    def extendUi(self):
        # some more custom UI setup for the progress in the statusBar
        self.stopButton.setFixedSize(self.stopButton.geometry().width(),
                                     self.stopButton.geometry().height())
        self.progressBar.setFixedSize(self.progressBar.geometry().width(),
                                      self.progressBar.geometry().height())

        # status change buttons are stacked on top of each other
        self.statusChanger = QStackedWidget()
        self.statusChanger.addWidget(self.startButton)
        self.statusChanger.addWidget(self.stopButton)
        self.statusChanger.setCurrentIndex(1)

        # status change is next to a progress bar in the status bar
        self.statusWidget = QWidget()
        self.statusLayout = QHBoxLayout(self.statusWidget)
        self.statusLayout.addWidget(self.statusChanger)
        self.statusLayout.addWidget(self.progressBar)
        self.statusWidget.setFixedHeight(35)
        self.statusWidget.setMaximumWidth(200)
        self.statusBar.addPermanentWidget(self.statusWidget)
        self.statusWidget.hide()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.extendUi()

        # internal data
        self.image_data = ImageData()
        self.read_thread = QThread(self)

        # thread-related data
        self.read_worker = ReadWorker(self.image_data)
        self.read_worker.result.connect(self.update_success)
        self.read_worker.error.connect(self.update_error)
        self.read_worker.progress.connect(self.update_progress)
        self.read_worker.finished.connect(self.finish_reader_success)
        self.read_signal.connect(self.read_worker.process_directories)

        self.read_worker.moveToThread(self.read_thread)
        self.read_thread.start()

        # Models
        # the input directory model holds the selected input directories
        # TODO: remove this and make the ImageData the model for the view
        self.inputDirsModel = QStandardItemModel()

        # Views
        # the directory list view is fed by the input directory model
        self.directoryList.setModel(self.inputDirsModel)
        self.directoryList.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # UI logic
        self.addDirButton.clicked.connect(self.add_input_dir)
        self.removeDirButton.clicked.connect(self.remove_input_dir)
        self.stopButton.clicked.connect(self.stop_processing)
        self.startButton.clicked.connect(self.start_processing)

    def print_info_status(self, status_msg):
        self.statusBar.setStyleSheet("color:black")
        self.statusBar.showMessage(status_msg)

    def print_error_status(self, status_msg):
        self.statusBar.setStyleSheet("color:red")
        self.statusBar.showMessage(status_msg)

    def update_success(self, data):
        # self.image_data[data.data_path].data = data
        self.print_info_status("Images successfully read")
        item = self.inputDirsModel.findItems(data.data_path)[0]
        item.setBackground(QColor(173, 255, 47, 50))

    def update_error(self, args):
        data, err = args

        if isinstance(err, FileNotFoundError):
            self.statusWidget.hide()
            self.print_error_status("Could not find any Reconxy images.")

            item = self.inputDirsModel.findItems(data.data_path)[0]
            item.setBackground(QColor(255, 0, 0, 50))
        elif isinstance(err, InterruptedError):
            self.statusChanger.setCurrentIndex(0)
            self.print_info_status("Image scan interrupted.")
        else:
            raise NotImplementedError

    def update_progress(self, percent):
        self.statusChanger.setCurrentIndex(1)
        self.statusChanger.show()
        self.statusWidget.show()
        self.print_info_status("Scanning files..")

        self.progressBar.setValue(percent)

    def finish_reader_success(self):
        self.statusChanger.hide()
        self.progressBar.setValue(100)

    def add_input_dir(self):
        # let the user select the target directory
        input_dir = QFileDialog.getExistingDirectory(
            caption="Select input directory.")

        # if no input was selected, skip
        if input_dir == '':
            return

        self.image_data.add_dir(input_dir)

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

    def remove_input_dir(self):
        removed_items = []

        # query the directory QListView for currently selected items
        for index in self.directoryList.selectionModel().selectedIndexes():
            item = self.inputDirsModel.itemFromIndex(index)
            removed_items.append(item)

        # remove the selected items from the input directory model
        for item in removed_items:
            self.image_data.del_dir(item.text())
            self.inputDirsModel.removeRow(item.row())

    def stop_processing(self):
        self.image_data.pause_reading()

    def start_processing(self):
        self.image_data.continue_reading()
        # re-emit signal to start processing again
        self.read_signal.emit()


def main():
    app = QApplication(sys.argv)
    form = ExampleApp()
    form.show()
    app.exec()


if __name__ == '__main__':
    main()
