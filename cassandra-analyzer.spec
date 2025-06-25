# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all cassandra_analyzer submodules
hiddenimports = collect_submodules('cassandra_analyzer')

# Add common dependencies that might be missed
hiddenimports.extend([
    'yaml',
    'pyyaml',
    'requests',
    'pandas',
    'numpy',
    'jinja2',
    'aiohttp',
    'structlog',
    'rich',
    'click',
    'pydantic',
    'pydantic_core',
])

# Collect data files
datas = []
datas += collect_data_files('cassandra_analyzer')

# Add specific data files
datas += [
    ('cassandra_analyzer/reports/templates', 'cassandra_analyzer/reports/templates'),
]

a = Analysis(
    ['cassandra_analyzer_main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='cassandra-analyzer',
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
)