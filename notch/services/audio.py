"""Default output device: master volume, live peak level (drives the
visualizer) and switching the default device."""

import time

import comtypes
from pycaw.constants import DEVICE_STATE, EDataFlow, ERole
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

from .base import Poller


class Audio(Poller):
    interval = 1 / 30
    com = True

    def setup(self):
        self.level = 0.0          # read directly by the UI's animation timers
        self.device_name = ""
        self._device_id = None
        self._bound_at = 0.0
        self._volume = None
        self._bind()

    def _bind(self):
        self._bound_at = time.monotonic()
        dev = AudioUtilities.GetSpeakers()
        if dev.id == self._device_id:
            return
        self._device_id = dev.id
        self.device_name = dev.FriendlyName or "Speakers"
        self._endpoint = dev.EndpointVolume
        meter = dev._dev.Activate(IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL, None)
        self._meter = meter.QueryInterface(IAudioMeterInformation)

    def tick(self):
        if time.monotonic() - self._bound_at > 2:
            self._bind()  # follow default-device changes
        self.level = self._meter.GetPeakValue()
        vol = (round(self._endpoint.GetMasterVolumeLevelScalar(), 3), bool(self._endpoint.GetMute()))
        if vol != self._volume:
            first = self._volume is None
            self._volume = vol
            if not first:
                self.bus.volume.emit(*vol)


def output_devices():
    """[(id, name, is_default)] for active playback devices. UI thread only."""
    default = AudioUtilities.GetSpeakers().id
    devices = AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
    return [(d.id, d.FriendlyName or d.id, d.id == default) for d in devices]


def set_output_device(device_id):
    AudioUtilities.SetDefaultDevice(device_id, roles=[ERole.eConsole, ERole.eMultimedia,
                                                      ERole.eCommunications])
