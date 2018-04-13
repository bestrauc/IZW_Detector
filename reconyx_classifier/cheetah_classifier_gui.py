from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

import design
import sys

from queue import Queue

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
    error = pyqtSignal(object)
    result = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.task_queue = Queue()

    def process_tasks(self):
        while not self.task_queue.empty():
            item = self.task_queue.get()
            # extract directory path out of the item
            dirpath = item.data_path

            if dirpath == "":
                print("Directory was removed")
                continue

            try:
                data = read_dir_metadata(dirpath,
                                         progress_callback=self.report_progress)
                item.data = data
                self.result.emit(item)
            except FileNotFoundError:
                self.error.emit(item)
            finally:
                self.finished.emit()

    @pyqtSlot(object)
    def read_directory(self, item):
        print("Received path {}".format(str(item.data_path)))

        self.task_queue.put(item)
        self.process_tasks()

    def stop_processing(self):
        pass

    def report_progress(self, val):
        self.progress.emit(val)


class ExampleApp(QMainWindow, design.Ui_MainWindow):
    read_signal = pyqtSignal(object)

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)

        # internal data
        self.image_data = {}
        self.read_thread = QThread(self)

        self.read_worker = ReadWorker()
        self.read_worker.result.connect(self.update_success)
        self.read_worker.error.connect(self.update_error)
        self.read_worker.progress.connect(self.update_progress)
        self.read_worker.finished.connect(self.finish_reader)
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

        self.stopButton.hide()
        self.progressBar.hide()
        self.label.hide()

    def update_success(self, data):
        # self.image_data[data.data_path].data = data
        item = self.inputDirsModel.findItems(data.data_path)[0]
        item.setBackground(QColor(173, 255, 47, 50))

    def update_error(self, data):
        item = self.inputDirsModel.findItems(data.data_path)[0]
        item.setBackground(QColor(255, 0, 0, 50))

    def update_progress(self, percent):
        self.progressBar.setValue(percent)

    def finish_reader(self):
        self.stopButton.hide()
        self.progressBar.setValue(100)

    def add_input_dir(self):
        # let the user select the target directory
        input_dir = QFileDialog.getExistingDirectory(
            caption="Select input directory.")

        data = DataInformation(input_dir)
        self.image_data[data.data_path] = data

        # QApplication.processEvents()

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

        self.stopButton.show()
        self.progressBar.show()
        self.label.show()

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


def main():
    app = QApplication(sys.argv)
    form = ExampleApp()
    form.show()
    app.exec()


if __name__ == '__main__':
    main()
