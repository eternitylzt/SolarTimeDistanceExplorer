"""Focused SunPy hook retaining Map/WCS support and all instrument Map classes."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


def _runtime_module(name: str) -> bool:
    return ".tests" not in name and ".test" not in name and ".conftest" not in name


datas = collect_data_files(
    "sunpy",
    excludes=[
        "**/tests/**", "**/test/**", "data/test/**", "data/sample/**",
        "**/*.rst", "**/README*",
    ],
)
# SunPy reads this file while importing its package root to expose citation
# metadata. It is runtime data, despite the documentation-style extension.
datas += collect_data_files("sunpy", includes=["CITATION.rst"])
datas += copy_metadata("sunpy")

# MapFactory selects the instrument class from FITS metadata at runtime.  Keep
# every source class, plus the coordinate and colormap registration modules
# needed to construct and plot a standards-compliant GenericMap/AIAMap.
# SunPy exposes ``self_test`` from its package root, so this one lightweight
# compatibility module is needed even though the real test suite is omitted.
hiddenimports = ["sunpy.tests.self_test"]
for package in (
    "sunpy.coordinates",
    "sunpy.image",
    "sunpy.io",
    "sunpy.map.sources",
    "sunpy.time",
    "sunpy.visualization.colormaps",
):
    hiddenimports += collect_submodules(package, filter=_runtime_module)
