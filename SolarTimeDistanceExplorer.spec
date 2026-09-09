# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir recipe for the Windows desktop application."""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata


datas = []
binaries = []
hiddenimports = [
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_pdf",
    "matplotlib.backends.backend_ps",
    "matplotlib.backends.backend_svg",
    "PIL.Image",
    "imageio_ffmpeg",
    "sunpy.map",
    "sunpy.coordinates",
    "sunpy.coordinates.screens",
    "aiapy.calibrate",
]
datas += [("resources/stde_icon.png", "resources")]
for package in ("matplotlib", "astropy", "sunpy", "aiapy", "certifi", "imageio_ffmpeg"):
    datas += collect_data_files(package)
for distribution in ("imageio-ffmpeg",):
    datas += copy_metadata(distribution)
# PyInstaller's PySide6 hook deliberately owns Qt DLL/plugin collection. Adding
# those binaries a second time can create conflicting load paths in an onedir
# build. imageio-ffmpeg remains explicit for MP4 export.
for package in ("imageio_ffmpeg",):
    binaries += collect_dynamic_libs(package)
# Map source plug-ins are dynamically selected by the SunPy factory. Exclude
# bundled test modules: they add third-party test-only dependencies to an EXE.
hiddenimports += collect_submodules("sunpy.map", filter=lambda name: ".tests" not in name)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SolarTimeDistanceExplorer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="resources/stde_icon.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SolarTimeDistanceExplorer",
)
