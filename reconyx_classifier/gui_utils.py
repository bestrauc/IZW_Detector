from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

import os
import sys

from data_utils.classifier import ImageClassifier
from data_utils.io import classification_to_dir

import logging
thread_log = logging.getLogger("worker")


class ReadWorker(QObject):
    """Worker responsible for reading images and reporting progress."""

    finished = pyqtSignal()
    progress = pyqtSignal(int, str)
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)

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

    # process signals are ignored if no outstanding directories left
    # the processing function blocks if reading is currently paused
    @pyqtSlot()
    def process_directories(self):
        # get next task, return if no tasks left
        item = self.data.get_next_unread()
        if item is None:
            return

        try:
            if item.read_data(self.report_scan_progress):
                self.result.emit(item)
                self.finished.emit()
        except (FileNotFoundError, InterruptedError) as err:
            self.error.emit((item, err))

    @pyqtSlot()
    def classify_directories(self):
        output_dir = self.data.model.options.output_dir
        labels = self.data.model.options.labels
        suffix = self.data.model.options.classification_suffix

        for node in self.data.get_scanned_dirs():
            data_path = os.path.basename(os.path.normpath(node.data.data_path))
            if node.parent:
                parent_path = os.path.normpath(node.parent.data.data_path)
                parent_path = os.path.basename(parent_path)
                parent_path = parent_path + "_" + suffix
                data_path = os.path.join(parent_path, data_path)
            else:
                data_path = data_path + "_" + suffix

            final_path = os.path.join(output_dir, data_path)
            print(final_path)
            item = node.data
            self.classifier.classify_data(item.metadata)
            classification_to_dir(final_path, item.metadata, labels)

    # report the progress and also check if we should interrupt processing
    def report_scan_progress(self, val):
        self.progress.emit(val, "Scanning files...")

        # check if the data processing was paused
        return not self.data.is_paused()

    def report_classification_progress(self, val):
        self.progress.emit(val, "Classifying files...")
