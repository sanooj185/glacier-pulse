# Glacier inventory data

Place `glaciers.geojson` here (or point `GLACIER_DATA_PATH` at it). The API serves **only** outlines from this
file — it never invents or approximates glacier boundaries. If the file is missing, `/api/glaciers/status`
reports `loaded: false` and the glacier endpoints return 503.

Build it from a real Randolph Glacier Inventory download:

```bash
pip install -r scripts/requirements.txt
python scripts/build_glacier_inventory.py RGI2000-v7.0-G-14_south_asia_west.zip \
    --min-area-km2 0.5 --bbox 70 25 100 40 --output backend/data/glaciers.geojson
```

Keep the file modest (tens of MB at most) — the API loads it into memory and builds a spatial index at first use.
On Render's free tier (512 MB RAM) use `--min-area-km2` and `--bbox` to limit the extract.
