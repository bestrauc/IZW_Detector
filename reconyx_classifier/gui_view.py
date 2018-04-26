from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from gui_model import ImageDataListModel
from gui_logic import ReadWorker
import design


class ClassificationApp(QMainWindow, design.Ui_MainWindow):
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

    def _configure_read_worker(self):
        # configure reader thread
        read_worker = ReadWorker(self.image_dir_model)
        read_worker.result.connect(self.update_success)
        read_worker.error.connect(self.update_error)
        read_worker.progress.connect(self.update_progress)
        read_worker.finished.connect(self.finish_reader_success)

        return read_worker

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.extendUi()

        # connect this view to the model
        self.image_dir_model = ImageDataListModel()
        self.directoryList.setModel(self.image_dir_model)
        self.directoryList.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # set GUI logic callbacks
        self.addDirButton.clicked.connect(self.add_input_dir)
        self.removeDirButton.clicked.connect(self.remove_selected_dirs)
        self.startButton.clicked.connect(self.image_dir_model.continue_reading)
        self.stopButton.clicked.connect(self.image_dir_model.pause_reading)
        self.autoScan_directories.changed.connect(self.toggle_auto_read)

        # configure reader and start its thread
        self.read_thread = QThread(self)
        self.read_worker = self._configure_read_worker()
        self.image_dir_model.read_signal.connect(self.read_worker.process_directories)
        self.read_worker.moveToThread(self.read_thread)
        self.read_thread.start()

    def toggle_auto_read(self):
        self.print_info_status("Press start to scan directories.")
        self.statusWidget.show()
        self.statusChanger.setCurrentIndex(0)
        self.progressBar.hide()

        self.image_dir_model.toggle_paused()

    def add_input_dir(self):
        # let the user select the target directory
        input_dir = QFileDialog.getExistingDirectory(
            caption="Select input directory.")

        self.image_dir_model.add_dir(input_dir)

    def remove_selected_dirs(self):
        selected_idx = [QPersistentModelIndex(index) for index in
                        self.directoryList.selectionModel().selectedIndexes()]

        for index in selected_idx:
            self.image_dir_model.del_dir(index.row())

    def print_info_status(self, status_msg):
        self.statusBar.setStyleSheet("color:black")
        self.statusBar.showMessage(status_msg)

    def print_error_status(self, status_msg):
        self.statusBar.setStyleSheet("color:red")
        self.statusBar.showMessage(status_msg)

    def update_success(self, data):
        self.print_info_status("Images successfully read")

    def update_error(self, args):
        data, err = args

        if isinstance(err, FileNotFoundError):
            self.statusWidget.hide()
            self.print_error_status("Could not find any Reconxy images.")
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
