import { useEffect, useState } from 'react'
import { getAlerts, updateAlertStatus } from '../services/api.js'
import {
  Async,
  Card,
  Pill,
  SeverityBadge,
  SEVERITY,
  SEVERITY_TEXT,
  SEVERITY_BAR,
  levelFor,
  useAsync,
} from '../components/ui.jsx'

const STATUS_BADGE = {
  open: { label: 'Open', cls: 'bg-high/15 text-high ring-high/30' },
  investigating: { label: 'Investigating', cls: 'bg-accent/15 text-accent ring-accent/30' },
  resolved: { label: 'Resolved', cls: 'bg-low/15 text-low ring-low/30' },
  dismissed: { label: 'Dismissed', cls: 'bg-raised text-muted ring-line' },
}

const STATUS_ACTIONS = {
  open: [
    { label: 'Investigating', status: 'investigating', primary: true },
    { label: 'Resolve', status: 'resolved' },
    { label: 'Dismiss', status: 'dismissed' },
  ],
  investigating: [
    { label: 'Resolve', status: 'resolved', primary: true },
    { label: 'Dismiss', status: 'dismissed' },
    { label: 'Reopen', status: 'open' },
  ],
  resolved: [{ label: 'Reopen', status: 'open' }],
  dismissed: [{ label: 'Reopen', status: 'open' }],
}

function SecurityFeed({ initial }) {
  const [items, setItems] = useState(initial)
  const [selectedId, setSelectedId] = useState(null)
  const [pending, setPending] = useState({})
  const [actionErrors, setActionErrors] = useState({})

  useEffect(() => setItems(initial), [initial])

  const a = items.find((x) => x.id === selectedId) || items[0]
  const level = a ? levelFor(a.riskScore) : 'LOW'

  const handleStatusChange = async (alertId, nextStatus) => {
    setActionErrors((prev) => {
      const next = { ...prev }
      delete next[alertId]
      return next
    })
    setPending((p) => ({ ...p, [alertId]: true }))
    try {
      await updateAlertStatus(alertId, nextStatus)
      setItems((prev) =>
        prev.map((x) => (x.id === alertId ? { ...x, status: nextStatus } : x)),
      )
    } catch (e) {
      setActionErrors((prev) => ({ ...prev, [alertId]: e.message || String(e) }))
    } finally {
      setPending((p) => {
        const n = { ...p }
        delete n[alertId]
        return n
      })
    }
  }

  if (!a) {
    return <p className="text-sm text-muted">No security alerts found.</p>
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
      <ul className="space-y-3" aria-label="Alert feed">
        {items.map((x) => (
          <li key={x.id}>
            <button
              onClick={() => setSelectedId(x.id)}
              aria-current={x.id === a.id}
              className={`w-full rounded-lg border p-4 text-left transition-colors ${
                x.id === a.id
                  ? 'border-accent bg-raised'
                  : 'border-line bg-panel hover:bg-raised/50'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <SeverityBadge level={x.severity} />
                <span className={`text-sm font-semibold ${SEVERITY_TEXT[x.severity]}`}>
                  {x.riskScore}
                </span>
              </div>
              <p className="mt-2 text-sm font-medium leading-snug">{x.title}</p>
              <p className="mt-1 text-xs text-muted">
                {x.id} · <span className="capitalize">{x.status}</span> ·{' '}
                {new Date(x.timestamp).toISOString().slice(11, 16)} UTC
              </p>
            </button>
          </li>
        ))}
      </ul>

      <div className="space-y-6">
        <Card
          title={a.id}
          aside={
            <Pill className={STATUS_BADGE[a.status]?.cls || 'bg-raised text-muted ring-line'}>
              {STATUS_BADGE[a.status]?.label || a.status}
            </Pill>
          }
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <p className="text-lg font-semibold leading-snug">{a.title}</p>
            <div className="flex flex-wrap items-center gap-2">
              {actionErrors[a.id] && (
                <span className="rounded-md bg-crit/10 px-2.5 py-1 text-xs text-crit" role="alert">
                  {actionErrors[a.id]}
                </span>
              )}
              {(STATUS_ACTIONS[a.status] || []).map((btn) => (
                <button
                  key={btn.label}
                  type="button"
                  disabled={!!pending[a.id]}
                  onClick={() => handleStatusChange(a.id, btn.status)}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    btn.primary
                      ? 'bg-accent text-ink hover:brightness-110'
                      : 'bg-raised text-text hover:bg-line'
                  }`}
                >
                  {btn.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5 grid gap-6 md:grid-cols-[10rem_1fr]">
            <div>
              <p className="text-sm text-muted">Risk score</p>
              <p className={`text-5xl font-semibold ${SEVERITY_TEXT[level]}`}>{a.riskScore}</p>
              <span
                className={`mt-2 inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${SEVERITY[level]}`}
              >
                {level[0] + level.slice(1).toLowerCase()}
              </span>
            </div>
            <ul className="space-y-3">
              {a.breakdown.map((b) => (
                <li key={b.key}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span>
                      {b.label}{' '}
                      <span className="text-muted">(weight {Math.round(b.weight * 100)}%)</span>
                    </span>
                    <span>{b.value}</span>
                  </div>
                  <div className="h-2 rounded-full bg-raised">
                    <div
                      className={`h-2 rounded-full ${SEVERITY_BAR[levelFor(b.value)]}`}
                      style={{ width: `${b.value}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <Card title="AI incident summary">
          <p className="max-w-prose text-sm leading-relaxed">{a.summary}</p>
          <p className="mt-5 text-sm font-semibold">What to do</p>
          <ol className="mt-2 max-w-prose list-decimal space-y-1.5 pl-5 text-sm leading-relaxed">
            {a.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </Card>

        <Card title="Correlated events">
          <ol className="space-y-3">
            {a.events.map((e, i) => (
              <li key={i} className="flex gap-4 text-sm">
                <span className="w-12 shrink-0 text-muted">{e.time}</span>
                <span className="flex-1">{e.text}</span>
                <span className="shrink-0 text-xs text-muted">{e.source}</span>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  )
}

export default function Security() {
  const state = useAsync(getAlerts)
  return <Async state={state}>{(alerts) => <SecurityFeed initial={alerts} />}</Async>
}
