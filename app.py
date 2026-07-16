import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication
from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    # GA Extractor — Game Archive Extractor
    QCoreApplication.setOrganizationName('GAExtractor')
    QCoreApplication.setApplicationName('GA Extractor')
    QCoreApplication.setApplicationVersion('0.12.7')
    app.setApplicationDisplayName('GA Extractor — Game Archive Extractor')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
