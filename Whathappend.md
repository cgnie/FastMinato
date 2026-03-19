# FastMinato Execution Flow: `proxy run git pull`

This document provides a detailed analysis of what happens when you execute `proxy run git pull`, including the complete call chain, data flow, and timing.

---

## Table of Contents

- [Execution Flow Diagram](#execution-flow-diagram)
- [Detailed Step Analysis](#detailed-step-analysis)
- [Complete Data Flow](#complete-data-flow)
- [Timeline](#timeline)
- [Key Design Principles](#key-design-principles)
- [Troubleshooting Flow](#troubleshooting-flow)
- [Summary](#summary)

---

## Execution Flow Diagram

```
User Input: proxy run git pull
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 1. CLI Entry Point: cli.py:38-73 run()                      │
│    - Parse command: ["git", "pull"]                         │
│    - Setup logging                                          │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. ProxyManager.run_command() - manager.py:68-156          │
│    - Determine upstream proxy config                        │
│    - Start LocalProxyServer on dynamic port                 │
│    - Build environment with proxy variables                 │
│    - Execute git pull subprocess                           │
│    - Cleanup resources                                      │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. LocalProxyServer.start() - server.py:497-523            │
│    - Create ThreadedHTTPServer                             │
│    - Listen on 127.0.0.1:random_port                       │
│    - Start server in background thread                     │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. EnvInjector.build_env() - env_injector.py:44-75         │
│    - Copy current environment                              │
│    - Set HTTP_PROXY, HTTPS_PROXY, etc.                     │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. subprocess.Popen() - Execute git pull                   │
│    - Spawn git process with modified env                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. LocalProxyServer handles HTTP requests                   │
│    - Receive request from git                               │
│    - Parse target host and port                            │
│    - Connect through upstream proxy                        │
│    - Forward request/response bidirectionally              │
└─────────────────────────────────────────────────────────────┘
```

---

## Detailed Step Analysis

### Step 1: CLI Entry Point

**File: [cli.py:38-73](src/proxy_cli/cli.py#L38-L73)**

```python
@main.command()
@click.argument("command", nargs=-1, required=True)  # command = ("git", "pull")
@click.option("--proxy", "-p", help="Override proxy URL")
@click.option("--verbose", "-v", is_flag=True)
def run(command: tuple, proxy: str, verbose: bool) -> None:
    # 1. Setup logging
    logger = setup_logger("proxy_cli", level="debug" if verbose else "warning", verbose=verbose)

    # 2. Create ProxyManager
    manager = ProxyManager()

    # 3. Call run_command (KEY STEP!)
    exit_code = manager.run_command(
        list(command),  # ["git", "pull"]
        proxy_url=proxy,
        verbose=verbose
    )

    # 4. Exit with git's exit code
    sys.exit(exit_code)
```

**What happens**:
- Click parses the command: `command = ("git", "pull")`
- Creates a `ProxyManager` instance to coordinate the operation
- Delegates to `ProxyManager.run_command()` for the actual work

---

### Step 2: ProxyManager.run_command()

**File: [manager.py:68-156](src/proxy_cli/manager.py#L68-L156)**

This is the core logic with 5 phases:

#### Phase 2.1: Determine Upstream Proxy Config

**Code: [manager.py:95-106](src/proxy_cli/manager.py#L95-L106)**

```python
# If user specified --proxy parameter
if proxy_url:
    upstream_config = self._parse_proxy_url(proxy_url)  # Parse URL
else:
    # Otherwise, load from config file
    upstream_config = {
        "protocol": self.config.protocol,  # e.g., "socks5"
        "host": self.config.host,          # e.g., "127.0.0.1"
        "port": self.config.port,          # e.g., 1080
        "username": self.config.username,
        "password": self.config.password,
        "rdns": self.config.dns_remote,
    }
```

**What happens**:
- Loads proxy configuration from `~/.proxy-cli/config.yaml`
- Or uses override URL provided via `--proxy` flag
- Result: `upstream_config` dict with connection details

---

#### Phase 2.2: Start Local HTTP Proxy Server

**Code: [manager.py:108-114](src/proxy_cli/manager.py#L108-L114)**

```python
self._server = LocalProxyServer(
    host="127.0.0.1",      # Local listen address
    port=0,                # port=0 means auto-assign available port
    upstream_config=upstream_config  # Upstream proxy config
)

# Start server and return actual assigned port
self._server_port = self._server.start()
# Example: self._server_port = 54321
```

**This calls: LocalProxyServer.start()**

**File: [server.py:497-523](src/proxy_cli/server.py#L497-L523)**

```python
def start(self) -> int:
    # Create HTTP server
    def handler(*args, **kwargs):
        LocalProxyHandler(*args, upstream_config=self.upstream_config, **kwargs)

    self.server = ThreadedHTTPServer((self.host, self.port), handler)
    actual_port = self.server.server_port  # Get actual port number

    # Run server in background thread
    self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    self.server_thread.start()

    return actual_port  # Return port number
```

**What happens**:
- Creates an HTTP server listening on `127.0.0.1:RANDOM_PORT`
- Server runs in a daemon thread (non-blocking)
- Returns the actual port number (e.g., 54321)
- Server is now ready to accept connections

---

#### Phase 2.3: Inject Environment Variables

**Code: [manager.py:116-118](src/proxy_cli/manager.py#L116-L118)**

```python
local_proxy_url = f"http://127.0.0.1:{self._server_port}"
# Example: "http://127.0.0.1:54321"

env = self.env_injector.build_env(proxy_url=local_proxy_url)
```

**This calls: EnvInjector.build_env()**

**File: [env_injector.py:44-75](src/proxy_cli/env_injector.py#L44-L75)**

```python
def build_env(self, env: Optional[Dict[str, str]] = None, proxy_url: Optional[str] = None) -> Dict[str, str]:
    # Copy current environment variables
    if env is None:
        env = os.environ.copy()
    else:
        env = env.copy()

    url = proxy_url or self.proxy_url  # "http://127.0.0.1:54321"

    # Inject all proxy environment variables
    for var in self.PROXY_VARS:  # HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, etc.
        env[var] = url

    return env
```

**Environment variables set**:

```bash
HTTP_PROXY=http://127.0.0.1:54321
HTTPS_PROXY=http://127.0.0.1:54321
ALL_PROXY=http://127.0.0.1:54321
http_proxy=http://127.0.0.1:54321
https_proxy=http://127.0.0.1:54321
all_proxy=http://127.0.0.1:54321
FTP_PROXY=http://127.0.0.1:54321
ftp_proxy=http://127.0.0.1:54321
RSYNC_PROXY=http://127.0.0.1:54321
rsync_proxy=http://127.0.0.1:54321
```

**What happens**:
- Copies all current environment variables
- Adds/overrides proxy-related variables to point to local proxy server
- When git runs, it will read these variables and use the proxy

---

#### Phase 2.4: Execute Command

**Code: [manager.py:134-142](src/proxy_cli/manager.py#L134-L142)**

```python
# Execute git pull with injected proxy environment variables
process = subprocess.Popen(command, env=env)
# command = ["git", "pull"]
# env = {all env vars, including HTTP_PROXY=http://127.0.0.1:54321, ...}

# Wait for command to complete
exit_code = process.wait()
# Returns git's exit code (0 = success)
```

**What happens**:
- Spawns a new `git pull` process with modified environment
- Git reads `HTTPS_PROXY` and `HTTP_PROXY` from environment
- Git directs all network traffic through `127.0.0.1:54321`
- Main process waits for git to complete

---

#### Phase 2.5: Cleanup Resources

**Code: [manager.py:154-156](src/proxy_cli/manager.py#L154-L156)**

```python
finally:
    # Always cleanup, regardless of success or failure
    self._cleanup()
```

**_cleanup() method**: [manager.py:393-407](src/proxy_cli/manager.py#L393-L407)

```python
def _cleanup(self) -> None:
    if self._server is not None:
        if self._server.is_running():
            self._server.stop()  # Stop HTTP server
        self._server = None
        self._server_port = None
```

**What happens**:
- Stops the local HTTP proxy server
- Closes the listening port
- Cleans up resources
- No daemon processes left behind

---

### Step 3: Git Uses Proxy

When `git pull` executes:

1. Git checks environment variables `HTTP_PROXY` and `HTTPS_PROXY`
2. Finds the value: `http://127.0.0.1:54321`
3. Git initiates HTTP request to `127.0.0.1:54321`
4. All git network operations go through this local proxy

---

### Step 4: LocalProxyServer Handles Request

When Git's request arrives at `127.0.0.1:54321`:

#### Phase 4.1: HTTP Request Processing

**File: [server.py:80-163](src/proxy_cli/server.py#L80-L163)**

```python
def do_GET(self) -> None:  # Example: GET https://github.com/...
    self._handle_http_request("GET")

def _handle_http_request(self, method: str) -> None:
    # 1. Parse target host and port
    host, port = self._parse_host_port()
    # Example: host="github.com", port=443

    # 2. Connect to target through upstream proxy
    upstream_sock = self._connect_upstream(host, port)
```

#### Phase 4.2: Connect Through Upstream Proxy

**File: [server.py:165-244](src/proxy_cli/server.py#L165-L244)**

```python
def _connect_upstream(self, host: str, port: int) -> socket.socket:
    protocol = self.upstream_config.get("protocol", "socks5")  # "socks5"
    proxy_host = self.upstream_config.get("host", "127.0.0.1")  # "127.0.0.1"
    proxy_port = self.upstream_config.get("port", 1080)  # 1080

    if protocol == "socks5":
        sock = socks.socksocket()
        sock.set_proxy(
            socks.SOCKS5,
            addr=proxy_host,     # 127.0.0.1
            port=proxy_port,     # 1080
            username=username,
            password=password,
        )
        # Connect to github.com:443 through SOCKS5 proxy at 127.0.0.1:1080
        sock.connect((host, port))  # ("github.com", 443)
        return sock
```

**What happens**:
- Establishes connection through upstream proxy (V2Ray/XRay)
- SOCKS5 handshake with upstream proxy
- Returns connected socket for data transfer

#### Phase 4.3: Forward Request and Response

```python
# Send original request to upstream proxy
upstream_sock.sendall(request_data)

# Receive response and forward back to git
self._forward_response(upstream_sock)
```

**For CONNECT method (HTTPS)**: [server.py:49-78](src/proxy_cli/server.py#L49-L78)

```python
def do_CONNECT(self) -> None:
    # Parse destination
    host = self.path.split(":")[0]
    port = int(self.path.split(":")[1]) if ":" in self.path else 443

    # Connect through upstream proxy
    upstream_sock = self._connect_upstream(host, port)

    # Send 200 Connection established
    self.send_response(200, "Connection Established")
    self.end_headers()

    # Start bidirectional forwarding
    self._forward_bidirectional(upstream_sock)
```

**What happens**:
- Data flows bidirectionally: Git ↔ LocalProxyServer ↔ Upstream Proxy
- LocalProxyServer acts as a transparent middleman
- No data modification, pure forwarding

---

## Complete Data Flow

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Application                        │
│                       git pull                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ Reads HTTPS_PROXY
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              Environment Variables                          │
│         HTTPS_PROXY=http://127.0.0.1:54321                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ HTTP Request to 127.0.0.1:54321
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              LocalProxyServer (FastMinato)                  │
│                 127.0.0.1:54321                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  LocalProxyHandler                                  │   │
│  │  - Receives request from git                       │   │
│  │  - Parses target: github.com:443                   │   │
│  │  - Connects via upstream proxy                     │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ SOCKS5 Connect to 127.0.0.1:1080
                         ↓
┌─────────────────────────────────────────────────────────────┐
│               Upstream Proxy (V2Ray/XRay)                   │
│                   127.0.0.1:1080                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  SOCKS5 Inbound                                    │   │
│  │  - Accepts connection from LocalProxyServer        │   │
│  │  - Routes to vmess outbound                        │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ vmess protocol over KCP + DTLS
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              Remote Proxy Server                            │
│            104.168.170.134:8080                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  vmess Server                                      │   │
│  │  - Authenticates via UUID                          │   │
│  │  - Decrypts and forwards to target                 │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ HTTPS Request to github.com
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                   Target Website                            │
│                    github.com                               │
└─────────────────────────────────────────────────────────────┘
```

### Data Packet Journey

**Request path (git → github.com)**:

```
1. git process creates HTTPS request to github.com

2. Request routed to 127.0.0.1:54321 (HTTPS_PROXY)

3. LocalProxyServer receives request

4. LocalProxyServer parses target: github.com:443

5. LocalProxyServer connects to 127.0.0.1:1080 (SOCKS5)

6. V2Ray accepts SOCKS5 connection

7. V2Ray routes through vmess outbound

8. V2Ray connects to 104.168.170.134:8080 (KCP + DTLS)

9. Remote server decrypts vmess and forwards to github.com

10. github.com receives request
```

**Response path (github.com → git)**:

```
1. github.com sends response

2. Remote server receives and encrypts with vmess

3. V2Ray receives vmess data via KCP

4. V2Ray decrypts and sends to SOCKS5 client

5. LocalProxyServer receives from SOCKS5

6. LocalProxyServer forwards to git

7. git process receives response
```

---

## Timeline

### Sequential Events

| Time | Event | Component | Description |
|------|-------|-----------|-------------|
| **T0** | User executes command | Shell | `proxy run git pull` |
| **T1** | CLI parsing | Click | Parse command: `["git", "pull"]` |
| **T2** | Create manager | ProxyManager | `ProxyManager.__init__()` |
| **T3** | Load config | ConfigManager | Read `~/.proxy-cli/config.yaml` |
| **T4** | Start server | LocalProxyServer | Bind to `127.0.0.1:RANDOM_PORT` |
| **T5** | Server ready | ThreadedHTTPServer | Listening on port (e.g., 54321) |
| **T6** | Inject env vars | EnvInjector | Set `HTTP_PROXY=http://127.0.0.1:54321` |
| **T7** | Spawn git | subprocess.Popen | Start `git pull` with modified env |
| **T8** | Git reads proxy | git process | Git reads `HTTPS_PROXY` |
| **T9** | Git makes request | git process | Connect to `127.0.0.1:54321` |
| **T10** | Accept connection | LocalProxyServer | Accept git's connection |
| **T11** | Parse request | LocalProxyHandler | Extract target: `github.com:443` |
| **T12** | Connect upstream | _connect_upstream | SOCKS5 connect to `127.0.0.1:1080` |
| **T13** | SOCKS5 handshake | V2Ray/XRay | Authenticate and route |
| **T14** | vmess connection | V2Ray/XRay | Connect to remote server |
| **T15** | Data transfer | All components | Git ↔ LocalProxyServer ← SOCKS5 → V2Ray → Remote |
| **T16** | Git completes | git process | `git pull` finishes |
| **T17** | Return exit code | ProxyManager | Get git's exit code |
| **T18** | Cleanup | ProxyManager | Stop LocalProxyServer |
| **T19** | Exit | CLI | `sys.exit(exit_code)` |

### Concurrent Operations

During **T15-T16** (data transfer phase):

```
┌─ LocalProxyServer Thread ─┐    ┌─ Git Process ─┐    ┌─ V2Ray Process ─┐
│                           │    │                │    │                  │
│  Receive from git →       │───→│  Sending       │    │                  │
│  Forward to upstream →    │───→─────────────────→───│  Forwarding      │
│                           │    │                │    │  to remote       │
│  Receive from upstream ←  │←────────────────────←───│  Receiving       │
│  Forward to git ←         │←───│  Receiving     │    │  from remote     │
│                           │    │                │    │                  │
└───────────────────────────┘    └────────────────┘    └──────────────────┘
```

**Key points**:
- LocalProxyServer runs in daemon thread (non-blocking)
- Git process runs independently
- V2Ray handles concurrent connections
- Data flows bidirectionally through all layers

---

## Key Design Principles

### 1. Two-Layer Proxy Architecture

```
Application → Local Proxy Server → Upstream Proxy → Remote Server
              (HTTP)               (SOCKS5/HTTP)     (vmess/SS/etc.)
```

**Why?**
- **Separation of concerns**: FastMinato handles UX, V2Ray handles protocols
- **Flexibility**: Can switch upstream proxies without changing application
- **Stability**: Leverages mature V2Ray implementation

### 2. Ephemeral Server Model

**For `proxy run`**:
- Server starts before command
- Server stops after command
- Clean state for each execution
- No leftover processes

**Benefits**:
- Isolated executions
- No state pollution
- Predictable cleanup

### 3. Environment Variable Injection

**Standard proxy variables**:
```bash
HTTP_PROXY, HTTPS_PROXY, ALL_PROXY
http_proxy, https_proxy, all_proxy
FTP_PROXY, RSYNC_PROXY, ...
```

**Benefits**:
- Works with any proxy-aware application
- No code modification needed
- Standard Unix convention

### 4. Transparent Forwarding

**LocalProxyServer does NOT**:
- Modify request headers
- Inspect payload
- Cache responses
- Transform data

**It ONLY**:
- Forward requests
- Forward responses
- Maintain bidirectional data flow

**Benefits**:
- Zero application modification
- Protocol agnostic
- Minimal overhead

---

## Troubleshooting Flow

### If `proxy run git pull` fails:

#### 1. Check Local Proxy Server

```bash
# Is the server running?
proxy status

# Can you connect to the local port?
curl -v http://127.0.0.1:<PORT>  # Use port from proxy status
```

#### 2. Check Upstream Proxy

```bash
# Test V2Ray directly
curl --socks5 127.0.0.1:1080 https://api.ip.sb

# Is V2Ray running?
lsof -i :1080  # Should show V2Ray process
```

#### 3. Check Environment Variables

```bash
# In the git process
env | grep -i proxy
# Should show: HTTPS_PROXY=http://127.0.0.1:<PORT>
```

#### 4. Check Logs

```bash
# View FastMinato logs
tail -50 ~/.proxy-cli/proxy.log

# Enable verbose mode
proxy run --verbose git pull
```

---

## Summary

### Execution Flow Recap

1. **CLI Entry**: `cli.py:run()` parses command
2. **Manager Coordination**: `ProxyManager.run_command()` orchestrates
3. **Server Startup**: `LocalProxyServer.start()` creates local HTTP proxy
4. **Env Injection**: `EnvInjector.build_env()` sets proxy variables
5. **Command Execution**: `subprocess.Popen()` spawns git with proxy
6. **Request Handling**: `LocalProxyServer` forwards to upstream proxy
7. **Data Transfer**: Bidirectional flow through all layers
8. **Cleanup**: Server stops, resources released

### The "Last Mile" Promise

**FastMinato's responsibility**:
- ✅ Provide convenient local HTTP proxy
- ✅ Manage environment variables
- ✅ Command wrapping (`proxy run`)
- ✅ Global proxy mode (`proxy on/off`)
- ✅ Clean lifecycle management

**V2Ray/XRay's responsibility**:
- ✅ Connect to remote servers
- ✅ Implement vmess/SS/Trojan protocols
- ✅ Handle complex transport (KCP, WebSocket, gRPC)
- ✅ Encryption and authentication

**Clear separation**: Each tool does what it does best.

---

**End of Document**

For questions or issues, please visit: [GitHub Issues](https://github.com/cgnie/FastMinato/issues)

---

---

# FastMinato 执行流程：`proxy run git pull`

本文档详细说明执行 `proxy run git pull` 时发生的所有操作，包括完整的调用链、数据流和时间线。

---

## 目录

- [执行流程图](#执行流程图)
- [详细步骤分析](#详细步骤分析)
- [完整数据流](#完整数据流)
- [时间线](#时间线)
- [关键设计原则](#关键设计原则)
- [故障排除流程](#故障排除流程)
- [总结](#总结)

---

## 执行流程图

```
用户输入: proxy run git pull
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 1. CLI 入口点: cli.py:38-73 run()                           │
│    - 解析命令: ["git", "pull"]                              │
│    - 设置日志                                               │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. ProxyManager.run_command() - manager.py:68-156          │
│    核心协调逻辑                                             │
│    - 确定上游代理配置                                       │
│    - 在动态端口启动本地代理服务器                           │
│    - 构建包含代理变量的环境变量                             │
│    - 执行 git pull 子进程                                   │
│    - 清理资源                                               │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. LocalProxyServer.start() - server.py:497-523            │
│    启动本地 HTTP 代理服务器                                 │
│    - 创建线程化 HTTP 服务器                                 │
│    - 监听 127.0.0.1:随机端口                               │
│    - 在后台线程中启动服务器                                 │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. EnvInjector.build_env() - env_injector.py:44-75         │
│    注入代理环境变量                                         │
│    - 复制当前环境变量                                       │
│    - 设置所有代理环境变量                                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. subprocess.Popen() - 执行 git pull                       │
│    - 使用修改后的环境变量启动 git 进程                      │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. LocalProxyServer 处理 HTTP 请求                           │
│    - 接收来自 git 的请求                                       │
│    - 解析目标主机和端口                                        │
│    - 通过上游代理连接                                          │
│    - 双向转发请求和响应                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 详细步骤分析

### 第 1 步：CLI 入口点

**文件：[cli.py:38-73](src/proxy_cli/cli.py#L38-L73)**

```python
@main.command()
@click.argument("command", nargs=-1, required=True)  # command = ("git", "pull")
@click.option("--proxy", "-p", help="Override proxy URL")
@click.option("--verbose", "-v", is_flag=True)
def run(command: tuple, proxy: str, verbose: bool) -> None:
    # 1. 设置日志
    logger = setup_logger("proxy_cli", level="debug" if verbose else "warning", verbose=verbose)

    # 2. 创建 ProxyManager
    manager = ProxyManager()

    # 3. 调用 run_command（关键步骤！）
    exit_code = manager.run_command(
        list(command),  # ["git", "pull"]
        proxy_url=proxy,
        verbose=verbose
    )

    # 4. 使用 git 的退出码退出
    sys.exit(exit_code)
```

**发生了什么**:
- Click 解析命令：`command = ("git", "pull")`
- 创建 `ProxyManager` 实例来协调操作
- 委托给 `ProxyManager.run_command()` 执行实际工作

---

### 第 2 步：ProxyManager.run_command()

**文件：[manager.py:68-156](src/proxy_cli/manager.py#L68-L156)**

这是核心逻辑，分为 5 个阶段：

#### 阶段 2.1：确定上游代理配置

**代码：[manager.py:95-106](src/proxy_cli/manager.py#L95-L106)**

```python
# 如果用户指定了 --proxy 参数
if proxy_url:
    upstream_config = self._parse_proxy_url(proxy_url)  # 解析 URL
else:
    # 否则从配置文件读取
    upstream_config = {
        "protocol": self.config.protocol,  # 例如 "socks5"
        "host": self.config.host,          # 例如 "127.0.0.1"
        "port": self.config.port,          # 例如 1080
        "username": self.config.username,
        "password": self.config.password,
        "rdns": self.config.dns_remote,
    }
```

**发生了什么**:
- 从 `~/.proxy-cli/config.yaml` 加载代理配置
- 或使用 `--proxy` 标志提供的覆盖 URL
- 结果：包含连接信息的 `upstream_config` 字典

---

#### 阶段 2.2：启动本地 HTTP 代理服务器

**代码：[manager.py:108-114](src/proxy_cli/manager.py#L108-L114)**

```python
self._server = LocalProxyServer(
    host="127.0.0.1",      # 本地监听地址
    port=0,                # port=0 表示自动分配可用端口
    upstream_config=upstream_config  # 上游代理配置
)

# 启动服务器并返回实际分配的端口
self._server_port = self._server.start()
# 例如: self._server_port = 54321
```

**调用：LocalProxyServer.start()**

**文件：[server.py:497-523](src/proxy_cli/server.py#L497-L523)**

```python
def start(self) -> int:
    # 创建 HTTP 服务器
    def handler(*args, **kwargs):
        LocalProxyHandler(*args, upstream_config=self.upstream_config, **kwargs)

    self.server = ThreadedHTTPServer((self.host, self.port), handler)
    actual_port = self.server.server_port  # 获取实际端口号

    # 在后台线程中运行服务器
    self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    self.server_thread.start()

    return actual_port  # 返回端口号
```

**发生了什么**:
- 创建一个监听在 `127.0.0.1:随机端口` 的 HTTP 服务器
- 服务器在守护线程中运行（非阻塞）
- 返回实际端口号（例如 54321）
- 服务器现在已准备好接受连接

---

#### 阶段 2.3：注入代理环境变量

**代码：[manager.py:116-118](src/proxy_cli/manager.py#L116-L118)**

```python
local_proxy_url = f"http://127.0.0.1:{self._server_port}"
# 例如: "http://127.0.0.1:54321"

env = self.env_injector.build_env(proxy_url=local_proxy_url)
```

**调用：EnvInjector.build_env()**

**文件：[env_injector.py:44-75](src/proxy_cli/env_injector.py#L44-L75)**

```python
def build_env(self, env: Optional[Dict[str, str]] = None, proxy_url: Optional[str] = None) -> Dict[str, str]:
    # 复制当前环境变量
    if env is None:
        env = os.environ.copy()
    else:
        env = env.copy()

    url = proxy_url or self.proxy_url  # "http://127.0.0.1:54321"

    # 注入所有代理环境变量
    for var in self.PROXY_VARS:  # HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, etc.
        env[var] = url

    return env
```

**设置的环境变量**:

```bash
HTTP_PROXY=http://127.0.0.1:54321
HTTPS_PROXY=http://127.0.0.1:54321
ALL_PROXY=http://127.0.0.1:54321
http_proxy=http://127.0.0.1:54321
https_proxy=http://127.0.0.1:54321
all_proxy=http://127.0.0.1:54321
FTP_PROXY=http://127.0.0.1:54321
ftp_proxy=http://127.0.0.1:54321
RSYNC_PROXY=http://127.0.0.1:54321
rsync_proxy=http://127.0.0.1:54321
```

**发生了什么**:
- 复制所有当前环境变量
- 添加/覆盖代理相关变量，使其指向本地代理服务器
- 当 git 运行时，它会读取这些变量并使用代理

---

#### 阶段 2.4：执行命令

**代码：[manager.py:134-142](src/proxy_cli/manager.py#L134-L142)**

```python
# 使用注入了代理环境变量的 env 来执行 git pull
process = subprocess.Popen(command, env=env)
# command = ["git", "pull"]
# env = {所有环境变量，包括 HTTP_PROXY=http://127.0.0.1:54321, ...}

# 等待命令完成
exit_code = process.wait()
# 返回 git 的退出码（0 = 成功）
```

**发生了什么**:
- 启动一个新的 `git pull` 进程，使用修改后的环境
- Git 从环境变量读取 `HTTPS_PROXY` 和 `HTTP_PROXY`
- Git 将所有网络流量定向到 `127.0.0.1:54321`
- 主进程等待 git 完成

---

#### 阶段 2.5：清理资源

**代码：[manager.py:154-156](src/proxy_cli/manager.py#L154-L156)**

```python
finally:
    # 无论成功失败，都会停止本地代理服务器
    self._cleanup()
```

**_cleanup() 方法**：[manager.py:393-407](src/proxy_cli/manager.py#L393-L407)

```python
def _cleanup(self) -> None:
    if self._server is not None:
        if self._server.is_running():
            self._server.stop()  # 停止 HTTP 服务器
        self._server = None
        self._server_port = None
```

**发生了什么**:
- 停止本地 HTTP 代理服务器
- 关闭监听端口
- 清理资源
- 不留下守护进程

---

### 第 3 步：Git 使用代理

当 `git pull` 执行时：

1. Git 检查环境变量 `HTTP_PROXY` 和 `HTTPS_PROXY`
2. 发现值：`http://127.0.0.1:54321`
3. Git 发起 HTTP 请求到 `127.0.0.1:54321`
4. 所有 git 网络操作都通过这个本地代理

---

### 第 4 步：本地代理服务器处理请求

当 Git 的请求到达 `127.0.0.1:54321` 时：

#### 阶段 4.1：HTTP 请求处理

**文件：[server.py:80-163](src/proxy_cli/server.py#L80-L163)**

```python
def do_GET(self) -> None:  # 例如: GET https://github.com/...
    self._handle_http_request("GET")

def _handle_http_request(self, method: str) -> None:
    # 1. 解析目标主机和端口
    host, port = self._parse_host_port()
    # 例如: host="github.com", port=443

    # 2. 通过上游代理连接目标
    upstream_sock = self._connect_upstream(host, port)
```

#### 阶段 4.2：连接上游代理

**文件：[server.py:165-244](src/proxy_cli/server.py#L165-L244)**

```python
def _connect_upstream(self, host: str, port: int) -> socket.socket:
    protocol = self.upstream_config.get("protocol", "socks5")  # "socks5"
    proxy_host = self.upstream_config.get("host", "127.0.0.1")  # "127.0.0.1"
    proxy_port = self.upstream_config.get("port", 1080)  # 1080

    if protocol == "socks5":
        sock = socks.socksocket()
        sock.set_proxy(
            socks.SOCKS5,
            addr=proxy_host,     # 127.0.0.1
            port=proxy_port,     # 1080
            username=username,
            password=password,
        )
        # 通过 127.0.0.1:1080 的 SOCKS5 代理连接到 github.com:443
        sock.connect((host, port))  # ("github.com", 443)
        return sock
```

**发生了什么**:
- 通过上游代理（V2Ray/XRay）建立连接
- 与上游代理进行 SOCKS5 握手
- 返回已连接的套接字用于数据传输

#### 阶段 4.3：转发请求和响应

```python
# 发送原始请求到上游代理
upstream_sock.sendall(request_data)

# 接收响应并转发回 git
self._forward_response(upstream_sock)
```

**对于 CONNECT 方法（HTTPS）**：[server.py:49-78](src/proxy_cli/server.py#L49-L78)

```python
def do_CONNECT(self) -> None:
    # 解析目标
    host = self.path.split(":")[0]
    port = int(self.path.split(":")[1]) if ":" in self.path else 443

    # 通过上游代理连接
    upstream_sock = self._connect_upstream(host, port)

    # 发送 200 连接建立
    self.send_response(200, "Connection Established")
    self.end_headers()

    # 开始双向转发
    self._forward_bidirectional(upstream_sock)
```

**发生了什么**:
- 数据双向流动：Git ↔ LocalProxyServer ↔ 上游代理
- LocalProxyServer 充当透明的中间人
- 不修改数据，纯粹转发

---

## 完整数据流

### 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                     用户应用程序                            │
│                       git pull                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ 读取 HTTPS_PROXY
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              环境变量                                       │
│         HTTPS_PROXY=http://127.0.0.1:54321                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ HTTP 请求到 127.0.0.1:54321
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              LocalProxyServer (FastMinato)                  │
│                 127.0.0.1:54321                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  LocalProxyHandler                                  │   │
│  │  - 接收来自 git 的请求                             │   │
│  │  - 解析目标: github.com:443                        │   │
│  │  - 通过上游代理连接                                │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ SOCKS5 连接到 127.0.0.1:1080
                         ↓
┌─────────────────────────────────────────────────────────────┐
│               上游代理 (V2Ray/XRay)                         │
│                   127.0.0.1:1080                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  SOCKS5 入站                                        │   │
│  │  - 接收来自 LocalProxyServer 的连接                │   │
│  │  - 路由到 vmess 出站                                │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ vmess 协议通过 KCP + DTLS
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              远程代理服务器                                 │
│            104.168.170.134:8080                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  vmess 服务器                                       │   │
│  │  - 通过 UUID 认证                                  │   │
│  │  - 解密并转发到目标                                │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ HTTPS 请求到 github.com
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                   目标网站                                  │
│                    github.com                               │
└─────────────────────────────────────────────────────────────┘
```

### 数据包旅程

**请求路径（git → github.com）**：

```
1. git 进程创建到 github.com 的 HTTPS 请求

2. 请求路由到 127.0.0.1:54321 (HTTPS_PROXY)

3. LocalProxyServer 接收请求

4. LocalProxyServer 解析目标: github.com:443

5. LocalProxyServer 连接到 127.0.0.1:1080 (SOCKS5)

6. V2Ray 接受 SOCKS5 连接

7. V2Ray 通过 vmess 出站路由

8. V2Ray 连接到 104.168.170.134:8080 (KCP + DTLS)

9. 远程服务器解密 vmess 并转发到 github.com

10. github.com 接收请求
```

**响应路径（github.com → git）**：

```
1. github.com 发送响应

2. 远程服务器接收并用 vmess 加密

3. V2Ray 通过 KCP 接收 vmess 数据

4. V2Ray 解密并发送到 SOCKS5 客户端

5. LocalProxyServer 从 SOCKS5 接收

6. LocalProxyServer 转发到 git

7. git 进程接收响应
```

---

## 时间线

### 事件序列

| 时间 | 事件 | 组件 | 描述 |
|------|-------|-----------|-------------|
| **T0** | 用户执行命令 | Shell | `proxy run git pull` |
| **T1** | CLI 解析 | Click | 解析命令：`["git", "pull"]` |
| **T2** | 创建管理器 | ProxyManager | `ProxyManager.__init__()` |
| **T3** | 加载配置 | ConfigManager | 读取 `~/.proxy-cli/config.yaml` |
| **T4** | 启动服务器 | LocalProxyServer | 绑定到 `127.0.0.1:随机端口` |
| **T5** | 服务器就绪 | ThreadedHTTPServer | 监听端口（例如 54321） |
| **T6** | 注入环境变量 | EnvInjector | 设置 `HTTP_PROXY=http://127.0.0.1:54321` |
| **T7** | 启动 git | subprocess.Popen | 使用修改后的环境启动 `git pull` |
| **T8** | Git 读取代理 | git 进程 | Git 读取 `HTTPS_PROXY` |
| **T9** | Git 发起请求 | git 进程 | 连接到 `127.0.0.1:54321` |
| **T10** | 接受连接 | LocalProxyServer | 接受 git 的连接 |
| **T11** | 解析请求 | LocalProxyHandler | 提取目标：`github.com:443` |
| **T12** | 连接上游 | _connect_upstream | SOCKS5 连接到 `127.0.0.1:1080` |
| **T13** | SOCKS5 握手 | V2Ray/XRay | 认证和路由 |
| **T14** | vmess 连接 | V2Ray/XRay | 连接到远程服务器 |
| **T15** | 数据传输 | 所有组件 | Git ↔ LocalProxyServer ← SOCKS5 → V2Ray → 远程 |
| **T16** | Git 完成 | git 进程 | `git pull` 完成 |
| **T17** | 返回退出码 | ProxyManager | 获取 git 的退出码 |
| **T18** | 清理 | ProxyManager | 停止 LocalProxyServer |
| **T19** | 退出 | CLI | `sys.exit(exit_code)` |

### 并发操作

在 **T15-T16**（数据传输阶段）：

```
┌─ LocalProxyServer 线程 ─┐    ┌─ Git 进程 ─┐    ┌─ V2Ray 进程 ─┐
│                           │    │                │    │                  │
│  从 git 接收 →           │───→│  发送中       │    │                  │
│  转发到上游 →            │───→─────────────────→───│  转发中          │
│                           │    │                │    │  到远程服务器    │
│  从上游接收 ←            │←────────────────────←───│  接收中          │
│  转发到 git ←            │←───│  接收中       │    │  从远程服务器    │
│                           │    │                │    │                  │
└───────────────────────────┘    └────────────────┘    └──────────────────┘
```

**关键点**:
- LocalProxyServer 在守护线程中运行（非阻塞）
- Git 进程独立运行
- V2Ray 处理并发连接
- 数据在所有层中双向流动

---

## 关键设计原则

### 1. 双层代理架构

```
应用程序 → 本地代理服务器 → 上游代理 → 远程服务器
              (HTTP)               (SOCKS5/HTTP)     (vmess/SS/etc.)
```

**为什么？**
- **职责分离**：FastMinato 处理用户体验，V2Ray 处理协议
- **灵活性**：可以切换上游代理而不改变应用程序
- **稳定性**：利用成熟的 V2Ray 实现

### 2. 临时服务器模型

**对于 `proxy run`**:
- 服务器在命令前启动
- 服务器在命令后停止
- 每次执行都是干净状态
- 不留下遗留进程

**优点**:
- 隔离的执行
- 不污染状态
- 可预测的清理

### 3. 环境变量注入

**标准代理变量**:
```bash
HTTP_PROXY, HTTPS_PROXY, ALL_PROXY
http_proxy, https_proxy, all_proxy
FTP_PROXY, RSYNC_PROXY, ...
```

**优点**:
- 适用于任何支持代理的应用程序
- 不需要修改代码
- 标准 Unix 约定

### 4. 透明转发

**LocalProxyServer 不**:
- 修改请求头
- 检查负载
- 缓存响应
- 转换数据

**只**:
- 转发请求
- 转发响应
- 维护双向数据流

**优点**:
- 零应用程序修改
- 与协议无关
- 最小开销

---

## 故障排除流程

### 如果 `proxy run git pull` 失败：

#### 1. 检查本地代理服务器

```bash
# 服务器是否在运行？
proxy status

# 能连接到本地端口吗？
curl -v http://127.0.0.1:<端口>  # 使用 proxy status 显示的端口
```

#### 2. 检查上游代理

```bash
# 直接测试 V2Ray
curl --socks5 127.0.0.1:1080 https://api.ip.sb

# V2Ray 是否在运行？
lsof -i :1080  # 应该显示 V2Ray 进程
```

#### 3. 检查环境变量

```bash
# 在 git 进程中
env | grep -i proxy
# 应该显示: HTTPS_PROXY=http://127.0.0.1:<端口>
```

#### 4. 检查日志

```bash
# 查看 FastMinato 日志
tail -50 ~/.proxy-cli/proxy.log

# 启用详细模式
proxy run --verbose git pull
```

---

## 总结

### 执行流程回顾

1. **CLI 入口**：`cli.py:run()` 解析命令
2. **管理器协调**：`ProxyManager.run_command()` 协调
3. **服务器启动**：`LocalProxyServer.start()` 创建本地 HTTP 代理
4. **环境注入**：`EnvInjector.build_env()` 设置代理变量
5. **命令执行**：`subprocess.Popen()` 使用代理启动 git
6. **请求处理**：`LocalProxyServer` 转发到上游代理
7. **数据传输**：通过所有层双向流动
8. **清理**：服务器停止，释放资源

### "最后一公里"承诺

**FastMinato 的职责**:
- ✅ 提供便捷的本地 HTTP 代理
- ✅ 管理环境变量
- ✅ 命令包装（`proxy run`）
- ✅ 全局代理模式（`proxy on/off`）
- ✅ 干净的生命周期管理

**V2Ray/XRay 的职责**:
- ✅ 连接远程服务器
- ✅ 实现 vmess/SS/Trojan 协议
- ✅ 处理复杂传输（KCP、WebSocket、gRPC）
- ✅ 加密和认证

**清晰分工**：每个工具都做它最擅长的事情。

---

**文档结束**

如有问题或建议，请访问：[GitHub Issues](https://github.com/cgnie/FastMinato/issues)
