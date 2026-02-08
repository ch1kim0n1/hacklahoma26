"""File system context manager for PixelLink."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class FileInfo:
    """Information about a file."""

    path: str
    name: str
    size: int
    modified: datetime
    extension: str = ""

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)


class FileSystemContext:
    """Manages file system context for file queries."""

    DEFAULT_SEARCH_PATHS = [
        "~/Documents",
        "~/Desktop",
        "~/Downloads",
    ]

    INDEXABLE_EXTENSIONS = {
        ".txt", ".md", ".pdf", ".doc", ".docx", ".rtf",
        ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".go", ".rs",
        ".html", ".css", ".json", ".xml", ".yaml", ".yml",
        ".csv", ".xlsx", ".xls", ".db", ".sqlite",
        ".jpg", ".jpeg", ".png", ".gif", ".svg",
        ".zip", ".tar", ".gz",
    }

    def __init__(self, search_paths: Optional[List[str]] = None, max_files: int = 10000):
        self.search_paths = search_paths or self.DEFAULT_SEARCH_PATHS
        self.max_files = max_files
        self.indexed_files: List[FileInfo] = []
        self.last_indexed: Optional[datetime] = None
        self._excluded_dirs = {".git", ".venv", "node_modules", "__pycache__", ".cache"}

    def index_files(self, force: bool = False) -> int:
        if not force and self.last_indexed is not None:
            return len(self.indexed_files)

        self.indexed_files.clear()
        for search_path in self.search_paths:
            expanded_path = os.path.expanduser(search_path)
            if not os.path.exists(expanded_path):
                continue
            try:
                self._index_directory(expanded_path)
            except Exception:
                continue

        self.indexed_files.sort(key=lambda f: f.modified, reverse=True)
        if len(self.indexed_files) > self.max_files:
            self.indexed_files = self.indexed_files[: self.max_files]

        self.last_indexed = datetime.now()
        return len(self.indexed_files)

    def _index_directory(self, directory: str) -> None:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in self._excluded_dirs]
            for filename in files:
                if len(self.indexed_files) >= self.max_files:
                    return
                ext = os.path.splitext(filename)[1].lower()
                if ext not in self.INDEXABLE_EXTENSIONS:
                    continue
                file_path = os.path.join(root, filename)
                file_info = self._build_file_info(file_path)
                if file_info:
                    self.indexed_files.append(file_info)

    def search_files(self, query: str, limit: int = 20) -> List[FileInfo]:
        """Search files by name/path. Uses macOS Spotlight fast-path when enabled."""
        query = (query or "").strip()
        if not query:
            return []

        mdfind_results = self._search_with_mdfind(query, limit)
        if mdfind_results:
            return mdfind_results

        if not self.indexed_files:
            self.index_files()

        query_lower = query.lower()
        matches: List[FileInfo] = []
        for file_info in self.indexed_files:
            if query_lower in file_info.name.lower() or query_lower in file_info.path.lower():
                matches.append(file_info)
                if len(matches) >= limit:
                    break
        return matches

    def get_recent_files(self, limit: int = 20, extension: Optional[str] = None) -> List[FileInfo]:
        if extension:
            return [f for f in self.indexed_files if f.extension == extension][:limit]
        return self.indexed_files[:limit]

    def get_files_by_extension(self, extension: str, limit: int = 20) -> List[FileInfo]:
        return [f for f in self.indexed_files if f.extension == extension][:limit]

    def find_exact_file(self, filename: str) -> Optional[FileInfo]:
        for file_info in self.indexed_files:
            if file_info.name.lower() == filename.lower():
                return file_info
        return None

    def get_context_summary(self) -> str:
        if not self.indexed_files:
            return "No files indexed. Run index_files() first."

        recent_files = self.get_recent_files(5)
        ext_counts: dict[str, int] = {}
        for file_info in self.indexed_files:
            ext_counts[file_info.extension] = ext_counts.get(file_info.extension, 0) + 1

        top_exts = sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        summary_parts = [
            f"Indexed {len(self.indexed_files)} files from {len(self.search_paths)} locations",
        ]

        if recent_files:
            summary_parts.append("\nRecent files:")
            for file_info in recent_files:
                time_str = file_info.modified.strftime("%Y-%m-%d %H:%M")
                summary_parts.append(f"  [{time_str}] {file_info.name} ({file_info.size_mb:.1f}MB)")

        if top_exts:
            ext_str = ", ".join([f"{ext}({count})" for ext, count in top_exts])
            summary_parts.append(f"\nTop file types: {ext_str}")

        return "\n".join(summary_parts)

    def _mdfind_enabled(self) -> bool:
        flag = os.getenv("PIXELINK_ENABLE_MDFIND", "1").strip().lower()
        return flag in {"1", "true", "yes", "on"}

    def _search_with_mdfind(self, query: str, limit: int) -> List[FileInfo]:
        if not self._mdfind_enabled():
            return []
        if platform.system() != "Darwin":
            return []
        if shutil.which("mdfind") is None:
            return []

        seen: set[str] = set()
        matches: List[FileInfo] = []
        for search_path in self.search_paths:
            root = os.path.expanduser(search_path)
            if not os.path.exists(root):
                continue
            try:
                result = subprocess.run(
                    ["mdfind", "-name", query, "-onlyin", root],
                    capture_output=True,
                    text=True,
                    timeout=1.2,
                    check=False,
                )
            except Exception:
                continue

            for line in result.stdout.splitlines():
                path = line.strip()
                if not path or path in seen:
                    continue
                seen.add(path)
                file_info = self._build_file_info(path)
                if not file_info:
                    continue
                matches.append(file_info)
                if len(matches) >= limit:
                    return matches

        return matches

    def _build_file_info(self, file_path: str) -> FileInfo | None:
        try:
            stat = os.stat(file_path)
        except Exception:
            return None

        path_obj = Path(file_path)
        ext = path_obj.suffix.lower()
        return FileInfo(
            path=str(path_obj),
            name=path_obj.name,
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime),
            extension=ext,
        )
