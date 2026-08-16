"""Engine for comparing two project directory trees file-by-file.

Files are matched between the two projects by relative path (not filename
alone), then categorized as identical, different, or present in only one of
the two projects. No Qt dependency -- driven by modes/project_compare_widget.py.
"""

import fnmatch
import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DEFAULT_IGNORE_PATTERNS = [
    # Version control metadata
    ".git",
    ".svn",
    ".hg",
    # Python
    "__pycache__",
    "venv",
    ".venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "*.egg-info",
    ".eggs",
    "*.pyc",
    # Node / JS
    "node_modules",
    ".next",
    ".nuxt",
    # Common build output (deliberately excludes compiled-object types like
    # *.so/*.o -- those can be artifacts a user actually wants to compare,
    # unlike these directories, which are always regenerable byproducts)
    "dist",
    "build",
    "target",
    # Test coverage artifacts
    ".coverage",
    "htmlcov",
    # IDE / editor
    ".idea",
    ".vscode",
    # OS cruft
    ".DS_Store",
    "Thumbs.db",
]

BINARY_CHECK_BYTES = 8192


@dataclass
class FileEntry:
    """A single file discovered during a project scan."""
    relative_path: str
    absolute_path: str
    size: int
    content_hash: str
    is_binary: bool


@dataclass
class ProjectComparisonResult:
    """Categorized outcome of comparing two project directories, keyed by
    the relative path shared between them."""
    identical: List[str] = field(default_factory=list)
    different: List[str] = field(default_factory=list)
    only_in_a: List[str] = field(default_factory=list)
    only_in_b: List[str] = field(default_factory=list)
    files_a: Dict[str, FileEntry] = field(default_factory=dict)
    files_b: Dict[str, FileEntry] = field(default_factory=dict)

    def get_absolute_paths(self, relative_path: str) -> Optional[Tuple[str, str]]:
        """Return (path_a, path_b) for a relative path present in both projects."""
        entry_a = self.files_a.get(relative_path)
        entry_b = self.files_b.get(relative_path)
        if entry_a is None or entry_b is None:
            return None
        return entry_a.absolute_path, entry_b.absolute_path


def _hash_file(filepath: str) -> str:
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
    except OSError:
        return ""
    return hasher.hexdigest()


def _is_binary_file(filepath: str) -> bool:
    """Heuristic: a null byte in the first few KB marks a file as binary."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(BINARY_CHECK_BYTES)
    except OSError:
        return False
    return b"\x00" in chunk


def load_gitignore_patterns(root_path: str) -> List[str]:
    """Read .gitignore patterns from a project root, if present."""
    gitignore_path = os.path.join(root_path, ".gitignore")
    if not os.path.isfile(gitignore_path):
        return []
    patterns = []
    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line.rstrip("/"))
    except OSError:
        pass
    return patterns


def _pattern_matches(pattern: str, name: str, relative_path: str) -> bool:
    if pattern.startswith("!"):
        # Negation ("un-ignore") patterns are not supported -- treated as
        # never matching, so the file stays excluded by any earlier pattern
        # that did match rather than being silently re-included.
        return False
    if pattern.startswith("/"):
        anchored = pattern.lstrip("/")
        return relative_path == anchored or fnmatch.fnmatch(relative_path, anchored)
    if "/" in pattern:
        return fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(relative_path, f"*/{pattern}")
    return fnmatch.fnmatch(name, pattern)


def _is_ignored(name: str, relative_path: str, patterns: List[str]) -> bool:
    return any(_pattern_matches(pattern, name, relative_path) for pattern in patterns)


class ProjectComparator:
    """Scans and compares two project directory trees."""

    def __init__(self, extra_ignore_patterns: Optional[List[str]] = None, respect_gitignore: bool = True):
        self.extra_ignore_patterns = list(extra_ignore_patterns) if extra_ignore_patterns else []
        self.respect_gitignore = respect_gitignore

    def scan(self, root_path: str) -> Dict[str, FileEntry]:
        """Recursively scan a project root, returning relative_path -> FileEntry.

        Symlinks (files and directories) are never followed. Paths matching
        the default ignore list or any extra patterns passed to the
        constructor are always skipped; the project's own .gitignore (if
        present) is additionally honored unless respect_gitignore is False.
        """
        root_path = os.path.abspath(root_path)
        gitignore_patterns = load_gitignore_patterns(root_path) if self.respect_gitignore else []
        ignore_patterns = DEFAULT_IGNORE_PATTERNS + self.extra_ignore_patterns + gitignore_patterns

        entries = {}
        for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
            rel_dir = os.path.relpath(dirpath, root_path).replace(os.sep, "/")
            if rel_dir == ".":
                rel_dir = ""

            pruned_dirnames = []
            for dirname in dirnames:
                dir_abs_path = os.path.join(dirpath, dirname)
                dir_rel_path = f"{rel_dir}/{dirname}" if rel_dir else dirname
                if os.path.islink(dir_abs_path):
                    continue
                if _is_ignored(dirname, dir_rel_path, ignore_patterns):
                    continue
                pruned_dirnames.append(dirname)
            dirnames[:] = pruned_dirnames

            for filename in filenames:
                file_abs_path = os.path.join(dirpath, filename)
                if os.path.islink(file_abs_path):
                    continue
                file_rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
                if _is_ignored(filename, file_rel_path, ignore_patterns):
                    continue
                try:
                    size = os.path.getsize(file_abs_path)
                except OSError:
                    continue
                entries[file_rel_path] = FileEntry(
                    relative_path=file_rel_path,
                    absolute_path=file_abs_path,
                    size=size,
                    content_hash=_hash_file(file_abs_path),
                    is_binary=_is_binary_file(file_abs_path),
                )
        return entries

    def compare(self, root_a: str, root_b: str) -> ProjectComparisonResult:
        """Compare two project roots, matching files by relative path."""
        files_a = self.scan(root_a)
        files_b = self.scan(root_b)

        result = ProjectComparisonResult(files_a=files_a, files_b=files_b)

        keys_a = set(files_a.keys())
        keys_b = set(files_b.keys())

        for relative_path in sorted(keys_a & keys_b):
            entry_a = files_a[relative_path]
            entry_b = files_b[relative_path]
            if entry_a.size == entry_b.size and entry_a.content_hash == entry_b.content_hash:
                result.identical.append(relative_path)
            else:
                result.different.append(relative_path)

        result.only_in_a = sorted(keys_a - keys_b)
        result.only_in_b = sorted(keys_b - keys_a)

        return result
