"""Diff mode widget for comparing code files."""

import os
import hashlib
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QTextEdit, QLabel, QComboBox, QMessageBox, QFileDialog, QSplitter,
    QTabWidget, QProgressBar, QListWidgetItem, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, QThread, Signal

from diff.diff_engine import DiffEngine, DiffType, FileMetadata
from diff.llm_analyzer import DiffLLMAnalyzer
from ui.formatting import markdown_to_html, DiffHighlighter
from utils.app_info_cache import app_info_cache



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


class DiffModeWidget(QWidget):
    """Widget for diff mode."""
    
    def __init__(self):
        super().__init__()
        self.diff_engine = DiffEngine()
        self.current_diff_lines = []
        self.llm_analyzer = DiffLLMAnalyzer()
        self.llm_analysis_worker = None
        self.llm_generation_worker = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        
        # Top panel - File selection
        top_panel = QWidget()
        top_layout = QHBoxLayout(top_panel)
        
        self.add_file_button = QPushButton("Add File")
        self.add_file_button.clicked.connect(self.add_file)
        top_layout.addWidget(self.add_file_button)
        
        self.clear_files_button = QPushButton("Clear Files")
        self.clear_files_button.clicked.connect(self.clear_files)
        top_layout.addWidget(self.clear_files_button)
        
        top_layout.addWidget(QLabel("Compare:"))
        
        self.file_a_combo = QComboBox()
        self.file_a_combo.currentIndexChanged.connect(self.update_diff)
        top_layout.addWidget(self.file_a_combo)
        
        top_layout.addWidget(QLabel("vs"))
        
        self.file_b_combo = QComboBox()
        self.file_b_combo.currentIndexChanged.connect(self.update_diff)
        top_layout.addWidget(self.file_b_combo)
        
        self.unified_diff_button = QPushButton("Show Unified Diff")
        self.unified_diff_button.clicked.connect(self.show_unified_diff)
        top_layout.addWidget(self.unified_diff_button)
        
        self.html_diff_button = QPushButton("Show HTML Diff")
        self.html_diff_button.clicked.connect(self.show_html_diff)
        top_layout.addWidget(self.html_diff_button)
        
        top_layout.addStretch()
        
        layout.addWidget(top_panel)
        
        # File list
        file_list_label = QLabel("Added Files:")
        layout.addWidget(file_list_label)
        
        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(100)
        self.file_list_widget.setToolTip("Files added for comparison. Shows filename and directory context.")
        layout.addWidget(self.file_list_widget)
        
        # Main diff display
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side - Line-by-line diff
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("Line-by-Line Diff:"))
        
        self.diff_text = QTextEdit()
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
        self.file_a_label = QLabel("File A:")
        file_a_layout.addWidget(self.file_a_label)
        
        self.file_a_text = QTextEdit()
        self.file_a_text.setReadOnly(True)
        self.file_a_text.setFontFamily("Courier")
        file_a_layout.addWidget(self.file_a_text)
        
        # File B display
        file_b_layout = QVBoxLayout()
        self.file_b_label = QLabel("File B:")
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
        tabs.addTab(splitter, "Diff View")
        
        # LLM Analysis tab
        llm_tab = self.create_llm_analysis_tab()
        tabs.addTab(llm_tab, "LLM Analysis")
        
        # File Grouping tab
        grouping_tab = self.create_file_grouping_tab()
        tabs.addTab(grouping_tab, "File Grouping")
        
        # Request History tab
        history_tab = self.create_request_history_tab()
        tabs.addTab(history_tab, "Request History")
        
        layout.addWidget(tabs)
    
    def add_file(self):
        """Add a file to compare."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select file to compare", "", "All Files (*)"
        )
        if filename:
            try:
                self.diff_engine.add_file(filename)
                # Show filename with directory context
                dir_context = os.path.dirname(filename) or "."
                display_name = f"{os.path.basename(filename)} ({dir_context})"
                item = QListWidgetItem(display_name)
                item.setToolTip(filename)  # Full path in tooltip
                self.file_list_widget.addItem(item)
                self.update_file_combos()
                self.update_base_file_combo()
                self.update_file_groups()  # Update grouping tab
                QMessageBox.information(self, "Success", f"Added file: {os.path.basename(filename)}\nFrom: {dir_context}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add file: {str(e)}")
    
    def clear_files(self):
        """Clear all added files."""
        reply = QMessageBox.question(
            self, "Confirm Clear",
            "Are you sure you want to clear all files?",
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
            return
        
        if file_a_idx == file_b_idx:
            self.diff_text.setPlainText("Select two different files to compare.")
            self.file_a_text.clear()
            self.file_b_text.clear()
            return
        
        try:
            # Get diff lines
            diff_lines = self.diff_engine.compare_two_files(file_a_idx, file_b_idx)
            self.current_diff_lines = diff_lines
            
            # Update line-by-line diff
            diff_text_lines = []
            for diff_line in diff_lines:
                diff_text_lines.append(diff_line.unified_line.rstrip('\n'))
            
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
            self.file_a_label.setText(f"File A: {file_a_name} ({file_a_dir})")
            self.file_b_label.setText(f"File B: {file_b_name} ({file_b_dir})")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate diff: {str(e)}")
    
    def show_unified_diff(self):
        """Show unified diff format."""
        file_a_idx = self.file_a_combo.currentData()
        file_b_idx = self.file_b_combo.currentData()
        
        if file_a_idx is None or file_b_idx is None:
            QMessageBox.warning(self, "Warning", "Please select two files to compare.")
            return
        
        if file_a_idx == file_b_idx:
            QMessageBox.warning(self, "Warning", "Please select two different files.")
            return
        
        try:
            unified_diff = self.diff_engine.get_unified_diff(file_a_idx, file_b_idx)
            self.diff_text.setPlainText(unified_diff)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate unified diff: {str(e)}")
    
    def show_html_diff(self):
        """Show HTML diff in a new window."""
        file_a_idx = self.file_a_combo.currentData()
        file_b_idx = self.file_b_combo.currentData()
        
        if file_a_idx is None or file_b_idx is None:
            QMessageBox.warning(self, "Warning", "Please select two files to compare.")
            return
        
        if file_a_idx == file_b_idx:
            QMessageBox.warning(self, "Warning", "Please select two different files.")
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
                self, "HTML Diff",
                f"HTML diff opened in your default browser.\nTemporary file: {temp_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate HTML diff: {str(e)}")
    
    def create_llm_analysis_tab(self) -> QWidget:
        """Create the LLM analysis tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Input section
        input_group = QWidget()
        input_layout = QVBoxLayout(input_group)
        
        input_layout.addWidget(QLabel("Target Context:"))
        self.target_context_input = QTextEdit()
        self.target_context_input.setPlaceholderText(
            "Describe the target application/context where you want to use this tool module..."
        )
        self.target_context_input.setMaximumHeight(80)
        input_layout.addWidget(self.target_context_input)
        
        input_layout.addWidget(QLabel("Specific Requirements (optional):"))
        self.requirements_input = QTextEdit()
        default_requirements = "Please identify the module with the most up-to-date and complete basic logic, irrespective of custom logic native to each application context."
        self.requirements_input.setPlaceholderText(default_requirements)
        self.requirements_default = default_requirements  # Store for use as default
        self.requirements_input.setMaximumHeight(80)
        input_layout.addWidget(self.requirements_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.analyze_button = QPushButton("Analyze Versions")
        self.analyze_button.clicked.connect(self.run_llm_analysis)
        button_layout.addWidget(self.analyze_button)
        
        self.generate_button = QPushButton("Generate Merged Version")
        self.generate_button.clicked.connect(self.generate_merged_version)
        button_layout.addWidget(self.generate_button)
        
        self.base_file_combo = QComboBox()
        self.base_file_combo.setToolTip("Select base file for generation (optional)")
        button_layout.addWidget(QLabel("Base File:"))
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
        self.llm_progress.setFormat("Processing LLM request...")
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
        analysis_header_layout.addWidget(QLabel("Analysis Results:"))
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
        code_header_layout.addWidget(QLabel("Generated Code:"))
        self.code_status_label = QLabel("")
        self.code_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        code_header_layout.addStretch()
        code_header_layout.addWidget(self.code_status_label)
        code_layout.addLayout(code_header_layout)
        self.generated_code = QTextEdit()
        self.generated_code.setFontFamily("Courier")
        code_layout.addWidget(self.generated_code)
        
        # Save button
        save_button = QPushButton("Save Generated Code")
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
                self, "Warning",
                "Please add at least 2 files to analyze."
            )
            return
        
        # Cancel any existing worker
        if self.llm_analysis_worker and self.llm_analysis_worker.isRunning():
            self.llm_analysis_worker.terminate()
            self.llm_analysis_worker.wait()
        
        # Show progress indicators
        self.llm_progress.setVisible(True)
        self.llm_progress.setRange(0, 0)  # Indeterminate
        self.llm_status_label.setText("⏳ Processing analysis request...")
        self.analysis_status_label.setText("⏳ Processing...")
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
            error_text = f"❌ Error: {result['error']}"
            html_content = markdown_to_html(error_text)
            self.analysis_results.setHtml(html_content)
            self.analysis_status_label.setText("❌ Error")
        else:
            analysis_text = result.get('analysis', 'No analysis available')
            recommendation = result.get('recommendation', {})
            
            display_text = analysis_text
            if recommendation and recommendation.get('recommended_file_index') is not None:
                idx = recommendation['recommended_file_index']
                metadata = file_metadata[idx]
                filename = metadata['filename']
                dir_context = metadata['directory_context']
                # Use 1-based indexing for display
                display_text += f"\n\n## Recommended File\n\n"
                display_text += f"**File {idx+1}**: `{filename}` (from `{dir_context}`)\n"
            
            html_content = markdown_to_html(display_text)
            self.analysis_results.setHtml(html_content)
            self.analysis_status_label.setText("✅ Complete")
            
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
        QMessageBox.critical(self, "Error", f"Analysis failed: {error_msg}")
        html_content = markdown_to_html(f"Error: {error_msg}")
        self.analysis_results.setHtml(html_content)
        self.analysis_status_label.setText("❌ Error")
        
        # Clean up
        self.llm_progress.setVisible(False)
        self.llm_status_label.setText("")
        self.analyze_button.setEnabled(True)
        self.llm_analysis_worker = None
    
    def generate_merged_version(self):
        """Generate a merged version using LLM."""
        if self.diff_engine.get_file_count() < 1:
            QMessageBox.warning(
                self, "Warning",
                "Please add at least 1 file to generate from."
            )
            return
        
        target_context = self.target_context_input.toPlainText().strip()
        if not target_context:
            QMessageBox.warning(
                self, "Warning",
                "Please provide a target context."
            )
            return
        
        # Cancel any existing worker
        if self.llm_generation_worker and self.llm_generation_worker.isRunning():
            self.llm_generation_worker.terminate()
            self.llm_generation_worker.wait()
        
        # Show progress indicators
        self.llm_progress.setVisible(True)
        self.llm_progress.setRange(0, 0)  # Indeterminate
        self.llm_progress.setFormat("Generating merged version...")
        self.llm_status_label.setText("⏳ Generating code...")
        self.code_status_label.setText("⏳ Processing...")
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
            error_text = f"❌ Error: {result['error']}"
            self.generated_code.setPlainText(error_text)
            self.code_status_label.setText("❌ Error")
        else:
            code = result.get('code', 'No code generated')
            self.generated_code.setPlainText(code)
            self.code_status_label.setText("✅ Complete")
            
            if result.get('explanation'):
                explanation = result['explanation']
                if explanation != code:
                    html_content = markdown_to_html(f"## Generation Explanation\n\n{explanation}")
                    self.analysis_results.setHtml(html_content)
            
            # Cache the request and response
            self._cache_llm_request('generation', result, self._pending_generation_data.get('file_metadata', []))
        
        # Clean up
        self.llm_progress.setVisible(False)
        self.llm_progress.setFormat("Processing LLM request...")
        self.llm_status_label.setText("")
        self.generate_button.setEnabled(True)
        self.llm_generation_worker = None
    
    def _on_generation_error(self, error_msg):
        """Handle error from LLM code generation."""
        QMessageBox.critical(self, "Error", f"Generation failed: {error_msg}")
        self.generated_code.setPlainText(f"Error: {error_msg}")
        self.code_status_label.setText("❌ Error")
        
        # Clean up
        self.llm_progress.setVisible(False)
        self.llm_progress.setFormat("Processing LLM request...")
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
        self.base_file_combo.insertItem(0, "None (merge all)", None)
        self.base_file_combo.setCurrentIndex(0)
    
    def save_generated_code(self):
        """Save the generated code to a file."""
        code = self.generated_code.toPlainText()
        if not code or code.startswith("Error:"):
            QMessageBox.warning(self, "Warning", "No code to save.")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Generated Code", "", "Python Files (*.py);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(code)
                QMessageBox.information(self, "Success", f"Code saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")
    
    def create_file_grouping_tab(self) -> QWidget:
        """Create the file grouping tab that groups files by content (size + hash)."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Header
        header_label = QLabel("Files grouped by content (size + hash). Identical files are grouped together.")
        header_label.setWordWrap(True)
        layout.addWidget(header_label)
        
        # Refresh button
        refresh_button = QPushButton("Refresh Groups")
        refresh_button.clicked.connect(self.update_file_groups)
        refresh_button.setToolTip("Recalculate file groups based on current files")
        layout.addWidget(refresh_button)
        
        # Tree widget for collapsible groups
        self.grouping_tree = QTreeWidget()
        self.grouping_tree.setHeaderLabels(["File / Group", "Size", "Hash", "Path"])
        self.grouping_tree.setColumnWidth(0, 300)
        self.grouping_tree.setColumnWidth(1, 100)
        self.grouping_tree.setColumnWidth(2, 150)
        self.grouping_tree.setColumnWidth(3, 400)
        self.grouping_tree.setAlternatingRowColors(True)
        self.grouping_tree.setToolTip("Groups of identical files. Expand groups to see individual files.")
        layout.addWidget(self.grouping_tree)
        
        # Info label
        self.grouping_info_label = QLabel("No files added yet.")
        layout.addWidget(self.grouping_info_label)
        
        # Update groups when files are added
        self.update_file_groups()
        
        return tab
    
    def update_file_groups(self):
        """Update the file grouping display."""
        import hashlib
        
        self.grouping_tree.clear()
        
        if self.diff_engine.get_file_count() == 0:
            self.grouping_info_label.setText("No files added yet.")
            return
        
        # Calculate hash for each file
        file_hashes = {}
        file_sizes = {}
        
        for i, (filepath, _) in enumerate(self.diff_engine.files):
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
            group_item.setText(0, f"Group {group_number} ({len(filepaths)} file{'s' if len(filepaths) > 1 else ''})")
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
                f"All {total_files} file(s) are unique (no duplicates found)."
            )
        else:
            duplicates = total_files - unique_groups
            self.grouping_info_label.setText(
                f"Found {unique_groups} unique file group(s) from {total_files} file(s). "
                f"{duplicates} duplicate(s) detected."
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
        header_label = QLabel("View and restore previous LLM requests. Double-click an entry to restore its configuration.")
        header_label.setWordWrap(True)
        layout.addWidget(header_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        refresh_button = QPushButton("Refresh History")
        refresh_button.clicked.connect(self.update_request_history)
        button_layout.addWidget(refresh_button)
        
        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self.delete_selected_history_entry)
        button_layout.addWidget(delete_button)
        
        clear_all_button = QPushButton("Clear All History")
        clear_all_button.clicked.connect(self.clear_all_history)
        button_layout.addWidget(clear_all_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # List widget for history entries
        self.history_list_widget = QListWidget()
        self.history_list_widget.setAlternatingRowColors(True)
        self.history_list_widget.itemDoubleClicked.connect(self.restore_history_entry)
        self.history_list_widget.setToolTip("Double-click an entry to restore its file configuration and view the cached response.")
        layout.addWidget(self.history_list_widget)
        
        # Details panel
        details_label = QLabel("Entry Details:")
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
                self.history_list_widget.addItem("No cached requests found.")
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
                type_display = "Analysis" if request_type == 'analysis' else "Generation"
                
                # Show first few filenames
                if file_paths:
                    filenames = [os.path.basename(fp) for fp in file_paths[:3]]
                    files_display = ', '.join(filenames)
                    if len(file_paths) > 3:
                        files_display += f" (+{len(file_paths) - 3} more)"
                else:
                    files_display = "No files"
                
                display_text = f"[{time_display}] {type_display} - {file_count} file(s): {files_display}"
                
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, entry_id)  # Store entry ID
                self.history_list_widget.addItem(item)
        except Exception as e:
            self.history_list_widget.addItem(f"Error loading history: {str(e)}")
    
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
                self.history_details.setPlainText("Entry not found.")
                return
            
            entry = history[entry_id]
            
            # Build details text
            details_lines = []
            details_lines.append(f"Request Type: {entry.get('request_type', 'unknown')}")
            details_lines.append(f"Timestamp: {entry.get('timestamp', 'unknown')}")
            details_lines.append(f"\nFiles ({len(entry.get('file_paths', []))}):")
            for i, filepath in enumerate(entry.get('file_paths', []), 1):
                filename = os.path.basename(filepath)
                dir_context = os.path.dirname(filepath) or "."
                details_lines.append(f"  {i}. {filename} (from {dir_context})")
                details_lines.append(f"     {filepath}")
            
            target_context = entry.get('target_context')
            if target_context:
                details_lines.append(f"\nTarget Context: {target_context}")
            
            requirements = entry.get('requirements')
            if requirements:
                details_lines.append(f"\nRequirements: {requirements}")
            
            base_file_index = entry.get('base_file_index')
            if base_file_index is not None:
                details_lines.append(f"\nBase File Index: {base_file_index}")
            
            result = entry.get('result', {})
            if result.get('error'):
                details_lines.append(f"\nResult: Error - {result.get('error')}")
            else:
                if entry.get('request_type') == 'analysis':
                    details_lines.append(f"\nResult: Analysis completed successfully")
                else:
                    details_lines.append(f"\nResult: Code generation completed successfully")
            
            self.history_details.setPlainText('\n'.join(details_lines))
        except Exception as e:
            self.history_details.setPlainText(f"Error loading details: {str(e)}")
    
    def restore_history_entry(self, item):
        """Restore a history entry's configuration."""
        try:
            entry_id = item.data(Qt.UserRole)
            cache_key = 'diff_mode_llm_history'
            history = app_info_cache.get(cache_key, {})
            
            if entry_id not in history:
                QMessageBox.warning(self, "Error", "Entry not found in cache.")
                return
            
            entry = history[entry_id]
            file_paths = entry.get('file_paths', [])
            
            if not file_paths:
                QMessageBox.warning(self, "Error", "No files found in this entry.")
                return
            
            # Confirm restoration
            reply = QMessageBox.question(
                self, "Restore Configuration",
                f"This will replace your current file configuration with {len(file_paths)} file(s).\n"
                f"Continue?",
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
                        self.diff_engine.add_file(filepath)
                        dir_context = os.path.dirname(filepath) or "."
                        display_name = f"{os.path.basename(filepath)} ({dir_context})"
                        list_item = QListWidgetItem(display_name)
                        list_item.setToolTip(filepath)
                        self.file_list_widget.addItem(list_item)
                    except Exception as e:
                        QMessageBox.warning(
                            self, "Warning",
                            f"Failed to add file {filepath}: {str(e)}"
                        )
                else:
                    QMessageBox.warning(
                        self, "Warning",
                        f"File no longer exists: {filepath}"
                    )
            
            # Update UI
            self.update_file_combos()
            self.update_base_file_combo()
            self.update_file_groups()
            
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
                    error_text = f"❌ Error: {result['error']}"
                    html_content = markdown_to_html(error_text)
                    self.analysis_results.setHtml(html_content)
                    self.analysis_status_label.setText("❌ Error (cached)")
                else:
                    analysis_text = result.get('analysis', 'No analysis available')
                    recommendation = result.get('recommendation', {})
                    
                    display_text = analysis_text
                    if recommendation and recommendation.get('recommended_file_index') is not None:
                        idx = recommendation['recommended_file_index']
                        file_metadata = entry.get('file_metadata', [])
                        if idx < len(file_metadata):
                            metadata = file_metadata[idx]
                            filename = metadata.get('filename', 'unknown')
                            dir_context = metadata.get('directory_context', 'unknown')
                            display_text += f"\n\n## Recommended File\n\n"
                            display_text += f"**File {idx+1}**: `{filename}` (from `{dir_context}`)\n"
                    
                    html_content = markdown_to_html(display_text)
                    self.analysis_results.setHtml(html_content)
                    self.analysis_status_label.setText("✅ Complete (cached)")
            else:  # generation
                if result.get('error'):
                    error_text = f"❌ Error: {result['error']}"
                    self.generated_code.setPlainText(error_text)
                    self.code_status_label.setText("❌ Error (cached)")
                else:
                    code = result.get('code', 'No code generated')
                    self.generated_code.setPlainText(code)
                    self.code_status_label.setText("✅ Complete (cached)")
                    
                    if result.get('explanation'):
                        explanation = result['explanation']
                        if explanation != code:
                            html_content = markdown_to_html(f"## Generation Explanation\n\n{explanation}")
                            self.analysis_results.setHtml(html_content)
            
            # Switch to LLM Analysis tab
            # Find the parent tab widget
            parent = self.parent()
            while parent and not isinstance(parent, QTabWidget):
                parent = parent.parent()
            if parent:
                # Find the tab index for LLM Analysis
                for i in range(parent.count()):
                    if parent.tabText(i) == "LLM Analysis":
                        parent.setCurrentIndex(i)
                        break
            
            QMessageBox.information(
                self, "Restored",
                f"Configuration restored from {entry.get('timestamp', 'unknown')}.\n"
                f"Cached response displayed in LLM Analysis tab."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restore entry: {str(e)}")
    
    def delete_selected_history_entry(self):
        """Delete the selected history entry."""
        selected_items = self.history_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select an entry to delete.")
            return
        
        try:
            entry_id = selected_items[0].data(Qt.UserRole)
            
            reply = QMessageBox.question(
                self, "Confirm Delete",
                "Are you sure you want to delete this entry?",
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
            QMessageBox.critical(self, "Error", f"Failed to delete entry: {str(e)}")
    
    def clear_all_history(self):
        """Clear all cached history entries."""
        reply = QMessageBox.question(
            self, "Confirm Clear All",
            "Are you sure you want to clear all cached history?\nThis cannot be undone.",
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
            QMessageBox.information(self, "Success", "All history cleared.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear history: {str(e)}")

