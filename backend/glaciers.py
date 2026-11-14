"""Glacier inventory access for Glacier Pulse.

The inventory is a GeoJSON FeatureCollection of real glacier outlines (built from the
Randolph Glacier Inventory with ``scripts/build_glacier_inventory.py``). This module never
creates, guesses or approximates glacier geometry: if no inventory file is installed the
API reports that clearly and returns no glaciers.

Spatial maths
-------------
* Outlines and observation footprints are WGS84 lon/lat polygons.
* Areas and distances are computed after projecting to EPSG:6933 (WGS 84 / NSIDC EASE-Grid 2.0
  Global, an equal-area projection), so coverage percentages are area-faithful.
* ASF scene footprints are polygons whose edges are straight lines between listed vertices.
  Real radar footprint edges are geodesic, so glaciers lying within a few kilometres of a
  footprint edge are flagged ``nearEdge`` and their classification should be treated as
  approximate.
"""
from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import shapely
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

DEFAULT_PATH = Path(__file__).parent / "data" / "glaciers.geojson"
EQUAL_AREA_EPSG = 6933
NEAR_EDGE_KM = 5.0
FULL_COVERAGE_FRACTION = 0.9999

_to_equal_area = Transformer.from_crs("EPSG:4326", f"EPSG:{EQUAL_AREA_EPSG}", always_xy=True)


def _project(geom: BaseGeometry) -> BaseGeometry:
    def apply(coords):
        x, y = _to_equal_area.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])
    return shapely.transform(geom, apply)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class InventoryNotLoaded(RuntimeError):
    """Raised when no glacier outline file is installed."""


