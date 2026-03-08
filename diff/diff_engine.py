"""Diff engine for comparing code files."""

import difflib
import os
from datetime import datetime
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field
from enum import Enum


class DiffType(Enum):
    """Types of differences between files."""
    EQUAL = "equal"
    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"


@dataclass
class DiffLine:
    """Represents a single line in a diff."""
    line_type: DiffType
    line_num_a: Optional[int]
    line_num_b: Optional[int]
    content_a: Optional[str]
    content_b: Optional[str]
    unified_line: str


@dataclass
class FileMetadata:
    """Metadata about a file."""
    filepath: str
    modification_time: datetime
    size: int
    line_count: int
    directory_context: str
    filename: str
    
    @classmethod
    def from_file(cls, filepath: str) -> 'FileMetadata':
        """Create metadata from a file path."""
        stat = os.stat(filepath)
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        
        # Count lines
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            line_count = sum(1 for _ in f)
        
        directory_context = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        
        return cls(
            filepath=filepath,
            modification_time=mod_time,
            size=stat.st_size,
            line_count=line_count,
            directory_context=directory_context,
            filename=filename
        )
    
    def to_dict(self) -> Dict:
        """Convert metadata to dictionary for LLM compatibility."""
        return {
            'filepath': self.filepath,
            'filename': self.filename,
            'directory_context': self.directory_context,
            'modification_time': self.modification_time.strftime('%Y-%m-%d %H:%M:%S'),
            'size': self.size,
            'line_count': self.line_count
        }


