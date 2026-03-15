"""
Proxy manager for proxy-cli-tool
Core coordinator for local proxy service, environment injection, and subprocess management
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from proxy_cli.config import ConfigManager
from proxy_cli.env_injector import EnvInjector
from proxy_cli.logger import get_logger
from proxy_cli.models import ProxyConfig
from proxy_cli.platform_adapter import PlatformAdapter
from proxy_cli.server import LocalProxyServer


class ProxyManager:
    """
    Core manager that coordinates proxy operations

    Manages:
    - Local proxy server lifecycle
    - Environment variable injection
    - Subprocess execution with proxy
    - Global proxy mode
    - State persistence
    """

    STATE_FILE = "~/.proxy-cli/state.json"

    def __init__(self, config: Optional[ProxyConfig] = None):
        """
        Initialize proxy manager

        Args:
            config: Optional proxy configuration (defaults to loading from config file)
        """
        self.logger = get_logger("proxy_cli.manager")
        self.config_manager = ConfigManager()
        self.env_injector = EnvInjector()
        self.platform_adapter = PlatformAdapter()

        # Load configuration
        if config is None:
            try:
                self.config = self.config_manager.load()
            except FileNotFoundError:
                self.config = ProxyConfig()
        else:
            self.config = config

        # Local proxy server (created when needed)
        self._server: Optional[LocalProxyServer] = None
        self._server_port: Optional[int] = None

        # State
        self._state_file = Path(self.STATE_FILE).expanduser()

    def run_command(
        self, command: List[str], proxy_url: Optional[str] = None, verbose: bool = False
    ) -> int:
        """
        Run a command with proxy enabled

        Complete flow:
        1. Start local proxy server
        2. Inject environment variables
        3. Run subprocess
        4. Wait for exit
        5. Clean up resources

        Args:
            command: Command and arguments to run
            proxy_url: Optional override proxy URL
            verbose: Enable verbose logging

        Returns:
            Process exit code
        """
        # Setup logging
        if verbose:
            self.logger.handlers[0].setLevel(1)  # DEBUG level

        self.logger.info(f"Running command with proxy: {' '.join(command)}")

        # Determine proxy URL to use
        if proxy_url:
            upstream_config = self._parse_proxy_url(proxy_url)
        else:
            upstream_config = {
                "protocol": self.config.protocol,
                "host": self.config.host,
                "port": self.config.port,
                "username": self.config.username,
                "password": self.config.password,
                "rdns": self.config.dns_remote,
            }

        # Start local proxy server
        self.logger.debug("Starting local proxy server...")
        self._server = LocalProxyServer(
            host="127.0.0.1", port=0, upstream_config=upstream_config
        )
        self._server_port = self._server.start()
        self.logger.info(f"Local proxy server listening on 127.0.0.1:{self._server_port}")

        # Build environment with proxy variables
        local_proxy_url = f"http://127.0.0.1:{self._server_port}"
        env = self.env_injector.build_env(proxy_url=local_proxy_url)

        try:
            # Setup signal handlers for graceful shutdown
            def signal_handler(signum, frame):
                self.logger.info(f"Received signal {signum}, shutting down...")
                self._cleanup()
                sys.exit(1)

            original_sigint = signal.getsignal(signal.SIGINT)
            original_sigterm = signal.getsignal(signal.SIGTERM)

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            try:
                # Run subprocess
                self.logger.debug(f"Executing: {' '.join(command)}")
                process = subprocess.Popen(command, env=env)

                # Wait for completion
                exit_code = process.wait()
                self.logger.info(f"Command exited with code {exit_code}")

                return exit_code

            finally:
                # Restore signal handlers
                signal.signal(signal.SIGINT, original_sigint)
                signal.signal(signal.SIGTERM, original_sigterm)

        except Exception as e:
            self.logger.error(f"Error running command: {e}")
            self._cleanup()
            return 1

        finally:
            # Always cleanup
            self._cleanup()

    def enable_global(
        self, proxy_url: Optional[str] = None, persist: bool = False
    ) -> Tuple[bool, str]:
        """
        Enable global proxy mode

        Starts a background proxy server and outputs shell commands to set proxy environment variables.

        Args:
            proxy_url: Optional override proxy URL
            persist: Whether to persist proxy configuration to shell config file

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Check if already enabled
            state = self._load_state()
            if state.get("enabled", False):
                # Check if the process is still running
                old_pid = state.get('pid')
                if old_pid and self._is_process_running(old_pid):
                    return (
                        False,
                        f"Proxy is already enabled (PID: {old_pid}, Port: {state.get('port')})\n"
                        f"Run 'proxy status' for more information.",
                    )
                else:
                    # Old process is dead, clean up state
                    self.logger.info(f"Old proxy process {old_pid} is dead, cleaning up state")

            # Determine upstream proxy config
            if proxy_url:
                upstream_config = self._parse_proxy_url(proxy_url)
            else:
                upstream_config = {
                    "protocol": self.config.protocol,
                    "host": self.config.host,
                    "port": self.config.port,
                    "username": self.config.username,
                    "password": self.config.password,
                    "rdns": self.config.dns_remote,
                }

            # Start local proxy server in a daemon process
            self._server_port = self._start_daemon_server(upstream_config)
            self.logger.info(
                f"Global proxy enabled: 127.0.0.1:{self._server_port} -> {upstream_config['protocol']}://{upstream_config['host']}:{upstream_config['port']}"
            )

            # Save state with daemon PID
            daemon_pid = self._get_daemon_pid()
            self._save_state(
                {
                    "enabled": True,
                    "pid": daemon_pid,
                    "port": self._server_port,
                    "upstream": upstream_config,
                }
            )

            # Generate shell commands
            local_proxy_url = f"http://127.0.0.1:{self._server_port}"
            success, message = self.platform_adapter.set_system_proxy(
                local_proxy_url, persist=persist
            )

            return success, message

        except Exception as e:
            self.logger.error(f"Error enabling global proxy: {e}")
            return False, f"Error enabling global proxy: {e}"

    def disable_global(self, persist: bool = False) -> Tuple[bool, str]:
        """
        Disable global proxy mode

        Stops the background proxy server and outputs shell commands to clear proxy environment variables.

        Args:
            persist: Whether to remove proxy configuration from shell config file

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Load state
            state = self._load_state()

            if not state.get("enabled", False):
                return (
                    False,
                    "Proxy is not enabled.\n"
                    "Run 'proxy status' for more information.",
                )

            # Stop local proxy server
            self._cleanup()

            # Clear state
            self._save_state({"enabled": False, "pid": None, "port": None, "upstream": None})

            # Generate shell commands
            success, message = self.platform_adapter.unset_system_proxy(persist=persist)

            return success, message

        except Exception as e:
            self.logger.error(f"Error disabling global proxy: {e}")
            return False, f"Error disabling global proxy: {e}"

    def get_status(self) -> Dict[str, any]:
        """
        Get current proxy status

        Returns:
            Dictionary with status information:
            - enabled: bool
            - port: int or None
            - upstream: dict or None
            - config: dict (current configuration)
        """
        state = self._load_state()
        config_dict = self.config.to_dict()

        # Don't include password in status
        if "password" in config_dict:
            config_dict["password"] = "***" if config_dict["password"] else None

        return {
            "enabled": state.get("enabled", False),
            "port": state.get("port"),
            "pid": state.get("pid"),
            "upstream": state.get("upstream"),
            "config": config_dict,
        }

    def _parse_proxy_url(self, proxy_url: str) -> Dict[str, any]:
        """
        Parse proxy URL into upstream config dict

        Args:
            proxy_url: Proxy URL (e.g., "socks5://127.0.0.1:1080" or "http://user:pass@proxy:8080")

        Returns:
            Upstream configuration dictionary
        """
        # Parse protocol
        if "://" not in proxy_url:
            raise ValueError(f"Invalid proxy URL: {proxy_url}")

        protocol, rest = proxy_url.split("://", 1)

        # Parse auth if present
        username = None
        password = None
        if "@" in rest:
            auth, host_port = rest.rsplit("@", 1)
            if ":" in auth:
                username, password = auth.split(":", 1)
            else:
                username = auth
        else:
            host_port = rest

        # Parse host and port
        if ":" in host_port:
            host, port_str = host_port.split(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                raise ValueError(f"Invalid port in proxy URL: {proxy_url}")
        else:
            host = host_port
            # Default ports
            if protocol == "http":
                port = 8080
            elif protocol == "https":
                port = 443
            elif protocol == "socks5":
                port = 1080
            elif protocol == "socks4":
                port = 1080
            else:
                raise ValueError(f"Unknown protocol: {protocol}")

        return {
            "protocol": protocol,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "rdns": protocol == "socks5",  # SOCKS5 supports remote DNS
        }

    def _load_state(self) -> Dict[str, any]:
        """
        Load state from state file

        Returns:
            State dictionary (empty if file doesn't exist)
        """
        try:
            if self._state_file.exists():
                with open(self._state_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Error loading state file: {e}")

        return {}

    def _save_state(self, state: Dict[str, any]) -> None:
        """
        Save state to state file

        Args:
            state: State dictionary to save
        """
        try:
            # Ensure state directory exists
            self._state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self._state_file, "w") as f:
                json.dump(state, f, indent=2)

            # Set file permissions to 600 on Unix
            if self.platform_adapter.is_unix:
                try:
                    os.chmod(self._state_file, 0o600)
                except:
                    pass

        except Exception as e:
            self.logger.error(f"Error saving state file: {e}")

    def _cleanup(self) -> None:
        """
        Clean up resources (stop proxy server)
        """
        if self._server is not None:
            try:
                if self._server.is_running():
                    self.logger.info("Stopping local proxy server...")
                    self._server.stop()
                    self.logger.debug("Local proxy server stopped")
            except Exception as e:
                self.logger.error(f"Error stopping server: {e}")

            self._server = None
            self._server_port = None

    def _is_process_running(self, pid: int) -> bool:
        """
        Check if a process is running

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        try:
            if self.platform_adapter.is_unix:
                os.kill(pid, 0)
                return True
            else:
                # Windows
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x100000
                process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if process:
                    kernel32.CloseHandle(process)
                    return True
                return False
        except (OSError, ProcessLookupError):
            return False

    def _start_daemon_server(self, upstream_config: dict) -> int:
        """
        Start proxy server as a daemon process using subprocess

        Args:
            upstream_config: Upstream proxy configuration

        Returns:
            Port number the server is listening on
        """
        import tempfile
        import json

        # Create temp files for communication
        port_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.port')
        port_file.close()

        config_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json')
        json.dump(upstream_config, config_file)
        config_file.close()

        # Create daemon runner script
        daemon_script = '''
import sys
import os
import json
import time

# Load config
config_file = sys.argv[1]
port_file = sys.argv[2]

with open(config_file, 'r') as f:
    upstream_config = json.load(f)

# Add package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proxy_cli.server import LocalProxyServer
from proxy_cli.logger import setup_logger

logger = setup_logger("proxy_cli.daemon", level="warning")

# Start server
server = LocalProxyServer(
    host="127.0.0.1",
    port=0,
    upstream_config=upstream_config
)

port = server.start()
logger.info(f"Daemon server listening on port {port}")

# Write port to file
with open(port_file, 'w') as f:
    f.write(str(port))

# Keep running forever
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    logger.info("Daemon shutting down...")
    server.stop()
'''

        # Write daemon script
        script_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py')
        script_file.write(daemon_script)
        script_file.close()

        try:
            # Start daemon process
            if self.platform_adapter.is_unix:
                # Unix: use nohup to start daemon
                daemon_process = subprocess.Popen(
                    ['nohup', sys.executable, script_file.name, config_file.name, port_file.name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True
                )
            else:
                # Windows: use CREATE_NEW_PROCESS_GROUP
                daemon_process = subprocess.Popen(
                    [sys.executable, script_file.name, config_file.name, port_file.name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )

            # Wait for server to start and read port
            import time
            for _ in range(50):  # Wait up to 5 seconds
                time.sleep(0.1)
                try:
                    with open(port_file.name, 'r') as f:
                        content = f.read().strip()
                        if content:
                            port = int(content)
                            self.logger.info(f"Daemon server started on port {port}, PID: {daemon_process.pid}")
                            return port
                except (FileNotFoundError, ValueError):
                    continue

            raise RuntimeError("Daemon server failed to start within timeout")

        finally:
            # Clean up temp files
            try:
                os.unlink(port_file.name)
            except:
                pass
            try:
                os.unlink(config_file.name)
            except:
                pass
            try:
                os.unlink(script_file.name)
            except:
                pass

    def _get_daemon_pid(self) -> int:
        """
        Get the PID of the daemon process

        Returns:
            Daemon process ID
        """
        # Find the daemon process by port number
        import time
        time.sleep(0.2)  # Give process time to fully start

        # Try to find process using the port
        port = self._server_port
        try:
            if self.platform_adapter.is_unix:
                result = subprocess.run(
                    ['lsof', '-t', '-i', f':{port}', '-sTCP:LISTEN'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    return int(result.stdout.strip().split('\n')[0])
            else:
                # Windows
                result = subprocess.run(
                    ['netstat', '-ano'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                for line in result.stdout.split('\n'):
                    if f':{port}' in line and 'LISTENING' in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            return int(parts[-1])
        except Exception as e:
            self.logger.warning(f"Could not determine daemon PID: {e}")

        # Fallback: return current process PID
        return os.getpid()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cleanup"""
        self._cleanup()
