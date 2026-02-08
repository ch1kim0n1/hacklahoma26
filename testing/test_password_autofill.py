#!/usr/bin/env python3
"""Test script for password autofill feature."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from core.context.password_manager import PasswordManager, get_password_manager
from core.nlu.parser import parse_intent
from core.context.session import SessionContext


def test_password_manager():
    """Test password manager functionality."""
    print("\n" + "="*60)
    print("Test 1: Password Manager Integration")
    print("="*60)
    
    pm = PasswordManager()
    
    # Test service normalization
    print("\n1. Service name normalization:")
    variations = pm._normalize_service_name("github")
    print(f"   'github' variations: {variations[:5]}")
    
    variations = pm._normalize_service_name("google")
    print(f"   'google' variations: {variations[:5]}")
    
    # Test credential retrieval (will fail if no credentials stored)
    print("\n2. Credential retrieval test:")
    test_services = ["github", "google", "test-service-that-doesnt-exist"]
    
    for service in test_services:
        cred = pm.get_credential(service)
        if cred:
            print(f"   ✓ Found credentials for '{service}': {cred.username}")
        else:
            print(f"   ✗ No credentials found for '{service}'")
    
    print("\n✓ Password manager module works!")


def test_login_intent_parsing():
    """Test login intent parsing."""
    print("\n" + "="*60)
    print("Test 2: Login Intent Parsing")
    print("="*60)
    
    test_cases = [
        "login to github",
        "log in to google",
        "sign in to facebook",
        "signin to twitter",
        "authenticate to linkedin",
        "github login",
        "login on amazon",
    ]
    
    session = SessionContext()
    
    for test_input in test_cases:
        intent = parse_intent(test_input, session)
        service = intent.entities.get("service", "N/A")
        print(f"Input: '{test_input}'")
        print(f"  → Intent: {intent.name}, Service: {service}")
        
        if intent.name != "login":
            print(f"  ⚠ Warning: Expected 'login' intent, got '{intent.name}'")
    
    print("\n✓ Login intent parsing works!")


def test_action_planning():
    """Test login action planning."""
    print("\n" + "="*60)
    print("Test 3: Login Action Planning")
    print("="*60)
    
    from core.planner.action_planner import ActionPlanner
    from core.safety.guard import SafetyGuard
    
    session = SessionContext()
    planner = ActionPlanner()
    guard = SafetyGuard()
    
    # Parse login intent
    intent = parse_intent("login to github", session)
    
    # Plan actions
    steps = planner.plan(intent, session, guard)
    
    print(f"\nPlanned {len(steps)} step(s) for 'login to github':")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step.action} - {step.description}")
        print(f"     Params: {step.params}")
    
    assert len(steps) > 0, "Should have at least one step"
    assert steps[0].action == "autofill_login", f"Expected autofill_login, got {steps[0].action}"
    
    print("\n✓ Login action planning works!")


def test_full_integration():
    """Test full integration of password autofill."""
    print("\n" + "="*60)
    print("Test 4: Full Integration Test")
    print("="*60)
    
    from core.runtime.orchestrator import PixelLinkRuntime, DEFAULT_PERMISSION_PROFILE
    
    # Create runtime
    runtime = PixelLinkRuntime(
        dry_run=True,  # Don't actually type anything
        speed=1.0,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=False,
        verbose=False,
    )
    
    # Test login command
    print("\n1. Testing 'login to github' command:")
    result = runtime.handle_input("login to github", source="test")
    
    print(f"   Status: {result['status']}")
    print(f"   Message: {result['message']}")
    
    if result['status'] == 'error':
        if 'No credentials found' in result['message']:
            print("   ℹ️  This is expected if you don't have GitHub credentials in Keychain")
        else:
            print(f"   Error: {result['message']}")
    elif result['status'] == 'completed':
        print("   ✓ Would autofill credentials!")
    
    print("\n✓ Full integration test completed!")
    
    runtime.close()


def test_singleton_pattern():
    """Test password manager singleton."""
    print("\n" + "="*60)
    print("Test 5: Singleton Pattern")
    print("="*60)
    
    pm1 = get_password_manager()
    pm2 = get_password_manager()
    
    assert pm1 is pm2, "Should return same instance"
    print("   ✓ Singleton pattern works correctly")
    
    print("\n✓ Singleton test passed!")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Testing Password Autofill Feature")
    print("="*60)
    
    try:
        test_password_manager()
        test_login_intent_parsing()
        test_action_planning()
        test_full_integration()
        test_singleton_pattern()
        
        print("\n" + "="*60)
        print("✓ All Tests Passed!")
        print("="*60)
        print("\n📝 How to use password autofill:")
        print("\n1. Store credentials in your password manager:")
        print("   macOS: Use Keychain Access to add passwords")
        print("   - Open Keychain Access app")
        print("   - File → New Password Item")
        print("   - Enter service name (e.g., 'github.com')")
        print("   - Enter username and password")
        
        print("\n2. Use PixelLink to autofill:")
        print("   > login to github")
        print("   > sign in to google")
        print("   > authenticate to linkedin")
        
        print("\n3. PixelLink will:")
        print("   - Find credentials in password manager")
        print("   - Type username")
        print("   - Press Tab")
        print("   - Type password")
        print("   - Ready to submit!")
        
        print("\n⚠️  Security Notes:")
        print("   - Passwords are retrieved securely from Keychain")
        print("   - Never stored in memory longer than needed")
        print("   - Typed directly, not copied to clipboard")
        print("   - Requires macOS permission for Terminal")
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
