"""
Environment variable injector for proxy-cli-tool
"""

import os
from typing import Dict, List, Optional


class EnvInjector:
    """
    Injects proxy environment variables into environment dictionaries
    """

    # Standard proxy environment variables
    PROXY_VARS = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "FTP_PROXY",
        "ftp_proxy",
        "RSYNC_PROXY",
        "rsync_proxy",
    ]

    # Variables that should be preserved (not overwritten)
    PRESERVE_VARS = ["NO_PROXY", "no_proxy"]

    def __init__(self, proxy_url: Optional[str] = None):
        """
        Initialize environment injector

        Args:
            proxy_url: Optional proxy URL (e.g., "http://127.0.0.1:8080" or "socks5://127.0.0.1:1080")
        """
        self.proxy_url = proxy_url

    def build_env(self, env: Optional[Dict[str, str]] = None, proxy_url: Optional[str] = None) -> Dict[str, str]:
        """
        Build environment dictionary with proxy variables injected

        Args:
            env: Base environment dictionary (defaults to os.environ.copy())
            proxy_url: Proxy URL to use (defaults to self.proxy_url)

        Returns:
            Environment dictionary with proxy variables set

        Raises:
            ValueError: If no proxy URL is configured
        """
        # Use provided env or copy current environment
        if env is None:
            env = os.environ.copy()
        else:
            env = env.copy()

        # Determine proxy URL to use
        url = proxy_url or self.proxy_url
        if not url:
            raise ValueError("No proxy URL provided")

        # Inject proxy variables (preserving NO_PROXY if it exists)
        for var in self.PROXY_VARS:
            # Don't overwrite preserved variables
            if var not in self.PRESERVE_VARS or var not in env:
                env[var] = url

        return env

    def clean_env(self, env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Remove all proxy-related variables from environment dictionary

        Args:
            env: Environment dictionary to clean (defaults to os.environ.copy())

        Returns:
            Environment dictionary with proxy variables removed
        """
        # Use provided env or copy current environment
        if env is None:
            env = os.environ.copy()
        else:
            env = env.copy()

        # Remove all proxy variables
        for var in self.PROXY_VARS:
            env.pop(var, None)

        # Also remove NO_PROXY variables
        for var in self.PRESERVE_VARS:
            env.pop(var, None)

        return env

    def get_proxy_vars(self, proxy_url: Optional[str] = None) -> Dict[str, str]:
        """
        Get dictionary of proxy environment variables

        Args:
            proxy_url: Proxy URL to use (defaults to self.proxy_url)

        Returns:
            Dictionary of proxy variable names to values

        Raises:
            ValueError: If no proxy URL is configured
        """
        url = proxy_url or self.proxy_url
        if not url:
            raise ValueError("No proxy URL provided")

        return {var: url for var in self.PROXY_VARS}

    def get_export_commands(self, proxy_url: Optional[str] = None, shell: str = "bash") -> List[str]:
        """
        Get shell export commands for setting proxy variables

        Args:
            proxy_url: Proxy URL to use (defaults to self.proxy_url)
            shell: Shell type ("bash", "zsh", "fish", "powershell")

        Returns:
            List of export command strings

        Raises:
            ValueError: If no proxy URL is configured or unsupported shell type
        """
        url = proxy_url or self.proxy_url
        if not url:
            raise ValueError("No proxy URL provided")

        if shell in ("bash", "zsh"):
            return [f"export {var}={url}" for var in self.PROXY_VARS]
        elif shell == "fish":
            return [f"set -gx {var} {url}" for var in self.PROXY_VARS]
        elif shell == "powershell":
            return [f"$env:{var} = '{url}'" for var in self.PROXY_VARS]
        else:
            raise ValueError(f"Unsupported shell type: {shell}")

    def get_unset_commands(self, shell: str = "bash") -> List[str]:
        """
        Get shell unset commands for removing proxy variables

        Args:
            shell: Shell type ("bash", "zsh", "fish", "powershell")

        Returns:
            List of unset command strings

        Raises:
            ValueError: If unsupported shell type
        """
        if shell in ("bash", "zsh"):
            commands = [f"unset {var}" for var in self.PROXY_VARS]
            commands.extend([f"unset {var}" for var in self.PRESERVE_VARS])
            return commands
        elif shell == "fish":
            commands = [f"set -e {var}" for var in self.PROXY_VARS]
            commands.extend([f"set -e {var}" for var in self.PRESERVE_VARS])
            return commands
        elif shell == "powershell":
            all_vars = self.PROXY_VARS + self.PRESERVE_VARS
            return [f"Remove-Item Env:{var}" for var in all_vars]
        else:
            raise ValueError(f"Unsupported shell type: {shell}")

    def has_proxy_vars(self, env: Optional[Dict[str, str]] = None) -> bool:
        """
        Check if environment has any proxy variables set

        Args:
            env: Environment dictionary to check (defaults to os.environ)

        Returns:
            True if any proxy variables are set, False otherwise
        """
        if env is None:
            env = os.environ

        return any(var in env for var in self.PROXY_VARS)

    def get_active_proxy_urls(self, env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Get all currently active proxy URLs from environment

        Args:
            env: Environment dictionary to check (defaults to os.environ)

        Returns:
            Dictionary of variable names to their proxy URLs
        """
        if env is None:
            env = os.environ

        return {var: env[var] for var in self.PROXY_VARS if var in env}
