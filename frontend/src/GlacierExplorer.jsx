import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import { AlertTriangle, ArrowUpRight, Layers, MapPin, Mountain, Search, ShieldCheck } from 'lucide-react';

const MIN_OUTLINE_ZOOM = 7;
const STYLES = {
  outline: { color: '#127f93', weight: 1.2, fillColor: '#35c7d6', fillOpacity: 0.2 },
  selected: { color: '#ff9f1c', weight: 3, fillColor: '#ffb347', fillOpacity: 0.3 },
  full: { color: '#0b8f6f', weight: 2, fillColor: '#2ecf9f', fillOpacity: 0.07, interactive: false },
  partial: { color: '#c77700', weight: 2, fillColor: '#ffb347', fillOpacity: 0.07, interactive: false },
  grid: { color: '#6b4dff', weight: 2, dashArray: '7 5', fill: false, interactive: false },
};

const fmtArea = (v) => (v == null ? '—' : v >= 10 ? `${Number(v).toFixed(1)} km²` : `${Number(v).toFixed(2)} km²`);
const fmtDate = (s) => (s ? String(s).slice(0, 10) : 'date unavailable');

async function getJson(url, options) {
  const res = await fetch(url, options);
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON error body */ }
  if (!res.ok) throw new Error((body && body.detail) || `Request failed (${res.status})`);
  return body;
}

// Boundary ring of the GOFF preview grid in lon/lat, following the actual grid edges (no min/max box).
function gridRing(data) {
  const lat = data?.latitude, lon = data?.longitude;
  if (!lat?.length || !lon?.length) return null;
  const h = lat.length, w = lat[0].length;
  const pts = [];
  for (let x = 0; x < w; x++) pts.push([lon[0][x], lat[0][x]]);
  for (let y = 1; y < h; y++) pts.push([lon[y][w - 1], lat[y][w - 1]]);
  for (let x = w - 2; x >= 0; x--) pts.push([lon[h - 1][x], lat[h - 1][x]]);
  for (let y = h - 2; y > 0; y--) pts.push([lon[y][0], lat[y][0]]);
  const ring = pts.filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b));
  if (ring.length < 4) return null;
  ring.push(ring[0]);
  return ring;
}

function CoverageBadge({ coverage }) {
  if (!coverage) return null;
  const full = coverage.status === 'full';
  return (
    <span className={'gx-badge ' + (full ? 'full' : 'partial')}>
      {full ? 'Full coverage' : `Partial · ${coverage.coveragePercent.toFixed(1)}%`}
    </span>
  );
}

