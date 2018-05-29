from PyQt5.QtCore import *
from PyQt5.QtGui import *

from enum import Enum
from itertools import chain

from data_utils.io import read_dir_metadata

from typing import Callable

import os


class ClassificationOptions:
    def __init__(self, output_dir, classification_suffix):
        self.output_dir = output_dir
        self.classification_suffix = classification_suffix


class ProcessState(Enum):
    QUEUED = 0
    IN_PROG = 1
    FAILED = 2
    DONE = 3


class TreeNode:
    def __init__(self, data, parent=None):
        self.parent = parent
        self.child_list = []

        self.data = data

    def add_child(self, data):
        child_node = TreeNode(data, parent=self)
        self.child_list.append(child_node)

    def __eq__(self, other):
        return self.data == other.data


class ImageDataItem(QObject):
    """Manages the set of image files in a directory.

    The ImageDataItem holds the path to the image directory and
    a metadata pandas.DataFrame for all the images. Additionally,
    it provides `read_data` and `classify_data` functions to read
    the image metadata and classify the images in the directory.
    """

    change_signal = pyqtSignal()

    def __init__(self, data_path: str):
        super().__init__()

        self.data_path = data_path
        self.metadata = None
        self.state = ProcessState.QUEUED

        self.process_lock = QMutex()

    def __eq__(self, other):
        return self.data_path == other.data_path

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

    def path_data(self, index: QModelIndex,
                  role: int = Qt.DisplayRole):

        item = index.internalPointer().data

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
        node = index.internalPointer()
        item = node.data
        col = index.column()

        # column 0 stores directory paths and their formatting, etc.
        if col == 0:
            return self.path_data(index, role)

        # column 1 stores the processing state
        if col == 1:
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
        # return the number of top level directories
        if not parent.isValid():
            return len(self._data)

        parent_obj = parent.internalPointer()

        # return the number of children of the root level dir
        if len(parent_obj.child_list) > 0:
            return len(parent_obj.child_list)

        return 0

    def columnCount(self, parent: QModelIndex = QModelIndex(), *args, **kwargs):
        return 2

    def parent(self, child: QModelIndex):
        if not child.isValid():
            return QModelIndex()

        child_obj = child.internalPointer()
        if child_obj is None or child_obj.parent is None:
            return QModelIndex()
        else:
            # find the index of the parent. Somewhat inefficient
            # but the quickest solution for changing indices
            parent_row = self._data.index(child_obj.parent)
            return self.createIndex(parent_row, 0, child_obj.parent)

    def index(self, row: int, column: int, parent: QModelIndex = ...):
        if not parent.isValid():
            if row < 0 or row >= len(self._data):
                return QModelIndex()

            return self.createIndex(row, column, self._data[row])

        parent = parent.internalPointer()

        if row < 0 or row >= len(parent.child_list):
            return QModelIndex()

        return self.createIndex(row, column, parent.child_list[row])

    def __init__(self, parent=None):
        super().__init__(parent)

        # set up default options. Relative output path to dir 'output/'
        # and classification outputs end with the output "input_labeled"
        self.options = ClassificationOptions(
            output_dir=os.path.join(os.getcwd(), "output"),
            classification_suffix="labeled")

        # worker thread synchronization
        self._data_lock = QMutex(QMutex.Recursive)
        self._unpause_lock = QMutex()
        self._unpause_signal = QWaitCondition()

        self._data = []
        self._paused = False
        self._active_item = None

        # prepare processing state icons
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))
        self.none_icon = QIcon(pixmap)
        self.prog_icon = QIcon(QPixmap(":/images/hourglass.svg").scaled(20, 20))

    def add_dir(self, dir_path: str):
        dir_data = ImageDataItem(dir_path)
        dir_root = TreeNode(dir_data)

        # if no input selected or duplicate path, do not add
        # (only matches by path, does not recognize symlinks etc.)
        if dir_path == '' or dir_root in self._data:
            return

        self._data_lock.lock()
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())

        # if the directory has subdirectories, add them instead
        # else we just add the selected directory on its own
        subdirs = [os.path.join(dir_path, dirname)
                   for dirname in os.listdir(dir_path)
                   if os.path.isdir(os.path.join(dir_path, dirname))]

        for iter_path in subdirs:
            child_data = ImageDataItem(iter_path)
            child_data.change_signal.connect(self._changed_dir_item)
            dir_root.add_child(child_data)
            self.read_signal.emit()

        # if no subdirectories found, emit a read signal to try to scan the root instead
        if len(subdirs) == 0:
            self.read_signal.emit()

        self._data.append(dir_root)

        self.endInsertRows()
        self._data_lock.unlock()

    def del_dir(self, index: QModelIndex):
        row_index = index.row()
        item = index.internalPointer()

        parent_index = index.parent()
        parent_row = parent_index.row()

        self._data_lock.lock()
        self.beginRemoveRows(parent_index, row_index, row_index)

        # try to acquire the lock of the item and all its children before proceeding
        for child_item in ([item] + item.child_list):
            if not child_item.data.process_lock.tryLock():
                # signal end and wait for the lock
                self._active_item = None
                child_item.data.process_lock.lock()

        # at this point we know the item is not being processed anymore
        # if it's a root node, delete it (all sub-nodes along with it)
        if item.parent is None:
            del self._data[row_index]
        else:
            del self._data[parent_row].child_list[row_index]

            # child_list may have become empty now - delete the whole root
            if len(self._data[parent_row].child_list) == 0:
                self.del_dir(parent_index)

        for child_item in ([item] + item.child_list):
            child_item.data.process_lock.unlock()

        self.endRemoveRows()
        self._data_lock.unlock()

    def get_next_unread(self) -> ImageDataItem:
        if self._paused:
            self._unpause_lock.lock()
            self._unpause_signal.wait(self._unpause_lock)
            self._unpause_lock.unlock()

        self._data_lock.lock()
        self._active_item = None
        # naively iterate through the dictionary to get next task
        # (can't easily use a generator since inserts invalidate iterator)
        for parent_dir in self._data:
            for val in (parent_dir.child_list or [parent_dir]):
                if val.data.state == ProcessState.QUEUED:
                    self._active_item = val.data
                    break

        self._data_lock.unlock()

        return self._active_item

    def scan_status(self):
        single_dirs = [node for node in self._data if not node.child_list]
        sub_dirs = [subnode for node in self._data for subnode in node.child_list
                    if node.child_list]

        # all directories have to be processed and at least some have to be completed without error
        scanned = all([node.data.state.value > 1 for node in chain(single_dirs, sub_dirs)])
        success = any([node.data.state.value == ProcessState.DONE.value for node in chain(single_dirs, sub_dirs)])

        return scanned, success

    def is_paused(self) -> bool:
        return self._active_item is None

    def pause_reading(self):
        self._paused = True
        self._active_item = None

    def continue_reading(self):
        self._paused = False
        self._unpause_signal.wakeAll()
        self.read_signal.emit()
