"""Join mode widget for analyzing and grouping file data."""

import os
import threading
from enum import Enum
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, 
    QTextEdit, QLabel, QComboBox, QMessageBox, QFileDialog, QProgressBar,
    QSplitter, QListWidgetItem
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut

from join.join import JoinMulti


class SortBy(Enum):
    """Sort options for groupings."""
    MOST_COMMON = 0
    ALPHANUMERIC = 1


def clean_filename(file_path):
    """Clean filename by removing common prefixes and extensions."""
    basename = os.path.basename(file_path)
    return basename.replace(
        "skyrim_", "").replace(
        "daggerfall_", "").replace(
        "modlist_", "").replace(
        ".txt", "")


class JoinWorker(QThread):
    """Worker thread for running join analysis."""
    finished = Signal()
    error = Signal(str)
    
    def __init__(self, file_list, parent=None):
        super().__init__(parent)
        self.file_list = file_list
        self.join = None
    
    def run(self):
        """Run the join analysis."""
        try:
            self.join = JoinMulti.remove_store()
            self.join = JoinMulti(self.file_list, similars=True, file_path_op=clean_filename)
            self.join.set_name()
            self.join.do_join()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class JoinModeWidget(QWidget):
    """Widget for join/grouping mode."""
    
    def __init__(self):
        super().__init__()
        self.join = JoinMulti.get_stored_or_new()
        if self.join is None:
            self.join = JoinMulti([])
        self.unconfirmed_groupings = {}
        self.groupings = {}
        self.unconfirmed_list_mode = False
        self.file_list = []
        self.worker = None
        
        self.init_ui()
        
        if self.join.restored:
            self.file_list = self.join.file_paths
            self.update_file_list_display()
            self.fill_grouping_lists()
            self.set_name()
    
    def init_ui(self):
        """Initialize the UI."""
        layout = QHBoxLayout(self)
        
        # Create splitter for resizable panes
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Left panel - Data lists
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # File list display
        file_list_label = QLabel("Added Files:")
        left_layout.addWidget(file_list_label)
        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(80)
        self.file_list_widget.setToolTip("Files added for analysis")
        left_layout.addWidget(self.file_list_widget)
        
        # List widgets
        self.u_listbox = QListWidget()
        self.u_listbox.setSelectionMode(QListWidget.ExtendedSelection)
        self.u_listbox.itemDoubleClicked.connect(self.show_info_unconfirmed_grouping)
        self.u_listbox.setVisible(False)
        # Keyboard shortcuts for unconfirmed groupings
        delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.u_listbox)
        delete_shortcut.activated.connect(self.remove_selected)
        merge_shortcut = QShortcut(QKeySequence("Shift+M"), self.u_listbox)
        merge_shortcut.activated.connect(self.merge_similars)
        
        self.g_listbox = QListWidget()
        self.g_listbox.itemDoubleClicked.connect(self.show_info_grouping)
        
        left_layout.addWidget(QLabel("Groupings:"))
        left_layout.addWidget(self.g_listbox)
        left_layout.addWidget(QLabel("Unconfirmed Groupings:"))
        left_layout.addWidget(self.u_listbox)
        
        splitter.addWidget(left_widget)
        
        # Right panel - Info and controls
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Info display
        info_label = QLabel("File Info:")
        right_layout.addWidget(info_label)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        right_layout.addWidget(self.info_text)
        
        # Buttons
        self.add_button = QPushButton("Add File")
        self.add_button.clicked.connect(self.add_file)
        self.add_button.setToolTip("Add files to analyze")
        right_layout.addWidget(self.add_button)
        
        self.run_join_button = QPushButton("Start Analysis")
        self.run_join_button.clicked.connect(self.do_join)
        self.run_join_button.setToolTip("Start the join analysis on added files")
        right_layout.addWidget(self.run_join_button)
        
        self.analysis_output_button = QPushButton("Analysis Output")
        self.analysis_output_button.clicked.connect(self.analysis_output)
        self.analysis_output_button.setToolTip("Generate analysis output file")
        right_layout.addWidget(self.analysis_output_button)
        
        self.store_button = QPushButton("Store Data")
        self.store_button.clicked.connect(self.store_data)
        self.store_button.setToolTip("Save current analysis state")
        right_layout.addWidget(self.store_button)
        
        self.reset_button = QPushButton("Reset Data")
        self.reset_button.clicked.connect(self.reset_data)
        self.reset_button.setToolTip("Clear all data and reset")
        right_layout.addWidget(self.reset_button)
        
        self.toggle_view_button = QPushButton("Toggle View Mode")
        self.toggle_view_button.clicked.connect(self.toggle_view_mode)
        self.toggle_view_button.setToolTip("Switch between confirmed and unconfirmed groupings view")
        right_layout.addWidget(self.toggle_view_button)
        
        # Unconfirmed grouping actions (only visible when in unconfirmed mode)
        unconfirmed_actions_layout = QHBoxLayout()
        self.merge_button = QPushButton("Merge Selected (Shift+M)")
        self.merge_button.clicked.connect(self.merge_similars)
        self.merge_button.setToolTip("Merge the selected unconfirmed grouping")
        self.merge_button.setEnabled(False)
        unconfirmed_actions_layout.addWidget(self.merge_button)
        
        self.remove_button = QPushButton("Remove Selected (Del)")
        self.remove_button.clicked.connect(self.remove_selected)
        self.remove_button.setToolTip("Remove the selected unconfirmed grouping")
        self.remove_button.setEnabled(False)
        unconfirmed_actions_layout.addWidget(self.remove_button)
        
        right_layout.addLayout(unconfirmed_actions_layout)
        
        # Update button states when selection changes
        self.u_listbox.itemSelectionChanged.connect(self.update_unconfirmed_button_states)
        
        # Sort options
        sort_label = QLabel("Sort for files in browsing mode:")
        right_layout.addWidget(sort_label)
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems([e.name for e in SortBy])
        self.sort_combo.setCurrentText(SortBy.MOST_COMMON.name)
        self.sort_combo.currentTextChanged.connect(self.set_sort_by)
        right_layout.addWidget(self.sort_combo)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        right_layout.addStretch()
        
        splitter.addWidget(right_widget)
        
        # Set splitter proportions
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
    
    def set_name(self):
        """Set the name based on file paths."""
        if not self.join.name or self.join.name == "" or self.join.name == "UNNAMED":
            self.join.set_name()
    
    def clear_listboxes(self):
        """Clear both list boxes."""
        self.u_listbox.clear()
        self.g_listbox.clear()
    
    def clear_info_text(self):
        """Clear the info text area."""
        self.info_text.clear()
    
    def add_file(self):
        """Add files via file dialog."""
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Select files", "", "All Files (*)"
        )
        added_count = 0
        for file_path in filenames:
            if file_path and file_path != "":
                if file_path not in self.file_list:  # Avoid duplicates
                    self.file_list.append(file_path)
                    added_count += 1
        
        if added_count > 0:
            self.join.file_paths = self.file_list
            self.set_name()
            self.update_file_list_display()
            QMessageBox.information(
                self, "Files Added",
                f"Added {added_count} file(s). Total: {len(self.file_list)}"
            )
        elif len(filenames) > 0:
            QMessageBox.information(
                self, "No New Files",
                "All selected files are already in the list."
            )
    
    def update_file_list_display(self):
        """Update the file list widget display."""
        self.file_list_widget.clear()
        for file_path in self.file_list:
            display_name = os.path.basename(file_path)
            item = QListWidgetItem(display_name)
            item.setToolTip(file_path)
            self.file_list_widget.addItem(item)
    
    def display_file_list(self):
        """Display the list of added files in info text (legacy method)."""
        self.clear_info_text()
        for filename in self.file_list:
            self.info_text.append(f"Added file: {filename}")
        # Also update the file list widget
        self.update_file_list_display()
    
    def show_info_unconfirmed_grouping(self, item):
        """Show info for unconfirmed grouping."""
        grouping_key = item.text()
        if grouping_key in self.unconfirmed_groupings:
            grouping = self.unconfirmed_groupings[grouping_key]
            self.show_text(str(grouping))
    
    def show_info_grouping(self, item):
        """Show info for confirmed grouping."""
        grouping_key = item.text()
        if grouping_key in self.groupings:
            grouping = self.groupings[grouping_key]
            self.show_text(str(grouping))
    
    def show_text(self, text):
        """Display text in info area."""
        self.info_text.setPlainText(text)
    
    def toggle_view_mode(self):
        """Toggle between confirmed and unconfirmed groupings view."""
        if self.unconfirmed_list_mode:
            self.u_listbox.setVisible(False)
            self.g_listbox.setVisible(True)
        else:
            self.g_listbox.setVisible(False)
            self.u_listbox.setVisible(True)
        self.unconfirmed_list_mode = not self.unconfirmed_list_mode
        self.update_unconfirmed_button_states()
    
    def do_join(self):
        """Start the join analysis."""
        if len(self.file_list) == 0:
            QMessageBox.information(
                self, "Unable to start analysis",
                "Files must be added before a join analysis can begin."
            )
            return
        
        if (self.join and self.join.restored and 
            QMessageBox.question(
                self, "Confirm Merge",
                "A stored merge already exists. Do you still want to run a merge?",
                QMessageBox.Yes | QMessageBox.No
            ) == QMessageBox.No):
            return
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        
        self.worker = JoinWorker(self.file_list)
        self.worker.finished.connect(self.on_join_finished)
        self.worker.error.connect(self.on_join_error)
        self.worker.start()
    
    def on_join_finished(self):
        """Handle join analysis completion."""
        self.join = self.worker.join
        self.progress_bar.setVisible(False)
        self.clear_listboxes()
        self.fill_grouping_lists()
        self.store_data()
    
    def on_join_error(self, error_msg):
        """Handle join analysis error."""
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Error", f"Join analysis failed: {error_msg}")
    
    def fill_grouping_lists(self):
        """Fill the grouping lists."""
        if self.join:
            for name, grouping in self.join.groupings.items():
                self.groupings[name] = grouping
                self.g_listbox.addItem(name)
            
            for unconfirmed_grouping in self.join.maybe_groupings:
                unconfirmed_grouping_key = unconfirmed_grouping.display_value()
                self.unconfirmed_groupings[unconfirmed_grouping_key] = unconfirmed_grouping
                self.u_listbox.addItem(unconfirmed_grouping_key)
            
            if self.join.has_unconfirmed_groupings():
                self.g_listbox.setVisible(False)
                self.u_listbox.setVisible(True)
                self.unconfirmed_list_mode = True
            else:
                self.u_listbox.setVisible(False)
                self.g_listbox.setVisible(True)
                self.unconfirmed_list_mode = False
            self.update_unconfirmed_button_states()
    
    def analysis_output(self):
        """Generate analysis output."""
        if self.join:
            self.join.grouping_output()
            self.join.find_common_uniques()
            QMessageBox.information(
                self, "Analysis Complete",
                "Analysis output has been written to the analysis file."
            )
    
    def set_sort_by(self, sort_name):
        """Set sorting method."""
        sort_by = SortBy[sort_name]
        self.g_listbox.clear()
        
        if sort_by == SortBy.ALPHANUMERIC:
            for grouping in sorted(self.groupings):
                self.g_listbox.addItem(grouping)
        elif sort_by == SortBy.MOST_COMMON:
            for grouping in self.join.groupings:
                self.g_listbox.addItem(grouping)
    
    def store_data(self):
        """Store the join data."""
        if self.join:
            self.join.store()
    
    def reset_data(self):
        """Reset all data."""
        reply = QMessageBox.question(
            self, "Confirm Reset",
            "Are you sure you want to reset?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.join = JoinMulti.remove_store()
            self.file_list = []
            self.unconfirmed_groupings = {}
            self.groupings = {}
            self.clear_listboxes()
            self.clear_info_text()
            self.file_list_widget.clear()
            self.update_unconfirmed_button_states()
    
    def update_unconfirmed_button_states(self):
        """Update the enabled state of unconfirmed grouping action buttons."""
        has_selection = len(self.u_listbox.selectedItems()) > 0
        self.merge_button.setEnabled(has_selection and self.unconfirmed_list_mode)
        self.remove_button.setEnabled(has_selection and self.unconfirmed_list_mode)
    
    def merge_similars(self):
        """Merge the selected unconfirmed grouping."""
        selected_items = self.u_listbox.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self, "No Selection",
                "Please select an unconfirmed grouping to merge."
            )
            return
        
        item = selected_items[0]
        unconfirmed_grouping_key = item.text()
        
        if not unconfirmed_grouping_key or unconfirmed_grouping_key == "":
            QMessageBox.warning(
                self, "Invalid Selection",
                "Selected grouping is invalid."
            )
            return
        
        if unconfirmed_grouping_key not in self.unconfirmed_groupings:
            QMessageBox.warning(
                self, "Not Found",
                f"Grouping '{unconfirmed_grouping_key}' not found."
            )
            return
        
        try:
            unconfirmed_grouping = self.unconfirmed_groupings[unconfirmed_grouping_key]
            merged_grouping = self.join.merge_similars(unconfirmed_grouping) if self.join else None
            
            if merged_grouping:
                # Remove from unconfirmed and add to confirmed
                self.remove_selected_item(item)
                self.groupings[merged_grouping.name] = merged_grouping
                self.g_listbox.addItem(merged_grouping.name)
                self.store_data()
                QMessageBox.information(
                    self, "Merge Successful",
                    f"Successfully merged grouping: {merged_grouping.name}"
                )
            else:
                QMessageBox.critical(
                    self, "Merge Failed",
                    f"Failed to merge grouping: {unconfirmed_grouping_key}"
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                f"Error merging grouping: {str(e)}"
            )
    
    def remove_selected(self):
        """Remove the selected unconfirmed grouping."""
        selected_items = self.u_listbox.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self, "No Selection",
                "Please select an unconfirmed grouping to remove."
            )
            return
        
        # Remove all selected items
        for item in selected_items:
            self.remove_selected_item(item)
        
        # Update the join's maybe_groupings list
        if self.join:
            self.join.maybe_groupings = [
                ug for ug in self.join.maybe_groupings
                if ug.display_value() in self.unconfirmed_groupings
            ]
        
        self.store_data()
        self.update_unconfirmed_button_states()
        
        # Auto-toggle to confirmed view if no unconfirmed groupings remain
        if len(self.unconfirmed_groupings) == 0:
            self.toggle_view_mode()
            QMessageBox.information(
                self, "All Processed",
                "All unconfirmed groupings have been processed."
            )
    
    def remove_selected_item(self, item):
        """Remove a specific item from unconfirmed groupings."""
        unconfirmed_grouping_key = item.text()
        
        if unconfirmed_grouping_key in self.unconfirmed_groupings:
            del self.unconfirmed_groupings[unconfirmed_grouping_key]
        
        row = self.u_listbox.row(item)
        self.u_listbox.takeItem(row)

