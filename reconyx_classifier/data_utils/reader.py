import os
import struct
import array

import exifread
import datetime

import pandas
import numpy as np

import logging

log = logging.getLogger(__name__)


class Info(object):
    offset = None
    name = None
    fmt = None

    def __init__(self, name, offset, fmt):
        self.name = name
        self.offset = offset
        self.fmt = fmt

    def read(self, blob):
        global INFOS
        idx = INFOS.index(self)
        next_offset = len(blob)
        if idx + 1 < len(INFOS):
            next_offset = INFOS[idx + 1].offset

        size = next_offset - self.offset
        subbuffer = blob[self.offset:next_offset]
        req_size = struct.calcsize(self.fmt)

        if size > req_size:
            subbuffer = blob[self.offset:(self.offset + req_size)]

        try:
            val = struct.unpack(self.fmt, subbuffer)

            try:
                if len(val) == 1:
                    val = val[0]
            except:
                pass

            return val
        except Exception as e:
            print(str(e))
            print("\tint {}, len {}".format(self.name, size))
            return None


# global constant with the metadata we want to extract
INFOS = [
    Info("Makernote Version", 0x0000, "H"),
    Info("Firmware Version", 0x0002, "H"),
    Info("Trigger Mode", 0x000c, "2s"),
    Info("Sequence", 0x000e, "2H"),
    Info("Event Number", 0x0012, "2H"),
    Info("Date/Time Original", 0x0016, "6H"),
    Info("Moon Phase", 0x0024, "H"),
    Info("Ambient Temperature Fahrenheit", 0x0026, "h"),
    Info("Ambient Temperature", 0x0028, "h"),
    Info("Serial Number", 0x002a, "30s"),
    Info("Contrast", 0x0048, "H"),
    Info("Brightness", 0x004a, "H"),
    Info("Sharpness", 0x004c, "H"),
    Info("Saturation", 0x004e, "H"),
    Info("Infrared Illuminator", 0x0050, "H"),
    Info("Motion Sensitivity", 0x0052, "H"),
    Info("Battery Voltage", 0x0054, "H"),
    Info("User Label", 0x0056, "22s"),
]


def _unpack(makernote):
    global INFOS

    makernote_bin = array.array('B', makernote)

    res = {}
    for info in INFOS:
        res[info.name] = info.read(makernote_bin.tobytes())

    return res


def _read_im_exif(file_path):
    tags = None

    with open(file_path, 'rb') as f:
        tags = exifread.process_file(f)

    return _unpack(tags['EXIF MakerNote'].values)


def _make_exif_dict(image_path, file_name):
    """Create a dictionary with metadata extracted from the image file."""
    meta = _read_im_exif(image_path)

    s, m, h, M, D, Y = meta["Date/Time Original"]
    exif_dict = {
        "filename": file_name,
        "path": image_path,
        "set": 'none',
        "datetime": datetime.datetime(Y, M, D, h, m, s),
        "event1": meta["Event Number"][0],
        "event2": meta["Event Number"][1],
        "sequence_idx": meta["Sequence"][0],
        "sequence_max": meta["Sequence"][1],
        "ambient_temp": meta["Ambient Temperature"],
        "hour": h,
        "brightness": meta["Brightness"],
        "sharpness": meta["Sharpness"],
        "saturation": meta["Saturation"],
        "contrast": meta["Contrast"],
        "serial_no": "".join([chr(c) for c in meta["Serial Number"] if c != 0])
    }

    return exif_dict


def _check_duplicates(data: pandas.DataFrame):
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


def _extend_event_keys(data: pandas.DataFrame, window_secs=10):
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


def read_dir_metadata(dir_path: str, sort_vals=True):
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

    data = []
    for filename in os.listdir(dir_path):
        if filename.lower().endswith((".jpg", ".jpeg")):
            file_path = os.path.join(dir_path, filename)
            row = _make_exif_dict(file_path, filename)
            data.append(row)

    data = pandas.DataFrame(data)
    add_event_keys(data)

    if sort_vals:
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

                # append to existing data or create new if necessary
                data = set_data if data is None \
                    else pandas.concat([data, set_data], ignore_index=True)
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
                data = pandas.concat([data, set_data])

    _check_duplicates(data)

    # sort by the sortkey we constructed and break ties by filename
    data = data.sort_values(by=["sortkey", 'filename'])
    data["timeoffset"] = data.datetime.diff()

    if extend_events:
        _extend_event_keys(data)

    return data
