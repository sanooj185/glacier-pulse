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
- ASF catalog search returns metadata. Downloading full granules requires NASA Earthdata Login; automatic product download is not included yet.

## Scientific limitations

The preview displays georeferenced GOFF along-track/slant-range offsets and quality layers. These radar-coordinate offsets are not geographic east/north displacement or glacier velocity. Do not interpret them as melt, retreat, or mass loss. Glacier inventory, validated velocity transformation, multi-date comparison, persistent storage, AI API integration and report export remain future work.

## Hosting notes

Render free web services can spin down after inactivity, so the first request after a quiet period may be slow. Large HDF5 uploads may exceed free-instance memory/request limits; the catalog search is the lighter live-data feature.
