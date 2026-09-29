"""Check that stored IP geodata reaches a real headful Camoufox page."""

import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from camoufox.sync_api import Camoufox

import launcher.storage as storage
from launcher.browser import launch_options
from launcher.network import locate


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><title>geo smoke</title>"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    geo = locate({"proxy_type": "none"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="camoufox-geo-smoke-") as tmp:
            storage.PROFILES_DIR = Path(tmp)
            identity = {"id": "a" * 32, "proxy_type": "none", **geo}
            with Camoufox(**launch_options(identity)) as context:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                observed = page.evaluate("""async () => ({
                  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                  language: navigator.language,
                  position: await new Promise((resolve, reject) =>
                    navigator.geolocation.getCurrentPosition(
                      p => resolve([p.coords.latitude, p.coords.longitude]),
                      e => reject(new Error(e.message)), {timeout: 7000}))
                })""")
            assert observed["timezone"] == geo["timezone"], observed
            assert observed["language"].lower() == geo["language"].lower(), observed
            assert abs(observed["position"][0] - float(geo["latitude"])) < 0.01, observed
            assert abs(observed["position"][1] - float(geo["longitude"])) < 0.01, observed
            print(f"Headful timezone, language, geolocation: PASS ({geo['country']})")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
