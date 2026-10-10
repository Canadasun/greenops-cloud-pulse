import { STATUS, ago, countByStatus, inRange, needsAttention, temp } from '../status';

test('every status has a colour and a letter (readable without colour)', () => {
  for (const s of Object.values(STATUS)) {
    expect(s.color).toMatch(/^#/);
    expect(s.letter.length).toBeGreaterThan(0);
  }
});

test('counts trucks per status for the header chips', () => {
  const c = countByStatus([{ status: 'normal' }, { status: 'breach' }, { status: 'normal' }, { status: 'offline' }]);
  expect(c).toEqual({ normal: 2, warning: 0, breach: 1, offline: 1, waiting: 0, parked: 0 });
});

test('friendly time and temperature text', () => {
  expect(ago(3)).toBe('3 s ago');
  expect(ago(125)).toBe('2 min ago');
  expect(ago(null)).toBe('—');
  expect(temp(4.25)).toBe('4.3 °C');
});

test('in-range check uses each truck’s own cargo limits', () => {
  expect(inRange({ temp_c: 4, temp_min_c: 2, temp_max_c: 8 })).toBe(true);
  expect(inRange({ temp_c: -10, temp_min_c: -25, temp_max_c: -15 })).toBe(false);
});

test('a parked truck (planned end of a demo run) has its own status and needs no attention', () => {
  expect(STATUS.parked.label).toBe('Parked');
  expect(countByStatus([{ status: 'parked' }, { status: 'parked' }, { status: 'offline' }]).parked).toBe(2);
  expect(needsAttention({ status: 'parked' })).toBe(false);
  expect(needsAttention({ status: 'normal' })).toBe(false);
  for (const status of ['breach', 'warning', 'offline', 'waiting']) expect(needsAttention({ status })).toBe(true);
});
