"""Synced lyrics from LRCLIB (https://lrclib.net), a free, keyless lyrics
database. Only the track title, artist, album and duration are sent."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

import requests

log = logging.getLogger(__name__)

API = "https://lrclib.net/api"
HEADERS = {"User-Agent": "Ramanan/1.0 (Windows notch agent)"}
STAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(text):
    lines = []
    for raw in text.splitlines():
        stamps = STAMP.findall(raw)
        content = STAMP.sub("", raw).strip()
        for minutes, seconds in stamps:
            lines.append((int(minutes) * 60 + float(seconds), content))
    return sorted(lines)


def line_at(lines, position):
    current = ""
    for t, text in lines:
        if t > position:
            break
        current = text
    return current


class Lyrics:
    def __init__(self, bus):
        self.bus = bus
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lyrics")
        self._cache = {}

    def fetch(self, snap):
        key = snap["key"]
        if key in self._cache:
            self.bus.lyrics.emit(key, self._cache[key])
            return
        self._pool.submit(self._fetch, key, snap["title"], snap["artist"], snap["album"], snap["duration"])

    def _fetch(self, key, title, artist, album, duration):
        lines = None
        try:
            params = {"track_name": title, "artist_name": artist}
            if album:
                params["album_name"] = album
            if duration > 0:
                params["duration"] = round(duration)
            r = requests.get(f"{API}/get", params=params, headers=HEADERS, timeout=6)
            synced = r.json().get("syncedLyrics") if r.ok else None
            if not synced:
                r = requests.get(f"{API}/search", params={"track_name": title, "artist_name": artist},
                                 headers=HEADERS, timeout=6)
                hits = r.json() if r.ok else []
                synced = next((h["syncedLyrics"] for h in hits if h.get("syncedLyrics")), None)
            if synced:
                lines = parse_lrc(synced)
            self._cache[key] = lines  # only cache real answers, so offline lookups retry
        except Exception as exc:
            log.info("lyrics lookup failed for %s - %s: %s", artist, title, exc)
        self.bus.lyrics.emit(key, lines)

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
