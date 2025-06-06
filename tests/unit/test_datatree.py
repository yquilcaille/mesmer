import numpy as np
import pytest
import xarray as xr

import mesmer
from mesmer.core._datatreecompat import map_over_datasets
from mesmer.core.datatree import _datatree_wrapper
from mesmer.core.utils import _check_dataarray_form
from mesmer.testing import trend_data_1D, trend_data_2D


def test_collapse_datatree_into_dataset():
    n_ts = 30
    ds1 = xr.Dataset({"tas": trend_data_1D(n_timesteps=n_ts)})
    ds2 = ds1 * 2
    ds3 = ds1 * 3

    dim = xr.Variable("member", np.arange(3))
    leaf1 = xr.concat([ds1, ds2, ds3], dim=dim)
    dim = xr.Variable("member", np.arange(2))
    leaf2 = xr.concat([ds1, ds2], dim=dim)

    dt = xr.DataTree.from_dict({"scen1": leaf1, "scen2": leaf2})

    collapse_dim = "scenario"
    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)

    assert isinstance(res, xr.Dataset)
    assert collapse_dim in res.dims
    assert (res[collapse_dim] == ["scen1", "scen2"]).all()
    assert len(res.dims) == 3
    assert np.isnan(res.sel(scenario="scen2", member=2)).all()

    # error if data set has no coords along dim (bc then it is not concatenable if lengths differ)
    leaf_missing_coords = leaf1.drop_vars("member")
    dt = xr.DataTree.from_dict({"scen1": leaf_missing_coords, "scen2": leaf2})
    with pytest.raises(
        ValueError, match="cannot reindex or align along dimension 'member'"
    ):
        res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)

    # Dimension along which to concatenate already exists
    leaf1_scen = leaf1.assign_coords({"scenario": "scen1"}).expand_dims(collapse_dim)
    leaf2_scen = leaf2.assign_coords({"scenario": "scen2"}).expand_dims(collapse_dim)
    dt = xr.DataTree.from_dict({"scen1": leaf1_scen, "scen2": leaf2_scen})

    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)
    assert isinstance(res, xr.Dataset)

    scen1 = res.sel(scenario="scen1")
    xr.testing.assert_equal(scen1.drop_vars("scenario"), leaf1)

    # only one leaf works
    dt = xr.DataTree.from_dict({"scen1": leaf1})
    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)

    assert isinstance(res, xr.Dataset)
    assert collapse_dim in res.dims
    assert (res[collapse_dim] == ["scen1"]).all()
    assert len(res.dims) == 3

    xr.testing.assert_equal(scen1.drop_vars(collapse_dim), leaf1)

    # test data in root works
    dt = xr.DataTree(leaf1, name="scen1")
    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)

    assert isinstance(res, xr.Dataset)
    assert collapse_dim in res.dims
    assert (res[collapse_dim] == ["scen1"]).all()
    assert len(res.dims) == 3

    xr.testing.assert_equal(scen1.drop_vars(collapse_dim), leaf1)

    # nested DataTree works
    dt = xr.DataTree()
    dt["scen1/sub_scen1"] = xr.DataTree(leaf1)
    dt["scen1/sub_scen2"] = xr.DataTree(leaf2)
    dt["scen2"] = xr.DataTree(leaf2)

    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)
    assert isinstance(res, xr.Dataset)
    assert collapse_dim in res.dims
    assert len(res.dims) == 3
    assert set(res[collapse_dim].values) == {"sub_scen1", "sub_scen2", "scen2"}

    # more than one datavariable - works and fills with nans if necessary
    ds = ds3.rename({"tas": "tas2"})

    leaf3 = xr.merge(
        [ds1.assign_coords({"member": 1}), ds.assign_coords({"member": 1})]
    ).expand_dims("member")
    dt = xr.DataTree.from_dict({"scen1": leaf1, "scen2": leaf2, "scen3": leaf3})

    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)
    assert isinstance(res, xr.Dataset)
    assert collapse_dim in res.dims
    assert len(res.dims) == 3
    assert (res[collapse_dim] == ["scen1", "scen2", "scen3"]).all()
    assert len(res.data_vars) == 2
    assert np.isnan(res.sel(scenario="scen1").tas2).all()

    # two time dimensions that have different length fills missing values with nans
    ds_with_different_time = ds1.shift(time=1)

    badleaf = ds_with_different_time.assign_coords({"member": 0}).expand_dims("member")
    dt = xr.DataTree.from_dict({"scen1": leaf1, "scen2": badleaf})

    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)

    assert np.isnan(res.sel(scenario="scen2", time=leaf1.time)).all()

    # make sure it also works with stacked dimension
    # NOTE: only works if the stacked dimension has the same size on all datasets
    n_lat, n_lon = 2, 3
    da1 = mesmer.testing.trend_data_2D(n_timesteps=n_ts, n_lat=n_lat, n_lon=n_lon)
    ds1 = xr.Dataset({"tas": da1})
    da2 = mesmer.testing.trend_data_2D(n_timesteps=n_ts, n_lat=n_lat, n_lon=n_lon)
    ds2 = xr.Dataset({"tas": da2})

    dt = xr.DataTree.from_dict({"mem1": ds1, "mem2": ds2})
    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim="members")

    # empty nodes are removed before concatenating
    # NOTE: implicitly this is already there in the other tests, since the root node is always empty
    # but it is nice to have it explicitly too
    dt = xr.DataTree.from_dict({"scen1": leaf1, "scen2": xr.DataTree()})
    res = mesmer.datatree.collapse_datatree_into_dataset(dt, dim=collapse_dim)
    expected = leaf1.expand_dims(collapse_dim).assign_coords(
        {collapse_dim: np.array(["scen1"])}
    )
    xr.testing.assert_equal(res, expected)