export default function GlacierExplorer({ api, data }) {
  const host = useRef(null), mapRef = useRef(null), baseRef = useRef(null);
  const outlinesRef = useRef(null), selectedRef = useRef(null), footprintsRef = useRef(null), gridRef = useRef(null);
  const fetchAbort = useRef(null), statusRef = useRef(null);

  const [status, setStatus] = useState(null);
  const [base, setBase] = useState('labels');
  const [layers, setLayers] = useState({ outlines: true, footprints: true, grid: true });
  const [view, setView] = useState({ zoom: 6, shown: 0, total: 0, truncated: false, loading: false, error: '' });
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searchErr, setSearchErr] = useState('');
  const [selected, setSelected] = useState(null);       // full GeoJSON feature
  const [attribution, setAttribution] = useState(null);
  const [obs, setObs] = useState({ loading: false, error: '', list: [], dropped: 0, note: '' });
  const [activeObs, setActiveObs] = useState(null);
  const [gridCover, setGridCover] = useState({ loading: false, error: '', list: [], count: 0 });

  // ---------------------------------------------------------------- status
  useEffect(() => {
    getJson(`${api}/api/glaciers/status`).then((s) => { setStatus(s); statusRef.current = s; if (s.attribution) setAttribution(s.attribution); })
      .catch((e) => { const s = { loaded: false, message: `Could not reach the API: ${e.message}` }; setStatus(s); statusRef.current = s; });
  }, [api]);

  // ---------------------------------------------------------------- map init
  useEffect(() => {
    if (!host.current || mapRef.current) return undefined;
    const map = L.map(host.current, { zoomControl: true, preferCanvas: true }).setView([33.0, 78.0], 6);
    mapRef.current = map;
    outlinesRef.current = L.geoJSON(null).addTo(map);
    footprintsRef.current = L.layerGroup().addTo(map);
    gridRef.current = L.layerGroup().addTo(map);
    selectedRef.current = L.layerGroup().addTo(map);
    L.control.scale({ imperial: false }).addTo(map);
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // ---------------------------------------------------------------- basemap
  useEffect(() => {
    const map = mapRef.current; if (!map) return;
    if (baseRef.current) map.removeLayer(baseRef.current);
    const labels = base === 'labels';
    baseRef.current = L.tileLayer(
      labels ? 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png' : 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 18, attribution: labels ? '© OpenStreetMap contributors' : 'Tiles © Esri' }
    ).addTo(map);
    baseRef.current.bringToBack();
  }, [base]);

  // ---------------------------------------------------------------- select a glacier
  const selectGlacier = useCallback(async (id, { fit = true } = {}) => {
    try {
      const body = await getJson(`${api}/api/glaciers/${encodeURIComponent(id)}`);
      const feature = body.glacier;
      setAttribution(body.attribution);
      setSelected(feature);
      setActiveObs(null);
      setResults([]);
      const map = mapRef.current;
      if (map && fit) {
        const b = L.geoJSON(feature).getBounds();
        if (b.isValid()) map.fitBounds(b, { padding: [60, 60], maxZoom: 13 });
      }
    } catch (e) {
      setView((v) => ({ ...v, error: e.message }));
    }
  }, [api]);

  // draw the selected glacier on top of everything
  useEffect(() => {
    const group = selectedRef.current; if (!group) return;
    group.clearLayers();
    if (selected) group.addLayer(L.geoJSON(selected, { style: STYLES.selected, interactive: false }));
  }, [selected]);

  // observations for the selected glacier (exact outline intersection is computed by the API)
  useEffect(() => {
    if (!selected) { setObs({ loading: false, error: '', list: [], dropped: 0, note: '' }); return undefined; }
    let alive = true;
    setObs({ loading: true, error: '', list: [], dropped: 0, note: '' });
    getJson(`${api}/api/glaciers/${encodeURIComponent(selected.id)}/observations?max_results=50`)
      .then((r) => alive && setObs({ loading: false, error: '', list: r.observations, dropped: r.droppedNoCoverage, note: r.note }))
      .catch((e) => alive && setObs({ loading: false, error: e.message, list: [], dropped: 0, note: '' }));
    return () => { alive = false; };
  }, [api, selected]);

  // observation footprints
  useEffect(() => {
    const group = footprintsRef.current; if (!group) return;
    group.clearLayers();
    if (!layers.footprints) return;
    obs.list.forEach((o) => {
      if (!o.geometry) return;
      const base = STYLES[o.coverage?.status === 'full' ? 'full' : 'partial'];
      const on = activeObs === o.granuleId;
      group.addLayer(L.geoJSON(o.geometry, { style: { ...base, weight: on ? 4 : base.weight, fillOpacity: on ? 0.16 : base.fillOpacity } }));
    });
  }, [obs, layers.footprints, activeObs]);

  // ---------------------------------------------------------------- loaded GOFF grid extent
  const ring = useMemo(() => gridRing(data), [data]);
  useEffect(() => {
    const group = gridRef.current; if (!group) return undefined;
    group.clearLayers();
    if (!ring) { setGridCover({ loading: false, error: '', list: [], count: 0 }); return undefined; }
    if (layers.grid) group.addLayer(L.polygon(ring.map(([lon, lat]) => [lat, lon]), STYLES.grid));
    if (!statusRef.current?.loaded) return undefined;
    let alive = true;
    setGridCover({ loading: true, error: '', list: [], count: 0 });
    getJson(`${api}/api/observations/glaciers`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ geometry: { type: 'Polygon', coordinates: [ring] }, limit: 500 }) })
      .then((r) => alive && setGridCover({ loading: false, error: '', list: r.glaciers, count: r.count }))
      .catch((e) => alive && setGridCover({ loading: false, error: e.message, list: [], count: 0 }));
    return () => { alive = false; };
  }, [api, ring, layers.grid, status]);

  // ---------------------------------------------------------------- viewport outlines
  const loadOutlines = useCallback(async () => {
    const map = mapRef.current, group = outlinesRef.current;
    if (!map || !group) return;
    const zoom = map.getZoom();
    group.clearLayers();
    if (fetchAbort.current) fetchAbort.current.abort();
    if (!layers.outlines || !statusRef.current?.loaded) { setView((v) => ({ ...v, zoom, shown: 0, total: 0, truncated: false, loading: false })); return; }
    if (zoom < MIN_OUTLINE_ZOOM) { setView((v) => ({ ...v, zoom, shown: 0, total: 0, truncated: false, loading: false, error: '' })); return; }
    const b = map.getBounds();
    const controller = new AbortController(); fetchAbort.current = controller;
    const simplify = zoom >= 11 ? 0 : zoom >= 9 ? 0.0002 : 0.0006;
    const q = new URLSearchParams({ west: Math.max(-180, b.getWest()), south: Math.max(-90, b.getSouth()), east: Math.min(180, b.getEast()), north: Math.min(90, b.getNorth()), limit: zoom >= 10 ? 900 : 500, simplify });
    setView((v) => ({ ...v, zoom, loading: true, error: '' }));
    try {
      const fc = await getJson(`${api}/api/glaciers?${q}`, { signal: controller.signal });
      group.addData(fc);
      group.setStyle(STYLES.outline);
      group.eachLayer((layer) => {
        const p = layer.feature?.properties || {};
        layer.bindTooltip(`${p.name || 'Unnamed glacier'} · ${fmtArea(p.areaKm2)}`, { sticky: true });
        layer.on('click', () => selectGlacier(p.id, { fit: false }));
      });
      setView({ zoom, shown: fc.features.length, total: fc.totalInView, truncated: fc.truncated, loading: false, error: '' });
    } catch (e) {
      if (e.name !== 'AbortError') setView((v) => ({ ...v, loading: false, error: e.message }));
    }
  }, [api, layers.outlines, selectGlacier]);

  useEffect(() => {
    const map = mapRef.current; if (!map) return undefined;
    let timer;
    const schedule = () => { clearTimeout(timer); timer = setTimeout(loadOutlines, 250); };
    map.on('moveend', schedule);
    loadOutlines();
    return () => { clearTimeout(timer); map.off('moveend', schedule); };
  }, [loadOutlines, status]);

  // ---------------------------------------------------------------- search
  useEffect(() => {
    if (query.trim().length < 2 || !status?.loaded) { setResults([]); setSearchErr(''); return undefined; }
    let alive = true;
    const t = setTimeout(() => {
      getJson(`${api}/api/glaciers/search?q=${encodeURIComponent(query.trim())}&limit=12`)
        .then((r) => { if (alive) { setResults(r.results); setSearchErr(r.results.length ? '' : 'No glacier with that name or ID in the installed inventory.'); } })
        .catch((e) => alive && setSearchErr(e.message));
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [api, query, status]);

  const toggle = (k) => setLayers((l) => ({ ...l, [k]: !l[k] }));
  const p = selected?.properties;

  return (
    <div className="gx">
      {status && !status.loaded && (
        <div className="gx-banner"><AlertTriangle size={17} /><div>
          <b>No glacier outlines are installed on this API yet.</b>
          <p>{status.message || 'Install a Randolph Glacier Inventory extract to enable glacier boundaries, search and profiles.'} The map below shows the basemap only — no glacier locations are drawn or guessed.</p>
        </div></div>
      )}
      <div className="gx-layout">
        <section className="gx-mapcard">
          <div className="gx-toolbar">
            <div className="gx-search">
              <Search size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={status?.loaded ? 'Search glacier name or RGI ID…' : 'Search needs the glacier inventory'} disabled={!status?.loaded} aria-label="Search glaciers" />
              {(results.length > 0 || searchErr) && (
                <div className="gx-results" role="listbox">
                  {results.map((r) => (
                    <button key={r.id} role="option" onClick={() => { setQuery(''); selectGlacier(r.id); }}>
                      <b>{r.name || 'Unnamed glacier'}</b><span>{fmtArea(r.areaKm2)} · {r.region || r.id}</span>
                    </button>
                  ))}
                  {searchErr && <p>{searchErr}</p>}
                </div>
              )}
            </div>
            <div className="gx-switch" role="group" aria-label="Basemap">
              <button className={base === 'labels' ? 'on' : ''} onClick={() => setBase('labels')}>Map</button>
              <button className={base === 'satellite' ? 'on' : ''} onClick={() => setBase('satellite')}>Satellite</button>
            </div>
          </div>
          <div className="gx-mapwrap">
            <div ref={host} className="gx-map" />
            <div className="gx-layerbox">
              <b><Layers size={13} /> Layers</b>
              <label><input type="checkbox" checked={layers.outlines} onChange={() => toggle('outlines')} /> Glacier outlines</label>
              <label><input type="checkbox" checked={layers.footprints} onChange={() => toggle('footprints')} /> Observation footprints</label>
              <label><input type="checkbox" checked={layers.grid} onChange={() => toggle('grid')} disabled={!ring} /> Loaded GOFF grid extent{!ring && ' (none loaded)'}</label>
            </div>
            <div className="gx-legend" aria-label="Legend">
              <b>Legend</b>
              <span><i className="sw outline" /> Glacier outline (RGI)</span>
              <span><i className="sw selected" /> Selected glacier</span>
              <span><i className="sw full" /> Footprint · full coverage</span>
              <span><i className="sw partial" /> Footprint · partial coverage</span>
              <span><i className="sw grid" /> Loaded GOFF grid extent</span>
            </div>
          </div>
          <div className="gx-status">
            {!status?.loaded ? 'Glacier inventory not installed'
              : view.zoom < MIN_OUTLINE_ZOOM ? `Zoom in to level ${MIN_OUTLINE_ZOOM}+ to load glacier outlines (now ${view.zoom})`
              : view.loading ? 'Loading outlines…'
              : view.error ? view.error
              : `${view.shown.toLocaleString()} outlines shown${view.truncated ? ` of ${view.total.toLocaleString()} in view (largest first — zoom in for the rest)` : ''}`}
          </div>
        </section>

        <aside className="gx-panel">
          {!selected ? (
            <div className="gx-empty"><Mountain size={22} /><h3>Select a glacier</h3>
              <p>Click an outline on the map or search by name. You will see its inventory record and the NISAR GOFF observations whose footprints actually intersect it.</p></div>
          ) : (
            <>
              <div className="gx-profile">
                <small>GLACIER PROFILE</small>
                <h3>{p.name || 'Unnamed glacier'}</h3>
                <code>{selected.id}</code>
                <dl>
                  <div><dt>Area</dt><dd>{fmtArea(p.area_km2 ?? p.areaKm2)}</dd></div>
                  <div><dt>Region</dt><dd>{p.region || '—'}</dd></div>
                  <div><dt>Centroid</dt><dd>{p.cenlat != null ? `${Number(p.cenlat).toFixed(3)}°, ${Number(p.cenlon).toFixed(3)}°` : '—'}</dd></div>
                  {p.src_date && <div><dt>Outline date</dt><dd>{p.src_date}</dd></div>}
                  {p.glac_type != null && <div><dt>RGI type code</dt><dd>{p.glac_type}</dd></div>}
                  {p.term_type != null && <div><dt>RGI terminus code</dt><dd>{p.term_type}</dd></div>}
                </dl>
                <p className="gx-fine">Outlines are inventory polygons mapped at the date above, not a measurement of today's glacier extent.</p>
              </div>
              <div className="gx-obs">
                <h4><MapPin size={14} /> NISAR GOFF observations</h4>
                {obs.loading && <p className="gx-fine">Searching ASF and intersecting footprints with this outline…</p>}
                {obs.error && <p className="gx-err">{obs.error}</p>}
                {!obs.loading && !obs.error && obs.list.length === 0 && <p className="gx-fine">No GOFF products found whose footprint intersects this outline{obs.dropped ? ` (${obs.dropped} nearby products did not overlap it)` : ''}. This is not evidence about glacier movement.</p>}
                <div className="gx-obslist">
                  {obs.list.map((o) => (
                    <button key={o.granuleId} className={activeObs === o.granuleId ? 'on' : ''} onClick={() => setActiveObs(activeObs === o.granuleId ? null : o.granuleId)}>
                      <span><b>{fmtDate(o.startTime)}</b> <CoverageBadge coverage={o.coverage} /></span>
                      <small>{[o.dataMaturity, o.flightDirection && `Orbit ${o.flightDirection}`, o.pathNumber && `Path ${o.pathNumber}`].filter(Boolean).join(' · ')}</small>
                      {o.coverage?.nearEdge && <small className="gx-warn">Within {5} km of the footprint edge — coverage is approximate</small>}
                      <small className="gx-id">{o.granuleId}</small>
                    </button>
                  ))}
                </div>
                {obs.note && <p className="gx-fine">{obs.note}</p>}
              </div>
            </>
          )}

          {ring && (
            <div className="gx-obs gx-grid">
              <h4><ShieldCheck size={14} /> Loaded GOFF grid extent</h4>
              {!status?.loaded ? <p className="gx-fine">Install the glacier inventory to list glaciers inside this extent.</p>
                : gridCover.loading ? <p className="gx-fine">Intersecting with glacier outlines…</p>
                : gridCover.error ? <p className="gx-err">{gridCover.error}</p>
                : <>
                    <p className="gx-fine"><b>{gridCover.count.toLocaleString()}</b> inventory glaciers intersect the grid extent of the loaded granule. This is the extent of the grid, not the footprint of valid, high-quality pixels.</p>
                    <div className="gx-obslist">
                      {gridCover.list.slice(0, 8).map((g) => (
                        <button key={g.id} onClick={() => selectGlacier(g.id)}>
                          <span><b>{g.name || 'Unnamed glacier'}</b> <CoverageBadge coverage={g.coverage} /></span>
                          <small>{fmtArea(g.areaKm2)} · {g.id}</small>
                        </button>
                      ))}
                    </div>
                    {gridCover.count > 8 && <p className="gx-fine">Showing the 8 largest. Search by name to find others.</p>}
                  </>}
            </div>
          )}

          {attribution?.citation && (
            <p className="gx-attrib">Glacier outlines: {attribution.source}. {attribution.citation} {attribution.url && <a href={attribution.url} target="_blank" rel="noreferrer">Source <ArrowUpRight size={11} /></a>}</p>
          )}
        </aside>
      </div>
    </div>
  );
}
