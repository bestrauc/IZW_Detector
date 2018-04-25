from PyQt5.QtWidgets import *

from gui_view import ExampleApp
import sys


import logging

log = logging.getLogger(__name__)

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(levelname)-7s - %(name)-10s - %(message)s")


def main():
    app = QApplication(sys.argv)
    form = ExampleApp()
    form.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
