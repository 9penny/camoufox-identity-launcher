from __future__ import annotations

import ipaddress
import select
import socket
import socketserver
import threading
from urllib.parse import quote, urlsplit

import requests
import socks
from camoufox.geolocation import get_geolocation


class LocationError(Exception):
    pass


class ProxyCheckError(Exception):
    pass


def proxy_for_browser(identity: dict, relay_port: int | None = None) -> dict | None:
    kind = identity.get("proxy_type", "none")
    if kind == "none":
        return None
    if relay_port is not None:
        return {"server": f"http://127.0.0.1:{relay_port}"}
    proxy = {"server": f"{kind}://{identity['host']}:{identity['port']}"}
    if identity.get("username"):
        proxy["username"] = identity["username"]
        proxy["password"] = identity.get("password", "")
    return proxy


def _requests_proxy_url(identity: dict) -> str | None:
    kind = identity.get("proxy_type", "none")
    if kind == "none":
        return None
    scheme = "socks5h" if kind == "socks5" else kind
    host = identity["host"]
    auth = ""
    if identity.get("username"):
        auth = quote(identity["username"], safe="") + ":" + quote(identity.get("password", ""), safe="") + "@"
    return f"{scheme}://{auth}{host}:{identity['port']}"


def locate(identity: dict) -> dict:
    """Query the exit IP through the selected proxy, then use Camoufox's local GeoIP DB."""
    proxy_url = _requests_proxy_url(identity)
    session = requests.Session()
    session.trust_env = False
    if proxy_url:
        session.proxies = {"http": proxy_url, "https": proxy_url}
    ip = None
    for endpoint in ("https://api.ipify.org", "https://checkip.amazonaws.com"):
        try:
            response = session.get(endpoint, timeout=8)
            response.raise_for_status()
            ip = str(ipaddress.ip_address(response.text.strip()))
            break
        except (requests.RequestException, ValueError):
            continue
    session.close()
    if ip is None:
        raise LocationError("无法通过当前代理获取出口 IP。请检查代理地址、端口、认证和网络连接，或手动填写地理参数。")
    try:
        geo = get_geolocation(ip)
        return {
            "ip": ip,
            "country": geo.locale.region or "",
            "timezone": geo.timezone,
            "language": geo.locale.as_string,
            "latitude": str(geo.latitude),
            "longitude": str(geo.longitude),
        }
    except Exception as exc:
        raise LocationError("已获取出口 IP，但 GeoIP 数据库无法定位。请检查 Camoufox GeoIP 数据，或手动填写地理参数。") from exc


def test_proxy(identity: dict) -> str:
    """Check proxy connectivity and return its public exit IP without GeoIP lookup."""
    if identity.get("proxy_type", "none") == "none":
        raise ProxyCheckError("请先选择代理类型并填写代理地址。")
    session = requests.Session()
    session.trust_env = False
    proxy_url = _requests_proxy_url(identity)
    session.proxies = {"http": proxy_url, "https": proxy_url}
    last_error = None
    try:
        for endpoint in ("https://api.ipify.org", "https://checkip.amazonaws.com"):
            try:
                response = session.get(endpoint, timeout=(6, 10))
                if response.status_code == 407:
                    raise ProxyCheckError("代理要求认证或用户名/密码不正确（HTTP 407）。")
                response.raise_for_status()
                return str(ipaddress.ip_address(response.text.strip()))
            except ProxyCheckError:
                raise
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
    finally:
        session.close()
    if isinstance(last_error, requests.exceptions.ConnectTimeout):
        message = "连接代理超时，请检查代理主机、端口和网络。"
    elif isinstance(last_error, requests.exceptions.ReadTimeout):
        message = "代理已连接，但查询出口 IP 超时；请检查代理服务或网络。"
    elif isinstance(last_error, requests.exceptions.SSLError):
        message = "通过代理建立 HTTPS 连接失败，请检查代理类型及 TLS 配置。"
    elif isinstance(last_error, requests.exceptions.ProxyError):
        detail = str(last_error).lower()
        message = ("代理认证失败，请检查用户名和密码。" if "auth" in detail or "407" in detail
                   else "无法连接代理，请检查主机、端口、类型及代理服务状态。")
    elif isinstance(last_error, requests.RequestException):
        message = "代理连接失败或出口 IP 查询服务不可用，请稍后重试。"
    else:
        message = "代理返回的出口 IP 格式无效，请检查代理服务。"
    raise ProxyCheckError(message)


class _RelayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, identity: dict):
        self.identity = identity
        super().__init__(("127.0.0.1", 0), _RelayHandler)


class _RelayHandler(socketserver.BaseRequestHandler):
    def handle(self):
        client = self.request
        client.settimeout(10)
        data = b""
        try:
            while b"\r\n\r\n" not in data and len(data) < 65536:
                part = client.recv(4096)
                if not part:
                    return
                data += part
            header, _, rest = data.partition(b"\r\n\r\n")
            lines = header.split(b"\r\n")
            method, target, version = lines[0].decode("latin1").split(" ", 2)
            if method.upper() == "CONNECT":
                parsed = urlsplit("//" + target)
                host, port = parsed.hostname, parsed.port or 443
            else:
                parsed = urlsplit(target)
                host, port = parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            if not host:
                return
            ident = self.server.identity
            upstream = socks.socksocket()
            upstream.set_proxy(socks.SOCKS5, ident["host"], int(ident["port"]), rdns=True,
                               username=ident.get("username") or None, password=ident.get("password") or None)
            upstream.settimeout(10)
            upstream.connect((host, port))
            try:
                if method.upper() == "CONNECT":
                    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    if rest:
                        upstream.sendall(rest)
                else:
                    path = parsed.path or "/"
                    if parsed.query:
                        path += "?" + parsed.query
                    filtered = [line for line in lines[1:] if not line.lower().startswith((b"proxy-authorization:", b"proxy-connection:"))]
                    upstream.sendall(f"{method} {path} {version}\r\n".encode("latin1") + b"\r\n".join(filtered) + b"\r\n\r\n" + rest)
                client.settimeout(None)
                upstream.settimeout(None)
                while True:
                    ready, _, _ = select.select([client, upstream], [], [], 30)
                    if not ready:
                        continue
                    for source in ready:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        (upstream if source is client else client).sendall(chunk)
            finally:
                upstream.close()
        except (OSError, ValueError, IndexError, socks.ProxyError):
            try:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass


class SocksAuthRelay:
    """Loopback HTTP relay because Playwright does not authenticate to SOCKS5."""

    def __init__(self, identity: dict):
        self.server = _RelayServer(identity)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
