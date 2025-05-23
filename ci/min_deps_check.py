#!/usr/bin/env python
"""Fetch from conda database all available versions of the xarray dependencies and their
publication date. Compare it against requirements/*-min-all-deps.yml to verify the
policy on obsolete dependencies is being followed. Print a pretty report :)
"""

# min_deps_check.py is copied from xarray:
# https://github.com/pydata/xarray/blob/main/ci/min_deps_check.py
# Used under the terms of xarray's license, see licenses/XARRAY_LICENSE.

import itertools
import sys
from collections.abc import Iterator
from datetime import datetime

import conda.api  # type: ignore[import]
import yaml
from dateutil.relativedelta import relativedelta

CHANNELS = ["conda-forge", "defaults"]
IGNORE_DEPS = {
    "black",
    "coveralls",
    "flake8",
    "hypothesis",
    "isort",
    "mypy",
    "pip",
    "pytest-cov",
    "pytest-xdist",
    "pytest",
    "setuptools",
}

POLICY_MONTHS = {"python": 30, "numpy": 18}
POLICY_MONTHS_DEFAULT = 12
# xarray v2025.03 is needed for xr.DataTree support
POLICY_OVERRIDE: dict[str, tuple[int, int]] = {"xarray": (2025, 3)}
errors = []


def error(msg: str) -> None:
    global errors
    errors.append(msg)
    print("ERROR:", msg)


def warning(msg: str) -> None:
    print("WARNING:", msg)


def parse_requirements(fname) -> Iterator[tuple[str, int, int, int | None]]:
    """Load requirements/py*-min-all-deps.yml

    Yield (package name, major version, minor version, [patch version])
    """
    global errors

    with open(fname) as fh:
        contents = yaml.safe_load(fh)
    for row in contents["dependencies"]:
        if isinstance(row, dict) and list(row) == ["pip"]:
            continue
        pkg, eq, version = row.partition("=")
        if pkg.rstrip("<>") in IGNORE_DEPS:
            continue
        if pkg.endswith("<") or pkg.endswith(">") or eq != "=":
            error("package should be pinned with exact version: " + row)
            continue

        try:
            version_tup = tuple(int(x) for x in version.split("."))
        except ValueError:
            raise ValueError("non-numerical version: " + row)

        if len(version_tup) == 2:
            yield (pkg, *version_tup, None)  # type: ignore[misc]
        elif len(version_tup) == 3:
            yield (pkg, *version_tup)  # type: ignore[misc]
        else:
            raise ValueError("expected major.minor or major.minor.patch: " + row)


def query_conda(pkg: str) -> dict[tuple[int, int], datetime]:
    """Query the conda repository for a specific package

    Return map of {(major version, minor version): publication date}
    """

    def metadata(entry):
        version = entry.version

        time = datetime.fromtimestamp(entry.timestamp)
        major, minor = map(int, version.split(".")[:2])

        return (major, minor), time

    raw_data = conda.api.SubdirData.query_all(pkg, channels=CHANNELS)
    data = sorted(metadata(entry) for entry in raw_data if entry.timestamp != 0)

    release_dates = {
        version: [time for _, time in group if time is not None]
        for version, group in itertools.groupby(data, key=lambda x: x[0])
    }
    out = {version: min(dates) for version, dates in release_dates.items() if dates}

    # Hardcoded fix to work around incorrect dates in conda
    if pkg == "python":
        out.update(
            {
                (2, 7): datetime(2010, 6, 3),
                (3, 5): datetime(2015, 9, 13),
                (3, 6): datetime(2016, 12, 23),
                (3, 7): datetime(2018, 6, 27),
                (3, 8): datetime(2019, 10, 14),
                (3, 9): datetime(2020, 10, 5),
                (3, 10): datetime(2021, 10, 4),
                (3, 11): datetime(2022, 10, 24),
            }
        )

    return out


def process_pkg(
    pkg: str, req_major: int, req_minor: int, req_patch: int | None
) -> tuple[str, str, str, str, str, str]:
    """Compare package version from requirements file to available versions in conda.
    Return row to build pandas dataframe:

    - package name
    - major.minor.[patch] version in requirements file
    - publication date of version in requirements file (YYYY-MM-DD)
    - major.minor version suggested by policy
    - publication date of version suggested by policy (YYYY-MM-DD)
    - status ("<", "=", "> (!)")
    """
    print(f"Analyzing {pkg}...")
    versions = query_conda(pkg)

    try:
        req_published = versions[req_major, req_minor]
    except KeyError:
        error("not found in conda: " + pkg)
        return pkg, fmt_version(req_major, req_minor, req_patch), "-", "-", "-", "(!)"

    policy_months = POLICY_MONTHS.get(pkg, POLICY_MONTHS_DEFAULT)
    policy_published = datetime.now() - relativedelta(months=policy_months)

    filtered_versions = [
        version
        for version, published in versions.items()
        if published < policy_published
    ]
    policy_major, policy_minor = max(filtered_versions, default=(req_major, req_minor))

    try:
        policy_major, policy_minor = POLICY_OVERRIDE[pkg]
    except KeyError:
        pass
    policy_published_actual = versions[policy_major, policy_minor]

    if (req_major, req_minor) < (policy_major, policy_minor):
        status = "<"
    elif (req_major, req_minor) > (policy_major, policy_minor):
        status = "> (!)"
        delta = relativedelta(datetime.now(), req_published).normalized()
        n_months = delta.years * 12 + delta.months
        warning(
            f"Package is too new: {pkg}={req_major}.{req_minor} was "
            f"published on {req_published:%Y-%m-%d} "
            f"which was {n_months} months ago (policy is {policy_months} months)"
        )
    else:
        status = "="

    if req_patch is not None:
        warning("patch version should not appear in requirements file: " + pkg)
        status += " (w)"

    return (
        pkg,
        fmt_version(req_major, req_minor, req_patch),
        req_published.strftime("%Y-%m-%d"),
        fmt_version(policy_major, policy_minor),
        policy_published_actual.strftime("%Y-%m-%d"),
        status,
    )


def fmt_version(major: int, minor: int, patch: int = None) -> str:
    if patch is None:
        return f"{major}.{minor}"
    else:
        return f"{major}.{minor}.{patch}"


def main(fname) -> None:
    rows = [
        process_pkg(pkg, major, minor, patch)
        for pkg, major, minor, patch in parse_requirements(fname)
    ]

    print("\nPackage           Required             Policy               Status")
    print("----------------- -------------------- -------------------- ------")
    fmt = "{:17} {:7} ({:10}) {:7} ({:10}) {}"
    for row in rows:
        print(fmt.format(*row))

    if errors:
        print("\nErrors:")
        print("-------")
        for i, e in enumerate(errors):
            print(f"{i + 1}. {e}")
        sys.exit(1)


if __name__ == "__main__":
    fnames = sys.argv[1:]

    for fname in fnames:
        main(fname)
