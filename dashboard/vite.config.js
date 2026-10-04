import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the API calls are forwarded to the local Functions host and the simulator's fault API.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:7071',
      '/sim': { target: 'http://localhost:8090', rewrite: (p) => p.replace(/^\/sim/, '') },
    },
  },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.js', globals: true },
});
