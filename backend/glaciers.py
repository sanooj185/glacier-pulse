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

import gzip
import json
import os
import re
import tempfile
import threading
import time
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


_FEATURES_KEY = re.compile(r'"features"\s*:\s*\[')


def _stream_feature_collection(handle, chunk_size: int = 1 << 20, header_limit: int = 8 << 20):
    """Return ``(metadata, feature_iterator)`` for a GeoJSON FeatureCollection without loading it whole.

    Returns ``None`` when the text before the ``"features"`` array is not a recognisable header.
    Features are decoded one by one with ``raw_decode`` and the consumed text is discarded.
    """
    buf = handle.read(chunk_size)
    match = _FEATURES_KEY.search(buf)
    while not match and buf and len(buf) < header_limit:
        more = handle.read(chunk_size)
        if not more:
            break
        buf += more
        match = _FEATURES_KEY.search(buf)
    if not match:
        return None
    header = buf[: match.start()].rstrip().rstrip(",")
    try:
        head = json.loads(header + "}")
    except ValueError:
        return None
    if not isinstance(head, dict) or head.get("type") != "FeatureCollection":
        return None
    metadata = head.get("metadata") or {}

    def iterate():
        decoder = json.JSONDecoder()
        text, pos, eof = buf[match.end():], 0, False

        def refill():
            nonlocal text, pos, eof
            more = handle.read(chunk_size)
            if not more:
                eof = True
                return
            text, pos = text[pos:] + more, 0

        while True:
            while pos < len(text) and text[pos] in " \t\r\n,":
                pos += 1
            if pos >= len(text):
                if eof:
                    raise ValueError("Glacier inventory ended before its feature list was closed.")
                refill()
                continue
            if text[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(text, pos)
            except json.JSONDecodeError:
                if eof:
                    raise
                refill()
                continue
            yield obj
            pos = end

    return metadata, iterate()


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
    def from_file(cls, path: str | os.PathLike, chunk_size: int = 1 << 20) -> "GlacierInventory":
        """Load an inventory, streaming features one at a time so peak memory stays near the final size.

        A plain ``json.load`` of a large GeoJSON builds every coordinate as a Python object first and
        can exhaust a small (512 MB) instance. If the file layout is not the expected
        ``{"type", "metadata", "features": [...]}`` we fall back to the whole-document parse.
        """
        path = Path(path)
        opener = gzip.open if path.suffix.lower() == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as handle:
            streamed = _stream_feature_collection(handle, chunk_size)
            if streamed is not None:
                metadata, features = streamed
                return cls(features, metadata)
        with opener(path, "rt", encoding="utf-8") as handle:
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
_state: dict[str, Any] = {"phase": "idle", "stage": None, "error": None, "errorType": None,
                          "startedAt": None, "finishedAt": None, "failedAt": None}
_warm: dict[str, Any] = {"thread": None}
_warm_lock = threading.Lock()
RETRY_COOLDOWN_SECONDS = 60
R2_SETTINGS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_OBJECT_KEY")


def r2_requested() -> bool:
    return bool(os.getenv("R2_ACCOUNT_ID") and os.getenv("R2_BUCKET_NAME") and os.getenv("R2_OBJECT_KEY"))


def inventory_path() -> Path:
    configured = os.getenv("GLACIER_DATA_PATH")
    if configured:
        return Path(configured)
    # Render's filesystem is ephemeral; cache the archive in /tmp for this instance.
    if r2_requested():
        return Path(tempfile.gettempdir()) / Path(os.getenv("R2_OBJECT_KEY", "glaciers.geojson.gz")).name
    return DEFAULT_PATH


def _download_inventory_from_r2(path: Path) -> None:
    missing = [key for key in R2_SETTINGS if not os.getenv(key)]
    if missing:
        raise InventoryNotLoaded("Private R2 storage is not fully configured on the API service. Missing settings: " + ", ".join(missing) + ".")
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise InventoryNotLoaded("R2 storage support is unavailable; redeploy the API dependencies.") from exc
    endpoint = f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto", config=Config(signature_version="s3v4"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".download")
    try:
        client.download_file(os.environ["R2_BUCKET_NAME"], os.environ["R2_OBJECT_KEY"], str(temporary))
        temporary.replace(path)
    except Exception as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise InventoryNotLoaded(
            f"Could not retrieve the glacier inventory from private R2 storage ({type(exc).__name__}). "
            "Check the bucket name, object key, and read-only API token."
        ) from exc


def _fail(stage: str | None, message: str, error_type: str) -> None:
    _state.update(phase="failed", stage=stage, error=message, errorType=error_type, failedAt=time.time(), finishedAt=time.time())


def get_inventory() -> GlacierInventory:
    """Return the installed inventory, downloading it from private R2 on first use if configured.

    Download and parse are serialised under one lock. Every outcome is recorded in ``_state`` so the
    API can say *why* the inventory is unavailable. A failed download or parse is not retried for
    ``RETRY_COOLDOWN_SECONDS`` so a bad file cannot trigger a re-download on every request.
    """
    with _lock:
        path = inventory_path()
        if (_state["phase"] == "failed" and _state["stage"] in ("download", "parse")
                and time.time() - (_state["failedAt"] or 0) < RETRY_COOLDOWN_SECONDS):
            raise InventoryNotLoaded(_state["error"])
        stage = "config"
        try:
            if not path.is_file():
                if not r2_requested() and not any(os.getenv(k) for k in R2_SETTINGS):
                    raise InventoryNotLoaded("No glacier outline inventory is installed. Configure private Cloudflare R2 storage or set GLACIER_DATA_PATH.")
                stage = "download"
                _state.update(phase="loading", stage="download", startedAt=_state["startedAt"] or time.time(), error=None, errorType=None)
                _download_inventory_from_r2(path)
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            if _cache["key"] != key:
                stage = "parse"
                _state.update(phase="loading", stage="parse", startedAt=_state["startedAt"] or time.time(), error=None, errorType=None)
                inventory = GlacierInventory.from_file(path)
                _cache["inventory"], _cache["key"] = inventory, key
            _state.update(phase="ready", stage="ready", error=None, errorType=None, finishedAt=time.time(),
                          fileMB=round(stat.st_size / 1e6, 1), glacierCount=len(_cache["inventory"]))
            return _cache["inventory"]
        except InventoryNotLoaded as exc:
            _fail(stage, str(exc), type(exc).__name__)
            raise
        except MemoryError as exc:
            message = ("The API ran out of memory while reading the glacier inventory. Build a smaller inventory "
                       "(raise --min-area-km2 or narrow --bbox) or use a larger instance.")
            _fail("parse", message, "MemoryError")
            raise InventoryNotLoaded(message) from exc
        except Exception as exc:
            message = (f"The glacier inventory file could not be read ({type(exc).__name__}). "
                       "Rebuild it with scripts/build_glacier_inventory.py and upload it again.")
            _fail(stage, message, type(exc).__name__)
            raise InventoryNotLoaded(message) from exc


def warm_up(wait: float = 0.0) -> None:
    """Start loading the inventory in a background thread (no-op if loading or loaded).

    ``wait`` blocks for at most that many seconds, so small local files can still be ready on the
    first request while a large download/parse never blocks the API.
    """
    with _warm_lock:
        thread = _warm["thread"]
        if thread is None or not thread.is_alive():
            if _state["phase"] not in ("ready", "failed"):
                _state.update(phase="loading", stage=_state["stage"] or "queued", startedAt=time.time(), error=None, errorType=None)

                def run():
                    try:
                        get_inventory()
                    except Exception:
                        pass  # the outcome is recorded in _state

                thread = threading.Thread(target=run, name="glacier-inventory-warmup", daemon=True)
                _warm["thread"] = thread
                thread.start()
    thread = _warm["thread"]
    if wait > 0 and thread is not None:
        thread.join(timeout=wait)


def is_loading() -> bool:
    return _state["phase"] == "loading"


def load_state() -> dict[str, Any]:
    started = _state.get("startedAt")
    return {"phase": _state["phase"], "stage": _state["stage"], "error": _state["error"], "errorType": _state["errorType"],
            "elapsedSeconds": round(time.time() - started, 1) if started and _state["phase"] == "loading" else None}


def diagnostics() -> dict[str, Any]:
    """Safe-to-share facts about why the inventory may be unavailable. Never includes setting values."""
    try:
        import boto3  # noqa: F401
        boto3_ok = True
    except ImportError:
        boto3_ok = False
    path = inventory_path()
    local = {"exists": path.is_file(), "sizeMB": round(path.stat().st_size / 1e6, 1) if path.is_file() else None}
    try:
        import resource
        peak = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # KB on Linux
    except Exception:
        peak = None
    return {"phase": _state["phase"], "stage": _state["stage"], "errorType": _state["errorType"],
            "r2SettingsPresent": {k: bool(os.getenv(k)) for k in R2_SETTINGS},
            "missingR2Settings": [k for k in R2_SETTINGS if not os.getenv(k)],
            "dataPathOverride": bool(os.getenv("GLACIER_DATA_PATH")),
            "boto3Installed": boto3_ok, "localFile": local, "peakMemoryMB": peak}


def reset_cache() -> None:
    with _lock:
        _cache["key"] = None
        _cache["inventory"] = None
        _state.update(phase="idle", stage=None, error=None, errorType=None, startedAt=None, finishedAt=None, failedAt=None)
    with _warm_lock:
        thread = _warm["thread"]
        _warm["thread"] = None
    if thread is not None and thread.is_alive():
        thread.join(timeout=5)


def footprint_from_geojson(geometry: dict[str, Any]) -> BaseGeometry:
    geom = shape(geometry)
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Footprint must be a Polygon or MultiPolygon.")
    return geom
