from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

import design
import sys

# classification imports
from data_utils import *
import pandas as pd

import logging

log = logging.getLogger(__name__)

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(levelname)-7s - %(name)-10s - %(message)s")


class WorkerSignals(QObject):
    """Slot class for notifying main thread about worker progress."""

    finished = pyqtSignal()
    progress = pyqtSignal(int)
    error = pyqtSignal(str)
    result = pyqtSignal(tuple)


class ReaderWorker(QRunnable):
    """Worker responsible for scanning the image metadata."""

    def __init__(self, dirpath):
        super(ReaderWorker, self).__init__()
        self.dirpath = dirpath
        self.signals = WorkerSignals()

        self.runnable = True;

    def run(self):
        if not self.runnable:
            self.signals.error.emit(self.dirpath)
            return

        try:
            data = read_dir_metadata(self.dirpath,
                                     progress_callback=self.report_progress)
            self.signals.result.emit((self.dirpath, data))
        except FileNotFoundError:
            self.signals.error.emit(self.dirpath)
        finally:
            self.signals.finished.emit()

    def report_progress(self, val):
        self.signals.progress.emit(val)


class ExampleApp(QMainWindow, design.Ui_MainWindow):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)

        # internal data
        self.image_data = {}
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)

        # self.reader_thread = ReaderWorker()

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

        self.progressBar.hide()
        self.label.hide()

    def update_success(self, args):
        item_path, data = args
        self.image_data[item_path] = data
        item = self.inputDirsModel.findItems(item_path)[0]
        item.setBackground(QColor(173, 255, 47, 50))

    def update_error(self, item_path):
        item = self.inputDirsModel.findItems(item_path)[0]
        item.setBackground(QColor(255, 0, 0, 50))

    def update_progress(self, percent):
        self.progressBar.setValue(percent)

    def finish_reader(self):
        self.progressBar.setValue(100)

    def add_input_dir(self):
        # let the user select the target directory
        input_dir = QFileDialog.getExistingDirectory(
            caption="Select input directory.")

        # QApplication.processEvents()

        # if no input was selected, skip
        if input_dir == '':
            return

        # don't add duplicate directories
        # (only matches by path name, does not recognize symlinks etc.)
        if len(self.inputDirsModel.findItems(input_dir)) > 0:
            return

        # add path to file list model
        # at this point, the path is still not processed
        item = QStandardItem(input_dir)
        item.setBackground(QColor(255, 250, 205, 50))
        self.inputDirsModel.appendRow(item)

        # add the path to a queue for a worker thread
        reader = ReaderWorker(input_dir)
        reader.signals.result.connect(self.update_success)
        reader.signals.error.connect(self.update_error)
        reader.signals.progress.connect(self.update_progress)
        reader.signals.finished.connect(self.finish_reader)

        self.progressBar.show()
        self.label.show()
        self.thread_pool.start(reader)

    def remove_input_dir(self):
        removed_items = []

        # query the directory QListView for currently selected items
        for index in self.directoryList.selectionModel().selectedIndexes():
            item = self.inputDirsModel.itemFromIndex(index)
            removed_items.append(item)

        # remove the selected items from the input directory model
        for item in removed_items:
            self.inputDirsModel.removeRow(item.row())


def main():
    app = QApplication(sys.argv)
    form = ExampleApp()
    form.show()
    app.exec()


if __name__ == '__main__':
    main()
