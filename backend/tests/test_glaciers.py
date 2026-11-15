"""Tests for glacier search, bbox queries, footprint coverage and the API.

All geometries below are SYNTHETIC test fixtures (simple squares with made-up names). They exist only to
verify the spatial logic and are never shipped as glacier data.
"""
import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box, mapping

import glaciers
import main

# (id, name, west, south, east, north) - synthetic squares near lon 77, lat 32
SYNTHETIC = [
    ("TEST-A", "Alpha Test Glacier", 77.00, 32.00, 77.05, 32.05),
    ("TEST-B", "Beta Test Glacier", 77.18, 32.00, 77.28, 32.05),   # straddles a footprint edge at lon 77.23
    ("TEST-C", None, 80.00, 33.00, 80.02, 33.02),                  # far away, unnamed
    ("TEST-D", "Älpha Südtest", 77.10, 32.10, 77.12, 32.12),       # accent-folding check
]


def feature(gid, name, w, s, e, n, area=None):
    return {"type": "Feature", "properties": {"id": gid, "name": name, "area_km2": area or round((e - w) * (n - s) * 111 * 94, 3),
            "region": "SYNTHETIC", "cenlon": (w + e) / 2, "cenlat": (s + n) / 2},
            "geometry": mapping(box(w, s, e, n))}


@pytest.fixture
def inv():
    return glaciers.GlacierInventory([feature(*row) for row in SYNTHETIC], {"source": "SYNTHETIC TEST DATA", "citation": "n/a"})


FOOTPRINT = box(76.9, 31.9, 77.23, 32.2)  # fully covers A and D, cuts B at lon 77.23


def test_full_partial_none_classification(inv):
    a = inv.coverage(inv.geometry("TEST-A"), FOOTPRINT)
    b = inv.coverage(inv.geometry("TEST-B"), FOOTPRINT)
    c = inv.coverage(inv.geometry("TEST-C"), FOOTPRINT)
    assert a["status"] == "full" and a["coveragePercent"] == pytest.approx(100.0, abs=0.01)
    assert b["status"] == "partial"
    assert c["status"] == "none" and c["coveragePercent"] == 0.0 and c["intersectionKm2"] == 0.0


def test_partial_coverage_percent_is_area_faithful(inv):
    # B spans lon 77.18-77.28; the footprint cuts at 77.23 => exactly half of B's width (equal height).
    b = inv.coverage(inv.geometry("TEST-B"), FOOTPRINT)
    assert b["coveragePercent"] == pytest.approx(50.0, abs=0.5)
    assert 0 < b["intersectionKm2"] < b["glacierAreaKm2"]


def test_proximity_is_not_intersection(inv):
    # A footprint ending 1 km short of glacier A must NOT be associated with it.
    near_miss = box(76.0, 31.0, 76.99, 33.0)
    assert inv.coverage(inv.geometry("TEST-A"), near_miss)["status"] == "none"
    assert all(g["id"] != "TEST-A" for g in inv.intersecting(near_miss))


def test_touching_edge_only_is_none(inv):
    touching = box(76.0, 31.0, 77.0, 33.0)  # shares only the lon=77.00 edge with A
    assert inv.coverage(inv.geometry("TEST-A"), touching)["status"] == "none"


def test_near_edge_flag(inv):
    cov = inv.coverage(inv.geometry("TEST-B"), FOOTPRINT)
    assert cov["nearEdge"] is True            # crosses the footprint edge
    far = inv.coverage(inv.geometry("TEST-A"), box(70, 25, 85, 40))
    assert far["status"] == "full" and far["nearEdge"] is False


def test_intersecting_lists_only_real_intersections(inv):
    ids = {g["id"] for g in inv.intersecting(FOOTPRINT)}
    assert ids == {"TEST-A", "TEST-B", "TEST-D"}


def test_search_ranking_and_accent_folding(inv):
    assert [g["id"] for g in inv.search("alpha test")] == ["TEST-A"]
    assert {g["id"] for g in inv.search("alpha")} == {"TEST-A", "TEST-D"}   # "Älpha" folds to "alpha"
    assert inv.search("a") == []                                            # too short
    assert inv.search("zzzz") == []
    assert [g["id"] for g in inv.search("TEST-C")] == ["TEST-C"]           # id search works for unnamed glaciers


def test_bbox_query_limits_and_truncation(inv):
    all_in = inv.in_bbox(76, 31, 78, 33)
    assert {f["id"] for f in all_in["features"]} == {"TEST-A", "TEST-B", "TEST-D"} and not all_in["truncated"]
    capped = inv.in_bbox(76, 31, 78, 33, limit=1)
    assert len(capped["features"]) == 1 and capped["truncated"] and capped["totalInView"] == 3
    assert inv.in_bbox(0, 0, 1, 1)["features"] == []