def test_extract_single_dataarray_from_dt():
    da = trend_data_1D(n_timesteps=30).rename("tas")
    dt = xr.DataTree.from_dict({"/": xr.Dataset({"tas": da})})

    res = mesmer.datatree._extract_single_dataarray_from_dt(dt)
    xr.testing.assert_equal(res, da)

    dt = xr.DataTree(xr.Dataset({"tas": da, "tas2": da}))
    with pytest.raises(
        ValueError,
        match="Node must only contain one data variable, node has tas2 and tas.",
    ):
        mesmer.datatree._extract_single_dataarray_from_dt(dt)

    dt = xr.DataTree.from_dict(
        {"scen1": xr.Dataset({"tas": da, "tas2": da}), "scen2": xr.Dataset({"tas": da})}
    )

    # passing empty root
    with pytest.raises(ValueError, match="node has no data."):
        mesmer.datatree._extract_single_dataarray_from_dt(dt)

    # check name
    with pytest.raises(
        ValueError,
        match="Node must only contain one data variable, scen1 has tas2 and tas.",
    ):
        mesmer.datatree._extract_single_dataarray_from_dt(dt["scen1"], name="scen1")

    res = mesmer.datatree._extract_single_dataarray_from_dt(dt["scen2"])
    xr.testing.assert_equal(res, da)

    # passing empty Dataree
    with pytest.raises(ValueError, match="node has no data."):
        mesmer.datatree._extract_single_dataarray_from_dt(xr.DataTree())


