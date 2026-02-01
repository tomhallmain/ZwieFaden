"""Dark theme configuration for the PySide6 application."""

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor


def apply_dark_theme(app: QApplication):
    """Apply a dark theme to the application."""
    # Set Fusion style for better theme support
    app.setStyle('Fusion')
    
    # Create dark palette
    palette = QPalette()
    
    # Window colors
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    
    # Base colors (for input widgets)
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    
    # Text colors
    palette.setColor(QPalette.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    
    # Button colors
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    
    # Highlight colors (for selections)
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    
    # Disabled colors
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(127, 127, 127))
    
    # Tooltip colors
    palette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    
    # Link colors
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.LinkVisited, QColor(130, 42, 218))
    
    app.setPalette(palette)
    
    # Additional dark stylesheet for better appearance
    dark_stylesheet = """
        QMainWindow {
            background-color: #353535;
        }
        QWidget {
            background-color: #353535;
            color: #ffffff;
        }
        QPushButton {
            background-color: #454545;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 5px;
            min-width: 80px;
        }
        QPushButton:hover {
            background-color: #555555;
            border: 1px solid #666666;
        }
        QPushButton:pressed {
            background-color: #353535;
        }
        QPushButton:checked {
            background-color: #2a82da;
            border: 1px solid #2a82da;
        }
        QListWidget {
            background-color: #232323;
            border: 1px solid #555555;
            border-radius: 4px;
        }
        QListWidget::item {
            padding: 4px;
        }
        QListWidget::item:selected {
            background-color: #2a82da;
            color: #ffffff;
        }
        QListWidget::item:hover {
            background-color: #454545;
        }
        QTextEdit, QTextEdit:focus {
            background-color: #232323;
            border: 1px solid #555555;
            border-radius: 4px;
            color: #ffffff;
        }
        QComboBox {
            background-color: #454545;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 4px;
            min-width: 100px;
        }
        QComboBox:hover {
            background-color: #555555;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid #ffffff;
            margin-right: 5px;
        }
        QComboBox QAbstractItemView {
            background-color: #454545;
            border: 1px solid #555555;
            selection-background-color: #2a82da;
            color: #ffffff;
        }
        QLabel {
            color: #ffffff;
        }
        QProgressBar {
            background-color: #232323;
            border: 1px solid #555555;
            border-radius: 4px;
            text-align: center;
            color: #ffffff;
        }
        QProgressBar::chunk {
            background-color: #2a82da;
            border-radius: 3px;
        }
        QSplitter::handle {
            background-color: #555555;
        }
        QSplitter::handle:horizontal {
            width: 3px;
        }
        QSplitter::handle:vertical {
            height: 3px;
        }
    """
    app.setStyleSheet(dark_stylesheet)

