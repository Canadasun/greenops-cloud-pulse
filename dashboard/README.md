# GreenOps dashboard

React + Vite dashboard for fleet and cold-chain operations. Run `npm ci`, then `npm run dev` to serve port 5173 with `/api` proxied to the local Functions host on 7071. Production nginx also proxies `/api`; Azure builds use `VITE_API_BASE` for the Function app's origin.

- **Overview:** attention counts, current telemetry coverage, a three-incident priority preview, and fleet snapshot.
- **Fleet:** search, condition/cargo/route filters, stable ID or condition sorting, and list/map display. Inspection opens a focused detail screen; Back restores the invoking control and list context.
- **Incidents:** Needs action, Monitoring and Resolved. Cargo breaches precede offline, door and delay incidents; oldest first within each group. All open incidents remain available. Resolved pages use server cursors in the URL.
- **System:** usage/capacity aggregates and explicitly labelled simulated fault controls. These are not service-level health checks.

Operator keys are validated by `/api/session`, retained only in memory, and required for acknowledgement and simulation changes. Internal navigation preserves the connection. Reload requires reconnecting. Persistent identity, assignments, escalation and sustainability metrics are separate product capabilities, not simulated by this interface.

Fleet and open incidents refresh every five seconds while visible, with error backoff and immediate refresh on return to the tab. API availability and sensor freshness are separate: readings older than 90 seconds are labelled stale. This display threshold does not change backend incident rules. History refreshes every five seconds for 1h and every 30 seconds for 6h/24h. Map code and route requests load only for map mode.

The history endpoint accepts `max_points=1000` for a representative chart, preserving bucket first/last/min/max samples and outage boundaries. Responses include `window_start`, `window_end` and `total_points`. Raw readings use `limit=50`, `offset`, and an anchored `end`. The raw table is paginated and is never substituted with chart samples. Outage boundaries can exceed the chart budget to preserve evidence. Storage retrieval still reads the selected window; this is not a database-level rollup.

## Validation

```bash
npm run typecheck      # incremental TypeScript API boundary
npm test               # frontend unit and lifecycle regressions
npm run build
npm run test:browser   # behavior + axe accessibility + responsive assertions
npm run test:a11y      # same integrated accessibility/browser suite
```

Install Chromium with `npx playwright install chromium`. The browser harness uses `../functions/.venv/bin/python`; override `GREENOPS_PYTHON` with an interpreter containing `functions/requirements-dev.txt`. It starts a temporary in-memory API, rejects startup failure/timeouts, and never changes the shared fleet or Azure. Test artifacts go to `docs/audit-2026-10-10/implemented/`.

Accessibility checks cover WCAG 2/2.1/2.2 A/AA axe rules, keyboard skip navigation, chart inspection, acknowledgement focus, inspector return focus, and overflow at 320/390/768/1440 px. Review artifacts and manual assistive-technology checks before claiming full WCAG conformance. Routine telemetry updates are not live announcements; action feedback and errors are announced.
