"""Now-playing info and transport controls via the Windows global media
session API (works with Spotify, browsers, Media Player, VLC, ...)."""

import asyncio
import logging
import threading
import time

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.storage.streams import DataReader

log = logging.getLogger(__name__)

TICKS_PER_SECOND = 10_000_000


def _pretty_app(app_id):
    # "Spotify.exe", "MSEdge", "Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic"
    if "!" in app_id:
        # packaged app: the entry point after "!" is the readable part
        name = app_id.split("!")[-1].split(".")[-1]
    else:
        name = app_id.rsplit("\\", 1)[-1]
        if name.lower().endswith(".exe"):
            name = name[:-4]
    known = {"msedge": "Edge", "chrome": "Chrome", "spotify": "Spotify", "zunemusic": "Media Player",
             "308046b0af4a39cb": "Firefox", "6f193ccc56814779": "Firefox", "vlc": "VLC"}
    return known.get(name.lower(), name)


class MediaService(threading.Thread):
    poll_interval = 0.4

    def __init__(self, bus):
        super().__init__(daemon=True, name="MediaService")
        self.bus = bus
        self.loop = asyncio.new_event_loop()
        self._halt = False
        self._manager = None
        self._track_key = None
        self._art = b""
        self._last = None
        # Some browser players (Apple Music web) stream the whole queue as one media
        # element, so on auto-advance the timeline keeps counting from the previous
        # songs and its "duration" is the buffered queue. We remember where in that
        # stream the track began and report time from there, with no known length.
        self._offset = None
        # Artwork lags the title the same way: the previous track's image, refused for a few seconds.
        self._stale_art = b""
        self._stale_art_until = 0.0

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    def stop(self):
        self._halt = True

    def command(self, name, arg=None):
        """Thread-safe: "toggle", "next", "prev", "seek" (arg = seconds)."""
        if self._manager is not None:
            asyncio.run_coroutine_threadsafe(self._command(name, arg), self.loop)

    async def _main(self):
        try:
            self._manager = await SessionManager.request_async()
        except Exception:
            log.exception("media sessions unavailable")
            return
        while not self._halt:
            try:
                await self._poll()
            except OSError as exc:
                # The player closed mid-call (RPC failed); the next poll recovers.
                log.info("media session went away: %s", exc)
                await asyncio.sleep(1)
            except Exception:
                log.exception("media poll failed")
                await asyncio.sleep(2)
            await asyncio.sleep(self.poll_interval)

    async def _poll(self):
        session = self._manager.get_current_session()
        if session is None:
            snap = {"active": False}
        else:
            props = await session.try_get_media_properties_async()
            info = session.get_playback_info()
            timeline = session.get_timeline_properties()
            key = (session.source_app_user_model_id, props.title, props.artist)
            playing = info.playback_status == PlaybackStatus.PLAYING
            updated = timeline.last_updated_time
            valid_stamp = updated.year > 1601
            updated_ts = updated.timestamp() if valid_stamp else time.time()
            position = (timeline.position - timeline.start_time).total_seconds()
            duration = (timeline.end_time - timeline.start_time).total_seconds()
            if duration <= 0:
                duration = (timeline.max_seek_time - timeline.min_seek_time).total_seconds()

            now = time.time()
            live = position + (max(now - updated_ts, 0) if playing else 0)
            if key != self._track_key:
                same_app = self._track_key is not None and self._track_key[0] == key[0]
                self._offset = live if same_app and valid_stamp and live > 5 else None
                self._track_key = key
                prev_art = self._art
                self._art = await self._read_thumbnail(props.thumbnail)
                if same_app and prev_art and self._art == prev_art:
                    self._stale_art, self._stale_art_until = prev_art, now + 6
                    self._art = b""
            elif not self._art and props.thumbnail is not None:
                # Some players publish the artwork a moment after the title.
                art = await self._read_thumbnail(props.thumbnail)
                if art != self._stale_art or time.time() > self._stale_art_until:
                    self._art, self._stale_art = art, b""

            if self._offset is not None and live < self._offset - 2:
                self._offset = None  # timeline restarted: the player now reports this track itself
            if self._offset is not None:
                position, duration = position - self._offset, 0.0

            controls = info.controls
            snap = {
                "active": True,
                "key": key,
                "app": _pretty_app(session.source_app_user_model_id),
                "title": props.title or "",
                "artist": props.artist or props.album_artist or "",
                "album": props.album_title or "",
                "playing": playing,
                "position": position,
                "duration": duration,
                "updated_at": updated_ts,
                "elapsed_only": self._offset is not None,
                "can_seek": bool(controls.is_playback_position_enabled),
                "can_next": bool(controls.is_next_enabled),
                "can_prev": bool(controls.is_previous_enabled),
                "art": self._art,
            }
        if snap != self._last:
            self._last = snap
            self.bus.media.emit(snap)

    async def _read_thumbnail(self, ref):
        if ref is None:
            return b""
        try:
            stream = await ref.open_read_async()
            size = stream.size
            if not size:
                return b""
            reader = DataReader(stream.get_input_stream_at(0))
            await reader.load_async(size)
            data = bytearray(size)
            reader.read_bytes(data)
            return bytes(data)
        except Exception:
            log.exception("could not read album art")
            return b""

    async def _command(self, name, arg):
        session = self._manager.get_current_session()
        if session is None:
            return
        try:
            if name == "toggle":
                await session.try_toggle_play_pause_async()
            elif name == "next":
                await session.try_skip_next_async()
            elif name == "prev":
                await session.try_skip_previous_async()
            elif name == "seek":
                await session.try_change_playback_position_async(int(max(arg, 0) * TICKS_PER_SECOND))
            await asyncio.sleep(0.15)
            await self._poll()
        except Exception:
            log.exception("media command %s failed", name)


def current_position(snap):
    """Position interpolated from the last timeline update."""
    if not snap.get("active"):
        return 0.0
    pos = snap["position"]
    if snap["playing"]:
        pos += max(time.time() - snap["updated_at"], 0)
    duration = snap["duration"]
    pos = max(pos, 0.0)
    return min(pos, duration) if duration > 0 else pos
