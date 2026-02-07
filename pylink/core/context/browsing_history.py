"""Browsing history tracking for PixelLink."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from urllib.parse import urlparse


@dataclass
class BrowsingEntry:
    """Single browsing history entry."""
    url: str
    timestamp: datetime
    title: str = ""
    search_query: str = ""  # If it was a search
    
    @property
    def domain(self) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(self.url)
            return parsed.netloc
        except Exception:
            return ""
    
    @property
    def is_search(self) -> bool:
        """Check if this was a search query."""
        return bool(self.search_query)


class BrowsingHistory:
    """Manages browsing history for context."""
    
    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self.history: List[BrowsingEntry] = []
    
    def add_url(self, url: str, title: str = "", search_query: str = "") -> None:
        """Add a URL to browsing history."""
        entry = BrowsingEntry(
            url=url,
            timestamp=datetime.now(),
            title=title,
            search_query=search_query,
        )
        self.history.append(entry)
        
        # Keep history size manageable
        if len(self.history) > self.max_entries:
            self.history = self.history[-self.max_entries:]
    
    def get_recent(self, count: int = 10) -> List[BrowsingEntry]:
        """Get most recent browsing entries."""
        return list(reversed(self.history[-count:]))
    
    def search_history(self, query: str, limit: int = 10) -> List[BrowsingEntry]:
        """Search browsing history for matching entries."""
        query_lower = query.lower()
        matches = []
        
        for entry in reversed(self.history):
            # Search in URL, title, and search query
            if (query_lower in entry.url.lower() or
                query_lower in entry.title.lower() or
                query_lower in entry.search_query.lower()):
                matches.append(entry)
                if len(matches) >= limit:
                    break
        
        return matches
    
    def get_domains(self, limit: int = 20) -> List[str]:
        """Get most frequently visited domains."""
        domain_counts = {}
        for entry in self.history:
            domain = entry.domain
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        # Sort by frequency
        sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
        return [domain for domain, _ in sorted_domains[:limit]]
    
    def get_search_queries(self, limit: int = 20) -> List[str]:
        """Get recent search queries."""
        queries = []
        for entry in reversed(self.history):
            if entry.is_search and entry.search_query not in queries:
                queries.append(entry.search_query)
                if len(queries) >= limit:
                    break
        return queries
    
    def clear(self) -> None:
        """Clear all browsing history."""
        self.history.clear()
    
    def get_context_summary(self) -> str:
        """Get a text summary of browsing context for LLM."""
        if not self.history:
            return "No browsing history available."
        
        recent = self.get_recent(5)
        domains = self.get_domains(5)
        queries = self.get_search_queries(5)
        
        summary_parts = []
        
        if recent:
            summary_parts.append("Recent browsing:")
            for entry in recent:
                time_str = entry.timestamp.strftime("%H:%M")
                if entry.is_search:
                    summary_parts.append(f"  [{time_str}] Searched: {entry.search_query}")
                else:
                    summary_parts.append(f"  [{time_str}] {entry.url}")
        
        if domains:
            summary_parts.append(f"\nFrequent sites: {', '.join(domains)}")
        
        if queries:
            summary_parts.append(f"\nRecent searches: {', '.join(queries[:3])}")
        
        return "\n".join(summary_parts)
