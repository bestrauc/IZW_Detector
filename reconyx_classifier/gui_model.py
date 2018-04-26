from PyQt5.QtCore import *
from PyQt5.QtGui import *
from collections import OrderedDict

from data_utils.io import read_dir_metadata
import pandas as pd


class ImageDataItem:
    def __init__(self, data_path):
        self.data_path = data_path
        self.metadata = None

        self.process_lock = QMutex()

    def read_data(self, progress_callback):
        """Read the images in the directory specified by this data."""

        # only process if the main thread isn't trying to delete it
        if not self.process_lock.tryLock():
            return False

        try:
            self.metadata = read_dir_metadata(
                self.data_path,
                progress_callback=progress_callback)
        except FileNotFoundError as err:
            self.metadata = pd.DataFrame()
            raise err
        finally:
            self.process_lock.unlock()

        return True

    def classify_data(self):
        pass


class ImageDataListModel(QAbstractListModel):
    read_signal = pyqtSignal()

    """Data model for the set of image directories we classify."""

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        """Necessary override of the data query of AbstractListModel."""

        row = index.row()
        item = list(self._data.values())[row]

        # display the directory path in the ListView
        if role == Qt.DisplayRole:
            return item.data_path

        # set background of the directory depending on processing state
        # Successful read: Green. No images found: Red. Else no color.
        if role == Qt.BackgroundColorRole and item.metadata is not None:
            if len(item.metadata) > 0:
                return QColor(173, 255, 47, 50)
            else:
                return QColor(255, 0, 0, 50)

    def rowCount(self, parent: QModelIndex = QModelIndex(), *args, **kwargs):
        """Necessary override of rowCount. Returns number of directories."""
        return len(self._data)

    def __init__(self, parent=None):
        super().__init__(parent)

        # worker thread synchronization
        self._data_lock = QMutex()
        self._unpause_lock = QMutex()
        self._unpause_signal = QWaitCondition()

        # self._data = image_data
        self._data = OrderedDict()
        self._paused = False
        self._active_item = None

    def add_dir(self, dir_path):
        # if no input selected or duplicate path, do not add
        # (only matches by path, does not recognize symlinks etc.)
        if dir_path == '' or dir_path in self._data:
            return

        self._data_lock.lock()
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        if dir_path not in self._data:
            data_info = ImageDataItem(dir_path)
            self._data[data_info.data_path] = data_info

        self.endInsertRows()
        self._data_lock.unlock()

        self.read_signal.emit()

    def del_dir(self, row_index: QModelIndex):
        item = list(self._data.values())[row_index]

        self._data_lock.lock()
        self.beginRemoveRows(QModelIndex(), row_index, row_index)

        # interrupt processing first if item is being processed
        if not item.process_lock.tryLock():
            # signal end and wait for the lock
            self._active_item = None
            item.process_lock.lock()

        # item is not being processed, delete it
        del self._data[item.data_path]
        item.process_lock.unlock()

        self.endRemoveRows()
        self._data_lock.unlock()

    def get_dir(self, dir_path: str) -> ImageDataItem:
        item = self._data[dir_path]
        return item

    def get_next_unread(self):
        if self._paused:
            self._unpause_lock.lock()
            self._unpause_signal.wait(self._unpause_lock)
            self._unpause_lock.unlock()

        self._data_lock.lock()
        self._active_item = None
        # naively iterate through the dictionary to get next task
        # (can't easily use a generator since inserts invalidate iterator)
        for val in self._data.values():
            if val.metadata is None:
                self._active_item = val
                break

        self._data_lock.unlock()

        return self._active_item

    def is_paused(self):
        return self._active_item is None

    def pause_reading(self):
        self._paused = True
        self._active_item = None

    def continue_reading(self):
        self._paused = False
        self._unpause_signal.wakeAll()
        self.read_signal.emit()
