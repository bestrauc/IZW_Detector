import sys
import os
import argparse

import logging

log = logging.getLogger(__name__)

default_labels = ['unknown', 'cheetah', 'leopard']


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
    logging.basicConfig(stream=sys.stdout, level=args.verbose,
                        format="%(levelname)-7s - %(name)-10s - %(message)s")

    # import only after parsing to reduce startup delay
    from data_utils.classifier import ImageClassifier
    from data_utils.io import read_dir_metadata, classification_to_dir

    log.info("Initializing ImageClassifier")
    try:
        im_class = ImageClassifier(args.model, args.batch_size,
                                   default_labels)
    except OSError as err:
        log.error("OS error: {}".format(err))
        sys.exit(1)

    log.info("Classifying images in '{}'".format(args.directory))
    data = read_dir_metadata(args.directory)
    im_class.classify_data(data)

    print()

    if args.copy_output:
        classified_path = args.directory.rstrip('/\\') + '_classified'
        log.info("Creating dir '{}'".format(classified_path))
        try:
            os.mkdir(classified_path)
        except FileExistsError:
            log.error("Directory '{}' already exists.".format(
                os.path.basename(os.path.normpath(classified_path))
            ))
            return

        classification_to_dir(classified_path, data, default_labels)


if __name__ == '__main__':
    main()
