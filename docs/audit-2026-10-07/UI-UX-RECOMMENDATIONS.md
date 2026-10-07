# GreenOps Cloud Pulse — senior frontend UI/UX review

Based on the React implementation and browser checks at 1440px and 390px. The recommendations below were used as the remediation checklist; the resulting changes are implemented in the current dashboard.

The dashboard should help a dispatcher answer three questions quickly: which trucks need attention, what is happening, and what action has already been taken. The current map communicates location well, but a long history table dominates the page and incident actions can be difficult to reach.

## Recommended layout

**Desktop:** a compact header with connection status and last successful update; a row of actionable fleet counts; then a searchable fleet list, map and selected-truck details. Put a short active-incident queue directly below the summary or alongside the selected truck. Move resolved history into a separate tab with pagination. Keep system health and demo controls in secondary views.

**Mobile:** start with an “Attention needed” list and a truck selector. Use Fleet / Map / Alerts navigation; show truck details as a dedicated view or accessible drawer. Alerts become stacked cards with an always-visible action. Keep map gestures inside the map and prevent page-wide horizontal scrolling.

## Priorities

| Priority | Change | Why it matters | Completion check |
|---|---|---|---|
| P0 | Correct history identity when switching trucks | The current UI temporarily labels one truck's readings as another's and can show false breaches. | Delay/fail the new history request: the previous truck's data must never appear under the new selection. |
| P0 | Expose errors and stale data in every panel | A successful fleet refresh currently masks failed alerts or history requests. | An alerts-only outage shows an inline error, last successful update and retry; existing rows are explicitly marked stale. |
| P0 | Contain mobile alerts and controls | At 390px, an active-alert row produced a 534px document and pushed Acknowledge outside its card. | No document overflow at 320/390/768px; all actions remain reachable without horizontal page scrolling. |
| P1 | Separate active incidents from resolved history | New resolved rows can displace older active alerts from the newest-50 response. | Every open incident remains accessible regardless of the amount of resolved history. |
| P1 | Add fleet search and selection independent of the map | Missing GPS and overlapping markers should not prevent selecting a truck. | Select every truck, including waiting/offline trucks, by keyboard and touch without using the map. |
| P1 | Make acknowledge and fault changes update immediately | Current controls remain in the old state until a later poll. | Show a per-item pending state, reconcile the returned result, and retain a clear retry path on failure. |
| P1 | Improve timestamp context | Time-only alerts cannot distinguish today from yesterday or identify the displayed timezone. | Show relative age plus date/time/timezone on focus or expansion; ETA includes early/late/arrived context. |
| P2 | Add chart inspection and missing-data gaps | A static line offers little diagnostic context and can connect across an outage. | Users can inspect values by pointer/keyboard, change the time window, and identify intervals without samples. |
| P2 | Refine typography, spacing and status contrast | Small metadata badges compete with operational information; some status backgrounds use white text unnecessarily. | Use consistent type/spacing tokens, readable status text, visible focus and verified contrast. |

## Interaction details

- Make status counts filters: selecting “2 breaches” filters the fleet and incident queue. Include “Waiting for data” so counts explain the entire fleet.
- Make truck IDs in alerts selectable. Selecting an incident should open that truck, highlight the incident and make the relevant history easy to inspect.
- Give incidents clear states: Active, Acknowledged and Resolved. Show who acknowledged and when; acknowledgement should not visually imply recovery.
- Add “Fit fleet” and “Locate selected truck.” Auto-fit the initial fleet, but do not repeatedly move the map after the user pans.
- Keep the last good result during refresh for the same truck, with a stale indication on failure. On a different truck, show its cached data or a loading state. Do not reuse another truck's chart.
- Use truthful empty states: “No incidents reported” and “Waiting for first telemetry” instead of claiming the fleet is healthy before readings exist.
- Distinguish “Email queued,” “Sent” and “Failed.” The frontend needs a corresponding backend delivery-state contract; do not infer delivery from a successful enqueue call.
- Display “Demo operator” instead of “Signed in” until authentication exists. Move requirement identifiers such as FR-10 to project documentation or an optional demo explanation.

## Frontend implementation approach

1. Replace the current minimal polling contract with keyed request state: data, loading, refreshing, error, last-success time, and an explicit refresh function. Prevent overlapping/stale responses and abort obsolete requests. A small shared implementation is sufficient if these guarantees are tested.
2. Keep selection and filters in URL parameters so a truck or incident can be bookmarked and browser Back works predictably. Key history by truck ID and requested time window.
3. Build shared status badges, inline loading/error/empty states and pending-action buttons. Use semantic headings, labelled inputs and polite announcements for action results.
4. Use server pagination for resolved history and a separate open-incidents query. Do not solve the newest-50 problem only with client filtering.
5. Use a bounded alert-history region or separate page so its row count does not stretch unrelated cards. Stack fault controls on narrow screens.
6. Test meaningful user outcomes with delayed and failed API responses, keyboard navigation, mobile viewport assertions and truck-selection transitions. Keep screenshots for regression review, alongside behavior tests.

## Recommended first delivery

Ship chart identity, partial-failure visibility, mobile containment and immediate action feedback together. Then introduce the fleet selector and active-incident queue. Visual polish should follow once the displayed state and core dispatch flow are dependable.

Evidence: [full technical audit](REPORT.md), [desktop](desktop.png), [mobile alert overflow](mobile-alert.png).
