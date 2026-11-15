from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import h5py, numpy as np, os, re, shutil, tempfile
from pyproj import Transformer
import glaciers

app = FastAPI(title="Glacier Pulse API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
ROOT = "science/LSAR/GOFF/grids/frequencyA/pixelOffsets/HH/"

class StreamRequest(BaseModel):
    granuleId: str
    layer: str = "layer1"
    maxDim: int = 420
    maturity: str | None = None

def attr_text(f, path, key, default=""):
    try:
        value = f[path].attrs[key]
        return value.decode() if isinstance(value, bytes) else str(value)
    except Exception:
        return default

def make_preview(f, filename, layer="layer1", max_dim=420):
    if layer not in ("layer1", "layer2", "layer3") or not 64 <= max_dim <= 600:
        raise HTTPException(400, "Invalid layer or preview dimensions.")
    lp = ROOT + layer + "/"
    mask_path = "science/LSAR/GOFF/grids/frequencyA/pixelOffsets/mask"
    legacy_mask_path = ROOT + "validDataMask"
    required = [lp+"alongTrackOffset", lp+"slantRangeOffset", lp+"correlationSurfacePeak", lp+"xCoordinates", lp+"yCoordinates", lp+"projection"]
    missing = [p for p in required if p not in f]
    if missing:
        # Return a compact HDF5 inventory to diagnose product-version differences.
        inventory = []
        def collect(name, obj):
            if isinstance(obj, h5py.Dataset) and any(token in name for token in ("pixelOffsets", "xCoordinates", "yCoordinates", "snr", "projection", "mask")):
                inventory.append(name)
        f.visititems(collect)
        raise HTTPException(422, "GOFF structure differs from expected layout. Missing: " + ", ".join(missing) + ". Available relevant datasets: " + ", ".join(inventory[:45]))
    along_ds = f[lp+"alongTrackOffset"]
    height, width = along_ds.shape[-2:]
    step = max(1, int(np.ceil(max(height, width) / max_dim)))
    along = along_ds[::step, ::step]
    slant = f[lp+"slantRangeOffset"][::step, ::step]
    corr = f[lp+"correlationSurfacePeak"][::step, ::step]
    snr = f[lp+"snr"][::step, ::step] if lp+"snr" in f else np.full(along.shape, np.nan)
    x, y = f[lp+"xCoordinates"][::step], f[lp+"yCoordinates"][::step]
    # Standard GOFF places a product-level bit mask at pixelOffsets/mask.
    # Older/pre-release granules may instead expose validDataMask under HH.
    # Do not interpret the standard bit mask as the legacy 0/1/2/3 mask;
    # finite data and HDF5 fill values determine preview validity here.
    mask_valid = None
    if legacy_mask_path in f:
        mask_valid = f[legacy_mask_path][::step, ::step] == 3
    try: epsg = int(f[lp+"projection"].attrs.get("epsg_code", 32645))
    except (TypeError, ValueError): epsg = 32645
    xx, yy = np.meshgrid(x, y)
    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(xx, yy)
    valid = np.isfinite(along) & np.isfinite(slant) & np.isfinite(corr)
    if mask_valid is not None:
        valid &= mask_valid
    def clean(a):
        z = np.asarray(a, dtype=float).copy()
        z[~valid] = np.nan
        return [[None if not np.isfinite(v) else round(float(v), 3) for v in row] for row in z]
    ident = "science/LSAR/GOFF/identification/"
    metadata = {
        "granuleId": attr_text(f, ident, "granuleId", filename),
        "referenceStart": attr_text(f, ident, "referenceZeroDopplerStartTime"),
        "secondaryStart": attr_text(f, ident, "secondaryZeroDopplerStartTime"),
        "trackNumber": attr_text(f, ident, "trackNumber"),
        "orbitPassDirection": attr_text(f, ident, "orbitPassDirection"),
        "lookDirection": attr_text(f, ident, "lookDirection"),
        "epsg": epsg, "rows": int(height), "cols": int(width),
        "previewRows": int(len(y)), "previewCols": int(len(x)), "downsampleStep": int(step),
        "maskSource": "legacy validDataMask (value 3)" if mask_valid is not None else ("standard pixelOffsets/mask present; not decoded in this preview" if mask_path in f else "no mask dataset found"),
        "previewValidPercent": round(100 * float(valid.sum()) / valid.size, 2),
        "offsetUnits": attr_text(f, lp+"alongTrackOffset", "units", "m"),
        "accessMethod": "Earthdata-authenticated HTTPS streaming"
    }
    return {"metadata": metadata, "longitude": lon.tolist(), "latitude": lat.tolist(),
            "alongTrack": clean(along), "slantRange": clean(slant), "correlation": clean(corr), "snr": clean(snr)}

@app.get("/api/health")
def health():
    return {"status":"ok", "service":"Glacier Pulse API"}

def _asf_goff_search(polygon: str, start=None, end=None, maturity=None, max_results: int = 30):
    """Query ASF for NISAR GOFF products intersecting a WKT polygon (shared by the catalogue and glacier routes)."""
    try:
        import asf_search as asf
    except ImportError:
        raise HTTPException(503, "ASF search dependency is not installed.")
    params = {"dataset":"NISAR", "processingLevel":"GOFF", "intersectsWith":polygon, "maxResults":max_results}
    if start: params["start"] = start
    if end: params["end"] = end
    if maturity: params["dataMaturity"] = maturity.upper()
    try:
        results = asf.search(**params)
        products = []
        for product in results:
            try:
                feature = product.geojson()
                p = feature.get("properties", {})
                products.append({"granuleId":p.get("granuleName") or p.get("fileName") or p.get("sceneName") or p.get("productName"),
                    "fileName":p.get("fileName"), "startTime":p.get("startTime") or p.get("acquisitionDate"),
                    "stopTime":p.get("stopTime"), "processingLevel":p.get("processingLevel"), "dataMaturity":p.get("dataMaturity"),
                    "flightDirection":p.get("flightDirection"), "pathNumber":p.get("pathNumber"), "bytes":p.get("bytes"),
                    "url":p.get("url"), "geometry":feature.get("geometry")})
            except Exception: continue
        return {"count":len(products), "query":params, "products":products, "source":"ASF DAAC"}
    except Exception as exc:
        raise HTTPException(502, f"ASF search failed: {exc}")

@app.get("/api/asf/search")
def asf_search_goff(west: float, south: float, east: float, north: float, start: str = None, end: str = None, maturity: str = None, max_results: int = 30):
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, "Enter a valid bounding box: west < east and south < north.")
    if max_results < 1 or max_results > 100:
        raise HTTPException(400, "max_results must be between 1 and 100.")
    polygon = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
    return _asf_goff_search(polygon, start, end, maturity, max_results)

