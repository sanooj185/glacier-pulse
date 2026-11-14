import React,{useEffect,useMemo,useRef,useState} from 'react';import{createRoot}from'react-dom/client';import{Activity,ArrowUpRight,BarChart3,BookOpen,ChevronDown,CloudUpload,Compass,Database,Globe2,Layers,Menu,MessageCircle,Mountain,Satellite,Search,ShieldCheck,SlidersHorizontal,Sparkles,Timer,Upload,Wind}from'lucide-react';import'leaflet/dist/leaflet.css';import L from 'leaflet';import GlacierExplorer from './GlacierExplorer.jsx';import'./style.css';
const configuredApi=(import.meta.env.VITE_API_URL||'').trim();
const API=configuredApi ? (configuredApi.startsWith('http') ? configuredApi : `https://${configuredApi}`).replace(/\/$/,'') : 'http://localhost:8000';
function App(){const[page,setPage]=useState('Overview'),[layer,setLayer]=useState('alongTrack'),[data,setData]=useState(null),[busy,setBusy]=useState(false),[err,setErr]=useState(''),[mode,setMode]=useState('Explore'),[query,setQuery]=useState('');
const nav=[['Overview',Compass],['Glacier Explorer',Globe2],['Time Machine',Timer],['Movement Intelligence',Activity],['NISAR Radar Lab',Satellite],['AI Interpreter',Sparkles],['Research & Reports',BookOpen]];
async function uploadFile(file){if(!file)return;setBusy(true);setErr('');try{const fd=new FormData();fd.append('file',file);const r=await fetch(`${API}/api/goff/preview?layer=layer1&max_dim=420`,{method:'POST',body:fd});const j=await r.json();if(!r.ok)throw new Error(j.detail||'Upload failed');setData(j);setPage('NISAR Radar Lab')}catch(e){setErr(e.message+' — Check that the API is running on port 8000.')}finally{setBusy(false)}}
return <div className="app"><aside className="sidebar"><div className="brand"><div className="brandmark"><Mountain size={22}/></div><div><b>GLACIER PULSE</b><small>EARTH OBSERVATION LAB</small></div></div><div className="workspace"><span className="dot"/> PROJECT WORKSPACE <ChevronDown size={14}/></div><div className="navlabel">WORKSPACE</div>{nav.map(([n,I])=><button key={n} className={'navitem '+(page===n?'active':'')} onClick={()=>setPage(n)}><I size={17}/>{n}{n==='NISAR Radar Lab'&&data&&<span className="navdot"/>}</button>)}<div className="sidebottom"><div className="status"><span className="pulse"/> SYSTEM READY <span className="statusright">v0.1</span></div><div className="user"><div className="avatar">GP</div><div><b>Glacier Pulse</b><small>Research workspace</small></div></div></div></aside><main className="main"><header><div className="crumb">GLACIER PULSE <span>/</span> {page.toUpperCase()}</div><div className="headright"><div className="mode"><button className={mode==='Explore'?'selected':''} onClick={()=>setMode('Explore')}>Explore</button><button className={mode==='Research'?'selected':''} onClick={()=>setMode('Research')}>Research</button></div><div className="avatar small">GP</div></div></header><div className="content"><div className="eyebrow"><span className="eyebrowline"/> NASA NISAR · GLACIER MONITORING</div><div className="herohead"><div><h1>{page==='Overview'?'Every glacier has a story.':page}</h1><p className="sub">{page==='Overview'?'Explore glacier movement through satellite observations, scientific context and clear explanations.':descriptions[page]||'Explore satellite observations and glacier information.'}</p></div>{page==='Overview'&&<div className="heroicon"><Mountain size={34}/><span>HIMALAYAN<br/>OBSERVATION</span></div>}</div>
{page==='Overview'?<><div className="heroimage"><div className="heroimageoverlay"><span className="livepill"><span/> OBSERVATION WORKSPACE</span><h2>See the movement.<br/><i>Understand the change.</i></h2><p>Bring radar observations, glacier geography and scientific interpretation into one place.</p><button className="primary" onClick={()=>setPage('Glacier Explorer')}>Explore glaciers <ArrowUpRight size={16}/></button></div><div className="heroimagecaption">HIMALAYAN CRYOSPHERE <span>EARTH · ICE · CHANGE</span></div></div><div className="sectiontitle"><div><h2>Workspace modules</h2><p>Move from observation to understanding.</p></div><span className="muted">01 — 06</span></div><div className="modulegrid">{nav.slice(1).map(([n,I],i)=><button className="module" key={n} onClick={()=>setPage(n)}><div className="moduleicon"><I size={19}/></div><span className="modnum">0{i+1}</span><h3>{n}</h3><p>{moduleDesc[n]}</p><ArrowUpRight size={16} className="modulearrow"/></button>)}</div></>:page==='NISAR Radar Lab'?<RadarLab data={data} layer={layer} setLayer={setLayer} uploadFile={uploadFile} setData={setData} busy={busy} err={err}/>:page==='AI Interpreter'?<AIInterpreter data={data}/>:page==='Glacier Explorer'?<GlacierExplorer api={API} data={data}/>:page==='Time Machine'?<TimeMachine data={data}/>:page==='Movement Intelligence'?<Movement data={data}/>:<Reports data={data}/>}
<footer><span>GLACIER PULSE <b>·</b> EVERY GLACIER HAS A STORY</span><span>Built for exploration · Scientific claims require validated observations</span></footer></div></main></div>}
const descriptions={'Glacier Explorer':'Discover glacier locations, boundaries and available satellite observations.','Time Machine':'Compare observation dates and explore how the evidence changes over time.','Movement Intelligence':'Understand displacement products, uncertainty and the limits of interpretation.','NISAR Radar Lab':'Load a GOFF granule and preview its georeferenced radar offset and quality layers.','AI Interpreter':'Translate satellite observations into clear, evidence-grounded explanations.','Research & Reports':'Review data sources, processing notes and exportable research summaries.'};const moduleDesc={'Glacier Explorer':'Browse glacier geography and available observations.','Time Machine':'Compare dates and explore observation history.','Movement Intelligence':'Interpret displacement and measurement quality.','NISAR Radar Lab':'Inspect real NISAR GOFF data products.','AI Interpreter':'Ask questions in clear scientific language.','Research & Reports':'Keep methods, sources and findings together.'};
function describeGranule(p){
 const id=p.granuleId||p.fileName||'';
 const stamps=[...id.matchAll(/(20\d{6})T(\d{6})/g)].map(m=>m[1]+'T'+m[2]);
 const dates=[...new Set(stamps.slice(0,2).map(s=>s.slice(0,8)))];
 const type=/_UR_GOFF_/.test(id)?'Urgent response GOFF':/_PR_GOFF_/.test(id)?'Precision GOFF':id.match(/NISAR_L2_([^_]+)_([^_]+)/)?.slice(1).join(' ')||'NISAR product';
 const level=id.match(/NISAR_(L\d)_/)?.[1]||'L2';
 const track=id.match(/GOFF_(\d{3})_(\d{3})_/)?.slice(1).join(' / ');
 const orbit=id.match(/GOFF_\d{3}_\d{3}_([A-Z])_(\d{3})_/) ;
 const primary=stamps[0]||p.startTime||'';
 const pretty=s=>s?new Date(s.length===15? s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6,8)+'T'+s.slice(9,11)+':'+s.slice(11,13)+':'+s.slice(13,15)+'Z':s).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}):'Date unavailable';
 return {id,type,level,dates:dates.map(d=>pretty(d+'T000000')),sortDate:primary,track,orbit:orbit?.[1],path:orbit?.[2],dateLabel:dates.length>1?dates.map(d=>pretty(d+'T000000')).join(' → '):pretty(primary),maturity:p.dataMaturity||'Maturity not listed'};
}
function RadarLab({data,layer,setLayer,uploadFile,setData,busy,err}){const[drag,setDrag]=useState(false);const[asfBusy,setAsfBusy]=useState(false);const[asfErr,setAsfErr]=useState('');const[asfResults,setAsfResults]=useState(null);const[productType,setProductType]=useState('all');const[streamBusy,setStreamBusy]=useState('');const[streamErr,setStreamErr]=useState('');const[bbox,setBbox]=useState({west:'86.5',south:'35.17',east:'90.2',north:'38.01'});const[start,setStart]=useState('');const[end,setEnd]=useState('');const[maturity,setMaturity]=useState('');async function streamFromASF(granuleId,maturity){setStreamBusy(granuleId);setStreamErr('');try{const r=await fetch(`${API}/api/asf/stream-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({granuleId,maturity:maturity||null,layer:'layer1',maxDim:420})});const j=await r.json();if(!r.ok)throw new Error(j.detail||'Earthdata stream preview failed');setData(j);setLayer('alongTrack')}catch(ex){setStreamErr(ex.message)}finally{setStreamBusy('')}}async function searchASF(e){e.preventDefault();setAsfBusy(true);setAsfErr('');setAsfResults(null);try{const q=new URLSearchParams({...bbox,max_results:'30'});if(start)q.set('start',start);if(end)q.set('end',end);if(maturity)q.set('maturity',maturity);const r=await fetch(`${API}/api/asf/search?${q}`);const j=await r.json();if(!r.ok)throw new Error(j.detail||'ASF search failed');setAsfResults(j)}catch(ex){setAsfErr(ex.message)}finally{setAsfBusy(false)}}return <><div className="panel" style={{marginBottom:18}}><div className="sectiontitle"><div><h2>Find NISAR data automatically</h2><p>Search the ASF DAAC catalog for GOFF granules intersecting your region.</p></div><span className="muted">ASF SEARCH</span></div><SearchRegionMap bbox={bbox} setBbox={setBbox}/><form onSubmit={searchASF} style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(130px,1fr))',gap:10,marginTop:16}}><label className="fieldlabel">West longitude<input required type="number" step="any" value={bbox.west} onChange={e=>setBbox({...bbox,west:e.target.value})} placeholder="e.g. 86.5"/></label><label className="fieldlabel">South latitude<input required type="number" step="any" value={bbox.south} onChange={e=>setBbox({...bbox,south:e.target.value})} placeholder="e.g. 35.1"/></label><label className="fieldlabel">East longitude<input required type="number" step="any" value={bbox.east} onChange={e=>setBbox({...bbox,east:e.target.value})} placeholder="e.g. 90.2"/></label><label className="fieldlabel">North latitude<input required type="number" step="any" value={bbox.north} onChange={e=>setBbox({...bbox,north:e.target.value})} placeholder="e.g. 38.0"/></label><label className="fieldlabel">Start date<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label className="fieldlabel">End date<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><label className="fieldlabel">Data maturity<select value={maturity} onChange={e=>setMaturity(e.target.value)}><option value="">All maturities</option><option value="VALIDATED">Validated</option><option value="PROVISIONAL">Provisional</option><option value="BETA">Beta</option></select></label><div style={{display:'flex',alignItems:'end'}}><button className="primary" type="submit" disabled={asfBusy}>{asfBusy?'Searching ASF…':'Search ASF catalog'} <Search size={15}/></button></div></form>{asfErr&&<div className="errorbox" style={{marginTop:12}}>{asfErr}</div>}{streamErr&&<div className="errorbox" style={{marginTop:12}}>{streamErr}</div>}{asfResults&&<div className="catalog-results"><div className="catalog-top"><div><b>{asfResults.count} observations found</b><p>Newest acquisitions first · dates and product family decoded from each granule name</p></div><select aria-label="Filter product type" value={productType} onChange={e=>setProductType(e.target.value)}><option value="all">All product types</option><option value="Precision GOFF">Precision GOFF</option><option value="Urgent response GOFF">Urgent response GOFF</option></select></div>{asfResults.products.length===0?<p>No products found. Try a wider region or date range.</p>:<div className="catalog-list">{asfResults.products.map((p,i)=>({...p,_info:describeGranule(p)})).filter(p=>productType==='all'||p._info.type===productType).sort((a,b)=>b._info.sortDate.localeCompare(a._info.sortDate)).map((p,i)=><article key={p.granuleId||p.fileName||i} className="catalog-item"><div className="catalog-date"><span>{p._info.dateLabel}</span><small>{p._info.maturity}</small></div><div className="catalog-main"><div className="catalog-tags"><span className="catalog-type">{p._info.type}</span><span>{p._info.level}</span>{p._info.track&&<span>Track {p._info.track}</span>}</div><details><summary>View original granule filename</summary><code>{p.granuleId||p.fileName||'NISAR product name unavailable'}</code></details></div><button className="primary catalog-action" disabled={!p.granuleId||!!streamBusy} onClick={()=>streamFromASF(p.granuleId,p.dataMaturity)}>{streamBusy===p.granuleId?'Loading…':'Open data'} <ArrowUpRight size={14}/></button></article>)}</div>}</div>}</div><div className="uploadbar" ><div><b>NISAR GOFF data</b><p>Optional local fallback. Prefer streaming directly from an ASF catalog result above.</p></div><label className="uploadbtn"><Upload size={16}/>{busy?'Processing…':'Upload GOFF file'}<input type="file" accept=".h5,.hdf5" disabled={busy} onChange={e=>uploadFile(e.target.files?.[0])}/></label></div>{err&&<div className="errorbox">{err}</div>}{!data?<div className={'dropzone '+(drag?'drag':'')} onDragOver={e=>{e.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);uploadFile(e.dataTransfer.files?.[0])}}><div className="dropicon"><CloudUpload size={27}/></div><h2>Bring your NISAR observation into the lab</h2><p>Stream a catalog result above, or use a local GOFF HDF5 file as a fallback.</p><div className="dropmeta"><span>HDF5 · GOFF</span><span>Layer 1 preview</span><span>Geographic coordinates</span></div><p className="hint">ASF streaming reads selected datasets over authenticated HTTPS; local uploads remain temporary and are not retained.</p></div>:<><div className="statgrid"><Stat label="Granule" value={data.metadata.granuleId?.slice(0,22)+'…'||'Loaded'} sub="NISAR L2 PR GOFF"/><Stat label="Reference acquisition" value={data.metadata.referenceStart?.slice(0,10)||'Metadata unavailable'} sub="Reference date"/><Stat label="Secondary acquisition" value={data.metadata.secondaryStart?.slice(0,10)||'Metadata unavailable'} sub="Secondary date"/><Stat label="Finite preview coverage" value={data.metadata.previewValidPercent+'%'} sub="Finite offset pixels"/></div><div className="mapcard"><div className="maphead"><div><h3>Georeferenced offset preview</h3><p>EPSG:{data.metadata.epsg} → WGS84 · {data.metadata.previewRows} × {data.metadata.previewCols} preview</p></div><select value={layer} onChange={e=>setLayer(e.target.value)}><option value="alongTrack">Along-track offset</option><option value="slantRange">Slant-range offset</option><option value="correlation">Correlation peak</option><option value="snr">SNR</option></select></div><GeoMap data={data} layer={layer}/><div className="raster-detail-title"><b>Raster detail</b><span>Pixel-level view and distribution</span></div><Heatmap data={data} layer={layer}/><div className="mapfoot"><span>Track {data.metadata.trackNumber||'—'} · {data.metadata.orbitPassDirection||'—'} · Look {data.metadata.lookDirection||'—'}</span><span>Finite offset pixels · mask handling shown in metadata</span></div></div><div className="notice"><ShieldCheck size={18}/><span>This is a georeferenced GOFF measurement preview, not a glacier velocity map. Radar-coordinate offsets have not yet been transformed into ground-motion components.</span></div></>}</>}
function SearchRegionMap({bbox,setBbox}){
 const host=useRef(null),mapRef=useRef(null),shape=useRef(null),drag=useRef(null);
 const [selection,setSelection]=useState('point');
 const selectionRef=useRef('point');
 const [message,setMessage]=useState('Click the map to search around a point, or drag to draw a rectangle.');
 useEffect(()=>{
  if(!host.current||mapRef.current)return;
  const map=L.map(host.current,{scrollWheelZoom:true,dragging:true}).setView([36.6,88.2],5);
  mapRef.current=map;
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap contributors'}).addTo(map);
  const update=(bounds,label)=>{
   const sw=bounds.getSouthWest(),ne=bounds.getNorthEast();
   const next={west:sw.lng.toFixed(4),south:sw.lat.toFixed(4),east:ne.lng.toFixed(4),north:ne.lat.toFixed(4)};
   setBbox(next);setMessage(label+' · '+next.west+', '+next.south+' to '+next.east+', '+next.north);
   if(shape.current)map.removeLayer(shape.current);
   shape.current=L.rectangle(bounds,{color:'#087e79',weight:2,fillColor:'#20b9a5',fillOpacity:.13}).addTo(map);
  };
  map.on('click',e=>{
   if(selectionRef.current!=='point')return;
   const d=.25,b=L.latLngBounds([e.latlng.lat-d,e.latlng.lng-d],[e.latlng.lat+d,e.latlng.lng+d]);
   update(b,'Point selected · approx. 50 km search window');
  });
  map.on('mousedown',e=>{if(selectionRef.current==='rectangle'){map.dragging.disable();drag.current=e.latlng}});
  map.on('mouseup',e=>{if(selectionRef.current==='rectangle'&&drag.current){const b=L.latLngBounds(drag.current,e.latlng);drag.current=null;if(b.getNorthEast().distanceTo(b.getSouthWest())>1000)update(b,'Rectangle selected');}});
  return ()=>{map.remove();mapRef.current=null};
 },[]);
 useEffect(()=>{
  selectionRef.current=selection;
  const map=mapRef.current;if(!map)return;
  if(selection==='point')map.dragging.enable();else map.dragging.disable();
 },[selection]);
 useEffect(()=>{
  const map=mapRef.current;if(!map)return;
  if(shape.current)map.removeLayer(shape.current);
  const b=[[Number(bbox.south),Number(bbox.west)],[Number(bbox.north),Number(bbox.east)]];
  if(b.flat().every(Number.isFinite))shape.current=L.rectangle(b,{color:'#087e79',weight:2,fillColor:'#20b9a5',fillOpacity:.13}).addTo(map);
 },[bbox]);
 return <div className="search-map-panel">
  <div className="search-map-head"><div><b>Select your observation region</b><p>Choose a point or draw a search rectangle on the map.</p></div><div className="base-switch"><button type="button" className={selection==='point'?'on':''} onClick={()=>{setSelection('point');setMessage('Click the map to search around a point.')}}>Click point</button><button type="button" className={selection==='rectangle'?'on':''} onClick={()=>{setSelection('rectangle');setMessage('Drag on the map to draw a search rectangle.')}}>Draw area</button></div></div>
  <div ref={host} className="search-region-map"/>
  <div className="search-map-message">{message}</div>
 </div>
}
function GeoMap({data,layer}){
 const host=useRef(null),mapRef=useRef(null),overlayRef=useRef(null),[base,setBase]=useState('labels'),[opacity,setOpacity]=useState(.78);
 const raster=useMemo(()=>{
  if(!data?.[layer]?.length||!data.latitude?.length||!data.longitude?.length)return null;
  const a=data[layer],h=a.length,w=a[0].length,valid=[];
  for(const row of a)for(const v of row)if(v!==null&&Number.isFinite(v))valid.push(v);
  if(!valid.length)return null;
  valid.sort((x,y)=>x-y);
  const q=v=>valid[Math.min(valid.length-1,Math.floor((valid.length-1)*v))];
  const diverging=layer==='alongTrack'||layer==='slantRange',lim=diverging?Math.max(Math.abs(q(.02)),Math.abs(q(.98))):null;
  const lo=diverging?-lim:Math.max(0,q(.02)),hi=diverging?lim:q(.98);
  const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;
  const ctx=canvas.getContext('2d'),img=ctx.createImageData(w,h);
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
   const v=a[y][x],i=(y*w+x)*4;if(v===null||!Number.isFinite(v)){img.data[i+3]=0;continue}
   const t=Math.max(0,Math.min(1,(v-lo)/(hi-lo||1)));let c;
   if(diverging)c=t<.5?[35+185*t*2,95+145*t*2,190+65*t*2]:[220+35*(t-.5)*2,240-190*(t-.5)*2,255-205*(t-.5)*2];
   else if(layer==='correlation')c=[25+35*t,75+155*t,105+125*t];else c=[30+215*t,65+150*t,100-65*t];
   img.data[i]=c[0];img.data[i+1]=c[1];img.data[i+2]=c[2];img.data[i+3]=255;
  }
  ctx.putImageData(img,0,0);
  let minLat=Infinity,maxLat=-Infinity,minLon=Infinity,maxLon=-Infinity;
  for(const row of data.latitude)for(const v of row)if(Number.isFinite(v)){minLat=Math.min(minLat,v);maxLat=Math.max(maxLat,v)}
  for(const row of data.longitude)for(const v of row)if(Number.isFinite(v)){minLon=Math.min(minLon,v);maxLon=Math.max(maxLon,v)}
  if(!Number.isFinite(minLat)||!Number.isFinite(minLon))return null;
  return {url:canvas.toDataURL('image/png'),bounds:[[minLat,minLon],[maxLat,maxLon]],center:[(minLat+maxLat)/2,(minLon+maxLon)/2],lo,hi};
 },[data,layer]);
 useEffect(()=>{
  if(!host.current||mapRef.current)return;
  const map=L.map(host.current,{zoomControl:true,scrollWheelZoom:false,preferCanvas:true});
  mapRef.current=map;
  return ()=>{map.remove();mapRef.current=null};
 },[]);
 useEffect(()=>{
  const map=mapRef.current;if(!map||!raster)return;
  if(overlayRef.current){map.removeLayer(overlayRef.current);overlayRef.current=null}
  const url=base==='labels'?'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png':'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  if(map._gpBase)map.removeLayer(map._gpBase);
  map._gpBase=L.tileLayer(url,{maxZoom:19,attribution:base==='labels'?'© OpenStreetMap contributors © CARTO':'Tiles © Esri'}).addTo(map);
  overlayRef.current=L.imageOverlay(raster.url,raster.bounds,{opacity,interactive:false}).addTo(map);
  map.fitBounds(raster.bounds,{padding:[22,22],maxZoom:9});
 },[raster,base]);
 useEffect(()=>{if(overlayRef.current)overlayRef.current.setOpacity(opacity)},[opacity]);
 const labels={alongTrack:'Along-track offset',slantRange:'Slant-range offset',correlation:'Correlation peak',snr:'Signal-to-noise ratio'};
 return <section className="geo-panel">
  <div className="geo-head"><div><b>Observation footprint on Earth</b><p>{labels[layer]} · approximate geographic extent from GOFF coordinates</p></div><div className="base-switch"><button className={base==='labels'?'on':''} onClick={()=>setBase('labels')}>Map labels</button><button className={base==='satellite'?'on':''} onClick={()=>setBase('satellite')}>Satellite</button></div></div>
  <div ref={host} className="geo-map"/>
  <div className="geo-controls"><label>Raster opacity <input type="range" min="0.15" max="1" step="0.05" value={opacity} onChange={e=>setOpacity(Number(e.target.value))}/><b>{Math.round(opacity*100)}%</b></label><span>Outlined extent = GOFF observation coverage</span></div>
  <p className="geo-caveat">The raster is positioned using its geographic coordinate extent. Glacier outlines and named glacier boundaries are not yet loaded, so this map does not identify individual glaciers or prove that the footprint covers a specific glacier.</p>
 </section>
}
function Heatmap({data,layer}){
 const ref=React.useRef(null);
 const values=useMemo(()=>data?.[layer]?.flat().filter(v=>v!==null&&Number.isFinite(v))||[],[data,layer]);
 const stats=useMemo(()=>{
  if(!values.length)return null;
  const sorted=[...values].sort((a,b)=>a-b),at=q=>sorted[Math.min(sorted.length-1,Math.floor((sorted.length-1)*q))];
  const mean=values.reduce((a,b)=>a+b,0)/values.length;
  const abs98=quant(values.map(Math.abs),.98);
  const lo=layer==='alongTrack'||layer==='slantRange'?-abs98:Math.max(0,at(.02));
  const hi=layer==='alongTrack'||layer==='slantRange'?abs98:at(.98);
  const clipped=values.filter(v=>v<lo||v>hi).length;
  return {min:at(0),p02:at(.02),median:at(.5),p98:at(.98),max:at(1),mean,lo,hi,clipped,valid:values.length};
 },[values,layer]);
 React.useEffect(()=>{
  const c=ref.current;if(!c||!data||!stats)return;
  const ctx=c.getContext('2d'),a=data[layer],h=a.length,w=a[0].length;
  c.width=w;c.height=h;
  const img=ctx.createImageData(w,h),diverging=layer==='alongTrack'||layer==='slantRange';
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
   const v=a[y][x],i=(y*w+x)*4;
   if(v===null||!Number.isFinite(v)){img.data[i+3]=0;continue}
   const t=Math.max(0,Math.min(1,(v-stats.lo)/(stats.hi-stats.lo||1)));
   let rgb;
   if(diverging){
    // Blue = negative, near-white = zero, red = positive radar-coordinate offset.
    rgb=t<.5?[Math.round(35+185*t*2),Math.round(95+145*t*2),Math.round(190+65*t*2)]:[Math.round(220+35*(t-.5)*2),Math.round(240-190*(t-.5)*2),Math.round(255-205*(t-.5)*2)];
   }else if(layer==='correlation'){
    rgb=[Math.round(25+35*t),Math.round(75+155*t),Math.round(105+125*t)];
   }else{
    rgb=[Math.round(30+215*t),Math.round(65+150*t),Math.round(100-65*t)];
   }
   img.data[i]=rgb[0];img.data[i+1]=rgb[1];img.data[i+2]=rgb[2];img.data[i+3]=255;
  }
  ctx.putImageData(img,0,0);
 },[data,layer,stats]);
 const labels={alongTrack:'Along-track offset',slantRange:'Slant-range offset',correlation:'Correlation peak',snr:'Signal-to-noise ratio'};
 const unit=(layer==='alongTrack'||layer==='slantRange')?'m':'';
 const fmt=v=>Number(v).toFixed(3)+(unit?' m':'');
 if(!stats)return <div className="heatwrap"><p>No finite pixels available for this layer.</p></div>;
 return <div className="heatwrap">
  <div className="heatcanvas"><canvas ref={ref}/></div>
  <div className="raster-scale"><div className={'scale-gradient '+((layer==='alongTrack'||layer==='slantRange')?'diverging':'sequential')}/><div className="scale-labels"><span>{fmt(stats.lo)}</span><span>{(layer==='alongTrack'||layer==='slantRange')?'0':fmt((stats.lo+stats.hi)/2)}</span><span>{fmt(stats.hi)}</span></div></div>
  <div className="heatlegend"><span>{labels[layer]} · {unit||'unitless'}</span><span>{stats.valid.toLocaleString()} valid preview pixels · {stats.clipped.toLocaleString()} outside display range</span></div>
  <div className="raster-stats"><div><small>MIN</small><b>{fmt(stats.min)}</b></div><div><small>2ND PCTL</small><b>{fmt(stats.p02)}</b></div><div><small>MEDIAN</small><b>{fmt(stats.median)}</b></div><div><small>MEAN</small><b>{fmt(stats.mean)}</b></div><div><small>98TH PCTL</small><b>{fmt(stats.p98)}</b></div><div><small>MAX</small><b>{fmt(stats.max)}</b></div></div>
  <p className="raster-note">{(layer==='alongTrack'||layer==='slantRange')?'Diverging scale is centred at zero; blue and red indicate negative and positive radar-coordinate offsets, respectively.':'Sequential scale uses the 2nd–98th percentile range for contrast.'} Values outside the display range are clipped for visualization only; the underlying measurements are unchanged.</p>
 </div>
}
function quant(a,q){if(!a.length)return 1;const s=[...a].sort((x,y)=>x-y);return s[Math.min(s.length-1,Math.floor((s.length-1)*q))]}
function Stat({label,value,sub}){return <div className="stat"><span>{label}</span><b title={value}>{value}</b><small>{sub}</small></div>}
function AIInterpreter({data}){
 const [question,setQuestion]=useState('');
 const [answer,setAnswer]=useState(null);
 const m=data?.metadata||{};
 const prompts=['What does along-track offset mean?','How reliable is this observation?','What is the time interval?','Does this prove the glacier is moving?'];
 function explain(q){
  const lower=q.toLowerCase(),ref=m.referenceStart,sec=m.secondaryStart;
  const interval=ref&&sec?Math.round(Math.abs(new Date(sec)-new Date(ref))/86400000):null;
  const valid=m.previewValidPercent;
  let heading='How to read this observation',body='';
  if(!data) body='Load a GOFF observation in NISAR Radar Lab first. I can then explain its acquisition dates, offset layers and available quality indicators. No observation values are available in this workspace yet.';
  else if(lower.includes('along')||lower.includes('slant')||lower.includes('offset')){heading='Radar-coordinate offsets';body='Along-track and slant-range offsets describe estimated image displacement in the radar acquisition geometry. They are not automatically east-west/north-south ground motion and are not glacier velocity. Converting them to ground-motion components requires a validated geometry transformation and careful quality masking.';}
  else if(lower.includes('reliable')||lower.includes('quality')||lower.includes('confidence')){heading='Quality is part of the result';body='Use correlation peak, signal-to-noise ratio, valid-data masks and uncertainty layers together. A high finite-pixel percentage alone does not prove that offsets are accurate. '+(valid!=null?'This preview reports '+valid+'% finite offset pixels.':'A finite-pixel coverage percentage is not available in this preview.')+' Inspect spatial patterns and reject low-quality or high-uncertainty pixels before drawing conclusions.';}
  else if(lower.includes('interval')||lower.includes('date')||lower.includes('time')){heading='The acquisition interval';body='The reference acquisition is '+(ref||'not available')+' and the secondary acquisition is '+(sec||'not available')+'. '+(interval!==null?'They are '+interval+' days apart.':'The interval cannot be calculated from the available metadata.')+' This is the comparison interval for this GOFF product, not a repeat measurement series.';}
  else if(lower.includes('prove')||lower.includes('moving')||lower.includes('velocity')||lower.includes('speed')){heading='What this does — and does not — prove';body='No. A GOFF offset preview alone does not prove glacier flow speed, retreat, melt or mass loss. It provides radar-coordinate image offsets. A defensible glacier-motion result needs a confirmed glacier intersection, geometry conversion, acquisition interval, uncertainty assessment and independent validation.';}
  else body='I can explain the loaded product, acquisition interval, radar-coordinate offsets and quality indicators. Try one of the suggested questions. I will distinguish metadata and measurements from interpretation, and I will not infer glacier change from an unverified footprint.';
  setAnswer({heading,body});
 }
 return <div className="ai-page"><div className="ai-hero"><div className="aiicon"><Sparkles size={23}/></div><div><span className="eyebrowline"/> EVIDENCE-GROUNDED EXPLAINER<h2>Ask the signal. Not the hype.</h2><p>Plain-language help for NISAR observations, with measured values kept separate from scientific interpretation.</p></div></div>
 <div className="ai-context"><div><small>WORKSPACE EVIDENCE</small><b>{data?'GOFF observation loaded':'No observation loaded'}</b></div><div><small>REFERENCE DATE</small><b>{m.referenceStart?.slice(0,10)||'—'}</b></div><div><small>SECONDARY DATE</small><b>{m.secondaryStart?.slice(0,10)||'—'}</b></div><div><small>FINITE PREVIEW</small><b>{m.previewValidPercent!=null?m.previewValidPercent+'%':'—'}</b></div></div>
 <div className="ai-ask"><label htmlFor="gp-question">What would you like to understand?</label><div className="askrow"><input id="gp-question" value={question} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&question.trim())explain(question.trim())}} placeholder="Ask about offsets, quality, dates or glacier motion…"/><button className="primary" disabled={!question.trim()} onClick={()=>explain(question.trim())}>Explain <ArrowUpRight size={15}/></button></div><div className="ai-prompts">{prompts.map(p=><button key={p} onClick={()=>{setQuestion(p);explain(p)}}>{p}</button>)}</div></div>
 {answer&&<div className="ai-answer"><div className="ai-answer-label"><Sparkles size={15}/> EXPLANATION <span>Based on available workspace context</span></div><h3>{answer.heading}</h3><p>{answer.body}</p></div>}
 <div className="ai-guardrail"><ShieldCheck size={18}/><div><b>Scientific guardrails</b><p>This first version uses transparent, rule-based explanations, not a connected generative AI model. It does not invent measurements or claim glacier coverage. A generative assistant can be connected later with retrieval restricted to verified product metadata and processing outputs.</p></div></div></div>
}

function TimeMachine({data}){
 const m=data?.metadata||{},ref=m.referenceStart,sec=m.secondaryStart;
 const fmt=v=>v?new Date(v).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}):'Date unavailable';
 const days=ref&&sec?Math.round(Math.abs(new Date(sec)-new Date(ref))/86400000):null;
 const dateGap=days===null?'Waiting for an observation pair':days===0?'Same-day pair':days+' day'+(days===1?'':'s')+' between acquisitions';
 return <div className="time-page">
  <div className="time-hero"><div><span className="eyebrowline"/> OBSERVATION HISTORY<h2>Time, written in ice.</h2><p>Every GOFF observation is a comparison between two radar acquisitions. Explore the pair, its interval and the limits of what one pair can tell us.</p></div><div className="time-orbit"><Timer size={30}/><b>{days!==null?days+'d':'—'}</b><small>PAIR INTERVAL</small></div></div>
  {!data?<div className="time-empty"><Timer size={28}/><h3>Your timeline starts with an observation</h3><p>Open a GOFF product in NISAR Radar Lab. Its acquisition pair will appear here.</p></div>:
  <><div className="tm-summary"><div><small>SELECTED OBSERVATION</small><b>{m.granuleId?.includes('_UR_')?'Urgent Response GOFF':'Precision GOFF'}</b></div><div><small>TRACK</small><b>{m.trackNumber||'Not listed'}</b></div><div><small>ORBIT</small><b>{m.orbitPassDirection||'Not listed'}</b></div></div>
  <div className="tm-timeline"><div className="tm-line"></div><article className="tm-event"><span className="tm-node"></span><small>01 · REFERENCE</small><b>{fmt(ref)}</b><p>First acquisition in the pair</p><code>{ref||'Timestamp unavailable'}</code></article><div className="tm-gap"><span>{dateGap}</span></div><article className="tm-event tm-event-secondary"><span className="tm-node"></span><small>02 · SECONDARY</small><b>{fmt(sec)}</b><p>Second acquisition in the pair</p><code>{sec||'Timestamp unavailable'}</code></article></div>
  <div className="tm-insight"><ShieldCheck size={18}/><div><b>What changed over this interval?</b><p>The GOFF product estimates radar-coordinate offsets between these acquisitions. This pair alone does not show whether motion is speeding up, slowing down, seasonal, or long-term. A glacier time series needs multiple comparable observations over the same glacier and consistent processing.</p></div></div>
  <div className="tm-next"><div><b>Build a longer story</b><p>Search the same region in NISAR Radar Lab and compare additional acquisition pairs. Keep track, viewing geometry, product type and quality in mind.</p></div><span>PAIR ≠ TREND</span></div></>}
 </div>
}
function TimeMachine({data}){
 const m=data?.metadata||{},ref=m.referenceStart,sec=m.secondaryStart;
 const fmt=v=>v?new Date(v).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}):'Date unavailable';
 const days=ref&&sec?Math.round(Math.abs(new Date(sec)-new Date(ref))/86400000):null;
 const dateGap=days===null?'Waiting for an observation pair':days===0?'Same-day pair':days+' day'+(days===1?'':'s')+' between acquisitions';
 return <div className="time-page">
  <div className="time-hero"><div><span className="eyebrowline"/> OBSERVATION HISTORY<h2>Time, written in ice.</h2><p>Every GOFF observation is a comparison between two radar acquisitions. Explore the pair, its interval and the limits of what one pair can tell us.</p></div><div className="time-orbit"><Timer size={30}/><b>{days!==null?days+'d':'—'}</b><small>PAIR INTERVAL</small></div></div>
  {!data?<div className="time-empty"><Timer size={28}/><h3>Your timeline starts with an observation</h3><p>Open a GOFF product in NISAR Radar Lab. Its acquisition pair will appear here.</p></div>:
  <><div className="tm-summary"><div><small>SELECTED OBSERVATION</small><b>{m.granuleId?.includes('_UR_')?'Urgent Response GOFF':'Precision GOFF'}</b></div><div><small>TRACK</small><b>{m.trackNumber||'Not listed'}</b></div><div><small>ORBIT</small><b>{m.orbitPassDirection||'Not listed'}</b></div></div>
  <div className="tm-timeline"><div className="tm-line"></div><article className="tm-event"><span className="tm-node"></span><small>01 · REFERENCE</small><b>{fmt(ref)}</b><p>First acquisition in the pair</p><code>{ref||'Timestamp unavailable'}</code></article><div className="tm-gap"><span>{dateGap}</span></div><article className="tm-event tm-event-secondary"><span className="tm-node"></span><small>02 · SECONDARY</small><b>{fmt(sec)}</b><p>Second acquisition in the pair</p><code>{sec||'Timestamp unavailable'}</code></article></div>
  <div className="tm-insight"><ShieldCheck size={18}/><div><b>What changed over this interval?</b><p>The GOFF product estimates radar-coordinate offsets between these acquisitions. This pair alone does not show whether motion is speeding up, slowing down, seasonal, or long-term. A glacier time series needs multiple comparable observations over the same glacier and consistent processing.</p></div></div>
  <div className="tm-next"><div><b>Build a longer story</b><p>Search the same region in NISAR Radar Lab and compare additional acquisition pairs. Keep track, viewing geometry, product type and quality in mind.</p></div><span>PAIR ≠ TREND</span></div></>}
 </div>
}
function Movement({data}){
 const m=data?.metadata||{};
 const values=useMemo(()=>{if(!data)return null;const get=k=>(data[k]||[]).flat().filter(v=>v!==null&&Number.isFinite(v));const mid=a=>{if(!a.length)return null;const b=[...a].sort((x,y)=>x-y);return b[Math.floor((b.length-1)/2)]};return{along:mid(get('alongTrack')),slant:mid(get('slantRange')),corr:mid(get('correlation')),snr:mid(get('snr')),count:get('alongTrack').length}},[data]);
 const date=v=>v?new Date(v).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}):'Not available';
 const fmt=v=>v===null||v===undefined?'Not available':v.toFixed(2);
 return <div className="movement-page">
  <div className="movement-hero"><div><span className="eyebrowline"/> MOVEMENT INTELLIGENCE<h2>Understand what the radar sees.</h2><p>A simple guide to the measurements and their reliability. These are radar observations, not direct glacier-speed readings.</p></div><div className="move-mark"><Activity size={38}/><span>GOFF<br/>OBSERVATION</span></div></div>
  {!data?<div className="time-empty"><Activity size={28}/><h3>No observation selected yet</h3><p>Choose a GOFF product in NISAR Radar Lab. We’ll turn its measurements into a clear summary here.</p></div>:<>
   <section className="mi-simple-intro"><div><span className="mi-kicker">YOUR OBSERVATION</span><h3>{m.granuleId?'NISAR radar observation':'GOFF radar observation'}</h3><p>{values?.count?.toLocaleString()||'No'} pixels contain usable offset values in this preview.</p></div><div className="mi-simple-chip"><ShieldCheck size={16}/> Measurement summary</div></section>
   <section className="mi-simple-section"><div><span className="mi-kicker">THE MEASUREMENTS</span><h3>What the radar detected</h3><p>Two directions of apparent image displacement.</p></div><div className="mi-simple-grid">
    <article className="mi-simple-card"><div className="mi-simple-icon mint"><MoveHorizontal size={19}/></div><span>Along the satellite track</span><strong>{fmt(values?.along)} <small>{m.offsetUnits||'m'}</small></strong><p>Apparent shift in the direction the satellite travels.</p></article>
    <article className="mi-simple-card"><div className="mi-simple-icon blue"><Radar size={19}/></div><span>Across the radar view</span><strong>{fmt(values?.slant)} <small>{m.offsetUnits||'m'}</small></strong><p>Apparent shift in the radar’s viewing direction.</p></article>
   </div></section>
   <section className="mi-simple-section"><div><span className="mi-kicker">HOW CLEAR IS THE SIGNAL?</span><h3>Measurement quality</h3><p>These indicators help judge whether matching radar patterns are clear.</p></div><div className="mi-quality-grid">
    <article className="mi-quality-card"><div className="mi-quality-top"><span>Pattern match</span><b>{values?.corr===null?'Not available':fmt(values?.corr)}</b></div><div className="mi-quality-track"><span style={{width:Math.max(0,Math.min(100,(values?.corr||0)*100))+'%'}}/></div><p>Correlation indicator. Higher values mean a stronger pattern match; this is not a probability or a complete confidence score.</p></article>
    <article className="mi-quality-card"><div className="mi-quality-top"><span>Signal clarity</span><b>{values?.snr===null?'Not available':'Available'}</b></div><p>{values?.snr===null?'No signal-to-noise values were included in this preview.':'Signal-to-noise measurements are present and can help assess the radar signal relative to noise.'} The detailed value is kept out of the main summary.</p></article>
   </div></section>
   <section className="mi-plain-note"><ShieldCheck size={21}/><div><h3>So, is the glacier moving?</h3><p>This preview alone cannot tell us. It shows radar-image shifts, not glacier speed. To measure glacier movement, we still need to confirm the footprint overlaps a mapped glacier, convert radar directions into ground directions, check the acquisition interval and apply quality screening.</p><b>We’ll only show a glacier-motion result when those checks are complete.</b></div></section>
   <div className="mi-simple-footer"><span>Reference date · {date(m.referenceStart)}</span><span>Second date · {date(m.secondaryStart)}</span><span>Orbit · {m.orbitPassDirection||'Not available'}</span></div>
  </>}
 </div>
}
function Reports({data}){return <div className="panel empty"><div className="emptyicon"><BookOpen/></div><h2>Research notebook</h2><p>{data?'Granule metadata is available in the Radar Lab. Report generation can be added once processing provenance and derived outputs are finalized.':'Load a GOFF product to begin collecting acquisition metadata, processing notes and reproducible observations.'}</p><div className="tagrow"><span>Data provenance</span><span>Processing methods</span><span>Exportable reports · planned</span></div></div>}
createRoot(document.getElementById('root')).render(<App/>);
