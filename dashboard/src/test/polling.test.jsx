import { act, renderHook, waitFor } from '@testing-library/react';
import { usePolling, request } from '../api';

const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test('changing identity hides old data even when the new query fails', async () => {
  const next = deferred();
  const { result, rerender } = renderHook(({ id }) => usePolling(() => id === 'A' ? Promise.resolve({ truck: 'A' }) : next.promise, 5000, [id]), { initialProps: { id: 'A' } });
  await waitFor(() => expect(result.current.data?.truck).toBe('A'));
  rerender({ id: 'B' }); expect(result.current.data).toBeNull();
  await act(async () => next.reject(new Error('unavailable')));
  expect(result.current.data).toBeNull(); expect(result.current.error).toBe('unavailable');
});

test('slow requests never overlap and unmount aborts the request', async () => {
  vi.useFakeTimers(); const pending = deferred(), fn = vi.fn(() => pending.promise);
  const { unmount } = renderHook(() => usePolling(fn, 5000));
  await act(async () => vi.advanceTimersByTime(20000));
  expect(fn).toHaveBeenCalledTimes(1);
  const signal = fn.mock.calls[0][0].signal;
  unmount(); expect(signal.aborted).toBe(true);
});

test('an obsolete response cannot replace a newer truck result', async () => {
  const old = deferred();
  const { result, rerender } = renderHook(({ id }) => usePolling(() => id === 'A' ? old.promise : Promise.resolve('B'), 5000, [id]), { initialProps: { id: 'A' } });
  rerender({ id: 'B' }); await waitFor(() => expect(result.current.data).toBe('B'));
  await act(async () => old.resolve('A')); expect(result.current.data).toBe('B');
});

test('refresh retains same-query data and exposes a failure', async () => {
  const fn = vi.fn().mockResolvedValueOnce('cached').mockRejectedValueOnce(new Error('offline')).mockResolvedValue('new');
  const { result } = renderHook(() => usePolling(fn, 5000));
  await waitFor(() => expect(result.current.data).toBe('cached'));
  act(() => result.current.refresh()); await waitFor(() => expect(result.current.error).toBe('offline'));
  expect(result.current.data).toBe('cached');
  act(() => result.current.refresh()); await waitFor(() => expect(result.current.data).toBe('new'));
  expect(result.current.error).toBeNull();
});

test('successful HTTP with invalid JSON is still a failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.reject(new Error('html')) }));
  await expect(request('/api/trucks')).rejects.toThrow('unreadable');
});

test('a slow request still refreshes every 5 s, start to start (NFR-02)', async () => {
  vi.useFakeTimers();
  const fn = vi.fn(() => new Promise(resolve => setTimeout(() => resolve('ok'), 1500)));
  renderHook(() => usePolling(fn, 5000));
  await act(async () => { await vi.advanceTimersByTimeAsync(10100); });
  expect(fn).toHaveBeenCalledTimes(3); // starts at 0 s, 5 s and 10 s – not 0, 6.5 and 13 s
});
