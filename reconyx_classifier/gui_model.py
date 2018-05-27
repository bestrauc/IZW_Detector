from PyQt5.QtCore import *
from PyQt5.QtGui import *

from collections import OrderedDict

from typing import Callable
from data_utils.io import read_dir_metadata
from enum import Enum

import os


class ProcessState(Enum):
    QUEUED = 0
    IN_PROG = 1
    FAILED = 2
    DONE = 3


class ImageDirRoot:
    def __init__(self, path=None):
        self.path = path
        self.child_list = []




class ImageDataItem(QObject):
    """Manages the set of image files in a directory.

    The ImageDataItem holds the path to the image directory and
    a metadata pandas.DataFrame for all the images. Additionally,
    it provides `read_data` and `classify_data` functions to read
    the image metadata and classify the images in the directory.
    """

    change_signal = pyqtSignal()

    def __init__(self, data_path: str, parent_path: str = None):
        super().__init__()

        self.data_path = data_path
        self.parent_path = parent_path
        self.metadata = None
        self.state = ProcessState.QUEUED

        self.process_lock = QMutex()

    def read_data(self, progress_callback: Callable[[int], bool]) -> bool:
        """Read the images in the directory specified by this data.

        :param progress_callback:
            The read_data function can optionally report the progress
            of reading the images from the directory to a callback.
            Will report a value in [0,100]% and expect a boolean in
            return which indicates whether to keep processing.
        :return:
            False if the object is currently not ready for processing.
        """

        # only process if the main thread isn't trying to delete it
        if not self.process_lock.tryLock():
            return False

        self.state = ProcessState.IN_PROG
        self.change_signal.emit()

        try:
            self.metadata = read_dir_metadata(
                self.data_path,
                progress_callback=progress_callback)
            self.state = ProcessState.DONE
        except FileNotFoundError as err:
            self.state = ProcessState.FAILED
            raise err
        except InterruptedError as err:
            self.state = ProcessState.QUEUED
            raise err
        finally:
            self.change_signal.emit()
            self.process_lock.unlock()

        return True

    def classify_data(self):
        pass


