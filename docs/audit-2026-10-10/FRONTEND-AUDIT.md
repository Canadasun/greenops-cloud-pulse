# GreenOps frontend audit and upgrade proposal

Reviewed 10 October 2026. Scope: every dashboard source component, styles, API client and polling lifecycle; dashboard-facing Functions contracts; build/serving configuration, CI, existing frontend tests, prior remediation notes and freshly generated browser screenshots. This is a frontend/product audit across the build, not a fresh certification of Azure infrastructure, security, or the ingestion pipeline. Live Azure, real operator research, assistive-technology testing and production performance were not exercised.

## Assessment

GreenOps has a functional, compact React foundation. The next upgrade should focus on dispatch decisions: identify a problem, inspect its evidence, take an action, and confirm its outcome. Today the layout gives too much space to repeated navigation, metadata and incident cards, and too little to the selected truck and diagnostic chart.

Preserve the existing safe-range visualization, non-color status labels, explicit stale/error states, request cancellation, keyed history, URL selection, server-owned operator identity and mutation feedback. These are implemented improvements; the older audit's fixed findings should not be presented as new defects.

## Evidence and validation

- `npm test`: 17 tests passed across 5 files.
- `npm run build`: passed; JavaScript 322.69 kB / 99.67 kB gzip, CSS 24.07 kB / 8.89 kB gzip. These are build sizes, not measured loading performance.
- `npm run test:browser`: passed operator authentication, acknowledgement, history identity, fault mutation, resolved pagination, partial outage and 15 combinations of five views at 320/390/768 px. It required execution outside the sandbox to bind a temporary local API.
- Screenshots: [desktop](current-desktop.png), [mobile](current-mobile.png). They use the deterministic in-memory API, not live fleet telemetry. Map tile rendering depends on network availability.
- The browser runner initially exited with code zero after its Python server failed to bind. The successful rerun printed the explicit completion message. Improve the harness to reject child startup failure and timeout instead of treating process exit alone as proof of success.

## Prioritized findings

P1 means address in the first redesign release; P2 means the next increment. The findings below distinguish reproducible code behavior from proposed improvements.

