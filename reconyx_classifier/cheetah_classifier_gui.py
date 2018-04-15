from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

import design
import sys

from queue import Queue
from collections import OrderedDict

# classification imports
from data_utils import *
import pandas as pd

import logging

log = logging.getLogger(__name__)

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(levelname)-7s - %(name)-10s - %(message)s")


class DataInformation:
    def __init__(self, data_path):
        self.data_path = data_path
        self.data = None


class ReadWorker(QObject):
    """Slot class for notifying main thread about worker progress."""

    finished = pyqtSignal()
    progress = pyqtSignal(int)
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.mutex = QMutex()
        self.running_mutex = QMutexLocker(self.mutex)
        self.running = True

    def process_directories(self, item):
        # if the process is currently paused..
        if not self.running:
            # wait for signal by `continue_iteration` to proceed
            self.running_mutex.relock()
            self.running = True
            self.running_mutex.unlock()

        # extract directory path out of the item
        dir_path = item.data_path

        if dir_path == '':
            print("Directory was removed")
            # self.task_queue.task_done()
            return

        try:
            data = read_dir_metadata(dir_path,
                                     progress_callback=self.report_progress)
            item.data = data
            self.result.emit(item)
            self.finished.emit()
        except (FileNotFoundError, InterruptedError) as err:
            self.error.emit((item, err))

    @pyqtSlot(object)
    def read_directory(self, item):
        self.process_directories(item)

    def pause_iteration(self):
        """Pause processing by locking the mutex and setting running to False"""
        self.running_mutex.relock()
        self.running = False

    def continue_iteration(self):
        self.running = True
        self.running_mutex.unlock()

    # report the progress and also check if we should interrupt processing
    def report_progress(self, val):
        self.progress.emit(val)

        return self.running


class ExampleApp(QMainWindow, design.Ui_MainWindow):
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

    read_signal = pyqtSignal(object)

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.extendUi()

        # internal data
        self.image_data = OrderedDict()
        self.read_thread = QThread(self)

        self.read_worker = ReadWorker()
        self.read_worker.result.connect(self.update_success)
        self.read_worker.error.connect(self.update_error)
        self.read_worker.progress.connect(self.update_progress)
        self.read_worker.finished.connect(self.finish_reader_success)
        self.read_signal.connect(self.read_worker.read_directory)

        self.read_worker.moveToThread(self.read_thread)
        self.read_thread.start()

        # Models
        # the input directory model holds the selected input directories
        self.inputDirsModel = QStandardItemModel()

        # Views
        # the directory list view is fed by the input directory model
        self.directoryList.setModel(self.inputDirsModel)
        self.directoryList.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # UI logic
        self.addDirButton.clicked.connect(self.add_input_dir)
        self.removeDirButton.clicked.connect(self.remove_input_dir)
        self.stopButton.clicked.connect(self.stop_processing)

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
        item = self.inputDirsModel.findItems(data.data_path)[0]

        if isinstance(err, FileNotFoundError):
            self.statusWidget.hide()
            self.print_error_status("Could not find any Reconxy images.")
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

        data = DataInformation(input_dir)
        self.image_data[data.data_path] = data

        # if no input was selected, skip
        if data.data_path == '':
            return

        # don't add duplicate directories
        # (only matches by path name, does not recognize symlinks etc.)
        if len(self.inputDirsModel.findItems(data.data_path)) > 0:
            return

        # add path to file list model
        # at this point, the path is still not processed
        item = QStandardItem(data.data_path)
        item.setBackground(QColor(255, 250, 205, 50))
        self.inputDirsModel.appendRow(item)

        self.read_signal.emit(data)

    def remove_input_dir(self):
        removed_items = []

        # query the directory QListView for currently selected items
        for index in self.directoryList.selectionModel().selectedIndexes():
            item = self.inputDirsModel.itemFromIndex(index)
            removed_items.append(item)

        # remove the selected items from the input directory model
        for item in removed_items:
            self.image_data[item.text()].data_path = ''
            del self.image_data[item.text()]
            self.inputDirsModel.removeRow(item.row())

    def stop_processing(self):
        self.read_worker.pause_iteration()


def main():
    app = QApplication(sys.argv)
    form = ExampleApp()
    form.show()
    app.exec()


if __name__ == '__main__':
    main()
