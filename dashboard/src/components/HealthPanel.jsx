export default function HealthPanel({ health }) {
  if (!health) return null;
  const pct = health.daily_allowance ? Math.min(100, Math.round(health.messages_today / health.daily_allowance * 100)) : 0;
  return <>
    {health.capacity_warning && <p role="alert" className="error">Projected traffic exceeds the configured plan's daily allowance. Capacity does not upgrade automatically.</p>}
    <dl className="readings">
      <dt>Configured plan</dt><dd>{health.iot_hub_sku}</dd>
      <dt>Messages today (UTC)</dt><dd>{health.messages_today.toLocaleString()}{health.daily_allowance && <> / {health.daily_allowance.toLocaleString()}<div className="meter" role="meter" aria-label="Daily message allowance used" aria-valuenow={pct} aria-valuemin="0" aria-valuemax="100"><span style={{ width: `${pct}%` }} /></div></>}</dd>
      <dt>Alerts today (UTC)</dt><dd>{health.alerts_today}</dd>
      <dt>Emails sent for today's alerts</dt><dd>{health.emails_today} · average event-to-send {health.avg_email_seconds} s</dd>
      <dt>Projected messages / day</dt><dd>{health.projected_messages_per_day.toLocaleString()}</dd>
      <dt>Configured base cost / month</dt><dd>USD {health.estimated_monthly_cost_usd.toFixed(2)}</dd>
    </dl><p className="small muted">{health.cost_note}</p>
  </>;
}
