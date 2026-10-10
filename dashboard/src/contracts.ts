// Runtime validation and typed models at the server boundary. Reject malformed data
// as a query error, so the last good result remains explicitly stale.
export interface Truck {
  truck_id: string; route_id: string; cargo_type: string; origin: string; destination: string;
  status: string; open_alerts: string[]; temp_min_c: number; temp_max_c: number;
  temp_c?: number; humidity_pct?: number; speed_kmh?: number; lat?: number; lon?: number;
  last_seen?: string; scheduled_eta?: string; door_open?: boolean; simulation_time_scale?: number;
}
export interface Reading { timestamp: string; temp_c: number; humidity_pct?: number; door_open?: boolean; contiguous?: boolean }
export interface History { truck_id: string; hours: number; temp_min_c: number; temp_max_c: number; points: Reading[]; window_start?: string; window_end?: string; total_points?: number }
export interface Incident { id: string; truck_id: string; type: string; details: string; status: string; started_at: string; [key: string]: unknown }
type Obj = Record<string, unknown>;
const invalid = (): never => { throw new Error('The server returned unexpected data. Please retry.'); };
function object(v: unknown): Obj { if (!v || typeof v !== 'object' || Array.isArray(v)) invalid(); return v as Obj; }
function string(v: unknown): string { if (typeof v !== 'string') invalid(); return v as string; }
function number(v: unknown): number { if (typeof v !== 'number' || !Number.isFinite(v)) invalid(); return v as number; }
function date(v: unknown): string { const s = string(v); if (!Number.isFinite(Date.parse(s))) invalid(); return s; }
function array(v: unknown): unknown[] { if (!Array.isArray(v)) invalid(); return v as unknown[]; }
export function parseTrucks(value: unknown): Truck[] {
  return array(value).map(value => { const t = { ...object(value) };
    for (const key of ['truck_id', 'route_id', 'cargo_type', 'origin', 'destination', 'status']) string(t[key]);
    for (const key of ['temp_min_c', 'temp_max_c']) number(t[key]);
    for (const key of ['temp_c', 'humidity_pct', 'speed_kmh', 'lat', 'lon', 'simulation_time_scale']) if (t[key] != null) number(t[key]);
    for (const key of ['last_seen', 'scheduled_eta']) if (t[key] != null) date(t[key]);
    if (t.door_open != null && typeof t.door_open !== 'boolean') invalid();
    t.open_alerts = array(t.open_alerts).map(string);
    return t as unknown as Truck;
  });
}
export function parseHistory(value: unknown): History {
  const h = { ...object(value) }; string(h.truck_id); number(h.hours); number(h.temp_min_c); number(h.temp_max_c);
  for (const key of ['window_start', 'window_end']) if (h[key] != null) date(h[key]);
  if (h.total_points != null) number(h.total_points);
  h.points = array(h.points).map(value => { const p = object(value); date(p.timestamp); number(p.temp_c); if (p.humidity_pct != null) number(p.humidity_pct); return p; });
  return h as unknown as History;
}
export function parseAlerts(value: unknown): { items: Incident[]; next_cursor: string | null } {
  const page = object(value); if (page.next_cursor != null) string(page.next_cursor);
  return { items: array(page.items).map(value => { const a = object(value); for (const key of ['id', 'truck_id', 'type', 'details', 'status']) string(a[key]); date(a.started_at); return a as Incident; }), next_cursor: page.next_cursor as string | null };
}
export function parseRoutes(value: unknown): Record<string, { waypoints: number[][] }> {
  const routes = object(value);
  for (const value of Object.values(routes)) { const r = object(value); for (const point of array(r.waypoints)) { const p = array(point); if (p.length !== 2) invalid(); p.forEach(number); } }
  return routes as Record<string, { waypoints: number[][] }>;
}
export interface Health {
  iot_hub_sku: string; messages_today: number; daily_allowance: number | null;
  alerts_today: number; emails_today: number; avg_email_seconds: number;
  projected_messages_per_day: number; estimated_monthly_cost_usd: number;
  capacity_warning: boolean; cost_note: string;
}
export function parseHealth(value: unknown): Health {
  const h = object(value);
  for (const key of ['iot_hub_sku', 'cost_note']) string(h[key]);
  for (const key of ['messages_today', 'alerts_today', 'emails_today', 'avg_email_seconds', 'projected_messages_per_day', 'estimated_monthly_cost_usd']) number(h[key]);
  if (h.daily_allowance != null) number(h.daily_allowance);
  if (typeof h.capacity_warning !== 'boolean') invalid();
  return h as unknown as Health;
}
export function parseSession(value: unknown): { can_operate: boolean; user: string | null } {
  const s = object(value);
  if (typeof s.can_operate !== 'boolean') invalid();
  if (s.can_operate) string(s.user);
  return s as { can_operate: boolean; user: string | null };
}
export function parseFaults(value: unknown): Record<string, string> {
  const faults = object(value);
  for (const scenario of Object.values(faults)) if (!['none', 'compressor', 'door', 'delay', 'offline'].includes(string(scenario))) invalid();
  return faults as Record<string, string>;
}
export function parseIncident(value: unknown): Incident {
  return parseAlerts({ items: [value], next_cursor: null }).items[0];
}
