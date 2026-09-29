"""Real Windows Camoufox smoke test; run with the project's Python venv."""

from __future__ import annotations

import ctypes
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from camoufox.sync_api import Camoufox
from launcher.browser import restore_session_cookies, snapshot_session_cookies
import launcher.storage as storage


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (b"<!doctype html><title>Camoufox smoke</title>"
                b"<button>click</button>"
                b"<p id='select'>Drag selection across these words.</p>"
                b"<div style='height:3000px'></div>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def visit(profile: Path, url: str, write: bool):
    with Camoufox(
        headless=False,
        os="windows",
        persistent_context=True,
        user_data_dir=str(profile),
        enable_cache=True,
        firefox_user_prefs={"browser.startup.page": 3},
    ) as context:
        restore_session_cookies(context, profile.name)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url)
        if write:
            page.evaluate("localStorage.setItem('identity', 'A'); document.cookie='identity=A; Max-Age=86400; path=/'; document.cookie='session_id=A; path=/';")
        page.evaluate("document.querySelector('button').addEventListener('click', () => window.testClick = true)")
        button = page.locator("button").bounding_box()
        page.mouse.click(button["x"] + button["width"] / 2, button["y"] + button["height"] / 2)
        mouse_clicked = page.evaluate("window.testClick === true")
        line = page.locator("#select").bounding_box()
        page.mouse.move(line["x"] + 5, line["y"] + line["height"] / 2)
        page.mouse.down()
        page.mouse.move(line["x"] + min(180, line["width"] - 5), line["y"] + line["height"] / 2, steps=8)
        page.mouse.up()
        interaction = page.evaluate("({selection: window.getSelection().toString()})")
        interaction["clicked"] = mouse_clicked
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(200)
        interaction["scrolled"] = page.evaluate("scrollY > 0")
        result = page.evaluate("""() => ({cookie: document.cookie,
          storage: localStorage.getItem('identity'), dpr: devicePixelRatio,
          outerWidth: outerWidth, innerWidth: innerWidth,
          screenWidth: screen.width, tz: Intl.DateTimeFormat().resolvedOptions().timeZone})""")
        result["interaction"] = interaction
        snapshot_session_cookies(context, profile.name, None)
        return result


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    with tempfile.TemporaryDirectory(prefix="camoufox-windows-smoke-") as tmp:
        base = Path(tmp)
        storage.PROFILES_DIR = base
        first = visit(base / ("a" * 32), url, True)
        repeat = visit(base / ("a" * 32), url, False)
        other = visit(base / ("b" * 32), url, False)
    server.shutdown()
    result = {
        "windows_dpi": ctypes.windll.user32.GetDpiForSystem(),
        "first": first,
        "repeat": repeat,
        "other": other,
        "persisted": repeat["storage"] == "A" and "identity=A" in repeat["cookie"],
        "session_cookie_persisted": "session_id=A" in repeat["cookie"],
        "isolated": other["storage"] is None and "identity=A" not in other["cookie"],
        "mouse_automation": all(x["interaction"]["clicked"] and x["interaction"]["selection"]
                                and x["interaction"]["scrolled"] for x in (first, repeat, other)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(result[k] for k in ("persisted", "session_cookie_persisted", "isolated", "mouse_automation")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
