import { useState } from 'react'
import { getAlerts } from '../services/api.js'
import { Async, Card, SeverityBadge, SEVERITY, SEVERITY_TEXT, SEVERITY_BAR, levelFor, useAsync } from '../components/ui.jsx'

export default function Security() {
  const state = useAsync(getAlerts)
  const [selectedId, setSelectedId] = useState(null)

  return (
    <Async state={state}>
      {(alerts) => {
        const a = alerts.find((x) => x.id === selectedId) || alerts[0]
        const level = levelFor(a.riskScore)
        return (
          <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
            <ul className="space-y-3" aria-label="Alert feed">
              {alerts.map((x) => (
                <li key={x.id}>
                  <button
                    onClick={() => setSelectedId(x.id)}
                    aria-current={x.id === a.id}
                    className={`w-full rounded-lg border p-4 text-left transition-colors ${x.id === a.id ? 'border-accent bg-raised' : 'border-line bg-panel hover:bg-raised/50'}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <SeverityBadge level={x.severity} />
                      <span className={`text-sm font-semibold ${SEVERITY_TEXT[x.severity]}`}>{x.riskScore}</span>
                    </div>
                    <p className="mt-2 text-sm font-medium leading-snug">{x.title}</p>
                    <p className="mt-1 text-xs text-muted">{x.id} · {x.status} · {new Date(x.timestamp).toISOString().slice(11, 16)} UTC</p>
                  </button>
                </li>
              ))}
            </ul>

            <div className="space-y-6">
              <Card title={a.id}>
                <p className="text-lg font-semibold leading-snug">{a.title}</p>
                <div className="mt-5 grid gap-6 md:grid-cols-[10rem_1fr]">
                  <div>
                    <p className="text-sm text-muted">Risk score</p>
                    <p className={`text-5xl font-semibold ${SEVERITY_TEXT[level]}`}>{a.riskScore}</p>
                    <span className={`mt-2 inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${SEVERITY[level]}`}>{level[0] + level.slice(1).toLowerCase()}</span>
                  </div>
                  <ul className="space-y-3">
                    {a.breakdown.map((b) => (
                      <li key={b.key}>
                        <div className="mb-1 flex justify-between text-sm">
                          <span>{b.label} <span className="text-muted">(weight {Math.round(b.weight * 100)}%)</span></span>
                          <span>{b.value}</span>
                        </div>
                        <div className="h-2 rounded-full bg-raised"><div className={`h-2 rounded-full ${SEVERITY_BAR[levelFor(b.value)]}`} style={{ width: `${b.value}%` }} /></div>
                      </li>
                    ))}
                  </ul>
                </div>
              </Card>

              <Card title="AI incident summary">
                <p className="max-w-prose text-sm leading-relaxed">{a.summary}</p>
                <p className="mt-5 text-sm font-semibold">What to do</p>
                <ol className="mt-2 max-w-prose list-decimal space-y-1.5 pl-5 text-sm leading-relaxed">
                  {a.steps.map((s) => <li key={s}>{s}</li>)}
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
      }}
    </Async>
  )
}
