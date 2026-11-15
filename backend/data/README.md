# Glacier inventory data

The API serves only real glacier outlines from `glaciers.geojson`. It never invents or approximates glacier geometry. Until this file is installed, `/api/glaciers/status` reports `loaded: false`.

## Build from official RGI 7.0 data

Download the official **RGI 7.0 Glacier Product** shapefile ZIPs for Region 14 (South Asia West) and/or Region 15 (South Asia East) from the [NSIDC dataset page](https://nsidc.org/data/nsidc-0770/versions/7). These two regions cover the western and central/eastern Himalayan sectors respectively.

From the repository root:

```bash
python -m pip install -r backend/scripts/requirements.txt
python backend/scripts/build_glacier_inventory.py RGI2000-v7.0-G-14_south_asia_west.zip --bbox 70 25 100 40 --min-area-km2 0.01 --output backend/data/glaciers.geojson
```

Run the builder for the Region 15 archive as well if eastern coverage is required. Each run writes a GeoJSON for the chosen region; combine regional inputs before production if both are needed in one inventory.

The builder clips to a WGS84 bounding box, preserves source glacier geometries, and simplifies only in a metric equal-area projection. It writes dataset attribution and processing parameters into GeoJSON metadata.

## Deployment

Set `GLACIER_DATA_PATH` to the generated file's absolute path on the API host. Render's ephemeral filesystem is not durable across deploys/restarts; use a persistent disk or object storage for production. Do not commit a large GeoJSON inventory to the application source.

## Attribution and scientific limits

RGI 7.0 is a reference inventory targeting approximately year 2000, not a current glacier-boundary update. It is not suitable for glacier-by-glacier rates of area change. The app must label it as a historical reference outline and must not imply the outlines represent 2026 conditions.

Citation: RGI 7.0 Consortium (2023), Randolph Glacier Inventory, Version 7.0, NSIDC-0770, [DOI 10.5067/F6JMOVY5NAVZ](https://doi.org/10.5067/F6JMOVY5NAVZ). License: CC BY 4.0.
