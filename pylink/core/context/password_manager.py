"""Password manager integration for PixelLink."""

import platform
import subprocess
import json
import re
from typing import Optional, Dict, List
from dataclasses import dataclass


@dataclass
class Credential:
    """Represents a stored credential."""
    username: str
    password: str
    service: str
    url: str = ""
    
    def __repr__(self) -> str:
        return f"Credential(username='{self.username}', service='{self.service}')"


class PasswordManager:
    """Interface for password manager operations."""
    
    # Common service name mappings
    SERVICE_ALIASES = {
        "github": ["github.com", "github", "GitHub"],
        "google": ["google.com", "gmail.com", "accounts.google.com", "Google"],
        "facebook": ["facebook.com", "fb.com", "Facebook"],
        "twitter": ["twitter.com", "x.com", "Twitter", "X"],
        "linkedin": ["linkedin.com", "LinkedIn"],
        "amazon": ["amazon.com", "Amazon"],
        "netflix": ["netflix.com", "Netflix"],
        "reddit": ["reddit.com", "Reddit"],
        "stackoverflow": ["stackoverflow.com", "Stack Overflow"],
        "slack": ["slack.com", "Slack"],
    }
    
    def __init__(self):
        self.system = platform.system().lower()
    
    def _normalize_service_name(self, service: str) -> List[str]:
        """Get all possible service name variations."""
        service_lower = service.lower().strip()
        
        # Check aliases
        for key, aliases in self.SERVICE_ALIASES.items():
            if service_lower in [a.lower() for a in aliases]:
                return aliases
        
        # If not in aliases, return common variations
        variations = [service, service.lower(), service.capitalize()]
        
        # Add .com version if not present
        if not service.endswith('.com'):
            variations.extend([f"{service}.com", f"{service_lower}.com"])
        
        return list(set(variations))  # Remove duplicates
    
    def get_credential(self, service: str) -> Optional[Credential]:
        """
        Retrieve credential for a service.
        
        Args:
            service: Service name or URL (e.g., "github", "github.com")
            
        Returns:
            Credential object if found, None otherwise
        """
        service_variations = self._normalize_service_name(service)
        
        if self.system == "darwin":
            return self._get_credential_macos_keychain(service_variations)
        elif self.system == "windows":
            return self._get_credential_windows(service_variations)
        else:
            return self._get_credential_linux(service_variations)
    
    def _get_credential_macos_keychain(self, service_variations: List[str]) -> Optional[Credential]:
        """Retrieve credential from macOS Keychain."""
        for service_name in service_variations:
            try:
                # Try to find internet password
                cmd = [
                    "security", "find-internet-password",
                    "-s", service_name,
                    "-g"  # Show password
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    # Parse output
                    username = self._extract_keychain_field(result.stdout, "acct")
                    # Password is in stderr for security reasons
                    password = self._extract_keychain_password(result.stderr)
                    
                    if username and password:
                        return Credential(
                            username=username,
                            password=password,
                            service=service_name,
                            url=f"https://{service_name}" if not service_name.startswith("http") else service_name
                        )
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
        
        # Try generic password if internet password not found
        for service_name in service_variations:
            try:
                cmd = [
                    "security", "find-generic-password",
                    "-s", service_name,
                    "-g"
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    username = self._extract_keychain_field(result.stdout, "acct")
                    password = self._extract_keychain_password(result.stderr)
                    
                    if username and password:
                        return Credential(
                            username=username,
                            password=password,
                            service=service_name,
                            url=f"https://{service_name}" if not service_name.startswith("http") else service_name
                        )
            except Exception:
                continue
        
        return None
    
    def _get_credential_windows(self, service_variations: List[str]) -> Optional[Credential]:
        """Retrieve credential from Windows Credential Manager."""
        try:
            # Try using cmdkey to list credentials
            for service_name in service_variations:
                cmd = ["cmdkey", "/list"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0 and service_name in result.stdout:
                    # Windows Credential Manager doesn't easily expose passwords via CLI
                    # Would need PowerShell or Windows API
                    # This is a simplified placeholder
                    return None
        except Exception:
            pass
        
        return None
    
    def _get_credential_linux(self, service_variations: List[str]) -> Optional[Credential]:
        """Retrieve credential from Linux password managers."""
        # Try Secret Service API (GNOME Keyring, KWallet)
        try:
            import secretstorage
            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            
            for service_name in service_variations:
                items = collection.search_items({"service": service_name})
                for item in items:
                    return Credential(
                        username=item.get_attributes().get("username", ""),
                        password=item.get_secret().decode('utf-8'),
                        service=service_name,
                        url=item.get_attributes().get("url", "")
                    )
        except ImportError:
            # secretstorage not installed
            pass
        except Exception:
            pass
        
        return None
    
    def _extract_keychain_field(self, output: str, field: str) -> str:
        """Extract a field from macOS Keychain output."""
        # Format: "acct"<blob>="username"
        pattern = rf'"{field}"<blob>="([^"]+)"'
        match = re.search(pattern, output)
        if match:
            return match.group(1)
        
        # Alternative format: acct: "username"
        pattern = rf'{field}\s*:\s*"([^"]+)"'
        match = re.search(pattern, output)
        if match:
            return match.group(1)
        
        return ""
    
    def _extract_keychain_password(self, stderr: str) -> str:
        """Extract password from macOS Keychain stderr output."""
        # Format: password: "actual_password"
        pattern = r'password:\s*"([^"]*)"'
        match = re.search(pattern, stderr)
        if match:
            return match.group(1)
        
        # Alternative format without quotes
        pattern = r'password:\s*(\S+)'
        match = re.search(pattern, stderr)
        if match:
            return match.group(1)
        
        return ""
    
    def list_services(self, limit: int = 20) -> List[str]:
        """List available services in password manager."""
        services = []
        
        if self.system == "darwin":
            try:
                # List internet passwords
                cmd = ["security", "dump-keychain"]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    # Parse service names from output
                    for line in result.stdout.split('\n'):
                        if 'srvr' in line or 'svce' in line:
                            match = re.search(r'"([^"]+)"', line)
                            if match:
                                services.append(match.group(1))
            except Exception:
                pass
        
        return list(set(services))[:limit]
    
    def search_credentials(self, query: str) -> List[Credential]:
        """Search for credentials matching query."""
        results = []
        
        # Get service variations
        service_variations = self._normalize_service_name(query)
        
        for service in service_variations:
            cred = self.get_credential(service)
            if cred:
                results.append(cred)
        
        return results


# Singleton instance
_password_manager = None

def get_password_manager() -> PasswordManager:
    """Get the password manager singleton."""
    global _password_manager
    if _password_manager is None:
        _password_manager = PasswordManager()
    return _password_manager
