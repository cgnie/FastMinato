"""
Local HTTP proxy server for proxy-cli-tool

Copyright (c) 2026 cgnie chenguang.nie@icloud.com

Licensed under the MIT License.
"""


import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional, Tuple
import socks
from proxy_cli.logger import get_logger


class LocalProxyHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler that forwards requests through an upstream proxy
    """

    def __init__(self, *args, upstream_config: dict, **kwargs):
        """
        Initialize handler with upstream proxy configuration

        Args:
            *args: Positional args for BaseHTTPRequestHandler
            upstream_config: Dictionary containing upstream proxy config
                - protocol: http, https, socks4, socks5
                - host: Proxy server hostname/IP
                - port: Proxy server port
                - username: Optional username
                - password: Optional password
                - rdns: Use remote DNS (SOCKS5 only)
            **kwargs: Keyword args for BaseHTTPRequestHandler
        """
        self.upstream_config = upstream_config
        self.logger = get_logger("proxy_cli.server")
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args) -> None:
        """
        Override to use our logger instead of stderr
        """
        self.logger.info(f"{self.address_string()} - {format % args}")

    def do_CONNECT(self) -> None:
        """
        Handle HTTP CONNECT method (HTTPS tunneling)

        Establishes a tunnel through the upstream proxy and forwards
        all data bidirectionally.
        """
        # Parse destination
        host = self.path.split(":")[0]
        port = int(self.path.split(":")[1]) if ":" in self.path else 443

        self.logger.info(f"CONNECT {host}:{port}")

        try:
            # Connect through upstream proxy
            upstream_sock = self._connect_upstream(host, port)

            # Send 200 Connection established
            self.send_response(200, "Connection Established")
            self.send_header("Proxy-Agent", "proxy-cli-tool")
            self.end_headers()

            # Start bidirectional forwarding
            self._forward_bidirectional(upstream_sock)

        except Exception as e:
            self.logger.error(f"CONNECT failed: {e}")
            if not self.headers.get("Connection", "").lower() == "close":
                self.send_error(502, "Bad Gateway")
            return

    def do_GET(self) -> None:
        """
        Handle HTTP GET requests
        """
        self._handle_http_request("GET")

    def do_POST(self) -> None:
        """
        Handle HTTP POST requests
        """
        self._handle_http_request("POST")

    def do_PUT(self) -> None:
        """
        Handle HTTP PUT requests
        """
        self._handle_http_request("PUT")

    def do_DELETE(self) -> None:
        """
        Handle HTTP DELETE requests
        """
        self._handle_http_request("DELETE")

    def do_HEAD(self) -> None:
        """
        Handle HTTP HEAD requests
        """
        self._handle_http_request("HEAD")

    def do_OPTIONS(self) -> None:
        """
        Handle HTTP OPTIONS requests
        """
        self._handle_http_request("OPTIONS")

    def _handle_http_request(self, method: str) -> None:
        """
        Handle standard HTTP request (GET, POST, etc.)

        Args:
            method: HTTP method
        """
        self.logger.info(f"{method} {self.path}")

        try:
            # Parse host and port from request
            host, port = self._parse_host_port()
            self.logger.debug(f"Parsed host: {host}:{port}")

            # Connect through upstream proxy
            self.logger.debug("Connecting to upstream proxy...")
            upstream_sock = self._connect_upstream(host, port)
            self.logger.debug("Connected to upstream proxy")

            # Build and send HTTP request
            request_line = f"{method} {self.path} HTTP/1.1\r\n"
            headers = self._build_request_headers()

            request_data = (request_line + headers + "\r\n").encode()
            self.logger.debug(f"Sending request: {len(request_data)} bytes")
            upstream_sock.sendall(request_data)
            self.logger.debug("Request sent")

            # Send request body if present
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.logger.debug(f"Sending body: {content_length} bytes")
                body = self.rfile.read(content_length)
                upstream_sock.sendall(body)
                self.logger.debug("Body sent")

            # Forward response back to client
            self.logger.debug("Receiving response...")
            self._forward_response(upstream_sock)
            self.logger.debug("Response forwarded")

            upstream_sock.close()
            self.logger.debug("Connection closed")

        except Exception as e:
            self.logger.error(f"{method} request failed: {e}", exc_info=True)
            self.send_error(502, "Bad Gateway")
            return

    def _connect_upstream(self, host: str, port: int) -> socket.socket:
        """
        Connect to destination through upstream proxy

        Args:
            host: Destination hostname/IP
            port: Destination port

        Returns:
            Connected socket

        Raises:
            ConnectionError: If connection fails
        """
        protocol = self.upstream_config.get("protocol", "socks5")
        proxy_host = self.upstream_config.get("host", "127.0.0.1")
        proxy_port = self.upstream_config.get("port", 1080)
        username = self.upstream_config.get("username")
        password = self.upstream_config.get("password")
        rdns = self.upstream_config.get("rdns", True)

        try:
            if protocol == "socks5":
                sock = socks.socksocket()
                sock.set_proxy(
                    socks.SOCKS5,
                    addr=proxy_host,
                    port=proxy_port,
                    username=username,
                    password=password,
                    rdns=rdns,
                )
                sock.connect((host, port))
                return sock

            elif protocol == "socks4":
                sock = socks.socksocket()
                sock.set_proxy(
                    socks.SOCKS4,
                    addr=proxy_host,
                    port=proxy_port,
                    username=username,
                    rdns=False,  # SOCKS4 doesn't support remote DNS
                )
                sock.connect((host, port))
                return sock

            elif protocol in ("http", "https"):
                # For HTTP proxy, we connect to the proxy server directly
                sock = socket.create_connection((proxy_host, proxy_port))

                # Send CONNECT request for HTTP/HTTPS proxy
                connect_request = f"CONNECT {host}:{port} HTTP/1.1\r\n"
                connect_request += f"Host: {host}:{port}\r\n"
                connect_request += "Proxy-Connection: keep-alive\r\n"

                if username and password:
                    import base64

                    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                    connect_request += f"Proxy-Authorization: Basic {credentials}\r\n"

                connect_request += "\r\n"
                sock.sendall(connect_request.encode())

                # Read response
                response = sock.recv(4096).decode()
                if not response.startswith("HTTP/1.1 200") and not response.startswith(
                    "HTTP/1.0 200"
                ):
                    raise ConnectionError(f"Proxy CONNECT failed: {response}")

                return sock

            else:
                raise ValueError(f"Unsupported proxy protocol: {protocol}")

        except Exception as e:
            self.logger.error(f"Upstream connection failed: {e}")
            raise ConnectionError(f"Failed to connect through upstream proxy: {e}")

    def _parse_host_port(self) -> Tuple[str, int]:
        """
        Parse hostname and port from request

        Returns:
            Tuple of (hostname, port)

        Raises:
            ValueError: If host cannot be determined
        """
        # Try to get host from headers (for absolute URIs)
        host_header = self.headers.get("Host", "")

        if host_header:
            # Parse host:port
            if ":" in host_header:
                host, port_str = host_header.split(":", 1)
                try:
                    port = int(port_str)
                except ValueError:
                    port = 80
            else:
                host = host_header
                port = 80
            return host, port

        # For relative URIs, we need to parse the path
        if self.path.startswith(("http://", "https://")):
            # Extract host from absolute URI
            from urllib.parse import urlparse

            parsed = urlparse(self.path)
            host = parsed.hostname or parsed.netloc.split(":")[0]
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return host, port

        raise ValueError(f"Cannot determine host for request: {self.path}")

    def _build_request_headers(self) -> str:
        """
        Build HTTP request headers string

        Returns:
            Headers string
        """
        headers = ""
        for header, value in self.headers.items():
            # Skip headers that should be regenerated or are proxy-specific
            if header.lower() not in ("connection", "keep-alive", "proxy-connection", "proxy-authorization"):
                headers += f"{header}: {value}\r\n"
        return headers

    def _forward_response(self, sock: socket.socket) -> None:
        """
        Forward HTTP response from upstream to client

        Args:
            sock: Upstream socket
        """
        sock.settimeout(2)  # 2 second timeout for chunked responses
        response = b""
        total_received = 0

        self.logger.debug("Starting response receive loop")

        try:
            # Receive response data
            while True:
                try:
                    self.logger.debug(f"Calling recv()...")
                    chunk = sock.recv(8192)
                    if not chunk:
                        self.logger.debug("Connection closed by upstream")
                        break
                    total_received += len(chunk)
                    self.logger.debug(f"Received chunk: {len(chunk)} bytes, total: {total_received}")
                    response += chunk

                    # Check if we have complete headers
                    if b"\r\n\r\n" in response:
                        header_end = response.index(b"\r\n\r\n")
                        headers = response[:header_end].decode("latin-1")

                        # Check for Content-Length
                        content_length = None
                        for line in headers.split("\r\n"):
                            if line.lower().startswith("content-length:"):
                                try:
                                    content_length = int(line.split(":")[1].strip())
                                    self.logger.debug(f"Content-Length: {content_length}")
                                except ValueError:
                                    pass
                                break

                        if content_length is not None:
                            # We have Content-Length, check if body is complete
                            body = response[header_end + 4 :]
                            if len(body) >= content_length:
                                self.logger.debug("Complete response received (Content-Length)")
                                break
                        else:
                            # No Content-Length, check for Transfer-Encoding or Connection
                            if "transfer-encoding: chunked" in headers.lower():
                                self.logger.debug("Chunked encoding, waiting for connection close")
                            elif "connection: close" in headers.lower():
                                self.logger.debug("Connection: close, waiting for close")

                except socket.timeout:
                    # Timeout - use what we have
                    self.logger.warning("Response receive timed out after 5s")
                    break

        except Exception as e:
            self.logger.error(f"Error in response receive loop: {e}", exc_info=True)

        self.logger.debug(f"Receive loop finished, total: {total_received} bytes")

        # Parse and send response
        try:
            if not response:
                raise ValueError("Empty response")

            header_end = response.index(b"\r\n\r\n")
            headers = response[:header_end].decode("latin-1")
            body = response[header_end + 4 :]

            # Parse status line
            first_line = headers.split("\r\n")[0]
            parts = first_line.split(" ", 2)
            if len(parts) >= 3:
                status_code = parts[1]
                status_text = parts[2] if len(parts) > 2 else "OK"
            else:
                status_code = "200"
                status_text = "OK"

            self.logger.debug(f"Sending response: {status_code} {status_text}")

            # Send response
            self.send_response(int(status_code), status_text)

            # Parse and send headers (skip ones that are auto-generated)
            for line in headers.split("\r\n")[1:]:
                if ":" in line:
                    header_name, header_value = line.split(":", 1)
                    # Skip headers that BaseHTTPRequestHandler will set
                    if header_name.strip().lower() not in ("server", "date", "connection"):
                        self.send_header(header_name.strip(), header_value.strip())

            self.end_headers()

            # Send body
            if body:
                self.wfile.write(body)
            self.wfile.flush()

            self.logger.debug(f"Response forwarded: {len(response)} bytes")

        except (ValueError, IndexError) as e:
            # If parsing fails, send raw response
            self.logger.error(f"Response parsing failed: {e}, sending raw", exc_info=True)
            try:
                self.wfile.write(response)
                self.wfile.flush()
            except:
                pass

    def _forward_bidirectional(self, sock: socket.socket) -> None:
        """
        Forward data bidirectionally between client and upstream

        Args:
            sock: Upstream socket
        """
        # Set both sockets to non-blocking
        sock.settimeout(None)
        self.connection.settimeout(None)

        def forward(source, destination):
            """Forward data from source to destination"""
            try:
                while True:
                    data = source.recv(4096)
                    if not data:
                        break
                    destination.sendall(data)
            except:
                pass
            finally:
                try:
                    destination.shutdown(socket.SHUT_WR)
                except:
                    pass

        # Start forwarding threads
        client_to_upstream = threading.Thread(
            target=forward, args=(self.connection, sock), daemon=True
        )
        upstream_to_client = threading.Thread(
            target=forward, args=(sock, self.connection), daemon=True
        )

        client_to_upstream.start()
        upstream_to_client.start()

        # Wait for both threads to complete
        client_to_upstream.join()
        upstream_to_client.join()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """
    Threaded HTTP server for handling multiple connections concurrently
    """

    daemon_threads = True
    allow_reuse_address = True


class LocalProxyServer:
    """
    Local HTTP proxy server that forwards requests through an upstream proxy
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        upstream_config: Optional[dict] = None,
    ):
        """
        Initialize local proxy server

        Args:
            host: Listen address (default: 127.0.0.1)
            port: Listen port (0 for random available port)
            upstream_config: Upstream proxy configuration
                - protocol: http, https, socks4, socks5
                - host: Proxy server hostname/IP
                - port: Proxy server port
                - username: Optional username
                - password: Optional password
                - rdns: Use remote DNS (SOCKS5 only)
        """
        self.host = host
        self.port = port
        self.upstream_config = upstream_config or {}
        self.server: Optional[ThreadedHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.logger = get_logger("proxy_cli.server")

    def start(self) -> int:
        """
        Start the proxy server

        Returns:
            The actual port the server is listening on

        Raises:
            OSError: If server fails to start
        """
        if self.server is not None:
            raise RuntimeError("Server is already running")

        # Create server
        def handler(*args, **kwargs):
            LocalProxyHandler(*args, upstream_config=self.upstream_config, **kwargs)

        self.server = ThreadedHTTPServer((self.host, self.port), handler)
        actual_port = self.server.server_port

        self.logger.info(f"Starting proxy server on {self.host}:{actual_port}")

        # Start server in background thread
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

        return actual_port

    def stop(self) -> None:
        """
        Stop the proxy server
        """
        if self.server is None:
            return

        self.logger.info("Stopping proxy server")

        self.server.shutdown()
        self.server.server_close()

        if self.server_thread:
            self.server_thread.join(timeout=5)

        self.server = None
        self.server_thread = None

    def is_running(self) -> bool:
        """
        Check if server is running

        Returns:
            True if server is running, False otherwise
        """
        return self.server is not None

    @property
    def address(self) -> Optional[Tuple[str, int]]:
        """
        Get server address

        Returns:
            Tuple of (host, port) or None if not running
        """
        if self.server is None:
            return None
        return (self.host, self.server.server_port)