# ---------------------------------------------------------------------------
# Glacier inventory (real outlines only; see glaciers.py and the build script)
# ---------------------------------------------------------------------------
def _inventory():
    try:
        return glaciers.get_inventory()
    except glaciers.InventoryNotLoaded as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Glacier inventory could not be read: {type(exc).__name__}")

class FootprintRequest(BaseModel):
    geometry: dict
    limit: int = 200

@app.get("/api/glaciers/status")
def glacier_status():
    try:
        return glaciers.get_inventory().status()
    except glaciers.InventoryNotLoaded as exc:
        return {"loaded": False, "glacierCount": 0, "message": str(exc)}

@app.get("/api/glaciers/search")
def glacier_search(q: str, limit: int = 20):
    if not 1 <= limit <= 50:
        raise HTTPException(400, "limit must be between 1 and 50.")
    inv = _inventory()
    return {"query": q, "results": inv.search(q, limit), "attribution": inv.attribution()}

@app.get("/api/glaciers")
def glacier_outlines(west: float, south: float, east: float, north: float, limit: int = 400, min_area_km2: float = 0.0, simplify: float = 0.0):
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, "Enter a valid bounding box: west < east and south < north.")
    if not 1 <= limit <= 2000 or min_area_km2 < 0 or not 0 <= simplify <= 0.05:
        raise HTTPException(400, "Invalid limit, min_area_km2 or simplify value.")
    inv = _inventory()
    result = inv.in_bbox(west, south, east, north, limit, min_area_km2, simplify)
    result["attribution"] = inv.attribution()
    return result

