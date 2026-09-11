# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all pywebview and pythonnet requirements
webview_datas = collect_data_files('webview')
webview_submodules = collect_submodules('webview')
pythonnet_submodules = collect_submodules('pythonnet')

project_dir = Path(SPECPATH)

datas = [
    (str(project_dir / 'pod006' / 'ui'), 'ui'),
    (str(project_dir / 'pod006' / 'assets'), 'assets'),
] + webview_datas

binaries = [
    (str(project_dir / 'pod006' / 'bin' / '7z.exe'), 'bin'),
    (str(project_dir / 'pod006' / 'bin' / '7z.dll'), 'bin'),
]

hiddenimports = [
    'clr',
    'pythonnet',
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
] + webview_submodules + pythonnet_submodules

a = Analysis(
    ['pod006/app.py'],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'numpy', 'IPython', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='pod 006',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / 'pod006' / 'assets' / 'icon.ico'),
)