| Priority | Finding and evidence | User consequence | Recommended change and acceptance |
|---|---|---|---|
| P1 | `App.jsx` renders the same fleet list/map/detail composition for Overview, Fleet and Map. Fleet and Map are effectively identical on desktop; all use the heading “Fleet overview.” | Navigation promises different workspaces without delivering them. | Overview summarizes exceptions; Fleet provides list/map modes with a persistent inspector; Incidents owns triage/history. Each destination has a distinct title and task. |
| P1 | `App.jsx` computes selected truck from the full list while computing visible trucks separately. Select TRK-001, then filter to a status excluding it. | Details can describe a truck absent from the visible fleet. An incident link also preserves unrelated filters. | Either explicitly label a pinned selection outside the filter or clear/reconcile selection. Incident navigation must reveal its truck and preserve a return path. Test filter, search, Back and direct links. |
| P1 | `useLocation.change` calls `pushState` for every search keystroke. | Back walks through each character; URL state feels broken. | Replace history during typing; push for intentional navigation/committed filters. One Back should return to the prior destination. |
| P1 | Desktop screenshot places the fleet cards at roughly y=823 after a single acknowledged incident; `.attention` has its own scrolling region at higher counts. | Monitoring context is below the fold and triage requires nested scrolling. | Show a compact summary and a few actionable incident rows on Overview, with a clearly labelled link/count for all incidents. Keep the full queue on Incidents. |
| P1 | Mobile stacks every truck before the selected detail; clicking a truck does not move focus or navigate to details. | The result of a tap may be far outside the viewport. | Open a dedicated truck screen or accessible sheet. Preserve list position on return, move focus to the detail heading, and return focus to the invoking row. |
| P1 | `alert_page` sorts OPEN by newest start time; `AlertHistory` intermixes ACTIVE and ACKNOWLEDGED, with no priority/duration filters. | Recent acknowledged warnings can displace the most actionable problems visually. | Separate Needs action / Monitoring / Resolved; sort using a documented operational priority policy, then age. Show time open, measurement and threshold. Never infer recovery from acknowledgement. |
| P1 | `QueryState` leaves stale values in place correctly, but header connection describes only the fleet request. Counts begin at zero before data loads; `seconds_ago` freezes if the API fails. | Successful HTTP polling, fresh sensor readings and complete incident visibility can be confused. | Distinguish API availability from telemetry freshness. Use unknown placeholders until loaded, retain per-panel errors, and compute live age from `last_seen`. All-stale trucks must not look like fresh telemetry merely because GET succeeds. |
| P2 | Map renders every route regardless of truck filtering, uses status letters without an on-map legend, and overlapping markers have no disambiguation. | Spatial context is harder to interpret and co-located vehicles are hard to select. | Highlight the selected route; dim or hide unrelated routes; add a legend and co-located-truck chooser. Keep fleet-list selection. Clustering is optional if scale warrants it. |
| P2 | Truck temperature, door, ETA and last message share a relatively flat definition-list hierarchy; chart occupies a narrow third column. | Critical cargo evidence is harder to scan than secondary metadata. | Lead with temperature, safe range, excursion amount and last reading age; enlarge the chart and place route/humidity/speed below. Show incident context beside the evidence. |
| P2 | `TempChart` scales x to first/last returned sample, even for a selected 24-hour window; it handles internal gaps but does not visualize a trailing outage. | Two recent samples can visually fill a chart labelled “24 hours.” | Use the requested time window on the axis, visibly mark unavailable spans including the end, and retain table/keyboard inspection. |
| P2 | History is fetched in full every five seconds. At a continuous 10-second cadence a truck can produce 8,640 points/day. SVG breach circles, table rows and linear pointer searches scale with this count. | Long histories can cause unnecessary transfer and interaction work. This is a risk inferred from implementation, not a measured slowdown. | Benchmark realistic 24-hour data; use backend buckets retaining min/max excursions, incremental retrieval where needed, and paginated raw readings. Do not smooth away breaches. |
| P2 | `OperatorAccess` uses a memory-only key; the brand anchor reloads the document. | Clicking the brand loses operator state; reload requires reconnecting. | Make internal navigation client-side. Keep the current key flow for the demo; product authentication requires a backend-supported session/identity design. Do not fix persistence by saving bearer keys to localStorage. |
| P2 | `App.jsx` combines routing, queries, access and all pages; statuses are directly indexed in several components; there is no render error boundary. | Future changes are harder to isolate and unexpected response shapes can break the screen. | Extract page components and shared primitives, type API models, normalize unknown states, and add a recoverable error boundary. Keep tested polling guarantees. |
| P2 | Readability relies heavily on 10–13 px metadata and badges. Automated browser coverage checks overflow but not full keyboard/screen-reader workflows. | Fitting a screen does not establish comfortable use or accessibility. | Use a readable type scale, test zoom/reflow, focus movement and announcements, and add automated accessibility checks plus manual keyboard/screen-reader review. |
| P2 | Dashboard README still says login is planned, lists nine tests, and describes stale API/proxy behavior. | Onboarding and deployment expectations diverge from the implementation. | Update documentation alongside the redesign; describe current key access and actual API routing. |

Important non-finding: although the client sends `limit=20`, the server intentionally returns every OPEN incident and ignores pagination for that bounded set. Open incidents are not truncated by that limit.

## Proposed experience

### Navigation

Use Overview, Fleet, Incidents and System. Place Simulation inside System with an explicit demo label and operator gating. Fleet contains List / Map modes rather than two nearly identical primary destinations. Keep the navigation compact for this six-truck product; a sidebar is only warranted when the information architecture grows.

### Overview

Show four compact summaries: trucks needing attention, active incidents needing acknowledgement, offline/waiting trucks, and reporting trucks. Make definitions visible: “Reporting” measures freshness, not HTTP connectivity; “Normal” is an observed state, not proof of compliance.

Under the summaries, show a compact priority queue beside a fleet snapshot. A queue row includes truck, issue, latest measurement/range, time open, acknowledgement state and Inspect. Keep secondary email metadata in expansion. An explicit “View all N incidents” preserves discoverability when the preview is capped.

### Fleet workspace

On wide screens use a searchable, sortable fleet table/list at left and a larger selected-truck workspace at right. Offer map mode for geographic tasks. The inspector shows cargo/route, a prominent temperature value and safe range, telemetry freshness, active issues, a wide history chart, then supporting readings. The selected route is visually distinct. History windows remain 1h/6h/24h.

Table columns: truck, route/cargo, temperature versus range, condition, last reading, scheduled arrival. Support status/route/cargo filters with visible chips and Clear all. Maintain stable row order during polling unless an explicit priority sort is chosen.

### Incidents

Use Needs action / Monitoring / Resolved tabs, independent incident filters and a shared detail panel. Clicking an incident should open the truck's evidence at the relevant time while retaining a return link. Keep action semantics narrow: Acknowledge means someone has seen the issue; recovery comes from telemetry. Assignment, notes, escalation and incident timelines beyond existing timestamps need explicit backend support.

