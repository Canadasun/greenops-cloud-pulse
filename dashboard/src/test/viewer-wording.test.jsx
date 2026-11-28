import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import OverviewPage from '../pages/OverviewPage';
import IncidentsPage from '../pages/IncidentsPage';

// F12: operator keys were replaced by Microsoft sign-in in Part 4, so a view-only account must be told why it cannot act,
// in the same words as the fault panel, and never asked for an "operator key" that no longer exists.
const props = { trucks: { data: [] }, open: { data: { items: [] } }, params: new URLSearchParams(), change: () => {}, inspect: () => {}, acknowledge: () => {}, identity: null };

test('a viewer on the overview is told the account can view only, not asked for an operator key', () => {
  const { container } = render(<OverviewPage {...props} />);
  expect(screen.getByText(/Your account can view only/)).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/operator key/i);
});
test('a viewer in the incident centre is told the account can view only, not asked for an operator key', () => {
  const { container } = render(<IncidentsPage {...props} />);
  expect(screen.getByText(/Your account can view only/)).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/operator key/i);
});
test('an operator sees no view-only notice', () => {
  render(<OverviewPage {...props} identity="Dispatcher" />);
  expect(screen.queryByText(/Your account can view only/)).toBeNull();
});
