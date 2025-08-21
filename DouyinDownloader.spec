# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/main_window.ui', 'ui')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtWebEngine',      # 网页引擎
        'PySide6.Qt3D',             # 3D 功能
        'PySide6.QtSvg',            # SVG 支持
        'PySide6.QtMultimedia',     # 多媒体
        'PySide6.QtLocation',       # 地理位置
        'PySide6.QtWebChannel',     # Web 通道
        'PySide6.QtQuick',          # QML 支持
        'PySide6.QtQml',            # QML 支持
        'PySide6.QtNetwork',        # 网络功能（如果不需要）
        'PySide6.QtSql',            # 数据库支持
        'PySide6.QtTest',           # 测试模块
        'tkinter',
        'numpy',
        'pandas',
        'scipy',
        'matplotlib',
        ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure,cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    # 单文件模式关键：将所有二进制文件和数据文件直接包含在EXE中
    a.binaries,      # 包含所有二进制文件
    a.zipfiles,      # 包含所有zip文件
    a.datas,
    name='DouyinDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='dy.ico',
    # 单文件模式关键：设置为False，确保所有文件都包含在EXE中
    exclude_binaries=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 单文件模式关键参数
    onefile=True,   # 这是最重要的参数，启用单文件模式
)
