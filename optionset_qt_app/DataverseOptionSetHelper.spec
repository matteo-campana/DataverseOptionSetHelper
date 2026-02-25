# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# Paths
APP_DIR = os.path.abspath('.')
PARENT_DIR = os.path.abspath('..')

a = Analysis(
    ['main.py'],
    pathex=[APP_DIR, PARENT_DIR],
    binaries=[],
    datas=[
        (os.path.join('optionset_qt', 'assets', 'styles.qss'), os.path.join('optionset_qt', 'assets')),
        (os.path.join(PARENT_DIR, 'OptionSetHelper.py'), '.'),
    ],
    hiddenimports=[
        'OptionSetHelper',
        'optionset_qt',
        'optionset_qt.app',
        'optionset_qt.main_window',
        'optionset_qt.controllers.main_controller',
        'optionset_qt.models.optionset_model',
        'optionset_qt.ui.main_window_ui',
        'optionset_qt.views.bulk_progress_dialog',
        'optionset_qt.views.settings_dialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='DataverseOptionSetHelper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowed app (no terminal)
    icon=None,              # add path to .ico if you have one
)