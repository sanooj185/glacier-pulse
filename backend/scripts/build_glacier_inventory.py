#!/usr/bin/env python3
"""Convert an official RGI 7.0 regional shapefile ZIP to Glacier Pulse GeoJSON."""
import argparse, json, zipfile, tempfile
from pathlib import Path
import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform

ALIASES={"id":("rgi_id","rgiid","glac_id","glims_id","id"),"name":("glac_name","name","glacier_name"),
"area":("area_km2","area","glac_area"),"lon":("cenlon","longitude","lon"),"lat":("cenlat","latitude","lat"),
"type":("glac_type","glacier_type"),"term":("term_type","terminus_type")}
def find_field(cols, aliases):
    by_lower={str(c).lower():c for c in cols}
    return next((by_lower[a] for a in aliases if a in by_lower),None)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive",type=Path)
    p.add_argument("--bbox",nargs=4,type=float,default=[70,25,100,40],metavar=("W","S","E","N"))
    p.add_argument("--min-area-km2",type=float,default=0.01)
    p.add_argument("--simplify-m",type=float,default=20)
    p.add_argument("--output",type=Path,default=Path("backend/data/glaciers.geojson"))
    a=p.parse_args()
    if not a.archive.is_file(): p.error("Regional RGI ZIP not found")
    w,s,e,n=a.bbox
    if not (-180<=w<e<=180 and -90<=s<n<=90): p.error("Invalid WGS84 bbox")
    if a.min_area_km2<0 or a.simplify_m<0: p.error("Area and simplification must be non-negative")
    with zipfile.ZipFile(a.archive) as z, tempfile.TemporaryDirectory() as td:
        shp=next((x for x in z.namelist() if x.lower().endswith(".shp")),None)
        if not shp: raise SystemExit("Archive contains no shapefile")
        z.extractall(td)
        gdf=gpd.read_file(Path(td)/shp)
        if gdf.crs is None: raise SystemExit("Shapefile CRS missing; refusing to guess")
        gdf=gdf.to_crs("EPSG:4326")
        f={k:find_field(gdf.columns,v) for k,v in ALIASES.items()}
        if not f["id"]: raise SystemExit("No recognized glacier ID field: "+", ".join(gdf.columns))
        gdf=gdf.cx[w:e,s:n]
        if f["area"]: gdf=gdf[gdf[f["area"]].fillna(0).astype(float)>=a.min_area_km2]
        to_ea=Transformer.from_crs("EPSG:4326","EPSG:6933",always_xy=True).transform
        to_ll=Transformer.from_crs("EPSG:6933","EPSG:4326",always_xy=True).transform
        features=[]
        for _,r in gdf.iterrows():
            geom=r.geometry
            if geom is None or geom.is_empty: continue
            if not geom.is_valid: geom=geom.buffer(0)
            if a.simplify_m: geom=transform(to_ll,transform(to_ea,geom).simplify(a.simplify_m,preserve_topology=True))
            area=float(r[f["area"]]) if f["area"] and r[f["area"]] is not None else transform(to_ea,geom).area/1e6
            center=geom.centroid
            def val(key):
                col=f[key]
                return str(r[col]).strip() if col and r[col] is not None else None
            props={"id":str(r[f["id"]]),"name":val("name"),"area_km2":area,
            "cenlon":float(r[f["lon"]]) if f["lon"] and r[f["lon"]] is not None else center.x,
            "cenlat":float(r[f["lat"]]) if f["lat"] and r[f["lat"]] is not None else center.y,
            "glac_type":val("type"),"term_type":val("term")}
            features.append({"type":"Feature","properties":props,"geometry":mapping(geom)})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    doc={"type":"FeatureCollection","metadata":{"source":"Randolph Glacier Inventory (RGI) 7.0","version":"7.0",
    "license":"CC BY 4.0","citation":"RGI 7.0 Consortium (2023), NSIDC-0770, DOI: 10.5067/F6JMOVY5NAVZ",
    "url":"https://doi.org/10.5067/F6JMOVY5NAVZ","builtFrom":a.archive.name,"bbox":a.bbox,
    "minAreaKm2":a.min_area_km2,"simplifyMetres":a.simplify_m,"featureCount":len(features)},"features":features}
    with a.output.open("w",encoding="utf-8") as out: json.dump(doc,out,separators=(",",":"),ensure_ascii=False)
    print(f"Wrote {len(features):,} outlines to {a.output} ({a.output.stat().st_size/1e6:.1f} MB)")
if __name__=="__main__": main()
