"""File system context manager for PixelLink."""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Set, Optional


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
        """File size in MB."""
        return self.size / (1024 * 1024)


class FileSystemContext:
    """Manages file system context for queries."""
    
    # Common directories to search
    DEFAULT_SEARCH_PATHS = [
        "~/Documents",
        "~/Desktop",
        "~/Downloads",
    ]
    
    # File extensions to index
    INDEXABLE_EXTENSIONS = {
        # Documents
        ".txt", ".md", ".pdf", ".doc", ".docx", ".rtf",
        # Code
        ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".go", ".rs",
        ".html", ".css", ".json", ".xml", ".yaml", ".yml",
        # Data
        ".csv", ".xlsx", ".xls", ".db", ".sqlite",
        # Images (for reference)
        ".jpg", ".jpeg", ".png", ".gif", ".svg",
        # Other
        ".zip", ".tar", ".gz",
    }
    
    def __init__(self, search_paths: Optional[List[str]] = None, max_files: int = 10000):
        self.search_paths = search_paths or self.DEFAULT_SEARCH_PATHS
        self.max_files = max_files
        self.indexed_files: List[FileInfo] = []
        self.last_indexed: Optional[datetime] = None
        self._excluded_dirs = {".git", ".venv", "node_modules", "__pycache__", ".cache"}
    
    def index_files(self, force: bool = False) -> int:
        """Index files in search paths. Returns number of files indexed."""
        # Only re-index if forced or never indexed
        if not force and self.last_indexed is not None:
            return len(self.indexed_files)
        
        self.indexed_files.clear()
        
        for search_path in self.search_paths:
            expanded_path = os.path.expanduser(search_path)
            if not os.path.exists(expanded_path):
                continue
            
            try:
                self._index_directory(expanded_path)
            except Exception as e:
                print(f"Warning: Could not index {expanded_path}: {e}")
        
        # Sort by modified time (most recent first)
        self.indexed_files.sort(key=lambda f: f.modified, reverse=True)
        
        # Limit total files
        if len(self.indexed_files) > self.max_files:
            self.indexed_files = self.indexed_files[:self.max_files]
        
        self.last_indexed = datetime.now()
        return len(self.indexed_files)
    
    def _index_directory(self, directory: str) -> None:
        """Recursively index a directory."""
        try:
            for root, dirs, files in os.walk(directory):
                # Remove excluded directories from traversal
                dirs[:] = [d for d in dirs if d not in self._excluded_dirs]
                
                for filename in files:
                    # Check if we've hit the limit
                    if len(self.indexed_files) >= self.max_files:
                        return
                    
                    file_path = os.path.join(root, filename)
                    ext = os.path.splitext(filename)[1].lower()
                    
                    # Only index known extensions
                    if ext not in self.INDEXABLE_EXTENSIONS:
                        continue
                    
                    try:
                        stat = os.stat(file_path)
                        file_info = FileInfo(
                            path=file_path,
                            name=filename,
                            size=stat.st_size,
                            modified=datetime.fromtimestamp(stat.st_mtime),
                            extension=ext,
                        )
                        self.indexed_files.append(file_info)
                    except Exception:
                        # Skip files we can't access
                        continue
        except Exception:
            # Skip directories we can't access
            pass
    
    def search_files(self, query: str, limit: int = 20) -> List[FileInfo]:
        """Search indexed files by name or path."""
        query_lower = query.lower()
        matches = []
        
        for file_info in self.indexed_files:
            if (query_lower in file_info.name.lower() or
                query_lower in file_info.path.lower()):
                matches.append(file_info)
                if len(matches) >= limit:
                    break
        
        return matches
    
    def get_recent_files(self, limit: int = 20, extension: Optional[str] = None) -> List[FileInfo]:
        """Get recently modified files, optionally filtered by extension."""
        if extension:
            filtered = [f for f in self.indexed_files if f.extension == extension]
            return filtered[:limit]
        return self.indexed_files[:limit]
    
    def get_files_by_extension(self, extension: str, limit: int = 20) -> List[FileInfo]:
        """Get files with specific extension."""
        matches = [f for f in self.indexed_files if f.extension == extension]
        return matches[:limit]
    
    def find_exact_file(self, filename: str) -> Optional[FileInfo]:
        """Find a file by exact name match."""
        for file_info in self.indexed_files:
            if file_info.name.lower() == filename.lower():
                return file_info
        return None
    
    def get_context_summary(self) -> str:
        """Get a text summary of file system context for LLM."""
        if not self.indexed_files:
            return "No files indexed. Run index_files() first."
        
        recent_files = self.get_recent_files(5)
        
        # Count files by extension
        ext_counts = {}
        for file_info in self.indexed_files:
            ext = file_info.extension
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
        
        # Get top extensions
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
