"""Main PySide6 application with multiple modes."""

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget
from PySide6.QtGui import QKeySequence

from modes.join_mode import JoinModeWidget
from modes.diff_mode import DiffModeWidget
from ui.theme import apply_dark_theme
from utils.app_info_cache import app_info_cache
from utils.constants import AppMode
from utils.logging_setup import get_logger

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Main application window with mode switching."""
    LAST_MODE_CACHE_KEY = "last_mode"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Analysis & Diff Tool")
        self.setGeometry(100, 100, 1400, 900)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create mode selector buttons (Diff left, Join right)
        mode_layout = QHBoxLayout()
        self.diff_mode_btn = QPushButton("Diff Mode")
        self.join_mode_btn = QPushButton("Join Mode")

        self.diff_mode_btn.setCheckable(True)
        self.join_mode_btn.setCheckable(True)

        self.diff_mode_btn.clicked.connect(lambda: self.switch_mode(AppMode.DIFF))
        self.join_mode_btn.clicked.connect(lambda: self.switch_mode(AppMode.JOIN))

        mode_layout.addWidget(self.diff_mode_btn)
        mode_layout.addWidget(self.join_mode_btn)
        mode_layout.addStretch()

        main_layout.addLayout(mode_layout)

        # Create stacked widget for modes (index 0 = Join, 1 = Diff)
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        self.join_widget = JoinModeWidget()
        self.diff_widget = DiffModeWidget()

        self.stacked_widget.addWidget(self.join_widget)
        self.stacked_widget.addWidget(self.diff_widget)

        # Initial mode: cached last mode, or Diff by default
        cached = app_info_cache.get(self.LAST_MODE_CACHE_KEY, AppMode.DIFF)
        initial_mode = AppMode.get(cached)
        self.stacked_widget.setCurrentIndex(int(initial_mode))
        self.diff_mode_btn.setChecked(initial_mode == AppMode.DIFF)
        self.join_mode_btn.setChecked(initial_mode == AppMode.JOIN)

        # Keyboard shortcuts
        self.diff_mode_btn.setShortcut(QKeySequence("Ctrl+1"))
        self.join_mode_btn.setShortcut(QKeySequence("Ctrl+2"))

    def switch_mode(self, mode: AppMode):
        """Switch between modes and cache selection."""
        self.stacked_widget.setCurrentIndex(int(mode))
        self.diff_mode_btn.setChecked(mode == AppMode.DIFF)
        self.join_mode_btn.setChecked(mode == AppMode.JOIN)
        app_info_cache.set(self.LAST_MODE_CACHE_KEY, int(mode))


def main():
    """Main entry point."""
    app = QApplication(sys.argv)

    def save_cache_on_quit():
        try:
            app_info_cache.store()
        except Exception as e:
            logger.warning("Failed to save app cache on exit: %s", e)

    app.aboutToQuit.connect(save_cache_on_quit)

    apply_dark_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

