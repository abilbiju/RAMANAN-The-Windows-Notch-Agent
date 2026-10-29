import logging
import threading

log = logging.getLogger(__name__)


class Poller(threading.Thread):
    """Background thread that calls tick() every `interval` seconds.

    If setup() raises, the feature is treated as unsupported on this machine
    and the thread exits quietly.
    """

    interval = 1.0
    com = False  # initialise COM on this thread (needed for pycaw / WMI)

    def __init__(self, bus):
        super().__init__(daemon=True, name=type(self).__name__)
        self.bus = bus
        self._halt = threading.Event()

    def setup(self):
        pass

    def tick(self):
        raise NotImplementedError

    def run(self):
        if self.com:
            import pythoncom
            pythoncom.CoInitialize()
        try:
            self.setup()
        except Exception as exc:
            log.info("%s unavailable: %s", self.name, exc)
            return
        while not self._halt.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("%s tick failed", self.name)
                self._halt.wait(5)
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()