class GlacierInventory:
    def __init__(self, features: list[dict[str, Any]], metadata: dict[str, Any] | None = None):
        self.metadata = metadata or {}
        self._records: list[dict[str, Any]] = []
        self._by_id: dict[str, int] = {}
        self.repaired_geometries = 0
        geoms: list[BaseGeometry] = []
        for feature in features:
            props = dict(feature.get("properties") or {})
            gid = props.get("id")
            geom_json = feature.get("geometry")
            if not gid or not geom_json:
                continue
            geom = shape(geom_json)
            if geom.is_empty:
                continue
            if not geom.is_valid:
                geom = make_valid(geom)
                self.repaired_geometries += 1
            idx = len(self._records)
            self._by_id[str(gid)] = idx
            self._records.append({"props": props, "geom": geom, "norm_name": _normalize(props.get("name") or "")})
            geoms.append(geom)
        self._tree = STRtree(geoms) if geoms else None
        self._geoms = geoms

    # ------------------------------------------------------------------ loading
    @classmethod
    def from_file(cls, path: str | os.PathLike) -> "GlacierInventory":
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("type") != "FeatureCollection":
            raise ValueError("Glacier inventory must be a GeoJSON FeatureCollection.")
        return cls(data.get("features", []), data.get("metadata", {}))

    def __len__(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------ output
    def _summary(self, idx: int) -> dict[str, Any]:
        rec = self._records[idx]
        minx, miny, maxx, maxy = rec["geom"].bounds
        p = rec["props"]
        return {
            "id": p.get("id"), "name": p.get("name") or None, "areaKm2": p.get("area_km2"),
            "region": p.get("region"), "centroid": [p.get("cenlon"), p.get("cenlat")],
            "bbox": [minx, miny, maxx, maxy], "glacierType": p.get("glac_type"), "terminusType": p.get("term_type"),
        }

    def attribution(self) -> dict[str, Any]:
        return {k: self.metadata.get(k) for k in ("source", "version", "license", "citation", "url", "builtFrom")}

    def status(self) -> dict[str, Any]:
        return {"loaded": True, "glacierCount": len(self), "namedGlacierCount": sum(1 for r in self._records if r["norm_name"]),
                "repairedGeometries": self.repaired_geometries, "attribution": self.attribution()}

    # ------------------------------------------------------------------ queries
    def get(self, glacier_id: str) -> dict[str, Any] | None:
        idx = self._by_id.get(glacier_id)
        if idx is None:
            return None
        rec = self._records[idx]
        return {"type": "Feature", "id": glacier_id, "properties": {**rec["props"], **self._summary(idx)}, "geometry": mapping(rec["geom"])}

    def geometry(self, glacier_id: str) -> BaseGeometry | None:
        idx = self._by_id.get(glacier_id)
        return None if idx is None else self._records[idx]["geom"]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = _normalize(query)
        if len(q) < 2:
            return []
        scored: list[tuple[int, float, int]] = []
        for idx, rec in enumerate(self._records):
            gid_norm = _normalize(str(rec["props"].get("id")))
            name = rec["norm_name"]
            if name == q:
                rank = 0
            elif name.startswith(q):
                rank = 1
            elif name and q in name:
                rank = 2
            elif q in gid_norm:
                rank = 3
            else:
                continue
            scored.append((rank, -(rec["props"].get("area_km2") or 0.0), idx))
        scored.sort()
        return [self._summary(idx) for _, _, idx in scored[:limit]]

    def in_bbox(self, west: float, south: float, east: float, north: float, limit: int = 400,
                min_area_km2: float = 0.0, simplify_deg: float = 0.0) -> dict[str, Any]:
        """Return glacier outlines intersecting a bounding box (largest first, capped at ``limit``)."""
        if self._tree is None:
            return {"type": "FeatureCollection", "features": [], "truncated": False, "totalInView": 0}
        hits = self._tree.query(box(west, south, east, north), predicate="intersects")
        candidates = [int(i) for i in hits if (self._records[int(i)]["props"].get("area_km2") or 0.0) >= min_area_km2]
        candidates.sort(key=lambda i: -(self._records[i]["props"].get("area_km2") or 0.0))
        chosen = candidates[:limit]
        features = []
        for idx in chosen:
            rec = self._records[idx]
            geom = rec["geom"].simplify(simplify_deg, preserve_topology=True) if simplify_deg > 0 else rec["geom"]
            features.append({"type": "Feature", "id": rec["props"]["id"], "properties": self._summary(idx), "geometry": mapping(geom)})
        return {"type": "FeatureCollection", "features": features, "truncated": len(candidates) > limit, "totalInView": len(candidates)}

    # ------------------------------------------------------------------ footprint coverage
    @staticmethod
    def coverage(glacier: BaseGeometry, footprint: BaseGeometry) -> dict[str, Any]:
        """Classify how much of a glacier outline lies inside an observation footprint."""
        if not footprint.is_valid:
            footprint = make_valid(footprint)
        g_area = _project(glacier).area
        if g_area <= 0:
            return {"status": "none", "coveragePercent": 0.0, "intersectionKm2": 0.0, "glacierAreaKm2": 0.0, "nearEdge": False, "edgeDistanceKm": None}
        inter = glacier.intersection(footprint)
        i_area = _project(inter).area if not inter.is_empty else 0.0
        fraction = min(1.0, i_area / g_area)
        if fraction >= FULL_COVERAGE_FRACTION:
            status = "full"
        elif fraction > 0:
            status = "partial"
        else:
            status = "none"
        edge_km = _project(glacier).distance(_project(footprint.boundary)) / 1000.0
        return {"status": status, "coveragePercent": round(fraction * 100, 3), "intersectionKm2": round(i_area / 1e6, 4),
                "glacierAreaKm2": round(g_area / 1e6, 4), "nearEdge": bool(edge_km < NEAR_EDGE_KM),
                "edgeDistanceKm": round(edge_km, 3)}

    def intersecting(self, footprint: BaseGeometry, limit: int = 200) -> list[dict[str, Any]]:
        """Glaciers whose outlines truly intersect ``footprint`` (never proximity-based)."""
        if self._tree is None:
            return []
        if not footprint.is_valid:
            footprint = make_valid(footprint)
        out = []
        for i in self._tree.query(footprint, predicate="intersects"):
            idx = int(i)
            cov = self.coverage(self._records[idx]["geom"], footprint)
            if cov["status"] == "none":
                continue
            out.append({**self._summary(idx), "coverage": cov})
        out.sort(key=lambda r: -(r.get("areaKm2") or 0.0))
        return out[:limit]


# ---------------------------------------------------------------------- process-wide cache
_lock = threading.Lock()
_cache: dict[str, Any] = {"key": None, "inventory": None}


def inventory_path() -> Path:
    return Path(os.getenv("GLACIER_DATA_PATH") or DEFAULT_PATH)


def get_inventory() -> GlacierInventory:
    """Return the installed inventory or raise :class:`InventoryNotLoaded`."""
    path = inventory_path()
    if not path.is_file():
        raise InventoryNotLoaded(
            "No glacier outline inventory is installed on this API. Build one from the Randolph Glacier "
            "Inventory with scripts/build_glacier_inventory.py and deploy it as backend/data/glaciers.geojson "
            "(or set GLACIER_DATA_PATH)."
        )
    key = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
    with _lock:
        if _cache["key"] != key:
            _cache["inventory"] = GlacierInventory.from_file(path)
            _cache["key"] = key
        return _cache["inventory"]


def reset_cache() -> None:
    with _lock:
        _cache["key"] = None
        _cache["inventory"] = None


def footprint_from_geojson(geometry: dict[str, Any]) -> BaseGeometry:
    geom = shape(geometry)
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Footprint must be a Polygon or MultiPolygon.")
    return geom
