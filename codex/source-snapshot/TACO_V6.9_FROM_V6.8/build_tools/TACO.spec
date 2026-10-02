# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

# PyInstaller's SPEC global is the complete spec-file argument.
# Resolve the project root from the actual .spec file so the build works
# regardless of the caller's current directory.
ROOT = Path(SPEC).resolve().parent.parent
APP = ROOT / 'desktop_app'
RES = APP / 'resources'

if not (APP / 'main.py').exists():
    raise SystemExit(
        f'TACO build root resolution failed. Cannot find: {APP / "main.py"}\n'
        f'SPEC={SPEC}\nROOT={ROOT}'
    )

license_pub = RES / 'license_public_key.pem'
update_pub = RES / 'update_public_key.pem'
for key in (license_pub, update_pub):
    if not key.exists():
        raise SystemExit(
            f'Production build is missing Public Key: {key}\n'
            'Run build_tools\\prepare_security_keys.bat first.'
        )

icon_path = RES / 'taco.ico'
version_info = ROOT / 'build_tools' / 'version_info.txt'
for required in (icon_path, version_info):
    if not required.exists():
        raise SystemExit(f'Production build is missing required file: {required}')

datas = [
    (str(license_pub), 'resources'),
    (str(update_pub), 'resources'),
    (str(icon_path), 'resources'),
]

hiddenimports = [
    'PyQt6.QtPrintSupport',
    'pandas',
    'openpyxl',
    'xlrd',
    'fitz',
    'pymupdf',
    'pyodbc',
    'cryptography',
    'cryptography.hazmat.primitives.asymmetric.ed25519',
]

a = Analysis(
    [str(APP / 'main.py')],
    pathex=[str(APP)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TACO',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_path),
    version=str(version_info),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TACO',
)
