"""Loading, streaming-parse and status behaviour of the glacier inventory (synthetic fixtures only)."""
import gzip
import io
import json
import time

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box, mapping

import glaciers
import main

R2 = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_OBJECT_KEY")


def feat(i):
    w = 77 + i * 0.1
    return {"type": "Feature", "properties": {"id": f"T-{i}", "name": f"Test {i}", "area_km2": 1.0 + i,
            "cenlon": w, "cenlat": 32.0}, "geometry": mapping(box(w, 32, w + 0.05, 32.05))}


def doc(n=5):
    return {"type": "FeatureCollection", "metadata": {"source": "SYNTHETIC"}, "features": [feat(i) for i in range(n)]}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in R2 + ("GLACIER_DATA_PATH",):
        monkeypatch.delenv(k, raising=False)
    glaciers.reset_cache()
    yield
    glaciers.reset_cache()


@pytest.mark.parametrize("chunk", [1, 7, 64, 1 << 20])
def test_streaming_parse_matches_with_tiny_chunks(tmp_path, chunk):
    p = tmp_path / "g.geojson"
    p.write_text(json.dumps(doc(6)))
    inv = glaciers.GlacierInventory.from_file(p, chunk_size=chunk)
    assert len(inv) == 6 and inv.metadata["source"] == "SYNTHETIC"


def test_gzip_and_plain_agree(tmp_path):
    plain, gz = tmp_path / "a.geojson", tmp_path / "a.geojson.gz"
    plain.write_text(json.dumps(doc()))
    with gzip.open(gz, "wt", encoding="utf-8") as h:
        h.write(json.dumps(doc()))
    assert len(glaciers.GlacierInventory.from_file(plain)) == len(glaciers.GlacierInventory.from_file(gz)) == 5


def test_features_before_metadata_falls_back(tmp_path):
    d = doc(3)
    p = tmp_path / "odd.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": d["features"], "metadata": d["metadata"]}))
    assert len(glaciers.GlacierInventory.from_file(p, chunk_size=16)) == 3


def test_truncated_file_is_an_error_not_a_partial_inventory(tmp_path):
    p = tmp_path / "cut.geojson"
    p.write_text(json.dumps(doc(5))[:-200])
    with pytest.raises(Exception):
        glaciers.GlacierInventory.from_file(p, chunk_size=64)


def test_missing_r2_settings_are_named(monkeypatch, tmp_path):
    monkeypatch.setenv("R2_ACCOUNT_ID", "x")
    monkeypatch.setenv("R2_BUCKET_NAME", "b")
    monkeypatch.setenv("R2_OBJECT_KEY", str(tmp_path / "k.gz").split("/")[-1])
    with pytest.raises(glaciers.InventoryNotLoaded) as e:
        glaciers.get_inventory()
    assert "R2_ACCESS_KEY_ID" in str(e.value) and "R2_SECRET_ACCESS_KEY" in str(e.value)
    d = glaciers.diagnostics()
    assert "R2_ACCESS_KEY_ID" in d["missingR2Settings"]
    assert "x" not in json.dumps({k: v for k, v in d.items() if k != "r2SettingsPresent"}).replace("exists", "")  # no values leaked


def test_failure_has_cooldown_and_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setenv("R2_ACCOUNT_ID", "a"); monkeypatch.setenv("R2_BUCKET_NAME", "b"); monkeypatch.setenv("R2_OBJECT_KEY", "nope-cooldown.gz")
    for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "v")
    def boom(path):
        calls.append(1)
        raise glaciers.InventoryNotLoaded("download failed")
    monkeypatch.setattr(glaciers, "_download_inventory_from_r2", boom)
    for _ in range(3):
        with pytest.raises(glaciers.InventoryNotLoaded):
            glaciers.get_inventory()
    assert len(calls) == 1
    assert glaciers.load_state()["phase"] == "failed"


def test_corrupt_file_reports_failure_stage(tmp_path, monkeypatch):
    p = tmp_path / "bad.geojson"
    p.write_text("{not json")
    monkeypatch.setenv("GLACIER_DATA_PATH", str(p))
    with pytest.raises(glaciers.InventoryNotLoaded):
        glaciers.get_inventory()
    s = glaciers.load_state()
    assert s["phase"] == "failed" and s["stage"] == "parse"


def test_status_never_blocks_on_slow_load(tmp_path, monkeypatch):
    p = tmp_path / "slow.geojson"
    p.write_text(json.dumps(doc()))
    monkeypatch.setenv("GLACIER_DATA_PATH", str(p))
    real = glaciers.GlacierInventory.from_file
    def slow(path, *a, **k):
        time.sleep(1.5)
        return real(path, *a, **k)
    monkeypatch.setattr(glaciers.GlacierInventory, "from_file", staticmethod(slow))
    monkeypatch.setattr(glaciers, "warm_up", lambda wait=0.0, _orig=glaciers.warm_up: _orig(wait=0.1))
    c = TestClient(main.app)
    t = time.time()
    s = c.get("/api/glaciers/status").json()
    assert time.time() - t < 1.2 and s["loaded"] is False and s["loading"] is True
    assert c.get("/api/glaciers/search?q=test").status_code == 503
    time.sleep(2)
    s = c.get("/api/glaciers/status").json()
    assert s["loaded"] is True and s["glacierCount"] == 5
    assert c.get("/api/glaciers/search?q=test").status_code == 200


def test_status_failed_includes_diagnostics_without_secrets(tmp_path, monkeypatch):
    p = tmp_path / "bad.geojson"
    p.write_text("[]")
    monkeypatch.setenv("GLACIER_DATA_PATH", str(p))
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "SUPERSECRETVALUE")
    s = TestClient(main.app).get("/api/glaciers/status")
    body = s.text
    assert s.json()["loaded"] is False and "diagnostics" in s.json() and "SUPERSECRETVALUE" not in body
