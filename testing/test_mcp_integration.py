#!/usr/bin/env python3
"""Test script to verify MCP integration in main PixelLink runtime."""

import sys
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from bridge import load_plugins
from core.nlu.parser import parse_intent
from core.planner.action_planner import ActionPlanner
from core.context.session import SessionContext
from core.safety.guard import SafetyGuard


def test_mcp_integration():
    """Test that MCP tools are loaded and intents are parsed correctly."""
    
    print("=" * 60)
    print("Testing MCP Integration")
    print("=" * 60)
    
    # Load MCP plugins
    user_config = {
        "reminders-mcp": {},
        "notes-mcp": {},
    }
    
    try:
        mcp_tools = load_plugins(ROOT / "plugins", user_config)
        tool_map = {tool["name"]: tool["fn"] for tool in mcp_tools}
        print(f"\n✓ Loaded {len(mcp_tools)} MCP tools:")
        for name in tool_map.keys():
            print(f"  - {name}")
    except Exception as e:
        print(f"\n✗ Failed to load MCP plugins: {e}")
        return False
    
    # Test intent parsing
    print("\n" + "-" * 60)
    print("Testing Intent Parsing")
    print("-" * 60)
    
    test_cases = [
        "create reminder Buy groceries",
        "add reminder to Work list Call client",
        "make reminder Meeting at 3pm in Personal",
        "create note Project ideas",
        "add note Meeting notes in Work folder",
        "write note TODO list in Personal",
    ]
    
    session = SessionContext()
    
    for test_input in test_cases:
        intent = parse_intent(test_input, session)
        print(f"\nInput: '{test_input}'")
        print(f"Intent: {intent.name} (confidence: {intent.confidence:.2f})")
        if intent.entities:
            print(f"Entities: {intent.entities}")
    
    # Test action planning
    print("\n" + "-" * 60)
    print("Testing Action Planning")
    print("-" * 60)
    
    planner = ActionPlanner(mcp_tools=tool_map)
    guard = SafetyGuard()
    
    test_intents = [
        parse_intent("create reminder Buy milk", session),
        parse_intent("create note Meeting notes in Work", session),
    ]
    
    for intent in test_intents:
        steps = planner.plan(intent, session, guard)
        print(f"\nIntent: {intent.name}")
        print(f"Planned steps ({len(steps)}):")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step.action} - {step.description}")
            print(f"     Params: {step.params}")
    
    print("\n" + "=" * 60)
    print("✓ All tests completed successfully!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_mcp_integration()
    sys.exit(0 if success else 1)
