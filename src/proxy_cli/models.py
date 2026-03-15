"""
Data models for proxy-cli-tool
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProxyConfig:
    """
    Proxy configuration data model

    Attributes:
        protocol: Proxy protocol (http, https, socks4, socks5)
        host: Proxy server hostname or IP address
        port: Proxy server port
        username: Optional username for authentication
        password: Optional password for authentication
        dns_remote: Use remote DNS resolution (SOCKS5 only)
        log_level: Logging level (debug, info, warning, error)
        log_file: Path to log file
    """

    protocol: str = "socks5"
    host: str = "127.0.0.1"
    port: int = 1080
    username: Optional[str] = None
    password: Optional[str] = None
    dns_remote: bool = True
    log_level: str = "info"
    log_file: str = "~/.proxy-cli/proxy.log"

    def to_dict(self) -> dict:
        """
        Convert config to dictionary, excluding None values

        Returns:
            Dictionary representation of config
        """
        result = {}
        for key, value in self.__dict__.items():
            if value is not None:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ProxyConfig":
        """
        Create config from dictionary

        Args:
            data: Dictionary containing config values

        Returns:
            ProxyConfig instance
        """
        # Filter out unknown keys
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    def get_proxy_url(self) -> str:
        """
        Get proxy URL in format: protocol://[username:password@]host:port

        Returns:
            Proxy URL string
        """
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    def validate(self) -> list[str]:
        """
        Validate configuration values

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate protocol
        valid_protocols = ["http", "https", "socks4", "socks5"]
        if self.protocol not in valid_protocols:
            errors.append(f"Invalid protocol '{self.protocol}'. Must be one of: {', '.join(valid_protocols)}")

        # Validate port
        if not 1 <= self.port <= 65535:
            errors.append(f"Invalid port '{self.port}'. Must be between 1 and 65535")

        # Validate log level
        valid_log_levels = ["debug", "info", "warning", "error"]
        if self.log_level not in valid_log_levels:
            errors.append(f"Invalid log level '{self.log_level}'. Must be one of: {', '.join(valid_log_levels)}")

        return errors
