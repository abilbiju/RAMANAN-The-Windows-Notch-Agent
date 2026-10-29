"""Tracks in-progress browser downloads by watching the Downloads folder for
temporary files (.crdownload for Chrome/Edge/Brave, .part for Firefox, ...).

Browsers don't expose the total size in the temp file, so we report bytes
received and speed, not a percentage."""

import os
import time
from pathlib import Path

from .base import Poller
from .system import downloads_dir

TEMP_EXTENSIONS = (".crdownload", ".part", ".partial", ".opdownload", ".download")
STALE_AFTER = 15  # seconds without growth before a leftover temp file is ignored


def _display_name(path):
    name = Path(path).name
    for ext in TEMP_EXTENSIONS:
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    if name.lower().startswith("unconfirmed "):
        return "Downloading…"
    return name or "Downloading…"


class Downloads(Poller):
    interval = 0.7

    def setup(self):
        self.folder = downloads_dir()
        if not self.folder.is_dir():
            raise RuntimeError(f"{self.folder} not found")
        self._active = {}
        self._had_live = False

    def _scan(self):
        found = {}
        with os.scandir(self.folder) as it:
            for entry in it:
                if entry.name.lower().endswith(TEMP_EXTENSIONS) and entry.is_file():
                    try:
                        st = entry.stat()
                        found[entry.path] = (st.st_size, st.st_mtime)
                    except OSError:
                        pass
        return found

    def _final_file(self, temp_path, started):
        stem = Path(temp_path)
        for ext in TEMP_EXTENSIONS:
            if stem.name.lower().endswith(ext):
                candidate = stem.with_name(stem.name[: -len(ext)])
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return candidate
        # Chrome renames "Unconfirmed 1234.crdownload" to the real name, so
        # fall back to the newest regular file written since the download began.
        newest, newest_time = None, started - 1
        with os.scandir(self.folder) as it:
            for entry in it:
                if entry.is_file() and not entry.name.lower().endswith(TEMP_EXTENSIONS):
                    mtime = entry.stat().st_mtime
                    if mtime > newest_time:
                        newest, newest_time = Path(entry.path), mtime
        return newest

    def tick(self):
        now = time.monotonic()
        found = self._scan()
        for path, (size, mtime) in found.items():
            d = self._active.get(path)
            if d is None:
                fresh = time.time() - mtime < STALE_AFTER
                self._active[path] = {"id": path, "name": _display_name(path), "size": size,
                                      "speed": 0.0, "t": now, "started": time.time(),
                                      "grown_at": now if fresh else now - STALE_AFTER}
                continue
            dt = now - d["t"]
            if dt > 0:
                instant = max(size - d["size"], 0) / dt
                d["speed"] = 0.6 * d["speed"] + 0.4 * instant
            if size != d["size"]:
                d["grown_at"] = now
            d["size"], d["t"] = size, now

        gone = [p for p in self._active if p not in found]
        for path in gone:
            d = self._active.pop(path)
            if now - d["grown_at"] < STALE_AFTER:
                final = self._final_file(path, d["started"])
                if final is not None:
                    self.bus.download_done.emit(final.name, str(final))

        live = [dict(d) for d in self._active.values() if now - d["grown_at"] < STALE_AFTER]
        if live or gone or self._had_live:
            self.bus.downloads.emit(live)
        self._had_live = bool(live)
