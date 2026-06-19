import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

block_cipher = None

datas = collect_data_files('PySide6')
# UnityPy требует бинарные ресурсы (lzma.tpk, brotli.tpk, etc.) для декодирования
datas += collect_data_files('UnityPy')
# archspec (зависимость numpy → UnityPy) содержит JSON схемы процессоров
datas += collect_data_files('archspec')
# numpy динамические библиотеки
datas += collect_data_files('numpy')
datas.append(('icon.ico', '.'))

# fmod.dll нужен UnityPy для декодирования текстур и аудио
binaries = collect_dynamic_libs('fmod_toolkit')
# numpy.dll, openblas.dll и пр.
binaries += collect_dynamic_libs('numpy')

# Собираем ВСЕ подмодули UnityPy явно — PyInstaller сам не находит
unitypy_submodules = collect_submodules('UnityPy')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'unpackers.unity_unpacker',
        'unpackers.rpa_unpacker',
        'unpackers',
    ] + unitypy_submodules,
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
    name='RPAExtractor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
