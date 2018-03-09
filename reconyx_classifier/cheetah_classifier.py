import sys
from data_utils.classifier import ImageClassifier


def main():
    args = sys.argv[1:]
    print("Hello %s", args)

    im_class = ImageClassifier(args[0])
    input("Press any key to continue.")


if __name__ == '__main__':
    main()
