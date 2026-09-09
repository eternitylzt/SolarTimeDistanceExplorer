from __future__ import annotations

from pathlib import Path

from scipy import io

from app.data.sav_cube import inspect_sav


def test_scipy_sav_reader_can_inspect_standard_idl_fixture() -> None:
    fixture = Path(io.__file__).parent / "tests" / "data" / "array_float32_1d.sav"
    if not fixture.exists():
        return
    values = inspect_sav(fixture)
    assert "array1d" in values