class DiffEngine:
    """Engine for performing diffs between multiple code files."""
    
    def __init__(self):
        self.files: List[Tuple[str, List[str]]] = []  # List of (filename, lines)
        self.metadata: List[FileMetadata] = []  # List of file metadata
    
    def add_file(self, filepath: str, content: Optional[str] = None) -> None:
        """
        Add a file to compare.
        
        Args:
            filepath: Path to the file
            content: Optional file content. If None, reads from filepath
        """
        if content is None:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            # Collect metadata from actual file
            metadata = FileMetadata.from_file(filepath)
        else:
            lines = content.splitlines(keepends=True)
            if not lines or not lines[-1].endswith('\n'):
                lines.append('\n')
            # Create minimal metadata for content-based files
            metadata = FileMetadata(
                filepath=filepath,
                modification_time=datetime.now(),
                size=len(content.encode('utf-8')),
                line_count=len(lines),
                directory_context=os.path.dirname(filepath) if os.path.dirname(filepath) else ".",
                filename=os.path.basename(filepath)
            )
        
        self.files.append((filepath, lines))
        self.metadata.append(metadata)
    
    @staticmethod
    def _normalize_line_for_diff(line: str, highlight_whitespace_only_diffs: bool) -> str:
        """Normalize a line for comparison when whitespace-only changes should be ignored."""
        if highlight_whitespace_only_diffs:
            return line

        # Ignore trailing whitespace-only differences and blank-line whitespace changes.
        # Keep leading indentation differences because they can be semantically meaningful.
        # TODO: Add per-language handling for indentation-insensitive languages.
        normalized = line.rstrip("\r\n").rstrip(" \t")
        if normalized.strip(" \t") == "":
            return ""
        return normalized

    @staticmethod
    def _is_whitespace_only_line(line: Optional[str]) -> bool:
        """Return True when a line only contains whitespace/newline characters."""
        if line is None:
            return False
        return line.rstrip("\r\n").strip(" \t") == ""

    def compare_two_files(
        self,
        file_a: int,
        file_b: int,
        highlight_whitespace_only_diffs: bool = True
    ) -> List[DiffLine]:
        """
        Compare two files by index.
        
        Args:
            file_a: Index of first file
            file_b: Index of second file
            
        Returns:
            List of DiffLine objects representing the differences
        """
        if file_a >= len(self.files) or file_b >= len(self.files):
            raise IndexError("File index out of range")
        
        name_a, lines_a = self.files[file_a]
        name_b, lines_b = self.files[file_b]
        
        diff_lines = []
        comparable_a = [
            self._normalize_line_for_diff(line, highlight_whitespace_only_diffs)
            for line in lines_a
        ]
        comparable_b = [
            self._normalize_line_for_diff(line, highlight_whitespace_only_diffs)
            for line in lines_b
        ]
        matcher = difflib.SequenceMatcher(None, comparable_a, comparable_b)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for idx, line in enumerate(lines_a[i1:i2]):
                    diff_lines.append(DiffLine(
                        line_type=DiffType.EQUAL,
                        line_num_a=i1 + idx + 1,
                        line_num_b=j1 + idx + 1,
                        content_a=line,
                        content_b=lines_b[j1 + idx],
                        unified_line=line
                    ))
            elif tag == 'delete':
                for idx, line in enumerate(lines_a[i1:i2]):
                    if (not highlight_whitespace_only_diffs
                            and self._is_whitespace_only_line(line)):
                        continue
                    diff_lines.append(DiffLine(
                        line_type=DiffType.DELETE,
                        line_num_a=i1 + idx + 1,
                        line_num_b=None,
                        content_a=line,
                        content_b=None,
                        unified_line=f"- {line}"
                    ))
            elif tag == 'insert':
                for idx, line in enumerate(lines_b[j1:j2]):
                    if (not highlight_whitespace_only_diffs
                            and self._is_whitespace_only_line(line)):
                        continue
                    diff_lines.append(DiffLine(
                        line_type=DiffType.INSERT,
                        line_num_a=None,
                        line_num_b=j1 + idx + 1,
                        content_a=None,
                        content_b=line,
                        unified_line=f"+ {line}"
                    ))
            elif tag == 'replace':
                # Add deleted lines
                for idx, line in enumerate(lines_a[i1:i2]):
                    if (not highlight_whitespace_only_diffs
                            and self._is_whitespace_only_line(line)):
                        continue
                    diff_lines.append(DiffLine(
                        line_type=DiffType.DELETE,
                        line_num_a=i1 + idx + 1,
                        line_num_b=None,
                        content_a=line,
                        content_b=None,
                        unified_line=f"- {line}"
                    ))
                # Add inserted lines
                for idx, line in enumerate(lines_b[j1:j2]):
                    if (not highlight_whitespace_only_diffs
                            and self._is_whitespace_only_line(line)):
                        continue
                    diff_lines.append(DiffLine(
                        line_type=DiffType.INSERT,
                        line_num_a=None,
                        line_num_b=j1 + idx + 1,
                        content_a=None,
                        content_b=line,
                        unified_line=f"+ {line}"
                    ))
        
        return diff_lines
    
    def get_unified_diff(self, file_a: int, file_b: int, context_lines: int = 3) -> str:
        """
        Get unified diff format string.
        
        Args:
            file_a: Index of first file
            file_b: Index of second file
            context_lines: Number of context lines to include
            
        Returns:
            Unified diff string (cleaned of excessive blank lines)
        """
        if file_a >= len(self.files) or file_b >= len(self.files):
            raise IndexError("File index out of range")
        
        name_a, lines_a = self.files[file_a]
        name_b, lines_b = self.files[file_b]
        
        diff = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=name_a,
            tofile=name_b,
            lineterm='',
            n=context_lines
        )
        
        diff_text = '\n'.join(diff)
        
        # Clean up excessive blank lines
        return self._clean_unified_diff(diff_text)
    
    def _clean_unified_diff(self, diff_text: str) -> str:
        """Clean unified diff text by removing all blank lines."""
        if not diff_text or not diff_text.strip():
            return ""
        
        lines = diff_text.split('\n')
        # Remove ALL blank lines - filter out any line that is empty or contains only whitespace
        cleaned_lines = [line for line in lines if line.strip()]
        
        return '\n'.join(cleaned_lines)
    
    def get_html_diff(self, file_a: int, file_b: int) -> str:
        """
        Get HTML formatted diff.
        
        Args:
            file_a: Index of first file
            file_b: Index of second file
            
        Returns:
            HTML string with diff highlighting
        """
        if file_a >= len(self.files) or file_b >= len(self.files):
            raise IndexError("File index out of range")
        
        name_a, lines_a = self.files[file_a]
        name_b, lines_b = self.files[file_b]
        
        differ = difflib.HtmlDiff(wrapcolumn=80)
        html = differ.make_file(
            lines_a,
            lines_b,
            fromdesc=name_a,
            todesc=name_b,
            context=True,
            numlines=3
        )
        
        return html
    
    def compare_all_files(self) -> List[Dict]:
        """
        Compare all files pairwise.
        
        Returns:
            List of diff results for each pair with metadata
        """
        results = []
        for i in range(len(self.files)):
            for j in range(i + 1, len(self.files)):
                diff = self.compare_two_files(i, j)
                unified_diff = self.get_unified_diff(i, j)
                
                # Calculate statistics
                insertions = sum(1 for d in diff if d.line_type == DiffType.INSERT)
                deletions = sum(1 for d in diff if d.line_type == DiffType.DELETE)
                changes = insertions + deletions
                
                results.append({
                    'file_a_index': i,
                    'file_b_index': j,
                    'file_a': self.files[i][0],
                    'file_b': self.files[j][0],
                    'metadata_a': self.metadata[i].to_dict(),
                    'metadata_b': self.metadata[j].to_dict(),
                    'diff': diff,
                    'unified_diff': unified_diff,
                    'statistics': {
                        'insertions': insertions,
                        'deletions': deletions,
                        'total_changes': changes,
                        'similarity_ratio': difflib.SequenceMatcher(
                            None, 
                            self.files[i][1], 
                            self.files[j][1]
                        ).ratio()
                    }
                })
        return results
    
    def clear_files(self):
        """Clear all added files."""
        self.files = []
        self.metadata = []
    
    def get_file_content(self, index: int) -> str:
        """Get the full content of a file by index."""
        if index >= len(self.files):
            raise IndexError("File index out of range")
        return ''.join(self.files[index][1])
    
    def get_diff_matrix_summary(self) -> str:
        """
        Generate a summary of the diff matrix for LLM analysis.
        
        Returns:
            Formatted string with file metadata and diff statistics
        """
        if len(self.files) < 2:
            return "Not enough files to generate diff matrix."
        
        summary_lines = []
        summary_lines.append("=" * 80)
        summary_lines.append("FILE METADATA")
        summary_lines.append("=" * 80)
        
        for i, metadata in enumerate(self.metadata):
            summary_lines.append(f"\nFile {i}: {metadata.filename}")
            summary_lines.append(f"  Path: {metadata.filepath}")
            summary_lines.append(f"  Directory Context: {metadata.directory_context}")
            summary_lines.append(f"  Modification Time: {metadata.modification_time.strftime('%Y-%m-%d %H:%M:%S')}")
            summary_lines.append(f"  Size: {metadata.size} bytes")
            summary_lines.append(f"  Lines: {metadata.line_count}")
        
        summary_lines.append("\n" + "=" * 80)
        summary_lines.append("DIFF MATRIX SUMMARY")
        summary_lines.append("=" * 80)
        
        comparisons = self.compare_all_files()
        for comp in comparisons:
            meta_a = comp['metadata_a']
            meta_b = comp['metadata_b']
            summary_lines.append(f"\n{meta_a['filename']} vs {meta_b['filename']}:")
            summary_lines.append(f"  Insertions: {comp['statistics']['insertions']}")
            summary_lines.append(f"  Deletions: {comp['statistics']['deletions']}")
            summary_lines.append(f"  Total Changes: {comp['statistics']['total_changes']}")
            summary_lines.append(f"  Similarity: {comp['statistics']['similarity_ratio']:.2%}")
            summary_lines.append(f"  File A Context: {meta_a['directory_context']}")
            summary_lines.append(f"  File B Context: {meta_b['directory_context']}")
            summary_lines.append(f"  File A Modified: {meta_a['modification_time']}")
            summary_lines.append(f"  File B Modified: {meta_b['modification_time']}")
        
        return '\n'.join(summary_lines)
    
    def get_file_count(self) -> int:
        """Get the number of files added."""
        return len(self.files)
    
    def get_file_names(self) -> List[str]:
        """Get list of all file names."""
        return [name for name, _ in self.files]

