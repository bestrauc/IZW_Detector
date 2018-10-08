import sys

import grpc
import numpy
import tensorflow as tf

from tensorflow_serving.apis import predict_pb2
from tensorflow_serving.apis import prediction_service_pb2_grpc

import keras.backend as K
from keras.applications.inception_resnet_v2 import preprocess_input
from keras.preprocessing.image import ImageDataGenerator, load_img, img_to_array

from exif_utils import make_exif_dict

# the app flags functionality supposedly is not official, so use with care
# we only use it here because this is just a small demo server
tf.app.flags.DEFINE_string('server', '', 'PredictionService host:port')
tf.app.flags.DEFINE_string('image', '', 'Image to classify')
FLAGS = tf.app.flags.FLAGS

IMAGE_SHAPE = (299+20, 299+20, 3)
predict_generator = ImageDataGenerator()


def make_image_input_data(image_path):
    batch_x = numpy.zeros((1, 299 + 20, 299 + 20, 3),
                       dtype=K.floatx())
    batch_t = numpy.zeros((1,), dtype=K.floatx())
    batch_h = numpy.zeros((1,), dtype=K.floatx())

    image_meta = make_exif_dict(image_path, None)

    img = load_img(image_path, grayscale=False,
                   target_size=IMAGE_SHAPE)
    x = img_to_array(img)
    x = predict_generator.random_transform(x.astype(K.floatx()))
    x = predict_generator.standardize(x)

    batch_x[0] = x
    batch_t[0] = image_meta['ambient_temp']
    batch_h[0] = image_meta['hour']

    batch_x = batch_x[:, 10:-10, 10:-10, :]
    batch_x = [preprocess_input(batch_x),
               numpy.stack((batch_t, batch_h), axis=1)]

    return batch_x


def classify_image_rpc(hostport, image_path):
    batch = make_image_input_data(image_path)
    x = batch[0]
    image_meta = batch[1]

    channel = grpc.insecure_channel(hostport)

    stub = prediction_service_pb2_grpc.PredictionServiceStub(channel)
    request = predict_pb2.PredictRequest()
    request.model_spec.name = 'cheetah_inception'
    request.model_spec.signature_name = \
        tf.saved_model.signature_constants.DEFAULT_SERVING_SIGNATURE_DEF_KEY

    request.inputs['image'].CopyFrom(
        tf.contrib.util.make_tensor_proto(x,
                                          dtype=tf.float32,
                                          shape=[1, 299, 299, 3])
    )

    request.inputs['meta'].CopyFrom(
        tf.contrib.util.make_tensor_proto(image_meta,
                                          dtype=tf.float32,
                                          shape=[1, 2])
    )

    response = stub.Predict(request, 10.0)

    print(response)


def main(_):
    if not FLAGS.server:
        print("Please specify server host:port")
        return

    if not FLAGS.image:
        print("Please pass a camera trap image to classify")
        return

    classify_image_rpc(FLAGS.server, FLAGS.image)


if __name__ == '__main__':
    tf.app.run()
