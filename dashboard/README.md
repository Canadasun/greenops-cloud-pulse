# Dashboard – Role 5 (Idowu Ayeni)

React 18 + Vite + Leaflet / OpenStreetMap. Follows the Part 2 wireframe (Figure 8).

| Area | Feature | Data |
|---|---|---|
| Live fleet map – coloured, lettered markers (N, W, B, O) and route lines | F1, FR-10 | `GET /api/trucks`, `/api/routes` every 5 s (NFR-02) |
| Truck details + one-hour temperature chart with the safe band | F4, FR-10 | `GET /api/trucks/{id}/history?hours=1` |
| Alert history + **Acknowledge** | F9, FR-11 | `GET /api/alerts`, `POST /api/alerts/{id}/ack` |
| System health and cost | F11 | `GET /api/health` |
| Demo fault scenarios | FR-02 | simulator API through `/sim` |

`npm run dev` (proxies to the local Functions host on 7071 and the simulator on 8090) · `npm test` (9 Vitest tests) ·
`npm run build`. In Docker, nginx serves the build and forwards `/api` and `/sim` (Static Web Apps does this on Azure).
Login (F12) is planned for Part 4.
