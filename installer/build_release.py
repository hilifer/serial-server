#!/usr/bin/env python3
"""
Build encrypted release package.
Uses marshal to serialize code objects — version-independent bytecode.
Target machine loads .pyc at first run via thin stubs.
"""
import os
import sys
import shutil
import marshal
import struct
import time
import zipfile
from pathlib import Path

PROJ_ROOT = Path(__file__).parent.parent
BUILD_DIR = PROJ_ROOT / 'installer' / 'build'
OUTPUT_DIR = PROJ_ROOT / 'installer' / 'output'

PY_FILES = [
    'server.py', 'serial_manager.py', 'meter.py', 'meter_api.py',
    'parking.py', 'state.py', 'deps.py', 'colors.py',
]
COPY_FILES = ['config.yaml', 'requirements.txt']
COPY_DIRS = ['web']


def clean():
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def encode_source(src_path, out_path):
    """Compile .py to .dat (marshal serialized code object).
    Cannot be read as text. Loaded via marshal.loads() at runtime."""
    with open(src_path, 'r', encoding='utf-8') as f:
        source = f.read()
    code = compile(source, os.path.basename(src_path), 'exec')
    data = marshal.dumps(code)
    # Simple XOR obfuscation so it's not even recognizable as marshal
    key = 0x5A
    obfuscated = bytes(b ^ key for b in data)
    with open(out_path, 'wb') as f:
        f.write(obfuscated)
    return len(data)


def compile_py():
    """Encode .py to .dat (obfuscated bytecode), create loader stubs."""
    print('[1/4] Encrypting Python source...')
    data_dir = BUILD_DIR / '_data'
    data_dir.mkdir(exist_ok=True)

    for name in PY_FILES:
        src = PROJ_ROOT / name
        if not src.exists():
            print(f'  SKIP {name}')
            continue

        module = name[:-3]
        dat_name = module + '.dat'
        size = encode_source(src, data_dir / dat_name)
        print(f'  ✓ {name} → _data/{dat_name} ({size} bytes)')

        # Create loader stub
        stub = f'''# Compiled module
import marshal, types, os, sys
_dir = os.path.dirname(os.path.abspath(__file__))
_dat = os.path.join(_dir, '_data', '{dat_name}')
with open(_dat, 'rb') as _f:
    _raw = _f.read()
_data = bytes(b ^ 0x5A for b in _raw)
_code = marshal.loads(_data)
exec(_code)
'''
        (BUILD_DIR / name).write_text(stub, encoding='utf-8')

    # run.py — main entry point
    run_py = '''#!/usr/bin/env python3
import marshal, os, sys
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
_dat = os.path.join(_dir, '_data', 'server.dat')
with open(_dat, 'rb') as _f:
    _raw = _f.read()
_data = bytes(b ^ 0x5A for b in _raw)
_code = marshal.loads(_data)
exec(_code)
'''
    (BUILD_DIR / 'run.py').write_text(run_py, encoding='utf-8')


def copy_assets():
    print('[2/4] Copying assets...')
    for name in COPY_FILES:
        src = PROJ_ROOT / name
        if src.exists():
            shutil.copy2(src, BUILD_DIR / name)
            print(f'  ✓ {name}')

    for d in COPY_DIRS:
        src = PROJ_ROOT / d
        if src.exists():
            shutil.copytree(src, BUILD_DIR / d, dirs_exist_ok=True,
                          ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
            print(f'  ✓ {d}/')

    for f in ['launch.bat', 'install.bat']:
        src = PROJ_ROOT / 'installer' / f
        if src.exists():
            shutil.copy2(src, BUILD_DIR / f)
            print(f'  ✓ {f}')

    inst_dir = BUILD_DIR / 'installer'
    inst_dir.mkdir(exist_ok=True)
    for f in ['create_shortcut.vbs', 'README.txt']:
        src = PROJ_ROOT / 'installer' / f
        if src.exists():
            shutil.copy2(src, inst_dir / f)


def fix_launch():
    launch = BUILD_DIR / 'launch.bat'
    if launch.exists():
        content = launch.read_text(encoding='utf-8')
        content = content.replace('python server.py', 'python run.py')
        launch.write_text(content, encoding='utf-8')
        print('  ✓ launch.bat → run.py')


def create_zip():
    print('[3/4] Creating ZIP package...')
    zip_path = OUTPUT_DIR / 'yriot_v1.0.zip'

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BUILD_DIR):
            for f in files:
                fpath = Path(root) / f
                arcname = fpath.relative_to(BUILD_DIR)
                zf.write(fpath, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f'  ✓ {zip_path.name} ({size_mb:.1f} MB)')
    return zip_path


def verify():
    print('[4/4] Verifying encryption...')
    for name in PY_FILES:
        stub = BUILD_DIR / name
        module = name[:-3]
        dat = BUILD_DIR / '_data' / (module + '.dat')

        stub_size = stub.stat().st_size if stub.exists() else 0
        dat_size = dat.stat().st_size if dat.exists() else 0

        # Check stub doesn't contain real logic
        if stub.exists():
            content = stub.read_text(encoding='utf-8')
            has_import = 'import ' in content and 'marshal' in content
            has_logic = 'def ' in content or 'class ' in content
            if has_logic:
                print(f'  ✗ {name} contains application logic!')
            else:
                print(f'  ✓ {name}: stub {stub_size}B, encrypted {dat_size}B')

        # Verify .dat is not readable
        if dat.exists():
            with open(dat, 'rb') as f:
                head = f.read(20)
            if b'import' in head or b'def ' in head or b'class ' in head:
                print(f'  ✗ {module}.dat contains readable code!')
            # else OK — it's XOR obfuscated


def main():
    print('=' * 50)
    print('  耀嵘光储充管理系统 — 加密发布包构建')
    print('=' * 50)
    print()
    clean()
    compile_py()
    copy_assets()
    fix_launch()
    create_zip()
    verify()
    print()
    print('=' * 50)
    print('  构建完成!')
    print(f'  输出: installer/output/yriot_v1.0.zip')
    print('  源码已加密为 .dat 文件，无法直接阅读')
    print('=' * 50)


if __name__ == '__main__':
    main()
