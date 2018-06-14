import os
import pandas as pd
import numpy as np
import keras.backend as K
import keras.models
import keras.utils

from tensorflow import get_default_graph, Session, global_variables_initializer

from keras.applications.inception_resnet_v2 import preprocess_input
from keras.preprocessing.image import ImageDataGenerator, load_img, img_to_array

from typing import Generator, List, Callable

import logging
log = logging.getLogger("classifier")

# set TensorFlow log-level to warnings and above
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '1'

predict_generator = ImageDataGenerator()
target_im_size = (299 + 20, 299 + 20)


def data_to_matrix(data_batch):
    """Given a dataframe with image paths and metadata, convert to NN input."""
    batch_x = np.zeros((len(data_batch), 299 + 20, 299 + 20, 3),
                       dtype=K.floatx())
    batch_t = np.zeros((len(data_batch),), dtype=K.floatx())
    batch_h = np.zeros((len(data_batch),), dtype=K.floatx())

    for i, (key, row) in enumerate(data_batch.iterrows()):
        img = load_img(row['path'], grayscale=False,
                       target_size=target_im_size)
        x = img_to_array(img)
        x = predict_generator.random_transform(x.astype(K.floatx()))
        x = predict_generator.standardize(x)
        batch_x[i] = x
        batch_t[i] = row['ambient_temp']
        batch_h[i] = row['hour']

    batch_x = batch_x[:, 10:-10, 10:-10, :]
    batch_x = [preprocess_input(batch_x),
               np.stack((batch_t, batch_h), axis=1)]

    return batch_x


class ImageClassifier:
    """The image classifier for the Reconxy images.

    The classifier detects a certain number of classes in the image,
    but at most one class per image currently (e.g. Cheetah or Leopard).
    """

    def __init__(self, model_path: str, batch_size: int,
                 class_labels: List[str]):
        """Initialized the classifier with a Keras model.

        :param model_path: string
            Path to the Keras model file.
            The model should output a softmax activation of the classes.
        :param batch_size: int
            Batch size to use for classification.
        :param class_labels: List[str]
            Labels of the prediction, e.g. ['cheetah', 'leopard', 'unknown']
        """

        log.info("Loading model from '{}'".format(model_path))

        # store the session graph, else we get threading problems
        self.model = keras.models.load_model(model_path)
        self.model._make_predict_function()

        self.graph = get_default_graph()

        self.batch_size = batch_size
        self.class_labels = class_labels
        log.info("Model successfully loaded")

    def classify_data(self, data: pd.DataFrame,
                      classify_events: bool = False,
                      progress: Callable[[int], bool] = None) -> pd.DataFrame:
        """Classify the data described by a Pandas dataframe.

        :param data: pandas.DataFrame
            A data frame with columns containing at least the following:
            file path - path to the image file
            simple_event_key - the event the image belongs to
            event_key - the extended event when 3-image events are merged
        :param classify_events: bool
            Whether to classify images in an event together. Event-
            resolution classification uses the class with strongest
            prediction confidence in any image as the event label.

        :returns: pandas.DataFrame
            The data frame, with a new 'label' column.
        """

        log.info("Classifying DataFrame {}.".format(
            "WITH events" if classify_events else "WITHOUT events"
        ))

        # build a sequence of images+metadata from the DataFrame
        data_seq = DataFrameSequence(data, self.batch_size)

        all_preds = []
        # use the stored session graph to make predictions
        with self.graph.as_default():
                for batch_idx in range(len(data_seq)):
                    if progress and not progress((batch_idx*100)/len(data_seq)):
                        raise InterruptedError("Classification interrupted.")

                    batch = data_seq[batch_idx]
                    data_batch = data_to_matrix(batch)
                    preds = self.model.predict_on_batch(data_batch)
                    all_preds.extend(preds)

        data['predict_probs'] = all_preds

        # store the labels in the DataFrame. could just store indices
        # and resolve labels later, but for convenience we do it here
        if not classify_events:
            data['label'] = data['predict_probs'].apply(np.argmax)
        else:
            # event gets the label of the maximum confidence prediction
            group_label = lambda x: np.argmax(np.concatenate(x.tolist())) \
                                    % len(self.class_labels)

            data['label'] = data['predict_probs'].\
                            groupby(data['event_key_simple']).\
                            transform(group_label)

        return data

    @staticmethod
    def dataframe_generator(data: pd.DataFrame, batch_size: int) \
            -> Generator[List[np.ndarray], None, None]:
        """Generate classification input from the dataframe information.

        :param data: pandas.DataFrame
            The dataframe generated by the `read_dir_metadata` function.
        :param batch_size: int
            Number of images to process per batch.

        :returns: [numpy.matrix]
            A `batch_size x data_dimension` size list of input matrices.
        """

        for pos in range(0, len(data), batch_size):
            data_batch = data[pos:(pos + batch_size)]
            data_batch = data_to_matrix(data_batch)

            yield data_batch


class DataFrameSequence(keras.utils.Sequence):
    """Holds a sequence of classification derived from a dataframe."""

    def __init__(self, data: pd.DataFrame, batch_size: int):
        self.data = data
        self.batch_size = batch_size

    def __len__(self):
        return int(np.ceil(len(self.data) / float(self.batch_size)))

    def __getitem__(self, index):
        batch = self.data[index * self.batch_size:(index + 1) * self.batch_size]
        # data_batch = data_to_matrix(batch)

        return batch
