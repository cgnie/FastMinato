"""
Platform adapter for proxy-cli-tool
Handles cross-platform differences in setting/unsetting system proxy
"""

import os
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from proxy_cli.logger import get_logger


class PlatformAdapter:
    """
    Cross-platform adapter for setting/unsetting system proxy
    """

    # Supported platforms
    PLATFORM_WINDOWS = "Windows"
    PLATFORM_LINUX = "Linux"
    PLATFORM_DARWIN = "Darwin"  # macOS

    # Shell types
    SHELL_BASH = "bash"
    SHELL_ZSH = "zsh"
    SHELL_FISH = "fish"
    SHELL_POWERSHELL = "powershell"
    SHELL_CMD = "cmd"

    # Proxy environment variables
    PROXY_VARS = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]

    def __init__(self):
        """Initialize platform adapter and detect current platform"""
        self.logger = get_logger("proxy_cli.platform")
        self.system = platform.system()
        self._detected_shell = self._detect_shell()

    @property
    def is_windows(self) -> bool:
        """Check if running on Windows"""
        return self.system == self.PLATFORM_WINDOWS

    @property
    def is_linux(self) -> bool:
        """Check if running on Linux"""
        return self.system == self.PLATFORM_LINUX

    @property
    def is_macos(self) -> bool:
        """Check if running on macOS"""
        return self.system == self.PLATFORM_DARWIN

    @property
    def is_unix(self) -> bool:
        """Check if running on Unix-like system (Linux or macOS)"""
        return self.is_linux or self.is_macos

    def _detect_shell(self) -> str:
        """
        Detect current shell

        Returns:
            Detected shell type
        """
        if self.is_windows:
            # Check if PowerShell or CMD
            if "PSModulePath" in os.environ:
                return self.SHELL_POWERSHELL
            return self.SHELL_CMD

        # Unix-like systems
        shell = os.environ.get("SHELL", "")
        if "zsh" in shell:
            return self.SHELL_ZSH
        elif "fish" in shell:
            return self.SHELL_FISH
        else:
            return self.SHELL_BASH

    @property
    def current_shell(self) -> str:
        """Get detected current shell"""
        return self._detected_shell

    def get_shell_export_command(self, proxy_url: str, shell: Optional[str] = None) -> str:
        """
        Get shell export command for setting proxy

        Args:
            proxy_url: Proxy URL (e.g., "http://127.0.0.1:8080" or "socks5://127.0.0.1:1080")
            shell: Shell type (defaults to auto-detected)

        Returns:
            String of export commands

        Raises:
            ValueError: If unsupported platform or shell type
        """
        shell = shell or self._detected_shell

        if shell == self.SHELL_BASH or shell == self.SHELL_ZSH:
            commands = [f"export {var}={proxy_url}" for var in self.PROXY_VARS]
            return " && ".join(commands)

        elif shell == self.SHELL_FISH:
            commands = [f"set -gx {var} {proxy_url}" for var in self.PROXY_VARS]
            return "; ".join(commands)

        elif shell == self.SHELL_POWERSHELL:
            commands = [f"$env:{var} = '{proxy_url}'" for var in self.PROXY_VARS]
            return "; ".join(commands)

        elif shell == self.SHELL_CMD:
            commands = [f"set {var}={proxy_url}" for var in self.PROXY_VARS]
            return " & ".join(commands)

        else:
            raise ValueError(f"Unsupported shell type: {shell}")

    def get_shell_unset_command(self, shell: Optional[str] = None) -> str:
        """
        Get shell unset command for removing proxy

        Args:
            shell: Shell type (defaults to auto-detected)

        Returns:
            String of unset commands

        Raises:
            ValueError: If unsupported shell type
        """
        shell = shell or self._detected_shell

        if shell == self.SHELL_BASH or shell == self.SHELL_ZSH:
            commands = [f"unset {var}" for var in self.PROXY_VARS]
            # Also remove NO_PROXY
            commands.extend(["unset NO_PROXY", "unset no_proxy"])
            return " && ".join(commands)

        elif shell == self.SHELL_FISH:
            commands = [f"set -e {var}" for var in self.PROXY_VARS]
            commands.extend(["set -e NO_PROXY", "set -e no_proxy"])
            return "; ".join(commands)

        elif shell == self.SHELL_POWERSHELL:
            vars_to_remove = self.PROXY_VARS + ["NO_PROXY", "no_proxy"]
            commands = [f"Remove-Item Env:{var}" for var in vars_to_remove]
            return "; ".join(commands)

        elif shell == self.SHELL_CMD:
            vars_to_remove = self.PROXY_VARS + ["NO_PROXY", "no_proxy"]
            commands = [f"set {var}=" for var in vars_to_remove]
            return " & ".join(commands)

        else:
            raise ValueError(f"Unsupported shell type: {shell}")

    def set_system_proxy(
        self,
        proxy_url: str,
        persist: bool = False,
        shell_config: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Set system proxy for current platform

        Args:
            proxy_url: Proxy URL
            persist: Whether to persist to shell config file (Unix only)
            shell_config: Path to shell config file (auto-detected if None)

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self.is_windows:
                return self._set_windows_proxy(proxy_url, persist)
            elif self.is_unix:
                return self._set_unix_proxy(proxy_url, persist, shell_config)
            else:
                return False, f"Unsupported platform: {self.system}"
        except Exception as e:
            self.logger.error(f"Failed to set system proxy: {e}")
            return False, f"Error: {e}"

    def unset_system_proxy(
        self,
        persist: bool = False,
        shell_config: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Unset system proxy for current platform

        Args:
            persist: Whether to remove from shell config file (Unix only)
            shell_config: Path to shell config file (auto-detected if None)

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self.is_windows:
                return self._unset_windows_proxy(persist)
            elif self.is_unix:
                return self._unset_unix_proxy(persist, shell_config)
            else:
                return False, f"Unsupported platform: {self.system}"
        except Exception as e:
            self.logger.error(f"Failed to unset system proxy: {e}")
            return False, f"Error: {e}"

    def _set_windows_proxy(self, proxy_url: str, persist: bool) -> Tuple[bool, str]:
        """
        Set proxy on Windows

        Args:
            proxy_url: Proxy URL
            persist: Whether to persist using setx command

        Returns:
            Tuple of (success: bool, message: str)
        """
        command = self.get_shell_export_command(proxy_url, shell=self.SHELL_POWERSHELL)

        if persist:
            # For persistence, use setx command
            # Note: setx only works for simple variables, might not handle all cases
            return (
                True,
                f"# Run in PowerShell as Administrator:\n"
                f"[Environment]::SetEnvironmentVariable('HTTP_PROXY', '{proxy_url}', 'User')\n"
                f"[Environment]::SetEnvironmentVariable('HTTPS_PROXY', '{proxy_url}', 'User')\n"
                f"[Environment]::SetEnvironmentVariable('ALL_PROXY', '{proxy_url}', 'User')\n"
                f"# Current session:\n"
                f"{command}",
            )
        else:
            return True, f"# Run in PowerShell:\n{command}"

    def _unset_windows_proxy(self, persist: bool) -> Tuple[bool, str]:
        """
        Unset proxy on Windows

        Args:
            persist: Whether to remove persistent environment variables

        Returns:
            Tuple of (success: bool, message: str)
        """
        command = self.get_shell_unset_command(shell=self.SHELL_POWERSHELL)

        if persist:
            return (
                True,
                f"# Run in PowerShell as Administrator:\n"
                f"[Environment]::SetEnvironmentVariable('HTTP_PROXY', $null, 'User')\n"
                f"[Environment]::SetEnvironmentVariable('HTTPS_PROXY', $null, 'User')\n"
                f"[Environment]::SetEnvironmentVariable('ALL_PROXY', $null, 'User')\n"
                f"# Current session:\n"
                f"{command}",
            )
        else:
            return True, f"# Run in PowerShell:\n{command}"

    def _set_unix_proxy(
        self, proxy_url: str, persist: bool, shell_config: Optional[str]
    ) -> Tuple[bool, str]:
        """
        Set proxy on Unix-like systems (Linux/macOS)

        Args:
            proxy_url: Proxy URL
            persist: Whether to write to shell config file
            shell_config: Path to shell config file

        Returns:
            Tuple of (success: bool, message: str)
        """
        command = self.get_shell_export_command(proxy_url)

        if persist:
            config_file = self._get_shell_config_file(shell_config)
            if config_file is None:
                return False, "Could not determine shell config file"

            export_line = f"\n# Proxy configuration\n{command}\n"

            try:
                # Ensure config file exists
                config_file = Path(config_file).expanduser()

                # Create file if it doesn't exist
                if not config_file.exists():
                    config_file.parent.mkdir(parents=True, exist_ok=True)
                    config_file.touch()

                # Check if proxy config already exists
                content = config_file.read_text()

                # Remove old proxy config
                lines = content.split("\n")
                filtered_lines = []
                skip = False
                for line in lines:
                    if "# Proxy configuration" in line:
                        skip = True
                    elif skip and line.startswith("export ") and "_PROXY" in line:
                        continue
                    elif skip and line.strip() == "":
                        continue
                    else:
                        skip = False
                        filtered_lines.append(line)

                # Add new proxy config
                filtered_lines.append(export_line.strip())
                new_content = "\n".join(filtered_lines)

                # Write back
                config_file.write_text(new_content)

                return (
                    True,
                    f"# Proxy configuration written to {config_file}\n"
                    f"# Run: source {config_file}\n"
                    f"# Or restart your terminal\n"
                    f"# For current session:\n"
                    f"{command}",
                )
            except Exception as e:
                return False, f"Failed to write to {config_file}: {e}"
        else:
            return True, f"# Run: eval $(proxy on)\n# Or:\n{command}"

    def _unset_unix_proxy(
        self, persist: bool, shell_config: Optional[str]
    ) -> Tuple[bool, str]:
        """
        Unset proxy on Unix-like systems (Linux/macOS)

        Args:
            persist: Whether to remove from shell config file
            shell_config: Path to shell config file

        Returns:
            Tuple of (success: bool, message: str)
        """
        command = self.get_shell_unset_command()

        if persist:
            config_file = self._get_shell_config_file(shell_config)
            if config_file is None:
                return False, "Could not determine shell config file"

            try:
                config_file = Path(config_file).expanduser()

                if not config_file.exists():
                    return True, f"# No config file at {config_file}\n{command}"

                # Remove proxy config from file
                content = config_file.read_text()
                lines = content.split("\n")
                filtered_lines = []
                skip = False
                for line in lines:
                    if "# Proxy configuration" in line:
                        skip = True
                    elif skip and (line.startswith("export ") or line.startswith("unset ")) and "_PROXY" in line.upper():
                        continue
                    elif skip and line.strip() == "":
                        continue
                    else:
                        skip = False
                        filtered_lines.append(line)

                # Remove trailing empty lines
                while filtered_lines and filtered_lines[-1].strip() == "":
                    filtered_lines.pop()

                new_content = "\n".join(filtered_lines)

                # Write back
                config_file.write_text(new_content)

                return (
                    True,
                    f"# Proxy configuration removed from {config_file}\n"
                    f"# Restart your terminal or run: source {config_file}\n"
                    f"# For current session:\n"
                    f"{command}",
                )
            except Exception as e:
                return False, f"Failed to update {config_file}: {e}"
        else:
            return True, f"# Run: eval $(proxy off)\n# Or:\n{command}"

    def _get_shell_config_file(self, shell_config: Optional[str]) -> Optional[str]:
        """
        Get shell config file path

        Args:
            shell_config: Explicit config file path

        Returns:
            Path to shell config file or None
        """
        if shell_config:
            return shell_config

        # Auto-detect based on shell
        shell = self._detected_shell

        if shell == self.SHELL_ZSH:
            # Check for .zshrc
            zshrc = Path.home() / ".zshrc"
            if zshrc.exists():
                return str(zshrc)

            # Check for .zprofile
            zprofile = Path.home() / ".zprofile"
            if zprofile.exists():
                return str(zprofile)

            # Default to .zshrc
            return str(zshrc)

        elif shell == self.SHELL_BASH:
            # Check for .bashrc
            bashrc = Path.home() / ".bashrc"
            if bashrc.exists():
                return str(bashrc)

            # Check for .bash_profile (macOS)
            bash_profile = Path.home() / ".bash_profile"
            if bash_profile.exists():
                return str(bash_profile)

            # Default to .bashrc on Linux, .bash_profile on macOS
            if self.is_macos:
                return str(bash_profile)
            return str(bashrc)

        elif shell == self.SHELL_FISH:
            # Fish config directory
            fish_config = Path.home() / ".config" / "fish" / "config.fish"
            return str(fish_config)

        return None

    def get_eval_command(self, proxy_url: str) -> str:
        """
        Get eval command for setting proxy in current shell

        Usage: eval $(proxy on)

        Args:
            proxy_url: Proxy URL

        Returns:
            Eval command string
        """
        if self.is_unix:
            # For Unix, output shell commands
            return self.get_shell_export_command(proxy_url)
        elif self.is_windows:
            # For Windows, output PowerShell command
            return self.get_shell_export_command(proxy_url, shell=self.SHELL_POWERSHELL)
        else:
            raise ValueError(f"Unsupported platform: {self.system}")

    def get_platform_info(self) -> Dict[str, str]:
        """
        Get platform information

        Returns:
            Dictionary with platform details
        """
        return {
            "system": self.system,
            "is_windows": str(self.is_windows),
            "is_linux": str(self.is_linux),
            "is_macos": str(self.is_macos),
            "is_unix": str(self.is_unix),
            "shell": self._detected_shell,
        }
