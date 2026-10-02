# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPEC).resolve().parent.parent
APP = ROOT / 'desktop_app'
UPDATER = APP / 'updater.py'
ICON = APP / 'resources' / 'taco.ico'

for required in (UPDATER, ICON):
    if not required.exists():
        raise SystemExit(
            f'TACOUpdater build root resolution failed. Cannot find: {required}\n'
            f'SPEC={SPEC}\nROOT={ROOT}'
        )

a = Analysis(
    [str(UPDATER)],
    pathex=[str(APP)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TACOUpdater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
)
