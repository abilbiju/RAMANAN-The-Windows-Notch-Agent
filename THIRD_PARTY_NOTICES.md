# Third-party notices

Ramanan is released under the MIT License (see `LICENSE`). The source code and the
prebuilt `Ramanan.exe` use the open-source components below; the exe bundles them.
Each one remains under its own license.

| Component | Version | License | Project |
|---|---|---|---|
| Python | 3.12 | PSF License | https://www.python.org |
| Qt for Python (PySide6, shiboken6) | 6.12.0 | LGPL-3.0 | https://doc.qt.io/qtforpython |
| Qt 6 (bundled with PySide6) | 6.12 | LGPL-3.0 | https://www.qt.io |
| FFmpeg (Qt Multimedia backend, bundled with PySide6) | — | LGPL-2.1-or-later | https://ffmpeg.org |
| pycaw | 20260927 | MIT | https://github.com/AndreMiras/pycaw |
| comtypes | 1.4.17 | MIT | https://github.com/enthought/comtypes |
| pywin32 | 312 | PSF License | https://github.com/mhammond/pywin32 |
| psutil | 7.2.2 | BSD-3-Clause | https://github.com/giampaolo/psutil |
| requests | 2.34.2 | Apache-2.0 | https://github.com/psf/requests |
| urllib3 | 2.8.0 | MIT | https://github.com/urllib3/urllib3 |
| certifi | 2026.10.23 | MPL-2.0 | https://github.com/certifi/python-certifi |
| charset-normalizer | 3.5.2 | MIT | https://github.com/jawah/charset_normalizer |
| idna | 3.20 | BSD-3-Clause | https://github.com/kjd/idna |
| PyWinRT (`winrt-*` packages) | 4.0.3 | MIT | https://github.com/pywinrt/pywinrt |
| PyInstaller (bootloader in `Ramanan.exe`) | 6.22.3 | GPL-2.0 with bootloader exception | https://pyinstaller.org |

## Qt / PySide6 and FFmpeg (LGPL)

`Ramanan.exe` contains unmodified Qt, PySide6 and FFmpeg libraries, which are licensed
under the GNU Lesser General Public License. Their source code is available from the
project links above. You may replace these libraries with your own builds: the complete
source of Ramanan is in this repository, and `build.ps1` rebuilds the exe against
whichever PySide6 is installed.

## PyInstaller

The PyInstaller bootloader is GPL-licensed with an exception that allows it to be used
in executables under any license, so it doesn't affect Ramanan's MIT license.

## Services

Synced lyrics come from [LRCLIB](https://lrclib.net), a free lyrics database. Only the
track title, artist, album and duration are sent, and this can be turned off in
Settings → Behaviour.

## Mascot

The pixel-art mascot is an original drawing made in code (`notch/ui/mascot.py`): a fan
tribute to the character Ramanan from the Malayalam film *Punjabi House* (2002). This
project isn't affiliated with or endorsed by the film's makers or cast.
