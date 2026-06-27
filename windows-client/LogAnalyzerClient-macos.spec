# -*- mode: python ; coding: utf-8 -*-

from client_build_info import APP_VERSION

bundle_version = APP_VERSION.lstrip("v")


a = Analysis(
    ["log_analyzer_client.py"],
    pathex=[],
    binaries=[],
    datas=[("notice_config.json", ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["windnd"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LogAnalyzerClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LogAnalyzerClient",
)

app = BUNDLE(
    coll,
    name="LogAnalyzerClient.app",
    icon=None,
    bundle_identifier="com.wezhuiyi.loganalyzerclient",
    info_plist={
        "CFBundleName": "LogAnalyzerClient",
        "CFBundleDisplayName": "\u65e5\u5fd7\u5206\u6790\u5ba2\u6237\u7aef",
        "CFBundleShortVersionString": bundle_version,
        "CFBundleVersion": bundle_version,
        "NSHighResolutionCapable": True,
    },
)
