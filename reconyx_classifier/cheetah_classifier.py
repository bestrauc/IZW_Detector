import sys
import argparse

import logging


def parse_arguments():
    """ Parse the sys.argv command line arguments.
    :return: A NameSpace object with the parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Reconyx image classifier")
    optional = parser._action_groups.pop()
    required = parser.add_argument_group('required arguments')

    parser.add_argument(dest='directory',
                        help="Images to be classified.")

    required.add_argument('--model', required=True,
                          help="Stored Keras model to load for classification.")

    optional.add_argument('--batch_size', type=int, default=1,
                          metavar='N',
                          help="Batch size to use for classification.")

    optional.add_argument('--copy_output', action='store_true',
                          help="Copy classified images to output directories.")

    optional.add_argument('-v', '--verbose', help="Increase output verbosity.",
                          action='store_const', const=logging.DEBUG,
                          default=logging.INFO)

    parser._action_groups.append(optional)

    args = parser.parse_args()
    return args


def main():
    args = parse_arguments()

    log = logging.getLogger(__name__)
    logging.basicConfig(stream=sys.stdout, level=args.verbose)

    # import only after parsing to reduce startup delay
    from data_utils.classifier import ImageClassifier
    from data_utils.reader import read_dir_metadata

    log.info("Loading model from '{}'".format(args.model))
    try:
        im_class = ImageClassifier(args.model, args.batch_size,
                                   ['unknown', 'cheetah', 'leopard'])
        log.info("Model successfully loaded")
    except OSError as err:
        log.error("OS error: {}".format(err))
        sys.exit(1)

    log.info("Classifying images in '{}'".format(args.directory))
    data = read_dir_metadata(args.directory)
    print(data.head(20))
    print("================")
    im_class.classify_data(data)

    print(data.head(20))
    print("================")
    # input("Press any key to continue.")


if __name__ == '__main__':
    main()
