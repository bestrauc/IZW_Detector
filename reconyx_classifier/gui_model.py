from PyQt5.QtCore import *
from PyQt5.QtGui import *

from itertools import chain

from gui_utils import ReadWorker, ProcessState
from data_utils.io import read_dir_metadata

from typing import Callable

import os

import logging
gui_log = logging.getLogger("gui")


class ClassificationOptions:
    def __init__(self, output_dir, classification_suffix,
                 model_path, batch_size, labels):
        self.output_dir = output_dir
        self.classification_suffix = classification_suffix
        self.model_path = model_path
        self.batch_size = batch_size
        self.labels = labels


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

        self.state = ProcessState.READ_IN_PROG
        self.change_signal.emit()

        try:
            self.metadata = read_dir_metadata(
                self.data_path,
                progress_callback=progress_callback)
            self.state = ProcessState.READ
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


class ImageData:
    def __init__(self, parent_model):
        self._data = []

        # could expose signals to models, but we just store a reference
        self.model = parent_model

        # worker thread synchronization
        self._data_lock = QMutex(QMutex.Recursive)
        self._unpause_lock = QMutex()
        self._unpause_signal = QWaitCondition()
        # processing state
        self._paused = False
        self._active_item = None

    def __len__(self):
        return len(self._data)

    def __getitem__(self, key):
        return self._data[key]

    def index(self, val):
        return self._data.index(val)

    def add_dir(self, dir_path: str):
        dir_data = ImageDataItem(dir_path)
        dir_root = TreeNode(dir_data)

        # if no input selected or duplicate path, do not add
        # (only matches by path, does not recognize symlinks etc.)
        if dir_path == '' or dir_root in self._data:
            return

        self._data_lock.lock()

        # if the directory has subdirectories, add them instead
        # else we just add the selected directory on its own
        subdirs = [os.path.join(dir_path, dirname)
                   for dirname in os.listdir(dir_path)
                   if os.path.isdir(os.path.join(dir_path, dirname))]

        for iter_path in subdirs:
            child_data = ImageDataItem(iter_path)
            child_data.change_signal.connect(self.model.update_view)
            dir_root.add_child(child_data)
            self.model.read_signal.emit()

        # if no subdirectories found, emit a read signal
        # to try to scan the root instead
        if len(subdirs) == 0:
            self.model.read_signal.emit()

        self._data.append(dir_root)

        self._data_lock.unlock()

    def del_dir(self, index: QModelIndex):
        row_index = index.row()
        item = index.internalPointer()

        parent_index = index.parent()
        parent_row = parent_index.row()

        self._data_lock.lock()

        # try to acquire the lock of the item and its children before proceeding
        for child_item in ([item] + item.child_list):
            if not child_item.data.process_lock.tryLock():
                # signal end and wait for the lock
                self._active_item = None
                child_item.data.process_lock.lock()

        keep_root = True
        # at this point we know the item is not being processed anymore
        # if it's a root node, delete it (all sub-nodes along with it)
        if item.parent is None:
            del self._data[row_index]
        else:
            del self._data[parent_row].child_list[row_index]
            keep_root = len(self._data[parent_row].child_list) > 0

        for child_item in ([item] + item.child_list):
            child_item.data.process_lock.unlock()

        self._data_lock.unlock()

        # child_list may have become empty now - if that is the case
        # we return False and tell the caller to delete the root too
        return keep_root

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
                    self.model.update_view()
                    self._active_item = val.data
                    break

        self._data_lock.unlock()

        return self._active_item

    def get_scanned_dirs(self):
        single_dirs = [node for node in self._data if not node.child_list]
        sub_dirs = [subnode for node in self._data
                    for subnode in node.child_list
                    if node.child_list]

        return [node for node in chain(single_dirs, sub_dirs)
                if node.data.state.value == ProcessState.READ.value]

    def scan_status(self):
        single_dirs = [node for node in self._data if not node.child_list]
        sub_dirs = [subnode for node in self._data
                    for subnode in node.child_list
                    if node.child_list]

        # all directories have to be processed and at
        # least some have to be completed without error
        scanned = all([node.data.state.value > 1
                       for node in chain(single_dirs, sub_dirs)])
        success = any([node.data.state.value == ProcessState.READ.value
                       for node in chain(single_dirs, sub_dirs)])

        return scanned, success

    def is_paused(self) -> bool:
        return self._paused

    def pause_reading(self):
        self._paused = True
        self._active_item = None

    def continue_reading(self):
        self._paused = False
        self._unpause_signal.wakeAll()
        self.model.read_signal.emit()


