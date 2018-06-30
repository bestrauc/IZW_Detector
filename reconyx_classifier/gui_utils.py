from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

import os
import sys
from enum import Enum

from data_utils.classifier import ImageClassifier
from data_utils.io import classification_to_dir

import logging
thread_log = logging.getLogger("worker")


class ProcessState(Enum):
    QUEUED = 0
    READ_IN_PROG = 1
    FAILED = 2
    READ = 3
    CLASS_IN_PROG = 4
    CLASSIFIED = 5


class ReadWorker(QObject):
    """Worker responsible for reading images and reporting progress."""

    finished = pyqtSignal()
    notified = pyqtSignal(str)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, data, options, parent=None):
        super().__init__(parent)
        self.data = data
        self.options = options
        self.classifier = None

    @pyqtSlot()
    def initialize_classifier(self):
        # from data_utils.classifier import ImageClassifier
        # classifier object
        thread_log.info("Initializing ImageClassifier")
        try:
            self.classifier = ImageClassifier(self.options.model_path,
                                              self.options.batch_size,
                                              self.options.labels)
        except OSError as err:
            thread_log.error("OS error: {}".format(err))
            sys.exit(1)

        self.notified.emit("Classifier initialized")

    # process signals are ignored if no outstanding directories left
    # the processing function blocks if reading is currently paused
    @pyqtSlot()
    def process_directories(self):
        # get next task, return if no tasks left
        item = self.data.get_next_unread()
        if item is None:
            return

        try:
            self.changed.emit()
            if item.read_data(self.report_scan_progress):
                self.notified.emit("Images successfully scanned.")
                self.finished.emit()
        except (FileNotFoundError, InterruptedError) as err:
            self.error.emit(err)
        finally:
            self.changed.emit()

    @pyqtSlot()
    def classify_directories(self):
        output_dir = self.data.model.options.output_dir
        labels = self.data.model.options.labels
        suffix = self.data.model.options.classification_suffix

        for node in self.data.get_scanned_dirs():
            data_path = os.path.basename(os.path.normpath(node.data.data_path))
            # if the node is a subnode, append its parent path
            if node.parent:
                parent_path = os.path.normpath(node.parent.data.data_path)
                parent_path = os.path.basename(parent_path)
                parent_path = parent_path + "_" + suffix
                data_path = os.path.join(parent_path, data_path)
            # else just use the node directly as output
            else:
                data_path = data_path + "_" + suffix

            final_path = os.path.join(output_dir, data_path)
            thread_log.info("Output directory: {}".format(final_path))

            item = node.data

            try:
                item.state = ProcessState.CLASS_IN_PROG
                self.changed.emit()
                self.classifier.classify_data(item.metadata,
                                progress=self.report_classification_progress)
                classification_to_dir(final_path, item.metadata, labels)
                item.state = ProcessState.CLASSIFIED
                item.compute_class_freqs()
                self.changed.emit()
                self.finished.emit()
            except InterruptedError as err:
                item.state = ProcessState.READ
                self.changed.emit()
                self.error.emit(err)

                # exit the loop if classification was interrupted
                self.data.continue_reading()
                return

        self.notified.emit("Classification finished.")

    # report the progress and also check if we should interrupt processing
    def report_scan_progress(self, val):
        self.progress.emit(val, "Scanning files...")

        # check if the data processing was paused
        return not self.data.is_paused()

    def report_classification_progress(self, val):
        self.progress.emit(val, "Classifying files...")

        return not self.data.is_paused()
