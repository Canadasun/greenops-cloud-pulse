import { render, screen } from '@testing-library/react';
import { ClockContext, Freshness, StatusBadge, prioritize } from '../components/UI';
import { parseTrucks, parseHistory } from '../contracts';
import TempChart from '../components/TempChart';
test('stale age advances without a successful API request', () => {
  const start = Date.parse('2026-10-10T00:00:00Z');
  const { rerender } = render(<ClockContext.Provider value={start + 20000}><Freshness lastSeen="2026-10-10T00:00:00Z" /></ClockContext.Provider>);
  expect(screen.getByText('20 s ago')).toBeInTheDocument();
  rerender(<ClockContext.Provider value={start + 120000}><Freshness lastSeen="2026-10-10T00:00:00Z" /></ClockContext.Provider>);
  expect(screen.getByText('Stale · 2 min ago')).toBeInTheDocument();
});
test('a parked truck shows its last reading in plain text, not as stale', () => {
  const start = Date.parse('2026-10-10T00:00:00Z');
  const { container } = render(<ClockContext.Provider value={start + 120000}><Freshness lastSeen="2026-10-10T00:00:00Z" parked /></ClockContext.Provider>);
  expect(screen.getByText('Parked · last reading 2 min ago')).toBeInTheDocument();
  expect(container.querySelector('.freshness.stale')).toBeNull();
});
test('unknown conditions remain readable and malformed readings fail safely', () => {
  render(<StatusBadge status="new-status" />);
  expect(screen.getByText(/Unknown condition/)).toBeInTheDocument();
  expect(() => parseTrucks([{}])).toThrow(/unexpected data/);
  expect(() => parseHistory({truck_id:'a',hours:1,temp_min_c:2,temp_max_c:8,points:[{timestamp:'invalid',temp_c:4}]})).toThrow(/unexpected data/);
});
test('incident priority prefers cargo then age without mutating the server response', () => {
  const input = [{id:'1',type:'DELAYED',started_at:'2026-10-10T00:00:00Z'}, {id:'2',type:'TEMPERATURE',started_at:'2026-10-10T02:00:00Z'}, {id:'3',type:'TEMPERATURE',started_at:'2026-10-10T01:00:00Z'}];
  expect(prioritize(input).map(a=>a.id)).toEqual(['3','2','1']);
  expect(input[0].id).toBe('1');
});
test('chart represents leading and trailing missing data in the requested window', () => {
  const points = [{timestamp:'2026-10-10T00:10:00Z',temp_c:4},{timestamp:'2026-10-10T00:10:10Z',temp_c:5}];
  const {container} = render(<TempChart points={points} min={2} max={8} start="2026-10-10T00:00:00Z" end="2026-10-10T01:00:00Z" />);
  expect(container.querySelectorAll('.missing-band')).toHaveLength(2);
  expect(screen.getByRole('slider')).toHaveAttribute('aria-valuetext', expect.stringContaining('5.0 °C'));
});
