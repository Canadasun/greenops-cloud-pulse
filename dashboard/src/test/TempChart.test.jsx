import { render, screen } from '@testing-library/react';
import TempChart from '../components/TempChart';

const pts = [4, 5, 9.2, 10].map((t, i) => ({ timestamp: `2026-10-03T14:0${i}:00Z`, temp_c: t }));

test('draws the safe band and marks every reading outside it', () => {
  const { container } = render(<TempChart points={pts} min={2} max={8} />);
  expect(screen.getByRole('img', { name: /safe range 2 to 8/ })).toBeInTheDocument();
  expect(container.querySelectorAll('.breach-dot')).toHaveLength(2);
  expect(container.querySelector('.temp-line').getAttribute('points').split(' ')).toHaveLength(4);
});

test('asks for patience until there are two readings', () => {
  render(<TempChart points={pts.slice(0, 1)} min={2} max={8} />);
  expect(screen.getByText(/Collecting readings/)).toBeInTheDocument();
});
