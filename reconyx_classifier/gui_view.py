from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from PyQt5 import QtCore, QtGui, QtWidgets

from gui_model import ImageDataListModel, ProcessState
from gui_utils import ReadWorker
import design


class StatusWidgetManager:
    """StatusWidgetManager keeps status bar components in a consistent state."""

    def __init__(self, statusChanger, progressBar):
        self.statusChanger = statusChanger
        self.progressBar = progressBar

        self.statusWidget = QWidget()
        self.statusLayout = QHBoxLayout(self.statusWidget)
        self.statusLayout.addWidget(self.statusChanger)
        self.statusLayout.addWidget(self.progressBar)
        self.statusWidget.setFixedHeight(35)
        self.statusWidget.setMaximumWidth(200)
        self.statusWidget.hide()

    def reset_state(self):
        """Reset the components to a well-defined state.

           The reset helps making the other state updates easier.
        """
        self.statusChanger.show()
        self.progressBar.show()
        self.progressBar.setValue(0)
        self.progressBar.setEnabled(True)
        self.statusWidget.show()

    def set_error_state(self):
        """Hide the widget, since it's not informative for errors."""
        self.reset_state()
        self.statusWidget.hide()

    def set_interrupted_state(self):
        """Disable progress and show restart button to indicate interrupt."""
        self.reset_state()
        self.statusChanger.setCurrentIndex(0)
        self.progressBar.setEnabled(False)

    def set_update_state(self, percent):
        """Update progress and show stop button."""
        self.reset_state()
        self.statusChanger.setCurrentIndex(1)
        self.statusChanger.show()
        self.statusWidget.show()
        self.progressBar.setValue(percent)

    def set_success_state(self):
        """Hide start/stop buttons and indicate complete progress."""
        self.reset_state()
        self.statusChanger.hide()
        self.progressBar.setValue(100)


class ClassificationApp(QMainWindow, design.Ui_MainWindow):
    def initStatusWidgetElements(self):
        self.progressBar = QtWidgets.QProgressBar(self.centralwidget)
        self.progressBar.setGeometry(QtCore.QRect(408, 490, 150, 14))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                           QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.progressBar.sizePolicy().hasHeightForWidth())
        self.progressBar.setSizePolicy(sizePolicy)
        self.progressBar.setObjectName("progressBar")
        self.stopButton = QtWidgets.QPushButton(self.centralwidget)
        self.stopButton.setGeometry(QtCore.QRect(390, 490, 14, 14))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                           QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.stopButton.sizePolicy().hasHeightForWidth())
        self.stopButton.setSizePolicy(sizePolicy)
        self.stopButton.setStyleSheet("background-color:red")
        self.stopButton.setText("")
        self.stopButton.setObjectName("stopButton")
        self.startButton = QtWidgets.QPushButton(self.centralwidget)
        self.startButton.setGeometry(QtCore.QRect(370, 490, 14, 14))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                           QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.startButton.sizePolicy().hasHeightForWidth())
        self.startButton.setSizePolicy(sizePolicy)
        self.startButton.setText("")
        icon2 = QtGui.QIcon()
        icon2.addPixmap(QtGui.QPixmap(":/images/continue-processing.svg"),
                        QtGui.QIcon.Normal, QtGui.QIcon.On)
        self.startButton.setIcon(icon2)
        self.startButton.setFlat(True)
        self.startButton.setObjectName("startButton")

    def extendUi(self):
        self.initStatusWidgetElements()

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

        self.statusManager = StatusWidgetManager(self.statusChanger,
                                                 self.progressBar)

        self.statusBar.addPermanentWidget(self.statusManager.statusWidget)

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

        # self.statBox.hide()

        # connect this view to the model
        self.image_dir_model = ImageDataListModel()
        self.directoryList.setModel(self.image_dir_model)
        # self.directoryList.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # set GUI logic callbacks
        self.addDirButton.clicked.connect(self.add_input_dir)
        self.removeDirButton.clicked.connect(self.remove_selected_dirs)
        self.startButton.clicked.connect(self.image_dir_model.continue_reading)
        self.stopButton.clicked.connect(self.image_dir_model.pause_reading)
        self.classifyButton.clicked.connect(self.classify_directories)

        self.dir_info_mapper = QDataWidgetMapper()
        self.dir_info_mapper.setModel(self.image_dir_model)
        self.dir_info_mapper.addMapping(self.imageNumLabel, 2, b"text")
        self.dir_info_mapper.addMapping(self.outputDirEdit, 1)
        self.directoryList.selectionModel().selectionChanged.connect(
            self.set_info)
        self.directoryList.selectionModel().currentRowChanged.connect(
            self.dir_info_mapper.setCurrentModelIndex)

        # configure reader and start its thread
        self.read_thread = QThread(self)
        self.read_worker = self._configure_read_worker()
        self.image_dir_model.read_signal.connect(
            self.read_worker.process_directories)
        self.read_worker.moveToThread(self.read_thread)
        self.read_thread.start()

    def set_info(self, selection: QItemSelection):
        if len(selection.indexes()) == 0:
            self.imageNumLabel.setText("No input directory selected")
            self.outputDirEdit.setText("")
            self.outputDirEdit.setEnabled(False)
        else:
            self.outputDirEdit.setEnabled(True)

    def add_input_dir(self):
        # let the user select the target directory
        input_dir = QFileDialog.getExistingDirectory(
            caption="Select input directory.")

        self.image_dir_model.add_dir(input_dir)

    def classify_directories(self):
        if not self.image_dir_model.all_scanned():
            pass

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
            self.statusManager.set_error_state()
            self.print_error_status("Could not find any Reconxy images.")
        elif isinstance(err, InterruptedError):
            self.statusManager.set_interrupted_state()
            self.print_info_status("Image scan interrupted.")
        else:
            raise NotImplementedError

    def update_progress(self, percent):
        self.statusManager.set_update_state(percent)
        self.print_info_status("Scanning files..")

    def finish_reader_success(self):
        self.statusManager.set_success_state()
