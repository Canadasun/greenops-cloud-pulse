// System health and cost panel (F11 – a "Could" feature, built early because the data was available).
export default function HealthPanel({ health }) {
  if (!health) return <p className="muted">Loading…</p>;
  const pct = Math.min(100, Math.round((health.messages_today / health.iot_hub_free_daily_limit) * 100));
  return (
    <dl className="readings">
      <dt>Messages today</dt>
      <dd>{health.messages_today.toLocaleString()} / {health.iot_hub_free_daily_limit.toLocaleString()} free
        <div className="meter" aria-label={`${pct}% of the free daily IoT Hub messages used`}><span style={{ width: `${pct}%` }} /></div></dd>
      <dt>Alerts today</dt><dd>{health.alerts_today} (emails sent: {health.emails_today}, average {health.avg_email_seconds} s)</dd>
      <dt>Projected messages / day</dt><dd>{health.projected_messages_per_day.toLocaleString()}</dd>
      <dt>Estimated cost / month</dt><dd>USD {health.estimated_monthly_cost_usd.toFixed(2)}</dd>
      <dt>Budget alerts</dt><dd>USD {health.budget_alerts_usd.join(' · USD ')}</dd>
    </dl>
  );
}
