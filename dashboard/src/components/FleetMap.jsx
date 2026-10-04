// Live fleet map (F1, FR-10): OpenStreetMap tiles via Leaflet, one coloured, lettered marker per truck.
import L from 'leaflet';
import { MapContainer, Marker, Polyline, TileLayer, Tooltip } from 'react-leaflet';
import { STATUS, temp } from '../status';

const icon = (status, selected) => {
  const s = STATUS[status];
  return L.divIcon({
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<div class="marker${selected ? ' selected' : ''}" style="background:${s.color}">${s.letter}</div>`,
  });
};

export default function FleetMap({ trucks, routes, selected, onSelect }) {
  return (
    <MapContainer center={[44.7, -76.4]} zoom={7} className="map" scrollWheelZoom>
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {routes && Object.entries(routes).map(([id, r]) => (
        <Polyline key={id} positions={r.waypoints} pathOptions={{ color: '#5b6b8c', weight: 3, opacity: 0.45, dashArray: '6 8' }} />
      ))}
      {trucks.filter((t) => t.lat != null).map((t) => (
        <Marker key={t.truck_id} position={[t.lat, t.lon]} icon={icon(t.status, t.truck_id === selected)}
          eventHandlers={{ click: () => onSelect(t.truck_id) }} title={`${t.truck_id} – ${STATUS[t.status].label}`}>
          <Tooltip direction="top" offset={[0, -14]}>{t.truck_id} · {STATUS[t.status].label} · {temp(t.temp_c)}</Tooltip>
        </Marker>
      ))}
    </MapContainer>
  );
}
