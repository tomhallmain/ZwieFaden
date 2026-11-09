"""Project Compare tab: finds files shared between two project directories
and categorizes them as identical, different, or present in only one side.
Lives outside modes/diff_mode.py to keep that file from growing further --
DiffModeWidget only wires this tab in and hands it a callback to load a
selected pair into its own Diff View tab."""

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QProgressBar, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget
)

from diff.project_compare import ProjectComparator, ProjectComparisonResult
from utils.app_info_cache import app_info_cache
from utils.translations import _


class ProjectCompareWorker(QThread):
    """Worker thread for running a project comparison."""
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, root_a, root_b, extra_ignore_patterns=None, respect_gitignore=True, parent=None):
        super().__init__(parent)
        self.root_a = root_a
        self.root_b = root_b
        self.extra_ignore_patterns = extra_ignore_patterns or []
        self.respect_gitignore = respect_gitignore

    def run(self):
        """Run the project comparison."""
        try:
            comparator = ProjectComparator(
                extra_ignore_patterns=self.extra_ignore_patterns,
                respect_gitignore=self.respect_gitignore,
            )
            result = comparator.compare(self.root_a, self.root_b)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ProjectCompareTab(QWidget):
    """Widget for the "Projektvergleich" tab within Diff Mode."""
    PROJECT_A_CACHE_KEY = "project_compare_project_a"
    PROJECT_B_CACHE_KEY = "project_compare_project_b"
    GLOBAL_EXCLUSIONS_CACHE_KEY = "project_compare_global_exclusions"
    RESPECT_GITIGNORE_CACHE_KEY = "project_compare_respect_gitignore"

    def __init__(self, open_pair_callback, parent=None):
        """open_pair_callback(path_a: str, path_b: str) is invoked when the
        user opens a "different" pair from the results into the Diff View."""
        super().__init__(parent)
        self.open_pair_callback = open_pair_callback
        self.worker = None
        self.result = None
        self.init_ui()
        self._restore_cached_directories()
        self._restore_global_exclusions()
        self._restore_respect_gitignore()

    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        row_a = QHBoxLayout()
        row_a.addWidget(QLabel(_("Projekt A:")))
        self.project_a_input = QLineEdit()
        self.project_a_input.setReadOnly(True)
        row_a.addWidget(self.project_a_input)
        self.project_a_button = QPushButton(_("Ordner wählen…"))
        self.project_a_button.clicked.connect(lambda: self._choose_directory(self.project_a_input))
        row_a.addWidget(self.project_a_button)
        layout.addLayout(row_a)

        row_b = QHBoxLayout()
        row_b.addWidget(QLabel(_("Projekt B:")))
        self.project_b_input = QLineEdit()
        self.project_b_input.setReadOnly(True)
        row_b.addWidget(self.project_b_input)
        self.project_b_button = QPushButton(_("Ordner wählen…"))
        self.project_b_button.clicked.connect(lambda: self._choose_directory(self.project_b_input))
        row_b.addWidget(self.project_b_button)
        layout.addLayout(row_b)

        exclusions_label = QLabel(
            _("Globale Ausschlüsse (gelten für alle Projektvergleiche, zusätzlich zur "
            "Standardliste und zum .gitignore des jeweiligen Projekts):")
        )
        exclusions_label.setWordWrap(True)
        layout.addWidget(exclusions_label)

        exclusions_input_row = QHBoxLayout()
        self.global_exclusion_input = QLineEdit()
        self.global_exclusion_input.setPlaceholderText(_("z. B. *.tmp oder build/"))
        self.global_exclusion_input.returnPressed.connect(self._add_global_exclusion)
        exclusions_input_row.addWidget(self.global_exclusion_input)
        self.add_exclusion_button = QPushButton(_("Hinzufügen"))
        self.add_exclusion_button.clicked.connect(self._add_global_exclusion)
        exclusions_input_row.addWidget(self.add_exclusion_button)
        layout.addLayout(exclusions_input_row)

        self.global_exclusions_list = QListWidget()
        self.global_exclusions_list.setMaximumHeight(80)
        self.global_exclusions_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.global_exclusions_list.setToolTip(
            _("Muster im .gitignore-Stil, unabhängig vom verglichenen Projekt.")
        )
        layout.addWidget(self.global_exclusions_list)

        self.remove_exclusion_button = QPushButton(_("Ausgewählte Ausschlüsse entfernen"))
        self.remove_exclusion_button.clicked.connect(self._remove_selected_global_exclusions)
        layout.addWidget(self.remove_exclusion_button)

        self.respect_gitignore_checkbox = QCheckBox(_("Projekteigene .gitignore-Muster berücksichtigen"))
        self.respect_gitignore_checkbox.setChecked(True)
        self.respect_gitignore_checkbox.setToolTip(
            _("Deaktivieren, um auch Dateien zu finden, die im .gitignore des jeweiligen "
            "Projekts stehen. Die Standardliste und die globalen Ausschlüsse oben gelten "
            "weiterhin unabhängig davon.")
        )
        self.respect_gitignore_checkbox.stateChanged.connect(self._on_respect_gitignore_changed)
        layout.addWidget(self.respect_gitignore_checkbox)

        self.compare_button = QPushButton(_("Vergleich starten"))
        self.compare_button.clicked.connect(self.start_comparison)
        layout.addWidget(self.compare_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels([_("Datei")])
        self.result_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.result_tree.itemSelectionChanged.connect(self._update_open_pair_button_state)
        layout.addWidget(self.result_tree)

        self.open_pair_button = QPushButton(_("Ausgewähltes Paar in Diff-Ansicht öffnen"))
        self.open_pair_button.clicked.connect(self._open_selected_pair)
        self.open_pair_button.setEnabled(False)
        layout.addWidget(self.open_pair_button)

        self.summary_label = QLabel(_("Noch kein Vergleich durchgeführt."))
        layout.addWidget(self.summary_label)

    def _choose_directory(self, target_input):
        """Open a directory picker and store the result in target_input."""
        start_dir = target_input.text() or os.getcwd()
        directory = QFileDialog.getExistingDirectory(self, _("Projektordner wählen"), start_dir)
        if directory:
            target_input.setText(directory)
            self._cache_directories()

    def start_comparison(self):
        """Start a project comparison in a background thread."""
        root_a = self.project_a_input.text().strip()
        root_b = self.project_b_input.text().strip()
        if not root_a or not root_b:
            QMessageBox.warning(self, _("Projektvergleich"), _("Bitte beide Projektordner auswählen."))
            return
        if not os.path.isdir(root_a) or not os.path.isdir(root_b):
            QMessageBox.warning(self, _("Projektvergleich"), _("Einer der ausgewählten Ordner existiert nicht mehr."))
            return

        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.compare_button.setEnabled(False)
        self.summary_label.setText(_("Vergleich läuft…"))

        self.worker = ProjectCompareWorker(
            root_a, root_b,
            extra_ignore_patterns=self._current_global_exclusions(),
            respect_gitignore=self.respect_gitignore_checkbox.isChecked(),
            parent=self,
        )
        self.worker.finished.connect(self._on_comparison_finished)
        self.worker.error.connect(self._on_comparison_error)
        self.worker.start()

    def _on_comparison_finished(self, result):
        """Handle successful completion of the comparison."""
        self.result = result
        self._populate_result_tree(result)
        self.progress_bar.setVisible(False)
        self.compare_button.setEnabled(True)
        self.summary_label.setText(
            _("{0} identisch, {1} unterschiedlich, {2} nur in Projekt A, {3} nur in Projekt B.").format(len(result.identical), len(result.different), len(result.only_in_a), len(result.only_in_b))
        )
        self.worker = None

    def _on_comparison_error(self, error_msg):
        """Handle an error from the comparison worker."""
        self.progress_bar.setVisible(False)
        self.compare_button.setEnabled(True)
        self.summary_label.setText(_("Vergleich fehlgeschlagen."))
        QMessageBox.critical(self, _("Projektvergleich"), _("Vergleich fehlgeschlagen: {0}").format(error_msg))
        self.worker = None

    def _populate_result_tree(self, result: ProjectComparisonResult):
        """Fill the results tree with the four comparison categories."""
        self.result_tree.clear()
        categories = [
            (_("Unterschiedlich ({0})").format(len(result.different)), result.different, "different"),
            (_("Nur in Projekt A ({0})").format(len(result.only_in_a)), result.only_in_a, "only_a"),
            (_("Nur in Projekt B ({0})").format(len(result.only_in_b)), result.only_in_b, "only_b"),
            (_("Identisch ({0})").format(len(result.identical)), result.identical, "identical"),
        ]
        for label, relative_paths, category in categories:
            group_item = QTreeWidgetItem(self.result_tree, [label])
            group_item.setExpanded(category == "different")
            for relative_path in relative_paths:
                child_item = QTreeWidgetItem(group_item, [relative_path])
                child_item.setData(0, Qt.UserRole, (category, relative_path))

    def _update_open_pair_button_state(self):
        """Enable "open pair" only when a "different"-category file is selected."""
        selected_items = self.result_tree.selectedItems()
        can_open = False
        if selected_items:
            data = selected_items[0].data(0, Qt.UserRole)
            can_open = bool(data) and data[0] == "different"
        self.open_pair_button.setEnabled(can_open)

    def _on_item_double_clicked(self, item, _column):
        """Open a double-clicked "different" entry directly."""
        data = item.data(0, Qt.UserRole)
        if data and data[0] == "different":
            self._open_pair_for_relative_path(data[1])

    def _open_selected_pair(self):
        """Open the selected "different" entry via the button."""
        selected_items = self.result_tree.selectedItems()
        if not selected_items:
            return
        data = selected_items[0].data(0, Qt.UserRole)
        if data and data[0] == "different":
            self._open_pair_for_relative_path(data[1])

    def _open_pair_for_relative_path(self, relative_path):
        """Resolve a relative path to both absolute paths and hand them to
        the Diff View, unless either side was detected as binary."""
        if not self.result:
            return
        paths = self.result.get_absolute_paths(relative_path)
        if not paths:
            return
        path_a, path_b = paths
        entry_a = self.result.files_a.get(relative_path)
        entry_b = self.result.files_b.get(relative_path)
        if (entry_a and entry_a.is_binary) or (entry_b and entry_b.is_binary):
            QMessageBox.information(
                self, _("Binärdatei"),
                _("Diese Datei wurde als Binärdatei erkannt und kann nicht in der "
                "Diff-Ansicht geöffnet werden.")
            )
            return
        self.open_pair_callback(path_a, path_b)

    def _cache_directories(self):
        """Persist the currently selected project directories."""
        app_info_cache.set(self.PROJECT_A_CACHE_KEY, self.project_a_input.text())
        app_info_cache.set(self.PROJECT_B_CACHE_KEY, self.project_b_input.text())
        try:
            app_info_cache.store()
        except Exception:
            # Keep UI responsive even if cache persistence fails.
            pass

    def _restore_cached_directories(self):
        """Restore the last-used project directories, if they still exist."""
        cached_a = app_info_cache.get(self.PROJECT_A_CACHE_KEY, "")
        cached_b = app_info_cache.get(self.PROJECT_B_CACHE_KEY, "")
        if cached_a and os.path.isdir(cached_a):
            self.project_a_input.setText(cached_a)
        if cached_b and os.path.isdir(cached_b):
            self.project_b_input.setText(cached_b)

    def _on_respect_gitignore_changed(self, *_args):
        """Persist the .gitignore toggle whenever the user changes it."""
        app_info_cache.set(self.RESPECT_GITIGNORE_CACHE_KEY, self.respect_gitignore_checkbox.isChecked())
        try:
            app_info_cache.store()
        except Exception:
            # Keep UI responsive even if cache persistence fails.
            pass

    def _restore_respect_gitignore(self):
        """Restore the cached .gitignore toggle (defaults to on)."""
        self.respect_gitignore_checkbox.setChecked(
            bool(app_info_cache.get(self.RESPECT_GITIGNORE_CACHE_KEY, True))
        )

    def _current_global_exclusions(self):
        """Return the global exclusion patterns currently shown in the list."""
        return [
            self.global_exclusions_list.item(i).text()
            for i in range(self.global_exclusions_list.count())
        ]

    def _save_global_exclusions(self):
        """Persist the global exclusion list -- shared across all project
        comparisons, independent of any single project's own .gitignore."""
        app_info_cache.set(self.GLOBAL_EXCLUSIONS_CACHE_KEY, self._current_global_exclusions())
        try:
            app_info_cache.store()
        except Exception:
            # Keep UI responsive even if cache persistence fails.
            pass

    def _restore_global_exclusions(self):
        """Restore the cached global exclusion list."""
        patterns = app_info_cache.get(self.GLOBAL_EXCLUSIONS_CACHE_KEY, [])
        if not isinstance(patterns, list):
            patterns = []
        self.global_exclusions_list.clear()
        for pattern in patterns:
            self.global_exclusions_list.addItem(pattern)

    def _add_global_exclusion(self):
        """Add the pattern currently typed into the exclusion input."""
        # Normalize the same way .gitignore lines are (diff/project_compare.py's
        # load_gitignore_patterns), so "build/" behaves identically regardless
        # of whether it came from a .gitignore or was typed in here.
        pattern = self.global_exclusion_input.text().strip().rstrip("/")
        if not pattern or pattern in self._current_global_exclusions():
            self.global_exclusion_input.clear()
            return
        self.global_exclusions_list.addItem(pattern)
        self.global_exclusion_input.clear()
        self._save_global_exclusions()

    def _remove_selected_global_exclusions(self):
        """Remove the selected pattern(s) from the exclusion list."""
        for item in self.global_exclusions_list.selectedItems():
            self.global_exclusions_list.takeItem(self.global_exclusions_list.row(item))
        self._save_global_exclusions()
