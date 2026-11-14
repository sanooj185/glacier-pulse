from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import h5py, numpy as np, tempfile, os, shutil
from pyproj import Transformer

app = FastAPI(title="Glacier Pulse API", version="0.1.0")
# Public API: allow the separately hosted static frontend to call this API.
# No cookie-based authentication is used by this starter.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

@app.get('/api/health')
def health(): return {"status":"ok", "service":"Glacier Pulse API"}



@app.get('/api/asf/search')
def asf_search_goff(west: float, south: float, east: float, north: float, start: str = None, end: str = None, maturity: str = None, max_results: int = 30):
    """Search ASF for NISAR GOFF granules intersecting a user-supplied bbox."""
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, 'Enter a valid bounding box: west < east and south < north.')
    if max_results < 1 or max_results > 100:
        raise HTTPException(400, 'max_results must be between 1 and 100.')
    try:
        import asf_search as asf
    except ImportError:
        raise HTTPException(503, 'ASF search dependency is not installed. Run pip install asf_search.')

    wkt = f'POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))'
    params = {'dataset': 'NISAR', 'processingLevel': 'GOFF', 'intersectsWith': wkt, 'maxResults': max_results}
    if start: params['start'] = start
    if end: params['end'] = end
    if maturity: params['dataMaturity'] = maturity.upper()
    try:
        results = asf.search(**params)
        products = []
        for product in results:
            try:
                feature = product.geojson()
                props = feature.get('properties', {})
                products.append({
                    'granuleId': props.get('granuleName') or props.get('fileName') or props.get('sceneName') or props.get('productName'),
                    'fileName': props.get('fileName'),
                    'startTime': props.get('startTime') or props.get(' acquisitionDate'),
                    'stopTime': props.get('stopTime'),
                    'processingLevel': props.get('processingLevel'),
                    'dataMaturity': props.get('dataMaturity'),
                    'flightDirection': props.get('flightDirection'),
                    'pathNumber': props.get('pathNumber'),
                    'bytes': props.get('bytes'),
                    'url': props.get('url'),
                    'geometry': feature.get('geometry'),
                })
            except Exception:
                continue
        return {'count': len(products), 'query': params, 'products': products, 'source': 'ASF DAAC'}
    except Exception as e:
        raise HTTPException(502, f'ASF search failed: {e}')


@app.post('/api/goff/preview')
async def goff_preview(file: UploadFile = File(...), layer: str = 'layer1', max_dim: int = 420):
    if not file.filename.lower().endswith(('.h5','.hdf5')):
        raise HTTPException(400, 'Upload a NISAR GOFF .h5 or .hdf5 file.')
    if layer not in ('layer1','layer2','layer3'):
        raise HTTPException(400, 'Layer must be layer1, layer2 or layer3.')
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.h5')
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.flush()
        if tmp.tell() > 2_000_000_000: raise HTTPException(413, 'File exceeds the 2 GB demo upload limit.')
        tmp.close()
        with h5py.File(tmp.name, 'r') as f:
            root='science/LSAR/GOFF/grids/frequencyA/pixelOffsets/HH/'
            lp=root+layer+'/'
            required=[root+'validDataMask', lp+'alongTrackOffset', lp+'slantRangeOffset', lp+'correlationSurfacePeak', lp+'snr', lp+'xCoordinates', lp+'yCoordinates']
            missing=[p for p in required if p not in f]
            if missing: raise HTTPException(422, 'This HDF5 file is missing expected GOFF datasets: '+', '.join(missing))
            mask_ds=f[root+'validDataMask']; h,w=mask_ds.shape
            step=max(1, int(np.ceil(max(h,w)/max_dim)))
            mask=mask_ds[::step,::step]
            along=f[lp+'alongTrackOffset'][::step,::step]
            slant=f[lp+'slantRangeOffset'][::step,::step]
            corr=f[lp+'correlationSurfacePeak'][::step,::step]
            snr=f[lp+'snr'][::step,::step]
            x=f[lp+'xCoordinates'][::step]; y=f[lp+'yCoordinates'][::step]
            proj=f[lp+'projection']
            epsg=proj.attrs.get('epsg_code', 32645)
            try: epsg=int(epsg)
            except Exception: epsg=32645
            xx,yy=np.meshgrid(x,y)
            transformer=Transformer.from_crs(f'EPSG:{epsg}','EPSG:4326',always_xy=True)
            lon,lat=transformer.transform(xx,yy)
            valid=(mask==3)&np.isfinite(along)&np.isfinite(slant)&np.isfinite(corr)&np.isfinite(snr)
            def clean(a):
                z=np.asarray(a,dtype=float); z[~valid]=np.nan
                return [[None if not np.isfinite(v) else round(float(v),3) for v in row] for row in z]
            def attr_text(path, key, default=''):
                try:
                    v=f[path].attrs[key]
                    return v.decode() if isinstance(v,bytes) else str(v)
                except Exception: return default
            ident='science/LSAR/GOFF/identification/'
            metadata={
                'granuleId':attr_text(ident,'granuleId',file.filename),
                'referenceStart':attr_text(ident,'referenceZeroDopplerStartTime'),
                'secondaryStart':attr_text(ident,'secondaryZeroDopplerStartTime'),
                'trackNumber':attr_text(ident,'trackNumber'),
                'orbitPassDirection':attr_text(ident,'orbitPassDirection'),
                'lookDirection':attr_text(ident,'lookDirection'),
                'epsg':epsg,'rows':h,'cols':w,'previewRows':len(y),'previewCols':len(x),'downsampleStep':step,
                'maskValidPercent':round(100*float(np.count_nonzero(mask==3))/mask.size,2),
                'previewValidPercent':round(100*float(valid.sum())/valid.size,2),
                'offsetUnits':attr_text(lp+'alongTrackOffset','units','m'),
            }
            return JSONResponse({'metadata':metadata,'longitude':lon.tolist(),'latitude':lat.tolist(),'alongTrack':clean(along),'slantRange':clean(slant),'correlation':clean(corr),'snr':clean(snr)})
    except HTTPException: raise
    except Exception as e: raise HTTPException(422, f'Could not read this GOFF file: {e}')
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass
