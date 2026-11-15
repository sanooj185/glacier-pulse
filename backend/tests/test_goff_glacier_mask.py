"""The GOFF preview must only mark samples as glacier when their centre is inside a real outline.

Everything here is SYNTHETIC: a made-up GOFF-shaped HDF5 file on a UTM 45N grid and one made-up
rectangular "glacier". The expected mask is computed independently, in lon/lat, so the test does
not share the production code's projection path.
"""
import json

import h5py
import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import box, mapping, Point

import glaciers
import main

EPSG = 32645
ROOT = "science/LSAR/GOFF/grids/frequencyA/pixelOffsets/HH/layer1/"
GLACIER_LL = box(87.020, 36.010, 87.060, 36.040)   # synthetic; lies in the upper-left of the grid below


def make_goff(path, rows=200, cols=240):
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{EPSG}", always_xy=True)
    x0, y0 = to_utm.transform(87.000, 36.060)       # north-west corner
    x = x0 + 80.0 * np.arange(cols)
    y = y0 - 80.0 * np.arange(rows)                 # DESCENDING y, as in a north-up product
    rng = np.random.default_rng(0)
    with h5py.File(path, "w") as f:
        for name in ("alongTrackOffset", "slantRangeOffset", "correlationSurfacePeak", "snr"):
            f.create_dataset(ROOT + name, data=rng.normal(size=(rows, cols)).astype("float32"))
        f.create_dataset(ROOT + "xCoordinates", data=x)
        f.create_dataset(ROOT + "yCoordinates", data=y)
        f.create_dataset(ROOT + "projection", data=np.int32(EPSG)).attrs["epsg_code"] = EPSG
    return x, y


def inventory_file(tmp_path, geom=GLACIER_LL):
    p = tmp_path / "glaciers.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "metadata": {"source": "SYNTHETIC TEST DATA", "url": "n/a"},
                             "features": [{"type": "Feature", "properties": {"id": "SYN-1", "name": "Synthetic", "area_km2": 3.0},
                                           "geometry": mapping(geom)}]}))
    return p


@pytest.fixture
def goff(tmp_path):
    path = tmp_path / "synthetic_goff.h5"
    x, y = make_goff(path)
    return path, x, y


def test_mask_matches_independent_lonlat_test_and_orientation(goff, tmp_path, monkeypatch):
    path, x, y = goff
    monkeypatch.setenv("GLACIER_DATA_PATH", str(inventory_file(tmp_path)))
    glaciers.reset_cache()
    with h5py.File(path, "r") as f:
        out = main.make_preview(f, "synthetic.h5", "layer1", 120)     # step = 2 -> samples every 2nd pixel
    mask = np.array(out["glacierMask"], dtype=bool)
    lon, lat = np.array(out["longitude"]), np.array(out["latitude"])
    expected = np.array([[GLACIER_LL.contains(Point(a, b)) for a, b in zip(rl, rb)] for rl, rb in zip(lon, lat)])
    assert mask.shape == lon.shape == expected.shape
    assert expected.sum() > 20                                         # the test glacier really holds samples
    assert (mask != expected).sum() <= 2                               # only samples within ~1 m of an edge may differ
    rows, cols = np.where(mask)
    assert rows.max() < mask.shape[0] * 0.6 and cols.max() < mask.shape[1] * 0.6   # upper-left, not mirrored/transposed
    meta = out["metadata"]["glacierMask"]
    assert meta["available"] and meta["insidePixels"] == int(mask.sum()) and meta["source"] == "SYNTHETIC TEST DATA"


def test_samples_near_but_outside_are_not_marked(goff, tmp_path, monkeypatch):
    """Proximity must never count: a sample 100 m outside the outline is excluded."""
    path, x, y = goff
    monkeypatch.setenv("GLACIER_DATA_PATH", str(inventory_file(tmp_path)))
    glaciers.reset_cache()
    inv = glaciers.get_inventory()
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{EPSG}", always_xy=True)
    west, south = to_utm.transform(87.020, 36.025)     # on the west edge, mid-height
    px = np.array([west - 100.0, west + 100.0]); py = np.array([south, south])
    to_ll = Transformer.from_crs(f"EPSG:{EPSG}", "EPSG:4326", always_xy=True)
    lon, lat = to_ll.transform(px, py)
    mask, n = inv.samples_inside(px, py, np.asarray(lon), np.asarray(lat), EPSG)
    assert n == 1 and mask.tolist() == [False, True]


def test_preview_still_works_without_inventory(goff, tmp_path, monkeypatch):
    path, *_ = goff
    monkeypatch.setenv("GLACIER_DATA_PATH", str(tmp_path / "missing.geojson"))
    glaciers.reset_cache()
    with h5py.File(path, "r") as f:
        out = main.make_preview(f, "synthetic.h5", "layer1", 120)
    assert out["glacierMask"] is None
    assert out["metadata"]["glacierMask"]["available"] is False and "inventory" in out["metadata"]["glacierMask"]["reason"].lower()
    assert len(out["alongTrack"]) == len(out["longitude"])           # rest of the preview untouched


def test_no_outlines_near_the_grid_gives_empty_mask(goff, tmp_path, monkeypatch):
    path, *_ = goff
    far = box(80.0, 30.0, 80.05, 30.05)
    monkeypatch.setenv("GLACIER_DATA_PATH", str(inventory_file(tmp_path, far)))
    glaciers.reset_cache()
    with h5py.File(path, "r") as f:
        out = main.make_preview(f, "synthetic.h5", "layer1", 120)
    assert sum(map(sum, out["glacierMask"])) == 0
    assert out["metadata"]["glacierMask"]["insidePixels"] == 0 and out["metadata"]["glacierMask"]["candidateGlaciers"] == 0
