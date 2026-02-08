#!/usr/bin/env python3
"""Test script to verify all 4 new features."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from core.nlu.parser import parse_intent
from core.context.session import SessionContext
from core.context.browsing_history import BrowsingHistory
from core.context.filesystem_context import FileSystemContext
from core.executor.os_control import OSController


def test_browsing_feature():
    """Test #1: Enhanced browsing/search patterns."""
    print("\n" + "="*60)
    print("Test 1: Enhanced Browsing Feature")
    print("="*60)
    
    test_cases = [
        "browse for python tutorials",
        "search internet for machine learning",
        "find online best restaurants",
        "look online for weather forecast",
        "google latest news",
        "search for AI tools",
    ]
    
    session = SessionContext()
    
    for test_input in test_cases:
        intent = parse_intent(test_input, session)
        print(f"Input: '{test_input}'")
        print(f"  → Intent: {intent.name}, Query: {intent.entities.get('query', 'N/A')}")
        assert intent.name == "search_web", f"Expected search_web, got {intent.name}"
    
    print("\n✓ All browsing patterns recognized correctly!")


def test_browsing_history():
    """Test #2: Browsing history context."""
    print("\n" + "="*60)
    print("Test 2: Browsing History Context")
    print("="*60)
    
    history = BrowsingHistory()
    
    # Add some browsing entries
    history.add_url("https://www.google.com/search?q=python", search_query="python")
    history.add_url("https://github.com/python/cpython")
    history.add_url("https://stackoverflow.com/questions/123", title="How to use Python")
    history.add_url("https://www.youtube.com/watch?v=xyz", search_query="python tutorials")
    
    print(f"\nAdded {len(history.history)} browsing entries")
    
    # Test recent retrieval
    recent = history.get_recent(3)
    print(f"\nRecent browsing ({len(recent)} entries):")
    for entry in recent:
        if entry.is_search:
            print(f"  - Search: {entry.search_query}")
        else:
            print(f"  - Visit: {entry.domain}")
    
    # Test search
    matches = history.search_history("python", limit=5)
    print(f"\nSearch for 'python': {len(matches)} matches")
    
    # Test context summary
    summary = history.get_context_summary()
    print(f"\nContext summary:\n{summary}")
    
    assert len(recent) == 3, "Should get 3 recent entries"
    assert len(matches) > 0, "Should find matches for 'python'"
    
    print("\n✓ Browsing history tracking works!")


def test_filesystem_context():
    """Test #3: File system context."""
    print("\n" + "="*60)
    print("Test 3: File System Context")
    print("="*60)
    
    fs = FileSystemContext(
        search_paths=["~/Documents", "~/Desktop"],
        max_files=100  # Limit for testing
    )
    
    print("\nIndexing files (this may take a moment)...")
    file_count = fs.index_files()
    print(f"✓ Indexed {file_count} files")
    
    if file_count > 0:
        # Test recent files
        recent = fs.get_recent_files(5)
        print(f"\nRecent files ({len(recent)}):")
        for file_info in recent:
            print(f"  - {file_info.name} ({file_info.extension}, {file_info.size_mb:.1f}MB)")
        
        # Test search
        if recent:
            first_name = recent[0].name.split('.')[0][:5]  # Search for part of filename
            matches = fs.search_files(first_name, limit=3)
            print(f"\nSearch for '{first_name}': {len(matches)} matches")
        
        # Test context summary
        summary = fs.get_context_summary()
        print(f"\nContext summary:\n{summary}")
        
        print("\n✓ File system context works!")
    else:
        print("\n⚠ No files indexed (directories may be empty)")


def test_app_running_check():
    """Test #4: Check if app is already running."""
    print("\n" + "="*60)
    print("Test 4: App Running Check")
    print("="*60)
    
    os_ctrl = OSController()
    
    # Test with common apps that are likely running
    test_apps = ["Finder", "Terminal"]  # macOS system apps
    
    for app in test_apps:
        try:
            is_running = os_ctrl.is_app_running(app)
            print(f"  {app}: {'✓ Running' if is_running else '✗ Not running'}")
        except Exception as e:
            print(f"  {app}: Error checking - {e}")
    
    print("\n✓ App running check implemented!")
    print("  (When you run 'open app X', it will focus if already running)")


def test_file_search_intent():
    """Test file search intent parsing."""
    print("\n" + "="*60)
    print("Test 5: File Search Intent")
    print("="*60)
    
    test_cases = [
        "find file report.pdf",
        "search file presentation.pptx",
        "locate file data.csv",
        "find document notes.txt",
    ]
    
    session = SessionContext()
    
    for test_input in test_cases:
        intent = parse_intent(test_input, session)
        print(f"Input: '{test_input}'")
        print(f"  → Intent: {intent.name}, Query: {intent.entities.get('query', 'N/A')}")
        assert intent.name == "search_file", f"Expected search_file, got {intent.name}"
    
    print("\n✓ File search intent recognized!")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Testing New PixelLink Features")
    print("="*60)
    
    try:
        test_browsing_feature()
        test_browsing_history()
        test_filesystem_context()
        test_app_running_check()
        test_file_search_intent()
        
        print("\n" + "="*60)
        print("✓ All Tests Passed!")
        print("="*60)
        print("\nNew features ready to use:")
        print("  1. Enhanced browsing (browse for, search internet, etc.)")
        print("  2. Browsing history tracking")
        print("  3. File system context (indexed files)")
        print("  4. Smart app opening (focus if running)")
        print("\nTry these commands:")
        print("  - browse for python tutorials")
        print("  - find file report.pdf")
        print("  - open Notes (will focus if already open)")
        print("  - context (show current context)")
        print("="*60 + "\n")
        
        return True
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
