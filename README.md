# Glacier Pulse — deploy-ready starter

React/Vite frontend + FastAPI backend. Includes ASF NISAR GOFF catalog search and upload/preview of a GOFF HDF5 file.

## Deploy both services on Render

1. Put this entire `glacier-pulse-app` folder in a GitHub repository (the `render.yaml` file must be at the repository root).
2. In Render, choose **New → Blueprint**, connect the GitHub repository, and deploy the Blueprint. Render reads `render.yaml` and creates:
   - `glacier-pulse-api` — FastAPI service
   - `glacier-pulse-web` — public static frontend
3. Wait for both services to finish deploying. Open the `glacier-pulse-web` URL shown in Render.
4. Check the API health at `https://YOUR-API.onrender.com/api/health` and API docs at `https://YOUR-API.onrender.com/docs`.

The Blueprint wires the frontend's `VITE_API_URL` to the API hostname automatically. The frontend adds HTTPS. The backend allows browser calls from the hosted frontend.

## Local development (Windows PowerShell)

Backend (Python 3.11 recommended):

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173`. For local development the frontend defaults to `http://localhost:8000`.

## Live data workflow

- Open **NISAR Radar Lab** and search the ASF catalog using the prefilled Himalayan example bounding box. This is a regional example footprint, not a verified outline for Samudra Tapu, Bara Shigri, or Gangotri.
- To preview a granule, upload a NISAR GOFF `.h5`/`.hdf5` file. The API processes the upload temporarily; it does not retain it as a permanent archive.
- ASF catalog search returns metadata. The **Stream preview from ASF** action resolves a selected GOFF granule through Earthdata and opens it over authenticated HTTPS for a downsampled preview; visitors do not upload the full granule. Configure `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` as private backend environment variables. This is a preview path, not a persistent processing/archive pipeline.

## Scientific limitations

The preview displays georeferenced GOFF along-track/slant-range offsets and quality layers. These radar-coordinate offsets are not geographic east/north displacement or glacier velocity. Do not interpret them as melt, retreat, or mass loss. Glacier inventory, validated velocity transformation, multi-date comparison, persistent storage, AI API integration and report export remain future work.

## Hosting notes

Render free web services can spin down after inactivity, so the first request after a quiet period may be slow. Large HDF5 uploads may exceed free-instance memory/request limits; the catalog search is the lighter live-data feature.

## Glacier-aware map (Glacier Explorer)

The **Glacier Explorer** page shows real glacier outlines from the Randolph Glacier Inventory (RGI), a name/ID
search, clickable glacier profiles, NISAR GOFF observation footprints that truly intersect the selected glacier,
and the grid extent of any GOFF granule loaded in the Radar Lab.

Outlines are **not bundled**. Download RGI (NSIDC-0770 v7, or GLIMS RGI 6.0), then build the inventory file as
described in `backend/data/README.md` and deploy `backend/data/glaciers.geojson` with the API. Until then the
Explorer says so and draws no glaciers.

New API routes: `GET /api/glaciers/status`, `/api/glaciers?west&south&east&north`, `/api/glaciers/search?q=`,
`/api/glaciers/{id}`, `/api/glaciers/{id}/observations`, `POST /api/observations/glaciers`.

How coverage is computed: footprints and outlines are intersected as polygons and areas are measured in an
equal-area projection (EPSG:6933). "Full" means at least 99.99 % of the outline lies inside the catalogue footprint;
"partial" means some but not all; products with no overlap are dropped. Proximity never counts as coverage.
Catalogue footprints have straight edges between vertices while true radar edges are geodesic, so glaciers within
5 km of a footprint edge are flagged as approximate. Catalogue coverage says nothing about whether valid,
high-quality offset pixels exist over the glacier.

Backend tests: `cd backend && pip install pytest httpx && python -m pytest tests`. The tests use synthetic
squares as geometry fixtures to verify the spatial logic; they are not glacier data.

### Glacier-only raster view (Radar Lab)

`/api/goff/preview` and `/api/asf/stream-preview` now return a `glacierMask` aligned with the preview grid, plus
`metadata.glacierMask` describing the rule. A sample is marked only if its **own centre lies inside** a Randolph
Glacier Inventory outline (outlines are projected into the granule's CRS and tested there; nothing is buffered).
The Radar Lab shows only those samples by default and has a switch to show every finite sample. Without an installed
inventory the preview is unchanged and the UI says the filter is unavailable.

The raster is also drawn sample by sample at each sample's own georeferenced position instead of being stretched
over a lat/lon bounding box. For a UTM granule this removes the grid-convergence rotation error (about 1.4° for a
frame ~2.4° from the zone's central meridian, i.e. several hundred metres at the frame corners).

Limits: the preview is decimated from 80 m pixels, so each drawn block is one sampled pixel at preview spacing.
Inventory outlines are not today's glacier extent. Masking removes water and bare ground from view; it does not make
the remaining offsets quality-controlled or convert them into glacier velocity.
