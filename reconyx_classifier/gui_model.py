from PyQt5.QtCore import *
from collections import OrderedDict

from data_utils.io import read_dir_metadata
import pandas as pd


class ImageData:
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


# TODO: make class into a model for the QListView
class ImageDataListModel:
    def __init__(self):
        # worker thread synchronization
        self._data_lock = QMutex()
        self._unpause_lock = QMutex()
        self._unpause_signal = QWaitCondition()

        # self._data = image_data
        self._data = OrderedDict()
        self._paused = False
        self._active_item = None

    def add_dir(self, dir_path):
        self._data_lock.lock()
        if dir_path not in self._data:
            data_info = ImageData(dir_path)
            self._data[data_info.data_path] = data_info

        self._data_lock.unlock()

    def del_dir(self, dir_path):
        self._data_lock.lock()
        if dir_path in self._data:
            item = self._data[dir_path]

            # interrupt processing first if item is being processed
            if not item.process_lock.tryLock():
                # signal end and wait for the lock
                self._active_item = None
                item.process_lock.lock()

            # item is not being processed, delete it
            del self._data[dir_path]
            item.process_lock.unlock()

        self._data_lock.unlock()

    def get_next_unread(self):
        if self._paused:
            self._unpause_lock.lock()
            self._unpause_signal.wait(self._unpause_lock)
            self._unpause_lock.unlock()

        self._data_lock.lock()
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