### Mobile

Use Overview / Fleet / Incidents / More navigation with readable labels. Start with a concise attention summary. Open truck details as a dedicated screen or sheet; avoid making users scroll through the entire fleet after each selection. Use a sticky action region only when it does not obscure content or focused controls. Map is an intentional mode, with list access always available.

### System and simulation

Separate ingestion/capacity information from scenario controls within System. The current endpoint exposes usage and alert/email aggregates, not individual service health; label what is actually known. Show configured cost with its existing exclusions. Present simulated faults as demo controls, with selected state, pending feedback and an obvious per-truck return to Normal.

## Visual direction

Aim for a calm operations console: warm off-white canvas, white surfaces, deep green navigation/selection and charcoal text. Reserve red and amber for operational meaning. Keep the existing GreenOps identity, reduce repeated borders and oversized empty cards, and increase information hierarchy.

- Type: approximately 28 px page title, 18 px section title, 14–16 px body, 12–13 px secondary metadata. Use tabular numerals for readings and ages.
- Spacing: shared 4/8/12/16/24/32 px tokens; consistent 8–12 px surface radii; subtle elevation for overlays only.
- Status: common badge component with label/icon; distinguish operational condition from acknowledgement state.
- Interaction: consistent hover, selected, focus, disabled, pending, success and error states; avoid movement from routine polling.
- Loading: preserve layout with lightweight placeholders; show actual last-success time on failure and concise freshness in normal operation.
- Avoid adding decorative analytics, emissions estimates, cost savings or “compliance scores” without supporting data. The GreenOps name does not establish a carbon measurement model.

Use WCAG 2.2 AA as the acceptance target. Review contrast, focus visibility/non-obscuration, target size, reflow and status announcements. See the [W3C WCAG 2.2 guidance](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/). A larger 44 px target remains a useful touch design goal; do not confuse it with the AA minimum rule. No conformance claim is made by this audit.

## Technical approach and dependency boundaries

Retain React, Vite and Leaflet initially. The observed usability problems do not require a framework rewrite. First extract OverviewPage, FleetPage, IncidentsPage and SystemPage; shared StatusBadge, FreshnessIndicator, FilterBar, IncidentRow and TruckInspector components; and centralized design tokens. Introduce TypeScript incrementally at the API boundary. Only adopt a router or query library if the new route/cache needs justify migration of the tested current behavior.

Immediately feasible with current contracts: layout, filter reconciliation, URL history fix, compact queue, state tabs, freshness display, map route emphasis, selected-truck detail and chart axis improvements.

Backend-dependent: secure persistent sign-in, explicit incident ownership/notes/escalation, aggregated history, service-level diagnostics, exports with durable audit semantics, delivery predictions and any sustainability metrics. Scope these independently; do not mock them as live facts in a production interface.

Performance: lazy-load map code when a view needs it, avoid map mounting on mobile views that merely hide it with CSS, and consider slower/static route refresh. Review background polling and retry backoff against the five-second foreground refresh requirement. Validate optimizations against fresh and stale state behavior.

## Delivery sequence and acceptance

1. **Correct navigation and context.** Distinct destinations, search replaceState, explicit filter/selection policy, direct mobile details, unknown/loading summary states and non-reloading brand navigation. Test browser Back, deep links, filtered incident navigation and partial outages.
2. **Build the operations workspace.** Design tokens and reusable components, compact Overview, Fleet list/map modes, large inspector and action-oriented incident tabs. Review populated, empty, waiting, offline, acknowledged and error screens on desktop and mobile.
3. **Strengthen diagnostics and scale.** Full-window chart/gaps, realistic history performance tests, map overlap handling, API typing, error recovery, accessible focus/announcements and improved browser-runner failure reporting.
4. **Add product capabilities only with contracts.** Persistent identity, ownership/escalation, exports and richer system diagnostics as separate backend/frontend work.

Suggested usability acceptance targets, not measured baselines: a dispatcher can identify the highest-priority unacknowledged incident within ten seconds; reach its truck evidence in one interaction; return to the exact previous list context; and distinguish fresh, stale and never-reported data without relying on color. Confirm these targets with actual operators.

Add meaningful regression cases for filtered selection, search history, mobile detail focus/return, more than 20 open incidents, stale ages, long history, overlapping markers and startup-failure detection in the browser harness. Retain the existing passing tests. Do not treat screenshots alone as performance or accessibility evidence.
