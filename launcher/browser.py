from __future__ import annotations

import ipaddress
import json
import logging
import os
import threading
from contextlib import nullcontext
from logging.handlers import RotatingFileHandler

from camoufox.sync_api import Camoufox
from camoufox.multiversion import get_active_path, list_installed
from camoufox.pkgman import launch_path
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .network import SocksAuthRelay, proxy_for_browser
from .storage import LOGS_DIR, ensure_dirs, profile_dir


def make_logger() -> logging.Logger:
    ensure_dirs()
    logger = logging.getLogger("camoufox_identity_launcher")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(LOGS_DIR / "launcher.log", maxBytes=1_000_000,
                                      backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def safe_error(exc: Exception, identity: dict) -> str:
    message = str(exc).replace("\r", " ").replace("\n", " ")
    for secret in (identity.get("password", ""), identity.get("username", "")):
        if secret:
            message = message.replace(secret, "***")
    return message[:350] or type(exc).__name__


def installed_browser() -> tuple[str, int]:
    """Resolve a real Windows installation without trusting a stale channel selection."""
    selected = selected_browser()
    return launch_path(selected.path), int(selected.version.version.split(".", 1)[0])


def selected_browser():
    versions = list_installed()
    if not versions:
        raise RuntimeError("未找到 Camoufox Windows 浏览器。请运行 setup.ps1 安装。")
    active = get_active_path()
    selected = next((v for v in versions if v.path == active), None)
    if selected is None:
        selected = next((v for v in versions if v.repo_name == "official" and not v.is_prerelease), None)
    if selected is None:
        selected = versions[0]
    return selected


def browser_version_label() -> str:
    selected = selected_browser()
    return f"Camoufox {selected.version.version} · {selected.repo_name}"


def launch_options(identity: dict, relay_port: int | None = None) -> dict:
    executable, firefox_major = installed_browser()
    config = {
        "timezone": identity["timezone"],
        "locale:region": identity["country"].upper(),
        "geolocation:latitude": float(identity["latitude"]),
        "geolocation:longitude": float(identity["longitude"]),
        # Camoufox reads the highlighter toggle from its injected config.
        "showcursor": False,
    }
    ip = identity.get("ip", "")
    try:
        parsed_ip = ipaddress.ip_address(ip)
        config["webrtc:ipv4" if parsed_ip.version == 4 else "webrtc:ipv6"] = ip
    except ValueError:
        pass
    opts = {
        "headless": False,
        "os": "windows",
        "persistent_context": True,
        "user_data_dir": str(profile_dir(identity["id"])),
        "enable_cache": True,
        "locale": identity["language"],
        "timezone_id": identity["timezone"],
        "config": config,
        "block_webrtc": not bool(ip),
        "i_know_what_im_doing": True,
        "executable_path": executable,
        "ff_version": firefox_major,
        # Keep tab close buttons visible even when tabs become narrow, and
        # allow closing the final tab without closing the whole browser.
        "firefox_user_prefs": {
            "browser.tabs.tabClipWidth": 1,
            "browser.tabs.closeWindowWithLastTab": False,
        },
    }
    proxy = proxy_for_browser(identity, relay_port)
    if proxy:
        opts["proxy"] = proxy
    return opts


def restore_session_cookies(context, identity_id: str) -> None:
    path = profile_dir(identity_id) / "session_cookies.json"
    if not path.exists():
        return
    cookies = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cookies, list):
        raise ValueError("会话 Cookie 数据格式错误")
    for cookie in cookies:
        cookie.pop("expires", None)
    if cookies:
        context.add_cookies(cookies)


def snapshot_session_cookies(context, identity_id: str, previous: str | None) -> str:
    cookies = [cookie for cookie in context.cookies() if cookie.get("expires", -1) == -1]
    content = json.dumps(cookies, ensure_ascii=False, sort_keys=True)
    if content != previous:
        path = profile_dir(identity_id) / "session_cookies.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)
    return content


