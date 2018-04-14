from typing import List

import os

import numpy as np
import pandas as pd

from .exif_utils import make_exif_dict

import logging

log_in = logging.getLogger("reader")
log_out = logging.getLogger("writer")


def _check_duplicates(data: pd.DataFrame):
    # group into distinct events (usually 3 images per event)
    event_groups = data.groupby('event_key_simple')

    duplicate_col = np.zeros(data.shape[0], dtype=np.uint8)

    # for all events, check if there are duplicate images
    # (i.e. duplicate sequnce_idx at the same time point)
    for group in event_groups:
        sequence_group = group[1].groupby(['sequence_idx'])
        group_index = data.event_key_simple == group[0]
        duplicate_ids = any(sequence_group['sequence_idx'].count() > 1)

        # for duplicate ids:
        # if the image just occurred twice         -> deduplicate
        # if the duplicates had different labels   -> remove from set
        if duplicate_ids:
            # different labels
            if group[1]['label'].unique().size > 1:
                duplicate_col[group_index] = 2
            else:
                duplicate_col[group_index] = 1
        else:
            duplicate_col[group_index] = 0

    data['duplicates'] = duplicate_col


def _extend_event_keys(data: pd.DataFrame, window_secs=10):
    """ Merge subsequent events from the same camera if they occur closely enough.

    Duplicate frames are also removed.

    :param data: The data frame to process.
    :param window_secs: The time frame to merge subsequent events [in seconds].
    :return: A data frame with extended event keys added.
    """
    simple_event_keys = data.event_key_simple.values
    event_keys = [simple_event_keys[0]]

    for i in range(1, data.shape[0]):
        last_key = event_keys[i - 1]
        current_key = simple_event_keys[i]

        if (data.timeoffset.values[i] >= np.timedelta64(0, "s")) and \
                (data.timeoffset.values[i] < np.timedelta64(window_secs,
                                                            "s")) and \
                (data.serial_no.values[i] == data.serial_no.values[i - 1]):
            current_key = last_key

        event_keys.append(current_key)

    data["event_key"] = event_keys


def read_dir_metadata(dir_path: str, sort_vals=True, progress_callback=None):
    def add_event_keys(data):
        """Add some unique keys to the rows.

        The key is serial+year+day+event2(+datetime), which can be used
        for sorting and grouping of trigger events.
        """
        data["event_key_simple"] = data.serial_no.astype(str) + "_" + \
                                   data.datetime.dt.year.astype(str) + "_" + \
                                   data.datetime.dt.dayofyear.astype(str) + \
                                   "_" + data.event2.astype(str)

        data["sortkey"] = data.event_key_simple.astype(str) + \
                          data.datetime.values.astype(np.int64).astype(str)

    log_in.info("Scanning directory '{}'".format(dir_path))
    data = []

    # candidate image files, read to list so we know max files
    jpg_files = [fname for fname in os.listdir(dir_path)
                 if fname.lower().endswith((".jpg", ".jpeg"))]

    # report progress every 2% of files scanned
    max_files = len(jpg_files)
    prog_step = max_files // 50

    log_in.info("Found {} .jpg files".format(max_files))

    # for filename in os.listdir(dir_path):
    #     if filename.lower().endswith((".jpg", ".jpeg")):
    for i, filename in enumerate(jpg_files):
        file_path = os.path.join(dir_path, filename)
        file_name = os.path.basename(file_path)

        # skip jpg file with IO issue or without right EXIF tags
        try:
            row = make_exif_dict(file_path, filename)
        except (IOError, KeyError) as err:
            log_in.warning("Skipping file '{}' - {} : {}".format(
                file_name, type(err).__name__, str(err)
            ))
            continue

        data.append(row)

        # report progress to the caller (if desired)
        # the caller could also signal us to abort processing
        if progress_callback and (i % prog_step) == 0:
            continue_signal = progress_callback(i / float(max_files) * 100)
            if not continue_signal:
                return None

    if len(data) == 0:
        raise FileNotFoundError("No Reconxy image files found in directory")

    data = pd.DataFrame(data)
    add_event_keys(data)

    if sort_vals:
        log_in.info("Sorting data rows.")
        data = data.sort_values(by=["sortkey"])

    return data


