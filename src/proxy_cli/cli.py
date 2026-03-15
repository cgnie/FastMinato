"""
CLI entry point for proxy-cli-tool
"""

import sys

import click
from proxy_cli import __version__
from proxy_cli.config import ConfigManager
from proxy_cli.logger import setup_logger
from proxy_cli.manager import ProxyManager
from proxy_cli.models import ProxyConfig


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def main(ctx: click.Context) -> None:
    """
    Proxy CLI Tool - A command-line proxy tool for managing upstream proxy connections

    Run commands with proxy, or enable/disable global proxy mode.

    \b
    Examples:
      proxy run curl https://api.ip.sb
      proxy on
      proxy off
      proxy status
    """
    ctx.ensure_object(dict)


@main.command(context_settings={"ignore_unknown_options": True})
@click.argument("command", nargs=-1, required=True)
@click.option("--proxy", "-p", help="Override proxy URL (e.g., socks5://127.0.0.1:1080)")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def run(command: tuple, proxy: str, verbose: bool) -> None:
    """
    Run a command with proxy enabled

    The command will be executed with proxy environment variables injected.
    A local proxy server will be started and automatically cleaned up after the command completes.

    \b
    Examples:
      proxy run curl https://api.ip.sb
      proxy run git fetch origin --progress --prune
      proxy run --proxy socks5://127.0.0.1:1080 npm install
      proxy run --verbose git push
    """
    if not command:
        click.echo("Error: No command specified", err=True)
        sys.exit(1)

    # Setup logging
    logger = setup_logger("proxy_cli", level="debug" if verbose else "warning", verbose=verbose)

    try:
        manager = ProxyManager()
        exit_code = manager.run_command(
            list(command), proxy_url=proxy, verbose=verbose
        )
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Error running command: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--proxy", "-p", help="Override proxy URL (e.g., socks5://127.0.0.1:1080)")
@click.option("--persist", is_flag=True, help="Persist proxy configuration to shell config file")
def on(proxy: str, persist: bool) -> None:
    """
    Enable global proxy mode

    Starts a background proxy server and displays shell commands to set proxy environment variables.

    \b
    After running this command, execute the displayed shell commands to enable proxy in your current shell:

    \b
    For Bash/Zsh:
      eval $(proxy on)

    For PowerShell:
      proxy on | Invoke-Expression

    \b
    Examples:
      proxy on
      proxy on --proxy socks5://127.0.0.1:1080
      proxy on --persist
    """
    logger = setup_logger("proxy_cli", level="warning")

    try:
        manager = ProxyManager()
        success, message = manager.enable_global(proxy_url=proxy, persist=persist)

        # Split message into comments and commands
        lines = message.split('\n')
        commands = []
        comments = []
        for line in lines:
            if line.startswith('#'):
                comments.append(line)
            else:
                commands.append(line)

        # Print comments to stderr
        for comment in comments:
            if comment.strip():
                click.echo(comment, err=True)

        # Print commands to stdout (for eval)
        click.echo('\n'.join(commands))

        if not success:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error enabling proxy: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--persist", is_flag=True, help="Remove proxy configuration from shell config file")
def off(persist: bool) -> None:
    """
    Disable global proxy mode

    Stops the background proxy server and displays shell commands to clear proxy environment variables.

    \b
    After running this command, execute the displayed shell commands to disable proxy in your current shell:

    \b
    For Bash/Zsh:
      eval $(proxy off)

    For PowerShell:
      proxy off | Invoke-Expression

    \b
    Examples:
      proxy off
      proxy off --persist
    """
    logger = setup_logger("proxy_cli", level="warning")

    try:
        manager = ProxyManager()
        success, message = manager.disable_global(persist=persist)

        # Split message into comments and commands
        lines = message.split('\n')
        commands = []
        comments = []
        for line in lines:
            if line.startswith('#'):
                comments.append(line)
            else:
                commands.append(line)

        # Print comments to stderr
        for comment in comments:
            if comment.strip():
                click.echo(comment, err=True)

        # Print commands to stdout (for eval)
        click.echo('\n'.join(commands))

        if not success:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error disabling proxy: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed status information")
def status(verbose: bool) -> None:
    """
    Show current proxy status

    Displays whether global proxy mode is enabled, proxy configuration, and connection details.
    """
    logger = setup_logger("proxy_cli", level="warning")

    try:
        manager = ProxyManager()
        status_info = manager.get_status()

        # Display status
        if status_info["enabled"]:
            click.echo("Proxy Status: Enabled")
            click.echo(f"  Local Port: {status_info['port']}")
            if status_info.get("upstream"):
                upstream = status_info["upstream"]
                click.echo(f"  Upstream: {upstream['protocol']}://{upstream['host']}:{upstream['port']}")
                if upstream.get("username"):
                    click.echo(f"  Username: {upstream['username']}")
        else:
            click.echo("Proxy Status: Disabled")

        # Display configuration
        click.echo("\nConfiguration:")
        config = status_info["config"]
        click.echo(f"  Protocol: {config['protocol']}")
        click.echo(f"  Host: {config['host']}")
        click.echo(f"  Port: {config['port']}")
        if config.get("username"):
            click.echo(f"  Username: {config['username']}")
        click.echo(f"  DNS Remote: {config['dns_remote']}")
        click.echo(f"  Proxy URL: {config['protocol']}://{config['host']}:{config['port']}")

        if verbose:
            click.echo(f"\nLog Level: {config['log_level']}")
            click.echo(f"Log File: {config['log_file']}")

    except Exception as e:
        logger.error(f"Error getting status: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.group()
def config() -> None:
    """
    Manage proxy configuration

    Configuration is stored in ~/.proxy-cli/config.yaml
    """
    pass


@config.command("init")
def config_init() -> None:
    """
    Initialize default configuration

    Creates ~/.proxy-cli/config.yaml with default values
    """
    mgr = ConfigManager()

    if mgr.exists():
        if not click.confirm("Configuration file already exists. Overwrite?", default=False):
            click.echo("Aborted.")
            return

    config = mgr.init_default()
    click.echo(f"✓ Configuration initialized at {mgr.config_file}")
    click.echo(f"  Proxy URL: {config.get_proxy_url()}")


@config.command("show")
@click.option("--verbose", "-v", is_flag=True, help="Show all configuration details")
def config_show(verbose: bool) -> None:
    """
    Show current configuration
    """
    mgr = ConfigManager()

    if not mgr.exists():
        click.echo("No configuration found. Run 'proxy config init' to create one.")
        return

    config = mgr.load()

    click.echo("Current configuration:")
    click.echo(f"  Protocol: {config.protocol}")
    click.echo(f"  Host: {config.host}")
    click.echo(f"  Port: {config.port}")
    if config.username:
        click.echo(f"  Username: {config.username}")
    click.echo(f"  DNS Remote: {config.dns_remote}")
    click.echo(f"\n  Proxy URL: {config.get_proxy_url()}")

    if verbose:
        click.echo(f"\n  Log Level: {config.log_level}")
        click.echo(f"  Log File: {config.log_file}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """
    Set a configuration value

    Examples:
      proxy config set port 10808
      proxy config set protocol socks5
      proxy config set host 192.168.1.1
    """
    mgr = ConfigManager()

    if not mgr.exists():
        click.echo("No configuration found. Run 'proxy config init' to create one.")
        return

    try:
        # Convert value to appropriate type
        config = mgr.config
        field_type = type(getattr(config, key))

        if field_type == bool:
            value = value.lower() in ("true", "1", "yes", "on")
        elif field_type == int:
            value = int(value)

        mgr.set(key, value)
        click.echo(f"✓ Set {key} = {value}")
    except AttributeError as e:
        click.echo(f"Error: {e}")
    except (ValueError, TypeError) as e:
        click.echo(f"Error: Invalid value for {key}: {e}")


@config.command("validate")
def config_validate() -> None:
    """
    Validate current configuration
    """
    mgr = ConfigManager()

    if not mgr.exists():
        click.echo("No configuration found. Run 'proxy config init' to create one.")
        return

    config = mgr.load()
    errors = config.validate()

    if errors:
        click.echo("Configuration validation failed:")
        for error in errors:
            click.echo(f"  ✗ {error}")
    else:
        click.echo("✓ Configuration is valid")


@config.command("clear")
def config_clear() -> None:
    """
    Clear all configuration by deleting the configuration file

    This will remove the configuration file at ~/.proxy-cli/config.yaml.
    You can run 'proxy config init' to create a new default configuration.
    """
    mgr = ConfigManager()

    if not mgr.exists():
        click.echo("No configuration found. Nothing to clear.")
        return

    if click.confirm(
        "This will delete all configuration at ~/.proxy-cli/config.yaml. Continue?",
        default=False,
    ):
        mgr.delete()
        click.echo("✓ Configuration cleared")

        # Also try to remove the state file if it exists
        state_file = mgr.config_dir / "state.json"
        if state_file.exists():
            state_file.unlink()
            click.echo("✓ State file cleared")


if __name__ == "__main__":
    main()
