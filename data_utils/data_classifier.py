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



if __name__ == '__main__':
    print("Mane")