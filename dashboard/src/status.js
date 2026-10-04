// Status rules shown on the map and in the header (Part 1, Section 5.5; Part 2, Figure 8).
// Every status has a colour AND a letter, so it is readable without colour.
export const STATUS = {
  normal: { label: 'Normal', letter: 'N', color: '#1f9d63', text: '#0f5132' },
  warning: { label: 'Warning', letter: 'W', color: '#e0a100', text: '#664d03' },
  breach: { label: 'Breach', letter: 'B', color: '#d64545', text: '#842029' },
  offline: { label: 'Offline', letter: 'O', color: '#8c8c88', text: '#41413e' },
  waiting: { label: 'Waiting for data', letter: '…', color: '#c9c9c4', text: '#41413e' },
};

export const ALERT_TITLES = {
  TEMPERATURE: 'Temperature breach',
  HUMIDITY: 'Humidity breach',
  DOOR_OPEN: 'Door left open',
  OFFLINE: 'Truck offline',
  DELAYED: 'Truck delayed',
};

export const CARGO = { vaccines: 'Vaccines', fresh_produce: 'Fresh produce', frozen_food: 'Frozen food' };

export function countByStatus(trucks) {
  const counts = { normal: 0, warning: 0, breach: 0, offline: 0, waiting: 0 };
  for (const t of trucks) counts[t.status] = (counts[t.status] || 0) + 1;
  return counts;
}

export function ago(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return `${Math.floor(seconds / 3600)} h ago`;
}

export function clock(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit', hour12: false });
}

export function temp(c) {
  return c == null ? '—' : `${c.toFixed(1)} °C`;
}

export function inRange(t) {
  return t.temp_c != null && t.temp_c >= t.temp_min_c && t.temp_c <= t.temp_max_c;
}
