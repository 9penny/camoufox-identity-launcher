"""A missing active channel must not prevent launching an installed build."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from camoufox.sync_api import Camoufox

import launcher.storage as storage
from launcher.browser import launch_options


def main():
    with tempfile.TemporaryDirectory(prefix="camoufox-stale-active-") as tmp:
        storage.PROFILES_DIR = Path(tmp)
        identity = {"id": "c" * 32, "proxy_type": "none", "ip": "",
                    "country": "US", "timezone": "America/Los_Angeles", "language": "en-US",
                    "latitude": "34.05", "longitude": "-118.27"}
        with patch("launcher.browser.get_active_path", return_value=None), \
             patch("camoufox.multiversion.get_active_path", return_value=None):
            with Camoufox(**launch_options(identity)) as context:
                assert context.pages
                timezone = context.pages[0].evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
                assert timezone == identity["timezone"], timezone
    print("Headful launch with stale active channel and manual timezone: PASS")


if __name__ == "__main__":
    main()
