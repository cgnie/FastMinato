"""
Configuration management for proxy-cli-tool

Copyright (c) 2026 cgnie chenguang.nie@icloud.com

Licensed under the MIT License.
"""

import os
import platform
import stat
from pathlib import Path
from typing import Optional

import yaml

from proxy_cli.models import ProxyConfig


class ConfigManager:
    """
    Manages configuration loading, saving, and manipulation
    """

    DEFAULT_CONFIG_DIR = "~/.proxy-cli"
    DEFAULT_CONFIG_FILE = "config.yaml"

    def __init__(self, config_dir: Optional[str] = None, config_file: Optional[str] = None):
        """
        Initialize ConfigManager

        Args:
            config_dir: Configuration directory path (defaults to ~/.proxy-cli)
            config_file: Configuration file name (defaults to config.yaml)
        """
        self.config_dir = Path(config_dir or self.DEFAULT_CONFIG_DIR).expanduser()
        self.config_file = self.config_dir / (config_file or self.DEFAULT_CONFIG_FILE)
        self._config: Optional[ProxyConfig] = None

    @property
    def config(self) -> ProxyConfig:
        """
        Get current configuration (lazy loads if not loaded)

        Returns:
            Current ProxyConfig instance
        """
        if self._config is None:
            self.load()
        return self._config

    def load(self, overrides: Optional[dict] = None) -> ProxyConfig:
        """
        Load configuration from file

        Args:
            overrides: Optional dictionary of values to override loaded config

        Returns:
            Loaded ProxyConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist and no overrides provided
            yaml.YAMLError: If config file is invalid YAML
        """
        if not self.config_file.exists():
            if overrides:
                self._config = ProxyConfig.from_dict(overrides)
            else:
                raise FileNotFoundError(
                    f"Configuration file not found: {self.config_file}. "
                    "Run 'proxy config init' to create default configuration."
                )

        with open(self.config_file, "r") as f:
            data = yaml.safe_load(f) or {}

        # Apply overrides
        if overrides:
            data.update(overrides)

        self._config = ProxyConfig.from_dict(data)
        return self._config

    def save(self, config: Optional[ProxyConfig] = None) -> None:
        """
        Save configuration to file

        Args:
            config: ProxyConfig instance to save (defaults to current config)
        """
        if config is not None:
            self._config = config

        if self._config is None:
            raise ValueError("No configuration to save")

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Save config to file
        with open(self.config_file, "w") as f:
            yaml.dump(self._config.to_dict(), f, default_flow_style=False, sort_keys=False)

        # Set file permissions on Unix-like systems
        self._set_permissions()

    def set(self, key: str, value: any) -> None:
        """
        Set a single configuration value and persist to file

        Args:
            key: Configuration key name
            value: Configuration value

        Raises:
            AttributeError: If key is not a valid configuration field
        """
        if not hasattr(ProxyConfig, key):
            valid_keys = [f.name for f in ProxyConfig.__dataclass_fields__.values()]
            raise AttributeError(
                f"Invalid configuration key '{key}'. Valid keys: {', '.join(valid_keys)}"
            )

        # Ensure config is loaded
        _ = self.config

        # Set the value
        setattr(self._config, key, value)

        # Save to file
        self.save()

    def get(self, key: str) -> any:
        """
        Get a single configuration value

        Args:
            key: Configuration key name

        Returns:
            Configuration value

        Raises:
            AttributeError: If key is not a valid configuration field
        """
        if not hasattr(ProxyConfig, key):
            valid_keys = [f.name for f in ProxyConfig.__dataclass_fields__.values()]
            raise AttributeError(
                f"Invalid configuration key '{key}'. Valid keys: {', '.join(valid_keys)}"
            )

        return getattr(self.config, key)

    def init_default(self) -> ProxyConfig:
        """
        Initialize default configuration

        Returns:
            Default ProxyConfig instance
        """
        self._config = ProxyConfig()
        self.save()
        return self._config

    def exists(self) -> bool:
        """
        Check if configuration file exists

        Returns:
            True if configuration file exists, False otherwise
        """
        return self.config_file.exists()

    def _set_permissions(self) -> None:
        """
        Set file permissions to 600 (read/write for owner only) on Unix-like systems

        On Windows, this is a no-op as Windows uses ACLs instead.
        """
        if platform.system() != "Windows":
            try:
                os.chmod(self.config_file, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                # Fail silently if we can't set permissions
                pass

    def delete(self) -> None:
        """
        Delete configuration file if it exists
        """
        if self.config_file.exists():
            self.config_file.unlink()
        self._config = None
