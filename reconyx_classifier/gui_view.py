from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from gui_model import ImageDataListModel
from gui_logic import Controller, ReadWorker
import design


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

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.extendUi()

        # connect this view to the model
        self.image_dir_model = ImageDataListModel()
        self.directoryList.setModel(self.image_dir_model)
        self.directoryList.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # configure reader thread
        self.read_thread = QThread(self)
        self.read_worker = ReadWorker(self.image_dir_model)
        self.read_worker.result.connect(self.update_success)
        self.read_worker.error.connect(self.update_error)
        self.read_worker.progress.connect(self.update_progress)
        self.read_worker.finished.connect(self.finish_reader_success)

        # connect this view to the controller
        self.controller = Controller(self.image_dir_model)

        self.addDirButton.clicked.connect(self.controller.add_input_dir)

        self.removeDirButton.clicked.connect(self.remove_selected_dirs)

        self.startButton.clicked.connect(self.controller.start_processing)
        self.stopButton.clicked.connect(self.controller.stop_processing)
        self.controller.read_signal.connect(self.read_worker.process_directories)

        # start reader thread
        self.read_worker.moveToThread(self.read_thread)
        self.read_thread.start()

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
