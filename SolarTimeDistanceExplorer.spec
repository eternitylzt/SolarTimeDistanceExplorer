# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir recipe for Windows, Linux and macOS."""

import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


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
# Matplotlib/Astropy/SunPy/certifi data are handled by their hooks.  Only the
# active-platform FFmpeg executable is explicitly retained here.
datas += collect_data_files("imageio_ffmpeg", includes=["binaries/*"])
datas += collect_data_files("aiapy", includes=["CITATION.rst"])
datas += collect_data_files("drms", includes=["CITATION.rst"])
for distribution in ("imageio-ffmpeg",):
    datas += copy_metadata(distribution)
# Map source plug-ins are dynamically selected by the SunPy factory. Exclude
# bundled test modules: they add third-party test-only dependencies to an EXE.
hiddenimports += collect_submodules("sunpy.map", filter=lambda name: ".tests" not in name)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["packaging_hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "pytest", "IPython", "jupyter", "notebook",
        "dask.dataframe",
    ],
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
    icon="resources/stde_icon.ico" if sys.platform == "win32" else None,
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

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SolarTimeDistanceExplorer.app",
        bundle_identifier="com.zhentongli.solartimedistanceexplorer",
    )
