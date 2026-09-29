"""Exercise the real Tk app and browser worker without touching saved identities."""

import tempfile
import time
import tkinter as tk
from pathlib import Path

import launcher.browser as browser_module
import launcher.storage as storage
from launcher.gui import App
from launcher.network import locate


def main():
    location = locate({"proxy_type": "none"})
    with tempfile.TemporaryDirectory(prefix="camoufox-launcher-smoke-") as tmp:
        base = Path(tmp)
        storage.APP_DIR = base
        storage.CONFIG_PATH = base / "identities.json"
        storage.PROFILES_DIR = base / "profiles"
        storage.LOGS_DIR = base / "logs"
        browser_module.LOGS_DIR = storage.LOGS_DIR
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        app.show_edit(None)
        app.vars["name"].set("Smoke Test")
        for key in ("country", "timezone", "language", "latitude", "longitude"):
            app.vars[key].set(location[key])
        app.ip = location["ip"]
        app._save()
        assert len(app.identities) == 1, app.edit_hint.cget("text")
        identity_id = app.identities[0]["id"]
        assert storage.profile_dir(identity_id).parent == base / "profiles"
        app._start(identity_id)
        deadline = time.monotonic() + 35
        while app.states.get(identity_id) != "running" and time.monotonic() < deadline:
            root.update()
            time.sleep(0.1)
        assert app.states.get(identity_id) == "running", app.list_hint.cget("text")
        app._stop(identity_id)
        deadline = time.monotonic() + 15
        while app.browser.running(identity_id) and time.monotonic() < deadline:
            root.update()
            time.sleep(0.1)
        assert not app.browser.running(identity_id)
        assert storage.profile_dir(identity_id).exists()
        assert storage.load_identities()[0]["name"] == "Smoke Test"
        for handler in app.browser.logger.handlers[:]:
            handler.close()
            app.browser.logger.removeHandler(handler)
        root.destroy()
        print("GUI save, real headful browser start/stop, profile retention: PASS")


if __name__ == "__main__":
    main()
