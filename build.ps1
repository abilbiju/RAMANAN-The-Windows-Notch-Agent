# Builds dist\Ramanan.exe — a single, windowed (no console) executable.
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = if (Test-Path "..\.venv\Scripts\python.exe") { "..\.venv\Scripts\python.exe" } else { "python" }
& $python -m pip install -q -r requirements.txt pyinstaller pillow
& $python tools\make_icon.py

$exclude = @(
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtGraphs", "PySide6.QtDesigner", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "tkinter", "unittest", "pydoc"
) | ForEach-Object { "--exclude-module=$_" }

& $python -m PyInstaller main.py `
    --name Ramanan `
    --onefile `
    --windowed `
    --noconfirm `
    --clean `
    --icon assets\winnotch.ico `
    --add-data "assets;assets" `
    --hidden-import win32timezone `
    @exclude

Write-Host "`nBuilt: $PSScriptRoot\dist\Ramanan.exe"
