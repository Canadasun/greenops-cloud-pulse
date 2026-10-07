export default function QueryState({ query, label }) {
  if (query.error) return <div className="query-error" role="alert">
    <span>{label}: {query.error} {query.data != null ? 'Showing stale data.' : 'Data unavailable.'}</span>
    {query.updatedAt && <time dateTime={new Date(query.updatedAt).toISOString()}>Last success: {new Date(query.updatedAt).toLocaleTimeString()}</time>}
    <button onClick={query.refresh} disabled={query.loading}>Retry {label.toLowerCase()}</button>
  </div>;
  if (query.data == null && query.loading) return <p className="muted" role="status">Loading {label.toLowerCase()}…</p>;
  return query.updatedAt ? <p className="query-freshness muted small">{query.loading ? 'Refreshing · ' : ''}Last success: <time dateTime={new Date(query.updatedAt).toISOString()}>{new Date(query.updatedAt).toLocaleTimeString()}</time></p> : null;
}