def session_pages_path(identity_id: str):
    return profile_dir(identity_id) / "session_pages.json"


def load_session_pages(identity_id: str) -> list[str]:
    path = session_pages_path(identity_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [url for url in data[:100]
            if isinstance(url, str) and len(url) <= 8192
            and url.startswith(("http://", "https://"))]


def snapshot_session_pages(context, identity_id: str, previous: str | None) -> str:
    urls = []
    try:
        for page in context.pages[:100]:
            try:
                url = page.url
            except Exception:
                continue
            if isinstance(url, str) and len(url) <= 8192 and url.startswith(("http://", "https://")):
                urls.append(url)
    except Exception:
        return previous or "[]"
    content = json.dumps(urls, ensure_ascii=False)
    if content != previous:
        path = session_pages_path(identity_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)
    return content


def restore_session_pages(context, identity_id: str, logger: logging.Logger) -> None:
    urls = load_session_pages(identity_id)
    pages = context.pages
    if not urls:
        if not pages:
            context.new_page()
        return
    for index, url in enumerate(urls):
        try:
            page = pages[index] if index < len(pages) else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as exc:
            logger.info("identity %s could not restore tab %s (%s)", identity_id,
                        index + 1, type(exc).__name__)


class BrowserManager:
    def __init__(self, notify):
        self.notify = notify
        self.logger = make_logger()
        self.workers: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self.lock = threading.Lock()

    def running(self, identity_id: str) -> bool:
        with self.lock:
            return identity_id in self.workers

    def start(self, identity: dict) -> None:
        identity = dict(identity)
        identity_id = identity["id"]
        with self.lock:
            if identity_id in self.workers:
                return
            stop = threading.Event()
            thread = threading.Thread(target=self._run, args=(identity, stop), daemon=True)
            self.workers[identity_id] = (thread, stop)
            thread.start()
        self.notify(identity_id, "starting", "")

    def stop(self, identity_id: str) -> None:
        with self.lock:
            worker = self.workers.get(identity_id)
        if worker:
            worker[1].set()
            self.notify(identity_id, "stopping", "")

    def stop_all(self) -> None:
        with self.lock:
            ids = list(self.workers)
        for identity_id in ids:
            self.stop(identity_id)

    def any_running(self) -> bool:
        with self.lock:
            return bool(self.workers)

    def _run(self, identity: dict, stop: threading.Event) -> None:
        identity_id = identity["id"]
        try:
            use_relay = identity.get("proxy_type") == "socks5" and bool(identity.get("username"))
            relay_cm = SocksAuthRelay(identity) if use_relay else nullcontext()
            with relay_cm as relay:
                options = launch_options(identity, relay.port if use_relay else None)
                with Camoufox(**options) as context:
                    restore_session_cookies(context, identity_id)
                    restore_session_pages(context, identity_id, self.logger)
                    self.logger.info("identity %s started", identity_id)
                    self.notify(identity_id, "running", "")
                    cookie_snapshot = None
                    page_snapshot = None
                    while not stop.is_set():
                        try:
                            context.wait_for_event("close", timeout=500)
                            snapshot_session_pages(context, identity_id, page_snapshot)
                            break
                        except PlaywrightTimeout:
                            cookie_snapshot = snapshot_session_cookies(context, identity_id, cookie_snapshot)
                            page_snapshot = snapshot_session_pages(context, identity_id, page_snapshot)
                    if stop.is_set():
                        snapshot_session_cookies(context, identity_id, cookie_snapshot)
                        snapshot_session_pages(context, identity_id, page_snapshot)
            self.logger.info("identity %s stopped", identity_id)
        except Exception as exc:
            self.logger.error("identity %s failed (%s)", identity_id, type(exc).__name__)
            self.notify(identity_id, "error", safe_error(exc, identity))
        finally:
            with self.lock:
                self.workers.pop(identity_id, None)
            self.notify(identity_id, "stopped", "")
