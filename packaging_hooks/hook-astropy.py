"""Focused PyInstaller hook for the Astropy features used by STDE.

The upstream compatibility hook deliberately bundles every Astropy submodule,
including test suites and optional pandas/notebook integrations.  STDE uses a
well-defined scientific subset, so collecting its dynamic submodules here keeps
FITS/WCS/Time/coordinates/visualization complete without shipping unrelated
developer and interoperability modules.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


def _runtime_module(name: str) -> bool:
    return ".tests" not in name and ".test" not in name and ".conftest" not in name


datas = collect_data_files(
    "astropy",
    excludes=[
        "**/tests/**", "**/test/**", "**/*.c", "**/*.h", "**/*.pyx",
        "**/*.rst", "**/README*",
    ],
)
# Astropy's PLY parsers open these generated Python tables by filesystem path,
# so they must also exist as ordinary files outside PyInstaller's code archive.
datas += collect_data_files(
    "astropy",
    include_py_files=True,
    includes=[
        "coordinates/angles/*_parsetab.py",
        "coordinates/angles/*_lextab.py",
        "units/format/*_parsetab.py",
        "units/format/*_lextab.py",
    ],
)
datas += copy_metadata("astropy") + copy_metadata("numpy")

# Astropy 7.x creates its public ``astropy.test`` helper during package import.
# Keep only that tiny compatibility module; the actual test suites and pytest
# dependencies remain excluded from data/submodule collection.
hiddenimports = ["numpy.lib.recfunctions", "astropy.tests.runner"]
# Astropy selects constants, coordinate representations, FITS compression,
# models, and unit formats dynamically. Collecting all *runtime* modules avoids
# brittle per-version allowlists while the filter still omits its test suites.
hiddenimports += collect_submodules("astropy", filter=_runtime_module)
