import os
import struct
import array

import exifread
import datetime

import pandas
import numpy as np


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


def unpack(makernote):
    global INFOS

    makernote_bin = array.array('B', makernote)

    res = {}
    for info in INFOS:
        res[info.name] = info.read(makernote_bin.tobytes())

    return res


def read_im_exif(file_path):
    tags = None

    with open(file_path, 'rb') as f:
        tags = exifread.process_file(f)

    return unpack(tags['EXIF MakerNote'].values)


def read_dir_metadata(dir_path, detect_dataset=True, extend_events=True):
    def add_event_keys(data):
        """ Add some unique keys to the rows.

        The key is serial+year+day+event2(+datetime), which can be used for sorting and grouping of trigger events.
        """
        data["event_key_simple"] = data.serial_no.astype(str) + "_" + \
                                   data.datetime.dt.year.astype(str) + "_" + \
                                   data.datetime.dt.dayofyear.astype(str) + "_" + \
                                   data.event2.astype(str)

        data["sortkey"] = data.event_key_simple.astype(str) + data.datetime.values.astype(np.int64).astype(str)

    def check_duplicates(data):
        # group into distinct events (usually 3 images per event)
        event_groups = data.groupby('event_key_simple')

        duplicate_col = np.zeros(data.shape[0], dtype=np.uint8)

        # for all events, check if there are duplicate images (i.e. duplicate sequnce_idx at the same time point)
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

    def extend_event_keys(data, window_secs=10):
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
                    (data.timeoffset.values[i] < np.timedelta64(window_secs, "s")) and \
                    (data.serial_no.values[i] == data.serial_no.values[i - 1]):

                current_key = last_key
            event_keys.append(current_key)
        data["event_key"] = event_keys

    data = []
    for root, dirs, files in os.walk(dir_path):
        print(root)

        dataset = 'none'
        if detect_dataset:
            if "train" in root:
                dataset = "train"
            elif "val" in root:
                dataset = "val"

        for file_path in files:
            lower = file_path.lower()
            name, ext = os.path.splitext(file_path)

            if ext not in ['.jpg', '.jpeg']:
                continue

            label = 'unknown'
            if 'leopard' in lower:
                label = 'leopard'
            elif 'cheetah' in lower:
                label = 'cheetah'

            full_file_path = root + '/' + file_path
            meta = read_im_exif(full_file_path)

            s, m, h, M, D, Y = meta["Date/Time Original"]
            row = {
                "path": full_file_path,
                "filename": file_path,
                "label": label,
                "set": dataset,
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
                # "serial_no": "".join([chr(c) for c in meta["Serial Number"] if c != "\x00"])
                "serial_no": "".join([chr(c) for c in meta["Serial Number"] if c != 0])
            }

            data.append(row)

    data = pandas.DataFrame(data)
    add_event_keys(data)
    check_duplicates(data)
    data = data.sort_values("sortkey")
    data["timeoffset"] = data.datetime.diff()

    if extend_events:
        extend_event_keys(data)

    return data
