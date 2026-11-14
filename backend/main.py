from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import h5py, numpy as np, os, re, shutil, tempfile
from pyproj import Transformer

app = FastAPI(title="Glacier Pulse API", version="0.2.0")
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
    required = [ROOT+"validDataMask", lp+"alongTrackOffset", lp+"slantRangeOffset", lp+"correlationSurfacePeak", lp+"snr", lp+"xCoordinates", lp+"yCoordinates", lp+"projection"]
    missing = [p for p in required if p not in f]
    if missing:
        raise HTTPException(422, "Missing expected GOFF datasets: " + ", ".join(missing))
    mask_ds = f[ROOT+"validDataMask"]
    height, width = mask_ds.shape
    step = max(1, int(np.ceil(max(height, width) / max_dim)))
    mask = mask_ds[::step, ::step]
    along = f[lp+"alongTrackOffset"][::step, ::step]
    slant = f[lp+"slantRangeOffset"][::step, ::step]
    corr = f[lp+"correlationSurfacePeak"][::step, ::step]
    snr = f[lp+"snr"][::step, ::step]
    x, y = f[lp+"xCoordinates"][::step], f[lp+"yCoordinates"][::step]
    try: epsg = int(f[lp+"projection"].attrs.get("epsg_code", 32645))
    except (TypeError, ValueError): epsg = 32645
    xx, yy = np.meshgrid(x, y)
    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(xx, yy)
    valid = (mask == 3) & np.isfinite(along) & np.isfinite(slant) & np.isfinite(corr) & np.isfinite(snr)
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
        "maskValidPercent": round(100 * float(np.count_nonzero(mask == 3)) / mask.size, 2),
        "previewValidPercent": round(100 * float(valid.sum()) / valid.size, 2),
        "offsetUnits": attr_text(f, lp+"alongTrackOffset", "units", "m"),
        "accessMethod": "Earthdata-authenticated HTTPS streaming"
    }
    return {"metadata": metadata, "longitude": lon.tolist(), "latitude": lat.tolist(),
            "alongTrack": clean(along), "slantRange": clean(slant), "correlation": clean(corr), "snr": clean(snr)}

@app.get("/api/health")
def health():
    return {"status":"ok", "service":"Glacier Pulse API"}

@app.get("/api/asf/search")
def asf_search_goff(west: float, south: float, east: float, north: float, start: str = None, end: str = None, maturity: str = None, max_results: int = 30):
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, "Enter a valid bounding box: west < east and south < north.")
    if max_results < 1 or max_results > 100:
        raise HTTPException(400, "max_results must be between 1 and 100.")
    try:
        import asf_search as asf
    except ImportError:
        raise HTTPException(503, "ASF search dependency is not installed.")
    polygon = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
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
    maturities = [request.maturity.upper()] if request.maturity else ["PROVISIONAL", "BETA", "VALIDATED"]
    # ASF's granuleName is a human-readable producer granule ID. CMR exposes
    # this as readable_granule_name / producer_granule_id, not granule_name.
    target_id = granule_id.removesuffix(".h5")
    granules = []
    searched = []
    try:
        for maturity in maturities:
            collection = maturity_to_collection.get(maturity)
            if not collection:
                continue
            searched.append(collection)
            # Try CMR's documented identifier fields. Some catalog records
            # include the .h5 suffix and some do not.
            for identifier in (target_id, target_id + ".h5"):
                try:
                    granules = earthaccess.search_data(
                        short_name=collection,
                        readable_granule_name=identifier,
                        cloud_hosted=True,
                        count=5,
                    )
                except Exception:
                    granules = []
                if not granules:
                    try:
                        granules = earthaccess.search_data(
                            short_name=collection,
                            producer_granule_id=identifier,
                            cloud_hosted=True,
                            count=5,
                        )
                    except Exception:
                        granules = []
                if granules:
                    break
            if granules:
                break
    except Exception:
        raise HTTPException(502, "Earthdata catalog search failed while resolving this ASF granule.")
    if not granules:
        raise HTTPException(
            404,
            f"Granule {granule_id} was not found in Earthdata CMR. Searched collections: {', '.join(searched)}. The ASF result ID may differ from the CMR producer granule ID.",
        )
    remote_files = []
    try:
        remote_files = earthaccess.open(granules, access="https", open_kwargs={"block_size":8*1024*1024})
        if not remote_files: raise RuntimeError("Earthdata returned no readable HTTPS stream.")
        with h5py.File(remote_files[0], "r") as hdf:
            return JSONResponse(make_preview(hdf, granule_id, request.layer, request.maxDim))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Could not stream this GOFF granule: {type(exc).__name__}. Check API logs.")
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
