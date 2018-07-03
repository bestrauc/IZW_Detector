from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5 import QtCore, QtGui, QtWidgets

from gui_model import ImageDataListModel
from gui_utils import ProcessState

import time
import os

import design


class ImageDataItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.decorationPosition = QStyleOptionViewItem.Right
        super(ImageDataItemDelegate, self).paint(painter, option, index)


class StatusWidgetManager:
    """StatusWidgetManager keeps status bar components in a consistent state."""

    def __init__(self, statusChanger, progressBar: QProgressBar):
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
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setEnabled(True)
        self.statusWidget.show()

    def hide_state(self):
        self.statusWidget.hide()

    def set_error_state(self):
        """Hide the widget, since it's not informative for errors."""
        self.reset_state()
        self.statusWidget.hide()

    def set_interrupted_state(self, show_resume=True):
        """Disable progress and show restart button to indicate interrupt."""
        self.reset_state()
        if show_resume:
            self.statusChanger.setCurrentIndex(0)
        else:
            self.statusChanger.hide()
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

    def set_busy_state(self):
        self.reset_state()
        self.statusChanger.hide()
        self.progressBar.setMaximum(0)


class StatusBarManager(QObject):
    def __init__(self, statusBar: QStatusBar, statusManager: StatusWidgetManager):
        super(StatusBarManager, self).__init__()
        self.statusBar = statusBar
        self.statusManager = statusManager

        self.locked_until = 0

    def _check_lock(self):
        return time.time() > self.locked_until

    @pyqtSlot(str)
    def print_info_status(self, status_msg, color="black", lock_seconds=0, ignore_lock=False):
        if not self._check_lock() and not ignore_lock:
            return

        self.statusBar.setStyleSheet("color:{}".format(color))
        self.statusBar.showMessage(status_msg)

        self.locked_until = time.time() + lock_seconds

    @pyqtSlot(str)
    def print_highlight_status(self, status_msg, hide_status=True):
        self.print_info_status(status_msg, color="blue")
        if hide_status:
            self.statusManager.hide_state()

    @pyqtSlot(str)
    def print_error_status(self, status_msg, lock_seconds=0):
        if not self._check_lock():
            return

        self.print_info_status(status_msg, color="red", lock_seconds=lock_seconds)

    @pyqtSlot(tuple)
    def update_error(self, err):
        if isinstance(err, FileNotFoundError):
            self.statusManager.set_error_state()
            self.print_error_status("Could not find any Reconxy images.")
        elif isinstance(err, InterruptedError):
            # if the interrupt came from the directory scan, show resume button
            resumable = "Directory" in str(err)
            self.statusManager.set_interrupted_state(show_resume=resumable)
            self.print_info_status(str(err), ignore_lock=True)
        else:
            raise NotImplementedError

    @pyqtSlot(int, str)
    def update_progress(self, percent: int, message: str):
        self.statusManager.set_update_state(percent)
        self.print_info_status(message)

    @pyqtSlot()
    def finish_reader_success(self):
        self.statusManager.set_success_state()


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
        icon2.addPixmap(QtGui.QPixmap(":/images/icons/continue-processing.png"),
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

        # add widget with buttons and progress bar to the status bar
        self.statusBar.addPermanentWidget(self.statusManager.statusWidget)

        self.statusBarManager = StatusBarManager(self.statusBar, self.statusManager)

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.extendUi()

        # connect this view to the model
        self.image_dir_model = ImageDataListModel()
        self.image_dir_model.connect_status_signals(self.statusBarManager)

        self.directoryList.setModel(self.image_dir_model)

        # hide all columns except the first one
        for i in range(1, self.image_dir_model.columnCount()):
            self.directoryList.hideColumn(i)

        # set GUI logic callbacks
        self.addDirButton.clicked.connect(self.add_input_dir)
        self.removeDirButton.clicked.connect(self.remove_selected_dirs)
        self.startButton.clicked.connect(self.image_dir_model.continue_processing)
        self.stopButton.clicked.connect(self.pause_processing)
        self.classifyButton.clicked.connect(self.classify_directories)
        self.outputDirButton.clicked.connect(self.set_output_dir)

        # set up a mapper that displays more detailed information
        # about model data, such as image metadata and output path
        self.dir_info_mapper = QDataWidgetMapper()
        self.dir_info_mapper.setModel(self.image_dir_model)
        self.dir_info_mapper.addMapping(self.imageNumLabel, 1, b"text")

        self.statBox.hide()

        # show default output directory
        self.outputDirEdit.setText(self.image_dir_model.options.output_dir)

        # set up the selection behavior for clicking items
        self.directoryList.selectionModel().selectionChanged.connect(
            self.clear_info)
        self.directoryList.selectionModel().currentRowChanged.connect(
            self.tree_index_changed)

        # configure a delegate that lets us show progress icons on the right
        self.itemDelegate = ImageDataItemDelegate()
        self.directoryList.setItemDelegate(self.itemDelegate)

        # tell that we are loading the model
        self.statusBarManager.print_highlight_status(
            "Loading Classification model", hide_status=False)
        self.statusManager.set_busy_state()

    def tree_index_changed(self, index: QModelIndex):
        if not index.isValid():
            return

        # don't show information for root nodes
        if index.internalPointer().child_list:
            self.statBox.hide()
            return

        self.statBox.show()
        self.dir_info_mapper.setRootIndex(index.parent())
        self.dir_info_mapper.setCurrentModelIndex(index)

    def clear_info(self, selection: QItemSelection):
        if len(selection.indexes()) == 0:
            # self.statusManager.set_error_state()
            self.statBox.hide()
            self.imageNumLabel.setText("No input directory selected")

    def set_output_dir(self):
        input_dir = QFileDialog.getExistingDirectory(
            caption="Select output directory.")

        # don't change anything if no directory was selected
        if input_dir == '':
            return

        self.outputDirEdit.setText(input_dir)
        self.image_dir_model.options.output_dir = input_dir

    def pause_processing(self):
        self.statusBarManager.print_info_status(
            "Pausing processing..")
        self.image_dir_model.pause_processing()

    def add_input_dir(self):
        model_state = self.image_dir_model.scan_status()
        if model_state == ProcessState.CLASS_IN_PROG:
            self.statusBarManager.print_info_status(
                "Cannot add directories while classification in progress.",
                color="blue", lock_seconds=2)
            return

        # let the user select the target directory
        input_dir = QFileDialog.getExistingDirectory(
            caption="Select input directory.")

        self.image_dir_model.add_dir(input_dir)
        self.directoryList.expandAll()

    def remove_selected_dirs(self):
        model_state = self.image_dir_model.scan_status()
        if model_state == ProcessState.CLASS_IN_PROG:
            self.statusBarManager.print_info_status(
                "Cannot remove directories while classification in progress.",
                color="blue", lock_seconds=2)
            return

        selected_idx = [QPersistentModelIndex(index) for index in
                        self.directoryList.selectionModel().selectedIndexes()
                        if index.column() == 0]

        for i, index in enumerate(selected_idx):
            self.image_dir_model.del_dir(QModelIndex(index))

    def classify_directories(self):
        if self.image_dir_model.is_paused():
            self.statusBarManager.print_info_status(
                "Please scan all directories before classification.",
                color="blue", lock_seconds=2)
            return

        model_state = self.image_dir_model.scan_status()

        if model_state == ProcessState.READ_IN_PROG:
            self.statusBarManager.print_info_status(
                "Please wait for directory scans to finish.",
                color="blue", lock_seconds=2)
        elif model_state == ProcessState.QUEUED:
            self.statusBarManager.print_info_status(
                "Please add directories to classify",
                color="blue", lock_seconds=2)
        elif model_state == ProcessState.FAILED:
            self.statusBarManager.print_error_status(
                "No valid images found during directory scan.", lock_seconds=2)
        elif model_state == ProcessState.CLASS_IN_PROG:
            self.statusBarManager.print_info_status(
                "Classification already in progress",
                color="blue", lock_seconds=2)
        elif model_state == ProcessState.READ:
            out_path = self.image_dir_model.options.output_dir
            if not (os.path.exists(out_path) and os.path.isdir(out_path)):
                self.statusBarManager.print_error_status(
                    "Please select an existing output directory")
                return

            if os.listdir(out_path):
                self.statusBarManager.print_error_status(
                    "Please select an empty output directory.")
                return

            self.image_dir_model.start_classification()
            self.statusBarManager.print_info_status("Starting classification..")
            self.statusManager.set_busy_state()
        elif model_state == ProcessState.CLASSIFIED:
            self.statusBarManager.print_info_status(
                "All directories already classified.",
                color="blue", lock_seconds=2)
