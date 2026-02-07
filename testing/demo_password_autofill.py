#!/usr/bin/env python3
"""
Quick demo of password autofill feature.
Shows how to add credentials and use autofill.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))


def check_keychain_setup():
    """Check if we can access keychain and show stored credentials."""
    print("\n" + "="*60)
    print("Checking Password Manager Setup")
    print("="*60)
    
    import platform
    if platform.system().lower() != "darwin":
        print("\n⚠️  This demo is optimized for macOS.")
        print("Password autofill works on other platforms too!")
        return
    
    print("\n1. Checking if we can access Keychain...")
    
    try:
        # Try to list some keychain items
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "pixelink-demo"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        if result.returncode == 0:
            print("   ✓ Found demo credential in Keychain")
        else:
            print("   ℹ️  No demo credential found (this is expected)")
            
    except Exception as e:
        print(f"   ⚠️  Could not access Keychain: {e}")


def demo_add_credential():
    """Show how to add a credential."""
    print("\n" + "="*60)
    print("Demo: Adding Credentials to Keychain")
    print("="*60)
    
    print("\n📝 To add credentials to macOS Keychain:\n")
    print("Method 1: Using Keychain Access App")
    print("-" * 40)
    print("1. Open 'Keychain Access' app")
    print("2. File → New Password Item")
    print("3. Fill in:")
    print("   - Keychain Item Name: github.com")
    print("   - Account Name: your-username")
    print("   - Password: your-password")
    print("4. Click 'Add'")
    
    print("\nMethod 2: Using Terminal")
    print("-" * 40)
    print("$ security add-generic-password \\")
    print("    -a 'demo-user' \\")
    print("    -s 'pixelink-demo' \\")
    print("    -w 'demo-password'")
    
    print("\nMethod 3: Let's add a demo credential now!")
    print("-" * 40)
    
    import platform
    if platform.system().lower() != "darwin":
        print("⚠️  Keychain is macOS-only. Use your OS password manager.")
        return
    
    response = input("\nAdd demo credential 'pixelink-demo'? (y/N): ").strip().lower()
    
    if response == 'y':
        try:
            cmd = [
                "security", "add-generic-password",
                "-a", "demo-user@email.com",
                "-s", "pixelink-demo",
                "-w", "demo-pass-123",
                "-U"  # Update if exists
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                print("✓ Demo credential added successfully!")
                print("\nYou can now use:")
                print("  > login to pixelink-demo")
            else:
                print(f"⚠️  Could not add credential: {result.stderr}")
                
        except Exception as e:
            print(f"⚠️  Error: {e}")
    else:
        print("Skipped. You can add it manually later.")


def demo_password_manager():
    """Demo password manager functionality."""
    print("\n" + "="*60)
    print("Demo: Password Manager Functionality")
    print("="*60)
    
    from core.context.password_manager import get_password_manager
    
    pm = get_password_manager()
    
    print("\n1. Service Name Normalization:")
    print("-" * 40)
    services = ["github", "google", "pixelink-demo"]
    for service in services:
        variations = pm._normalize_service_name(service)
        print(f"   '{service}' → {variations[:3]}")
    
    print("\n2. Retrieving Credentials:")
    print("-" * 40)
    
    test_services = ["pixelink-demo", "github", "google"]
    
    for service in test_services:
        cred = pm.get_credential(service)
        if cred:
            print(f"   ✓ {service}: {cred.username}")
        else:
            print(f"   ✗ {service}: No credentials found")
    
    print("\n3. Testing Intent Recognition:")
    print("-" * 40)
    
    from core.nlu.parser import parse_intent
    from core.context.session import SessionContext
    
    session = SessionContext()
    
    test_inputs = [
        "login to github",
        "sign in to google",
        "pixelink-demo login"
    ]
    
    for input_text in test_inputs:
        intent = parse_intent(input_text, session)
        service = intent.entities.get("service", "N/A")
        print(f"   '{input_text}' → Intent: {intent.name}, Service: {service}")


def demo_full_workflow():
    """Demo full autofill workflow."""
    print("\n" + "="*60)
    print("Demo: Full Autofill Workflow")
    print("="*60)
    
    print("\n📋 Complete workflow example:")
    print("-" * 40)
    print("1. Store credential in Keychain")
    print("   ✓ Done (demo-user@email.com for pixelink-demo)")
    print()
    print("2. Open login page")
    print("   > open Safari")
    print("   > open url github.com/login")
    print()
    print("3. Click on username field")
    print("   (Make sure cursor is in the username field)")
    print()
    print("4. Run autofill")
    print("   > login to pixelink-demo")
    print()
    print("5. What happens:")
    print("   - Retrieves credentials from Keychain")
    print("   - Types username: demo-user@email.com")
    print("   - Presses Tab key")
    print("   - Types password: •••••••••••")
    print()
    print("6. Submit login")
    print("   > press key return")
    print()
    print("✓ Logged in securely!")


def show_usage_examples():
    """Show usage examples."""
    print("\n" + "="*60)
    print("Usage Examples")
    print("="*60)
    
    print("\n🎯 Basic Usage:")
    print("-" * 40)
    print("$ python3 main.py")
    print()
    print("> login to github")
    print("✓ Autofilled credentials for github (username@email.com)")
    print()
    print("> sign in to google")
    print("✓ Autofilled credentials for google (you@gmail.com)")
    print()
    print("> authenticate to linkedin")
    print("✓ Autofilled credentials for linkedin (professional@email.com)")
    
    print("\n🔗 Combined Workflows:")
    print("-" * 40)
    print("> open Safari")
    print("> open url github.com")
    print("> login to github")
    print("> press return")
    print("✓ Complete login automation!")
    
    print("\n🔐 Security Features:")
    print("-" * 40)
    print("✓ Passwords stored in OS-level encrypted storage")
    print("✓ No clipboard usage (direct typing)")
    print("✓ Permission-based Keychain access")
    print("✓ Passwords never logged or stored")
    print("✓ Short-lived in memory")


def main():
    """Run the demo."""
    print("\n" + "="*60)
    print("PixelLink Password Autofill Demo")
    print("="*60)
    
    print("\n🎉 New Feature: Password Autofill!")
    print("\nSecurely retrieve and autofill credentials from your")
    print("password manager with simple natural language commands.")
    
    try:
        check_keychain_setup()
        demo_add_credential()
        demo_password_manager()
        demo_full_workflow()
        show_usage_examples()
        
        print("\n" + "="*60)
        print("✓ Demo Complete!")
        print("="*60)
        
        print("\n📚 For more information:")
        print("   - Read: PASSWORD_AUTOFILL_GUIDE.md")
        print("   - Test: python3 test_password_autofill.py")
        print("   - Try: python3 main.py")
        print()
        print("🚀 Start using password autofill now:")
        print("   1. Add credentials to your password manager")
        print("   2. Run PixelLink")
        print("   3. Say 'login to <service>'")
        print("   4. Enjoy automated, secure login!")
        print("="*60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted.")
    except Exception as e:
        print(f"\n✗ Demo error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
