import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { STATUS, temp } from '../status';
import { StatusBadge } from './UI';
const icon = (status, selected) => {
  const s = STATUS[status] || STATUS.waiting;
  return L.divIcon({ className: '', iconSize: [38, 38], iconAnchor: [19, 19], html: `<div class="marker${selected ? ' selected' : ''}" style="background:${s.color};color:${s.text}">${s.letter}</div>` });
};
function Controls({ trucks, selected }) {
  const map = useMap(), fitted = useRef(false);
  const fit = () => { if (trucks.length) map.fitBounds(trucks.map(t => [t.lat, t.lon]), { padding: [35, 35], maxZoom: 10 }); };
  useEffect(() => { if (!fitted.current && trucks.length) { fit(); fitted.current = true; } }, [trucks]);
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  const truck = trucks.find(t => t.truck_id === selected);
  return <div className="map-actions" ref={node => { if (node) { L.DomEvent.disableClickPropagation(node); L.DomEvent.disableScrollPropagation(node); } }}>
    <button onClick={fit} disabled={!trucks.length}>Fit fleet</button>
    <button disabled={!truck} onClick={() => map.setView([truck.lat, truck.lon], 10)}>Locate selected</button>
  </div>;
}
export default function FleetMap({ trucks, routes, selected, onSelect }) {
  const visible = trucks.filter(t => Number.isFinite(t.lat) && Number.isFinite(t.lon));
  const [tileError, setTileError] = useState(false);
  const selectedTruck = trucks.find(t => t.truck_id === selected);
  const routeIds = new Set(trucks.map(t => t.route_id));
  const groups = new Map();
  visible.forEach(t => { const key = `${t.lat.toFixed(5)},${t.lon.toFixed(5)}`; groups.set(key, [...(groups.get(key) || []), t]); });
  return <>{tileError && <p role="status" className="query-error">Map tiles are unavailable. Truck selection and readings remain available in the list.</p>}<MapContainer center={[44.7, -76.4]} zoom={7} className="map" scrollWheelZoom={false}>
    <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" eventHandlers={{ tileerror: () => setTileError(true), load: () => {} }} />
    {routes && Object.entries(routes).filter(([id]) => routeIds.has(id)).map(([id, r]) => <Polyline key={id} positions={r.waypoints} pathOptions={{ color: selectedTruck?.route_id === id ? '#116747' : '#546c7b', weight: selectedTruck?.route_id === id ? 5 : 3, opacity: selectedTruck?.route_id === id ? 1 : 0.5, dashArray: '6 8' }} />)}
    {visible.map(t => <Marker key={t.truck_id} position={[t.lat, t.lon]} icon={icon(t.status, t.truck_id === selected)} eventHandlers={{ click: () => onSelect(t.truck_id) }} title={`${t.truck_id} – ${(STATUS[t.status]?.label || 'Unknown condition')}`}>
      <Tooltip>{t.truck_id} · {(STATUS[t.status]?.label || 'Unknown condition')} · {temp(t.temp_c)}</Tooltip>
    </Marker>)}
    <Controls trucks={visible} selected={selected} />
  </MapContainer><div className="map-legend" role="group" aria-label="Map condition legend">{Object.keys(STATUS).map(status => <StatusBadge key={status} status={status} />)}</div>{[...groups.values()].filter(group => group.length > 1).map(group => <div className="map-overlap" key={group[0].truck_id}><p className="small">{group.length} trucks share this location. Choose a truck:</p>{group.map(t => <button key={t.truck_id} onClick={e => onSelect(t.truck_id, null, e.currentTarget)}>{t.truck_id}</button>)}</div>)}</>;
}