def test_invalid_geometry_is_repaired_not_dropped():
    bowtie = {"type": "Polygon", "coordinates": [[[77, 32], [77.1, 32.1], [77.1, 32], [77, 32.1], [77, 32]]]}
    inv = glaciers.GlacierInventory([{"type": "Feature", "properties": {"id": "X", "name": "Bow", "area_km2": 1}, "geometry": bowtie}])
    assert len(inv) == 1 and inv.repaired_geometries == 1


# ------------------------------------------------------------------ API
@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "glaciers.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "metadata": {"source": "SYNTHETIC TEST DATA"},
                                "features": [feature(*row) for row in SYNTHETIC]}))
    monkeypatch.setenv("GLACIER_DATA_PATH", str(path))
    glaciers.reset_cache()
    yield TestClient(main.app)
    glaciers.reset_cache()


def test_api_without_inventory_reports_clearly(tmp_path, monkeypatch):
    monkeypatch.setenv("GLACIER_DATA_PATH", str(tmp_path / "missing.geojson"))
    glaciers.reset_cache()
    c = TestClient(main.app)
    assert c.get("/api/glaciers/status").json()["loaded"] is False
    r = c.get("/api/glaciers?west=70&south=25&east=100&north=40")
    assert r.status_code == 503 and "inventory" in r.json()["detail"].lower()
    assert c.get("/api/glaciers/search?q=alpha").status_code == 503


def test_api_status_search_profile(client):
    s = client.get("/api/glaciers/status").json()
    assert s["loaded"] and s["glacierCount"] == 4 and s["namedGlacierCount"] == 3
    hits = client.get("/api/glaciers/search?q=beta").json()["results"]
    assert [h["id"] for h in hits] == ["TEST-B"]
    prof = client.get("/api/glaciers/TEST-A").json()["glacier"]
    assert prof["properties"]["name"] == "Alpha Test Glacier" and prof["geometry"]["type"] == "Polygon"
    assert client.get("/api/glaciers/NOPE").status_code == 404


def test_api_outlines_validation_and_content(client):
    r = client.get("/api/glaciers?west=76&south=31&east=78&north=33&simplify=0.0001").json()
    assert {f["id"] for f in r["features"]} == {"TEST-A", "TEST-B", "TEST-D"}
    assert client.get("/api/glaciers?west=78&south=31&east=76&north=33").status_code == 400
    assert client.get("/api/glaciers?west=76&south=31&east=78&north=33&limit=0").status_code == 400


def test_api_footprint_intersection(client):
    body = {"geometry": mapping(FOOTPRINT)}
    r = client.post("/api/observations/glaciers", json=body).json()
    by_id = {g["id"]: g["coverage"]["status"] for g in r["glaciers"]}
    assert by_id == {"TEST-A": "full", "TEST-B": "partial", "TEST-D": "full"}
    assert client.post("/api/observations/glaciers", json={"geometry": {"type": "Point", "coordinates": [77, 32]}}).status_code == 400


def test_glacier_observations_classifies_asf_footprints(client, monkeypatch):
    """ASF is stubbed with synthetic scene footprints; verifies the exact-intersection filter, not the live ASF service."""
    products = [
        {"granuleId": "SYN_COVERS_A", "startTime": "2026-10-21T00:00:00Z", "geometry": mapping(box(76.9, 31.9, 77.2, 32.2))},
        {"granuleId": "SYN_BBOX_ONLY", "startTime": "2026-10-09T00:00:00Z", "geometry": mapping(box(77.06, 31.9, 77.5, 32.2))},   # in A's bbox query area? no overlap with A's outline
        {"granuleId": "SYN_NO_GEOM", "startTime": "2026-10-01T00:00:00Z", "geometry": None},
    ]
    monkeypatch.setattr(main, "_asf_goff_search", lambda *a, **k: {"count": 3, "products": products})
    r = client.get("/api/glaciers/TEST-A/observations").json()
    assert [o["granuleId"] for o in r["observations"]] == ["SYN_COVERS_A"]
    assert r["observations"][0]["coverage"]["status"] == "full"
    assert r["droppedNoCoverage"] == 1 and r["skippedNoGeometry"] == 1


def test_existing_asf_search_route_still_builds_polygon(monkeypatch):
    seen = {}
    def fake(polygon, start, end, maturity, max_results):
        seen.update(polygon=polygon, maturity=maturity, n=max_results)
        return {"count": 0, "products": []}
    monkeypatch.setattr(main, "_asf_goff_search", fake)
    c = TestClient(main.app)
    assert c.get("/api/asf/search?west=86.5&south=35.17&east=90.2&north=38.01&maturity=provisional").status_code == 200
    assert seen["polygon"].startswith("POLYGON((86.5 35.17,90.2 35.17,90.2 38.01") and seen["n"] == 30
    assert c.get("/api/asf/search?west=90&south=35&east=86&north=38").status_code == 400
