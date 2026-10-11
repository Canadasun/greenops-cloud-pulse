import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AlertHistory from '../components/AlertHistory';

const alerts = [
  { id: 'alt-1', truck_id: 'TRK-003', type: 'TEMPERATURE', details: '9.1 °C outside 2–8 °C', status: 'ACTIVE', started_at: '2026-10-03T14:05:00Z', email_sent_at: '2026-10-03T14:05:00Z', email_seconds: 0.1 },
  { id: 'alt-2', truck_id: 'TRK-002', type: 'DOOR_OPEN', details: 'door open 130 s', status: 'RESOLVED', started_at: '2026-10-03T13:20:00Z', email_sent_at: '2026-10-03T13:20:00Z', email_seconds: 0.1 },
];

test('lists alerts with readable titles and only ACTIVE ones can be acknowledged', () => {
  render(<AlertHistory alerts={alerts} onAcknowledge={() => {}} user="Dispatcher" />);
  expect(screen.getByRole('heading', { name: /Temperature breach/ })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /Door left open/ })).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: /Acknowledge/ })).toHaveLength(1);
});

test('clicking Acknowledge sends the alert id and the user', async () => {
  const onAck = vi.fn().mockResolvedValue({});
  render(<AlertHistory alerts={alerts} onAcknowledge={onAck} user="Dispatcher (demo)" />);
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge TRK-003 TEMPERATURE' }));
  await waitFor(() => expect(onAck).toHaveBeenCalledWith('alt-1', 'Dispatcher (demo)'));
});

test('shows a friendly message when there are no alerts', () => {
  render(<AlertHistory alerts={[]} onAcknowledge={() => {}} user="x" />);
  expect(screen.getByText(/No incidents reported/)).toBeInTheDocument();
});

test('an email whose retries were stopped is not shown as still queued', () => {
  const stopped = { ...alerts[1], id: 'alt-3', email_sent_at: null, email_status: 'abandoned' };
  render(<AlertHistory alerts={[stopped]} onAcknowledge={() => {}} user="x" />);
  expect(screen.getByText(/not delivered · retries stopped/)).toBeInTheDocument();
});
