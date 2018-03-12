import os
import pandas as pd
import keras.models

# import logging
# log = logging.getLogger(__name__)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '1'


class ImageClassifier:
    """The image classifier for the Reconxy images.

    The classifier detects a certain number of classes in the image,
    but at most one class per image currently (e.g. Cheetah or Leopard).
    """

    def __init__(self, model_path):
        """ Initialized the classifier with a Keras model.

        :param model_path: string
            Path to the Keras model file.
            The model should output a softmax activation of the classes.
        """

        # log.info("Initializing ImageClassifier")
        self.model = keras.models.load_model(model_path)

    def classify_data(self, data):
        """ Classify the data described by a Pandas dataframe.

        :param data: pandas.DataFrame
            A data frame with columns containing at least the following:
            file path - path to the image file
            simple_event_key - the event the image belongs to
            event_key - the extended event when 3-image events are merged

        :returns: pandas.DataFrame
            The data frame, with a new 'label' column.
        """

        return data

    def classify_directory(self, dir_path):
        """ Classify all image under this directory.

        Classifies images in this directory and subdirectories.

        :param dir_path: string
            Path to image root directory.
        :return: pandas.DataFrame
            Data frame with some image metadata, labels and image paths.
        """

        metadata = pd.DataFrame()

        return metadata