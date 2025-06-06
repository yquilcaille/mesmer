import numpy as np
import xarray as xr

import mesmer
from mesmer.testing import _convert


def test_lon_to_180():

    arr = np.array([-180.1, -180, -1, 0, 179.99, 180, 179 + 2 * 360])

    expected = np.array([179.9, -180, -1, 0, 179.99, -180, 179])

    result = mesmer.grid._lon_to_180(arr)
    np.testing.assert_allclose(result, expected)

    # ensure arr is not updated in-place
    assert not (arr == result).all()

    attrs = {"name": "test"}
    da = xr.DataArray(arr, dims="lon", coords={"lon": arr}, attrs=attrs, name="lon")
    expected = xr.DataArray(
        expected, dims="lon", coords={"lon": expected}, attrs=attrs, name="lon"
    )

    result = mesmer.grid._lon_to_180(da)

    xr.testing.assert_allclose(result, expected)

    assert result.attrs == expected.attrs


def test_lon_to_360():

    arr = np.array([-180.1, -180, -1, 0, 179.99, 180, 179 + 2 * 360, 259.9, 360])

    expected = np.array([179.9, 180, 359, 0, 179.99, 180, 179, 259.9, 0])

    result = mesmer.grid._lon_to_360(arr)
    np.testing.assert_allclose(result, expected)

    # ensure arr is not updated in-place
    assert not (arr == result).all()

    attrs = {"name": "test"}
    da = xr.DataArray(arr, dims="lon", coords={"lon": arr}, attrs=attrs, name="lon")
    expected = xr.DataArray(
        expected, dims="lon", coords={"lon": expected}, attrs=attrs, name="lon"
    )

    result = mesmer.grid._lon_to_360(da)

    xr.testing.assert_allclose(result, expected)

    assert result.attrs == expected.attrs


def test_wrap_to_180(datatype):

    attrs = {"name": "test"}
    obj = xr.DataArray(
        [0, 1, 2, 3, 4],
        dims="lon",
        coords={"lon": [-1, 1, 179, 180, 360]},
        name="data",
        attrs=attrs,
    )
    obj.lon.attrs = {"coord": "attrs"}
    expected = xr.DataArray(
        [3, 0, 4, 1, 2],
        dims="lon",
        coords={"lon": [-180, -1, 0, 1, 179]},
        name="data",
        attrs=attrs,
    )
    expected.lon.attrs = {"coord": "attrs"}

    obj = _convert(obj, datatype)
    expected = _convert(expected, datatype)

    result = mesmer.grid.wrap_to_180(obj)
    xr.testing.assert_identical(result, expected)

    # TODO: rename not working on DataTree https://github.com/pydata/xarray/issues/10015
    if datatype == "DataTree":
        return

    obj = obj.rename(lon="longitude")
    expected = expected.rename(lon="longitude")

    result = mesmer.grid.wrap_to_180(obj, lon_name="longitude")

    xr.testing.assert_identical(result, expected)


def test_wrap_to_360(datatype):

    attrs = {"name": "test"}
    obj = xr.DataArray(
        [0, 1, 2, 3, 4],
        dims="lon",
        coords={"lon": [-5, 1, 180, 359, 360]},
        name="data",
        attrs=attrs,
    )
    obj.lon.attrs = {"coord": "attrs"}
    expected = xr.DataArray(
        [4, 1, 2, 0, 3],
        dims="lon",
        coords={"lon": [0, 1, 180, 355, 359]},
        name="data",
        attrs=attrs,
    )
    expected.lon.attrs = {"coord": "attrs"}

    obj = _convert(obj, datatype)
    expected = _convert(expected, datatype)

    result = mesmer.grid.wrap_to_360(obj)
    xr.testing.assert_identical(result, expected)

    # TODO: rename not working on DataTree https://github.com/pydata/xarray/issues/10015
    if datatype == "DataTree":
        return

    obj = obj.rename(lon="longitude")
    expected = expected.rename(lon="longitude")

    result = mesmer.grid.wrap_to_360(obj, lon_name="longitude")

    xr.testing.assert_identical(result, expected)


def _get_test_data_grid(lon, datatype):
    lat = np.arange(90, -91, -10)

    data = np.random.randn(lat.size, lon.size)

    attrs = {"name": "test"}
    orig = xr.DataArray(
        data,
        dims=("lat", "lon"),
        coords={"lat": lat, "lon": lon},
        name="data",
        attrs=attrs,
    )

    return _convert(orig, datatype)


def test_wrap_to_360_roundtrip(datatype):

    lon = np.arange(-180, 180)

    orig = _get_test_data_grid(lon, datatype)

    wrapped = mesmer.grid.wrap_to_360(orig)
    roundtripped = mesmer.grid.wrap_to_180(wrapped)

    xr.testing.assert_identical(orig, roundtripped)


def test_wrap_to_180_roundtrip(datatype):

    lon = np.arange(0, 360)

    orig = _get_test_data_grid(lon, datatype)

    wrapped = mesmer.grid.wrap_to_180(orig)
    roundtripped = mesmer.grid.wrap_to_360(wrapped)

    xr.testing.assert_identical(orig, roundtripped)
