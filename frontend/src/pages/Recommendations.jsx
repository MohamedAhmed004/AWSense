import { useEffect, useState } from 'react'
import { getRecommendations, actOnRecommendation } from '../services/api.js'
import { Async, Pill, useAsync, money } from '../components/ui.jsx'

const CATEGORY = {
  cost: 'bg-accent/15 text-accent ring-accent/30',
  security: 'bg-crit/15 text-crit ring-crit/30',
  backup: 'bg-med/15 text-med ring-med/30',
}
const STATE = {
  approved: { label: 'Approved', cls: 'bg-low/15 text-low ring-low/30' },
  dismissed: { label: 'Dismissed', cls: 'bg-raised text-muted ring-line' },
}

function List({ initial }) {
  const [items, setItems] = useState(initial)
  const [error, setError] = useState(null)
  useEffect(() => setItems(initial), [initial])

  const act = async (id, state) => {
    setError(null)
    try {
      await actOnRecommendation(id, state)
      setItems((prev) => prev.map((r) => (r.id === id ? { ...r, state } : r)))
    } catch (e) {
      setError(`Could not save your choice: ${e.message}`)
    }
  }

  const pending = items.filter((r) => r.state === 'pending')
  const savings = pending.reduce((s, r) => s + r.estimatedSavings, 0)

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">
        {pending.length} pending, worth <span className="font-semibold text-low">{money(savings)}</span> a month.
      </p>
      {error && <p className="rounded-md bg-crit/10 p-3 text-sm text-crit" role="alert">{error}</p>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((r) => (
          <article key={r.id} className={`flex flex-col rounded-lg border border-line bg-panel p-5 ${r.state === 'dismissed' ? 'opacity-60' : ''}`}>
            <div className="flex items-center justify-between">
              <Pill className={CATEGORY[r.category]}>{r.category[0].toUpperCase() + r.category.slice(1)}</Pill>
              {STATE[r.state] && <Pill className={STATE[r.state].cls}>{STATE[r.state].label}</Pill>}
            </div>
            <h3 className="mt-3 font-semibold leading-snug">{r.title}</h3>
            <p className="mt-1 text-xs text-muted">{r.resourceId}</p>
            <p className="mt-3 flex-1 text-sm leading-relaxed text-muted">{r.action}</p>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-muted">Estimated savings</dt><dd className="text-lg font-semibold">{r.estimatedSavings ? `${money(r.estimatedSavings)}/mo` : 'Risk reduction'}</dd></div>
              <div><dt className="text-muted">Confidence</dt><dd className="text-lg font-semibold">{Math.round(r.confidence * 100)}%</dd></div>
            </dl>
            <div className="mt-4 flex gap-2">
              {r.state === 'pending' ? (
                <>
                  <button onClick={() => act(r.id, 'approved')} className="flex-1 rounded-md bg-accent px-3 py-2 text-sm font-semibold text-ink hover:brightness-110">Approve</button>
                  <button onClick={() => act(r.id, 'dismissed')} className="flex-1 rounded-md bg-raised px-3 py-2 text-sm font-medium hover:bg-line">Dismiss</button>
                </>
              ) : (
                <button onClick={() => act(r.id, 'pending')} className="rounded-md bg-raised px-3 py-2 text-sm font-medium hover:bg-line">Undo</button>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

export default function Recommendations() {
  const state = useAsync(getRecommendations)
  return <Async state={state}>{(data) => <List initial={data} />}</Async>
}
