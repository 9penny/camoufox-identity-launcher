"""Verify authenticated SOCKS5 works through the local browser relay."""

import socketserver
import tempfile
import threading
import warnings

import requests
from camoufox.sync_api import Camoufox

from launcher.network import SocksAuthRelay


def exact(sock, size):
    data = b""
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise EOFError
        data += part
    return data


class SocksHandler(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        version, count = exact(sock, 2)
        assert version == 5 and 2 in exact(sock, count)
        sock.sendall(b"\x05\x02")
        version, length = exact(sock, 2)
        username = exact(sock, length)
        password = exact(sock, exact(sock, 1)[0])
        assert (version, username, password) == (1, b"tester", b"secret")
        sock.sendall(b"\x01\x00")
        version, command, _reserved, address_type = exact(sock, 4)
        assert version == 5 and command == 1
        if address_type == 3:
            exact(sock, exact(sock, 1)[0])
        elif address_type == 1:
            exact(sock, 4)
        else:
            exact(sock, 16)
        exact(sock, 2)
        sock.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
        data = b""
        while b"\r\n\r\n" not in data:
            data += sock.recv(4096)
        body = b"proxy-ok"
        sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\nConnection: close\r\n\r\n" + body)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    server = Server(("127.0.0.1", 0), SocksHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    identity = {"host": "127.0.0.1", "port": str(server.server_address[1]),
                "username": "tester", "password": "secret"}
    try:
        with SocksAuthRelay(identity) as relay:
            response = requests.get("http://example.test/", proxies={"http": f"http://127.0.0.1:{relay.port}"}, timeout=10)
            assert response.status_code == 200 and response.text == "proxy-ok"
            with tempfile.TemporaryDirectory(prefix="camoufox-socks-smoke-") as profile:
                with warnings.catch_warnings():
                    # Camoufox's proxy warning checks an exact "geolocation" key,
                    # although its documented config uses geolocation:latitude/longitude.
                    warnings.filterwarnings("ignore", message="When using a proxy, it is heavily recommended")
                    with Camoufox(headless=False, os="windows", persistent_context=True,
                                   user_data_dir=profile, proxy={"server": f"http://127.0.0.1:{relay.port}"},
                                   config={"geolocation:latitude": 0.0, "geolocation:longitude": 0.0,
                                           "timezone": "Etc/UTC", "locale:region": "US"}, locale="en-US",
                                   i_know_what_im_doing=True) as context:
                        page = context.pages[0] if context.pages else context.new_page()
                        page.goto("http://example.test/", wait_until="domcontentloaded", timeout=15000)
                        assert page.locator("body").inner_text() == "proxy-ok"
        print("Authenticated SOCKS5 relay and headful Camoufox traffic: PASS")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
