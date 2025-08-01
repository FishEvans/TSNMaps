@echo off
start "" cmd /k "cd /d \"%~dp0\""

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist StellarCartography.py.spec del /f /q StellarCartography.py.spec

REM Run PyInstaller to create a windowed executable
pyinstaller --name StellarCartography ^
    --add-data "HTML\Images;HTML\Images" ^
    --add-data "GalMapInfo.json;." ^
    --add-data "LocMapGen.py;." ^
    --add-data "GalMapGen.py;." ^
    StellarCartography.py


pyinstaller --name LocMapGen LocMapGen.py

pyinstaller --name GalMapGen GalMapGen.py

pyinstaller --name SystemEditor SystemEditor.py


REM Pause to show build results
pause
