# FastMinato

[English](#english) | [中文](#中文)

---

## English

### What is FastMinato?

FastMinato is a high-performance command-line proxy tool that manages upstream proxy connections (SOCKS4/5, HTTP/HTTPS). It provides a convenient way to run commands with proxy or enable global proxy mode in your terminal.

**Key Features:**
- 🚀 **Command Wrapping**: Run individual commands with proxy (`proxy run <command>`)
- 🌍 **Global Proxy Mode**: Enable proxy for entire shell session (`proxy on`)
- 🔄 **Multiple Protocols**: Supports SOCKS4, SOCKS5, HTTP, HTTPS upstream proxies
- 🔐 **Authentication**: Supports username/password authentication
- 📝 **Configuration Management**: YAML-based configuration with validation
- 📊 **Logging**: Rotating logs with sensitive data redaction
- 🖥️ **Cross-Platform**: Works on Linux, macOS, and Windows
- ⚡ **High Performance**: Daemon-based proxy server for persistent connections

### Architecture

```
FastMinato/
├── src/proxy_cli/
│   ├── __init__.py          # Package initialization
│   ├── cli.py               # CLI entry point (Click commands)
│   ├── models.py            # Data models (ProxyConfig)
│   ├── config.py            # Configuration management
│   ├── logger.py            # Logging setup
│   ├── server.py            # Local HTTP proxy server
│   ├── manager.py           # Core proxy manager
│   ├── env_injector.py      # Environment variable injection
│   └── platform_adapter.py  # Cross-platform shell commands
├── pyproject.toml           # Project configuration
├── README.md                # This file
└── LICENSE                  # MIT License
```

### How It Works

FastMinato uses a **two-layer proxy architecture**:

```
Your Application → Local Proxy Server → Upstream Proxy → Target Website
                       (HTTP)            (SOCKS5/HTTP)
                   127.0.0.1:DYNAMIC    127.0.0.1:1080
```

**Two Usage Modes:**

1. **Command Wrapping Mode** (`proxy run`):
   - Local proxy server starts before command, stops after
   - Each command gets a fresh temporary proxy server
   - Clean and isolated, no shell configuration changes

2. **Global Proxy Mode** (`proxy on`):
   - Local proxy server runs as a **daemon process** in the background
   - Environment variables are set in your current shell
   - All subsequent commands in that shell session use proxy automatically
   - Daemon continues running until `proxy off` is executed

**Key Components:**
- **Local Proxy Server**: HTTP server on `127.0.0.1:动态端口` that receives application requests
- **Upstream Proxy**: Your existing proxy (e.g., V2Ray/XRay on `127.0.0.1:1080`)
- **Environment Injection**: Sets `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` to point to local proxy
- **Daemon Process**: Background process that keeps the local proxy server running

### Quick Start

#### 1. Installation

```bash
# Clone repository
git clone https://github.com/cgnie/FastMinato.git
cd FastMinato

# Install in development mode
pip install -e .
```

Or install directly from PyPI (when published):

```bash
pip install fastminato
```

#### 2. Initialize Configuration

```bash
# Create default configuration
proxy config init
```

This creates `~/.proxy-cli/config.yaml` with default values:

```yaml
protocol: socks5
host: 127.0.0.1
port: 1080
dns_remote: true
log_level: info
log_file: ~/.proxy-cli/proxy.log
```

#### 3. Test Proxy Connection

```bash
# Test with command wrapping mode (recommended for one-off use)
proxy run curl https://api.ip.sb

# Or enable global proxy mode (recommended for extended sessions)
eval $(proxy on)
curl https://api.ip.sb
eval $(proxy off)
```

**⚠️ Important**: For global proxy mode, you MUST use `eval $(proxy on)`, not just `proxy on`.
- `proxy on` only displays the commands to set environment variables
- `eval $(proxy on)` actually executes those commands in your current shell

### Usage

#### Mode 1: Command Wrapping (Recommended for One-off Commands)

Run individual commands with proxy:

```bash
proxy run curl https://www.google.com
proxy run git pull
proxy run npm install
proxy run pip install requests
```

**Characteristics:**
- Proxy server starts before command, stops after
- Only affects the wrapped command
- No shell configuration changes
- No daemon processes left behind
- Clean and isolated

#### Mode 2: Global Proxy Mode (Recommended for Extended Sessions)

Enable proxy for entire shell session:

```bash
# Enable global proxy (starts daemon process)
eval $(proxy on)

# Now all commands use proxy automatically
curl https://api.ip.sb
git fetch origin
npm install

# Disable when done (stops daemon process)
eval $(proxy off)
```

**Characteristics:**
- Proxy server runs as a **daemon process** in the background
- All commands in current shell use proxy automatically
- Environment variables persist until `eval $(proxy off)`
- Daemon process continues running even after the `proxy on` command exits
- **Must use `eval $(proxy on)`** - not just `proxy on`

### Commands Reference

#### Main Commands

##### `proxy run <command> [--proxy <url>] [--verbose]`

Run a command with proxy enabled.

```bash
# Basic usage
proxy run curl https://api.ip.sb

# Override proxy URL
proxy run --proxy http://192.168.1.1:8080 curl https://api.ip.sb

# Enable verbose output
proxy run --verbose git pull

# Commands with options (works correctly)
proxy run git fetch origin --progress --prune
```

**Options:**
- `--proxy`, `-p`: Override proxy URL (e.g., `socks5://127.0.0.1:1080`)
- `--verbose`, `-v`: Enable verbose logging

##### `proxy on [--proxy <url>] [--persist]`

Enable global proxy mode.

```bash
# Basic usage
eval $(proxy on)

# Override proxy URL
eval $(proxy on --proxy socks5://127.0.0.1:1080)

# Persist to shell config file
proxy on --persist
```

**Options:**
- `--proxy`, `-p`: Override proxy URL
- `--persist`: Write proxy configuration to shell config file (`~/.zshrc`, `~/.bashrc`, etc.)

##### `proxy off [--persist]`

Disable global proxy mode.

```bash
# Basic usage
eval $(proxy off)

# Remove from shell config file
proxy off --persist
```

**Options:**
- `--persist`: Remove proxy configuration from shell config file

##### `proxy status [--verbose]`

Show current proxy status and configuration.

```bash
# Basic status
proxy status

# Verbose output
proxy status --verbose
```

**Output:**
```
Proxy Status: Disabled
Configuration:
  Protocol: socks5
  Host: 127.0.0.1
  Port: 1080
  DNS Remote: True
  Proxy URL: socks5://127.0.0.1:1080
```

#### Configuration Commands

##### `proxy config init`

Initialize default configuration file.

```bash
proxy config init
```

Creates `~/.proxy-cli/config.yaml` with default values.

##### `proxy config show [--verbose]`

Show current configuration.

```bash
# Basic configuration
proxy config show

# Include all details
proxy config show --verbose
```

##### `proxy config set <key> <value>`

Set a configuration value.

```bash
# Change port
proxy config set port 10808

# Change protocol
proxy config set protocol http

# Change host
proxy config set host 192.168.1.1

# Enable remote DNS
proxy config set dns_remote true
```

**Available keys:**
- `protocol`: Proxy protocol (`http`, `https`, `socks4`, `socks5`)
- `host`: Proxy server hostname or IP
- `port`: Proxy server port (1-65535)
- `username`: Authentication username (optional)
- `password`: Authentication password (optional)
- `dns_remote`: Enable remote DNS resolution (`true`/`false`)
- `log_level`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `log_file`: Log file path

##### `proxy config validate`

Validate current configuration.

```bash
proxy config validate
```

Output:
```
✓ Configuration is valid
```

Or:
```
Configuration validation failed:
  ✗ Port must be between 1 and 65535
  ✗ Invalid protocol: invalid_protocol
```

##### `proxy config clear`

Delete all configuration files.

```bash
proxy config clear
```

Prompts for confirmation, then deletes:
- `~/.proxy-cli/config.yaml`
- `~/.proxy-cli/state.json`

### File Locations

All data is stored in `~/.proxy-cli/`:

```
~/.proxy-cli/
├── config.yaml    # Proxy configuration
├── state.json     # Global proxy state
└── proxy.log      # Application logs
```

### Proxy URL Formats

FastMinato supports multiple proxy URL formats:

```bash
# SOCKS5 (default)
socks5://127.0.0.1:1080

# SOCKS4
socks4://127.0.0.1:1080

# HTTP
http://127.0.0.1:8080

# HTTPS
https://127.0.0.1:443

# With authentication
socks5://username:password@127.0.0.1:1080
http://user:pass@proxy.example.com:8080
```

### Platform Support

FastMinato supports multiple platforms and shells:

**Platforms:**
- ✅ Linux
- ✅ macOS
- ✅ Windows

**Shells:**
- ✅ Bash
- ✅ Zsh
- ✅ Fish
- ✅ PowerShell
- ✅ CMD

### Examples

#### Example 1: Git Operations with Proxy

```bash
# Command wrapping mode
proxy run git fetch origin
proxy run git pull
proxy run git push

# Global proxy mode
eval $(proxy on)
git fetch origin
git pull
git push
eval $(proxy off)
```

#### Example 2: Package Management

```bash
# npm
proxy run npm install
proxy run npm update

# pip
proxy run pip install requests
proxy run pip install --upgrade pip

# apt (Ubuntu/Debian)
sudo proxy run apt update
sudo proxy run apt upgrade
```

#### Example 3: Web Scraping

```bash
# curl
proxy run curl -I https://www.google.com

# wget
proxy run wget https://example.com/file.zip

# Python requests
proxy run python script.py
```

### Troubleshooting

#### Commands not using proxy after `eval $(proxy on)`

**Symptom**: You ran `eval $(proxy on)` but commands don't use proxy.

**Solution 1**: Verify environment variables are set:
```bash
env | grep -i proxy
```
You should see output like:
```
HTTP_PROXY=http://127.0.0.1:xxxxx
HTTPS_PROXY=http://127.0.0.1:xxxxx
ALL_PROXY=http://127.0.0.1:xxxxx
```

**Solution 2**: Check if daemon is running:
```bash
proxy status
lsof -i :<port>  # Replace <port> with the port from proxy status
```

**Solution 3**: Clear state and try again:
```bash
rm ~/.proxy-cli/state.json
eval $(proxy on)
```

#### "Proxy is already enabled" error

**Symptom**: Running `proxy on` shows "Proxy is already enabled".

**Cause**: The daemon process is still running from a previous session.

**Solution**:
```bash
# Check status
proxy status

# Disable first (this stops the daemon)
eval $(proxy off)

# Then enable again if needed
eval $(proxy on)
```

#### Curl shows "Couldn't connect to server"

**Symptom**: `curl` fails with "Failed to connect to 127.0.0.1 port xxxx".

**Cause**: The local proxy daemon is not running.

**Solution 1**: Check if daemon process exists:
```bash
# Find the process
ps aux | grep "Python.*proxy-cli"

# If found, note the PID and check proxy status
proxy status
```

**Solution 2**: Restart proxy:
```bash
eval $(proxy off)
eval $(proxy on)
```

#### Upstream proxy connection failed

**Symptom**: Everything works locally but can't reach external websites.

**Solution 1**: Test upstream proxy directly:
```bash
# For SOCKS5 proxy
curl --socks5 127.0.0.1:1080 https://api.ip.sb

# For HTTP proxy
curl -x http://127.0.0.1:8080 https://api.ip.sb
```

**Solution 2**: Verify upstream proxy is running:
```bash
# Check if port is in use
lsof -i :1080  # Or your upstream proxy port
```

**Solution 3**: Check configuration:
```bash
proxy config validate
proxy config show
```

#### Check logs for errors

```bash
# View recent logs
tail -50 ~/.proxy-cli/proxy.log

# Follow logs in real-time
tail -f ~/.proxy-cli/proxy.log
```

#### Common mistakes to avoid

❌ **Wrong**: `proxy on` (without eval)
- This only displays commands, doesn't execute them

❌ **Wrong**: `eval proxy on` (without $())
- This tries to execute the string "proxy on"

❌ **Wrong**: `sudo proxy on` (with sudo)
- Creates state file with root permissions

✅ **Correct**: `eval $(proxy on)`
- Executes the commands in current shell

### Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### License

MIT License - see LICENSE file for details

---

## 中文

### FastMinato 是什么？

FastMinato 是一个高性能命令行代理工具，用于管理上游代理连接（SOCKS4/5、HTTP/HTTPS）。它提供了便捷的方式在终端中使用代理运行命令或启用全局代理模式。

**核心特性：**
- 🚀 **命令包装**：使用代理运行单个命令（`proxy run <命令>`）
- 🌍 **全局代理模式**：为整个 shell 会话启用代理（`proxy on`）
- 🔄 **多协议支持**：支持 SOCKS4、SOCKS5、HTTP、HTTPS 上游代理
- 🔐 **身份验证**：支持用户名/密码认证
- 📝 **配置管理**：基于 YAML 的配置文件，支持验证
- 📊 **日志记录**：带敏感数据脱敏的循环日志
- 🖥️ **跨平台**：支持 Linux、macOS 和 Windows
- ⚡ **高性能**：基于守护进程的代理服务器，支持持久连接

### 架构设计

```
FastMinato/
├── src/proxy_cli/
│   ├── __init__.py          # 包初始化
│   ├── cli.py               # CLI 入口点（Click 命令）
│   ├── models.py            # 数据模型（ProxyConfig）
│   ├── config.py            # 配置管理
│   ├── logger.py            # 日志设置
│   ├── server.py            # 本地 HTTP 代理服务器
│   ├── manager.py           # 核心代理管理器
│   ├── env_injector.py      # 环境变量注入
│   └── platform_adapter.py  # 跨平台 shell 命令
├── pyproject.toml           # 项目配置
├── README.md                # 本文件
└── LICENSE                  # MIT 许可证
```

### 工作原理

FastMinato 使用**双层代理架构**：

```
你的应用程序 → 本地代理服务器 → 上游代理 → 目标网站
                       (HTTP)            (SOCKS5/HTTP)
                   127.0.0.1:动态端口    127.0.0.1:1080
```

**两种使用模式：**

1. **命令包装模式**（`proxy run`）：
   - 本地代理服务器在命令启动前启动，命令结束后停止
   - 每个命令都获得一个新的临时代理服务器
   - 清理隔离，无需修改 shell 配置

2. **全局代理模式**（`proxy on`）：
   - 本地代理服务器作为**守护进程**在后台运行
   - 环境变量在你当前的 shell 中设置
   - 该 shell 会话中的所有后续命令自动使用代理
   - 守护进程持续运行，直到执行 `proxy off`

**核心组件：**
- **本地代理服务器**：运行在 `127.0.0.1:动态端口` 上的 HTTP 服务器，接收应用程序请求
- **上游代理**：你现有的代理服务器（例如 V2Ray/XRay 在 `127.0.0.1:1080`）
- **环境变量注入**：设置 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 指向本地代理
- **守护进程**：保持本地代理服务器运行的后台进程

### 快速开始

#### 1. 安装

```bash
# 克隆仓库
git clone https://github.com/cgnie/FastMinato.git
cd FastMinato

# 以开发模式安装
pip install -e .
```

或直接从 PyPI 安装（发布后）：

```bash
pip install fastminato
```

#### 2. 初始化配置

```bash
# 创建默认配置
proxy config init
```

这会创建 `~/.proxy-cli/config.yaml` 并包含默认值：

```yaml
protocol: socks5
host: 127.0.0.1
port: 1080
dns_remote: true
log_level: info
log_file: ~/.proxy-cli/proxy.log
```

#### 3. 测试代理连接

```bash
# 使用命令包装模式测试（推荐用于偶尔使用）
proxy run curl https://api.ip.sb

# 或启用全局代理模式（推荐用于持续使用）
eval $(proxy on)
curl https://api.ip.sb
eval $(proxy off)
```

**⚠️ 重要提示**：对于全局代理模式，你必须使用 `eval $(proxy on)`，而不能只用 `proxy on`。
- `proxy on` 只显示设置环境变量的命令
- `eval $(proxy on)` 才会在当前的 shell 中实际执行这些命令

### 使用方法

#### 方式 1：命令包装模式（推荐用于偶尔使用）

使用代理运行单个命令：

```bash
proxy run curl https://www.google.com
proxy run git pull
proxy run npm install
proxy run pip install requests
```

**特点：**
- 代理服务器在命令启动前启动，命令结束后停止
- 只影响被包装的命令
- 不需要修改 shell 配置
- 不会留下守护进程
- 清理且隔离

#### 方式 2：全局代理模式（推荐用于持续使用）

为整个 shell 会话启用代理：

```bash
# 启用全局代理（启动守护进程）
eval $(proxy on)

# 现在所有命令都会自动使用代理
curl https://api.ip.sb
git fetch origin
npm install

# 使用完毕后关闭（停止守护进程）
eval $(proxy off)
```

**特点：**
- 代理服务器作为**守护进程**在后台运行
- 当前 shell 中的所有命令都自动使用代理
- 环境变量持续有效，直到执行 `eval $(proxy off)`
- 即使 `proxy on` 命令退出，守护进程仍继续运行
- **必须使用 `eval $(proxy on)`** - 不能只用 `proxy on`

### 命令参考

#### 主要命令

##### `proxy run <命令> [--proxy <url>] [--verbose]`

使用代理运行命令。

```bash
# 基本用法
proxy run curl https://api.ip.sb

# 覆盖代理 URL
proxy run --proxy http://192.168.1.1:8080 curl https://api.ip.sb

# 启用详细输出
proxy run --verbose git pull

# 带选项的命令（可以正常工作）
proxy run git fetch origin --progress --prune
```

**选项：**
- `--proxy`, `-p`：覆盖代理 URL（例如 `socks5://127.0.0.1:1080`）
- `--verbose`, `-v`：启用详细日志

##### `proxy on [--proxy <url>] [--persist]`

启用全局代理模式。

```bash
# 基本用法
eval $(proxy on)

# 覆盖代理 URL
eval $(proxy on --proxy socks5://127.0.0.1:1080)

# 持久化到 shell 配置文件
proxy on --persist
```

**选项：**
- `--proxy`, `-p`：覆盖代理 URL
- `--persist`：将代理配置写入 shell 配置文件（`~/.zshrc`、`~/.bashrc` 等）

##### `proxy off [--persist]`

禁用全局代理模式。

```bash
# 基本用法
eval $(proxy off)

# 从 shell 配置文件中移除
proxy off --persist
```

**选项：**
- `--persist`：从 shell 配置文件中移除代理配置

##### `proxy status [--verbose]`

显示当前代理状态和配置。

```bash
# 基本状态
proxy status

# 详细输出
proxy status --verbose
```

**输出：**
```
Proxy Status: Disabled
Configuration:
  Protocol: socks5
  Host: 127.0.0.1
  Port: 1080
  DNS Remote: True
  Proxy URL: socks5://127.0.0.1:1080
```

#### 配置命令

##### `proxy config init`

初始化默认配置文件。

```bash
proxy config init
```

创建 `~/.proxy-cli/config.yaml` 并包含默认值。

##### `proxy config show [--verbose]`

显示当前配置。

```bash
# 基本配置
proxy config show

# 包含所有详细信息
proxy config show --verbose
```

##### `proxy config set <key> <value>`

设置配置值。

```bash
# 修改端口
proxy config set port 10808

# 修改协议
proxy config set protocol http

# 修改主机
proxy config set host 192.168.1.1

# 启用远程 DNS
proxy config set dns_remote true
```

**可用的键：**
- `protocol`：代理协议（`http`、`https`、`socks4`、`socks5`）
- `host`：代理服务器主机名或 IP
- `port`：代理服务器端口（1-65535）
- `username`：认证用户名（可选）
- `password`：认证密码（可选）
- `dns_remote`：启用远程 DNS 解析（`true`/`false`）
- `log_level`：日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`）
- `log_file`：日志文件路径

##### `proxy config validate`

验证当前配置。

```bash
proxy config validate
```

输出：
```
✓ Configuration is valid
```

或：
```
Configuration validation failed:
  ✗ Port must be between 1 and 65535
  ✗ Invalid protocol: invalid_protocol
```

##### `proxy config clear`

删除所有配置文件。

```bash
proxy config clear
```

会提示确认，然后删除：
- `~/.proxy-cli/config.yaml`
- `~/.proxy-cli/state.json`

### 文件位置

所有数据存储在 `~/.proxy-cli/` 中：

```
~/.proxy-cli/
├── config.yaml    # 代理配置
├── state.json     # 全局代理状态
└── proxy.log      # 应用日志
```

### 代理 URL 格式

FastMinato 支持多种代理 URL 格式：

```bash
# SOCKS5（默认）
socks5://127.0.0.1:1080

# SOCKS4
socks4://127.0.0.1:1080

# HTTP
http://127.0.0.1:8080

# HTTPS
https://127.0.0.1:443

# 带身份验证
socks5://username:password@127.0.0.1:1080
http://user:pass@proxy.example.com:8080
```

### 平台支持

FastMinato 支持多个平台和 shell：

**支持的平台：**
- ✅ Linux
- ✅ macOS
- ✅ Windows

**支持的 Shell：**
- ✅ Bash
- ✅ Zsh
- ✅ Fish
- ✅ PowerShell
- ✅ CMD

### 使用示例

#### 示例 1：Git 操作使用代理

```bash
# 命令包装模式
proxy run git fetch origin
proxy run git pull
proxy run git push

# 全局代理模式
eval $(proxy on)
git fetch origin
git pull
git push
eval $(proxy off)
```

#### 示例 2：包管理

```bash
# npm
proxy run npm install
proxy run npm update

# pip
proxy run pip install requests
proxy run pip install --upgrade pip

# apt (Ubuntu/Debian)
sudo proxy run apt update
sudo proxy run apt upgrade
```

#### 示例 3：网络请求

```bash
# curl
proxy run curl -I https://www.google.com

# wget
proxy run wget https://example.com/file.zip

# Python requests
proxy run python script.py
```

### 故障排除

#### 执行 `eval $(proxy on)` 后命令不使用代理

**症状**：运行了 `eval $(proxy on)` 但命令不使用代理。

**解决方案 1**：验证环境变量已设置：
```bash
env | grep -i proxy
```
你应该看到类似这样的输出：
```
HTTP_PROXY=http://127.0.0.1:xxxxx
HTTPS_PROXY=http://127.0.0.1:xxxxx
ALL_PROXY=http://127.0.0.1:xxxxx
```

**解决方案 2**：检查守护进程是否运行：
```bash
proxy status
lsof -i :<端口>  # 将 <端口> 替换为 proxy status 显示的端口
```

**解决方案 3**：清除状态并重试：
```bash
rm ~/.proxy-cli/state.json
eval $(proxy on)
```

#### "代理已启用" 错误

**症状**：运行 `proxy on` 显示"代理已启用"。

**原因**：守护进程仍在之前的会话中运行。

**解决方案**：
```bash
# 检查状态
proxy status

# 先禁用（这会停止守护进程）
eval $(proxy off)

# 然后如果需要重新启用
eval $(proxy on)
```

#### Curl 显示"无法连接到服务器"

**症状**：`curl` 失败，显示"Failed to connect to 127.0.0.1 port xxxx"。

**原因**：本地代理守护进程没有运行。

**解决方案 1**：检查守护进程是否存在：
```bash
# 查找进程
ps aux | grep "Python.*proxy-cli"

# 如果找到，记录 PID 并检查代理状态
proxy status
```

**解决方案 2**：重启代理：
```bash
eval $(proxy off)
eval $(proxy on)
```

#### 上游代理连接失败

**症状**：本地正常工作，但无法访问外部网站。

**解决方案 1**：直接测试上游代理：
```bash
# 对于 SOCKS5 代理
curl --socks5 127.0.0.1:1080 https://api.ip.sb

# 对于 HTTP 代理
curl -x http://127.0.0.1:8080 https://api.ip.sb
```

**解决方案 2**：验证上游代理正在运行：
```bash
# 检查端口是否被占用
lsof -i :1080  # 或你的上游代理端口
```

**解决方案 3**：检查配置：
```bash
proxy config validate
proxy config show
```

#### 检查日志中的错误

```bash
# 查看最近的日志
tail -50 ~/.proxy-cli/proxy.log

# 实时跟踪日志
tail -f ~/.proxy-cli/proxy.log
```

#### 常见错误避免

❌ **错误**：`proxy on`（不带 eval）
- 这只会显示命令，不会执行它们

❌ **错误**：`eval proxy on`（不带 $()）
- 这会尝试执行字符串 "proxy on"

❌ **错误**：`sudo proxy on`（带 sudo）
- 会以 root 权限创建状态文件

✅ **正确**：`eval $(proxy on)`
- 在当前 shell 中执行命令

### 贡献

欢迎贡献！请随时提交 Pull Request。

### 许可证

MIT License - 详见 LICENSE 文件
