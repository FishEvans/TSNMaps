# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['StellarCartography.py'],
    pathex=[],
    binaries=[],
    datas=[('HTML\\Images', 'HTML\\Images'), ('GalMapInfo.json', '.')] + [('scripts/Referance/tsn_databases.py', 'scripts/Referance'), ('scripts/Referance/shipData.yaml', 'scripts/Referance'), ('scripts/Referance/ship_descriptions_fallback.json', 'scripts/Referance')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StellarCartography',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Icon.ico',
)
