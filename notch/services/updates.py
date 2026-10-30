"""Checks GitHub for a newer release. Only an anonymous request for the
latest release of the public repo is made; nothing about the user is sent."""

import logging
import re
import threading

import requests

from .. import REPO, VERSION

log = logging.getLogger(__name__)

API = f"https://api.github.com/repos/{REPO}/releases/latest"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": f"Ramanan/{VERSION}"}


def parse_version(tag):
    return tuple(int(n) for n in re.findall(r"\d+", tag)[:3])


class UpdateChecker(threading.Thread):
    """Emits bus.update with {"state": "checking" | "available" | "latest" | "error", ...}."""

    interval = 6 * 60 * 60
    first_delay = 20  # let startup settle before touching the network

    def __init__(self, bus):
        super().__init__(daemon=True, name="UpdateChecker")
        self.bus = bus
        self.enabled = True  # set from the UI thread when the setting changes
        self._halt = threading.Event()
        self._wake = threading.Event()

    def check_now(self):
        self._wake.set()

    def stop(self):
        self._halt.set()
        self._wake.set()

    def run(self):
        manual = self._wake.wait(self.first_delay)
        while not self._halt.is_set():
            self._wake.clear()
            if self.enabled or manual:
                self._check()
            manual = self._wake.wait(self.interval)

    def _check(self):
        self.bus.update.emit({"state": "checking"})
        try:
            r = requests.get(API, headers=HEADERS, timeout=10)
            r.raise_for_status()
            rel = r.json()
            tag = rel["tag_name"]
            exe = next((a["browser_download_url"] for a in rel.get("assets", [])
                        if a["name"].lower().endswith(".exe")), None)
            info = {"version": tag.lstrip("vV"), "page": rel["html_url"], "download": exe,
                    "notes": rel.get("body") or ""}
            newer = parse_version(tag) > parse_version(VERSION)
            self.bus.update.emit({"state": "available" if newer else "latest", **info})
        except Exception as exc:
            log.info("update check failed: %s", exc)
            self.bus.update.emit({"state": "error"})
