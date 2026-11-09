"""Diff mode widget for comparing code files."""

import os
import hashlib
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QTextEdit, QLabel, QComboBox, QCheckBox, QMessageBox, QFileDialog, QSplitter,
    QTabWidget, QProgressBar, QListWidgetItem, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, QThread, Signal

from diff.diff_engine import DiffEngine, DiffType, FileMetadata
from diff.llm_analyzer import DiffLLMAnalyzer
from modes.project_compare_widget import ProjectCompareTab
from ui.formatting import markdown_to_html, DiffHighlighter
from utils.app_info_cache import app_info_cache
from utils.translations import _



class LLMAnalysisWorker(QThread):
    """Worker thread for running LLM analysis."""
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, llm_analyzer, files_content, file_metadata, diff_matrix, target_context, requirements, parent=None):
        super().__init__(parent)
        self.llm_analyzer = llm_analyzer
        self.files_content = files_content
        self.file_metadata = file_metadata
        self.diff_matrix = diff_matrix
        self.target_context = target_context
        self.requirements = requirements
    
    def run(self):
        """Run the LLM analysis."""
        try:
            result = self.llm_analyzer.analyze_versions(
                self.files_content, self.file_metadata, self.diff_matrix,
                self.target_context, self.requirements
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class LLMGenerationWorker(QThread):
    """Worker thread for running LLM code generation."""
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, llm_analyzer, files_content, file_metadata, diff_matrix, target_context, requirements, base_file_index, parent=None):
        super().__init__(parent)
        self.llm_analyzer = llm_analyzer
        self.files_content = files_content
        self.file_metadata = file_metadata
        self.diff_matrix = diff_matrix
        self.target_context = target_context
        self.requirements = requirements
        self.base_file_index = base_file_index
    
    def run(self):
        """Run the LLM code generation."""
        try:
            result = self.llm_analyzer.generate_merged_version(
                self.files_content, self.file_metadata, self.diff_matrix,
                self.target_context, self.requirements, self.base_file_index
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DiffTextEdit(QTextEdit):
    """Diff text box with an extra copy action."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def contextMenuEvent(self, event):
        """Extend context menu with an optional strip-prefix copy action."""
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        menu.addAction(_("Copy (Strip First Column)"), self.copy_strip_first_column)
        menu.exec(event.globalPos())

    def copy_strip_first_column(self):
        """Copy selected text with first character removed from each line."""
        selected_text = self.textCursor().selectedText()
        if not selected_text:
            return

        # QTextEdit selections use Unicode paragraph separator for line breaks.
        lines = selected_text.split('\u2029')
        processed_lines = [(line[1:] if line else line) for line in lines]
        QApplication.clipboard().setText('\n'.join(processed_lines))


class DiffModeWidget(QWidget):
    """Widget for diff mode."""
    SESSION_FILES_CACHE_KEY = "diff_mode_current_files"
    LAST_DIRECTORY_CACHE_KEY = "diff_mode_last_directory"
    HIGHLIGHT_WHITESPACE_CACHE_KEY = "diff_mode_highlight_whitespace"
    GROUPING_HISTORY_CACHE_KEY = "diff_mode_grouping_history"
    GROUPING_HISTORY_MAX_ENTRIES = 30
    
    def __init__(self):
        super().__init__()
        self.diff_engine = DiffEngine()
        self.current_diff_lines = []
        self.llm_analyzer = DiffLLMAnalyzer()
        self.llm_analysis_worker = None
        self.llm_generation_worker = None
        self.last_selected_directory = app_info_cache.get(self.LAST_DIRECTORY_CACHE_KEY, "")
        self.init_ui()
        self._restore_cached_diff_session()
    
    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        
        # Top panel - controls (split across two rows for readability)
        top_panel = QWidget()
        self.top_panel = top_panel
        top_layout = QVBoxLayout(top_panel)
        row_one_layout = QHBoxLayout()
        row_two_layout = QHBoxLayout()
        
        self.add_file_button = QPushButton(_("Add File"))
        self.add_file_button.clicked.connect(self.add_file)
        row_one_layout.addWidget(self.add_file_button)
        
        self.remove_file_button = QPushButton(_("Remove Selected"))
        self.remove_file_button.clicked.connect(self.remove_selected_files)
        self.remove_file_button.setToolTip(_("Remove selected file(s) from current diff set"))
        row_one_layout.addWidget(self.remove_file_button)

        self.move_up_button = QPushButton("↑")
        self.move_up_button.clicked.connect(self.move_selected_files_up)
        self.move_up_button.setToolTip(_("Move selected file(s) up"))
        row_one_layout.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("↓")
        self.move_down_button.clicked.connect(self.move_selected_files_down)
        self.move_down_button.setToolTip(_("Move selected file(s) down"))
        row_one_layout.addWidget(self.move_down_button)

        self.clear_files_button = QPushButton(_("Clear Files"))
        self.clear_files_button.clicked.connect(self.clear_files)
        row_one_layout.addWidget(self.clear_files_button)

        self.refresh_files_button = QPushButton(_("Refresh Files"))
        self.refresh_files_button.clicked.connect(self.refresh_files)
        self.refresh_files_button.setToolTip(_("Reload file contents from disk and rerun diff"))
        row_one_layout.addWidget(self.refresh_files_button)
        
        row_one_layout.addWidget(QLabel(_("Compare:")))
        
        self.file_a_combo = QComboBox()
        self.file_a_combo.currentIndexChanged.connect(self.update_diff)
        row_one_layout.addWidget(self.file_a_combo)
        
        row_one_layout.addWidget(QLabel(_("vs")))
        
        self.file_b_combo = QComboBox()
        self.file_b_combo.currentIndexChanged.connect(self.update_diff)
        row_one_layout.addWidget(self.file_b_combo)
        row_one_layout.addStretch()

        row_two_layout.addWidget(QLabel(_("Saved Grouping:")))
        self.grouping_history_combo = QComboBox()
        self.grouping_history_combo.setMinimumWidth(320)
        self.grouping_history_combo.setToolTip(_("Load a previously used file grouping"))
        row_two_layout.addWidget(self.grouping_history_combo)

        self.load_grouping_button = QPushButton(_("Load Grouping"))
        self.load_grouping_button.clicked.connect(self.load_selected_grouping)
        row_two_layout.addWidget(self.load_grouping_button)

        self.save_grouping_button = QPushButton(_("Save Grouping"))
        self.save_grouping_button.clicked.connect(self.save_current_grouping_to_history)
        self.save_grouping_button.setToolTip(_("Store current file grouping for later quick restore"))
        row_two_layout.addWidget(self.save_grouping_button)
        
        self.unified_diff_button = QPushButton(_("Show Unified Diff"))
        self.unified_diff_button.clicked.connect(self.show_unified_diff)
        row_two_layout.addWidget(self.unified_diff_button)
        
        self.html_diff_button = QPushButton(_("Show HTML Diff"))
        self.html_diff_button.clicked.connect(self.show_html_diff)
        row_two_layout.addWidget(self.html_diff_button)

        self.highlight_whitespace_checkbox = QCheckBox(_("Highlight Whitespace-Only Diffs"))
        self.highlight_whitespace_checkbox.setChecked(
            bool(app_info_cache.get(self.HIGHLIGHT_WHITESPACE_CACHE_KEY, False))
        )
        self.highlight_whitespace_checkbox.setToolTip(
            _("When disabled, trailing/blank-line whitespace-only changes are not highlighted.")
        )
        self.highlight_whitespace_checkbox.stateChanged.connect(self._on_whitespace_highlight_changed)
        row_two_layout.addWidget(self.highlight_whitespace_checkbox)

        row_two_layout.addStretch()
        top_layout.addLayout(row_one_layout)
        top_layout.addLayout(row_two_layout)
        
        layout.addWidget(top_panel)
        
        # File list
        file_list_label = QLabel(_("Added Files:"))
        self.file_list_label = file_list_label
        layout.addWidget(file_list_label)
        
        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(100)
        self.file_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list_widget.setToolTip(_("Files added for comparison. Shows filename and directory context."))
        layout.addWidget(self.file_list_widget)
        
        # Main diff display
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side - Line-by-line diff
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.diff_section_label = QLabel(_("Line-by-Line Diff:"))
        left_layout.addWidget(self.diff_section_label)
        
        self.diff_text = DiffTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setFontFamily("Courier")
        self.highlighter = DiffHighlighter(self.diff_text.document())
        left_layout.addWidget(self.diff_text)
        
        splitter.addWidget(left_widget)
        
        # Right side - Side-by-side comparison
        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)
        
        # File A display
        file_a_layout = QVBoxLayout()
        self.file_a_label = QLabel(_("File A:"))
        file_a_layout.addWidget(self.file_a_label)
        
        self.file_a_text = QTextEdit()
        self.file_a_text.setReadOnly(True)
        self.file_a_text.setFontFamily("Courier")
        file_a_layout.addWidget(self.file_a_text)
        
        # File B display
        file_b_layout = QVBoxLayout()
        self.file_b_label = QLabel(_("File B:"))
        file_b_layout.addWidget(self.file_b_label)
        
        self.file_b_text = QTextEdit()
        self.file_b_text.setReadOnly(True)
        self.file_b_text.setFontFamily("Courier")
        file_b_layout.addWidget(self.file_b_text)
        
        right_layout.addLayout(file_a_layout)
        right_layout.addLayout(file_b_layout)
        
        splitter.addWidget(right_widget)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        # Create tabbed interface
        tabs = QTabWidget()
        self.tabs = tabs
        self.diff_view_tab_index = tabs.addTab(splitter, _("Diff View"))

        # LLM Analysis tab
        llm_tab = self.create_llm_analysis_tab()
        tabs.addTab(llm_tab, _("LLM Analysis"))

        # File Grouping tab
        grouping_tab = self.create_file_grouping_tab()
        tabs.addTab(grouping_tab, _("File Grouping"))

        # Request History tab
        history_tab = self.create_request_history_tab()
        tabs.addTab(history_tab, _("Request History"))

        # Project Compare tab
        self.project_compare_tab = ProjectCompareTab(self._open_pair_in_diff_view)
        self.project_compare_tab_index = tabs.addTab(self.project_compare_tab, _("Project Compare"))

        # The top toolbar and file list operate on the current diff file set,
        # which Project Compare doesn't use (it works on two whole project
        # directories instead) -- hide them there so they don't sit around
        # looking actionable while doing nothing.
        tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(tabs)
        self.update_grouping_history_combo()

    def _on_tab_changed(self, index: int):
        """Show/hide the file-list toolbar based on whether it applies to the active tab."""
        applies_to_tab = index != self.project_compare_tab_index
        self.top_panel.setVisible(applies_to_tab)
        self.file_list_label.setVisible(applies_to_tab)
        self.file_list_widget.setVisible(applies_to_tab)

    def _open_pair_in_diff_view(self, path_a: str, path_b: str):
        """Load a file pair (e.g. from Project Compare) into the Diff View tab."""
        self.diff_engine.clear_files()
        self.file_list_widget.clear()
        for filepath in (path_a, path_b):
            try:
                self._add_file_to_engine_and_list(filepath)
            except Exception as e:
                QMessageBox.critical(self, _("Error"), _("Failed to add file: {0}").format(str(e)))
                return
        self.update_file_combos()
        self.update_base_file_combo()
        self.update_file_groups()
        self.last_selected_directory = os.path.dirname(path_a) or self.last_selected_directory
        self._cache_current_diff_session()
        self.tabs.setCurrentIndex(self.diff_view_tab_index)
    
    def add_file(self):
        """Add a file to compare."""
        start_directory = self._get_dialog_start_directory()
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self, _("Select file to compare"), start_directory, _("All Files (*)")
        )
        if filename:
            try:
                self._add_file_to_engine_and_list(filename)
                self.last_selected_directory = os.path.dirname(filename) or self.last_selected_directory
                self.update_file_combos()
                self.update_base_file_combo()
                self.update_file_groups()  # Update grouping tab
                self._cache_current_diff_session()
                dir_context = os.path.dirname(filename) or "."
                QMessageBox.information(self, _("Success"), _("Added file: {0}\nFrom: {1}").format(os.path.basename(filename), dir_context))
            except Exception as e:
                QMessageBox.critical(self, _("Error"), _("Failed to add file: {0}").format(str(e)))
    
    def clear_files(self):
        """Clear all added files."""
        reply = QMessageBox.question(
            self, _("Confirm Clear"),
            _("Are you sure you want to clear all files?"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.diff_engine.clear_files()
            self.file_list_widget.clear()
            self.file_a_combo.clear()
            self.file_b_combo.clear()
            self.base_file_combo.clear()
            self.diff_text.clear()
            self.file_a_text.clear()
            self.file_b_text.clear()
            self.analysis_results.clear()
            self.generated_code.clear()
            self.update_file_groups()  # Update grouping tab
            self._set_no_diff_indicator(False)
            self._cache_current_diff_session()

    def remove_selected_files(self):
        """Remove selected files from the current diff grouping."""
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, _("Remove Selected"), _("Select one or more files to remove."))
            return

        selected_paths = {
            item.toolTip()
            for item in selected_items
            if item.toolTip()
        }
        current_paths = self.diff_engine.get_file_names()
        remaining_paths = [path for path in current_paths if path not in selected_paths]
        removed_count = len(current_paths) - len(remaining_paths)
        if removed_count <= 0:
            return

        self._apply_file_grouping(remaining_paths)

    def move_selected_files_up(self):
        """Move selected files up in grouping order."""
        self._reorder_selected_files(direction=-1)

    def move_selected_files_down(self):
        """Move selected files down in grouping order."""
        self._reorder_selected_files(direction=1)

    def _reorder_selected_files(self, direction: int):
        """Reorder selected files by one step up/down."""
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            return

        paths = self.diff_engine.get_file_names()
        if len(paths) < 2:
            return

        selected_indices = sorted(self.file_list_widget.row(item) for item in selected_items)
        selected_paths = [paths[i] for i in selected_indices if 0 <= i < len(paths)]
        if not selected_paths:
            return

        reordered = list(paths)
        if direction < 0:
            for idx in selected_indices:
                if idx > 0 and (idx - 1) not in selected_indices:
                    reordered[idx - 1], reordered[idx] = reordered[idx], reordered[idx - 1]
        else:
            for idx in reversed(selected_indices):
                if idx < len(reordered) - 1 and (idx + 1) not in selected_indices:
                    reordered[idx + 1], reordered[idx] = reordered[idx], reordered[idx + 1]

        if reordered == paths:
            return

        self._apply_file_grouping(
            reordered,
            select_paths=set(selected_paths),
            preserve_selected_paths=False
        )

    def refresh_files(self):
        """Reload current files from disk and rerun the selected diff."""
        current_paths = self.diff_engine.get_file_names()
        if not current_paths:
            QMessageBox.information(self, _("Refresh Files"), _("No files to refresh."))
            return

        # Preserve current pair selection by file path.
        selected_a_path = self._get_selected_combo_file_path(self.file_a_combo)
        selected_b_path = self._get_selected_combo_file_path(self.file_b_combo)

        existing_paths = []
        missing_paths = []
        for path in current_paths:
            if os.path.exists(path):
                existing_paths.append(path)
            else:
                missing_paths.append(path)

        # Reload file contents and metadata from disk.
        self.diff_engine.clear_files()
        self.file_list_widget.clear()
        for filepath in existing_paths:
            self._add_file_to_engine_and_list(filepath)

        self.update_file_combos()
        self.update_base_file_combo()

        # Restore selection when possible.
        self._set_combo_selection_by_path(self.file_a_combo, selected_a_path)
        self._set_combo_selection_by_path(self.file_b_combo, selected_b_path)
        self.update_diff()
        if existing_paths:
            self.last_selected_directory = os.path.dirname(existing_paths[0]) or self.last_selected_directory
        self._cache_current_diff_session()

        if missing_paths:
            QMessageBox.warning(
                self,
                _("Refresh Files"),
                _("Some files could not be refreshed because they no longer exist:\n{0}").format("\n".join(missing_paths))
            )

        if not existing_paths:
            return

        if self._has_cached_analysis_for_paths(existing_paths):
            reply = QMessageBox.question(
                self,
                _("Rerun Analysis?"),
                _("A previous LLM analysis exists for this same file grouping.\n"
                "Do you want to rerun analysis with the refreshed file contents?"),
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.run_llm_analysis()

    def _get_selected_combo_file_path(self, combo: QComboBox):
        """Get selected file path from combo tooltip data."""
        index = combo.currentIndex()
        if index < 0:
            return None
        return combo.itemData(index, Qt.ToolTipRole)

    def _set_combo_selection_by_path(self, combo: QComboBox, file_path: str):
        """Select combo item by file path, if present."""
        if not file_path:
            return
        for idx in range(combo.count()):
            item_path = combo.itemData(idx, Qt.ToolTipRole)
            if item_path == file_path:
                combo.setCurrentIndex(idx)
                return

    def _has_cached_analysis_for_paths(self, file_paths: list) -> bool:
        """Return True if cached analysis exists for the exact same file path grouping."""
        if not file_paths:
            return False
        normalized_current = sorted(os.path.normcase(path) for path in file_paths)
        cache_key = 'diff_mode_llm_history'
        history = app_info_cache.get(cache_key, {})
        if not isinstance(history, dict):
            return False

        for entry in history.values():
            if entry.get('request_type') != 'analysis':
                continue
            cached_paths = entry.get('file_paths', [])
            if not cached_paths:
                continue
            if not all(os.path.exists(path) for path in cached_paths):
                continue
            normalized_cached = sorted(os.path.normcase(path) for path in cached_paths)
            if normalized_cached == normalized_current:
                return True
        return False

    def _get_dialog_start_directory(self) -> str:
        """Return the best directory to open file dialogs."""
        if self.last_selected_directory and os.path.isdir(self.last_selected_directory):
            return self.last_selected_directory
        cached_dir = app_info_cache.get(self.LAST_DIRECTORY_CACHE_KEY, "")
        if cached_dir and os.path.isdir(cached_dir):
            return cached_dir
        return os.getcwd()

    def _add_file_to_engine_and_list(self, filepath: str):
        """Add file to diff engine and visible list."""
        self.diff_engine.add_file(filepath)
        dir_context = os.path.dirname(filepath) or "."
        display_name = f"{os.path.basename(filepath)} ({dir_context})"
        item = QListWidgetItem(display_name)
        item.setToolTip(filepath)
        self.file_list_widget.addItem(item)

    def _apply_file_grouping(
        self,
        file_paths: list,
        select_paths: set = None,
        preserve_selected_paths: bool = True
    ):
        """Replace current files with provided grouping paths."""
        selected_a_path = self._get_selected_combo_file_path(self.file_a_combo)
        selected_b_path = self._get_selected_combo_file_path(self.file_b_combo)
        self.diff_engine.clear_files()
        self.file_list_widget.clear()

        existing_paths = []
        for filepath in file_paths:
            if not isinstance(filepath, str) or not os.path.exists(filepath):
                continue
            try:
                self._add_file_to_engine_and_list(filepath)
                existing_paths.append(filepath)
            except Exception:
                continue

        self.update_file_combos()
        if preserve_selected_paths:
            self._set_combo_selection_by_path(self.file_a_combo, selected_a_path)
            self._set_combo_selection_by_path(self.file_b_combo, selected_b_path)
        self.update_base_file_combo()
        self.update_file_groups()
        self.update_diff()
        if select_paths:
            for idx in range(self.file_list_widget.count()):
                item = self.file_list_widget.item(idx)
                if item.toolTip() in select_paths:
                    item.setSelected(True)
        if existing_paths:
            self.last_selected_directory = os.path.dirname(existing_paths[0]) or self.last_selected_directory
        self._cache_current_diff_session()

    def save_current_grouping_to_history(self):
        """Manually store the current file grouping for quick reload."""
        file_paths = self.diff_engine.get_file_names()
        if not file_paths:
            QMessageBox.information(self, _("Save Grouping"), _("No files in current grouping to save."))
            return
        self._cache_file_grouping_history(file_paths)
        self._cache_current_diff_session()
        QMessageBox.information(
            self,
            _("Grouping Saved"),
            _("Saved grouping with {0} file(s).").format(len(file_paths))
        )

    def load_selected_grouping(self):
        """Load file grouping selected in the saved-grouping combo."""
        entry_id = self.grouping_history_combo.currentData()
        if not entry_id:
            QMessageBox.information(self, _("Load Grouping"), _("No saved grouping selected."))
            return

        history = app_info_cache.get(self.GROUPING_HISTORY_CACHE_KEY, {})
        entry = history.get(entry_id) if isinstance(history, dict) else None
        if not entry:
            QMessageBox.warning(self, _("Load Grouping"), _("Saved grouping entry was not found."))
            return

        file_paths = entry.get("file_paths", [])
        if not file_paths:
            QMessageBox.warning(self, _("Load Grouping"), _("Saved grouping has no files."))
            return

        reply = QMessageBox.question(
            self,
            _("Load Saved Grouping"),
            _("This will replace your current files with {0} saved file(s).\nContinue?").format(len(file_paths)),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._apply_file_grouping(file_paths)

    def update_grouping_history_combo(self):
        """Refresh the saved-grouping combo entries."""
        if not hasattr(self, "grouping_history_combo"):
            return

        self.grouping_history_combo.clear()
        self.grouping_history_combo.addItem(_("Select saved grouping..."), None)

        history = app_info_cache.get(self.GROUPING_HISTORY_CACHE_KEY, {})
        if not isinstance(history, dict) or not history:
            return

        sorted_entries = sorted(
            history.items(),
            key=lambda x: x[1].get("timestamp", ""),
            reverse=True
        )
        for entry_id, entry in sorted_entries:
            paths = entry.get("file_paths", [])
            if not paths:
                continue
            timestamp = entry.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(timestamp)
                stamp = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                stamp = timestamp or _("unknown time")
            short_label, full_label = self._build_grouping_display_labels(paths, max_items=3)
            display_text = self._truncate_text(_("[{0}] {1} file(s): {2}").format(stamp, len(paths), short_label), 120)
            self.grouping_history_combo.addItem(display_text, entry_id)
            self.grouping_history_combo.setItemData(
                self.grouping_history_combo.count() - 1,
                _("[{0}] {1} file(s): {2}").format(stamp, len(paths), full_label),
                Qt.ToolTipRole
            )

    def _truncate_text(self, text: str, max_len: int) -> str:
        """Truncate long display text while preserving readability."""
        if len(text) <= max_len:
            return text
        return text[:max_len - 1] + "…"

    def _build_grouping_path_labels(self, paths: list) -> dict:
        """Build path labels with uncommon directory context for duplicate basenames."""
        labels = {}
        by_basename = {}
        for path in paths:
            basename = os.path.basename(path)
            by_basename.setdefault(basename, []).append(path)

        for basename, group_paths in by_basename.items():
            if len(group_paths) == 1:
                labels[group_paths[0]] = basename
                continue
            for path in group_paths:
                context = self._find_uncommon_directory_context(path, group_paths)
                labels[path] = f"{basename} ({context})" if context else basename
        return labels

    def _build_grouping_display_labels(self, paths: list, max_items: int = 3):
        """
        Build short/full grouping labels.
        If all basenames are identical, display basename once with uncommon directory specifiers.
        """
        if not paths:
            return "", ""

        basenames = [os.path.basename(path) for path in paths]
        if len(set(basenames)) == 1:
            basename = basenames[0]
            contexts = []
            for path in paths:
                context = self._find_uncommon_directory_context(path, paths)
                if not context:
                    context = os.path.dirname(path) or "."
                if context not in contexts:
                    contexts.append(context)
            shown_contexts = contexts[:max_items]
            short_label = f"{basename} ({', '.join(shown_contexts)})"
            if len(contexts) > max_items:
                short_label += f" (+{len(contexts) - max_items})"
            full_label = f"{basename} ({', '.join(contexts)})"
            return short_label, full_label

        labels_by_path = self._build_grouping_path_labels(paths)
        shown_paths = paths[:max_items]
        short_label = ", ".join(labels_by_path.get(path, os.path.basename(path)) for path in shown_paths)
        if len(paths) > max_items:
            short_label += f" (+{len(paths) - max_items})"
        full_label = ", ".join(labels_by_path.get(path, os.path.basename(path)) for path in paths)
        return short_label, full_label

    def _find_uncommon_directory_context(self, target_path: str, peer_paths: list) -> str:
        """
        Find the most specific uncommon directory from the right.
        If the first rightmost directory is already uncommon, include two levels.
        """
        target_parts = os.path.normpath(target_path).split(os.sep)
        target_dirs = target_parts[:-1][::-1]
        all_dirs = [os.path.normpath(path).split(os.sep)[:-1][::-1] for path in peer_paths]
        if not target_dirs:
            return ""

        max_depth = max(len(parts) for parts in all_dirs)
        uncommon_idx = None
        for idx in range(max_depth):
            level_values = [parts[idx] if idx < len(parts) else None for parts in all_dirs]
            if len(set(level_values)) > 1:
                uncommon_idx = idx
                break

        if uncommon_idx is None:
            uncommon_idx = min(len(target_dirs) - 1, 0)

        if uncommon_idx == 0:
            taken = target_dirs[:min(2, len(target_dirs))]
            return "/".join(reversed(taken))
        return target_dirs[uncommon_idx]

    def _cache_current_diff_session(self):
        """Persist current diff session state (files and picker directory)."""
        file_paths = self.diff_engine.get_file_names()
        app_info_cache.set(self.SESSION_FILES_CACHE_KEY, file_paths)
        app_info_cache.set(self.LAST_DIRECTORY_CACHE_KEY, self.last_selected_directory or "")
        app_info_cache.set(
            self.HIGHLIGHT_WHITESPACE_CACHE_KEY,
            self.highlight_whitespace_checkbox.isChecked()
        )
        self._cache_file_grouping_history(file_paths)
        self.update_grouping_history_combo()
        try:
            app_info_cache.store()
        except Exception:
            # Keep UI responsive even if cache persistence fails.
            pass

    def _cache_file_grouping_history(self, file_paths: list):
        """Persist file grouping history independent of LLM request history."""
        if not file_paths:
            return

        normalized_paths = sorted({os.path.normcase(path): path for path in file_paths}.values())
        if not normalized_paths:
            return
        entry_id = hashlib.md5("||".join(sorted(os.path.normcase(path) for path in normalized_paths)).encode()).hexdigest()
        history = app_info_cache.get(self.GROUPING_HISTORY_CACHE_KEY, {})
        if not isinstance(history, dict):
            history = {}

        history[entry_id] = {
            "timestamp": datetime.now().isoformat(),
            "file_paths": normalized_paths
        }

        sorted_entries = sorted(
            history.items(),
            key=lambda x: x[1].get("timestamp", ""),
            reverse=True
        )
        trimmed = dict(sorted_entries[:self.GROUPING_HISTORY_MAX_ENTRIES])
        app_info_cache.set(self.GROUPING_HISTORY_CACHE_KEY, trimmed)

    def _restore_cached_diff_session(self):
        """Restore previously opened diff files and settings."""
        cached_paths = app_info_cache.get(self.SESSION_FILES_CACHE_KEY, [])
        if not isinstance(cached_paths, list):
            cached_paths = []

        self.last_selected_directory = app_info_cache.get(self.LAST_DIRECTORY_CACHE_KEY, self.last_selected_directory)
        existing_paths = [path for path in cached_paths if isinstance(path, str) and os.path.exists(path)]
        if not existing_paths:
            self._cache_current_diff_session()
            return

        self.diff_engine.clear_files()
        self.file_list_widget.clear()
        for filepath in existing_paths:
            try:
                self._add_file_to_engine_and_list(filepath)
            except Exception:
                continue

        self.update_file_combos()
        self.update_base_file_combo()
        self.update_file_groups()
        self._cache_current_diff_session()

    def _on_whitespace_highlight_changed(self, *_args):
        """Update diff and cache whitespace highlight preference."""
        self._cache_current_diff_session()
        self.update_diff()
    
    def update_file_combos(self):
        """Update the file selection combos."""
        file_names = self.diff_engine.get_file_names()
        
        self.file_a_combo.clear()
        self.file_b_combo.clear()
        
        for i, name in enumerate(file_names):
            # Show filename with directory context
            dir_context = os.path.dirname(name) or "."
            display_name = f"{os.path.basename(name)} ({dir_context})"
            self.file_a_combo.addItem(display_name, i)
            self.file_b_combo.addItem(display_name, i)
            # Set tooltip with full path
            self.file_a_combo.setItemData(i, name, Qt.ToolTipRole)
            self.file_b_combo.setItemData(i, name, Qt.ToolTipRole)
        
        # Set defaults if files available
        if len(file_names) >= 2:
            self.file_a_combo.setCurrentIndex(0)
            self.file_b_combo.setCurrentIndex(1)
        elif len(file_names) == 1:
            self.file_a_combo.setCurrentIndex(0)
            self.file_b_combo.setCurrentIndex(0)
    
    def update_diff(self):
        """Update the diff display."""
        file_a_idx = self.file_a_combo.currentData()
        file_b_idx = self.file_b_combo.currentData()
        
        if file_a_idx is None or file_b_idx is None:
            self._set_no_diff_indicator(False)
            return
        
        if file_a_idx == file_b_idx:
            self.diff_text.setPlainText("Select two different files to compare.")
            self.file_a_text.clear()
            self.file_b_text.clear()
            self._set_no_diff_indicator(False)
            return
        
        try:
            # Get diff lines
            diff_lines = self.diff_engine.compare_two_files(
                file_a_idx,
                file_b_idx,
                highlight_whitespace_only_diffs=self.highlight_whitespace_checkbox.isChecked()
            )
            self.current_diff_lines = diff_lines
            has_diff = any(line.line_type != DiffType.EQUAL for line in diff_lines)
            self._set_no_diff_indicator(not has_diff)
            
            # Update line-by-line diff
            diff_text_lines = []
            for diff_line in diff_lines:
                if diff_line.line_type == DiffType.DELETE:
                    content = diff_line.content_a.rstrip('\n')
                    diff_text_lines.append(f"-{content}")
                elif diff_line.line_type == DiffType.INSERT:
                    content = diff_line.content_b.rstrip('\n')
                    diff_text_lines.append(f"+{content}")
                else:
                    # Keep a reserved prefix column so text starts in same column as +/- lines.
                    content = diff_line.unified_line.rstrip('\n')
                    diff_text_lines.append(f" {content}")
            
            self.diff_text.setPlainText('\n'.join(diff_text_lines))
            
            # Update side-by-side view
            file_a_lines = []
            file_b_lines = []
            
            for diff_line in diff_lines:
                if diff_line.line_type == DiffType.EQUAL:
                    file_a_lines.append(diff_line.content_a.rstrip('\n'))
                    file_b_lines.append(diff_line.content_b.rstrip('\n'))
                elif diff_line.line_type == DiffType.DELETE:
                    file_a_lines.append(diff_line.content_a.rstrip('\n'))
                    file_b_lines.append("")  # Empty line for alignment
                elif diff_line.line_type == DiffType.INSERT:
                    file_a_lines.append("")  # Empty line for alignment
                    file_b_lines.append(diff_line.content_b.rstrip('\n'))
            
            self.file_a_text.setPlainText('\n'.join(file_a_lines))
            self.file_b_text.setPlainText('\n'.join(file_b_lines))
            
            # Update labels with directory context
            file_a_path = self.diff_engine.files[file_a_idx][0]
            file_b_path = self.diff_engine.files[file_b_idx][0]
            file_a_name = os.path.basename(file_a_path)
            file_b_name = os.path.basename(file_b_path)
            file_a_dir = os.path.dirname(file_a_path) or "."
            file_b_dir = os.path.dirname(file_b_path) or "."
            self.file_a_label.setText(_("File A: {0} ({1})").format(file_a_name, file_a_dir))
            self.file_b_label.setText(_("File B: {0} ({1})").format(file_b_name, file_b_dir))
            
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Failed to generate diff: {0}").format(str(e)))
    
    def show_unified_diff(self):
        """Show unified diff format."""
        file_a_idx = self.file_a_combo.currentData()
        file_b_idx = self.file_b_combo.currentData()
        
        if file_a_idx is None or file_b_idx is None:
            QMessageBox.warning(self, _("Warning"), _("Please select two files to compare."))
            return
        
        if file_a_idx == file_b_idx:
            QMessageBox.warning(self, _("Warning"), _("Please select two different files."))
            return
        
        try:
            unified_diff = self.diff_engine.get_unified_diff(file_a_idx, file_b_idx)
            self.diff_text.setPlainText(unified_diff)
            self._set_no_diff_indicator(False)
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Failed to generate unified diff: {0}").format(str(e)))
    
    def show_html_diff(self):
        """Show HTML diff in a new window."""
        file_a_idx = self.file_a_combo.currentData()
        file_b_idx = self.file_b_combo.currentData()
        
        if file_a_idx is None or file_b_idx is None:
            QMessageBox.warning(self, _("Warning"), _("Please select two files to compare."))
            return
        
        if file_a_idx == file_b_idx:
            QMessageBox.warning(self, _("Warning"), _("Please select two different files."))
            return
        
        try:
            html_diff = self.diff_engine.get_html_diff(file_a_idx, file_b_idx)
            
            # Save to temporary file and open in browser
            import tempfile
            import webbrowser
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html_diff)
                temp_path = f.name
            
            webbrowser.open(f'file://{temp_path}')
            QMessageBox.information(
                self, _("HTML Diff"),
                _("HTML diff opened in your default browser.\nTemporary file: {0}").format(temp_path)
            )
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Failed to generate HTML diff: {0}").format(str(e)))

    def _set_no_diff_indicator(self, no_diff: bool):
        """Update header indicator for identical file contents."""
        if no_diff:
            self.diff_section_label.setText(_("Line-by-Line Diff: ✅ No differences"))
        else:
            self.diff_section_label.setText(_("Line-by-Line Diff:"))
    
    def create_llm_analysis_tab(self) -> QWidget:
        """Create the LLM analysis tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Input section
        input_group = QWidget()
        input_layout = QVBoxLayout(input_group)
        
        input_layout.addWidget(QLabel(_("Target Context:")))
        self.target_context_input = QTextEdit()
        self.target_context_input.setPlaceholderText(
            _("Describe the target application/context where you want to use this tool module...")
        )
        self.target_context_input.setMaximumHeight(80)
        input_layout.addWidget(self.target_context_input)
        
        input_layout.addWidget(QLabel(_("Specific Requirements (optional):")))
        self.requirements_input = QTextEdit()
        default_requirements = "Please identify the module with the most up-to-date and complete basic logic, irrespective of custom logic native to each application context."
        self.requirements_input.setPlaceholderText(default_requirements)
        self.requirements_default = default_requirements  # Store for use as default
        self.requirements_input.setMaximumHeight(80)
        input_layout.addWidget(self.requirements_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.analyze_button = QPushButton(_("Analyze Versions"))
        self.analyze_button.clicked.connect(self.run_llm_analysis)
        button_layout.addWidget(self.analyze_button)
        
        self.generate_button = QPushButton(_("Generate Merged Version"))
        self.generate_button.clicked.connect(self.generate_merged_version)
        button_layout.addWidget(self.generate_button)
        
        self.base_file_combo = QComboBox()
        self.base_file_combo.setToolTip(_("Select base file for generation (optional)"))
        button_layout.addWidget(QLabel(_("Base File:")))
        button_layout.addWidget(self.base_file_combo)
        button_layout.addStretch()
        
        input_layout.addLayout(button_layout)
        
        # Status label and progress bar
        status_layout = QHBoxLayout()
        self.llm_status_label = QLabel("")
        self.llm_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        status_layout.addWidget(self.llm_status_label)
        
        self.llm_progress = QProgressBar()
        self.llm_progress.setVisible(False)
        self.llm_progress.setFormat(_("Processing LLM request..."))
        self.llm_progress.setTextVisible(True)
        status_layout.addWidget(self.llm_progress)
        status_layout.addStretch()
        
        input_layout.addLayout(status_layout)
        
        layout.addWidget(input_group)
        
        # Results section
        results_splitter = QSplitter(Qt.Horizontal)
        
        # Analysis results
        analysis_widget = QWidget()
        analysis_layout = QVBoxLayout(analysis_widget)
        analysis_header_layout = QHBoxLayout()
        analysis_header_layout.addWidget(QLabel(_("Analysis Results:")))
        self.analysis_status_label = QLabel("")
        self.analysis_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        analysis_header_layout.addStretch()
        analysis_header_layout.addWidget(self.analysis_status_label)
        analysis_layout.addLayout(analysis_header_layout)
        self.analysis_results = QTextEdit()
        self.analysis_results.setReadOnly(True)
        # Don't set font family - let HTML styling handle it for markdown rendering
        analysis_layout.addWidget(self.analysis_results)
        results_splitter.addWidget(analysis_widget)
        
        # Generated code
        code_widget = QWidget()
        code_layout = QVBoxLayout(code_widget)
        code_header_layout = QHBoxLayout()
        code_header_layout.addWidget(QLabel(_("Generated Code:")))
        self.code_status_label = QLabel("")
        self.code_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        code_header_layout.addStretch()
        code_header_layout.addWidget(self.code_status_label)
        code_layout.addLayout(code_header_layout)
        self.generated_code = QTextEdit()
        self.generated_code.setFontFamily("Courier")
        code_layout.addWidget(self.generated_code)
        
        # Save button
        save_button = QPushButton(_("Save Generated Code"))
        save_button.clicked.connect(self.save_generated_code)
        code_layout.addWidget(save_button)
        
        results_splitter.addWidget(code_widget)
        results_splitter.setStretchFactor(0, 1)
        results_splitter.setStretchFactor(1, 1)
        
        layout.addWidget(results_splitter)
        
        return tab
    
    def run_llm_analysis(self):
        """Run LLM analysis on the versions."""
        if self.diff_engine.get_file_count() < 2:
            QMessageBox.warning(
                self, _("Warning"),
                _("Please add at least 2 files to analyze.")
            )
            return
        
        # Cancel any existing worker
        if self.llm_analysis_worker and self.llm_analysis_worker.isRunning():
            self.llm_analysis_worker.terminate()
            self.llm_analysis_worker.wait()
        
        # Show progress indicators
        self.llm_progress.setVisible(True)
        self.llm_progress.setRange(0, 0)  # Indeterminate
        self.llm_status_label.setText(_("⏳ Processing analysis request..."))
        self.analysis_status_label.setText(_("⏳ Processing..."))
        self.analyze_button.setEnabled(False)
        
        # Prepare data
        files_content = [
            self.diff_engine.get_file_content(i) 
            for i in range(self.diff_engine.get_file_count())
        ]
        
        file_metadata = []
        for metadata in self.diff_engine.metadata:
            file_metadata.append({
                'filepath': metadata.filepath,
                'filename': metadata.filename,
                'directory_context': metadata.directory_context,
                'modification_time': metadata.modification_time.strftime('%Y-%m-%d %H:%M:%S'),
                'size': metadata.size,
                'line_count': metadata.line_count
            })
        
        diff_matrix = self.diff_engine.compare_all_files()
        
        target_context = self.target_context_input.toPlainText().strip() or None
        requirements_text = self.requirements_input.toPlainText().strip()
        # Use default requirements if field is empty
        requirements = requirements_text or self.requirements_default

        # Store request data for caching (will be cached on completion)
        self._pending_analysis_data = {
            'target_context': target_context,
            'requirements': requirements,
            'file_metadata': file_metadata
        }
        
        # Create and start worker thread
        self.llm_analysis_worker = LLMAnalysisWorker(
            self.llm_analyzer, files_content, file_metadata, diff_matrix,
            target_context, requirements, self
        )
        self.llm_analysis_worker.finished.connect(self._on_analysis_finished)
        self.llm_analysis_worker.error.connect(self._on_analysis_error)
        self.llm_analysis_worker.start()
    
    def _on_analysis_finished(self, result):
        """Handle successful completion of LLM analysis."""
        file_metadata = []
        for metadata in self.diff_engine.metadata:
            file_metadata.append({
                'filepath': metadata.filepath,
                'filename': metadata.filename,
                'directory_context': metadata.directory_context,
                'modification_time': metadata.modification_time.strftime('%Y-%m-%d %H:%M:%S'),
                'size': metadata.size,
                'line_count': metadata.line_count
            })
        
        if result.get('error'):
            error_text = _("❌ Error: {0}").format(result['error'])
            html_content = markdown_to_html(error_text)
            self.analysis_results.setHtml(html_content)
            self.analysis_status_label.setText(_("❌ Error"))
        else:
            analysis_text = result.get('analysis', _('No analysis available'))
            recommendation = result.get('recommendation', {})
            
            display_text = analysis_text
            if recommendation and recommendation.get('recommended_file_index') is not None:
                idx = recommendation['recommended_file_index']
                metadata = file_metadata[idx]
                filename = metadata['filename']
                dir_context = metadata['directory_context']
                # Use 1-based indexing for display
                display_text += "\n\n## " + _("Recommended File") + "\n\n"
                display_text += _("**File {0}**: `{1}` (from `{2}`)").format(idx + 1, filename, dir_context) + "\n"
            
            html_content = markdown_to_html(display_text)
            self.analysis_results.setHtml(html_content)
            self.analysis_status_label.setText(_("✅ Complete"))
            
            # Update base file combo if recommendation exists
            if recommendation and recommendation.get('recommended_file_index') is not None:
                self.update_base_file_combo()
                self.base_file_combo.setCurrentIndex(recommendation['recommended_file_index'])
            
            # Cache the request and response
            self._cache_llm_request('analysis', result, self._pending_analysis_data.get('file_metadata', file_metadata))
        
        # Clean up
        self.llm_progress.setVisible(False)
        self.llm_status_label.setText("")
        self.analyze_button.setEnabled(True)
        self.llm_analysis_worker = None
    
    def _on_analysis_error(self, error_msg):
        """Handle error from LLM analysis."""
        QMessageBox.critical(self, _("Error"), _("Analysis failed: {0}").format(error_msg))
        html_content = markdown_to_html(_("Error: {0}").format(error_msg))
        self.analysis_results.setHtml(html_content)
        self.analysis_status_label.setText(_("❌ Error"))
        
        # Clean up
        self.llm_progress.setVisible(False)
        self.llm_status_label.setText("")
        self.analyze_button.setEnabled(True)
        self.llm_analysis_worker = None
    
    def generate_merged_version(self):
        """Generate a merged version using LLM."""
        if self.diff_engine.get_file_count() < 1:
            QMessageBox.warning(
                self, _("Warning"),
                _("Please add at least 1 file to generate from.")
            )
            return
        
        target_context = self.target_context_input.toPlainText().strip()
        if not target_context:
            QMessageBox.warning(
                self, _("Warning"),
                _("Please provide a target context.")
            )
            return
        
        # Cancel any existing worker
        if self.llm_generation_worker and self.llm_generation_worker.isRunning():
            self.llm_generation_worker.terminate()
            self.llm_generation_worker.wait()
        
        # Show progress indicators
        self.llm_progress.setVisible(True)
        self.llm_progress.setRange(0, 0)  # Indeterminate
        self.llm_progress.setFormat(_("Generating merged version..."))
        self.llm_status_label.setText(_("⏳ Generating code..."))
        self.code_status_label.setText(_("⏳ Processing..."))
        self.generate_button.setEnabled(False)
        
        # Prepare data
        files_content = [
            self.diff_engine.get_file_content(i) 
            for i in range(self.diff_engine.get_file_count())
        ]
        
        file_metadata = []
        for metadata in self.diff_engine.metadata:
            file_metadata.append({
                'filepath': metadata.filepath,
                'filename': metadata.filename,
                'directory_context': metadata.directory_context,
                'modification_time': metadata.modification_time.strftime('%Y-%m-%d %H:%M:%S'),
                'size': metadata.size,
                'line_count': metadata.line_count
            })
        
        diff_matrix = self.diff_engine.compare_all_files()
        
        requirements_text = self.requirements_input.toPlainText().strip()
        # Use default requirements if field is empty
        requirements = requirements_text or self.requirements_default
        base_file_index = self.base_file_combo.currentData()
        
        # Store request data for caching (will be cached on completion)
        self._pending_generation_data = {
            'target_context': target_context,
            'requirements': requirements,
            'base_file_index': base_file_index,
            'file_metadata': file_metadata
        }
        
        # Create and start worker thread
        self.llm_generation_worker = LLMGenerationWorker(
            self.llm_analyzer, files_content, file_metadata, diff_matrix,
            target_context, requirements, base_file_index, self
        )
        self.llm_generation_worker.finished.connect(self._on_generation_finished)
        self.llm_generation_worker.error.connect(self._on_generation_error)
        self.llm_generation_worker.start()
    
    def _on_generation_finished(self, result):
        """Handle successful completion of LLM code generation."""
        if result.get('error'):
            error_text = _("❌ Error: {0}").format(result['error'])
            self.generated_code.setPlainText(error_text)
            self.code_status_label.setText(_("❌ Error"))
        else:
            code = result.get('code', _('No code generated'))
            self.generated_code.setPlainText(code)
            self.code_status_label.setText(_("✅ Complete"))
            
            if result.get('explanation'):
                explanation = result['explanation']
                if explanation != code:
                    html_content = markdown_to_html(_("## Generation Explanation\n\n{0}").format(explanation))
                    self.analysis_results.setHtml(html_content)
            
            # Cache the request and response
            self._cache_llm_request('generation', result, self._pending_generation_data.get('file_metadata', []))
        
        # Clean up
        self.llm_progress.setVisible(False)
        self.llm_progress.setFormat(_("Processing LLM request..."))
        self.llm_status_label.setText("")
        self.generate_button.setEnabled(True)
        self.llm_generation_worker = None
    
    def _on_generation_error(self, error_msg):
        """Handle error from LLM code generation."""
        QMessageBox.critical(self, _("Error"), _("Generation failed: {0}").format(error_msg))
        self.generated_code.setPlainText(_("Error: {0}").format(error_msg))
        self.code_status_label.setText(_("❌ Error"))
        
        # Clean up
        self.llm_progress.setVisible(False)
        self.llm_progress.setFormat(_("Processing LLM request..."))
        self.llm_status_label.setText("")
        self.generate_button.setEnabled(True)
        self.llm_generation_worker = None
    
    def update_base_file_combo(self):
        """Update the base file combo box."""
        self.base_file_combo.clear()
        file_names = self.diff_engine.get_file_names()
        for i, name in enumerate(file_names):
            # Show filename with directory context
            dir_context = os.path.dirname(name) or "."
            display_name = f"{os.path.basename(name)} ({dir_context})"
            self.base_file_combo.addItem(display_name, i)
            # Set tooltip with full path
            self.base_file_combo.setItemData(i, name, Qt.ToolTipRole)
        self.base_file_combo.insertItem(0, _("None (merge all)"), None)
        self.base_file_combo.setCurrentIndex(0)
    
    def save_generated_code(self):
        """Save the generated code to a file."""
        code = self.generated_code.toPlainText()
        if not code or code.startswith(_("Error: {0}").format("")):
            QMessageBox.warning(self, _("Warning"), _("No code to save."))
            return
        
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self, _("Save Generated Code"), "", _("Python Files (*.py);;All Files (*)")
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(code)
                QMessageBox.information(self, _("Success"), _("Code saved to {0}").format(filename))
            except Exception as e:
                QMessageBox.critical(self, _("Error"), _("Failed to save file: {0}").format(str(e)))
    
    def create_file_grouping_tab(self) -> QWidget:
        """Create the file grouping tab that groups files by content (size + hash)."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Header
        header_label = QLabel(_("Files grouped by content (size + hash). Identical files are grouped together."))
        header_label.setWordWrap(True)
        layout.addWidget(header_label)
        
        # Refresh button
        refresh_button = QPushButton(_("Refresh Groups"))
        refresh_button.clicked.connect(self.update_file_groups)
        refresh_button.setToolTip(_("Recalculate file groups based on current files"))
        layout.addWidget(refresh_button)
        
        # Tree widget for collapsible groups
        self.grouping_tree = QTreeWidget()
        self.grouping_tree.setHeaderLabels([_("File / Group"), _("Size"), _("Hash"), _("Path")])
        self.grouping_tree.setColumnWidth(0, 300)
        self.grouping_tree.setColumnWidth(1, 100)
        self.grouping_tree.setColumnWidth(2, 150)
        self.grouping_tree.setColumnWidth(3, 400)
        self.grouping_tree.setAlternatingRowColors(True)
        self.grouping_tree.setToolTip(_("Groups of identical files. Expand groups to see individual files."))
        layout.addWidget(self.grouping_tree)
        
        # Info label
        self.grouping_info_label = QLabel(_("No files added yet."))
        layout.addWidget(self.grouping_info_label)
        
        # Update groups when files are added
        self.update_file_groups()
        
        return tab
    
    def update_file_groups(self):
        """Update the file grouping display."""
        import hashlib
        
        self.grouping_tree.clear()
        
        if self.diff_engine.get_file_count() == 0:
            self.grouping_info_label.setText(_("No files added yet."))
            return
        
        # Calculate hash for each file
        file_hashes = {}
        file_sizes = {}
        
        for i, (filepath, _content) in enumerate(self.diff_engine.files):
            try:
                with open(filepath, 'rb') as f:
                    content = f.read()
                    file_hash = hashlib.md5(content).hexdigest()
                    file_size = len(content)
                    file_hashes[filepath] = file_hash
                    file_sizes[filepath] = file_size
            except Exception as e:
                # If file can't be read, skip it
                continue
        
        # Group files by (size, hash)
        groups = {}
        for filepath, file_hash in file_hashes.items():
            file_size = file_sizes[filepath]
            key = (file_size, file_hash)
            if key not in groups:
                groups[key] = []
            groups[key].append(filepath)
        
        # Create tree items for each group
        group_number = 1
        total_files = len(file_hashes)
        unique_groups = len(groups)
        
        # Sort groups by size (largest first) for better visibility
        sorted_groups = sorted(groups.items(), key=lambda x: x[0][0], reverse=True)
        
        for (size, hash_value), filepaths in sorted_groups:
            # Create group item
            group_item = QTreeWidgetItem(self.grouping_tree)
            group_item.setText(0, _("Group {0} ({1} file(s))").format(group_number, len(filepaths)))
            group_item.setText(1, self._format_size(size))
            group_item.setText(2, hash_value[:16] + "...")  # Show first 16 chars
            group_item.setText(3, "")
            group_item.setExpanded(True)  # Expanded by default
            
            # Make group item bold
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            
            # Add individual files as children
            for filepath in sorted(filepaths):
                file_item = QTreeWidgetItem(group_item)
                filename = os.path.basename(filepath)
                dir_context = os.path.dirname(filepath) or "."
                file_item.setText(0, filename)
                file_item.setText(1, self._format_size(size))
                file_item.setText(2, hash_value[:16] + "...")
                file_item.setText(3, filepath)
                file_item.setToolTip(0, filepath)
                file_item.setToolTip(3, filepath)
            
            group_number += 1
        
        # Update info label
        if unique_groups == total_files:
            self.grouping_info_label.setText(
                _("All {0} file(s) are unique (no duplicates found).").format(total_files)
            )
        else:
            duplicates = total_files - unique_groups
            self.grouping_info_label.setText(
                _("Found {0} unique file group(s) from {1} file(s). {2} duplicate(s) detected.").format(unique_groups, total_files, duplicates)
            )
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _cache_llm_request(self, request_type: str, result: dict, file_metadata: list):
        """Cache an LLM request and its response."""
        try:
            # Get current file configuration
            file_paths = [metadata['filepath'] for metadata in file_metadata]
            
            # Get target context and requirements from stored request data
            if request_type == 'analysis':
                pending_data = getattr(self, '_pending_analysis_data', {})
                target_context = pending_data.get('target_context')
                requirements = pending_data.get('requirements', self.requirements_default)
                base_file_index = None
            else:  # generation
                pending_data = getattr(self, '_pending_generation_data', {})
                target_context = pending_data.get('target_context')
                requirements = pending_data.get('requirements', self.requirements_default)
                base_file_index = pending_data.get('base_file_index')
            
            # Generate a unique ID based on the file configuration
            # If all files have the same filename, use just the filename
            # Otherwise, use the sorted list of file paths
            filenames = [os.path.basename(fp) for fp in file_paths]
            if len(set(filenames)) == 1 and len(file_paths) > 0:
                # All files have the same name - use filename as ID
                entry_id = filenames[0]
            else:
                # Different filenames - use sorted file paths
                sorted_paths = sorted(file_paths)
                entry_id = hashlib.md5(''.join(sorted_paths).encode()).hexdigest()
            
            # Create cache entry
            cache_entry = {
                'request_type': request_type,  # 'analysis' or 'generation'
                'timestamp': datetime.now().isoformat(),
                'file_paths': file_paths,
                'file_metadata': file_metadata,
                'target_context': target_context,
                'requirements': requirements,
                'base_file_index': base_file_index,
                'result': result
            }
            
            # Get or create the cache map
            cache_key = 'diff_mode_llm_history'
            history = app_info_cache.get(cache_key, {})
            
            # Store/update entry (will overwrite if same file configuration exists)
            history[entry_id] = cache_entry
            
            # Store back in cache
            app_info_cache.set(cache_key, history)
            app_info_cache.store()
            
            # Update history tab if it exists
            if hasattr(self, 'history_list_widget'):
                self.update_request_history()
        except Exception as e:
            # Don't fail the request if caching fails
            import traceback
            print(f"Failed to cache LLM request: {e}")
            print(traceback.format_exc())
    
    def create_request_history_tab(self) -> QWidget:
        """Create the request history tab for viewing and restoring cached LLM requests."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Header
        header_label = QLabel(_("View and restore previous LLM requests. Double-click an entry to restore its configuration."))
        header_label.setWordWrap(True)
        layout.addWidget(header_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        refresh_button = QPushButton(_("Refresh History"))
        refresh_button.clicked.connect(self.update_request_history)
        button_layout.addWidget(refresh_button)
        
        delete_button = QPushButton(_("Delete Selected"))
        delete_button.clicked.connect(self.delete_selected_history_entry)
        button_layout.addWidget(delete_button)
        
        clear_all_button = QPushButton(_("Clear All History"))
        clear_all_button.clicked.connect(self.clear_all_history)
        button_layout.addWidget(clear_all_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # List widget for history entries
        self.history_list_widget = QListWidget()
        self.history_list_widget.setAlternatingRowColors(True)
        self.history_list_widget.itemDoubleClicked.connect(self.restore_history_entry)
        self.history_list_widget.setToolTip(_("Double-click an entry to restore its file configuration and view the cached response."))
        layout.addWidget(self.history_list_widget)
        
        # Details panel
        details_label = QLabel(_("Entry Details:"))
        layout.addWidget(details_label)
        
        self.history_details = QTextEdit()
        self.history_details.setReadOnly(True)
        self.history_details.setMaximumHeight(200)
        layout.addWidget(self.history_details)
        
        # Connect selection change to show details
        self.history_list_widget.itemSelectionChanged.connect(self.show_history_entry_details)
        
        # Initial update
        self.update_request_history()
        
        return tab
    
    def update_request_history(self):
        """Update the request history list."""
        self.history_list_widget.clear()
        
        try:
            cache_key = 'diff_mode_llm_history'
            history = app_info_cache.get(cache_key, {})
            
            if not history:
                self.history_list_widget.addItem(_("No cached requests found."))
                return
            
            # Sort by timestamp (newest first)
            sorted_entries = sorted(
                history.items(),
                key=lambda x: x[1].get('timestamp', ''),
                reverse=True
            )
            
            for entry_id, entry in sorted_entries:
                request_type = entry.get('request_type', 'unknown')
                timestamp_str = entry.get('timestamp', '')
                file_paths = entry.get('file_paths', [])
                
                # Parse timestamp for display
                try:
                    dt = datetime.fromisoformat(timestamp_str)
                    time_display = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    time_display = timestamp_str
                
                # Create display text
                file_count = len(file_paths)
                type_display = _("Analysis") if request_type == 'analysis' else _("Generation")
                
                # Show first few filenames
                if file_paths:
                    filenames = [os.path.basename(fp) for fp in file_paths[:3]]
                    files_display = ', '.join(filenames)
                    if len(file_paths) > 3:
                        files_display += _(" (+{0} more)").format(len(file_paths) - 3)
                else:
                    files_display = _("No files")
                
                display_text = _("[{0}] {1} - {2} file(s): {3}").format(time_display, type_display, file_count, files_display)
                
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, entry_id)  # Store entry ID
                self.history_list_widget.addItem(item)
        except Exception as e:
            self.history_list_widget.addItem(_("Error loading history: {0}").format(str(e)))
    
    def show_history_entry_details(self):
        """Show details of the selected history entry."""
        selected_items = self.history_list_widget.selectedItems()
        if not selected_items:
            self.history_details.clear()
            return
        
        try:
            entry_id = selected_items[0].data(Qt.UserRole)
            cache_key = 'diff_mode_llm_history'
            history = app_info_cache.get(cache_key, {})
            
            if entry_id not in history:
                self.history_details.setPlainText(_("Entry not found."))
                return
            
            entry = history[entry_id]
            
            # Build details text
            details_lines = []
            details_lines.append(_("Request Type: {0}").format(entry.get('request_type', _('unknown'))))
            details_lines.append(_("Timestamp: {0}").format(entry.get('timestamp', _('unknown'))))
            details_lines.append("\n" + _("Files ({0}):").format(len(entry.get('file_paths', []))))
            for i, filepath in enumerate(entry.get('file_paths', []), 1):
                filename = os.path.basename(filepath)
                dir_context = os.path.dirname(filepath) or "."
                details_lines.append("  " + _("{0}. {1} (from {2})").format(i, filename, dir_context))
                details_lines.append(f"     {filepath}")
            
            target_context = entry.get('target_context')
            if target_context:
                details_lines.append("\n" + _("Target Context: {0}").format(target_context))
            
            requirements = entry.get('requirements')
            if requirements:
                details_lines.append("\n" + _("Requirements: {0}").format(requirements))
            
            base_file_index = entry.get('base_file_index')
            if base_file_index is not None:
                details_lines.append("\n" + _("Base File Index: {0}").format(base_file_index))
            
            result = entry.get('result', {})
            if result.get('error'):
                details_lines.append("\n" + _("Result: Error - {0}").format(result.get('error')))
            else:
                if entry.get('request_type') == 'analysis':
                    details_lines.append("\n" + _("Result: Analysis completed successfully"))
                else:
                    details_lines.append("\n" + _("Result: Code generation completed successfully"))
            
            self.history_details.setPlainText('\n'.join(details_lines))
        except Exception as e:
            self.history_details.setPlainText(_("Error loading details: {0}").format(str(e)))
    
    def restore_history_entry(self, item):
        """Restore a history entry's configuration."""
        try:
            entry_id = item.data(Qt.UserRole)
            cache_key = 'diff_mode_llm_history'
            history = app_info_cache.get(cache_key, {})
            
            if entry_id not in history:
                QMessageBox.warning(self, _("Error"), _("Entry not found in cache."))
                return
            
            entry = history[entry_id]
            file_paths = entry.get('file_paths', [])
            
            if not file_paths:
                QMessageBox.warning(self, _("Error"), _("No files found in this entry."))
                return
            
            # Confirm restoration
            reply = QMessageBox.question(
                self, _("Restore Configuration"),
                _("This will replace your current file configuration with {0} file(s).\nContinue?").format(len(file_paths)),
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # Clear current files
            self.diff_engine.clear_files()
            self.file_list_widget.clear()
            
            # Add files from cache
            for filepath in file_paths:
                if os.path.exists(filepath):
                    try:
                        self._add_file_to_engine_and_list(filepath)
                    except Exception as e:
                        QMessageBox.warning(
                            self, _("Warning"),
                            _("Failed to add file {0}: {1}").format(filepath, str(e))
                        )
                else:
                    QMessageBox.warning(
                        self, _("Warning"),
                        _("File no longer exists: {0}").format(filepath)
                    )
            
            # Update UI
            self.update_file_combos()
            self.update_base_file_combo()
            self.update_file_groups()
            if file_paths:
                self.last_selected_directory = os.path.dirname(file_paths[0]) or self.last_selected_directory
            self._cache_current_diff_session()
            
            # Restore target context and requirements
            target_context = entry.get('target_context')
            if target_context:
                self.target_context_input.setPlainText(target_context)
            else:
                self.target_context_input.clear()
            
            requirements = entry.get('requirements')
            if requirements:
                self.requirements_input.setPlainText(requirements)
            else:
                self.requirements_input.clear()
            
            # Get request type and result
            request_type = entry.get('request_type', 'analysis')
            result = entry.get('result', {})
            
            # Restore base file index if applicable
            base_file_index = entry.get('base_file_index')
            if base_file_index is not None and request_type == 'generation':
                self.update_base_file_combo()
                # Find the index in the combo
                for i in range(self.base_file_combo.count()):
                    if self.base_file_combo.itemData(i) == base_file_index:
                        self.base_file_combo.setCurrentIndex(i)
                        break
            
            # Display the cached result
            
            if request_type == 'analysis':
                if result.get('error'):
                    error_text = _("❌ Error: {0}").format(result['error'])
                    html_content = markdown_to_html(error_text)
                    self.analysis_results.setHtml(html_content)
                    self.analysis_status_label.setText(_("❌ Error (cached)"))
                else:
                    analysis_text = result.get('analysis', _('No analysis available'))
                    recommendation = result.get('recommendation', {})
                    
                    display_text = analysis_text
                    if recommendation and recommendation.get('recommended_file_index') is not None:
                        idx = recommendation['recommended_file_index']
                        file_metadata = entry.get('file_metadata', [])
                        if idx < len(file_metadata):
                            metadata = file_metadata[idx]
                            filename = metadata.get('filename', _('unknown'))
                            dir_context = metadata.get('directory_context', _('unknown'))
                            display_text += "\n\n## " + _("Recommended File") + "\n\n"
                            display_text += _("**File {0}**: `{1}` (from `{2}`)").format(idx + 1, filename, dir_context) + "\n"
                    
                    html_content = markdown_to_html(display_text)
                    self.analysis_results.setHtml(html_content)
                    self.analysis_status_label.setText(_("✅ Complete (cached)"))
            else:  # generation
                if result.get('error'):
                    error_text = _("❌ Error: {0}").format(result['error'])
                    self.generated_code.setPlainText(error_text)
                    self.code_status_label.setText(_("❌ Error (cached)"))
                else:
                    code = result.get('code', _('No code generated'))
                    self.generated_code.setPlainText(code)
                    self.code_status_label.setText(_("✅ Complete (cached)"))
                    
                    if result.get('explanation'):
                        explanation = result['explanation']
                        if explanation != code:
                            html_content = markdown_to_html(_("## Generation Explanation\n\n{0}").format(explanation))
                            self.analysis_results.setHtml(html_content)
            
            # Switch to LLM Analysis tab
            # Find the parent tab widget
            parent = self.parent()
            while parent and not isinstance(parent, QTabWidget):
                parent = parent.parent()
            if parent:
                # Find the tab index for LLM Analysis
                for i in range(parent.count()):
                    if parent.tabText(i) == _("LLM Analysis"):
                        parent.setCurrentIndex(i)
                        break
            
            QMessageBox.information(
                self, _("Restored"),
                _("Configuration restored from {0}.\nCached response displayed in LLM Analysis tab.").format(entry.get('timestamp', _('unknown')))
            )
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Failed to restore entry: {0}").format(str(e)))
    
    def delete_selected_history_entry(self):
        """Delete the selected history entry."""
        selected_items = self.history_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, _("Warning"), _("Please select an entry to delete."))
            return
        
        try:
            entry_id = selected_items[0].data(Qt.UserRole)
            
            reply = QMessageBox.question(
                self, _("Confirm Delete"),
                _("Are you sure you want to delete this entry?"),
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            cache_key = 'diff_mode_llm_history'
            history = app_info_cache.get(cache_key, {})
            
            if entry_id in history:
                del history[entry_id]
                app_info_cache.set(cache_key, history)
                app_info_cache.store()
                self.update_request_history()
                self.history_details.clear()
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Failed to delete entry: {0}").format(str(e)))
    
    def clear_all_history(self):
        """Clear all cached history entries."""
        reply = QMessageBox.question(
            self, _("Confirm Clear All"),
            _("Are you sure you want to clear all cached history?\nThis cannot be undone."),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            cache_key = 'diff_mode_llm_history'
            app_info_cache.set(cache_key, {})
            app_info_cache.store()
            self.update_request_history()
            self.history_details.clear()
            QMessageBox.information(self, _("Success"), _("All history cleared."))
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Failed to clear history: {0}").format(str(e)))