@app.get("/api/glaciers/{glacier_id}")
def glacier_profile(glacier_id: str):
    inv = _inventory()
    feature = inv.get(glacier_id)
    if not feature:
        raise HTTPException(404, f"Glacier {glacier_id} is not in the installed inventory.")
    return {"glacier": feature, "attribution": inv.attribution()}

@app.get("/api/glaciers/{glacier_id}/observations")
def glacier_observations(glacier_id: str, start: str = None, end: str = None, maturity: str = None, max_results: int = 50):
    """NISAR GOFF products whose footprints truly intersect this glacier outline, with coverage."""
    if not 1 <= max_results <= 100:
        raise HTTPException(400, "max_results must be between 1 and 100.")
    inv = _inventory()
    geom = inv.geometry(glacier_id)
    if geom is None:
        raise HTTPException(404, f"Glacier {glacier_id} is not in the installed inventory.")
    west, south, east, north = geom.bounds
    # ASF narrows by the glacier's bounding box; exact coverage is computed here against the outline.
    polygon = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
    catalogue = _asf_goff_search(polygon, start, end, maturity, max_results)
    observations, dropped, skipped = [], 0, 0
    for product in catalogue["products"]:
        if not product.get("geometry"):
            skipped += 1
            continue
        try:
            footprint = glaciers.footprint_from_geojson(product["geometry"])
            coverage = glaciers.GlacierInventory.coverage(geom, footprint)
        except Exception:
            skipped += 1
            continue
        if coverage["status"] == "none":
            dropped += 1
            continue
        observations.append({**product, "coverage": coverage})
    observations.sort(key=lambda p: p.get("startTime") or "", reverse=True)
    return {"glacierId": glacier_id, "count": len(observations), "droppedNoCoverage": dropped, "skippedNoGeometry": skipped,
            "observations": observations, "source": "ASF DAAC catalogue footprints",
            "note": "Coverage compares the catalogue scene footprint with the glacier outline. It does not mean the GOFF raster has valid, high-quality pixels over the glacier."}

@app.post("/api/observations/glaciers")
def glaciers_in_footprint(request: FootprintRequest):
    """Glaciers whose outlines truly intersect an observation footprint (GeoJSON Polygon/MultiPolygon)."""
    if not 1 <= request.limit <= 1000:
        raise HTTPException(400, "limit must be between 1 and 1000.")
    inv = _inventory()
    try:
        footprint = glaciers.footprint_from_geojson(request.geometry)
    except Exception as exc:
        raise HTTPException(400, f"Invalid footprint geometry: {exc}")
    found = inv.intersecting(footprint, request.limit)
    return {"count": len(found), "glaciers": found, "attribution": inv.attribution()}

