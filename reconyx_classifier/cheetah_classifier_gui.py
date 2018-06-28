from PyQt5.QtWidgets import QApplication

from gui_view import ClassificationApp
import sys

import logging

log = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO,
                    handlers=[logging.FileHandler("classifier.log", mode="w"),
                              logging.StreamHandler(stream=sys.stdout)],
                    format="%(asctime)s - %(levelname)-7s"
                           " - %(name)-10s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")


def main():
    app = QApplication(sys.argv)
    form = ClassificationApp()
    form.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
