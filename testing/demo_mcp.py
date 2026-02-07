#!/usr/bin/env python3
"""
Quick demo script showing MCP features in action.
This demonstrates the integration without full runtime overhead.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from bridge import load_plugins


async def demo_mcp_features():
    """Demonstrate MCP tools for reminders and notes."""
    
    print("\n" + "="*60)
    print("PixelLink MCP Features Demo")
    print("="*60)
    
    # Load MCP plugins
    user_config = {
        "reminders-mcp": {},
        "notes-mcp": {},
    }
    
    print("\n📦 Loading MCP plugins...")
    mcp_tools = load_plugins(ROOT / "plugins", user_config)
    tool_map = {tool["name"]: tool["fn"] for tool in mcp_tools}
    print(f"✓ Loaded {len(mcp_tools)} MCP tools")
    
    # Demo 1: List reminder lists
    print("\n" + "-"*60)
    print("1️⃣  Listing Reminder Lists")
    print("-"*60)
    try:
        lists = await tool_map["reminders_list_lists"]()
        print(f"Found {len(lists)} reminder lists:")
        for lst in lists:
            print(f"  • {lst}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Demo 2: List note folders
    print("\n" + "-"*60)
    print("2️⃣  Listing Note Folders")
    print("-"*60)
    try:
        folders = await tool_map["notes_list_folders"]()
        print(f"Found {len(folders)} note folders:")
        for folder in folders:
            print(f"  • {folder}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Demo 3: Create a test reminder
    print("\n" + "-"*60)
    print("3️⃣  Creating Test Reminder")
    print("-"*60)
    try:
        result = await tool_map["reminders_create_reminder"](
            list_name="PixelLink Demo",
            name="Test from PixelLink MCP",
            body="This reminder was created by the PixelLink demo script",
            due_date_iso=None,
        )
        print(f"✓ Created reminder: '{result['name']}' in list '{result['list']}'")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Demo 4: Create a test note
    print("\n" + "-"*60)
    print("4️⃣  Creating Test Note")
    print("-"*60)
    try:
        # Get first folder or use Notes
        folders = await tool_map["notes_list_folders"]()
        folder = folders[0] if folders else "Notes"
        
        result = await tool_map["notes_create_note"](
            folder_name=folder,
            title="PixelLink MCP Demo",
            body="This note was created by the PixelLink demo script to showcase MCP integration.",
        )
        print(f"✓ Created note: '{result['title']}' in folder '{result['folder']}'")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*60)
    print("✓ Demo completed!")
    print("\nTip: Open Reminders and Notes apps to see the created items.")
    print("="*60 + "\n")


if __name__ == "__main__":
    print("\n⚠️  This demo will create a test reminder and note on your system.")
    response = input("Continue? (y/N): ").strip().lower()
    
    if response == 'y':
        asyncio.run(demo_mcp_features())
    else:
        print("Demo cancelled.")
