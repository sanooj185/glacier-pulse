#!/usr/bin/env python3
"""Build backend/data/glaciers.geojson from a real Randolph Glacier Inventory (RGI) download.

Glacier Pulse never ships invented outlines. Download RGI yourself, then run this once:

  RGI 7.0 (NSIDC-0770, DOI 10.5067/f6jmovy5navz) - regional shapefiles/GeoPackages, e.g.
      RGI2000-v7.0-G-13_central_asia, -14_south_asia_west, -15_south_asia_east
  RGI 6.0 (NSIDC-0770 v6 / GLIMS, DOI 10.7265/N5-RGI-60) - regional shapefiles, e.g.
      13_rgi60_CentralAsia, 14_rgi60_SouthAsiaWest, 15_rgi60_SouthAsiaEast

Example (Himalaya + Karakoram + Tibet, glaciers >= 0.5 km2):

  pip install -r scripts/requirements.txt
  python scripts/build_glacier_inventory.py \\
      RGI2000-v7.0-G-14_south_asia_west.zip RGI2000-v7.0-G-15_south_asia_east.zip \\
      --min-area-km2 0.5 --bbox 70 25 100 40 --output backend/data/glaciers.geojson

Both RGI 6 and RGI 7 attribute schemas are understood. Geometry is kept as published (only
repaired if invalid and rounded to ~1 m) and is simplified only when --simplify is given.
"""
import argparse
import json
import sys
from pathlib import Path

CITATIONS = {
    "7": {
        "source": "Randolph Glacier Inventory (RGI) 7.0",
        "citation": "RGI 7.0 Consortium (2023). Randolph Glacier Inventory - A Dataset of Global Glacier Outlines, Version 7. "
                    "Boulder, Colorado USA. NSIDC: National Snow and Ice Data Center. https://doi.org/10.5067/f6jmovy5navz",
        "url": "https://nsidc.org/data/nsidc-0770/versions/7",
        "license": "See NSIDC for current terms (RGI 7.0 is distributed with attribution requirements)",
    },
    "6": {
        "source": "Randolph Glacier Inventory (RGI) 6.0",
        "citation": "RGI Consortium (2017). Randolph Glacier Inventory - A Dataset of Global Glacier Outlines: Version 6.0: "
                    "Technical Report, Global Land Ice Measurements from Space, Colorado, USA. Digital Media. "
                    "https://doi.org/10.7265/N5-RGI-60",
        "url": "https://www.glims.org/RGI/",
        "license": "See GLIMS/NSIDC for current terms (attribution required)",
    },
}


def pick(row, *names, default=None):
    for name in names:
        if name in row and row[name] is not None:
            value = row[name]
            try:
                if value != value:  # NaN
                    continue
            except Exception:
                pass
            return value
    return default


def clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="RGI shapefile / GeoPackage / zip files (one per region)")
    parser.add_argument("--output", default="backend/data/glaciers.geojson")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"), help="keep glaciers intersecting this box (lon/lat)")
    parser.add_argument("--min-area-km2", type=float, default=0.0)
    parser.add_argument("--simplify", type=float, default=0.0, help="optional simplification tolerance in degrees (0 = none)")
    parser.add_argument("--rgi-version", choices=["6", "7"], help="override automatic version detection")
    args = parser.parse_args()

    try:
        import geopandas as gpd
        from shapely import make_valid
    except ImportError:
        sys.exit("Install the build dependencies first: pip install -r scripts/requirements.txt")

    features, version, repaired = [], args.rgi_version, 0
    seen = set()
    for path in args.inputs:
        gdf = gpd.read_file(f"zip://{path}" if str(path).lower().endswith(".zip") else path)
        if gdf.crs is None:
            sys.exit(f"{path}: no CRS found; refusing to guess one.")
        gdf = gdf.to_crs(4326)
        columns = set(gdf.columns)
        detected = "7" if "rgi_id" in columns else "6" if "RGIId" in columns else None
        if detected is None:
            sys.exit(f"{path}: not recognisable as RGI 6 (RGIId) or RGI 7 (rgi_id). Columns: {sorted(columns)}")
        if version and version != detected:
            sys.exit(f"{path}: looks like RGI {detected} but another input was RGI {version}. Do not mix versions.")
        version = detected
        if args.bbox:
            w, s, e, n = args.bbox
            gdf = gdf.cx[w:e, s:n]
        for _, row in gdf.iterrows():
            area = float(pick(row, "area_km2", "Area", default=0.0) or 0.0)
            if area < args.min_area_km2:
                continue
            gid = str(pick(row, "rgi_id", "RGIId"))
            if gid in seen:
                continue
            seen.add(gid)
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            if not geom.is_valid:
                geom = make_valid(geom)
                repaired += 1
            if args.simplify > 0:
                geom = geom.simplify(args.simplify, preserve_topology=True)
            region = pick(row, "o1region", "o2region")
            props = {
                "id": gid, "name": clean_text(pick(row, "glac_name", "Name")), "area_km2": round(area, 4),
                "region": f"RGI {version} region {pick(row, 'o1region', default='')}{'/' + str(pick(row, 'o2region')) if pick(row, 'o2region') else ''}".strip() if region else None,
                "cenlon": round(float(pick(row, "cenlon", "CenLon")), 5) if pick(row, "cenlon", "CenLon") is not None else round(geom.centroid.x, 5),
                "cenlat": round(float(pick(row, "cenlat", "CenLat")), 5) if pick(row, "cenlat", "CenLat") is not None else round(geom.centroid.y, 5),
                "glac_type": clean_text(pick(row, "glac_type", "GlacType")),
                "term_type": clean_text(pick(row, "term_type", "TermType")),
                "glims_id": clean_text(pick(row, "glims_id", "GLIMSId")),
                "src_date": clean_text(pick(row, "src_date", "BgnDate")),
            }
            features.append({"type": "Feature", "properties": props, "geometry": json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]})

    if not features:
        sys.exit("No glaciers matched your filters; nothing written.")

    def round_coords(obj):
        if isinstance(obj, (list, tuple)):
            return [round_coords(o) for o in obj]
        return round(obj, 5)

    for f in features:
        f["geometry"]["coordinates"] = round_coords(f["geometry"]["coordinates"])

    meta = {**CITATIONS[version], "version": version, "builtFrom": [Path(p).name for p in args.inputs],
            "filters": {"bbox": args.bbox, "minAreaKm2": args.min_area_km2, "simplifyDeg": args.simplify},
            "repairedGeometries": repaired}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "metadata": meta, "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(features)} glaciers ({out.stat().st_size / 1e6:.1f} MB) to {out}")


if __name__ == "__main__":
    main()
