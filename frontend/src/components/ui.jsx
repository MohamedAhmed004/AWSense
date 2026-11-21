import { useCallback, useEffect, useState } from 'react'

export const SEVERITY = {
  CRITICAL: 'bg-crit/15 text-crit ring-crit/30',
  HIGH: 'bg-high/15 text-high ring-high/30',
  MEDIUM: 'bg-med/15 text-med ring-med/30',
  LOW: 'bg-low/15 text-low ring-low/30',
}
export const SEVERITY_TEXT = { CRITICAL: 'text-crit', HIGH: 'text-high', MEDIUM: 'text-med', LOW: 'text-low' }
export const SEVERITY_BAR = { CRITICAL: 'bg-crit', HIGH: 'bg-high', MEDIUM: 'bg-med', LOW: 'bg-low' }

export const levelFor = (score) => (score >= 85 ? 'CRITICAL' : score >= 65 ? 'HIGH' : score >= 35 ? 'MEDIUM' : 'LOW')
export const money = (n) => `$${Math.round(n).toLocaleString('en-US')}`
export const compact = (n) => Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n)

export function Pill({ className = '', children }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}>
      {children}
    </span>
  )
}

export const SeverityBadge = ({ level }) => <Pill className={SEVERITY[level]}>{level[0] + level.slice(1).toLowerCase()}</Pill>

export function Card({ title, aside, children, className = '' }) {
  return (
    <section className={`rounded-lg border border-line bg-panel ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {aside}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function Stat({ label, value, note, valueClass = '' }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className={`mt-2 text-3xl font-semibold ${valueClass}`}>{value}</p>
      {note && <p className="mt-1 text-sm text-muted">{note}</p>}
    </div>
  )
}

export function useAsync(fn) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const run = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }))
  }, [fn])
  useEffect(run, [run])
  return { ...state, reload: run }
}

export function Async({ state, children }) {
  if (state.loading && !state.data) return <p className="text-sm text-muted" role="status">Loading data…</p>
  if (state.error)
    return (
      <div className="rounded-lg border border-crit/30 bg-crit/10 p-5 text-sm" role="alert">
        <p className="font-medium text-crit">Could not load this page</p>
        <p className="mt-1 text-muted">{state.error.message}. Check that the backend is running at the API URL in your .env file, or set VITE_USE_MOCK=true.</p>
        <button onClick={state.reload} className="mt-3 rounded-md bg-raised px-3 py-1.5 font-medium hover:bg-line">Try again</button>
      </div>
    )
  return children(state.data)
}

export const chartTooltip = {
  contentStyle: { background: '#1B2A3E', border: '1px solid #26374D', borderRadius: 8, color: '#E5EBF3', fontSize: 13 },
  labelStyle: { color: '#8B9BB0' },
}
