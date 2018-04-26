from PyQt5.QtCore import *


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

    # process signals are ignored if no outstanding directories left
    # the processing function blocks if reading is currently paused
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

        # check if the data processing was paused
        return not self.data.is_paused()