def test_stack_linear_regression_datatrees():
    n_ts, n_lat, n_lon = 30, 2, 3
    member_dim = "member"
    time_dim = "time"
    stacking_dims = [time_dim, member_dim]
    collapse_dim = "scenario"
    stacked_dim = "sample"

    d2D_1 = xr.Dataset(
        {"tas": trend_data_2D(n_timesteps=n_ts, n_lat=n_lat, n_lon=n_lon)}
    )
    d2D_2 = d2D_1 * 2
    d2D_3 = d2D_1 * 3
    d2D_4 = d2D_1 * 4
    d2D_5 = d2D_1 * 5

    leaf1 = xr.concat([d2D_1, d2D_2, d2D_3], dim=member_dim).assign_coords(
        {member_dim: np.arange(3)}
    )
    leaf2 = xr.concat([d2D_4, d2D_5], dim=member_dim).assign_coords(
        {member_dim: np.arange(2)}
    )

    target = xr.DataTree.from_dict({"scen1": leaf1, "scen2": leaf2})

    d1D_1 = xr.Dataset({"tas": trend_data_1D(n_timesteps=n_ts)})
    d1D_2 = d1D_1 * 2
    d1D_3 = d1D_1 * 3
    d1D_4 = d1D_1 * 4
    predictors = xr.DataTree.from_dict(
        {
            "pred1": xr.DataTree.from_dict({"scen1": d1D_1, "scen2": d1D_2}),
            "pred2": xr.DataTree.from_dict({"scen1": d1D_3, "scen2": d1D_4}),
        }
    )

    weights = map_over_datasets(xr.ones_like, target.sel(cells=0))
    weights = map_over_datasets(
        lambda ds: ds.rename({var: "weights" for var in ds.data_vars}), weights
    )

    predictors_stacked, target_stacked, weights_stacked = (
        mesmer.datatree.stack_datatrees_for_linear_regression(
            predictors,
            target,
            weights,
            stacking_dims=stacking_dims,
            collapse_dim=collapse_dim,
            stacked_dim=stacked_dim,
        )
    )

    n_samples = n_ts * (2 + 3)  # 2 members for scen1, 3 members for scen2

    for pred in predictors_stacked.children:
        da = predictors_stacked[pred].to_dataset().tas
        _check_dataarray_form(
            da, name="pred1", ndim=1, required_dims={"sample"}, shape=(n_samples,)
        )

    _check_dataarray_form(
        target_stacked.tas,
        ndim=2,
        required_dims={"cells", "sample"},
        shape=(n_lat * n_lon, n_samples),
    )
    _check_dataarray_form(
        weights_stacked.weights, ndim=1, required_dims={"sample"}, shape=(n_samples,)
    )

    # check if datasets align
    pred1_stacked = predictors_stacked["pred1"].to_dataset()
    target_aligned, pred1_aligned = xr.align(
        target_stacked, pred1_stacked, join="exact"
    )
    xr.testing.assert_equal(target_stacked, target_aligned)
    xr.testing.assert_equal(pred1_stacked, pred1_aligned)

    pred2_stacked = predictors_stacked["pred2"].to_dataset()
    target_aligned, pred2_aligned = xr.align(
        target_stacked, pred2_stacked, join="exact"
    )
    xr.testing.assert_equal(target_stacked, target_aligned)
    xr.testing.assert_equal(pred2_stacked, pred2_aligned)

    target_aligned, weights_aligned = xr.align(
        target_stacked, weights_stacked, join="exact"
    )
    xr.testing.assert_equal(target_stacked, target_aligned)
    xr.testing.assert_equal(weights_stacked, weights_aligned)

    predictors_stacked, target_stacked, weights_stacked = (
        mesmer.datatree.stack_datatrees_for_linear_regression(
            predictors,
            target,
            None,
            stacking_dims=stacking_dims,
            collapse_dim=collapse_dim,
            stacked_dim=stacked_dim,
        )
    )
    assert weights_stacked is None, "Weights should be None if not provided"

    # check if exclude_dim can be empty
    predictors_stacked, target_stacked, weights_stacked = (
        mesmer.datatree.stack_datatrees_for_linear_regression(
            predictors,
            target.sel(cells=0),
            weights,
            stacking_dims=stacking_dims,
            collapse_dim=collapse_dim,
            stacked_dim=stacked_dim,
        )
    )

    pred1 = predictors_stacked["pred1"].to_dataset()
    target_aligned, pred1_aligned = xr.align(target_stacked, pred1, join="exact")
    xr.testing.assert_equal(target_stacked, target_aligned)
    xr.testing.assert_equal(pred1, pred1_aligned)


def test_datatree_wrapper_dt_kwarg_errors():

    @_datatree_wrapper
    def func(arg):
        return arg

    dt = xr.DataTree()

    with pytest.raises(TypeError, match="Passed a `DataTree` as keyword argument"):
        func(arg=dt)


def test_datatree_wrapper():

    @_datatree_wrapper
    def func(arg):
        assert isinstance(arg, xr.Dataset)
        return arg

    da = xr.DataArray([1, 2, 3], dims="x")
    ds = xr.Dataset(data_vars={"da": da})

    dt = xr.DataTree.from_dict({"node": ds})

    result_ds = func(ds)
    assert isinstance(result_ds, xr.Dataset)

    result_dt = func(dt)
    assert isinstance(result_dt, xr.DataTree)