class ImageDataListModel(QAbstractItemModel):
    """Implements a ListModel interface for a set of image directories."""

    read_signal = pyqtSignal()

    @pyqtSlot()
    def _changed_dir_item(self):
        ind1 = self.createIndex(0, 0)
        ind2 = self.createIndex(self.rowCount()-1, self.columnCount()-1)
        self.dataChanged.emit(ind1, ind2)

    def _item_from_index(self, index: QModelIndex):
        row, col = index.row(), index.column()
        item = [v for x in self._data.values() for v in x][row]

        return item

    def path_data(self, index: QModelIndex,
                  role: int = Qt.DisplayRole):

        item = self._item_from_index(index)

        # display the directory path in the ListView
        if role == Qt.DisplayRole:
            return item.data_path

        # set background of the directory depending on processing state
        # Successful read: Green. No images found: Red. Else no color.
        if role == Qt.BackgroundColorRole and item.state != ProcessState.QUEUED:
            if item.state == ProcessState.DONE:
                return QColor(173, 255, 47, 60)
            elif item.state == ProcessState.FAILED:
                return QColor(255, 0, 0, 50)
            else:
                return QColor(238, 232, 170, 80)

        if role == Qt.UserRole:
            return item.state

        if role == Qt.DecorationRole:
            if item.state == ProcessState.IN_PROG:
                return self.prog_icon

            return self.none_icon

        if role == Qt.SizeHintRole:
            # we just want to set the height, view will change width 25
            return QSize(25, 25)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        """Necessary override of the data query of AbstractListModel."""

        # if the index is a top level directory (with children),
        # only return the path of the directory
        if index.internalPointer() is None:
            dir_name, subdir_items = list(self._data.items())[index.row()]
            if len(subdir_items) > 1:
                return dir_name
            else:
                item = subdir_items[0]
        else:
            item = self._item_from_index(index)

        col = index.column()

        # column 0 stores directory paths and their formatting, etc.
        if col == 0:
            return self.path_data(index, role)

        # column 1 stores the output paths
        if col == 1:
            if role == Qt.EditRole:
                return item.data_path + "_classified"

        # column 2 stores the processing state
        if col == 2:
            if role == Qt.EditRole:
                if item.state == ProcessState.QUEUED:
                    return "Waiting for directory scan.."
                if item.state == ProcessState.FAILED:
                    return "No Reconyx images found"
                if item.state == ProcessState.IN_PROG:
                    return "Waiting for scan to finish.."
                if item.state == ProcessState.DONE:
                    return "{} images found in {} events".format(
                       len(item.metadata),
                       item.metadata['event_key_simple'].nunique()
                    )

                raise RuntimeError("Undefined state")

    def rowCount(self, parent: QModelIndex = QModelIndex(), *args, **kwargs):
        """Necessary override of rowCount. Returns number of directories."""
        if parent.isValid() and parent.internalPointer() is not None:
            parent_row = parent.internalPointer()
            return len(list(self._data.values())[parent_row])

        # return the number of top level directories
        return len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex(), *args, **kwargs):
        return 3

    def parent(self, child: QModelIndex):
        if not child.isValid():
            return QModelIndex()

        parent_row = child.internalPointer()
        if parent_row is None:
            return QModelIndex()
        else:
            return self.createIndex(parent_row, 0, None)

    def index(self, row: int, column: int, parent: QModelIndex = ...):
        if not parent.isValid():
            return self.createIndex(row, column, None)

        # parent_dir = parent.internalPointer()
        return self.createIndex(row, column, parent.row())

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

        # prepare processing state icons
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))
        self.none_icon = QIcon(pixmap)
        self.prog_icon = QIcon(QPixmap(":/images/hourglass.svg").scaled(20, 20))

    def add_dir(self, dir_path: str):
        # if no input selected or duplicate path, do not add
        # (only matches by path, does not recognize symlinks etc.)
        if dir_path == '' or dir_path in self._data:
            return

        self._data_lock.lock()
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())

        # if the directory has subdirectories, add them instead
        # else we just add the selected directory on its own
        subdirs = [os.path.join(dir_path, dirname)
                   for dirname in os.listdir(dir_path)
                   if os.path.isdir(os.path.join(dir_path, dirname))]

        print(list(os.listdir(dir_path)))
        print(subdirs)

        self._data[dir_path] = []
        # iterate over subdirs or dir_path if subdirs is empty
        for iter_path in (subdirs or [dir_path]):
            data_info = ImageDataItem(iter_path, dir_path)
            data_info.change_signal.connect(self._changed_dir_item)
            # self._data[data_info.parent_path][data_info.data_path] = data_info
            self._data[data_info.parent_path].append(data_info)
            self.read_signal.emit()

        self.endInsertRows()
        self._data_lock.unlock()

    def del_dir(self, index: QModelIndex):
        row_index = index.row()
        item = self._item_from_index(index)

        self._data_lock.lock()
        self.beginRemoveRows(QModelIndex(), row_index, row_index)

        # interrupt processing first if item is being processed
        if not item.process_lock.tryLock():
            # signal end and wait for the lock
            self._active_item = None
            item.process_lock.lock()

        # item is not being processed, delete it
        del self._data[item.parent_path][row_index]
        # delete the parent entry if the whole dictionary is empty
        if not self._data[item.parent_path]:
            del self._data[item.parent_path]
        item.process_lock.unlock()

        self.endRemoveRows()
        self._data_lock.unlock()

    def get_dir(self, index: QModelIndex) -> ImageDataItem:
        item = self._item_from_index(index)
        return item

    def get_next_unread(self) -> ImageDataItem:
        if self._paused:
            self._unpause_lock.lock()
            self._unpause_signal.wait(self._unpause_lock)
            self._unpause_lock.unlock()

        self._data_lock.lock()
        self._active_item = None
        # naively iterate through the dictionary to get next task
        # (can't easily use a generator since inserts invalidate iterator)
        for parent_dir in self._data.values():
            for val in parent_dir:
                if val.state == ProcessState.QUEUED:
                    self._active_item = val
                    break

        self._data_lock.unlock()

        return self._active_item

    def all_scanned(self):
        dir_states = [val.state.value for val in self._data.values()]
        scanned = all([state > 1 for state in dir_states])
        success = any([state == ProcessState.DONE for state in dir_states])

        return scanned and success

    def is_paused(self) -> bool:
        return self._active_item is None

    def pause_reading(self):
        self._paused = True
        self._active_item = None

    def continue_reading(self):
        self._paused = False
        self._unpause_signal.wakeAll()
        self.read_signal.emit()
