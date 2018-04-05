import struct
import array

import exifread
import datetime

import logging

# only ever log warnings from the external exifread library
logging.getLogger('exifread').setLevel(logging.WARN)


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

    # try:
    #     if str(tags['Image Make']) != 'RECONYX':
    #         raise ValueError("Not a RECONYX JPG file.")
    # except KeyError:
    #     print("Error path: {}".format(file_path))
    #     raise

    # a RECONYX file should have a MakerNote.
    return _unpack(tags['EXIF MakerNote'].values)


def make_exif_dict(image_path, file_name):
    """Create a dictionary with metadata extracted from the image file."""
    meta = _read_im_exif(image_path)

    s, m, h, M, D, Y = meta["Date/Time Original"]
    exif_dict = {
        "filename": file_name,
        "path": image_path,
        # "set": 'none',
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
