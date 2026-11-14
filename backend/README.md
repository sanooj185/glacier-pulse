# Glacier Pulse API

Local development API for uploading a NISAR GOFF HDF5 granule and generating a downsampled, georeferenced preview. The preview retains only pixels where `validDataMask == 3` and the displayed measurement layers are finite. This is a visualization preview, not a validated glacier-velocity product.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API health: `http://localhost:8000/api/health`
