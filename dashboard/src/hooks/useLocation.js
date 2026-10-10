import { useEffect, useState } from 'react';

export default function useLocation() {
  const [params, setParams] = useState(() => new URLSearchParams(location.search));
  useEffect(() => {
    const pop = () => setParams(new URLSearchParams(location.search));
    addEventListener('popstate', pop);
    return () => removeEventListener('popstate', pop);
  }, []);
  const change = (values, { replace = false } = {}) => {
    const next = new URLSearchParams(location.search);
    Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    if (next.toString() === location.search.slice(1)) return;
    history[replace ? 'replaceState' : 'pushState'](null, '', `${location.pathname}?${next}`);
    setParams(next);
  };
  return [params, change];
}
