# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('kb/references', 'kb/references'), ('interfaces/web/index.html', 'interfaces/web'), ('config.example.json', '.')]
binaries = []
hiddenimports = ['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'websockets']
hiddenimports += collect_submodules('junshi_harness')
hiddenimports += collect_submodules('junshi_domain')
hiddenimports += collect_submodules('providers')
hiddenimports += collect_submodules('adapters')
hiddenimports += collect_submodules('interfaces')
tmp_ret = collect_all('wxauto4')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='狗头助手',
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
)