@app.post("/api/asf/stream-preview")
def stream_asf_preview(request: StreamRequest):
    """Stream the selected GOFF HDF5 product over authenticated HTTPS; do not save the full granule."""
    granule_id = request.granuleId.strip()
    if not re.fullmatch(r"NISAR_L2_(?:PR|UR)_GOFF_[A-Z0-9_]+(?:\.h5)?", granule_id):
        raise HTTPException(400, "Select a valid NISAR L2 GOFF granule from ASF.")
    if request.layer not in ("layer1", "layer2", "layer3") or not 64 <= request.maxDim <= 600:
        raise HTTPException(400, "Invalid layer or preview dimensions.")
    if not os.getenv("EARTHDATA_USERNAME") or not os.getenv("EARTHDATA_PASSWORD"):
        raise HTTPException(503, "Earthdata credentials are not configured on the API service.")
    try:
        import earthaccess
    except ImportError:
        raise HTTPException(503, "Earthdata streaming support is not installed. Redeploy the API.")
    try:
        earthaccess.login(strategy="environment", persist=False)
    except Exception:
        raise HTTPException(401, "Earthdata authentication failed. Check the private Render environment variables.")
    maturity_to_collection = {
        "PROVISIONAL": "NISAR_L2_GOFF_PROVISIONAL_V1",
        "BETA": "NISAR_L2_GOFF_BETA_V1",
        "VALIDATED": "NISAR_L2_GOFF_V1",
    }
    # UR granules live in the separate NISAR Urgent Response Level 2 collection,
    # not in the normal GOFF maturity collections.
    is_urgent_response = "_UR_GOFF_" in granule_id
    if is_urgent_response:
        maturity_to_collection["URGENT_RESPONSE"] = "NISAR_UR_L2"
        maturities = ["URGENT_RESPONSE"]
    else:
        requested_maturity = (request.maturity or "").strip().upper()
        # ASF metadata labels can differ between catalogue versions. Only use a
        # single collection for the three recognised CMR maturity values;
        # otherwise search all GOFF maturity collections rather than returning
        # a misleading "not found" without searching anything.
        maturities = [requested_maturity] if requested_maturity in maturity_to_collection else ["PROVISIONAL", "BETA", "VALIDATED"]
    # earthaccess exposes CMR readable_granule_name as the granule_name argument.
    target_id = granule_id.removesuffix(".h5")
    granules = []
    searched = []
    try:
        for maturity in maturities:
            collection = maturity_to_collection.get(maturity)
            if not collection:
                continue
            searched.append(collection)
            for identifier in (target_id, target_id + ".h5"):
                granules = earthaccess.search_data(
                    short_name=collection,
                    granule_name=identifier,
                    cloud_hosted=True,
                    count=5,
                )
                if granules:
                    break
            if granules:
                break
    except Exception as exc:
        raise HTTPException(502, f"Earthdata catalog search failed: {type(exc).__name__}. Check API logs.")
    if not granules:
        raise HTTPException(
            404,
            f"Granule {granule_id} was not found in Earthdata CMR. Searched collections: {', '.join(searched)}. Confirm the ASF ID matches the CMR granule ID.",
        )
    remote_files = []
    try:
        remote_files = earthaccess.open(granules, open_kwargs={"block_size":8*1024*1024})
        if not remote_files: raise RuntimeError("Earthdata returned no readable HTTPS stream.")
        with h5py.File(remote_files[0], "r") as hdf:
            return JSONResponse(make_preview(hdf, granule_id, request.layer, request.maxDim))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Could not stream this GOFF granule: {type(exc).__name__}: {str(exc)[:240]}")
    finally:
        for remote_file in remote_files:
            try: remote_file.close()
            except Exception: pass

@app.post("/api/goff/preview")
async def goff_preview(file: UploadFile = File(...), layer: str = "layer1", max_dim: int = 420):
    """Legacy local-upload preview; use ASF streaming where possible."""
    if not file.filename.lower().endswith((".h5", ".hdf5")):
        raise HTTPException(400, "Upload a NISAR GOFF .h5 or .hdf5 file.")
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".h5")
    try:
        shutil.copyfileobj(file.file, temporary)
        temporary.flush()
        if temporary.tell() > 2_000_000_000:
            raise HTTPException(413, "File exceeds the 2 GB demo upload limit.")
        temporary.close()
        with h5py.File(temporary.name, "r") as hdf:
            return JSONResponse(make_preview(hdf, file.filename, layer, max_dim))
    except HTTPException: raise
    except Exception as exc: raise HTTPException(422, f"Could not read this GOFF file: {exc}")
    finally:
        try:
            temporary.close()
            os.unlink(temporary.name)
        except Exception: pass
