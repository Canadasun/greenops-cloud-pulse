import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { STATUS, temp } from '../status';
const icon = (status, selected) => {
  const s = STATUS[status] || STATUS.waiting;
  return L.divIcon({ className: '', iconSize: [34, 34], iconAnchor: [17, 17], html: `<div class="marker${selected ? ' selected' : ''}" style="background:${s.color};color:${s.text}">${s.letter}</div>` });
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
  return <MapContainer center={[44.7, -76.4]} zoom={7} className="map" scrollWheelZoom={false}>
    <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
    {routes && Object.entries(routes).map(([id, r]) => <Polyline key={id} positions={r.waypoints} pathOptions={{ color: '#546c7b', weight: 3, opacity: 0.5, dashArray: '6 8' }} />)}
    {visible.map(t => <Marker key={t.truck_id} position={[t.lat, t.lon]} icon={icon(t.status, t.truck_id === selected)} eventHandlers={{ click: () => onSelect(t.truck_id) }} title={`${t.truck_id} – ${STATUS[t.status].label}`}>
      <Tooltip>{t.truck_id} · {STATUS[t.status].label} · {temp(t.temp_c)}</Tooltip>
    </Marker>)}
    <Controls trucks={visible} selected={selected} />
  </MapContainer>;
}
