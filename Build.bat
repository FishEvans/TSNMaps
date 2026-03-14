@echo off
setlocal
pushd "%~dp0"

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build using spec files (keeps hidden imports + data definitions in sync)
pyinstaller "StellarCartography.spec" || goto :error
pyinstaller "LocMapGen.spec" || goto :error
pyinstaller "GalMapGen.spec" || goto :error
pyinstaller "SystemEditor.spec" || goto :error

REM Stage distributable data (terrain JSON + settings with blank author)
set "DIST=%CD%\dist"
set "TERRAIN_SRC=%CD%\data\missions\Map Designer\Terrain"
set "TERRAIN_DST=%DIST%\data\missions\Map Designer\Terrain"
set "GALMAPINFO_SRC=%CD%\GalMapInfo.json"
set "HTML_SRC=%CD%\HTML"
set "HTML_DST=%DIST%\HTML"
set "SCRIPTS_SRC=%CD%\scripts"
set "SCRIPTS_DST=%DIST%\scripts"

powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path '%DIST%' | Out-Null; New-Item -ItemType Directory -Force -Path '%TERRAIN_DST%' | Out-Null; Copy-Item -Path (Join-Path '%TERRAIN_SRC%' '*.json') -Destination '%TERRAIN_DST%' -Force" || goto :error
powershell -NoProfile -Command "$src='%CD%\SystemEditorSettings.json'; $dst='%DIST%\SystemEditorSettings.json'; if (Test-Path $src) { $q=[char]34; $pattern='(?ms)('+$q+'author'+$q+'\s*:\s*)'+$q+'(?:\\.|[^'+$q+'\\])*'+$q; $replacement='$1'+$q+$q; $content=[System.IO.File]::ReadAllText($src); $content=[regex]::Replace($content, $pattern, $replacement, 1); [System.IO.File]::WriteAllText($dst, $content, [System.Text.UTF8Encoding]::new($false)) }" || goto :error
powershell -NoProfile -Command "$src='%CD%\Settings.json'; $dst='%DIST%\Settings.json'; if (Test-Path $src) { $q=[char]34; $pattern='(?ms)('+$q+'author'+$q+'\s*:\s*)'+$q+'(?:\\.|[^'+$q+'\\])*'+$q; $replacement='$1'+$q+$q; $content=[System.IO.File]::ReadAllText($src); $content=[regex]::Replace($content, $pattern, $replacement, 1); [System.IO.File]::WriteAllText($dst, $content, [System.Text.UTF8Encoding]::new($false)) }" || goto :error
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%GALMAPINFO_SRC%') { Copy-Item -LiteralPath '%GALMAPINFO_SRC%' -Destination '%DIST%\GalMapInfo.json' -Force }" || goto :error
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%HTML_DST%') { Remove-Item -LiteralPath '%HTML_DST%' -Recurse -Force }; Copy-Item -LiteralPath '%HTML_SRC%' -Destination '%HTML_DST%' -Recurse -Force" || goto :error
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%SCRIPTS_DST%') { Remove-Item -LiteralPath '%SCRIPTS_DST%' -Recurse -Force }; Copy-Item -LiteralPath '%SCRIPTS_SRC%' -Destination '%SCRIPTS_DST%' -Recurse -Force" || goto :error
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%CD%\cargo_teams.json') { Copy-Item -LiteralPath '%CD%\cargo_teams.json' -Destination '%DIST%\cargo_teams.json' -Force }" || goto :error

echo.
echo Build complete. Dist staged for zip.
goto :end

:error
echo.
echo Build failed.
exit /b 1

:end
popd
pause