def read_training_metadata(dir_path: str, class_dir_names, extend_events=True):
    """Read training/validation data from directory 'dir_path'.

    The directory should contain some subdirectories corresponding to
    the classes we want to train. The label of the images will be extracted
    from the directory names or the EXIF data, whatever is preferable.

    A directory structure could look as follows:

    e.g.:   dir ->
                Cheetah ->
                    Cheetah_000001.jpg
                    Cheetah_000002.jpg
                    ...
                Leopard
                Unknown

    :param dir_path: string
        Path to the root directory with the training/validation data
    :param extend_events: bool
        Whether to merge Reconyx events based on successive timestamps.
    """

    found_dirs = 0
    data = None
    for dir_name in os.listdir(dir_path):
        file_path = os.path.join(os.path.abspath(dir_path) + '/' + dir_name)
        # skip files that aren't directories
        if not os.path.isdir(file_path):
            continue

        # if the directory is one of the class directories, read the metadata
        for label in class_dir_names:
            if label in dir_name:
                print("Reading %s" % file_path)
                set_data = read_dir_metadata(file_path)
                set_data['label'] = label
                set_data['set'] = 'none'

                # append to existing data or create new if necessary
                data = set_data if data is None \
                    else pd.concat([data, set_data], ignore_index=True)
                found_dirs += 1
                break

    # if not all directories specified by the user were found, abort
    if found_dirs < len(class_dir_names):
        raise IOError("Not all class directories found: {}"
                      .format(class_dir_names))

    _check_duplicates(data)

    # sort by the sortkey we constructed and break ties by filename
    data = data.sort_values(by=["sortkey", 'filename'])
    data["timeoffset"] = data.datetime.diff()

    if extend_events:
        _extend_event_keys(data)

    return data


# not sure if this function is needed
# parse the already sorted training/test data
# normally this data should exist somewhere as a metadata.hdf5 file
def read_training_metadata_old(dir_path: str, extend_events=True):
    """Read training/validation data from directory 'dir_path'.

    The directory should contain subdirectories 'train' and 'val', which
    respectively contain subdirectories for all of the desired classes.

    e.g.:   dir ->
                train -> (cheetah, leopard, unknown)
                test  -> (cheetah, leopard, unknown)

    :param dir_path: string
        Path to the root directory with the training/validation data
    :param extend_events: bool
    """

    data = None
    datasets = ['train', 'val']
    labels = ['cheetah', 'leopard', 'unknown']

    for d_set in datasets:
        d_set_path = dir_path + '/' + d_set
        if not os.path.isdir(d_set_path):
            raise IOError("Directory '{}' not found.".format(d_set_path))

        for label in labels:
            lab_set_path = d_set_path + '/' + label
            if not os.path.isdir(lab_set_path):
                raise IOError("Directory '{}' not found.".format(lab_set_path))

            print("Reading %s" % lab_set_path)
            set_data = read_dir_metadata(lab_set_path)
            set_data['set'] = d_set
            set_data['label'] = label

            if data is None:
                data = set_data
            else:
                data = pd.concat([data, set_data])

    _check_duplicates(data)

    # sort by the sortkey we constructed and break ties by filename
    data = data.sort_values(by=["sortkey", 'filename'])
    data["timeoffset"] = data.datetime.diff()

    if extend_events:
        _extend_event_keys(data)

    return data


def classification_to_dir(out_dir: str, data: pd.DataFrame, labels: List[str]):
    """Copy the labeled data to the output directory.

    :param out_dir: str
        The output directory for the sorted data.
    :param data: pandas.DataFrame
        The data, with image paths and class columns.
    :param labels:
        The label vector that will be indexed by the class number in the data.
    """

    log_out.info("Writing output to directory '{}'".format(out_dir))
    for index, label in enumerate(labels):
        target_dir = os.path.abspath(os.path.join(out_dir, label))
        label_data = data[data.label == index]
        if len(label_data) > 0:
            log_out.debug("Creating class directory {}".format(target_dir))
            try:
                os.mkdir(target_dir)
            except FileExistsError:
                log_out.error("Class directory already exists.")
                return

            for _, row in label_data.iterrows():
                src_path = os.path.abspath(row['path'])
                dst_path = os.path.join(target_dir, row['filename'])
                # log_out.debug("Copying {} to {}".format(src_path, dst_path))
                os.symlink(src_path, dst_path)