class ImageDataListModel(QAbstractItemModel):
    """Implements a ListModel interface for a set of image directories."""

    read_signal = pyqtSignal()
    classify_signal = pyqtSignal()
    init_classifier = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # set up default options. Relative output path to dir 'output/'
        # and classification outputs end with the output "input_labeled"
        self.options = ClassificationOptions(
            output_dir=os.path.join(os.getcwd(), "output"),
            classification_suffix="labeled",
            model_path="model/inception-resnet-v2-cheetahs.h5",
            batch_size=16,
            # labels=['cheetah', 'unknown', 'leopard']
            labels=['unknown', 'cheetah', 'leopard']
        )

        # internal data store
        self._image_data = ImageData(parent_model=self)

        # prepare processing state icons
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(0, 0, 0, 0))
        self.none_icon = QIcon(pixmap)
        self.prog_icon = QIcon(QPixmap(":/images/hourglass.svg").scaled(20, 20))

        # configure reader and start its thread
        self.read_thread = QThread(self)
        self.read_worker = ReadWorker(self._image_data, self.options)

        self.read_signal.connect(
            self.read_worker.process_directories)
        self.classify_signal.connect(
            self.read_worker.classify_directories)
        self.read_worker.moveToThread(self.read_thread)
        self.init_classifier.connect(
            self.read_worker.initialize_classifier)
        self.read_thread.start()

        self.init_classifier.emit()

    @pyqtSlot()
    def changed_dir_item(self):
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
            if item.state == ProcessState.READ:
                return QColor(173, 255, 47, 60)
            elif item.state == ProcessState.CLASSIFIED:
                return QColor(0, 191, 255, 60)
            elif item.state == ProcessState.FAILED:
                return QColor(255, 0, 0, 50)
            else:
                return QColor(238, 232, 170, 80)

        if role == Qt.UserRole:
            return item.state

        if role == Qt.DecorationRole:
            if item.state == ProcessState.READ_IN_PROG or \
               item.state == ProcessState.CLASS_IN_PROG:
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
                if item.state == ProcessState.READ_IN_PROG:
                    return "Waiting for scan to finish.."
                if item.state == ProcessState.READ:
                    return "{} images found in {} events".format(
                       len(item.metadata),
                       item.metadata['event_key_simple'].nunique()
                    )

                if item.state == ProcessState.CLASS_IN_PROG:
                    return "Classifying images.."

                if item.state == ProcessState.CLASSIFIED:
                    return "{} images found in {} events\n{}".format(
                        len(item.metadata),
                        item.metadata['event_key_simple'].nunique(),
                        "testing next line"
                    )

                raise RuntimeError("Undefined state")

    def rowCount(self, parent: QModelIndex = QModelIndex(), *args, **kwargs):
        """Necessary override of rowCount. Returns number of directories."""
        # return the number of top level directories
        if not parent.isValid():
            return len(self._image_data)

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
            parent_row = self._image_data.index(child_obj.parent)
            return self.createIndex(parent_row, 0, child_obj.parent)

    def index(self, row: int, column: int, parent: QModelIndex = ...):
        if not parent.isValid():
            if row < 0 or row >= len(self._image_data):
                return QModelIndex()

            return self.createIndex(row, column, self._image_data[row])

        parent = parent.internalPointer()

        if row < 0 or row >= len(parent.child_list):
            return QModelIndex()

        return self.createIndex(row, column, parent.child_list[row])

    def connect_status_signals(self, statusBar):
        self.read_worker.result.connect(statusBar.update_success)
        self.read_worker.error.connect(statusBar.update_error)
        self.read_worker.progress.connect(statusBar.update_progress)
        self.read_worker.finished.connect(statusBar.finish_reader_success)
        self.read_worker.notified.connect(statusBar.print_highlight_status)
        self.read_worker.changed.connect(self.update_view)

    def update_view(self):
        self.dataChanged.emit(QModelIndex(), QModelIndex())

    def add_dir(self, dir_path: str):
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        self._image_data.add_dir(dir_path)
        self.endInsertRows()

    def del_dir(self, index: QModelIndex):
        row_index = index.row()
        parent_index = index.parent()

        self.beginRemoveRows(parent_index, row_index, row_index)
        keep_root = self._image_data.del_dir(index)
        self.endRemoveRows()

        if not keep_root:
            self.del_dir(parent_index)

    def scan_status(self):
        return self._image_data.scan_status()

    def pause_reading(self):
        self._image_data.pause_reading()

    def continue_reading(self):
        self._image_data.continue_reading()

    def start_classification(self):
        self.classify_signal.emit()
