# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for 耀嵘光储充管理系统
Compiles into a single .exe with all Python source embedded as bytecode.
No source code can be extracted.
"""
import os

block_cipher = None

# Collect all web assets
web_dir = os.path.join(os.path.dirname(os.path.abspath(SPECPATH)), 'web')
web_datas = []
for root, dirs, files in os.walk(web_dir):
    for f in files:
        src = os.path.join(root, f)
        dst = os.path.relpath(root, os.path.dirname(web_dir))
        web_datas.append((src, dst))

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('requirements.txt', '.'),
        ('web', 'web'),
    ],
    hiddenimports=[
        'serial_manager', 'meter', 'meter_api', 'parking',
        'state', 'deps', 'colors',
        'flask', 'yaml', 'paho.mqtt.client', 'serial',
        'requests', 'jinja2', 'markupsafe',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'PIL'],
    noarchive=False,
    optimize=2,  # Maximum bytecode optimization
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='耀嵘光储充管理系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Show console for server logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
