import { endpoints } from '../api';

test('local build uses the nginx/Vite proxy paths', () => {
  expect(endpoints('')).toEqual({ api: '/api', sim: '/api/sim' });
});

test('Azure build calls the Function app directly, including the fault table', () => {
  expect(endpoints('https://func-greenops.azurewebsites.net/')).toEqual({
    api: 'https://func-greenops.azurewebsites.net/api',
    sim: 'https://func-greenops.azurewebsites.net/api/sim',
  });
});
